"""Market-neutral scoring and the sub-period concentration gate.

The regression cases are the ones the TypeScript reference pinned down, because
these two statistics are only worth having if they agree with the ones the
study was written against: beta 2 when the strategy IS the market doubled, beta
0 and residual == raw when the two are uncorrelated, concentration 1.0 when one
fifth carried everything, and an undefined share rather than a number when
there is no net to attribute.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from tradingbacktester.analytics.neutral import (BETA_SHARE_LIMIT,
                                                 CONCENTRATION_LIMIT,
                                                 CONCENTRATION_PARTS, analyse,
                                                 build_session_map,
                                                 concentration, market_neutral,
                                                 session_pnl)
from tradingbacktester.core.types import BacktestConfig, SessionSettings


# --------------------------------------------------------------------------
# The regression
# --------------------------------------------------------------------------

def test_beta_is_two_when_the_strategy_is_the_market_doubled():
    market = np.array([1.0, -2.0, 3.0, 0.5, -1.5, 2.0, -0.5, 1.0, 0.0, -1.0])
    stats = market_neutral(market * 2, market)
    assert stats.beta == pytest.approx(2.0)
    assert stats.correlation == pytest.approx(1.0)
    assert stats.residual_sharpe == pytest.approx(0.0)
    assert stats.beta_pnl_share == pytest.approx(1.0)
    assert stats.mostly_beta


def test_beta_is_zero_and_the_sharpe_survives_when_uncorrelated():
    """The residual must equal the raw Sharpe when there is nothing to strip."""
    rng = np.random.default_rng(7)
    strategy = rng.normal(0.0, 1.0, 4000)
    market = rng.normal(0.0, 1.0, 4000)
    # Orthogonalise the CENTRED series: beta is built from the covariance, so
    # a zero raw dot product is not the same thing and does not zero the beta.
    centred_s = strategy - strategy.mean()
    centred_m = market - market.mean()
    market = market - np.dot(centred_s, centred_m) / np.dot(centred_s, centred_s) * centred_s

    stats = market_neutral(strategy, market)
    assert abs(stats.beta) < 1e-12
    assert stats.residual_sharpe == pytest.approx(stats.sharpe)
    assert not stats.mostly_beta


def test_alpha_and_beta_are_recovered_exactly():
    market = np.array([2.0, -1.0, 4.0, -3.0, 1.0, 0.0, -2.0, 3.0])
    stats = market_neutral(0.5 * market + 0.05, market)
    assert stats.beta == pytest.approx(0.5)
    assert stats.alpha == pytest.approx(0.05)
    assert stats.beta_pnl_share > BETA_SHARE_LIMIT


def test_there_is_no_share_of_nothing():
    stats = market_neutral(np.array([1.0, -1.0, 2.0, -2.0]),
                           np.array([1.0, 1.0, -1.0, -1.0]))
    assert math.isnan(stats.beta_pnl_share)
    assert "no share of it" in stats.verdict()


def test_a_flat_market_leaves_the_sharpe_untouched():
    """Nothing to regress on: beta 0, and the residual is the raw Sharpe."""
    strategy = np.array([1.0, 2.0, -1.0, 3.0, 0.5])
    stats = market_neutral(strategy, np.zeros(5))
    assert stats.beta == 0.0
    assert stats.residual_sharpe == pytest.approx(stats.sharpe)


def test_mismatched_series_are_refused_by_name():
    with pytest.raises(ValueError) as exc:
        market_neutral(np.ones(10), np.ones(9))
    assert "same block" in str(exc.value)


def test_an_empty_block_returns_zeros_a_ui_can_render():
    stats = market_neutral([], [])
    assert stats.sessions == 0 and stats.sharpe == 0.0
    assert math.isnan(stats.beta_pnl_share)
    assert isinstance(stats.verdict(), str)


def test_annualisation_scales_the_sharpe_by_root_sessions():
    strategy = np.array([1.0, 2.0, -1.0, 3.0, 0.5, 1.5, -0.5, 2.5])
    a = market_neutral(strategy, np.zeros(8), sessions_per_year=252.0)
    b = market_neutral(strategy, np.zeros(8), sessions_per_year=63.0)
    assert a.sharpe == pytest.approx(b.sharpe * 2.0)     # sqrt(252/63) == 2


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------

def test_concentration_is_one_when_a_fifth_carried_everything():
    found = concentration(np.array([0.0] * 80 + [5.0] * 20))
    assert found.share == pytest.approx(1.0)
    assert not found.passed
    assert "one good stretch" in found.verdict()


def test_concentration_is_a_fifth_when_the_profit_is_spread():
    found = concentration(np.ones(100))
    assert found.share == pytest.approx(1.0 / CONCENTRATION_PARTS)
    assert found.passed


def test_the_parts_add_back_to_the_block():
    series = np.array([0.0] * 40 + [6.0] * 10 + [1.0] * 50)
    found = concentration(series)
    assert sum(found.parts) == pytest.approx(float(series.sum()))
    assert len(found.parts) == CONCENTRATION_PARTS


def test_an_uneven_session_count_loses_no_sessions():
    """101 sessions into 5 parts: the remainder must not be dropped."""
    series = np.arange(101, dtype="float64")
    found = concentration(series)
    assert sum(found.parts) == pytest.approx(float(series.sum()))


def test_the_gate_does_not_pass_on_a_block_with_no_net():
    found = concentration(np.zeros(50))
    assert math.isnan(found.share)
    assert not found.passed and not found.applicable


def test_the_gate_is_about_profit_so_a_losing_block_is_not_applicable():
    """Dividing by a negative total flips the sign and reads above 1.0."""
    found = concentration(np.array([-40.0] * 20 + [1.0] * 80))
    assert found.total < 0
    assert not found.applicable and not found.passed
    assert "lost money" in found.verdict()


def test_the_limit_is_the_protocols_figure():
    assert CONCENTRATION_LIMIT == 0.6
    assert CONCENTRATION_PARTS == 5


# --------------------------------------------------------------------------
# Against a real run
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def bars():
    from tradingbacktester.data.bundled import find
    from tradingbacktester.data.csv_loader import load_csv, sniff_csv
    from tradingbacktester.data.instruments import default_instrument_for

    dataset = find("US30 30m")
    path = str(dataset.path())
    return load_csv(path, sniff_csv(path).mapping,
                    default_instrument_for("US30"))


def _run(bars, name="MACD Trend"):
    from tradingbacktester.engine.backtester import Backtester
    from tradingbacktester.strategy.builtin import BUILTIN_STRATEGIES

    spec = BUILTIN_STRATEGIES[name]()
    config = BacktestConfig(starting_capital=100_000.0)
    config.exits, config.execution = spec.exits, spec.execution
    config.session, config.costs, config.risk = spec.session, spec.costs, spec.risk
    return Backtester(bars, spec, config).run()


def test_the_session_map_covers_every_bar_once(bars):
    found = build_session_map(bars, SessionSettings())
    assert found.count > 100
    assert found.ordinal.size == len(bars)
    assert found.ordinal.min() >= 0, "no session filter means every bar counts"
    assert found.ordinal.max() == found.count - 1
    assert np.all(np.diff(found.ordinal) >= 0), "sessions must be in order"


def test_a_session_window_excludes_the_bars_outside_it(bars):
    window = SessionSettings(enabled=True, start="09:30", end="11:00",
                             timezone="America/New_York")
    found = build_session_map(bars, window)
    assert (found.ordinal < 0).any(), "bars outside the window must be excluded"
    assert found.count > 100
    # Every session must contain at least one bar, or the market factor gains a
    # spurious all-zero session and the Sharpe denominator is wrong.
    counts = np.bincount(found.ordinal[found.ordinal >= 0],
                         minlength=found.count)
    assert counts.min() > 0


def test_the_market_factor_prices_one_long_unit_across_the_window(bars):
    found = build_session_map(bars, SessionSettings())
    point_value = float(bars.instrument.point_value)
    inside = found.ordinal >= 0
    first = np.where(found.ordinal[inside] == 0)[0]
    opens = np.asarray(bars.open)[inside][first]
    closes = np.asarray(bars.close)[inside][first]
    expected = (closes[-1] - opens[0]) * point_value
    assert found.market[0] == pytest.approx(expected)


def test_flat_sessions_are_in_the_denominator(bars):
    """Dropping them is how an intraday Sharpe gets inflated two or three times."""
    result = _run(bars)
    found = build_session_map(bars, result.config.session)
    series = session_pnl(result.trades, found)
    assert series.size == found.count
    traded = int(np.count_nonzero(series))
    assert traded < found.count, "this run should not trade every session"
    assert series.sum() == pytest.approx(
        sum(t.net_pnl for t in result.trades), rel=1e-9)


def test_analyse_reports_both_statistics_on_a_real_run(bars):
    report = analyse(_run(bars))
    assert report is not None
    assert report.sessions > 100
    assert 0 < report.traded_sessions <= report.sessions
    assert math.isfinite(report.neutral.sharpe)
    assert math.isfinite(report.neutral.beta)
    payload = json.loads(json.dumps(report.to_dict()))
    assert payload["neutral"]["verdict"]
    assert payload["concentration"]["verdict"]


def test_analyse_declines_rather_than_raising_when_there_is_nothing_to_do():
    from tradingbacktester.engine.results import BacktestResult

    assert analyse(BacktestResult()) is None


def test_the_session_map_is_memoised_but_not_across_datasets(bars):
    """The cache saves 110 ms a call in a sweep; it must not confuse datasets."""
    import time

    from tradingbacktester.analytics.neutral import build_session_map

    plain = SessionSettings()
    build_session_map(bars, plain)                      # warm
    started = time.perf_counter()
    for _ in range(20):
        build_session_map(bars, plain)
    cached = (time.perf_counter() - started) / 20
    assert cached < 0.005, f"the cache is not being hit ({cached * 1000:.1f} ms)"

    # A different window must not be served the cached grouping.
    window = SessionSettings(enabled=True, start="09:30", end="11:00",
                             timezone="America/New_York")
    assert build_session_map(bars, window).count != build_session_map(bars, plain).count

    # Nor must a different series, even one of the same length.
    other = bars.slice(0, len(bars))
    assert build_session_map(other, plain).count == build_session_map(bars, plain).count
