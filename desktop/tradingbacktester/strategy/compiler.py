"""Compiling a :class:`~tradingbacktester.strategy.spec.StrategySpec` to arrays.

This is where "a strategy is data, not code" is cashed in.  The compiler takes a
declarative spec plus a :class:`~tradingbacktester.data.models.BarSeries` and
produces four boolean signal arrays, a tradeable mask, the indicator arrays the
chart draws, and the ATR series the stops, targets and volatility sizing all
read.  The engine never sees a rule tree: it sees ``entry_long[i]``.

The order of work, and why:

1. **Resolve parameters.**  ``"$ema_fast"`` inside an indicator slot becomes the
   number the user (or the optimiser) chose.  This happens before anything is
   computed so a bad value is reported once, by name, instead of as a failure
   inside an indicator.
2. **Compute every indicator once.**  Slots are computed one at a time and
   memoised by ``(indicator, parameters, source)``, so two slots that happen to
   be the same EMA cost one pass, and a rule that mentions the same slot ten
   times costs none.
3. **Compute the ATR.**  Stops, targets, trailing stops, ATR slippage and
   volatility sizing all need it, and none of them should each compute their
   own.
4. **Evaluate the four rule trees** against one shared context, so a shared
   sub-expression is evaluated once across all four.
5. **Build ``tradeable``** from the session filter and the warm-up, and blank
   every signal inside the warm-up.

**What ``tradeable`` means for the engine.**  The four signal arrays are the
rules and nothing else.  ``tradeable`` is the separate question of whether the
account is allowed to *open* a position on that bar — inside the session, after
the warm-up.  The broker must require ``tradeable[i]`` before entering, and must
**not** require it before exiting: a position opened at 15:55 has to be closable
at 16:05 even though a new one could not be opened then.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..core.errors import (BacktesterError, InsufficientDataError, StrategyError)
from ..core.types import SizingMode
from ..data.models import BarSeries
from ..indicators import REGISTRY
from .expression import EvalContext, evaluate_operand
from .rules import evaluate_condition, session_mask
from .spec import IndicatorSlot, StrategySpec

log = logging.getLogger(__name__)

__all__ = ["CompiledStrategy", "compile_strategy", "resolve_slot_params",
           "evaluate_operand", "evaluate_condition"]


@dataclass
class CompiledStrategy:
    """One strategy, one dataset, one set of parameter values, all as arrays.

    Every array here has the same length as ``bars``.  Boolean arrays are
    ``bool``; ``atr`` is ``float64`` with NaN through its warm-up.
    """

    spec: StrategySpec
    params: dict[str, Any]
    """Resolved parameter values -- the defaults with any overrides applied."""
    indicators: dict[str, dict[str, np.ndarray]]
    """``{slot_ref: {output_name: array}}``, ready for the chart and the result."""
    entry_long: np.ndarray
    entry_short: np.ndarray
    exit_long: np.ndarray
    exit_short: np.ndarray
    tradeable: np.ndarray
    """Bars on which a *new* position may be opened: in session, past warm-up."""
    warmup: int
    """Bars reserved for indicator warm-up.  No signal is True before this."""
    atr: np.ndarray
    """Average true range at ``spec.exits.atr_period``, for stops and targets."""
    sizing_atr: np.ndarray = field(repr=False, default_factory=lambda: np.empty(0))
    """ATR at ``spec.risk.volatility_atr_period``.  The *same object* as ``atr``
    when the two periods agree, so comparing with ``is`` is meaningful."""
    bars: BarSeries | None = field(default=None, repr=False)
    warnings: list[str] = field(default_factory=list)
    """Non-fatal problems worth showing the user, e.g. "no signals at all"."""
    entry_long_price: np.ndarray | None = field(default=None, repr=False)
    """Resting-order prices per bar (NaN where undefined); None for market."""
    entry_short_price: np.ndarray | None = field(default=None, repr=False)
    entry_cancel: np.ndarray | None = field(default=None, repr=False)

    # -- convenience -----------------------------------------------------

    def __len__(self) -> int:
        return len(self.entry_long)

    @property
    def signals(self) -> dict[str, np.ndarray]:
        """The arrays in the shape :class:`BacktestResult.signals` wants."""
        out = {"entry_long": self.entry_long, "entry_short": self.entry_short,
               "exit_long": self.exit_long, "exit_short": self.exit_short,
               "tradeable": self.tradeable}
        if self.entry_long_price is not None:
            out["entry_long_price"] = self.entry_long_price
            out["entry_short_price"] = self.entry_short_price
            out["entry_cancel"] = self.entry_cancel
        return out

    @property
    def entry_long_allowed(self) -> np.ndarray:
        """Long entries that the session filter and warm-up actually permit."""
        return self.entry_long & self.tradeable

    @property
    def entry_short_allowed(self) -> np.ndarray:
        """Short entries that the session filter and warm-up actually permit."""
        return self.entry_short & self.tradeable

    def signal_counts(self) -> dict[str, int]:
        """How often each rule fired -- what the editor's Preview button shows."""
        return {name: int(np.count_nonzero(arr)) for name, arr in self.signals.items()}

    def describe(self) -> str:
        counts = self.signal_counts()
        return (f"{self.spec.name}: {counts['entry_long']} long and "
                f"{counts['entry_short']} short entry signals over "
                f"{len(self)} bars, warm-up {self.warmup}")


