"""Whether a candidate is robust, scored across dimensions that can disagree.

A search always produces a winner.  Ranking those winners by profit ranks them
by how lucky they got, because the thing profit measures best on a single
sample is how well the rule fitted it.  So nothing here ranks on return.

Two mechanisms, and the difference between them matters:

**Blockers** are disqualifying.  A rule that took no trades out of sample, or
lost money out of sample, or never survived its own multiplicity correction,
does not get a score at all -- it gets a reason.  No weighting can rescue it,
because there is nothing to weigh: the evidence for it does not exist.  This is
what stops a strategy being called "proven" on the strength of one block.

**Dimensions** are scored 0..1 and weighted, and they only run on what got past
the blockers.  Each one answers a different question, and a candidate can be
excellent on one while failing another -- which is the point.  A rule with a
beautiful equity curve that earns all of it in one month is not consistent; a
rule that beats its control only at exactly one parameter setting has no
mechanism, only a coincidence.

Dimensions that cannot be measured are marked inapplicable and drop out of the
weighted mean rather than scoring zero.  Scoring an unrun test as failure would
punish a candidate for the depth the caller chose, and the total is reported
with the count of dimensions behind it so a thin score is visible as thin.

Every number here comes from a real backtest -- the engine's confirmation, the
walk-forward, the Monte Carlo resample, the mirror.  Nothing is estimated.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)

ProgressFn = Callable[[int, int, str], None]

#: Below this many out-of-sample trades a ratio is a description of a handful
#: of days.  Matches the reliability threshold used across the application.
MIN_OOS_TRADES = 20

#: A rule that keeps less than this share of its in-sample edge out of sample
#: was mostly fitted.  Not a blocker -- decay is normal and expected -- but it
#: dominates the score, because it is the only dimension measured on data the
#: search never saw.
RETENTION_FLOOR = 0.0

#: Costs eating more than this share of gross profit make the result a bet on
#: the cost model rather than on the rule.
COST_SHARE_LIMIT = 0.5

#: Out-of-sample retention above this is reported as the wrong shape.  A rule
#: selected on the research block should look better there; a locked block that
#: pays half again as much is a question, not a bonus.
WRONG_SHAPE = 1.5


@dataclass
class Dimension:
    """One question, scored 0..1, with the sentence that justifies it."""

    key: str
    label: str
    score: float
    weight: float
    detail: str
    applicable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "label": self.label,
                "score": None if not self.applicable else round(self.score, 4),
                "weight": self.weight, "detail": self.detail,
                "applicable": self.applicable}


@dataclass
class Robustness:
    """The whole verdict: blockers first, then a weighted score."""

    dimensions: list[Dimension] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return bool(self.blockers)

    @property
    def measured(self) -> list[Dimension]:
        return [d for d in self.dimensions if d.applicable]

    @property
    def total(self) -> float:
        """0..100, or NaN when nothing could be measured or a blocker fired."""
        if self.blocked:
            return float("nan")
        measured = self.measured
        weight = sum(d.weight for d in measured)
        if weight <= 0:
            return float("nan")
        return 100.0 * sum(d.score * d.weight for d in measured) / weight

    @property
    def grade(self) -> str:
        """A word, chosen so that no word here means "will make money"."""
        if self.blocked:
            return "disqualified"
        total = self.total
        if not math.isfinite(total):
            return "unmeasured"
        if len(self.measured) < 4:
            return "too little evidence to grade"
        if total >= 75:
            return "robust on this sample"
        if total >= 55:
            return "mixed"
        if total >= 35:
            return "weak"
        return "fragile"

    def to_dict(self) -> dict[str, Any]:
        total = self.total
        return {
            "total": None if not math.isfinite(total) else round(total, 1),
            "grade": self.grade,
            "blocked": self.blocked,
            "blockers": list(self.blockers),
            "dimensions": [d.to_dict() for d in self.dimensions],
            "measured": len(self.measured),
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# scoring helpers
# ---------------------------------------------------------------------------

def _clamp(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return max(0.0, min(1.0, value))


def _ramp(value: float, zero: float, one: float) -> float:
    """Linear 0..1 between two anchors, either direction, clamped."""
    if not math.isfinite(value) or zero == one:
        return 0.0
    return _clamp((value - zero) / (one - zero))


def _number(source: dict[str, Any], key: str, default: float = float("nan")) -> float:
    raw = source.get(key)
    if raw is None or isinstance(raw, bool):
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# the blockers
# ---------------------------------------------------------------------------

def _blockers(finding: Any, minimum_trades: int) -> list[str]:
    """Reasons this candidate cannot be recommended at any score."""
    out: list[str] = []
    confirmation = getattr(finding, "confirmation", None)

    if confirmation is None or not confirmation.ran:
        reason = ("the engine did not confirm it" if confirmation is None
                  else confirmation.research.error or
                  confirmation.holdout.error or "the engine could not run it")
        out.append(f"No engine backtest stands behind this rule: {reason}.")
        return out

    if not confirmation.agreement.agrees:
        out.append(
            f"The engine did not reproduce the figure the search ranked on "
            f"({confirmation.agreement.reason}), so the search's own ranking of "
            f"this rule cannot be trusted.")

    holdout = confirmation.holdout
    if holdout.trades == 0:
        out.append(
            "It took no trades at all on the locked block, so there is no "
            "out-of-sample evidence for it — only the absence of any.")
        return out

    oos_net = _number(holdout.metrics, "net_profit", 0.0)
    if oos_net <= 0:
        out.append(
            f"It lost money on the locked block ({oos_net:+,.0f}), which is the "
            f"only part of the sample it was not chosen on.")

    if holdout.trades < minimum_trades:
        out.append(
            f"Only {holdout.trades} out-of-sample trades, below the "
            f"{minimum_trades} this style needs before a ratio describes "
            f"anything but a handful of days.")

    if not getattr(finding, "survives_fdr", False):
        out.append(
            "It did not survive the multiplicity correction for the number of "
            "combinations the search tried.")
    return out


# ---------------------------------------------------------------------------
# the dimensions
# ---------------------------------------------------------------------------

def _retention(finding: Any) -> Dimension:
    """How much of the in-sample edge survived into the locked block.

    Weighted heaviest deliberately: it is the only dimension measured on data
    the search never saw, and it is the question every other dimension is a
    proxy for.
    """
    confirmation = finding.confirmation
    research, holdout = confirmation.research, confirmation.holdout
    in_trades, out_trades = research.trades, holdout.trades
    if not in_trades or not out_trades:
        return Dimension("retention", "Out-of-sample retention", 0.0, 3.0,
                         "not measurable without trades on both blocks", False)
    in_per = _number(research.metrics, "net_profit", 0.0) / in_trades
    out_per = _number(holdout.metrics, "net_profit", 0.0) / out_trades
    if in_per <= 0:
        return Dimension(
            "retention", "Out-of-sample retention", 0.0, 3.0,
            "the rule did not make money in-sample either, so there is no edge "
            "to have retained", False)
    kept = out_per / in_per
    # 1.0 means the locked block matched the research block. Anything above is
    # capped rather than rewarded, and past WRONG_SHAPE it is called out: a rule
    # chosen on the research block should look BETTER there. The locked block is
    # where an edge decays, not where it appears, so a rule that does markedly
    # better on the data it was not chosen on is more likely to have found an
    # easier period -- or a leak -- than a better edge.
    score = _clamp(kept)
    detail = (f"kept {kept * 100:.0f}% of its in-sample edge per trade "
              f"({in_per:+,.2f} → {out_per:+,.2f})")
    if kept > WRONG_SHAPE:
        detail += ("; that is the wrong shape — it did markedly better on the "
                   "block it was not chosen on, which is a defect to explain, "
                   "not a result to bank")
    return Dimension("retention", "Out-of-sample retention", score, 3.0, detail)


def _significance(finding: Any) -> Dimension:
    """How unlikely the result is against a matched random control."""
    control = getattr(finding, "control", None)
    if control is None:
        return Dimension("significance", "Statistical significance", 0.0, 2.0,
                         "no control was run", False)
    p = float(getattr(control, "p_value", float("nan")))
    if not math.isfinite(p):
        return Dimension("significance", "Statistical significance", 0.0, 2.0,
                         "the control produced no p-value", False)
    # p=0.10 scores 0, p=0.001 scores 1, on a log scale because the interesting
    # range spans orders of magnitude.
    score = _ramp(-math.log10(max(p, 1e-12)), 1.0, 3.0)
    holdout_control = getattr(finding, "holdout_control", None)
    detail = f"p={p:.4f} against a time-of-day matched control"
    if holdout_control is not None:
        excess = float(getattr(holdout_control, "excess_per_trade", 0.0))
        detail += f"; locked-block excess {excess:+,.2f} per trade"
        if excess <= 0:
            score *= 0.5
            detail += " (it did not beat its control out of sample)"
    return Dimension("significance", "Statistical significance", score, 2.0,
                     detail)


def _sensitivity(finding: Any) -> Dimension:
    """Does the edge survive a change of parameters, or live at one setting?"""
    neighbourhood = getattr(finding, "neighbourhood", None)
    if neighbourhood is None or not getattr(neighbourhood, "tested", 0):
        return Dimension("sensitivity", "Parameter sensitivity", 0.0, 2.0,
                         "the neighbourhood was not tested", False)
    fraction = float(getattr(neighbourhood, "fraction_positive", 0.0) or 0.0)
    return Dimension(
        "sensitivity", "Parameter sensitivity", _clamp(fraction), 2.0,
        f"{neighbourhood.positive}/{neighbourhood.tested} nearby settings also "
        f"beat their control — a real edge decays smoothly, a coincidence does "
        f"not")


def _sample(finding: Any) -> Dimension:
    """Enough trades that the ratios describe a process, not an anecdote."""
    confirmation = finding.confirmation
    trades = confirmation.research.trades + confirmation.holdout.trades
    score = _ramp(float(trades), 30.0, 300.0)
    return Dimension(
        "sample", "Sample size", score, 1.0,
        f"{trades:,} trades in total "
        f"({confirmation.research.trades:,} research, "
        f"{confirmation.holdout.trades:,} locked)")


def _drawdown(finding: Any) -> Dimension:
    """Return measured against the worst the equity curve got, out of sample."""
    metrics = finding.confirmation.holdout.metrics
    calmar = _number(metrics, "calmar_ratio")
    recovery = _number(metrics, "recovery_factor")
    parts = [v for v in (calmar, recovery) if math.isfinite(v)]
    if not parts:
        return Dimension("drawdown", "Drawdown quality", 0.0, 1.5,
                         "no drawdown statistics out of sample", False)
    score = _clamp(sum(_ramp(v, 0.0, 3.0) for v in parts) / len(parts))
    drawdown = _number(metrics, "max_drawdown", 0.0)
    return Dimension(
        "drawdown", "Drawdown quality", score, 1.5,
        f"locked-block Calmar {calmar:.2f}, recovery {recovery:.2f}, worst "
        f"drawdown {abs(drawdown):,.0f}")


def _costs(finding: Any) -> Dimension:
    """How much of the gross result the spread, commission and slippage took."""
    metrics = finding.confirmation.research.metrics
    gross = _number(metrics, "gross_profit", 0.0)
    costs = _number(metrics, "total_costs", 0.0)
    if not math.isfinite(gross) or gross <= 0:
        return Dimension("costs", "Cost sensitivity", 0.0, 1.5,
                         "no gross profit to compare the costs against", False)
    share = abs(costs) / gross
    score = _clamp(1.0 - share / COST_SHARE_LIMIT)
    return Dimension(
        "costs", "Cost sensitivity", score, 1.5,
        f"trading costs are {share * 100:.0f}% of gross profit "
        f"({abs(costs):,.0f} of {gross:,.0f})"
        + ("; the result is a bet on the cost model as much as on the rule"
           if share > COST_SHARE_LIMIT else ""))


def _consistency(finding: Any, concentration: Any) -> Dimension:
    """Was the profit spread through the sample, or earned in one stretch?"""
    if concentration is None or not getattr(concentration, "applicable", False):
        return Dimension("consistency", "Consistency", 0.0, 1.5,
                         "the concentration test did not apply", False)
    share = float(getattr(concentration, "share", 1.0))
    # A perfectly even split over five parts gives 0.2. Anything above 0.6 is
    # one part carrying the result.
    score = _clamp((0.6 - share) / 0.4)
    return Dimension(
        "consistency", "Consistency", score, 1.5,
        f"the best fifth of the sample carried {share * 100:.0f}% of the profit")


def _walk_forward(result: Any) -> Dimension:
    if result is None:
        return Dimension("walkforward", "Walk-forward", 0.0, 2.0,
                         "not run", False)
    efficiency = float(getattr(result, "efficiency", float("nan")))
    if not math.isfinite(efficiency):
        return Dimension(
            "walkforward", "Walk-forward", 0.0, 2.0,
            "efficiency is undefined because the in-sample total was not "
            "positive", False)
    score = _clamp(efficiency)
    stability = float(getattr(result, "stability", float("nan")))
    detail = f"kept {efficiency * 100:.0f}% of its in-sample profit out of sample"
    if math.isfinite(stability):
        detail += f"; the winning parameters changed in {(1 - stability) * 100:.0f}% of windows"
    return Dimension("walkforward", "Walk-forward", score, 2.0, detail)


def _monte_carlo(result: Any) -> Dimension:
    if result is None:
        return Dimension("montecarlo", "Monte Carlo", 0.0, 1.5, "not run", False)
    losing = _number({"p": getattr(result, "losing_probability", None)}, "p")
    if not math.isfinite(losing):
        return Dimension("montecarlo", "Monte Carlo", 0.0, 1.5,
                         "the resample produced no loss probability", False)
    score = _clamp(1.0 - losing)
    return Dimension(
        "montecarlo", "Monte Carlo", score, 1.5,
        f"{losing * 100:.0f}% of resampled orderings of these trades ended "
        f"below where they started")


def _direction(mirror: Any) -> Dimension:
    """Is this a rule, or a long position wearing one?"""
    if mirror is None:
        return Dimension("direction", "Direction independence", 0.0, 2.0,
                         "the mirror control was not run", False)
    share = float(getattr(mirror, "direction_share", float("nan")))
    if not math.isfinite(share):
        return Dimension("direction", "Direction independence", 0.0, 2.0,
                         "the mirror produced no decomposition", False)
    score = _clamp(1.0 - abs(share))
    return Dimension(
        "direction", "Direction independence", score, 2.0,
        f"{abs(share) * 100:.0f}% of the result is the direction the market "
        f"went, not the rule")


# ---------------------------------------------------------------------------
# the entry point
# ---------------------------------------------------------------------------

def assess(finding: Any, *, minimum_trades: int = MIN_OOS_TRADES,
           concentration: Any = None, walkforward: Any = None,
           montecarlo: Any = None, mirror: Any = None) -> Robustness:
    """Score one confirmed candidate across every dimension available.

    The optional arguments are the deeper validations.  Passing none of them
    still produces a score -- from retention, significance, sensitivity, sample
    size, drawdown and costs -- and the grade says how many dimensions stood
    behind it, so a shallow assessment cannot pass for a thorough one.
    """
    out = Robustness()
    # The same minimum the verdict uses, passed in by the caller. Two
    # thresholds for "enough out-of-sample trades" would let the score and the
    # verdict contradict each other on the same row, which is worse than either
    # being wrong.
    out.blockers = _blockers(finding, max(int(minimum_trades), MIN_OOS_TRADES))
    if out.blocked:
        out.notes.append(
            "Disqualified before scoring. A weighted score would average this "
            "away; it should not be averaged away.")
        return out

    out.dimensions = [
        _retention(finding),
        _significance(finding),
        _sensitivity(finding),
        _sample(finding),
        _drawdown(finding),
        _costs(finding),
        _consistency(finding, concentration),
        _walk_forward(walkforward),
        _monte_carlo(montecarlo),
        _direction(mirror),
    ]

    retention = next((d for d in out.dimensions if d.key == "retention"), None)
    if retention is not None and "wrong shape" in retention.detail:
        out.notes.append(
            "This candidate did better out of sample than in sample. That is "
            "the wrong shape for a rule chosen on the research block and it is "
            "worth explaining before trusting the score — the usual causes are "
            "an easier period in the locked block or a leak between them.")

    missing = [d.label for d in out.dimensions if not d.applicable]
    if missing:
        out.notes.append(
            f"{len(missing)} of {len(out.dimensions)} dimensions could not be "
            f"measured and were left out of the score rather than counted as "
            f"failures: {', '.join(missing)}.")
    out.notes.append(
        "This scores robustness on one instrument over one period. It is not a "
        "forecast, and the highest score here is still a description of the "
        "past.")
    return out


def rank(findings: list[Any]) -> list[Any]:
    """Order candidates by robustness, blocked ones last, never by return.

    Ties are broken by out-of-sample retention rather than by profit, so the
    ordering never falls back on the number that overfitting inflates.
    """
    def key(finding: Any) -> tuple:
        score = getattr(finding, "robustness", None)
        if score is None:
            return (2, 0.0, 0.0)
        if score.blocked:
            return (1, 0.0, 0.0)
        total = score.total
        retention = next((d.score for d in score.dimensions
                          if d.key == "retention" and d.applicable), 0.0)
        return (0, -(total if math.isfinite(total) else 0.0), -retention)

    return sorted(findings, key=key)
