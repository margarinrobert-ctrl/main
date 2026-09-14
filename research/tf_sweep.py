"""Timeframe sweep: does the 1-hour chart beat the 30-minute one?

A quarter of a million configurations of the BOS/CHoCH rule across four timeframes, scored the
only way that has ever survived on this branch: chosen on the RESEARCH block (first 65% of
sessions), then read ONCE on the LOCKED block. The incumbent v7 spec is priced on the same
locked block so the comparison is like for like.

Costs are MNQ throughout: $2/point, $1.00 commission per round turn, 1 tick spread + 1 tick
entry slip charged both sides, 1 extra tick of slip on a stop.

Usage: python3 research/tf_sweep.py
"""
from __future__ import annotations

import sys
import time

import numpy as np
from numba import njit, prange

sys.path.insert(0, "research")
from bos_choch import prep

TICK = 0.25
PV = 2.0
COMM = 1.0
EC = (1.0 + 1.0) * TICK          # spread + slip, in points, charged on each side
SE = 1.0 * TICK                  # extra slip on a stop fill

# ---- the grid ------------------------------------------------------------------------------------
TFS      = [15, 30, 60, 120]
SWING_K  = [2, 3, 4, 5]
EMA_N    = [50, 100, 200]

N_BOS    = [1, 2, 3]
ATR_MULT = [1.5, 2.0, 2.5, 3.0]
TP_R     = [0.0, 1.0, 1.5, 2.0, 2.5, 3.0]     # 0 = no target, exit on the opposite break
DMIN     = [0.0, 0.5, 1.0]                    # |close - EMA| in ATRs, minimum
DMAX     = [1e9, 2.5]                         # ... and maximum
SESSIONS = [(570, 960), (570, 720), (570, 690), (0, 1440)]
SIDES    = [0, 1, -1]

SESS_NAME = {(570, 960): "RTH 09:30-16:00", (570, 720): "09:30-12:00",
             (570, 690): "09:30-11:30", (0, 1440): "24h"}


@njit(cache=True)
def _one(o, h, l, c, sess, mod, ph, pl, ema_, atr_, cut,
         atr_mult, n_bos, tp_r, dmin, dmax, s_lo, s_hi, side, out, row):
    n = len(c)
    pos = 0; entry = 0.0; stopL = 0.0; tp = 0.0; risk = 0.0
    bias = 0; rn = 0; bh = np.nan; bl = np.nan
    aSig = np.nan; pend = 0; ent_i = 0

    # [research, locked] x accumulators
    cnt = np.zeros(2, np.int64); net = np.zeros(2, np.float64)
    wcnt = np.zeros(2, np.int64); gwin = np.zeros(2, np.float64); glos = np.zeros(2, np.float64)
    eq = np.zeros(2, np.float64); pk = np.zeros(2, np.float64); dd = np.zeros(2, np.float64)
    lcnt = np.zeros(2, np.int64); lnet = np.zeros(2, np.float64)

    for i in range(1, n):
        ns = sess[i] != sess[i - 1]

        if pend != 0 and pos == 0:
            pos = pend; entry = o[i]; ent_i = i; pend = 0
            risk = atr_mult * aSig
            stopL = entry - pos * risk
            tp = entry + pos * tp_r * risk if tp_r > 0 else np.nan

        if pos != 0:
            hit = (l[i] <= stopL) if pos == 1 else (h[i] >= stopL)
            won = (tp_r > 0) and ((h[i] >= tp) if pos == 1 else (l[i] <= tp))
            if hit and won:
                won = False              # both in one bar: the stop is assumed to fill first
            px = np.nan
            if hit:
                px = o[i] if ((pos == 1 and o[i] < stopL) or (pos == -1 and o[i] > stopL)) else stopL
                px += -SE if pos == 1 else SE
            elif won:
                px = o[i] if ((pos == 1 and o[i] > tp) or (pos == -1 and o[i] < tp)) else tp
            if hit or won:
                p = pos * (px - entry) * PV - 2 * EC * PV - COMM
                b = 0 if sess[ent_i] < cut else 1
                cnt[b] += 1; net[b] += p
                if p > 0:
                    wcnt[b] += 1; gwin[b] += p
                else:
                    glos[b] -= p
                if pos == 1:
                    lcnt[b] += 1; lnet[b] += p
                eq[b] += p
                if eq[b] > pk[b]:
                    pk[b] = eq[b]
                if pk[b] - eq[b] > dd[b]:
                    dd[b] = pk[b] - eq[b]
                pos = 0

        bU = (not np.isnan(ph[i])) and c[i] > ph[i] and (np.isnan(bh) or ph[i] != bh)
        bD = (not np.isnan(pl[i])) and c[i] < pl[i] and (np.isnan(bl) or pl[i] != bl)
        if bU:
            bh = ph[i]
        if bD:
            bl = pl[i]
        if bU:
            rn = rn + 1 if bias == 1 else 1
            bias = 1
        if bD:
            rn = rn + 1 if bias == -1 else 1
            bias = -1

        a = atr_[i]
        ready = (a > 0) and (not np.isnan(a)) and (not np.isnan(ema_[i]))
        m0 = mod[i]; m1 = mod[i + 1] if i + 1 < n else -1
        t0 = (m0 >= s_lo) and (m0 < s_hi)
        t1 = (m1 >= s_lo) and (m1 < s_hi)
        ok = (i + 1 < n) and t0 and t1 and (not ns)

        if pos == 0 and pend == 0 and ok and ready:
            dist = abs(c[i] - ema_[i]) / a
            if dist >= dmin and dist <= dmax:
                s_ = 0
                if bU and rn >= n_bos and c[i] > ema_[i]:
                    s_ = 1
                elif bD and rn >= n_bos and c[i] < ema_[i]:
                    s_ = -1
                if s_ != 0 and (side == 0 or side == s_):
                    aSig = a; pend = s_

        if pos != 0 and tp_r <= 0 and ((pos == 1 and bD) or (pos == -1 and bU)) and i + 1 < n:
            p = pos * (o[i + 1] - entry) * PV - 2 * EC * PV - COMM
            b = 0 if sess[ent_i] < cut else 1
            cnt[b] += 1; net[b] += p
            if p > 0:
                wcnt[b] += 1; gwin[b] += p
            else:
                glos[b] -= p
            if pos == 1:
                lcnt[b] += 1; lnet[b] += p
            eq[b] += p
            if eq[b] > pk[b]:
                pk[b] = eq[b]
            if pk[b] - eq[b] > dd[b]:
                dd[b] = pk[b] - eq[b]
            pos = 0

    for b in range(2):
        out[row, b * 6 + 0] = cnt[b]
        out[row, b * 6 + 1] = net[b]
        out[row, b * 6 + 2] = wcnt[b]
        out[row, b * 6 + 3] = gwin[b]
        out[row, b * 6 + 4] = glos[b]
        out[row, b * 6 + 5] = dd[b]
    out[row, 12] = lcnt[0] + lcnt[1]
    out[row, 13] = lnet[0] + lnet[1]


