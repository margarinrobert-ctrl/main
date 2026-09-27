"""Compiling a declarative strategy into boolean signal arrays."""

from __future__ import annotations

import numpy as np
import pytest

from tradingbacktester.core.errors import StrategyError
from tradingbacktester.core.types import AssetClass
from tradingbacktester.data.models import Instrument
from tradingbacktester.indicators.base import ParamSpec
from tradingbacktester.strategy.compiler import compile_strategy
from tradingbacktester.strategy.spec import (Always, Compare, Const, Cross,
                                             ExprOperand, Group, Ind,
                                             IndicatorSlot, Param, Price,
                                             SessionWindow, State, StrategySpec)

from .conftest import make_bars


def fired(compiled) -> list[int]:
    """Bar indices where a signal fired."""
    return [int(i) for i in np.flatnonzero(compiled.entry_long)]


def expect_after_warmup(compiled, expected_mask) -> np.ndarray:
    """Blank an expected mask over the compiler's warm-up.

    The compiler refuses to signal until every indicator is defined and there is
    a previous bar for cross and state conditions to look at, so an expectation
    written from the raw series has to be masked the same way.
    """
    out = np.asarray(expected_mask, dtype=bool).copy()
    out[:compiled.warmup] = False
    return out


# --------------------------------------------------------------------------
# Cross semantics
# --------------------------------------------------------------------------

def test_cross_fires_once_per_crossing():
    """A cross is an event, not a state.

    close: 1 2 3 4 5 ... crosses 3 exactly once, on the bar it first exceeds it.
    """
    bars = make_bars([1.0, 2.0, 3.0, 4.0, 5.0, 4.0, 3.0, 2.0, 3.0, 4.0])
    spec = StrategySpec(name="X")
    spec.entry_long = Cross(Price("close"), "above", Const(3.0))
    spec.exit_long = Cross(Price("close"), "below", Const(3.0))
    compiled = compile_strategy(spec, bars)

    # close > 3 first at index 3 (4.0), having been == 3 at index 2.
    assert fired(compiled) == [3, 9]
    # close < 3 first at index 7 (2.0), having been == 3 at index 6.
    assert [int(i) for i in np.flatnonzero(compiled.exit_long)] == [7]


def test_cross_does_not_fire_on_a_touch():
    bars = make_bars([1.0, 3.0, 3.0, 3.0, 1.0])
    spec = StrategySpec(name="Touch")
    spec.entry_long = Cross(Price("close"), "above", Const(3.0))
    compiled = compile_strategy(spec, bars)
    assert not compiled.entry_long.any()


def test_cross_either_way():
    bars = make_bars([1.0, 5.0, 1.0, 5.0])
    spec = StrategySpec(name="Any")
    spec.entry_long = Cross(Price("close"), "any", Const(3.0))
    compiled = compile_strategy(spec, bars)
    # Bar 1 is inside the warm-up, so the first reportable cross is bar 2.
    assert fired(compiled) == [i for i in (1, 2, 3) if i >= compiled.warmup]


def test_cross_never_fires_across_a_nan_boundary():
    """An indicator's first defined bar must not read as a cross."""
    bars = make_bars(list(np.arange(100.0, 140.0)))
    spec = StrategySpec(name="NaN")
    spec.indicators = [IndicatorSlot("sma", "SMA", {"period": 10})]
    spec.entry_long = Cross(Price("close"), "above", Ind("sma"))
    compiled = compile_strategy(spec, bars)
    # The SMA is NaN until index 9; no signal may appear at index 9 merely
    # because the comparison became possible there.
    assert not compiled.entry_long[:10].any()


# --------------------------------------------------------------------------
# Operands
# --------------------------------------------------------------------------

def test_offset_looks_backwards_not_forwards():
    """offset=1 must mean the PREVIOUS bar."""
    bars = make_bars([1.0, 2.0, 3.0, 4.0, 5.0])
    spec = StrategySpec(name="Offset")
    # close[1] == 2 is true only on bar 2, where the previous close was 2.
    spec.entry_long = Compare(Price("close", offset=1), "==", Const(2.0))
    compiled = compile_strategy(spec, bars)
    assert fired(compiled) == [2]
    # And emphatically NOT bar 0, which is what a forward shift would give.
    assert not compiled.entry_long[0]


