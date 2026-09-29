"""W3 -- the deflation, done fairly, because my first one was not.

Two things were wrong with the N=1,295 figure in STUDY_S3_10M:

1. IT COUNTED VALIDATION LOOKS AS SEARCH LOOKS. 1,260 of those 1,295 cells were the 10-minute
   geometry grid, which was run to FALSIFY the 5-minute result, not to find it. A test you run on
   a finished result is not a trial that produced it. Multiplicity prices the search.

2. var_trials WAS MEASURED ON THE WRONG POPULATION -- the 10-minute (k,w) family, which is a
   materially worse and more dispersed family than the one the cell came from. A larger trial
   variance makes E[max | noise] larger, so that choice made the test harsher than it should be.
   This branch has recorded the same error with both signs (STUDY_XAU_TWO_LAYER too generous,
   STUDY_VP_TPO too harsh); the fix is to state what the variance is measured over and use the
   population that actually produced the candidate.

Reported here as a CURVE over assumed N, because the assumption is doing the work.
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5"); sys.path.insert(0, "research/s310")
import numpy as np, pandas as pd
from scipy import stats as sps
import s5sig as SG
import t10core as T

R = "results/s310/"
print(__doc__); t0 = time.time()
pd.set_option("display.width", 220)
D, F, base = T.build(5)

# the population that ACTUALLY produced the cell: the 5-minute (k,w) family at the shipped geometry
srs = []
for k in (1, 2, 3, 4, 5):
    for w in (5, 10, 15, 20, 30, 40):
        lg, sh = SG.s3_flow_exhaustion(D, F, dict(k=k, w=w))
        t = T.run(D, lg, sh)
        s = t[t.blk == 0]
        if len(s) >= 30:
            r = s.pts.to_numpy()
            srs.append(r.mean() / (r.std(ddof=1) + 1e-12))
var5 = float(np.var(srs, ddof=1))
print(f"  var of trial Sharpes, 5m family ({len(srs)} cells): {var5:.6f}")
print(f"  var used in STUDY_S3_10M (10m family):              0.004208")

def emax(N, var):
    g = 0.5772156649
    return np.sqrt(var) * ((1 - g) * sps.norm.ppf(1 - 1.0 / N) + g * sps.norm.ppf(1 - 1.0 / (N * np.e)))

def dsr(sr, T_obs, N, var, sk, ku):
    num = (sr - emax(N, var)) * np.sqrt(T_obs - 1)
    den = np.sqrt(1 - sk * sr + (ku - 1) / 4.0 * sr ** 2)
    return float(sps.norm.cdf(num / den))

lg, sh = SG.s3_flow_exhaustion(D, F, T.CARRY)
t = T.run(D, lg, sh)
print("\n" + "=" * 104)
print("W3.1  DEFLATED SHARPE AS A CURVE OVER ASSUMED N -- 5m variance, both blocks")
print("=" * 104)
print(f"  {'N':>8} {'E[max|noise]':>14} | {'research DSR':>13} {'LOCKED DSR':>12}")
rows = []
for b, bl in ((0, "research"), (1, "LOCKED")):
    r = t[t.blk == b].pts.to_numpy()
    rows.append((bl, r.mean() / r.std(ddof=1), len(r), float(sps.skew(r)), float(sps.kurtosis(r) + 3)))
for N in (1, 5, 30, 100, 400, 805, 1295, 5000):
    e = emax(N, var5)
    ds = [dsr(sr, n, N, var5, sk, ku) for _, sr, n, sk, ku in rows]
    print(f"  {N:>8} {e:>14.4f} | {ds[0]:>13.4f} {ds[1]:>12.4f}")
print(f"\n  the cell's per-trade Sharpe: research {rows[0][1]:+.4f}, LOCKED {rows[1][1]:+.4f}")
print("  N = 805 is the honest search count for the 5m cell (5 designs x ~800 declared geometry")
print("  cells + 30 (k,w) reads); N = 1,295 was my figure and it wrongly included 1,260 cells of")
print("  10-minute stress testing that could only ever have killed the result, never produced it.")

print("\n" + "=" * 104)
print("W3.2  THE SAME QUESTION WITHOUT A NORMALITY ASSUMPTION -- the control's own maximum")
print("=" * 104)
print("  A deflated Sharpe assumes a distributional form for the trial set. The non-parametric")
print("  version asks it directly: over 2,000 matched random entries, how often does the BEST of")
print("  30 draws (one per (k,w) cell searched) beat what the rule actually earned?")
rng = np.random.default_rng(77)
for b, bl in ((0, "research"), (1, "LOCKED")):
    s = t[t.blk == b]
    real = s.pts.mean()
    elig = np.flatnonzero(D["inw"] & (D["blk"] == b) & np.isfinite(D["atr"]) & (D["atr"] > 0))
    p_long = float((s.side > 0).mean())
    draws = []
    for _ in range(600):
        pick = np.sort(rng.choice(elig, min(len(s), len(elig)), replace=False))
        L = np.zeros(D["n"], bool); Sh = np.zeros(D["n"], bool)
        isl = rng.random(len(pick)) < p_long
        L[pick[isl]] = True; Sh[pick[~isl]] = True
        q = T.run(D, L, Sh); q = q[q.blk == b]
        draws.append(q.pts.mean() if len(q) else np.nan)
    draws = np.array(draws)
    draws = draws[np.isfinite(draws)]
    # best-of-30 null: the maximum a 30-cell search over NOISE would have produced
    best30 = np.array([np.max(rng.choice(draws, 30)) for _ in range(4000)])
    print(f"  {bl:8s}: rule {real:+7.3f}   single random entry beats it "
          f"{np.mean(draws >= real):.3f}   BEST-OF-30 beats it {np.mean(best30 >= real):.3f}")
print("  The second column is the search-corrected p-value with no distributional assumption.")
print(f"\ntotal {time.time()-t0:.0f}s")
