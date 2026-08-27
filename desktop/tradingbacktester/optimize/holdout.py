"""Optimise on one block, then look at the other one exactly once.

The grid optimiser has no train/test concept.  It sweeps the whole series,
ranks by a metric, and hands back a winner -- and nothing anywhere stops a user
reading that winner as a result.  Walk-forward exists on the same dialog and
answers a harder question, but it is opt-in and it re-optimises in every window,
so it does not tell you what THESE parameters are worth out of sample.

This is the missing middle: the same grid, chosen on the first block only, then
revealed once on the block it never saw.

Why "exactly once" is the whole design
--------------------------------------

A holdout stops being a holdout the moment it can influence a choice.  If the
locked block is scored for every combination and the best one on it is
reported, the split has bought nothing -- the search simply had more data to
overfit.  So the block is touched only *after* the ranking is fixed, only for
the top few, and the report says so in those words.

The two blocks are never merged into one number.  A blended figure is how a
combination chosen on one block gets described as profitable.

What it cannot do
-----------------

It cannot make a grid search safe.  A thousand combinations ranked on the
research block still had a thousand chances to fit it, and the retention figure
here is one sample of what happened next -- not a correction for that
multiplicity.  The report states the grid size beside the result for the same
reason the finder does.
"""

from __future__ import annotations

import copy
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from ..core.errors import InsufficientDataError
from ..data.models import BarSeries
from .grid import ParameterRange
from .ranking import ranking_metric
from .runner import (OptimizationResults, OptimizationRow, OptimizationRunner,
                     evaluate_combination)

log = logging.getLogger(__name__)

ProgressFn = Callable[[int, int], None]
CancelFn = Callable[[], bool]

#: Below this the split leaves too little on either side to mean anything.
MIN_BARS = 500

#: How much of the series chooses the parameters.  Matches the finder, so the
#: two tools do not disagree about what "out of sample" means.
RESEARCH_FRACTION = 0.65

#: How many of the ranked combinations are revealed on the locked block.  Small
#: on purpose: revealing all of them and picking the best is selecting on the
#: holdout with extra steps.
DEFAULT_REVEAL = 3


@dataclass
class Revealed:
    """One combination, chosen on research, measured on the locked block."""

    params: dict[str, Any]
    rank: int
    research_value: float
    holdout_value: float
    research_trades: int = 0
    holdout_trades: int = 0
    research_metrics: dict[str, Any] = field(default_factory=dict)
    holdout_metrics: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    maximise: bool = True
    """Whether the ranking metric is one where a bigger number is better."""

    @property
    def retention(self) -> float:
        """Locked over research, or NaN when the ratio would not mean anything.

        Three cases give NaN rather than a number.  A research block that lost
        money, because "kept -80% of a loss" is not a sentence and a ratio of
        two negatives is worse than useless.  A research value of zero.  And
        any metric where *smaller* is better -- ranking by drawdown and
        reporting that the winner "kept 150%" of it would read as a good
        result while describing a worse one.
        """
        if not self.maximise:
            return float("nan")
        if not math.isfinite(self.research_value) or self.research_value <= 0:
            return float("nan")
        return self.holdout_value / self.research_value

    @property
    def label(self) -> str:
        return ", ".join(f"{k}={v}" for k, v in self.params.items())

    def to_dict(self) -> dict[str, Any]:
        retention = self.retention
        return {"params": dict(self.params), "rank": self.rank,
                "research_value": self.research_value,
                "holdout_value": self.holdout_value,
                "research_trades": self.research_trades,
                "holdout_trades": self.holdout_trades,
                "retention": None if not math.isfinite(retention) else retention,
                "error": self.error}


@dataclass
class HoldoutResult:
    """A grid ranked on one block and revealed once on the other."""

    metric: str = "net_profit"
    maximise: bool = True
    """Direction of ``metric``, taken from the ranking table, not guessed."""
    combinations: int = 0
    research_bars: int = 0
    holdout_bars: int = 0
    split_index: int = 0
    warmup_pad: int = 0
    revealed: list[Revealed] = field(default_factory=list)
    research: OptimizationResults | None = None
    elapsed: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def best(self) -> Revealed | None:
        return self.revealed[0] if self.revealed else None

    @property
    def wrong_shape(self) -> bool:
        """Did the winner do BETTER on the block it was not chosen on?

        Flagged, never celebrated. An edge decays out of sample; it does not
        appear there, and when it does the usual causes are an easier period in
        the locked block or a leak between the two.
        """
        best = self.best
        if best is None or not self.maximise:
            return False
        retention = best.retention
        return math.isfinite(retention) and retention > 1.5

    def to_dict(self) -> dict[str, Any]:
        return {"metric": self.metric, "maximise": self.maximise,
                "combinations": self.combinations,
                "research_bars": self.research_bars,
                "holdout_bars": self.holdout_bars,
                "split_index": self.split_index,
                "warmup_pad": self.warmup_pad,
                "revealed": [r.to_dict() for r in self.revealed],
                "elapsed_seconds": round(self.elapsed, 2),
                "wrong_shape": self.wrong_shape,
                "notes": list(self.notes)}


