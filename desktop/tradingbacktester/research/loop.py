"""The research loop: hypothesis, experiment, verdict, repeat.

    research -> hypothesis -> generate -> backtest -> analyse ->
    reject/improve -> validate -> walk-forward -> rank -> report

The structural rule the whole module is built on, and the reason it is shaped
this way:

    **The proposer proposes.  The engine disposes.**

A proposer -- whether it is the systematic one in this file or a language model
behind :class:`Proposer` -- may only emit a *hypothesis*: a family to try, a
parameter range, a direction, a reason.  It never emits a number.  Every figure
that reaches a report comes from
:class:`~tradingbacktester.engine.backtester.Backtester` by way of
:mod:`tradingbacktester.finder.confirm`, and every verdict comes from
:mod:`tradingbacktester.finder.robustness`.  There is no path by which a
proposer's opinion about how a strategy performed can be printed, because a
proposer is never asked and its output has nowhere to put one.

That matters more for a language-model proposer than for the systematic one,
which is exactly why the seam is drawn here rather than inside the model
adapter.  A model that hallucinates a Sharpe ratio hallucinates it into a
field that does not exist.

What a round does
-----------------

Each round asks the proposer for hypotheses given everything learned so far,
runs each one as a real search over its family, confirms the survivors through
the engine, validates and scores them, and records what happened -- including
the ones that failed, and why.  A hypothesis that fails is not discarded: it is
the input to the next round, because "trend-following on this instrument beats
nothing at 15m" is a finding, and a loop that only remembers its successes is a
loop that keeps re-proposing its failures.

The loop stops when it runs out of rounds, out of hypotheses, or out of ideas
the proposer has not already tried.  It does not stop when it finds something,
because the first thing found is not evidence that it is the best thing.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

log = logging.getLogger(__name__)

ProgressFn = Callable[[int, int, str], None]

#: How many hypotheses one round may ask for.  Small: each is a real search
#: with a real multiplicity cost, and the loop states the total at the end.
HYPOTHESES_PER_ROUND = 3

#: Rounds before the loop gives up on its own.
DEFAULT_ROUNDS = 3


@dataclass
class Hypothesis:
    """A claim to test.  Deliberately carries no numbers about performance.

    A proposer fills this in.  There is no field for a result, an expected
    return, a Sharpe ratio or a win rate, and that is not an oversight: a
    proposer that could state one could state a false one.
    """

    idea: str
    """What is being claimed, in a sentence. Shown to the user verbatim."""
    templates: tuple[str, ...] = ()
    """Entry-rule families to search. Empty means every family."""
    sides: tuple[int, ...] = (1, -1)
    timeframe: str = ""
    """Empty means "whatever this data can actually produce"."""
    rationale: str = ""
    """Why this is worth a test. Prose, never a prediction."""
    source: str = "systematic"
    """Which proposer emitted it."""

    def key(self) -> tuple:
        """Identity, so the loop does not re-run a hypothesis it has tried."""
        return (tuple(sorted(self.templates)), tuple(sorted(self.sides)),
                self.timeframe)

    def to_dict(self) -> dict[str, Any]:
        return {"idea": self.idea, "templates": list(self.templates),
                "sides": list(self.sides), "timeframe": self.timeframe,
                "rationale": self.rationale, "source": self.source}


@dataclass
class Experiment:
    """One hypothesis, run.  Everything here came out of the engine."""

    hypothesis: Hypothesis
    round_index: int
    combinations: int = 0
    tested: int = 0
    shortlisted: int = 0
    survivors: list[Any] = field(default_factory=list)
    """Findings that were not disqualified. Each carries its own confirmation,
    validations and robustness score."""
    best_score: float = float("nan")
    verdict: str = ""
    notes: list[str] = field(default_factory=list)
    error: str = ""
    elapsed: float = 0.0

    @property
    def worked(self) -> bool:
        return bool(self.survivors) and not self.error

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis": self.hypothesis.to_dict(),
            "round": self.round_index,
            "combinations": self.combinations, "tested": self.tested,
            "shortlisted": self.shortlisted,
            "survivors": [f.to_dict() for f in self.survivors],
            "best_score": (None if not math.isfinite(self.best_score)
                           else round(self.best_score, 1)),
            "verdict": self.verdict, "notes": list(self.notes),
            "error": self.error, "elapsed_seconds": round(self.elapsed, 2),
        }


@dataclass
class LoopReport:
    """Every experiment the loop ran, and what it concluded."""

    symbol: str = ""
    style: str = ""
    rounds: int = 0
    experiments: list[Experiment] = field(default_factory=list)
    elapsed: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def total_combinations(self) -> int:
        """The multiplicity of the WHOLE loop, not of one search.

        Reported because it is the number of chances the loop had to be lucky,
        and it is much larger than any single search's -- which is the honest
        cost of automating this.
        """
        return sum(e.combinations for e in self.experiments)

    @property
    def survivors(self) -> list[Any]:
        """Every candidate that was not disqualified, ranked, deduplicated.

        Two experiments can legitimately arrive at the same rule -- a family
        tested alone and again inside a wider pool, say -- and listing it twice
        would report one finding as two.
        """
        from ..finder.robustness import rank

        out: list[Any] = []
        seen: set[str] = set()
        for experiment in self.experiments:
            for finding in experiment.survivors:
                label = getattr(finding, "label", "")
                if label in seen:
                    continue
                seen.add(label)
                out.append(finding)
        return rank(out)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol, "style": self.style, "rounds": self.rounds,
            "experiments": [e.to_dict() for e in self.experiments],
            "total_combinations": self.total_combinations,
            "elapsed_seconds": round(self.elapsed, 2),
            "notes": list(self.notes),
        }


class Proposer(Protocol):
    """Emits hypotheses.  Never emits a measurement.

    Implement this to plug in a language model, a paper-reading agent, or
    anything else.  The contract is one method and one return type, and the
    return type has nowhere to put a performance claim.
    """

    name: str

    def propose(self, context: "Context") -> list[Hypothesis]:
        """Up to :data:`HYPOTHESES_PER_ROUND` things worth testing next."""
        ...


@dataclass
class Context:
    """What the proposer is allowed to know: the data, and what happened."""

    symbol: str
    timeframe: str
    bars: int
    style_key: str
    style_label: str
    families: tuple[str, ...]
    """Every entry-rule family available to search."""
    history: list[Experiment] = field(default_factory=list)
    round_index: int = 0

    def tried(self) -> set[tuple]:
        return {e.hypothesis.key() for e in self.history}

    def summary(self) -> str:
        """The history as prose, for a proposer that reads rather than computes."""
        if not self.history:
            return "Nothing has been tried yet."
        lines: list[str] = []
        for experiment in self.history:
            outcome = (f"{len(experiment.survivors)} survived"
                       if experiment.worked else
                       experiment.error or experiment.verdict or "nothing survived")
            lines.append(f"- {experiment.hypothesis.idea} -> {outcome}")
        return "\n".join(lines)


class SystematicProposer:
    """The offline proposer.  Enumerates families, then narrows on what worked.

    No network, no model, no key.  It is the default because a research loop
    that only runs when an external service is reachable is a research loop
    that does not run.

    Its strategy is deliberately dull: try each family alone first, because a
    family that beats a matched control on its own is the only evidence worth
    building on; then re-test the families that survived on the other side, and
    at a different bar size.  Dull is the point -- it means every hypothesis it
    emits can be justified in one sentence from what came before.
    """

    name = "systematic"

    def propose(self, context: Context) -> list[Hypothesis]:
        tried = context.tried()
        out: list[Hypothesis] = []

        if context.round_index == 0:
            for family in context.families:
                candidate = Hypothesis(
                    idea=f"The {family.replace('_', ' ')} family has an edge on "
                         f"{context.symbol} that beats entering at random at "
                         f"the same times",
                    templates=(family,),
                    rationale="Each family is tried alone first: a family that "
                              "beats its control by itself is the only evidence "
                              "worth building on.",
                    source=self.name)
                if candidate.key() not in tried:
                    out.append(candidate)
            return out[:HYPOTHESES_PER_ROUND]

        # Later rounds: narrow onto whatever survived, one variable at a time.
        worked = [e for e in context.history if e.worked]
        if not worked:
            # Nothing survived on its own. Widen rather than narrow: try every
            # family together, which is a different (and weaker) question, and
            # say so.
            candidate = Hypothesis(
                idea="Some rule somewhere in the whole family pool beats its "
                     "control, even though no single family did",
                templates=(),
                rationale="No family survived alone, so this widens the search "
                          "instead of narrowing it. The multiplicity is much "
                          "larger and the correction is correspondingly harsher.",
                source=self.name)
            return [candidate] if candidate.key() not in tried else []

        for experiment in worked:
            if len(out) >= HYPOTHESES_PER_ROUND:
                break
            previous = experiment.hypothesis
            family = previous.templates[0] if previous.templates else ""
            label = family.replace("_", " ") or "surviving"

            # Only propose a side test when there is a side left to test. A
            # search that already ran both directions has nothing to flip, and
            # proposing one anyway re-runs the identical search and reports the
            # same rule twice as if it were two findings.
            candidate: Hypothesis | None = None
            if len(previous.sides) == 1:
                candidate = Hypothesis(
                    idea=f"The {label} edge is a property of the rule, not of "
                         f"the direction — it should show up on the other side "
                         f"too",
                    templates=previous.templates,
                    sides=(-previous.sides[0],),
                    timeframe=previous.timeframe,
                    rationale="Every dataset here is an instrument that went "
                              "up. A rule that only works long may be riding "
                              "that.",
                    source=self.name)
            else:
                # Both sides already tested. The next variable worth moving is
                # the bar size: an edge that lives at exactly one is a property
                # of that sampling, not of the market.
                for timeframe in _style_timeframes(context):
                    trial = Hypothesis(
                        idea=f"The {label} edge survives a change of bar size, "
                             f"so it is a property of the market rather than of "
                             f"how the data was sampled",
                        templates=previous.templates,
                        sides=previous.sides, timeframe=timeframe,
                        rationale="An edge that exists at exactly one bar size "
                                  "is a property of that sampling.",
                        source=self.name)
                    if trial.key() not in tried:
                        candidate = trial
                        break
            if candidate is not None and candidate.key() not in tried:
                out.append(candidate)
                tried.add(candidate.key())
        return out[:HYPOTHESES_PER_ROUND]


def _style_timeframes(context: Context) -> tuple[str, ...]:
    """Bar sizes this style accepts AND this data can actually produce.

    Bars can only be combined into longer ones, never split, so proposing a
    finer bar size than the dataset has is proposing an experiment that cannot
    run.  Filtering here rather than letting the search raise keeps a wasted
    round out of the report -- a failed experiment should mean the idea failed,
    not that the loop asked for something impossible.
    """
    from ..core.timeframe import Timeframe
    from ..finder.styles import style as lookup

    try:
        style = lookup(context.style_key)
        have = Timeframe.parse(context.timeframe).approx_seconds
    except Exception:                       # noqa: BLE001 - a proposer that
        return ()                           # cannot look one up proposes none

    out: list[str] = []
    for candidate in getattr(style, "timeframes", ()):
        if candidate == context.timeframe:
            continue
        try:
            if Timeframe.parse(candidate).approx_seconds >= have:
                out.append(candidate)
        except Exception:                   # noqa: BLE001 - an unparseable
            continue                        # timeframe is simply not proposed
    return tuple(out)


def _families() -> tuple[str, ...]:
    from ..finder.candidates import TEMPLATES

    return tuple(t.key for t in TEMPLATES)


def run_loop(bars: Any, style: Any, *, proposer: Proposer | None = None,
             rounds: int = DEFAULT_ROUNDS, validate: str = "standard",
             control_draws: int = 500, seed: int = 0,
             progress: ProgressFn | None = None) -> LoopReport:
    """Run the loop and report every experiment, including the failures.

    Never raises for a hypothesis that cannot be searched: that experiment
    records its error and the loop continues, because one unrunnable idea is
    not a reason to lose the rest of the research.
    """
    from ..finder import find_strategies

    started = time.time()
    proposer = proposer or SystematicProposer()
    report = LoopReport(
        symbol=getattr(bars.instrument, "symbol", "?"),
        style=getattr(style, "label", "?"), rounds=int(rounds))

    context = Context(
        symbol=report.symbol,
        timeframe=getattr(getattr(bars, "timeframe", None), "label", ""),
        bars=len(bars), style_key=getattr(style, "key", ""),
        style_label=report.style, families=_families())

    total_steps = max(1, int(rounds) * HYPOTHESES_PER_ROUND)
    step = 0

    for round_index in range(int(rounds)):
        context.round_index = round_index
        try:
            hypotheses = list(proposer.propose(context))[:HYPOTHESES_PER_ROUND]
        except Exception as exc:            # noqa: BLE001 - a proposer that
            # fails is a proposer that stops, not a loop that crashes.
            report.notes.append(
                f"The {getattr(proposer, 'name', '?')} proposer failed in round "
                f"{round_index + 1} ({type(exc).__name__}: {exc}), so the loop "
                f"stopped there.")
            break

        if not hypotheses:
            report.notes.append(
                f"The proposer had nothing new to suggest in round "
                f"{round_index + 1}, so the loop stopped with "
                f"{len(report.experiments)} experiments rather than repeating "
                f"itself.")
            break

        for hypothesis in hypotheses:
            step += 1
            if progress is not None:
                progress(step, total_steps,
                         f"Round {round_index + 1}: {hypothesis.idea[:70]}")
            experiment = _run_one(bars, style, hypothesis, round_index,
                                  validate, control_draws, seed,
                                  find_strategies)
            report.experiments.append(experiment)
            context.history.append(experiment)

    report.elapsed = time.time() - started
    _conclude(report)
    return report


def _run_one(bars: Any, style: Any, hypothesis: Hypothesis, round_index: int,
             validate: str, control_draws: int, seed: int,
             find_strategies: Any) -> Experiment:
    """Search one hypothesis.  Every figure comes back from the engine."""
    experiment = Experiment(hypothesis=hypothesis, round_index=round_index)
    started = time.time()
    try:
        found = find_strategies(
            bars, style, templates=tuple(hypothesis.templates),
            sides=tuple(hypothesis.sides),
            timeframe=hypothesis.timeframe,
            control_draws=control_draws, seed=seed, validate=validate)
    except Exception as exc:                # noqa: BLE001 - see run_loop
        experiment.error = f"{type(exc).__name__}: {exc}"
        experiment.verdict = "could not be tested"
        experiment.elapsed = time.time() - started
        log.debug("Hypothesis failed: %s", exc)
        return experiment

    experiment.combinations = found.combinations
    experiment.tested = found.tested
    experiment.shortlisted = len(found.shortlist)
    experiment.notes = list(found.notes)

    survivors = [f for f in found.shortlist
                 if getattr(f, "robustness", None) is not None
                 and not f.robustness.blocked]
    experiment.survivors = survivors
    scores = [f.robustness.total for f in survivors
              if math.isfinite(f.robustness.total)]
    experiment.best_score = max(scores) if scores else float("nan")

    if survivors:
        experiment.verdict = (
            f"{len(survivors)} of {experiment.shortlisted} shortlisted rules "
            f"survived every disqualifying check")
    elif experiment.shortlisted:
        experiment.verdict = (
            f"{experiment.shortlisted} shortlisted, none survived — the "
            f"reasons are on each candidate")
    else:
        experiment.verdict = "nothing was shortlisted"
    experiment.elapsed = time.time() - started
    return experiment


def _conclude(report: LoopReport) -> None:
    """The honest summary, including the multiplicity the loop itself created."""
    survivors = report.survivors
    total = report.total_combinations

    report.notes.append(
        f"{len(report.experiments)} experiments over {total:,} rule-and-geometry "
        f"combinations in total. That total is the number of chances this loop "
        f"had to be lucky, and it is much larger than any single search's — "
        f"which is the price of automating the search. Each experiment applied "
        f"its own multiplicity correction; none of them corrected for the "
        f"others.")

    if not survivors:
        report.notes.append(
            "Nothing survived. That is the normal outcome of an honest search "
            "and it is worth more than a shortlist would be: the loop tested "
            "every family it had and none of them beat entering at random at "
            "the same times by enough to survive its own multiplicity.")
    else:
        report.notes.append(
            f"{len(survivors)} candidate(s) were not disqualified. Ranked by "
            f"robustness, never by return. Read the blockers on the ones that "
            f"were disqualified too — a rule that fails for a stated reason is "
            f"more informative than one that was never tried.")

    # On every path, including the one where nothing was found. A caveat that
    # only appears beside a result is a caveat that appears exactly when it is
    # least likely to be read.
    report.notes.append(
        "Everything above describes what already happened on one instrument "
        "over one period. It is not a prediction, and a candidate that "
        "survived here can still lose money.")
