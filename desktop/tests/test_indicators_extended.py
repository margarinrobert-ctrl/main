"""The thirty indicators in `indicators/extended.py`, checked by arithmetic.

`tests/test_indicators.py` already sweeps the whole registry for shape, for
short-series survival and for look-ahead, so these do not repeat any of that.
What they pin down is the thing a sweep cannot: that each one computes the
indicator it is NAMED after. A causal, correctly-shaped series of the wrong
formula passes every generic test there is.

Most are hand-computed on four or five bars. Where a hand computation would be
meaningless -- six nested EMAs -- the check is an identity against the core
library instead, which is the same argument made a different way.
"""

from __future__ import annotations

import numpy as np
import pytest

from tradingbacktester.core.timeframe import Timeframe
from tradingbacktester.data.instruments import default_instrument_for
from tradingbacktester.data.models import BarSeries
from tradingbacktester.data.sample import generate_sample_data
from tradingbacktester.indicators.base import safe_divide
from tradingbacktester.indicators.library import (REGISTRY, _ema, _rolling_max,
                                                  _rolling_mean, _rolling_sum,
                                                  _shift)


def bars_of(open_, high, low, close, volume=None) -> BarSeries:
    """A BarSeries from four lists, with five-minute stamps."""
    n = len(close)
    ts = (np.arange(n, dtype="int64") * 300 + 1_700_000_000) * 1_000_000_000
    return BarSeries(
        ts=ts, open=np.asarray(open_, dtype="float64"),
        high=np.asarray(high, dtype="float64"),
        low=np.asarray(low, dtype="float64"),
        close=np.asarray(close, dtype="float64"),
        volume=np.asarray(volume if volume is not None else [1.0] * n,
                          dtype="float64"),
        instrument=default_instrument_for("US30"),
        timeframe=Timeframe.parse("5m"))


def flat(values, volume=None) -> BarSeries:
    """A series where open == high == low == close."""
    return bars_of(values, values, values, values, volume)


@pytest.fixture(scope="module")
def sample() -> BarSeries:
    return generate_sample_data("NQ", "5m", n_bars=600, seed=3)


# --------------------------------------------------------------------------
# Moving averages
# --------------------------------------------------------------------------

def test_zlema_removes_the_lag_it_says_it_does():
    """Period 3 gives lag 1, so the EMA runs on ``2c - c[-1]``."""
    bars = flat([10.0, 11.0, 12.0, 13.0, 14.0])
    out = REGISTRY.compute("ZLEMA", bars, {"period": 3})["value"]
    # de-lagged = [nan, 12, 13, 14, 15]; EMA(3) seeds on the first three
    # DEFINED values, so the seed is mean(12, 13, 14) = 13 at index 3.
    assert out[3] == pytest.approx(13.0)
    assert out[4] == pytest.approx(13.0 + 0.5 * (15.0 - 13.0))


def test_t3_with_no_volume_factor_is_the_triple_ema(sample):
    """At v = 0 the coefficients collapse to ``c4 = 1`` on the third EMA."""
    price = sample.close.astype("float64")
    out = REGISTRY.compute("T3", sample,
                           {"period": 10, "volume_factor": 0.0})["value"]
    triple = _ema(_ema(_ema(price, 10), 10), 10)
    both = np.isfinite(out) & np.isfinite(triple)
    assert both.sum() > 400
    assert np.allclose(out[both], triple[both])


def test_t3_waits_for_all_six_of_its_averages(sample):
    """Its warm-up is the SIXTH nested EMA's, not the first's.

    The extra terms are multiplied by zero at ``v = 0``, and ``0 * nan`` is
    still nan -- which is the honest answer, because the sixth average really
    is undefined there.
    """
    price = sample.close.astype("float64")
    out = REGISTRY.compute("T3", sample,
                           {"period": 10, "volume_factor": 0.0})["value"]
    sixth = _ema(_ema(_ema(_ema(_ema(_ema(price, 10), 10), 10), 10), 10), 10)
    assert (int(np.flatnonzero(np.isfinite(out))[0])
            == int(np.flatnonzero(np.isfinite(sixth))[0]))


