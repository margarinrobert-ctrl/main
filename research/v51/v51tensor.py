"""V51's engine. A trade's outcome depends only on its SIGNAL BAR and its GEOMETRY, never on which
filter let it through -- so the price is walked ONCE per (signal bar, geometry) and every one of the
1.16 million configurations becomes an array lookup plus a position-lock pass. Same construction as
`research/v14/v14tensor.py`, which did 5.16M cells in 16 seconds and was verified trade-for-trade
against `eem.run` before it was trusted.

TWO EXIT CONVENTIONS THAT ARE NOT OPTIONAL HERE:
  * The working stop is capped at the PRIOR BAR'S CLOSE. `STUDY_V10_LIMIT` found a Donchian channel
    exit sitting ABOVE the fill, so `max(ATR stop, channel)` fired instantly AT A PROFIT -- 3,170
    trades averaging +1.14 on a median hold of ONE bar. A sell stop resting above the market is not
    a stop.
  * The flatten fills at the NEXT BAR'S OPEN, not the triggering bar's close, because
    `strategy.close_all()` cannot sell the close of the bar that triggers it.
"""
from __future__ import annotations

import numpy as np
from numba import njit, prange


@njit(cache=True)
def walk(o, h, l, c, atr, sig, ent_lo, stop_mult, flat_mod, mod, cost, slip, max_hold):
    """Exit bar and R for every signal bar, one geometry. flat_mod < 0 disables the flatten."""
    n = len(sig)
    m = len(c)
    xb = np.full(n, -1, np.int64)
    R = np.full(n, np.nan)
    for k in range(n):
        i = sig[k]
        a = i + 1
        if a >= m - 1 or not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        px = o[a] + slip
        risk = stop_mult * atr[i]
        fixed = px - risk
        end = a + max_hold
        if end > m - 2:
            end = m - 2
        out = np.nan
        j = a
        while j <= end:
            lvl = fixed
            ch = ent_lo[j]
            if np.isfinite(ch) and ch > lvl:
                lvl = ch
            cap = c[j - 1]
            if lvl > cap:
                lvl = cap
            if l[j] <= lvl:
                fill = lvl if o[j] > lvl else o[j]     # a gap through fills at the open
                out = fill - slip
                break
            if flat_mod >= 0 and mod[j] >= flat_mod:
                out = o[j + 1] - slip
                j = j + 1
                break
            j += 1
        if not np.isfinite(out):
            j = end
            out = c[j] - slip
        xb[k] = j
        R[k] = (out - px - cost) / risk
    return xb, R


@njit(cache=True, parallel=True)
def score_all(sub, bars, xb, R, MA, CX, AB, SS, ss_ids, cut,
              out_n, out_sum, out_win, out_gp, out_gl, out_nl, out_suml):
    """One pass per configuration over the entry's own signal bars, with the four filter readings
    evaluated inline so no mask is ever materialised. `sub` indexes into the geometry's arrays."""
    nma, ncx, nab, nss = MA.shape[0], CX.shape[0], AB.shape[0], len(ss_ids)
    total = nma * ncx * nab * nss
    ns = len(sub)
    for t in prange(total):
        ia = t // (ncx * nab * nss)
        r = t - ia * (ncx * nab * nss)
        ic = r // (nab * nss)
        r -= ic * (nab * nss)
        ib = r // nss
        isx = ss_ids[r - ib * nss]
        n = 0
        s = 0.0
        w = 0
        gp = 0.0
        gl = 0.0
        nl = 0
        sl = 0.0
        free = -1
        for k in range(ns):
            p = sub[k]
            b = xb[p]
            if b < 0:
                continue
            i = bars[k]
            if i < free:
                continue
            if not (MA[ia, k] and CX[ic, k] and AB[ib, k] and SS[isx, k]):
                continue
            v = R[p]
            if not np.isfinite(v):
                continue
            free = b
            if i < cut:
                n += 1
                s += v
                if v > 0:
                    w += 1
                    gp += v
                else:
                    gl -= v
            else:
                nl += 1
                sl += v
        out_n[t] = n
        out_sum[t] = s
        out_win[t] = w
        out_gp[t] = gp
        out_gl[t] = gl
        out_nl[t] = nl
        out_suml[t] = sl
