"""Proper false-positive calibration: ONE geometry, MANY independent series.

The previous run gave 10 tests from 2 series - correlated within a series, so
not a false-positive rate. Here each series contributes one independent test.
"""
import numpy as np
from engine import build_walk, stats
from strategy import run
from control import matched_control
from null_test import synth
import data as D

real = D.load("NAS")
NS = 24
print("="*100)
print(f"FALSE-POSITIVE CALIBRATION - {NS} independent driftless series, one test each")
print("="*100)
zs, ps, ts = [], [], []
for k in range(NS):
    d = synth(real, phi=0.0, seed=30000+k); w = build_walk(d)
    tr = run(d, w, n_entry=20, stop_mult=1.5, targ_mult=2.0, cost_pts=0.0, slip_pts=0.0)
    mn, p = matched_control(d, w, tr, n_draws=400, seed=30000+k, cost_pts=0.0,
                            slip_pts=0.0, stop_mult=1.5, targ_mult=2.0)
    z = (tr.net.mean()-mn.mean())/mn.std(ddof=1)
    zs.append(z); ps.append(p); ts.append(stats(tr)["t"])
    print(f"  series {k:>2}: n={len(tr):>5,}  exp={tr.net.mean():>+7.2f}  ctrl={mn.mean():>+7.2f}"
          f"  z={z:>+6.2f}  p={p:.3f}")
zs=np.array(zs); ps=np.array(ps); ts=np.array(ts)
print("\n"+"="*100)
print(f"  RAW t vs zero      : mean {ts.mean():+.3f}  sd {ts.std():.2f}  |t|>1.96 in {np.mean(np.abs(ts)>1.96):.1%}")
print(f"  z vs MATCHED CTRL  : mean {zs.mean():+.3f}  sd {zs.std():.2f}  |z|>1.96 in {np.mean(np.abs(zs)>1.96):.1%}")
print(f"  control p<0.05     : {np.mean(ps<0.05):.1%}   (nominal 5%)")
print(f"  control p<0.10     : {np.mean(ps<0.10):.1%}   (nominal 10%)")
ok = abs(zs.mean())<0.4 and np.mean(ps<0.05)<=0.15
print(f"\n  VERDICT: {'PASS - matched control is calibrated. Scoring gate is valid.' if ok else 'FAIL - control mis-calibrated'}")
np.save("/home/user/main/data/donchian/null_z.npy", zs)
