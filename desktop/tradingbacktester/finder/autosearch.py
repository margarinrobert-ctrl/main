"""Search every combination this data can support, and price the search itself.

The finder runs one style on one bar size: a thousand-odd combinations, judged
against a matched control and corrected for the multiplicity of that one run.
This does the whole grid -- every style, every bar size the data can build,
every entry-rule family, every geometry, both sides -- and that is a different
statistical problem, not just a bigger one.

**Why a bigger search needs a bigger correction, and what happens if it does not
get one.** A search of N combinations has N chances to be lucky. Run seven
searches of 1,500 and correct each one for 1,500, and the answer looks
significant seven times more often than it should -- the correction was applied
to a seventh of the search that actually happened. So every p-value from every
sweep goes into ONE Benjamini-Hochberg correction over the whole grid. That is
the only thing in this module that makes an exhaustive search worth running
rather than a machine for generating false positives.

The direct consequence, stated because users are surprised by it: **searching
harder makes every individual result harder to believe, not easier.** Ten
thousand combinations means the best one has to clear a bar ten thousand
combinations high. If that feels like the tool fighting you, the alternative is
a tool that hands you the best of ten thousand coin flips and calls it a
strategy.

**The best-of-N yardstick.** Correction aside, there is a second question worth
answering directly: on data with no edge at all, how good would the best of N
tries *look*? That number is computable -- the maximum of N draws from the
control's own null -- and it is reported beside the actual best. A result that
does not clear its own null's best-of-N is not a finding, whatever its p-value
says.

What this module does not do is decide anything for you. It runs the grid,
pools the correction, reports what survived and what the search cost, and if
nothing survived it says so in those words.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import numpy as np

from ..core.errors import BacktesterError, InsufficientDataError
from ..core.timeframe import Timeframe
from ..core.types import CostModel
from ..data.models import BarSeries
from .control import benjamini_hochberg
from .overfit import PBOResult
from .search import Finding, FinderReport, find_strategies
from .styles import STYLES, TradingStyle

log = logging.getLogger(__name__)

ProgressFn = Callable[[int, int, str], None]

#: The false-discovery rate the pooled correction is run at.
DEFAULT_ALPHA = 0.10

#: Draws used to estimate what the best of N tries looks like under the null.
NULL_DRAWS = 20_000

#: Sub-divisions of one sweep on the grid's progress bar. Progress is reported
#: in integers, so a sweep's own fraction needs somewhere to go.
_TICKS = 1000

#: How many survivors the full validation pass covers, best first.
#:
#: On data with a real edge the correction can pass most of the grid -- a
#: planted edge produced 1,441 survivors out of 2,436 scored -- and pushing all
#: of them back through the engine, the mirror, Monte Carlo and walk-forward is
#: hours of work for a list nobody reads past the top of. The cap is stated in
#: the report rather than applied silently, because a bound on coverage that
#: the reader cannot see reads as "we checked everything".
VALIDATION_CAP = 25

#: A sweep needs this many cross-validated candidates before its probability of
#: overfitting is allowed to speak for the whole grid.
#:
#: Without it the summary is decided by the WEAKEST sweep: a position-trading
#: search of daily bars scored 60 combinations, 36 of which traded in every
#: block, and its 0.75 -- an estimate over 36 candidates, next to another
#: sweep's over 1,488 -- was printed at the top of the report as the grid's
#: answer. Reporting the worst is right; letting the noisiest estimate be the
#: worst is not.
MIN_CANDIDATES_FOR_GRID = 100


@dataclass
class Sweep:
    """One (style, bar size) search inside the grid."""

    style: str
    timeframe: str
    combinations: int = 0
    scored: int = 0
    report: FinderReport | None = None
    error: str = ""
    elapsed: float = 0.0

    @property
    def ran(self) -> bool:
        return self.report is not None and not self.error

    def to_dict(self) -> dict[str, Any]:
        return {"style": self.style, "timeframe": self.timeframe,
                "combinations": self.combinations, "scored": self.scored,
                "error": self.error, "elapsed": round(self.elapsed, 2)}


@dataclass
class AutoSearchReport:
    """Everything the grid tried, and the few things that survived it."""

    symbol: str
    bars: int
    sweeps: list[Sweep] = field(default_factory=list)
    combinations: int = 0
    """Total (rule, geometry, style, bar size) pairs tried. The multiplicity."""
    scored: int = 0
    """How many of those produced enough trades to be scored at all."""
    survivors: list[Finding] = field(default_factory=list)
    """Findings that survived the correction over the WHOLE grid."""
    best: Finding | None = None
    """The best excess found, whether or not it survived. Read the verdict."""
    null_best: float = float("nan")
    """What the best of this many tries would score on data with no edge."""
    alpha: float = DEFAULT_ALPHA
    overfitting: "PBOResult | None" = None
    """The WORST probability of backtest overfitting among the sweeps.

    Worst rather than pooled, and worst rather than best: the sweeps have
    different bar sizes, so their blocks are different lengths and averaging
    them would be averaging incomparable things. Reporting the worst is the
    one summary that cannot flatter the grid -- but only among sweeps with
    enough candidates to have measured it properly. See
    :data:`MIN_CANDIDATES_FOR_GRID`."""
    overfitting_sweep: str = ""
    """Which sweep that came from, since it speaks for the grid."""
    elapsed: float = 0.0
    notes: list[str] = field(default_factory=list)
    origins: dict[tuple[str, str], str] = field(default_factory=dict)
    """``(rule label, bar size) -> style``, for naming where a survivor came
    from. Keyed on the finding's own description rather than on its identity
    because validation REPLACES a survivor with the object its sweep produced
    on the second, fully-checked pass: an identity lookup names every survivor
    correctly under ``validate="quick"`` and none of them under any other
    setting, which is the worst possible failure mode -- correct in the tests
    and blank in the application."""

    @property
    def found_anything(self) -> bool:
        return bool(self.survivors)

    def sweep_of(self, finding: Any) -> tuple[str, str]:
        """Which (style, bar size) search a finding came out of."""
        timeframe = str(getattr(finding, "timeframe", "") or "")
        style = self.origins.get((str(getattr(finding, "label", "")),
                                  timeframe), "")
        return (style or "—", timeframe or "—")

    @property
    def beats_its_own_null(self) -> bool:
        """Did the best result clear what luck alone would have produced?"""
        if self.best is None or not math.isfinite(self.null_best):
            return False
        return float(self.best.control.excess_per_trade) > self.null_best

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol, "bars": self.bars,
            "sweeps": [s.to_dict() for s in self.sweeps],
            "combinations": self.combinations, "scored": self.scored,
            "survivors": [f.to_dict() for f in self.survivors],
            "best": self.best.to_dict() if self.best else None,
            "null_best_excess": (None if not math.isfinite(self.null_best)
                                 else round(self.null_best, 4)),
            "beats_its_own_null": self.beats_its_own_null,
            "overfitting": (self.overfitting.to_dict() if self.overfitting
                            else None),
            "overfitting_sweep": self.overfitting_sweep,
            "origins": {f"{label}|{timeframe}": style
                        for (label, timeframe), style in self.origins.items()},
            "alpha": self.alpha,
            "elapsed_seconds": round(self.elapsed, 2),
            "notes": list(self.notes),
        }


def plan(bars: BarSeries, styles: Sequence[str] = (),
         timeframes: Sequence[str] = ()) -> list[tuple[TradingStyle, str]]:
    """Every (style, bar size) pair this data can actually support.

    Bars combine into longer ones and never the reverse, so five-minute data
    can be a scalp on 5m but never on 1m. A pair the data cannot build is left
    out of the plan rather than attempted and reported as an error.
    """
    wanted = {s.strip().lower() for s in styles if str(s).strip()}
    chosen = [s for s in STYLES if not wanted or s.key in wanted]
    if wanted and not chosen:
        raise BacktesterError(
            f"None of those are trading styles. Choose from: "
            f"{', '.join(s.key for s in STYLES)}.")
    asked = {t.strip().lower() for t in timeframes if str(t).strip()}

    out: list[tuple[TradingStyle, str]] = []
    for style in chosen:
        for name in style.timeframes:
            if asked and name.lower() not in asked:
                continue
            try:
                target = Timeframe.parse(name)
            except Exception:               # pragma: no cover - defensive
                continue
            same = target.approx_seconds == bars.timeframe.approx_seconds
            try:
                buildable = same or target.can_build_from(bars.timeframe)
            except Exception:               # pragma: no cover - defensive
                buildable = False
            if buildable:
                out.append((style, name))
    return out


def auto_search(bars: BarSeries, *, styles: Sequence[str] = (),
                timeframes: Sequence[str] = (),
                costs: CostModel | None = None,
                sides: tuple[int, ...] = (1, -1),
                templates: tuple[str, ...] = (),
                research_fraction: float = 0.65,
                alpha: float = DEFAULT_ALPHA,
                control_draws: int = 500,
                validate: str = "standard",
                top_n: int = 5, seed: int = 0,
                progress: ProgressFn | None = None) -> AutoSearchReport:
    """Run the whole grid, correct once over all of it, and report honestly."""
    started = time.time()
    pairs = plan(bars, styles, timeframes)
    if not pairs:
        raise InsufficientDataError(
            f"No trading style can be searched on {bars.timeframe.label} bars. "
            f"Bars can only be combined into longer ones, so a style needing a "
            f"finer bar size than the data has cannot run at all.")

    out = AutoSearchReport(symbol=getattr(bars.instrument, "symbol", "?"),
                           bars=len(bars), alpha=float(alpha))

    # -- every sweep, gated cheaply; the expensive checks come after ------
    steps = len(pairs) + 1
    for index, (style, timeframe) in enumerate(pairs):
        heading = (f"{style.label} on {timeframe} "
                   f"({index + 1} of {len(pairs)})")
        if progress is not None:
            progress(index * _TICKS, steps * _TICKS, heading)
        # A sweep can take a minute on its own, so its progress is mapped into
        # its slot on the grid's bar rather than swallowed. Without this the
        # bar sits still for the whole sweep and a Cancel pressed during one is
        # not noticed until it ends -- which on the full grid is the difference
        # between a responsive Stop button and one that appears broken.
        inner = None
        if progress is not None:
            def inner(done: int, of: int, message: str = "",
                      _i=index, _head=heading) -> None:   # noqa: F811
                share = min(1.0, (done / of) if of else 0.0)
                progress(int((_i + share) * _TICKS), steps * _TICKS,
                         f"{_head} — {message}" if message else _head)

        sweep = Sweep(style=style.key, timeframe=timeframe)
        clock = time.time()
        try:
            sweep.report = find_strategies(
                bars, style, timeframe=timeframe, costs=costs, sides=sides,
                templates=templates, research_fraction=research_fraction,
                top_n=top_n, control_draws=control_draws, alpha=alpha,
                seed=seed, validate="quick", progress=inner)
            sweep.combinations = int(sweep.report.combinations)
            sweep.scored = int(sweep.report.tested)
        except BacktesterError as exc:
            # One style that cannot run on this data must not lose the grid.
            sweep.error = exc.user_message
            log.info("Sweep %s/%s skipped: %s", style.key, timeframe,
                     sweep.error)
        except Exception as exc:            # noqa: BLE001 - same reason
            sweep.error = f"{type(exc).__name__}: {exc}"
            log.exception("Sweep %s/%s failed", style.key, timeframe)
        sweep.elapsed = time.time() - clock
        out.sweeps.append(sweep)
        out.combinations += sweep.combinations
        out.scored += sweep.scored
        if sweep.ran:
            for finding in sweep.report.findings:
                key = (finding.label, str(finding.timeframe))
                # Two styles can search the same bar size, so the same rule can
                # legitimately appear twice. Say "several" rather than pick one.
                previous = out.origins.get(key)
                out.origins[key] = (style.key if previous in (None, style.key)
                                    else "several")

    # -- ONE correction over the whole grid ------------------------------
    scored: list[Finding] = []
    for sweep in out.sweeps:
        if sweep.ran:
            scored.extend(sweep.report.findings)
    if scored:
        out.best = max(scored, key=lambda f: float(f.control.excess_per_trade))
        survives = benjamini_hochberg(
            [float(f.control.p_value) for f in scored], alpha)
        out.survivors = [f for f, ok in zip(scored, survives) if ok]
        out.survivors.sort(key=lambda f: -float(f.control.excess_per_trade))
        out.null_best = _null_best(scored, seed)
        _deflate_over_the_grid(out, scored)

    # A sweep measures its own probability of overfitting over its own blocks.
    # The grid's answer is the worst of them, for the reason on the field.
    measured = [(s, s.report.overfitting) for s in out.sweeps
                if s.ran and s.report.overfitting is not None
                and s.report.overfitting.ran]
    if measured:
        solid = [pair for pair in measured
                 if pair[1].candidates >= MIN_CANDIDATES_FOR_GRID]
        # If no sweep cleared the bar, the best-measured one speaks rather
        # than the worst: with every estimate thin, the widest sample is the
        # least misleading, and the candidate count is printed beside it.
        pool = solid or [max(measured, key=lambda pair: pair[1].candidates)]
        sweep, result = max(pool, key=lambda pair: pair[1].probability)
        out.overfitting = result
        out.overfitting_sweep = f"{sweep.style} on {sweep.timeframe}"

    # The grid was gated cheaply, because gating ten thousand combinations
    # through the engine would take hours to reject all but a handful. What
    # survived now gets the full treatment -- engine confirmation on both
    # blocks, concentration, Monte Carlo, mirror, walk-forward -- because a
    # candidate nobody validated is a claim, not a result.
    if out.survivors and validate != "quick":
        _validate_survivors(out, bars, costs, sides, templates,
                            research_fraction, alpha, control_draws, validate,
                            top_n, seed, progress, len(pairs))

    _notes(out, pairs)
    out.elapsed = time.time() - started
    if progress is not None:
        progress(steps * _TICKS, steps * _TICKS, "Done")
    return out


def _deflate_over_the_grid(out: AutoSearchReport,
                           scored: Sequence[Finding]) -> None:
    """Re-price every Sharpe for the size of the WHOLE grid.

    Each sweep deflated its findings against its own trial count, which is the
    right answer for that sweep and the wrong one here: a rule that came out of
    a 1,560-combination sweep of a 7,890-combination grid was selected from the
    grid. Re-pricing raises the benchmark and can only lower a deflated Sharpe,
    which is the direction an honest correction moves in.
    """
    sharpes = np.array([float(f.research.get("sharpe", 0.0)) for f in scored],
                       dtype="float64")
    sharpes = sharpes[np.isfinite(sharpes)]
    if sharpes.size < 2:
        return
    variance = float(sharpes.var(ddof=1))
    trials = len(scored)
    for finding in scored:
        if finding.deflated is not None:
            finding.deflated = finding.deflated.redeflate(trials, variance)


def _validate_survivors(out: AutoSearchReport, bars: BarSeries,
                        costs: CostModel | None, sides: tuple[int, ...],
                        templates: tuple[str, ...], research_fraction: float,
                        alpha: float, control_draws: int, validate: str,
                        top_n: int, seed: int, progress: ProgressFn | None,
                        planned: int) -> None:
    """Re-run the sweeps that produced survivors, with the real checks on.

    A survivor of a correction over the whole grid is by construction among the
    very best in its own sweep, so re-running that sweep with validation on
    puts it in the shortlist with its confirmation, its locked block and its
    robustness score attached. Only sweeps that produced something are re-run:
    on data with no edge that is none of them, and the pass costs nothing.

    Covers the best :data:`VALIDATION_CAP` survivors, and says so when there
    are more.
    """
    from .styles import style as get_style

    focus = out.survivors[:max(top_n, VALIDATION_CAP)]
    wanted = {id(f) for f in focus}
    by_sweep: dict[tuple[str, str], list[Finding]] = {}
    for sweep in out.sweeps:
        if not sweep.ran:
            continue
        hits = [f for f in sweep.report.findings if id(f) in wanted]
        if hits:
            by_sweep[(sweep.style, sweep.timeframe)] = hits
    if len(out.survivors) > len(focus):
        out.notes.append(
            f"The full checks -- engine confirmation on both blocks, "
            f"sub-period concentration, Monte Carlo, the mirror market and "
            f"walk-forward -- were run on the best {len(focus)} of "
            f"{len(out.survivors):,} survivors. The rest are listed with the "
            f"cheap gate's numbers and no engine confirmation, and are "
            f"unverified. A grid that passes most of its own combinations is "
            f"itself worth a second look: it usually means the data has one "
            f"large effect in it that almost any rule picks up.")

    replaced: dict[str, Finding] = {}
    for index, ((style_key, timeframe), hits) in enumerate(by_sweep.items()):
        if progress is not None:
            progress(planned * _TICKS, (planned + 1) * _TICKS,
                     f"Validating {len(hits)} survivor(s) from "
                     f"{style_key} {timeframe}")
        try:
            full = find_strategies(
                bars, get_style(style_key), timeframe=timeframe, costs=costs,
                sides=sides, templates=templates,
                research_fraction=research_fraction,
                top_n=max(top_n, len(hits)), control_draws=control_draws,
                alpha=alpha, seed=seed, validate=validate)
        except BacktesterError as exc:
            out.notes.append(
                f"The survivors from {style_key} on {timeframe} could not be "
                f"validated: {exc.user_message}. They are reported with the "
                f"cheap gate's numbers only.")
            continue
        for finding in full.shortlist:
            replaced[finding.label] = finding

    if not replaced:
        return
    out.survivors = [replaced.get(f.label, f) for f in out.survivors]
    # Verified first, then by excess. A survivor with the engine's numbers on
    # both blocks and a robustness score is a stronger claim than one carrying
    # only the cheap gate's, whatever their excesses say, and leading a table
    # with an unverified row is how "not run" ends up read as a result.
    out.survivors.sort(key=lambda f: (getattr(f, "confirmation", None) is None,
                                      -float(f.control.excess_per_trade)))
    unchecked = sum(1 for f in focus
                    if getattr(replaced.get(f.label, f), "confirmation",
                               None) is None)
    if unchecked:
        out.notes.append(
            f"{unchecked} of the {len(focus)} survivor(s) put through "
            f"validation did not come back in their sweep's shortlist, so "
            f"they carry the cheap gate's numbers and no engine confirmation. "
            f"Treat them as unverified.")


def _null_best(scored: Sequence[Finding], seed: int) -> float:
    """What the best excess of this many tries looks like with no edge at all.

    Every scored combination reports an excess and a standard error from its
    own matched control. Under the null its excess is centred on zero with that
    error, so one repetition of the whole search is one draw per combination
    and the best of them is the max. Repeat that and the median is the answer:
    the excess a search this size typically produces on nothing.

    Drawn rather than derived, because a closed form for the maximum would
    assume the combinations are independent and they are emphatically not --
    they share bars, geometries and rules. Drawing them independently makes
    this an OPTIMISTIC bar: correlated tries explore less, so the real
    best-of-N under the null is if anything smaller. A result that fails to
    clear even this has certainly not cleared the search that produced it.
    """
    errors = np.array([float(f.control.standard_error) for f in scored],
                      dtype="float64")
    errors = errors[np.isfinite(errors) & (errors > 0)]
    if errors.size == 0:
        return float("nan")

    repetitions = 2000
    # Cap the working array: 10,000 combinations by 2,000 repetitions is 160 MB
    # in one allocation, and the answer is identical taken a slice at a time.
    per_pass = max(1, min(repetitions, NULL_DRAWS // int(errors.size) or 1))
    best = np.empty(repetitions, dtype="float64")
    done = 0
    rng = np.random.default_rng(seed or 12345)
    while done < repetitions:
        rows = min(per_pass, repetitions - done)
        sample = rng.normal(0.0, errors, size=(rows, errors.size))
        best[done:done + rows] = sample.max(axis=1)
        done += rows
    return float(np.median(best))


def _notes(out: AutoSearchReport, pairs: Sequence[tuple]) -> None:
    """Everything a reader needs in order not to over-read the grid."""
    ran = [s for s in out.sweeps if s.ran]
    skipped = [s for s in out.sweeps if not s.ran]
    out.notes.append(
        f"{len(ran)} of {len(out.sweeps)} planned "
        f"{'search' if len(out.sweeps) == 1 else 'searches'} ran, covering "
        f"{out.combinations:,} combinations in total. "
        f"{out.scored:,} of those produced enough trades to be scored.")
    if skipped:
        out.notes.append(
            "Not run: " + "; ".join(
                f"{s.style} on {s.timeframe} ({s.error})" for s in skipped))

    if len(ran) > 1:
        out.notes.append(
            f"The correction is applied ONCE over all {out.scored:,} scored "
            f"combinations, not per search. Correcting each of the {len(ran)} "
            f"searches for its own size would report a result as significant "
            f"about {len(ran)} times more often than it should: the correction "
            f"would have been applied to a fraction of the search that "
            f"actually happened.")
    else:
        out.notes.append(
            f"The correction is applied ONCE over all {out.scored:,} scored "
            f"combinations. Only one search ran, so this grid is no harder to "
            f"clear than that search on its own — the pooling matters when "
            f"there are several.")
    out.notes.append(
        "Searching harder therefore makes every individual result HARDER to "
        "believe, not easier. That is the cost of an exhaustive search and it "
        "is the reason this one is worth running; the alternative is a tool "
        "that hands you the best of ten thousand coin flips.")

    if out.overfitting is not None and out.overfitting.ran:
        pbo = out.overfitting
        out.notes.append(
            f"Probability of backtest overfitting: {pbo.probability:.2f} "
            f"(the worst of the {len(ran)} searches — {out.overfitting_sweep}, "
            f"measured over {pbo.candidates:,} candidates and {pbo.splits:,} "
            f"half-and-half splits of {pbo.blocks} time-ordered pieces of the "
            f"research block). This asks whether SELECTION generalises, which "
            f"is a different question from whether any one candidate does, and "
            f"one no candidate's own statistics can answer. The in-sample "
            f"winner gave up {abs(pbo.degradation):.2f} of its metric out of "
            f"sample and was outright negative "
            f"{pbo.probability_of_loss:.0%} of the time. "
            + ("Above 0.5 the search is fitting noise: picking the winner did "
               "not carry over, and anything that survived should be treated "
               "as unproven however good its own numbers look."
               if pbo.probability > 0.5 else
               "At or below 0.5, picking the winner carried over to pieces it "
               "was not picked on -- necessary, not sufficient."))

    if out.best is not None and math.isfinite(out.null_best):
        out.notes.append(
            f"On data with no edge at all, the best of a search this size "
            f"would be expected to show an excess of about "
            f"{out.null_best:+,.2f} per trade simply by being the best of "
            f"{out.scored:,} tries. The best actually found is "
            f"{float(out.best.control.excess_per_trade):+,.2f}"
            + (", which clears that bar." if out.beats_its_own_null
               else ", which does NOT clear that bar — it is what a search "
                    "this size produces on nothing."))

    if not out.survivors:
        out.notes.append(
            "Nothing survived the correction. That is the ordinary outcome of "
            "an honest exhaustive search on one instrument over one period, "
            "and it is a result: the ground has been covered and there is no "
            "edge in it of the kind this grid can express.")
        if out.beats_its_own_null:
            # Two honest measurements can disagree, and a reader who sees the
            # best result clear its yardstick and the correction reject it
            # anyway deserves to be told which is the stricter of the two
            # rather than left to guess that one of them is broken.
            out.notes.append(
                "The best result did clear the best-of-N yardstick above "
                "while still failing the correction. The two are not the same "
                "test: the yardstick is deliberately optimistic — it draws "
                "the tries as if they were independent, and they are not — "
                "while the correction controls the false-discovery rate over "
                "the whole grid at "
                f"{out.alpha:.0%}. Clearing the looser of the two and failing "
                "the stricter is not a finding.")
    else:
        out.notes.append(
            f"{len(out.survivors)} combination(s) survived. Surviving the "
            f"correction is necessary, not sufficient: each one still has to "
            f"pass its own locked block, its neighbourhood and the engine, "
            f"which is what the detail below reports.")
    out.notes.append(
        "Everything here describes one instrument over one period. It is not "
        "a prediction, and a rule that survived can still lose money.")


def format_auto_search(report: AutoSearchReport, currency: str = "USD",
                       width: int = 78, top: int = 8) -> str:
    """The whole grid as plain text, with what it cost stated first."""
    import textwrap

    from ..core.textfmt import row as _fit

    rule = "-" * width
    out = _fit("", f"Exhaustive search — {report.symbol}", width)
    out.append(rule)
    out.extend(_fit("", f"{report.bars:,} bars. {len(report.sweeps)} searches, "
                    f"{report.combinations:,} combinations, "
                    f"{report.scored:,} scored.  {report.elapsed:.1f}s.",
                    width))
    out.append("")

    out.append(f"   {'style':<10} {'bars':<5} {'combinations':>13} "
               f"{'scored':>8} {'time':>7}")
    for sweep in report.sweeps:
        if not sweep.ran:
            out.extend(_fit(f"   {sweep.style:<10} {sweep.timeframe:<5} ",
                            f"not run — {sweep.error}", width))
            continue
        out.append(f"   {sweep.style:<10} {sweep.timeframe:<5} "
                   f"{sweep.combinations:>13,} {sweep.scored:>8,} "
                   f"{sweep.elapsed:>6.1f}s")
    out.append("")
    out.append(rule)

    # The yardstick first, because it is what decides how to read the rest.
    if report.best is not None and math.isfinite(report.null_best):
        actual = float(report.best.control.excess_per_trade)
        verdict = ("clears it" if report.beats_its_own_null
                   else "DOES NOT clear it")
        out.extend(_fit("", f"Best found: {actual:+,.2f} {currency} per trade. "
                        f"Best a search of {report.scored:,} tries produces on "
                        f"data with no edge: {report.null_best:+,.2f}. "
                        f"The finding {verdict}.", width))
        out.append("")
        if report.best.deflated is not None:
            out.extend(_fit("", "Deflated Sharpe of that finding: "
                            + report.best.deflated.describe() + ".", width))
            out.append("")

    if report.overfitting is not None and report.overfitting.ran:
        out.extend(_fit("", f"Worst of the {len(report.sweeps)} searches "
                        f"({report.overfitting_sweep}): "
                        + report.overfitting.describe(), width))
        out.append("")

    if report.survivors:
        out.extend(_fit("", f"{len(report.survivors):,} combination(s) "
                        f"survived the correction over the whole grid"
                        + (f" (the best {top} shown):" if
                           len(report.survivors) > top else ":"), width))
        out.append("")
        for index, finding in enumerate(report.survivors[:top], start=1):
            out.extend(_fit(f"   {index}. ", finding.label, width))
            style_key, timeframe = report.sweep_of(finding)
            out.extend(_fit("      ",
                            f"from the {style_key} search on {timeframe} bars",
                            width))
            control = finding.control
            out.extend(_fit("      ",
                            f"{int(finding.research.get('trades', 0)):,} trades, "
                            f"{float(finding.research.get('per_trade', 0.0)):+,.2f} "
                            f"{currency}/trade, excess "
                            f"{control.excess_per_trade:+,.2f} "
                            f"(p={control.p_value:.4g})", width))
            if finding.deflated is not None:
                out.extend(_fit("      ", "deflated Sharpe "
                                f"{finding.deflated.probability:.3f} "
                                f"({finding.deflated.sharpe:+.4f}/trade "
                                f"against {finding.deflated.benchmark:+.4f} "
                                f"for the best of "
                                f"{finding.deflated.trials:,} tries)", width))
            # Same three cases as `report._robustness_lines`, and for the same
            # reason: a number printed beside a disqualifying reason is a
            # number someone will quote without the reason, and "nan/100" is
            # not a score.
            score = getattr(finding, "robustness", None)
            if score is None:
                headline = ("not validated" if getattr(finding, "confirmation",
                                                       None) is None else "")
            elif score.blocked:
                headline = "robustness DISQUALIFIED"
            elif score.total != score.total:
                headline = "robustness unmeasured"
            else:
                headline = f"robustness {score.total:.0f}/100"
            out.extend(_fit("      ", " — ".join(
                bit for bit in (headline, finding.verdict) if bit), width))
            out.append("")
    else:
        out.extend(_fit("", "Nothing survived.", width))
        out.append("")

    out.append(rule)
    for note in report.notes:
        out.extend(textwrap.wrap(note, width))
        out.append("")
    return "\n".join(out).rstrip() + "\n"
