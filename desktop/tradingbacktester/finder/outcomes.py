"""What every bar would have been worth, had you entered on it.

Searching thousands of entry rules by running thousands of backtests is the
obvious approach and it is far too slow. The observation that makes the search
affordable is that **a trade's result depends only on the bar it was signalled
on and the geometry it was given** -- not on the rule that produced the signal.
So the forward walk is done once per geometry, for every bar, and cached. After
that a candidate rule is a boolean mask, and evaluating it is a sum.

This is the same simulation the engine performs, written for a different shape
of question, and it makes the same conservative choices:

* a signal on bar *i* fills at the **open of bar i+1** -- never on the bar that
  produced it;
* the stop and target are placed from the ATR at bar *i*, the signal bar, which
  is the last thing known when the order is sent;
* a bar that reaches both the stop and the target is assumed to have hit the
  **stop** first -- unless the bar *opened* through the target and not through
  the stop, which settles the order rather than guessing at it;
* an opening gap through the stop fills at the **open**, not at the stop;
* costs are charged on both sides and are always adverse.

:func:`verify_against_engine` re-runs a cached result through the real
:class:`~..engine.backtester.Backtester` so the two can be compared. Nothing
here is trusted on the strength of its own arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass

from typing import Sequence

import numpy as np

from ..core.types import CommissionMode, CostModel, SlippageMode, SpreadMode
from ..data.models import BarSeries

#: Exit reason codes, as small integers so they can live in an array.
EXIT_STOP = 0
EXIT_TARGET = 1
EXIT_TIME = 2
EXIT_NONE = 3

EXIT_NAMES = {EXIT_STOP: "stop", EXIT_TARGET: "target", EXIT_TIME: "time",
              EXIT_NONE: "none"}

#: Rows scanned at once.  Bounds peak memory at roughly chunk x max_bars bools.
_CHUNK = 32_768


@dataclass
class Geometry:
    """The shape of a trade: how far the barriers are and how long it may run."""

    side: int
    """``+1`` long, ``-1`` short."""
    stop_atr: float
    target_r: float
    max_bars: int
    atr_period: int = 14

    @property
    def label(self) -> str:
        way = "long" if self.side > 0 else "short"
        return f"{way} {self.stop_atr:g}xATR stop, {self.target_r:g}R target"


@dataclass
class OutcomeCache:
    """Per-bar trade outcomes for one instrument, side and geometry.

    Every array is indexed by the **signal** bar. ``valid[i]`` is False where a
    trade could not have been taken at all -- no ATR yet, no next bar to fill
    on, or the session closes before the trade can be given room.
    """

    geometry: Geometry
    valid: np.ndarray
    """bool: a trade signalled on this bar could actually be taken."""
    net_points: np.ndarray
    """Price points won or lost, costs included, signed for the trader."""
    net_cash: np.ndarray
    """The same in account currency, one contract."""
    exit_reason: np.ndarray
    """int8, one of the ``EXIT_*`` codes."""
    bars_held: np.ndarray
    """int32: bars between the fill and the exit, so 0 means it resolved on the
    bar it filled on."""
    entry_price: np.ndarray
    stop_price: np.ndarray
    target_price: np.ndarray
    risk_points: np.ndarray
    """Distance from entry to stop; the R the target is measured in."""
    cost_points: np.ndarray
    """Round-turn cost charged, in price points."""
    minute_of_day: np.ndarray
    """int16: used to build a control that trades at the same times."""

    def __len__(self) -> int:
        return int(self.valid.size)

    def summary(self, mask: np.ndarray | None = None) -> dict[str, float]:
        """Aggregate the trades a boolean *mask* selects."""
        take = self.valid if mask is None else (self.valid & mask)
        count = int(take.sum())
        if count == 0:
            return {"trades": 0, "net": 0.0, "per_trade": 0.0, "win_rate": 0.0,
                    "gross_win": 0.0, "gross_loss": 0.0, "profit_factor": 0.0,
                    "stops": 0.0, "targets": 0.0, "times": 0.0,
                    "avg_bars": 0.0, "median_bars": 0.0, "max_drawdown": 0.0}
        cash = self.net_cash[take]
        wins = cash[cash > 0]
        losses = cash[cash < 0]
        gross_win = float(wins.sum())
        gross_loss = float(-losses.sum())
        equity = np.cumsum(cash)
        peak = np.maximum.accumulate(equity)
        reason = self.exit_reason[take]
        return {
            "trades": count,
            "net": float(cash.sum()),
            "per_trade": float(cash.mean()),
            "win_rate": float((cash > 0).mean()),
            "gross_win": gross_win,
            "gross_loss": gross_loss,
            "profit_factor": (gross_win / gross_loss if gross_loss > 0
                              else float("inf") if gross_win > 0 else 0.0),
            "stops": float((reason == EXIT_STOP).mean()),
            "targets": float((reason == EXIT_TARGET).mean()),
            "times": float((reason == EXIT_TIME).mean()),
            "avg_bars": float(self.bars_held[take].mean()),
            # Hold times are heavily right-skewed -- a mass at zero bars and a
            # tail at the time stop -- so the mean sits well above the typical
            # trade and the report needs both.
            "median_bars": float(np.median(self.bars_held[take])),
            "max_drawdown": float((peak - equity).max()) if count else 0.0,
        }


# ---------------------------------------------------------------------------
# costs
# ---------------------------------------------------------------------------


def spread_halves(costs: CostModel) -> tuple[float, float]:
    """``(entry, exit)`` spread in price points, exactly as the engine splits it.

    This is not a detail that can be rounded off into a single round-turn
    figure. The engine fills the entry at the adverse side of the spread and
    then places the stop and the target *from that price*, so a two-point
    spread moves both barriers by a point. Charging the whole spread at the end
    instead gets the same P&L per trade and a different set of trades.
    """
    spread = float(costs.spread_points)
    if costs.spread_mode == SpreadMode.HALF_EACH_SIDE:
        return spread * 0.5, spread * 0.5
    if costs.spread_mode == SpreadMode.FULL_ON_ENTRY:
        return spread, 0.0
    return 0.0, 0.0


def slippage_points(costs: CostModel, price: np.ndarray,
                    atr: np.ndarray) -> np.ndarray:
    """Slippage charged on one side of a trade, in price points.

    *price* must be the price the fill actually happens at, not the bar's
    close: under ``PERCENT`` the engine charges a fraction of the fill, and on
    a bar that ranges a percent the two differ enough to move the barriers.
    """
    price = np.asarray(price, dtype="float64")
    if costs.slippage_mode == SlippageMode.FIXED_POINTS:
        return np.full(price.shape, float(costs.slippage_value))
    if costs.slippage_mode == SlippageMode.PERCENT:
        return float(costs.slippage_value) / 100.0 * np.abs(price)
    if costs.slippage_mode == SlippageMode.ATR_FRACTION:
        return float(costs.slippage_value) * np.nan_to_num(
            np.broadcast_to(atr, price.shape))
    return np.zeros(price.shape)


def commission_side(costs: CostModel, instrument,
                    price: np.ndarray) -> np.ndarray:
    """Commission for **one** side of a trade at *price*, in price points.

    ``min_commission`` is a per-side **floor**, the way a broker charges a
    minimum ticket -- not an extra charge on top. Adding it instead overstates
    the cost of every trade whenever both figures are set, which makes a real
    edge look unprofitable. And percent-of-notional is charged at the price
    each side actually transacts at, so entry and exit are computed
    separately rather than both from the entry.
    """
    price = np.asarray(price, dtype="float64")
    point = float(getattr(instrument, "point_value", 1.0)) or 1.0
    floor = float(costs.min_commission or 0.0)
    if costs.commission_mode == CommissionMode.PERCENT_NOTIONAL:
        cash = float(costs.commission_value) / 100.0 * np.abs(price) * point
    else:
        cash = np.full(price.shape, float(costs.commission_value))
    return np.maximum(cash, floor) / point


def commission_points(costs: CostModel, instrument,
                      price: np.ndarray) -> np.ndarray:
    """Round-turn commission, both sides transacting at the same price."""
    return 2.0 * commission_side(costs, instrument, price)


def round_turn_points(costs: CostModel, instrument, price: np.ndarray,
                      atr: np.ndarray) -> np.ndarray:
    """Everything one round turn costs, in price points.

    Kept for reporting; the simulation applies the halves separately because
    where a cost is charged changes where the barriers sit.
    """
    entry, exit_ = spread_halves(costs)
    slip = slippage_points(costs, price, atr)
    return (entry + exit_) + 2.0 * slip + commission_points(costs, instrument,
                                                            price)


# ---------------------------------------------------------------------------
# building the cache
# ---------------------------------------------------------------------------


#: Wilder's ATR is a bar-by-bar recursion in Python -- about four tenths of a
#: second on half a million bars -- and a search recomputes the same one for
#: every geometry, every feature and every detector. This is a small bounded
#: cache of the last few (series, period) pairs.
_ATR_CACHE: "dict[tuple[int, int], tuple[BarSeries, np.ndarray]]" = {}
_ATR_CACHE_SIZE = 24


def wilder_atr(bars: BarSeries, period: int) -> np.ndarray:
    """Wilder's ATR -- the one the engine's stops are placed from.

    Memoised per (series, period): the value is a pure function of both, and
    recomputing it two dozen times per search was most of the search. The key
    holds the series itself, so an id reused after a garbage collection cannot
    return another dataset's ATR.
    """
    from ..engine.backtester import _wilder_atr

    period = int(period)
    key = (id(bars), period)
    entry = _ATR_CACHE.get(key)
    if entry is not None and entry[0] is bars:
        return entry[1]

    values = _wilder_atr(bars, period)
    values.setflags(write=False)            # shared, so nobody may mutate it
    if len(_ATR_CACHE) >= _ATR_CACHE_SIZE:
        _ATR_CACHE.pop(next(iter(_ATR_CACHE)), None)
    _ATR_CACHE[key] = (bars, values)
    return values


def hold_bars(max_bars: int) -> int:
    """Bars a trade may occupy under the engine's max-bars time stop.

    The engine closes a position on the first bar where
    ``bar - entry_bar >= max_bars``, and it tests the barriers on that bar
    *before* the time stop. So a trade fills on its entry bar and may still be
    open ``max_bars`` bars later: ``max_bars + 1`` bars in total, every one of
    them a bar the stop and the target are live on.

    Counting ``max_bars`` bars instead is not a rounding error. It closes the
    trade one bar early at the previous close and never tests the last bar at
    all, so a trade the engine resolves at its target is recorded here as a
    time stop at a different price. On 5-minute scalp geometry, where the
    12-bar limit actually binds, that was 66 trades in 2,125 on a single
    candidate.
    """
    return max(1, int(max_bars)) + 1


def _first_hit(window: np.ndarray) -> np.ndarray:
    """Index of the first True in each row, or the row width when there is none."""
    width = window.shape[1]
    any_hit = window.any(axis=1)
    first = window.argmax(axis=1)
    return np.where(any_hit, first, width)


def build_outcomes(bars: BarSeries, geometry: Geometry, costs: CostModel,
                   hold_limit: np.ndarray | None = None,
                   detail: bool = True,
                   eligible: np.ndarray | None = None) -> OutcomeCache:
    """Walk every bar forward and record what a trade opened there would do.

    *hold_limit* optionally caps the hold per signal bar -- that is how "flat at
    the session close" is applied exactly rather than approximately.

    *detail* keeps the per-bar entry, stop, target and risk prices. They are
    only read when checking a result against the engine, and a search builds
    two dozen of these caches: on half a million bars they are two thirds of
    the memory and none of the answer, so the search asks for them off.

    *eligible* restricts the walk to the bars a rule may actually fire on. A
    scalp style trades two hours of a twenty-four-hour instrument, so eleven
    bars in twelve can never be a signal bar and simulating them is work whose
    answer nothing reads. Bars outside it come back ``valid=False``, which is
    what they were destined to be once the session mask met the signal mask --
    the difference is that this way they are never computed.
    """
    n = len(bars)
    side = 1 if geometry.side >= 0 else -1
    horizon = hold_bars(geometry.max_bars)
    open_, high, low, close = bars.open, bars.high, bars.low, bars.close

    atr = wilder_atr(bars, geometry.atr_period)
    valid = np.zeros(n, dtype=bool)
    net_points = np.zeros(n, dtype="float64")
    exit_reason = np.full(n, EXIT_NONE, dtype="int8")
    bars_held = np.zeros(n, dtype="int32")
    empty = np.zeros(0, dtype="float64")
    entry_price = np.full(n, np.nan) if detail else empty
    stop_price = np.full(n, np.nan) if detail else empty
    target_price = np.full(n, np.nan) if detail else empty
    risk_points = np.full(n, np.nan) if detail else empty

    minute = _minute_of_day(bars)
    entry_spread, exit_spread = spread_halves(costs)
    cost = round_turn_points(costs, bars.instrument, close, atr)

    # A signal on bar i fills on bar i+1. The last few bars of the series do
    # not have a full horizon left, but the engine still takes those trades and
    # closes them at the end of the run, so they are simulated the same way:
    # the price arrays are padded with bars no barrier can reach, and the hold
    # is capped at the data that actually exists.
    last = n - 2
    if last < 0:
        return OutcomeCache(geometry, valid, net_points,
                            net_points * float(getattr(bars.instrument,
                                                       "point_value", 1.0)),
                            exit_reason, bars_held, entry_price, stop_price,
                            target_price, risk_points, cost, minute)

    if eligible is None:
        idx = np.arange(0, last + 1)
    else:
        idx = np.flatnonzero(np.asarray(eligible[:last + 1], dtype=bool))
        if idx.size == 0:
            return OutcomeCache(geometry, valid, net_points,
                                net_points * float(getattr(bars.instrument,
                                                           "point_value", 1.0)),
                                exit_reason, bars_held, entry_price,
                                stop_price, target_price, risk_points, cost,
                                minute)
    risk = np.abs(atr[idx]) * float(geometry.stop_atr)
    # The fill is the next open moved against you by the entry half-spread and
    # the entry slippage, and the barriers are measured from THAT price -- as
    # the engine does, because the order is filled before the stop is placed.
    # Percent slippage is a fraction of the price being filled at, so it is
    # taken from the open the order fills on, never from the bar's close.
    entry_slip = slippage_points(costs, open_[idx + 1], atr[idx + 1])
    fill = open_[idx + 1] + side * (entry_spread + entry_slip)
    usable = np.isfinite(risk) & (risk > 0) & np.isfinite(fill)

    stop = fill - side * risk
    target = fill + side * risk * float(geometry.target_r)

    limit = np.full(idx.size, horizon, dtype="int32")
    if hold_limit is not None:
        limit = np.minimum(limit, np.asarray(hold_limit[idx], dtype="int32"))
    remaining = (n - (idx + 1)).astype("int32")
    limit = np.minimum(limit, remaining)
    usable &= limit > 0

    # Sliding windows of the bars a trade may resolve in: row k covers
    # high[k : k + horizon], and the trade signalled at i starts at row i + 1.
    from numpy.lib.stride_tricks import sliding_window_view

    # Padding a long trade's target out of reach (-inf highs) and its stop out
    # of reach (+inf lows) means the padding can never trigger a barrier, for
    # either side, so the tail needs no special case beyond the capped hold.
    pad_high = np.concatenate([high, np.full(horizon, -np.inf)])
    pad_low = np.concatenate([low, np.full(horizon, np.inf)])
    high_win = sliding_window_view(pad_high, horizon)
    low_win = sliding_window_view(pad_low, horizon)

    for start in range(0, idx.size, _CHUNK):
        stop_at = min(start + _CHUNK, idx.size)
        rows = idx[start:stop_at] + 1
        take = usable[start:stop_at]
        if not take.any():
            continue
        # Slice rather than fancy-index whenever the rows are contiguous, which
        # they are when nothing was filtered out. Fancy indexing copies: at
        # 32,768 rows and a 13-bar horizon that is 3.4 MB per array per chunk,
        # built and thrown away for no reason. A slice of a
        # sliding_window_view is a view of the original prices.
        if int(rows[-1]) - int(rows[0]) == rows.size - 1:
            hw = high_win[rows[0]:rows[-1] + 1]
            lw = low_win[rows[0]:rows[-1] + 1]
        else:
            hw = high_win[rows]
            lw = low_win[rows]
        s = stop[start:stop_at][:, None]
        t = target[start:stop_at][:, None]
        if side > 0:
            stop_hit = lw <= s
            target_hit = hw >= t
        else:
            stop_hit = hw >= s
            target_hit = lw <= t
        first_stop = _first_hit(stop_hit)
        first_target = _first_hit(target_hit)
        cap = limit[start:stop_at]

        # One bar reaching both barriers is recorded as the stop -- unless the
        # bar OPENED through the target and not through the stop, in which case
        # there is nothing to guess about: the target was reached at the first
        # price of the bar, before any other price in it. The engine calls that
        # branch "a fact" and only falls back to the pessimistic assumption when
        # the open settles nothing. Without this the fast path books a loss on a
        # trade that was in profit at the open, and on 5-minute bars, where a
        # bar can span both barriers, it happened on 28 of 36 style/geometry
        # combinations -- invisibly, because the trade counts still matched.
        #
        # The comparisons are non-strict to match ``stop_fill_price`` and
        # ``limit_fill_price``, which treat an open exactly ON a barrier as a
        # gap. The fill price is the same either way there; the classification
        # is not.
        tie_bar = np.minimum(rows + first_stop, n - 1)
        open_at_tie = open_[tie_bar]
        s_col = stop[start:stop_at]
        t_col = target[start:stop_at]
        opened_through_stop = side * (open_at_tie - s_col) <= 0
        opened_through_target = side * (open_at_tie - t_col) >= 0
        target_first = ((first_stop == first_target) & opened_through_target
                        & ~opened_through_stop)

        stopped = (first_stop <= first_target) & (first_stop < cap) & ~target_first
        targeted = ((first_target < first_stop) | target_first) & (first_target < cap)
        timed = ~(stopped | targeted)

        held = np.where(stopped, first_stop,
                        np.where(targeted, first_target, cap - 1))
        exit_index = np.minimum(rows + held, n - 1)

        # A gap through the stop fills at the open, which is worse than the
        # stop price -- the single most important honesty in this simulation.
        gap_open = open_[exit_index]
        exit_at = np.where(
            stopped,
            np.where(side * (gap_open - stop[start:stop_at]) < 0, gap_open,
                     stop[start:stop_at]),
            np.where(targeted,
                     np.where(side * (gap_open - target[start:stop_at]) > 0,
                              gap_open, target[start:stop_at]),
                     close[exit_index]))

        # The exit is moved against you by the exit half-spread and slippage;
        # commission is the only cost that is not part of a price.
        exit_slip = slippage_points(costs, exit_at, atr[exit_index])
        exit_fill = exit_at - side * (exit_spread + exit_slip)
        gross = side * (exit_fill - fill[start:stop_at])
        net = gross - (commission_side(costs, bars.instrument,
                                       fill[start:stop_at])
                       + commission_side(costs, bars.instrument, exit_fill))

        sl = slice(start, stop_at)
        valid[idx[sl]] = take
        net_points[idx[sl]] = np.where(take, net, 0.0)
        exit_reason[idx[sl]] = np.where(
            take, np.where(stopped, EXIT_STOP,
                           np.where(targeted, EXIT_TARGET, EXIT_TIME)),
            EXIT_NONE).astype("int8")
        bars_held[idx[sl]] = np.where(take, held, 0).astype("int32")
        if detail:
            entry_price[idx[sl]] = np.where(take, fill[sl], np.nan)
            stop_price[idx[sl]] = np.where(take, stop[sl], np.nan)
            target_price[idx[sl]] = np.where(take, target[sl], np.nan)
            risk_points[idx[sl]] = np.where(take, risk[sl], np.nan)

    point_value = float(getattr(bars.instrument, "point_value", 1.0)) or 1.0
    return OutcomeCache(
        geometry=geometry, valid=valid, net_points=net_points,
        net_cash=net_points * point_value, exit_reason=exit_reason,
        bars_held=bars_held, entry_price=entry_price, stop_price=stop_price,
        target_price=target_price, risk_points=risk_points, cost_points=cost,
        minute_of_day=minute,
    )


def _minute_of_day(bars: BarSeries) -> np.ndarray:
    """Minutes past midnight UTC for each bar, as int16."""
    ts = np.asarray(bars.ts, dtype="int64")
    minutes = (ts // 60_000_000_000) % 1440
    return minutes.astype("int16")


def session_arrays(bars: BarSeries, timezone: str, start: str, end: str,
                   weekdays: Sequence[int] = (0, 1, 2, 3, 4)
                   ) -> tuple[np.ndarray, np.ndarray]:
    """``(in_session, last_of_session)`` from the engine's own session code.

    Reimplementing this was a mistake once already: the engine treats the
    window as ``start <= minute < end``, so on thirty-minute bars the last bar
    of a session ending at 16:00 is the one stamped 15:30, and a rule of
    ``<= end`` lets every trade run one bar longer than the engine does. Rather
    than copy the convention and hope it stays copied, this calls the engine.
    """
    from ..core.types import SessionSettings
    from ..engine.backtester import _SessionArrays

    settings = SessionSettings(enabled=True, start=start, end=end,
                               timezone=timezone, weekdays=tuple(weekdays),
                               flat_at_session_end=True)
    arrays = _SessionArrays.build(bars.ts, settings, timezone)
    return (np.asarray(arrays.in_session, dtype=bool),
            np.asarray(arrays.session_last, dtype=bool))


def session_hold_limit(bars: BarSeries, timezone: str, start: str, end: str,
                       horizon: int, weekdays: Sequence[int] = (0, 1, 2, 3, 4)
                       ) -> np.ndarray:
    """How long a trade signalled on each bar may run before the session closes.

    Returns an array the length of *bars*: a signal on bar ``i`` fills on
    ``i+1`` and must be flat by the last in-session bar of that fill bar's
    session. Getting this wrong is not a rounding error -- an index CFD trades
    almost around the clock, so an extra hour of licence here lets a trade the
    engine shuts at the New York close run into the evening.
    """
    n = len(bars)
    if n == 0:
        return np.zeros(0, dtype="int32")
    in_session, last_of_session = session_arrays(bars, timezone, start, end,
                                                 weekdays)

    # For each bar, the index of the next session close at or after it.
    closes = np.flatnonzero(last_of_session)
    room = np.zeros(n, dtype="int32")
    if closes.size:
        position = np.searchsorted(closes, np.arange(n), side="left")
        valid = position < closes.size
        next_close = np.where(valid, closes[np.minimum(position,
                                                       closes.size - 1)], n - 1)
        fill = np.minimum(np.arange(n) + 1, n - 1)
        next_close_at_fill = next_close[fill]
        room = (next_close_at_fill - fill + 1).astype("int32")
        room[~in_session[fill]] = 0
        room[~valid[fill]] = 0
    # Capped at what a trade may occupy, not at ``horizon`` itself: the engine
    # holds a position for ``max_bars`` bars *after* the one it filled on.
    return np.clip(room, 0, hold_bars(horizon))


def block_hold_limit(n: int, split: int, horizon: int) -> np.ndarray:
    """How long a trade may run before it hits the end of its own block.

    A search splits the series in two and scores each block separately. Without
    this, a trade signalled a few bars before the split runs on into the locked
    block and its full result is counted in the RESEARCH figure -- so the
    number the search ranks on is partly determined by data the search is not
    allowed to see. It is one trade per block, and on a swing candidate it was
    worth $478 of a $4,297 research result: 11% of the per-trade figure, on a
    candidate whose rank it could move.

    It also made the two layers disagree. The engine, handed the research block
    as a standalone series, closes that position at the block's last close --
    which is the right answer -- and the finder then reported "the engine did
    not reproduce the figure the search ranked on" against a candidate that was
    perfectly sound.

    Capping here rather than at scoring time means one cache still serves both
    blocks, and every consumer of it -- the summary, the matched control, the
    neighbourhood -- gets the corrected outcome without knowing there was ever
    a question.
    """
    n = max(0, int(n))
    fill = np.arange(n, dtype="int64") + 1
    split = max(0, min(int(split), n))
    boundary = np.where(fill < split, split, n)
    room = np.maximum(0, boundary - fill).astype("int32")
    return np.clip(room, 0, hold_bars(horizon))


def session_entry_mask(bars: BarSeries, timezone: str, start: str | None,
                       end: str | None,
                       weekdays: Sequence[int] = (0, 1, 2, 3, 4),
                       flat_at_session_end: bool = True) -> np.ndarray:
    """Bars a rule is allowed to fire on.

    The engine gates on the **signal** bar, not the fill bar: it evaluates
    rules only while the session is open, and an order raised on the last bar
    of the session still fills at the next open. Gating on the fill bar instead
    -- which looks equally reasonable -- silently adds a trade at 09:30 every
    time a rule fires on the 09:00 bar, and the engine takes none of them.

    With *flat_at_session_end* the engine also refuses the **last** in-session
    bar, because a position opened there would be closed at that same bar's
    close. On data that carries only session bars, allowing it produces a
    phantom trade held overnight in a style whose premise is that nothing is.
    """
    n = len(bars)
    if n == 0:
        return np.zeros(0, dtype=bool)
    if start is None or end is None:
        ok = np.ones(n, dtype=bool)
        if weekdays is not None and len(weekdays) < 7:
            import pandas as pd

            local = pd.DatetimeIndex(pd.to_datetime(bars.ts, utc=True))
            try:
                local = local.tz_convert(timezone)
            except Exception:               # pragma: no cover - bad tz name
                pass
            ok &= np.isin(local.dayofweek.to_numpy(), list(weekdays))
    else:
        ok, last = session_arrays(bars, timezone, start, end, weekdays)
        ok = np.asarray(ok, dtype=bool).copy()
        if flat_at_session_end:
            ok &= ~np.asarray(last, dtype=bool)
    # The last bar has no bar after it to fill on.
    ok = np.asarray(ok, dtype=bool).copy()
    ok[-1] = False
    return ok


def _minutes(text: str) -> int:
    hour, minute = (int(x) for x in str(text).split(":")[:2])
    return hour * 60 + minute


def select_sequential(cache: OutcomeCache, mask: np.ndarray) -> np.ndarray:
    """Thin a signal mask down to the trades that could actually be taken.

    One contract, one position: a signal that arrives while an earlier trade is
    still running is not a trade, it is a missed opportunity. Counting it would
    inflate every result -- often several-fold on a rule that fires in clusters
    -- and would not match what the engine does with the same rule.
    """
    take = np.asarray(mask, dtype=bool) & cache.valid
    signals = np.flatnonzero(take)
    if signals.size == 0:
        return np.zeros_like(take)
    held = cache.bars_held
    kept = np.zeros(take.size, dtype=bool)
    busy_until = -1
    for i in signals:
        if i <= busy_until:
            continue
        kept[i] = True
        # Filled on i+1 and out on bar i+1+held. The engine evaluates rules at
        # the close of every bar, including the one a position closed on, so
        # the exit bar itself can raise the next signal -- which fills the bar
        # after. Anything earlier would overlap.
        busy_until = i + int(held[i])
    return kept


def verify_against_engine(bars: BarSeries, cache: OutcomeCache,
                          mask: np.ndarray, spec) -> dict[str, float]:
    """Run *spec* through the real engine and report both sets of numbers.

    The fast path exists because it is fast, not because it is authoritative.
    This is how a result from it is checked: same bars, same geometry, same
    signals, and the difference reported rather than assumed away.
    """
    from ..core.types import BacktestConfig
    from ..engine.backtester import Backtester

    config = BacktestConfig(starting_capital=100_000.0)
    config.exits = spec.exits
    config.execution = spec.execution
    config.session = spec.session
    config.costs = spec.costs
    config.risk = spec.risk
    config.warmup_bars = spec.warmup_bars()
    result = Backtester(bars, spec, config).run()

    kept = select_sequential(cache, mask)
    fast = cache.summary(kept)
    trades = list(getattr(result, "trades", ()) or ())
    engine_net = float(sum(float(t.net_pnl) for t in trades))

    # Which trades the two agree on, matched by the bar the position opened.
    fast_fills = set((np.flatnonzero(kept) + 1).tolist())
    engine_fills = {int(t.entry_bar) for t in trades}
    by_bar = {int(t.entry_bar): t for t in trades}
    worst = 0.0
    for i in np.flatnonzero(kept):
        trade = by_bar.get(int(i) + 1)
        if trade is not None:
            worst = max(worst, abs(float(cache.net_cash[i]) - float(trade.net_pnl)))

    return {
        "fast_trades": float(fast["trades"]), "fast_net": fast["net"],
        "engine_trades": float(len(trades)), "engine_net": engine_net,
        "shared_trades": float(len(fast_fills & engine_fills)),
        "fast_only": float(len(fast_fills - engine_fills)),
        "engine_only": float(len(engine_fills - fast_fills)),
        "worst_matched_difference": worst,
        "trade_difference": float(len(trades) - fast["trades"]),
        "net_difference": engine_net - fast["net"],
    }
