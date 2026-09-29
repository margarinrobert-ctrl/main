"""Turtle Trading (long only), implemented faithfully to the supplied indicator spec.

WHAT THE SPEC SAYS, and every detail below is reproduced rather than tidied up:

  System 2   enter when high > the previous bar's `entryLen2`-bar highest high. Always allowed.
  System 1   enter when high > the previous bar's `entryLen1`-bar highest high, but SKIPPED once
             if the last completed trade was a winner (and the skip flag is then cleared, so it
             skips one signal, not all of them).
  exits      ATR stop first, then the channel low (`exitLen1` for S1, `exitLen2` for S2).
  pyramid    while units < maxUnits and high >= nextAdd, add a unit; the stop RE-ANCHORS to the
             new fill minus atrMult*ATR, and nextAdd moves to fill + pyramidStep*ATR.
  fills      every entry and add fills at the NEXT bar's open. ATR is read at the signal bar.
  winner     decided by close-at-exit vs the FIRST unit's entry, which is what the spec compares.

Two things the spec leaves open, resolved conservatively and stated here because they move the
result more than any parameter does:

  EXIT PRICE. The indicator only marks exits, it does not price them. A stop fills at
  min(open, stop) and a channel exit at min(open, channel) -- so a gap through the level is paid
  in full, and a level touched intrabar fills exactly at the level, never better.

  "20-DAY" IS 20 BARS. The spec indexes bars, not sessions, so on a 15-minute chart its "20-day
  high" is five hours. Both readings are testable here: `bars()` takes any timeframe, and the
  sweep treats the timeframe as a parameter rather than assuming the original daily intent.
"""
from __future__ import annotations

import numpy as np
from numba import njit

STOP_EXIT, S1_EXIT, S2_EXIT = 1, 2, 3


@njit(cache=True)
def _rolling_max(x, n):
    """Monotonic-deque rolling maximum: O(len(x)) rather than O(len(x)*n).

    The naive double loop is 11 million comparisons per channel on a 206k-bar series, which is
    what made a 100,000-configuration sweep look infeasible.
    """
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
def _rolling_min(x, n):
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


@njit(cache=True)
def _atr_wilder(h, l, c, n):
    m = len(c); tr = np.empty(m); out = np.full(m, np.nan)
    tr[0] = h[0] - l[0]
    for i in range(1, m):
        a = h[i] - l[i]
        b = abs(h[i] - c[i - 1])
        d = abs(l[i] - c[i - 1])
        tr[i] = a if (a > b and a > d) else (b if b > d else d)
    s = 0.0
    for i in range(n):
        s += tr[i]
    out[n - 1] = s / n
    for i in range(n, m):
        out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out


