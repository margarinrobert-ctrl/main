"""An independent reimplementation of the Initial Balance strategy and the execution model.

This is deliberately NOT a port. It was written from the stated rules and from reading the
TypeScript engine's semantics, in a different language, with a different array layout. Its value is
that a disagreement with the TypeScript result is evidence of a bug in one of them — which is worth
more than a second copy of the same mistake.

The execution rules it has to honour, all of which change the answer:
  * Decide on a closed bar, place a RESTING LIMIT, and fill only when a later bar trades THROUGH it.
    A touch is not a fill: at the front of the queue you are behind everyone already resting there.
  * A bar that contains both the stop and the target books the STOP. The path inside a bar is
    unknown and assuming the good one is how backtests lie.
  * A bar that OPENS through a level fills at the open, not at the level.
  * The entry bar itself is not managed; protective levels are live from the next bar.
  * Costs: taking liquidity on entry, taking again on a stop, resting free on a target, plus
    commission — charged in full at exit.
"""
from __future__ import annotations

import numpy as np
from numba import njit

# --- NQ, matching instruments.ts -------------------------------------------------------------
TICK = 0.25
TICK_VALUE = 5.0
POINT_VALUE = TICK_VALUE / TICK          # $20 per point
TAKER_SIDE = 0.5 * 1 * TICK + 1 * TICK   # half the spread plus one tick of slippage = 0.375
COMMISSION_PTS = 4.0 / POINT_VALUE       # $4 round turn = 0.2 points


@njit(cache=True)
def _snap(px: float, up: bool, tick: float) -> float:
    n = px / tick
    k = np.ceil(n - 1e-9) if up else np.floor(n + 1e-9)
    return k * tick


