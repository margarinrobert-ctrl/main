"""The parameter grid: ranges in, a list of parameter dictionaries out.

A sweep is defined by a small list of :class:`ParameterRange` objects, one per
strategy parameter the user ticked.  This module turns those into the cartesian
product of *validated* parameter dictionaries that the runner will backtest.

Two details matter more than they look.

*Float ranges.*  ``0.1`` cannot be represented exactly, so building a range by
repeatedly adding the step accumulates error and quietly drops the last rung:
``0.1 + 0.1 + ... `` never lands on ``1.0``.  Every value here is computed as
``start + i * step`` and then rounded to the number of decimals implied by the
inputs, so ``0.1 -> 1.0 step 0.1`` has ten steps and ends exactly on ``1.0``.

*Validation up front.*  Each value is coerced through the strategy's own
:class:`~tradingbacktester.indicators.base.ParamSpec` before the sweep starts.
A period of ``0`` is refused now, with a message naming the parameter, rather
than 400 backtests into a run that will fail on every combination anyway.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Sequence, TYPE_CHECKING

from ..core.errors import BacktesterError, ParameterError
from ..logging_setup import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..indicators.base import ParamSpec
    from ..strategy.spec import StrategySpec

log = get_logger(__name__)

#: Default ceiling on the number of combinations a sweep may contain.  A grid
#: this size is already many hours of computation; the guard exists so a
#: mistyped step (``0.001`` instead of ``0.1``) is caught before anything runs.
DEFAULT_MAX_COMBINATIONS = 100_000

#: Ceiling on the number of rungs in a *single* range.  A range longer than this
#: cannot take part in any sensible grid and would only waste memory.
MAX_RANGE_VALUES = 1_000_000

#: Relative tolerance used when deciding whether the final rung fits.  Chosen so
#: that accumulated double-precision error over a few thousand steps cannot lose
#: a rung, while a genuine gap of a whole step is never invented.
_RUNG_TOLERANCE = 1e-9

_MAX_DECIMALS = 12


def _decimals(value: float) -> int:
    """Decimal places implied by ``value`` when written out normally.

    Used to round generated rungs so that ``0.30000000000000004`` is presented
    (and hashed, and compared) as ``0.3``.
    """
    try:
        exponent = Decimal(str(float(value))).as_tuple().exponent
    except (InvalidOperation, ValueError, OverflowError):  # pragma: no cover
        return 0
    if not isinstance(exponent, int) or exponent >= 0:
        return 0
    return min(-exponent, _MAX_DECIMALS)


@dataclass(frozen=True)
class ParameterRange:
    """One swept parameter: ``start`` to ``stop`` inclusive, in ``step`` rungs.

    ``stop`` is included whenever it lands on a rung.  ``stop`` below ``start``
    is a descending sweep; the sign of ``step`` is ignored and its magnitude
    used, because a UI spin box will happily hand over a negative step for an
    ascending range and the user means the same thing either way.
    """

    name: str
    start: float
    stop: float
    step: float = 1.0

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ParameterError("A swept parameter needs a name.")
        for label, value in (("start", self.start), ("stop", self.stop),
                             ("step", self.step)):
            if value is None or not math.isfinite(float(value)):
                raise ParameterError(
                    f"The {label} value for '{self.name}' must be a number."
                )

    # -- shape -----------------------------------------------------------

    @property
    def is_integer(self) -> bool:
        """True when every rung is a whole number, so the list is ``int``."""
        return all(float(v).is_integer()
                   for v in (self.start, self.stop, self.step))

    def count(self) -> int:
        """How many rungs this range produces, without building them."""
        start, stop, step = float(self.start), float(self.stop), abs(float(self.step))
        if start == stop:
            return 1
        if step == 0.0:
            raise ParameterError(
                f"The step for '{self.name}' is zero, so the sweep from "
                f"{start:g} to {stop:g} would never finish."
            )
        span = abs(stop - start)
        ratio = span / step
        return int(math.floor(ratio + max(_RUNG_TOLERANCE, _RUNG_TOLERANCE * ratio))) + 1

    def values(self) -> list[Any]:
        """The inclusive list of values, ``int`` when the range is integral."""
        n = self.count()
        if n > MAX_RANGE_VALUES:
            raise ParameterError(
                f"'{self.name}' would be swept over {n:,} values. Use a larger "
                f"step or a narrower range."
            )
        start, stop = float(self.start), float(self.stop)
        step = abs(float(self.step)) * (1.0 if stop >= start else -1.0)
        decimals = max(_decimals(start), _decimals(self.step))
        integral = self.is_integer
        out: list[Any] = []
        for i in range(n):
            # Multiply, never accumulate: repeated addition drifts and drops the
            # last rung of any range with a fractional step.
            value = start + i * step
            out.append(int(round(value)) if integral else round(value, decimals))
        return out

    def describe(self) -> str:
        """One line for a tooltip or a log entry."""
        n = self.count()
        fmt = "{:g}"
        return (f"{self.name}: {fmt.format(float(self.start))} to "
                f"{fmt.format(float(self.stop))} step "
                f"{fmt.format(abs(float(self.step)))} ({n} value"
                f"{'' if n == 1 else 's'})")

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "start": self.start, "stop": self.stop,
                "step": self.step}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "ParameterRange":
        try:
            return ParameterRange(str(d["name"]), float(d["start"]),
                                  float(d["stop"]), float(d.get("step", 1.0)))
        except (KeyError, TypeError, ValueError) as exc:
            raise ParameterError(
                "A saved parameter range is missing its name, start or stop value.",
                detail=repr(exc)) from exc


def suggested_range(param: "ParamSpec") -> ParameterRange:
    """A sensible default sweep for one strategy parameter.

    The optimiser dialog pre-fills its rows from this so the user starts with
    something runnable rather than three empty boxes.  The range is centred on
    the parameter's default and clipped to its own minimum and maximum.
    """
    default = param.default
    step = float(param.step) if param.step else 1.0
    if param.kind == "int":
        step = max(1.0, round(step))
    try:
        centre = float(default)
    except (TypeError, ValueError):
        # A choice or bool parameter has no numeric neighbourhood; sweeping it
        # is not meaningful, so offer the single default value.
        return ParameterRange(param.name, 0.0, 0.0, 1.0)
    span = step * 4
    low = centre - span / 2
    high = centre + span / 2
    if param.minimum is not None:
        low = max(low, float(param.minimum))
    if param.maximum is not None:
        high = min(high, float(param.maximum))
    if high < low:
        high = low
    if param.kind == "int":
        low, high = float(round(low)), float(round(high))
    return ParameterRange(param.name, low, high, step)


def combination_count(ranges: Sequence[ParameterRange]) -> int:
    """Number of combinations the cartesian product of ``ranges`` would have."""
    total = 1
    for r in ranges:
        total *= max(1, r.count())
    return total if ranges else 0


def check_combination_count(ranges: Sequence[ParameterRange],
                            maximum: int = DEFAULT_MAX_COMBINATIONS) -> int:
    """Return the combination count, raising if it exceeds ``maximum``.

    Raises :class:`~tradingbacktester.core.errors.ParameterError` naming the
    count, because "too many combinations" without the number tells the user
    nothing about how much to cut.
    """
    total = combination_count(ranges)
    if maximum is not None and total > int(maximum):
        raise ParameterError(
            f"This grid has {total:,} combinations, which is more than the "
            f"limit of {int(maximum):,}. Sweep fewer parameters, narrow a "
            f"range, or use a larger step."
        )
    return total


def build_grid(spec: "StrategySpec", ranges: Sequence[ParameterRange],
               maximum: int = DEFAULT_MAX_COMBINATIONS) -> list[dict[str, Any]]:
    """Every parameter combination the sweep will test, validated.

    Each value is coerced by the strategy parameter's own ``ParamSpec``, so the
    dictionaries handed to the runner are already of the right type and inside
    the parameter's own limits.  Coercion can collapse rungs -- a step of 0.5 on
    an integer parameter produces each whole number twice -- and duplicates are
    removed, so the returned list never contains the same combination twice.
    """
    if not ranges:
        raise ParameterError(
            "Choose at least one parameter to sweep before optimising."
        )
    names = [r.name for r in ranges]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise ParameterError(
            f"The parameter(s) {', '.join(duplicates)} are listed twice in the "
            f"sweep. Each parameter can only be swept once."
        )

    columns: list[list[Any]] = []
    for r in ranges:
        param = spec.param(r.name)          # raises ParameterError if unknown
        coerced: list[Any] = []
        for raw in r.values():
            try:
                value = param.coerce(raw)
            except BacktesterError as exc:
                raise ParameterError(
                    f"The sweep of '{r.name}' includes the value {raw!r}, which "
                    f"this strategy will not accept: {exc.user_message}"
                ) from exc
            if value not in coerced:
                coerced.append(value)
        if not coerced:  # pragma: no cover - count() guarantees at least one
            raise ParameterError(f"The sweep of '{r.name}' has no values.")
        columns.append(coerced)

    total = 1
    for column in columns:
        total *= len(column)
    if maximum is not None and total > int(maximum):
        raise ParameterError(
            f"This grid has {total:,} combinations, which is more than the "
            f"limit of {int(maximum):,}. Sweep fewer parameters, narrow a "
            f"range, or use a larger step."
        )

    grid = [dict(zip(names, combo)) for combo in itertools.product(*columns)]
    log.debug("Built a grid of %d combinations over %s", len(grid), ", ".join(names))
    return grid


def describe_grid(ranges: Iterable[ParameterRange]) -> str:
    """A human-readable summary of the sweep, for logs and the dialog header."""
    ranges = list(ranges)
    if not ranges:
        return "No parameters selected."
    total = combination_count(ranges)
    body = "; ".join(r.describe() for r in ranges)
    return f"{total:,} combination{'' if total == 1 else 's'} -- {body}"
