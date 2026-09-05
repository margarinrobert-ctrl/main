"""V53 -- read the grid for UNDERFITTING, not for a top row.

The operational definition used here: a configuration is more underfit when it has FEWER active
conditions, no tuned threshold, and its research score SURVIVES to the locked block. The third of
those is measurable across the whole population -- corr(research R, locked R) within a slice is an
overfitting diagnostic that needs no single cell to be named.
"""
from __future__ import annotations
import sys
import numpy as np, pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/v53")
import run_v53 as R    # noqa: E402
import v53abs as A     # noqa: E402

MIN_N = 100
D = pd.read_parquet("results/v53/v53_grid.parquet")
lab = [m[0] for m in R.ABS_MODES]
D["abs_side"] = [("off" if R.ABS_MODES[i][1] is None else R.ABS_MODES[i][1]) for i in D.ab]
D["abs_ltf"] = [(0 if R.ABS_MODES[i][2] is None else R.ABS_MODES[i][2]) for i in D.ab]
D["abs_k"] = [(0 if R.ABS_MODES[i][3] is None else R.ABS_MODES[i][3][0]) for i in D.ab]
D["abs_w"] = [(0 if R.ABS_MODES[i][3] is None else R.ABS_MODES[i][3][1]) for i in D.ab]
D["nfilt"] = (D.ma > 0).astype(int) + (D.cx > 0).astype(int) + (D.ab > 0).astype(int)
q = D[(D.n >= MIN_N) & (D.nlk >= 30)].copy()

print("=" * 100)
print("  THE GRID -- deliberately small, and every tuned number removed")
print("=" * 100)
print(f"  {len(D):,} configurations = 4 timeframes x 4 entry x 4 exit x 4 stop x 5 MA200 x 3 cross"
      f" x {len(R.ABS_MODES)} absorption")
print("  absorption carries NO free threshold: volume >= its own rolling mean (ratio 1.0) and the")
print("  close on the wrong side of the bar's MIDPOINT (0.5). Only the mean's window is swept, and")
print("  only to show the answer does not depend on it.")
print(f"  scorable (>= {MIN_N} research and >= 30 locked trades): {len(q):,} ({100*len(q)/len(D):.1f}%)")
print(f"  positive research R: {100*(q.R > 0).mean():.1f}%   median R {q.R.median():+.4f}   "
      f"median PF {q.pf.median():.3f}")

print("\n" + "=" * 100)
print("  THE UNDERFITTING READING -- by NUMBER OF ACTIVE CONDITIONS")
print("=" * 100)
print(f"  {'filters':<9} {'cells':>7} {'research R':>11} {'locked R':>10} {'decay':>8} "
      f"{'corr(res,lk)':>13} {'median n':>9} {'pos lk':>7}")
for k, g in q.groupby("nfilt"):
    c = np.corrcoef(g.R, g.Rlk)[0, 1] if len(g) > 5 else np.nan
    print(f"  {k:<9} {len(g):>7} {g.R.mean():+11.4f} {g.Rlk.mean():+10.4f} "
          f"{g.Rlk.mean()-g.R.mean():+8.4f} {c:+13.4f} {int(g.n.median()):>9} "
          f"{100*(g.Rlk > 0).mean():6.1f}%")
print("\n  corr(research, locked) FALLING as conditions are added is the overfitting signature:")
print("  each extra condition buys research score that does not survive the split.")

print("\n" + "=" * 100)
print("  MARGINAL AVERAGE PER AXIS -- research and locked side by side")
print("=" * 100)
LB = {"ma": R.MA_MODES, "cx": R.CX_MODES}
for ax in ("tf", "entN", "exitN", "stopN", "ma", "cx", "abs_side", "abs_ltf", "abs_k", "abs_w"):
    g = q.groupby(ax).agg(cells=("R", "size"), res=("R", "mean"), lk=("Rlk", "mean"),
                          pf=("pf", "median"))
    print(f"\n  {ax}")
    for k, r in g.iterrows():
        nm = LB[ax][int(k)] if ax in LB else str(k)
        print(f"    {nm:<20} cells {int(r.cells):>6}  research {r.res:+.4f}  locked {r.lk:+.4f}"
              f"  median PF {r.pf:.3f}")

print("\n" + "=" * 100)
print("  THE ABSORPTION AXIS ON ITS OWN -- side x lower timeframe, locked block")
print("=" * 100)
a = q[q.abs_side != "off"]
piv = a.pivot_table(index="abs_ltf", columns="abs_side", values="Rlk", aggfunc="mean")
base = q[q.abs_side == "off"].Rlk.mean()
print(f"  absorption OFF, locked mean R = {base:+.4f}")
for ltf, row in piv.iterrows():
    print(f"    {int(ltf):>3}m   buyer {row.get('buyer', np.nan):+.4f}   "
          f"seller {row.get('seller', np.nan):+.4f}")
q.to_parquet("results/v53/v53_scorable.parquet", index=False)
