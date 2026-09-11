"""What did 225,792 configurations actually buy?

The sweep is an experiment, not a parameter picker. The question it answers: if you search as wide
as you possibly can, select on the data you are allowed to see, and then look at data selection
never touched — what do you get?
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

path = sys.argv[1] if len(sys.argv) > 1 else "results/mega/mega.npz"
z = np.load(path)
g = pd.DataFrame({k: z[k] for k in z.files})
names = ["ib_minutes", "retr_pct", "stop_pct", "rr_mult", "side_mode", "break_buffer", "exit_mso"]
pd.set_option("display.width", 220)

print(f"{len(g):,} configurations\n")
MIN_N = 30
ok = (g.n_res >= MIN_N) & (g.n_val >= MIN_N) & (g.n_hold >= MIN_N)
w = g[ok].copy()
print(f"  {ok.sum():,} have >= {MIN_N} trades in each of research / validate / locked")
print(f"  research  P&L: mean ${w.d_res.mean():>9,.0f}   median ${w.d_res.median():>9,.0f}   best ${w.d_res.max():>10,.0f}")
print(f"  validate  P&L: mean ${w.d_val.mean():>9,.0f}   median ${w.d_val.median():>9,.0f}   best ${w.d_val.max():>10,.0f}")
print(f"  LOCKED    P&L: mean ${w.d_hold.mean():>9,.0f}   median ${w.d_hold.median():>9,.0f}   best ${w.d_hold.max():>10,.0f}")
print(f"  share profitable on the locked holdout: {(w.d_hold > 0).mean()*100:.1f}%")
print(f"  rank correlation research -> locked: {w.d_res.corr(w.d_hold, method='spearman'):+.3f}")
print(f"  rank correlation research -> validate: {w.d_res.corr(w.d_val, method='spearman'):+.3f}")

# ---- the honest experiment: select on research only, then look at LOCKED ----
print("\n  SELECT ON RESEARCH ONLY, THEN OPEN THE LOCKED HOLDOUT")
print(f"    {'search width':>14}{'median locked $':>18}{'mean locked $':>16}{'% profitable':>14}{'locked pctile':>15}")
rng = np.random.default_rng(11)
idx = w.index.to_numpy()
dres, dhold = w.d_res.to_numpy(), w.d_hold.to_numpy()
pos = {v: i for i, v in enumerate(idx)}
for W in (1, 10, 100, 1_000, 10_000, 50_000, len(idx)):
    if W > len(idx):
        break
    picks = []
    draws = 400 if W < len(idx) else 1
    for _ in range(draws):
        sel = rng.choice(len(idx), size=W, replace=False) if W < len(idx) else np.arange(len(idx))
        picks.append(sel[np.argmax(dres[sel])])
    hp = dhold[picks]
    pct = [(dhold < v).mean() * 100 for v in hp]
    print(f"    {W:>14,}{np.median(hp):>18,.0f}{np.mean(hp):>16,.0f}{(hp>0).mean()*100:>13.0f}%{np.median(pct):>15.1f}")

# ---- the single best configuration by research, examined ----
best = w.loc[w.d_res.idxmax()]
print(f"\n  the single best of {len(w):,} on research:")
print("    " + "  ".join(f"{k}={best[k]:g}" for k in names))
print(f"    research ${best.d_res:>9,.0f} ({int(best.n_res)} trades)   "
      f"validate ${best.d_val:>9,.0f} ({int(best.n_val)})   LOCKED ${best.d_hold:>9,.0f} ({int(best.n_hold)})")
print(f"    its locked-holdout percentile among all {len(w):,}: {(w.d_hold < best.d_hold).mean()*100:.1f}")

# ---- what a pre-specified configuration did, for comparison ----
v = g[(g.ib_minutes == 60) & (g.retr_pct == 50) & (g.stop_pct == 80) & (g.rr_mult == 2.0)
      & (g.side_mode == 0) & (g.break_buffer == 0) & (g.exit_mso == 150)]
if len(v):
    r = v.iloc[0]
    print(f"\n  the pre-specified v3 geometry (exit 150m, the nearest grid point to 11:59):")
    print(f"    research ${r.d_res:>9,.0f} ({int(r.n_res)} trades)   validate ${r.d_val:>9,.0f} ({int(r.n_val)})   "
          f"LOCKED ${r.d_hold:>9,.0f} ({int(r.n_hold)})")
    print(f"    its locked-holdout percentile: {(w.d_hold < r.d_hold).mean()*100:.1f}")

# ---- which axis actually matters, on the locked holdout ----
print("\n  marginal effect of each axis on LOCKED holdout P&L (mean over all configurations)")
for k in names:
    med = w.groupby(k).d_hold.median()
    line = "  ".join(f"{lvl:g}:{val:>8,.0f}" for lvl, val in med.items())
    print(f"    {k:<13} {line}")
