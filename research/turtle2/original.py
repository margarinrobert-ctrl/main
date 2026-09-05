"""The ORIGINAL Turtle system, reconstructed as faithfully as the data allows. NOT optimised.

Every rule below is the published Richard Dennis / Curtis Faith specification, not a variant. No
parameter here is searched; they are constants because the system defines them.

  N              Wilder's 20-day ATR, N = (19*PDN + TR)/20, seeded on a simple mean of the first
                 20 true ranges. Updated daily, but a unit's SIZE and STOP are fixed using the N
                 in force when that unit filled.
  System 1       enter on a 20-day breakout; exit on the 10-day opposite breakout.
  System 2       enter on a 55-day breakout; exit on the 20-day opposite breakout.
  the skip rule  a System 1 breakout is SKIPPED if the PREVIOUS 20-day breakout would have been a
                 winner -- whether or not it was actually taken. See `shadow_ledger`.
  the failsafe   System 2's 55-day breakout is ALWAYS taken, which is what makes the skip rule
                 survivable: a skipped move that keeps going is caught at 55 days.
  stop           2N from entry.
  pyramid        add a unit every 0.5N in your favour, measured from the ACTUAL FILL of the
                 previous unit, not from the breakout level. Maximum 4 units.
  re-anchor      when a unit is added, ALL stops move to 2N from the most recent unit's entry.
                 (The standard method; the 0.5N "whipsaw" alternative is not used.)
  exit           closes the WHOLE position at once.
  both sides     long and short, symmetric.

EXECUTION. Every Turtle order is a STOP order, so every fill is intraday and every fill slips.
This engine walks the TRUE INTRADAY PATH inside each day rather than resolving order precedence by
rule -- `STUDY_ATME_LIVE.md` measured what the alternative costs (PF 1.99 -> 0.99 on the same
trades). Within one intraday bar two levels can still both be touched; that residual is resolved
STOP-FIRST and COUNTED, so it is reported rather than hidden.

A gap through a level fills at the intraday bar's OPEN, never at the level.

WHAT IS DELIBERATELY NOT MODELLED, and would flatter the system if it were: portfolio-level unit
caps (the original limited 6 units per correlated group and 12 per direction). The brief specifies
the 4-units-per-market cap only, and leaving the portfolio caps out means the trade sequence does
not depend on account state -- which is what lets the equity model be applied separately and
exactly.
"""
from __future__ import annotations

import numpy as np
from numba import njit

STOP_EXIT, CHANNEL_EXIT, END_OF_DATA = 1, 2, 3
MAX_UNITS = 4


@njit(cache=True)
def _roll_max(x, n):
    m = len(x); out = np.full(m, np.nan)
    q = np.empty(m, np.int64); head = 0; tail = 0
    for i in range(m):
        while tail > head and x[q[tail - 1]] <= x[i]:
            tail -= 1
        q[tail] = i; tail += 1
        if q[head] <= i - n:
            head += 1
        if i >= n - 1:
            out[i] = x[q[head]]
    return out


@njit(cache=True)
def _roll_min(x, n):
    m = len(x); out = np.full(m, np.nan)
    q = np.empty(m, np.int64); head = 0; tail = 0
    for i in range(m):
        while tail > head and x[q[tail - 1]] >= x[i]:
            tail -= 1
        q[tail] = i; tail += 1
        if q[head] <= i - n:
            head += 1
        if i >= n - 1:
            out[i] = x[q[head]]
    return out


def channels(h, l, c):
    """Prior-day-exclusive channel extremes and Wilder's 20-day N."""
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    n = np.full(len(c), np.nan)
    if len(c) > 20:
        n[19] = tr[:20].mean()
        for i in range(20, len(c)):
            n[i] = (19.0 * n[i - 1] + tr[i]) / 20.0
    out = {}
    for k in (10, 20, 55):
        out[f"hi{k}"] = np.roll(_roll_max(h, k), 1)
        out[f"lo{k}"] = np.roll(_roll_min(l, k), 1)
        out[f"hi{k}"][:k + 1] = np.nan
        out[f"lo{k}"][:k + 1] = np.nan
    out["N"] = np.roll(n, 1)          # yesterday's N decides today's orders
    out["N"][:21] = np.nan
    return out


@njit(cache=True)
def shadow_ledger(h, l, hi20, lo20, hi10, lo10, N):
    """Non-overlapping hypothetical 20-day breakouts, to decide the skip rule.

    THE RULE IS ABOUT BREAKOUTS, NOT ABOUT TRADES TAKEN. A System 1 signal is skipped when the
    previous 20-day breakout would have won -- whether or not it was traded. That cannot be read
    off the realised trade list, so it is simulated here as a separate single-unit ledger: enter
    at the channel on the first day it is exceeded, stop at 2N, exit at the 10-day opposite
    channel, then wait for the next breakout. A breakout is a LOSER if the 2N stop came first.

    Returns `prev_won[i]`: at day i, did the last COMPLETED hypothetical breakout win? -1 = none
    yet, which the original treats as "take the trade".
    """
    n = len(h)
    prev_won = np.full(n, -1, np.int64)
    state = 0            # 0 flat, 1 long, -1 short
    entry = 0.0; stop = 0.0; last = -1
    for i in range(n):
        prev_won[i] = last
        if np.isnan(N[i]) or np.isnan(hi20[i]) or np.isnan(lo20[i]):
            continue
        if state == 0:
            if h[i] >= hi20[i]:
                state = 1; entry = hi20[i]; stop = entry - 2.0 * N[i]
            elif l[i] <= lo20[i]:
                state = -1; entry = lo20[i]; stop = entry + 2.0 * N[i]
            continue
        if state == 1:
            if l[i] <= stop:
                last = 0; state = 0                      # 2N hit first -> loser
            elif (not np.isnan(lo10[i])) and l[i] <= lo10[i]:
                last = 1 if lo10[i] > entry else 0
                state = 0
        else:
            if h[i] >= stop:
                last = 0; state = 0
            elif (not np.isnan(hi10[i])) and h[i] >= hi10[i]:
                last = 1 if hi10[i] < entry else 0
                state = 0
    return prev_won