# --------------------------------------------------------------------------
# Parameter resolution
# --------------------------------------------------------------------------


def resolve_slot_params(slot: IndicatorSlot, params: dict[str, Any]) -> dict[str, Any]:
    """Replace ``"$name"`` references in a slot's parameters with their values.

    A literal is passed through untouched; the registry coerces and validates it
    a moment later.  A reference to a parameter the strategy does not declare is
    an error here rather than a ``KeyError`` deeper down.
    """
    resolved: dict[str, Any] = {}
    for key, value in slot.params.items():
        if isinstance(value, str) and value.startswith("$"):
            name = value[1:]
            if name not in params:
                known = ", ".join(sorted(params)) or "none"
                raise StrategyError(
                    f"The indicator '{slot.ref}' uses the parameter '{name}', which "
                    f"this strategy does not define. Defined parameters: {known}.")
            resolved[key] = params[name]
        else:
            resolved[key] = value
    return resolved


# --------------------------------------------------------------------------
# Compilation
# --------------------------------------------------------------------------


def compile_strategy(spec: StrategySpec, bars: BarSeries,
                     overrides: dict[str, Any] | None = None) -> CompiledStrategy:
    """Compile ``spec`` against ``bars``, applying ``overrides`` to its parameters.

    Raises :class:`~tradingbacktester.core.errors.StrategyError` (or a subclass)
    for anything wrong with the strategy, naming the indicator slot or parameter
    at fault, and :class:`InsufficientDataError` when there is nothing to
    compile against.
    """
    if bars is None or len(bars) == 0:
        raise InsufficientDataError(
            "There are no bars to compile this strategy against. Load a dataset "
            "first.")
    n = len(bars)

    params = spec.param_values(overrides)          # raises ParameterError
    indicators = _compute_indicators(spec, bars, params)
    atr, sizing_atr = _compute_atr(spec, bars)

    ctx = EvalContext(bars=bars, indicators=indicators, params=params)
    # ``np.array(..., copy=True)`` because the warm-up blanking below writes into
    # these arrays, and a rule that is nothing but a session window would
    # otherwise be handed the same object twice.
    entry_long = np.array(evaluate_condition(spec.entry_long, ctx), dtype=bool)
    entry_short = np.array(evaluate_condition(spec.entry_short, ctx), dtype=bool)
    exit_long = np.array(evaluate_condition(spec.exit_long, ctx), dtype=bool)
    exit_short = np.array(evaluate_condition(spec.exit_short, ctx), dtype=bool)

    warnings: list[str] = []
    warmup = _warmup_bars(spec, overrides)
    if warmup >= n:
        warnings.append(
            f"This strategy needs {warmup} bars of warm-up but the dataset has "
            f"{n}, so no signal can be produced. Use more data or shorter "
            f"indicator periods.")
        log.warning("Warm-up (%d) exceeds the %d bars available for '%s'",
                    warmup, n, spec.name)

    tradeable = _session_filter(spec, bars, warnings)

    # One barrier for the whole compile: nothing that happens inside the
    # warm-up is trustworthy, so nothing inside it is allowed to be a signal.
    blank = min(warmup, n)
    for arr in (entry_long, entry_short, exit_long, exit_short, tradeable):
        arr[:blank] = False

    long_price = short_price = cancel = None
    if spec.uses_resting_entries():
        def price_of(op) -> np.ndarray:
            if op is None:
                return np.full(n, np.nan)
            return np.array(evaluate_operand(op, ctx), dtype="float64")

        long_price = price_of(spec.entry_long_price)
        short_price = price_of(spec.entry_short_price)
        cancel = (np.array(evaluate_condition(spec.entry_cancel, ctx), dtype=bool)
                  if spec.entry_cancel is not None else np.zeros(n, dtype=bool))
        long_price[:blank] = np.nan
        short_price[:blank] = np.nan

    if not entry_long.any() and not entry_short.any():
        warnings.append(
            "No entry signal fired anywhere in this dataset. Check the rule "
            "thresholds, or try a longer history.")

    compiled = CompiledStrategy(
        spec=spec, params=params, indicators=indicators,
        entry_long=entry_long, entry_short=entry_short,
        exit_long=exit_long, exit_short=exit_short,
        tradeable=tradeable, warmup=int(warmup), atr=atr, sizing_atr=sizing_atr,
        bars=bars, warnings=warnings, entry_long_price=long_price,
        entry_short_price=short_price, entry_cancel=cancel,
    )
    log.debug("Compiled %s", compiled.describe())
    return compiled


