"""The optimisations, and the guards that stop them changing an answer.

Every test here exists because making something faster is the easiest way to
make it wrong. Each one pins the fast version against a reference that is
obviously correct and obviously slow.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from tradingbacktester.core.types import CostModel
from tradingbacktester.data.sample import generate_sample_data
from tradingbacktester.finder.candidates import (_INDICATOR_CACHE, _compute,
                                                 clear_indicator_cache)
from tradingbacktester.finder.outcomes import Geometry, build_outcomes
from tradingbacktester.indicators.library import _recursive_smooth


def _reference(a: np.ndarray, alpha: float, seed_period: int) -> np.ndarray:
    """The recursion written the obvious way, as a Python loop.

    This is what ``_recursive_smooth`` used to be. It is kept here, in the
    tests, precisely so the fast version has something to be equal to.
    """
    n = len(a)
    out = np.full(n, np.nan)
    finite = np.flatnonzero(np.isfinite(a))
    if finite.size == 0:
        return out
    start = int(finite[0])
    if n - start < seed_period:
        return out
    seed_end = start + seed_period
    prev = float(np.mean(a[start:seed_end]))
    if not np.isfinite(prev):
        return out
    out[seed_end - 1] = prev
    beta = 1.0 - alpha
    for i in range(seed_end, n):
        prev = alpha * a[i] + beta * prev
        out[i] = prev
    return out


# --------------------------------------------------------------------------
# The IIR recursion
# --------------------------------------------------------------------------

@pytest.mark.parametrize("period", [2, 3, 7, 14, 20, 50, 100, 200, 400])
@pytest.mark.parametrize("kind", ["ema", "wilder"])
def test_the_vectorised_recursion_equals_the_loop(period, kind):
    """Block-wise or bar-by-bar, the answer has to be the same number."""
    rng = np.random.default_rng(3)
    a = 40000.0 + np.cumsum(rng.normal(scale=5.0, size=20000))
    alpha = (2.0 / (period + 1.0)) if kind == "ema" else (1.0 / period)
    fast = _recursive_smooth(a, alpha, period)
    slow = _reference(a, alpha, period)
    assert np.array_equal(np.isnan(fast), np.isnan(slow))
    both = ~np.isnan(fast)
    # Machine epsilon, not "close enough": the cumulative sum is dominated by
    # its newest term and multiplying back by beta**j returns the error.
    assert np.allclose(fast[both], slow[both], rtol=1e-12, atol=1e-6)


def test_leading_nan_is_skipped_the_same_way():
    """A composed indicator such as EMA(RSI) starts undefined."""
    rng = np.random.default_rng(5)
    a = np.concatenate([np.full(30, np.nan),
                        100.0 + np.cumsum(rng.normal(size=2000))])
    fast = _recursive_smooth(a, 2.0 / 15.0, 14)
    slow = _reference(a, 2.0 / 15.0, 14)
    assert np.array_equal(np.isnan(fast), np.isnan(slow))
    both = ~np.isnan(fast)
    assert np.allclose(fast[both], slow[both])


def test_a_nan_after_the_seed_poisons_the_rest_exactly_as_the_loop_did():
    """Once the recursion has seen a NaN it never recovers, either way."""
    a = np.full(500, 10.0)
    a[300] = np.nan
    fast = _recursive_smooth(a, 0.2, 14)
    slow = _reference(a, 0.2, 14)
    assert np.array_equal(np.isnan(fast), np.isnan(slow))
    assert np.isnan(fast[400])
    assert not np.isnan(fast[299])


@pytest.mark.parametrize("alpha", [1.0, 0.0])
def test_the_degenerate_alphas_do_not_divide_by_zero(alpha):
    """alpha=1 has no memory; alpha=0 never moves. Neither may raise."""
    a = np.arange(1.0, 501.0)
    out = _recursive_smooth(a, alpha, 10)
    assert np.isfinite(out[20:]).all()
    if alpha == 1.0:
        assert out[-1] == pytest.approx(a[-1])
    else:
        assert out[-1] == pytest.approx(float(np.mean(a[:10])))


def test_a_series_shorter_than_its_seed_is_all_undefined():
    assert np.isnan(_recursive_smooth(np.arange(5.0), 0.2, 20)).all()


def test_the_vectorised_recursion_is_actually_faster():
    """Not a benchmark -- a guard against silently reverting to the loop."""
    rng = np.random.default_rng(11)
    a = 40000.0 + np.cumsum(rng.normal(scale=5.0, size=200_000))
    t0 = time.perf_counter()
    _recursive_smooth(a, 2.0 / 51.0, 50)
    fast = time.perf_counter() - t0
    t0 = time.perf_counter()
    _reference(a, 2.0 / 51.0, 50)
    slow = time.perf_counter() - t0
    assert fast * 4 < slow, f"expected a clear speed-up, got {slow / fast:.1f}x"


# --------------------------------------------------------------------------
# The indicator cache
# --------------------------------------------------------------------------

def test_the_cache_returns_the_same_numbers():
    clear_indicator_cache()
    bars = generate_sample_data("NQ", "1h", n_bars=2000, seed=4)
    first = _compute(bars, "EMA", {"period": 50})["value"]
    second = _compute(bars, "EMA", {"period": 50})["value"]
    assert np.array_equal(first, second, equal_nan=True)


def test_the_cache_does_not_confuse_two_series():
    """Keyed on the series OBJECT, so a recycled id cannot serve stale data."""
    clear_indicator_cache()
    one = generate_sample_data("NQ", "1h", n_bars=2000, seed=1)
    two = generate_sample_data("NQ", "1h", n_bars=2000, seed=2)
    a = _compute(one, "EMA", {"period": 20})["value"].copy()
    b = _compute(two, "EMA", {"period": 20})["value"].copy()
    assert not np.allclose(a[100:], b[100:]), "two different series"
    assert np.array_equal(_compute(one, "EMA", {"period": 20})["value"], a,
                          equal_nan=True)


def test_different_parameters_are_different_entries():
    clear_indicator_cache()
    bars = generate_sample_data("NQ", "1h", n_bars=2000, seed=6)
    fast = _compute(bars, "EMA", {"period": 10})["value"]
    slow = _compute(bars, "EMA", {"period": 200})["value"]
    assert not np.allclose(fast[300:], slow[300:])


def test_the_cache_is_bounded():
    """An unbounded cache of half-million-point arrays is a leak with a name."""
    from tradingbacktester.finder.candidates import _CACHE_LIMIT

    clear_indicator_cache()
    bars = generate_sample_data("NQ", "1h", n_bars=600, seed=8)
    for period in range(2, _CACHE_LIMIT + 40):
        _compute(bars, "EMA", {"period": period})
    assert len(_INDICATOR_CACHE) <= _CACHE_LIMIT


def test_a_search_computes_each_indicator_once():
    """188 computations of 34 distinct things was 5.5x of wasted work."""
    from collections import Counter

    from tradingbacktester.finder.candidates import (all_candidates,
                                                     signals_for, warmup_for)
    from tradingbacktester.indicators import base

    clear_indicator_cache()
    bars = generate_sample_data("NQ", "30m", n_bars=3000, seed=12)
    calls: Counter = Counter()
    real = base.REGISTRY.compute

    def spy(key, b, params=None, source=None):
        calls[(key, tuple(sorted((params or {}).items())))] += 1
        return real(key, b, params, source)

    base.REGISTRY.compute = spy
    try:
        for candidate in all_candidates():
            signals_for(bars, candidate, warmup_for(candidate, 14))
    finally:
        base.REGISTRY.compute = real
    assert calls, "the spy saw nothing"
    assert max(calls.values()) == 1, "an indicator was computed twice"


# --------------------------------------------------------------------------
# Walking only the bars that can trade
# --------------------------------------------------------------------------

def test_restricting_the_walk_changes_nothing_it_still_walks():
    """A scalp style trades 9% of the bars; the other 91% are wasted work."""
    from tradingbacktester.finder.outcomes import session_entry_mask
    from tradingbacktester.finder.styles import style

    bars = generate_sample_data("NQ", "5m", n_bars=20000, seed=15)
    chosen = style("scalp")
    eligible = session_entry_mask(
        bars, bars.instrument.timezone, chosen.session[0], chosen.session[1],
        chosen.weekdays, chosen.flat_at_session_end)
    assert 0 < eligible.mean() < 0.5, "the fixture needs a real session filter"

    geometry = Geometry(1, 1.0, 2.0, chosen.max_bars, chosen.atr_period)
    full = build_outcomes(bars, geometry, CostModel(), detail=True)
    part = build_outcomes(bars, geometry, CostModel(), detail=True,
                          eligible=eligible)
    keep = eligible & full.valid
    assert int(keep.sum()) > 100
    for name in ("valid", "net_points", "net_cash", "exit_reason",
                 "bars_held", "entry_price", "stop_price", "target_price"):
        a = np.asarray(getattr(full, name))[keep]
        b = np.asarray(getattr(part, name))[keep]
        assert np.allclose(a, b, equal_nan=True), name


def test_nothing_outside_the_eligible_mask_is_marked_tradeable():
    from tradingbacktester.finder.outcomes import session_entry_mask
    from tradingbacktester.finder.styles import style

    bars = generate_sample_data("NQ", "5m", n_bars=20000, seed=16)
    chosen = style("scalp")
    eligible = session_entry_mask(
        bars, bars.instrument.timezone, chosen.session[0], chosen.session[1],
        chosen.weekdays, chosen.flat_at_session_end)
    cache = build_outcomes(bars, Geometry(-1, 1.0, 1.5, 12, 14), CostModel(),
                           eligible=eligible)
    assert not np.asarray(cache.valid)[~eligible].any()


def test_an_empty_eligible_mask_produces_an_empty_cache():
    bars = generate_sample_data("NQ", "5m", n_bars=2000, seed=17)
    cache = build_outcomes(bars, Geometry(1, 1.0, 2.0, 12, 14), CostModel(),
                           eligible=np.zeros(len(bars), dtype=bool))
    assert not np.asarray(cache.valid).any()
    assert len(cache) == len(bars)


# --------------------------------------------------------------------------
# The control population, summarised once
# --------------------------------------------------------------------------

def test_a_prebuilt_minute_table_gives_the_same_control():
    from tradingbacktester.finder.control import MinuteTable, analytic_control

    rng = np.random.default_rng(21)
    minutes = rng.integers(570, 690, size=5000).astype("int16")
    values = rng.normal(scale=40.0, size=5000)
    trade_minutes = minutes[:300]
    trade_values = values[:300] + 3.0

    without = analytic_control(minutes, values, trade_minutes, trade_values)
    table = MinuteTable.build(minutes, values)
    with_table = analytic_control(minutes, values, trade_minutes, trade_values,
                                  table=table)
    assert with_table.expected_per_trade == pytest.approx(
        without.expected_per_trade)
    assert with_table.excess_per_trade == pytest.approx(
        without.excess_per_trade)
    assert with_table.p_value == pytest.approx(without.p_value)


def test_an_empty_pool_is_still_an_empty_control():
    from tradingbacktester.finder.control import MinuteTable, analytic_control

    empty = np.zeros(0)
    table = MinuteTable.build(np.zeros(0, dtype="int16"), empty)
    out = analytic_control(empty, empty, np.array([600]), np.array([1.0]),
                           table=table)
    assert out.trades == 0
    assert out.p_value == 1.0
