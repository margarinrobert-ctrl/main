"""Searching for a strategy without fooling yourself.

Given bars and a trading style, this tries every entry rule in the candidate
space against every geometry the style allows, and reports what survived. The
searching is the easy part. Everything else here exists to stop the search
producing a confident answer that means nothing, because that is what a search
does by default.

The protocol, in order, and none of the steps are optional:

1. **Split the data in time.** The first 65% is the research block; the last
   35% is locked. Every decision -- which rule, which parameters, which
   geometry -- is made on the research block alone.
2. **Score against a matched control, as a gate.** Random entries at the same
   times with the same geometry price in drift, costs, barrier width and
   session timing at once. A candidate has to beat that, not zero.
3. **Correct for multiplicity.** The number of combinations tried is the number
   of chances the search had to be lucky. It is reported, and a
   false-discovery-rate correction is applied to the p-values.
4. **Test the neighbourhood.** A real edge decays smoothly as its parameters
   move. One that vanishes a rung away was a coincidence at one setting; that
   is the single most reliable tell there is.
5. **Reveal the locked block once**, for the shortlist only, and report it as
   an out-of-sample check rather than as a score to select on.
6. **Say what it means.** A result that is better on the locked block than on
   research is the wrong shape and is labelled as such, not celebrated.

Everything it produces is a description of what already happened. It is not a
prediction, and the report says so in those words.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from ..core.errors import InsufficientDataError
from ..core.timeframe import Timeframe
from ..core.types import CostModel, SlippageMode, SpreadMode
from ..data.models import BarSeries
from .candidates import (Candidate, TEMPLATES_BY_KEY, all_candidates,
                         build_spec, signals_for, warmup_for)
from .control import ControlResult, analytic_control, benjamini_hochberg, sampled_control
from .outcomes import (EXIT_NAMES, Geometry, OutcomeCache, build_outcomes,
                       select_sequential, session_entry_mask,
                       session_hold_limit)
from .styles import TradingStyle

ProgressFn = Callable[[int, int, str], None]

#: Candidates below this are not reported at all, whatever they earned: with
#: too few trades the result is a description of a handful of days.
ABSOLUTE_MIN_TRADES = 25


@dataclass
class Neighbourhood:
    """How a candidate's edge behaves when its settings are nudged."""

    tested: int
    positive: int
    median_excess: float
    own_excess: float

    @property
    def fraction_positive(self) -> float:
        return self.positive / self.tested if self.tested else 0.0

    @property
    def smooth(self) -> bool:
        """True when the edge survives being moved, rather than sitting on a spike."""
        return self.tested >= 2 and self.fraction_positive >= 0.5


@dataclass
class Finding:
    """One entry rule at one geometry, and everything measured about it."""

    candidate: Candidate
    timeframe: str
    stop_atr: float
    target_r: float
    research: dict[str, float]
    control: ControlResult
    survives_fdr: bool = False
    sampled: ControlResult | None = None
    neighbourhood: Neighbourhood | None = None
    holdout: dict[str, float] | None = None
    holdout_control: ControlResult | None = None
    verdict: str = ""
    concerns: list[str] = field(default_factory=list)
    spec: Any = None

    @property
    def label(self) -> str:
        template = TEMPLATES_BY_KEY[self.candidate.template]
        bits = ", ".join(f"{k}={v}" for k, v in self.candidate.params.items())
        return (f"{template.label} {self.candidate.side_label} [{bits}] "
                f"stop {self.stop_atr:g}xATR target {self.target_r:g}R")

    @property
    def excess(self) -> float:
        return self.control.excess_per_trade

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "template": self.candidate.template,
            "params": dict(self.candidate.params),
            "side": self.candidate.side_label,
            "timeframe": self.timeframe,
            "stop_atr": self.stop_atr,
            "target_r": self.target_r,
            "research": dict(self.research),
            "control_excess_per_trade": self.control.excess_per_trade,
            "control_p_value": self.control.p_value,
            "survives_fdr": self.survives_fdr,
            "sampled_p_value": (self.sampled.p_value if self.sampled else None),
            "neighbourhood_positive": (self.neighbourhood.fraction_positive
                                       if self.neighbourhood else None),
            "holdout": dict(self.holdout) if self.holdout else None,
            "holdout_excess_per_trade": (self.holdout_control.excess_per_trade
                                         if self.holdout_control else None),
            "holdout_p_value": (self.holdout_control.p_value
                                if self.holdout_control else None),
            "verdict": self.verdict,
            "concerns": list(self.concerns),
        }


