"""Is the 1-hour chart's higher win rate a real property, and does it add anything to the 30m book?"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
from bos_choch import prep

TICK = 0.25; PV = 2.0; COMM = 1.0; EC = 2.0 * TICK; SE = TICK


def trades(m, k=3, e=200, am=2.0, nb=2, tp=2.0, dn=1.0, lo=570, hi=960, sd=0):
    d = prep(m, swing_k=k, ema_n=e)
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    sess, mod, ph, pl, ema_, atr_ = d["sess"], d["mod"], d["ph"], d["pl"], d["ema"], d["atr"]
    n = len(c)
    pos = 0; entry = 0.0; stopL = np.nan; tp_ = np.nan; bias = 0; rn = 0
    bh = bl = np.nan; aSig = np.nan; pend = 0; ei = 0
    P = []; E = []; S = []
    for i in range(1, n):
        ns = sess[i] != sess[i - 1]
        if pend != 0 and pos == 0:
            pos = pend; entry = o[i]; ei = i; pend = 0
            risk = am * aSig; stopL = entry - pos * risk
            tp_ = entry + pos * tp * risk if tp > 0 else np.nan
        if pos != 0:
            hit = (l[i] <= stopL) if pos == 1 else (h[i] >= stopL)
            won = (tp > 0) and ((h[i] >= tp_) if pos == 1 else (l[i] <= tp_))
            if hit and won:
                won = False
            if hit or won:
                if hit:
                    px = o[i] if ((pos == 1 and o[i] < stopL) or (pos == -1 and o[i] > stopL)) else stopL
                    px += -SE if pos == 1 else SE
                else:
                    px = o[i] if ((pos == 1 and o[i] > tp_) or (pos == -1 and o[i] < tp_)) else tp_
                P.append(pos * (px - entry) * PV - 2 * EC * PV - COMM); E.append(ei); S.append(pos)
                pos = 0
        bU = (not np.isnan(ph[i])) and c[i] > ph[i] and (np.isnan(bh) or ph[i] != bh)
        bD = (not np.isnan(pl[i])) and c[i] < pl[i] and (np.isnan(bl) or pl[i] != bl)
        if bU: bh = ph[i]
        if bD: bl = pl[i]
        if bU: rn = rn + 1 if bias == 1 else 1; bias = 1
        if bD: rn = rn + 1 if bias == -1 else 1; bias = -1
        a = atr_[i]
        ready = a > 0 and not np.isnan(a) and not np.isnan(ema_[i])
        ok = i + 1 < n and lo <= mod[i] < hi and lo <= mod[i + 1] < hi and not ns
        if pos == 0 and pend == 0 and ok and ready and abs(c[i] - ema_[i]) / a >= dn:
            s_ = 1 if (bU and rn >= nb and c[i] > ema_[i]) else (-1 if (bD and rn >= nb and c[i] < ema_[i]) else 0)
            if s_ and (sd == 0 or sd == s_):
                aSig = a; pend = s_
        if pos != 0 and tp <= 0 and ((pos == 1 and bD) or (pos == -1 and bU)) and i + 1 < n:
            P.append(pos * (o[i + 1] - entry) * PV - 2 * EC * PV - COMM); E.append(ei); S.append(pos)
            pos = 0
    d2 = prep(m, swing_k=k, ema_n=e)
    return np.array(P), np.array(E), np.array(S), d2["sess"], d2["df"].index


W = 96
print("=" * W)
print("A. IS THE 1-HOUR WIN RATE A PLATEAU? — 60m, one parameter moved at a time")
print("=" * W)
print("   At a 2R target a driftless path wins 33.3%. Excess over that is what the ENTRY earned.\n")
print(f"   {'variant':<28}{'n':>6}{'win%':>8}{'excess':>9}{'net $':>10}{'PF':>7}{'maxDD':>9}{'binom z':>9}")


def show(tag, P, S, tp=2.0):
    if len(P) == 0:
        print(f"   {tag:<28}   (no trades)"); return
    b = 1.0 / (1.0 + tp); w = (P > 0).mean()
    eq = np.cumsum(P); dd = (np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max()
    gw = P[P > 0].sum(); gl = -P[P <= 0].sum()
    z = (w - b) / np.sqrt(b * (1 - b) / len(P))
    print(f"   {tag:<28}{len(P):>6}{100*w:>8.1f}{100*(w-b):>+9.1f}{P.sum():>10,.0f}"
          f"{(gw/gl if gl else np.inf):>7.2f}{dd:>9,.0f}{z:>+9.2f}")


P0, E0, S0, sess0, idx0 = trades(60)
show("60m incumbent spec", P0, S0)
for tag, kw in [("nBos 1", dict(nb=1)), ("nBos 3", dict(nb=3)),
                ("stop 1.5xATR", dict(am=1.5)), ("stop 2.5xATR", dict(am=2.5)),
                ("swing k2", dict(k=2)), ("swing k4", dict(k=4)),
                ("EMA 100", dict(e=100)), ("EMA 50", dict(e=50)),
                ("dist >= 0.0", dict(dn=0.0)), ("dist >= 1.5", dict(dn=1.5)),
                ("longs only", dict(sd=1)), ("shorts only", dict(sd=-1))]:
    P, E, S, _, _ = trades(60, **kw)
    show(tag, P, S)

print(f"\n   30m incumbent, for reference:")
P3, E3, S3, sess3, idx3 = trades(30)
show("30m incumbent spec", P3, S3)

print()
print("=" * W)
print("B. DOES A 60m LEG DIVERSIFY THE 30m BOOK?")
print("=" * W)
d3 = np.zeros(2000); d6 = np.zeros(2000)
u = np.unique(np.r_[sess3[E3], sess0[E0]])
m3 = {s: 0.0 for s in u}; m6 = {s: 0.0 for s in u}
for p, e in zip(P3, E3): m3[sess3[e]] += p
for p, e in zip(P0, E0): m6[sess0[e]] += p
a = np.array([m3[s] for s in u]); b = np.array([m6[s] for s in u])
both = np.array([1.0 if (m3[s] != 0 and m6[s] != 0) else 0.0 for s in u])
print(f"   sessions with a 30m trade: {(a!=0).sum()}   with a 60m trade: {(b!=0).sum()}"
      f"   with BOTH: {int(both.sum())}")
print(f"   daily P&L correlation: {np.corrcoef(a, b)[0,1]:+.3f}")
comb = a + b
eq = np.cumsum(comb); dd = (np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max()
eq3 = np.cumsum(a); dd3 = (np.maximum.accumulate(np.r_[0, eq3]) - np.r_[0, eq3]).max()
eq6 = np.cumsum(b); dd6 = (np.maximum.accumulate(np.r_[0, eq6]) - np.r_[0, eq6]).max()
NS = 922
print(f"\n   {'book':<22}{'net $':>10}{'maxDD':>10}{'net/DD':>9}{'daily Sharpe':>14}")
for nm, x, D in [("30m alone", a, dd3), ("60m alone", b, dd6), ("30m + 60m", comb, dd)]:
    full = np.zeros(NS); full[:len(x)] = x
    sh = full.mean() / full.std(ddof=1) * np.sqrt(252) if full.std() > 0 else 0
    print(f"   {nm:<22}{x.sum():>10,.0f}{D:>10,.0f}{x.sum()/D:>9.2f}{sh:>14.2f}")

print()
print("=" * W)
print("C. THE TEST THAT DECIDES IT — the combined book, split into research and LOCKED")
print("=" * W)
cut = np.unique(sess3)[int(0.65 * len(np.unique(sess3)))]
res_m = u < cut
print(f"   {'book':<22}{'block':<12}{'n days':>8}{'net $':>10}{'maxDD':>10}{'net/DD':>9}{'Sharpe':>9}")
NR = int((np.unique(sess3) < cut).sum()); NL = 922 - NR
for nm, x in [("30m alone", a), ("60m alone", b), ("30m + 60m", comb)]:
    for bn, msk, ND in [("research", res_m, NR), ("LOCKED", ~res_m, NL)]:
        y = x[msk]
        eqy = np.cumsum(y); ddy = (np.maximum.accumulate(np.r_[0, eqy]) - np.r_[0, eqy]).max()
        full = np.zeros(ND); full[:len(y)] = y
        sh = full.mean() / full.std(ddof=1) * np.sqrt(252) if full.std() > 0 else 0
        print(f"   {nm:<22}{bn:<12}{(y!=0).sum():>8}{y.sum():>10,.0f}{ddy:>10,.0f}"
              f"{(y.sum()/ddy if ddy else np.inf):>9.2f}{sh:>9.2f}")
    print()

print("   Paired by session, the 60m leg's contribution on the LOCKED block only:")
y = b[~res_m]
t = y.mean() / (y.std(ddof=1) / np.sqrt(len(y))) if y.std() > 0 else np.nan
print(f"      net ${y.sum():,.0f} over {(y!=0).sum()} trading days, t = {t:+.2f}")

print("\n   Stationary block bootstrap, 10,000 paths, combined book, LOCKED block:")
rng = np.random.default_rng(7)
z = comb[~res_m]; nz = len(z); L = 20
sims = np.empty(10000)
for s_ in range(10000):
    out_ = np.empty(nz); f = 0
    while f < nz:
        st = rng.integers(0, nz); ln = min(rng.geometric(1.0 / L), nz - f)
        for q in range(ln):
            out_[f + q] = z[(st + q) % nz]
        f += ln
    sims[s_] = out_.sum()
print(f"      p5 ${np.percentile(sims,5):,.0f}   median ${np.median(sims):,.0f}   "
      f"p95 ${np.percentile(sims,95):,.0f}   P(net<0) = {100*(sims<0).mean():.1f}%")
