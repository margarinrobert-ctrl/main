"""Read the corrected IVB sweep. Is there anything here worth trading?"""
from __future__ import annotations
import sys
import numpy as np
sys.path.insert(0, "research")
import ivb_sweep as S

out = np.load("results/ivb/ivb_out.npy"); meta = np.load("results/ivb/ivb_meta.npy"); G = np.load("results/ivb/ivb_grid.npy")
GG = np.tile(G, (len(out) // len(G), 1))
RN, RNET, RW, RGW, RGL = out[:, 0], out[:, 1], out[:, 2], out[:, 3], out[:, 4]
LN, LNET, LW, LGW, LGL = out[:, 7], out[:, 8], out[:, 9], out[:, 10], out[:, 11]
N = RN + LN; NET = RNET + LNET; WN = RW + LW
PF = (RGW + LGW) / np.maximum(RGL + LGL, 1e-9)
DD = np.maximum(out[:, 5], out[:, 12])
TF, IV = meta[:, 0], meta[:, 1]
IB, EN, ST, AM, TM, TP, BF, TR, RF, FL, SD = (GG[:, i] for i in range(11))
ok = (RN >= 25) & (LN >= 12) & (N >= 50)

W = 112
EM = ["break", "retest", "half-retest", "fade-fail"]
SM = ["ATR", "opp edge", "midpoint", "trigger bar"]
TRM = ["no trend", "trend agrees", "trend opposes"]


def desc(j):
    return (f"{int(TF[j]):>2}m/{int(IV[j]):>2}m {'HL' if IB[j] else 'VA'} {EM[int(EN[j])]:<11} "
            f"stop {SM[int(ST[j])]:<11} {'R' if TM[j]==0 else 'rng'}x{TP[j]:.1f} "
            f"{TRM[int(TR[j])]:<13} {'rngfilt' if RF[j] else '-------'} "
            f"flat{int(FL[j])} {'both' if SD[j]==0 else ('long' if SD[j]>0 else 'short')}")


H = (f"   {'configuration':<74}{'n':>5}{'net $':>9}{'PF':>6}{'research':>10}{'LOCKED':>9}{'DD':>8}")


def show(idx):
    print(H)
    for j in idx:
        print(f"   {desc(j):<74}{int(N[j]):>5}{NET[j]:>9,.0f}{PF[j]:>6.2f}"
              f"{RNET[j]:>10,.0f}{LNET[j]:>9,.0f}{DD[j]:>8,.0f}")


print("=" * W)
print(f"{len(out):,} configurations; {ok.sum():,} with enough trades to score")
print("=" * W)
idx = np.where(ok)[0]
j = idx[np.argmax(RNET[idx])]
print(f"\n   BEST ON RESEARCH  ${RNET[j]:,.0f}  ->  LOCKED ${LNET[j]:,.0f}")
show([j])
print(f"\n   best on LOCKED (hindsight, unattainable): ${LNET[idx].max():,.0f}")
print(f"   MEDIAN locked across all scored: ${np.median(LNET[idx]):,.0f}")
print(f"   positive on research {100*(RNET[idx]>0).mean():.1f}%   on locked "
      f"{100*(LNET[idx]>0).mean():.1f}%   on BOTH {100*((RNET[idx]>0)&(LNET[idx]>0)).mean():.1f}%")
r1 = np.argsort(np.argsort(RNET[idx])); r2 = np.argsort(np.argsort(LNET[idx]))
print(f"   rank correlation research vs locked: {np.corrcoef(r1, r2)[0,1]:+.3f}")
print(f"\n   For scale, on the same locked block: BOS 30m $8,932, S/D preset A $14,638.")

print()
print("=" * W)
print("THE DEFENSIBLE SHORTLIST — positive on BOTH blocks, ranked by the WEAKER of the two")
print("=" * W)
d = ok & (RNET > 0) & (LNET > 0) & (N >= 80) & (DD < 4000)
print(f"   {int(d.sum()):,} of {int(ok.sum()):,} qualify ({100*d.sum()/ok.sum():.1f}%)\n")
di = np.where(d)[0]
if len(di):
    show(di[np.argsort(-np.minimum(RNET[di], LNET[di]))[:12]])

print()
print("=" * W)
print("MARGINALS — median locked $, everything else averaged over")
print("=" * W)
for nm, arr, vals, lab in [("bar size", TF, S.TFS, None), ("initial value", IV, S.IVMIN, None),
                           ("levels", IB, [1, 0], ["high/low", "value area"]),
                           ("entry", EN, [0, 1, 2, 3], EM),
                           ("stop", ST, [0, 1, 2, 3], SM),
                           ("target type", TM, [0, 1], ["R multiple", "range multiple"]),
                           ("target size", TP, S.TP, None),
                           ("trend filter", TR, [0, 1, 2], TRM),
                           ("range filter", RF, [0, 1], ["off", "on"]),
                           ("flatten", FL, S.FLAT, None),
                           ("side", SD, [0, 1, -1], ["both", "long", "short"])]:
    parts = []
    for i, v in enumerate(vals):
        s = ok & (arr == v)
        if s.sum() < 100:
            continue
        tag = lab[i] if lab else f"{v:g}"
        parts.append(f"{tag}:{np.median(LNET[s]):>7,.0f}")
    print(f"   {nm:<14}" + "   ".join(parts))
