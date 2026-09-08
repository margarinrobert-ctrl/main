"""Whether a book is several bets or one bet wearing several hats.

The checks that matter here are the ones that catch a *flattering* answer: a
matrix that says "diversified" about two copies of the same strategy, or an
effective-bet count that quietly treats an unmeasurable pair as uncorrelated.
"""

from __future__ import annotations

import numpy as np
import pytest

from tradingbacktester.analytics.correlation import (MIN_OVERLAP,
                                                     correlate_results,
                                                     series_from_result)
from tradingbacktester.core.errors import BacktestError
from tradingbacktester.core.types import BacktestConfig
from tradingbacktester.data.sample import generate_sample_data
from tradingbacktester.engine.backtester import Backtester
from tradingbacktester.strategy import builtin


@pytest.fixture(scope="module")
def bars():
    return generate_sample_data("US100", "15m", n_bars=8000, seed=3)


@pytest.fixture(scope="module")
def runs(bars):
    return [Backtester(bars, factory(), BacktestConfig()).run()
            for factory in (builtin.donchian_breakout, builtin.macd_trend,
                            builtin.ema_cross_rsi, builtin.bollinger_breakout)]


# --------------------------------------------------------------------------
# shape
# --------------------------------------------------------------------------

def test_one_run_is_not_a_book(runs):
    with pytest.raises(BacktestError):
        correlate_results(runs[:1])


def test_the_matrix_is_square_symmetric_and_one_on_the_diagonal(runs):
    report = correlate_results(runs)
    m = report.matrix
    assert m.shape == (len(runs), len(runs))
    assert np.allclose(np.diag(m), 1.0)
    finite = np.isfinite(m)
    assert np.allclose(m[finite], m.T[finite])


def test_every_pair_appears_exactly_once(runs):
    report = correlate_results(runs)
    n = len(runs)
    assert len(report.pairs) == n * (n - 1) // 2
    keys = {frozenset((p.a, p.b)) for p in report.pairs}
    assert len(keys) == len(report.pairs)


def test_two_runs_of_the_same_strategy_do_not_collapse_into_one_row(runs):
    report = correlate_results([runs[0], runs[0], runs[1]])
    assert len(set(report.names)) == 3, report.names


# --------------------------------------------------------------------------
# the numbers mean what they say
# --------------------------------------------------------------------------

def test_a_strategy_correlates_perfectly_with_itself(runs):
    report = correlate_results([runs[0], runs[0]])
    pair = report.pairs[0]
    assert pair.correlation == pytest.approx(1.0, abs=1e-9)
    assert pair.exposure_overlap == pytest.approx(1.0)
    assert pair.same_side_share == pytest.approx(1.0)
    assert pair.entry_coincidence == pytest.approx(1.0)


def test_a_duplicated_strategy_is_one_bet_not_two(runs):
    report = correlate_results([runs[0], runs[0]])
    assert report.effective_bets == pytest.approx(1.0, abs=1e-6), (
        "the same strategy twice must not read as diversification")


def test_independent_strategies_approach_their_own_count():
    # Two runs whose returns are built to be unrelated.
    a = _fake(np.random.default_rng(1).normal(0, 0.01, 400))
    b = _fake(np.random.default_rng(2).normal(0, 0.01, 400))
    report = correlate_results([a, b])
    assert report.effective_bets > 1.8


def test_an_unmeasurable_pair_is_excluded_not_assumed_independent(runs):
    short = _fake(np.random.default_rng(3).normal(0, 0.01, MIN_OVERLAP - 5))
    report = correlate_results([runs[0], runs[1], short])
    assert any("shared fewer than" in n for n in report.notes), report.notes
    assert any(p.correlation is None for p in report.pairs)


def test_exposure_overlap_is_zero_when_they_never_hold_together(bars):
    left = _fake_with_trades(bars, first_half=True)
    right = _fake_with_trades(bars, first_half=False)
    report = correlate_results([left, right])
    assert report.pairs[0].exposure_overlap == pytest.approx(0.0)


# --------------------------------------------------------------------------
# what it refuses to say
# --------------------------------------------------------------------------

def test_the_report_never_recommends_adding_a_strategy(runs):
    text = correlate_results(runs).describe().lower()
    assert "decorrelated leg" in text and "edge of its own" in text
    for promise in ("you should add", "worth adding", "recommend"):
        assert promise not in text


def test_most_and_least_alike_are_ordered_by_magnitude(runs):
    report = correlate_results(runs)
    most = [abs(p.correlation) for p in report.most_alike()]
    least = [abs(p.correlation) for p in report.least_alike()]
    assert most == sorted(most, reverse=True)
    assert least == sorted(least)
    assert most[0] >= least[0]


def test_series_from_a_run_with_no_curves_is_empty():
    series = series_from_result(_Bare())
    assert series.ts.size == 0 and series.returns.size == 0


# --------------------------------------------------------------------------
# fixtures that stand in for a run
# --------------------------------------------------------------------------

class _Bare:
    curves = None
    trades: list = []
    metrics: dict = {}
    strategy_name = "bare"


class _Curves:
    def __init__(self, ts, equity):
        self.ts = ts
        self.equity = equity


class _Run:
    def __init__(self, ts, equity, trades, name):
        self.curves = _Curves(ts, equity)
        self.trades = trades
        self.metrics = {"net_profit": float(equity[-1] - equity[0])}
        self.strategy_name = name


def _fake(returns, name="fake"):
    """A run whose daily equity produces exactly ``returns``."""
    n = returns.size + 1
    day = 86_400_000_000_000
    ts = (np.arange(n, dtype="int64") * day) + 1_672_617_600_000_000_000
    equity = 100_000.0 * np.cumprod(np.concatenate([[1.0], 1.0 + returns]))
    return _Run(ts, equity, [], name)


class _Trade:
    def __init__(self, entry_ts, exit_ts, side="Side.LONG"):
        self.entry_ts = entry_ts
        self.exit_ts = exit_ts
        self.side = side
        self.net_pnl = 1.0
        self.bars_held = 1


def _fake_with_trades(bars, *, first_half: bool):
    ts = np.asarray(bars.ts, dtype="int64")
    half = ts.size // 2
    window = ts[:half] if first_half else ts[half:]
    equity = np.linspace(100_000.0, 101_000.0, ts.size)
    trades = [_Trade(int(window[0]), int(window[-1]))]
    return _Run(ts, equity, trades, "first" if first_half else "second")
