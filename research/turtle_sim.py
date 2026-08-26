"""The Turtle-scalp engine: Pine semantics, in numba, fast enough to sweep.

WHAT IT MIRRORS
---------------
`Turtle Long-Only (measured presets)` as supplied: a Donchian breakout with two entry systems, a
Wilder ATR stop re-anchored to every actual fill, up to four pyramid units spaced `pyrStep * N`
apart, an exit at the HIGHER of the ATR stop and the trailing channel low, and the System-1
skip-after-a-win filter.  The gates (`ADX <`, distance above EMA100) are kept as written.

Pine's execution model is reproduced exactly rather than approximated, because at a scalping
horizon the approximation is the result:

  * a decision taken on the close of bar *i* (`barstate.isconfirmed`) becomes an order that fills
    at the OPEN of bar *i+1*.  Nothing is ever filled on the bar that generated it.
  * `strategy.exit(stop=...)` issued on the close of bar *i* is live from bar *i+1*.  The supplied
    script derives `stopLvl` from `strategy.opentrades.entry_price`, which does not exist until the
    fill has happened, so **the first bar of a position carries no stop**.  That is a real property
    of the script and it is modelled, not smoothed away; `armed_stop` switches to the alternative
    (anchor the stop to the signal bar's close, place it with the entry) so the difference can be
    priced instead of assumed.
  * when a bar contains both the stop and the take-profit the trade is booked at the STOP.  The
    intrabar path is unknown and the pessimistic reading is the only one that cannot flatter.

WHAT IT ADDS, AND WHY
---------------------
A Turtle position is held for days.  A 07:00-11:00 session is four hours.  Those two facts cannot
both be true, so the scalping version needs knobs the original does not have -- an entry window, a
hard flatten time, an R-multiple take-profit, a max hold.  They are all off by default so that
`params()` with no arguments reproduces the supplied script bar for bar.

`side = -1` runs the exact mirror image (Donchian low breakout, stop above, adds below).  It is not
there to be traded.  `CLAUDE.md` §4c: on a sample where the instrument tripled, a long-only search
finds the bull market and every holdout agrees with it.  The short mirror is the control that says
whether anything was found at all.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, asdict, replace

import numpy as np
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------- exit reason codes
EX_STOP, EX_CHAN, EX_TP, EX_FLAT, EX_HOLD, EX_EOD = 0, 1, 2, 3, 4, 5
EXIT_NAMES = ("atr_stop", "chan_stop", "take_profit", "session_flatten", "max_hold", "data_end")


# ================================================================= indicators (Pine definitions)

@njit(cache=True)
def _rma(x, n):
    """Pine `ta.rma`: SMA seed at index n-1, then Wilder smoothing.  NaN before the seed."""
    out = np.full(x.shape[0], np.nan)
    if x.shape[0] < n:
        return out
    s = 0.0
    for i in range(n):
        s += x[i]
    out[n - 1] = s / n
    for i in range(n, x.shape[0]):
        out[i] = (out[i - 1] * (n - 1) + x[i]) / n
    return out


@njit(cache=True)
def _ema(x, n):
    """Pine `ta.ema`: SMA seed at index n-1, then alpha = 2/(n+1)."""
    out = np.full(x.shape[0], np.nan)
    if x.shape[0] < n:
        return out
    s = 0.0
    for i in range(n):
        s += x[i]
    out[n - 1] = s / n
    a = 2.0 / (n + 1.0)
    for i in range(n, x.shape[0]):
        out[i] = a * x[i] + (1.0 - a) * out[i - 1]
    return out


@njit(cache=True)
def _true_range(h, l, c):
    n = h.shape[0]
    tr = np.empty(n)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        a = h[i] - l[i]
        b = abs(h[i] - c[i - 1])
        d = abs(l[i] - c[i - 1])
        tr[i] = max(a, max(b, d))
    return tr


@njit(cache=True)
def _highest(x, n):
    """`ta.highest(x, n)` -- includes the current bar.  Monotonic deque, O(len)."""
    m = x.shape[0]
    out = np.full(m, np.nan)
    dq = np.empty(m, np.int64)
    head, tail = 0, 0
    for i in range(m):
        while tail > head and x[dq[tail - 1]] <= x[i]:
            tail -= 1
        dq[tail] = i
        tail += 1
        while dq[head] <= i - n:
            head += 1
        if i >= n - 1:
            out[i] = x[dq[head]]
    return out


@njit(cache=True)
def _lowest(x, n):
    m = x.shape[0]
    out = np.full(m, np.nan)
    dq = np.empty(m, np.int64)
    head, tail = 0, 0
    for i in range(m):
        while tail > head and x[dq[tail - 1]] >= x[i]:
            tail -= 1
        dq[tail] = i
        tail += 1
        while dq[head] <= i - n:
            head += 1
        if i >= n - 1:
            out[i] = x[dq[head]]
    return out


@njit(cache=True)
def _dmi(h, l, c, di_len, adx_len):
    """Pine `ta.dmi(diLen, adxLen)` -> (+DI, -DI, ADX)."""
    n = h.shape[0]
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    for i in range(1, n):
        up = h[i] - h[i - 1]
        dn = l[i - 1] - l[i]
        plus_dm[i] = up if (up > dn and up > 0.0) else 0.0
        minus_dm[i] = dn if (dn > up and dn > 0.0) else 0.0
    trur = _rma(_true_range(h, l, c), di_len)
    sp = _rma(plus_dm, di_len)
    sm = _rma(minus_dm, di_len)
    plus = np.full(n, np.nan)
    minus = np.full(n, np.nan)
    dx = np.full(n, np.nan)
    for i in range(n):
        if np.isnan(trur[i]) or trur[i] == 0.0:
            continue
        plus[i] = 100.0 * sp[i] / trur[i]
        minus[i] = 100.0 * sm[i] / trur[i]
        s = plus[i] + minus[i]
        dx[i] = abs(plus[i] - minus[i]) / (1.0 if s == 0.0 else s)
    adx = _rma(np.where(np.isnan(dx), 0.0, dx), adx_len) * 100.0
    for i in range(n):
        if np.isnan(dx[i]):
            adx[i] = np.nan
    return plus, minus, adx


# ================================================================= parameters

@dataclass(frozen=True)
class P:
    # --- signal
    entry1: int = 20          # System 1 Donchian entry length
    entry2: int = 55          # System 2 Donchian entry length
    exit1: int = 10           # System 1 Donchian trailing exit
    exit2: int = 20           # System 2 Donchian trailing exit
    atr_len: int = 20
    atr_mult: float = 2.0
    pyr_step: float = 0.5     # add every pyr_step * N in favour
    max_units: int = 4
    skip_win: bool = True     # the Turtle System-1 skip-after-a-win filter
    # --- gates
    adx_max: float = 0.0      # 0 = off
    ext_max: float = 0.0      # max (close - ema100)/ATR, 0 = off
    ema_len: int = 100
    break_ticks: float = 0.0  # require the break by this many price units
    # --- scalping additions (all no-ops at their defaults)
    sess_start: int = 0       # New York minute-of-day, entries allowed from
    sess_end: int = 1440      # ... to (exclusive)
    flatten_min: int = -1     # hard market exit at/after this NY minute, -1 = never
    flat_grace: int = 60      # minutes the flatten order may rest before it becomes a close
    tp_r: float = 0.0         # take-profit at tp_r x initial risk, 0 = off
    max_hold: int = 0         # bars, 0 = off
    use_chan_exit: bool = True
    chan_shift: int = 1       # bars to lag the trailing exit channel; 1 = the supplied Pine
    armed_stop: bool = False  # stop live on the entry bar, anchored to the signal close
    one_shot: bool = False    # at most one position per session
    side: int = 1             # 1 = long (the supplied script), -1 = the short mirror
    # --- costs, in price units unless named _bp
    cost_abs: float = 0.0     # round turn, absolute price
    cost_bp: float = 0.0      # round turn, basis points of entry price
    stop_slip: float = 0.0    # extra adverse price on stop fills
    tp_rests: bool = False    # take-profit is a resting limit: pays no spread

    def as_dict(self) -> dict:
        return asdict(self)


def params(**kw) -> P:
    return P(**kw)


# ================================================================= the kernel

@njit(cache=True)
def _simulate(o, h, l, c, ny_min, sess, atr, e1, e2, x1, x2,
              adx, ema, forced, use_forced, atr_mult, pyr_step, max_units,
              skip_win, adx_max, ext_max, break_ticks, sess_start, sess_end, flatten_min,
              flat_grace, tp_r, max_hold, use_chan_exit, armed_stop, one_shot, side,
              cost_abs, cost_bp, stop_slip, tp_rests,
              out_entry_bar, out_exit_bar, out_units, out_pnl, out_reason, out_risk, out_sys):
    """One sequential pass.  Returns the number of closed positions written to the out arrays.

    Bar i is processed in Pine's order: fill the orders issued on bar i-1 (market at the open,
    then stop/limit intrabar), then run the script on the close of bar i to issue orders for i+1.

    `e1`/`e2` are the System 1 / System 2 ENTRY levels already shifted one bar (so `e2[i]` is the
    channel as of bar i-1, which is what `chanHi2[1]` means in the Pine) and already resolved for
    `side`.  `x1`/`x2` are the unshifted trailing EXIT levels, likewise side-resolved.  Doing the
    shift and the side choice outside the kernel is what lets a caller hand it a slice of the
    series covering only the session window: nothing inside reads index i-1 of a level array, so
    a discontiguous slice cannot silently read across a gap.

    `forced` replaces the Donchian signal when `use_forced` is set -- 0 no entry, 1 System 1,
    2 System 2.  That is the matched control: identical geometry, costs, pyramiding, session and
    exit machinery, with the only thing removed being the reason for entering.
    """
    n = o.shape[0]
    ntr = 0

    # --- open-position state
    units = 0                 # units currently filled
    sys_on = 0                # 1 or 2, which entry system opened this position
    avg_px = 0.0              # cost basis of the filled units, in price
    first_fill = 0.0
    stop_lvl = np.nan
    next_add = np.nan
    pend_atr = np.nan         # the ATR reading at the signal bar, per the script's pendAtr
    entry_bar = -1
    init_risk = 0.0           # atr_mult * N at the first fill, per unit -- the R denominator
    tp_lvl = np.nan
    last_win = False
    sess_traded = -1          # session index that has already used its one_shot allowance

    # --- orders standing for the next bar
    ord_entry = 0             # 0 none, 1 open a new position, 2 pyramid add
    ord_sys = 0
    ord_atr = np.nan
    ord_stop = np.nan         # stop price live for the next bar (nan = none)
    ord_tp = np.nan
    ord_flat = False          # market exit at the next open
    armed_stop_px = np.nan    # only used when armed_stop is on
    stop_from_chan = False    # the live stop came from the trailing channel, not the ATR level
    flat_is_hold = False      # the flatten order was raised by max_hold, not by the clock

    for i in range(n):
        new_sess = i > 0 and sess[i] != sess[i - 1]

        # ---------------------------------------------------------------- 1. fills at the open
        if ord_entry != 0:
            # A session boundary cancels an unfilled entry: the script would not have wanted a
            # position opened across the overnight gap on a signal from yesterday's close.
            if new_sess and flatten_min >= 0:
                ord_entry = 0
            else:
                fill = o[i]
                if units == 0:
                    units = 1
                    avg_px = fill
                    first_fill = fill
                    entry_bar = i
                    sys_on = ord_sys
                    pend_atr = ord_atr
                    init_risk = atr_mult * ord_atr
                    stop_lvl = fill - side * atr_mult * ord_atr
                    next_add = fill + side * pyr_step * ord_atr
                    tp_lvl = fill + side * tp_r * init_risk if tp_r > 0.0 else np.nan
                    if one_shot:
                        sess_traded = sess[i]
                else:
                    avg_px = (avg_px * units + fill) / (units + 1.0)
                    units += 1
                    stop_lvl = fill - side * atr_mult * ord_atr
                    next_add = fill + side * pyr_step * ord_atr
                ord_entry = 0

        if units > 0:
            # An armed stop is live from the entry bar itself.
            if armed_stop and i == entry_bar and not np.isnan(armed_stop_px):
                ord_stop = armed_stop_px
                stop_from_chan = False

            # ------------------------------------------------------------ 2. intrabar exits
            reason = -1
            px = 0.0
            hit_stop = (not np.isnan(ord_stop)) and (
                (l[i] <= ord_stop) if side > 0 else (h[i] >= ord_stop))
            hit_tp = (not np.isnan(ord_tp)) and (
                (h[i] >= ord_tp) if side > 0 else (l[i] <= ord_tp))

            if ord_flat:
                reason = EX_HOLD if flat_is_hold else EX_FLAT
                px = o[i]
            elif hit_stop:
                # A gap through the stop fills at the open, not at the stop price.
                reason = EX_CHAN if stop_from_chan else EX_STOP
                if side > 0:
                    px = o[i] if o[i] < ord_stop else ord_stop
                else:
                    px = o[i] if o[i] > ord_stop else ord_stop
                px -= side * stop_slip
            elif hit_tp:
                reason = EX_TP
                if side > 0:
                    px = o[i] if o[i] > ord_tp else ord_tp
                else:
                    px = o[i] if o[i] < ord_tp else ord_tp

            if reason >= 0:
                gross = side * (px - avg_px) * units
                cost = units * (cost_abs + cost_bp * 1e-4 * avg_px)
                if reason == EX_TP and tp_rests:
                    cost *= 0.5
                out_entry_bar[ntr] = entry_bar
                out_exit_bar[ntr] = i
                out_units[ntr] = units
                out_pnl[ntr] = gross - cost
                out_reason[ntr] = reason
                out_risk[ntr] = init_risk
                out_sys[ntr] = sys_on
                ntr += 1
                # Pine's own definition, kept verbatim so the mirror is exact: `lastWin := close >
                # firstFill`, read on the bar the position went flat.  It ignores costs and the
                # pyramid average on purpose -- it is what the shipped script computes.
                last_win = side * (c[i] - first_fill) > 0.0
                units = 0
                sys_on = 0
                stop_lvl = np.nan
                next_add = np.nan
                tp_lvl = np.nan
                ord_stop = np.nan
                ord_tp = np.nan
                ord_flat = False
                armed_stop_px = np.nan

        # ---------------------------------------------------------------- 3. script on the close
        ord_stop = np.nan
        ord_tp = np.nan
        ord_flat = False
        armed_stop_px = np.nan

        a = atr[i]
        if np.isnan(a) or a <= 0.0:
            continue

        if units == 0:
            if one_shot and sess[i] == sess_traded:
                continue
            m = ny_min[i]
            in_sess = (m >= sess_start) and (m < sess_end)
            if not in_sess:
                continue
            if adx_max > 0.0 and (np.isnan(adx[i]) or adx[i] >= adx_max):
                continue
            if ext_max > 0.0:
                if np.isnan(ema[i]):
                    continue
                if side * (c[i] - ema[i]) / a >= ext_max:
                    continue
            if use_forced:
                s2 = forced[i] == 2
                s1 = forced[i] == 1
            elif side > 0:
                # Donchian break, measured against the channel as of the PREVIOUS bar.
                lvl2, lvl1 = e2[i], e1[i]
                s2 = (not np.isnan(lvl2)) and h[i] > lvl2 + break_ticks
                s1 = (not np.isnan(lvl1)) and h[i] > lvl1 + break_ticks
            else:
                lvl2, lvl1 = e2[i], e1[i]
                s2 = (not np.isnan(lvl2)) and l[i] < lvl2 - break_ticks
                s1 = (not np.isnan(lvl1)) and l[i] < lvl1 - break_ticks
            if s2:
                ord_entry, ord_sys, ord_atr = 1, 2, a
            elif s1:
                if skip_win and last_win:
                    last_win = False
                else:
                    ord_entry, ord_sys, ord_atr = 1, 1, a
            if ord_entry == 1:
                # The cost model charges entry slippage through the fill price used above; the
                # armed stop is anchored to this bar's close because the fill is not known yet.
                if armed_stop:
                    armed_stop_px = c[i] - side * atr_mult * a
            continue

        # ---- position open: adds, flatten, hold cap, then the trailing stop for the next bar
        if units < max_units and pyr_step > 0.0:
            trig = (h[i] >= next_add) if side > 0 else (l[i] <= next_add)
            if trig:
                ord_entry, ord_sys, ord_atr = 2, sys_on, a

        # A market exit issued on the close of bar i fills at the open of bar i+1.  When bar i+1
        # is in another session -- a holiday, a half day, a data hole -- that "next open" is days
        # away, and the model would hold a scalp across the very gap it exists to avoid.  A live
        # desk flattens on the close instead.  So in scalp mode (`flatten_min >= 0`) a position
        # NEVER crosses a session boundary: if the next bar is not in this session and inside the
        # grace window, the position closes at this bar's close, whether or not the clock reached
        # the flatten time.  New Year's Eve 2008 in gold is the case that forces this -- the
        # session ends at 10:45 New York, `ny_min >= 660` never fires, and without the rule the
        # trade was carried to 2 January.  It reads the next bar's CLOCK, never its price: the
        # exchange calendar is known in advance.
        ok_next = (i + 1 < n) and (sess[i + 1] == sess[i]) and \
                  (ny_min[i + 1] <= flatten_min + flat_grace)
        want_flat = flatten_min >= 0 and ny_min[i] >= flatten_min
        hold_out = max_hold > 0 and (i - entry_bar) >= max_hold
        if flatten_min < 0:
            if hold_out:
                ord_flat = True
                flat_is_hold = True
                ord_entry = 0
        elif want_flat or hold_out or not ok_next:
            ord_entry = 0
            flat_is_hold = hold_out and not want_flat
            if ok_next:
                ord_flat = True
            else:
                gross = side * (c[i] - avg_px) * units
                cost = units * (cost_abs + cost_bp * 1e-4 * avg_px)
                out_entry_bar[ntr] = entry_bar
                out_exit_bar[ntr] = i
                out_units[ntr] = units
                out_pnl[ntr] = gross - cost
                out_reason[ntr] = EX_HOLD if flat_is_hold else EX_FLAT
                out_risk[ntr] = init_risk
                out_sys[ntr] = sys_on
                ntr += 1
                last_win = side * (c[i] - first_fill) > 0.0
                units = 0
                sys_on = 0
                stop_lvl = np.nan
                next_add = np.nan
                tp_lvl = np.nan
                ord_stop = np.nan
                ord_tp = np.nan
                ord_flat = False
                armed_stop_px = np.nan
                continue

        if not ord_flat:
            lvl = stop_lvl
            stop_from_chan = False
            if use_chan_exit:
                ch = x1[i] if sys_on == 1 else x2[i]
                if not np.isnan(ch):
                    if side > 0:
                        if ch > lvl:
                            lvl, stop_from_chan = ch, True
                    else:
                        if ch < lvl:
                            lvl, stop_from_chan = ch, True
            ord_stop = lvl
            ord_tp = tp_lvl

    # A position still open when the data ends is closed at the last close, marked EX_EOD, so no
    # configuration can bank an unrealised gain by never exiting.
    if units > 0:
        px = c[n - 1]
        gross = side * (px - avg_px) * units
        cost = units * (cost_abs + cost_bp * 1e-4 * avg_px)
        out_entry_bar[ntr] = entry_bar
        out_exit_bar[ntr] = n - 1
        out_units[ntr] = units
        out_pnl[ntr] = gross - cost
        out_reason[ntr] = EX_EOD
        out_risk[ntr] = init_risk
        out_sys[ntr] = sys_on
        ntr += 1

    return ntr


# ================================================================= python-side wrapper

def _shift1(x: np.ndarray) -> np.ndarray:
    """`x[1]` in Pine: the value as of the previous bar, NaN at index 0."""
    out = np.empty_like(x)
    out[0] = np.nan
    out[1:] = x[:-1]
    return out


class Series:
    """Bars plus every indicator any configuration might read, memoised by period.

    `window()` returns a Series restricted to a range of New York minutes.  Restricting is not a
    convenience: the search below evaluates each configuration against thousands of matched-control
    draws, and a 07:00-11:00 window is a tenth of a 24-hour instrument's bars.  It is safe because
    every level array is materialised on the FULL series first and only then sliced -- a windowed
    Series has the same channel and ATR readings at every bar it keeps, including the ones that
    depend on overnight bars it does not.
    """

    __slots__ = ("o", "h", "l", "c", "v", "ny_min", "sess", "ts", "n", "name", "tf",
                 "_parent", "_keep", "_cache")

    def __init__(self, o, h, l, c, v, ny_min, sess, ts, name="", tf=0, parent=None, keep=None):
        self.o, self.h, self.l, self.c, self.v = (np.ascontiguousarray(x, dtype=np.float64)
                                                  for x in (o, h, l, c, v))
        self.ny_min = np.ascontiguousarray(ny_min, dtype=np.int64)
        self.sess = np.ascontiguousarray(sess, dtype=np.int64)
        self.ts = np.asarray(ts)
        self.n = len(self.o)
        self.name, self.tf = name, tf
        self._parent, self._keep = parent, keep
        self._cache: dict = {}

    # -- level arrays.  A windowed Series delegates to its parent and slices the result, so a
    #    rolling maximum is never recomputed on a discontiguous slice.
    def _lv(self, key, build):
        if key in self._cache:
            return self._cache[key]
        if self._parent is not None:
            v = np.ascontiguousarray(self._parent._lv(key, build)[self._keep])
        else:
            v = build(self)
        self._cache[key] = v
        return v

    def hi(self, k): return self._lv(("hi", k), lambda s: _highest(s.h, k))
    def lo(self, k): return self._lv(("lo", k), lambda s: _lowest(s.l, k))
    def ehi(self, k): return self._lv(("ehi", k), lambda s: _shift1(_highest(s.h, k)))
    def elo(self, k): return self._lv(("elo", k), lambda s: _shift1(_lowest(s.l, k)))
    def atr(self, k): return self._lv(("atr", k), lambda s: _rma(_true_range(s.h, s.l, s.c), k))
    def adx(self, k=14): return self._lv(("adx", k), lambda s: _dmi(s.h, s.l, s.c, k, k)[2])
    def ema(self, k): return self._lv(("ema", k), lambda s: _ema(s.c, k))

    def window(self, lo_min: int, hi_min: int) -> "Series":
        """Bars whose New York minute-of-day lies in [lo_min, hi_min], as a child Series."""
        if self._parent is not None:
            raise ValueError("window a root Series, not a windowed one")
        keep = (self.ny_min >= lo_min) & (self.ny_min <= hi_min)
        w = Series(self.o[keep], self.h[keep], self.l[keep], self.c[keep], self.v[keep],
                   self.ny_min[keep], self.sess[keep], self.ts[keep],
                   name=self.name, tf=self.tf, parent=self, keep=keep)
        return w

    def slice_sessions(self, lo: int, hi: int) -> "Series":
        """A contiguous run of sessions, keeping the parent's level arrays."""
        m = (self.sess >= lo) & (self.sess < hi)
        root = self if self._parent is None else self._parent
        keep = np.zeros(root.n, bool)
        if self._parent is None:
            keep = m
        else:
            keep[np.flatnonzero(self._keep)[m]] = True
        return Series(root.o[keep], root.h[keep], root.l[keep], root.c[keep], root.v[keep],
                      root.ny_min[keep], root.sess[keep], root.ts[keep],
                      name=root.name, tf=root.tf, parent=root, keep=keep)