def test_arithmetic_operand():
    bars = make_bars([10.0, 10.0, 10.0], highs=[10.5, 10.05, 12.0],
                     lows=[9.0, 9.0, 9.0], opens=[10.0, 10.0, 10.0])
    spec = StrategySpec(name="Expr")
    spec.indicators = [IndicatorSlot("sma", "SMA", {"period": 1})]
    # high > sma * 1.1  ->  only the bar whose high is 12.
    spec.entry_long = Compare(Price("high"), ">",
                              ExprOperand("*", Ind("sma"), Const(1.1)))
    compiled = compile_strategy(spec, bars)
    assert fired(compiled) == [2]


def test_parameter_operand_is_resolved():
    bars = make_bars([1.0, 5.0, 9.0])
    spec = StrategySpec(name="Param")
    spec.params = [ParamSpec("level", "Level", "float", 4.0, 0.0, 100.0, 0.5)]
    spec.entry_long = Compare(Price("close"), ">", Param("level"))
    bars = make_bars([1.0, 1.0, 1.0, 5.0, 9.0])       # room for the warm-up
    assert int(compile_strategy(spec, bars).entry_long.sum()) == 2
    assert int(compile_strategy(spec, bars, {"level": 8.0}).entry_long.sum()) == 1


def test_indicator_parameter_reference_is_resolved():
    bars = make_bars(list(np.arange(100.0, 140.0)))
    spec = StrategySpec(name="Ref")
    spec.params = [ParamSpec("n", "N", "int", 5, 2, 50, 1)]
    spec.indicators = [IndicatorSlot("sma", "SMA", {"period": "$n"})]
    spec.entry_long = Compare(Price("close"), ">", Ind("sma"))
    short = compile_strategy(spec, bars, {"n": 5})
    long_ = compile_strategy(spec, bars, {"n": 30})
    assert np.isnan(short.indicators["sma"]["value"][:4]).all()
    assert np.isnan(long_.indicators["sma"]["value"][:29]).all()


def test_nan_makes_a_comparison_false_not_true():
    bars = make_bars(list(np.arange(100.0, 130.0)))
    spec = StrategySpec(name="NaN")
    spec.indicators = [IndicatorSlot("sma", "SMA", {"period": 20})]
    spec.entry_long = Compare(Ind("sma"), "<", Const(1e9))
    compiled = compile_strategy(spec, bars)
    assert not compiled.entry_long[:19].any()
    assert compiled.entry_long[compiled.warmup:].all()


# --------------------------------------------------------------------------
# Groups and states
# --------------------------------------------------------------------------

def test_and_or_and_not():
    bars = make_bars([1.0, 5.0, 9.0, 13.0])
    spec = StrategySpec(name="Logic")
    gt4 = Compare(Price("close"), ">", Const(4.0))
    lt10 = Compare(Price("close"), "<", Const(10.0))

    spec.entry_long = Group("AND", [gt4, lt10])
    compiled = compile_strategy(spec, bars)
    assert fired(compiled) == [i for i in (1, 2) if i >= compiled.warmup]

    spec.entry_long = Group("OR", [Compare(Price("close"), "<", Const(2.0)),
                                   Compare(Price("close"), ">", Const(12.0))])
    compiled = compile_strategy(spec, bars)
    assert fired(compiled) == [i for i in (0, 3) if i >= compiled.warmup]

    spec.entry_long = Group("AND", [gt4, lt10], negate=True)
    compiled = compile_strategy(spec, bars)
    assert fired(compiled) == [i for i in (0, 3) if i >= compiled.warmup]


