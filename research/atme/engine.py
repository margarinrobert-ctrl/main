"""Adaptive Trade Management & Execution: optimise HOW a trade is entered and managed, not WHEN.

WHY THIS IS THE RIGHT SEARCH SPACE HERE. Nineteen studies on this branch have established that the
entry signals available in this data carry little or no edge: a coin-flip entry matches the Turtle
breakout, 27,786 conditions produced one PROMISING candidate, and every surviving cell sits where
costs are smallest rather than where a signal is strongest. If WHEN carries nothing, the remaining
lever is HOW.

There is also a specific prior. `STUDY_LIMIT_ENTRY.md` found a resting limit 0.75xATR in your
favour beats a market order at the next open on EVERY bar with no rule at all -- and destroys a
good signal, because waiting for an adverse excursion discards exactly the trades whose edge is
immediacy. Those two facts together predict something testable: on a signal with NO edge, the
limit mechanic should be ADDITIVE rather than substitutive. That is the central hypothesis here.

THE ENGINE walks the true bar path once per configuration and models:

  entry     market at next open | resting LIMIT k*ATR below | buy STOP k*ATR above (confirmation)
  stop      fixed k*ATR | chandelier trail from the running high | breakeven after b*R
  target    fixed R | partial p at the first target then trail the rest
  time      hard max hold, plus a give-up rule that exits if not +g*R by bar t

CONSERVATIVE THROUGHOUT. A limit that never fills is NOT a trade (no free option). When one bar
touches both the stop and the target, the STOP wins. A trailing stop is checked before the target
on the same bar. Gaps through a level fill at the open, never at the level.
"""
from __future__ import annotations

import numpy as np
from numba import njit

MARKET, LIMIT, STOPENTRY = 0, 1, 2


@njit(cache=True)
def walk(o, h, l, c, atr, mod, trig,
         entry_mode, entry_k, entry_wait,
         stop_k, trail_k, be_trigger, be_offset,
         tp_r, partial_frac, partial_r,
         max_hold, flat_mod, give_up_r, give_up_bar,
         half_spread, slip_entry, slip_stop, commission):
    """One configuration over all triggers. Returns per-trade R, plus fill/exit diagnostics."""
    n = len(c); m = len(trig)
    R = np.zeros(m); filled = np.zeros(m, np.uint8); why = np.zeros(m, np.int64)
    held = np.zeros(m, np.int64); mfe = np.zeros(m); mae = np.zeros(m)
    k = 0
    for t in range(m):
        i = trig[t]
        if i + 1 >= n or atr[i] <= 0.0:
            continue
        a = atr[i]
        # ---- entry ------------------------------------------------------
        e = i + 1
        entry = 0.0
        got = False
        if entry_mode == MARKET:
            entry = o[e] + half_spread[e] + slip_entry
            got = True
        else:
            ref = c[i]
            want = ref - entry_k * a if entry_mode == LIMIT else ref + entry_k * a
            j = e
            while j < n and (j - e) < entry_wait:
                if entry_mode == LIMIT:
                    if l[j] <= want:
                        entry = (o[j] if o[j] < want else want) + half_spread[j]
                        e = j; got = True
                        break
                else:
                    if h[j] >= want:
                        entry = (o[j] if o[j] > want else want) + half_spread[j] + slip_entry
                        e = j; got = True
                        break
                j += 1
        if not got:
            filled[k] = 0; R[k] = 0.0; why[k] = 0; k += 1
            continue
        filled[k] = 1
        risk = stop_k * a
        if risk <= 0.0:
            k += 1
            continue
        stop = entry - risk
        target = entry + tp_r * risk
        hi = entry; lo = entry
        realised = 0.0
        remaining = 1.0
        moved_be = False
        j = e
        done = 0
        while j < n and (j - e) < max_hold:
            if h[j] > hi:
                hi = h[j]
            if l[j] < lo:
                lo = l[j]
            # trailing stop from the running high
            if trail_k > 0.0:
                cand = hi - trail_k * a
                if cand > stop:
                    stop = cand
            # breakeven move
            if (not moved_be) and be_trigger > 0.0 and hi >= entry + be_trigger * risk:
                cand = entry + be_offset * risk
                if cand > stop:
                    stop = cand
                moved_be = True
            # stop first, always
            if l[j] <= stop:
                px = (o[j] if o[j] < stop else stop) - slip_stop - half_spread[j]
                realised += remaining * (px - entry)
                why[k] = 1; done = 1
                break
            # partial then trail the rest
            if partial_frac > 0.0 and remaining > partial_frac and h[j] >= entry + partial_r * risk:
                px = entry + partial_r * risk - half_spread[j]
                realised += partial_frac * (px - entry)
                remaining -= partial_frac
            if h[j] >= target:
                px = (o[j] if o[j] > target else target) - half_spread[j]
                realised += remaining * (px - entry)
                why[k] = 2; done = 1
                break
            # give up if the trade has not worked by a set bar
            if give_up_bar > 0 and (j - e) >= give_up_bar and (c[j] - entry) < give_up_r * risk:
                realised += remaining * (c[j] - entry - half_spread[j])
                why[k] = 4; done = 1
                break
            if flat_mod > 0 and mod[j] >= flat_mod:
                realised += remaining * (c[j] - entry - half_spread[j])
                why[k] = 3; done = 1
                break
            j += 1
        if done == 0:
            jj = j if j < n else n - 1
            realised += remaining * (c[jj] - entry - half_spread[jj])
            why[k] = 5
        R[k] = (realised - commission) / risk
        held[k] = j - e
        mfe[k] = (hi - entry) / risk
        mae[k] = (entry - lo) / risk
        k += 1
    return R[:k], filled[:k], why[:k], held[:k], mfe[:k], mae[:k]
