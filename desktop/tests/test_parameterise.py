"""Naming a strategy's hard-coded numbers must not change what it trades.

That is the whole contract of :mod:`tradingbacktester.strategy.parameterise`:
the strategy that comes out is the strategy that went in, in a shape the
optimiser, walk-forward and the variant search can read.  Most of this file
exists to hold that line, because the failure mode is silent -- a rewritten
threshold trades differently and still looks like the same strategy in the UI.
"""

from __future__ import annotations

import pytest

from tradingbacktester.core.types import BacktestConfig, ExitSettings
from tradingbacktester.data.sample import generate_sample_data
from tradingbacktester.engine.backtester import Backtester
from tradingbacktester.finder.variants import axes_for
from tradingbacktester.indicators.base import REGISTRY
from tradingbacktester.strategy import builtin
from tradingbacktester.strategy.importer import import_strategy
from tradingbacktester.strategy.parameterise import (extract_parameters,
                                                     describe_extraction)
from tradingbacktester.strategy.spec import (Compare, ConstOperand,
                                             IndicatorOperand, ParamOperand,
                                             StrategySpec)

PINE = """//@version=5
strategy("Turtle", overlay = true)
atrN     = ta.atr(20)
entryHi  = ta.highest(high, 20)
exitLo   = ta.lowest(low, 10)
ema100   = ta.ema(close, 100)
[dp, dm, adxVal] = ta.dmi(14, 14)
adxOk = adxVal < 22.0
extOk = close - ema100 < 3.964 * atrN
longSignal = high > entryHi[1] and adxOk and extOk
if longSignal
    strategy.entry("L", strategy.long)
if low < exitLo[1]
    strategy.close("L")
"""


@pytest.fixture(scope="module")
def imported() -> StrategySpec:
    report = import_strategy(PINE, name_numbers=False)
    assert report.spec is not None, report.errors
    return report.spec


def _fingerprint(result):
    return [(t.entry_bar, t.exit_bar, str(t.side), round(float(t.net_pnl), 8),
             round(float(t.entry_price), 8), round(float(t.exit_price), 8))
            for t in result.trades]


# --------------------------------------------------------------------------
# the contract
# --------------------------------------------------------------------------

@pytest.mark.parametrize("symbol,timeframe,seed",
                         [("US100", "15m", 11), ("NQ", "1h", 4),
                          ("US30", "5m", 7)])
def test_extraction_does_not_change_a_single_trade(imported, symbol,
                                                   timeframe, seed):
    bars = generate_sample_data(symbol, timeframe, n_bars=3000, seed=seed)
    before = Backtester(bars, imported, BacktestConfig()).run()
    after = Backtester(bars, extract_parameters(imported).spec,
                       BacktestConfig()).run()
    assert before.trades, "the fixture must trade or this proves nothing"
    assert _fingerprint(before) == _fingerprint(after)


@pytest.mark.parametrize("factory", [
    builtin.donchian_breakout, builtin.macd_trend, builtin.ema_cross_rsi,
    builtin.rsi_mean_reversion, builtin.bollinger_breakout,
    builtin.supertrend_follower, builtin.opening_range_momentum,
])
def test_every_builtin_survives_extraction_unchanged(factory):
    bars = generate_sample_data("US100", "15m", n_bars=3000, seed=11)
    spec = factory()
    before = Backtester(bars, spec, BacktestConfig()).run()
    after = Backtester(bars, extract_parameters(spec).spec,
                       BacktestConfig()).run()
    assert _fingerprint(before) == _fingerprint(after)


def test_a_fully_parameterised_strategy_is_left_alone(imported):
    once = extract_parameters(imported)
    twice = extract_parameters(once.spec)
    assert not twice.changed, describe_extraction(twice)
    assert [p.name for p in twice.spec.params] == [p.name for p in once.spec.params]


# --------------------------------------------------------------------------
# what gets named, and what it is named after
# --------------------------------------------------------------------------

def test_indicator_periods_become_references(imported):
    spec = extract_parameters(imported).spec
    for slot in spec.indicators:
        for key, value in slot.params.items():
            assert isinstance(value, str) and value.startswith("$"), (
                f"{slot.ref}.{key} is still the literal {value!r}")
            spec.param(value[1:])          # raises if undeclared


def test_a_rule_threshold_becomes_a_parameter(imported):
    extraction = extract_parameters(imported)
    named = {p.name: p for p in extraction.added}
    level = next(p for p in named.values() if p.value == 22.0)
    assert "adx" in level.name
    assert "threshold" in level.where
    # No constant 22.0 may survive anywhere in the rules.
    assert "22" not in _consts(extraction.spec)


