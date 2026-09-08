"""Side-by-side comparison of several backtest runs.

Two runs are only comparable to the extent that they saw the same market.  This
module therefore does three things and says out loud when it cannot do them:

* builds a metric matrix, marking which run is best **only** for metrics where
  "best" is well defined (net profit yes, trade count no) and never awarding it
  to a run whose own analytics flagged that metric as unavailable;
* indexes every equity curve to 100 at the **first timestamp all the runs
  share**, so the lines start together and a run that simply had more history
  does not look like a better strategy;
* writes an ``align_note`` describing any date-range mismatch, because the
  usual reason one curve ends higher than another is that it ran for longer.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from ..core.errors import BacktesterError, BacktestError
from ..engine.results import BacktestResult
from .metrics import compute_metrics

log = logging.getLogger(__name__)

__all__ = ["ComparisonRow", "ComparisonCurve", "ComparisonTable",
           "compare_results", "COMPARISON_METRICS"]

#: ``(key, label, kind, direction)``.  ``direction`` is ``"max"`` when bigger is
#: better, ``"min"`` when smaller is, and ``None`` when the metric describes the
#: run rather than judging it -- there is no "best" number of trades, and a run
#: that was in the market more of the time is not thereby better.
COMPARISON_METRICS: tuple[tuple[str, str, str, str | None], ...] = (
    ("net_profit", "Net profit", "money", "max"),
    ("return_pct", "Return %", "pct", "max"),
    ("cagr", "CAGR %", "pct", "max"),
    ("max_drawdown", "Max drawdown", "money", "min"),
    ("max_drawdown_pct", "Max drawdown %", "pct", "min"),
    ("max_drawdown_duration_bars", "Longest drawdown (bars)", "int", "min"),
    ("recovery_factor", "Recovery factor", "ratio", "max"),
    ("profit_factor", "Profit factor", "ratio", "max"),
    ("expectancy", "Expectancy", "money", "max"),
    ("expectancy_r", "Expectancy (R)", "ratio", "max"),
    ("sharpe_ratio", "Sharpe ratio", "ratio", "max"),
    ("sortino_ratio", "Sortino ratio", "ratio", "max"),
    ("calmar_ratio", "Calmar ratio", "ratio", "max"),
    ("annual_volatility_pct", "Annual volatility %", "pct", "min"),
    ("ulcer_index", "Ulcer index", "ratio", "min"),
    ("sqn", "System quality (SQN)", "ratio", "max"),
    ("win_rate", "Win rate %", "pct", "max"),
    ("payoff_ratio", "Payoff ratio", "ratio", "max"),
    ("total_trades", "Trades", "int", None),
    ("winning_trades", "Winners", "int", None),
    ("losing_trades", "Losers", "int", None),
    ("max_consecutive_losses", "Max consecutive losses", "int", "min"),
    ("avg_bars_held", "Average bars held", "float", None),
    ("trades_per_year", "Trades per year", "float", None),
    ("exposure_pct", "Bars in market %", "pct", None),
    ("total_costs", "Total costs", "money", "min"),
    ("long_trades", "Long trades", "int", None),
    ("short_trades", "Short trades", "int", None),
    ("best_month_pct", "Best month %", "pct", "max"),
    ("worst_month_pct", "Worst month %", "pct", "max"),
    ("profitable_months_pct", "Profitable months %", "pct", "max"),
)


@dataclass
class ComparisonRow:
    """One metric across every run."""

    key: str
    label: str
    kind: str
    """``money``, ``pct``, ``ratio``, ``int`` or ``float`` -- how to format it."""
    values: list[Any]
    """One entry per run, in the order the runs were given.  ``None`` where the
    run does not report that metric."""
    reliability: list[str]
    """The per-run reliability state (``ok``/``low_sample``/``unavailable``)."""
    best_index: int | None = None
    """Index of the winning run, or ``None`` when "best" is not well defined,
    when fewer than two runs were supplied, or when no run produced a finite
    value that its own analytics stood behind."""
    higher_is_better: bool | None = None
    note: str = ""

    def best_label(self, labels: Sequence[str]) -> str:
        if self.best_index is None or self.best_index >= len(labels):
            return ""
        return str(labels[self.best_index])


@dataclass
class ComparisonCurve:
    """One run's equity curve, indexed to 100 at the common start."""

    label: str
    ts: np.ndarray
    values: np.ndarray
    """Equity as an index: 100 at ``base_ts``."""
    base_ts: int | None = None
    base_equity: float = 0.0
    final_index: float = 100.0

    def __len__(self) -> int:
        return len(self.ts)