#: Indicator arrays shared ACROSS compiles, keyed on the indicator, its
#: resolved parameters, its source and a fingerprint of the bars.
#:
#: Within one compile ``_compute_indicators`` already shares a computation
#: between two slots with identical definitions.  Across a sweep it did not: a
#: strategy with six indicators where the optimiser moves two of them
#: recomputed the other four -- and the ATR the exits read -- on every one of
#: several hundred combinations, over the same bars, to the same answer.
#:
#: The arrays are marked read-only.  Downstream code already treats them as
#: shared within a compile ("read-only by convention"); the flag turns that
#: convention into an error at the write site rather than a wrong number three
#: sweeps later.  Bounded and keyed on a fingerprint rather than the object, so
#: a resampled or sliced series is a different entry, not a stale one.
_INDICATOR_CACHE_LIMIT = 512
_INDICATOR_CACHE: dict[tuple, dict[str, np.ndarray]] = {}


def clear_indicator_cache() -> None:
    """Forget every cached indicator array.  Tests use this."""
    _INDICATOR_CACHE.clear()


def _bars_fingerprint(bars: BarSeries) -> tuple:
    """Cheap identity for a bar series: length plus sampled stamps AND closes.

    Timestamps alone are not enough here -- two datasets of the same instrument
    over the same period from two vendors share every stamp and differ in
    price, and an indicator cached from one must not answer for the other.
    """
    n = len(bars)
    if n == 0:
        return (0,)
    picks = np.linspace(0, n - 1, num=min(n, 9), dtype=np.int64)
    ts = np.asarray(bars.ts)[picks]
    cl = np.asarray(bars.close)[picks]
    return (n,) + tuple(int(v) for v in ts) + tuple(float(v) for v in cl)


def _cached_compute(indicator: str, bars: BarSeries, params: dict[str, Any],
                    source: str, fingerprint: tuple) -> dict[str, np.ndarray]:
    """``REGISTRY.compute`` through the cross-compile cache."""
    key = (str(indicator).upper(),
           tuple(sorted((k, _hashable(v)) for k, v in params.items())),
           source, fingerprint)
    hit = _INDICATOR_CACHE.get(key)
    if hit is not None:
        return hit
    arrays = REGISTRY.compute(indicator, bars, params, source)
    for arr in arrays.values():
        if isinstance(arr, np.ndarray):
            arr.setflags(write=False)
    if len(_INDICATOR_CACHE) >= _INDICATOR_CACHE_LIMIT:
        _INDICATOR_CACHE.pop(next(iter(_INDICATOR_CACHE)))
    _INDICATOR_CACHE[key] = arrays
    return arrays