@njit(cache=True)
def run(o, h, l, c, hi1, hi2, lo1, lo2, atr, start,
        atr_mult, pyramid_step, max_units, skip_after_winner, allow_s1, allow_s2,
        cost_pts, slip_pts, gate, path_exit):
    """One pass of the state machine. Returns per-trade arrays.

    P&L is in INDEX POINTS summed over units, and `risk` is the initial one-unit risk
    (atr_mult * ATR at the first entry) so a trade can also be read in R.
    """
    n = len(c)
    cap = n // 2 + 16          # an entry needs a bar and an exit needs another
    t_pnl = np.zeros(cap); t_risk = np.zeros(cap); t_units = np.zeros(cap, np.int64)
    t_sys = np.zeros(cap, np.int64); t_why = np.zeros(cap, np.int64)
    t_in = np.zeros(cap, np.int64); t_out = np.zeros(cap, np.int64)
    t_mfe = np.zeros(cap); t_mae = np.zeros(cap)
    k = 0

    in_trade = False; system = 0; units = 0
    stop = 0.0; next_add = 0.0; first_entry = 0.0; risk0 = 0.0
    fills = np.zeros(8); entry_bar = 0
    last_winner = False
    hi_since = 0.0; lo_since = 0.0

    for i in range(start, n):
        exited = False
        if in_trade:
            if h[i] > hi_since:
                hi_since = h[i]
            if l[i] < lo_since:
                lo_since = l[i]
            why = 0; px = 0.0
            chan = lo1[i - 1] if system == 1 else lo2[i - 1]
            if path_exit:
                # Path-accurate: as price falls it reaches the HIGHER level first, so the
                # effective exit is max(stop, channel). This is what a single Pine stop order
                # does. The spec's own ordering (below) checks the ATR stop first and therefore
                # books the WORSE of the two whenever one bar pierces both.
                lvl = stop if stop > chan else chan
                if l[i] <= lvl:
                    why = STOP_EXIT if stop > chan else (S1_EXIT if system == 1 else S2_EXIT)
                    px = (o[i] if o[i] < lvl else lvl) - slip_pts
            elif l[i] <= stop:
                why = STOP_EXIT
                px = o[i] if o[i] < stop else stop
                px -= slip_pts
            elif system == 1 and l[i] <= lo1[i - 1]:
                why = S1_EXIT
                px = o[i] if o[i] < lo1[i - 1] else lo1[i - 1]
                px -= slip_pts
            elif system == 2 and l[i] <= lo2[i - 1]:
                why = S2_EXIT
                px = o[i] if o[i] < lo2[i - 1] else lo2[i - 1]
                px -= slip_pts
            if why != 0:
                pnl = 0.0
                for u in range(units):
                    pnl += (px - fills[u]) - cost_pts
                if k < cap:
                    t_pnl[k] = pnl; t_risk[k] = risk0; t_units[k] = units
                    t_sys[k] = system; t_why[k] = why
                    t_in[k] = entry_bar; t_out[k] = i
                    t_mfe[k] = hi_since - first_entry; t_mae[k] = first_entry - lo_since
                    k += 1
                last_winner = c[i] > first_entry
                in_trade = False; system = 0; units = 0; exited = True
            elif units < max_units and h[i] >= next_add and pyramid_step > 0.0:
                if i + 1 < n:
                    fp = o[i + 1]
                    fills[units] = fp + slip_pts
                    units += 1
                    stop = fp - atr_mult * atr[i]
                    next_add = fp + pyramid_step * atr[i]

        if (not in_trade) and (not exited):
            took = False
            if not gate[i]:
                pass
            elif allow_s2 and h[i] > hi2[i - 1] and i + 1 < n:
                fp = o[i + 1]
                in_trade = True; system = 2; units = 1
                fills[0] = fp + slip_pts; first_entry = fp
                risk0 = atr_mult * atr[i]
                stop = fp - risk0
                next_add = fp + pyramid_step * atr[i]
                entry_bar = i + 1
                hi_since = fp; lo_since = fp
                took = True
            elif allow_s1 and h[i] > hi1[i - 1] and i + 1 < n:
                if skip_after_winner and last_winner:
                    last_winner = False
                else:
                    fp = o[i + 1]
                    in_trade = True; system = 1; units = 1
                    fills[0] = fp + slip_pts; first_entry = fp
                    risk0 = atr_mult * atr[i]
                    stop = fp - risk0
                    next_add = fp + pyramid_step * atr[i]
                    entry_bar = i + 1
                    hi_since = fp; lo_since = fp
                    took = True
            if took and risk0 <= 0.0:
                in_trade = False; units = 0; system = 0
    return (t_pnl[:k], t_risk[:k], t_units[:k], t_sys[:k], t_why[:k],
            t_in[:k], t_out[:k], t_mfe[:k], t_mae[:k])


def channels(d, e1, e2, x1, x2, an):
    h, l, c = d["h"], d["l"], d["c"]
    return (_rolling_max(h, e1), _rolling_max(h, e2),
            _rolling_min(l, x1), _rolling_min(l, x2), _atr_wilder(h, l, c, an))


def backtest(d, entry1=20, entry2=55, exit1=10, exit2=20, atr_len=20, atr_mult=2.0,
             pyramid_step=0.5, max_units=4, skip_after_winner=True,
             allow_s1=True, allow_s2=True, cost_pts=0.0, slip_pts=0.0, cache=None,
             gate=None, path_exit=False):
    key = (entry1, entry2, exit1, exit2, atr_len)
    if cache is not None and key in cache:
        hi1, hi2, lo1, lo2, atr = cache[key]
    else:
        hi1, hi2, lo1, lo2, atr = channels(d, entry1, entry2, exit1, exit2, atr_len)
        if cache is not None:
            cache[key] = (hi1, hi2, lo1, lo2, atr)
    start = max(entry1, entry2, exit1, exit2, atr_len) + 1
    g = np.ones(len(d["c"]), np.bool_) if gate is None else np.ascontiguousarray(
        np.asarray(gate, np.bool_))
    p, r, u, s, w, bi, bo, mfe, mae = run(
        d["o"], d["h"], d["l"], d["c"], hi1, hi2, lo1, lo2, atr, start,
        float(atr_mult), float(pyramid_step), int(max_units),
        bool(skip_after_winner), bool(allow_s1), bool(allow_s2),
        float(cost_pts), float(slip_pts), g, bool(path_exit))
    return dict(pnl=p, risk=r, units=u, system=s, why=w, bar_in=bi, bar_out=bo,
                mfe=mfe, mae=mae, R=np.where(r > 0, p / np.maximum(r, 1e-9), 0.0))


