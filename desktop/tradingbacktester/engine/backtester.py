"""The bar-by-bar simulation loop.

THE SIMULATION RULES
====================

These are the rules the engine actually implements.  They are written down here
because every one of them is a place where a backtest can be made to look better
than the strategy is, and a reader is entitled to know which way each choice was
made.

1. **Rules see only the past.**  Every condition is evaluated on the *close* of
   bar ``i`` using data from bars ``0..i`` only.  The compiler guarantees the
   indicator arrays have that property; the loop never reads an index above the
   bar it is on.

2. **Signals execute on the next bar.**  Under
   :attr:`~tradingbacktester.core.types.SignalExecution.NEXT_OPEN` -- the
   default, and the only setting that is free of look-ahead -- the market order
   raised by bar ``i`` fills at the **open of bar ``i+1``**.
   :attr:`~tradingbacktester.core.types.SignalExecution.THIS_CLOSE` fills at the
   close of bar ``i`` instead.  That is **optimistic**: it assumes you
   transacted at a price that was only known once the bar was over.  It is
   offered because some vendors report results that way, and it is labelled
   optimistic everywhere it appears.

3. **Protective exits are live on the entry bar.**  A stop, target or trailing
   stop is checked on every bar from the entry bar onwards.  Strictly, only the
   part of the entry bar that comes *after* the fill can hit a barrier, and bar
   data cannot resolve that -- so on the entry bar the whole bar range is
   tested, under the same :class:`~tradingbacktester.core.types.IntrabarPriority`
   rule as any other bar.  This is deliberately the conservative choice: with
   the default ``PESSIMISTIC`` priority a trade whose entry bar contains both
   barriers is recorded as a loser.  Under ``NEXT_OPEN`` the entry is at that
   bar's open, so almost the whole range genuinely is after the fill.  Under
   ``THIS_CLOSE`` the fill is at the bar's close and there is no range left
   after it, so protection starts on the following bar.

4. **Gaps fill at the open.**  If a bar *opens* beyond a stop or a target, the
   fill is the open, not the barrier price.  This is the difference between an
   honest backtest and a flattering one: it is exactly the trades that gap
   through a stop that do the damage in a real account.

5. **Two barriers in one bar** are resolved by ``IntrabarPriority``:
   ``PESSIMISTIC`` gives it to the stop, ``OPTIMISTIC`` to the target, and
   ``OHLC_PATH`` assumes ``open -> high -> low -> close`` when the bar closed up
   and ``open -> low -> high -> close`` when it closed down, taking whichever
   barrier that path reaches first.  A barrier the bar *opened* through is not
   ambiguous and is applied first whatever the setting says.

6. **Trailing stops are tested before they are moved.**  On each bar the
   existing stop is checked against the range first, and only then is the trail
   anchor updated from that bar's extreme.  Updating first would let a bar that
   stopped you out also move the stop -- look-ahead that turns losers into
   winners.

7. **Limit orders** fill only when the bar trades through the limit by at least
   ``ExecutionSettings.limit_requires_through`` points, or at the open when the
   bar gapped past in the trader's favour.  Take-profit and partial targets are
   limit orders.

8. **Stop orders** fill at the stop price, or at the open when the bar gapped
   past it.

9. **Costs** are spread (per ``SpreadMode``), slippage (per ``SlippageMode``;
   ``ATR_FRACTION`` uses the ATR of the bar the fill happens on) and commission
   (per ``CommissionMode``, with ``min_commission`` as a per-side floor).  All
   of them are adverse and all are charged on both sides where the mode says so.
   Barrier *geometry* is different and uses the **signal** bar's ATR -- see
   :mod:`tradingbacktester.engine.broker`.

10. **Sessions.**  With ``SessionSettings.enabled``, entries are taken only on
    tradeable bars, and with ``flat_at_session_end`` any open position is closed
    at the close of the last in-session bar of the day
    (:attr:`~tradingbacktester.core.types.ExitReason.SESSION_END`).  Which bar
    is last is read from the session schedule, which is calendar knowledge and
    not market information.

11. **Daily loss limit.**  When the day's realised plus unrealised loss breaches
    ``max_daily_loss``, the position is closed
    (:attr:`~tradingbacktester.core.types.ExitReason.DAILY_LOSS_LIMIT`) and no
    further entry is taken that session day.  The check is made on each bar's
    close, because a bar-level backtest cannot honestly claim to know the
    account's low-water mark inside a bar.

12. **Margin.**  When ``use_margin`` is on, an entry whose initial margin
    exceeds free equity is rejected, counted in ``result.rejected_orders`` and
    logged with the reason.  Equity at or below maintenance margin -- taken as
    50% of initial margin, a documented stand-in for a venue-specific number --
    liquidates everything
    (:attr:`~tradingbacktester.core.types.ExitReason.MARGIN_CALL`).

13. **Partial exits.**  ``ExitSettings.partial_exits`` is
    ``((fraction, r_multiple), ...)``.  Each rung fires once, when the trade
    reaches that R in its favour; it emits its own
    :class:`~tradingbacktester.core.types.Trade` row with ``parent_id`` pointing
    at the position's final row and
    :attr:`~tradingbacktester.core.types.ExitReason.PARTIAL_TARGET`, reduces the
    position, and leaves the remainder running.

14. **Reversal.**  With ``allow_reversal``, an opposite entry signal while in a
    position closes it
    (:attr:`~tradingbacktester.core.types.ExitReason.REVERSAL`) and opens the
    new one on the same fill bar.  With reversal off but
    ``close_on_opposite_signal`` on, it closes and stays flat.

15. **End of data.**  Every position still open on the last bar is closed at
    that bar's close
    (:attr:`~tradingbacktester.core.types.ExitReason.END_OF_DATA`), so the
    equity curve ends at a real number and open risk is never counted as profit.

16. **MAE/MFE** are tracked in price points from the entry price, using each
    bar's high and low across the whole holding period, entry bar included.

17. **R multiple** is ``net_pnl / (abs(entry - initial_stop) * qty *
    point_value)`` -- the cash that was genuinely at risk when the position was
    opened -- and is ``None`` when the trade had no stop.

Configuration precedence
------------------------
A run is configured by :class:`~tradingbacktester.core.types.BacktestConfig`.
A :class:`~tradingbacktester.strategy.spec.StrategySpec` also carries its own
risk, cost, exit, session and execution blocks, because a strategy that says
"stop 1.5 x ATR" means it.  The rule is: **the config wins**, except that a
config block left exactly at its dataclass default is treated as "not
specified" and the strategy's own block is used instead, with a note in
``result.warnings``.  That makes ``Backtester(bars, spec, BacktestConfig())``
run the strategy as written, while the UI -- which always builds a fully
populated config from its panels -- always gets what the panels say.
"""