def _compute_indicators(spec: StrategySpec, bars: BarSeries,
                        params: dict[str, Any]) -> dict[str, dict[str, np.ndarray]]:
    """Run every slot exactly once, memoised across identical definitions."""
    out: dict[str, dict[str, np.ndarray]] = {}
    memo: dict[tuple[Any, ...], dict[str, np.ndarray]] = {}
    keys: dict[str, Any] = {}
    fingerprint = _bars_fingerprint(bars)
    for slot in spec.indicators:
        if not slot.ref:
            raise StrategyError("Every indicator on a strategy needs a reference name.")
        if slot.ref in out:
            raise StrategyError(
                f"Two indicators on this strategy are both called '{slot.ref}'. "
                f"Give each one a different reference name.")
        resolved = resolve_slot_params(slot, params)
        source = slot.source or "close"
        if source.startswith("@"):
            out[slot.ref] = _chained(slot, source, bars, resolved, out, keys)
            keys[slot.ref] = (slot.indicator, tuple(sorted(
                (k, _hashable(v)) for k, v in resolved.items())), source,
                keys.get(source[1:].split(".", 1)[0]))
            continue
        key = (str(slot.indicator).upper(), tuple(sorted(
            (k, _hashable(v)) for k, v in resolved.items())), source)
        keys[slot.ref] = key
        cached = memo.get(key)
        if cached is not None:
            # Two slots with identical definitions share one computation.  The
            # arrays are read-only by convention everywhere downstream, so
            # sharing them is safe and saves a full pass over the data.
            out[slot.ref] = cached
            continue
        try:
            arrays = _cached_compute(slot.indicator, bars, resolved, source,
                                     fingerprint)
        except BacktesterError as exc:
            raise StrategyError(
                f"The indicator '{slot.ref}' ({slot.indicator}) could not be "
                f"calculated: {exc.user_message}",
                detail=exc.detail,
            ) from exc
        except Exception as exc:  # pragma: no cover - registry wraps its own
            raise StrategyError(
                f"The indicator '{slot.ref}' ({slot.indicator}) could not be "
                f"calculated.",
                detail=f"{type(exc).__name__}: {exc}",
            ) from exc
        memo[key] = arrays
        out[slot.ref] = arrays
    return out


def _chained(slot: Any, source: str, bars: BarSeries, resolved: dict[str, Any],
             done: dict[str, dict[str, np.ndarray]], keys: dict[str, Any]
             ) -> dict[str, np.ndarray]:
    """An indicator computed on another indicator's output: an EMA of an EMA.

    ``source`` is ``"@ref"`` (the upstream's first output) or ``"@ref.output"``.
    The upstream series stands in for price: a bar series whose open, high,
    low and close are all that series is handed to the indicator, from the
    upstream's first defined value on, and the result is padded back with NaN.
    Only indicators that read a single price source can be chained; one that
    reads the bar's high and low would see a bar with no range.

    Not held in the cross-compile cache: its input changes with the upstream's
    parameters, which the cache key does not see.
    """
    from ..indicators.base import REGISTRY

    ref, _, output = source[1:].partition(".")
    if ref not in done:
        raise StrategyError(
            f"The indicator '{slot.ref}' is computed on '{ref}', which must be "
            f"defined above it.")
    upstream = done[ref]
    if not output:
        output = next(iter(upstream))
    if output not in upstream:
        raise StrategyError(
            f"'{ref}' has no output called '{output}'. It has: "
            f"{', '.join(upstream)}.")
    definition = REGISTRY.get(slot.indicator)
    if not definition.uses_source:
        raise StrategyError(
            f"{definition.name} reads the bar's high and low, so it cannot be "
            f"computed on another indicator. Only single-source indicators "
            f"(moving averages, RSI and the like) can.")
    series = np.asarray(upstream[output], dtype="float64")
    n = series.size
    finite = np.flatnonzero(np.isfinite(series))
    result: dict[str, np.ndarray]
    if finite.size == 0:
        return {name: np.full(n, np.nan) for name in definition.outputs}
    k = int(finite[0])
    tail = series[k:]
    derived = BarSeries(ts=np.asarray(bars.ts)[k:], open=tail, high=tail, low=tail,
                        close=tail, volume=np.asarray(bars.volume)[k:],
                        instrument=bars.instrument, timeframe=bars.timeframe,
                        source=f"{bars.source} -> {ref}.{output}")
    try:
        computed = REGISTRY.compute(slot.indicator, derived, resolved, "close")
    except BacktesterError as exc:
        raise StrategyError(
            f"The indicator '{slot.ref}' ({slot.indicator} of {ref}) could not "
            f"be calculated: {exc.user_message}", detail=exc.detail) from exc
    result = {}
    for name, arr in computed.items():
        full = np.full(n, np.nan)
        full[k:] = np.asarray(arr, dtype="float64")
        full.setflags(write=False)
        result[name] = full
    return result


