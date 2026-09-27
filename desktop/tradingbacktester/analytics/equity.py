"""Equity curves, drawdowns and underwater periods.

Drawdown here is defined on **equity**, not on the closed-trade balance: a
position that is 20% under water is a 20% drawdown whether or not it has been
closed, because that is what the account is worth and what a trader actually
lives through.

Two sign conventions live in this module and they are deliberate:

* the *curve* arrays (:attr:`EquityCurves.drawdown`, ``drawdown_pct``) and the
  per-excursion dictionaries returned here are **negative or zero** -- a
  drawdown is a fall, and the chart draws it downwards;
* the headline ``max_drawdown`` / ``max_drawdown_pct`` metrics in
  :mod:`tradingbacktester.analytics.metrics` are **positive magnitudes**,
  because "max drawdown 18.2%" is how the number is spoken and written.

``drawdown_pct`` on the curve is a *fraction* (``-0.05`` is five percent below
the peak); every ``*_pct`` value in the dictionaries and in the metrics layer is
already multiplied by 100.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from ..core.errors import BacktestError
from ..engine.results import EquityCurves

log = logging.getLogger(__name__)

__all__ = [
    "build_curves",
    "underwater_periods",
    "drawdown_table",
    "max_drawdown",
    "ulcer_index",
    "bar_returns",
    "time_under_water_pct",
    "forward_fill",
]


def forward_fill(values: np.ndarray) -> np.ndarray:
    """Carry the last finite value forward over NaN/inf holes.

    A hole in an equity series is a defect upstream, not a total loss, and it
    must not be allowed to propagate: ``np.maximum.accumulate`` treats NaN as
    the largest value there is, so a single bad bar would otherwise turn the
    running peak -- and therefore every drawdown after it -- into NaN, and the
    run would report a maximum drawdown of zero.  Values before the *first*
    finite value stay non-finite; there is nothing to carry forward yet.
    """
    values = np.asarray(values, dtype="float64")
    valid = np.isfinite(values)
    if valid.all() or not valid.any():
        return values
    idx = np.where(valid, np.arange(values.size), 0)
    np.maximum.accumulate(idx, out=idx)
    filled = values[idx]
    filled[:int(np.argmax(valid))] = np.nan
    return filled


def build_curves(ts, equity, balance=None, exposure=None) -> EquityCurves:
    """Assemble an :class:`EquityCurves` from the per-bar account series.

    ``peak`` is the running maximum of equity, ``drawdown`` is the cash distance
    below it (always ``<= 0``) and ``drawdown_pct`` is that distance as a
    *fraction* of the peak (so ``-0.05`` is a 5% drawdown; the UI multiplies by
    100).

    ``balance`` defaults to a copy of ``equity`` and ``exposure`` to zeros, so a
    caller that only has an equity series -- a test, or a report rebuilding a
    curve from a saved run -- still gets a complete object.

    Raises
    ------
    BacktestError
        If the timestamps and the equity series are different lengths, which
        always means the caller assembled them wrongly and would otherwise
        produce a silently misaligned chart.
    """
    ts = np.ascontiguousarray(ts, dtype="int64")
    equity = np.ascontiguousarray(equity, dtype="float64")
    n = len(equity)
    if len(ts) != n:
        raise BacktestError(
            "The equity curve and its timestamps have different lengths.",
            detail=f"ts={len(ts)} equity={n}")

    balance = (np.ascontiguousarray(balance, dtype="float64")
               if balance is not None else equity.copy())
    exposure = (np.ascontiguousarray(exposure, dtype="float64")
                if exposure is not None else np.zeros(n, dtype="float64"))
    if len(balance) != n:
        raise BacktestError(
            "The balance curve does not match the equity curve.",
            detail=f"balance={len(balance)} equity={n}")
    if len(exposure) != n:
        raise BacktestError(
            "The exposure series does not match the equity curve.",
            detail=f"exposure={len(exposure)} equity={n}")

    if n == 0:
        empty = np.empty(0, dtype="float64")
        return EquityCurves(ts=ts, equity=empty, balance=empty, drawdown=empty,
                            drawdown_pct=empty, exposure=empty, peak=empty)

    # The peak and the drawdown are derived from a hole-free copy of the equity
    # series (see forward_fill); ``equity`` itself is stored exactly as supplied
    # so the chart draws what the engine produced.
    usable_equity = forward_fill(equity)
    if not np.isfinite(equity).all():
        log.warning("Equity curve contains %d non-finite values; drawdowns are "
                    "measured against the last valid equity before each hole.",
                    int((~np.isfinite(equity)).sum()))

    peak = np.maximum.accumulate(usable_equity)
    drawdown = usable_equity - peak
    # A peak of zero or below cannot be expressed as a percentage; report no
    # percentage drawdown there rather than dividing and producing an infinity
    # that would then dominate every summary statistic.
    drawdown_pct = np.zeros(n, dtype="float64")
    usable = peak > 0
    np.divide(drawdown, peak, out=drawdown_pct, where=usable)

    return EquityCurves(ts=ts, equity=equity, balance=balance, drawdown=drawdown,
                        drawdown_pct=drawdown_pct, exposure=exposure, peak=peak)


def underwater_periods(curves: EquityCurves | None) -> list[dict[str, Any]]:
    """Every excursion below the previous equity peak, in order of occurrence.

    A period starts on the first bar below a peak and ends on the last bar
    before the peak is regained; ``end_ts``/``end_index`` name the bar that
    regained it.  A period still under water at the last bar is returned with
    ``end_ts`` and ``recovery_bars`` set to ``None``, because calling an
    unrecovered drawdown "recovered at the end of the data" is exactly the kind
    of quiet flattery this application avoids.

    Each dictionary carries:

    ``start_index`` / ``start`` / ``start_ts``
        First bar below the peak.  ``start`` is an alias of ``start_index``.
    ``trough_index`` / ``trough_ts``
        Bar at which the fall was deepest.
    ``end_index`` / ``end`` / ``end_ts``
        Bar that regained the peak, or ``None`` if it never did.
    ``length_bars`` / ``length``
        Bars spent below the peak, trough included, recovery bar excluded.
    ``recovery_bars``
        Bars from the trough to the recovery bar, or ``None``.
    ``depth`` / ``depth_pct``
        Cash fall (negative) and the same fall as a percentage of the peak
        (negative).
    ``peak_equity`` / ``trough_equity``
        The two equity values the fall is measured between.
    """
    if curves is None or len(curves) == 0:
        return []

    under = np.asarray(curves.drawdown, dtype="float64") < 0
    if not under.any():
        return []

    # Run-length encode the boolean instead of walking it in Python: the curve
    # can be millions of bars long and this is called on every result shown.
    edges = np.flatnonzero(np.diff(under.astype(np.int8)))
    starts = edges[under[edges + 1]] + 1
    ends = edges[under[edges]] + 1          # first bar back above the peak
    if under[0]:
        starts = np.concatenate(([0], starts))

    periods: list[dict[str, Any]] = []
    n = len(curves)
    for k, start in enumerate(starts):
        recovered_at = int(ends[k]) if k < len(ends) else None
        last = (recovered_at - 1) if recovered_at is not None else n - 1
        periods.append(_period(curves, int(start), int(last), recovered_at))
    return periods


def _period(curves: EquityCurves, start: int, end: int,
            recovered_at: int | None) -> dict[str, Any]:
    """One excursion, described in both bar indices and timestamps."""
    window = curves.drawdown[start:end + 1]
    trough = int(start + np.argmin(window))
    length = int(end - start + 1)
    return {
        "start_index": start,
        "start": start,
        "trough_index": trough,
        "end_index": recovered_at,
        "end": recovered_at,
        "start_ts": int(curves.ts[start]),
        "trough_ts": int(curves.ts[trough]),
        "end_ts": int(curves.ts[recovered_at]) if recovered_at is not None else None,
        "depth": float(curves.drawdown[trough]),
        "depth_pct": float(curves.drawdown_pct[trough] * 100.0),
        "length_bars": length,
        "length": length,
        "recovery_bars": (int(recovered_at - trough)
                          if recovered_at is not None else None),
        "peak_equity": float(curves.peak[trough]),
        "trough_equity": float(curves.equity[trough]),
        "recovered": recovered_at is not None,
    }


def drawdown_table(curves: EquityCurves | None, top: int = 10) -> list[dict[str, Any]]:
    """The ``top`` deepest drawdowns, deepest first.

    Sorted by cash depth, which is negative, so an ordinary ascending sort puts
    the worst excursion at the top.
    """
    periods = underwater_periods(curves)
    periods.sort(key=lambda p: p["depth"])
    return periods[:max(0, int(top))]


def max_drawdown(curves: EquityCurves | None) -> dict[str, Any]:
    """The single worst drawdown, with the timestamps that bracket it.

    ``depth`` and ``depth_pct`` are negative here, matching the curve arrays.
    The metrics layer reports their magnitudes.
    """
    blank: dict[str, Any] = {
        "depth": 0.0, "depth_pct": 0.0, "duration_bars": 0, "start_index": None,
        "trough_index": None, "end_index": None, "start_ts": None,
        "trough_ts": None, "end_ts": None, "recovery_bars": None,
        "peak_equity": None, "trough_equity": None,
    }
    if curves is None or len(curves) == 0:
        return blank
    worst = drawdown_table(curves, top=1)
    if not worst:
        return blank
    p = worst[0]
    return {
        "depth": p["depth"], "depth_pct": p["depth_pct"],
        "duration_bars": p["length_bars"], "start_index": p["start_index"],
        "trough_index": p["trough_index"], "end_index": p["end_index"],
        "start_ts": p["start_ts"], "trough_ts": p["trough_ts"],
        "end_ts": p["end_ts"], "recovery_bars": p["recovery_bars"],
        "peak_equity": p["peak_equity"], "trough_equity": p["trough_equity"],
    }


def ulcer_index(curves: EquityCurves | None) -> float:
    """Root mean square of the percentage drawdown series.

    Unlike maximum drawdown it accounts for how *long* the account spent below
    its peak, not just how far it fell once: two strategies with the same worst
    fall are separated by how quickly each climbed back out of it.
    """
    if curves is None or len(curves) == 0:
        return 0.0
    pct = np.asarray(curves.drawdown_pct, dtype="float64") * 100.0
    pct = pct[np.isfinite(pct)]
    if pct.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(pct))))


def time_under_water_pct(curves: EquityCurves | None) -> float:
    """Percentage of bars spent below the previous equity peak."""
    if curves is None or len(curves) == 0:
        return 0.0
    under = np.asarray(curves.drawdown, dtype="float64") < 0
    return float(under.mean() * 100.0)


def bar_returns(curves: EquityCurves | None) -> np.ndarray:
    """Simple per-bar equity returns, guarded against a zero or negative base.

    Returns an array one shorter than the curve.  Bars whose *previous* equity
    was zero or negative contribute a zero return: an account that has been
    wiped out has no meaningful percentage change, and emitting an infinity
    there would poison every moment computed from the series.
    """
    if curves is None or len(curves) < 2:
        return np.empty(0, dtype="float64")
    equity = np.asarray(curves.equity, dtype="float64")
    prev = equity[:-1]
    out = np.zeros(len(equity) - 1, dtype="float64")
    ok = prev > 0
    np.divide(equity[1:] - prev, prev, out=out, where=ok)
    return np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)