from __future__ import annotations

import copy
import logging
import time
import uuid
from array import array
from datetime import datetime, timezone
from typing import Any, Callable, Sequence

import numpy as np

from ..core.errors import (BacktestError, BacktesterError, CancelledError,
                           DataError, InsufficientDataError)
from ..core.types import (BacktestConfig, CostModel, ExecutionSettings,
                          ExitReason, ExitSettings, RiskSettings,
                          SessionSettings, Side, SignalExecution)
from ..data.models import BarSeries
from .broker import SimulatedBroker
from .execution import CostCalculator
from .results import BacktestResult, EquityCurves
from .risk import PositionSizer

logger = logging.getLogger(__name__)

__all__ = ["Backtester"]

#: Upper bound on how many bars may pass between progress reports.  Checking
#: every bar would cost more than the simulation itself.
_PROGRESS_EVERY_MAX = 4096

#: Roughly how many progress reports a run should produce.  The interval is
#: derived from the bar count so that a 4,000-bar run still moves its progress
#: bar and still answers the Cancel button, which a fixed 4,096-bar interval
#: would not: it would poll exactly once, at bar zero.
_PROGRESS_REPORTS = 200


def _progress_interval(n: int) -> int:
    """Bars between progress/cancellation checks for a run of ``n`` bars."""
    if n <= 0:
        return 1
    return max(1, min(_PROGRESS_EVERY_MAX, n // _PROGRESS_REPORTS or 1))

# Pending-operation opcodes.  Small ints rather than objects: this is the hot
# path and a tuple of ints allocates far less than a class per signal.
_OP_EXIT = 0
_OP_ENTRY = 1
_OP_REVERSE = 2


def _touch_only_warning(broker: Any) -> list[str]:
    """Say how much of this run rests on the one optimistic fill assumption.

    Everything else in this engine defaults pessimistic. Limit fills do not:
    with `limit_requires_through` at its default of zero, a target fills the
    moment the bar's range reaches it, and the assumptions document concedes
    that on a level that trades once and leaves you probably did not get
    filled. Reporting the count is better than changing the default silently
    and better than saying nothing -- it turns a paragraph of prose into a
    number about THIS run.
    """
    touched = int(getattr(broker, "_touch_only_fills", 0) or 0)
    total = int(getattr(broker, "_limit_fills", 0) or 0)
    if not touched:
        return []
    share = touched / total if total else 0.0
    return [
        f"{touched:,} of {total:,} limit fills ({share:.0%}) happened on a "
        f"single touch — the bar reached the level but never traded a tick "
        f"past it, so the fill assumes nobody was ahead of you in the queue. "
        f"That share is NOT how much of the result depends on it. A target "
        f"that does not fill leaves the position open to run to its stop, so "
        f"one touch-only fill is worth a win PLUS the loss that replaces it. "
        f"Measured on a 73-trade sample: one such fill in 28 turned a "
        f"+1,773 winner into a -2,590 loser and moved the net by half, with "
        f"the other 72 trades unchanged. Set "
        f"Execution ▸ 'limit needs to trade through' to a tick and re-run to "
        f"see what this strategy is actually worth without them."]


class Backtester:
    """Runs one strategy over one bar series and returns a
    :class:`~tradingbacktester.engine.results.BacktestResult`.

    Parameters
    ----------
    bars:
        The data to simulate.  Indicators are compiled over the **whole**
        series so that a date-restricted run still has its warm-up history; only
        the selected range is simulated.
    spec:
        The strategy definition.
    config:
        Run configuration.  See *Configuration precedence* in the module
        docstring.
    progress:
        Called as ``progress(bar, total)`` a few hundred times per run.
    cancel:
        Polled at the same cadence; returning True raises
        :class:`~tradingbacktester.core.errors.CancelledError`.
    param_overrides:
        Strategy parameter values to use instead of the defaults -- this is what
        the optimiser sweeps.
    """

    def __init__(self, bars: BarSeries, spec: Any,
                 config: BacktestConfig | None = None,
                 progress: Callable[[int, int], None] | None = None,
                 cancel: Callable[[], bool] | None = None,
                 param_overrides: dict[str, Any] | None = None,
                 label: str = "") -> None:
        self.bars = bars
        self.spec = spec
        self.config = config if config is not None else BacktestConfig()
        self.progress = progress
        self.cancel = cancel
        self.param_overrides = dict(param_overrides or {})
        self.label = label
        self.warnings: list[str] = []


    #: Non-finite OHLC values above this share of the series make the run a
    #: description of the gaps rather than of the strategy.
    _BAD_PRICE_LIMIT = 0.02

    def _check_bars(self, bars: BarSeries) -> None:
        """Refuse a series that breaks BarSeries' own contract; warn on the rest.

        The engine walks bars in order and carries state between them, so a
        timestamp that repeats or goes backwards does not make the answer
        slightly wrong -- it makes it meaningless. Until now nothing checked:
        a hand-built series with a duplicated or swapped timestamp ran to
        completion and reported trades, and a NaN close quietly took a
        fifteen-trade run down to six with no warning anywhere. The importer
        repairs all of this, so the exposure is programmatic callers, which is
        exactly where nobody is watching the screen.

        Timestamps raise. Prices warn, because a gap is a fact about the data
        rather than a defect in it, and the engine already declines to trade a
        bar it cannot price.
        """
        ts = np.asarray(bars.ts, dtype="int64")
        if ts.size > 1:
            steps = np.diff(ts)
            duplicates = int((steps == 0).sum())
            backwards = int((steps < 0).sum())
            if duplicates or backwards:
                first = int(np.argmax(steps <= 0)) + 1
                raise DataError(
                    f"The bars are not in strictly ascending time order, which "
                    f"the simulation depends on: "
                    f"{duplicates:,} repeated and {backwards:,} out-of-order "
                    f"timestamps, the first at bar {first:,}. Re-import the "
                    f"file, or repair the series with "
                    f"tradingbacktester.data.validation.clean_bars.",
                    detail=f"bar {first}: {ts[first - 1]} then {ts[first]}")

        bad = np.zeros(len(bars), dtype=bool)
        for name in ("open", "high", "low", "close"):
            values = np.asarray(getattr(bars, name), dtype="float64")
            bad |= ~np.isfinite(values)
        count = int(bad.sum())
        if count:
            share = count / len(bars)
            self.warnings.append(
                f"{count:,} of {len(bars):,} bars ({share:.1%}) carry a price "
                f"that is not a number. Those bars cannot be traded and cannot "
                f"raise a signal, so this run covers less of the period than "
                f"its dates suggest."
                + ("  That is most of the series; treat the result as a "
                   "description of the gaps rather than of the strategy."
                   if share > self._BAD_PRICE_LIMIT else ""))

    # ------------------------------------------------------------------
    # entry point
    # ------------------------------------------------------------------

    def run(self) -> BacktestResult:
        """Simulate the strategy and return the finished result."""
        started = time.perf_counter()
        bars = self.bars
        if bars is None or len(bars) == 0:
            raise InsufficientDataError("There are no bars to run the backtest on.")

        self._check_bars(bars)
        spec_warnings = self._validate_spec()
        config = self._effective_config()
        compiled = self._compile(config)

        lo, hi = self._run_range(config)
        n = hi - lo
        if n < 2:
            raise InsufficientDataError(
                "The selected date range contains fewer than two bars, which is "
                "not enough to simulate a trade.",
                detail=f"start={config.start_ts} end={config.end_ts} bars={n}")

        run_bars = bars if (lo == 0 and hi == len(bars)) else bars.slice(lo, hi)
        atr = self._resolve_atr(compiled, bars, config.exits.atr_period)[lo:hi]

        broker = SimulatedBroker(
            bars.instrument, config, atr,
            costs=CostCalculator(config.costs, bars.instrument),
            sizer=PositionSizer(
                config.risk, bars.instrument,
                atr_stop_multiple=(config.exits.stop_loss_value
                                   if config.exits.stop_loss_enabled
                                   and config.exits.stop_loss_mode == "atr" else 2.0)),
        )

        signals = self._signal_arrays(compiled, lo, hi)
        session = _SessionArrays.build(run_bars.ts, config.session,
                                       bars.instrument.timezone)
        if config.session.enabled:
            # The compiler builds ``tradeable`` from the strategy's own session
            # block; the run configuration is what actually governs the run, so
            # the two are combined here and the combined mask is what the result
            # reports.
            mask = np.asarray(session.in_session, dtype=bool)
            if config.session.flat_at_session_end:
                # An entry on the last bar of the session would be closed at that
                # same bar's close, so it is not offered at all.
                mask = mask & ~np.asarray(session.session_last, dtype=bool)
            signals["tradeable"] = signals["tradeable"] & mask
        start_bar = self._first_tradeable_bar(compiled, config, lo, n)
        if start_bar >= n - 1:
            self.warnings.append(
                "The indicators need more warm-up bars than the selected range "
                "contains, so no trade could be taken.")

        equity, balance, exposure = self._simulate(
            broker, run_bars, signals, session, atr, start_bar, config)

        result = self._build_result(run_bars, compiled, config, broker, signals,
                                    equity, balance, exposure, lo, hi)
        result.warnings = (spec_warnings + self.warnings + broker.warnings
                           + _touch_only_warning(broker))
        result.duration_seconds = time.perf_counter() - started
        result.metrics = self._metrics(result)
        logger.info("Backtest finished: %s", result.summary_line())
        return result

    # ------------------------------------------------------------------
    # set-up
    # ------------------------------------------------------------------

    def _validate_spec(self) -> list[str]:
        try:
            return list(self.spec.validate())
        except BacktesterError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            raise BacktestError(
                "This strategy could not be checked before running.",
                detail=f"{type(exc).__name__}: {exc}") from exc

    def _effective_config(self) -> BacktestConfig:
        """Merge the strategy's own settings into the run configuration.

        See *Configuration precedence* in the module docstring.  The caller's
        object is never mutated: the UI reuses one config across runs and would
        otherwise find the strategy's settings baked into its panels.
        """
        config = copy.deepcopy(self.config)
        defaults = BacktestConfig()
        adopted: list[str] = []
        blocks = (("risk", RiskSettings), ("costs", CostModel),
                  ("session", SessionSettings), ("exits", ExitSettings),
                  ("execution", ExecutionSettings))
        for name, _cls in blocks:
            mine = getattr(config, name)
            theirs = getattr(self.spec, name, None)
            if theirs is None:
                continue
            if mine == getattr(defaults, name) and theirs != getattr(defaults, name):
                setattr(config, name, copy.deepcopy(theirs))
                adopted.append(name)

        if "risk" in adopted:
            spec_capital = float(getattr(self.spec.risk, "starting_capital", 0.0))
            if (config.starting_capital == defaults.starting_capital
                    and spec_capital > 0.0):
                config.starting_capital = spec_capital
        # ``validate`` re-syncs risk.starting_capital with the config's value.
        if adopted:
            self.warnings.append(
                "The " + ", ".join(adopted) + " settings were taken from the "
                "strategy because the run configuration left them at their "
                "defaults.")
        try:
            config.validate()
        except BacktesterError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            raise BacktestError("The backtest settings are not valid.",
                                detail=f"{type(exc).__name__}: {exc}") from exc
        return config

    def _compile(self, config: BacktestConfig) -> Any:
        """Compile the strategy over the whole series.

        Imported here rather than at module scope so that a circular import in
        the strategy layer cannot stop the engine module from loading.
        """
        from ..strategy.compiler import compile_strategy

        try:
            compiled = compile_strategy(self.spec, self.bars, self.param_overrides)
        except BacktesterError:
            raise
        except Exception as exc:
            raise BacktestError(
                "This strategy could not be prepared for the backtest.",
                detail=f"{type(exc).__name__}: {exc}") from exc
        n = len(self.bars)
        for name in ("entry_long", "entry_short", "exit_long", "exit_short",
                     "tradeable"):
            arr = getattr(compiled, name, None)
            if arr is None:
                continue
            if len(arr) != n:
                raise BacktestError(
                    "The strategy compiler produced signals that do not line up "
                    "with the data.",
                    detail=f"{name}: {len(arr)} values for {n} bars")
        return compiled

    def _run_range(self, config: BacktestConfig) -> tuple[int, int]:
        """Bar index bounds ``[lo, hi)`` for the configured date range."""
        ts = self.bars.ts
        lo = 0 if config.start_ts is None else int(
            np.searchsorted(ts, config.start_ts, side="left"))
        hi = len(ts) if config.end_ts is None else int(
            np.searchsorted(ts, config.end_ts, side="right"))
        if hi <= lo:
            raise InsufficientDataError(
                "The selected date range contains no bars.",
                detail=f"start_ts={config.start_ts} end_ts={config.end_ts}")
        return lo, hi

    def _resolve_atr(self, compiled: Any, bars: BarSeries, period: int) -> np.ndarray:
        """The ATR series used for stops, targets, sizing and ATR slippage.

        The compiled strategy already carries an ATR at the *strategy's* period.
        When the run configuration asks for a different period the array is
        recomputed, because a stop advertised as "1.5 x ATR(20)" must not
        quietly be 1.5 x ATR(14).
        """
        period = int(period)
        spec_period = int(getattr(getattr(self.spec, "exits", None), "atr_period",
                                  period))
        candidate = getattr(compiled, "atr", None)
        if candidate is not None and spec_period == period:
            arr = np.asarray(candidate, dtype="float64")
            if len(arr) == len(bars):
                return arr
        try:
            from ..indicators.registry import REGISTRY

            return REGISTRY.compute("ATR", bars, {"period": period})["value"]
        except BacktesterError as exc:
            logger.info("Falling back to the built-in ATR: %s", exc)
        except Exception as exc:  # pragma: no cover - defensive
            logger.info("Falling back to the built-in ATR: %r", exc)
        return _wilder_atr(bars, period)

    def _signal_arrays(self, compiled: Any, lo: int, hi: int) -> dict[str, np.ndarray]:
        """The four rule arrays plus the tradeable mask, sliced to the run range."""
        n = hi - lo
        out: dict[str, np.ndarray] = {}
        for name in ("entry_long", "entry_short", "exit_long", "exit_short"):
            arr = getattr(compiled, name, None)
            if arr is None:
                out[name] = np.zeros(n, dtype=bool)
            else:
                out[name] = np.asarray(arr, dtype=bool)[lo:hi]
        tradeable = getattr(compiled, "tradeable", None)
        out["tradeable"] = (np.ones(n, dtype=bool) if tradeable is None
                            else np.asarray(tradeable, dtype=bool)[lo:hi])
        return out

    def _first_tradeable_bar(self, compiled: Any, config: BacktestConfig,
                             lo: int, n: int) -> int:
        """First bar of the run window that may raise a signal.

        Bar 0 of the window is excluded: under ``NEXT_OPEN`` an entry needs a
        signal bar *before* it, and the bar before the window is outside the
        simulation.
        """
        warmup = int(getattr(compiled, "warmup", 0) or 0)
        need = max(warmup - lo, int(config.warmup_bars), 1)
        return max(1, min(need, n))

    # ------------------------------------------------------------------
    # the loop
    # ------------------------------------------------------------------

    def _simulate(self, broker: SimulatedBroker, bars: BarSeries,
                  signals: dict[str, np.ndarray], session: "_SessionArrays",
                  atr: np.ndarray, start_bar: int,
                  config: BacktestConfig) -> tuple[list[float], list[float],
                                                   list[float]]:
        """The bar loop.

        Genuinely sequential -- every bar depends on the account state the
        previous bar left behind -- so it is a Python loop, written to keep the
        common case (flat, no signal) down to a handful of list indexings.  The
        price columns are copied into ``array('d')`` buffers because indexing
        one returns a native float roughly three times faster than indexing a
        NumPy array, without the memory cost of a list of boxed floats.
        """
        n = len(bars)
        OP = array("d", bars.open)
        HI = array("d", bars.high)
        LO = array("d", bars.low)
        CL = array("d", bars.close)
        TS = bars.ts
        ATR = array("d", atr)

        EL = signals["entry_long"].tolist()
        ES = signals["entry_short"].tolist()
        XL = signals["exit_long"].tolist()
        XS = signals["exit_short"].tolist()
        TR = signals["tradeable"].tolist()

        day_key = session.day_key
        session_last = session.session_last

        execu = config.execution
        risk = config.risk
        this_close = execu.signal_execution is SignalExecution.THIS_CLOSE
        allow_long = bool(risk.allow_long)
        allow_short = bool(risk.allow_short)
        allow_reversal = bool(execu.allow_reversal)
        close_on_opposite = bool(execu.close_on_opposite_signal)
        max_positions = max(1, int(risk.max_concurrent_positions))
        session_flat = bool(config.session.enabled and config.session.flat_at_session_end)
        use_margin = bool(risk.use_margin)
        trailing = bool(config.exits.trailing_enabled)

        daily_limit_pct = bool(risk.max_daily_loss_is_percent)
        daily_limit_raw = float(risk.max_daily_loss)
        daily_limit_on = daily_limit_raw > 0.0

        positions = broker.positions            # mutated in place by the broker
        manage_bar = broker.manage_bar
        set_bar_atr = broker.set_bar_atr
        equity_of = broker.equity
        flatten = broker.flatten
        progress = self.progress
        cancel = self.cancel

        equity_curve: list[float] = []
        balance_curve: list[float] = []
        exposure_curve: list[float] = []
        eq_append = equity_curve.append
        bal_append = balance_curve.append
        exp_append = exposure_curve.append

        report_every = _progress_interval(n)
        pending: list[tuple] | None = None
        blocked_day = -1
        current_day = day_key[0] if n else -1
        day_start_equity = broker.cash
        ambiguous = 0

        for i in range(n):
            o = OP[i]
            c = CL[i]

            if i % report_every == 0:
                if cancel is not None and cancel():
                    raise CancelledError("The backtest was cancelled.")
                if progress is not None:
                    progress(i, n)

            # -- day roll ------------------------------------------------
            dk = day_key[i]
            if dk != current_day:
                current_day = dk
                day_start_equity = equity_of(o) if positions else broker.cash

            # -- 1. orders raised on the previous bar fill at this open ---
            if pending is not None:
                self._run_ops(broker, pending, i, TS[i], o)
                pending = None

            # -- 2. protective exits over this bar's range ----------------
            if positions:
                if trailing:
                    set_bar_atr(ATR[i])
                manage_bar(i, TS[i], o, HI[i], LO[i], c)

            # -- 3. close-of-bar account rules ---------------------------
            if positions and session_flat and session_last[i]:
                flatten(i, TS[i], c, ExitReason.SESSION_END)
            if positions and use_margin:
                broker.check_margin_call(i, TS[i], c)

            eq = equity_of(c) if positions else broker.cash

            if daily_limit_on:
                limit = (day_start_equity * daily_limit_raw / 100.0 if daily_limit_pct
                         else daily_limit_raw)
                if limit > 0.0 and (eq - day_start_equity) <= -limit:
                    if positions:
                        flatten(i, TS[i], c, ExitReason.DAILY_LOSS_LIMIT)
                        eq = broker.cash
                    if blocked_day != dk:
                        blocked_day = dk
                        logger.info(
                            "Daily loss limit reached on bar %d (%.2f); no more "
                            "entries today.", i, eq - day_start_equity)

            # -- 4. evaluate the rules on this bar's close ----------------
            if i >= start_bar and i < n - 1:
                ops: list[tuple] | None = None
                held = broker.net_side() if positions else None

                if held is not None:
                    if (XL[i] if held is Side.LONG else XS[i]):
                        ops = [(_OP_EXIT, ExitReason.SIGNAL)]

                long_sig = EL[i]
                short_sig = ES[i]
                if long_sig and short_sig:
                    ambiguous += 1
                    long_sig = short_sig = False

                if long_sig or short_sig:
                    side = Side.LONG if long_sig else Side.SHORT
                    permitted = allow_long if long_sig else allow_short
                    if permitted and TR[i] and blocked_day != dk:
                        if held is None:
                            if ops is None:
                                ops = [(_OP_ENTRY, side, i)]
                        elif held is side:
                            # Same-way signal: stack another unit if the
                            # configuration allows more than one position.
                            if ops is None and len(positions) < max_positions:
                                ops = [(_OP_ENTRY, side, i)]
                        elif allow_reversal:
                            ops = [(_OP_REVERSE, side, i)]
                        elif close_on_opposite:
                            ops = [(_OP_EXIT, ExitReason.SIGNAL)]

                if ops is not None:
                    if this_close:
                        self._run_ops(broker, ops, i, TS[i], c)
                        eq = equity_of(c) if positions else broker.cash
                    else:
                        pending = ops

            # -- 5. mark the account -------------------------------------
            eq_append(eq)
            bal_append(broker.cash)
            exp_append(broker.exposure() if positions else 0.0)

        # -- 15. nothing is left open when the data runs out --------------
        if positions:
            last = n - 1
            flatten(last, TS[last], CL[last], ExitReason.END_OF_DATA)
            equity_curve[last] = broker.cash
            balance_curve[last] = broker.cash
            exposure_curve[last] = 0.0

        if ambiguous:
            self.warnings.append(
                f"The long and short entry rules were both true on {ambiguous:,} "
                f"bar(s); no trade was taken on those bars because the strategy "
                f"does not say which way to go.")
        if progress is not None:
            progress(n, n)
        return equity_curve, balance_curve, exposure_curve

    def _run_ops(self, broker: SimulatedBroker, ops: Sequence[tuple], bar: int,
                 ts: int, price: float) -> None:
        """Execute the operations a previous bar's close scheduled."""
        for op in ops:
            code = op[0]
            if code == _OP_EXIT:
                broker.flatten(bar, ts, price, op[1])
            elif code == _OP_ENTRY:
                broker.open_position(op[1], bar, ts, price, op[2])
            else:  # _OP_REVERSE
                broker.flatten(bar, ts, price, ExitReason.REVERSAL)
                broker.open_position(op[1], bar, ts, price, op[2])

    # ------------------------------------------------------------------
    # results
    # ------------------------------------------------------------------

    def _build_result(self, bars: BarSeries, compiled: Any, config: BacktestConfig,
                      broker: SimulatedBroker, signals: dict[str, np.ndarray],
                      equity: list[float], balance: list[float],
                      exposure: list[float], lo: int, hi: int) -> BacktestResult:
        eq = np.asarray(equity, dtype="float64")
        peak = np.maximum.accumulate(eq) if len(eq) else eq
        drawdown = eq - peak
        # A percentage of a zero or negative peak has no meaning; report 0 there
        # rather than an infinity that would poison every downstream statistic.
        with np.errstate(divide="ignore", invalid="ignore"):
            dd_pct = np.where(peak > 0.0, drawdown / np.where(peak > 0.0, peak, 1.0),
                              0.0)
        curves = EquityCurves(
            ts=np.asarray(bars.ts, dtype="int64"), equity=eq,
            balance=np.asarray(balance, dtype="float64"), drawdown=drawdown,
            drawdown_pct=dd_pct, exposure=np.asarray(exposure, dtype="float64"),
            peak=peak,
        )

        indicators: dict[str, dict[str, np.ndarray]] = {}
        for ref, outputs in (getattr(compiled, "indicators", {}) or {}).items():
            indicators[ref] = {name: np.asarray(arr)[lo:hi]
                               for name, arr in outputs.items()}

        spec = self.spec
        result = BacktestResult(
            run_id=uuid.uuid4().hex[:12], label=self.label,
            strategy_name=getattr(spec, "name", ""),
            strategy_id=getattr(spec, "id", ""),
            instrument_symbol=bars.instrument.symbol,
            timeframe_label=bars.timeframe.label,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            bars=bars, config=config,
            strategy_dict=spec.to_dict() if hasattr(spec, "to_dict") else {},
            param_values=dict(getattr(compiled, "params", {}) or {}),
            trades=broker.trades, orders=broker.orders, curves=curves,
            indicators=indicators, signals=signals,
            rejected_orders=broker.rejected_orders, bars_processed=hi - lo,
        )
        return result

    def _metrics(self, result: BacktestResult) -> dict[str, Any]:
        """Compute the statistics.

        Imported inside the call so that an import-ordering problem in the
        analytics package can never stop the engine module from loading.
        """
        from ..analytics.metrics import compute_metrics

        try:
            return compute_metrics(result)
        except BacktesterError:
            raise
        except Exception as exc:
            raise BacktestError(
                "The backtest ran but its statistics could not be worked out.",
                detail=f"{type(exc).__name__}: {exc}") from exc


# --------------------------------------------------------------------------
# session helpers
# --------------------------------------------------------------------------


class _SessionArrays:
    """Per-bar session facts, all precomputed and vectorised.

    ``day_key`` is the local calendar date as ``YYYYMMDD``; it groups the daily
    loss limit and (for an ordinary daytime window) the flat-at-close rule.  For
    an overnight window the session block itself is used instead, so a session
    that runs 18:00 to 17:00 is not flattened at local midnight.
    """

    __slots__ = ("in_session", "day_key", "session_last")

    def __init__(self, in_session: list[bool], day_key: list[int],
                 session_last: list[bool]) -> None:
        self.in_session = in_session
        self.day_key = day_key
        self.session_last = session_last

    @classmethod
    def build(cls, ts: np.ndarray, session: SessionSettings,
              fallback_tz: str) -> "_SessionArrays":
        import pandas as pd

        # An empty session timezone means the instrument's, which is what
        # SessionSettings documents and what the compiler already did. Reading
        # `session.timezone` unconditionally is how a CME instrument got
        # filtered in New York.
        tz = (session.timezone or fallback_tz or "UTC") if session.enabled \
            else (fallback_tz or "UTC")
        idx = pd.DatetimeIndex(pd.to_datetime(np.asarray(ts, dtype="int64"),
                                              utc=True))
        try:
            local = idx.tz_convert(tz)
        except Exception as exc:
            raise BacktestError(
                f"'{tz}' is not a timezone this computer knows about.",
                detail=f"{type(exc).__name__}: {exc}") from exc

        years = np.asarray(local.year, dtype="int64")
        months = np.asarray(local.month, dtype="int64")
        days = np.asarray(local.day, dtype="int64")
        day_key = years * 10000 + months * 100 + days
        n = len(day_key)

        if not session.enabled:
            in_session = np.ones(n, dtype=bool)
            last = np.zeros(n, dtype=bool)
            return cls(in_session.tolist(), day_key.tolist(), last.tolist())

        start = _parse_hhmm(session.start, "session start")
        end = _parse_hhmm(session.end, "session end")
        minutes = (np.asarray(local.hour, dtype="int64") * 60
                   + np.asarray(local.minute, dtype="int64"))
        weekday = np.asarray(local.weekday, dtype="int64")

        allowed = np.zeros(7, dtype=bool)
        for d in session.weekdays or (0, 1, 2, 3, 4):
            if 0 <= int(d) <= 6:
                allowed[int(d)] = True
        day_ok = allowed[weekday]

        overnight = end <= start
        if end == start:
            window = np.ones(n, dtype=bool)          # a 24-hour session
            overnight = False
        elif overnight:
            window = (minutes >= start) | (minutes < end)
        else:
            window = (minutes >= start) & (minutes < end)
        in_session = day_ok & window

        next_in = np.empty(n, dtype=bool)
        next_in[:-1] = in_session[1:]
        next_in[-1] = False
        if overnight:
            last = in_session & ~next_in
        else:
            day_change = np.empty(n, dtype=bool)
            day_change[:-1] = day_key[1:] != day_key[:-1]
            day_change[-1] = True
            last = in_session & (~next_in | day_change)
        return cls(in_session.tolist(), day_key.tolist(), last.tolist())


def _parse_hhmm(text: str, what: str) -> int:
    """``"09:30"`` -> 570 minutes past local midnight."""
    raw = str(text).strip()
    try:
        parts = raw.split(":")
        hh = int(parts[0])
        mm = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError) as exc:
        raise BacktestError(
            f"The {what} time '{text}' is not in HH:MM form.",
            detail=repr(exc)) from exc
    if not (0 <= hh <= 24) or not (0 <= mm < 60):
        raise BacktestError(f"The {what} time '{text}' is not a real time of day.")
    return hh * 60 + mm


def _wilder_atr(bars: BarSeries, period: int) -> np.ndarray:
    """Wilder's ATR, used only if the indicator library cannot be reached.

    The recursion ``atr[i] = atr[i-1] + (tr[i] - atr[i-1]) / period`` genuinely
    depends on the previous value, so this loops -- once, in O(n).
    """
    period = max(1, int(period))
    high = bars.high
    low = bars.low
    close = bars.close
    n = len(close)
    out = np.empty(n, dtype="float64")
    out.fill(np.nan)
    if n == 0:
        return out
    tr = np.empty(n, dtype="float64")
    tr[0] = high[0] - low[0]
    prev_close = close[:-1]
    tr[1:] = np.maximum(high[1:] - low[1:],
                        np.maximum(np.abs(high[1:] - prev_close),
                                   np.abs(low[1:] - prev_close)))
    if n < period:
        return out
    acc = float(np.mean(tr[:period]))
    out[period - 1] = acc
    inv = 1.0 / period
    for i in range(period, n):
        acc += (tr[i] - acc) * inv
        out[i] = acc
    return out
