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
  **stop** first;
* an opening gap through the stop fills at the **open**, not at the stop;
* costs are charged on both sides and are always adverse.

:func:`verify_against_engine` re-runs a cached result through the real
:class:`~..engine.backtester.Backtester` so the two can be compared. Nothing
here is trusted on the strength of its own arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass

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
                    "avg_bars": 0.0, "max_drawdown": 0.0}
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
            "max_drawdown": float((peak - equity).max()) if count else 0.0,
        }


# ---------------------------------------------------------------------------
# costs
# ---------------------------------------------------------------------------


def round_turn_points(costs: CostModel, instrument, price: np.ndarray,
                      atr: np.ndarray) -> np.ndarray:
    """Total cost of opening and closing one contract, in price points.

    Charged as a single adverse amount rather than modelled tick by tick: the
    question here is whether an edge survives its costs, and for that the total
    is what matters.
    """
    price = np.asarray(price, dtype="float64")
    point = float(getattr(instrument, "point_value", 1.0)) or 1.0
    out = np.zeros_like(price)

    if costs.spread_mode != SpreadMode.NONE:
        out += float(costs.spread_points)

    if costs.slippage_mode == SlippageMode.FIXED_POINTS:
        out += 2.0 * float(costs.slippage_value)
    elif costs.slippage_mode == SlippageMode.PERCENT:
        out += 2.0 * float(costs.slippage_value) / 100.0 * np.abs(price)
    elif costs.slippage_mode == SlippageMode.ATR_FRACTION:
        out += 2.0 * float(costs.slippage_value) * np.nan_to_num(atr)

    commission = 0.0
    if costs.commission_mode == CommissionMode.PER_UNIT:
        commission = 2.0 * float(costs.commission_value)
    elif costs.commission_mode == CommissionMode.PER_TRADE:
        commission = 2.0 * float(costs.commission_value)
    elif costs.commission_mode == CommissionMode.PERCENT_NOTIONAL:
        out += 2.0 * float(costs.commission_value) / 100.0 * np.abs(price)
    if commission:
        out += commission / point
    if costs.min_commission:
        out += 2.0 * float(costs.min_commission) / point
    return out


# ---------------------------------------------------------------------------
# building the cache
# ---------------------------------------------------------------------------


def wilder_atr(bars: BarSeries, period: int) -> np.ndarray:
    """Wilder's ATR -- the one the engine's stops are placed from."""
    from ..engine.backtester import _wilder_atr

    return _wilder_atr(bars, period)


def _first_hit(window: np.ndarray) -> np.ndarray:
    """Index of the first True in each row, or the row width when there is none."""
    width = window.shape[1]
    any_hit = window.any(axis=1)
    first = window.argmax(axis=1)
    return np.where(any_hit, first, width)


