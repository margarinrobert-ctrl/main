"""Indicator correctness.

Every assertion here is either a value that can be worked out on paper or an
invariant that must hold for any correct implementation.  The look-ahead test at
the bottom is the important one: it runs over *every* registered indicator.
"""

from __future__ import annotations

import numpy as np
import pytest

from tradingbacktester.core.errors import IndicatorError
from tradingbacktester.indicators.registry import REGISTRY

from .conftest import make_bars


# --------------------------------------------------------------------------
# Moving averages
# --------------------------------------------------------------------------

def test_sma_hand_computed():
    bars = make_bars([1, 2, 3, 4, 5])
    sma = REGISTRY.compute("SMA", bars, {"period": 3})["value"]
    assert np.isnan(sma[:2]).all()
    assert np.allclose(sma[2:], [2.0, 3.0, 4.0])


def test_sma_period_one_is_the_source():
    bars = make_bars([3, 1, 4, 1, 5])
    sma = REGISTRY.compute("SMA", bars, {"period": 1})["value"]
    assert np.allclose(sma, bars.close)


def test_ema_seeded_from_sma():
    """EMA is seeded with the SMA of the first n values, then recursive."""
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    bars = make_bars(values)
    ema = REGISTRY.compute("EMA", bars, {"period": 3})["value"]
    k = 2.0 / 4.0
    expected = [np.nan, np.nan, 2.0]
    for x in values[3:]:
        expected.append(x * k + expected[-1] * (1 - k))
    assert np.isnan(ema[:2]).all()
    assert np.allclose(ema[2:], expected[2:])


def test_moving_averages_track_a_constant_series():
    bars = make_bars([50.0] * 60)
    for key in ("SMA", "EMA", "WMA", "RMA", "DEMA", "TEMA", "HMA", "VWMA"):
        out = REGISTRY.compute(key, bars, {"period": 10})["value"]
        tail = out[~np.isnan(out)]
        assert len(tail) > 0, key
        assert np.allclose(tail, 50.0, atol=1e-6), key


def test_moving_average_lags_a_rising_series():
    """A trailing average of a rising series must sit below the latest price."""
    bars = make_bars(list(np.arange(100.0, 160.0)))
    for key in ("SMA", "EMA", "WMA", "RMA"):
        out = REGISTRY.compute(key, bars, {"period": 10})["value"]
        assert out[-1] < bars.close[-1], key


# --------------------------------------------------------------------------
# Oscillators
# --------------------------------------------------------------------------

def test_rsi_of_a_rising_series_is_100():
    bars = make_bars(list(np.arange(1.0, 40.0)))
    rsi = REGISTRY.compute("RSI", bars, {"period": 14})["value"]
    assert np.isnan(rsi[:14]).all()
    assert np.allclose(rsi[14:], 100.0)


def test_rsi_of_a_falling_series_is_zero():
    bars = make_bars(list(np.arange(40.0, 1.0, -1.0)))
    rsi = REGISTRY.compute("RSI", bars, {"period": 14})["value"]
    assert np.allclose(rsi[14:], 0.0)


def test_rsi_stays_within_bounds():
    rng = np.random.default_rng(4)
    bars = make_bars(100 + np.cumsum(rng.normal(0, 1, 400)))
    rsi = REGISTRY.compute("RSI", bars, {"period": 14})["value"]
    finite = rsi[~np.isnan(rsi)]
    assert (finite >= -1e-9).all() and (finite <= 100 + 1e-9).all()


def test_cci_uses_hlc3_and_mean_absolute_deviation():
    """CCI is defined on the typical price with MAD and the 0.015 constant."""
    rng = np.random.default_rng(11)
    close = 100 + np.cumsum(rng.normal(0, 1, 60))
    high, low = close + 1.5, close - 1.5
    bars = make_bars(close, high, low)
    cci = REGISTRY.compute("CCI", bars, {"period": 20})["value"]

    tp = (high + low + close) / 3.0
    expected = np.full(60, np.nan)
    for i in range(19, 60):
        window = tp[i - 19:i + 1]
        mad = np.mean(np.abs(window - window.mean()))
        expected[i] = (tp[i] - window.mean()) / (0.015 * mad) if mad else np.nan
    assert np.allclose(cci[19:], expected[19:], atol=1e-8)