@dataclass
class ComparisonTable:
    """The full comparison: labels, metric rows, indexed curves and a caveat."""

    labels: list[str] = field(default_factory=list)
    rows: list[ComparisonRow] = field(default_factory=list)
    equity_curves: list[ComparisonCurve] = field(default_factory=list)
    align_note: str = ""
    common_start_ts: int | None = None
    common_end_ts: int | None = None
    overlapping: bool = True
    run_count: int = 0

    def row(self, key: str) -> ComparisonRow | None:
        for row in self.rows:
            if row.key == key:
                return row
        return None

    def wins(self) -> list[int]:
        """How many decidable metrics each run won.

        Not a score to rank strategies by -- the metrics are correlated and the
        list is arbitrary -- but a useful summary line under the table.
        """
        counts = [0] * len(self.labels)
        for row in self.rows:
            if row.best_index is not None and row.best_index < len(counts):
                counts[row.best_index] += 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        """A JSON-safe view, for saving a comparison or handing it to a report."""
        return {
            "labels": list(self.labels),
            "align_note": self.align_note,
            "common_start_ts": self.common_start_ts,
            "common_end_ts": self.common_end_ts,
            "overlapping": self.overlapping,
            "run_count": self.run_count,
            "wins": self.wins(),
            "rows": [{"key": r.key, "label": r.label, "kind": r.kind,
                      "values": list(r.values), "reliability": list(r.reliability),
                      "best_index": r.best_index,
                      "higher_is_better": r.higher_is_better, "note": r.note}
                     for r in self.rows],
            "curves": [{"label": c.label, "base_ts": c.base_ts,
                        "base_equity": c.base_equity,
                        "final_index": c.final_index, "points": len(c)}
                       for c in self.equity_curves],
        }


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def compare_results(results: Sequence[BacktestResult]) -> ComparisonTable:
    """Build a :class:`ComparisonTable` from two or more runs.

    A single run is accepted and produces a table with no winners marked, which
    is what an interface wants while the user is still choosing the second run.
    An empty list produces an empty table rather than an exception.

    Raises
    ------
    BacktestError
        If an item in the list is not a backtest result.
    """
    runs = list(results or [])
    for item in runs:
        if not hasattr(item, "curves") or not hasattr(item, "metrics"):
            raise BacktestError(
                "Only backtest results can be compared.",
                detail=f"Got {type(item).__name__}")

    table = ComparisonTable(run_count=len(runs))
    if not runs:
        table.align_note = "There is nothing to compare yet."
        return table

    table.labels = _labels(runs)
    metric_sets = [_metrics_for(run) for run in runs]
    table.rows = _rows(metric_sets, len(runs))
    _curves(table, runs)
    return table


# --------------------------------------------------------------------------
# Internals
# --------------------------------------------------------------------------

def _labels(runs: Sequence[BacktestResult]) -> list[str]:
    """A short, unique name per run.  Duplicates get a numeric suffix."""
    labels: list[str] = []
    seen: dict[str, int] = {}
    for i, run in enumerate(runs, start=1):
        base = (str(getattr(run, "label", "") or "").strip()
                or str(getattr(run, "strategy_name", "") or "").strip()
                or str(getattr(run, "run_id", "") or "").strip()
                or f"Run {i}")
        count = seen.get(base, 0) + 1
        seen[base] = count
        labels.append(base if count == 1 else f"{base} ({count})")
    return labels


def _metrics_for(run: BacktestResult) -> dict[str, Any]:
    """The run's metrics, computed on demand when the run was never analysed."""
    existing = getattr(run, "metrics", None)
    if existing:
        return dict(existing)
    try:
        return compute_metrics(run)
    except BacktesterError as exc:
        log.warning("Could not compute metrics for a compared run: %s", exc)
        return {}


