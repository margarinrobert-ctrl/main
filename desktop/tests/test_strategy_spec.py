"""The declarative strategy definition and its JSON round trip."""

from __future__ import annotations

import json

import pytest

from tradingbacktester.core.errors import ParameterError, StrategyError
from tradingbacktester.indicators.base import ParamSpec
from tradingbacktester.strategy.spec import (Always, Compare, ConditionGroup,
                                             Const, Cross, ExprOperand, Group,
                                             Ind, IndicatorSlot, Param, Price,
                                             SessionWindow, State,
                                             StrategySpec)


def worked_example() -> StrategySpec:
    """The strategy from the specification, built by hand.

        LONG ENTRY:  EMA 20 crosses above EMA 50 AND RSI > 50
        LONG EXIT:   EMA 20 crosses below EMA 50
        Stop 1.5 x ATR, target 3 x ATR
    """
    spec = StrategySpec(name="EMA Cross + RSI")
    spec.params = [
        ParamSpec("ema_fast", "EMA Fast", "int", 20, 2, 400, 1),
        ParamSpec("ema_slow", "EMA Slow", "int", 50, 3, 800, 1),
        ParamSpec("rsi_period", "RSI Length", "int", 14, 2, 200, 1),
        ParamSpec("rsi_level", "RSI Entry Level", "float", 50.0, 0.0, 100.0, 1.0),
    ]
    spec.indicators = [
        IndicatorSlot("emaFast", "EMA", {"period": "$ema_fast"}),
        IndicatorSlot("emaSlow", "EMA", {"period": "$ema_slow"}),
        IndicatorSlot("rsi", "RSI", {"period": "$rsi_period"}, panel="sub"),
    ]
    spec.entry_long = Group("AND", [
        Cross(Ind("emaFast"), "above", Ind("emaSlow")),
        Compare(Ind("rsi"), ">", Param("rsi_level")),
    ])
    spec.exit_long = Cross(Ind("emaFast"), "below", Ind("emaSlow"))
    spec.exits.stop_loss_enabled = True
    spec.exits.stop_loss_mode = "atr"
    spec.exits.stop_loss_value = 1.5
    spec.exits.take_profit_enabled = True
    spec.exits.take_profit_mode = "atr"
    spec.exits.take_profit_value = 3.0
    return spec


def test_worked_example_validates():
    spec = worked_example()
    warnings = spec.validate()
    assert isinstance(warnings, list)


def test_worked_example_reads_back_in_english():
    spec = worked_example()
    assert spec.entry_long.describe() == \
        "emaFast crosses above emaSlow AND rsi > $rsi_level"
    assert spec.exit_long.describe() == "emaFast crosses below emaSlow"


def test_json_round_trip_is_lossless():
    spec = worked_example()
    text = spec.to_json()
    restored = StrategySpec.from_json(text)
    assert restored.to_json() == text
    assert restored.entry_long.describe() == spec.entry_long.describe()
    assert restored.exits.stop_loss_value == 1.5


def test_round_trip_preserves_every_condition_kind():
    spec = StrategySpec(name="All kinds")
    spec.params = [ParamSpec("level", "Level", "float", 1.0, 0.0, 10.0, 0.1)]
    spec.indicators = [IndicatorSlot("ema", "EMA", {"period": 10}),
                       IndicatorSlot("rsi", "RSI", {"period": 14})]
    spec.entry_long = Group("OR", [
        Compare(Price("close"), ">", Const(100)),
        Cross(Ind("ema"), "below", Price("close", offset=1)),
        State(Ind("rsi"), "rising", 3),
        SessionWindow("09:30", "16:00", "America/New_York", (0, 1, 2, 3, 4)),
        Always(True),
        Group("AND", [Compare(
            ExprOperand("*", Ind("ema"), Const(1.01)), "<", Price("high"))],
            negate=True),
    ])
    restored = StrategySpec.from_json(spec.to_json())
    assert restored.entry_long.describe() == spec.entry_long.describe()


def test_parameter_defaults_and_overrides():
    spec = worked_example()
    assert spec.param_values()["ema_fast"] == 20
    assert spec.param_values({"ema_fast": 10})["ema_fast"] == 10


def test_unknown_parameter_override_is_rejected():
    spec = worked_example()
    with pytest.raises(ParameterError):
        spec.param_values({"not_a_parameter": 1})


def test_out_of_range_parameter_is_rejected():
    spec = worked_example()
    with pytest.raises(ParameterError):
        spec.param_values({"rsi_level": 500.0})


def test_rule_referring_to_a_missing_indicator_is_rejected():
    spec = worked_example()
    spec.entry_long = Compare(Ind("doesNotExist"), ">", Const(1))
    with pytest.raises(StrategyError) as exc:
        spec.validate()
    assert "doesNotExist" in str(exc.value)


def test_duplicate_indicator_reference_is_rejected():
    spec = worked_example()
    spec.indicators.append(IndicatorSlot("emaFast", "SMA", {"period": 5}))
    with pytest.raises(StrategyError):
        spec.validate()


def test_indicator_parameter_referring_to_a_missing_strategy_parameter():
    spec = worked_example()
    spec.indicators[0].params["period"] = "$nope"
    with pytest.raises(StrategyError):
        spec.validate()


def test_strategy_with_no_entry_rule_is_rejected():
    spec = StrategySpec(name="Empty")
    with pytest.raises(StrategyError):
        spec.validate()


def test_partial_exits_cannot_exceed_the_whole_position():
    spec = worked_example()
    spec.exits.partial_exits = ((0.6, 1.0), (0.6, 2.0))
    with pytest.raises(StrategyError):
        spec.validate()


def test_unused_indicator_is_a_warning_not_an_error():
    spec = worked_example()
    spec.indicators.append(IndicatorSlot("unused", "SMA", {"period": 5}))
    warnings = spec.validate()
    assert any("unused" in w for w in warnings)


def test_warmup_bars_follows_the_longest_period():
    spec = worked_example()
    assert spec.warmup_bars() >= 50
    assert spec.warmup_bars({"ema_slow": 200}) >= 200


def test_copy_gets_a_new_id_and_keeps_the_rules():
    spec = worked_example()
    copy = spec.copy("Copy of it")
    assert copy.id != spec.id
    assert copy.name == "Copy of it"
    assert copy.entry_long.describe() == spec.entry_long.describe()


def test_corrupt_json_is_reported_not_crashed():
    with pytest.raises(StrategyError):
        StrategySpec.from_json("{not json")
    with pytest.raises(StrategyError):
        StrategySpec.from_json('{"schema_version": 9999}')
    with pytest.raises(StrategyError):
        StrategySpec.from_json('["a list, not an object"]')


def test_unknown_condition_kind_is_reported():
    data = json.loads(worked_example().to_json())
    data["entry_long"] = {"kind": "telepathy"}
    with pytest.raises(StrategyError):
        StrategySpec.from_dict(data)


def test_summary_lines_cover_the_rules_and_exits():
    lines = worked_example().summary_lines()
    joined = "\n".join(lines)
    assert "Long entry" in joined
    assert "Stop loss" in joined
    assert "Take profit" in joined
