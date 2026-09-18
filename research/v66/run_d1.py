"""D1 -- Gate 1 on every declared candidate primary, RESEARCH ONLY. No features exist yet."""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, "research/v66")
import v66core as V

t0 = time.time()
pd.set_option("display.width", 200)
print(V.__doc__)
print("=" * 118)
print("D1  GATE 1 -- the raw primary alone, research block, against a matched random entry")
print("=" * 118)
print(f"{'primary':>18} {'n res':>7} {'/yr':>6} {'pct/ev':>9} {'PF':>7} {'win%':>7} "
      f"{'ctl med':>9} {'excess':>9} {'p':>7}")
Dc, rows = {}, []
for name, cfg in V.CANDIDATES.items():
    tf = cfg["tf"]
    if tf not in Dc:
        Dc[tf] = V.load(tf)
    D = Dc[tf]
    E = V.primary(D, cfg)
    r = E[E.blk == 0]
    if len(r) < 40:
        print(f"{name:>18} {len(r):>7}  -- too few --")
        continue
    x = r.pct.to_numpy()
    yrs = (D["ix"][D["blk"] == 0][-1] - D["ix"][D["blk"] == 0][0]) / np.timedelta64(365, "D")
    ctl = V.control(D, cfg, len(r), seed=hash(name) % 9999, block=0, draws=200)
    pf = x[x > 0].sum() / max(-x[x < 0].sum(), 1e-9)
    p = float((ctl >= x.mean()).mean())
    rows.append(dict(name=name, n=len(r), pct=x.mean(), PF=pf, p=p, per_yr=len(r) / yrs))
    print(f"{name:>18} {len(r):>7} {len(r)/yrs:>6.0f} {x.mean():>9.4f} {pf:>7.3f} "
          f"{(x>0).mean()*100:>6.1f}% {np.median(ctl):>9.4f} {x.mean()-np.median(ctl):>9.4f} "
          f"{p:>7.3f}")
R = pd.DataFrame(rows)
R.to_csv("results/v66/d1_gate1.csv", index=False)
ok = R[(R.p <= 0.05) & (R.pct > 0)]
print(f"\n  eligible (p<=0.05 AND profitable): {len(ok)} of {len(R)}")
if len(ok):
    best = ok.sort_values("n", ascending=False).iloc[0]
    print(f"  MOST EVENTS AMONG THE ELIGIBLE: {best['name']}  n={int(best.n)} "
          f"({best.per_yr:.0f}/yr)  pct/ev {best.pct:.4f}  p {best.p:.3f}")
print(f"[{time.time()-t0:.0f}s]")