def test_kama_and_mcginley_track_the_price_they_follow(sample):
    price = sample.close.astype("float64")
    low, high = float(price.min()), float(price.max())
    span = high - low
    for key, params in (("KAMA", {"period": 10}), ("MCGINLEY", {"period": 14})):
        out = REGISTRY.compute(key, sample, params)["value"]
        seen = out[np.isfinite(out)]
        assert seen.size > 500
        assert seen.min() > low - span and seen.max() < high + span, key


def test_kama_is_flat_on_a_flat_series():
    bars = flat([100.0] * 40)
    out = REGISTRY.compute("KAMA", bars, {"period": 10})["value"]
    seen = out[np.isfinite(out)]
    assert np.allclose(seen, 100.0)


def test_alma_weights_sum_to_one_so_a_constant_survives():
    bars = flat([7.0] * 30)
    out = REGISTRY.compute("ALMA", bars, {"period": 9})["value"]
    assert np.allclose(out[np.isfinite(out)], 7.0)


def test_alma_offset_one_leans_on_the_newest_bar():
    """Offset 1.0 puts the Gaussian's peak on the most recent bar."""
    rising = [float(x) for x in range(1, 31)]
    late = REGISTRY.compute("ALMA", flat(rising),
                            {"period": 9, "offset": 1.0})["value"]
    early = REGISTRY.compute("ALMA", flat(rising),
                             {"period": 9, "offset": 0.0})["value"]
    # On a rising series the responsive one must sit closer to price.
    assert late[20] > early[20]


def test_alma_rejects_a_sigma_of_zero():
    from tradingbacktester.core.errors import IndicatorError

    with pytest.raises(IndicatorError):
        REGISTRY.compute("ALMA", flat([1.0] * 20), {"period": 9, "sigma": 0.0})


# --------------------------------------------------------------------------
# Oscillators
# --------------------------------------------------------------------------

def test_awesome_oscillator_is_the_difference_of_two_midpoint_averages():
    bars = bars_of([0.0, 2.0, 4.0, 6.0], [2.0, 4.0, 6.0, 8.0],
                   [0.0, 2.0, 4.0, 6.0], [0.0, 2.0, 4.0, 6.0])
    # hl2 = 1, 3, 5, 7
    out = REGISTRY.compute("AO", bars, {"fast": 2, "slow": 4})["value"]
    assert out[3] == pytest.approx((5 + 7) / 2 - (1 + 3 + 5 + 7) / 4)


def test_chande_momentum_is_net_over_total_movement():
    bars = flat([10.0, 11.0, 10.0, 13.0])
    out = REGISTRY.compute("CMO", bars, {"period": 2})["value"]
    assert not np.isfinite(out[1]), "the first difference is not a full window"
    assert out[2] == pytest.approx(0.0)          # up 1, down 1
    assert out[3] == pytest.approx(50.0)         # up 3, down 1 -> 100*2/4


def test_chande_momentum_is_bounded(sample):
    out = REGISTRY.compute("CMO", sample, {"period": 14})["value"]
    seen = out[np.isfinite(out)]
    assert seen.min() >= -100.0 - 1e-9 and seen.max() <= 100.0 + 1e-9


def test_ppo_is_macd_as_a_percentage(sample):
    price = sample.close.astype("float64")
    out = REGISTRY.compute("PPO", sample,
                           {"fast": 12, "slow": 26, "signal": 9})
    slow = _ema(price, 26)
    expected = 100.0 * safe_divide(_ema(price, 12) - slow, slow)
    assert np.allclose(out["ppo"], expected, equal_nan=True)
    assert np.allclose(out["histogram"], out["ppo"] - out["signal"],
                       equal_nan=True)


def test_trix_is_the_percentage_change_of_a_triple_ema(sample):
    price = sample.close.astype("float64")
    out = REGISTRY.compute("TRIX", sample, {"period": 15, "signal": 9})["trix"]
    triple = _ema(_ema(_ema(price, 15), 15), 15)
    expected = 100.0 * safe_divide(triple - _shift(triple, 1),
                                   _shift(triple, 1))
    assert np.allclose(out, expected, equal_nan=True)


