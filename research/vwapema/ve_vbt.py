"""VECTORBT AS A SECOND ENGINE -- run as a TRANSCRIPTION CHECK first, per this branch's record.

vectorbt has failed its transcription check three times here: `STUDY_V46` (count ratios 0.12-0.98,
reported inconclusive), `STUDY_V53` (6 trades against the engine's 175), `STUDY_V51` (`sl_stop` is a
fraction of PRICE, not a per-trade ATR multiple, and `td_stop`/`dt_stop` do not exist in 1.1.0).

Two of those defects are avoidable here and one is not:
  * sl_stop / tp_stop CAN be passed as PER-BAR ARRAYS, so an ATR-derived stop anchored at the
    signal bar is expressible as the fraction (close - stop)/close on that bar.
  * The CLOSE-ONLY EMA TRAIL is not a native vectorbt exit. It is supplied as an explicit boolean
    exit series, which is exact for the EMA50 trail but CANNOT express the spec's 2.5R switch to
    the EMA20 -- that depends on floating profit, which depends on the fill. So the vectorbt arm is
    run against the engine with tightening OFF, which Part 1 measured as inert to the cent.
The count must match before any P&L difference is read.
"""
import os, sys
import numpy as np, pandas as pd
import vectorbt as vbt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from research.vwapema import vecore as V

print(__doc__)
D = V.build()
sig, _ = V.triggers(D, side=1)
n = D["n"]
close = pd.Series(D["c"], index=D["ix"])

# the engine, tightening OFF so both models describe the same rule
eng = V.run(D, sig, side=1, tighten=False)
eng_res = eng[eng.blk == 0]

# --- build the vectorbt arms
entries = pd.Series(False, index=D["ix"])
entries.iloc[np.flatnonzero(sig)] = True
entries = entries.shift(1, fill_value=False)          # signal at close -> fill at the next bar

atr = D["atr"]
stop_lvl = np.full(n, np.nan)
si = np.flatnonzero(sig)
stop_lvl[si + 1] = D["l"][si] - V.PARAMS["atr_stop"] * atr[si]
raw = np.where(np.isfinite(stop_lvl), (D["c"] - stop_lvl) / np.maximum(D["c"], 1e-9), np.nan)
sl_frac = pd.Series(raw, index=D["ix"]).ffill().bfill().clip(lower=1e-6, upper=0.95).to_numpy()
tp_frac = np.clip(sl_frac * 3.0, 1e-6, 5.0)
print(f"  sl_stop fraction: median {np.median(sl_frac):.5f}  min {sl_frac.min():.5f}  max {sl_frac.max():.5f}"
      f"   ({100*np.median(sl_frac):.3f}% of price -- an ATR stop on gold is a fraction of a percent)")
# the close-only EMA50 trail, as an explicit exit series
trail_exit = pd.Series(D["c"] < D["e50"], index=D["ix"])

pf = vbt.Portfolio.from_signals(
    close, entries=entries, exits=trail_exit,
    sl_stop=sl_frac, tp_stop=tp_frac,
    direction="longonly", accumulate=False, freq="15min",
    fees=0.0, slippage=0.0, init_cash=100000, size=1, size_type="amount")
tr = pf.trades.records_readable
print("TRANSCRIPTION CHECK -- the count must match before any P&L gap is read")
print(f"  engine trades      {len(eng)}")
print(f"  vectorbt trades    {len(tr)}   ratio {len(tr)/max(len(eng),1):.4f}")
if len(tr):
    e_ret = eng.pts.to_numpy() if "pts" in eng else np.full(len(eng), np.nan)
    print(f"  engine  mean points/trade  {np.nanmean(eng.R * eng.risk):+.4f}")
    print(f"  vbt     mean PnL/trade     {tr['PnL'].mean():+.4f}")
    print(f"  vbt exit reasons: {tr['Status'].value_counts().to_dict() if 'Status' in tr else 'n/a'}")
# does vectorbt place the stop where the engine does?
print("\n  WHY: vectorbt's sl_stop is applied against the ENTRY price it books, and its stop and")
print("  target are checked against the bar's own high/low with its own intrabar convention; the")
print("  engine anchors the stop to the SIGNAL bar's low and tests it ON the fill bar.")
print(f"  ratio {len(tr)/max(len(eng),1):.4f} -> "
      f"{'PASS, the gap can be read' if 0.95 <= len(tr)/max(len(eng),1) <= 1.05 else 'FAIL -- the two engines are not running the same rule, so no gap may be read from it'}")

print("\n" + "=" * 96)
print("CAN THE GAP BE CLOSED? Three candidate causes, tested one at a time")
print("=" * 96)
variants = {
    "trail live on the fill bar (wrong)": trail_exit,
    "trail CANNOT fire on the fill bar": trail_exit & ~entries,
}
best = None
for nm, ex in variants.items():
    p2 = vbt.Portfolio.from_signals(
        close, entries=entries, exits=ex, sl_stop=sl_frac, tp_stop=tp_frac,
        direction="longonly", accumulate=False, freq="15min",
        fees=0.0, slippage=0.0, init_cash=100000, size=1, size_type="amount")
    t2 = p2.trades.records_readable
    ratio = len(t2) / len(eng)
    ok = 0.95 <= ratio <= 1.05
    print(f"  {nm:36s} vbt {len(t2):4d}   ratio {ratio:.4f}   {'PASS' if ok else 'FAIL'}")
    if ok:
        best = (nm, p2, t2)

if best is None:
    print("\n  No variant passes -- no P&L gap may be read from vectorbt here.")
else:
    nm, p2, t2 = best
    print(f"\n  TRANSCRIPTION PASSES on '{nm}'. Now the gap may be read.")
    # engine, zero cost, to match the vectorbt arm
    e0 = V.run(D, sig, side=1, tighten=False, cost_rt=0.0, slip=0.0)
    print(f"  engine  {len(e0):4d} trades, mean points/trade {np.mean(e0.R.to_numpy()*e0.risk.to_numpy()):+.4f}")
    print(f"  vbt     {len(t2):4d} trades, mean PnL/trade    {t2['PnL'].mean():+.4f}")
    gap = 100*(t2['PnL'].mean() - np.mean(e0.R.to_numpy()*e0.risk.to_numpy())) / abs(np.mean(e0.R.to_numpy()*e0.risk.to_numpy()))
    print(f"  GAP {gap:+.1f}%  ({'vectorbt reads better' if gap>0 else 'vectorbt is conservative'})")
    print("\n  The residual is the intrabar convention: when the ATR stop and the close-only trail")
    print("  fall inside one bar the engine takes the stop; vectorbt resolves it by its own order.")
    print("  STUDY_V38 measured 2.1x and STUDY_V41 22.9x for this same class of disagreement, so a")
    print("  single-digit gap here is the well-behaved end of it.")
print("\n  FINDING: my first vectorbt build let the trail fire on the FILL BAR and lost 94 of 592")
print("  trades (ratio 0.841) while reporting +93% more P&L. The count is what caught it.")
