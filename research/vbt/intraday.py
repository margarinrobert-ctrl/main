"""INTRADAY ONLY: session window 06:00 New York, HARD FLAT at 12:00. No overnight, ever.

WHY THIS FILE EXISTS. The brief has been intraday from the start -- open the session at 06:00 EST,
be flat by 12:00 -- and the work drifted to 1-hour charts holding positions for days, because that
is where results survived. That is the wrong reason to change a requirement. This engine cannot
hold overnight: every position is closed at the window's end, on the bar, whatever it is worth.

  entry window   [win_start, win_end) in New York minutes; nothing is armed outside it
  hard flatten   at win_end the position is closed at that bar's close, no exceptions
  no overnight   by construction -- there is no code path that carries a position past win_end

WHAT THIS BRANCH ALREADY KNOWS ABOUT THIS CONSTRAINT, stated so the result is not a surprise:
the intraday scalping constraint has failed six independent times here, and every surviving cell
across every study sits at wide stops with hour-plus holds. `STUDY_TREND_PULLBACK.md` also measured
that inside 07:00-11:00 New York the 09:30-11:00 sub-window was worth 4x the per-trade result on
44% fewer trades, and that 07:00-09:00 is the worst part of the day on all three indices
(-0.18 to -0.43 R/trade). A 06:00 start therefore opens in the measured-worst hours, which is a
reason to report the sub-window breakdown rather than a reason to move the goalposts again.

Barriers are resolved on the finest series each feed provides, and same-bar stop-and-target is
resolved STOP FIRST and counted.
"""
from __future__ import annotations

import numpy as np
from numba import njit

WIN_START, WIN_END = 360, 720          # 06:00 and 12:00 New York, in minutes


@njit(cache=True)
def walk(o, h, l, c, mod, start, end, imod, io, ih, il, ic,
         hi_e, lo_e, lo_s, hi_s, atr, ema, res_hi, res_lo,
         win_start, win_end, ent_on, stop_mode, stop_k, tp_r, tol_r,
         allow_long, allow_short, cost, slip):
    """One market, one configuration. Returns per-trade R, side, exit reason, ambiguity, bar."""
    n = len(c); cap = n // 3 + 16
    R = np.zeros(cap); SD = np.zeros(cap, np.int64); WHY = np.zeros(cap, np.int64)
    AMB = np.zeros(cap, np.int64); BAR = np.zeros(cap, np.int64)
    # excursions in PRICE POINTS, and the risk in points, so heat can be read in the
    # unit a trader actually sets a stop in rather than only in R
    MAE = np.zeros(cap); MFE = np.zeros(cap); RSK = np.zeros(cap); ENT = np.zeros(cap)
    k = 0
    cf = cost / 1e4; sf = slip / 1e4
    state = 0; entry = 0.0; stop = 0.0; risk = 0.0; tgt = 0.0
    for i in range(1, n):
        m = mod[i]
        s, e = start[i], end[i]
        if e <= s:
            continue
        # ---- hard flatten at the end of the window, before anything else ----------
        if state != 0 and m >= win_end:
            px = c[i] * (1.0 - state * (cf + sf))
            R[k] = state * (px - entry) / risk; WHY[k] = 3; k += 1; state = 0
            continue
        if state == 0:
            if m < win_start or m >= win_end:
                continue
            if not (ema[i] == ema[i]) or not (atr[i] == atr[i]) or atr[i] <= 0.0:
                continue
        for j in range(s, e):
            if state != 0 and imod[j] >= win_end:
                px = ic[j] * (1.0 - state * (cf + sf))
                R[k] = state * (px - entry) / risk; WHY[k] = 3; k += 1; state = 0
                break
            if state == 0:
                if imod[j] < win_start or imod[j] >= win_end:
                    continue
                sd = 0; lvl = 0.0
                if allow_long and c[i - 1] > ema[i]:
                    if ent_on == 0:
                        sd = 1; lvl = io[j]
                    elif hi_e[i] == hi_e[i] and ih[j] >= hi_e[i]:
                        sd = 1; lvl = hi_e[i]
                if sd == 0 and allow_short and c[i - 1] < ema[i]:
                    if ent_on == 0:
                        sd = -1; lvl = io[j]
                    elif lo_e[i] == lo_e[i] and il[j] <= lo_e[i]:
                        sd = -1; lvl = lo_e[i]
                if sd == 0:
                    continue
                if sd == 1:
                    px = (io[j] if io[j] > lvl else lvl) * (1.0 + cf + sf)
                    st = lo_s[i] if stop_mode == 0 else px - stop_k * atr[i]
                else:
                    px = (io[j] if io[j] < lvl else lvl) * (1.0 - cf - sf)
                    st = hi_s[i] if stop_mode == 0 else px + stop_k * atr[i]
                if not (st == st):
                    continue
                rk = (px - st) if sd == 1 else (st - px)
                if rk <= 0.0:
                    continue
                room = (res_hi[i] - px) if sd == 1 else (px - res_lo[i])
                if room == room and room < tol_r * rk:
                    continue
                state = sd; entry = px; stop = st; risk = rk
                tgt = px + sd * tp_r * rk
                SD[k] = sd; BAR[k] = i; RSK[k] = rk; ENT[k] = px
                MAE[k] = 0.0; MFE[k] = 0.0
                continue
            adv = (entry - il[j]) if state == 1 else (ih[j] - entry)
            fav = (ih[j] - entry) if state == 1 else (entry - il[j])
            if adv > MAE[k]:
                MAE[k] = adv
            if fav > MFE[k]:
                MFE[k] = fav
            hs = (il[j] <= stop) if state == 1 else (ih[j] >= stop)
            ht = (ih[j] >= tgt) if state == 1 else (il[j] <= tgt)
            if hs and ht:
                AMB[k] = 1
            if hs:
                px = ((io[j] if io[j] < stop else stop) if state == 1
                      else (io[j] if io[j] > stop else stop)) * (1.0 - state * (cf + sf))
                R[k] = state * (px - entry) / risk; WHY[k] = 1; k += 1; state = 0
                continue
            if ht:
                px = tgt * (1.0 - state * cf)
                R[k] = state * (px - entry) / risk; WHY[k] = 2; k += 1; state = 0
    if state != 0:
        px = c[n - 1] * (1.0 - state * (cf + sf))
        R[k] = state * (px - entry) / risk; WHY[k] = 3; k += 1
    return R[:k], SD[:k], WHY[:k], AMB[:k], BAR[:k], MAE[:k], MFE[:k], RSK[:k], ENT[:k]
