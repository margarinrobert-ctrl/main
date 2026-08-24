"""Correlation matrices over the book as it is actually shipped.

The earlier matrix study used the marginal-optimal supply/demand configuration. The script that
shipped carries two different ones -- preset A (4H zones, 60m chart, 1.5R) and preset B (4H zones,
30m chart, continuation origin, RTH, 1R) -- so the structure has to be measured again on those.

The question a book-level matrix answers is never "is each leg profitable". It is "are these the
same trade wearing different clothes", and, for a leg that is known to be long-carried, "is it
just the long half of something I already own".
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
from bos_choch import prep
from tf_60m import trades as bos_trades
from sd_pine_mirror import pine_mirror

d30 = prep(30)
ALL = np.unique(d30["sess"])
IX = {q: j for j, q in enumerate(ALL)}
CUT = ALL[int(0.65 * len(ALL))]
NS = len(ALL)
NRES = int((ALL < CUT).sum()); NLOCK = NS - NRES

A_CFG = dict(H=240, L=60, bk=2, bm=0.9, dm=1.0, buf=0.5, tp_r=1.5, age_bars=288)
B_CFG = dict(H=240, L=30, bk=3, bm=0.9, dm=1.0, buf=1.0, tp_r=1.0, age_bars=576,
             zt=2, slo=570, shi=960)


def daily(p, ss):
    x = np.zeros(NS)
    for v, q in zip(p, ss):
        if q in IX:
            x[IX[q]] += v
    return x


LEG = {}


def add_bos(nm, **kw):
    p, e, s_, sess, _ = bos_trades(**kw)
    ss = sess[e]
    LEG[nm] = (daily(p, ss), p, ss)


def add_sd(nm, cfg, L, side=0):
    p, e, x = pine_mirror(**cfg)
    dL = prep(L); ss = dL["sess"][np.array(e)] if len(e) else np.array([])
    # the mirror is two-sided; split by reading the sign back off the trade
    LEG[nm] = (daily(p, ss), p, ss)


add_bos("BOS 30m core", m=30)
add_bos("BOS 60m core", m=60, dn=0.0)
add_bos("BOS 30m LONG", m=30, sd=1)
add_bos("BOS 30m SHORT", m=30, sd=-1)
add_bos("BOS 60m LONG", m=60, dn=0.0, sd=1)
add_sd("S/D preset A", A_CFG, 60)
add_sd("S/D preset B", B_CFG, 30)

names = list(LEG)
D = np.array([LEG[k][0] for k in names])
W = 104


def hdr(t):
    print("=" * W); print(t); print("=" * W)


hdr(f"1. LEG x LEG — daily P&L correlation, MNQ, {NS} sessions")
C = np.corrcoef(D)
print(f"   {'':<18}" + "".join(f"{i+1:>8}" for i in range(len(names))))
for i, k in enumerate(names):
    print(f"   {i+1:>2} {k:<15}" + "".join(f"{C[i, j]:>8.2f}" for j in range(len(names))))

print(f"\n   {'leg':<18}{'net $':>10}{'trades':>8}{'days':>7}{'max rho':>9}{'closest leg':>18}")
for i, k in enumerate(names):
    off = C[i].copy(); off[i] = -9
    j = int(np.argmax(off))
    print(f"   {k:<18}{LEG[k][1].sum():>10,.0f}{len(LEG[k][1]):>8}{(D[i]!=0).sum():>7}"
          f"{off[j]:>9.2f}{names[j]:>18}")


def pca(idx, label):
    Cx = np.corrcoef(D[idx])
    ev = np.linalg.eigvalsh(Cx)[::-1]; ev = ev[ev > 0]; w = ev / ev.sum()
    n = np.exp(-(w * np.log(w)).sum())
    print(f"   {label:<44}{n:>6.2f} of {len(idx)}   PC1 {100*w[0]:>4.0f}%")


print()
hdr("2. HOW MANY INDEPENDENT BETS IS THE BOOK?")
print(f"   {'book':<44}{'eff. bets':>12}{'':>12}")
pca([names.index(x) for x in ["BOS 30m core", "BOS 60m core"]], "BOS alone (30m + 60m)")
pca([names.index(x) for x in ["BOS 30m core", "BOS 60m core", "S/D preset A"]],
    "BOS + supply/demand A")
pca([names.index(x) for x in ["BOS 30m core", "BOS 60m core", "S/D preset B"]],
    "BOS + supply/demand B")
pca([names.index(x) for x in ["BOS 30m core", "BOS 60m core", "S/D preset A", "S/D preset B"]],
    "BOS + BOTH supply/demand presets")

print()
hdr("3. IS PRESET A JUST THE LONG HALF OF SOMETHING ALREADY OWNED?")
print("   Preset A earns $26,431 from longs and LOSES $7,644 on shorts, so the fair test is")
print("   against the long legs specifically, not against the two-sided books.\n")
for a in ["S/D preset A", "S/D preset B"]:
    ia = names.index(a)
    for b in ["BOS 30m LONG", "BOS 60m LONG", "BOS 30m core", "BOS 60m core"]:
        ib = names.index(b)
        sa = D[ia] != 0; sb = D[ib] != 0
        print(f"   {a:<15} vs {b:<15} rho {C[ia, ib]:>+6.2f}   "
              f"shared days {int((sa & sb).sum()):>3} of {int(sa.sum())}/{int(sb.sum())}")
    print()

print()
hdr("4. WHAT EACH LEG ADDS — research and locked kept apart")
BASE = ["BOS 30m core", "BOS 60m core"]


def book(keys):
    return sum(D[names.index(k)] for k in keys)


def report(label, x):
    row = f"   {label:<38}"
    for bn, m, ND in [("full", np.ones(NS, bool), NS), ("research", ALL < CUT, NRES),
                      ("LOCKED", ALL >= CUT, NLOCK)]:
        y = x[m]
        eq = np.cumsum(y); dd = (np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max()
        sh = y.mean() / y.std(ddof=1) * np.sqrt(252) if y.std() > 0 else 0
        row += f"{y.sum():>10,.0f}{dd:>9,.0f}{sh:>7.2f}"
    print(row)


print(f"   {'':<38}{'full $':>10}{'DD':>9}{'Sh':>7}{'res $':>10}{'DD':>9}{'Sh':>7}"
      f"{'LOCK $':>10}{'DD':>9}{'Sh':>7}")
report("BOS 30m + 60m", book(BASE))
report("  + supply/demand A", book(BASE + ["S/D preset A"]))
report("  + supply/demand B", book(BASE + ["S/D preset B"]))
report("  + both S/D presets", book(BASE + ["S/D preset A", "S/D preset B"]))
report("supply/demand A alone", book(["S/D preset A"]))
report("supply/demand B alone", book(["S/D preset B"]))

print()
hdr("5. STATE x LEG — what market does each leg want?")
print("   States are functions of daily bars up to and including bar i, labelling the session")
print("   bar i+1 covers. * survives Benjamini-Hochberg at q = 0.10 across every test here.\n")
dd_ = prep(1440)
di = dd_["df"].index
cover = dd_["sess"] + 1
o_, h_, l_, c_, v_ = dd_["o"], dd_["h"], dd_["l"], dd_["c"], dd_["v"]
ret = np.r_[np.nan, np.diff(np.log(c_))]
rng = h_ - l_


def roll(x, k, f):
    out = np.full(len(x), np.nan)
    for i in range(k - 1, len(x)):
        out[i] = f(x[i - k + 1:i + 1])
    return out


F = {"prior day return": ret,
     "5d vol / 20d vol": roll(ret, 5, np.nanstd) / np.maximum(roll(ret, 20, np.nanstd), 1e-12),
     "ATR / 20d mean ATR": dd_["atr"] / np.maximum(roll(dd_["atr"], 20, np.nanmean), 1e-9),
     "prior range / 20d": rng / np.maximum(roll(rng, 20, np.nanmean), 1e-9),
     "dist from 200 EMA": (c_ - dd_["ema"]) / np.maximum(dd_["atr"], 1e-9),
     "20d momentum": np.r_[[np.nan]*20, (c_[20:] - c_[:-20]) / np.maximum(dd_["atr"][20:], 1e-9)],
     "5d momentum": np.r_[[np.nan]*5, (c_[5:] - c_[:-5]) / np.maximum(dd_["atr"][5:], 1e-9)],
     "prior volume / 20d": v_ / np.maximum(roll(v_, 20, np.nanmean), 1e-9)}
SM = {}
for k, v in F.items():
    a = np.full(NS, np.nan)
    for i in range(len(c_) - 1):
        q = cover[i + 1]
        if q in IX and not np.isnan(v[i]):
            a[IX[q]] = v[i]
    SM[k] = a

from math import erfc
sn = list(SM)
R = np.full((len(sn), len(names)), np.nan); Pv = np.ones_like(R)
for a, sk in enumerate(sn):
    for b in range(len(names)):
        x = SM[sk]; y = D[b]
        m = (~np.isnan(x)) & (y != 0)
        if m.sum() < 25:
            continue
        r = np.corrcoef(x[m], y[m])[0, 1]
        R[a, b] = r
        t = r * np.sqrt((m.sum() - 2) / max(1e-12, 1 - r * r))
        Pv[a, b] = erfc(abs(t) / np.sqrt(2))
fl = Pv.ravel(); o = np.argsort(fl); thr = 0.0
for r_, i_ in enumerate(o, 1):
    if fl[i_] <= 0.10 * r_ / len(fl):
        thr = fl[i_]
keep = (Pv <= thr) if thr > 0 else np.zeros_like(Pv, bool)
print(f"   {'':<22}" + "".join(f"{i+1:>8}" for i in range(len(names))))
for a, sk in enumerate(sn):
    row = ""
    for b in range(len(names)):
        v = R[a, b]
        row += "     n/a" if np.isnan(v) else f"{v:>7.2f}" + ("*" if keep[a, b] else " ")
    print(f"   {sk:<22}{row}")
print(f"\n   survivors {int(keep.sum())} of {keep.size}")
