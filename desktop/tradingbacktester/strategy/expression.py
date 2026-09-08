"""Turning an :class:`~tradingbacktester.strategy.spec.Operand` into numbers.

An operand is the leaf of a rule: a price series, one output of one indicator
slot, a constant, a strategy parameter, or arithmetic over two of those.  This
module evaluates one into a ``float64`` array with the same length as the bars,
which is what :mod:`tradingbacktester.strategy.rules` then compares.

Two decisions here shape everything downstream.

*Everything becomes a full-length array.*  A constant is broadcast rather than
special-cased, so a comparison never has to ask what kind of operand it is
holding.  The cost is one array allocation per constant per compile, which is
nothing next to the indicator maths.

*NaN is contagious and never silently becomes a number.*  Warm-up bars, an
undefined division and a missing value are all NaN, and the rule layer turns a
NaN into ``False`` rather than guessing.  Division goes through
:func:`~tradingbacktester.indicators.base.safe_divide` so that ``x / 0`` is NaN
instead of ``inf`` or a raised exception; an ``inf`` would compare ``True``
against every threshold and quietly invent trades.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..core.errors import BacktesterError, StrategyError
from ..data.models import BarSeries
from ..indicators.base import safe_divide
from .spec import (ConstOperand, ExprOperand, IndicatorOperand, Operand,
                   ParamOperand, PriceOperand)

log = logging.getLogger(__name__)

__all__ = ["EvalContext", "evaluate_operand", "shift_back"]


@dataclass
class EvalContext:
    """Everything a rule needs to become a boolean array.

    The context is built once per compile and then handed to every condition, so
    the indicator arrays are computed once no matter how many rules mention
    them.  ``operand_cache`` extends the same idea to whole operand
    sub-expressions: ``close - ATR`` written in three rules is evaluated once.

    Arrays handed out by this context must be treated as read-only.  For an
    operand with no offset the array *is* the indicator's or the bar column's
    own memory, and writing into it would corrupt the dataset for every other
    consumer.
    """

    bars: BarSeries
    indicators: dict[str, dict[str, np.ndarray]] = field(default_factory=dict)
    """``{slot_ref: {output_name: array}}`` as produced by the registry."""
    params: dict[str, Any] = field(default_factory=dict)
    """Resolved strategy parameter values, defaults with overrides applied."""
    operand_cache: dict[str, np.ndarray] = field(default_factory=dict, repr=False)
    mask_cache: dict[tuple[Any, ...], np.ndarray] = field(default_factory=dict, repr=False)
    """Session masks, keyed by window; see :mod:`tradingbacktester.strategy.rules`."""

    # -- basics ----------------------------------------------------------

    def __len__(self) -> int:
        return len(self.bars)

    @property
    def n(self) -> int:
        """Number of bars, i.e. the length of every array in play."""
        return len(self.bars)

    def constant(self, value: float) -> np.ndarray:
        """A full-length array of one repeated number."""
        return np.full(self.n, float(value), dtype="float64")

    def price(self, field_name: str) -> np.ndarray:
        """Resolve a price source name, translating the data layer's error."""
        try:
            return self.bars.source_array(field_name)
        except BacktesterError as exc:
            raise StrategyError(
                f"A rule asks for the price series '{field_name}', which is not one "
                f"this application knows. Use open, high, low, close, volume, hlc3, "
                f"hl2 or ohlc4.",
                detail=exc.detail or exc.user_message,
            ) from exc

    def indicator(self, ref: str, output: str) -> np.ndarray:
        """One output array of one indicator slot."""
        arrays = self.indicators.get(ref)
        if arrays is None:
            known = ", ".join(sorted(self.indicators)) or "none"
            raise StrategyError(
                f"A rule refers to the indicator '{ref}', which this strategy does "
                f"not define. Defined indicators: {known}.")
        name = output or "value"
        if name not in arrays:
            raise StrategyError(
                f"The indicator '{ref}' has no output called '{name}'. "
                f"Its outputs are: {', '.join(sorted(arrays))}.")
        return arrays[name]

    def param_value(self, name: str) -> float:
        """A strategy parameter as a number, or a clear error saying why not."""
        if name not in self.params:
            known = ", ".join(sorted(self.params)) or "none"
            raise StrategyError(
                f"A rule refers to the parameter '{name}', which this strategy does "
                f"not define. Defined parameters: {known}.")
        raw = self.params[name]
        if isinstance(raw, bool):
            # A boolean parameter is usable as a switch: 1 or 0 in a comparison.
            return 1.0 if raw else 0.0
        try:
            return float(raw)
        except (TypeError, ValueError) as exc:
            raise StrategyError(
                f"The parameter '{name}' holds the value '{raw}', which is not a "
                f"number, so it cannot be used inside a rule.",
                detail=repr(exc),
            ) from exc


