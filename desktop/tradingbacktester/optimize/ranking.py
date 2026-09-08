"""Ranking a sweep, and saying out loud how much to trust the winner.

Sorting a grid by net profit takes three lines.  The rest of this module exists
because the top row of that sort is the single most misleading number the
application can show: on any historical sample the best combination is the one
that fitted that sample's noise best, and it is chosen from hundreds of
candidates, so its advantage over the median is mostly selection.

Two defences are offered here, and the optimiser dialog shows both.

:func:`neighbourhood_mean` scores each combination by how its *neighbours* did.
A parameter set whose immediate neighbours are also good sits on a plateau: the
edge, if there is one, does not depend on hitting an exact number.  One that
towers over its neighbours is a spike, and a spike is what over-fitting looks
like from the inside.

:func:`overfitting_note` turns the shape of the whole grid into a sentence a
user can act on.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import numpy as np

from ..logging_setup import get_logger
from .runner import OptimizationResults, OptimizationRow

log = get_logger(__name__)


@dataclass(frozen=True)
class RankingMetric:
    """One choice in the optimiser's "rank by" combo."""

    key: str
    label: str
    maximise: bool = True
    """True when bigger is better.  Drawdown is the obvious exception."""
    help: str = ""


#: The metrics the optimiser offers to rank by.  ``return_drawdown_ratio`` is
#: derived rather than reported by the metrics layer -- see
#: :meth:`~tradingbacktester.optimize.runner.OptimizationRow.value`.
RANKING_METRICS: tuple[RankingMetric, ...] = (
    RankingMetric("net_profit", "Net profit", True,
                  "Cash left over after costs. Scales with position size, so it "
                  "says nothing about risk on its own."),
    RankingMetric("profit_factor", "Profit factor", True,
                  "Gross profit divided by gross loss. Above 1 is profitable; "
                  "a huge value on few trades is usually one lucky winner."),
    RankingMetric("sharpe_ratio", "Sharpe ratio", True,
                  "Annualised return divided by the volatility of returns."),
    RankingMetric("sortino_ratio", "Sortino ratio", True,
                  "Like Sharpe, but only downside volatility is penalised."),
    RankingMetric("return_drawdown_ratio", "Return / drawdown", True,
                  "Return earned per unit of the worst peak-to-trough fall."),
    RankingMetric("expectancy", "Expectancy", True,
                  "Average net profit per trade."),
    RankingMetric("win_rate", "Win rate", True,
                  "Percentage of trades closed at a profit. Meaningless without "
                  "the payoff ratio beside it."),
    RankingMetric("total_trades", "Trades", True,
                  "How many trades the combination took."),
    RankingMetric("max_drawdown_pct", "Max drawdown %", False,
                  "Worst peak-to-trough fall in equity. Smaller is better."),
    RankingMetric("calmar_ratio", "Calmar ratio", True,
                  "Annual return divided by maximum drawdown."),
    RankingMetric("recovery_factor", "Recovery factor", True,
                  "Net profit divided by maximum drawdown."),
    RankingMetric("sqn", "System quality (SQN)", True,
                  "sqrt(n) x mean(R) / stdev(R); rewards consistency and sample size."),
    RankingMetric("residual_sharpe", "Residual Sharpe (market-neutral)", True,
                  "Sharpe of what is left after the market's own move across "
                  "this strategy's window is regressed out. A Sharpe on raw "
                  "cash cannot tell an edge from leverage; this one can. Worth "
                  "ranking on — but see the note: optimising hard against it "
                  "does not carry to an untouched block."),
    RankingMetric("beta_pnl_share", "Market share of P&L", False,
                  "Fraction of the result the market factor explains. Above "
                  "about a half, the Sharpe beside it is measuring exposure "
                  "rather than a rule."),
    RankingMetric("concentration", "Sub-period concentration", False,
                  "Share of the block's profit carried by its best fifth. "
                  "Above 0.6 the result is one good stretch, not an edge — a "
                  "spike in time, and as disqualifying as a spike in "
                  "parameter space."),
)

_BY_KEY: dict[str, RankingMetric] = {m.key: m for m in RANKING_METRICS}

#: A best/median ratio above this, on a metric that can be compared that way, is
#: reported as a suspiciously large edge over the typical combination.
_SUSPICIOUS_BEST_TO_MEDIAN = 2.0