def test_nested_groups():
    bars = make_bars([1.0, 5.0, 9.0, 13.0])
    spec = StrategySpec(name="Nested")
    spec.entry_long = Group("OR", [
        Group("AND", [Compare(Price("close"), ">", Const(4.0)),
                      Compare(Price("close"), "<", Const(6.0))]),
        Compare(Price("close"), ">", Const(12.0)),
    ])
    compiled = compile_strategy(spec, bars)
    assert fired(compiled) == [i for i in (1, 3) if i >= compiled.warmup]


def test_state_conditions():
    bars = make_bars([1.0, 2.0, 3.0, 2.0, 1.0, 4.0])
    spec = StrategySpec(name="State")
    spec.entry_long = State(Price("close"), "rising")
    compiled = compile_strategy(spec, bars)
    assert fired(compiled) == [i for i in (1, 2, 5) if i >= compiled.warmup]
    spec.entry_long = State(Price("close"), "falling")
    compiled = compile_strategy(spec, bars)
    assert fired(compiled) == [i for i in (3, 4) if i >= compiled.warmup]


def test_state_rising_for_n_bars():
    bars = make_bars([1.0, 2.0, 3.0, 4.0, 3.0])
    spec = StrategySpec(name="StateN")
    spec.entry_long = State(Price("close"), "increasing_for", 3)
    fired = list(np.flatnonzero(compile_strategy(spec, bars).entry_long))
    assert 3 in fired and 4 not in fired


def test_always_condition():
    bars = make_bars([1.0, 2.0, 3.0])
    spec = StrategySpec(name="Always")
    spec.entry_long = Always(True)
    compiled = compile_strategy(spec, bars)
    assert compiled.entry_long[compiled.warmup:].all()
    spec.entry_long = Always(False)
    assert not compile_strategy(spec, bars).entry_long.any()


# --------------------------------------------------------------------------
# Session filtering
# --------------------------------------------------------------------------

def test_session_window_selects_the_right_hours():
    """Hourly bars from midnight UTC; 14:30-16:00 New York is 19:30-21:00 UTC
    in January, so the 20:00 and 21:00 UTC bars fall inside a 15:00-16:00 window."""
    instrument = Instrument(symbol="TEST", timezone="America/New_York")
    bars = make_bars([100.0] * 48, instrument=instrument, timeframe="1h")
    spec = StrategySpec(name="Session")
    spec.entry_long = SessionWindow("10:00", "11:00", "America/New_York",
                                    (0, 1, 2, 3, 4, 5, 6))
    compiled = compile_strategy(spec, bars)

    import pandas as pd

    local = pd.DatetimeIndex(pd.to_datetime(bars.ts, utc=True)).tz_convert(
        "America/New_York")
    expected = np.array([10 <= t.hour <= 11 for t in local])
    assert np.array_equal(compiled.entry_long, expect_after_warmup(compiled, expected))


def test_session_window_wrapping_midnight():
    instrument = Instrument(symbol="TEST", timezone="UTC")
    bars = make_bars([100.0] * 48, instrument=instrument, timeframe="1h")
    spec = StrategySpec(name="Overnight")
    spec.entry_long = SessionWindow("22:00", "02:00", "UTC",
                                    (0, 1, 2, 3, 4, 5, 6))
    compiled = compile_strategy(spec, bars)
    import pandas as pd

    hours = pd.DatetimeIndex(pd.to_datetime(bars.ts, utc=True)).hour
    expected = (hours >= 22) | (hours <= 2)
    assert np.array_equal(compiled.entry_long,
                          expect_after_warmup(compiled, np.asarray(expected)))


def test_session_window_weekday_filter():
    instrument = Instrument(symbol="TEST", timezone="UTC")
    bars = make_bars([100.0] * (24 * 9), instrument=instrument, timeframe="1h")
    spec = StrategySpec(name="Weekday")
    spec.entry_long = SessionWindow("00:00", "23:59", "UTC", (0,))   # Monday only
    compiled = compile_strategy(spec, bars)
    import pandas as pd

    weekday = pd.DatetimeIndex(pd.to_datetime(bars.ts, utc=True)).weekday
    assert np.array_equal(compiled.entry_long,
                          expect_after_warmup(compiled, np.asarray(weekday == 0)))


