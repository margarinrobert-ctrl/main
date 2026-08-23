"""Two questions the sweep raises: what does the incumbent do on each timeframe, and is the
search winner a plateau or a spike?"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
from bos_choch import prep
import tf_sweep as T

d30 = prep(30)
usess = np.unique(d30["sess"])
cut = usess[int(0.65 * len(usess))]


def run(m, k, e, am, nb, tp, dn, dx, lo, hi, sd):
    d = prep(m, swing_k=int(k), ema_n=int(e))
    G = np.array([[am, nb, tp, dn, dx, lo, hi, sd]], np.float64)
    out = np.zeros((1, 14), np.float64)
    T.sweep(d["o"], d["h"], d["l"], d["c"], d["sess"].astype(np.int64), d["mod"].astype(np.int64),
            d["ph"], d["pl"], d["ema"], d["atr"], np.int64(cut), G, out, 0)
    r = out[0]
    n = r[0] + r[6]
    if n == 0:
        return None
    net = r[1] + r[7]; w = r[2] + r[8]; gw = r[3] + r[9]; gl = r[4] + r[10]
    return dict(n=int(n), net=net, pf=gw / gl if gl > 0 else np.inf, win=100 * w / n,
                res=r[1], lock=r[7], nlock=int(r[6]), dd=max(r[5], r[11]))


def line(tag, s):
    if s is None:
        return f"   {tag:<34}   (no trades)"
    return (f"   {tag:<34}{s['n']:>6}{s['net']:>11,.0f}{s['pf']:>7.2f}{s['win']:>7.1f}"
            f"{s['res']:>11,.0f}{s['lock']:>11,.0f}{s['dd']:>10,.0f}")


H = f"   {'':<34}{'n':>6}{'net $':>11}{'PF':>7}{'win%':>7}{'research':>11}{'LOCKED':>11}{'maxDD':>10}"
W = 96

print("=" * W)
print("A. THE INCUMBENT SPEC, RUN ON EACH TIMEFRAME — nothing else changed")
print("=" * W)
print("   nBos 2, stop 2xATR, 2R target, EMA200, swing k3, EMA distance >= 1 ATR, RTH, both sides.")
print("   Only the chart interval moves.\n")
print(H)
for m in [5, 15, 30, 60, 120, 240]:
    print(line(f"{m}m", run(m, 3, 200, 2.0, 2, 2.0, 1.0, 1e9, 570, 960, 0)))

print("\n   ... and on the 24h session, since a 1-hour chart sees far fewer RTH bars:\n")
print(H)
for m in [30, 60, 120]:
    print(line(f"{m}m  24h session", run(m, 3, 200, 2.0, 2, 2.0, 1.0, 1e9, 0, 1440, 0)))

print()
print("=" * W)
print("B. THE SEARCH WINNER — plateau or spike?")
print("=" * W)
BEST = dict(m=120, k=5, e=50, am=2.5, nb=1, tp=3.0, dn=0.5, dx=1e9, lo=0, hi=1440, sd=0)
b = run(BEST["m"], BEST["k"], BEST["e"], BEST["am"], BEST["nb"], BEST["tp"],
        BEST["dn"], BEST["dx"], BEST["lo"], BEST["hi"], BEST["sd"])
print("   120m, k5, EMA50, nBos 1, stop 2.5xATR, 3R target, dist >= 0.5, 24h, both sides\n")
print(H)
print(line("the winner itself", b))
print("\n   one step in each direction, one parameter at a time:\n")
print(H)
NB = [("timeframe 60m", dict(m=60)), ("timeframe 240m", dict(m=240)),
      ("swing k 4", dict(k=4)), ("EMA 100", dict(e=100)), ("EMA 200", dict(e=200)),
      ("nBos 2", dict(nb=2)), ("stop 2.0xATR", dict(am=2.0)), ("stop 3.0xATR", dict(am=3.0)),
      ("target 2.5R", dict(tp=2.5)), ("target 2.0R", dict(tp=2.0)),
      ("dist >= 0.0", dict(dn=0.0)), ("dist >= 1.0", dict(dn=1.0)),
      ("RTH session", dict(lo=570, hi=960))]
locks = []
for tag, mod in NB:
    p = dict(BEST); p.update(mod)
    s = run(p["m"], p["k"], p["e"], p["am"], p["nb"], p["tp"], p["dn"], p["dx"],
            p["lo"], p["hi"], p["sd"])
    print(line(tag, s))
    if s is not None:
        locks.append(s["lock"])
locks = np.array(locks)
print(f"\n   winner locked ${b['lock']:,.0f}   neighbours: median ${np.median(locks):,.0f}, "
      f"{100*(locks < b['lock']).mean():.0f}% below it, worst ${locks.min():,.0f}")
print("   A genuine setting sits on a PLATEAU -- its neighbours score close to it. A mined one")
print("   sits on a SPIKE, and every step away falls off.")

print()
print("=" * W)
print("C. WALK-FORWARD — the winner and the incumbent over the same six folds")
print("=" * W)


def wf(p, folds=6):
    d = prep(p["m"], swing_k=int(p["k"]), ema_n=int(p["e"]))
    G = np.array([[p["am"], p["nb"], p["tp"], p["dn"], p["dx"], p["lo"], p["hi"], p["sd"]]],
                 np.float64)
    out = np.zeros((1, 14), np.float64)
    us = np.unique(d["sess"])
    cuts = np.array_split(us, folds + 1)
    res = []
    for f in range(folds):
        c0 = cuts[f + 1][0]
        T.sweep(d["o"], d["h"], d["l"], d["c"], d["sess"].astype(np.int64),
                d["mod"].astype(np.int64), d["ph"], d["pl"], d["ema"], d["atr"],
                np.int64(c0), G, out, 0)
        res.append((out[0, 1], out[0, 7]))
    return res


INC = dict(m=30, k=3, e=200, am=2.0, nb=2, tp=2.0, dn=1.0, dx=1e9, lo=570, hi=960, sd=0)
print(f"   {'fold':<8}{'winner in-sample':>19}{'winner forward':>17}"
      f"{'incumbent in-sample':>22}{'incumbent forward':>20}")
a = wf(BEST); c = wf(INC)
for i in range(6):
    print(f"   {i+1:<8}{a[i][0]:>19,.0f}{a[i][1]:>17,.0f}{c[i][0]:>22,.0f}{c[i][1]:>20,.0f}")
print(f"\n   winner: {sum(1 for x in a if x[1] < 0)} negative forward folds of 6")
print(f"   incumbent: {sum(1 for x in c if x[1] < 0)} negative forward folds of 6")