#: Neighbourhood mean below this fraction of the best value is a spike; above
#: the plateau threshold it is a plateau.  Between the two it is neither, and
#: the note says so rather than pretending.
_SPIKE_FRACTION = 0.4
_PLATEAU_FRACTION = 0.7


def ranking_metric(key: str) -> RankingMetric:
    """The :class:`RankingMetric` for ``key``, invented if it is not a known one.

    Any numeric metric can be ranked by, including ones added to the metrics
    layer after this module was written, so an unknown key is treated as
    "bigger is better" rather than refused.
    """
    known = _BY_KEY.get(key)
    if known is not None:
        return known
    label = key.replace("_", " ").strip().capitalize()
    return RankingMetric(key, label, True, "")


def metric_label(key: str) -> str:
    return ranking_metric(key).label


def default_maximise(key: str) -> bool:
    """Whether ``key`` should be sorted biggest-first."""
    return ranking_metric(key).maximise


def _sort_value(row: OptimizationRow, metric: str, maximise: bool) -> float:
    """Sort key that always pushes unusable rows to the bottom."""
    value = row.value(metric)
    if math.isnan(value):
        return -math.inf if maximise else math.inf
    return value


def rank(results: OptimizationResults, metric: str, minimum_trades: int = 0,
         maximise: bool | None = None) -> list[OptimizationRow]:
    """Rows sorted best-first by ``metric``.

    ``maximise`` defaults to the metric's own direction, so ranking by
    ``max_drawdown_pct`` puts the *shallowest* drawdown first.  Defaulting to
    True instead would have every drawdown ranking silently inverted -- the
    worst result presented as the best -- which is the kind of mistake nobody
    notices until they have traded it.  Pass the flag explicitly only to
    override that.

    Rows that failed, rows whose metric is missing, and rows with fewer than
    ``minimum_trades`` trades are excluded rather than sorted to the bottom: a
    combination that took two trades has no measurable edge, and leaving it in
    the table invites someone to click it.

    Ties are broken by trade count (more trades is more evidence) and then by
    grid position, so the ordering is stable between runs.
    """
    if maximise is None:
        maximise = default_maximise(metric)
    keep: list[OptimizationRow] = []
    for row in results.rows:
        if not row.ok:
            continue
        if row.trade_count < int(minimum_trades):
            continue
        if math.isnan(row.value(metric)):
            continue
        keep.append(row)
    keep.sort(key=lambda r: (_sort_value(r, metric, maximise) * (-1.0 if maximise else 1.0),
                             -r.trade_count, r.index))
    log.debug("Ranked %d of %d rows by %s (minimum_trades=%d)",
              len(keep), len(results.rows), metric, int(minimum_trades))
    return keep


def neighbourhood_mean(results: OptimizationResults, row: OptimizationRow,
                       metric: str) -> float:
    """Mean of ``metric`` over the combinations one step from ``row``.

    "One step" means: change exactly one swept parameter to its adjacent rung
    and leave the others alone, in both directions, for every swept parameter.
    A two-parameter grid therefore has up to four neighbours, a three-parameter
    grid up to six.  The centre is deliberately excluded -- this column answers
    "would this still work if I were slightly wrong?", and including the peak
    itself blunts exactly the comparison it exists to make.

    Failed neighbours and neighbours with no value for the metric are skipped.
    A combination at the corner of a one-by-one grid has no neighbours at all;
    it reports its own value, because there is nothing else to say and NaN in
    the column would read as a defect.
    """
    return _Lattice(results).mean_around(row, metric)


def neighbours(results: OptimizationResults,
               row: OptimizationRow) -> list[OptimizationRow]:
    """The successful rows one rung away from ``row`` in exactly one parameter."""
    return _Lattice(results).around(row)


