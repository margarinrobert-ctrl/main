"""Turning a condition tree into a per-bar boolean array.

Every condition in :mod:`tradingbacktester.strategy.spec` is evaluated here into
a ``bool`` array the same length as the bars.  The rules that matter:

*A cross is a change, not a state.*  ``left`` crosses above ``right`` at bar *i*
only when ``left[i] > right[i]`` **and** ``left[i-1] <= right[i-1]``.  It fires
once per crossing instead of on every bar the inequality happens to hold, which
is the difference between an entry signal and a filter.

*NaN is False, never True.*  A warm-up bar, a division that was undefined, a
missing value: none of them are a signal.  A comparison against NaN in NumPy is
already ``False``, but a *cross* needs both bars finite, and a negation would
otherwise turn "unknown" into "yes" — ``NOT(NaN > 0)`` must not open a trade on
bar three of a 200-bar moving average.  So every condition masks its result by
the finiteness of its inputs before any grouping or negation happens.

*The session window is arithmetic, not a loop.*  Timestamps are converted once
with pandas and reduced to a seconds-of-day integer and a weekday integer, so a
million-bar dataset costs one vectorised pass rather than a million
``datetime`` objects.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Sequence

import numpy as np

from ..core.errors import StrategyError
from .expression import EvalContext, evaluate_operand
from .spec import (Always, Compare, Condition, ConditionGroup, Cross,
                   SessionWindow, State, Vote)

log = logging.getLogger(__name__)

__all__ = ["evaluate_condition", "session_mask", "parse_time_of_day",
           "SECONDS_PER_DAY"]

SECONDS_PER_DAY = 24 * 60 * 60

#: Relative tolerance used by ``==`` and ``!=``.  Exact equality between two
#: floats that were arrived at by different arithmetic (an EMA and a price, say)
#: is essentially never true, which would make ``==`` a rule that silently never
#: fires.  A relative tolerance of 1e-9 is far tighter than any tick size and
#: only forgives representation error.
_EQUAL_RTOL = 1e-9


def evaluate_condition(cond: Condition | None, ctx: EvalContext) -> np.ndarray:
    """Evaluate a condition tree to a boolean array of length ``len(ctx.bars)``.

    ``None`` means "no rule", which is all ``False``: a strategy with no exit
    rule does not exit on every bar.
    """
    n = ctx.n
    if cond is None:
        return np.zeros(n, dtype=bool)
    if isinstance(cond, ConditionGroup):
        return _group(cond, ctx)
    if isinstance(cond, Compare):
        return _compare(cond, ctx)
    if isinstance(cond, Cross):
        return _cross(cond, ctx)
    if isinstance(cond, State):
        return _state(cond, ctx)
    if isinstance(cond, SessionWindow):
        return _session(cond, ctx)
    if isinstance(cond, Always):
        return np.full(n, bool(cond.value), dtype=bool)
    if isinstance(cond, Vote):
        return _vote(cond, ctx)
    raise StrategyError(
        f"'{type(cond).__name__}' is not a condition this application can evaluate.")


# --------------------------------------------------------------------------
# Individual conditions
# --------------------------------------------------------------------------


def _compare(cond: Compare, ctx: EvalContext) -> np.ndarray:
    """``left <op> right`` bar by bar, False wherever either side is NaN."""
    left = evaluate_operand(cond.left, ctx)
    right = evaluate_operand(cond.right, ctx)
    defined = np.isfinite(left) & np.isfinite(right)
    op = str(cond.op)
    if op == ">":
        out = left > right
    elif op == ">=":
        out = left >= right
    elif op == "<":
        out = left < right
    elif op == "<=":
        out = left <= right
    elif op == "==":
        out = np.isclose(left, right, rtol=_EQUAL_RTOL, atol=0.0, equal_nan=False)
    elif op == "!=":
        out = ~np.isclose(left, right, rtol=_EQUAL_RTOL, atol=0.0, equal_nan=False)
    else:
        raise StrategyError(
            f"'{cond.op}' is not a comparison this application knows. "
            f"Use >, >=, <, <=, == or !=.")
    return np.asarray(out, dtype=bool) & defined


def _cross(cond: Cross, ctx: EvalContext) -> np.ndarray:
    """A crossing of two series, requiring both bars of the pair to be finite."""
    left = evaluate_operand(cond.left, ctx)
    right = evaluate_operand(cond.right, ctx)
    n = len(left)
    out = np.zeros(n, dtype=bool)
    if n < 2:
        return out

    defined = np.isfinite(left) & np.isfinite(right)
    # Bar 0 has no previous bar, so no crossing can be observed there.
    pair_defined = np.zeros(n, dtype=bool)
    pair_defined[1:] = defined[1:] & defined[:-1]

    now_above = np.zeros(n, dtype=bool)
    now_below = np.zeros(n, dtype=bool)
    prev_at_or_below = np.zeros(n, dtype=bool)
    prev_at_or_above = np.zeros(n, dtype=bool)
    now_above[1:] = left[1:] > right[1:]
    now_below[1:] = left[1:] < right[1:]
    prev_at_or_below[1:] = left[:-1] <= right[:-1]
    prev_at_or_above[1:] = left[:-1] >= right[:-1]

    direction = str(cond.direction)
    if direction == "above":
        out = now_above & prev_at_or_below
    elif direction == "below":
        out = now_below & prev_at_or_above
    elif direction == "any":
        out = (now_above & prev_at_or_below) | (now_below & prev_at_or_above)
    else:
        raise StrategyError(
            f"'{cond.direction}' is not a crossing direction this application knows. "
            f"Use above, below or any.")
    return out & pair_defined


def _state(cond: State, ctx: EvalContext) -> np.ndarray:
    """A property of one series: rising, falling, sign, or a run of either."""
    values = evaluate_operand(cond.left, ctx)
    n = len(values)
    defined = np.isfinite(values)
    op = str(cond.op)

    if op in ("positive", "negative"):
        out = (values > 0.0) if op == "positive" else (values < 0.0)
        return np.asarray(out, dtype=bool) & defined
    if op in ("true", "false"):
        # A numeric series used as a flag: anything non-zero is true.  An
        # undefined bar is neither true nor false, so both forms are False there.
        out = (values != 0.0) if op == "true" else (values == 0.0)
        return np.asarray(out, dtype=bool) & defined

    if op in ("rising", "falling", "increasing_for", "decreasing_for"):
        step = _step_direction(values, defined, up=op in ("rising", "increasing_for"))
        if op in ("rising", "falling"):
            return step
        bars = int(cond.bars)
        if bars < 1:
            raise StrategyError(
                f"'{cond.describe()}' asks for a run of {bars} bars; a run must be "
                f"at least 1 bar long.")
        return _run_of(step, bars)

    raise StrategyError(
        f"'{cond.op}' is not a state this application knows. Use one of: "
        f"rising, falling, positive, negative, increasing_for, decreasing_for, "
        f"true, false.")


def _step_direction(values: np.ndarray, defined: np.ndarray, up: bool) -> np.ndarray:
    """True where the series moved strictly up (or down) from the previous bar."""
    n = len(values)
    out = np.zeros(n, dtype=bool)
    if n < 2:
        return out
    moved = (values[1:] > values[:-1]) if up else (values[1:] < values[:-1])
    out[1:] = moved & defined[1:] & defined[:-1]
    return out


def _run_of(step: np.ndarray, bars: int) -> np.ndarray:
    """True where ``step`` has been True on each of the last ``bars`` bars.

    Computed from a cumulative sum so the cost is one pass regardless of how
    long the run has to be; a sliding window would be ``O(n * bars)``.
    """
    n = len(step)
    out = np.zeros(n, dtype=bool)
    if bars > n:
        return out
    cumulative = np.concatenate(([0], np.cumsum(step.astype(np.int64))))
    idx = np.arange(n)
    # ``step[i]`` compares bar i with bar i-1, so a run of ``bars`` steps needs
    # bars i-bars .. i to exist, i.e. i >= bars.
    usable = idx >= bars
    counts = cumulative[idx[usable] + 1] - cumulative[idx[usable] + 1 - bars]
    out[usable] = counts == bars
    return out


def _session(cond: SessionWindow, ctx: EvalContext) -> np.ndarray:
    """Time-of-day / weekday membership, cached per distinct window."""
    key = ("session", cond.start, cond.end, cond.timezone, tuple(cond.weekdays or ()))
    cached = ctx.mask_cache.get(key)
    if cached is None:
        cached = session_mask(ctx.bars.ts, cond.start, cond.end, cond.timezone,
                              cond.weekdays)
        ctx.mask_cache[key] = cached
    # Hand out a private copy: the cache holds the expensive part (one timezone
    # conversion over every timestamp) and callers are free to modify what they
    # are given, which the compiler does when it blanks the warm-up.
    return cached.copy()


# --------------------------------------------------------------------------
# Grouping
# --------------------------------------------------------------------------


def _group(cond: ConditionGroup, ctx: EvalContext) -> np.ndarray:
    """AND/OR over children, then an optional NOT.

    An empty group is the identity of its operator: an empty AND is True (no
    condition has failed) and an empty OR is False (nothing has fired).  That
    matches the way the editor builds a rule up from an empty group and matches
    ``ConditionGroup.describe()``.
    """
    op = str(cond.op).upper()
    if op not in ("AND", "OR"):
        raise StrategyError(
            f"'{cond.op}' is not a way of combining rules. Use AND or OR.")
    children = [c for c in cond.children if c is not None]
    if not children:
        out = np.full(ctx.n, op == "AND", dtype=bool)
        return ~out if cond.negate else out

    out = evaluate_condition(children[0], ctx)
    for child in children[1:]:
        other = evaluate_condition(child, ctx)
        if op == "AND":
            # Short-circuiting would save nothing here: the arrays are already
            # materialised, and np.logical_and on bool arrays is one pass.
            out = out & other
        else:
            out = out | other
    return ~out if cond.negate else out


def _vote(cond: Vote, ctx: EvalContext) -> np.ndarray:
    """At least ``threshold`` of the children true, counted in one pass.

    The children are summed as ``uint16`` rather than OR-ed, which is what
    makes this different from a group: the count is the answer.  Each child is
    evaluated exactly once, so a five-way vote costs five evaluations and not
    the thirty an OR-of-ANDs expansion would.

    ``NaN`` needs no special handling here because every child has already
    masked itself to False wherever its inputs were undefined, and False
    contributes zero to the count.  An unknown is therefore a withheld vote,
    never a cast one -- which is the same rule the rest of this module follows.
    """
    children = [c for c in cond.children if c is not None]
    threshold = int(cond.threshold)
    if threshold <= 0:
        out = np.ones(ctx.n, dtype=bool)
    elif threshold > len(children):
        # Unsatisfiable.  ``StrategySpec.validate`` rejects this, but a rule
        # tree can be evaluated without being validated, and the honest answer
        # to "at least 4 of 3" is that it never happens.
        out = np.zeros(ctx.n, dtype=bool)
    else:
        count = np.zeros(ctx.n, dtype=np.uint16)
        for child in children:
            count += evaluate_condition(child, ctx).astype(np.uint16)
        out = count >= threshold
    return ~out if cond.negate else out


# --------------------------------------------------------------------------
# Session windows
# --------------------------------------------------------------------------


def parse_time_of_day(text: Any) -> int:
    """``"09:30"`` or ``"09:30:15"`` -> seconds since local midnight."""
    raw = str(text).strip()
    if not raw:
        raise StrategyError("A session window needs a start and an end time, "
                            "written as HH:MM.")
    parts = raw.replace(".", ":").split(":")
    if len(parts) not in (2, 3):
        raise StrategyError(
            f"'{text}' is not a time this application understands. Write times as "
            f"HH:MM, for example 09:30.")
    try:
        numbers = [int(p) for p in parts]
    except ValueError as exc:
        raise StrategyError(
            f"'{text}' is not a time this application understands. Write times as "
            f"HH:MM, for example 09:30.",
            detail=repr(exc),
        ) from exc
    hour, minute = numbers[0], numbers[1]
    second = numbers[2] if len(numbers) == 3 else 0
    if not (0 <= hour <= 24 and 0 <= minute <= 59 and 0 <= second <= 59):
        raise StrategyError(
            f"'{text}' is not a valid time of day. Hours run 00-24 and minutes "
            f"00-59.")
    total = hour * 3600 + minute * 60 + second
    if total > SECONDS_PER_DAY:
        raise StrategyError(f"'{text}' is later than the end of the day.")
    return total


def _local_parts(ts: np.ndarray, timezone: str) -> tuple[np.ndarray, np.ndarray]:
    """Seconds-of-day and weekday for every timestamp, in ``timezone``."""
    import pandas as pd

    stamps = np.ascontiguousarray(ts, dtype="int64")
    index = pd.DatetimeIndex(pd.to_datetime(stamps, utc=True))
    name = str(timezone or "UTC").strip() or "UTC"
    try:
        local = index.tz_convert(name)
    except Exception as exc:
        # pandas resolves a timezone name through zoneinfo, which needs the
        # system tz database (or the 'tzdata' package on Windows).  Say which of
        # the two problems it is rather than showing a pandas traceback.
        raise StrategyError(
            f"'{timezone}' is not a timezone this computer knows about. Use a name "
            f"like 'America/New_York', 'Europe/London' or 'UTC'.",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc
    seconds = (local.hour.to_numpy(dtype="int64") * 3600
               + local.minute.to_numpy(dtype="int64") * 60
               + local.second.to_numpy(dtype="int64"))
    weekday = local.weekday.to_numpy(dtype="int64")
    return seconds, weekday


def session_mask(ts: np.ndarray, start: str, end: str, timezone: str,
                 weekdays: Iterable[int] | None = (0, 1, 2, 3, 4)) -> np.ndarray:
    """Boolean per bar: is this timestamp inside the window?

    Both ends are inclusive, so ``09:30``-``16:00`` includes a bar stamped
    exactly 16:00.  A window whose start is *after* its end wraps midnight, which
    is how an overnight futures session is written (``17:00``-``16:00``).  A
    window whose start equals its end covers the whole day: a zero-width window
    would silently disable all trading, which is never what a user means by
    typing the same time twice.

    ``weekdays`` uses Monday = 0 and is applied in the *local* timezone, because
    a Sunday-evening bar in Chicago is a Monday bar in UTC and the user means the
    former.  An empty selection is read as "every day", again because a filter
    that excludes everything is never the intent.
    """
    stamps = np.ascontiguousarray(ts, dtype="int64")
    n = len(stamps)
    if n == 0:
        return np.zeros(0, dtype=bool)

    begin = parse_time_of_day(start)
    finish = parse_time_of_day(end)
    seconds, weekday = _local_parts(stamps, timezone)

    if begin == finish:
        in_window = np.ones(n, dtype=bool)
    elif begin < finish:
        in_window = (seconds >= begin) & (seconds <= finish)
    else:
        # Wraps midnight: everything from the start to the end of the day, plus
        # everything from midnight to the end time.
        in_window = (seconds >= begin) | (seconds <= finish)

    days: Sequence[int] = tuple(int(d) for d in (weekdays or ()))
    if days and len(set(days)) < 7:
        in_window &= np.isin(weekday, np.asarray(days, dtype="int64"))
    return in_window