def test_stochastic_is_bounded_and_k_is_100_at_the_high():
    close = np.array([10.0, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20])
    bars = make_bars(close, close + 0.0, close - 0.0)
    out = REGISTRY.compute("STOCH", bars, {"k_period": 5, "smooth_k": 1, "d_period": 3})
    k = out["k"][~np.isnan(out["k"])]
    # Closing at the top of every window puts raw %K at 100.
    assert np.allclose(k, 100.0)
    assert set(out) == {"k", "d"}


# --------------------------------------------------------------------------
# Volatility
# --------------------------------------------------------------------------

def test_atr_of_a_constant_range():
    close = np.full(40, 100.0)
    bars = make_bars(close, close + 2.0, close - 2.0, close)
    atr = REGISTRY.compute("ATR", bars, {"period": 14})["value"]
    assert np.isclose(atr[-1], 4.0, atol=1e-9)


def test_atr_is_never_negative():
    rng = np.random.default_rng(5)
    close = 100 + np.cumsum(rng.normal(0, 1, 300))
    open_ = np.concatenate([[100.0], close[:-1]])
    high = np.maximum(open_, close) + rng.random(300)
    low = np.minimum(open_, close) - rng.random(300)
    bars = make_bars(close, high, low, open_)
    atr = REGISTRY.compute("ATR", bars, {"period": 14})["value"]
    finite = atr[~np.isnan(atr)]
    assert (finite >= 0).all()


def test_bollinger_bands_use_population_stdev():
    rng = np.random.default_rng(1)
    close = 100 + np.cumsum(rng.normal(0, 1, 60))
    bars = make_bars(close)
    bb = REGISTRY.compute("BBANDS", bars, {"period": 20, "deviation": 2.0})
    sma = REGISTRY.compute("SMA", bars, {"period": 20})["value"]
    sd = np.array([np.std(close[i - 19:i + 1]) for i in range(19, 60)])  # ddof=0
    assert np.allclose(bb["middle"][19:], sma[19:])
    assert np.allclose(bb["upper"][19:], sma[19:] + 2 * sd)
    assert np.allclose(bb["lower"][19:], sma[19:] - 2 * sd)


def test_bollinger_bands_collapse_on_a_flat_series():
    bars = make_bars([100.0] * 40)
    bb = REGISTRY.compute("BBANDS", bars, {"period": 20})
    assert np.allclose(bb["upper"][19:], 100.0)
    assert np.allclose(bb["lower"][19:], 100.0)


def test_donchian_bounds_the_price():
    rng = np.random.default_rng(6)
    close = 100 + np.cumsum(rng.normal(0, 1, 200))
    high, low = close + 1, close - 1
    bars = make_bars(close, high, low)
    dc = REGISTRY.compute("DONCHIAN", bars, {"period": 20})
    valid = ~np.isnan(dc["upper"])
    assert (dc["upper"][valid] >= high[valid] - 1e-9).all()
    assert (dc["lower"][valid] <= low[valid] + 1e-9).all()
    assert np.allclose(dc["middle"][valid],
                       (dc["upper"][valid] + dc["lower"][valid]) / 2.0)


# --------------------------------------------------------------------------
# Trend
# --------------------------------------------------------------------------

def test_macd_is_the_difference_of_two_emas():
    rng = np.random.default_rng(2)
    bars = make_bars(100 + np.cumsum(rng.normal(0, 1, 120)))
    macd = REGISTRY.compute("MACD", bars, {"fast": 12, "slow": 26, "signal": 9})
    fast = REGISTRY.compute("EMA", bars, {"period": 12})["value"]
    slow = REGISTRY.compute("EMA", bars, {"period": 26})["value"]
    assert np.allclose(macd["macd"][25:], (fast - slow)[25:], equal_nan=True)
    assert np.allclose(macd["histogram"][40:],
                       (macd["macd"] - macd["signal"])[40:])


