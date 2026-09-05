"""What survives, and — more useful — what the search itself proves about its own output."""
from __future__ import annotations

import pickle
import sys

import numpy as np

sys.path.insert(0, "research")
from bos_choch import prep

out = np.load("results/alpha/af_out.npy"); meta = np.load("results/alpha/af_meta.npy")
names, rules, EXITS = pickle.load(open("results/alpha/af_rules.pkl", "rb"))

RN, RNET, RW, RGW, RGL, RDD, RTG = (out[:, i] for i in range(7))
LN, LNET, LW, LGW, LGL, LDD, LTG = (out[:, 7 + i] for i in range(7))
N = RN + LN; NET = RNET + LNET; WN = RW + LW; TG = RTG + LTG
PF = (RGW + LGW) / np.maximum(RGL + LGL, 1e-9)
DD = np.maximum(RDD, LDD)
RI, SIDE, GI = meta[:, 0], meta[:, 1], meta[:, 2]
AM = np.array([EXITS[g][0] for g in GI]); TP = np.array([EXITS[g][1] for g in GI])
FL = np.array([EXITS[g][2] for g in GI])

ok = (RN >= 30) & (LN >= 15) & (N >= 60)
W = 104


def hdr(t):
    print("=" * W); print(t); print("=" * W)


def desc(j):
    r = rules[RI[j]]
    am, tp, fl = EXITS[GI[j]]
    return (("LONG  " if SIDE[j] == 1 else "SHORT ") + " AND ".join(names[i] for i in r) +
            f"   [stop {am}xATR, target {tp}R" + (f", flat {fl//60}:00]" if fl else "]"))


print(f"{len(out):,} strategies; {ok.sum():,} with enough trades to score "
      f"({len(rules):,} rules x 2 directions x {len(EXITS)} exits)\n")

