"""Calendar returns -- by day, month and year -- computed from the equity curve.

Two decisions here matter and both follow the project's assumptions document:

**Returns come from the equity curve, never from the trade list.**  The change
in an account over January is the change in its *equity* over January, including
the mark-to-market of a position that was still open on the 31st.  Adding up the
P&L of the trades that happened to close in January answers a different question
and flatters any strategy that holds losers across a period boundary.

**Periods compound; they do not sum.**  A year's return is the change from the
last equity value of the previous year to the last equity value of that year, so
the twelve monthly percentages multiply out to the yearly one.

Periods are bucketed in **UTC**, which is what the bar timestamps are stored in.
That is a deliberate simplification: a month boundary is a reporting convenience,
not a trading decision, and re-bucketing in a session timezone would make the
same run produce different monthly tables on different machines.  The HTML
report states the timezone it used for the same reason.

Everything returned is built from plain Python ``float``/``int``/``None`` so the
structures can be written straight to JSON by the run store.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from ..engine.results import BacktestResult
from .equity import forward_fill

log = logging.getLogger(__name__)

__all__ = ["monthly_returns", "yearly_returns", "daily_returns", "period_returns"]

#: Column order the UI table renders.  January is index 0.
MONTH_NAMES: tuple[str, ...] = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


# --------------------------------------------------------------------------
# Shared machinery
# --------------------------------------------------------------------------

def _series(result: BacktestResult) -> tuple[np.ndarray, np.ndarray, float]:
    """``(ts, equity, base)`` for a result, or empty arrays when it has no curve.

    ``base`` is the equity the first period is measured against: the configured
    starting capital when it is positive, otherwise the first finite equity
    value.  Using starting capital means the first (usually partial) month is
    measured from the account's opening value rather than from wherever the
    curve happened to be at its first bar.
    """
    curves = getattr(result, "curves", None)
    if curves is None or len(curves) == 0:
        return (np.empty(0, dtype="int64"), np.empty(0, dtype="float64"), 0.0)

    ts = np.asarray(curves.ts, dtype="int64")
    equity = np.asarray(curves.equity, dtype="float64")
    if ts.size != equity.size:          # defensive: a hand-built result
        size = min(ts.size, equity.size)
        ts, equity = ts[:size], equity[:size]
    if ts.size and np.any(np.diff(ts) < 0):
        order = np.argsort(ts, kind="stable")
        ts, equity = ts[order], equity[order]

    equity = forward_fill(equity)

    base = 0.0
    try:
        base = float(result.config.starting_capital)
    except (AttributeError, TypeError, ValueError):
        base = 0.0
    if not np.isfinite(base) or base <= 0.0:
        finite = equity[np.isfinite(equity)]
        base = float(finite[0]) if finite.size else 0.0
    return ts, equity, base


def _period_keys(ts: np.ndarray, unit: str) -> np.ndarray:
    """Integer period index per bar: months since epoch, days since epoch, etc."""
    return ts.astype("datetime64[ns]").astype(f"datetime64[{unit}]").astype("int64")


def _last_per_period(ts: np.ndarray, equity: np.ndarray,
                     unit: str) -> tuple[np.ndarray, np.ndarray]:
    """``(period_key, closing_equity)`` for each calendar period present.

    The bars are ascending, so the closing value of a period is the value at the
    last index whose key equals that period -- found by run-length encoding
    rather than by grouping, which keeps this O(n) with no pandas dependency.
    """
    if ts.size == 0:
        return np.empty(0, dtype="int64"), np.empty(0, dtype="float64")
    keys = _period_keys(ts, unit)
    last = np.flatnonzero(np.concatenate((np.diff(keys) != 0, [True])))
    return keys[last], equity[last]


def _chain(closing: np.ndarray, base: float) -> np.ndarray:
    """Percentage change of each period against the previous period's close.

    The first period is measured against ``base``.  A period whose base is zero
    or negative yields NaN: there is no meaningful percentage change from a
    wiped-out account, and inventing one would put an infinity in the table.
    """
    if closing.size == 0:
        return np.empty(0, dtype="float64")
    previous = np.empty(closing.size, dtype="float64")
    previous[0] = base
    previous[1:] = closing[:-1]
    out = np.full(closing.size, np.nan, dtype="float64")
    ok = np.isfinite(previous) & (previous > 0) & np.isfinite(closing)
    np.divide(closing, previous, out=out, where=ok)
    out = np.where(ok, (out - 1.0) * 100.0, np.nan)
    return out


def _clean(value: float) -> float | None:
    """A finite Python float, or ``None`` -- never NaN, never inf."""
    v = float(value)
    return v if np.isfinite(v) else None


def _split_month_key(key: int) -> tuple[int, int]:
    """``months since 1970-01`` -> ``(year, month_index_0_to_11)``."""
    return 1970 + int(key) // 12, int(key) % 12


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def monthly_returns(result: BacktestResult) -> dict[str, Any]:
    """A year-by-month grid of equity returns, ready for the UI table.

    Shape::

        {"years":  [2023, 2024],
         "months": [[jan, feb, ..., dec], [...]],   # percent, None where no data
         "totals": {2023: 12.4, 2024: -3.1},        # percent, keyed by int year
         "counts": {"months": 18, "positive": 11, "negative": 7},
         "best": 8.1, "worst": -6.4, "average": 0.9,
         "month_names": ("Jan", ...)}

    Every value is a percentage (``12.4`` means +12.4%), and ``None`` marks a
    month the run did not cover.  Returned unpopulated -- ``{"years": []}`` and
    friends -- when the result has no equity curve, so callers can render an
    empty table without special-casing.
    """
    ts, equity, base = _series(result)
    empty = _empty_monthly()
    if ts.size == 0 or base <= 0.0:
        return empty

    keys, closing = _last_per_period(ts, equity, "M")
    rets = _chain(closing, base)
    if keys.size == 0:
        return empty

    years = sorted({_split_month_key(int(k))[0] for k in keys})
    row_of = {year: i for i, year in enumerate(years)}
    grid: list[list[float | None]] = [[None] * 12 for _ in years]
    for key, value in zip(keys, rets):
        year, month = _split_month_key(int(key))
        grid[row_of[year]][month] = _clean(value)

    year_keys, year_closing = _last_per_period(ts, equity, "Y")
    year_rets = _chain(year_closing, base)
    totals: dict[int, float | None] = {}
    for key, value in zip(year_keys, year_rets):
        totals[1970 + int(key)] = _clean(value)

    values = [v for row in grid for v in row if v is not None]
    return {
        "years": years,
        "months": grid,
        "totals": totals,
        "month_names": MONTH_NAMES,
        "counts": {
            "months": len(values),
            "positive": sum(1 for v in values if v > 0),
            "negative": sum(1 for v in values if v < 0),
            "flat": sum(1 for v in values if v == 0),
        },
        "best": max(values) if values else None,
        "worst": min(values) if values else None,
        "average": (sum(values) / len(values)) if values else None,
    }


def _empty_monthly() -> dict[str, Any]:
    return {"years": [], "months": [], "totals": {}, "month_names": MONTH_NAMES,
            "counts": {"months": 0, "positive": 0, "negative": 0, "flat": 0},
            "best": None, "worst": None, "average": None}


def yearly_returns(result: BacktestResult) -> dict[str, Any]:
    """Calendar-year returns, with the equity each year opened and closed at.

    Shape::

        {"years": [2023, 2024],
         "returns": [12.4, -3.1],                  # percent, None where unknown
         "totals": {2023: 12.4, 2024: -3.1},
         "rows": [{"year": 2023, "return_pct": 12.4, "start_equity": 100000.0,
                   "end_equity": 112400.0, "net_profit": 12400.0}, ...]}
    """
    ts, equity, base = _series(result)
    if ts.size == 0 or base <= 0.0:
        return {"years": [], "returns": [], "totals": {}, "rows": []}

    keys, closing = _last_per_period(ts, equity, "Y")
    rets = _chain(closing, base)
    opens = np.empty(closing.size, dtype="float64")
    if closing.size:
        opens[0] = base
        opens[1:] = closing[:-1]

    years: list[int] = []
    returns: list[float | None] = []
    totals: dict[int, float | None] = {}
    rows: list[dict[str, Any]] = []
    for i, key in enumerate(keys):
        year = 1970 + int(key)
        value = _clean(rets[i])
        years.append(year)
        returns.append(value)
        totals[year] = value
        rows.append({
            "year": year,
            "return_pct": value,
            "start_equity": _clean(opens[i]),
            "end_equity": _clean(closing[i]),
            "net_profit": (_clean(closing[i] - opens[i])
                           if np.isfinite(closing[i]) and np.isfinite(opens[i])
                           else None),
        })
    return {"years": years, "returns": returns, "totals": totals, "rows": rows}


def daily_returns(result: BacktestResult) -> dict[str, Any]:
    """Per-calendar-day equity returns (UTC days).

    Shape::

        {"dates": ["2023-01-02", ...],       # ISO dates, one per day with bars
         "returns": [0.31, -0.12, ...],      # percent, None where unknown
         "equity": [100310.0, ...],          # closing equity of that day
         "counts": {"days": 250, "positive": 130, "negative": 118, "flat": 2},
         "best": 3.4, "worst": -2.9, "average": 0.04}

    Days on which the market was closed simply do not appear; there is no
    forward-filled row for them, because a flat day the strategy could not have
    traded is not a 0% day, it is no day at all.
    """
    ts, equity, base = _series(result)
    if ts.size == 0 or base <= 0.0:
        return {"dates": [], "returns": [], "equity": [],
                "counts": {"days": 0, "positive": 0, "negative": 0, "flat": 0},
                "best": None, "worst": None, "average": None}

    keys, closing = _last_per_period(ts, equity, "D")
    rets = _chain(closing, base)
    dates = [str(np.datetime64(int(k), "D")) for k in keys]
    values = [_clean(v) for v in rets]
    finite = [v for v in values if v is not None]
    return {
        "dates": dates,
        "returns": values,
        "equity": [_clean(v) for v in closing],
        "counts": {
            "days": len(finite),
            "positive": sum(1 for v in finite if v > 0),
            "negative": sum(1 for v in finite if v < 0),
            "flat": sum(1 for v in finite if v == 0),
        },
        "best": max(finite) if finite else None,
        "worst": min(finite) if finite else None,
        "average": (sum(finite) / len(finite)) if finite else None,
    }


def period_returns(result: BacktestResult, unit: str = "M") -> list[dict[str, Any]]:
    """Returns for an arbitrary calendar bucket -- ``"D"``, ``"M"`` or ``"Y"``.

    The three named functions above are the shapes the UI consumes; this is the
    building block behind them, exposed because reports and future panels want
    the same numbers in a flat list.
    """
    unit = str(unit).upper()
    if unit not in ("D", "M", "Y"):
        unit = "M"
    ts, equity, base = _series(result)
    if ts.size == 0 or base <= 0.0:
        return []
    keys, closing = _last_per_period(ts, equity, unit)
    rets = _chain(closing, base)
    out: list[dict[str, Any]] = []
    for i, key in enumerate(keys):
        stamp = np.datetime64(int(key), unit)
        out.append({"period": str(stamp), "unit": unit,
                    "return_pct": _clean(rets[i]),
                    "end_equity": _clean(closing[i])})
    return out
