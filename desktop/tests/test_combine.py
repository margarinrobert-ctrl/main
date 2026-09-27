"""Combining strategies: the merge, the vote condition, the CLI and the dialog.

The load-bearing test here is
``test_a_merged_rule_fires_exactly_where_the_set_operation_says``: it computes
what each mode *means* -- an intersection, a union, a count -- from the source
strategies' own compiled signal arrays, entirely outside ``combine.py``, and
demands the merged strategy match it bar for bar.  Everything else in this
file is about what the merge decides on the way there.
"""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import Qt

from tradingbacktester.core.errors import StrategyError
from tradingbacktester.core.types import BacktestConfig
from tradingbacktester.data.sample import generate_sample_data
from tradingbacktester.engine.backtester import Backtester
from tradingbacktester.strategy import builtin
from tradingbacktester.strategy.combine import (COMBINE_MODES,
                                                combine_strategies,
                                                default_threshold)
from tradingbacktester.strategy.compiler import compile_strategy
from tradingbacktester.strategy.expression import EvalContext
from tradingbacktester.strategy.rules import evaluate_condition
from tradingbacktester.strategy.spec import (Compare, Condition, Const, Group,
                                             Ind, IndicatorSlot, Price,
                                             StrategySpec, Vote,
                                             walk_conditions)

from .conftest import make_bars

FACTORIES = (builtin.ema_cross_rsi, builtin.rsi_mean_reversion,
             builtin.macd_trend, builtin.bollinger_breakout,
             builtin.donchian_breakout)


@pytest.fixture(scope="module")
def bars():
    return generate_sample_data("NQ", "1h", n_bars=6000, seed=7)


# --------------------------------------------------------------------------
# The Vote condition
# --------------------------------------------------------------------------


def _vote_over(closes, threshold, negate=False):
    bars = make_bars(closes)
    kids = [Compare(Price("close"), ">", Const(k)) for k in (1, 2, 3)]
    node = Vote(threshold, kids, negate)
    return evaluate_condition(node, EvalContext(bars=bars))


def test_a_vote_counts_rather_than_combining():
    # Closes 1..5 satisfy 0, 1, 2, 3 and 3 of the three thresholds.
    assert list(_vote_over([1, 2, 3, 4, 5], 1)) == [False, True, True, True, True]
    assert list(_vote_over([1, 2, 3, 4, 5], 2)) == [False, False, True, True, True]
    assert list(_vote_over([1, 2, 3, 4, 5], 3)) == [False, False, False, True, True]


def test_a_vote_nobody_can_win_is_never_true():
    assert not _vote_over([1, 2, 3, 4, 5], 4).any()


def test_a_vote_of_zero_is_true_everywhere():
    assert _vote_over([1, 2, 3, 4, 5], 0).all()


def test_a_negated_vote_is_the_complement():
    plain = _vote_over([1, 2, 3, 4, 5], 2)
    assert list(_vote_over([1, 2, 3, 4, 5], 2, negate=True)) == list(~plain)


def test_a_vote_of_one_matches_or_and_a_vote_of_all_matches_and():
    bars = make_bars([1, 2, 3, 4, 5])
    ctx = EvalContext(bars=bars)
    kids = [Compare(Price("close"), ">", Const(k)) for k in (1, 2, 3)]
    assert list(evaluate_condition(Vote(1, kids), ctx)) == \
        list(evaluate_condition(Group("OR", kids), ctx))
    assert list(evaluate_condition(Vote(3, kids), ctx)) == \
        list(evaluate_condition(Group("AND", kids), ctx))