def shift_back(values: np.ndarray, offset: int) -> np.ndarray:
    """Move a series ``offset`` bars into the past, NaN-filling the front.

    ``offset=1`` gives the previous bar's value at every index.  A negative
    offset would read a bar that has not happened yet, so it is refused rather
    than quietly producing a look-ahead backtest.
    """
    if offset == 0:
        return values
    if offset < 0:
        raise StrategyError(
            f"An operand offset of {offset} would read a future bar. Offsets count "
            f"backwards, so 1 means the previous bar.")
    n = len(values)
    out = np.full(n, np.nan, dtype="float64")
    if offset < n:
        out[offset:] = values[: n - offset]
    return out


def _cache_key(op: Operand) -> str:
    """A stable structural key for an operand sub-tree."""
    try:
        return json.dumps(op.to_dict(), sort_keys=True)
    except (TypeError, ValueError):  # pragma: no cover - operands are plain data
        return repr(op)


def evaluate_operand(op: Operand, ctx: EvalContext) -> np.ndarray:
    """Evaluate one operand to a ``float64`` array of length ``len(ctx.bars)``.

    The result is cached on the context, so an expression used by several rules
    costs one evaluation per compile.
    """
    key = _cache_key(op)
    cached = ctx.operand_cache.get(key)
    if cached is not None:
        return cached
    values = _evaluate(op, ctx)
    values = np.asarray(values, dtype="float64")
    if values.shape != (ctx.n,):
        # Defensive: an indicator that returned the wrong length is caught by the
        # registry, so reaching here means a bug rather than bad user input.
        raise StrategyError(
            f"The operand {op.describe()} produced {values.size} values for "
            f"{ctx.n} bars, which is a bug in this application.")
    ctx.operand_cache[key] = values
    return values


def _evaluate(op: Operand, ctx: EvalContext) -> np.ndarray:
    """Dispatch on operand type.  Kept separate so caching wraps every branch."""
    if isinstance(op, PriceOperand):
        return shift_back(ctx.price(op.field), int(op.offset))
    if isinstance(op, IndicatorOperand):
        return shift_back(ctx.indicator(op.ref, op.output), int(op.offset))
    if isinstance(op, ConstOperand):
        return ctx.constant(op.value)
    if isinstance(op, ParamOperand):
        return ctx.constant(ctx.param_value(op.name))
    if isinstance(op, ExprOperand):
        return _arithmetic(op, ctx)
    raise StrategyError(
        f"'{type(op).__name__}' is not an operand this application can evaluate.")


def _arithmetic(op: ExprOperand, ctx: EvalContext) -> np.ndarray:
    """Two-operand arithmetic with NaN-safe division."""
    left = evaluate_operand(op.left, ctx)
    right = evaluate_operand(op.right, ctx)
    symbol = str(op.op)
    if symbol == "+":
        return left + right
    if symbol == "-":
        return left - right
    if symbol == "*":
        return left * right
    if symbol == "/":
        # A zero denominator is a real possibility (an indicator that measures a
        # range, a volume series with an empty bar).  NaN there means "no signal
        # on this bar", which is the honest answer; inf would pass every
        # greater-than test in the strategy.
        return safe_divide(left, right)
    raise StrategyError(
        f"'{symbol}' is not an arithmetic operator this application knows. "
        f"Use +, -, * or /.")