def _warmup_for(spec: Any, config: Any, grid: Sequence[dict[str, Any]]) -> int:
    """The longest warm-up any combination in the grid needs."""
    need = int(getattr(config, "warmup_bars", 0) or 0)
    getter = getattr(spec, "warmup_bars", None)
    if callable(getter):
        for params in grid or ({},):
            try:
                need = max(need, int(getter(dict(params))))
            except Exception:               # noqa: BLE001 - a combination that
                continue                    # cannot say is covered by the rest
    return max(0, need)


def _value(metrics: dict[str, Any], metric: str) -> float:
    """The metric as a float, NaN when it is missing or not a number.

    Delegated to :class:`OptimizationRow` so the locked block is scored by
    exactly the code that scored the research block.  That matters for
    ``return_drawdown_ratio``, which is derived from two other metrics rather
    than stored, and would otherwise come back NaN here and a number there.
    """
    return OptimizationRow(params={}, metrics=dict(metrics or {})).value(metric)


def optimise_with_holdout(
        bars: BarSeries, spec: Any, config: Any,
        ranges: Sequence[ParameterRange], *, metric: str = "net_profit",
        research_fraction: float = RESEARCH_FRACTION,
        reveal: int = DEFAULT_REVEAL, max_workers: int = 0,
        progress: ProgressFn | None = None,
        cancel: CancelFn | None = None) -> HoldoutResult:
    """Sweep the grid on the research block, then reveal the locked one once."""
    started = time.perf_counter()
    total = len(bars)
    if total < MIN_BARS:
        raise InsufficientDataError(
            f"An out-of-sample optimisation needs at least {MIN_BARS} bars so "
            f"that both blocks mean something, and this dataset has "
            f"{total:,}.")

    fraction = min(0.95, max(0.05, float(research_fraction)))
    split = int(total * fraction)
    if split <= 0 or split >= total:
        raise InsufficientDataError(
            "The research fraction leaves one of the two blocks empty.")

    direction = ranking_metric(metric)
    maximise = bool(getattr(direction, "maximise", True))
    out = HoldoutResult(metric=metric, maximise=maximise, split_index=split,
                        research_bars=split, holdout_bars=total - split)

    runner = OptimizationRunner(bars.slice(0, split), spec, config,
                                max_workers=max_workers)
    grid = runner.build(ranges)
    out.combinations = len(grid)

    research = runner.run(ranges, progress=progress, cancel=cancel)
    out.research = research
    if research.cancelled:
        out.notes.append(
            "The sweep was stopped, so the locked block was not looked at. "
            "Revealing it against a partial ranking would spend the one thing "
            "a holdout has for nothing.")
        out.elapsed = time.perf_counter() - started
        return out

    successful = [r for r in research.successful()
                  if math.isfinite(_value(r.metrics, metric))]
    if not successful:
        out.notes.append(
            "No combination produced a usable result on the research block, so "
            "there was nothing to rank and the locked block was left alone.")
        out.elapsed = time.perf_counter() - started
        return out

    ranked = sorted(successful, key=lambda r: _value(r.metrics, metric),
                    reverse=maximise)

    # The locked block is padded with the bars immediately before it and the
    # engine's warm-up floor is raised to match, so a combination is warm on its
    # first bar there and cannot trade inside the block it was chosen on.
    pad = _warmup_for(spec, config, grid)
    pad = min(pad, split)
    out.warmup_pad = pad
    holdout_bars = bars.slice(split - pad, total)
    holdout_config = copy.copy(config)
    if pad > 0:
        holdout_config.warmup_bars = max(
            int(getattr(config, "warmup_bars", 0) or 0), pad)

    for position, row in enumerate(ranked[:max(1, int(reveal))]):
        payload = evaluate_combination(holdout_bars, spec, holdout_config,
                                       row.index, dict(row.params))
        entry = Revealed(
            params=dict(row.params), rank=position + 1,
            research_value=_value(row.metrics, metric),
            holdout_value=_value(payload.get("metrics", {}) or {}, metric),
            research_trades=int(row.trade_count),
            holdout_trades=int(payload.get("trade_count", 0) or 0),
            research_metrics=dict(row.metrics),
            holdout_metrics=dict(payload.get("metrics", {}) or {}),
            error=str(payload.get("error") or ""), maximise=maximise)
        out.revealed.append(entry)

    out.elapsed = time.perf_counter() - started
    _notes(out)
    return out