def test_dpo_is_the_causal_form_not_the_displayed_one():
    """The chart's DPO is shifted into the future; this one is not.

    ``DPO[i] = close[i - (period/2 + 1)] - SMA(period)[i]``. Every term is
    known at bar ``i``, which is the whole reason for the difference.
    """
    closes = [float(x) for x in range(1, 21)]
    out = REGISTRY.compute("DPO", flat(closes), {"period": 4})["value"]
    i, back = 10, 4 // 2 + 1
    assert out[i] == pytest.approx(closes[i - back]
                                   - float(np.mean(closes[i - 3:i + 1])))


def test_kst_is_prings_weighted_sum_of_four_smoothed_rates(sample):
    price = sample.close.astype("float64")

    def roc(period: int) -> np.ndarray:
        prior = _shift(price, period)
        return 100.0 * safe_divide(price - prior, prior)

    expected = (1.0 * _rolling_mean(roc(10), 10)
                + 2.0 * _rolling_mean(roc(15), 10)
                + 3.0 * _rolling_mean(roc(20), 10)
                + 4.0 * _rolling_mean(roc(30), 15))
    out = REGISTRY.compute("KST", sample, {"signal": 9})["kst"]
    assert np.allclose(out, expected, equal_nan=True)


def test_balance_of_power_is_body_over_range():
    bars = bars_of([1.0, 2.0], [3.0, 4.0], [0.0, 1.0], [2.0, 3.0])
    out = REGISTRY.compute("BOP", bars, {"period": 1})["value"]
    assert out[0] == pytest.approx((2 - 1) / (3 - 0))
    assert out[1] == pytest.approx((3 - 2) / (4 - 1))


def test_balance_of_power_survives_a_zero_range_bar():
    """A bar whose high equals its low would divide by zero."""
    bars = bars_of([5.0, 5.0], [5.0, 6.0], [5.0, 4.0], [5.0, 5.5])
    out = REGISTRY.compute("BOP", bars, {"period": 1})["value"]
    assert np.isfinite(out[0]) and out[0] == pytest.approx(0.0)


def test_fisher_transform_is_bounded_and_finite(sample):
    """The transform is infinite at exactly +/-1, so it must be clamped."""
    out = REGISTRY.compute("FISHER", sample, {"period": 9})
    line = out["fisher"][np.isfinite(out["fisher"])]
    assert line.size > 500
    assert np.isfinite(line).all()
    # 0.5*ln(1.999/0.001) is the clamp's ceiling, about 3.8, plus the
    # half-weight carried from the previous bar.
    assert np.abs(line).max() < 12.0


def test_fisher_trigger_is_the_previous_fisher_value(sample):
    out = REGISTRY.compute("FISHER", sample, {"period": 9})
    line, trigger = out["fisher"], out["trigger"]
    both = np.isfinite(line) & np.isfinite(trigger)
    index = np.flatnonzero(both)[5:]
    assert np.allclose(trigger[index], line[index - 1])


def test_fisher_survives_a_flat_window():
    """A window with no range makes the normalisation 0/0."""
    out = REGISTRY.compute("FISHER", flat([50.0] * 40), {"period": 9})
    assert np.isfinite(out["fisher"][20])


def test_smi_and_stc_stay_in_their_declared_ranges(sample):
    smi = REGISTRY.compute("SMI", sample, {"period": 10})["smi"]
    seen = smi[np.isfinite(smi)]
    assert seen.min() >= -100.0 - 1e-6 and seen.max() <= 100.0 + 1e-6

    stc = REGISTRY.compute("STC", sample,
                           {"fast": 23, "slow": 50, "cycle": 10})["value"]
    seen = stc[np.isfinite(stc)]
    assert seen.min() >= -1e-9 and seen.max() <= 100.0 + 1e-9


def test_rvgi_signal_is_the_four_bar_weighted_average(sample):
    out = REGISTRY.compute("RVGI", sample, {"period": 10})
    line = out["rvgi"]
    expected = (line + 2.0 * _shift(line, 1) + 2.0 * _shift(line, 2)
                + _shift(line, 3)) / 6.0
    assert np.allclose(out["signal"], expected, equal_nan=True)