class _Lattice:
    """The grid as a lattice: which combination is next to which.

    Built once and reused, because the obvious implementation -- rebuilding the
    ladders and the lookup for every row -- turns a ten-thousand-row robustness
    column into a hundred million dictionary builds.
    """

    def __init__(self, results: OptimizationResults) -> None:
        self.names = results.param_names
        self.ladders = {name: _rungs(results, name) for name in self.names}
        self.positions = {name: {v: i for i, v in enumerate(ladder)}
                          for name, ladder in self.ladders.items()}
        self.index = {tuple(r.params.get(n) for n in self.names): r
                      for r in results.rows}

    def around(self, row: OptimizationRow) -> list[OptimizationRow]:
        if not self.names:
            return []
        here = tuple(row.params.get(n) for n in self.names)
        out: list[OptimizationRow] = []
        for position, name in enumerate(self.names):
            ladder = self.ladders.get(name, [])
            at = self.positions.get(name, {}).get(here[position])
            if at is None:
                continue
            for step in (-1, 1):
                j = at + step
                if j < 0 or j >= len(ladder):
                    continue
                key = list(here)
                key[position] = ladder[j]
                found = self.index.get(tuple(key))
                if found is not None and found.ok:
                    out.append(found)
        return out

    def mean_around(self, row: OptimizationRow, metric: str) -> float:
        values = [n.value(metric) for n in self.around(row)]
        usable = [v for v in values if math.isfinite(v)]
        if not usable:
            return row.value(metric)
        return float(statistics.fmean(usable))


def _rungs(results: OptimizationResults, name: str) -> list[Any]:
    """The ordered distinct values of one parameter as the sweep actually ran it.

    Taken from the rows rather than from the range, because ``build_grid``
    coerces and de-duplicates: a 0.5 step on an integer parameter produces
    fewer rungs than the range implies, and a neighbourhood built from the
    range would then look for combinations that were never run.
    """
    seen = {row.params.get(name) for row in results.rows}
    seen.discard(None)
    try:
        return sorted(seen)
    except TypeError:  # pragma: no cover - a grid cannot mix types in one column
        return list(seen)


@dataclass
class RobustnessColumn:
    """Neighbourhood means for a whole ranked table, computed once."""

    metric: str
    values: dict[int, float] = field(default_factory=dict)
    """Keyed by :attr:`OptimizationRow.index`."""

    def get(self, row: OptimizationRow) -> float:
        return self.values.get(row.index, float("nan"))


def robustness_column(results: OptimizationResults, rows: Iterable[OptimizationRow],
                      metric: str) -> RobustnessColumn:
    """Neighbourhood means for every row in ``rows``.

    The table needs one value per visible row and the neighbour lookup builds an
    index each time; doing it once here keeps a 10,000-row table responsive.
    """
    lattice = _Lattice(results)
    column = RobustnessColumn(metric)
    for row in rows:
        column.values[row.index] = lattice.mean_around(row, metric)
    return column


@dataclass
class HeatmapData:
    """A two-parameter grid of one metric, ready for an image or a table.

    ``values[y, x]`` is the metric for ``y_values[y]`` and ``x_values[x]``, NaN
    where that combination failed or was never run.
    """

    x_name: str
    y_name: str
    x_values: list[Any]
    y_values: list[Any]
    values: np.ndarray
    metric: str

    @property
    def finite_range(self) -> tuple[float, float]:
        """Min and max over the cells that have a value, for colour scaling."""
        finite = self.values[np.isfinite(self.values)]
        if finite.size == 0:
            return (0.0, 0.0)
        return (float(finite.min()), float(finite.max()))


def heatmap(results: OptimizationResults, metric: str, x_name: str | None = None,
            y_name: str | None = None) -> HeatmapData | None:
    """The metric surface over two swept parameters, or ``None``.

    Returns ``None`` when fewer than two parameters were swept, or when the two
    requested parameters were not part of the sweep -- the dialog draws its heat
    map only for the two-parameter case, and this is how it asks.
    """
    names = results.param_names
    if len(names) < 2:
        return None
    x_name = x_name or names[0]
    y_name = y_name or names[1]
    if x_name not in names or y_name not in names or x_name == y_name:
        return None
    xs = _rungs(results, x_name)
    ys = _rungs(results, y_name)
    grid = np.full((len(ys), len(xs)), np.nan, dtype="float64")
    x_at = {v: i for i, v in enumerate(xs)}
    y_at = {v: i for i, v in enumerate(ys)}
    for row in results.rows:
        if not row.ok:
            continue
        i = y_at.get(row.params.get(y_name))
        j = x_at.get(row.params.get(x_name))
        if i is None or j is None:
            continue
        value = row.value(metric)
        # With a third parameter swept, several rows share one cell; the last
        # one would silently win, so keep the best, which is what a heat map of
        # "what is achievable here" should show.
        if math.isnan(grid[i, j]) or (not math.isnan(value) and value > grid[i, j]):
            grid[i, j] = value
    return HeatmapData(x_name, y_name, xs, ys, grid, metric)


