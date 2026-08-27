"""Scoring a candidate on more than what it earned.

A search always produces a winner, so ranking winners by profit ranks them by
how lucky they got.  These tests fix the two mechanisms that stop that:
blockers, which disqualify outright and cannot be averaged away, and weighted
dimensions, which only run on what survived.
"""

from __future__ import annotations

import math

import pytest

from tradingbacktester.finder.confirm import Agreement, BlockRun, Confirmation
from tradingbacktester.finder.robustness import (COST_SHARE_LIMIT,
                                                 MIN_OOS_TRADES, WRONG_SHAPE,
                                                 Dimension, Robustness, assess,
                                                 rank)


def _block(label: str, trades: int, **metrics) -> BlockRun:
    base = {"net_profit": 1000.0, "gross_profit": 2000.0, "total_costs": 100.0,
            "calmar_ratio": 2.0, "recovery_factor": 2.0, "max_drawdown": 200.0}
    base.update(metrics)
    return BlockRun(label=label, bars=1000, trades=trades, metrics=base)


class _Control:
    def __init__(self, p=0.001, excess=5.0):
        self.p_value = p
        self.excess_per_trade = excess


class _Neighbourhood:
    def __init__(self, positive=4, tested=4):
        self.positive = positive
        self.tested = tested

    @property
    def fraction_positive(self):
        return self.positive / self.tested if self.tested else 0.0


class _Finding:
    """A confirmed candidate that passes every blocker unless told otherwise."""

    def __init__(self, *, research=None, holdout=None, agrees=True,
                 survives_fdr=True, control=None, holdout_control=None,
                 neighbourhood=None):
        self.confirmation = Confirmation(
            research=research or _block("research", 200),
            holdout=holdout or _block("holdout", 100),
            agreement=Agreement(agrees=agrees,
                                reason="" if agrees else "they disagree"))
        self.survives_fdr = survives_fdr
        self.control = control if control is not None else _Control()
        self.holdout_control = (holdout_control if holdout_control is not None
                                else _Control())
        self.neighbourhood = neighbourhood or _Neighbourhood()
        self.robustness = None


# ---------------------------------------------------------------------------
# blockers
# ---------------------------------------------------------------------------

def test_a_clean_candidate_is_not_blocked():
    out = assess(_Finding())
    assert not out.blocked, out.blockers
    assert math.isfinite(out.total)


def test_losing_out_of_sample_is_disqualifying():
    out = assess(_Finding(holdout=_block("holdout", 100, net_profit=-500.0)))
    assert out.blocked
    assert any("lost money on the locked block" in b for b in out.blockers)
    assert math.isnan(out.total)
    assert out.grade == "disqualified"


def test_no_out_of_sample_trades_is_disqualifying():
    out = assess(_Finding(holdout=_block("holdout", 0)))
    assert out.blocked
    assert any("no trades at all" in b for b in out.blockers)


def test_too_few_out_of_sample_trades_is_disqualifying():
    out = assess(_Finding(holdout=_block("holdout", MIN_OOS_TRADES - 1)))
    assert out.blocked
    assert any("out-of-sample trades" in b for b in out.blockers)


def test_failing_the_multiplicity_correction_is_disqualifying():
    out = assess(_Finding(survives_fdr=False))
    assert out.blocked
    assert any("multiplicity" in b for b in out.blockers)


def test_an_engine_disagreement_is_disqualifying():
    out = assess(_Finding(agrees=False))
    assert out.blocked
    assert any("did not reproduce" in b for b in out.blockers)


def test_a_candidate_with_no_confirmation_is_disqualified_not_crashed():
    class Bare:
        confirmation = None
    out = assess(Bare())
    assert out.blocked
    assert math.isnan(out.total)


def test_blockers_are_never_averaged_away_by_good_dimensions():
    """The whole point of a blocker: a perfect score elsewhere cannot rescue it."""
    out = assess(_Finding(holdout=_block("holdout", 500, net_profit=-1.0,
                                         calmar_ratio=99.0,
                                         recovery_factor=99.0)))
    assert out.blocked
    assert math.isnan(out.total)
    assert not out.dimensions, "a blocked candidate should not be scored at all"


# ---------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------

def test_an_unmeasured_dimension_does_not_count_as_a_failure():
    """Walk-forward off should not score the same as walk-forward failed."""
    without = assess(_Finding())
    walk = type("W", (), {"efficiency": 0.0, "stability": 1.0})()
    with_failure = assess(_Finding(), walkforward=walk)
    assert without.total > with_failure.total
    assert any(d.key == "walkforward" and not d.applicable
               for d in without.dimensions)


