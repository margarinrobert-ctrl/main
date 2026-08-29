"""The most profitable supply/demand versions in the 590,976-configuration sweep -- ranked three
ways, because 'most profitable' means something different depending on which block you read.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
import sd_tf_sweep as W

out = np.load("results/sd/sd_tf_out.npy")
meta = np.load("results/sd/sd_tf_meta.npy")
P = np.load("results/sd/sd_tf_sel.npy")
SEL = np.tile(P, (len(out) // len(P), 1))

RN, RNET, RW, RGW, RGL, RDD = (out[:, i] for i in range(6))
LN, LNET, LW, LGW, LGL, LDD = (out[:, 6 + i] for i in range(6))
N = RN + LN; NET = RNET + LNET; WN = RW + LW
GW = RGW + LGW; GL = RGL + LGL
H, L, BK, BM, DM, ZT, SLO = (meta[:, i] for i in range(7))
slot = SEL[:, 0].astype(int)
BUF = np.array(W.BUF)[slot // len(W.TP_R)]
TP = np.array(W.TP_R)[slot % len(W.TP_R)]
BRK, AGE, OSH, SIDE = SEL[:, 1], SEL[:, 2], SEL[:, 3], SEL[:, 4]
AGED = AGE          # the selection grid stores zone lifetime in DAYS

EXC = 100 * WN / np.maximum(N, 1) - 100.0 / (1.0 + TP)
PF = GW / np.maximum(GL, 1e-9)
DD = np.maximum(RDD, LDD)
ok = (RN >= 25) & (LN >= 10) & (N >= 40)


def desc(j):
    return (f"{int(H[j]):>4}m/{int(L[j]):<3}m k{int(BK[j])} b{BM[j]:.1f} d{DM[j]:.1f} "
            f"{['any','rev','cont'][int(ZT[j])]:<4} {'RTH' if SLO[j]>0 else '24h':<3} "
            f"buf{BUF[j]:.2f} {TP[j]:.1f}R {'brk' if BRK[j] else '---'} "
            f"{AGED[j]:>2.0f}d {'1sh' if OSH[j] else 'reu'} "
            f"{'both' if SIDE[j]==0 else ('long' if SIDE[j]>0 else 'shrt')}")


HDR = (f"   {'#':>3} {'configuration':<52}{'n':>5}{'net $':>9}{'PF':>6}{'win%':>6}"
       f"{'exc':>6}{'research':>10}{'LOCKED':>9}{'maxDD':>8}")


def table(idx):
    print(HDR)
    for r, j in enumerate(idx, 1):
        print(f"   {r:>3} {desc(j):<52}{int(N[j]):>5}{NET[j]:>9,.0f}{PF[j]:>6.2f}"
              f"{100*WN[j]/N[j]:>6.1f}{EXC[j]:>+6.1f}{RNET[j]:>10,.0f}{LNET[j]:>9,.0f}{DD[j]:>8,.0f}")


Wd = 118
print("=" * Wd)
print("1. MOST PROFITABLE ON THE FULL SAMPLE — the naive answer, and the one to distrust")
print("=" * Wd)
print("   Ranking on all the data means the ranking has already seen the holdout. These are the")
print("   biggest numbers in the sweep; they are not a recommendation.\n")
idx = np.where(ok)[0]
table(idx[np.argsort(-NET[idx])[:15]])

print()
print("=" * Wd)
print("2. MOST PROFITABLE ON THE RESEARCH BLOCK — the only legitimate way to choose")
print("=" * Wd)
print("   Chosen on the first 65% of sessions, then read once on the locked 35%.\n")
top = idx[np.argsort(-RNET[idx])[:15]]
table(top)
print(f"\n   those 15 picked on research earn a MEDIAN of ${np.median(LNET[top]):,.0f} on the locked")
print(f"   block, {int((LNET[top] > 0).sum())} of 15 positive. Rank correlation between research and")
r1 = np.argsort(np.argsort(RNET[idx])); r2 = np.argsort(np.argsort(LNET[idx]))
print(f"   locked P&L across all {len(idx):,} scored configurations: "
      f"{np.corrcoef(r1, r2)[0,1]:+.3f}")

print()
print("=" * Wd)
print("3. THE DEFENSIBLE LIST — profitable on BOTH blocks AND above the barrier bound")
print("=" * Wd)
print("   Positive research, positive locked, win rate above 1/(1+R), at least 60 trades, and a")
print("   drawdown under $4,000. Ranked by the SMALLER of the two blocks' P&L, so a configuration")
print("   cannot buy its way in on one good block.\n")
d = ok & (RNET > 0) & (LNET > 0) & (EXC > 0) & (N >= 60) & (DD < 4000)
print(f"   {int(d.sum()):,} of {int(ok.sum()):,} scored configurations qualify "
      f"({100*d.sum()/ok.sum():.1f}%)\n")
di = np.where(d)[0]
worse = np.minimum(RNET[di], LNET[di])
table(di[np.argsort(-worse)[:20]])

print()
print("=" * Wd)
print("4. WHAT THE QUALIFIERS HAVE IN COMMON")
print("=" * Wd)
for nm, arr, vals in [("zone tf", H, W.HTFS), ("confirm tf", L, W.LTFS),
                      ("base k", BK, W.BASE_K), ("base width", BM, W.BASE_MAX),
                      ("departure", DM, W.DEP_MIN), ("zone origin", ZT, W.ZONE_TYPE),
                      ("session", SLO, [570, 0]), ("buffer", BUF, W.BUF),
                      ("target", TP, W.TP_R), ("break filter", BRK, W.NEED_BREAK),
                      ("one-shot", OSH, W.ONE_SHOT), ("side", SIDE, W.SIDE)]:
    parts = []
    for v in vals:
        a = (arr == v) & ok
        b = (arr == v) & d
        if a.sum() < 50:
            continue
        lift = (b.sum() / d.sum()) / (a.sum() / ok.sum())
        parts.append(f"{v:g}: {100*b.sum()/d.sum():>4.1f}% (x{lift:.2f})")
    print(f"   {nm:<13}" + "   ".join(parts))
print("\n   'x' is the share among qualifiers divided by the share among all scored configurations.")
print("   Above 1 means the setting is over-represented among the versions that work on both blocks.")
