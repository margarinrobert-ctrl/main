"""The engine's confirmation of a shortlisted candidate.

The search ranks on a cached fast path, so a search result is a claim, not
evidence.  Every candidate that reaches a shortlist is re-run through the real
engine on both blocks and measured with the same metrics module a hand-built
strategy uses.  These tests fix that contract:

* the metrics come from the engine, not from the search's summary
* in-sample and out-of-sample are reported separately and never merged
* the locked block is warm on its first bar and cannot trade inside research
* a disagreement between the fast path and the engine is REPORTED, not hidden
"""

from __future__ import annotations

import numpy as np
import pytest

from tradingbacktester.core.timeframe import Timeframe
from tradingbacktester.core.types import BacktestConfig
from tradingbacktester.data.sample import generate_sample_data
from tradingbacktester.finder.confirm import (AGREEMENT_TOLERANCE,
                                              HEADLINE_METRICS, Agreement,
                                              BlockRun, Confirmation,
                                              confirm)
from tradingbacktester.finder.report import _cell


def _bars(n: int = 4000):
    return generate_sample_data("CONF", Timeframe.parse("30m"), n_bars=n, seed=4)


class _Finding:
    """The minimum a Finding has to look like for confirm() to work on it."""

    def __init__(self, spec, research=None):
        self.spec = spec
        self.research = research or {}


def _spec():
    from tradingbacktester.strategy.builtin import BUILTIN_STRATEGIES

    return BUILTIN_STRATEGIES["EMA Cross + RSI"]()


# ---------------------------------------------------------------------------
# the contract
# ---------------------------------------------------------------------------

def test_confirmation_reports_every_headline_metric_on_both_blocks():
    bars = _bars()
    split = int(len(bars) * 0.65)
    out = confirm(_Finding(_spec()), bars, split)
    assert out.research.ran, out.research.error
    assert out.holdout.ran, out.holdout.error
    for key, label in HEADLINE_METRICS:
        assert key in out.research.metrics, f"research is missing {label}"
        assert key in out.holdout.metrics, f"locked is missing {label}"


def test_the_two_blocks_do_not_overlap_and_cover_the_split():
    """The locked block is padded for warm-up but must not TRADE in research."""
    bars = _bars()
    split = int(len(bars) * 0.65)
    out = confirm(_Finding(_spec()), bars, split)
    # `bars` on a BlockRun is the tradeable length, excluding the padding.
    assert out.research.bars == split
    assert out.holdout.bars == len(bars) - split
    assert out.research.bars + out.holdout.bars == len(bars)


def test_the_locked_block_is_warm_on_its_first_bar():
    """Without padding a cold slice is blind for its whole warm-up.

    A strategy with a long warm-up would take noticeably fewer trades in a
    cold locked block than a warm one, and those trades would be counted
    nowhere while the report still claimed to cover the period.
    """
    from tradingbacktester.finder import confirm as module

    bars = _bars()
    split = int(len(bars) * 0.65)
    spec = _spec()
    warm = confirm(_Finding(spec), bars, split)

    # Re-run with padding disabled, which is what a naive slice would do.
    real = module._warmup_for
    module._warmup_for = lambda *_a, **_k: 0
    try:
        cold = confirm(_Finding(spec), bars, split)
    finally:
        module._warmup_for = real
    assert warm.holdout.trades >= cold.holdout.trades, (
        "padding the locked block should never lose trades")


def test_a_candidate_with_no_strategy_is_reported_not_raised():
    out = confirm(_Finding(None), _bars(), 100)
    assert not out.ran
    assert not out.agreement.agrees
    assert out.notes and "never built" in out.notes[0]


def test_a_split_past_the_end_does_not_raise():
    bars = _bars(1200)
    out = confirm(_Finding(_spec()), bars, len(bars) + 5000)
    assert isinstance(out, Confirmation)


