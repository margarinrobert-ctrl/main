"""Windows over recent bars: within / held-for / at-least-K, in bars or minutes,
sized by a number or by a strategy parameter; and indicators of indicators."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from tradingbacktester.core.errors import StrategyError
from tradingbacktester.data.sample import generate_sample_data
from tradingbacktester.indicators.base import ParamSpec
from tradingbacktester.strategy.compiler import compile_strategy
from tradingbacktester.strategy.expression import EvalContext
from tradingbacktester.strategy.rules import evaluate_condition
from tradingbacktester.strategy.spec import (SCHEMA_VERSION, Compare, Const,
                                             Cross, Ind, IndicatorSlot, Price,
                                             StrategySpec, Within)

from .conftest import make_bars


def _ctx(flags, minutes_apart=1, gaps=(), params=None):
    """Bars whose close is 1 where ``flags`` is true, else 0."""
    close = np.asarray(flags, dtype="float64")
    bars = make_bars(close + 100.0, timeframe="1m")
    step = np.full(close.size, minutes_apart * 60_000_000_000, dtype="int64")
    for g in gaps:
        step[g] += 30 * 60_000_000_000
    step[0] = 0
    bars.ts = (1_780_000_000_000_000_000 + np.cumsum(step)).astype("int64")
    return EvalContext(bars=bars, params=dict(params or {}))


FLAG = Compare(Price("close"), ">", Const(100.5))


def _eval(cond, ctx):
    return evaluate_condition(cond, ctx).tolist()


def test_any_in_bars_is_unchanged():
    flags = [0, 1, 0, 0, 0, 0, 1, 0]
    got = _eval(Within(FLAG, 3), _ctx(flags))
    assert got == [False, True, True, True, False, False, True, True]


def test_any_in_minutes_is_time_not_bar_count():
    flags = [0, 1, 0, 0, 0, 0]
    # 5-minute bars: "within 7 minutes" reaches back to bars opened at most 7
    # minutes ago -- this bar and the one before.
    got = _eval(Within(FLAG, 7, unit="minutes"), _ctx(flags, minutes_apart=5))
    assert got == [False, True, True, False, False, False]
    # A 30-minute gap before bar 2: the flag at bar 1 is 35 minutes old there.
    got = _eval(Within(FLAG, 10, unit="minutes"), _ctx(flags, gaps=(2,)))
    assert got == [False, True, False, False, False, False]


def test_held_for_every_bar_and_not_before_a_full_window():
    flags = [1, 1, 1, 0, 1, 1, 1, 1]
    got = _eval(Within(FLAG, 3, mode="all"), _ctx(flags))
    assert got == [False, False, True, False, False, False, True, True]
    # Two minutes of 1-minute bars is two bars, the same as a 2-bar window.
    got = _eval(Within(FLAG, 2, unit="minutes", mode="all"), _ctx(flags))
    assert got == _eval(Within(FLAG, 2, mode="all"), _ctx(flags))
    assert got == [False, True, True, False, False, True, True, True]


def test_minutes_mean_the_same_clock_time_on_any_chart():
    rng = np.random.default_rng(7)
    fine = rng.random(600) < 0.2                     # 1-minute flags
    coarse = fine.reshape(-1, 5).any(axis=1)         # the same, on 5-minute bars
    for mode in ("any", "all", "count"):
        one = _eval(Within(FLAG, 30, unit="minutes", mode=mode, count=2),
                    _ctx(coarse, minutes_apart=5))
        six = _eval(Within(FLAG, 6, mode=mode, count=2), _ctx(coarse, minutes_apart=5))
        assert one == six, mode                      # 30 minutes = six 5-minute bars


def test_held_is_not_assumed_across_a_session_break():
    flags = [1, 1, 1, 1, 1, 1]
    # 1-minute bars with a 30-minute break before bar 3: "held for 3 minutes"
    # cannot be true on bar 3 or 4 -- the minutes before them were not traded.
    got = _eval(Within(FLAG, 3, unit="minutes", mode="all"), _ctx(flags, gaps=(3,)))
    assert got == [False, False, True, False, False, True]
    # "any" and "count" count the bars that did trade in the window.
    got = _eval(Within(FLAG, 3, unit="minutes"), _ctx(flags, gaps=(3,)))
    assert got == [True] * 6


def test_at_least_k_times():
    flags = [1, 0, 1, 0, 0, 1, 0, 0, 0, 0]
    got = _eval(Within(FLAG, 4, mode="count", count=2), _ctx(flags))
    expect = [sum(flags[max(0, i - 3):i + 1]) >= 2 for i in range(len(flags))]
    assert got == expect


def test_a_parameter_sizes_the_window_and_negation_applies_last():
    flags = [0, 1, 0, 0, 0, 0, 0, 0]
    cond = Within(FLAG, "$win")
    assert _eval(cond, _ctx(flags, params={"win": 2})) == [
        False, True, True, False, False, False, False, False]
    assert _eval(cond, _ctx(flags, params={"win": 5})) == [
        False, True, True, True, True, True, False, False]
    neg = Within(FLAG, "$win", negate=True, mode="all")
    assert _eval(neg, _ctx([1, 1, 1], params={"win": 2})) == [True, False, False]
    with pytest.raises(StrategyError):
        _eval(Within(FLAG, "$nope"), _ctx(flags))


# --------------------------------------------------------------------------
# The strategy file
# --------------------------------------------------------------------------

def _spec(cond, params=()):
    return StrategySpec(name="w", params=list(params),
                        indicators=[IndicatorSlot("f", "EMA", {"period": 13}, "close"),
                                    IndicatorSlot("s", "EMA", {"period": 48}, "close")],
                        entry_long=cond)


def test_plain_windows_stay_format_one_and_new_ones_are_format_three():
    plain = _spec(Within(Cross(Ind("f"), "above", Ind("s")), 5)).to_dict()
    assert plain["schema_version"] == 1
    assert set(plain["entry_long"]) == {"kind", "bars", "child", "negate"}
    for cond, params in ((Within(FLAG, 7, unit="minutes"), ()),
                         (Within(FLAG, 3, mode="all"), ()),
                         (Within(FLAG, "$w"), (ParamSpec("w", "W", "int", 5, 1, 50, 1),))):
        d = _spec(cond, params).to_dict()
        assert d["schema_version"] == 3 <= SCHEMA_VERSION
        back = StrategySpec.from_dict(json.loads(json.dumps(d)))
        assert back.entry_long.to_dict() == cond.to_dict()


def test_validation_names_the_problem():
    with pytest.raises(StrategyError) as exc:
        _spec(Within(FLAG, "$missing")).validate()
    assert "missing" in str(exc.value)
    with pytest.raises(StrategyError):
        _spec(Within(FLAG, 5, unit="hours")).validate()
    with pytest.raises(StrategyError):
        _spec(Within(FLAG, 0)).validate()


def test_extracting_parameters_names_the_window():
    from tradingbacktester.strategy.parameterise import extract_parameters
    spec = _spec(Within(Cross(Ind("f"), "above", Ind("s")), 5, unit="minutes"))
    out = extract_parameters(spec).spec
    window = out.entry_long.bars
    assert isinstance(window, str) and window.startswith("$window_minutes")
    param = next(p for p in out.params if p.name == window[1:])
    assert (param.kind, param.default) == ("int", 5)
    bars = generate_sample_data("NQ", "5m", n_bars=1500, seed=2)
    assert np.array_equal(compile_strategy(spec, bars).entry_long,
                          compile_strategy(out, bars).entry_long)


def test_the_optimiser_can_sweep_a_window():
    from tradingbacktester.core.types import BacktestConfig
    from tradingbacktester.optimize.grid import ParameterRange
    from tradingbacktester.optimize.runner import OptimizationRunner
    spec = _spec(Within(Cross(Ind("f"), "above", Ind("s")), "$win"),
                 (ParamSpec("win", "Window", "int", 5, 1, 60, 1),))
    spec.exits.stop_loss_enabled = True
    bars = generate_sample_data("NQ", "5m", n_bars=3000, seed=5)
    results = OptimizationRunner(bars, spec, BacktestConfig(), max_workers=1).run(
        [ParameterRange("win", 1, 41, 20)])
    counts = [r.trade_count for r in results.rows]
    assert len(counts) == 3 and len(set(counts)) > 1, counts


# --------------------------------------------------------------------------
# Indicators of indicators
# --------------------------------------------------------------------------

def _ema_sma_seeded(x, n):
    out = np.full(x.size, np.nan)
    k = int(np.flatnonzero(np.isfinite(x))[0])
    y = x[k:]
    a = 2.0 / (n + 1.0)
    e = y[:n].mean()
    out[k + n - 1] = e
    for j in range(n, y.size):
        e = a * y[j] + (1 - a) * e
        out[k + j] = e
    return out


def test_an_ema_of_an_ema_is_an_ema_applied_twice():
    bars = generate_sample_data("NQ", "5m", n_bars=2000, seed=4)
    spec = StrategySpec(name="c", indicators=[
        IndicatorSlot("f", "EMA", {"period": 13}, "close"),
        IndicatorSlot("ff", "EMA", {"period": 10}, "@f")],
        entry_long=Cross(Ind("f"), "above", Ind("ff")))
    assert spec.validate() == [] or all("no rule" not in w for w in spec.validate())
    compiled = compile_strategy(spec, bars)
    f = np.asarray(compiled.indicators["f"]["value"])
    ff = np.asarray(compiled.indicators["ff"]["value"])
    ref = _ema_sma_seeded(f, 10)
    assert np.allclose(ff, ref, equal_nan=True, atol=1e-8)
    assert int(np.flatnonzero(np.isfinite(ff))[0]) == 12 + 9
    assert spec.to_dict()["schema_version"] == 3


def test_an_indicator_used_only_as_a_source_is_not_called_unused():
    spec = StrategySpec(name="c", indicators=[
        IndicatorSlot("f", "EMA", {"period": 13}, "close"),
        IndicatorSlot("ff", "EMA", {"period": 10}, "@f.value")],
        entry_long=Compare(Price("close"), ">", Ind("ff")))
    assert not any("no rule uses" in w for w in spec.validate())


def test_chaining_must_point_upwards_and_at_a_single_source_indicator():
    forward = StrategySpec(name="c", indicators=[
        IndicatorSlot("ff", "EMA", {"period": 10}, "@f"),
        IndicatorSlot("f", "EMA", {"period": 13}, "close")],
        entry_long=Compare(Price("close"), ">", Ind("ff")))
    with pytest.raises(StrategyError):
        forward.validate()
    atr = StrategySpec(name="c", indicators=[
        IndicatorSlot("f", "EMA", {"period": 13}, "close"),
        IndicatorSlot("a", "ATR", {"period": 14}, "@f")],
        entry_long=Compare(Ind("a"), ">", Const(0)))
    with pytest.raises(StrategyError) as exc:
        compile_strategy(atr, generate_sample_data("NQ", "5m", n_bars=500, seed=1))
    assert "cannot be computed on another indicator" in str(exc.value)


# --------------------------------------------------------------------------
# The editor
# --------------------------------------------------------------------------

def test_the_editor_builds_and_parameterises_windows(qapp):
    from tradingbacktester.ui.dialogs.strategy_editor import (StrategyEditor,
                                                              _ConditionPicker,
                                                              _node_title,
                                                              _WithinEditor)
    spec = _spec(Within(FLAG, 5))
    editor = StrategyEditor(spec)
    picker = _ConditionPicker(editor)
    picker.kind_box.setCurrentIndex(picker.kind_box.findData("within_cross"))
    picker._accept()
    assert isinstance(picker.condition, Within)
    assert isinstance(picker.condition.child, Cross)

    from tradingbacktester.strategy.spec import walk_conditions
    node = next(n for n in walk_conditions(editor.spec.entry_long)
                if isinstance(n, Within))
    panel = _WithinEditor(editor, node)
    panel.unit.setCurrentIndex(panel.unit.findData("minutes"))
    panel.size.setValue(7)
    panel.as_param.setChecked(True)
    assert node.unit == "minutes" and node.bars == "$window_minutes"
    param = next(p for p in editor.spec.params if p.name == "window_minutes")
    assert param.default == 7
    panel.size.setValue(9)
    param = next(p for p in editor.spec.params if p.name == "window_minutes")
    assert param.default == 9 and node.bars == "$window_minutes"
    panel.mode.setCurrentIndex(panel.mode.findData("all"))
    assert _node_title(node) == "HELD for the last {window_minutes} minutes"
    editor.spec.validate()
    editor.close()


def test_the_editor_offers_indicators_as_sources_and_renames_follow(qapp):
    from tradingbacktester.ui.dialogs.strategy_editor import StrategyEditor
    spec = StrategySpec(name="c", indicators=[
        IndicatorSlot("f", "EMA", {"period": 13}, "close"),
        IndicatorSlot("ff", "EMA", {"period": 10}, "@f")],
        entry_long=Compare(Price("close"), ">", Ind("ff")))
    editor = StrategyEditor(spec)
    editor._rename_slot(0, "fast")
    assert editor.spec.indicators[1].source == "@fast"
    editor.close()


# --------------------------------------------------------------------------
# Renames reach windows and chained sources
# --------------------------------------------------------------------------


def _chained_windowed(ema: int) -> StrategySpec:
    """EMA of an EMA, crossing price within a window that is a parameter."""
    spec = StrategySpec(name=f"chain{ema}")
    spec.indicators = [IndicatorSlot("e1", "EMA", {"period": ema}),
                       IndicatorSlot("e2", "EMA", {"period": 5}, source="@e1.value")]
    spec.params = [ParamSpec("win", "Window", "int", 4, 1, 50, 1)]
    spec.entry_long = Within(Cross(Price("close"), "above", Ind("e2")), "$win")
    spec.exits.stop_loss_enabled = True
    return spec


def test_combining_strategies_renames_windows_and_chains():
    from tradingbacktester.strategy.combine import combine_strategies
    bars = generate_sample_data("NQ", "5m", n_bars=2000, seed=11)
    a, b = _chained_windowed(20), _chained_windowed(50)
    combined = combine_strategies([a.copy(), b.copy()], mode="any").spec
    combined.validate()
    either = compile_strategy(combined, bars).entry_long
    one = compile_strategy(a, bars).entry_long | compile_strategy(b, bars).entry_long
    assert np.array_equal(either, one) and one.any()
    # Two identical chains fold into one computation, and still agree.
    same = combine_strategies([a.copy(), a.copy()], mode="all").spec
    same.validate()
    assert len(same.indicators) == 2
    assert np.array_equal(compile_strategy(same, bars).entry_long,
                          compile_strategy(a, bars).entry_long)


def test_a_malformed_chain_reference_is_refused():
    for bad in ("@", "@e1."):
        spec = _chained_windowed(20)
        spec.indicators[1].source = bad
        with pytest.raises(StrategyError):
            spec.validate()


def test_renaming_a_parameter_in_the_editor_renames_the_window(qapp):
    from tradingbacktester.ui.dialogs.strategy_editor import _rename_param_in_condition
    cond = Within(Within(FLAG, "$win", mode="count", count="$win"), 3)
    _rename_param_in_condition(cond, "win", "span")
    assert cond.child.bars == "$span" and cond.child.count == "$span"