idx = np.where(ok)[0]
hdr("1. THE SELECTION CURVE — what does picking the best on research actually buy?")
print("   Strategies sorted by RESEARCH P&L, then their LOCKED P&L read once, in bands.\n")
o_ = idx[np.argsort(-RNET[idx])]
print(f"   {'research rank band':<26}{'n':>8}{'median research $':>20}{'median LOCKED $':>18}")
bands = [(0, 1), (0, 10), (0, 100), (0, 1000), (0, len(o_) // 10),
         (len(o_) // 4, len(o_) // 2), (len(o_) // 2, len(o_))]
for a, b in bands:
    sl = o_[a:b]
    if len(sl) == 0:
        continue
    lab = f"top {b}" if a == 0 else f"{100*a//len(o_)}-{100*b//len(o_)}th percentile"
    print(f"   {lab:<26}{len(sl):>8}{np.median(RNET[sl]):>20,.0f}{np.median(LNET[sl]):>18,.0f}")
r1 = np.argsort(np.argsort(RNET[idx])); r2 = np.argsort(np.argsort(LNET[idx]))
print(f"\n   rank correlation research vs locked: {np.corrcoef(r1, r2)[0,1]:+.3f}")
print(f"   median locked over ALL scored strategies: ${np.median(LNET[idx]):,.0f}")
print(f"   a RANDOM pick lands at the {100*(LNET[idx] < np.median(LNET[idx])).mean():.0f}th "
      f"percentile of locked P&L by construction; the question is where the SELECTED one lands.")
best = o_[0]
pctile = 100 * (LNET[idx] < LNET[best]).mean()
print(f"   the best-on-research strategy lands at the {pctile:.1f}th percentile of locked P&L.")

hdr("2. THE WINNER, READ ONCE")
print(f"   research ${RNET[best]:,.0f}  ->  LOCKED ${LNET[best]:,.0f}   "
      f"{int(N[best])} trades, PF {PF[best]:.2f}, maxDD ${DD[best]:,.0f}")
print(f"      {desc(best)}")
print(f"\n   best on LOCKED (hindsight, unattainable): ${LNET[idx].max():,.0f}")
print(f"   for scale, on the same locked block: BOS 30m $8,932, S/D preset A $14,638")

hdr("3. SECTION 4c — is the search choosing a direction?")
for nm, s in [("all", ok), ("LONG rules", ok & (SIDE == 1)), ("SHORT rules", ok & (SIDE == -1))]:
    ii = np.where(s)[0]
    j = ii[np.argmax(RNET[ii])]
    print(f"   {nm:<14}n={s.sum():>7,}   median locked ${np.median(LNET[s]):>8,.0f}   "
          f"best on research ${RNET[j]:>8,.0f} -> locked ${LNET[j]:>8,.0f}")
print(f"\n   share of the top 100 on research that are LONG: "
      f"{100*(SIDE[o_[:100]] == 1).mean():.0f}%")

hdr("4. THE BARRIER BOUND — only where it applies")
print("   With no time stop the trade runs to one barrier or the other, so a driftless path")
print("   wins exactly 1/(1+R). With a session flatten most trades touch neither and the bound")
print("   is meaningless -- the IVB study made that mistake and it is not repeated here.\n")
print(f"   {'geometry':<34}{'n':>9}{'mean win %':>12}{'bound':>8}{'EXCESS':>9}{'best':>9}")
for gi, (am, tp, fl) in enumerate(EXITS):
    s = ok & (GI == gi)
    if s.sum() < 50:
        continue
    wr = 100 * WN[s] / N[s]
    if fl:
        print(f"   {f'stop {am}xATR, {tp}R, flat {fl//60}:00':<34}{s.sum():>9,}"
              f"{wr.mean():>12.1f}{'n/a':>8}{'n/a':>9}{'n/a':>9}")
    else:
        b = 100.0 / (1.0 + tp)
        print(f"   {f'stop {am}xATR, {tp}R, no time stop':<34}{s.sum():>9,}{wr.mean():>12.1f}"
              f"{b:>8.1f}{wr.mean()-b:>+9.2f}{wr.max()-b:>+9.2f}")

hdr("5. THE MATCHED NULL — random rules with the same trade counts")
print("   A bootstrap cannot detect a regime bet. A rule that fires at RANDOM bars, with the")
print("   same count and the same exit geometry, can: it inherits the drift and nothing else.\n")
rng = np.random.default_rng(7)
d = prep(30); nbar = len(d["c"])
us = np.unique(d["sess"]); sidx = np.searchsorted(us, d["sess"])
cut = np.int64(int(0.65 * len(us)))
from alpha_factory import price_all, walk
res = {}
for gi in (0, 1):
    am, tp, fl = EXITS[gi]
    for s in (1, -1):
        eb = np.zeros(nbar, np.int64); ep = np.zeros(nbar); okk = np.zeros(nbar, np.int64)
        price_all(d["o"], d["h"], d["l"], d["c"], d["atr"], d["mod"].astype(np.int64),
                  s, am, tp, fl, eb, ep, okk)
        res[(gi, s)] = (eb, ep, okk)
print(f"   {'geometry / side':<28}{'real median locked':>20}{'random median locked':>22}"
      f"{'real beats random':>19}")
for gi in (0, 1):
    for s in (1, -1):
        sel = ok & (GI == gi) & (SIDE == s)
        if sel.sum() < 50:
            continue
        eb, ep, okk = res[(gi, s)]
        tgt_n = int(np.median(N[sel]))
        sims = np.empty(400)
        for q in range(400):
            trig = np.sort(rng.choice(nbar - 2, size=min(tgt_n * 6, nbar - 2), replace=False))
            o2 = np.zeros((1, 14))
            walk(trig.astype(np.int64), eb, ep, okk, sidx, cut, o2, 0)
            sims[q] = o2[0, 8]
        rm = np.median(LNET[sel])
        print(f"   {f'{EXITS[gi][1]}R, ' + ('long' if s == 1 else 'short'):<28}"
              f"{rm:>20,.0f}{np.median(sims):>22,.0f}{100*(sims < rm).mean():>18.0f}%")

hdr("6. THE SHORTLIST — positive on BOTH blocks, ranked by the weaker one")
d2 = ok & (RNET > 0) & (LNET > 0) & (N >= 100) & (DD < 4000)
print(f"   {int(d2.sum()):,} of {int(ok.sum()):,} qualify ({100*d2.sum()/ok.sum():.1f}%)\n")
di = np.where(d2)[0]
if len(di):
    for j in di[np.argsort(-np.minimum(RNET[di], LNET[di]))[:10]]:
        print(f"   research ${RNET[j]:>7,.0f}  locked ${LNET[j]:>7,.0f}  {int(N[j]):>4} trades  "
              f"PF {PF[j]:.2f}  DD ${DD[j]:>6,.0f}")
        print(f"      {desc(j)}")
