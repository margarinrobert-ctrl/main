"""How much of a book is actually one bet.

Running five strategies is not running five bets.  If they turn out to be the
same trade wearing different indicators, the book has one bet at five times the
size, and every diversification number computed from it -- the smoother
combined equity curve, the lower combined drawdown -- is describing an
arithmetic accident rather than a property of the strategies.

This module measures the overlap three ways, because return correlation alone
misses the two ways strategies are most often secretly identical:

* **Return correlation** over a common calendar.  The familiar number, and the
  one that feeds portfolio arithmetic.
* **Exposure overlap** -- the share of bars on which both were in the market at
  once, and of those, how often on the same side.  Two strategies can have a
  low return correlation simply because their position sizes differ while
  they hold the same view at the same moments.
* **Entry coincidence** -- the share of one strategy's entries that land within
  a few bars of the other's.  This is what catches "the same signal, one bar
  apart", which the other two both dilute.

The summary number is the **effective number of independent bets**, computed
from the eigenvalues of the correlation matrix.  Five strategies at an average
pairwise correlation of 0.8 is about 1.4 independent bets, and saying so is
more useful than printing twenty-five numbers.

One thing this module will not do is tell you a low correlation is good news.
A decorrelated leg still has to have an edge of its own: adding a coin flip at
low correlation raises a book's net profit and destroys its Sharpe, and a
correlation matrix on its own will happily talk you into that trade.  Every
report here therefore carries the per-strategy result beside the correlation,
and :meth:`CorrelationReport.describe` refuses to recommend anything.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from ..core.errors import BacktestError

log = logging.getLogger(__name__)

__all__ = ["StrategySeries", "PairOverlap", "CorrelationReport",
           "correlate_results", "series_from_result"]

#: Entries this many bars apart or fewer count as the same signal.  One bar
#: covers the common case of two rules firing on either side of a close; more
#: than a handful stops meaning "the same signal" at all.
ENTRY_WINDOW_BARS = 2

#: Below this many shared periods a correlation is noise dressed as a number.
MIN_OVERLAP = 20


@dataclass(frozen=True)
class StrategySeries:
    """One strategy's results, reduced to what a correlation needs."""

    name: str
    ts: np.ndarray
    """Period-end timestamps, ascending, in nanoseconds."""
    returns: np.ndarray
    """Per-period return of equity, aligned with ``ts``."""
    net_profit: float
    entry_ts: np.ndarray = field(default_factory=lambda: np.empty(0, "int64"))
    exposure_ts: np.ndarray = field(default_factory=lambda: np.empty(0, "int64"))
    """Bar timestamps on which a position was open."""
    exposure_side: np.ndarray = field(default_factory=lambda: np.empty(0, "int8"))
    """``+1`` long, ``-1`` short, aligned with ``exposure_ts``."""
    trades: int = 0


@dataclass(frozen=True)
class PairOverlap:
    """Everything measured about one pair of strategies."""

    a: str
    b: str
    correlation: float | None
    """Pearson on the shared calendar, or None when too little is shared."""
    shared_periods: int
    exposure_overlap: float | None
    """Share of the bars either was in the market on which both were."""
    same_side_share: float | None
    """Of the bars both were in the market, the share on the same side."""
    entry_coincidence: float | None
    """Share of the rarer strategy's entries within ``ENTRY_WINDOW_BARS``."""

    def describe(self) -> str:
        if self.correlation is None:
            return (f"{self.a} and {self.b}: only {self.shared_periods} shared "
                    f"periods, too few to correlate")
        parts = [f"{self.a} and {self.b}: correlation "
                 f"{self.correlation:+.2f} over {self.shared_periods} periods"]
        if self.exposure_overlap is not None:
            parts.append(f"in the market together {self.exposure_overlap:.0%} "
                         f"of the time")
        if self.same_side_share is not None:
            parts.append(f"same side {self.same_side_share:.0%} of that")
        if self.entry_coincidence is not None:
            parts.append(f"{self.entry_coincidence:.0%} of entries coincide")
        return ", ".join(parts)