def test_a_zero_split_does_not_raise():
    bars = _bars(1200)
    out = confirm(_Finding(_spec()), bars, 0)
    assert isinstance(out, Confirmation)


# ---------------------------------------------------------------------------
# the agreement check
# ---------------------------------------------------------------------------

def test_agreement_holds_when_the_fast_path_matches_the_engine():
    bars = _bars()
    split = int(len(bars) * 0.65)
    truth = confirm(_Finding(_spec()), bars, split)
    net = float(truth.research.metrics.get("net_profit", 0.0))
    trades = truth.research.trades
    finding = _Finding(_spec(), research={
        "trades": trades, "per_trade": net / trades if trades else 0.0})
    out = confirm(finding, bars, split)
    assert out.agreement.agrees, out.agreement.reason


def test_a_fast_path_that_disagrees_is_reported_not_hidden():
    """If the search ranked on a number the engine cannot reproduce, say so."""
    bars = _bars()
    split = int(len(bars) * 0.65)
    truth = confirm(_Finding(_spec()), bars, split)
    trades = truth.research.trades
    net = float(truth.research.metrics.get("net_profit", 0.0))
    honest = net / trades if trades else 0.0
    finding = _Finding(_spec(), research={
        "trades": trades,
        "per_trade": honest + AGREEMENT_TOLERANCE * 10 + 1.0})
    out = confirm(finding, bars, split)
    assert not out.agreement.agrees
    assert "per trade" in out.agreement.reason
    assert any("unverified" in n for n in out.notes)


def test_a_trade_count_mismatch_is_reported():
    bars = _bars()
    split = int(len(bars) * 0.65)
    truth = confirm(_Finding(_spec()), bars, split)
    trades = truth.research.trades
    assert trades > 10, "the fixture needs enough trades to be worth checking"
    finding = _Finding(_spec(), research={"trades": trades + 5,
                                          "per_trade": 0.0})
    out = confirm(finding, bars, split)
    assert not out.agreement.agrees
    assert "trades" in out.agreement.reason


def test_a_single_trade_of_difference_is_a_disagreement():
    """No share-based slack: the two layers run the same rule on the same bars.

    Every trade-count defect found in the fast path so far was a handful out of
    thousands -- ten in 3,614, four in 152. A 10% tolerance swallowed all of
    them, which is how they survived to be found by widening a different test.
    """
    bars = _bars()
    split = int(len(bars) * 0.65)
    truth = confirm(_Finding(_spec()), bars, split)
    trades = truth.research.trades
    per_trade = (float(truth.research.metrics.get("net_profit", 0.0)) / trades
                 if trades else 0.0)
    off_by_one = _Finding(_spec(), research={"trades": trades + 1,
                                             "per_trade": per_trade})
    assert not confirm(off_by_one, bars, split).agreement.agrees
    exact = _Finding(_spec(), research={"trades": trades,
                                        "per_trade": per_trade})
    assert confirm(exact, bars, split).agreement.agrees


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def test_a_drawdown_never_renders_with_a_profit_sign():
    """A "+904.37" drawdown puts a gain sign on a loss."""
    assert _cell(904.37, "cost", "USD") == "904.37 USD"
    assert _cell(-904.37, "cost", "USD") == "904.37 USD"
    assert _cell(1905.58, "money", "USD").startswith("+")


def test_missing_and_infinite_metrics_render_without_raising():
    assert _cell(None, "money", "USD") == "—"
    assert _cell(float("nan"), "ratio", "USD") == "—"
    assert _cell(float("inf"), "ratio", "USD") == "inf"
    assert _cell(True, "count", "USD") == "—"
    assert _cell("n/a", "ratio", "USD") == "n/a"


@pytest.mark.parametrize("seconds,expected", [
    (30, "30s"), (600, "10m"), (7200, "2.0h"), (172800, "2.0d")])
def test_durations_render_at_a_sensible_scale(seconds, expected):
    assert _cell(seconds, "duration", "USD") == expected
