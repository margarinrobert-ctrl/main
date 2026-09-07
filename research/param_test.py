"""Parameter sensitivity: is this rule a plateau or a spike?

A result that only exists at one setting is a hole in the noise. A real one has neighbours that
score near it. This moves every parameter the rule has, one step at a time, and reports what
survives -- including dropping each condition, which is the test most parameter sweeps omit and
which usually says the most.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
from bos_choch import prep
from alpha_factory2 import build_conditions, price_one, EXITS

_CACHE = {}


def _ctx(tf):
    if tf not in _CACHE:
        d = prep(tf)
        names, M = build_conditions(d)
        us = np.unique(d["sess"])
        _CACHE[tf] = (d, names, M, np.searchsorted(us, d["sess"]).astype(np.int64), len(us))
    return _CACHE[tf]


def run_rule(tf, cond_names, am, tp, flat, sides=(1, -1)):
    d, names, M, sidx, nsess = _ctx(tf)
    try:
        ids = [names.index(c) for c in cond_names]
    except ValueError:
        return None
    m = M[ids[0]].copy()
    for i in ids[1:]:
        m &= M[i]
    trig = np.flatnonzero(m).astype(np.int64)
    n = len(d["c"])
    P = []; ENT = []; EX = []
    for s in sides:
        eb = np.zeros(n, np.int64); ep = np.zeros(n); okk = np.zeros(n, np.int64)
        price_one(d["o"], d["h"], d["l"], d["c"], d["atr"], d["mod"].astype(np.int64),
                  s, am, tp, flat, eb, ep, okk)
        free = -1
        for i in trig:
            if i < free or okk[i] == 0:
                continue
            free = eb[i]
            P.append(ep[i]); ENT.append(sidx[i]); EX.append(sidx[min(eb[i], n - 1)])
    o = np.argsort(ENT)
    return np.array(P)[o], np.array(ENT)[o], np.array(EX)[o], nsess


def summarise(r, cut):
    if r is None or len(r[0]) < 10:
        return None
    p, ent, ex, nsess = r
    w = p[p > 0].sum(); l = -p[p <= 0].sum()
    eq = np.cumsum(p)
    return dict(n=len(p), net=p.sum(), pf=(w / l) if l > 0 else np.inf,
                res=p[ent < cut].sum(), lok=p[ent >= cut].sum(),
                dd=float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max()))


def report(cond_names, am, tp, flat, tf=30, tfs=(15, 30, 60), width=100):
    d, names, M, sidx, nsess = _ctx(tf)
    cut = int(0.65 * nsess)
    base = summarise(run_rule(tf, cond_names, am, tp, flat), cut)
    print("=" * width)
    print("PARAMETER SENSITIVITY — " + " AND ".join(cond_names))
    print("=" * width)
    print(f"   both directions, stop {am}xATR, target {tp}R"
          + (f", flat {flat//60}:00" if flat else ", no time stop") + f", {tf}-minute bars\n")
    hd = f"   {'variant':<44}{'n':>6}{'net $':>10}{'PF':>7}{'research':>10}{'LOCKED':>10}{'maxDD':>9}"
    print(hd)

    def row(lab, s):
        if s is None:
            print(f"   {lab:<44}   (too few trades)"); return None
        print(f"   {lab:<44}{s['n']:>6}{s['net']:>10,.0f}{s['pf']:>7.2f}"
              f"{s['res']:>10,.0f}{s['lok']:>10,.0f}{s['dd']:>9,.0f}")
        return s['lok']
    row("the rule as chosen", base)
    lok = []

    print("\n   STOP MULTIPLE")
    for a in (1.0, 1.5, 2.0, 2.5):
        if a == am:
            continue
        v = row(f"stop {a}xATR", summarise(run_rule(tf, cond_names, a, tp, flat), cut))
        if v is not None:
            lok.append(v)

    print("\n   TARGET")
    for t in (1.0, 1.5, 2.0, 3.0):
        if t == tp:
            continue
        v = row(f"target {t}R", summarise(run_rule(tf, cond_names, am, t, flat), cut))
        if v is not None:
            lok.append(v)

    print("\n   SESSION CUTOFF")
    for f in (0, 960):
        if f == flat:
            continue
        v = row("flat 16:00" if f else "no time stop",
                summarise(run_rule(tf, cond_names, am, tp, f), cut))
        if v is not None:
            lok.append(v)

    print("\n   BAR SIZE")
    for t2 in tfs:
        if t2 == tf:
            continue
        d2, _, _, _, ns2 = _ctx(t2)
        v = row(f"{t2}-minute bars",
                summarise(run_rule(t2, cond_names, am, tp, flat), int(0.65 * ns2)))
        if v is not None:
            lok.append(v)

    print("\n   DROP ONE CONDITION — the test most sweeps omit")
    for i in range(len(cond_names)):
        sub = [c for j, c in enumerate(cond_names) if j != i]
        if not sub:
            continue
        v = row(f"without: {cond_names[i]}",
                summarise(run_rule(tf, sub, am, tp, flat), cut))
        if v is not None:
            lok.append(v)

    print("\n   ONE DIRECTION ONLY")
    for s, lab in ((1,), ("longs only",)), ((-1,), ("shorts only",)):
        v = row(lab[0], summarise(run_rule(tf, cond_names, am, tp, flat, sides=s), cut))

    lok = np.array(lok)
    if len(lok) and base:
        print(f"\n   the rule as chosen scored ${base['lok']:,.0f} on the locked block.")
        print(f"   its {len(lok)} neighbours: median ${np.median(lok):,.0f}, "
              f"{100*(lok > 0).mean():.0f}% positive, worst ${lok.min():,.0f}")
        print("   A plateau has neighbours near it. A spike falls off in every direction.")


if __name__ == "__main__":
    report(["RSI14<30", "Williams%R<-80", "ADX>25"], 2.5, 3.0, 0, tf=30)