@dataclass(frozen=True)
class CorrelationReport:
    """The matrix, the pairs, and how many independent bets they amount to."""

    names: tuple[str, ...]
    matrix: np.ndarray
    """Square, symmetric, 1.0 on the diagonal.  NaN where too little is shared."""
    pairs: tuple[PairOverlap, ...]
    effective_bets: float | None
    """Eigenvalue-based count of independent bets among these strategies."""
    net_profit: tuple[float, float, ...] = ()
    trades: tuple[int, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def count(self) -> int:
        return len(self.names)

    def pair(self, a: str, b: str) -> PairOverlap | None:
        for p in self.pairs:
            if {p.a, p.b} == {a, b}:
                return p
        return None

    def most_alike(self, n: int = 3) -> list[PairOverlap]:
        rated = [p for p in self.pairs if p.correlation is not None]
        return sorted(rated, key=lambda p: -abs(p.correlation))[:n]

    def least_alike(self, n: int = 3) -> list[PairOverlap]:
        rated = [p for p in self.pairs if p.correlation is not None]
        return sorted(rated, key=lambda p: abs(p.correlation))[:n]

    def describe(self) -> str:
        """A paragraph that states what was measured and nothing more."""
        if self.count < 2:
            return "Correlation needs at least two strategies."
        lines: list[str] = []
        if self.effective_bets is not None:
            lines.append(
                f"{self.count} strategies amount to about "
                f"{self.effective_bets:.1f} independent bets.")
            if self.effective_bets < self.count * 0.6:
                lines.append(
                    "Most of the apparent diversification is arithmetic: these "
                    "are largely the same position.")
        lines.append("Most alike:")
        lines += [f"  • {p.describe()}" for p in self.most_alike()]
        lines.append("Least alike:")
        lines += [f"  • {p.describe()}" for p in self.least_alike()]
        lines.append(
            "A low correlation is not on its own a reason to add a strategy. "
            "A decorrelated leg with no edge of its own still raises a book's "
            "net profit while cutting its Sharpe and deepening its drawdown, "
            "and nothing in this table would show that. Read each strategy's "
            "own result beside its correlation.")
        lines += [f"NOTE: {n}" for n in self.notes]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# building a series from a run
# ---------------------------------------------------------------------------

def _period_key(ts: np.ndarray, unit: str) -> np.ndarray:
    """Bucket nanosecond timestamps into days, weeks or months."""
    days = ts.astype("int64") // 86_400_000_000_000
    if unit == "day":
        return days
    if unit == "week":
        return days // 7
    if unit == "month":
        as_dt = ts.astype("datetime64[ns]").astype("datetime64[M]")
        return as_dt.astype("int64")
    raise BacktestError(f"'{unit}' is not a period this can correlate on.")


def series_from_result(result: Any, *, unit: str = "day") -> StrategySeries:
    """Reduce one :class:`BacktestResult` to a :class:`StrategySeries`.

    Returns are computed on the **last equity value of each period**, which is
    what a daily correlation of two intraday strategies has to mean; comparing
    them bar by bar would instead measure how often they happened to be
    sampled at the same minute.
    """
    curves = getattr(result, "curves", None)
    name = getattr(result, "strategy_name", "") or getattr(result, "label", "?")
    if curves is None or curves.ts is None or len(curves.ts) < 2:
        return StrategySeries(name, np.empty(0, "int64"), np.empty(0, "float64"),
                              0.0)

    ts = np.asarray(curves.ts, dtype="int64")
    equity = np.asarray(curves.equity, dtype="float64")
    keys = _period_key(ts, unit)
    # The last row of each period, which is that period's close.
    last = np.flatnonzero(np.diff(keys)) if keys.size > 1 else np.empty(0, "int64")
    idx = np.concatenate([last, [keys.size - 1]]).astype("int64")
    closes = equity[idx]
    period_ts = ts[idx]

    with np.errstate(divide="ignore", invalid="ignore"):
        returns = np.diff(closes) / np.abs(closes[:-1])
    returns = np.where(np.isfinite(returns), returns, 0.0)
    period_ts = period_ts[1:]

    trades = list(getattr(result, "trades", []) or [])
    entry_ts = np.asarray([t.entry_ts for t in trades], dtype="int64")

    exposure_ts, exposure_side = _exposure(result, ts)
    net = float(getattr(result, "metrics", {}).get("net_profit", 0.0) or 0.0)
    return StrategySeries(name=name, ts=period_ts, returns=returns,
                          net_profit=net, entry_ts=entry_ts,
                          exposure_ts=exposure_ts, exposure_side=exposure_side,
                          trades=len(trades))


def _exposure(result: Any, ts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Bar timestamps a position was open on, and which way it faced."""
    trades = list(getattr(result, "trades", []) or [])
    if not trades or ts.size == 0:
        return np.empty(0, "int64"), np.empty(0, "int8")
    side = np.zeros(ts.size, dtype="int8")
    for trade in trades:
        start = int(np.searchsorted(ts, int(trade.entry_ts), side="left"))
        stop = int(np.searchsorted(ts, int(trade.exit_ts), side="right"))
        if stop <= start:
            stop = start + 1
        direction = 1 if str(trade.side).lower().endswith("long") else -1
        side[start:min(stop, ts.size)] = direction
    held = side != 0
    return ts[held], side[held]


# ---------------------------------------------------------------------------
# the pairwise measurements
# ---------------------------------------------------------------------------

def _align(a: StrategySeries, b: StrategySeries) -> tuple[np.ndarray, np.ndarray]:
    """The two return vectors on the timestamps they share."""
    shared, ia, ib = np.intersect1d(a.ts, b.ts, return_indices=True)
    return a.returns[ia], b.returns[ib]


def _pearson(x: np.ndarray, y: np.ndarray) -> float | None:
    if x.size < MIN_OVERLAP:
        return None
    sx, sy = float(x.std()), float(y.std())
    if sx <= 0.0 or sy <= 0.0:
        return None
    value = float(np.corrcoef(x, y)[0, 1])
    return value if math.isfinite(value) else None


def _exposure_overlap(a: StrategySeries, b: StrategySeries
                      ) -> tuple[float | None, float | None]:
    if a.exposure_ts.size == 0 or b.exposure_ts.size == 0:
        return None, None
    both, ia, ib = np.intersect1d(a.exposure_ts, b.exposure_ts,
                                  return_indices=True)
    either = np.union1d(a.exposure_ts, b.exposure_ts).size
    if either == 0:
        return None, None
    overlap = both.size / either
    if both.size == 0:
        return overlap, None
    same = float(np.mean(a.exposure_side[ia] == b.exposure_side[ib]))
    return overlap, same


def _entry_coincidence(a: StrategySeries, b: StrategySeries,
                       tolerance_ns: int) -> float | None:
    """Share of the rarer strategy's entries near one of the other's."""
    if a.entry_ts.size == 0 or b.entry_ts.size == 0:
        return None
    few, many = ((a.entry_ts, b.entry_ts) if a.entry_ts.size <= b.entry_ts.size
                 else (b.entry_ts, a.entry_ts))
    many = np.sort(many)
    pos = np.searchsorted(many, few)
    before = many[np.clip(pos - 1, 0, many.size - 1)]
    after = many[np.clip(pos, 0, many.size - 1)]
    nearest = np.minimum(np.abs(few - before), np.abs(few - after))
    return float(np.mean(nearest <= tolerance_ns))


def _effective_bets(matrix: np.ndarray) -> float | None:
    """Independent bets implied by a correlation matrix.

    ``(sum of eigenvalues)^2 / sum of squared eigenvalues`` -- the participation
    ratio.  It is ``n`` for ``n`` uncorrelated strategies and falls towards 1 as
    they converge on the same position.
    """
    if matrix.size == 0 or not np.isfinite(matrix).all():
        return None
    try:
        values = np.linalg.eigvalsh(matrix)
    except np.linalg.LinAlgError:               # pragma: no cover - degenerate
        return None
    values = np.clip(values, 0.0, None)
    total = float(values.sum())
    squared = float((values ** 2).sum())
    if squared <= 0.0:
        return None
    return total * total / squared


def correlate_results(results: Sequence[Any], *, unit: str = "day",
                      timeframe_seconds: float | None = None
                      ) -> CorrelationReport:
    """Measure how much of a set of runs is really one bet.

    ``results`` are :class:`BacktestResult` objects, or anything with the same
    ``curves``/``trades``/``metrics`` shape.  ``unit`` is the calendar the
    returns are correlated on -- daily by default, because two intraday
    strategies correlated bar by bar mostly measure their shared sampling.
    """
    if len(results) < 2:
        raise BacktestError(
            "Correlation needs at least two runs. One strategy is not a book.")

    series = [series_from_result(r, unit=unit) for r in results]
    names = _unique_names([s.name for s in series])
    n = len(series)

    step = timeframe_seconds
    if step is None:
        step = _infer_step(series)
    tolerance = int(ENTRY_WINDOW_BARS * (step or 60.0) * 1_000_000_000)

    matrix = np.full((n, n), np.nan, dtype="float64")
    np.fill_diagonal(matrix, 1.0)
    pairs: list[PairOverlap] = []
    notes: list[str] = []

    for i in range(n):
        for j in range(i + 1, n):
            x, y = _align(series[i], series[j])
            rho = _pearson(x, y)
            if rho is not None:
                matrix[i, j] = matrix[j, i] = rho
            overlap, same = _exposure_overlap(series[i], series[j])
            pairs.append(PairOverlap(
                a=names[i], b=names[j], correlation=rho,
                shared_periods=int(x.size), exposure_overlap=overlap,
                same_side_share=same,
                entry_coincidence=_entry_coincidence(series[i], series[j],
                                                     tolerance)))

    usable = matrix.copy()
    if not np.isfinite(usable).all():
        missing = int(np.count_nonzero(~np.isfinite(usable)) // 2)
        notes.append(
            f"{missing} pair{'' if missing == 1 else 's'} shared fewer than "
            f"{MIN_OVERLAP} periods, so they are left out of the independent-"
            f"bet count rather than assumed uncorrelated.")
        usable = np.where(np.isfinite(usable), usable, 0.0)
        np.fill_diagonal(usable, 1.0)

    return CorrelationReport(
        names=tuple(names), matrix=matrix, pairs=tuple(pairs),
        effective_bets=_effective_bets(usable),
        net_profit=tuple(s.net_profit for s in series),
        trades=tuple(s.trades for s in series), notes=tuple(notes))


def _infer_step(series: Sequence[StrategySeries]) -> float:
    """Median spacing of whichever series has the most exposure bars."""
    best = max(series, key=lambda s: s.exposure_ts.size, default=None)
    if best is None or best.exposure_ts.size < 3:
        return 60.0
    gaps = np.diff(best.exposure_ts.astype("float64"))
    gaps = gaps[gaps > 0]
    if gaps.size == 0:
        return 60.0
    return float(np.median(gaps)) / 1e9


def _unique_names(names: Sequence[str]) -> list[str]:
    """Two runs of the same strategy must not collapse into one row."""
    seen: dict[str, int] = {}
    out: list[str] = []
    for name in names:
        base = name or "unnamed"
        if base in seen:
            seen[base] += 1
            out.append(f"{base} ({seen[base]})")
        else:
            seen[base] = 1
            out.append(base)
    return out