def test_unknown_timezone_is_reported_clearly():
    bars = make_bars([100.0] * 24, timeframe="1h")
    spec = StrategySpec(name="BadTz")
    spec.entry_long = SessionWindow("09:00", "10:00", "Mars/Olympus_Mons")
    with pytest.raises(StrategyError):
        compile_strategy(spec, bars)


# --------------------------------------------------------------------------
# Compilation behaviour
# --------------------------------------------------------------------------

def test_signals_are_boolean_and_correctly_shaped(random_bars):
    spec = StrategySpec(name="Shape")
    spec.indicators = [IndicatorSlot("sma", "SMA", {"period": 20})]
    spec.entry_long = Compare(Price("close"), ">", Ind("sma"))
    spec.exit_long = Compare(Price("close"), "<", Ind("sma"))
    compiled = compile_strategy(spec, random_bars)
    for name in ("entry_long", "exit_long", "tradeable"):
        array = getattr(compiled, name)
        assert array.dtype == np.bool_, name
        assert array.shape == (len(random_bars),), name


def test_nothing_fires_before_the_warmup(random_bars):
    spec = StrategySpec(name="Warm")
    spec.indicators = [IndicatorSlot("sma", "SMA", {"period": 50})]
    spec.entry_long = Compare(Price("close"), ">", Ind("sma"))
    compiled = compile_strategy(spec, random_bars)
    assert compiled.warmup >= 50
    assert not compiled.entry_long[:compiled.warmup].any()


def test_compilation_is_free_of_look_ahead(random_bars):
    """Truncating the bars must not change any earlier signal."""
    spec = StrategySpec(name="Look")
    spec.indicators = [IndicatorSlot("fast", "EMA", {"period": 10}),
                       IndicatorSlot("slow", "EMA", {"period": 30}),
                       IndicatorSlot("rsi", "RSI", {"period": 14})]
    spec.entry_long = Group("AND", [Cross(Ind("fast"), "above", Ind("slow")),
                                    Compare(Ind("rsi"), ">", Const(50))])
    spec.exit_long = Cross(Ind("fast"), "below", Ind("slow"))

    cut = 350
    full = compile_strategy(spec, random_bars)
    part = compile_strategy(spec, random_bars.slice(0, cut))
    assert np.array_equal(full.entry_long[:cut], part.entry_long)
    assert np.array_equal(full.exit_long[:cut], part.exit_long)
    assert np.allclose(full.atr[:cut], part.atr, equal_nan=True)


def test_an_indicator_used_twice_is_computed_once(random_bars):
    spec = StrategySpec(name="Once")
    spec.indicators = [IndicatorSlot("sma", "SMA", {"period": 20})]
    spec.entry_long = Group("AND", [Compare(Price("close"), ">", Ind("sma")),
                                    Compare(Price("open"), ">", Ind("sma"))])
    compiled = compile_strategy(spec, random_bars)
    assert set(compiled.indicators) == {"sma"}


def test_a_broken_indicator_names_the_slot(random_bars):
    spec = StrategySpec(name="Broken")
    spec.indicators = [IndicatorSlot("thing", "NOT_AN_INDICATOR", {})]
    spec.entry_long = Compare(Price("close"), ">", Ind("thing"))
    with pytest.raises(StrategyError):
        compile_strategy(spec, random_bars)


def test_builtin_strategies_all_compile(random_bars):
    from tradingbacktester.strategy.builtin import BUILTIN_STRATEGIES

    assert len(BUILTIN_STRATEGIES) >= 6
    for name, factory in BUILTIN_STRATEGIES.items():
        spec = factory()
        spec.validate()
        compiled = compile_strategy(spec, random_bars)
        assert compiled.entry_long.dtype == np.bool_, name
        assert not compiled.entry_long[:compiled.warmup].any(), name