@dataclass
class Result:
    entry_bar: np.ndarray
    exit_bar: np.ndarray
    units: np.ndarray
    pnl: np.ndarray          # net, in PRICE units x units (multiply by point value for dollars)
    reason: np.ndarray
    risk: np.ndarray         # atr_mult * N at the first fill -- the R denominator, per unit
    sysno: np.ndarray

    def __len__(self) -> int:
        return len(self.pnl)

    @property
    def r(self) -> np.ndarray:
        """P&L in R multiples: net price P&L divided by (initial per-unit risk x units)."""
        d = self.risk * self.units
        return np.where(d > 0, self.pnl / np.maximum(d, 1e-12), 0.0)


_ZERO = np.zeros(1)
_ZEROI = np.zeros(1, np.int64)


def exit_levels(s: Series, p: P) -> tuple[np.ndarray, np.ndarray]:
    """The trailing-exit channels, lagged by `chan_shift`.

    The supplied Pine reads `chanLo1[1]` -- the channel as of the PREVIOUS bar -- not `chanLo1`.
    Both are causal, and the difference is not cosmetic: including the current bar can only push a
    long's channel low DOWN, so the unlagged version trails looser and gives back more.  The first
    version of this engine used the unlagged form and so, independently, did the reference written
    to check it; the mismatch only surfaced when the emitted Pine was read back against the
    original.  It is a parameter now, defaulting to the shipped script's `[1]`, so which one is
    better is measured rather than assumed.
    """
    if p.side > 0:
        a, b = s.lo(p.exit1), s.lo(p.exit2)
    else:
        a, b = s.hi(p.exit1), s.hi(p.exit2)
    for _ in range(max(0, int(p.chan_shift))):
        a, b = _shift1(a), _shift1(b)
    return a, b


