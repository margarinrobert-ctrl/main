"""EMA fast/slow crossover -> pullback to the SLOW ema -> entry on reclaim of the FAST ema.

THE HYPOTHESIS, stated so it can be falsified:

  LONG   EMA(fast) crosses above EMA(slow)          -- bias is set
         within `max_wait` bars, price PULLS BACK   -- low trades at or below EMA(slow) + depth*ATR
         then price RECLAIMS the fast ema           -- close back above EMA(fast)
         enter at the NEXT bar's open. Stop `sl` x ATR below the fill, target `tp` x that risk.
  SHORT  the mirror.

Causality: every ema and the ATR are computed from closed bars only; the pullback and reclaim are
both tested on bar i's completed values; the fill is the open of bar i+1. Nothing reads the future.
"""
import numpy as np
from numba import njit


@njit(cache=True)
def simulate(o, h, l, c, sess, tradeable, ef, es, atr_,
             max_wait, depth, sl_mult, tp_r, side_mode, need_reclaim,
             pv, tick, comm, spread_t, slip_t, stop_slip_t):
    n = len(c)
    max_t = n // 2 + 8
    t_pnl = np.zeros(max_t, np.float64)
    t_in = np.zeros(max_t, np.int64)
    t_side = np.zeros(max_t, np.int64)
    t_why = np.zeros(max_t, np.int64)      # 1 stop, 2 target, 3 end
    k = 0
    ec = (spread_t + slip_t) * tick
    se = stop_slip_t * tick

    pos = 0; entry = 0.0; stop = 0.0; tp = 0.0; risk = 0.0; ent_i = -1
    bias = 0            # +1 after a bullish cross, -1 after a bearish
    since = 0           # bars since the cross
    pulled = 0          # has the pullback to the slow ema happened yet
    pend = 0

    for i in range(1, n):
        new_sess = sess[i] != sess[i - 1]

        # ---- fill a pending order at THIS bar's open ----
        if pend != 0 and pos == 0:
            pos = pend; entry = o[i]; ent_i = i; pend = 0
            risk = sl_mult * atr_[i - 1]
            stop = entry - pos * risk
            tp = entry + pos * tp_r * risk if tp_r > 0.0 else 0.0

        # ---- manage the open position on bar i's own range ----
        if pos != 0:
            hit = False; won = False; px = 0.0
            if pos == 1:
                if l[i] <= stop: hit = True
                elif tp_r > 0.0 and h[i] >= tp: won = True
            else:
                if h[i] >= stop: hit = True
                elif tp_r > 0.0 and l[i] <= tp: won = True
            if hit:
                px = o[i] if ((pos == 1 and o[i] < stop) or (pos == -1 and o[i] > stop)) else stop
                px += -se if pos == 1 else se
                t_pnl[k] = pos * (px - entry) * pv - comm - 2.0 * ec * pv
                t_in[k] = ent_i; t_side[k] = pos; t_why[k] = 1; k += 1
                pos = 0
            elif won:
                px = o[i] if ((pos == 1 and o[i] > tp) or (pos == -1 and o[i] < tp)) else tp
                t_pnl[k] = pos * (px - entry) * pv - comm - 2.0 * ec * pv
                t_in[k] = ent_i; t_side[k] = pos; t_why[k] = 2; k += 1
                pos = 0

        # ---- state machine on bar i's CLOSED values ----
        a = atr_[i]
        if np.isnan(ef[i]) or np.isnan(es[i]) or np.isnan(a) or a <= 0.0:
            continue

        # crossover sets the bias and RESETS the pullback flag
        if ef[i] > es[i] and ef[i - 1] <= es[i - 1]:
            bias = 1; since = 0; pulled = 0
        elif ef[i] < es[i] and ef[i - 1] >= es[i - 1]:
            bias = -1; since = 0; pulled = 0
        else:
            since += 1

        if bias != 0 and since <= max_wait:
            # pullback: the bar's extreme reaches the slow ema (within depth * ATR of it)
            if bias == 1 and l[i] <= es[i] + depth * a:
                pulled = 1
            elif bias == -1 and h[i] >= es[i] - depth * a:
                pulled = 1

            # entry trigger: close back on the fast ema's trend side after the pullback
            if pulled == 1 and pos == 0 and pend == 0 and i + 1 < n:
                if tradeable[i] == 1 and tradeable[i + 1] == 1 and not new_sess:
                    want = 0
                    if bias == 1:
                        if need_reclaim == 1:
                            if c[i] > ef[i] and c[i - 1] <= ef[i - 1]: want = 1
                        else:
                            if c[i] > ef[i]: want = 1
                    else:
                        if need_reclaim == 1:
                            if c[i] < ef[i] and c[i - 1] >= ef[i - 1]: want = -1
                        else:
                            if c[i] < ef[i]: want = -1
                    if want != 0 and (side_mode == 0 or side_mode == want):
                        pend = want
                        pulled = 0          # one entry per pullback leg

    if pos != 0:
        t_pnl[k] = pos * (c[n - 1] - entry) * pv - comm - 2.0 * ec * pv
        t_in[k] = ent_i; t_side[k] = pos; t_why[k] = 3; k += 1

    return t_pnl[:k], t_in[:k], t_side[:k], t_why[:k]
