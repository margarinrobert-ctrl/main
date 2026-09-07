"""Build the 'best version' the disciplined way and price it once.

Every parameter is chosen by its MARGINAL median locked P&L -- the value that wins when averaged
over every setting of everything else -- rather than by taking the top cell of a 590,976-row
search. A marginal is not a selection on a single point, so it does not mine noise the way a max
does. Then the resulting configuration is evaluated once, and compared with the strategy exactly
as it was specified.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from bos_choch import prep, SPECS
from sd_4h15m import build_zones, run

S = SPECS["MNQ"]
A = (S["pv"], S["tick"], 1.0, S["spread_t"], S["slip_t"], S["stop_slip_t"])
u30 = np.unique(prep(30)["sess"])
CUT = u30[int(0.65 * len(u30))]
NRES = int((u30 < CUT).sum()); NLOCK = len(u30) - NRES

_C = {}


def go(H, L, bk, bm, dm, zt, slo, shi, buf, tp, nb, age_d, osh, sd):
    dH = prep(H); dL = prep(L)
    k = (H, L, bk, bm, dm, zt)
    if k not in _C:
        zl, zh, zd, zb = build_zones(dH["o"], dH["h"], dH["l"], dH["c"], dH["atr"], bk, bm, dm, zt)
        ct = (dH["df"].index[zb] + pd.Timedelta(minutes=H)).values
        _C[k] = (zl, zh, zd, np.searchsorted(dL["df"].index.values, ct, side="left").astype(np.int64))
    zl, zh, zd, zs = _C[k]
    trad = ((dL["mod"] >= slo) & (dL["mod"] < shi)).astype(np.uint8)
    age = int(age_d * 1440 / L)
    p, e, s_, w = run(dL["o"], dL["h"], dL["l"], dL["c"], dL["sess"], trad, dL["atr"],
                      zl, zh, zd, zs, buf, tp, nb, age, osh, sd, *A)
    if len(p) == 0:
        return None
    ss = dL["sess"][e]
    m = ss < CUT
    eq = np.cumsum(p); dd = (np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max()
    gw = p[p > 0].sum(); gl = -p[p <= 0].sum()
    win = 100 * (p > 0).mean(); bound = 100.0 / (1.0 + tp)
    z = ((p > 0).mean() - 1.0 / (1.0 + tp)) / np.sqrt((1 / (1 + tp)) * (1 - 1 / (1 + tp)) / len(p))
    return dict(n=len(p), net=p.sum(), pf=gw / gl if gl > 0 else np.inf, win=win,
                exc=win - bound, z=z, dd=dd, res=p[m].sum(), lock=p[~m].sum(),
                nres=int(m.sum()), nlock=int((~m).sum()), p=p, ss=ss)


W = 100
HD = (f"   {'':<38}{'n':>5}{'net $':>10}{'PF':>6}{'win%':>7}{'excess':>8}{'z':>7}"
      f"{'research':>10}{'LOCKED':>10}{'maxDD':>8}")


def line(tag, s):
    if s is None:
        return f"   {tag:<38}  (no trades)"
    return (f"   {tag:<38}{s['n']:>5}{s['net']:>10,.0f}{s['pf']:>6.2f}{s['win']:>7.1f}"
            f"{s['exc']:>+8.1f}{s['z']:>+7.2f}{s['res']:>10,.0f}{s['lock']:>10,.0f}{s['dd']:>8,.0f}")


print("=" * W)
print("A. AS SPECIFIED vs THE MARGINAL-OPTIMAL VERSION")
print("=" * W)
print("   Marginal winners from 590,976 configurations: 4H zones, 60m confirmation, base 2 bars")
print("   under 0.6 ATR, departure over 1.0 ATR, continuation origin, 24h session, buffer")
print("   1.0 x ATR, 2R target, break filter ON, zones reusable.\n")
print(HD)
SPEC = dict(H=240, L=15, bk=3, bm=0.6, dm=1.0, zt=0, slo=570, shi=960,
            buf=0.15, tp=2.0, nb=0, age_d=5, osh=0, sd=0)
print(line("as specified (4H zone, 15M confirm)", go(**SPEC)))
print(line("  ... same, but confirm on 60m", go(**{**SPEC, "L": 60})))

BEST = dict(H=240, L=60, bk=2, bm=0.6, dm=1.0, zt=2, slo=0, shi=1440,
            buf=1.0, tp=2.0, nb=1, age_d=5, osh=0, sd=0)
print()
for ad in (2, 5, 12):
    print(line(f"marginal-optimal, zones live {ad}d", go(**{**BEST, "age_d": ad})))
print()
print(line("marginal-optimal, LONG only", go(**{**BEST, "sd": 1})))
print(line("marginal-optimal, SHORT only", go(**{**BEST, "sd": -1})))

print()
print("=" * W)
print("B. ONE STEP AWAY — plateau or spike?")
print("=" * W)
print(HD)
b = go(**BEST)
print(line("the marginal-optimal version", b))
print()
locks = []
for tag, mod in [("confirm 30m", dict(L=30)), ("confirm 15m", dict(L=15)),
                 ("zones 2H", dict(H=120)), ("zones 8H", dict(H=480)),
                 ("base k3", dict(bk=3)), ("base < 0.9 ATR", dict(bm=0.9)),
                 ("departure > 1.5 ATR", dict(dm=1.5)), ("any zone origin", dict(zt=0)),
                 ("reversal origin", dict(zt=1)), ("RTH session", dict(slo=570, shi=960)),
                 ("buffer 0.5 ATR", dict(buf=0.5)), ("buffer 0.15 ATR", dict(buf=0.15)),
                 ("target 1.5R", dict(tp=1.5)), ("target 3R", dict(tp=3.0)),
                 ("no break filter", dict(nb=0)), ("one shot per zone", dict(osh=1))]:
    s = go(**{**BEST, **mod})
    print(line(tag, s))
    if s:
        locks.append(s["lock"])
locks = np.array(locks)
print(f"\n   locked ${b['lock']:,.0f}   neighbours median ${np.median(locks):,.0f}, "
      f"{100*(locks < b['lock']).mean():.0f}% below, worst ${locks.min():,.0f}, "
      f"{100*(locks > 0).mean():.0f}% still positive")

print()
print("=" * W)
print("C. IS IT WORTH TRADING, AND DOES IT ADD TO THE BOS BOOK?")
print("=" * W)
print(f"   {'book':<28}{'block':<11}{'net $':>10}{'maxDD':>9}{'net/DD':>8}{'Sharpe':>8}")


def blocks(nm, p, ss):
    for bn, m, ND in [("full", np.ones(len(p), bool), len(u30)),
                      ("research", ss < CUT, NRES), ("LOCKED", ss >= CUT, NLOCK)]:
        y = p[m]
        if len(y) == 0:
            continue
        eq = np.cumsum(y); dd = (np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max()
        day = {}
        for v, q in zip(y, ss[m]):
            day[q] = day.get(q, 0.0) + v
        f = np.zeros(ND); f[:len(day)] = list(day.values())
        sh = f.mean() / f.std(ddof=1) * np.sqrt(252) if f.std() > 0 else 0
        print(f"   {nm:<28}{bn:<11}{y.sum():>10,.0f}{dd:>9,.0f}"
              f"{(y.sum()/dd if dd else np.inf):>8.2f}{sh:>8.2f}")
    print()


blocks("supply/demand 4H->60m", b["p"], b["ss"])
sys.path.insert(0, "research")
from tf_60m import trades
P3, E3, S3, sess3, _ = trades(30)
P6, E6, S6, sess6, _ = trades(60, dn=0.0)
d = {}
for p_, e_, s_ in [(P3, E3, sess3), (P6, E6, sess6)]:
    for v, q in zip(p_, s_[e_]):
        d[q] = d.get(q, 0.0) + v
sdd = {}
for v, q in zip(b["p"], b["ss"]):
    sdd[q] = sdd.get(q, 0.0) + v
allk = sorted(set(d) | set(sdd))
bos = np.array([d.get(q, 0.0) for q in allk])
sdv = np.array([sdd.get(q, 0.0) for q in allk])
ks = np.array(allk)
print(f"   BOS book days {(bos!=0).sum()}   S/D days {(sdv!=0).sum()}   "
      f"shared {((bos!=0)&(sdv!=0)).sum()}   daily correlation "
      f"{np.corrcoef(bos, sdv)[0,1]:+.3f}")
print()
for nm, x in [("BOS 30m + 60m book", bos), ("... plus supply/demand", bos + sdv)]:
    for bn, m, ND in [("full", np.ones(len(x), bool), len(u30)),
                      ("research", ks < CUT, NRES), ("LOCKED", ks >= CUT, NLOCK)]:
        y = x[m]
        eq = np.cumsum(y); dd = (np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max()
        f = np.zeros(ND); f[:len(y)] = y
        sh = f.mean() / f.std(ddof=1) * np.sqrt(252) if f.std() > 0 else 0
        print(f"   {nm:<28}{bn:<11}{y.sum():>10,.0f}{dd:>9,.0f}"
              f"{(y.sum()/dd if dd else np.inf):>8.2f}{sh:>8.2f}")
    print()
