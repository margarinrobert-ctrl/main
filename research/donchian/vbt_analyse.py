"""Read the max-combination sweep and ask the only question that matters:

    is the BEST cell better than what this same machinery produces from noise?

A 169,344-cell sweep will always have a best cell. Its value is not the number
but its position in the distribution the pipeline generates under a null. The
null is run through the IDENTICAL vectorbt pipeline on driftless synthetic bars,
so any convention difference against the study's own engine cancels.
"""
import numpy as np, pandas as pd, glob

R = pd.read_parquet("/home/user/main/data/donchian/vbt_sweep.parquet")
R = R[R.trades >= 100].copy()
print("=" * 112)
print(f"VECTORBT MAX-COMBINATION SWEEP - {len(R):,} cells with >=100 trades "
      f"(of {len(pd.read_parquet('/home/user/main/data/donchian/vbt_sweep.parquet')):,} run)")
print("  research block only; costs applied as trades x round turn in points")
print("=" * 112)

for (sym, side), g in R.groupby(["sym", "side"]):
    print(f"\n  {sym}  side {'long' if side>0 else 'short':<5}  cells {len(g):>6,}"
          f"  trades/cell median {g.trades.median():>5.0f}")
    q = g.exp.quantile([0, .05, .25, .5, .75, .95, 1.0])
    print(f"    expectancy (pts/trade)  min {q.iloc[0]:>+7.2f}  p5 {q.iloc[1]:>+6.2f}  "
          f"p25 {q.iloc[2]:>+6.2f}  med {q.iloc[3]:>+6.2f}  p75 {q.iloc[4]:>+6.2f}  "
          f"p95 {q.iloc[5]:>+6.2f}  MAX {q.iloc[6]:>+6.2f}")
    print(f"    cells with exp > 0      {(g.exp>0).mean():>6.1%}   "
          f"cells with net > 0  {(g.net>0).mean():>6.1%}")

print("\n" + "=" * 112)
print("TOP 15 CELLS BY EXPECTANCY (the mining move - shown to be judged, not used)")
print("=" * 112)
top = R.sort_values("exp", ascending=False).head(15)
print(f"  {'sym':<6} {'side':>5} {'n_ent':>6} {'buf':>5} {'stop':>5} {'targ':>5} "
      f"{'trades':>7} {'exp':>8} {'net':>9}")
for _, x in top.iterrows():
    print(f"  {x['sym']:<6} {int(x.side):>5} {int(x.n_entry):>6} {x.buffer:>5.1f} "
          f"{x.stop:>5.2f} {x.targ:>5.2f} {int(x.trades):>7} {x.exp:>+8.2f} {x.net:>+9.0f}")

nulls = sorted(glob.glob("/home/user/main/data/donchian/vbtshift_NAS_*.parquet"))
if nulls:
    print("\n" + "=" * 112)
    print(f"NULL CALIBRATION - {len(nulls)} circular-shift nulls on NAS, identical pipeline")
    print("  Real prices, real bar geometry, real signal density; only the ALIGNMENT")
    print("  between signal and forward return is destroyed, so cell counts match and")
    print("  max-vs-max is a fair comparison.")
    print("=" * 112)
    print(f"  {'shift':<10} {'cells':>7} {'median exp':>11} {'MAX exp':>9} {'frac exp>0':>11}")
    mx = []
    for f in nulls:
        N = pd.read_parquet(f); N = N[N.trades >= 100]
        if not len(N): continue
        mx.append(N.exp.max())
        print(f"  {f.split('_')[-1][:-8]:<10} {len(N):>7,} {N.exp.median():>+11.2f} "
              f"{N.exp.max():>+9.2f} {(N.exp>0).mean():>11.1%}")
    RN = R[R.sym == "NAS"]
    real_max = RN.exp.max()
    mx = np.array(mx)
    print(f"\n  REAL NAS grid          : {len(RN):,} cells, median exp {RN.exp.median():+.2f}, "
          f"frac>0 {(RN.exp>0).mean():.1%}")
    print(f"\n  REAL NAS best cell     : {real_max:+.2f} pts/trade")
    print(f"  NULL best cell (mean)  : {mx.mean():+.2f}   range [{mx.min():+.2f}, {mx.max():+.2f}]")
    if len(mx) >= 4 and mx.std(ddof=1) > 0:
        print(f"  z of real vs null max  : {(real_max-mx.mean())/mx.std(ddof=1):+.2f}"
              f"   (from {len(mx)} nulls - treat as indicative, not a p-value)")
    else:
        print(f"  too few nulls for a dispersion estimate; comparing to the null RANGE only")
    print(f"  VERDICT: {'real max exceeds the null max' if real_max > mx.max() else 'the real best cell is INSIDE the range this grid produces from pure noise'}")