def _hashable(value: Any) -> Any:
    """Make a parameter value usable in a memo key without surprising equality."""
    if isinstance(value, (list, tuple)):
        return tuple(_hashable(v) for v in value)
    if isinstance(value, dict):  # pragma: no cover - indicators take flat params
        return tuple(sorted((k, _hashable(v)) for k, v in value.items()))
    return value


def _compute_atr(spec: StrategySpec, bars: BarSeries) -> tuple[np.ndarray, np.ndarray]:
    """The ATR series stops, targets, ATR slippage and volatility sizing use.

    Always computed, even when the current settings do not ask for a stop: the
    cost model can charge slippage as a fraction of ATR, the engine reports MAE
    and MFE in ATR terms, and a second pass later would cost more than this one.
    """
    exit_period = max(1, int(spec.exits.atr_period))
    method = str(getattr(spec.exits, "atr_method", "wilder") or "wilder")
    atr = _atr_array(bars, exit_period, method)
    size_period = max(1, int(spec.risk.volatility_atr_period))
    if size_period == exit_period:
        # Deliberately the same object: the sizer can check ``is`` to know it
        # need not hold two arrays alive.
        return atr, atr
    if spec.risk.sizing_mode is not SizingMode.VOLATILITY_TARGET:
        return atr, atr
    return atr, _atr_array(bars, size_period, method)


def _atr_array(bars: BarSeries, period: int, method: str = "wilder") -> np.ndarray:
    """The ATR through the registry, so there is one definition of it.

    ``method`` is the strategy's ``exits.atr_method``: Wilder's unless the
    strategy says otherwise.
    """
    try:
        return _cached_compute("ATR", bars, {"period": period, "method": method},
                               "close", _bars_fingerprint(bars))["value"]
    except BacktesterError as exc:
        raise StrategyError(
            f"The average true range over {period} bars could not be calculated, "
            f"so stops and targets cannot be placed: {exc.user_message}",
            detail=exc.detail,
        ) from exc


def _warmup_bars(spec: StrategySpec, overrides: dict[str, Any] | None) -> int:
    """Warm-up implied by the indicators, the ATR and the sizing method."""
    try:
        return max(1, int(spec.warmup_bars(overrides)))
    except BacktesterError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise StrategyError(
            "The warm-up period for this strategy could not be worked out.",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


def _session_filter(spec: StrategySpec, bars: BarSeries,
                    warnings: list[str]) -> np.ndarray:
    """Bars on which a new position may be opened, before the warm-up is applied."""
    n = len(bars)
    session = spec.session
    if not session.enabled:
        return np.ones(n, dtype=bool)
    timezone = session.timezone or bars.instrument.timezone or "UTC"
    mask = session_mask(bars.ts, session.start, session.end, timezone,
                        session.weekdays)
    if not mask.any():
        warnings.append(
            f"No bar in this dataset falls inside the trading session "
            f"{session.start}-{session.end} {timezone}, so no trade can be opened. "
            f"Check the session timezone.")
        log.warning("Session filter %s-%s %s excludes every bar",
                    session.start, session.end, timezone)
    return mask
