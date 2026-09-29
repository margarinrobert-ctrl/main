"""V51 gate 3 -- the POPULATION before any row is named, and every axis read by its MARGINAL
average. Selection uses US100L's first 70% ONLY. US100L's last 30% and the whole of US30L are held
back and are not touched here."""
from __future__ import annotations
import sys
import numpy as np, pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/v51")
import v51feat as V     # noqa: E402

MIN_N = 100
A = pd.read_parquet("results/v51/v51_grid_base.parquet")
S = A[(A.market == "US100L")].copy()

print("=" * 100)
print("  THE GRID")
print("=" * 100)
print(f"  {len(A):,} configurations = {len(V.ENT_N)} entry x {len(V.EXIT_N)} exit x {len(V.STOP_N)}"
      f" stop x {len(V.MA200_MODES)} MA200 x {len(V.CROSS_MODES)} cross x"
      f" {len(V.VOL_MULT) * len(V.ABS_MODES)} absorption x {len(V.SESS)} session x 3 timeframes"
      f" x 2 markets")
print(f"  search market US100L, first 70% of bars: {len(S):,} cells")
q = S[S.n >= MIN_N]
print(f"  cells with >= {MIN_N} research trades: {len(q):,} ({100*len(q)/len(S):.1f}%)")
print(f"  the other {100*(1-len(q)/len(S)):.1f}% are too thin to score -- a filter stack that keeps"
      f" 1% of signals leaves n=3, and\n  '100% win rate' on n=3 has a Clopper-Pearson lower bound"
      f" of 29.2%")

print("\n" + "=" * 100)
print("  GATE 3 -- THE SHARE PROFITABLE, before any top row")
print("=" * 100)
print(f"  positive mean R : {int((q.R > 0).sum()):,} of {len(q):,} = {100*(q.R > 0).mean():.1f}%")
print(f"  PF > 1.2        : {int((q.pf > 1.2).sum()):,} = {100*(q.pf > 1.2).mean():.1f}%")
print(f"  PF > 1.5        : {int((q.pf > 1.5).sum()):,} = {100*(q.pf > 1.5).mean():.1f}%")
print(f"  median mean R {q.R.median():+.4f}   median PF {q.pf.median():.3f}   "
      f"median n {int(q.n.median())}")
print(f"  So the best cell is the maximum of ~{int((q.R > 0).sum()):,} positive draws.")

print("\n" + "=" * 100)
print("  MARGINAL AVERAGE PER AXIS -- read this, never the top cell")
print("=" * 100)
LBL = dict(ma=V.MA200_MODES, cx=V.CROSS_MODES, ss=[f"{V.WINDOWS[w][0]//60:02d}:{V.WINDOWS[w][0]%60:02d}"
           f"-{V.WINDOWS[w][1]//60:02d}:{V.WINDOWS[w][1]%60:02d}" + (" flat" if f else "")
           for (w, f) in V.SESS])
AB_LBL = [f"v{m}.{a}" for m in V.VOL_MULT for a in V.ABS_MODES]
for ax, lbl in (("tf", None), ("entN", None), ("exitN", None), ("stopN", None),
                ("ma", LBL["ma"]), ("cx", LBL["cx"]), ("ab", AB_LBL), ("ss", LBL["ss"])):
    g = q.groupby(ax).agg(cells=("R", "size"), R=("R", "mean"), pf=("pf", "median"),
                          pos=("R", lambda s: 100.0 * (s > 0).mean()), n=("n", "median"))
    print(f"\n  {ax}")
    for k, r in g.iterrows():
        name = lbl[int(k)] if lbl is not None else str(k)
        print(f"    {name:<16} cells {int(r.cells):>6}  mean R {r.R:+.4f}  median PF {r.pf:.3f}"
              f"  positive {r.pos:5.1f}%  median n {int(r.n)}")

print("\n" + "=" * 100)
print("  TOP-1000 CONSENSUS -- what the best cells AGREE on, which is the only readable part")
print("=" * 100)
top = q.sort_values("R", ascending=False).head(1000)
for ax, lbl in (("tf", None), ("entN", None), ("exitN", None), ("stopN", None),
                ("ma", LBL["ma"]), ("cx", LBL["cx"]), ("ab", AB_LBL), ("ss", LBL["ss"])):
    vc = top[ax].value_counts(normalize=True)
    base = q[ax].value_counts(normalize=True)
    k = vc.index[0]
    name = lbl[int(k)] if lbl is not None else str(k)
    print(f"  {ax:<6} modal {name:<16} {100*vc.iloc[0]:5.1f}% of the top 1000  "
          f"against {100*base.get(k, 0):5.1f}% of the population")
print(f"\n  top-1000 median n {int(top.n.median())}, median PF {top.pf.median():.3f}, "
      f"median R {top.R.median():+.4f}")
S.to_parquet("results/v51/v51_search.parquet", index=False)
