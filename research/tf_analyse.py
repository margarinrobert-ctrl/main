"""Read the timeframe sweep and answer the question three ways.

1. PAIRED comparison  -- every parameter set held identical, 60m against 30m. This is the honest
   way to ask "is the 1-hour chart better", because it never lets search width choose.
2. SELECTED comparison -- best on research, read once on locked, per timeframe.
3. The driftless barrier bound -- P(target before stop) = 1/(1+R) for a path with no drift, so a
   win rate at the bound means the entry contributed nothing.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
import tf_sweep as T

out = np.load("results/tf/tf_sweep_out.npy")
meta = np.load("results/tf/tf_sweep_meta.npy")
G = np.load("results/tf/tf_sweep_grid.npy")
nk = len(G)
GG = np.tile(G, (len(meta) // nk, 1))

RN, RNET, RW, RGW, RGL, RDD = (out[:, i] for i in range(6))
LN, LNET, LW, LGW, LGL, LDD = (out[:, 6 + i] for i in range(6))
TOT_N = RN + LN
TOT_NET = RNET + LNET
TOT_W = RW + LW

tf, sk, en = meta[:, 0], meta[:, 1], meta[:, 2]
atr_m, nbos, tpr, dmin, dmax, slo, shi, side = (GG[:, i] for i in range(8))

MIN_TR = 40
ok = (RN >= 25) & (LN >= 10) & (TOT_N >= MIN_TR)
print(f"{len(out):,} configurations swept; {ok.sum():,} with enough trades to score\n")

INCUMBENT = 8932.0    # v7 spec (30m, k3, EMA200, nBos 2, 2xATR, 2R, dmin 1.0, RTH, both) on LOCKED

W = 96
def hdr(t):
    print("=" * W); print(t); print("=" * W)


def label(j):
    return (f"tf {int(tf[j]):>3}m  k{int(sk[j])}  EMA{int(en[j]):>3}  nBos {int(nbos[j])}  "
            f"stop {atr_m[j]:.1f}xATR  tp {tpr[j]:.1f}R  dist [{dmin[j]:.1f},"
            f"{'inf' if dmax[j] > 1e6 else f'{dmax[j]:.1f}'}]  "
            f"{T.SESS_NAME[(int(slo[j]), int(shi[j]))]:<15}  "
            f"side {'both' if side[j]==0 else ('long' if side[j]>0 else 'short')}")


# ---------------------------------------------------------------------------------------------
hdr("1. PAIRED — the same parameter set on each timeframe, nothing selected")
print("   Every one of the non-timeframe parameter sets is run on all four timeframes. Comparing")
print("   the pairs answers 'is the 1-hour chart better' without a search choosing anything.\n")

ntf = len(T.TFS)
per = len(out) // ntf
blocks = {int(m): slice(i * per, (i + 1) * per) for i, m in enumerate(T.TFS)}
okm = ok.reshape(ntf, per)
pair_ok = okm.all(axis=0)
print(f"   {pair_ok.sum():,} parameter sets are tradeable on all four timeframes\n")

print(f"   {'timeframe':<12}{'mean locked $':>15}{'median locked $':>17}{'% locked +':>12}"
      f"{'mean win %':>12}{'mean trades':>13}")
for m in T.TFS:
    s = blocks[m]
    ln = LNET[s][pair_ok]; wn = TOT_W[s][pair_ok] / np.maximum(TOT_N[s][pair_ok], 1)
    print(f"   {str(m)+'m':<12}{ln.mean():>15,.0f}{np.median(ln):>17,.0f}"
          f"{100*(ln>0).mean():>11.1f}%{100*wn.mean():>12.1f}{TOT_N[s][pair_ok].mean():>13.0f}")

print()
base = LNET[blocks[30]][pair_ok]
for m in T.TFS:
    if m == 30:
        continue
    x = LNET[blocks[m]][pair_ok] - base
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if x.std() > 0 else np.nan
    print(f"   {m}m minus 30m on the LOCKED block: mean {x.mean():>+9,.0f}   "
          f"wins {100*(x>0).mean():>5.1f}% of pairs   paired t = {t:>+6.2f}")

# ---------------------------------------------------------------------------------------------
hdr("2. SELECTED — best on RESEARCH, then read ONCE on LOCKED, per timeframe")
print(f"   {'timeframe':<12}{'research $':>13}{'-> LOCKED $':>14}{'median locked':>15}{'n cfgs':>9}")
for m in T.TFS:
    s = blocks[m]
    mm = ok[s]
    if mm.sum() == 0:
        continue
    idx = np.where(mm)[0]
    j = idx[np.argmax(RNET[s][idx])]
    g = s.start + j
    print(f"   {str(m)+'m':<12}{RNET[g]:>13,.0f}{LNET[g]:>14,.0f}"
          f"{np.median(LNET[s][mm]):>15,.0f}{mm.sum():>9,}")
    print(f"      {label(g)}")

j = np.where(ok)[0][np.argmax(RNET[ok])]
print(f"\n   BEST OVERALL on research: ${RNET[j]:,.0f}  ->  LOCKED ${LNET[j]:,.0f}")
print(f"      {label(j)}")
print(f"   best on LOCKED (hindsight, unattainable): ${LNET[ok].max():,.0f}")
print(f"   MEDIAN locked across all {ok.sum():,} scored configurations: ${np.median(LNET[ok]):,.0f}")
print(f"   INCUMBENT v7 spec on the same locked block: ${INCUMBENT:,.0f}")

# ---------------------------------------------------------------------------------------------
hdr("3. THE DRIFTLESS BARRIER BOUND — win rate against 1/(1+R)")
print("   A target/stop pair with no directional information wins exactly 1/(1+R) of the time.")
print("   Excess over that bound is the only part of the win rate the ENTRY earned.\n")
print(f"   {'timeframe':<12}{'target':>8}{'bound %':>10}{'mean win %':>12}{'EXCESS':>9}{'best':>9}{'n':>9}")
for m in T.TFS:
    s = blocks[m]
    for r in [1.0, 1.5, 2.0, 2.5, 3.0]:
        sel = ok[s] & (tpr[s] == r)
        if sel.sum() < 20:
            continue
        wr = 100 * TOT_W[s][sel] / TOT_N[s][sel]
        bound = 100.0 / (1.0 + r)
        print(f"   {str(m)+'m':<12}{r:>7.1f}R{bound:>10.1f}{wr.mean():>12.1f}"
              f"{wr.mean()-bound:>+9.2f}{wr.max()-bound:>+9.2f}{sel.sum():>9,}")

# ---------------------------------------------------------------------------------------------
hdr("4. SECTION 4c — is the winner a directional bet?")
print(f"   {'universe':<22}{'best research':>15}{'-> LOCKED':>12}{'median locked':>15}{'n':>9}")
for nm, sel in [("direction free", ok),
                ("both sides only", ok & (side == 0)),
                ("long only", ok & (side == 1)),
                ("short only", ok & (side == -1))]:
    if sel.sum() == 0:
        continue
    idx = np.where(sel)[0]
    g = idx[np.argmax(RNET[idx])]
    print(f"   {nm:<22}{RNET[g]:>15,.0f}{LNET[g]:>12,.0f}"
          f"{np.median(LNET[sel]):>15,.0f}{sel.sum():>9,}")

# ---------------------------------------------------------------------------------------------
hdr("5. MARGINALS — locked P&L by one parameter at a time, everything else averaged over")
for nm, arr, vals in [("timeframe", tf, T.TFS), ("swing k", sk, T.SWING_K), ("EMA", en, T.EMA_N),
                      ("nBos", nbos, T.N_BOS), ("stop xATR", atr_m, T.ATR_MULT),
                      ("target R", tpr, T.TP_R), ("EMA dist min", dmin, T.DMIN),
                      ("side", side, T.SIDES)]:
    parts = []
    for v in vals:
        sel = ok & (arr == v)
        if sel.sum() < 20:
            continue
        parts.append(f"{v:g}:{np.median(LNET[sel]):>7,.0f}")
    print(f"   {nm:<14} median locked $ by value -- " + "  ".join(parts))
