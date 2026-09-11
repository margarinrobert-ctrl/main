"""The limit walker with ONE LIVE ORDER, which is what a script can place.

THE DEFECT. `limit_entry._walk_limit` assigns its position lock `free` only on EXIT:

    if done == 1:
        ...
        free = e

An order that is RESTING and has not filled therefore blocks nothing, so trigger i+1 places its own
order while trigger i's is still live, and i+2 while both are. `order_audit.py` counts what that
implies: on every-bar 5m signals at `expiry=2`, a MEAN OF 2.45 orders are live at once with a
maximum of 3, and more than one is live 97.7% of the time; at `expiry=18` the mean is 15.9 and the
maximum 19. That is a book, not a script.

It is also measurable in the result. Holding depth fixed and lengthening the resting window, the
FILL RATE stops rising at expiry 6 (0.139) and stands still through 18, while $/signal climbs
monotonically -0.505 -> +0.228 -> +0.895 -> +1.400 -> +1.759 -> +2.115. Extra profit with no extra
fills is not the mechanic; it is the engine choosing among orders it should not have had.

Same class as `eem.run`'s eight simultaneous orders (`STUDY_V15_BOOK`), which kept 24-47% of its R
once corrected, and invisible there too in P&L per trade -- it shows only in the TRADE COUNT.

THE FIX, and the only change: an unfilled order holds the lock until it expires.

    if f < 0:
        free = i + expiry      # <- this line is the whole correction
        continue

`limit_entry.py` is left untouched so every earlier result stays reproducible; this module is the
corrected engine and V34 is scored on it.
"""
from __future__ import annotations

import sys

import numpy as np
from numba import njit

sys.path.insert(0, "research")
import indicators as I        # noqa: E402
import limit_entry as LE      # noqa: E402


@njit(cache=True)
def _walk_one(o1, h1, l1, c1, mod1, lo, hi, atr_sig, atr_lim, trig, side, lim_mult,
              stop_mult, tp_r, flat_min, expiry, cancel_mod, pv, comm, ec, se, entry_ec_mult,
              adverse_ticks, tick, through_ticks):
    n = len(trig)
    pnl = np.zeros(n); sb = np.zeros(n, np.int64); xb = np.zeros(n, np.int64)
    why = np.zeros(n, np.int64)
    k = 0; nfill = 0; ntry = 0
    free = -1
    N1 = len(c1)
    for t in range(n):
        i = trig[t]
        if i < free:
            continue
        a = atr_sig[i]; al = atr_lim[i]
        if np.isnan(a) or a <= 0.0 or np.isnan(al) or al <= 0.0:
            continue
        if hi[i] <= lo[i]:
            continue
        ntry += 1
        limit = c1[hi[i] - 1] - side * lim_mult * al
        start = hi[i]
        stop_at = hi[i + expiry] if i + expiry < len(hi) else N1
        if stop_at > N1:
            stop_at = N1
        f = -1; px = 0.0
        j = start
        while j < stop_at and j < N1:
            if cancel_mod > 0 and mod1[j] >= cancel_mod:
                break
            if side == 1:
                if l1[j] <= limit - through_ticks * tick:
                    f = j
                    px = limit if o1[j] >= limit else o1[j]
                    px += adverse_ticks * tick
                    break
            else:
                if h1[j] >= limit + through_ticks * tick:
                    f = j
                    px = limit if o1[j] <= limit else o1[j]
                    px -= adverse_ticks * tick
                    break
            j += 1
        if f < 0:
            # THE CORRECTION: the order rested and expired. No second order could have been live
            # while it was, so nothing may be attempted until it is gone.
            free = i + expiry
            continue
        nfill += 1
        entry = px
        st = entry - side * stop_mult * a
        tg = entry + side * tp_r * stop_mult * a
        jj = f; done = 0
        while jj < N1:
            hit = (l1[jj] <= st) if side == 1 else (h1[jj] >= st)
            won = (h1[jj] >= tg) if side == 1 else (l1[jj] <= tg)
            if hit:
                q = o1[jj] if ((side == 1 and o1[jj] < st) or (side == -1 and o1[jj] > st)) else st
                q += -se if side == 1 else se
                pnl[k] = side * (q - entry) * pv - comm - (1.0 + entry_ec_mult) * ec * pv
                xb[k] = jj; why[k] = 1; done = 1; break
            if won:
                q = o1[jj] if ((side == 1 and o1[jj] > tg) or (side == -1 and o1[jj] < tg)) else tg
                pnl[k] = side * (q - entry) * pv - comm - (1.0 + entry_ec_mult) * ec * pv
                xb[k] = jj; why[k] = 2; done = 1; break
            if flat_min > 0 and mod1[jj] >= flat_min:
                pnl[k] = side * (c1[jj] - entry) * pv - comm - (1.0 + entry_ec_mult) * ec * pv
                xb[k] = jj; why[k] = 3; done = 1; break
            jj += 1
        if done == 1:
            sb[k] = i
            e = i
            while e + 1 < len(hi) and hi[e] <= xb[k]:
                e += 1
            free = e
            k += 1
        else:
            free = i + expiry
    return pnl[:k], sb[:k], xb[:k], why[:k], nfill, ntry


def run_1m_one(tf, trig, side=1, lim_mult=0.75, lim_atr_n=5, stop_mult=2.0, tp_r=1.0,
               flat_min=0, expiry=2, cancel_mod=0, cost_mult=1.0, entry_ec_mult=1.0,
               adverse_ticks=0.0, through_ticks=0.0):
    from intrabar import minute_map
    m = minute_map(tf)
    d = m["d"]
    atr_lim = I.ema(I.true_range(d["h"], d["l"], d["c"]), lim_atr_n)
    return _walk_one(m["o"], m["h"], m["l"], m["c"], m["mod"], m["lo"], m["hi"],
                     d["atr"], atr_lim, np.asarray(trig, np.int64), np.int64(side),
                     float(lim_mult), float(stop_mult), float(tp_r), np.int64(flat_min),
                     np.int64(expiry), np.int64(cancel_mod), LE.PV, LE.COMM * cost_mult,
                     LE.EC * cost_mult, LE.SE * cost_mult, float(entry_ec_mult),
                     float(adverse_ticks), LE.TICK, float(through_ticks))