def test_the_worked_example_is_a_builtin():
    from tradingbacktester.strategy.builtin import BUILTIN_STRATEGIES

    key = next((k for k in BUILTIN_STRATEGIES
                if "EMA" in k.upper() and "RSI" in k.upper()), None)
    assert key, f"expected an EMA/RSI builtin, got {list(BUILTIN_STRATEGIES)}"
    spec = BUILTIN_STRATEGIES[key]()
    described = spec.entry_long.describe().lower()
    assert "crosses above" in described
    assert "rsi" in described
    assert spec.exits.stop_loss_enabled and spec.exits.take_profit_enabled


# --------------------------------------------------------------------------
# Caches across compiles
# --------------------------------------------------------------------------

def _trend_spec() -> StrategySpec:
    spec = StrategySpec(
        name="cache",
        indicators=[IndicatorSlot("fast", "EMA", {"period": 5}),
                    IndicatorSlot("slow", "EMA", {"period": 20})],
        entry_long=Cross(Ind("fast"), "above", Ind("slow")))
    spec.session.enabled = True
    spec.session.start, spec.session.end = "09:30", "16:00"
    spec.session.timezone = "America/New_York"
    return spec


def test_a_cached_compile_is_identical_to_a_fresh_one():
    from tradingbacktester.strategy import compiler, rules

    bars = make_bars(np.cumsum(np.random.default_rng(1).normal(0, 1, 600)) + 100,
                     timeframe="1h")
    spec = _trend_spec()
    compiler.clear_indicator_cache()
    rules.clear_session_cache()
    first = compile_strategy(spec, bars)
    assert len(compiler._INDICATOR_CACHE) > 0
    assert len(rules._LOCAL_PARTS_CACHE) == 1
    second = compile_strategy(spec, bars)
    assert np.array_equal(first.entry_long, second.entry_long)
    assert np.array_equal(first.tradeable, second.tradeable)
    for ref in ("fast", "slow"):
        assert np.array_equal(first.indicators[ref]["value"],
                              second.indicators[ref]["value"], equal_nan=True)


def test_cached_indicator_arrays_are_read_only():
    from tradingbacktester.strategy import compiler

    bars = make_bars(np.cumsum(np.random.default_rng(2).normal(0, 1, 300)) + 100,
                     timeframe="1h")
    compiler.clear_indicator_cache()
    compiled = compile_strategy(_trend_spec(), bars)
    values = compiled.indicators["fast"]["value"]
    with pytest.raises(ValueError):
        values[0] = 1.0


def test_the_indicator_cache_tells_two_datasets_apart_by_price_not_just_time():
    """Same stamps, different closes: the second must not read the first."""
    from tradingbacktester.strategy import compiler

    rng = np.random.default_rng(3)
    a = make_bars(np.cumsum(rng.normal(0, 1, 400)) + 100, timeframe="1h")
    b = make_bars(np.cumsum(rng.normal(0, 1, 400)) + 100, timeframe="1h")
    assert np.array_equal(a.ts, b.ts)
    compiler.clear_indicator_cache()
    ca = compile_strategy(_trend_spec(), a)
    cb = compile_strategy(_trend_spec(), b)
    assert not np.array_equal(ca.indicators["fast"]["value"],
                              cb.indicators["fast"]["value"])


def test_the_session_cache_is_bounded():
    from tradingbacktester.strategy import rules

    rules.clear_session_cache()
    for i in range(rules._LOCAL_PARTS_LIMIT + 5):
        ts = np.arange(50, dtype="int64") * 3_600_000_000_000 + i * 7
        rules.session_mask(ts, "09:30", "16:00", "UTC")
    assert len(rules._LOCAL_PARTS_CACHE) == rules._LOCAL_PARTS_LIMIT


# --------------------------------------------------------------------------
# Within: "it happened in the last N bars"
# --------------------------------------------------------------------------

def _within_bars():
    close = np.array([10, 10, 30, 10, 10, 10, 10, 10, 10, 10, 30, 10.0])
    return make_bars(close, timeframe="1h")