@njit(parallel=True, cache=True)
def sweep(o, h, l, c, sess, mod, ph, pl, ema_, atr_, cut, G, out, base):
    for j in prange(G.shape[0]):
        _one(o, h, l, c, sess, mod, ph, pl, ema_, atr_, cut,
             G[j, 0], np.int64(G[j, 1]), G[j, 2], G[j, 3], G[j, 4],
             np.int64(G[j, 5]), np.int64(G[j, 6]), np.int64(G[j, 7]), out, base + j)


def build_kernel_grid():
    rows = []
    for nb in N_BOS:
        for am in ATR_MULT:
            for tp in TP_R:
                for dn in DMIN:
                    for dx in DMAX:
                        for (lo, hi) in SESSIONS:
                            for sd in SIDES:
                                rows.append((am, nb, tp, dn, dx, lo, hi, sd))
    return np.array(rows, np.float64)


def main():
    t0 = time.time()
    G = build_kernel_grid()
    preps = [(m, k, e) for m in TFS for k in SWING_K for e in EMA_N]
    ncfg = len(preps) * len(G)
    print(f"{len(preps)} data preparations x {len(G)} parameter sets = {ncfg:,} configurations")

    # the research/locked cut is a CALENDAR cut, identical for every timeframe
    d30 = prep(30)
    usess = np.unique(d30["sess"])
    cut = usess[int(0.65 * len(usess))]

    out = np.zeros((ncfg, 14), np.float64)
    meta = np.zeros((ncfg, 3), np.float64)
    for pi, (m, k, e) in enumerate(preps):
        d = prep(m, swing_k=k, ema_n=e)
        base = pi * len(G)
        sweep(d["o"], d["h"], d["l"], d["c"], d["sess"].astype(np.int64),
              d["mod"].astype(np.int64), d["ph"], d["pl"], d["ema"], d["atr"],
              np.int64(cut), G, out, base)
        meta[base:base + len(G)] = (m, k, e)
        print(f"   {m:>4}m  swing_k {k}  EMA {e:>3}   {time.time()-t0:6.1f}s", flush=True)

    np.save("results/tf/tf_sweep_out.npy", out)
    np.save("results/tf/tf_sweep_meta.npy", meta)
    np.save("results/tf/tf_sweep_grid.npy", G)
    print(f"\ndone in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