# --------------------------------------------------------------------------
# Trend
# --------------------------------------------------------------------------

def test_vortex_legs_are_the_published_ratios():
    bars = bars_of([10.0, 10.0], [12.0, 13.0], [8.0, 9.0], [11.0, 12.0])
    out = REGISTRY.compute("VORTEX", bars, {"period": 1})
    true_range = max(13.0 - 9.0, abs(13.0 - 11.0), abs(9.0 - 11.0))
    assert out["plus"][1] == pytest.approx(abs(13.0 - 8.0) / true_range)
    assert out["minus"][1] == pytest.approx(abs(9.0 - 12.0) / true_range)


def test_vortex_legs_are_never_negative(sample):
    out = REGISTRY.compute("VORTEX", sample, {"period": 14})
    for leg in ("plus", "minus"):
        seen = out[leg][np.isfinite(out[leg])]
        assert (seen >= 0.0).all(), leg


def test_ichimoku_cloud_is_displaced_backward_into_the_present():
    """``span_a[i]`` must be the value computed at ``i - displacement``.

    A chart plots the spans forward, which puts a number above bar *i* that was
    derived from bars after *i*. Reading that number would be reading the
    future; this reads the one a trader can actually see at the bar.
    """
    high = [float(x) for x in range(10, 40)]
    low = [x - 5.0 for x in high]
    close = [x - 2.0 for x in high]
    out = REGISTRY.compute("ICHIMOKU", bars_of(close, high, low, close),
                           {"conversion": 2, "base": 3, "span": 4,
                            "displacement": 2})
    raw = (out["conversion"] + out["base"]) / 2.0
    assert out["span_a"][10] == pytest.approx(raw[8])


def test_ichimoku_does_not_return_a_lagging_span():
    """Chikou has no causal form, so it is absent rather than wrong."""
    assert "chikou" not in REGISTRY.get("ICHIMOKU").outputs


def test_heikin_ashi_open_is_the_previous_bodys_midpoint():
    """Three bars deep, because the recursion is where this goes wrong."""
    bars = bars_of([10.0, 12.0, 14.0], [14.0, 16.0, 18.0],
                   [6.0, 8.0, 10.0], [12.0, 14.0, 16.0])
    out = REGISTRY.compute("HEIKIN", bars)
    close_0 = (10 + 14 + 6 + 12) / 4
    open_0 = (10 + 12) / 2                     # seed: the real candle's mid
    close_1 = (12 + 16 + 8 + 14) / 4
    open_1 = (open_0 + close_0) / 2
    close_2 = (14 + 18 + 10 + 16) / 4
    open_2 = (open_1 + close_1) / 2

    assert out["close"][0] == pytest.approx(close_0)
    assert out["open"][0] == pytest.approx(open_0)
    assert out["open"][1] == pytest.approx(open_1)
    assert out["open"][2] == pytest.approx(open_2)
    assert out["high"][1] == pytest.approx(max(16.0, open_1, close_1))
    assert out["low"][1] == pytest.approx(min(8.0, open_1, close_1))


def test_heikin_ashi_high_and_low_bracket_the_body(sample):
    out = REGISTRY.compute("HEIKIN", sample)
    both = np.isfinite(out["open"]) & np.isfinite(out["close"])
    assert (out["high"][both] >= np.maximum(out["open"][both],
                                            out["close"][both]) - 1e-9).all()
    assert (out["low"][both] <= np.minimum(out["open"][both],
                                           out["close"][both]) + 1e-9).all()


# --------------------------------------------------------------------------
# Volatility
# --------------------------------------------------------------------------

def test_chandelier_hangs_an_atr_multiple_off_the_extreme():
    bars = bars_of([10.0, 10.0], [12.0, 13.0], [8.0, 9.0], [11.0, 12.0])
    out = REGISTRY.compute("CHANDELIER", bars,
                           {"period": 1, "multiplier": 2.0})
    true_range = 4.0
    assert out["long"][1] == pytest.approx(13.0 - 2.0 * true_range)
    assert out["short"][1] == pytest.approx(9.0 + 2.0 * true_range)


