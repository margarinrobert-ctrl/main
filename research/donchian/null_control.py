"""Does the matched control neutralise the engine's geometric bias?

If it does, `excess` is centred on zero for every geometry on a driftless
series, and the whole family becomes scorable. This is the test that decides
whether the research can proceed.
"""
import numpy as np
from engine import build_walk, stats
from strategy import run
from control import matched_control, report
from null_test import synth
import data as D

real = D.load("NAS")
print("="*112)
print("NULL + MATCHED CONTROL  (driftless synthetic bars, costs 0)")
print("If the control absorbs the geometric bias, `excess` sits on ~0 for EVERY geometry.")
print("="*112)
zs, raw_t = [], []
for seed in (1000, 1001):
    d = synth(real, phi=0.0, seed=seed); w = build_walk(d)
    print(f"\n  --- synthetic series seed {seed} ---")
    for sm, tm in ((1.0,1.5),(1.0,3.0),(1.5,2.0),(2.5,1.5),(2.5,3.0)):
        tr = run(d, w, n_entry=20, stop_mult=sm, targ_mult=tm, cost_pts=0.0, slip_pts=0.0)
        mn, p = matched_control(d, w, tr, n_draws=300, seed=seed, cost_pts=0.0,
                                slip_pts=0.0, stop_mult=sm, targ_mult=tm)
        s = stats(tr)
        z = (tr.net.mean()-mn.mean())/mn.std(ddof=1)
        zs.append(z); raw_t.append(s["t"])
        print("   " + report(tr, mn, p, f"stop={sm} targ={tm}"))
zs = np.array(zs); raw_t = np.array(raw_t)
print("\n" + "="*112)
print(f"  raw t vs zero      : mean {raw_t.mean():+.3f}   |t|>1.96 in {np.mean(np.abs(raw_t)>1.96):.0%}  <- biased")
print(f"  z vs matched ctrl  : mean {zs.mean():+.3f}   |z|>1.96 in {np.mean(np.abs(zs)>1.96):.0%}  <- should be ~0 / ~5%")
ok = abs(zs.mean()) < 0.5 and np.mean(np.abs(zs)>1.96) <= 0.25
print(f"  VERDICT            : {'PASS - control neutralises the bias; scoring is valid' if ok else 'FAIL'}")
