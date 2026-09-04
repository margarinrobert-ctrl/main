"""STAGE 0 - engine null calibration.

Run the whole strategy over simulated driftless bars with costs SWITCHED OFF.
There is no edge in that series by construction, so anything reliably
profitable is a BUG: look-ahead, an exit resolving in the trader's favour, or
a cost that never got charged.

Also a POWER CHECK: inject a known AR(1) momentum coefficient and confirm the
engine detects it. A pipeline that cannot find a planted effect is not
evidence of absence.
"""
import numpy as np, pandas as pd
from engine import build_walk, stats, fmt
from strategy import run
import data as D

rng = np.random.default_rng(20260829)


def synth(real, phi=0.0, seed=0):
    """Bars with the real file's timestamps and volatility, but a martingale
    (or a known-AR(1)) price path. Same session structure, same clock."""
    r = np.random.default_rng(seed)
    n = len(real)
    sd = np.diff(np.log(real.close.values)).std()
    e = r.normal(0, sd, n)
    lr = np.empty(n); lr[0] = e[0]
    for i in range(1, n):
        lr[i] = phi * lr[i - 1] + e[i]
    close = real.close.values[0] * np.exp(np.cumsum(lr))
    # build a plausible OHLC around the close path
    w = np.abs(r.normal(0, sd, n)) * close
    o = np.concatenate([[close[0]], close[:-1]])
    hi = np.maximum(o, close) + w
    lo = np.minimum(o, close) - w
    d = real.copy()
    d["open"], d["high"], d["low"], d["close"] = o, hi, lo, close
    return d.reset_index(drop=True)


if __name__ == "__main__":
    real = D.load("NAS")
    print("=" * 96)
    print("STAGE 0 - ENGINE NULL CALIBRATION   (driftless bars, costs = 0, slippage = 0)")
    print("Expect: net ~ 0, |t| < 2 for essentially every configuration.")
    print("=" * 96)

    cfgs = [dict(n_entry=n, stop_mult=s, targ_mult=t)
            for n in (10, 20, 40) for s in (1.0, 1.5) for t in (1.5, 2.0, 3.0)]
    ts = []
    for rep in range(3):
        d = synth(real, phi=0.0, seed=1000 + rep)
        w = build_walk(d)
        for cfg in cfgs:
            tr = run(d, w, cost_pts=0.0, slip_pts=0.0, **cfg)
            s = stats(tr)
            ts.append(s["t"])
    ts = np.array(ts)
    print(f"\n  {len(ts)} null configurations over 3 independent synthetic series")
    print(f"  mean t      : {ts.mean():+.3f}   (expect ~0)")
    print(f"  |t| > 1.96  : {(np.abs(ts) > 1.96).mean():.1%}   (expect ~5%)")
    print(f"  |t| > 2.58  : {(np.abs(ts) > 2.58).mean():.1%}   (expect ~1%)")
    print(f"  max |t|     : {np.abs(ts).max():.3f}")
    verdict = "PASS" if abs(ts.mean()) < 0.35 and (np.abs(ts) > 1.96).mean() < 0.16 else "FAIL - ENGINE BUG"
    print(f"  VERDICT     : {verdict}")

    print("\n" + "=" * 96)
    print("POWER CHECK - inject known AR(1) momentum; detection must scale with phi")
    print("=" * 96)
    for phi in (0.0, 0.05, 0.10, 0.20):
        acc = []
        for rep in range(3):
            d = synth(real, phi=phi, seed=7000 + rep)
            w = build_walk(d)
            tr = run(d, w, n_entry=20, stop_mult=1.5, targ_mult=2.0,
                     cost_pts=0.0, slip_pts=0.0)
            acc.append(stats(tr))
        print(f"  phi={phi:<5} mean t={np.mean([a['t'] for a in acc]):+7.2f}"
              f"   mean exp={np.mean([a['exp'] for a in acc]):+8.3f} pts"
              f"   n={int(np.mean([a['n'] for a in acc])):,}")
