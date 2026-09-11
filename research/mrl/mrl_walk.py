"""The 1-minute limit walk of `limit_entry._walk_limit`, with one more pessimism knob.

`tgt_next_minute`: the target may fire only from the minute AFTER the fill. On the fill minute
the high was most likely made BEFORE the dip that filled the order (a limit below the close is
reached on the way down), so letting that minute's high pay the target is STUDY_V10's artifact
number one at 1-minute scale -- filling at the bar's low and paying the target at the same
bar's high. The stop stays live on the fill minute, because a low beyond the stop means price
kept going after the fill, whichever way the minute was ordered.

ONE LIVE ORDER. `limit_entry._walk_limit` scans forward from each signal in turn, so with an
order life of three bars and a signal on every bar, up to three orders rest at once and the
OLDEST fills first -- the `eem.run` defect STUDY_V15_BOOK recorded, and it showed up here as
an every-bar entry earning 68% against 65% for random subsets of the same bars. A resting
order now blocks new signals until it expires or fills (the "hold the order untouched" policy
that beat re-pricing 2x in that study).
"""

from __future__ import annotations

import numpy as np
from numba import njit


@njit(cache=True)
def walk(
    o1,
    h1,
    l1,
    c1,
    mod1,
    lo,
    hi,
    atr_sig,
    atr_lim,
    trig,
    side,
    lim_mult,
    stop_mult,
    tp_r,
    flat_min,
    expiry,
    cancel_mod,
    pv,
    comm,
    ec,
    se,
    entry_ec_mult,
    tick,
    through_ticks,
    tgt_next_minute,
):
    n = len(trig)
    pnl = np.zeros(n)
    sb = np.zeros(n, np.int64)
    fb = np.zeros(n, np.int64)
    xb = np.zeros(n, np.int64)
    why = np.zeros(n, np.int64)
    risk = np.zeros(n)
    k = 0
    nfill = 0
    ntry = 0
    free = -1
    busy_until = -1  # ONE live order: a resting order blocks new ones until it expires
    N1 = len(c1)
    for t in range(n):
        i = trig[t]
        if i < free:
            continue
        if hi[i] < busy_until:
            continue
        a = atr_sig[i]
        al = atr_lim[i]
        if np.isnan(a) or a <= 0.0 or np.isnan(al) or al <= 0.0:
            continue
        ntry += 1
        if hi[i] <= lo[i]:
            continue
        limit = c1[hi[i] - 1] - side * lim_mult * al
        start = hi[i]
        stop_at = hi[i + expiry] if i + expiry < len(hi) else N1
        if stop_at > N1:
            stop_at = N1
        busy_until = stop_at
        f = -1
        px = 0.0
        j = start
        while j < stop_at and j < N1:
            if cancel_mod > 0 and mod1[j] >= cancel_mod:
                break
            if side == 1:
                if l1[j] <= limit - through_ticks * tick:
                    f = j
                    px = o1[j] if o1[j] < limit else limit
                    break
            else:
                if h1[j] >= limit + through_ticks * tick:
                    f = j
                    px = o1[j] if o1[j] > limit else limit
                    break
            j += 1
        if f < 0:
            continue
        nfill += 1
        entry = px
        st = entry - side * stop_mult * a
        tg = entry + side * tp_r * stop_mult * a
        jj = f
        done = 0
        while jj < N1:
            hit = (l1[jj] <= st) if side == 1 else (h1[jj] >= st)
            won = (h1[jj] >= tg) if side == 1 else (l1[jj] <= tg)
            if tgt_next_minute and jj == f:
                won = False
            if hit:
                q = o1[jj] if ((side == 1 and o1[jj] < st) or (side == -1 and o1[jj] > st)) else st
                q += -se if side == 1 else se
                pnl[k] = side * (q - entry) * pv - comm - (1.0 + entry_ec_mult) * ec * pv
                xb[k] = jj
                why[k] = 1
                done = 1
                break
            if won:
                q = o1[jj] if ((side == 1 and o1[jj] > tg) or (side == -1 and o1[jj] < tg)) else tg
                pnl[k] = side * (q - entry) * pv - comm - (1.0 + entry_ec_mult) * ec * pv
                xb[k] = jj
                why[k] = 2
                done = 1
                break
            if flat_min > 0 and mod1[jj] >= flat_min:
                pnl[k] = side * (c1[jj] - entry) * pv - comm - (1.0 + entry_ec_mult) * ec * pv
                xb[k] = jj
                why[k] = 3
                done = 1
                break
            jj += 1
        if done == 1:
            sb[k] = i
            fb[k] = f
            risk[k] = stop_mult * a * pv
            e = i
            while e + 1 < len(hi) and hi[e] <= xb[k]:
                e += 1
            free = e
            k += 1
    return pnl[:k], sb[:k], fb[:k], xb[:k], why[:k], risk[:k], nfill, ntry
