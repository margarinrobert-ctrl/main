"""The statistics indicators, checked against values worked out by hand.

The generic battery in ``test_indicators.py`` already proves every registered
indicator is causal and warms up with NaN.  What it cannot check is whether
each one computes the thing its name claims, and these are exactly the family
where a plausible-looking wrong answer is hardest to notice: an efficiency
ratio that is off by a factor still moves the right way.
"""

from __future__ import annotations

import numpy as np
import pytest

from tradingbacktester.indicators.base import REGISTRY
import tradingbacktester.indicators.library  # noqa: F401 - registers everything

from .conftest import make_bars

NEW = ("EFFICIENCY_RATIO", "RSQUARED", "AUTOCORR", "PERCENTILE_RANK",
       "DRAWDOWN", "SEMIVAR_RATIO", "SKEW", "CVAR", "VOL_RATIO",
       "ZSCORE_VOL", "CONNORS_RSI", "COPPOCK")


def _compute(key, bars, **params):
    definition = REGISTRY.get(key)
    values = dict(definition.default_params())
    values.update(params)
    out = REGISTRY.compute(key, bars, values, definition.default_source)
    return out["value"] if isinstance(out, dict) else out


@pytest.fixture
def rising(simple_instrument):
    return make_bars(list(np.arange(100.0, 200.0)), instrument=simple_instrument)


@pytest.fixture
def noisy(simple_instrument):
    rng = np.random.default_rng(7)
    close = 100.0 + np.cumsum(rng.normal(0.0, 1.0, 600))
    high = close + rng.random(600)
    low = close - rng.random(600)
    open_ = np.concatenate([[100.0], close[:-1]])
    return make_bars(close, high, low, open_, instrument=simple_instrument)


# --------------------------------------------------------------------------
# every new one is registered and behaves
# --------------------------------------------------------------------------

@pytest.mark.parametrize("key", NEW)
def test_it_is_registered_and_produces_numbers(key, noisy):
    values = _compute(key, noisy)
    assert values.shape == (len(noisy),)
    assert np.isfinite(values).any(), f"{key} produced no finite value at all"


@pytest.mark.parametrize("key", NEW)
def test_the_warm_up_is_nan_not_a_guess(key, noisy):
    values = _compute(key, noisy)
    first = int(np.argmax(np.isfinite(values)))
    assert first > 0, f"{key} produced a value on the very first bar"
    assert np.isnan(values[:first]).all()


@pytest.mark.parametrize("key", NEW)
def test_no_runtime_warning_escapes(key, noisy):
    with np.errstate(all="raise"):
        try:
            _compute(key, noisy)
        except FloatingPointError as exc:      # pragma: no cover - a real bug
            pytest.fail(f"{key} raised {exc} on ordinary data")


# --------------------------------------------------------------------------
# each one computes what its name says
# --------------------------------------------------------------------------

def test_efficiency_ratio_is_one_on_a_straight_line(rising):
    values = _compute("EFFICIENCY_RATIO", rising, period=20)
    assert values[-1] == pytest.approx(1.0)


def test_efficiency_ratio_is_low_on_a_saw_tooth(simple_instrument):
    bars = make_bars([100.0, 101.0] * 40, instrument=simple_instrument)
    values = _compute("EFFICIENCY_RATIO", bars, period=20)
    assert values[-1] == pytest.approx(0.0, abs=1e-9)


def test_rsquared_is_one_on_a_straight_line(rising):
    assert _compute("RSQUARED", rising, period=20)[-1] == pytest.approx(1.0)


def test_rsquared_matches_numpy_on_a_known_window(noisy):
    period = 30
    values = _compute("RSQUARED", noisy, period=period)
    window = np.asarray(noisy.close[-period:], dtype="float64")
    expected = np.corrcoef(np.arange(period), window)[0, 1] ** 2
    assert values[-1] == pytest.approx(expected, rel=1e-9)