@dataclass
class FinderReport:
    """The outcome of one search, including everything needed to judge it."""

    style: TradingStyle
    timeframe: str
    symbol: str
    bars: int
    research_bars: int
    holdout_bars: int
    research_start: str
    research_end: str
    holdout_end: str
    combinations: int
    """How many (rule, geometry) pairs were tried. The multiplicity."""
    tested: int
    """How many of them had enough trades to be scored at all."""
    findings: list[Finding] = field(default_factory=list)
    shortlist: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    elapsed: float = 0.0

    @property
    def found_anything(self) -> bool:
        return any(f.verdict.startswith("worth") for f in self.shortlist)

    def to_dict(self) -> dict[str, Any]:
        return {
            "style": self.style.key, "timeframe": self.timeframe,
            "symbol": self.symbol, "bars": self.bars,
            "research_bars": self.research_bars,
            "holdout_bars": self.holdout_bars,
            "research": [self.research_start, self.research_end],
            "holdout_end": self.holdout_end,
            "combinations": self.combinations, "tested": self.tested,
            "elapsed_seconds": round(self.elapsed, 2),
            "shortlist": [f.to_dict() for f in self.shortlist],
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# session handling
# ---------------------------------------------------------------------------


def default_costs(instrument) -> CostModel:
    """The instrument's own published costs, which are never zero."""
    spread = float(getattr(instrument, "default_spread_points", 0.0) or 0.0)
    commission = float(getattr(instrument, "default_commission", 0.0) or 0.0)
    costs = CostModel()
    if spread > 0:
        costs.spread_mode = SpreadMode.HALF_EACH_SIDE
        costs.spread_points = spread
    if commission > 0:
        costs.commission_value = commission
    costs.slippage_mode = SlippageMode.NONE
    return costs


# ---------------------------------------------------------------------------
# the search
# ---------------------------------------------------------------------------


def choose_timeframe(bars: BarSeries, style: TradingStyle) -> str:
    """The best bar size for this style that these bars can actually produce.

    A style lists its timeframes best-first, but bars can only be combined into
    longer ones: five-minute data cannot make one-minute bars. Rather than
    failing with an arithmetic complaint, the search takes the best size it can
    build and says which one it used.
    """
    for name in style.timeframes:
        wanted = Timeframe.parse(name)
        if bars.timeframe.approx_seconds == wanted.approx_seconds:
            return name
        try:
            if wanted.can_build_from(bars.timeframe):
                return name
        except Exception:                   # pragma: no cover - defensive
            continue
    return bars.timeframe.label


def prepare_bars(bars: BarSeries, timeframe: str) -> BarSeries:
    """Resample to the timeframe the style wants, if it is not already there."""
    wanted = Timeframe.parse(timeframe)
    if bars.timeframe.approx_seconds == wanted.approx_seconds:
        return bars
    from ..data.resample import resample

    return resample(bars, wanted)


#: Every analysis in this package needs at least this many bars before its
#: research/holdout split leaves enough on either side to mean anything.
MIN_BARS = 500


def too_few_bars(what: str, bars: BarSeries, working: BarSeries,
                 timeframe: str, minimum: int = MIN_BARS) -> str:
    """The message for a dataset that is too short, with usable advice.

    "Choose a smaller bar size" is the obvious suggestion and it is wrong
    whenever the analysis is already running at the dataset's own timeframe --
    which is exactly the case for a daily file, where it was the only advice
    being offered.
    """
    line = (f"{what} needs at least {minimum:,} bars and this dataset has "
            f"{len(working):,} at {timeframe}.")
    finer = bars.timeframe.approx_seconds < working.timeframe.approx_seconds
    if finer:
        return (f"{line} Import more history, or choose a smaller bar size — "
                f"the file itself is {bars.timeframe.label} "
                f"({len(bars):,} bars).")
    return (f"{line} {bars.timeframe.label} is the finest bar size this file "
            f"contains, so only more history will help.")


def find_strategies(bars: BarSeries, style: TradingStyle, *,
                    timeframe: str = "", costs: CostModel | None = None,
                    sides: tuple[int, ...] = (1, -1),
                    templates: tuple[str, ...] = (),
                    research_fraction: float = 0.65,
                    top_n: int = 5, control_draws: int = 2000,
                    alpha: float = 0.10, seed: int = 0,
                    progress: ProgressFn | None = None) -> FinderReport:
    """Search for entry rules that beat a matched control, and report honestly."""
    started = time.time()
    requested = timeframe
    timeframe = timeframe or choose_timeframe(bars, style)
    working = prepare_bars(bars, timeframe)
    n = len(working)
    if n < MIN_BARS:
        raise InsufficientDataError(
            too_few_bars("A search", bars, working, timeframe))

    instrument = working.instrument
    timezone = getattr(instrument, "timezone", "UTC") or "UTC"
    costs = costs if costs is not None else default_costs(instrument)

    split = int(n * float(research_fraction))
    research = np.zeros(n, dtype=bool)
    research[:split] = True
    holdout = ~research

    entry_ok = session_entry_mask(
        working, timezone,
        style.session[0] if style.session else None,
        style.session[1] if style.session else None, style.weekdays,
        style.flat_at_session_end)
    hold_limit = None
    if style.session is not None and style.flat_at_session_end:
        hold_limit = session_hold_limit(working, timezone, style.session[0],
                                        style.session[1], style.max_bars,
                                        style.weekdays)

    candidates = all_candidates(sides, templates)
    geometries = style.geometries()
    combinations = len(candidates) * len(geometries)

    notes: list[str] = []
    if not requested and timeframe != style.timeframes[0]:
        notes.append(
            f"This style prefers {style.timeframes[0]} bars, but the dataset is "
            f"{bars.timeframe.label} and bars can only be combined into longer "
            f"ones, so the search ran on {timeframe}.")
    notes.append(
        f"{combinations:,} combinations were tried: {len(candidates)} entry "
        f"rules x {len(geometries)} geometries. That is how many chances the "
        f"search had to be lucky. The correction is applied over the ones that "
        f"produced enough trades to be scored at all -- stated with the "
        f"results above -- since a combination that never traded was never a "
        f"chance to be lucky.")

    # -- signals, once per candidate ------------------------------------
    signal_cache: dict[tuple, np.ndarray] = {}
    for index, candidate in enumerate(candidates):
        if progress is not None and index % 5 == 0:
            progress(index, len(candidates) + combinations,
                     f"Reading {len(candidates)} entry rules")
        signal_cache[candidate.key()] = entry_ok & signals_for(
            working, candidate, warmup_for(candidate, style.atr_period))

    # -- outcomes, once per geometry ------------------------------------
    caches: dict[tuple[int, float, float], OutcomeCache] = {}
    for side in sides:
        for stop_atr, target_r in geometries:
            caches[(side, stop_atr, target_r)] = build_outcomes(
                working, Geometry(side, stop_atr, target_r, style.max_bars,
                                  style.atr_period), costs, hold_limit,
                detail=False)

    findings: list[Finding] = []
    step = len(candidates)
    minimum = max(ABSOLUTE_MIN_TRADES, int(style.min_trades))
    for candidate in candidates:
        mask = signal_cache[candidate.key()]
        for stop_atr, target_r in geometries:
            step += 1
            if progress is not None and step % 25 == 0:
                progress(step, len(candidates) + combinations,
                         f"Scoring {combinations:,} combinations")
            cache = caches[(candidate.side, stop_atr, target_r)]
            finding = _score(cache, mask, research, candidate, timeframe,
                             stop_atr, target_r, minimum)
            if finding is not None:
                findings.append(finding)

    if not findings:
        notes.append(
            f"Nothing was scored: no combination produced at least {minimum} "
            f"trades on the research block. That is a statement about the "
            f"dataset, not about the rules -- try a smaller bar size, more "
            f"history, or a style with a shorter hold.")
        return _report(style, timeframe, working, split, combinations, 0,
                       findings, [], notes, started)

    survives = benjamini_hochberg([f.control.p_value for f in findings], alpha)
    for finding, ok in zip(findings, survives):
        finding.survives_fdr = bool(ok)

    # Rank by the SIZE of the excess among survivors, never by its sign alone:
    # over a grid of thresholds a "positive excess" set is just its loosest
    # member, and ranking on sign selects that every time.
    ranked = sorted((f for f in findings if f.survives_fdr),
                    key=lambda f: -f.excess)
    if not ranked:
        best = max(findings, key=lambda f: f.excess)
        notes.append(
            f"No combination survived the multiplicity correction. The best "
            f"was {best.label} at p={best.control.p_value:.3f}, which needs to "
            f"be below about {alpha / len(findings):.5f} to mean anything "
            f"across {len(findings):,} tests. This is the normal outcome of an "
            f"honest search and it is worth more than a shortlist would be.")
        best.verdict = "not worth trading — did not survive multiplicity"
        # Still build it as a real strategy: the row is shown, so it should be
        # openable and chartable like any other. Being able to look at what
        # nearly worked is worth more than a row that cannot be clicked.
        best.spec = build_spec(
            best.candidate, style, timeframe, best.stop_atr, best.target_r,
            costs, name=f"Found · {best.label}", instrument_timezone=timezone)
        _reveal(caches[(best.candidate.side, best.stop_atr, best.target_r)],
                signal_cache[best.candidate.key()], holdout, best, minimum)
        return _report(style, timeframe, working, split, combinations,
                       len(findings), findings, [best], notes, started)

    shortlist = _deduplicate(ranked)[:max(1, int(top_n))]

    # -- confirm the shortlist ------------------------------------------
    for position, finding in enumerate(shortlist):
        if progress is not None:
            progress(len(candidates) + combinations, len(candidates) + combinations,
                     f"Checking shortlisted rule {position + 1} of {len(shortlist)}")
        cache = caches[(finding.candidate.side, finding.stop_atr, finding.target_r)]
        mask = signal_cache[finding.candidate.key()]
        finding.sampled = _sampled(cache, mask, research, control_draws, seed)
        finding.neighbourhood = _neighbourhood(
            working, caches, signal_cache, research, finding, style, minimum,
            entry_ok)
        _reveal(cache, mask, holdout, finding, minimum)
        finding.spec = build_spec(
            finding.candidate, style, timeframe, finding.stop_atr,
            finding.target_r, costs,
            name=f"Found · {finding.label}", instrument_timezone=timezone)
        _judge(finding, minimum)

    return _report(style, timeframe, working, split, combinations,
                   len(findings), findings, shortlist, notes, started)


# ---------------------------------------------------------------------------
# the pieces
# ---------------------------------------------------------------------------


def _score(cache: OutcomeCache, mask: np.ndarray, block: np.ndarray,
           candidate: Candidate, timeframe: str, stop_atr: float,
           target_r: float, minimum: int) -> Finding | None:
    """Evaluate one candidate on one block, against its matched control."""
    kept = select_sequential(cache, mask & block)
    count = int(kept.sum())
    if count < minimum:
        return None
    pool = cache.valid & block
    control = analytic_control(cache.minute_of_day[pool], cache.net_cash[pool],
                               cache.minute_of_day[kept], cache.net_cash[kept])
    return Finding(candidate=candidate, timeframe=timeframe, stop_atr=stop_atr,
                   target_r=target_r, research=cache.summary(kept),
                   control=control)


def _sampled(cache: OutcomeCache, mask: np.ndarray, block: np.ndarray,
             draws: int, seed: int) -> ControlResult:
    kept = select_sequential(cache, mask & block)
    pool = cache.valid & block
    return sampled_control(cache.minute_of_day[pool], cache.net_cash[pool],
                           cache.minute_of_day[kept], cache.net_cash[kept],
                           draws=draws, seed=seed)


def _reveal(cache: OutcomeCache, mask: np.ndarray, block: np.ndarray,
            finding: Finding, minimum: int) -> None:
    """Look at the locked block. Once, for one candidate, after it was chosen."""
    kept = select_sequential(cache, mask & block)
    finding.holdout = cache.summary(kept)
    if int(kept.sum()) == 0:
        return
    pool = cache.valid & block
    finding.holdout_control = analytic_control(
        cache.minute_of_day[pool], cache.net_cash[pool],
        cache.minute_of_day[kept], cache.net_cash[kept])


def _neighbourhood(bars: BarSeries, caches: dict, signal_cache: dict,
                   block: np.ndarray, finding: Finding, style: TradingStyle,
                   minimum: int, entry_ok: np.ndarray) -> Neighbourhood:
    """Nudge the settings one rung each way and see whether the edge follows."""
    template = TEMPLATES_BY_KEY[finding.candidate.template]
    excesses: list[float] = []

    for name, values in template.grid.items():
        current = finding.candidate.params.get(name)
        if current not in values:
            continue
        position = values.index(current)
        for offset in (-1, 1):
            neighbour = position + offset
            if not 0 <= neighbour < len(values):
                continue
            params = dict(finding.candidate.params)
            params[name] = values[neighbour]
            if not template._sane(params):
                continue
            other = Candidate(finding.candidate.template, params,
                              finding.candidate.side)
            key = other.key()
            if key not in signal_cache:
                signal_cache[key] = entry_ok & signals_for(
                    bars, other, warmup_for(other, style.atr_period))
            scored = _score(caches[(other.side, finding.stop_atr,
                                    finding.target_r)],
                            signal_cache[key], block, other, finding.timeframe,
                            finding.stop_atr, finding.target_r, minimum)
            if scored is not None:
                excesses.append(scored.excess)

    stops = list(style.stop_atr)
    targets = list(style.target_r)
    for values, current, kind in ((stops, finding.stop_atr, "stop"),
                                  (targets, finding.target_r, "target")):
        if current not in values:
            continue
        position = values.index(current)
        for offset in (-1, 1):
            neighbour = position + offset
            if not 0 <= neighbour < len(values):
                continue
            stop_atr = values[neighbour] if kind == "stop" else finding.stop_atr
            target_r = values[neighbour] if kind == "target" else finding.target_r
            scored = _score(caches[(finding.candidate.side, stop_atr, target_r)],
                            signal_cache[finding.candidate.key()], block,
                            finding.candidate, finding.timeframe, stop_atr,
                            target_r, minimum)
            if scored is not None:
                excesses.append(scored.excess)

    if not excesses:
        return Neighbourhood(0, 0, 0.0, finding.excess)
    return Neighbourhood(len(excesses), int(sum(1 for e in excesses if e > 0)),
                         float(np.median(excesses)), finding.excess)


def _deduplicate(findings: list[Finding]) -> list[Finding]:
    """Keep the best geometry per rule, so a shortlist is five ideas not one."""
    seen: set[tuple] = set()
    out: list[Finding] = []
    for finding in findings:
        key = (finding.candidate.template, finding.candidate.side)
        if key in seen:
            continue
        seen.add(key)
        out.append(finding)
    return out


def _judge(finding: Finding, minimum: int) -> None:
    """Turn the measurements into a sentence a person can act on."""
    concerns: list[str] = []
    research_excess = finding.excess
    holdout = finding.holdout or {}
    holdout_excess = (finding.holdout_control.excess_per_trade
                      if finding.holdout_control else 0.0)
    holdout_trades = int(holdout.get("trades", 0))

    if finding.sampled is not None and finding.sampled.p_value > 0.10:
        concerns.append(
            f"the sampled control disagrees with the fast one "
            f"(p={finding.sampled.p_value:.3f}); trust the sampled number")
    if finding.neighbourhood is not None and not finding.neighbourhood.smooth:
        concerns.append(
            "the edge disappears when the settings move one rung, so it is a "
            "property of these exact numbers rather than of the idea")
    if holdout_trades < minimum:
        concerns.append(
            f"the locked block produced only {holdout_trades} trades, too few "
            f"to confirm anything")
    if holdout_excess <= 0:
        concerns.append("the edge did not survive on the locked block")
    if holdout_excess > research_excess and research_excess > 0:
        concerns.append(
            "it did BETTER on the locked block than on the block it was chosen "
            "from, which is the wrong shape: an edge decays out of sample, it "
            "does not appear there")
    if finding.research.get("times", 0.0) > 0.6:
        concerns.append(
            "most trades ended on the time stop rather than at a barrier, so "
            "this is a bet on direction, not on the barriers")

    finding.concerns = concerns
    if not concerns:
        finding.verdict = "worth testing further"
    elif holdout_excess > 0 and holdout_trades >= minimum:
        finding.verdict = "survived the locked block, with reservations"
    else:
        finding.verdict = "not worth trading"


#: Appended to every report, on every path.  A caveat that only appears when
#: something was found is a caveat that appears when it is least likely to be
#: read.
DISCLAIMER = (
    "Everything above describes what already happened on one instrument over "
    "one period. It is not a prediction, and a strategy that passed here can "
    "still lose money.")


def _report(style, timeframe, bars, split, combinations, tested, findings,
            shortlist, notes, started) -> FinderReport:
    import pandas as pd

    notes = list(notes) + [DISCLAIMER]

    def stamp(index: int) -> str:
        index = max(0, min(index, len(bars) - 1))
        return str(pd.Timestamp(bars.ts[index], tz="UTC").date())

    return FinderReport(
        style=style, timeframe=timeframe,
        symbol=getattr(bars.instrument, "symbol", "?"),
        bars=len(bars), research_bars=split, holdout_bars=len(bars) - split,
        research_start=stamp(0), research_end=stamp(split - 1),
        holdout_end=stamp(len(bars) - 1), combinations=combinations,
        tested=tested, findings=findings, shortlist=shortlist, notes=notes,
        elapsed=time.time() - started,
    )
