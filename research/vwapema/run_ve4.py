"""TEST 4 -- the volume gradient read once on the locked block, DESCRIPTIVE.

The rule as specified was the pre-declared locked read (`run_ve2`). The volume gradient was found
by sweeping C5 on the research block AFTER that, so this is a SECOND look at the locked block and
every number below is descriptive, not a test. It is reported because the gradient is the only
component of the spec that beat a same-selectivity random filter, and because a component that
holds is worth more than one that does not.
"""
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from research.vwapema import vecore as V

RNG = np.random.default_rng(555)
pd.set_option("display.width", 210)
print(__doc__)
D = V.build()

base, _ = V.triggers(D, side=1, p={"vol_mult": 0.0})
rows = []
for blk, bn in ((0, "research"), (1, "LOCKED (descriptive)")):
    bidx = np.flatnonzero(base & (D["blk"] == blk))
    for vm in (1.0, 1.1, 1.3, 1.5, 2.0):
        s, _ = V.triggers(D, side=1, p={"vol_mult": vm})
        t = V.run(D, s, side=1); t = t[t.blk == blk]
        st = V.stats(t)
        keep = int((s & (D["blk"] == blk)).sum())
        null = []
        for _ in range(400):
            g = np.zeros(D["n"], bool)
            g[RNG.choice(bidx, size=min(keep, len(bidx)), replace=False)] = True
            tt = V.run(D, g, side=1); tt = tt[tt.blk == blk]
            if len(tt) >= 15:
                null.append(tt.R.mean())
        null = np.array(null)
        rows.append(dict(block=bn, vol_mult=vm, n=st["n"], R=st["R"], pf=st["pf"], win=st["win"],
                         totR=st["totR"], rand_R=float(np.median(null)) if len(null) else np.nan,
                         p=float((null >= st["R"]).mean()) if len(null) else np.nan))
G = pd.DataFrame(rows)
print(G.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
print("\n  Spearman(vol_mult, R) research "
      f"{G[G.block=='research'][['vol_mult','R']].corr(method='spearman').iloc[0,1]:+.3f}, "
      f"locked {G[G.block!='research'][['vol_mult','R']].corr(method='spearman').iloc[0,1]:+.3f}")

print("\n" + "=" * 100)
print("AND WHAT THE VOLUME FILTER IS ACTUALLY SELECTING")
print("=" * 100)
r = D["blk"] == 0
s11, _ = V.triggers(D, side=1, p={"vol_mult": 1.1})
s20, _ = V.triggers(D, side=1, p={"vol_mult": 2.0})
for nm, m in (("all RTH research bars", r & D["rth"]), ("C5 at 1.1x", s11 & r), ("C5 at 2.0x", s20 & r)):
    print(f"  {nm:24s} n {int(m.sum()):6d}  median ATR {np.nanmedian(D['atr'][m]):.3f}  "
          f"median bar range {np.nanmedian(D['h'][m]-D['l'][m]):.3f}  "
          f"median volume {np.nanmedian(D['v'][m]):.0f}")
print("\n  A volume spike selects FAST bars. On a fixed-cost instrument that widens the risk")
print("  denominator, which is `STUDY_V39`'s volatility-artifact warning -- but the random filter")
print("  above is drawn from the SAME signal population, so it prices that already.")
G.to_csv("results/vwapema/volgradient_locked.csv", index=False)