def test_autocorrelation_finds_a_deliberate_alternation(simple_instrument):
    # Up one, down one: every return is the negative of the last.
    close = 100.0 + np.tile([1.0, 0.0], 200)
    bars = make_bars(close, instrument=simple_instrument)
    values = _compute("AUTOCORR", bars, period=100, lag=1)
    assert values[-1] < -0.8, "an alternating series must autocorrelate negatively"


def test_autocorrelation_matches_numpy(noisy):
    period, lag = 120, 1
    values = _compute("AUTOCORR", noisy, period=period, lag=lag)
    close = np.asarray(noisy.close, dtype="float64")
    returns = np.log(close[1:] / close[:-1])
    a = returns[-period:]
    b = returns[-period - lag:-lag]
    assert values[-1] == pytest.approx(float(np.corrcoef(a, b)[0, 1]), abs=1e-9)


def test_percentile_rank_is_one_hundred_at_a_new_high(rising):
    values = _compute("PERCENTILE_RANK", rising, period=50)
    assert values[-1] == pytest.approx(100.0), (
        "a new high must reach 100, or a rule written as 'rank > 99' can "
        "never fire")


def test_percentile_rank_is_at_its_floor_at_a_new_low(simple_instrument):
    bars = make_bars(list(np.arange(200.0, 100.0, -1.0)),
                     instrument=simple_instrument)
    values = _compute("PERCENTILE_RANK", bars, period=50)
    assert values[-1] == pytest.approx(2.0)     # only itself, 1 of 50


def test_drawdown_is_zero_at_the_high_and_negative_below(rising, noisy):
    assert _compute("DRAWDOWN", rising, period=50)[-1] == pytest.approx(0.0)
    values = _compute("DRAWDOWN", noisy, period=50)
    finite = values[np.isfinite(values)]
    assert (finite <= 1e-9).all(), "drawdown must never be positive"


def test_semivariance_ratio_is_above_one_when_falls_are_larger(simple_instrument):
    # Three small rises then one large fall: the drift is roughly flat, so
    # what the ratio picks up is the asymmetry and nothing else. Alternating
    # -3%/+3.1% would NOT work -- in logs those are the same size.
    close = [100.0]
    for i in range(400):
        close.append(close[-1] * (0.94 if i % 4 == 3 else 1.021))
    bars = make_bars(close, instrument=simple_instrument)
    assert _compute("SEMIVAR_RATIO", bars, period=60)[-1] > 1.5


def test_semivariance_ratio_is_near_one_on_a_symmetric_series(simple_instrument):
    close = [100.0]
    for i in range(400):
        close.append(close[-1] * (0.97 if i % 2 else 1.0 / 0.97))
    bars = make_bars(close, instrument=simple_instrument)
    assert _compute("SEMIVAR_RATIO", bars, period=60)[-1] == pytest.approx(
        1.0, abs=0.05)


def test_skew_matches_the_population_definition(noisy):
    period = 80
    values = _compute("SKEW", noisy, period=period)
    close = np.asarray(noisy.close, dtype="float64")
    returns = np.log(close[1:] / close[:-1])[-period:]
    centred = returns - returns.mean()
    expected = (centred ** 3).mean() / (centred ** 2).mean() ** 1.5
    assert values[-1] == pytest.approx(expected, rel=1e-6)


def test_cvar_is_the_mean_of_the_tail_not_its_edge(noisy):
    period, tail = 100, 5.0
    values = _compute("CVAR", noisy, period=period, tail=tail)
    close = np.asarray(noisy.close, dtype="float64")
    returns = np.log(close[1:] / close[:-1])[-period:]
    take = int(round(period * tail / 100.0))
    expected = 100.0 * np.sort(returns)[:take].mean()
    assert values[-1] == pytest.approx(expected, rel=1e-9)
    # And it must be worse than the quantile at the tail's edge.
    edge = 100.0 * np.sort(returns)[take - 1]
    assert values[-1] <= edge + 1e-12