@njit(cache=True)
def simulate(
    o, h, l, c, sess, mso, atr,
    ib_minutes, retr_pct, stop_pct, rr_mult,
    side_mode, break_buffer, stop_mode, atr_mult, stop_pts,
    exit_mso,
    tick, point_value, taker_side, commission_pts,
):
    """Returns (entry_idx, exit_idx, side, entry_px, exit_px, pnl, r, is_target) for each trade.

    `exit_mso` is the flatten time in minutes since the session open. Making it a parameter rather
    than a property of the pre-filtered bar series lets the sweep search over it, and lets the whole
    regular session be loaded once instead of re-slicing per configuration.
    """
    n = o.shape[0]
    max_trades = n // 4 + 8
    t_entry = np.zeros(max_trades, np.int64)
    t_exit = np.zeros(max_trades, np.int64)
    t_side = np.zeros(max_trades, np.int64)
    t_epx = np.zeros(max_trades, np.float64)
    t_xpx = np.zeros(max_trades, np.float64)
    t_pnl = np.zeros(max_trades, np.float64)
    t_r = np.zeros(max_trades, np.float64)
    t_tgt = np.zeros(max_trades, np.int64)
    nt = 0

    # ---- pass 1: the initial balance of each session, forward only ----
    ib_hi = np.full(n, np.nan)
    ib_lo = np.full(n, np.nan)
    ready = np.zeros(n, np.uint8)
    cur = sess[0] - 1
    hi = -np.inf
    lo = np.inf
    saw = False
    for i in range(n):
        if sess[i] != cur:
            cur = sess[i]
            hi = -np.inf
            lo = np.inf
            saw = False
        if mso[i] < ib_minutes:
            if h[i] > hi:
                hi = h[i]
            if l[i] < lo:
                lo = l[i]
            saw = True
        elif saw and hi > -np.inf:
            ib_hi[i] = hi
            ib_lo[i] = lo
            ready[i] = 1

    # ---- pass 2: the event loop ----
    buf = break_buffer * tick
    used_side = 0
    state_sess = sess[0] - 1

    pos_side = 0
    pos_entry_i = -1
    pos_epx = 0.0
    pos_stop = 0.0
    pos_tgt = 0.0
    pos_stop_dist = 0.0

    pend_side = 0
    pend_limit = 0.0
    pend_stop_raw = 0.0
    pend_tgt_raw = 0.0
    pend_sess = -1

    for i in range(n):
        # ---- manage an open position ----
        if pos_side != 0:
            long = pos_side == 1
            gapped_stop = (o[i] <= pos_stop) if long else (o[i] >= pos_stop)
            gapped_tgt = (o[i] >= pos_tgt) if long else (o[i] <= pos_tgt)
            hit_stop = (l[i] <= pos_stop) if long else (h[i] >= pos_stop)
            hit_tgt = (h[i] >= pos_tgt) if long else (l[i] <= pos_tgt)
            past_exit = mso[i] >= exit_mso
            last_of_session = past_exit or (i + 1 >= n) or (sess[i + 1] != sess[i])

            exit_px = np.nan
            is_tgt = 0
            if gapped_stop:
                exit_px = o[i]
            elif hit_stop:
                exit_px = pos_stop          # the stop wins any ambiguous bar
            elif gapped_tgt:
                exit_px = o[i]
                is_tgt = 1
            elif hit_tgt:
                exit_px = pos_tgt
                is_tgt = 1
            elif last_of_session:
                exit_px = c[i]

            if not np.isnan(exit_px):
                gross = pos_side * (exit_px - pos_epx)
                cost = taker_side + (0.0 if is_tgt == 1 else taker_side) + commission_pts
                net = gross - cost
                pnl = net * point_value
                risk_usd = pos_stop_dist * point_value
                t_entry[nt] = pos_entry_i
                t_exit[nt] = i
                t_side[nt] = pos_side
                t_epx[nt] = pos_epx
                t_xpx[nt] = exit_px
                t_pnl[nt] = pnl
                t_r[nt] = pnl / risk_usd if risk_usd > 0 else 0.0
                t_tgt[nt] = is_tgt
                nt += 1
                pos_side = 0

        # ---- a resting limit: does this bar come to it? ----
        if pend_side != 0 and pos_side == 0:
            if sess[i] != pend_sess or mso[i] >= exit_mso:
                pend_side = 0                       # cancelled with the session, or at the flatten time
            else:
                long = pend_side == 1
                through = (l[i] < pend_limit) if long else (h[i] > pend_limit)
                if through:
                    fill = min(pend_limit, o[i]) if long else max(pend_limit, o[i])
                    stop_dist = abs(fill - pend_stop_raw)
                    if stop_dist < tick:
                        stop_dist = tick
                    pos_side = pend_side
                    pos_entry_i = i
                    pos_epx = fill
                    pos_stop = _snap(pend_stop_raw, not long, tick)
                    pos_tgt = _snap(pend_tgt_raw, long, tick)
                    pos_stop_dist = stop_dist
                    pend_side = 0

        # ---- decide on this close, rest the order from the next bar ----
        if pos_side == 0 and pend_side == 0 and i + 1 < n:
            if sess[i + 1] != sess[i] or mso[i + 1] >= exit_mso:
                pass
            else:
                if sess[i] != state_sess:
                    state_sess = sess[i]
                    used_side = 0
                if ready[i] == 1 and used_side == 0:
                    hh = ib_hi[i]
                    ll = ib_lo[i]
                    rng = hh - ll
                    if rng > 0:
                        broke_up = h[i] > hh + buf
                        broke_dn = l[i] < ll - buf
                        if broke_up or broke_dn:
                            if broke_up and broke_dn:
                                side = 1 if c[i] >= o[i] else -1
                            elif broke_up:
                                side = 1
                            else:
                                side = -1
                            used_side = side
                            if side_mode == 0 or side_mode == side:
                                edge = hh if side == 1 else ll
                                entry = edge - side * (rng * retr_pct) / 100.0
                                if stop_mode == 1:
                                    a = atr[i]
                                    stop = entry - side * atr_mult * a if a > 0 else np.nan
                                elif stop_mode == 2:
                                    stop = entry - side * stop_pts
                                elif stop_mode == 3:
                                    stop = ll if side == 1 else hh
                                else:
                                    stop = edge - side * (rng * stop_pct) / 100.0
                                if not np.isnan(stop) and side * (entry - stop) > 0:
                                    pend_side = side
                                    pend_limit = _snap(entry, side != 1, tick)
                                    pend_stop_raw = stop
                                    pend_tgt_raw = entry + side * rr_mult * abs(entry - stop)
                                    pend_sess = sess[i]

    return (t_entry[:nt], t_exit[:nt], t_side[:nt], t_epx[:nt], t_xpx[:nt], t_pnl[:nt], t_r[:nt], t_tgt[:nt])
