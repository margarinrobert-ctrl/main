"""A fast Turtle simulator with a hard session window, for optimisation.

WHAT IS BEING OPTIMISED, AND THE THREE MEASUREMENTS THAT ARGUE AGAINST IT. Stated first because a
search that finds something in a space the data has already rejected is finding an artefact.

  1. 07:00-11:00 IS THE WORST PART OF THE DAY. Measured on all three indices, 07:00-09:00 runs
     -0.18 to -0.43 R/trade and 10:00-11:00 is the only positive hour (STUDY_TREND_PULLBACK).
     Moving the open from 06:00 to 09:30 once raised out-of-sample expectancy 35% on 38% fewer
     trades (STUDY_INTRADAY_SESSION). The cost model does not widen the pre-RTH spread either, so
     the real penalty on the early block is LARGER than anything measured here.
  2. THE TURTLE'S OWN HEADER SAYS A CASH-SESSION WINDOW DESTROYS IT. all hours +0.398 out of
     sample, 08:00-20:00 +0.462, and 09:00-16:00 -0.017. A 07:00-11:00 window is more restrictive
     than the one already measured as harmful, and an 11:00 FLATTEN removes the multi-day hold
     that is the strategy's entire premise. STUDY_INTRADAY_SESSION puts the intraday constraint at
     ~88% of the result.
  3. THE BREAKOUT DOES NOT BEAT ITS OWN RANDOM-ENTRY CONTROL. +0.595 R/trade for the Turtle
     against +0.601 for a coin flip with identical exits, ladder and costs (STUDY_TURTLE).

So this is run as asked, in full, and the output is built to be readable EITHER WAY: the population
share before the top row, the research-to-locked transfer correlation, a same-selectivity control,
and one locked read. If the optimiser finds something here it has to clear all four.

THE SIMULATOR. Turtle long or short with the pyramid ladder, an ATR stop, a channel exit, the
skip-after-winner rule and a hard session. Entries only inside the window; the flatten is
unconditional at the window's end, which is what was asked for and is NOT how the strategy was
designed to work.
"""
from __future__ import annotations

import numpy as np
from numba import njit


@njit(cache=True)
def run(o, h, l, c, mod, sess, atr, ent_hi, ent_lo, ex_lo, ex_hi,
        side, atr_mult, pyr_step, max_units, win_start, win_end,
        adx, adx_max, ext, ext_max, gate2, gate2_min, cost_pts, skip_win):
    """One pass. Returns (trade R array, exit bar index array).

    Every entry is a market order at the NEXT bar's open, every add likewise. The stop is the
    NEARER of the ATR stop and the opposite channel, and the whole position is flattened at
    `win_end` regardless of where it stands -- at the NEXT bar's open, because a script cannot
    sell the close of the bar that triggers the flatten.
    """
    n = len(c)
    out = np.empty(4096 * 8)
    ebar = np.empty(4096 * 8, np.int64)
    m = 0
    pos = 0
    units = 0
    entry_px = 0.0
    stop = 0.0
    next_add = 0.0
    anchor = 0.0
    first_fill = 0.0
    last_win = False
    total = 0.0
    risk = 0.0
    i = 1
    while i < n - 2:
        if pos == 0:
            inw = (mod[i] >= win_start) and (mod[i] < win_end)
            ok = inw and np.isfinite(atr[i]) and atr[i] > 0.0
            if ok and adx_max > 0.0:
                ok = np.isfinite(adx[i]) and adx[i] < adx_max
            if ok and ext_max > 0.0:
                ok = np.isfinite(ext[i]) and ext[i] < ext_max
            if ok and gate2_min > -900.0:
                ok = np.isfinite(gate2[i]) and gate2[i] >= gate2_min
            if ok:
                if side > 0:
                    trig = np.isfinite(ent_hi[i]) and h[i] > ent_hi[i]
                else:
                    trig = np.isfinite(ent_lo[i]) and l[i] < ent_lo[i]
                if trig:
                    if skip_win and last_win:
                        last_win = False
                    else:
                        entry_px = o[i + 1]
                        anchor = atr[i]
                        stop = entry_px - side * atr_mult * anchor
                        next_add = entry_px + side * pyr_step * anchor
                        risk = atr_mult * anchor
                        first_fill = entry_px
                        total = -cost_pts
                        pos = 1
                        units = 1
                        i += 1
                        continue
            i += 1
            continue

        # ---- in a position
        j = i
        # flatten at the window end, at the NEXT open
        if mod[j] >= win_end:
            px = o[j + 1] if j + 1 < n else c[j]
            total += side * (px - entry_px) * units - cost_pts * units
            if m < len(out):
                out[m] = total / (risk * units)
                ebar[m] = j
                m += 1
            last_win = (side * (px - first_fill)) > 0.0
            pos = 0
            units = 0
            i = j + 1
            continue

        lvl = stop
        ch = ex_lo[j] if side > 0 else ex_hi[j]
        if np.isfinite(ch) and ((ch > lvl) if side > 0 else (ch < lvl)):
            lvl = ch
        cap = c[j - 1]
        if side > 0:
            if lvl > cap:
                lvl = cap
            hit = l[j] <= lvl
        else:
            if lvl < cap:
                lvl = cap
            hit = h[j] >= lvl
        if hit:
            total += side * (lvl - entry_px) * units - cost_pts * units
            if m < len(out):
                out[m] = total / (risk * units)
                ebar[m] = j
                m += 1
            last_win = (side * (lvl - first_fill)) > 0.0
            pos = 0
            units = 0
            i = j + 1
            continue
        # pyramid add
        if units < max_units and pyr_step > 0.0:
            reach = (h[j] >= next_add) if side > 0 else (l[j] <= next_add)
            if reach and j + 1 < n:
                add_px = o[j + 1]
                entry_px = (entry_px * units + add_px) / (units + 1)
                units += 1
                total -= cost_pts
                stop = add_px - side * atr_mult * anchor
                next_add = add_px + side * pyr_step * anchor
        i += 1
    return out[:m], ebar[:m]