def test_an_undefined_child_withholds_its_vote_rather_than_casting_it():
    """A NaN is not a yes, and it is not a no that lets others win either."""
    bars = make_bars([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    spec = StrategySpec(
        name="v",
        indicators=[IndicatorSlot("slow", "SMA", {"period": 8})],
        entry_long=Vote(2, [Compare(Price("close"), ">", Const(0)),
                            Compare(Price("close"), ">", Const(0)),
                            Compare(Ind("slow"), ">", Const(0))]))
    compiled = compile_strategy(spec, bars)
    # The two constant-true children alone reach the threshold of 2, so the
    # NaN child never decides anything -- but nor does it block them.
    assert compiled.entry_long[compiled.warmup:].all()


def test_a_vote_round_trips_through_json():
    kids = [Compare(Price("close"), ">", Const(k)) for k in (1, 2)]
    node = Vote(2, kids, negate=True)
    assert Condition.from_dict(node.to_dict()) == node


def test_a_vote_describes_itself_as_a_count():
    kids = [Compare(Price("close"), ">", Const(k)) for k in (1, 2, 3)]
    assert Vote(2, kids).describe().startswith("at least 2 of 3: ")


def test_validate_rejects_a_vote_that_can_never_be_satisfied():
    spec = StrategySpec(
        name="impossible",
        entry_long=Vote(4, [Compare(Price("close"), ">", Const(k))
                            for k in (1, 2, 3)]))
    with pytest.raises(StrategyError, match="can never happen"):
        spec.validate()


def test_walk_conditions_reaches_inside_a_vote():
    inner = Compare(Price("close"), ">", Const(1))
    tree = Group("AND", [Vote(1, [inner])])
    assert inner in list(walk_conditions(tree))


# --------------------------------------------------------------------------
# What the merge means
# --------------------------------------------------------------------------


def _expected(mode, arrays, allowed, threshold, n):
    """The set operation a mode names, computed without touching combine.py."""
    votes = [a for a, ok in zip(arrays, allowed) if ok]
    if not votes:
        return None
    if mode == "all":
        if len(votes) < len(arrays):
            return None
        return np.logical_and.reduce(votes)
    if mode == "any":
        return np.logical_or.reduce(votes)
    if threshold > len(votes):
        return None
    return sum(a.astype(np.int32) for a in votes) >= threshold


@pytest.mark.parametrize("mode", COMBINE_MODES)
@pytest.mark.parametrize("exit_mode", COMBINE_MODES)
def test_a_merged_rule_fires_exactly_where_the_set_operation_says(
        bars, mode, exit_mode):
    """The whole contract, checked bar by bar on every rule.

    Inside the merged strategy's own warm-up it is allowed to be quieter than
    the sources -- one strategy has one warm-up, the longest of its
    indicators', and the compiler blanks everything before it -- but it may
    never fire where no source did.
    """
    specs = [f() for f in FACTORIES]
    base = [compile_strategy(s, bars) for s in specs]
    report = combine_strategies([f() for f in FACTORIES], mode=mode,
                                exit_mode=exit_mode)
    merged = compile_strategy(report.spec, bars)
    warm = merged.warmup

    for key in ("entry_long", "entry_short", "exit_long", "exit_short"):
        side = "long" if key.endswith("long") else "short"
        rule_mode = mode if key.startswith("entry") else exit_mode

        def gate(spec, attribute):
            allowed = (spec.risk.allow_long if side == "long"
                       else spec.risk.allow_short)
            return allowed and getattr(spec, attribute) is not None

        want = _expected(rule_mode, [getattr(c, key) for c in base],
                         [gate(s, key) for s in specs], report.threshold,
                         len(bars))
        # An exit for a direction with no entry is dropped by the merge.
        if not key.startswith("entry"):
            entry_key = f"entry_{side}"
            if _expected(mode, [getattr(c, entry_key) for c in base],
                         [gate(s, entry_key) for s in specs],
                         report.threshold, len(bars)) is None:
                want = None

        got = getattr(merged, key)
        if want is None:
            assert not got.any(), f"{key} fired but no rule should exist"
            continue
        assert np.array_equal(got[warm:], want[warm:]), (
            f"{key} under {mode}/{exit_mode} differs from the "
            f"{rule_mode} of its sources after warm-up {warm}")
        assert not (got[:warm] & ~want[:warm]).any(), (
            f"{key} fired inside warm-up where no source did")


def test_all_trades_least_and_any_trades_most(bars):
    """The modes are ordered, which is the only reason to have three of them."""
    parts = [builtin.macd_trend(), builtin.donchian_breakout(),
             builtin.bollinger_breakout()]
    counts = {}
    for mode in COMBINE_MODES:
        spec = combine_strategies([p.copy() for p in parts], mode=mode).spec
        counts[mode] = int(compile_strategy(spec, bars).entry_long.sum())
    assert counts["all"] <= counts["majority"] <= counts["any"], counts


# --------------------------------------------------------------------------
# Namespacing
# --------------------------------------------------------------------------


def _two_colliding_specs():
    """Two strategies that use the same names for different things."""
    a = StrategySpec(
        name="Alpha",
        params=[__import__("tradingbacktester.indicators.base", fromlist=["x"])
                .ParamSpec("period", "Period", "int", 10)],
        indicators=[IndicatorSlot("ma", "SMA", {"period": "$period"})],
        entry_long=Compare(Price("close"), ">", Ind("ma")))
    b = StrategySpec(
        name="Beta",
        params=[__import__("tradingbacktester.indicators.base", fromlist=["x"])
                .ParamSpec("period", "Period", "int", 50)],
        indicators=[IndicatorSlot("ma", "EMA", {"period": "$period"})],
        entry_long=Compare(Price("close"), "<", Ind("ma")))
    return a, b


def test_colliding_names_are_kept_apart():
    report = combine_strategies(list(_two_colliding_specs()), mode="all")
    refs = [s.ref for s in report.spec.indicators]
    assert len(refs) == len(set(refs)) == 2
    names = [p.name for p in report.spec.params]
    assert len(names) == len(set(names)) == 2
    # And each slot still points at its own parameter.
    for slot in report.spec.indicators:
        target = slot.params["period"][1:]
        assert report.spec.param(target).default == (10 if slot.indicator == "SMA"
                                                     else 50)
    report.spec.validate()


def test_a_renamed_parameter_is_renamed_in_the_rules_too():
    from tradingbacktester.indicators.base import ParamSpec
    from tradingbacktester.strategy.spec import Param

    a = StrategySpec(name="A", params=[ParamSpec("level", "Level", "float", 1.0)],
                     indicators=[IndicatorSlot("r", "RSI", {"period": 14})],
                     entry_long=Compare(Ind("r"), ">", Param("level")))
    b = StrategySpec(name="B", params=[ParamSpec("level", "Level", "float", 2.0)],
                     indicators=[IndicatorSlot("r", "CCI", {"period": 20})],
                     entry_long=Compare(Ind("r"), ">", Param("level")))
    report = combine_strategies([a, b], mode="all")
    report.spec.validate()          # raises if a rule names a missing parameter
    text = report.spec.entry_long.describe()
    assert "$A_level" in text and "$B_level" in text


def test_combining_does_not_edit_the_strategies_it_was_given():
    a, b = _two_colliding_specs()
    before = (a.to_json(), b.to_json())
    combine_strategies([a, b], mode="any")
    assert (a.to_json(), b.to_json()) == before


def test_an_identical_indicator_is_computed_once():
    a = StrategySpec(name="A", indicators=[IndicatorSlot("ma", "SMA", {"period": 20})],
                     entry_long=Compare(Price("close"), ">", Ind("ma")))
    b = StrategySpec(name="B", indicators=[IndicatorSlot("sma", "SMA", {"period": 20})],
                     entry_long=Compare(Price("close"), "<", Ind("sma")))
    report = combine_strategies([a, b], mode="any")
    assert len(report.spec.indicators) == 1
    assert report.shared, "the shared slot was not reported"
    report.spec.validate()


def test_indicators_driven_by_a_parameter_are_not_shared():
    """Sharing them would tie two knobs the optimiser must be able to move."""
    from tradingbacktester.indicators.base import ParamSpec

    a = StrategySpec(name="A", params=[ParamSpec("p", "P", "int", 20)],
                     indicators=[IndicatorSlot("ma", "SMA", {"period": "$p"})],
                     entry_long=Compare(Price("close"), ">", Ind("ma")))
    b = StrategySpec(name="B", params=[ParamSpec("p", "P", "int", 20)],
                     indicators=[IndicatorSlot("ma", "SMA", {"period": "$p"})],
                     entry_long=Compare(Price("close"), "<", Ind("ma")))
    report = combine_strategies([a, b], mode="any")
    assert len(report.spec.indicators) == 2
    assert not report.shared


def test_a_shared_label_names_the_strategy_it_came_from():
    a = StrategySpec(name="Alpha", indicators=[IndicatorSlot("m", "SMA", {"period": 10})],
                     entry_long=Compare(Price("close"), ">", Ind("m")))
    b = StrategySpec(name="Beta", indicators=[IndicatorSlot("m", "SMA", {"period": 10},
                                                            source="high")],
                     entry_long=Compare(Price("close"), "<", Ind("m")))
    report = combine_strategies([a, b], mode="any")
    labels = [s.display_label() for s in report.spec.indicators]
    assert any("Alpha" in x for x in labels) and any("Beta" in x for x in labels)


# --------------------------------------------------------------------------
# What the merge refuses, and what it admits to
# --------------------------------------------------------------------------


def test_one_strategy_is_not_a_combination():
    with pytest.raises(StrategyError, match="at least two"):
        combine_strategies([builtin.macd_trend()])


def test_an_unknown_mode_is_refused_by_name():
    with pytest.raises(StrategyError, match="sometimes"):
        combine_strategies([builtin.macd_trend(), builtin.donchian_breakout()],
                           mode="sometimes")


def test_a_primary_outside_the_list_is_refused():
    with pytest.raises(StrategyError, match="primary"):
        combine_strategies([builtin.macd_trend(), builtin.donchian_breakout()],
                           primary=7)


def test_a_majority_larger_than_the_group_is_refused():
    with pytest.raises(StrategyError, match="between 1 and 2"):
        combine_strategies([builtin.macd_trend(), builtin.donchian_breakout()],
                           mode="majority", threshold=3)


def test_combining_opposite_directions_with_all_is_refused_not_returned_empty():
    """The failure mode this guards is a saved strategy that never trades."""
    long_only = StrategySpec(
        name="Longs", indicators=[IndicatorSlot("m", "SMA", {"period": 10})],
        entry_long=Compare(Price("close"), ">", Ind("m")))
    short_only = StrategySpec(
        name="Shorts", indicators=[IndicatorSlot("m", "SMA", {"period": 10})],
        entry_short=Compare(Price("close"), "<", Ind("m")))
    with pytest.raises(StrategyError, match="no entry rule at all"):
        combine_strategies([long_only, short_only], mode="all")
    # The union of the two is a perfectly good strategy, and says so.
    report = combine_strategies([long_only, short_only], mode="any")
    assert report.spec.entry_long is not None
    assert report.spec.entry_short is not None


def test_a_disabled_direction_counts_as_a_withheld_vote():
    a = StrategySpec(name="A", indicators=[IndicatorSlot("m", "SMA", {"period": 10})],
                     entry_long=Compare(Price("close"), ">", Ind("m")))
    b = StrategySpec(name="B", indicators=[IndicatorSlot("m", "SMA", {"period": 20})],
                     entry_long=Compare(Price("close"), ">", Ind("m")))
    b.risk.allow_long = False
    b.entry_short = Compare(Price("close"), "<", Ind("m"))
    with pytest.raises(StrategyError, match="no entry rule at all"):
        combine_strategies([a, b], mode="all")


def test_every_differing_setting_is_reported():
    a, b = _two_colliding_specs()
    a.exits.stop_loss_enabled = True
    a.exits.stop_loss_value = 1.5
    b.exits.stop_loss_enabled = True
    b.exits.stop_loss_value = 3.0
    b.risk.starting_capital = 250_000.0
    report = combine_strategies([a, b], mode="any")
    text = " ".join(report.conflicts)
    assert "stop_loss_value" in text and "1.5" in text and "3" in text
    assert "starting_capital" in text
    assert report.spec.exits.stop_loss_value == 1.5
    # And the description carries it, so it survives being saved.
    assert "stop_loss_value" in report.spec.description


def test_the_settings_come_from_the_primary_that_was_named():
    a, b = _two_colliding_specs()
    a.exits.max_bars_in_trade = 10
    b.exits.max_bars_in_trade = 99
    assert combine_strategies([a, b], mode="any",
                              primary=1).spec.exits.max_bars_in_trade == 99


def test_the_direction_gates_follow_the_merge_not_the_primary():
    a = StrategySpec(name="A", indicators=[IndicatorSlot("m", "SMA", {"period": 10})],
                     entry_long=Compare(Price("close"), ">", Ind("m")))
    b = StrategySpec(name="B", indicators=[IndicatorSlot("m", "SMA", {"period": 20})],
                     entry_long=Compare(Price("close"), ">", Ind("m")))
    report = combine_strategies([a, b], mode="all")
    assert report.spec.risk.allow_long is True
    assert report.spec.risk.allow_short is False


def test_a_dead_exit_rule_is_dropped_and_said_so():
    a = StrategySpec(name="A", indicators=[IndicatorSlot("m", "SMA", {"period": 10})],
                     entry_long=Compare(Price("close"), ">", Ind("m")),
                     exit_short=Compare(Price("close"), ">", Ind("m")))
    b = StrategySpec(name="B", indicators=[IndicatorSlot("m", "SMA", {"period": 20})],
                     entry_long=Compare(Price("close"), ">", Ind("m")),
                     exit_short=Compare(Price("close"), ">", Ind("m")))
    report = combine_strategies([a, b], mode="all")
    assert report.spec.exit_short is None
    assert any("no short entry rule" in n for n in report.notes)


def test_a_longer_warm_up_is_reported_because_it_costs_signals():
    report = combine_strategies([builtin.donchian_breakout(),
                                 builtin.macd_trend()], mode="any")
    assert any("warm-up" in n for n in report.notes)


def test_a_majority_of_two_says_it_is_the_same_as_all():
    report = combine_strategies([builtin.macd_trend(),
                                 builtin.donchian_breakout()], mode="majority")
    assert any("same as 'all'" in n for n in report.notes)


def test_default_threshold_is_a_strict_majority():
    assert [default_threshold(n) for n in (2, 3, 4, 5, 6)] == [2, 2, 3, 3, 4]


# --------------------------------------------------------------------------
# The result is a real strategy
# --------------------------------------------------------------------------


def test_a_combined_strategy_survives_a_save_and_reload_unchanged(bars):
    parts = [builtin.macd_trend(), builtin.donchian_breakout(),
             builtin.bollinger_breakout()]
    report = combine_strategies(parts, mode="majority")
    reloaded = StrategySpec.from_json(report.spec.to_json())
    first = Backtester(bars, report.spec, BacktestConfig()).run()
    again = Backtester(bars, reloaded, BacktestConfig()).run()
    assert len(first.trades) == len(again.trades)
    assert first.metrics["net_profit"] == again.metrics["net_profit"]


def test_a_combined_strategy_actually_trades(bars):
    report = combine_strategies([builtin.macd_trend(),
                                 builtin.donchian_breakout()], mode="any")
    result = Backtester(bars, report.spec, BacktestConfig()).run()
    assert len(result.trades) > 0


def test_a_combined_strategy_cannot_trade_before_its_warm_up(bars):
    report = combine_strategies([builtin.macd_trend(),
                                 builtin.donchian_breakout()], mode="any")
    compiled = compile_strategy(report.spec, bars)
    result = Backtester(bars, report.spec, BacktestConfig()).run()
    assert all(t.entry_bar >= compiled.warmup for t in result.trades)


def test_combining_a_combination_works():
    """Nothing about the result stops it being an input to another merge."""
    first = combine_strategies([builtin.macd_trend(),
                                builtin.donchian_breakout()], mode="all").spec
    second = combine_strategies([first, builtin.bollinger_breakout()],
                                mode="any")
    second.spec.validate()
    refs = [s.ref for s in second.spec.indicators]
    assert len(refs) == len(set(refs))


# --------------------------------------------------------------------------
# The CLI
# --------------------------------------------------------------------------


def test_the_cli_combines_and_saves(tmp_path, capsys):
    from tradingbacktester.cli import main
    from tradingbacktester.strategy.storage import StrategyStore
    from tradingbacktester.storage.workspace import Workspace

    code = main(["--workspace", str(tmp_path), "combine",
                 "--strategy", "MACD Trend",
                 "--strategy", "Donchian Channel Breakout",
                 "--mode", "any", "--name", "Merged", "--save"])
    assert code == 0
    out = capsys.readouterr().out
    assert "2 strategies combined with 'any'" in out
    assert "Saved 'Merged'." in out
    assert [e.name for e in StrategyStore(Workspace(tmp_path)).list()] == ["Merged"]


def test_the_cli_refuses_a_single_strategy(tmp_path, capsys):
    from tradingbacktester.cli import main

    assert main(["--workspace", str(tmp_path), "combine",
                 "--strategy", "MACD Trend"]) == 1
    assert "at least two" in capsys.readouterr().err


def test_the_cli_reports_conflicts_without_being_asked(tmp_path, capsys):
    from tradingbacktester.cli import main

    main(["--workspace", str(tmp_path), "combine",
          "--strategy", "MACD Trend",
          "--strategy", "Bollinger Breakout", "--mode", "all"])
    assert "Conflict:" in capsys.readouterr().out


def test_the_cli_emits_a_loadable_spec_as_json(tmp_path, capsys):
    import json

    from tradingbacktester.cli import main

    main(["--workspace", str(tmp_path), "combine", "--json",
          "--strategy", "MACD Trend",
          "--strategy", "Donchian Channel Breakout"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "all"
    StrategySpec.from_dict(payload["spec"]).validate()


# --------------------------------------------------------------------------
# The dialog
# --------------------------------------------------------------------------


@pytest.fixture
def dialog(qapp, tmp_path, bars):
    from tradingbacktester.storage.workspace import Workspace
    from tradingbacktester.strategy.storage import StrategyStore
    from tradingbacktester.ui.dialogs.combine_dialog import \
        CombineStrategiesDialog

    return CombineStrategiesDialog(StrategyStore(Workspace(tmp_path)), bars)


def _tick(dialog, fragment):
    from PySide6.QtCore import Qt

    for row in range(dialog.list.count()):
        item = dialog.list.item(row)
        if fragment.lower() in item.text().lower():
            item.setCheckState(Qt.CheckState.Checked)
            return
    raise AssertionError(f"no strategy matching {fragment!r}")


def test_the_dialog_will_not_combine_fewer_than_two(dialog):
    assert not dialog.save_button.isEnabled()
    _tick(dialog, "MACD")
    assert not dialog.save_button.isEnabled()
    assert "at least two" in dialog.headline.text()


def test_the_dialog_previews_as_soon_as_two_are_ticked(dialog):
    _tick(dialog, "MACD")
    _tick(dialog, "Donchian")
    assert dialog.save_button.isEnabled()
    assert dialog.backtest_button.isEnabled()
    assert "2 strategies combined" in dialog.headline.text()
    assert "Long entry:" in dialog.detail.toPlainText()


def test_the_dialog_shows_the_conflicts_it_resolved(dialog):
    _tick(dialog, "MACD")
    _tick(dialog, "Bollinger")
    assert "Conflict:" in dialog.detail.toPlainText()


def test_the_vote_box_only_matters_for_a_majority(dialog):
    _tick(dialog, "MACD")
    _tick(dialog, "Donchian")
    assert not dialog.threshold.isEnabled()
    dialog.mode.setCurrentIndex(list(COMBINE_MODES).index("majority"))
    assert dialog.threshold.isEnabled()
    assert dialog.threshold.value() == 2


def test_the_vote_default_follows_how_many_are_ticked(dialog):
    dialog.mode.setCurrentIndex(list(COMBINE_MODES).index("majority"))
    _tick(dialog, "MACD")
    _tick(dialog, "Donchian")
    assert dialog.threshold.value() == 2
    _tick(dialog, "Bollinger")
    _tick(dialog, "RSI Mean")
    assert dialog.threshold.value() == 3, "a majority of four is three"
    assert dialog.threshold.maximum() == 4


def test_a_hand_set_vote_is_not_overwritten_but_is_clamped(dialog):
    from PySide6.QtCore import Qt

    dialog.mode.setCurrentIndex(list(COMBINE_MODES).index("majority"))
    for name in ("MACD", "Donchian", "Bollinger"):
        _tick(dialog, name)
    dialog.threshold.setValue(3)
    _tick(dialog, "RSI Mean")
    assert dialog.threshold.value() == 3, "a hand-set vote was overwritten"
    for row in range(dialog.list.count()):
        if "bollinger" in dialog.list.item(row).text().lower():
            dialog.list.item(row).setCheckState(Qt.CheckState.Unchecked)
    assert dialog.threshold.value() == 3
    for row in range(dialog.list.count()):
        if "rsi mean" in dialog.list.item(row).text().lower():
            dialog.list.item(row).setCheckState(Qt.CheckState.Unchecked)
    assert dialog.threshold.value() == 2, "the vote was left above the count"


def test_ticking_another_strategy_does_not_move_the_settings_source(dialog):
    _tick(dialog, "MACD")
    _tick(dialog, "Donchian")
    dialog.primary.setCurrentIndex(1)
    chosen = dialog.primary.currentText()
    _tick(dialog, "Bollinger")
    assert dialog.primary.currentText() == chosen


def test_changing_the_settings_source_changes_the_result(dialog):
    _tick(dialog, "MACD")
    _tick(dialog, "Bollinger")
    names = [dialog.primary.itemText(i) for i in range(dialog.primary.count())]
    dialog.primary.setCurrentIndex(0)
    first = dialog.detail.toPlainText()
    dialog.primary.setCurrentIndex(1)
    second = dialog.detail.toPlainText()
    assert first != second
    assert f"taken from {names[1]}" in second


def test_the_dialog_saves_a_strategy_that_reloads(dialog, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "tradingbacktester.ui.dialogs.combine_dialog.show_info",
        lambda *a, **k: None)
    _tick(dialog, "MACD")
    _tick(dialog, "Donchian")
    dialog.on_save()
    entries = dialog._store.list()
    assert len(entries) == 1
    dialog._store.load(entries[0].id).validate()


def test_the_dialog_backtests_the_parts_beside_the_whole(dialog):
    _tick(dialog, "MACD")
    _tick(dialog, "Donchian")
    dialog.on_backtest()
    text = dialog.detail.toPlainText()
    assert "MACD Trend" in text and "Donchian Channel Breakout" in text
    assert "trades" in text
    assert "has not been shown to beat them anywhere else" in text


def test_the_dialog_explains_a_refusal_instead_of_showing_a_traceback(dialog,
                                                                     tmp_path):
    """An impossible combination must read as a sentence, not a stack trace."""
    from tradingbacktester.storage.workspace import Workspace
    from tradingbacktester.strategy.storage import StrategyStore

    store = StrategyStore(Workspace(tmp_path))
    longs = StrategySpec(name="Only longs",
                         indicators=[IndicatorSlot("m", "SMA", {"period": 10})],
                         entry_long=Compare(Price("close"), ">", Ind("m")))
    shorts = StrategySpec(name="Only shorts",
                          indicators=[IndicatorSlot("m", "SMA", {"period": 10})],
                          entry_short=Compare(Price("close"), "<", Ind("m")))
    store.save(longs)
    store.save(shorts)

    from tradingbacktester.ui.dialogs.combine_dialog import \
        CombineStrategiesDialog

    fresh = CombineStrategiesDialog(store, None)
    _tick(fresh, "Only longs")
    _tick(fresh, "Only shorts")
    assert not fresh.save_button.isEnabled()
    assert "no entry rule at all" in fresh.headline.text()
    assert "Traceback" not in fresh.detail.toPlainText()


# --------------------------------------------------------------------------
# The result stays editable
# --------------------------------------------------------------------------


def test_the_result_does_not_share_settings_with_the_strategy_it_came_from():
    """Editing the combination must not reach back into its source.

    Assigning the primary's own settings object leaves the two sharing it, so
    changing the combination's stop loss in the editor would silently change
    the strategy it was built from.
    """
    a, b = builtin.macd_trend(), builtin.donchian_breakout()
    spec = combine_strategies([a, b], mode="any").spec
    for block in ("risk", "exits", "execution", "session", "costs"):
        assert getattr(spec, block) is not getattr(a, block), f"{block} aliased"
    spec.exits.stop_loss_value = 99.0
    spec.costs.commission_value = 12.0
    spec.session.enabled = True
    assert a.exits.stop_loss_value != 99.0
    assert a.costs.commission_value != 12.0
    assert a.session.enabled is False


def test_a_vote_is_a_real_node_in_the_editor(qapp, bars):
    """Combining must not be a one-way door into a rule nobody can open."""
    from tradingbacktester.ui.dialogs import strategy_editor as SE

    report = combine_strategies([builtin.macd_trend(),
                                 builtin.donchian_breakout(),
                                 builtin.bollinger_breakout()], mode="majority")
    editor = SE.StrategyEditor(report.spec, None, bars)
    vote_item = editor.tree.topLevelItem(0).child(0)
    vote = vote_item.data(0, Qt.ItemDataRole.UserRole)
    assert isinstance(vote, Vote)
    assert vote_item.childCount() == len(vote.children) == 3, (
        "a vote's children were not shown, so the rule is opaque")
    assert isinstance(SE._node_editor(editor, vote), SE._VoteEditor)
    assert "at least 2 of 3" in SE._node_title(vote)


def test_a_votes_children_can_be_moved_and_removed(qapp, bars):
    from tradingbacktester.ui.dialogs import strategy_editor as SE

    report = combine_strategies([builtin.macd_trend(),
                                 builtin.donchian_breakout(),
                                 builtin.bollinger_breakout()], mode="majority")
    editor = SE.StrategyEditor(report.spec, None, bars)
    vote = editor.tree.topLevelItem(0).child(0).data(0, Qt.ItemDataRole.UserRole)

    order = [c.describe() for c in vote.children]
    editor.tree.setCurrentItem(editor.tree.topLevelItem(0).child(0).child(0))
    editor._move_node(1)
    assert [c.describe() for c in vote.children][0] == order[1]

    editor.tree.setCurrentItem(editor.tree.topLevelItem(0).child(0).child(0))
    editor._remove_node()
    assert len(vote.children) == 2


def test_changing_a_votes_threshold_changes_what_it_trades(bars):
    report = combine_strategies([builtin.macd_trend(),
                                 builtin.donchian_breakout(),
                                 builtin.bollinger_breakout()], mode="majority")
    spec = report.spec
    vote = spec.entry_long
    assert isinstance(vote, Vote)
    loose = int(compile_strategy(spec, bars).entry_long.sum())
    vote.threshold = 3
    strict = int(compile_strategy(spec, bars).entry_long.sum())
    assert strict < loose
