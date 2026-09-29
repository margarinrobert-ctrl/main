"""Read the supply/demand timeframe sweep."""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
import sd_tf_sweep as W

out = np.load("results/sd/sd_tf_out.npy")
meta = np.load("results/sd/sd_tf_meta.npy")
P = np.load("results/sd/sd_tf_sel.npy")
nsel = len(P)
SEL = np.tile(P, (len(out) // nsel, 1))

RN, RNET, RW, RGW, RGL, RDD = (out[:, i] for i in range(6))
LN, LNET, LW, LGW, LGL, LDD = (out[:, 6 + i] for i in range(6))
N = RN + LN; NET = RNET + LNET; WN = RW + LW
H, L, BK, BM, DM, ZT, SLO = (meta[:, i] for i in range(7))
slot = SEL[:, 0].astype(int)
BUFV = np.array(W.BUF)[slot // len(W.TP_R)]
TPV = np.array(W.TP_R)[slot % len(W.TP_R)]
BRK, AGE, OSH, SIDE = SEL[:, 1], SEL[:, 2], SEL[:, 3], SEL[:, 4]

ok = (RN >= 25) & (LN >= 10) & (N >= 40)
BOS = 8932.0
Wd = 100


def hdr(t):
    print("=" * Wd); print(t); print("=" * Wd)


def name(j):
    return (f"zone {int(H[j]):>4}m -> confirm {int(L[j]):>3}m   k{int(BK[j])} "
            f"base<{BM[j]:.1f}A dep>{DM[j]:.1f}A "
            f"{['any','reversal','continuation'][int(ZT[j])]:<12} "
            f"{'RTH' if SLO[j] > 0 else '24h':<4} buf {BUFV[j]:.2f} tp {TPV[j]:.1f}R "
            f"{'break' if BRK[j] else 'no-brk'} age {AGE[j]/ (1440/L[j]):.0f}d "
            f"{'1shot' if OSH[j] else 'reuse'} "
            f"{'both' if SIDE[j]==0 else ('long' if SIDE[j]>0 else 'short')}")


print(f"{len(out):,} configurations swept; {ok.sum():,} with enough trades to score\n")

hdr("1. THE TEST THAT MATTERS — win rate against the driftless barrier bound")
print("   P(target before stop) on a path with no drift is exactly 1/(1+R). An entry rule that")
print("   adds nothing scores that. The excess is all the ZONE contributed.")
print("   Reference: the BOS/CHoCH signal scores +10.6 at 2:1 on the same data.\n")
print(f"   {'zone tf':>9}{'confirm':>9}{'n cfgs':>9}{'mean win %':>12}{'mean bound':>12}"
      f"{'EXCESS':>9}{'best excess':>13}")
rows = []
for hh in W.HTFS:
    for ll in W.LTFS:
        sel = ok & (H == hh) & (L == ll)
        if sel.sum() < 50:
            continue
        wr = 100 * WN[sel] / N[sel]
        bd = 100.0 / (1.0 + TPV[sel])
        ex = wr - bd
        rows.append((hh, ll, sel.sum(), wr.mean(), bd.mean(), ex.mean(), ex.max()))
        print(f"   {str(hh)+'m':>9}{str(ll)+'m':>9}{sel.sum():>9,}{wr.mean():>12.1f}"
              f"{bd.mean():>12.1f}{ex.mean():>+9.2f}{ex.max():>+13.2f}")
allex = (100 * WN[ok] / N[ok]) - 100.0 / (1.0 + TPV[ok])
print(f"\n   across all {ok.sum():,} scored configurations: mean excess {allex.mean():+.2f} points, "
      f"{100*(allex>0).mean():.1f}% positive")

hdr("2. PAIRED — the same everything, only the confirmation interval moves")
per = len(out) // len(W.LTFS) if False else None
print("   For each (zone build, session, filter set, risk set) run on more than one confirmation")
print("   interval, compare the LOCKED P&L directly. No selection anywhere.\n")
key = {}
for j in np.where(ok)[0]:
    k = (H[j], BK[j], BM[j], DM[j], ZT[j], SLO[j], slot[j], BRK[j], OSH[j], SIDE[j],
         round(AGE[j] / (1440 / L[j])))
    key.setdefault(k, {})[int(L[j])] = LNET[j]
print(f"   {'confirm tf':<14}{'mean locked $':>16}{'median':>12}{'% positive':>13}{'n':>10}")
for ll in W.LTFS:
    v = np.array([d[ll] for d in key.values() if ll in d])
    if len(v) < 50:
        continue
    print(f"   {str(ll)+'m':<14}{v.mean():>16,.0f}{np.median(v):>12,.0f}"
          f"{100*(v>0).mean():>12.1f}%{len(v):>10,}")
print()
for a, b in [(15, 5), (30, 15), (60, 30), (60, 15)]:
    v = np.array([(d[a] - d[b]) for d in key.values() if a in d and b in d])
    if len(v) < 50:
        continue
    t = v.mean() / (v.std(ddof=1) / np.sqrt(len(v))) if v.std() > 0 else np.nan
    print(f"   confirm {a}m minus {b}m: mean {v.mean():>+9,.0f}   wins {100*(v>0).mean():>5.1f}%"
          f"   paired t = {t:>+7.2f}   n = {len(v):,}")

print()
key2 = {}
for j in np.where(ok)[0]:
    k = (L[j], BK[j], BM[j], DM[j], ZT[j], SLO[j], slot[j], BRK[j], OSH[j], SIDE[j], AGE[j])
    key2.setdefault(k, {})[int(H[j])] = LNET[j]
print(f"   {'zone tf':<14}{'mean locked $':>16}{'median':>12}{'% positive':>13}{'n':>10}")
for hh in W.HTFS:
    v = np.array([d[hh] for d in key2.values() if hh in d])
    if len(v) < 50:
        continue
    print(f"   {str(hh)+'m':<14}{v.mean():>16,.0f}{np.median(v):>12,.0f}"
          f"{100*(v>0).mean():>12.1f}%{len(v):>10,}")
print()
for a in [60, 120, 480, 1440]:
    v = np.array([(d[a] - d[240]) for d in key2.values() if a in d and 240 in d])
    if len(v) < 50:
        continue
    t = v.mean() / (v.std(ddof=1) / np.sqrt(len(v))) if v.std() > 0 else np.nan
    print(f"   zone {a}m minus 4H zones: mean {v.mean():>+9,.0f}   wins {100*(v>0).mean():>5.1f}%"
          f"   paired t = {t:>+7.2f}   n = {len(v):,}")

hdr("3. SELECTED — best on RESEARCH, read ONCE on LOCKED")
print(f"   {'zone -> confirm':<22}{'research $':>13}{'-> LOCKED $':>14}{'median locked':>15}{'n':>9}")
for hh in W.HTFS:
    for ll in W.LTFS:
        sel = ok & (H == hh) & (L == ll)
        if sel.sum() < 50:
            continue
        idx = np.where(sel)[0]
        j = idx[np.argmax(RNET[idx])]
        print(f"   {f'{int(hh)}m -> {int(ll)}m':<22}{RNET[j]:>13,.0f}{LNET[j]:>14,.0f}"
              f"{np.median(LNET[sel]):>15,.0f}{sel.sum():>9,}")
j = np.where(ok)[0][np.argmax(RNET[ok])]
print(f"\n   BEST OVERALL on research ${RNET[j]:,.0f} -> LOCKED ${LNET[j]:,.0f}")
print(f"      {name(j)}")
print(f"      {int(N[j])} trades, win {100*WN[j]/N[j]:.1f}%, bound {100/(1+TPV[j]):.1f}%, "
      f"excess {100*WN[j]/N[j]-100/(1+TPV[j]):+.1f}")
print(f"   best on LOCKED (hindsight): ${LNET[ok].max():,.0f}")
print(f"   MEDIAN locked across all scored: ${np.median(LNET[ok]):,.0f}")
print(f"   BOS/CHoCH 30m book on the same locked block: ${BOS:,.0f}")

hdr("4. SECTION 4c — direction fixed before the search")
print(f"   {'universe':<20}{'best research':>15}{'-> LOCKED':>12}{'median locked':>15}{'n':>10}")
for nm, s in [("direction free", ok), ("both sides only", ok & (SIDE == 0)),
              ("long only", ok & (SIDE == 1)), ("short only", ok & (SIDE == -1))]:
    if s.sum() == 0:
        continue
    idx = np.where(s)[0]
    j2 = idx[np.argmax(RNET[idx])]
    print(f"   {nm:<20}{RNET[j2]:>15,.0f}{LNET[j2]:>12,.0f}"
          f"{np.median(LNET[s]):>15,.0f}{s.sum():>10,}")

hdr("5. MARGINALS — median locked $ by one parameter, everything else averaged over")
for nm, arr, vals in [("zone tf", H, W.HTFS), ("confirm tf", L, W.LTFS),
                      ("base bars k", BK, W.BASE_K), ("base width", BM, W.BASE_MAX),
                      ("departure", DM, W.DEP_MIN), ("zone origin", ZT, W.ZONE_TYPE),
                      ("session", SLO, [570, 0]), ("buffer xATR", BUFV, W.BUF),
                      ("target R", TPV, W.TP_R), ("break filter", BRK, W.NEED_BREAK),
                      ("one-shot", OSH, W.ONE_SHOT), ("side", SIDE, W.SIDE)]:
    parts = []
    for v in vals:
        s = ok & (arr == v)
        if s.sum() < 50:
            continue
        parts.append(f"{v:g}:{np.median(LNET[s]):>7,.0f}")
    print(f"   {nm:<14}" + "  ".join(parts))