def overfitting_note(results: OptimizationResults,
                     ranked: Sequence[OptimizationRow],
                     metric: str = "net_profit") -> str:
    """A plain-language reading of how much the top row should be trusted.

    Names the number of combinations searched, how far ahead of the typical
    combination the winner is, and whether it sits on a plateau or on a spike.
    Written as prose because a number the user has to interpret is a number the
    user will not interpret.
    """
    total = results.total_combinations or len(results.rows)
    usable = [r for r in ranked if not math.isnan(r.value(metric))]
    label = metric_label(metric)
    if not usable:
        if results.rows and results.completed == 0:
            return ("No combination produced a result, so there is nothing to "
                    "rank. Check the failure column for the reason.")
        return (f"No combination has a value for {label}, so there is nothing "
                f"to rank. Try a different metric or a lower minimum trade count.")

    best = usable[0]
    best_value = best.value(metric)
    values = [r.value(metric) for r in usable]
    finite = [v for v in values if math.isfinite(v)]
    median = float(statistics.median(finite)) if finite else float("nan")

    parts: list[str] = [
        f"{total:,} combination{'' if total == 1 else 's'} were tested and the "
        f"best was picked by {label}. Searching that many settings finds a good "
        f"one even in data with no edge at all."
    ]

    if math.isfinite(best_value) and math.isfinite(median) and median > 0 \
            and best_value > 0:
        ratio = best_value / median
        if ratio >= _SUSPICIOUS_BEST_TO_MEDIAN:
            parts.append(
                f"The winner's {label.lower()} is {ratio:.1f} times the median "
                f"combination's, which is a large gap to explain by anything "
                f"other than the search itself.")
        else:
            parts.append(
                f"The winner's {label.lower()} is {ratio:.1f} times the median "
                f"combination's, so it is not far ahead of the pack -- which is "
                f"the healthier shape.")
    elif math.isfinite(median) and median <= 0 and math.isfinite(best_value) \
            and best_value > 0:
        parts.append(
            f"The median combination loses money and only the top of the grid "
            f"makes any, so the profitable settings are the exception here, not "
            f"the rule.")

    lattice = _Lattice(results)
    neighbour_rows = lattice.around(best)
    if not neighbour_rows:
        parts.append(
            "The best combination has no neighbours in this grid, so there is "
            "no way to tell whether it is a plateau or a spike. Sweep a wider "
            "range to find out.")
    else:
        mean = lattice.mean_around(best, metric)
        if not math.isfinite(best_value) or not math.isfinite(mean):
            parts.append(
                f"Its {label.lower()} cannot be compared with its neighbours' "
                f"because one of the values is not a finite number.")
        elif best_value <= 0:
            parts.append(
                f"The best {label.lower()} in the grid is {best_value:,.2f}, so "
                f"there is no winning combination here to be over-fitted to; "
                f"its neighbours average {mean:,.2f}.")
        else:
            fraction = mean / best_value
            if fraction < _SPIKE_FRACTION:
                parts.append(
                    f"Its {len(neighbour_rows)} immediate neighbours average "
                    f"{mean:,.2f} against its own {best_value:,.2f}: this is an "
                    f"isolated spike. A setting that only works at one exact "
                    f"value usually stops working out of sample.")
            elif fraction >= _PLATEAU_FRACTION:
                parts.append(
                    f"Its {len(neighbour_rows)} immediate neighbours average "
                    f"{mean:,.2f} against its own {best_value:,.2f}, so it sits "
                    f"on a plateau rather than a spike -- the most encouraging "
                    f"thing an optimisation can show.")
            else:
                parts.append(
                    f"Its {len(neighbour_rows)} immediate neighbours average "
                    f"{mean:,.2f} against its own {best_value:,.2f}: neither a "
                    f"clean plateau nor a lone spike. Compare the robustness "
                    f"column across the top few rows before choosing.")

    if best.trade_count < 30:
        parts.append(
            f"It also took only {best.trade_count} trade"
            f"{'' if best.trade_count == 1 else 's'}, which is too few for any "
            f"of these numbers to be stable.")

    if results.failed:
        parts.append(
            f"{results.failed:,} combination{'' if results.failed == 1 else 's'} "
            f"failed to run and {'is' if results.failed == 1 else 'are'} not in "
            f"the ranking.")

    return " ".join(parts)
