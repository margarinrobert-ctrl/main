"""Validate the 16.2M sweep, then do the part a list of winners cannot do: re-simulate the
survivors in full, cluster them so near-duplicates collapse, and build a portfolio from what is
left."""
from __future__ import annotations

import sys
import time

import numpy as np
from numba import njit

sys.path.insert(0, "research")
from bos_choch import prep
from alpha_factory2 import build_conditions, price_one, EXITS, PV, TICK, COMM, EC, SE

Z = np.load("results/alpha/af2.npz", allow_pickle=True)
res_net, res_n = Z["res_net"], Z["res_n"]
lok_net, lok_n = Z["lok_net"], Z["lok_n"]
combos, names = Z["combos"], list(Z["names"])
NVAR = 2 * len(EXITS)
total = len(res_net)
NET = res_net + lok_net
N = res_n + lok_n
RULE = np.arange(total) // NVAR
VAR = np.arange(total) % NVAR
SIDE = np.where(VAR < len(EXITS), 1, -1)
GI = VAR % len(EXITS)

ok = (res_n >= 30) & (lok_n >= 15) & (N >= 60)
W = 104


def hdr(t):
    print("=" * W); print(t); print("=" * W)


def desc(j):
    r = combos[RULE[j]]
    am, tp, fl = EXITS[GI[j]]
    txt = " AND ".join(names[i] for i in r if i >= 0)
    return (("LONG  " if SIDE[j] == 1 else "SHORT ") + txt +
            f"   [stop {am}xATR, target {tp}R" + (f", flat {fl//60}:00]" if fl else ", no time stop]"))


print(f"{total:,} strategies from {len(combos):,} rules; {ok.sum():,} scored\n")
idx = np.where(ok)[0]