def test_within_is_the_rolling_or_of_its_child():
    from tradingbacktester.strategy.spec import Within

    bars = _within_bars()
    spike = Compare(Price("close"), ">", Const(20.0))
    spec = StrategySpec(name="w", indicators=[], entry_long=Within(spike, 3))
    compiled = compile_strategy(spec, bars)
    # Spikes at bars 2 and 10; a 3-bar window covers the spike bar and the two after.
    expected = np.zeros(12, dtype=bool)
    expected[[2, 3, 4, 10, 11]] = True
    assert np.array_equal(compiled.entry_long,
                          expect_after_warmup(compiled, expected))


def test_within_equals_the_expanded_or_it_replaces():
    from tradingbacktester.strategy.spec import Within

    bars = make_bars(np.cumsum(np.random.default_rng(5).normal(0, 1, 500)) + 100,
                     timeframe="1h")
    slots = [IndicatorSlot("rsi", "RSI", {"period": 14})]
    child = Compare(Ind("rsi"), "<", Const(35.0))
    expanded = Group("or", [Compare(Ind("rsi", offset=k), "<", Const(35.0))
                            for k in range(8)])
    a = compile_strategy(StrategySpec(name="a", indicators=slots,
                                      entry_long=expanded), bars)
    b = compile_strategy(StrategySpec(name="b", indicators=slots,
                                      entry_long=Within(child, 8)), bars)
    assert np.array_equal(a.entry_long, b.entry_long)
    assert a.entry_long.any()


def test_within_can_be_negated_and_describes_itself():
    from tradingbacktester.strategy.spec import Within

    bars = _within_bars()
    spike = Compare(Price("close"), ">", Const(20.0))
    spec = StrategySpec(name="w", indicators=[],
                        entry_long=Within(spike, 3, negate=True))
    compiled = compile_strategy(spec, bars)
    expected = np.ones(12, dtype=bool)
    expected[[2, 3, 4, 10, 11]] = False
    assert np.array_equal(compiled.entry_long,
                          expect_after_warmup(compiled, expected))
    assert Within(spike, 3).describe() == "(Close > 20) within the last 3 bars"
    assert Within(spike, 3, negate=True).describe().startswith("NOT ")


def test_within_refuses_an_empty_window():
    from tradingbacktester.strategy.spec import Within

    spec = StrategySpec(name="w", indicators=[],
                        entry_long=Within(Compare(Price("close"), ">", Const(1.0)), 0))
    with pytest.raises(StrategyError):
        compile_strategy(spec, _within_bars())


def test_within_survives_a_json_round_trip_and_is_walked():
    import json

    from tradingbacktester.strategy.spec import Within, walk_conditions

    child = Compare(Ind("rsi"), "<", Const(30.0))
    spec = StrategySpec(name="w", indicators=[IndicatorSlot("rsi", "RSI", {"period": 14})],
                        entry_long=Group("and", [Within(child, 8),
                                                 Cross(Ind("rsi"), "above", Const(30.0))]))
    back = StrategySpec.from_dict(json.loads(json.dumps(spec.to_dict())))
    assert back.entry_long.to_dict() == spec.entry_long.to_dict()
    kinds = [type(n).__name__ for n in walk_conditions(back.entry_long)]
    assert kinds.count("Within") == 1 and "Compare" in kinds
    assert back.entry_long.referenced_indicators() == {"rsi"}


def test_parameter_extraction_reaches_inside_a_within():
    from tradingbacktester.strategy.parameterise import extract_parameters
    from tradingbacktester.strategy.spec import Within

    spec = StrategySpec(name="w", indicators=[IndicatorSlot("rsi", "RSI", {"period": 14})],
                        entry_long=Within(Compare(Ind("rsi"), "<", Const(30.0)), 8))
    extraction = extract_parameters(spec)
    names = {p.name for p in extraction.spec.params}
    assert names, "the literal inside the Within should have become a parameter"
    inner = extraction.spec.entry_long.child
    assert inner.right.to_dict()["kind"] == "param"