def test_natr_is_atr_as_a_percentage_of_price():
    bars = bars_of([10.0, 10.0], [12.0, 13.0], [8.0, 9.0], [11.0, 12.0])
    out = REGISTRY.compute("NATR", bars, {"period": 1})["value"]
    assert out[1] == pytest.approx(100.0 * 4.0 / 12.0)


def test_mass_index_is_the_ratio_of_a_single_to_a_double_ema(sample):
    span = sample.high.astype("float64") - sample.low.astype("float64")
    single = _ema(span, 9)
    expected = _rolling_sum(safe_divide(single, _ema(single, 9)), 25)
    out = REGISTRY.compute("MASS", sample, {"period": 25, "smoothing": 9})
    assert np.allclose(out["value"], expected, equal_nan=True)


def test_ulcer_index_is_never_negative_and_is_zero_at_a_new_high():
    rising = [float(x) for x in range(1, 40)]
    out = REGISTRY.compute("ULCER", flat(rising), {"period": 14})["value"]
    seen = out[np.isfinite(out)]
    assert (seen >= -1e-12).all()
    # Every bar is a new high, so the drawdown is zero throughout.
    assert np.allclose(seen, 0.0, atol=1e-9)


def test_ulcer_index_charges_only_for_downside(sample):
    out = REGISTRY.compute("ULCER", sample, {"period": 14})["value"]
    seen = out[np.isfinite(out)]
    assert seen.size > 500 and (seen >= -1e-12).all()


def test_historical_volatility_scales_with_the_annualising_factor(sample):
    one = REGISTRY.compute("HISTVOL", sample,
                           {"period": 20, "periods_per_year": 252})["value"]
    four = REGISTRY.compute("HISTVOL", sample,
                            {"period": 20, "periods_per_year": 1008})["value"]
    both = np.isfinite(one) & np.isfinite(four)
    assert np.allclose(four[both], 2.0 * one[both])


def test_historical_volatility_of_a_flat_series_is_zero():
    out = REGISTRY.compute("HISTVOL", flat([100.0] * 60), {"period": 20})
    assert np.allclose(out["value"][np.isfinite(out["value"])], 0.0, atol=1e-12)


def test_historical_volatility_survives_a_non_positive_price():
    """A log return needs a positive ratio; zero or negative must not crash."""
    out = REGISTRY.compute("HISTVOL", flat([10.0, 0.0, 10.0] * 15),
                           {"period": 20})["value"]
    assert not np.isinf(out).any()


# --------------------------------------------------------------------------
# Volume
# --------------------------------------------------------------------------

def test_accumulation_line_signs_volume_by_where_the_bar_closed():
    bars = bars_of([10.0, 10.0], [12.0, 12.0], [8.0, 8.0], [12.0, 8.0],
                   [100.0, 200.0])
    out = REGISTRY.compute("AD", bars)["value"]
    assert out[0] == pytest.approx(100.0)        # closed at the high
    assert out[1] == pytest.approx(100.0 - 200.0)  # closed at the low


def test_accumulation_line_survives_a_zero_range_bar():
    bars = bars_of([5.0, 5.0], [5.0, 6.0], [5.0, 4.0], [5.0, 6.0],
                   [10.0, 20.0])
    out = REGISTRY.compute("AD", bars)["value"]
    assert np.isfinite(out).all()


def test_chaikin_oscillator_is_the_macd_of_the_accumulation_line(sample):
    line = REGISTRY.compute("AD", sample)["value"]
    out = REGISTRY.compute("ADOSC", sample, {"fast": 3, "slow": 10})["value"]
    assert np.allclose(out, _ema(line, 3) - _ema(line, 10), equal_nan=True)


def test_price_volume_trend_scales_volume_by_the_percentage_move():
    bars = bars_of([10.0, 10.0], [12.0, 12.0], [8.0, 8.0], [12.0, 8.0],
                   [100.0, 200.0])
    out = REGISTRY.compute("PVT", bars)["value"]
    assert out[1] == pytest.approx((8.0 - 12.0) / 12.0 * 200.0)


