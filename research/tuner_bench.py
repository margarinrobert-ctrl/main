"""How much faster, and where the time actually goes.

The claim is not "numba is fast" -- `test_suite.sim_core` is already numba. The claim is that the
price walk is being done once per geometry instead of once per configuration, so the geometry
axes of a tuning grid become array indexing. This measures that against the existing path.
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import indpool
import tuner as U


def indpool_clear():
    """Drop the memoised indicator arrays, so a rule is timed as if it were never seen."""
    indpool._MEMO.clear()


RULE = "close>ema200 and close<ema20 and rsi14<40"
WIN = "09:30-11:00"
STOPS = [1.0, 1.5, 2.0, 2.5, 3.0]
TARGS = [0.5, 1.0, 1.5, 2.0, 3.0]
FLATS = [0, 690]
HOLDS = [0, 6, 12]


def bench(tf=30):
    from test_suite import build, bars_for
    print(f"\n{tf}-MINUTE BARS")
    print("-" * 78)

    t0 = time.time(); bars_for(tf); old_cold = time.time() - t0
    U._BARS.pop(tf, None)
    t0 = time.time(); d = U.bars(tf); new_cold = time.time() - t0
    print(f"  cold start (a fresh process)      test_suite {old_cold:6.2f}s    "
          f"tuner {new_cold:6.2f}s   {old_cold/max(new_cold,1e-6):>6.0f}x")

    wm = U.win_mask(d, WIN)
    trig = np.flatnonzero(U.mask(d, RULE) & wm).astype(np.int64)
    ng = len(STOPS) * len(TARGS) * len(FLATS) * len(HOLDS)

    build([], side=1, atr_mult=2.0, tp_r=1.0, tf=tf, trig=trig, pool=False)   # jit warm
    t0 = time.time()
    reps = 0
    for st in STOPS:
        for tg in TARGS:
            for fl in FLATS:
                build([], side=1, atr_mult=st, tp_r=tg, flat_min=fl, tf=tf,
                      trig=trig, pool=False)
                reps += 1
    old = time.time() - t0
    old_full = old * ng / reps          # test_suite has no max-hold exit; scale to the same grid

    U._TENSORS.clear()                  # otherwise this times a cache hit, not a build
    t0 = time.time()
    T = U.tensor(tf, 1, STOPS, TARGS, FLATS, HOLDS, only=wm)
    tb = time.time() - t0
    out = np.zeros((T.ng, U.NCOL)); cs = U.Costs()
    U._walk_many(trig, T.xb, T.why, T.raw, cs.se_pv(), cs.fixed(), d["si"],
                 np.int64(d["cut"]), out)
    t0 = time.time()
    n = 20
    for _ in range(n):
        U._walk_many(trig, T.xb, T.why, T.raw, cs.se_pv(), cs.fixed(), d["si"],
                     np.int64(d["cut"]), out)
    new = (time.time() - t0) / n

    print(f"  {ng} geometries, one rule          test_suite {old_full:6.2f}s    "
          f"tuner {new:6.4f}s   {old_full/max(new,1e-9):>6.0f}x   "
          f"(+{tb:.1f}s once to build the tensor)")
    print(f"  per geometry                      test_suite "
          f"{1000*old_full/ng:6.2f}ms    tuner {1e6*new/ng:6.1f}us")

    # the crossover: how many configurations before the tensor has paid for itself
    per_old = old_full / ng
    cross = tb / max(per_old - new / ng, 1e-12)
    print(f"  the tensor pays for itself after   {cross:,.0f} configurations "
          f"(and it is reused by every later rule)")

    # what a NEW rule costs on top: evaluating its indicators and finding its trigger bars
    U.mask(d, RULE)
    t0 = time.time()
    for i in range(10):
        U._CODE.clear(); indpool_clear()
        np.flatnonzero(U.mask(d, RULE) & wm)
    per_rule = (time.time() - t0) / 10
    print(f"  a new rule (indicators + triggers) {1000*per_rule:.1f} ms, "
          f"paid once however wide the geometry grid is")

    for label, k in (("10 rules x this grid", 10), ("100 rules x this grid", 100)):
        mask_cost = per_rule * k
        print(f"  {label:<33} test_suite {old_full*k:8.1f}s    "
              f"tuner {tb + new*k + mask_cost:8.2f}s   "
              f"{old_full*k/max(tb + new*k + mask_cost,1e-9):>6.0f}x")

    U.run(RULE, tf=tf, win=WIN, stop=2.0, target=1.0, control=64, _T=T)   # jit warm
    t0 = time.time()
    r = U.run(RULE, tf=tf, win=WIN, stop=2.0, target=1.0, control=2000, _T=T)
    print(f"  a 2,000-draw matched control      {1000*(time.time()-t0):.0f} ms "
          f"-- cheap enough to be a gate, not a final check")
    return r


if __name__ == "__main__":
    for tf in (int(x) for x in (sys.argv[1:] or [30, 5])):
        bench(tf)