hdr("1. SELECTION CURVE")
o_ = idx[np.argsort(-res_net[idx])]
print(f"   {'research rank band':<26}{'n':>10}{'median research $':>20}{'median LOCKED $':>18}")
for a, b, lab in [(0, 1, "top 1"), (0, 10, "top 10"), (0, 100, "top 100"),
                  (0, 1000, "top 1,000"), (0, 100000, "top 100,000"),
                  (len(o_)//2, len(o_), "bottom half")]:
    sl = o_[a:b]
    if not len(sl):
        continue
    print(f"   {lab:<26}{len(sl):>10,}{np.median(res_net[sl]):>20,.0f}"
          f"{np.median(lok_net[sl]):>18,.0f}")
r1 = np.argsort(np.argsort(res_net[idx])); r2 = np.argsort(np.argsort(lok_net[idx]))
print(f"\n   rank correlation research vs locked: {np.corrcoef(r1, r2)[0,1]:+.3f}")
print(f"   median locked over all scored: ${np.median(lok_net[idx]):,.0f}")
best = o_[0]
print(f"\n   best on research ${res_net[best]:,.0f} -> LOCKED ${lok_net[best]:,.0f}  "
      f"({int(N[best])} trades)")
print(f"      {desc(best)}")
print(f"   best on locked (hindsight): ${lok_net[idx].max():,.0f}")
print(f"   the best-on-research lands at the "
      f"{100*(lok_net[idx] < lok_net[best]).mean():.1f}th percentile of locked P&L")

hdr("2. SECTION 4c — direction")
for nm, s in [("LONG rules", ok & (SIDE == 1)), ("SHORT rules", ok & (SIDE == -1))]:
    ii = np.where(s)[0]
    j = ii[np.argmax(res_net[ii])]
    print(f"   {nm:<14}n={s.sum():>10,}   median locked ${np.median(lok_net[s]):>9,.0f}   "
          f"best research ${res_net[j]:>9,.0f} -> locked ${lok_net[j]:>9,.0f}")
print(f"   share of the top 1,000 on research that are LONG: "
      f"{100*(SIDE[o_[:1000]] == 1).mean():.0f}%")

hdr("3. DIRECTION-NEUTRAL PAIRS — the filter drift cannot pass")
pair_ok = np.zeros(len(combos) * len(EXITS), np.bool_)
lidx = np.arange(len(combos))[:, None] * NVAR + np.arange(len(EXITS))[None, :]
sidx_ = lidx + len(EXITS)
L = lidx.ravel(); S = sidx_.ravel()
# SELECTION USES THE RESEARCH BLOCK ONLY. Requiring locked > 0 here would make the locked
# block part of the selection criterion and every "out-of-sample" number downstream a lie --
# which is exactly the mistake this whole repository exists to avoid.
good = ok[L] & ok[S] & (res_net[L] > 0) & (res_net[S] > 0)
both = ok[L] & ok[S]
print(f"   selection is on the RESEARCH block only; the locked block is read once, afterwards.\n")
print(f"   {int(both.sum()):,} rule/geometry pairs scored on both sides")
print(f"   LONG side positive on research : {int(((res_net[L]>0)&both).sum()):,}")
print(f"   SHORT side positive on research: {int(((res_net[S]>0)&both).sum()):,}")
print(f"   BOTH sides positive on research: {int(good.sum()):,}  "
      f"({100*good.sum()/max(both.sum(),1):.2f}%)")
print(f"\n   and READ ONCE on the locked block, of those {int(good.sum()):,}:")
gl, gs = L[good], S[good]
print(f"      long side still positive : {int((lok_net[gl]>0).sum()):,}  "
      f"({100*(lok_net[gl]>0).mean():.1f}%)")
print(f"      short side still positive: {int((lok_net[gs]>0).sum()):,}  "
      f"({100*(lok_net[gs]>0).mean():.1f}%)")
print(f"      BOTH still positive      : {int(((lok_net[gl]>0)&(lok_net[gs]>0)).sum()):,}  "
      f"({100*((lok_net[gl]>0)&(lok_net[gs]>0)).mean():.1f}%)   "
      f"chance if independent would be ~{100*(lok_net[gl]>0).mean()*(lok_net[gs]>0).mean():.1f}%")
np.save("results/alpha/af2_neutral.npy", np.where(good)[0])


# ============================================================================================
# PASS 2 — re-simulate the survivors in full, collapse near-duplicates, build a portfolio
# ============================================================================================
@njit(cache=True)
def daily_of(trig, eb, ep, okk, sidx, nsess, out):
    free = -1
    for t in range(len(trig)):
        i = trig[t]
        if i < free or okk[i] == 0:
            continue
        free = eb[i]
        out[sidx[i]] += ep[i]


def pass2():
    t0 = time.time()
    d = prep(30)
    nm2, M = build_conditions(d)
    nbars = M.shape[1]
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    atr_, mod = d["atr"], d["mod"].astype(np.int64)
    us = np.unique(d["sess"]); sidx = np.searchsorted(us, d["sess"]).astype(np.int64)
    nsess = len(us); cut = int(0.65 * nsess)

    neutral = np.load("results/alpha/af2_neutral.npy")
    pl = neutral // len(EXITS)           # rule index
    pg = neutral % len(EXITS)            # geometry index
    Lj = pl * NVAR + pg
    Sj = Lj + len(EXITS)
    # ranked on RESEARCH only, both sides -- the locked block is not consulted until it is read
    score = np.minimum(res_net[Lj], res_net[Sj])
    top = np.argsort(-score)[:600]
    print(f"\n   re-simulating the {len(top)} strongest of {len(neutral):,} "
          f"direction-neutral candidates")

    cache = {}
    D = np.zeros((len(top), nsess), np.float32)
    for q, t in enumerate(top):
        r = combos[pl[t]]
        m = M[r[0]].copy()
        for i in r[1:]:
            if i >= 0:
                m &= M[i]
        trig = np.flatnonzero(m).astype(np.int64)
        gi = pg[t]
        for s in (1, -1):
            key = (s, gi)
            if key not in cache:
                eb = np.zeros(nbars, np.int64); ep = np.zeros(nbars); okk = np.zeros(nbars, np.int64)
                am, tp, fl = EXITS[gi]
                price_one(o, h, l, c, atr_, mod, s, am, tp, fl, eb, ep, okk)
                cache[key] = (eb, ep, okk)
            eb, ep, okk = cache[key]
            tmp = np.zeros(nsess)
            daily_of(trig, eb, ep, okk, sidx, nsess, tmp)
            D[q] += tmp.astype(np.float32)
    print(f"   done, {time.time()-t0:.0f}s")

    hdr("4. COLLAPSING NEAR-DUPLICATES")
    print("   A search this wide returns the same trade fifty times with a different label.")
    print("   Candidates are kept greedily, strongest first, only if they correlate below 0.30")
    print("   with everything already kept.\n")
    keep = []
    for q in range(len(top)):
        x = D[q]
        if x.std() == 0:
            continue
        dup = False
        for k in keep:
            r_ = np.corrcoef(x, D[k])[0, 1]
            if abs(r_) > 0.30:
                dup = True; break
        if not dup:
            keep.append(q)
        if len(keep) >= 12:
            break
    print(f"   {len(keep)} distinct strategies survive de-duplication from the top "
          f"{len(top)} candidates.\n")
    print(f"   {'#':<3}{'net $':>9}{'research':>10}{'LOCKED':>9}{'days':>7}{'maxDD':>9}  rule")
    for i, q in enumerate(keep):
        x = D[q].astype(float)
        eq = np.cumsum(x); dd = (np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max()
        print(f"   {i+1:<3}{x.sum():>9,.0f}{x[:cut].sum():>10,.0f}{x[cut:].sum():>9,.0f}"
              f"{int((x != 0).sum()):>7}{dd:>9,.0f}  "
              + " AND ".join(names[k] for k in combos[pl[top[q]]] if k >= 0))
        am, tp, fl = EXITS[pg[top[q]]]
        print(f"      both directions, stop {am}xATR, target {tp}R"
              + (f", flat {fl//60}:00" if fl else ", no time stop"))

    hdr("5. THE PORTFOLIO — equal weight across the distinct survivors")
    P = D[keep].astype(float)
    C = np.corrcoef(P)
    off = C[~np.eye(len(keep), dtype=bool)]
    ev = np.linalg.eigvalsh(C)[::-1]; ev = ev[ev > 0]; w = ev / ev.sum()
    print(f"   pairwise correlation: mean {off.mean():+.3f}, max {off.max():+.3f}")
    print(f"   effective number of bets: {np.exp(-(w*np.log(w)).sum()):.2f} of {len(keep)}\n")
    book = P.sum(0)
    print(f"   {'block':<12}{'net $':>11}{'maxDD':>10}{'net/DD':>9}{'Sharpe':>9}")
    for lab, sl, nd in [("full", slice(None), nsess), ("research", slice(0, cut), cut),
                        ("LOCKED", slice(cut, None), nsess - cut)]:
        y = book[sl]
        eq = np.cumsum(y); dd = (np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max()
        sh = y.mean() / y.std(ddof=1) * np.sqrt(252) if y.std() > 0 else 0
        print(f"   {lab:<12}{y.sum():>11,.0f}{dd:>10,.0f}"
              f"{(y.sum()/dd if dd else np.inf):>9.2f}{sh:>9.2f}")
    print("\n   walk-forward, seven forward folds, nothing refitted:")
    folds = np.array_split(np.arange(nsess), 8)
    neg = 0
    for f in range(1, 8):
        v = book[folds[f]].sum()
        neg += v < 0
        print(f"      fold {f}: ${v:>9,.0f}")
    print(f"   negative folds: {neg} of 7")
    np.save("results/alpha/af2_book.npy", P)


if __name__ == "__main__":
    pass2()