def test_adx_on_a_pure_uptrend():
    up = np.arange(1.0, 80.0) + 100.0
    bars = make_bars(up, up + 1, up - 1, up - 0.5)
    adx = REGISTRY.compute("ADX", bars, {"period": 14})
    assert adx["plus_di"][-1] > adx["minus_di"][-1]
    assert np.isclose(adx["minus_di"][-1], 0.0, atol=1e-6)


def test_supertrend_direction_is_plus_or_minus_one():
    rng = np.random.default_rng(9)
    close = 100 + np.cumsum(rng.normal(0, 1, 300))
    bars = make_bars(close, close + 2, close - 2)
    st = REGISTRY.compute("SUPERTREND", bars, {"period": 10, "multiplier": 3.0})
    direction = st["direction"][~np.isnan(st["direction"])]
    assert set(np.unique(direction)).issubset({-1.0, 1.0})


# --------------------------------------------------------------------------
# Volume
# --------------------------------------------------------------------------

def test_vwap_with_zero_volume_does_not_divide_by_zero():
    bars = make_bars([100.0] * 40, volumes=np.zeros(40))
    vwap = REGISTRY.compute("VWAP", bars)["value"]
    assert np.isnan(vwap).all()


def test_vwap_of_a_constant_price_is_that_price():
    bars = make_bars([100.0] * 40, volumes=np.full(40, 500.0))
    vwap = REGISTRY.compute("VWAP", bars)["value"]
    finite = vwap[~np.isnan(vwap)]
    assert len(finite) > 0
    assert np.allclose(finite, 100.0)


def test_obv_accumulates_signed_volume():
    close = np.array([10.0, 11.0, 10.0, 12.0])
    volume = np.array([100.0, 200.0, 300.0, 400.0])
    bars = make_bars(close, volumes=volume)
    obv = REGISTRY.compute("OBV", bars)["value"]
    # Bar 0 seeds at 0; up, down, up.
    assert np.allclose(obv, [0.0, 200.0, -100.0, 300.0])


# --------------------------------------------------------------------------
# Registry behaviour
# --------------------------------------------------------------------------

def test_unknown_indicator_raises_a_useful_error():
    bars = make_bars([1, 2, 3])
    with pytest.raises(IndicatorError) as exc:
        REGISTRY.compute("NOT_AN_INDICATOR", bars)
    assert "NOT_AN_INDICATOR" in str(exc.value)


def test_unknown_parameter_is_rejected():
    bars = make_bars([1, 2, 3, 4, 5])
    with pytest.raises(IndicatorError):
        REGISTRY.compute("SMA", bars, {"perid": 3})


def test_out_of_range_parameter_is_rejected():
    bars = make_bars([1, 2, 3, 4, 5])
    with pytest.raises(IndicatorError):
        REGISTRY.compute("SMA", bars, {"period": 0})


def test_every_indicator_returns_correctly_shaped_float_arrays(random_bars):
    for definition in REGISTRY.all():
        out = REGISTRY.compute(definition.key, random_bars)
        assert set(out) >= set(definition.outputs), definition.key
        for name, arr in out.items():
            assert arr.dtype == np.float64, f"{definition.key}.{name}"
            assert arr.shape == (len(random_bars),), f"{definition.key}.{name}"


def test_every_indicator_survives_a_very_short_series():
    """Three bars is fewer than any default period; nothing may raise."""
    bars = make_bars([100.0, 101.0, 99.5])
    for definition in REGISTRY.all():
        out = REGISTRY.compute(definition.key, bars)
        for arr in out.values():
            assert len(arr) == 3, definition.key


def test_no_indicator_looks_ahead(random_bars):
    """The decisive test.

    Truncating the series must not change any value the indicator already
    produced.  Anything that fails this is reading a future bar, which would
    make every backtest using it meaningless.
    """
    cut = 400
    truncated = random_bars.slice(0, cut)
    offenders: list[str] = []
    for definition in REGISTRY.all():
        full = REGISTRY.compute(definition.key, random_bars)
        part = REGISTRY.compute(definition.key, truncated)
        for name in full:
            if not np.allclose(full[name][:cut], part[name],
                               equal_nan=True, atol=1e-9):
                offenders.append(f"{definition.key}.{name}")
    assert not offenders, f"indicators using future data: {offenders}"
