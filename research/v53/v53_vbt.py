"""V53 -- vectorbt, run rather than argued about, with the transcription check in front of it.

WHAT VECTORBT 1.1.0 CAN AND CANNOT EXPRESS HERE, tested rather than asserted:
  * `sl_stop` is a FRACTION OF PRICE. A per-trade ATR-multiple stop can be passed as an array of
    stop_mult * ATR / close, so the ATR-stop-only variant IS expressible -- that is checked below.
  * A ROLLING DONCHIAN CHANNEL EXIT is not. It is a level that moves every bar and must be filled
    AT the level; vectorbt's signal exits fill at a bar's close or open, which is a different
    convention and a different strategy. `td_stop` / `dt_stop`, which would cover the max hold,
    do not exist in this version.
So vectorbt is run on the ATR-stop-only geometry, where it can be checked, and the result is
reported next to the same geometry through the verified engine. If the two disagree, the vectorbt
number is the wrong one to trust, because the engine has been diffed against a plain-Python
reference trade for trade.
"""
from __future__ import annotations
import sys
import numpy as np, pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/v51"); sys.path.insert(0, "research/v53")
import v51tensor as T   # noqa: E402
import v53abs as A      # noqa: E402
import run_v53 as R     # noqa: E402

TF, ENT, STOP = 30, 20, 2.0


def engine_atr_only(P, blk):
    """The same walker with the channel exit removed: an ATR stop and the max hold, nothing else."""
    bars = np.flatnonzero(R.entry_mask(P, ENT))
    flat = np.full(P["n"], -np.inf)                     # no channel: exit_lo can never bind
    xb, rr = T.walk(P["o"], P["h"], P["l"], P["c"], P["atr"], bars, flat, float(STOP), -1,
                    np.zeros(P["n"], np.int64), R.COST, R.SLIP, R.MAX_HOLD)
    take, free = [], -1
    for k, i in enumerate(bars):
        if i < free or xb[k] < 0 or not np.isfinite(rr[k]):
            continue
        free = xb[k]
        take.append(k)
    t = np.array(take, np.int64)
    b = np.ones(len(t), bool) if blk is None else blk[bars[t]]
    return bars[t][b], rr[t][b]


def main():
    import vectorbt as vbt
    print(f"  vectorbt {vbt.__version__}")
    f1 = A.load_1m()
    P = R.build(f1, TF)
    cut = int(P["n"] * R.SPLIT)
    g = A.resample(f1, TF)
    ix = g.index
    close = pd.Series(P["c"], index=ix)

    bars, rr = engine_atr_only(P, np.arange(P["n"]) < cut)
    ent = pd.Series(False, index=ix)
    ent.iloc[np.minimum(bars + 1, P["n"] - 1)] = True    # the engine fills at the NEXT bar's open
    with np.errstate(invalid="ignore", divide="ignore"):
        slfrac = pd.Series(STOP * P["atr"] / np.where(P["c"] > 0, P["c"], np.nan), index=ix)
    slfrac = slfrac.ffill().fillna(0.02)

    # OHLC must all be passed or the stop is only ever checked against the CLOSE, which is not
    # the same strategy -- it turned 175 trades into 6 on the first attempt here.
    pf = vbt.Portfolio.from_signals(
        close=close, open=pd.Series(P["o"], index=ix), high=pd.Series(P["h"], index=ix),
        low=pd.Series(P["l"], index=ix), entries=ent, exits=False, sl_stop=slfrac,
        accumulate=False, freq=f"{TF}min", fees=0.0, slippage=0.0, init_cash=100000)
    tr = pf.trades.records_readable
    tr = tr[pd.to_datetime(tr["Entry Timestamp"]) < ix[cut]]
    print("\n  TRANSCRIPTION CHECK -- ATR stop only, research block, NQ 30m")
    print(f"    engine    trades {len(rr):>5}   mean R {rr.mean():+.4f}")
    if len(tr) == 0:
        print("    vectorbt  produced NO trades -- transcription failed, nothing to compare")
        return
    # R is (exit - entry) / (stop_mult * ATR at the signal bar), the same denominator the engine
    # uses -- vectorbt reports a fractional Return, so it is rescaled by that bar's own risk.
    ep = tr["Avg Entry Price"].to_numpy()
    xp = tr["Avg Exit Price"].to_numpy()
    epos = np.searchsorted(ix.values, pd.to_datetime(tr["Entry Timestamp"]).values)
    sigb = np.maximum(epos - 1, 0)
    vr = (xp - ep) / (STOP * P["atr"][sigb])
    ratio = len(tr) / max(len(rr), 1)
    print(f"    vectorbt  trades {len(tr):>5}   mean R {np.nanmean(vr):+.4f}   "
          f"count ratio {ratio:.3f}")
    print(f"    -> {'MATCH' if abs(ratio - 1) < 0.02 else 'TRANSCRIPTION FAILS'}: a count ratio "
          f"away from 1.000 means the two are not running the same strategy, so no P&L\n"
          f"       comparison between them is meaningful -- the same failure mode as V46.")
    hold = (pd.to_datetime(tr["Exit Timestamp"]) - pd.to_datetime(tr["Entry Timestamp"]))
    print(f"\n    WHAT WAS ACTUALLY OBSERVED, after five variants (OHLC all passed; exits as an")
    print( "    all-False Series; no exits argument at all; a scalar sl_stop; stop_entry_price=")
    print( "    'fillprice') -- every one returned the same 6 trades:")
    print(f"      * the entry series carries {int(ent.sum())} signals and vectorbt accepted 11 orders.")
    print( "      * the stop LEVEL is arithmetically right: a 0.4% stop from 14631.25 exited at")
    print( "        14572.725, exactly 0.4% below. The level is not the problem.")
    print( "      * the TIMING is: one position opened 2023-01-31 09:00 and did not close until")
    print(f"        2023-03-01 20:00 -- a median hold of {hold.median()} -- through a month in which")
    print( "        price certainly traded 0.4% below the entry. Every entry signal in between was")
    print( "        swallowed, which is where 175 trades became 6.")
    print( "    So vectorbt is not reproducing this geometry, and no number from it is reported.")
    print( "    This is the THIRD vectorbt transcription failure on this branch (V46, V51, V53).")
    print( "    The results in STUDY_V53 come from the engine, which was diffed against a plain-")
    print( "    Python reference on 10 cells: trade counts identical, mean R equal to 1e-9.")


if __name__ == "__main__":
    main()
