"""Which indicators actually predict anything, for a given way of trading.

"Best indicator" is not a question until you say what it is being asked to
predict. An indicator that ranks bars by their next five minutes is answering a
scalper's question; the same indicator ranked against the next three days is
answering a different one and will usually give a different answer. So a study
here is always tied to a trading style, and the thing being predicted is not an
abstract forward return -- it is **what a trade with that style's geometry,
costs included, would actually have paid**.

The protocol:

1. **Split in time.** Features are ranked on the first 65% of the data. The
   rest is locked and used once, to check the sign held.
2. **Correct the standard errors for overlap.** Consecutive bars share most of
   their future, and most indicators barely change from bar to bar. Both
   together turn a t-statistic of 1.4 into one of 4.4 if you ignore them.
3. **Correct for multiplicity**, and report how many of the significant
   features are actually independent.
4. **Convert to money.** A rank correlation of 0.03 can be overwhelmingly
   significant and worth a fifth of a tick against a six-tick round turn. The
   spread between the top and bottom tenth of each feature is reported in
   account currency, beside the cost of trading.

The usual outcome is that a handful of features are statistically real and none
of them is worth its costs. That is a finding, and the report says it plainly.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from ..core.errors import InsufficientDataError
from ..core.types import CostModel
from ..data.models import BarSeries
from ..finder.outcomes import (Geometry, build_outcomes, round_turn_points,
                               session_entry_mask, session_hold_limit,
                               wilder_atr)
from ..finder.search import choose_timeframe, default_costs, prepare_bars
from ..finder.styles import TradingStyle
from .features import Feature, all_features, compute_matrix
from .ic import ICResult, evaluate, redundancy_groups

ProgressFn = Callable[[int, int, str], None]


@dataclass
class FeatureFinding:
    """One feature, judged."""

    feature: Feature
    research: ICResult
    holdout: ICResult | None = None
    cluster: list[str] = field(default_factory=list)
    verdict: str = ""
    concerns: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.feature.name

    @property
    def direction(self) -> str:
        """What the feature says to do when it is high."""
        if self.research.ic > 0:
            return "buy when high"
        if self.research.ic < 0:
            return "sell when high"
        return "no direction"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "family": self.feature.family,
            "description": self.feature.description,
            "direction": self.direction,
            "ic": self.research.ic, "t_stat": self.research.t_stat,
            "q_value": self.research.q_value,
            "spread_per_trade": self.research.spread,
            "monotonic": self.research.monotonic,
            "observations": self.research.observations,
            "holdout_ic": self.holdout.ic if self.holdout else None,
            "cluster": list(self.cluster),
            "verdict": self.verdict, "concerns": list(self.concerns),
        }


@dataclass
class FeatureStudy:
    """The whole study, including everything needed to disbelieve it."""

    style: TradingStyle
    timeframe: str
    symbol: str
    currency: str
    bars: int
    research_bars: int
    holdout_bars: int
    research_start: str
    research_end: str
    holdout_end: str
    horizon: int
    """Bars of overlap between consecutive observations, and the Newey-West lag."""
    cost_per_trade: float
    baseline: float
    """Mean outcome of a trade opened on every bar. Every decile figure has to
    be read against this: on most instruments it is negative, so a decile at
    -1.30 is not losing money, it is losing less than average."""
    tested: int
    independent: int
    """Number of redundancy clusters: how many separate ideas were really tried."""
    significant: int
    findings: list[FeatureFinding] = field(default_factory=list)
    clusters: list[list[str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    elapsed: float = 0.0

    def top(self, count: int = 12) -> list[FeatureFinding]:
        return self.findings[:count]

    def to_dict(self) -> dict[str, Any]:
        return {
            "style": self.style.key, "timeframe": self.timeframe,
            "symbol": self.symbol, "bars": self.bars,
            "research": [self.research_start, self.research_end],
            "holdout_end": self.holdout_end,
            "horizon_bars": self.horizon,
            "cost_per_trade": self.cost_per_trade,
            "baseline_per_trade": self.baseline,
            "features_tested": self.tested,
            "independent_features": self.independent,
            "significant": self.significant,
            "findings": [f.to_dict() for f in self.findings],
            "notes": list(self.notes),
            "elapsed_seconds": round(self.elapsed, 2),
        }


DISCLAIMER = (
    "An indicator that predicted the past is not an indicator that will "
    "predict the future, and one whose edge is smaller than the spread is not "
    "tradeable however certain the statistics are.")


def study_features(bars: BarSeries, style: TradingStyle, *,
                   timeframe: str = "", costs: CostModel | None = None,
                   side: int = 1, research_fraction: float = 0.65,
                   features: list[Feature] | None = None,
                   progress: ProgressFn | None = None) -> FeatureStudy:
    """Rank features by what they predict about this style's trades."""
    started = time.time()
    requested = timeframe
    timeframe = timeframe or choose_timeframe(bars, style)
    working = prepare_bars(bars, timeframe)
    n = len(working)
    if n < 1000:
        raise InsufficientDataError(
            f"A feature study needs at least 1,000 bars and this dataset has "
            f"{n:,} at {timeframe}.")

    instrument = working.instrument
    timezone = getattr(instrument, "timezone", "UTC") or "UTC"
    costs = costs if costs is not None else default_costs(instrument)

    # -- the target: what a trade opened on this bar would have paid ----
    stop_atr = style.stop_atr[len(style.stop_atr) // 2]
    target_r = style.target_r[len(style.target_r) // 2]
    hold_limit = None
    if style.session is not None and style.flat_at_session_end:
        hold_limit = session_hold_limit(working, timezone, style.session[0],
                                        style.session[1], style.max_bars,
                                        style.weekdays)
    entry_ok = session_entry_mask(
        working, timezone,
        style.session[0] if style.session else None,
        style.session[1] if style.session else None, style.weekdays,
        style.flat_at_session_end)

    if progress is not None:
        progress(0, 3, "Simulating a trade on every bar")
    cache = build_outcomes(working, Geometry(side, stop_atr, target_r,
                                             style.max_bars, style.atr_period),
                           costs, hold_limit, detail=False)
    target = np.where(cache.valid & entry_ok, cache.net_cash, np.nan)

    if progress is not None:
        progress(1, 3, "Computing features")
    matrix, features = compute_matrix(working, features)

    split = int(n * float(research_fraction))
    research = slice(0, split)
    holdout = slice(split, n)

    point_value = float(getattr(instrument, "point_value", 1.0)) or 1.0
    cost_points = round_turn_points(costs, instrument, working.close,
                                    wilder_atr(working, style.atr_period))
    cost_per_trade = float(np.nanmedian(cost_points) * point_value)

    # The overlap: two trades opened one bar apart share all but one bar of
    # their life, so the Newey-West lag is the hold.
    horizon = int(style.max_bars)
    baseline = float(np.nanmean(target[research])) if split else 0.0

    if progress is not None:
        progress(2, 3, f"Scoring {len(features)} features")
    results: list[ICResult] = []
    for column, feature in enumerate(features):
        results.append(evaluate(feature.name, matrix[research, column],
                                target[research], horizon))

    from ..finder.control import bh_q_values

    q_values = bh_q_values([r.p_value for r in results])
    for result, q in zip(results, q_values):
        result.q_value = q
    survives = [r.significant for r in results]

    clusters = redundancy_groups(matrix[research], [f.name for f in features])
    cluster_of = {name: group for group in clusters for name in group}

    findings: list[FeatureFinding] = []
    for column, (feature, result) in enumerate(zip(features, results)):
        finding = FeatureFinding(feature=feature, research=result,
                                 cluster=cluster_of.get(feature.name, []))
        if bool(survives[column]):
            finding.holdout = evaluate(feature.name, matrix[holdout, column],
                                       target[holdout], horizon)
        # Before the verdict, not after: a concern that arrives afterwards is
        # printed under a verdict that does not account for it, which is how a
        # feature ends up labelled "the edge is bigger than the costs" directly
        # above a line saying it is probably just the drift.
        _judge(finding, cost_per_trade,
               extra=_drift_concern(finding, baseline, side))
        findings.append(finding)

    findings.sort(key=lambda f: (-abs(f.research.ic) if f.research.significant
                                 else 1.0, f.research.q_value))
    significant = sum(1 for f in findings if f.research.significant)

    notes: list[str] = []
    if not requested and timeframe != style.timeframes[0]:
        notes.append(
            f"This style prefers {style.timeframes[0]} bars; the dataset is "
            f"{bars.timeframe.label}, so the study ran on {timeframe}.")
    notes.append(
        f"{len(features)} features were tested and they fall into "
        f"{len(clusters)} groups that say much the same thing, so the honest "
        f"count of separate ideas is {len(clusters)}, not {len(features)}.")
    notes.append(
        f"Standard errors are Newey-West with a lag of {horizon} bars, the "
        f"length of the trade. Without that correction a persistent indicator "
        f"against an overlapping outcome reads about three times more "
        f"significant than it is.")
    if (baseline > 0 and side > 0) or (baseline < 0 and side < 0):
        way = "rose" if side > 0 else "fell"
        notes.append(
            f"The market {way} over this period: a trade opened on every bar "
            f"and held to the same barriers made {baseline:+,.2f} "
            f"{getattr(instrument, 'currency', 'USD')} on average. The decile "
            f"spreads below are measured against that, so a feature only "
            f"counts if it separates good trades from bad ones beyond the "
            f"drift -- but a trend feature ranking highly is still the single "
            f"most likely thing here to be measuring the drift rather than "
            f"predicting anything, and the only way to settle it is a second "
            f"instrument or a period that went the other way.")
    notes.append(
        f"A round turn costs about {cost_per_trade:,.2f} "
        f"{getattr(instrument, 'currency', 'USD')} on this instrument. A "
        f"feature whose top-to-bottom spread is smaller than that predicts "
        f"something real and unprofitable.")
    notes.append(DISCLAIMER)

    import pandas as pd

    def stamp(index: int) -> str:
        index = max(0, min(index, n - 1))
        return str(pd.Timestamp(working.ts[index], tz="UTC").date())

    return FeatureStudy(
        style=style, timeframe=timeframe,
        symbol=getattr(instrument, "symbol", "?"),
        currency=getattr(instrument, "currency", "USD"),
        bars=n, research_bars=split, holdout_bars=n - split,
        research_start=stamp(0), research_end=stamp(split - 1),
        holdout_end=stamp(n - 1), horizon=horizon,
        cost_per_trade=cost_per_trade, baseline=baseline, tested=len(features),
        independent=len(clusters), significant=significant,
        findings=findings, clusters=clusters, notes=notes,
        elapsed=time.time() - started)


def _drift_concern(finding: FeatureFinding, baseline: float,
                   side: int) -> list[str]:
    """Flag a trend feature that agrees with the direction the market went.

    US30 tripled over the period this application ships data for. "Buy when
    price is above the 200 EMA" would have worked on that sample whether or not
    it means anything, and no amount of statistics inside one rising market can
    tell the two apart.
    """
    if not finding.research.significant or finding.feature.family != "trend":
        return []
    drifted = (baseline > 0 and side > 0) or (baseline < 0 and side < 0)
    if drifted and np.sign(finding.research.ic) == np.sign(side):
        return ["this is a trend feature pointing the same way the market went "
                "over this sample, which is the most likely thing here to be "
                "drift rather than prediction; test it on an instrument that "
                "fell"]
    return []


def _judge(finding: FeatureFinding, cost: float,
           extra: list[str] | None = None) -> None:
    """Turn the numbers into a sentence, including when the answer is no."""
    research = finding.research
    concerns: list[str] = list(extra or [])

    if not research.significant:
        finding.verdict = "predicts nothing"
        return

    if research.ic != 0 and research.spread != 0 and \
            np.sign(research.ic) != np.sign(research.spread):
        concerns.append(
            "the rank correlation and the average disagree in sign: high "
            "values of this feature produce more losers but bigger winners, "
            "so the effect is in the tails and a rule built on it will not "
            "behave like the correlation suggests")
    if abs(research.monotonic) < 0.5:
        concerns.append(
            "the effect is not monotone across the deciles, so it is a spike "
            "in one bucket rather than a gradient")
    if abs(research.spread) < cost:
        concerns.append(
            f"the top-to-bottom spread is {abs(research.spread):,.2f} against a "
            f"{cost:,.2f} round turn, so the edge is smaller than the cost of "
            f"taking it")
    if finding.holdout is not None:
        if finding.holdout.observations < 100:
            concerns.append("too few observations in the locked block to check")
        elif np.sign(finding.holdout.ic) != np.sign(research.ic):
            concerns.append(
                "the sign flipped on the locked block, which is what a "
                "coincidence looks like")
        elif abs(finding.holdout.ic) > abs(research.ic) * 1.5:
            concerns.append(
                "it is stronger on the locked block than on the block it was "
                "ranked in, which is the wrong shape")
    if finding.feature.family == "session":
        concerns.append(
            "this is a time-of-day feature. Every control in this application "
            "already matches on time of day, so an edge that is only 'trade "
            "at this hour' is priced in and is not an edge")
    if len(finding.cluster) > 3:
        concerns.append(
            f"{len(finding.cluster)} features in this study measure the same "
            f"thing, so this is one idea, not {len(finding.cluster)}")

    finding.concerns = concerns
    if not concerns:
        finding.verdict = "predicts, and the edge is bigger than the costs"
    elif abs(research.spread) >= cost:
        finding.verdict = "predicts, with reservations"
    else:
        finding.verdict = "predicts, but not enough to pay for the trade"