def _consts(spec: StrategySpec) -> set[str]:
    found: set[str] = set()

    def walk(node) -> None:
        if node is None:
            return
        if isinstance(node, ConstOperand):
            found.add(f"{node.value:g}")
        for attr in ("left", "right"):
            if hasattr(node, attr):
                walk(getattr(node, attr))
        for child in getattr(node, "children", []) or []:
            walk(child)

    for rule in (spec.entry_long, spec.entry_short, spec.exit_long,
                 spec.exit_short):
        walk(rule)
    return found


def test_bounds_come_from_the_registry_not_from_a_guess(imported):
    extraction = extract_parameters(imported)
    ema = next(s for s in imported.indicators if s.indicator == "EMA")
    period = next(p for p in extraction.added
                  if p.name == f"{ema.ref}_period")
    declared = REGISTRY.get("EMA").param_spec("period")
    assert period.minimum == float(declared.minimum)
    assert period.maximum == float(declared.maximum)
    assert "declares" in period.basis


def test_an_oscillator_threshold_gets_the_oscillator_scale(imported):
    level = next(p for p in extract_parameters(imported).added
                 if p.value == 22.0)
    assert (level.minimum, level.maximum) == (0.0, 100.0)
    assert "scale" in level.basis


def test_a_bare_multiplier_says_its_band_is_a_guess(imported):
    mult = next(p for p in extract_parameters(imported).added
                if abs(p.value - 3.964) < 1e-9)
    assert mult.minimum < 3.964 < mult.maximum
    assert "no declared range" in mult.basis, (
        "a band with no authority behind it must say so")


def test_every_default_sits_inside_its_own_bounds(imported):
    spec = extract_parameters(imported).spec
    spec.param_values()            # raises if any default is out of range
    for param in spec.params:
        assert param.minimum <= float(param.default) <= param.maximum


def test_a_zero_constant_is_refused_with_a_reason():
    spec = StrategySpec(name="zero")
    spec.indicators = [_slot("m", "MACD")]
    spec.entry_long = Compare(IndicatorOperand("m", "macd"), ">",
                              ConstOperand(0.0))
    extraction = extract_parameters(spec)
    assert any("zero has no proportional range" in s
               for s in extraction.skipped), extraction.skipped
    assert isinstance(extraction.spec.entry_long.right, ConstOperand)


def _slot(ref: str, indicator: str):
    from tradingbacktester.strategy.spec import IndicatorSlot

    return IndicatorSlot(ref=ref, indicator=indicator, params={})


def test_names_never_collide_with_existing_parameters():
    spec = builtin.ema_cross_rsi()
    taken = {p.name for p in spec.params}
    extraction = extract_parameters(spec)
    names = [p.name for p in extraction.spec.params]
    assert len(names) == len(set(names))
    assert taken <= set(names), "an existing parameter was renamed or dropped"


def test_switching_either_half_off_is_respected(imported):
    only_rules = extract_parameters(imported, indicators=False)
    assert all("threshold" in p.where or "multiplier" in p.where
               for p in only_rules.added)
    only_slots = extract_parameters(imported, thresholds=False)
    assert all("threshold" not in p.where and "multiplier" not in p.where
               for p in only_slots.added)


# --------------------------------------------------------------------------
# why this exists at all
# --------------------------------------------------------------------------

def test_extraction_is_what_makes_the_variant_search_possible(imported):
    assert axes_for(imported) == [], (
        "the fixture must start with nothing to search, or this proves nothing")
    assert len(axes_for(extract_parameters(imported).spec)) >= 5


def test_importing_names_the_numbers_by_default():
    named = import_strategy(PINE)
    literal = import_strategy(PINE, name_numbers=False)
    assert literal.spec.params == []
    assert len(named.spec.params) >= 8
    assert len(named.named) == len(named.spec.params)
    assert named.faithful and literal.faithful


def test_naming_on_import_does_not_change_the_trades():
    bars = generate_sample_data("US100", "15m", n_bars=3000, seed=11)
    named = Backtester(bars, import_strategy(PINE).spec, BacktestConfig()).run()
    literal = Backtester(bars, import_strategy(PINE, name_numbers=False).spec,
                         BacktestConfig()).run()
    assert _fingerprint(named) == _fingerprint(literal)


def test_the_description_never_promises_an_improvement(imported):
    text = describe_extraction(extract_parameters(imported)).lower()
    assert "trades exactly as before" in text
    for promise in ("will improve", "better performance", "more profitable"):
        assert promise not in text
