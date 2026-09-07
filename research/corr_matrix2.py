"""Correlation matrices over the book as it now stands, and over the market states it trades in.

Three matrices:
  1. LEG x LEG      -- daily P&L correlation. Answers "are these the same trade in different
                       clothes", which is the only question a book-level matrix can answer.
  2. STATE x LEG    -- market conditions known BEFORE the session against each leg's P&L, with
                       Benjamini-Hochberg control, because 11 states x 8 legs is 88 tests and at
                       q = 0.10 four of them come up "significant" on noise alone.
  3. TERCILE x LEG  -- the same states as $/trade in low/mid/high buckets, which is where an
                       effect is readable even when the linear correlation is not.

Every state variable is computed from data that closed before the session it labels.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
from bos_choch import prep, SPECS
from tf_60m import trades as bos_trades
from sd_tf_best import go as sd_run, BEST as SD_BEST, SPEC as SD_SPEC

S = SPECS["MNQ"]
d30 = prep(30)
ALL = np.unique(d30["sess"])
IX = {q: j for j, q in enumerate(ALL)}
CUT = ALL[int(0.65 * len(ALL))]
NS = len(ALL)


def to_daily(p, ss):
    x = np.zeros(NS)
    for v, q in zip(p, ss):
        if q in IX:
            x[IX[q]] += v
    return x


# ---- the legs ------------------------------------------------------------------------------------
LEG = {}


def add_bos(nm, **kw):
    p, e, s_, sess, _ = bos_trades(**kw)
    LEG[nm] = (to_daily(p, sess[e]), p, sess[e])


add_bos("BOS 30m core", m=30)
add_bos("BOS 60m core", m=60, dn=0.0)
add_bos("BOS 30m LONG", m=30, sd=1)
add_bos("BOS 30m SHORT", m=30, sd=-1)
add_bos("BOS 15m", m=15)

for nm, kw in [("S/D 4H->60m", {}), ("S/D 4H->60m LONG", dict(sd=1)),
               ("S/D 4H->60m SHORT", dict(sd=-1)), ("S/D as specified", None)]:
    r = sd_run(**SD_SPEC) if kw is None else sd_run(**{**SD_BEST, **kw})
    LEG[nm] = (to_daily(r["p"], r["ss"]), r["p"], r["ss"])

names = list(LEG)
D = np.array([LEG[k][0] for k in names])

W = 108
print("=" * W)
print(f"1. LEG x LEG — daily P&L correlation, MNQ, {NS} sessions")
print("=" * W)
print("   Two legs at rho 0.9 are one leg paying commission twice.\n")
C = np.corrcoef(D)
print(f"   {'':<20}" + "".join(f"{i+1:>7}" for i in range(len(names))))
for i, k in enumerate(names):
    print(f"   {i+1:>2} {k:<17}" + "".join(f"{C[i, j]:>7.2f}" for j in range(len(names))))

print(f"\n   {'leg':<20}{'net $':>10}{'trades':>8}{'days':>7}{'max rho vs others':>20}{'closest':>20}")
for i, k in enumerate(names):
    off = C[i].copy(); off[i] = -9
    j = int(np.argmax(off))
    print(f"   {k:<20}{LEG[k][1].sum():>10,.0f}{len(LEG[k][1]):>8}{(D[i]!=0).sum():>7}"
          f"{off[j]:>20.2f}{names[j]:>20}")

BOOK = ["BOS 30m core", "BOS 60m core", "S/D 4H->60m"]
bi = [names.index(x) for x in BOOK]
print(f"\n   THE TRADEABLE BOOK — {' / '.join(BOOK)}")
Cb = np.corrcoef(D[bi])
for i, k in enumerate(BOOK):
    print(f"   {k:<22}" + "".join(f"{Cb[i, j]:>8.2f}" for j in range(3)))
ev = np.linalg.eigvalsh(Cb)[::-1]; ev = ev[ev > 0]; w = ev / ev.sum()
print(f"   variance explained  " + "  ".join(f"PC{i+1} {100*x:.0f}%" for i, x in enumerate(w)))
print(f"   effective number of bets = {np.exp(-(w*np.log(w)).sum()):.2f} out of 3 legs")
ev2 = np.linalg.eigvalsh(C)[::-1]; ev2 = ev2[ev2 > 0]; w2 = ev2 / ev2.sum()
print(f"   ... across all {len(names)} legs studied: {np.exp(-(w2*np.log(w2)).sum()):.2f} "
      f"independent bets, PC1 = {100*w2[0]:.0f}%")

# ---- market states, all knowable before the session ----------------------------------------------
# ALIGNMENT. `session_index` puts a bar before 09:30 into the PREVIOUS session, so a daily bar
# stamped 00:00 on date D carries the session id of D-1 while actually covering session D. Indexing
# a state by the daily bar's own session id therefore labels each session with the NEXT day's data
# -- a look-ahead that showed up as a +0.79 correlation between "prior day return" and the long
# leg's P&L before it was caught. The rule used here instead: every state is a function of daily
# bars up to and INCLUDING bar i, and it labels the session that bar i+1 covers. Nothing about the
# labelled session is used to build its own state.
dd = prep(1440)
di = dd["df"].index
cover = dd["sess"] + 1                 # the session a daily bar actually covers
o_, h_, l_, c_, v_ = dd["o"], dd["h"], dd["l"], dd["c"], dd["v"]
n = len(c_)
ret = np.r_[np.nan, np.diff(np.log(c_))]
rng = (h_ - l_)


def roll(x, k, f):
    """f over the k bars ENDING AT i, inclusive."""
    out = np.full(len(x), np.nan)
    for i in range(k - 1, len(x)):
        out[i] = f(x[i - k + 1:i + 1])
    return out


F = {}
F["prior day return"] = ret
F["prior day gap"] = np.r_[np.nan, (o_[1:] - c_[:-1]) / np.maximum(dd["atr"][:-1], 1e-9)]
F["5d vol / 20d vol"] = roll(ret, 5, np.nanstd) / np.maximum(roll(ret, 20, np.nanstd), 1e-12)
F["ATR / 20d mean ATR"] = dd["atr"] / np.maximum(roll(dd["atr"], 20, np.nanmean), 1e-9)
F["prior range / 20d"] = rng / np.maximum(roll(rng, 20, np.nanmean), 1e-9)
F["dist from 200 EMA"] = (c_ - dd["ema"]) / np.maximum(dd["atr"], 1e-9)
F["20d momentum"] = np.r_[[np.nan] * 20, (c_[20:] - c_[:-20]) / np.maximum(dd["atr"][20:], 1e-9)]
F["5d momentum"] = np.r_[[np.nan] * 5, (c_[5:] - c_[:-5]) / np.maximum(dd["atr"][5:], 1e-9)]
F["prior volume / 20d"] = v_ / np.maximum(roll(v_, 20, np.nanmean), 1e-9)
F["2-day run"] = np.r_[np.nan, np.nan, np.sign(ret[1:-1]) + np.sign(ret[2:])]

SMAP = {}
for k, v in F.items():
    a = np.full(NS, np.nan)
    for i in range(n - 1):                       # bar i labels the session bar i+1 covers
        q = cover[i + 1]
        if q in IX and not np.isnan(v[i]):
            a[IX[q]] = v[i]
    SMAP[k] = a
# calendar states describe the labelled session itself, which is known in advance
for k, f in [("day of week", lambda t: t.dayofweek), ("day of month", lambda t: t.day)]:
    a = np.full(NS, np.nan)
    for i in range(n - 1):
        q = cover[i + 1]
        if q in IX:
            a[IX[q]] = f(di[i + 1])
    SMAP[k] = a
snames = list(SMAP)


def bh(ps, q=0.10):
    o = np.argsort(ps); m = len(ps); keep = np.zeros(m, bool); thr = 0.0
    for r, i in enumerate(o, 1):
        if ps[i] <= q * r / m:
            thr = ps[i]
    if thr > 0:
        keep = ps <= thr
    return keep


print()
print("=" * W)
print("2. STATE x LEG — correlation of a pre-session condition with that day's P&L")
print("=" * W)
print("   Restricted to days the leg actually traded. * marks survival of Benjamini-Hochberg")
print(f"   at q = 0.10 across all {len(snames) * len(names)} tests.\n")
R = np.full((len(snames), len(names)), np.nan)
Pv = np.ones((len(snames), len(names)))
for a, sk in enumerate(snames):
    for b, lk in enumerate(names):
        x = SMAP[sk]; y = D[b]
        m = (~np.isnan(x)) & (y != 0)
        if m.sum() < 25:
            continue
        r = np.corrcoef(x[m], y[m])[0, 1]
        R[a, b] = r
        t = r * np.sqrt((m.sum() - 2) / max(1e-12, 1 - r * r))
        from math import erfc
        Pv[a, b] = erfc(abs(t) / np.sqrt(2))
flat = Pv.ravel(); keep = bh(flat).reshape(Pv.shape)
print(f"   {'':<22}" + "".join(f"{i+1:>8}" for i in range(len(names))))
for a, sk in enumerate(snames):
    row = ""
    for b in range(len(names)):
        v = R[a, b]
        row += ("     n/a" if np.isnan(v) else f"{v:>7.2f}" + ("*" if keep[a, b] else " "))
    print(f"   {sk:<22}{row}")
print(f"\n   survivors at q = 0.10: {int(keep.sum())} of {keep.size}")
print(f"   smallest p anywhere: {flat.min():.4f}")

print()
print("=" * W)
print("3. TERCILE x LEG — $/trade in the low / mid / high third of each state")
print("=" * W)
print("   A linear correlation misses a hump. This does not.\n")
for a, sk in enumerate(snames):
    parts = []
    for b, lk in enumerate(BOOK):
        j = names.index(lk)
        x = SMAP[sk]; p = LEG[lk][1]; ss = LEG[lk][2]
        xv = np.array([x[IX[q]] if q in IX else np.nan for q in ss])
        m = ~np.isnan(xv)
        if m.sum() < 30:
            parts.append(f"{lk}: n/a"); continue
        q1, q2 = np.percentile(xv[m], [33.3, 66.7])
        buckets = [p[m & (xv <= q1)], p[m & (xv > q1) & (xv <= q2)], p[m & (xv > q2)]]
        parts.append(f"{lk:<13}" + "".join(
            f"{(b.mean() if len(b) else float('nan')):>7,.0f}" if len(b) else f"{'--':>7}"
            for b in buckets))
    print(f"   {sk:<22}" + "   ".join(parts))
print(f"\n   {'':<22}   " + "   ".join(f"{k:<13}{'low':>7}{'mid':>7}{'high':>7}" for k in BOOK))

print()
print("=" * W)
print("4. THE ONE ACTIONABLE THING, TESTED PROPERLY")
print("=" * W)
print("   The matrices say the BOS 30m leg is a volatility-expansion trade: it loses in the")
print("   quietest third and earns ~$250/trade in the noisiest. That is an in-sample")
print("   description of 922 sessions. The test is whether a threshold set on the RESEARCH")
print("   block alone still works on the LOCKED block it never saw.\n")
RES = ALL < CUT
for sk in ["ATR / 20d mean ATR", "5d vol / 20d vol", "prior range / 20d"]:
    x = SMAP[sk]
    xr = x[RES & ~np.isnan(x)]
    thr = np.percentile(xr, 33.3)              # fixed on the research block ONLY
    print(f"   {sk}   research-block 33rd percentile = {thr:.3f}")
    print(f"      {'':<20}{'trades':>8}{'net $':>10}{'$/trade':>9}{'win%':>7}{'maxDD':>9}")
    for lk in BOOK:
        p = LEG[lk][1]; ss = LEG[lk][2]
        xv = np.array([x[IX[q]] if q in IX else np.nan for q in ss])
        for bn, bm in [("research", np.array([q < CUT for q in ss])),
                       ("LOCKED", np.array([q >= CUT for q in ss]))]:
            for fn, fm in [("all", np.ones(len(p), bool)), ("quiet third REMOVED", xv > thr)]:
                m = bm & fm & ~np.isnan(xv)
                if m.sum() < 5:
                    continue
                y = p[m]; eq = np.cumsum(y)
                dd = (np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max()
                print(f"      {lk[:11]+' '+bn+' '+fn:<20}{len(y):>8}{y.sum():>10,.0f}"
                      f"{y.mean():>9,.0f}{100*(y>0).mean():>7.1f}{dd:>9,.0f}")
        print()