def run(s: Series, p: P, forced: np.ndarray | None = None,
        buf: tuple | None = None) -> Result:
    """Simulate `p` on `s`.  Pass `forced` (0/1/2 per bar) to replace the Donchian signal."""
    e1, e2 = (s.ehi(p.entry1), s.ehi(p.entry2)) if p.side > 0 else \
             (s.elo(p.entry1), s.elo(p.entry2))
    x1, x2 = exit_levels(s, p)
    if buf is None:
        cap = max(1024, s.n // 2 + 16)
        buf = (np.empty(cap, np.int64), np.empty(cap, np.int64), np.empty(cap, np.int64),
               np.empty(cap, np.float64), np.empty(cap, np.int64), np.empty(cap, np.float64),
               np.empty(cap, np.int64))
    eb, xb, un, pl, rs, rk, sy = buf
    ntr = _simulate(
        s.o, s.h, s.l, s.c, s.ny_min, s.sess, s.atr(p.atr_len), e1, e2, x1, x2,
        s.adx(14) if p.adx_max > 0 else _ZERO,
        s.ema(p.ema_len) if p.ext_max > 0 else _ZERO,
        forced if forced is not None else _ZEROI, forced is not None,
        p.atr_mult, p.pyr_step, p.max_units,
        p.skip_win, p.adx_max, p.ext_max, p.break_ticks, p.sess_start, p.sess_end,
        p.flatten_min, p.flat_grace, p.tp_r, p.max_hold, p.use_chan_exit, p.armed_stop,
        p.one_shot, p.side,
        p.cost_abs, p.cost_bp, p.stop_slip, p.tp_rests,
        eb, xb, un, pl, rs, rk, sy)
    return Result(eb[:ntr].copy(), xb[:ntr].copy(), un[:ntr].copy(), pl[:ntr].copy(),
                  rs[:ntr].copy(), rk[:ntr].copy(), sy[:ntr].copy())


def signal_bars(s: Series, p: P) -> np.ndarray:
    """The bars at which the rule would ISSUE an entry order, ignoring whether it is flat.

    The matched control has to match the signal's minute-of-day distribution, and the realised
    trades are the wrong thing to match against: they are already thinned by the no-overlap rule,
    which itself depends on the outcomes.  This returns the unthinned trigger set -- 1 for a
    System 1 break, 2 for a System 2 break, 0 for neither -- evaluated on exactly the same gates.
    """
    if p.side > 0:
        e1, e2 = s.ehi(p.entry1), s.ehi(p.entry2)
        b2 = s.h > e2 + p.break_ticks
        b1 = s.h > e1 + p.break_ticks
    else:
        e1, e2 = s.elo(p.entry1), s.elo(p.entry2)
        b2 = s.l < e2 - p.break_ticks
        b1 = s.l < e1 - p.break_ticks
    a = s.atr(p.atr_len)
    ok = np.isfinite(a) & (a > 0) & (s.ny_min >= p.sess_start) & (s.ny_min < p.sess_end)
    if p.adx_max > 0:
        ok &= np.isfinite(s.adx(14)) & (s.adx(14) < p.adx_max)
    if p.ext_max > 0:
        e = s.ema(p.ema_len)
        with np.errstate(invalid="ignore"):
            ok &= np.isfinite(e) & (p.side * (s.c - e) / a < p.ext_max)
    out = np.zeros(s.n, np.int64)
    out[ok & np.isfinite(e1) & b1] = 1
    out[ok & np.isfinite(e2) & b2] = 2
    return out


__all__ = ["P", "params", "Series", "Result", "run", "replace", "signal_bars",
           "exit_levels",
           "EXIT_NAMES", "EX_STOP", "EX_CHAN", "EX_TP", "EX_FLAT", "EX_HOLD", "EX_EOD",
           "_rma", "_ema", "_dmi", "_highest", "_lowest", "_true_range", "_shift1"]