@njit(cache=True)
def run(o, h, l, c, start, end, io, ih, il, ic,
        hi_in, lo_in, hi_out, lo_out, N, prev_won,
        system, use_skip, allow_long, allow_short, cost_bp, slip_bp):
    """One market, one system, walked on the true intraday path.

    Returns per-trade arrays plus per-unit entry prices, sizes-in-N and intraday indices, so the
    equity model can size each unit at the equity in force when it actually filled.
    """
    nd = len(c)
    cap = nd // 3 + 16
    t_dir = np.zeros(cap, np.int64); t_nu = np.zeros(cap, np.int64)
    t_why = np.zeros(cap, np.int64); t_in = np.zeros(cap, np.int64)
    t_out = np.zeros(cap, np.int64); t_px = np.zeros(cap)
    t_amb = np.zeros(cap, np.int64); t_N = np.zeros(cap)
    u_px = np.zeros((cap, MAX_UNITS)); u_N = np.zeros((cap, MAX_UNITS))
    u_day = np.zeros((cap, MAX_UNITS), np.int64)
    k = 0

    state = 0; units = 0
    stop = 0.0; nxt = 0.0; risk = 0.0
    cf = cost_bp / 1e4
    sf = slip_bp / 1e4

    for i in range(nd):
        if np.isnan(N[i]) or np.isnan(hi_in[i]) or np.isnan(lo_in[i]):
            continue
        a = N[i]
        s, e = start[i], end[i]
        if e <= s:
            continue
        for j in range(s, e):
            if state == 0:
                if units != 0:
                    units = 0
                took = 0
                if allow_long and ih[j] >= hi_in[i]:
                    if (system == 1) and use_skip and prev_won[i] == 1:
                        pass
                    else:
                        lvl = hi_in[i]
                        px = io[j] if io[j] > lvl else lvl
                        px = px * (1.0 + cf + sf)
                        state = 1; took = 1
                elif allow_short and il[j] <= lo_in[i]:
                    if (system == 1) and use_skip and prev_won[i] == 1:
                        pass
                    else:
                        lvl = lo_in[i]
                        px = io[j] if io[j] < lvl else lvl
                        px = px * (1.0 - cf - sf)
                        state = -1; took = 1
                if took == 1:
                    units = 1; risk = 2.0 * a
                    u_px[k, 0] = px; u_N[k, 0] = a; u_day[k, 0] = i
                    t_dir[k] = state; t_in[k] = i; t_N[k] = a
                    if state == 1:
                        stop = px - risk; nxt = px + 0.5 * a
                    else:
                        stop = px + risk; nxt = px - 0.5 * a
                continue

            # ---- in a position: stop, then adds, then the channel exit -------------
            hit_stop = (il[j] <= stop) if state == 1 else (ih[j] >= stop)
            ch = lo_out[i] if state == 1 else hi_out[i]
            hit_ch = False
            if not np.isnan(ch):
                hit_ch = (il[j] <= ch) if state == 1 else (ih[j] >= ch)
            if hit_stop and hit_ch:
                t_amb[k] = 1
            if hit_stop:
                px = (io[j] if io[j] < stop else stop) if state == 1 else \
                     (io[j] if io[j] > stop else stop)
                px = px * (1.0 - cf - sf) if state == 1 else px * (1.0 + cf + sf)
                t_nu[k] = units; t_why[k] = STOP_EXIT; t_out[k] = i; t_px[k] = px
                k += 1; state = 0; units = 0
                continue
            while units < MAX_UNITS and (
                    (state == 1 and ih[j] >= nxt) or (state == -1 and il[j] <= nxt)):
                if state == 1:
                    px = io[j] if io[j] > nxt else nxt
                    px = px * (1.0 + cf + sf)
                else:
                    px = io[j] if io[j] < nxt else nxt
                    px = px * (1.0 - cf - sf)
                u_px[k, units] = px; u_N[k, units] = a; u_day[k, units] = i
                units += 1
                risk = 2.0 * a
                if state == 1:
                    stop = px - risk; nxt = px + 0.5 * a
                else:
                    stop = px + risk; nxt = px - 0.5 * a
            if hit_ch:
                px = (io[j] if io[j] < ch else ch) if state == 1 else \
                     (io[j] if io[j] > ch else ch)
                px = px * (1.0 - cf - sf) if state == 1 else px * (1.0 + cf + sf)
                t_nu[k] = units; t_why[k] = CHANNEL_EXIT; t_out[k] = i; t_px[k] = px
                k += 1; state = 0; units = 0

    if state != 0:
        px = c[nd - 1]
        px = px * (1.0 - cf - sf) if state == 1 else px * (1.0 + cf + sf)
        t_nu[k] = units; t_why[k] = END_OF_DATA; t_out[k] = nd - 1; t_px[k] = px
        k += 1
    return (t_dir[:k], t_nu[:k], t_why[:k], t_in[:k], t_out[:k], t_px[:k],
            t_amb[:k], t_N[:k], u_px[:k], u_N[:k], u_day[:k])
