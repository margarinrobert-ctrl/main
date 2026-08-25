"""The YouTube Turtle variant, implemented separately from the original and NOT combined with it.

THE SPEC, as given by the user from the video, with every resolved ambiguity marked:

  chart        5m, 15m or 1H
  entry        20-bar Donchian breakout, intraday stop order
  stop         the 10-bar opposite Donchian extreme, FIXED AT ENTRY.
               [RESOLVED] The video says "10-bar stop". A TRAILING 10-bar channel would make R
               change during the trade, and then "1:1 / 2:1 / 3:1" has no fixed meaning. Fixing
               R at entry is the only reading under which the take-profit rule is well defined.
  filter 1     price above the 50 EMA on the HIGHER timeframe; HTF = 4H for 5m/15m/1H charts.
  filter 2     AVOID major resistance -- the DAILY, WEEKLY and MONTHLY high (low for shorts).
               Narrower than the ten levels in `levels.py`: 1H and 4H extremes are not "major".
  take profit  OPTION 1: fixed R:R, "minimum 1 to 1: 2 to 1 or 3 to 1", chosen by where the
               resistance is -- so take the LARGEST of 3R, 2R, 1R whose target still sits below
               the nearest major level. If not even 1R fits, the trade is not taken, which is the
               same constraint as filter 2 and is why the avoid-tolerance is 1.0R rather than a
               number of my choosing.
               OPTION 2: scale out in thirds at 1R, 2R and 3R, stop to break-even after the first.
               [RESOLVED] The slide reads "Exit 1/3 ... Exit 2/3 ... Exit final 1/3", which sums to
               4/3 of the position. Three equal thirds is the only reading that closes, and "2/3"
               is taken to mean the second third.
  sides        long and short, mirrored.

WHAT IS DELIBERATELY NOT HERE. No N-based unit sizing, no 0.5N pyramiding, no 4-unit cap, no skip
rule, no System 2 failsafe. Those belong to the ORIGINAL system and mixing them in would answer a
question nobody asked. Sizing is a flat 1% of equity risked per trade so that this variant and the
original can be compared on one account model.

EXECUTION. Entry and stop are stop orders; targets are limit orders. All are resolved on the finest
underlying series available for each market, and where a bar touches both the stop and a target the
STOP wins and the case is COUNTED.
"""
from __future__ import annotations

import numpy as np
from numba import njit

STOP_EXIT, TARGET_EXIT, END_EXIT = 1, 2, 3
RR_LADDER = (3.0, 2.0, 1.0)          # tried largest first; the first that fits is used


@njit(cache=True)
def run(o, h, l, c, start, end, io, ih, il, ic,
        hi20, lo20, hi10, lo10, ema, res_hi, res_lo,
        allow_long, allow_short, mode, cost_bp, slip_bp, tol_r):
    """One market, one chart timeframe. `mode` 1 = fixed R:R, 2 = scale out in thirds.

    Returns per-trade R (net of costs), direction, exit reason, chosen target multiple and the
    same-bar stop/target ambiguity flag.
    """
    n = len(c)
    cap = n // 4 + 16
    t_R = np.zeros(cap); t_dir = np.zeros(cap, np.int64); t_why = np.zeros(cap, np.int64)
    t_rr = np.zeros(cap); t_amb = np.zeros(cap, np.int64); t_in = np.zeros(cap, np.int64)
    k = 0
    cf = cost_bp / 1e4
    sf = slip_bp / 1e4

    state = 0
    entry = 0.0; stop = 0.0; risk = 0.0; rr = 0.0
    filled = 0.0; realised = 0.0; be_done = 0; tier = 0

    for i in range(n):
        if np.isnan(hi20[i]) or np.isnan(lo20[i]) or np.isnan(hi10[i]) or np.isnan(lo10[i]):
            continue
        if np.isnan(ema[i]):
            continue
        s, e = start[i], end[i]
        if e <= s:
            continue
        for j in range(s, e):
            if state == 0:
                side = 0
                lvl = 0.0
                if allow_long and ih[j] >= hi20[i] and c[i - 1] > ema[i]:
                    side = 1; lvl = hi20[i]
                elif allow_short and il[j] <= lo20[i] and c[i - 1] < ema[i]:
                    side = -1; lvl = lo20[i]
                if side == 0:
                    continue
                if side == 1:
                    px = (io[j] if io[j] > lvl else lvl) * (1.0 + cf + sf)
                    st = lo10[i]
                    if st >= px:
                        continue
                    rk = px - st
                    room = res_hi[i] - px
                else:
                    px = (io[j] if io[j] < lvl else lvl) * (1.0 - cf - sf)
                    st = hi10[i]
                    if st <= px:
                        continue
                    rk = st - px
                    room = px - res_lo[i]
                # the take-profit ladder: largest R:R that still fits below the major level
                chosen = 0.0
                if not np.isfinite(room):
                    chosen = 3.0
                else:
                    for m in range(3):
                        want = 3.0 - m
                        if room >= want * rk:
                            chosen = want
                            break
                    if chosen == 0.0:
                        continue                      # not even 1:1 fits -> avoid
                    if room < tol_r * rk:
                        continue
                state = side; entry = px; stop = st; risk = rk; rr = chosen
                filled = 1.0; realised = 0.0; be_done = 0; tier = 0
                t_dir[k] = side; t_rr[k] = chosen; t_in[k] = i
                continue

            hit_stop = (il[j] <= stop) if state == 1 else (ih[j] >= stop)
            if mode == 1:
                tgt = entry + state * rr * risk
                hit_tgt = (ih[j] >= tgt) if state == 1 else (il[j] <= tgt)
            else:
                nxt = 1.0 + tier
                tgt = entry + state * nxt * risk
                hit_tgt = (ih[j] >= tgt) if state == 1 else (il[j] <= tgt)
            if hit_stop and hit_tgt:
                t_amb[k] = 1
            if hit_stop:
                px = (io[j] if io[j] < stop else stop) if state == 1 else \
                     (io[j] if io[j] > stop else stop)
                px = px * (1.0 - cf - sf) if state == 1 else px * (1.0 + cf + sf)
                realised += filled * state * (px - entry) / risk
                t_R[k] = realised; t_why[k] = STOP_EXIT
                k += 1; state = 0
                continue
            if hit_tgt:
                px = tgt * (1.0 - cf) if state == 1 else tgt * (1.0 + cf)
                if mode == 1:
                    realised += filled * state * (px - entry) / risk
                    t_R[k] = realised; t_why[k] = TARGET_EXIT
                    k += 1; state = 0
                    continue
                part = 1.0 / 3.0
                if part > filled:
                    part = filled
                realised += part * state * (px - entry) / risk
                filled -= part
                tier += 1
                if be_done == 0:
                    stop = entry
                    be_done = 1
                if filled <= 1e-9 or tier >= 3:
                    t_R[k] = realised; t_why[k] = TARGET_EXIT
                    k += 1; state = 0
    if state != 0:
        px = c[n - 1]
        px = px * (1.0 - cf - sf) if state == 1 else px * (1.0 + cf + sf)
        realised += filled * state * (px - entry) / risk
        t_R[k] = realised; t_why[k] = END_EXIT
        k += 1
    return t_R[:k], t_dir[:k], t_why[:k], t_rr[:k], t_amb[:k], t_in[:k]