def test_vol_ratio_is_one_when_both_windows_see_the_same_market(simple_instrument):
    bars = make_bars([100.0, 102.0] * 200, instrument=simple_instrument)
    values = _compute("VOL_RATIO", bars, fast=10, slow=100)
    assert values[-1] == pytest.approx(1.0, abs=1e-9)


def test_vol_ratio_rises_when_the_market_speeds_up(simple_instrument):
    calm = list(100.0 + np.tile([0.0, 0.2], 150))
    wild = list(100.0 + np.tile([0.0, 6.0], 15))
    bars = make_bars(calm + wild, instrument=simple_instrument)
    values = _compute("VOL_RATIO", bars, fast=10, slow=100)
    quiet = values[len(calm) - 5]
    assert quiet == pytest.approx(1.0, abs=0.05), "the calm stretch is its own baseline"
    assert values[-1] > 3.0 * quiet


def test_zscore_vol_is_zero_when_volatility_is_unchanged(simple_instrument):
    rng = np.random.default_rng(3)
    close = 100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.002, 900))
    bars = make_bars(close, instrument=simple_instrument)
    values = _compute("ZSCORE_VOL", bars, period=20, lookback=250)
    finite = values[np.isfinite(values)]
    assert abs(float(np.median(finite))) < 1.0


def test_connors_rsi_stays_inside_its_own_scale(noisy):
    values = _compute("CONNORS_RSI", noisy)
    finite = values[np.isfinite(values)]
    assert finite.min() >= 0.0 and finite.max() <= 100.0


def test_connors_rsi_splits_into_its_three_components(rising):
    """A linear ramp pins all three, so the composite is arithmetic.

    RSI(3) of a series that only rises is 100 and the streak RSI is 100. The
    percentile rank is **0**, and that is correct rather than a defect: adding
    a fixed amount to a rising price is a *shrinking* percentage return, so
    every earlier return in the window is larger than the current one. The
    composite is therefore exactly 200/3, and a test that expected "high
    because price rose" would have been testing the wrong thing.
    """
    values = _compute("CONNORS_RSI", rising, rank_period=50)
    assert values[-1] == pytest.approx(200.0 / 3.0, abs=0.01)


def test_coppock_matches_its_definition(noisy):
    long_roc, short_roc, period = 14, 11, 10
    values = _compute("COPPOCK", noisy, long_roc=long_roc,
                      short_roc=short_roc, period=period)
    close = np.asarray(noisy.close, dtype="float64")
    combined = (100.0 * (close[-period:] / close[-period - long_roc:-long_roc] - 1.0)
                + 100.0 * (close[-period:] / close[-period - short_roc:-short_roc] - 1.0))
    weights = np.arange(1.0, period + 1.0)
    expected = float(combined @ (weights / weights.sum()))
    assert values[-1] == pytest.approx(expected, rel=1e-9)


# --------------------------------------------------------------------------
# they are usable from a strategy
# --------------------------------------------------------------------------

@pytest.mark.parametrize("key", NEW)
def test_each_one_can_carry_a_strategy(key, noisy):
    from tradingbacktester.core.types import BacktestConfig
    from tradingbacktester.engine.backtester import Backtester
    from tradingbacktester.strategy.spec import (Compare, IndicatorOperand,
                                                 IndicatorSlot, StrategySpec)

    definition = REGISTRY.get(key)
    values = _compute(key, noisy)
    finite = values[np.isfinite(values)]
    midpoint = float(np.median(finite))

    spec = StrategySpec(name=f"{key} test")
    spec.indicators = [IndicatorSlot(ref="x", indicator=key,
                                     params=dict(definition.default_params()))]
    spec.entry_long = Compare(IndicatorOperand("x"), ">",
                              _const(midpoint))
    spec.exit_long = Compare(IndicatorOperand("x"), "<", _const(midpoint))
    spec.validate()
    result = Backtester(noisy, spec, BacktestConfig()).run()
    assert result.trades, f"a strategy on {key} took no trades at its median"


def _const(value: float):
    from tradingbacktester.strategy.spec import ConstOperand

    return ConstOperand(float(value))
