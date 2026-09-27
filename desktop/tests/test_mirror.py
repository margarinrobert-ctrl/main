"""The mirror market.

The mirror is only a control if it really is the same market reflected, so most
of these tests are exact identities: the returns are negated, the volatility is
unchanged, the bar ranges are unchanged, the OHLC ordering still holds, and
mirroring twice returns the original. If any of those drift, the control is
comparing two different things and its verdict means nothing.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from tradingbacktester.core.errors import InsufficientDataError
from tradingbacktester.core.types import BacktestConfig
from tradingbacktester.data.sample import generate_sample_data
from tradingbacktester.data.validation import validate_bars
from tradingbacktester.research.mirror import (drift_pct, format_mirror,
                                               mirror_bars, mirror_test)
from tradingbacktester.strategy.builtin import BUILTIN_STRATEGIES

from .conftest import make_bars


@pytest.fixture(scope="module")
def bars():
    return generate_sample_data("NQ", "1h", n_bars=4000, seed=3)


@pytest.fixture(scope="module")
def mirrored(bars):
    return mirror_bars(bars)


# --------------------------------------------------------------------------
# The reflection is exact
# --------------------------------------------------------------------------

def test_every_log_return_is_negated(bars, mirrored):
    original = np.diff(np.log(bars.close))
    reflected = np.diff(np.log(mirrored.close))
    assert np.allclose(reflected, -original)


def test_volatility_is_unchanged(bars, mirrored):
    """Same volatility, and therefore the same volatility clustering."""
    original = np.diff(np.log(bars.close))
    reflected = np.diff(np.log(mirrored.close))
    assert reflected.std() == pytest.approx(original.std())
    # Clustering: |r| in the mirror is |r| in the original, bar for bar.
    assert np.allclose(np.abs(reflected), np.abs(original))


def test_bar_ranges_and_intrabar_shape_survive(bars, mirrored):
    """An up-bar that opened on its low becomes a down-bar that opened on its high."""
    assert np.allclose(np.log(mirrored.high / mirrored.low),
                       np.log(bars.high / bars.low))
    assert np.allclose(np.log(mirrored.high / mirrored.open),
                       -np.log(bars.low / bars.open))
    assert np.allclose(np.log(mirrored.low / mirrored.open),
                       -np.log(bars.high / bars.open))
    assert np.allclose(np.log(mirrored.close / mirrored.open),
                       -np.log(bars.close / bars.open))


def test_opening_gaps_are_reflected(bars, mirrored):
    original = np.log(bars.open[1:]) - np.log(bars.close[:-1])
    reflected = np.log(mirrored.open[1:]) - np.log(mirrored.close[:-1])
    assert np.allclose(reflected, -original)


def test_the_mirror_is_a_valid_bar_series(mirrored):
    assert np.all(mirrored.high >= np.maximum(mirrored.open, mirrored.close))
    assert np.all(mirrored.low <= np.minimum(mirrored.open, mirrored.close))
    assert np.all(mirrored.low > 0), "log space must keep every price positive"
    assert np.all(np.isfinite(mirrored.close))


def test_the_mirror_introduces_no_new_data_quality_issues(bars, mirrored):
    before = {i.code for i in validate_bars(bars).issues}
    after = {i.code for i in validate_bars(mirrored).issues}
    assert after <= before


def test_the_timestamps_volume_and_timeframe_are_untouched(bars, mirrored):
    assert np.array_equal(mirrored.ts, bars.ts)
    assert np.array_equal(mirrored.volume, bars.volume)
    assert mirrored.timeframe.label == bars.timeframe.label
    assert len(mirrored) == len(bars)


def test_mirroring_twice_returns_the_original(bars, mirrored):
    back = mirror_bars(mirrored)
    for name in ("open", "high", "low", "close"):
        assert np.allclose(getattr(back, name), getattr(bars, name)), name


def test_the_drift_is_inverted(bars, mirrored):
    up, down = drift_pct(bars), drift_pct(mirrored)
    assert up > 0 and down < 0
    # A rise of x% mirrors to 1/(1+x) - 1.
    assert (1 + down / 100) == pytest.approx(1 / (1 + up / 100))


def test_the_mirror_starts_at_the_same_price(bars, mirrored):
    assert mirrored.open[0] == pytest.approx(bars.open[0])


def test_the_symbol_says_it_is_a_mirror(bars, mirrored):
    assert "MIRROR" in mirrored.instrument.symbol.upper()
    assert mirrored.meta.get("mirror_of") == bars.instrument.symbol
    # And mirroring again must not stack the suffix.
    assert mirror_bars(mirrored).instrument.symbol == mirrored.instrument.symbol


def test_a_hand_written_series_mirrors_to_the_expected_prices():
    """100 -> 110 -> 121 (two +10% bars) mirrors to 100 -> 100/1.1 -> 100/1.21."""
    series = make_bars([100.0, 110.0, 121.0], opens=[100.0, 110.0, 121.0],
                       highs=[100.0, 110.0, 121.0], lows=[100.0, 110.0, 121.0])
    reflected = mirror_bars(series)
    assert reflected.close[0] == pytest.approx(100.0)
    assert reflected.close[1] == pytest.approx(100.0 / 1.1)
    assert reflected.close[2] == pytest.approx(100.0 / 1.21)


def test_a_series_too_short_to_have_a_return_is_refused():
    with pytest.raises(InsufficientDataError):
        mirror_bars(make_bars([100.0]))


def test_a_non_positive_price_is_refused_by_name():
    series = make_bars([100.0, 101.0, 102.0])
    series.low[1] = 0.0
    with pytest.raises(InsufficientDataError) as exc:
        mirror_bars(series)
    assert "low" in str(exc.value)


# --------------------------------------------------------------------------
# The test that uses it
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def report(bars):
    spec = BUILTIN_STRATEGIES["EMA Cross + RSI"]()
    config = BacktestConfig(starting_capital=100_000.0)
    config.exits, config.execution = spec.exits, spec.execution
    config.session, config.costs, config.risk = spec.session, spec.costs, spec.risk
    return mirror_test(bars, spec, config)


def test_the_mirror_test_runs_both_sides(report):
    assert report.real.trades > 0
    assert report.mirror.trades > 0
    assert report.real.drift_pct > 0 > report.mirror.drift_pct


def test_the_halves_add_back_to_the_two_runs(report):
    assert (report.symmetric_component + report.direction_component
            == pytest.approx(report.real.net_profit))
    assert (report.symmetric_component - report.direction_component
            == pytest.approx(report.mirror.net_profit))


def _report(real_net: float, mirror_net: float, trades: int = 100):
    """A report with the two net figures set and everything else plausible."""
    from tradingbacktester.research.mirror import MirrorReport, Side

    def side(label, net, drift):
        return Side(label=label, drift_pct=drift, trades=trades,
                    net_profit=net, win_rate=50.0, profit_factor=1.1,
                    max_drawdown_pct=5.0, expectancy=net / trades if trades else 0.0,
                    long_trades=trades, short_trades=0)

    return MirrorReport(strategy="test", real=side("real", real_net, 100.0),
                        mirror=side("mirror", mirror_net, -50.0))


def test_a_drift_bet_is_named_as_one():
    """Profit on the real series, the same size loss on the mirror."""
    verdict = _report(10_000.0, -9_000.0).verdict()
    assert "only because the market went up" in verdict
    assert "direction bet" in verdict


def test_a_symmetric_edge_is_named_as_one():
    verdict = _report(10_000.0, 9_000.0).verdict()
    assert "does not depend on which way the market went" in verdict


def test_a_partly_directional_edge_reports_the_share():
    report = _report(10_000.0, 2_000.0)
    assert report.direction_share == pytest.approx(0.4)
    assert "40% of the real result is explained" in report.verdict()


def test_a_losing_strategy_is_not_credited_with_surviving_the_mirror():
    """A rule that lost on the real series has not passed anything."""
    verdict = _report(-5_000.0, 3_000.0).verdict()
    assert "did not make money on the real series" in verdict


def test_a_side_with_no_trades_is_not_given_a_verdict():
    assert "nothing to compare" in _report(1_000.0, 500.0, trades=0).verdict()


def test_a_trend_follower_loses_its_profit_on_the_mirror():
    """End to end, against the engine, on a series that only goes up."""
    import numpy as np

    closes = 100.0 * np.exp(np.cumsum(
        np.abs(np.random.default_rng(2).normal(0.0015, 0.0008, 1500))))
    rising = make_bars(closes.tolist(), timeframe="1d")
    spec = BUILTIN_STRATEGIES["MACD Trend"]()
    config = BacktestConfig(starting_capital=100_000.0)
    config.exits, config.execution = spec.exits, spec.execution
    config.session, config.costs, config.risk = spec.session, spec.costs, spec.risk
    result = mirror_test(rising, spec, config)
    assert result.real.trades and result.mirror.trades
    assert result.real.net_profit > 0, "a long trend rule must profit here"
    assert result.mirror.net_profit < result.real.net_profit
    assert result.direction_component > 0


def test_the_report_says_the_mirror_is_not_a_second_sample(report):
    text = format_mirror(report)
    flat = " ".join(text.split())
    assert "control, not a second sample" in flat
    assert "never as a simulation of a downturn" in flat
    assert "real" in text and "mirrored" in text
    assert max(len(line) for line in text.splitlines()) <= 78


def test_report_is_json_serialisable(report):
    payload = json.loads(json.dumps(report.to_dict()))
    assert payload["real"]["trades"] == report.real.trades
    assert payload["verdict"]
    assert payload["notes"]


def test_cancelling_stops_before_the_second_run(bars):
    from tradingbacktester.core.errors import CancelledError

    class Token:
        cancelled = True

    spec = BUILTIN_STRATEGIES["EMA Cross + RSI"]()
    with pytest.raises(CancelledError):
        mirror_test(bars, spec, BacktestConfig(), cancel=Token())
