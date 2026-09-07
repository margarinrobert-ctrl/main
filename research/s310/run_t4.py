"""T4 -- correlation matrices: across parameter cells, across timeframes, and against always-long.

A grid of cells that correlate 0.9 is one strategy wearing many names, and a "diversified" pair of
readings of the same rule is not diversification. Daily P&L is zero-filled on sessions that did not
trade, because a matrix over TRADED days only is a matrix over a moving set of days.
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5"); sys.path.insert(0, "research/s310")
import numpy as np, pandas as pd
import s5sig as SG
import t10core as T

R = "results/s310/"
print(__doc__); t0 = time.time()
pd.set_option("display.width", 240); pd.set_option("display.max_columns", 40)
D, F, base = T.build(10)
D5, F5, _ = T.build(5)

print("=" * 118)
print("T4.1  ACROSS (k, w) CELLS AT 10 MINUTES -- is the grid a family or one rule?")
print("=" * 118)
cells = [(k, w) for k in (1, 2, 3, 4, 5) for w in (10, 20, 40)]
for blk, bl in ((0, "research"), (1, "LOCKED")):
    ser = {}
    for k, w in cells:
        lg, sh = SG.s3_flow_exhaustion(D, F, dict(k=k, w=w))
        t = T.run(D, lg, sh)
        if len(t[t.blk == blk]) >= 30:
            ser[f"k{k}w{w}"] = T.daily(t, D, blk)
    P = pd.DataFrame(ser)
    C = P.corr()
    iu = np.triu_indices_from(C, 1)
    v = C.to_numpy()[iu]
    print(f"\n  {bl}: {P.shape[1]} scorable cells, median pairwise corr {np.median(v):+.3f}, "
          f"min {v.min():+.3f}, max {v.max():+.3f}")
    print(f"  share of pairs above 0.7: {(v>0.7).mean():.1%}")
    if blk == 0:
        C.round(2).to_csv(R + "t4_corr_kw_research.csv")
        print(C.round(2).to_string())
    ev = np.linalg.eigvalsh(C.to_numpy())[::-1]
    ev = ev / ev.sum()
    print(f"  components for 90% of variance: {int(np.searchsorted(np.cumsum(ev), 0.90) + 1)} "
          f"of {len(ev)}  (first component {ev[0]:.1%})")

print("\n" + "=" * 118)
print("T4.2  ACROSS TIMEFRAMES AND AGAINST THE MARKET ITSELF")
print("=" * 118)
legs = {}
for lab, DD, FF, p in (("10m carry", D, F, T.CARRY), ("10m matched", D, F, T.MATCHED),
                       ("5m carry", D5, F5, T.CARRY), ("5m matched", D5, F5, T.MATCHED)):
    lg, sh = SG.s3_flow_exhaustion(DD, FF, p)
    legs[lab] = (DD, T.run(DD, lg, sh))
for blk, bl in ((0, "research"), (1, "LOCKED")):
    ser = {k: T.daily(v[1], v[0], blk) for k, v in legs.items()}
    # always-long in the same window, same geometry -- the drift the rule is exposed to
    for lab, DD in (("10m", D), ("5m", D5)):
        m = DD["inw"] & ~DD["last_win"]
        lg = np.zeros(DD["n"], bool); lg[np.flatnonzero(m)] = True
        t = T.run(DD, lg, np.zeros(DD["n"], bool))
        ser[f"always-long {lab}"] = T.daily(t, DD, blk)
    P = pd.DataFrame(ser)
    C = P.corr()
    print(f"\n  --- {bl} ---")
    print(C.round(3).to_string())
    C.round(3).to_csv(R + f"t4_corr_tf_{bl}.csv")
print("\n  The 10m and 5m readings share the same underlying event; a high correlation between them")
print("  means the 10m run is not an independent confirmation of the 5m result.")
print(f"\ntotal {time.time()-t0:.0f}s")
