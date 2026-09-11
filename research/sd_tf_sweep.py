"""Supply/demand zones: which zone timeframe and which confirmation timeframe?

The 4H-zone / 15M-confirmation spec generalised. The zone interval and the confirmation interval
both become parameters -- 1H zones, 2H, 4H, 8H, daily; confirmed on 5m, 15m, 30m or 60m -- crossed
with every zone-construction and risk parameter. Over a million configurations.

Scored the only way that survives here: chosen on the RESEARCH block (first 65% of sessions), read
ONCE on the LOCKED block. MNQ costs throughout.

Two-phase, because a naive sweep is O(bars x zones x configs) and would take days:
  phase 1  find every (bar, zone) TRIGGER once per zone-construction, and price each trigger under
           each (buffer, target) pair -- the entry bar and the outcome do not depend on the
           selection filters.
  phase 2  walk the trigger list applying side / age / break / one-shot filters and the
           one-position-at-a-time rule. O(triggers) per configuration.

Usage: python3 research/sd_tf_sweep.py
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd
from numba import njit, prange

sys.path.insert(0, "research")
from bos_choch import prep
from sd_4h15m import build_zones

TICK = 0.25; PV = 2.0; COMM = 1.0
EC = 2.0 * TICK              # (spread + slip) points, each side
SE = 1.0 * TICK              # extra slip on a stop

HTFS = [60, 120, 240, 480, 1440]
LTFS = [5, 15, 30, 60]
BASE_K = [2, 3, 4]
BASE_MAX = [0.6, 0.9]
DEP_MIN = [1.0, 1.5]
ZONE_TYPE = [0, 1, 2]                 # any / reversal-origin / continuation-origin
SESS = [(570, 960), (0, 1440)]

BUF = [0.15, 0.5, 1.0]                # 0.15 is the specified value
TP_R = [1.0, 1.5, 2.0, 3.0]
NEED_BREAK = [0, 1]
AGE_DAYS = [2, 5, 12]
ONE_SHOT = [0, 1]
SIDE = [0, 1, -1]

MAXC = 200_000


@njit(cache=True)
def find_triggers(o, h, l, c, atr_, trad, zl, zh, zd, zstart,
                  ci, cz, cd, cedge, ca, cclose, cage, cbrk):
    """Every bar/zone pair that satisfies the penetrate-reject-close rule, in bar order."""
    n = len(c); nz = len(zl); k = 0
    lo = 0
    for i in range(2, n - 1):
        a = atr_[i]
        if np.isnan(a) or a <= 0.0:
            continue
        if trad[i] != 1 or trad[i + 1] != 1:
            continue
        for z in range(nz):
            if zstart[z] > i:
                break                       # zstart is ascending: no later zone is known yet
            d = zd[z]
            if d == 1:
                if l[i] > zh[z] or l[i] < zl[z]:
                    continue
                if c[i] <= o[i] or c[i] <= zl[z]:
                    continue
                edge = zl[z]
                brk = 1 if h[i] > h[i - 1] else 0
            else:
                if h[i] < zl[z] or h[i] > zh[z]:
                    continue
                if c[i] >= o[i] or c[i] >= zh[z]:
                    continue
                edge = zh[z]
                brk = 1 if l[i] < l[i - 1] else 0
            if k >= MAXC:
                return k
            ci[k] = i; cz[k] = z; cd[k] = d; cedge[k] = edge
            ca[k] = a; cclose[k] = c[i]; cage[k] = i - zstart[z]; cbrk[k] = brk
            k += 1
    return k


@njit(cache=True, parallel=True)
def price_triggers(o, h, l, c, ci, cd, cedge, ca, cclose, k,
                   bufs, tps, ex_bar, ex_pnl, ok):
    """For each trigger and each (buffer, target), the exit bar and the P&L. Independent of the
    selection filters, so it is computed once."""
    n = len(c)
    for t in prange(k):
        i = ci[t]; d = cd[t]; a = ca[t]; cl = cclose[t]
        for bi in range(len(bufs)):
            st = cedge[t] - d * bufs[bi] * a
            risk = abs(cl - st)
            for ti in range(len(tps)):
                s = bi * len(tps) + ti
                if risk <= 0.0 or risk > 8.0 * a:
                    ok[t, s] = 0          # zone rejected before it claims the zone
                    continue
                tgt = cl + d * tps[ti] * risk
                j = i + 1
                if j >= n:
                    ok[t, s] = 3            # signalled on the last bar: never opens, blocks
                    continue
                entry = o[j]
                if (d == 1 and st >= entry) or (d == -1 and st <= entry):
                    ok[t, s] = 2      # claims the zone, then cancels: opened through its own stop
                    continue
                done = 0
                while j < n:
                    hit = (l[j] <= st) if d == 1 else (h[j] >= st)
                    won = (h[j] >= tgt) if d == 1 else (l[j] <= tgt)
                    if hit:
                        px = o[j] if ((d == 1 and o[j] < st) or (d == -1 and o[j] > st)) else st
                        px += -SE if d == 1 else SE
                        ex_bar[t, s] = j
                        ex_pnl[t, s] = d * (px - entry) * PV - COMM - 2.0 * EC * PV
                        ok[t, s] = 1; done = 1; break
                    if won:
                        px = o[j] if ((d == 1 and o[j] > tgt) or (d == -1 and o[j] < tgt)) else tgt
                        ex_bar[t, s] = j
                        ex_pnl[t, s] = d * (px - entry) * PV - COMM - 2.0 * EC * PV
                        ok[t, s] = 1; done = 1; break
                    j += 1
                if done == 0:
                    ok[t, s] = 3      # still open when the data ends -- it blocks everything after


@njit(cache=True, parallel=True)
def select(ci, cz, cd, cage, cbrk, k, nz, sess, cut,
           ex_bar, ex_pnl, ok, P, out, base):
    """P[j] = (slot, need_break, max_age_bars, one_shot, side). Walk the triggers in order."""
    for j in prange(P.shape[0]):
        s = np.int64(P[j, 0]); nb = np.int64(P[j, 1]); age = P[j, 2]
        osh = np.int64(P[j, 3]); side = np.int64(P[j, 4])
        used = np.zeros(nz, np.uint8)
        free_at = np.int64(-1)
        cnt = np.zeros(2, np.int64); net = np.zeros(2, np.float64)
        wc = np.zeros(2, np.int64); gw = np.zeros(2, np.float64); gl = np.zeros(2, np.float64)
        eq = np.zeros(2, np.float64); pk = np.zeros(2, np.float64); dd = np.zeros(2, np.float64)
        lc = np.zeros(2, np.int64)
        for t in range(k):
            if ok[t, s] == 0:
                continue
            i = ci[t]
            if i < free_at:
                continue
            if side != 0 and side != cd[t]:
                continue
            if cage[t] > age:
                continue
            if nb == 1 and cbrk[t] == 0:
                continue
            z = cz[t]
            if osh == 1 and used[z] == 1:
                continue
            used[z] = 1
            if ok[t, s] == 3:
                break             # open at the end of the sample: nothing can follow it
            if ok[t, s] == 2:
                continue          # the zone was claimed, then the open gapped through its own stop
            free_at = ex_bar[t, s]
            p = ex_pnl[t, s]
            b = 0 if sess[i] < cut else 1
            cnt[b] += 1; net[b] += p
            if p > 0:
                wc[b] += 1; gw[b] += p
            else:
                gl[b] -= p
            if cd[t] == 1:
                lc[b] += 1
            eq[b] += p
            if eq[b] > pk[b]:
                pk[b] = eq[b]
            if pk[b] - eq[b] > dd[b]:
                dd[b] = pk[b] - eq[b]
        r = base + j
        for b in range(2):
            out[r, b * 6 + 0] = cnt[b]; out[r, b * 6 + 1] = net[b]
            out[r, b * 6 + 2] = wc[b]; out[r, b * 6 + 3] = gw[b]
            out[r, b * 6 + 4] = gl[b]; out[r, b * 6 + 5] = dd[b]
        out[r, 12] = lc[0] + lc[1]


def main():
    t0 = time.time()
    bufs = np.array(BUF); tps = np.array(TP_R)
    nslot = len(BUF) * len(TP_R)

    pairs = [(H, L) for H in HTFS for L in LTFS if L < H]
    zparams = [(bk, bm, dm, zt) for bk in BASE_K for bm in BASE_MAX
               for dm in DEP_MIN for zt in ZONE_TYPE]
    sel = [(s, nb, ad, osh, sd) for s in range(nslot) for nb in NEED_BREAK
           for ad in AGE_DAYS for osh in ONE_SHOT for sd in SIDE]
    P = np.array(sel, np.float64)

    total = len(pairs) * len(zparams) * len(SESS) * len(P)
    print(f"{len(pairs)} timeframe pairs x {len(zparams)} zone builds x {len(SESS)} sessions "
          f"x {len(P)//nslot} filter sets x {nslot} risk sets")
    print(f"= {total:,} configurations\n", flush=True)

    d30 = prep(30); us = np.unique(d30["sess"]); cut = us[int(0.65 * len(us))]

    out = np.zeros((total, 13), np.float64)
    meta = np.zeros((total, 7), np.float64)
    row = 0
    for (H, L) in pairs:
        dH = prep(H); dL = prep(L)
        IDX = dL["df"].index.values
        ct = (dH["df"].index + pd.Timedelta(minutes=H)).values
        z_at = np.searchsorted(IDX, ct, side="left").astype(np.int64)
        bars_per_day = int(round(1440 / L))
        oL, hL, lL, cL = dL["o"], dL["h"], dL["l"], dL["c"]
        aL = dL["atr"]; modL = dL["mod"]; sessL = dL["sess"].astype(np.int64)
        n = len(cL)
        ci = np.zeros(MAXC, np.int64); cz = np.zeros(MAXC, np.int64)
        cd = np.zeros(MAXC, np.int64); ce = np.zeros(MAXC); ca = np.zeros(MAXC)
        cc = np.zeros(MAXC); cg = np.zeros(MAXC, np.int64); cb = np.zeros(MAXC, np.int64)
        for (bk, bm, dm, zt) in zparams:
            zl, zh, zd, zb = build_zones(dH["o"], dH["h"], dH["l"], dH["c"], dH["atr"],
                                         bk, bm, dm, zt)
            if len(zl) == 0:
                row += len(SESS) * len(P); continue
            zstart = z_at[zb]
            keep = zstart < n
            zl, zh, zd, zstart = zl[keep], zh[keep], zd[keep], zstart[keep]
            order = np.argsort(zstart, kind="stable")
            zl, zh, zd, zstart = zl[order], zh[order], zd[order], zstart[order]
            for (slo, shi) in SESS:
                trad = ((modL >= slo) & (modL < shi)).astype(np.uint8)
                k = find_triggers(oL, hL, lL, cL, aL, trad, zl, zh, zd, zstart,
                                  ci, cz, cd, ce, ca, cc, cg, cb)
                if k == 0:
                    row += len(P); continue
                ex_bar = np.zeros((k, nslot), np.int64)
                ex_pnl = np.zeros((k, nslot), np.float64)
                okm = np.zeros((k, nslot), np.uint8)
                price_triggers(oL, hL, lL, cL, ci, cd, ce, ca, cc, k, bufs, tps,
                               ex_bar, ex_pnl, okm)
                Pl = P.copy(); Pl[:, 2] = Pl[:, 2] * bars_per_day
                select(ci, cz, cd, cg, cb, k, len(zl), sessL, np.int64(cut),
                       ex_bar, ex_pnl, okm, Pl, out, row)
                meta[row:row + len(P)] = (H, L, bk, bm, dm, zt, slo)
                row += len(P)
        print(f"   zones {H:>5}m -> confirm {L:>3}m   {row:>9,} rows   "
              f"{time.time()-t0:7.1f}s", flush=True)

    np.save("results/sd/sd_tf_out.npy", out[:row])
    np.save("results/sd/sd_tf_meta.npy", meta[:row])
    np.save("results/sd/sd_tf_sel.npy", P)
    print(f"\ndone in {time.time()-t0:.0f}s, {row:,} rows")


if __name__ == "__main__":
    main()