def test_force_index_is_the_smoothed_price_change_times_volume(sample):
    close = sample.close.astype("float64")
    expected = _ema((close - _shift(close, 1)) * sample.volume.astype("float64"),
                    13)
    out = REGISTRY.compute("FI", sample, {"period": 13})["value"]
    assert np.allclose(out, expected, equal_nan=True)


def test_volume_indices_move_only_on_their_own_volume_direction():
    bars = flat([100.0, 110.0, 99.0], [10.0, 20.0, 5.0])
    out = REGISTRY.compute("PVI_NVI", bars)
    # Bar 1: volume rose, so PVI takes the +10% and NVI does not move.
    assert out["positive"][1] == pytest.approx(1000.0 * 1.10)
    assert out["negative"][1] == pytest.approx(1000.0)
    # Bar 2: volume fell, so NVI takes the -10% and PVI holds.
    assert out["positive"][2] == pytest.approx(1000.0 * 1.10)
    assert out["negative"][2] == pytest.approx(
        1000.0 * (1.0 + (99.0 - 110.0) / 110.0))


def test_ease_of_movement_survives_a_zero_range_bar():
    bars = bars_of([5.0, 5.0], [5.0, 6.0], [5.0, 4.0], [5.0, 5.5],
                   [10.0, 20.0])
    out = REGISTRY.compute("EOM", bars, {"period": 1})["value"]
    assert not np.isinf(out).any()


# --------------------------------------------------------------------------
# What the module refuses to duplicate
# --------------------------------------------------------------------------

def test_the_direction_lines_are_not_registered_twice():
    """+DI/-DI and the Aroon oscillator already ship as extra outputs.

    Registering them again would give one series two names, two parameter sets
    and two chances to drift apart.
    """
    assert "plus_di" in REGISTRY.get("ADX").outputs
    assert "minus_di" in REGISTRY.get("ADX").outputs
    assert "oscillator" in REGISTRY.get("AROON").outputs
    for absent in ("DMI", "PLUS_DI", "MINUS_DI", "AROON_OSC"):
        assert not REGISTRY.has(absent), absent


def test_the_library_grew_and_the_core_still_registers():
    from tradingbacktester.indicators.library import REQUIRED_KEYS

    assert len(REGISTRY.all()) >= 78
    for key in REQUIRED_KEYS:
        assert REGISTRY.has(key), key


def test_a_deep_warm_up_indicator_cannot_trade_on_its_own_nan():
    """The engine must not open a position while the indicator is undefined.

    T3 is nan for six nested EMAs, far longer than its declared warm-up, so if
    a nan comparison ever evaluated true this is where it would show.
    """
    from tradingbacktester.core.types import BacktestConfig
    from tradingbacktester.engine.backtester import Backtester
    from tradingbacktester.strategy.spec import StrategySpec

    bars = generate_sample_data("NQ", "5m", n_bars=800, seed=5)
    spec = StrategySpec.from_dict({
        "name": "T3 warm-up probe",
        "indicators": [{"ref": "t3", "indicator": "T3",
                        "params": {"period": 10, "volume_factor": 0.7}}],
        "entry_long": {"kind": "group", "op": "and", "children": [
            {"kind": "compare", "left": {"kind": "indicator", "ref": "t3"},
             "op": ">", "right": {"kind": "const", "value": 0.0}}]},
        "exit_long": {"kind": "group", "op": "and", "children": [
            {"kind": "compare", "left": {"kind": "indicator", "ref": "t3"},
             "op": "<", "right": {"kind": "const", "value": 0.0}}]},
    })
    series = REGISTRY.compute("T3", bars,
                              {"period": 10, "volume_factor": 0.7})["value"]
    first = int(np.flatnonzero(np.isfinite(series))[0])
    result = Backtester(bars, spec, BacktestConfig()).run()
    for trade in result.trades:
        assert trade.entry_bar >= first, (
            f"a trade opened at bar {trade.entry_bar} while T3 was still nan "
            f"until bar {first}")