def _numeric(value: Any) -> float | None:
    """Finite float, or ``None``.  Infinities are excluded from comparisons.

    An infinite profit factor means a run with no losing trades; it is not
    evidence that the run is better, so it never wins a row.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _rows(metric_sets: Sequence[dict[str, Any]], n_runs: int) -> list[ComparisonRow]:
    rows: list[ComparisonRow] = []
    for key, label, kind, direction in COMPARISON_METRICS:
        values = [m.get(key) for m in metric_sets]
        states = [str((m.get("reliability") or {}).get(key, "ok")) if m else "unavailable"
                  for m in metric_sets]
        if all(v is None for v in values):
            continue

        best: int | None = None
        note = ""
        if direction is not None and n_runs > 1:
            candidates = [(i, _numeric(v)) for i, v in enumerate(values)]
            usable = [(i, v) for i, v in candidates
                      if v is not None and states[i] != "unavailable"]
            if usable:
                pick = max if direction == "max" else min
                best = pick(usable, key=lambda pair: pair[1])[0]
                if any(states[i] == "low_sample" for i, _v in usable):
                    note = ("At least one run is flagged as a small sample on this "
                            "metric; the winner may not be a real difference.")
            else:
                note = ("No run produced a value for this metric that its own "
                        "analytics could stand behind.")
        elif direction is None:
            note = "Descriptive: there is no better or worse value here."
        elif n_runs < 2:
            note = "Only one run: there is nothing to be better than."

        rows.append(ComparisonRow(
            key=key, label=label, kind=kind, values=values, reliability=states,
            best_index=best,
            higher_is_better=(None if direction is None else direction == "max"),
            note=note))
    return rows


def _curve_arrays(run: BacktestResult) -> tuple[np.ndarray, np.ndarray]:
    curves = getattr(run, "curves", None)
    if curves is None or len(curves) == 0:
        return np.empty(0, dtype="int64"), np.empty(0, dtype="float64")
    ts = np.asarray(curves.ts, dtype="int64")
    equity = np.asarray(curves.equity, dtype="float64")
    size = min(ts.size, equity.size)
    return ts[:size], equity[:size]


def _stamp(ts: int | None) -> str:
    """``2023-01-02 09:30 UTC`` for a nanosecond timestamp."""
    if ts is None:
        return "unknown"
    try:
        return str(np.datetime64(int(ts), "ns").astype("datetime64[m]")).replace(
            "T", " ") + " UTC"
    except (ValueError, OverflowError):        # pragma: no cover - defensive
        return "unknown"


def _curves(table: ComparisonTable, runs: Sequence[BacktestResult]) -> None:
    """Index every curve to 100 at the first timestamp the runs share."""
    series = [_curve_arrays(run) for run in runs]
    have = [i for i, (ts, _eq) in enumerate(series) if ts.size > 0]
    missing = [table.labels[i] for i in range(len(runs)) if i not in have]

    if not have:
        table.align_note = ("None of these runs carries an equity curve, so only "
                            "the metric table can be compared.")
        return

    starts = [int(series[i][0][0]) for i in have]
    ends = [int(series[i][0][-1]) for i in have]
    common_start = max(starts)
    common_end = min(ends)
    table.common_start_ts = common_start
    table.common_end_ts = common_end
    table.overlapping = common_start <= common_end

    notes: list[str] = []
    for i in have:
        ts, equity = series[i]
        if table.overlapping:
            at = int(np.searchsorted(ts, common_start, side="left"))
            at = min(max(at, 0), ts.size - 1)
        else:
            at = 0
        base = float(equity[at])
        if not math.isfinite(base) or base <= 0:
            positive = np.flatnonzero(np.isfinite(equity) & (equity > 0))
            if positive.size == 0:
                notes.append(f"{table.labels[i]} has no positive equity to index "
                             f"against and is not drawn.")
                continue
            at = int(positive[0])
            base = float(equity[at])

        with np.errstate(divide="ignore", invalid="ignore"):
            indexed = np.where(np.isfinite(equity), equity / base * 100.0, np.nan)
        indexed = np.nan_to_num(indexed, nan=100.0, posinf=100.0, neginf=0.0)
        table.equity_curves.append(ComparisonCurve(
            label=table.labels[i], ts=ts, values=indexed,
            base_ts=int(ts[at]), base_equity=base,
            final_index=float(indexed[-1]) if indexed.size else 100.0))

    spans = {(int(series[i][0][0]), int(series[i][0][-1])) for i in have}
    if not table.overlapping:
        notes.insert(0, (
            "These runs do not overlap in time: the earliest common bar comes "
            f"after the last bar of another run. Each curve is indexed to 100 at "
            f"its own first bar, so compare their shapes, not their endpoints."))
    elif len(spans) > 1:
        detail = "; ".join(
            f"{table.labels[i]} {_stamp(int(series[i][0][0]))} to "
            f"{_stamp(int(series[i][0][-1]))}"
            for i in have)
        notes.insert(0, (
            f"The runs cover different date ranges ({detail}). Every curve is "
            f"indexed to 100 at {_stamp(common_start)}, the first bar they all "
            f"share, but the metric table above still describes each run over its "
            f"own full range."))
    else:
        notes.insert(0, (f"All runs cover {_stamp(common_start)} to "
                         f"{_stamp(common_end)}. Curves are indexed to 100 at the "
                         f"first bar."))

    if missing:
        notes.append("No equity curve for: " + ", ".join(missing) + ".")
    table.align_note = " ".join(notes)