def test_the_grade_says_when_there_is_too_little_evidence():
    thin = Robustness(dimensions=[
        Dimension("a", "A", 1.0, 1.0, ""),
        Dimension("b", "B", 1.0, 1.0, ""),
        Dimension("c", "C", 0.0, 1.0, "", applicable=False),
    ])
    assert thin.grade == "too little evidence to grade"


def test_doing_better_out_of_sample_is_flagged_as_the_wrong_shape():
    """CLAUDE.md: the holdout is where an edge decays, not where it appears."""
    out = assess(_Finding(
        research=_block("research", 200, net_profit=200.0),
        holdout=_block("holdout", 100, net_profit=1000.0)))
    retention = next(d for d in out.dimensions if d.key == "retention")
    kept = (1000.0 / 100) / (200.0 / 200)
    assert kept > WRONG_SHAPE
    assert "wrong shape" in retention.detail
    assert any("wrong shape" in n for n in out.notes)


def test_retention_is_capped_so_the_wrong_shape_earns_no_bonus():
    modest = assess(_Finding(
        research=_block("research", 200, net_profit=200.0),
        holdout=_block("holdout", 100, net_profit=100.0)))
    extreme = assess(_Finding(
        research=_block("research", 200, net_profit=200.0),
        holdout=_block("holdout", 100, net_profit=5000.0)))
    a = next(d for d in modest.dimensions if d.key == "retention")
    b = next(d for d in extreme.dimensions if d.key == "retention")
    assert a.score == b.score == 1.0


def test_retention_is_inapplicable_when_there_was_no_in_sample_edge():
    out = assess(_Finding(research=_block("research", 200, net_profit=-100.0),
                          holdout=_block("holdout", 100)))
    retention = next(d for d in out.dimensions if d.key == "retention")
    assert not retention.applicable


def test_costs_eating_the_profit_scores_zero_and_says_so():
    out = assess(_Finding(research=_block(
        "research", 200, gross_profit=1000.0,
        total_costs=1000.0 * COST_SHARE_LIMIT * 2)))
    costs = next(d for d in out.dimensions if d.key == "costs")
    assert costs.score == 0.0
    assert "bet on the cost model" in costs.detail


def test_a_control_it_failed_out_of_sample_halves_significance():
    strong = assess(_Finding(holdout_control=_Control(excess=5.0)))
    weak = assess(_Finding(holdout_control=_Control(excess=-5.0)))
    a = next(d for d in strong.dimensions if d.key == "significance")
    b = next(d for d in weak.dimensions if d.key == "significance")
    assert b.score == pytest.approx(a.score / 2)
    assert "did not beat its control" in b.detail


def test_an_edge_at_one_setting_only_scores_low_on_sensitivity():
    out = assess(_Finding(neighbourhood=_Neighbourhood(positive=0, tested=4)))
    sensitivity = next(d for d in out.dimensions if d.key == "sensitivity")
    assert sensitivity.score == 0.0


def test_direction_share_drives_the_direction_dimension():
    class Mirror:
        direction_share = 0.9
    out = assess(_Finding(), mirror=Mirror())
    direction = next(d for d in out.dimensions if d.key == "direction")
    assert direction.score == pytest.approx(0.1)
    assert "90%" in direction.detail


# ---------------------------------------------------------------------------
# ranking
# ---------------------------------------------------------------------------

def test_ranking_puts_blocked_candidates_last_however_profitable():
    rich = _Finding(holdout=_block("holdout", 100, net_profit=-1.0))
    rich.robustness = assess(rich)
    plain = _Finding()
    plain.robustness = assess(plain)
    assert rank([rich, plain]) == [plain, rich]


def test_ranking_is_by_score_not_by_return():
    """A bigger number on the research block must not outrank a robust one."""
    fitted = _Finding(
        research=_block("research", 200, net_profit=100_000.0,
                        gross_profit=200_000.0, total_costs=150_000.0),
        holdout=_block("holdout", 100, net_profit=1.0),
        neighbourhood=_Neighbourhood(positive=0, tested=4),
        control=_Control(p=0.09), holdout_control=_Control(excess=-1.0))
    fitted.robustness = assess(fitted)
    steady = _Finding()
    steady.robustness = assess(steady)
    assert steady.robustness.total > fitted.robustness.total
    assert rank([fitted, steady])[0] is steady


def test_ranking_tolerates_candidates_with_no_score():
    class Bare:
        robustness = None
    plain = _Finding()
    plain.robustness = assess(plain)
    ordered = rank([Bare(), plain])
    assert ordered[0] is plain
