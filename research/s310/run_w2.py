"""W2 -- is the concentration EVIDENCE, or is it the geometry?

W1.3 found that removing the best 5% of trades takes the locked block from +11.41 to -0.10 pts.
That looks damning and it may not be: a no-target system with a 3xATR stop and a 1R trail is
DESIGNED to earn in the tail, so heavy concentration could be a property of the exits that any
entry inherits. The only way to know is to measure the same statistic on the matched random entry
-- the same window, rate, side mix, geometry and position lock -- and compare.

Also here: the median trade. A tail artifact with no edge has a NEGATIVE median (many small losses
paying for a few large wins). A positive median AND a fat tail is a different object.
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5"); sys.path.insert(0, "research/s310")
import numpy as np, pandas as pd
import s5sig as SG, s5data as S
import t10core as T

R = "results/s310/"
print(__doc__); t0 = time.time()
pd.set_option("display.width", 220)
rng = np.random.default_rng(31)
D, F, base = T.build(5)
lg, sh = SG.s3_flow_exhaustion(D, F, T.CARRY)
t = T.run(D, lg, sh)

def conc(r):
    r = np.sort(np.asarray(r))[::-1]
    tot = r.sum()
    k5 = max(int(round(0.05 * len(r))), 1)
    return dict(n=len(r), mean=r.mean(), median=np.median(r), tot=tot,
                top5_share=r[:k5].sum() / tot if tot != 0 else np.nan,
                ex_top5=r[k5:].mean(), win=(r > 0).mean())

print("=" * 116)
print("W2.1  THE SAME CONCENTRATION STATISTIC ON THE MATCHED RANDOM ENTRY")
print("=" * 116)
for b, bl in ((0, "research"), (1, "LOCKED")):
    s = t[t.blk == b]
    rc = conc(s.pts.to_numpy())
    elig = np.flatnonzero(D["inw"] & (D["blk"] == b) & np.isfinite(D["atr"]) & (D["atr"] > 0))
    p_long = float((s.side > 0).mean())
    rows = []
    for _ in range(400):
        pick = np.sort(rng.choice(elig, min(len(s), len(elig)), replace=False))
        L = np.zeros(D["n"], bool); Sh = np.zeros(D["n"], bool)
        isl = rng.random(len(pick)) < p_long
        L[pick[isl]] = True; Sh[pick[~isl]] = True
        q = T.run(D, L, Sh)
        q = q[q.blk == b]
        if len(q) > 20:
            rows.append(conc(q.pts.to_numpy()))
    C = pd.DataFrame(rows)
    print(f"\n  --- {bl} ---")
    print(f"                       rule        random-entry control (400 draws)")
    print(f"    mean pts/trade   {rc['mean']:+8.3f}      median {C['mean'].median():+7.3f}   "
          f"p5 {C['mean'].quantile(.05):+7.3f}  p95 {C['mean'].quantile(.95):+7.3f}")
    print(f"    MEDIAN trade     {rc['median']:+8.3f}      median {C['median'].median():+7.3f}   "
          f"p5 {C['median'].quantile(.05):+7.3f}  p95 {C['median'].quantile(.95):+7.3f}"
          f"    -> rule beats {np.mean(C['median'] < rc['median']):.1%} of draws")
    print(f"    top 5% share     {rc['top5_share']:8.1%}      median {C['top5_share'].median():7.1%}   "
          f"p5 {C['top5_share'].quantile(.05):7.1%}  p95 {C['top5_share'].quantile(.95):7.1%}")
    print(f"    ex-top-5% mean   {rc['ex_top5']:+8.3f}      median {C['ex_top5'].median():+7.3f}   "
          f"p5 {C['ex_top5'].quantile(.05):+7.3f}  p95 {C['ex_top5'].quantile(.95):+7.3f}"
          f"    -> rule beats {np.mean(C['ex_top5'] < rc['ex_top5']):.1%} of draws")
    print(f"    win rate         {rc['win']:8.1%}      median {C['win'].median():7.1%}")

print("\n" + "=" * 116)
print("W2.2  WHAT DOES THE RULE ACTUALLY BEAT THE CONTROL ON?")
print("=" * 116)
print("  If the top-5% SHARE matches the control but the ex-top-5% MEAN beats it, the")
print("  concentration is the geometry and the rule is adding something underneath it.")
print("  If the ex-top-5% mean also matches, the whole result is which few trades ran.")

print("\n" + "=" * 116)
print("W2.3  THE TAIL ITSELF -- does the rule produce BIGGER winners, or just catch more of them?")
print("=" * 116)
for b, bl in ((0, "research"), (1, "LOCKED")):
    s = t[t.blk == b].pts.to_numpy()
    elig = np.flatnonzero(D["inw"] & (D["blk"] == b) & np.isfinite(D["atr"]) & (D["atr"] > 0))
    p_long = float((t[t.blk == b].side > 0).mean())
    big_r, p90_r = [], []
    for _ in range(300):
        pick = np.sort(rng.choice(elig, min(len(s), len(elig)), replace=False))
        L = np.zeros(D["n"], bool); Sh = np.zeros(D["n"], bool)
        isl = rng.random(len(pick)) < p_long
        L[pick[isl]] = True; Sh[pick[~isl]] = True
        q = T.run(D, L, Sh); q = q[q.blk == b]
        if len(q) > 20:
            v = q.pts.to_numpy()
            big_r.append(np.mean(v > 50)); p90_r.append(np.percentile(v, 90))
    print(f"  {bl:8s}  share of trades over +50 pts: rule {np.mean(s>50):.1%}  "
          f"control {np.median(big_r):.1%}   |   p90 of pts: rule {np.percentile(s,90):+.1f}  "
          f"control {np.median(p90_r):+.1f}")
print(f"\ntotal {time.time()-t0:.0f}s")