def build_outcomes(bars: BarSeries, geometry: Geometry, costs: CostModel,
                   hold_limit: np.ndarray | None = None) -> OutcomeCache:
    """Walk every bar forward and record what a trade opened there would do.

    *hold_limit* optionally caps the hold per signal bar -- that is how "flat at
    the session close" is applied exactly rather than approximately.
    """
    n = len(bars)
    side = 1 if geometry.side >= 0 else -1
    horizon = max(1, int(geometry.max_bars))
    open_, high, low, close = bars.open, bars.high, bars.low, bars.close

    atr = wilder_atr(bars, geometry.atr_period)
    valid = np.zeros(n, dtype=bool)
    net_points = np.zeros(n, dtype="float64")
    exit_reason = np.full(n, EXIT_NONE, dtype="int8")
    bars_held = np.zeros(n, dtype="int32")
    entry_price = np.full(n, np.nan)
    stop_price = np.full(n, np.nan)
    target_price = np.full(n, np.nan)
    risk_points = np.full(n, np.nan)

    minute = _minute_of_day(bars)
    cost = round_turn_points(costs, bars.instrument, close, atr)

    # A signal on bar i fills on bar i+1 and needs `horizon` bars to resolve in.
    last = n - horizon - 1
    if last < 0:
        return OutcomeCache(geometry, valid, net_points,
                            net_points * float(getattr(bars.instrument,
                                                       "point_value", 1.0)),
                            exit_reason, bars_held, entry_price, stop_price,
                            target_price, risk_points, cost, minute)

    idx = np.arange(0, last + 1)
    risk = np.abs(atr[idx]) * float(geometry.stop_atr)
    fill = open_[idx + 1]
    usable = np.isfinite(risk) & (risk > 0) & np.isfinite(fill)

    stop = fill - side * risk
    target = fill + side * risk * float(geometry.target_r)

    limit = np.full(idx.size, horizon, dtype="int32")
    if hold_limit is not None:
        limit = np.minimum(limit, np.asarray(hold_limit[idx], dtype="int32"))
    usable &= limit > 0

    # Sliding windows of the bars a trade may resolve in: row k covers
    # high[k : k + horizon], and the trade signalled at i starts at row i + 1.
    from numpy.lib.stride_tricks import sliding_window_view

    high_win = sliding_window_view(high, horizon)
    low_win = sliding_window_view(low, horizon)

    for start in range(0, idx.size, _CHUNK):
        stop_at = min(start + _CHUNK, idx.size)
        rows = idx[start:stop_at] + 1
        take = usable[start:stop_at]
        if not take.any():
            continue
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

        # Pessimistic: the same bar reaching both is recorded as the stop.
        stopped = (first_stop <= first_target) & (first_stop < cap)
        targeted = (first_target < first_stop) & (first_target < cap)
        timed = ~(stopped | targeted)

        held = np.where(stopped, first_stop,
                        np.where(targeted, first_target, cap - 1))
        exit_index = rows + held

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

        gross = side * (exit_at - fill[start:stop_at])
        net = gross - cost[idx[start:stop_at]]

        sl = slice(start, stop_at)
        valid[idx[sl]] = take
        net_points[idx[sl]] = np.where(take, net, 0.0)
        exit_reason[idx[sl]] = np.where(
            take, np.where(stopped, EXIT_STOP,
                           np.where(targeted, EXIT_TARGET, EXIT_TIME)),
            EXIT_NONE).astype("int8")
        bars_held[idx[sl]] = np.where(take, held, 0).astype("int32")
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


def session_hold_limit(bars: BarSeries, timezone: str, end: str,
                       horizon: int) -> np.ndarray:
    """Bars a trade signalled on each bar may run for before the session closes.

    Returns an array the length of *bars*: a signal on bar ``i`` fills on
    ``i+1`` and must be flat by the last bar of that fill bar's session.
    """
    import pandas as pd

    n = len(bars)
    index = pd.DatetimeIndex(pd.to_datetime(bars.ts, utc=True))
    try:
        local = index.tz_convert(timezone)
    except Exception:                       # pragma: no cover - bad tz name
        local = index
    hour, minute = (int(x) for x in str(end).split(":")[:2])
    end_minutes = hour * 60 + minute
    day = local.strftime("%Y-%m-%d").to_numpy()
    minutes = (local.hour * 60 + local.minute).to_numpy()

    # Last in-session bar of each day, then how far each bar is from it.
    in_session = minutes <= end_minutes
    limit = np.zeros(n, dtype="int32")
    if n == 0:
        return limit
    # Walk backwards: distance to the end of this day's tradeable run.
    last_index = np.zeros(n, dtype="int64")
    current = -1
    current_day = None
    for i in range(n - 1, -1, -1):
        if day[i] != current_day:
            current_day = day[i]
            current = i
        if in_session[i]:
            last_index[i] = current
        else:
            last_index[i] = i
    fill = np.minimum(np.arange(n) + 1, n - 1)
    limit = (last_index[fill] - fill + 1).astype("int32")
    return np.clip(limit, 0, horizon)


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
        # Filled on i+1, exited `held` bars later; the next fill is the bar
        # after that, so the next usable signal bar is one earlier again.
        busy_until = i + int(held[i]) + 1
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
    result = Backtester(bars, spec, config).run()

    fast = cache.summary(select_sequential(cache, mask))
    engine_trades = list(getattr(result, "trades", ()) or ())
    engine_net = float(sum(float(getattr(t, "net_pnl", 0.0)) for t in engine_trades))
    return {
        "fast_trades": float(fast["trades"]), "fast_net": fast["net"],
        "engine_trades": float(len(engine_trades)), "engine_net": engine_net,
        "trade_difference": float(len(engine_trades) - fast["trades"]),
        "net_difference": engine_net - fast["net"],
    }
