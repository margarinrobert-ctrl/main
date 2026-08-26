"""Walk-forward analysis: optimise on the past, trade the future, repeat.

An optimisation reports the best parameters *for the data it saw*, which is a
statement about history and not about anything else. Walk-forward is the
procedure that turns it into a question worth asking: choose the parameters on
one block, trade the **next** block with them without looking, move both
windows along, and stitch the untouched blocks into a single equity curve.

That curve is the honest one. Everything the optimiser earned in-sample is
excluded from it by construction, so it cannot contain a parameter chosen with
hindsight.

Two numbers make the report worth reading, and both are usually bad:

* **Walk-forward efficiency** -- what the chosen parameters earned out of
  sample divided by what they earned in sample. One means the optimisation
  found something that persisted. A half or less means most of what it found
  was the noise of that particular window.
* **Parameter stability** -- how often the winner changed. A strategy whose
  best settings jump every window has no optimum to find; the optimiser is
  reporting the shape of the last three months.

Windows can roll (a fixed-length lookback that slides) or anchor (a training
block that grows from the start). Rolling adapts to a changing market and has
less data; anchored has more data and assumes the past stays relevant.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from ..core.errors import InsufficientDataError, ParameterError
from ..data.models import BarSeries
from .grid import ParameterRange, build_grid
from .ranking import default_maximise
from .runner import evaluate_combination

ProgressFn = Callable[[int, int, str], None]

#: Smallest series the analysis will accept.  Below this the training blocks are
#: too short for an optimisation to mean anything, whatever the fold count.
MIN_BARS = 500


@dataclass
class Window:
    """One train/test pair, and what came out of it."""

    index: int
    train_start: int
    train_end: int
    """Exclusive."""
    test_start: int
    test_end: int
    """Exclusive."""
    params: dict[str, Any] = field(default_factory=dict)
    train_metric: float = float("nan")
    test_metric: float = float("nan")
    train_trades: int = 0
    train_net: float = 0.0
    test_trades: int = 0
    test_net: float = 0.0
    warmup_pad: int = 0
    """Bars of history prepended to each block so the indicators start settled."""
    error: str = ""

    @property
    def efficiency(self) -> float:
        """Out-of-sample result over in-sample result, for this window."""
        if not math.isfinite(self.train_metric) or self.train_metric == 0:
            return float("nan")
        return self.test_metric / self.train_metric


@dataclass
class WalkForwardResult:
    """Every window, and the out-of-sample record they add up to."""

    metric: str
    anchored: bool
    windows: list[Window] = field(default_factory=list)
    combinations: int = 0
    """Size of the grid searched in each window."""
    warmup: int = 0
    """Bars of history prepended to each block so indicators start settled."""
    out_of_sample_trades: int = 0
    out_of_sample_net: float = 0.0
    in_sample_net: float = 0.0
    equity: list[float] = field(default_factory=list)
    """Cumulative out-of-sample profit, one point per test window."""
    notes: list[str] = field(default_factory=list)
    elapsed: float = 0.0

    @property
    def completed(self) -> list[Window]:
        return [w for w in self.windows if not w.error]

    @property
    def efficiency(self) -> float:
        """Out-of-sample over in-sample across every window, in cash.

        The headline number, computed from the totals rather than as a mean of
        per-window ratios so that one near-zero denominator cannot dominate it.

        Always cash, whatever :attr:`metric` the windows were ranked by: a
        drawdown percentage or a profit factor cannot be summed across windows
        and a ratio of two such sums would mean nothing. When the optimiser was
        selecting for something other than profit, a low efficiency is not by
        itself a failure of the selection -- it says the profit did not
        persist, not that the thing being optimised did not.

        Undefined when the in-sample total is not positive. "Kept -76% of its
        in-sample profit" is not a sentence: if the best combination the
        optimiser could find still lost money on the data it was chosen from,
        there was nothing for the out-of-sample block to keep, and the ratio
        would flip sign for reasons that have nothing to do with robustness.
        """
        if not math.isfinite(self.in_sample_net) or self.in_sample_net <= 0:
            return float("nan")
        return self.out_of_sample_net / self.in_sample_net

    @property
    def stability(self) -> float:
        """Fraction of windows that kept the previous window's parameters.

        One means the optimum never moved. Near zero means there was no
        optimum, only a best fit to each window in turn.
        """
        chosen = [tuple(sorted(w.params.items())) for w in self.completed]
        if len(chosen) < 2:
            return float("nan")
        same = sum(1 for a, b in zip(chosen, chosen[1:]) if a == b)
        return same / (len(chosen) - 1)

    @property
    def winning_windows(self) -> int:
        return sum(1 for w in self.completed if w.test_net > 0)

    def verdict(self) -> str:
        """What the numbers mean, in a sentence."""
        done = self.completed
        if not done:
            return "no window produced a result"
        if self.out_of_sample_net <= 0:
            if self.in_sample_net <= 0:
                return ("lost money out of sample, and the best combination in "
                        "each training window lost money too — there was "
                        "nothing here for the optimiser to find")
            return ("lost money out of sample — the optimisation was fitting "
                    "the training window")
        efficiency = self.efficiency
        if math.isfinite(efficiency) and efficiency < 0.3:
            tail = ("so most of what the optimiser found was noise"
                    if self.metric == "net_profit" else
                    "so most of the in-sample profit did not persist")
            return (f"made money out of sample but kept only "
                    f"{efficiency * 100:.0f}% of what it made in sample, "
                    f"{tail}")
        if math.isfinite(self.stability) and self.stability < 0.34:
            return ("made money out of sample, but the best parameters changed "
                    "in most windows, so there is no stable setting to ship")
        if self.winning_windows <= len(done) // 2:
            return (f"made money out of sample, but only {self.winning_windows} "
                    f"of {len(done)} windows were profitable — the total rests "
                    f"on a minority of them")
        return "held up out of sample across the windows"

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric, "anchored": self.anchored,
            "combinations": self.combinations, "warmup": self.warmup,
            "windows": [
                {"index": w.index, "params": dict(w.params),
                 "train_metric": w.train_metric, "test_metric": w.test_metric,
                 "train_trades": w.train_trades, "test_trades": w.test_trades,
                 "test_net": w.test_net, "efficiency": w.efficiency,
                 "warmup_pad": w.warmup_pad, "error": w.error}
                for w in self.windows],
            "out_of_sample_trades": self.out_of_sample_trades,
            "out_of_sample_net": self.out_of_sample_net,
            "in_sample_net": self.in_sample_net,
            "equity": list(self.equity),
            "efficiency": self.efficiency, "stability": self.stability,
            "winning_windows": self.winning_windows,
            "verdict": self.verdict(), "notes": list(self.notes),
            "elapsed_seconds": round(self.elapsed, 2),
        }


def plan_windows(total: int, folds: int, train_fraction: float,
                 anchored: bool) -> list[tuple[int, int, int, int]]:
    """``(train_start, train_end, test_start, test_end)`` for each fold.

    The test blocks tile the tail of the series without overlapping, so the
    out-of-sample record is a real continuous history rather than the same
    period counted several times.
    """
    folds = max(1, int(folds))
    train_fraction = min(0.9, max(0.1, float(train_fraction)))
    # The first training block, then the remainder split into equal tests.
    first_train = int(total * train_fraction)
    testable = total - first_train
    if testable < folds:
        raise InsufficientDataError(
            f"{total:,} bars cannot be split into {folds} walk-forward folds "
            f"with {train_fraction:.0%} training. Use fewer folds, a smaller "
            f"training fraction, or more data.")
    size = testable // folds
    out: list[tuple[int, int, int, int]] = []
    for fold in range(folds):
        test_start = first_train + fold * size
        test_end = total if fold == folds - 1 else test_start + size
        train_start = 0 if anchored else max(0, test_start - first_train)
        out.append((train_start, test_start, test_start, test_end))
    return out


def walk_forward(bars: BarSeries, spec: Any, config: Any,
                 ranges: Sequence[ParameterRange], *, folds: int = 5,
                 train_fraction: float = 0.5, anchored: bool = False,
                 metric: str = "net_profit", minimum_trades: int = 5,
                 progress: ProgressFn | None = None,
                 cancel: Any = None) -> WalkForwardResult:
    """Optimise on each training block and trade the block that follows it."""
    started = time.time()
    total = len(bars)
    if total < MIN_BARS:
        raise InsufficientDataError(
            f"Walk-forward needs at least {MIN_BARS} bars and this dataset has "
            f"{total:,}.")
    if not ranges:
        raise ParameterError(
            "Walk-forward needs at least one parameter to optimise. A strategy "
            "with no parameters has nothing to choose, so an ordinary backtest "
            "already answers the question.")

    grid = build_grid(spec, ranges)
    maximise = default_maximise(metric)
    plan = plan_windows(total, folds, train_fraction, anchored)
    warmup = _grid_warmup(spec, grid, config)
    result = WalkForwardResult(metric=metric, anchored=anchored,
                               combinations=len(grid), warmup=warmup)

    steps = len(plan) * (len(grid) + 1)
    done = 0
    running = 0.0
    for index, (train_start, train_end, test_start, test_end) in enumerate(plan):
        window = Window(index=index, train_start=train_start,
                        train_end=train_end, test_start=test_start,
                        test_end=test_end)
        # Each block is handed the bars immediately before it so its indicators
        # begin settled.  Without this the first `warmup` bars of every test
        # block raise no signal, the out-of-sample blocks stop tiling, and the
        # analysis quietly throws away the trades it exists to count.  The
        # prepended bars are strictly in the past, so nothing here can see
        # forward; `_run` pins the first tradeable bar to the block's own start
        # so a combination with a shorter warm-up cannot trade into its
        # predecessor's block either.
        train_pad = min(warmup, train_start)
        test_pad = min(warmup, test_start)
        window.warmup_pad = test_pad
        train_bars = bars.slice(train_start - train_pad, train_end)
        test_bars = bars.slice(test_start - test_pad, test_end)

        best_value = -math.inf
        best: dict[str, Any] | None = None
        best_trades = 0
        best_net = 0.0
        for params in grid:
            if cancel is not None and getattr(cancel, "cancelled", False):
                from ..core.errors import CancelledError

                raise CancelledError("The walk-forward was cancelled.")
            done += 1
            if progress is not None and done % 5 == 0:
                progress(done, steps,
                         f"Window {index + 1} of {len(plan)}: choosing from "
                         f"{len(grid)} combinations")
            row = _run(train_bars, spec, config, train_pad, done, params)
            if row["error"] or row["trade_count"] < minimum_trades:
                continue
            value = _metric_value(row["metrics"], metric)
            if not math.isfinite(value):
                continue
            signed = value if maximise else -value
            if signed > best_value:
                best_value = signed
                best = dict(params)
                best_trades = int(row["trade_count"])
                best_net = float(row["metrics"].get("net_profit", 0.0) or 0.0)

        done += 1
        if best is None:
            window.error = (f"no combination produced at least "
                            f"{minimum_trades} trades in the training window")
            result.windows.append(window)
            continue

        window.params = best
        window.train_metric = best_value if maximise else -best_value
        window.train_trades = best_trades
        window.train_net = best_net
        if progress is not None:
            progress(done, steps,
                     f"Window {index + 1} of {len(plan)}: testing out of sample")
        tested = _run(test_bars, spec, config, test_pad, done, best)
        if tested["error"]:
            window.error = tested["error"]
            result.windows.append(window)
            continue
        window.test_metric = _metric_value(tested["metrics"], metric)
        window.test_trades = int(tested["trade_count"])
        window.test_net = float(tested["metrics"].get("net_profit", 0.0) or 0.0)

        result.out_of_sample_trades += window.test_trades
        result.out_of_sample_net += window.test_net
        # Taken from the row that won, not by re-running it: an extra backtest
        # per window for a number already in hand.
        result.in_sample_net += window.train_net
        running += window.test_net
        result.equity.append(running)
        result.windows.append(window)

    result.elapsed = time.time() - started
    result.notes = _notes(result, len(plan), anchored, train_fraction)
    return result


def _grid_warmup(spec: Any, grid: Sequence[dict[str, Any]], config: Any) -> int:
    """Bars of history the widest combination in ``grid`` needs.

    Taken as the maximum over the grid rather than per combination so that every
    window starts at the same bar and the fold boundaries are the same for all
    of them.  A combination with a shorter warm-up is simply handed more history
    than it needs, which costs nothing and keeps the blocks comparable.
    """
    need = int(getattr(config, "warmup_bars", 0) or 0)
    getter = getattr(spec, "warmup_bars", None)
    if callable(getter):
        for params in grid or ({},):
            try:
                need = max(need, int(getter(dict(params))))
            except Exception:               # noqa: BLE001 - a bad combination
                # is reported by the backtest itself; it must not stop the plan.
                continue
    return max(0, need)


def _run(block: BarSeries, spec: Any, config: Any, pad: int, index: int,
         params: dict[str, Any]) -> dict[str, Any]:
    """Backtest one block, trading only from ``pad`` bars in.

    ``config.warmup_bars`` is the engine's floor on the first bar that may raise
    a signal, so setting it to the padding pins the block's first trade to the
    block's own start whatever warm-up this particular combination needs.  The
    configuration is copied rather than mutated: the caller's object is theirs.
    """
    import copy

    if pad > 0:
        config = copy.copy(config)
        config.warmup_bars = max(int(getattr(config, "warmup_bars", 0) or 0), pad)
    return evaluate_combination(block, spec, config, index, params)


def _metric_value(metrics: dict[str, Any], metric: str) -> float:
    raw = metrics.get(metric)
    if isinstance(raw, bool) or raw is None:
        return float("nan")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float("nan")


def _notes(result: WalkForwardResult, folds: int, anchored: bool,
           train_fraction: float) -> list[str]:
    kind = ("an anchored window that grows from the start of the data"
            if anchored else
            "a rolling window of fixed length that slides forward")
    notes = [
        f"{folds} folds, {kind}, training on {train_fraction:.0%} of the "
        f"series and testing on what follows. The {result.combinations:,} "
        f"combinations were searched separately in every window.",
        "The out-of-sample total is the only number here that was not chosen "
        "with hindsight. The in-sample figures are shown so the two can be "
        "compared, not because either is a result.",
    ]
    if result.metric != "net_profit":
        notes.append(
            f"The windows were ranked by {result.metric.replace('_', ' ')}, but "
            f"walk-forward efficiency below is measured in cash — a drawdown "
            f"percentage or a profit factor cannot be summed across windows. "
            f"A combination chosen for something other than profit can keep "
            f"little of its profit without that being a failure of the "
            f"selection.")
    if result.warmup > 0:
        notes.append(
            f"Each block was handed the {result.warmup} bars immediately "
            f"before it so its indicators started settled, and was then only "
            f"allowed to trade from its own first bar. The test blocks "
            f"therefore tile the tail of the series exactly once, with no gap "
            f"where a moving average was still filling up and no overlap. The "
            f"one exception is any block that starts at bar 0, which has no "
            f"history to be handed and so trades on {result.warmup} bars "
            f"fewer than the rest.")
    efficiency = result.efficiency
    if math.isfinite(efficiency) and efficiency < 0:
        # "Kept -93%" is not a thing that can happen. It kept none of it and
        # then lost that much again.
        notes.append(
            f"Walk-forward efficiency {efficiency:.2f}: the chosen parameters "
            f"kept none of their in-sample profit. Out of sample they lost a "
            f"further {abs(efficiency) * 100:.0f}% of it, so the optimisation "
            f"was not merely weak — what it selected for did not survive "
            f"contact with data it had not seen.")
    elif math.isfinite(efficiency):
        notes.append(
            f"Walk-forward efficiency {efficiency:.2f}: the chosen parameters "
            f"kept {efficiency * 100:.0f}% of their in-sample profit when they "
            f"were used on data they had not seen. Anything under about a half "
            f"means the optimiser was mostly fitting each training window.")
    elif result.in_sample_net <= 0:
        notes.append(
            f"Walk-forward efficiency cannot be computed: the winning "
            f"combination lost money in the training windows too "
            f"({result.in_sample_net:+,.2f} in total), so there was no "
            f"in-sample profit for the out-of-sample block to keep.")
    stability = result.stability
    if math.isfinite(stability):
        notes.append(
            f"The best parameters were unchanged in {stability * 100:.0f}% of "
            f"the window-to-window steps. A strategy whose optimum moves every "
            f"window does not have one.")
    notes.append(
        "This is still one instrument over one period, and a walk-forward that "
        "held up is evidence, not a guarantee.")
    return notes


def format_walk_forward(result: WalkForwardResult, bars: BarSeries,
                        currency: str = "USD", width: int = 78) -> str:
    """The whole analysis as plain text."""
    import pandas as pd

    def stamp(index: int) -> str:
        index = max(0, min(index, len(bars) - 1))
        return str(pd.Timestamp(bars.ts[index], tz="UTC").date())

    rule = "-" * width
    out = [f"Walk-forward — {getattr(bars.instrument, 'symbol', '?')} "
           f"{bars.timeframe.label}, ranked by {result.metric}", rule]
    out.append(f"{len(result.windows)} folds, "
               f"{'anchored' if result.anchored else 'rolling'} windows, "
               f"{result.combinations:,} combinations per window.  "
               f"{result.elapsed:.1f}s.")
    out.append("")
    out.append(f"   {'#':<3} {'train':<23} {'test':<23} {'in-sample':>11} "
               f"{'out':>11}  parameters")
    for window in result.windows:
        train = f"{stamp(window.train_start)}–{stamp(window.train_end - 1)}"
        test = f"{stamp(window.test_start)}–{stamp(window.test_end - 1)}"
        if window.error:
            out.append(f"   {window.index + 1:<3} {train:<23} {test:<23} "
                       f"{window.error}")
            continue
        params = ", ".join(f"{k}={v}" for k, v in window.params.items())
        out.append(
            f"   {window.index + 1:<3} {train:<23} {test:<23} "
            f"{window.train_metric:>11,.2f} {window.test_metric:>11,.2f}"
            f"  {params}")
    out.append("")
    out.append(f"   out of sample: {result.out_of_sample_trades:,} trades, "
               f"{result.out_of_sample_net:+,.2f} {currency}, "
               f"{result.winning_windows} of {len(result.completed)} windows "
               f"profitable")
    import textwrap

    verdict = textwrap.wrap(f"verdict: {result.verdict()}", max(40, width - 3))
    out.extend("   " + line for line in verdict)
    out.append("")
    out.append(rule)

    for note in result.notes:
        out.extend(textwrap.wrap(note, width))
        out.append("")
    return "\n".join(out).rstrip() + "\n"
