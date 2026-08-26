"""Cached exits, so the matched control can be a gate instead of an afterthought.

`CLAUDE.md`: *"Run the matched control as a RESEARCH gate, not a final check.  Running it only at
the end let four rules reach a holdout they then passed while failing research."*  That is only
affordable if a control draw is cheap, and in a bar-walking engine it is not -- every draw is a
full re-simulation.

The observation that fixes it is the same one `research/tuner.py` is built on.  In this engine a
position's entire life depends on exactly two things: the bar its entry order was issued from, and
the geometry.  Nothing depends on which OTHER positions were taken -- the only coupling between
trades is that a new one cannot open while one is running, and that needs the exit BAR, not the
price path.  So the walk can be done once per geometry, for every bar as a hypothetical entry:

    exits[sys, i] -> (exit bar, units filled, gross P&L, exit reason, initial risk, average fill)

After that a rule is a trigger array, and evaluating it is a sequential scan that touches no price
data.  A 500-draw matched control on US30 costs about what one simulation used to.

Costs are deliberately kept OUT of the cached number.  `gross` is the price move before commission,
spread and stop slippage; all three are affine in the unit count, so any cost assumption is applied
at read time.  Sweeping the cost model is therefore free, which is the right incentive -- it is the
test most likely to kill a scalping result, and the protocol asks for it at 1.5x and 2x.

`turtle_test.check_tensor` asserts a scan over the tensor reproduces `turtle_sim.run` trade for
trade.  The tensor is an optimisation of that engine, never a second definition of the strategy.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import numpy as np
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turtle_sim as T
from turtle_sim import P, Series

NO_TRADE = -1


# ================================================================= build

@njit(cache=True)
def _build(o, h, l, c, ny_min, sess, atr, x, atr_mult, pyr_step, max_units, flatten_min,
           flat_grace, tp_r, max_hold, use_chan_exit, armed_stop, side,
           out_exit, out_reentry, out_units, out_gross, out_reason, out_risk, out_avg,
           out_first, out_stopunits):
    """For every bar i, walk the position an entry order issued at its close would produce."""
    n = o.shape[0]
    for i in range(n):
        out_exit[i] = NO_TRADE
        out_reentry[i] = i + 1
        out_units[i] = 0
        out_gross[i] = 0.0
        out_reason[i] = -1
        out_risk[i] = 0.0
        out_avg[i] = 0.0
        out_first[i] = 0.0
        out_stopunits[i] = 0

        if i + 1 >= n:
            continue
        if flatten_min >= 0 and sess[i + 1] != sess[i]:
            continue                      # the order is cancelled across a session boundary
        a = atr[i]
        if np.isnan(a) or a <= 0.0:
            continue

        entry_bar = i + 1
        fill = o[entry_bar]
        units = 1
        avg = fill
        first = fill
        init_risk = atr_mult * a
        stop_lvl = fill - side * init_risk
        next_add = fill + side * pyr_step * a
        tp_lvl = fill + side * tp_r * init_risk if tp_r > 0.0 else np.nan

        ord_stop = (c[i] - side * init_risk) if armed_stop else np.nan
        ord_tp = np.nan
        ord_flat = False
        flat_is_hold = False
        stop_from_chan = False
        pending_add = False
        pend_a = 0.0

        j = entry_bar
        while True:
            if j > entry_bar and pending_add:
                f2 = o[j]
                avg = (avg * units + f2) / (units + 1.0)
                units += 1
                stop_lvl = f2 - side * atr_mult * pend_a
                next_add = f2 + side * pyr_step * pend_a
                pending_add = False

            reason = -1
            px = 0.0
            hit_stop = (not np.isnan(ord_stop)) and (
                (l[j] <= ord_stop) if side > 0 else (h[j] >= ord_stop))
            hit_tp = (not np.isnan(ord_tp)) and (
                (h[j] >= ord_tp) if side > 0 else (l[j] <= ord_tp))
            if ord_flat:
                reason = T.EX_HOLD if flat_is_hold else T.EX_FLAT
                px = o[j]
            elif hit_stop:
                reason = T.EX_CHAN if stop_from_chan else T.EX_STOP
                if side > 0:
                    px = o[j] if o[j] < ord_stop else ord_stop
                else:
                    px = o[j] if o[j] > ord_stop else ord_stop
            elif hit_tp:
                reason = T.EX_TP
                if side > 0:
                    px = o[j] if o[j] > ord_tp else ord_tp
                else:
                    px = o[j] if o[j] < ord_tp else ord_tp
            if reason >= 0:
                out_exit[i] = j
                out_reentry[i] = j
                out_units[i] = units
                out_gross[i] = side * (px - avg) * units
                out_reason[i] = reason
                out_risk[i] = init_risk
                out_avg[i] = avg
                out_first[i] = first
                out_stopunits[i] = units if (reason == T.EX_STOP or reason == T.EX_CHAN) else 0
                break

            ord_stop = np.nan
            ord_tp = np.nan
            ord_flat = False
            a2 = atr[j]
            if not (np.isnan(a2) or a2 <= 0.0):
                if units < max_units and pyr_step > 0.0:
                    if (h[j] >= next_add) if side > 0 else (l[j] <= next_add):
                        pending_add = True
                        pend_a = a2

                ok_next = (j + 1 < n) and (sess[j + 1] == sess[j]) and \
                          (ny_min[j + 1] <= flatten_min + flat_grace)
                want_flat = flatten_min >= 0 and ny_min[j] >= flatten_min
                hold_out = max_hold > 0 and (j - entry_bar) >= max_hold
                closed = False
                if flatten_min < 0:
                    if hold_out:
                        ord_flat = True
                        flat_is_hold = True
                        pending_add = False
                elif want_flat or hold_out or not ok_next:
                    pending_add = False
                    flat_is_hold = hold_out and not want_flat
                    if ok_next:
                        ord_flat = True
                    else:
                        out_exit[i] = j
                        # The engine `continue`s past its entry logic after closing on the bar's
                        # close, so no new order can be issued from this bar.  The scan has to
                        # know that, or it would allow a re-entry the engine never took.
                        out_reentry[i] = j + 1
                        out_units[i] = units
                        out_gross[i] = side * (c[j] - avg) * units
                        out_reason[i] = T.EX_HOLD if flat_is_hold else T.EX_FLAT
                        out_risk[i] = init_risk
                        out_avg[i] = avg
                        out_first[i] = first
                        out_stopunits[i] = 0
                        closed = True
                if closed:
                    break
                if not ord_flat:
                    lvl = stop_lvl
                    stop_from_chan = False
                    if use_chan_exit and not np.isnan(x[j]):
                        if (x[j] > lvl) if side > 0 else (x[j] < lvl):
                            lvl = x[j]
                            stop_from_chan = True
                    ord_stop = lvl
                    ord_tp = tp_lvl

            j += 1
            if j >= n:
                out_exit[i] = n - 1
                out_reentry[i] = n
                out_units[i] = units
                out_gross[i] = side * (c[n - 1] - avg) * units
                out_reason[i] = T.EX_EOD
                out_risk[i] = init_risk
                out_avg[i] = avg
                out_first[i] = first
                out_stopunits[i] = 0
                break


@dataclass
class Exits:
    """Per-bar hypothetical positions, one set of arrays per entry system."""
    exit_bar: np.ndarray      # (2, n)  index 0 = System 1, index 1 = System 2
    reentry: np.ndarray
    units: np.ndarray
    gross: np.ndarray
    reason: np.ndarray
    risk: np.ndarray
    avg: np.ndarray
    first: np.ndarray
    stopunits: np.ndarray
    n: int
    side: int

    def net(self, k: int, cost_abs: float, cost_bp: float, stop_slip: float,
            tp_rests: bool = False) -> np.ndarray:
        """Net P&L per hypothetical position, for system `k` (0 or 1), at a cost assumption."""
        cost = self.units[k] * (cost_abs + cost_bp * 1e-4 * self.avg[k])
        if tp_rests:
            cost = np.where(self.reason[k] == T.EX_TP, cost * 0.5, cost)
        return self.gross[k] - cost - self.stopunits[k] * stop_slip


def build_leg(s: Series, p: P, exit_len: int) -> tuple:
    """The tensor for ONE trailing-exit length, as a tuple of 1-D arrays.

    Splitting the build by exit length is what keeps the sweep affordable.  A configuration pairs
    an exit length for System 1 with another for System 2, so building the pair jointly would cost
    |lengths|^2 walks; building each length once and pairing them afterwards costs |lengths|.
    """
    n = s.n
    a = lambda dt: np.empty(n, dt)
    ex, re_, un, gr, rs, rk, av, fi, su = (a(np.int64), a(np.int64), a(np.int64), a(np.float64),
                                           a(np.int64), a(np.float64), a(np.float64),
                                           a(np.float64), a(np.int64))
    x = s.lo(exit_len) if p.side > 0 else s.hi(exit_len)
    for _ in range(max(0, int(p.chan_shift))):
        x = T._shift1(x)
    _build(s.o, s.h, s.l, s.c, s.ny_min, s.sess, s.atr(p.atr_len), x,
           p.atr_mult, p.pyr_step, p.max_units, p.flatten_min, p.flat_grace, p.tp_r,
           p.max_hold, p.use_chan_exit, p.armed_stop, p.side,
           ex, re_, un, gr, rs, rk, av, fi, su)
    return (ex, re_, un, gr, rs, rk, av, fi, su)


def pair(leg1: tuple, leg2: tuple, n: int, side: int) -> Exits:
    """Assemble a two-system Exits from the System 1 and System 2 legs."""
    return Exits(*[np.stack((leg1[i], leg2[i])) for i in range(9)], n=n, side=side)


def build(s: Series, p: P) -> Exits:
    """Walk every bar as a hypothetical entry, once per entry system."""
    return pair(build_leg(s, p, p.exit1), build_leg(s, p, p.exit2), s.n, p.side)


# ================================================================= scan

@njit(cache=True)
def _scan(trigger, sess, c, exit_bar, reentry, units_a, gross_a, reason_a, risk_a, avg_a,
          first_a, stopunits_a, skip_win, one_shot, side,
          out_entry, out_exit, out_units, out_gross, out_reason, out_risk, out_avg,
          out_stopunits, out_sys):
    """Walk the trigger array, taking a position when flat.  No price data is touched."""
    n = trigger.shape[0]
    ntr = 0
    i = 0
    last_win = False
    sess_traded = -1
    while i < n:
        t = trigger[i]
        if t == 0:
            i += 1
            continue
        k = t - 1
        if one_shot and sess[i] == sess_traded:
            i += 1
            continue
        if t == 1 and skip_win and last_win:
            last_win = False
            i += 1
            continue
        e = exit_bar[k, i]
        if e < 0:
            i += 1
            continue
        out_entry[ntr] = i + 1
        out_exit[ntr] = e
        out_units[ntr] = units_a[k, i]
        out_gross[ntr] = gross_a[k, i]
        out_reason[ntr] = reason_a[k, i]
        out_risk[ntr] = risk_a[k, i]
        out_avg[ntr] = avg_a[k, i]
        out_stopunits[ntr] = stopunits_a[k, i]
        out_sys[ntr] = t
        ntr += 1
        last_win = side * (c[e] - first_a[k, i]) > 0.0
        if one_shot:
            sess_traded = sess[i + 1]
        i = reentry[k, i]
    return ntr


@dataclass
class Scan:
    entry_bar: np.ndarray
    exit_bar: np.ndarray
    units: np.ndarray
    gross: np.ndarray
    reason: np.ndarray
    risk: np.ndarray
    avg: np.ndarray
    stopunits: np.ndarray
    sysno: np.ndarray

    def __len__(self) -> int:
        return len(self.gross)

    def net(self, cost_abs: float = 0.0, cost_bp: float = 0.0, stop_slip: float = 0.0,
            tp_rests: bool = False) -> np.ndarray:
        cost = self.units * (cost_abs + cost_bp * 1e-4 * self.avg)
        if tp_rests:
            cost = np.where(self.reason == T.EX_TP, cost * 0.5, cost)
        return self.gross - cost - self.stopunits * stop_slip


def scan(s: Series, ex: Exits, trigger: np.ndarray, p: P, buf: dict | None = None) -> Scan:
    cap = max(256, s.n // 2 + 8)
    if buf is None:
        buf = {"e": np.empty(cap, np.int64), "x": np.empty(cap, np.int64),
               "u": np.empty(cap, np.int64), "g": np.empty(cap, np.float64),
               "r": np.empty(cap, np.int64), "k": np.empty(cap, np.float64),
               "a": np.empty(cap, np.float64), "su": np.empty(cap, np.int64),
               "sy": np.empty(cap, np.int64)}
    ntr = _scan(trigger, s.sess, s.c, ex.exit_bar, ex.reentry, ex.units, ex.gross, ex.reason,
                ex.risk, ex.avg, ex.first, ex.stopunits, p.skip_win, p.one_shot, p.side,
                buf["e"], buf["x"], buf["u"], buf["g"], buf["r"], buf["k"], buf["a"],
                buf["su"], buf["sy"])
    return Scan(buf["e"][:ntr].copy(), buf["x"][:ntr].copy(), buf["u"][:ntr].copy(),
                buf["g"][:ntr].copy(), buf["r"][:ntr].copy(), buf["k"][:ntr].copy(),
                buf["a"][:ntr].copy(), buf["su"][:ntr].copy(), buf["sy"][:ntr].copy())


# ================================================================= matched control

class Control:
    """Random entries with the same side, geometry and minute-of-day distribution as the rule.

    The comparison a scalping rule actually has to win is not "did it make money" -- on a sample
    where the instrument tripled, being long at 09:35 makes money.  It is "did it beat entering at
    the same clock times, with the same barriers, the same pyramiding and the same costs, for no
    reason at all".  That single control prices in drift, the cost line, barrier width and session
    timing simultaneously, which no single-factor adjustment does.

    Matching is on (minute-of-day, entry system) counts, drawn without replacement from the bars
    available at each minute WITHIN THE SAME BLOCK, so a research-block control cannot borrow bars
    from the locked block.
    """

    def __init__(self, s: Series, trigger: np.ndarray, block: np.ndarray | None = None,
                 seed: int = 20250822, slot: np.ndarray | None = None):
        self.s = s
        self.rng = np.random.default_rng(seed)
        blk = np.zeros(s.n, np.int64) if block is None else block
        self.groups: list[tuple[np.ndarray, int, int]] = []
        # A "slot" is one bucket: the pool the control draws from.  By default that is
        # (block, minute-of-day); pass `slot` to add strata -- `vol_slot` adds an ATR quintile,
        # which is the one that matters for a breakout rule.
        key = (blk * 10_000 + s.ny_min) if slot is None else (blk * 10_000_000 + slot)
        order = np.argsort(key, kind="stable")
        ks = key[order]
        bounds = np.flatnonzero(np.diff(ks)) + 1
        for pool in np.split(order, bounds):
            t = trigger[pool]
            n1, n2 = int((t == 1).sum()), int((t == 2).sum())
            if n1 or n2:
                self.groups.append((pool, n1, n2))
        self.n_sig = sum(a + b for _, a, b in self.groups)

    def draw(self, out: np.ndarray | None = None) -> np.ndarray:
        t = np.zeros(self.s.n, np.int64) if out is None else out
        if out is not None:
            t.fill(0)
        for pool, n1, n2 in self.groups:
            pick = self.rng.choice(pool, size=n1 + n2, replace=False)
            if n2:
                t[pick[:n2]] = 2
            if n1:
                t[pick[n2:]] = 1
        return t


def vol_slot(s: Series, atr_len: int, n_strata: int = 5) -> tuple[np.ndarray, int]:
    """Bucket bars by (minute-of-day, ATR quantile within that minute).

    A Donchian breakout does not fire at a random moment: it fires when the bar is big.  A wider
    bar means a wider ATR stop, more units on the ladder and a longer hold, so a breakout trade is
    mechanically larger in dollars than a random one -- and on a drifting sample "larger" and
    "better" are the same sign.  A control matched only on the clock would credit that to the rule.

    Stratifying the draw pool by ATR quantile *within* each minute removes it: the control now
    enters at the same times AND in the same volatility state, so what is left of the difference is
    the direction call.
    """
    a = s.atr(atr_len)
    minutes = np.unique(s.ny_min)
    mslot = np.searchsorted(minutes, s.ny_min)
    strat = np.zeros(s.n, np.int64)
    for m in range(len(minutes)):
        sel = np.flatnonzero(mslot == m)
        v = a[sel]
        ok = np.isfinite(v)
        if ok.sum() < n_strata * 10:
            continue
        q = np.quantile(v[ok], np.linspace(0, 1, n_strata + 1)[1:-1])
        strat[sel] = np.searchsorted(q, v, side="right")
    return mslot * n_strata + strat, len(minutes) * n_strata


__all__ = ["Exits", "Scan", "Control", "build", "build_leg", "pair", "scan", "vol_slot",
           "NO_TRADE"]