def _notes(out: HoldoutResult) -> None:
    """Everything the reader needs to not over-read the number."""
    out.notes.append(
        f"{out.combinations:,} combinations were ranked on the first "
        f"{out.research_bars:,} bars. The last {out.holdout_bars:,} were not "
        f"looked at until the ranking was fixed, and only for the top "
        f"{len(out.revealed)}.")
    out.notes.append(
        f"That split does not correct for the multiplicity. {out.combinations:,} "
        f"combinations had {out.combinations:,} chances to fit the research "
        f"block, and the locked figures below are one sample of what happened "
        f"next — not a p-value and not a correction.")

    best = out.best
    if best is None:
        return
    retention = best.retention
    if best.holdout_trades == 0:
        out.notes.append(
            "The best combination took no trades at all on the locked block, "
            "so there is no out-of-sample evidence for it — only the absence "
            "of any.")
    elif not out.maximise:
        out.notes.append(
            f"{out.metric.replace('_', ' ')} is a metric where a smaller "
            f"number is better, so there is no retention figure: a winner that "
            f"'kept 150%' of its drawdown kept a worse one. Read the two "
            f"columns separately.")
    elif not math.isfinite(best.research_value) or best.research_value <= 0:
        out.notes.append(
            f"Nothing in the grid worked on the block that chose it — the best "
            f"of {out.combinations:,} combinations scored "
            f"{best.research_value:,.2f} on the research block. Whatever the "
            f"locked column says, it is what the least-bad combination "
            f"happened to do next, not evidence of an edge.")
    elif out.wrong_shape:
        out.notes.append(
            f"The winner did markedly better out of sample "
            f"({retention * 100:.0f}% of its research result). That is the "
            f"wrong shape: an edge decays on a block it was not chosen from, "
            f"it does not appear there. The usual causes are an easier period "
            f"in the locked block or a leak between the two, and it is worth "
            f"explaining before trusting the number.")
    elif retention <= 0:
        out.notes.append(
            "The winner lost money on the locked block. Whatever the sweep "
            "found on the research block did not survive contact with data it "
            "had not seen.")
    else:
        out.notes.append(
            f"The winner kept {retention * 100:.0f}% of its research result "
            f"out of sample.")
    out.notes.append(
        "Everything here describes one instrument over one period. It is not a "
        "prediction, and the parameters that survived can still lose money.")


def format_holdout(result: HoldoutResult, bars: BarSeries | None = None,
                   currency: str = "USD", width: int = 78) -> str:
    """The whole thing as plain text, with the two blocks kept apart.

    Deliberately laid out as two columns rather than one blended figure: the
    research column is what was chosen, the locked column is what that choice
    was worth, and putting them side by side is the only presentation that
    makes the second readable as evidence rather than as a result.
    """
    import textwrap

    from ..core.textfmt import row as _fit

    def stamp(index: int) -> str:
        if bars is None or not len(bars):
            return f"bar {index:,}"
        import pandas as pd

        index = max(0, min(index, len(bars) - 1))
        return str(pd.Timestamp(bars.ts[index], tz="UTC").date())

    rule = "-" * width
    symbol = getattr(getattr(bars, "instrument", None), "symbol", "?")
    label = getattr(getattr(bars, "timeframe", None), "label", "")
    out = _fit("", f"Out-of-sample optimisation — {symbol} {label}, "
               f"ranked by {result.metric}", width)
    out.append(rule)
    out.extend(_fit(
        "", f"{result.combinations:,} combinations chosen on "
            f"{stamp(0)}–{stamp(result.split_index - 1)} "
            f"({result.research_bars:,} bars); revealed once on "
            f"{stamp(result.split_index)}–{stamp(result.split_index + result.holdout_bars - 1)} "
            f"({result.holdout_bars:,} bars).  {result.elapsed:.1f}s.", width))
    out.append("")

    if not result.revealed:
        out.append("   Nothing was revealed on the locked block.")
        out.append("")
    else:
        out.append(f"   {'#':<3} {'research':>13} {'trades':>7}   "
                   f"{'locked':>13} {'trades':>7}  {'kept':>7}")
        for entry in result.revealed:
            if entry.error:
                out.extend(_fit(f"   {entry.rank:<3} ", entry.error, width))
                out.extend(_fit("       ", entry.label, width))
                continue
            retention = entry.retention
            kept = "n/a" if not math.isfinite(retention) \
                else f"{retention * 100:.0f}%"
            out.append(
                f"   {entry.rank:<3} {entry.research_value:>13,.2f} "
                f"{entry.research_trades:>7,}   "
                f"{entry.holdout_value:>13,.2f} {entry.holdout_trades:>7,}  "
                f"{kept:>7}")
            out.extend(_fit("       ", entry.label, width))
        out.append("")

    out.append(rule)
    for note in result.notes:
        out.extend(textwrap.wrap(note, width))
        out.append("")
    return "\n".join(out).rstrip() + "\n"