@njit(cache=True)
def run_random(o, h, l, c, lo1, lo2, atr, start, atr_mult, pyramid_step, max_units,
               p_enter, use_sys, cost_pts, slip_pts, seed):
    """The same trade MANAGEMENT with a RANDOM entry trigger.

    This is the null the breakout has to beat. Everything else is held identical -- the ATR stop,
    the channel exit, the pyramid ladder, the fill convention, the costs -- and only the decision
    of WHEN to enter is replaced by a coin flip at rate `p_enter`. If a Turtle variant does not
    beat this, its edge is in the exit machinery and the market's drift, not in the 20- or 55-bar
    breakout that the strategy is named after.
    """
    np.random.seed(seed)
    n = len(c)
    cap = n // 2 + 16
    t_pnl = np.zeros(cap); t_risk = np.zeros(cap); t_units = np.zeros(cap, np.int64)
    t_in = np.zeros(cap, np.int64)
    k = 0
    in_trade = False; units = 0
    stop = 0.0; next_add = 0.0; first_entry = 0.0; risk0 = 0.0
    fills = np.zeros(8)
    for i in range(start, n):
        exited = False
        if in_trade:
            lo_ref = lo1[i - 1] if use_sys == 1 else lo2[i - 1]
            why = 0; px = 0.0
            if l[i] <= stop:
                why = 1; px = (o[i] if o[i] < stop else stop) - slip_pts
            elif l[i] <= lo_ref:
                why = 2; px = (o[i] if o[i] < lo_ref else lo_ref) - slip_pts
            if why != 0:
                pnl = 0.0
                for u in range(units):
                    pnl += (px - fills[u]) - cost_pts
                if k < cap:
                    t_pnl[k] = pnl; t_risk[k] = risk0; t_units[k] = units; t_in[k] = i
                    k += 1
                in_trade = False; units = 0; exited = True
            elif units < max_units and h[i] >= next_add and pyramid_step > 0.0:
                if i + 1 < n:
                    fp = o[i + 1]
                    fills[units] = fp + slip_pts; units += 1
                    stop = fp - atr_mult * atr[i]
                    next_add = fp + pyramid_step * atr[i]
        if (not in_trade) and (not exited) and i + 1 < n:
            if np.random.random() < p_enter and atr[i] > 0.0:
                fp = o[i + 1]
                in_trade = True; units = 1
                fills[0] = fp + slip_pts; first_entry = fp
                risk0 = atr_mult * atr[i]
                stop = fp - risk0
                next_add = fp + pyramid_step * atr[i]
    return t_pnl[:k], t_risk[:k], t_units[:k], t_in[:k]


def control(d, cfg, block, n_target, draws=200, cost_pts=0.0, slip_pts=0.0, seed=101,
            cache=None):
    """Random-entry control matched on trade count, using cfg's own exit machinery."""
    key = (cfg["entry1"], cfg["entry2"], cfg["exit1"], cfg["exit2"], 20)
    if cache is not None and key in cache:
        hi1, hi2, lo1, lo2, atr = cache[key]
    else:
        hi1, hi2, lo1, lo2, atr = channels(d, cfg["entry1"], cfg["entry2"],
                                           cfg["exit1"], cfg["exit2"], 20)
        if cache is not None:
            cache[key] = (hi1, hi2, lo1, lo2, atr)
    start = max(cfg["entry1"], cfg["entry2"], cfg["exit1"], cfg["exit2"], 20) + 1
    blk = np.asarray(block, bool)
    elig = int(blk[start:].sum())
    if elig < 50 or n_target < 5:
        return None
    p_enter = min(0.95, max(1e-5, n_target / float(elig)))
    outR = np.empty(draws); outN = np.empty(draws)
    for s in range(draws):
        p, r, u, bi = run_random(d["o"], d["h"], d["l"], d["c"], lo1, lo2, atr, start,
                                 float(cfg["atr_mult"]), float(cfg["pyramid_step"]),
                                 int(cfg["max_units"]), float(p_enter), 2,
                                 float(cost_pts), float(slip_pts), seed + s)
        if len(p) == 0:
            outR[s] = 0.0; outN[s] = 0; continue
        sel = blk[bi]
        if sel.sum() < 5:
            outR[s] = 0.0; outN[s] = 0; continue
        rr = np.where(r[sel] > 0, p[sel] / np.maximum(r[sel], 1e-9), 0.0)
        outR[s] = float(rr.mean()); outN[s] = int(sel.sum())
    ok = outN > 0
    return outR[ok] if ok.any() else None
