"""M7 -- vectorbt as a SECOND ENGINE on US100 and US30, run as a TRANSCRIPTION CHECK first.

Identical construction to `ve_vbt.py` on gold, and the same rule applies: THE TRADE COUNT MUST
MATCH before any P&L difference is read. vectorbt has failed transcription three times on this
branch (STUDY_V46, V51, V53) and the two avoidable defects are handled the same way here --
`sl_stop`/`tp_stop` as PER-BAR ARRAYS so an ATR stop anchored at the signal bar is expressible, and
the close-only EMA trail supplied as an explicit boolean exit that CANNOT fire on the fill bar.
The 2.5R switch to the EMA20 is not expressible (it depends on floating profit, which depends on
the fill), so both arms are run with tightening OFF -- measured inert to the cent in M1.
"""
import os, sys
import numpy as np, pandas as pd
import vectorbt as vbt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vecore as V, ve_markets as M

print(__doc__)
rows = []
for mk in ("US100", "US30", "US30_ISO"):
    D = M.build(mk)
    sig, _ = V.triggers(D, side=1)
    n = D["n"]
    close = pd.Series(D["c"], index=D["ix"])
    eng = M.run(D, sig, side=1, tighten=False, cost_rt=0.0, slip=0.0)

    entries = pd.Series(False, index=D["ix"])
    entries.iloc[np.flatnonzero(sig)] = True
    entries = entries.shift(1, fill_value=False)
    si = np.flatnonzero(sig)
    stop_lvl = np.full(n, np.nan)
    keep = si[si + 1 < n]
    stop_lvl[keep + 1] = D["l"][keep] - V.PARAMS["atr_stop"] * D["atr"][keep]
    raw = np.where(np.isfinite(stop_lvl), (D["c"] - stop_lvl) / np.maximum(D["c"], 1e-9), np.nan)
    sl = pd.Series(raw, index=D["ix"]).ffill().bfill().clip(lower=1e-6, upper=0.95).to_numpy()
    tp = np.clip(sl * 3.0, 1e-6, 5.0)
    trail = pd.Series(D["c"] < D["e50"], index=D["ix"])

    for nm, ex in (("trail live on the fill bar (wrong)", trail),
                   ("trail CANNOT fire on the fill bar", trail & ~entries)):
        pf = vbt.Portfolio.from_signals(close, entries=entries, exits=ex, sl_stop=sl, tp_stop=tp,
                                        direction="longonly", accumulate=False, freq="15min",
                                        fees=0.0, slippage=0.0, init_cash=1_000_000, size=1,
                                        size_type="amount")
        t = pf.trades.records_readable
        ratio = len(t) / max(len(eng), 1)
        epts = float(np.mean(eng.R.to_numpy() * eng.risk.to_numpy()))
        vpts = float(t["PnL"].mean()) if len(t) else np.nan
        rows.append(dict(feed=mk, variant=nm, engine_n=len(eng), vbt_n=len(t),
                         ratio=round(ratio, 4), pass_=0.95 <= ratio <= 1.05,
                         engine_pts=round(epts, 3), vbt_pts=round(vpts, 3),
                         gap_pct=round(100 * (vpts - epts) / abs(epts), 1) if np.isfinite(vpts) else np.nan))
T = pd.DataFrame(rows)
print(T.to_string(index=False))
T.to_csv("results/vwapema/m7_vbt.csv", index=False)
print("\nRead the `ratio` column first. A gap read from a FAILED transcription is a statement about")
print("two different rules, not about the execution convention (STUDY_V46 was reported inconclusive")
print("for exactly that reason).")
