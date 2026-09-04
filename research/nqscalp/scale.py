"""The fixed-point thresholds are scale-dependent over a 5x price range.

minPullbackPoints = 15, trailArmPoints = 15 and trailOffsetPoints = 8 are absolute
NQ points. NQ opens this sample near 4,790 and ends near 24,580. A 15-point filter
is a different filter in 2016 than in 2025, and a trail that is ~1 ATR wide at the
start is ~0.2 ATR wide at the end. Nothing in the strategy adapts.
"""
import numpy as np, pandas as pd, sys, warnings
sys.path.insert(0, "/home/user/main/research/donchian"); sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
import nqs, cache, data as D

df = D.load("NAS"); B = cache.build(df); R, H = D.blocks(df)
I, p = cache.indicators(df, B)
(lo, sh), insess = nqs.conditions(df, I, p)
yr = pd.DatetimeIndex(df.ts).year

print("=" * 104)
print("21. THE FIXED-POINT THRESHOLDS DRIFT OUT OF CALIBRATION ACROSS THE SAMPLE")
print("=" * 104)
print(f"  {'year':<6}{'close':>9}{'ATR(14)':>9}{'15 pts in ATR':>15}{'8 pts in ATR':>14}"
      f"{'15 pts as %':>13}{'triggers':>10}{'% bars w/ 15pt pullback':>25}")
rows = []
for y in sorted(set(yr[R])):
    m = (yr == y) & R & insess
    if m.sum() < 50: continue
    a = np.nanmedian(I["atr"][m]); c = np.nanmedian(I["c"][m])
    depth = (I["swing_hi"][m] - I["l"][m])
    rows.append(dict(year=y, close=c, atr=a, arm_atr=15/a, off_atr=8/a,
                     pct=15/c*100, trig=int((lo|sh)[m].sum()),
                     frac=float((depth >= 15).mean())))
    print(f"  {y:<6}{c:>9,.0f}{a:>9.1f}{15/a:>15.2f}{8/a:>14.2f}{15/c*100:>12.3f}%"
          f"{int((lo|sh)[m].sum()):>10}{(depth>=15).mean():>24.1%}")
pd.DataFrame(rows).to_csv("/home/user/main/docs/nqscalp/scale_drift.csv", index=False)
f, l_ = rows[0], rows[-1]
print(f"""
  The trailing stop's ARM distance goes from {f['arm_atr']:.2f} ATR in {f['year']} to {l_['arm_atr']:.2f} ATR in {l_['year']},
  and its OFFSET from {f['off_atr']:.2f} ATR to {l_['off_atr']:.2f} ATR. It is a different exit rule at each end
  of the sample, and at the {l_['year']} end it is tight enough to be inside the bar's own noise -
  which is exactly the regime where the intrabar artifact is largest.

  The pullback filter binds on {f['frac']:.0%} of in-session bars in {f['year']} and {l_['frac']:.0%} in {l_['year']},
  so by the end of the sample it is not filtering anything.""")

print("\n" + "=" * 104)
print("22. WHAT HAPPENS IF EVERY DISTANCE IS MADE ATR-RELATIVE (research block, barclose/adverse)")
print("=" * 104)
med_atr = float(np.nanmedian(I["atr"][R & insess]))
print(f"  research-block median ATR(14) = {med_atr:.1f} pts, so the as-written settings are")
print(f"  equivalent to pullback {15/med_atr:.2f} ATR, arm {15/med_atr:.2f} ATR, offset {8/med_atr:.2f} ATR on average.\n")
base = nqs.simulate(df, I, p, lo & R, sh & R, trail_mode="barclose", order="adverse")
print(f"  as written (fixed points)          n={len(base):>5}  {base.net_pts.mean():+.2f} pts/trade  "
      f"${base.net_usd.sum():+,.0f}")
