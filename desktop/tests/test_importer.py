"""Importing someone else's strategy.

The property every test here defends: **a strategy that cannot be fully
interpreted is reported, never approximated.** An import that quietly drops a
condition produces a backtest that runs, looks fine, and describes a strategy
the user did not write — and there is nothing on screen to tell them.

The most dangerous case has its own test. Pine's commonest shape is

    if longCondition
        strategy.entry("Long", strategy.long)

and an importer that reports the `if` as unsupported, then reads the indented
`strategy.entry` as a top-level line, has just built a strategy that enters on
every bar.
"""

from __future__ import annotations

import pytest

from tradingbacktester.strategy.importer import detect_format, import_strategy
from tradingbacktester.strategy.pine_parse import (PineSyntaxError, parse,
                                                   tokenize)

WORKING = '''//@version=5
strategy("EMA Cross RSI", overlay=true)
fast = ta.ema(close, 12)
slow = ta.ema(close, 26)
r = ta.rsi(close, 14)
longCond = ta.crossover(fast, slow) and r > 50
shortCond = ta.crossunder(fast, slow) and r < 50
if longCond
    strategy.entry("L", strategy.long)
if shortCond
    strategy.entry("S", strategy.short)
'''


# ---------------------------------------------------------------------------
# the tokeniser, where a regex would have gone wrong
# ---------------------------------------------------------------------------

def test_a_call_inside_a_comment_is_not_read_as_code():
    report = import_strategy(
        WORKING + "// ta.sma(close, 999) mentioned in a comment\n")
    slots = {(s.indicator, s.params.get("period")) for s in report.spec.indicators}
    assert ("SMA", 999) not in slots


def test_a_double_slash_inside_a_string_does_not_start_a_comment():
    statements = parse('label = "not // a comment"\nx = ta.ema(close, 5)\n')
    assert len(statements) == 2
    assert statements[0].value.value == "not // a comment"
    assert statements[1].target == "x"


def test_an_unterminated_string_is_an_error_with_a_line_number():
    with pytest.raises(PineSyntaxError) as caught:
        tokenize('a = "never closed\nb = 1\n')
    assert caught.value.line == 1


def test_nested_calls_parse_to_nested_nodes():
    statements = parse("x = ta.ema(ta.ema(close, 20), 5)\n")
    outer = statements[0].value
    assert outer.value == "ta.ema"
    assert outer.args[0].value == "ta.ema"
    assert outer.args[0].args[1].value == 20.0
    assert outer.args[1].value == 5.0


def test_operators_are_matched_longest_first():
    statements = parse("c = a >= b\n")
    assert statements[0].value.value == ">="


# ---------------------------------------------------------------------------
# guards -- the case that silently breaks a strategy
# ---------------------------------------------------------------------------

def test_an_indented_entry_keeps_the_condition_of_its_if():
    statements = parse("if cond\n    strategy.entry(\"L\", strategy.long)\n")
    entry = next(s for s in statements if s.target == "strategy.entry")
    assert entry.guard is not None
    assert entry.guard.describe() == "cond"


def test_an_else_branch_gets_the_negation():
    statements = parse(
        "if cond\n    strategy.entry(\"L\", strategy.long)\n"
        "else\n    strategy.close(\"L\")\n")
    close = next(s for s in statements if s.target == "strategy.close")
    assert "not" in close.guard.describe()


def test_else_if_chains_accumulate_the_negations():
    statements = parse(
        "if a\n    strategy.entry(\"A\", strategy.long)\n"
        "else if b\n    strategy.entry(\"B\", strategy.long)\n"
        "else\n    strategy.close(\"C\")\n")
    guards = {s.target: s.guard.describe() for s in statements if s.guard}
    assert guards["strategy.close"] == "(nota and notb)"


def test_nested_ifs_are_anded_together():
    statements = parse(
        "if a\n    if b\n        strategy.entry(\"L\", strategy.long)\n")
    entry = next(s for s in statements if s.target == "strategy.entry")
    assert entry.guard.describe() == "(a and b)"


def test_an_orphan_else_is_refused_not_treated_as_unconditional():
    statements = parse("else\n    strategy.entry(\"L\", strategy.long)\n")
    entry = [s for s in statements if s.target == "strategy.entry"]
    assert not entry or entry[0].kind == "unsupported"


def test_an_entry_inside_a_for_loop_is_refused_not_imported_unguarded():
    """The loop is unsupported; the entry inside it must not become always-on."""
    report = import_strategy(
        "//@version=5\nstrategy(\"X\")\n"
        "c = ta.ema(close,10) > ta.ema(close,20)\n"
        "for i = 0 to 5\n    strategy.entry(\"L\", strategy.long)\n")
    assert not report.faithful
    assert report.spec is None or report.spec.entry_long is None
    assert any("every bar" in l.detail for l in report.unsupported)


def test_an_entry_with_no_condition_is_refused():
    report = import_strategy(
        "//@version=5\nstrategy(\"X\")\nf = ta.ema(close, 10)\n"
        "strategy.entry(\"L\", strategy.long)\n")
    assert not report.faithful
    assert any("every bar" in l.detail for l in report.unsupported)
    assert report.errors


# ---------------------------------------------------------------------------
# conversion
# ---------------------------------------------------------------------------

def test_a_working_strategy_converts_faithfully():
    report = import_strategy(WORKING)
    assert report.detected == "pine"
    assert report.faithful, [l.detail for l in report.unsupported] + report.errors
    spec = report.spec
    spec.validate()
    assert {s.indicator for s in spec.indicators} == {"EMA", "RSI"}
    assert spec.entry_long is not None and spec.entry_short is not None


def test_identical_indicators_share_one_slot():
    report = import_strategy(WORKING + "dup = ta.ema(close, 12)\n")
    periods = [s.params.get("period") for s in report.spec.indicators
               if s.indicator == "EMA"]
    assert sorted(periods) == [12, 26], "ta.ema(close, 12) was slotted twice"


def test_an_imported_strategy_actually_backtests():
    from tradingbacktester.core.timeframe import Timeframe
    from tradingbacktester.core.types import BacktestConfig
    from tradingbacktester.data.sample import generate_sample_data
    from tradingbacktester.engine.backtester import Backtester

    report = import_strategy(WORKING)
    bars = generate_sample_data("IMP", Timeframe.parse("1h"), n_bars=4000,
                                seed=9)
    result = Backtester(bars, report.spec, BacktestConfig()).run()
    assert result.metrics
    assert len(result.trades) > 0


def test_a_bar_offset_becomes_an_operand_offset():
    report = import_strategy(
        "//@version=5\nstrategy(\"X\")\n"
        "if close > close[1]\n    strategy.entry(\"L\", strategy.long)\n")
    assert report.faithful, [l.detail for l in report.unsupported]
    condition = report.spec.entry_long
    assert condition.right.offset == 1


def test_a_variable_lookback_is_refused():
    report = import_strategy(
        "//@version=5\nstrategy(\"X\")\nn = ta.rsi(close, 14)\n"
        "if close > close[n]\n    strategy.entry(\"L\", strategy.long)\n")
    assert not report.faithful
    assert any("variable number of bars" in l.detail
               for l in report.unsupported)


def test_a_unary_minus_is_rewritten_rather_than_dropped():
    """The spec has no unary minus; 0 - x means the same thing."""
    report = import_strategy(
        "//@version=5\nstrategy(\"X\")\nm = ta.mom(close, 10)\n"
        "if m > -5\n    strategy.entry(\"L\", strategy.long)\n")
    assert report.faithful, [l.detail for l in report.unsupported]


def test_exact_equality_is_warned_about():
    report = import_strategy(
        "//@version=5\nstrategy(\"X\")\nr = ta.rsi(close, 14)\n"
        "if r == 50\n    strategy.entry(\"L\", strategy.long)\n")
    assert any("exactly" in w for w in report.warnings)


def test_position_sizing_and_costs_are_flagged_as_not_imported():
    report = import_strategy(
        '//@version=5\nstrategy("X", pyramiding=3, commission_value=0.1)\n'
        'f = ta.ema(close, 10)\n'
        'if close > f\n    strategy.entry("L", strategy.long)\n')
    assert any("pyramiding" in w and "NOT taken" in w for w in report.warnings)


def test_cosmetic_calls_are_listed_as_ignored_not_silently_dropped():
    report = import_strategy(WORKING + "plot(fast)\nbgcolor(color.red)\n")
    ignored = " ".join(l.source for l in report.ignored)
    assert "plot(fast)" in ignored and "bgcolor" in ignored


def test_var_declarations_are_reported_once():
    report = import_strategy(WORKING + "var float held = na\n")
    matching = [l for l in report.unsupported if "held" in l.source]
    assert len(matching) == 1
    assert "between bars" in matching[0].detail


# ---------------------------------------------------------------------------
# detection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("//@version=5\nstrategy('x')\n", "pine"),
    ('#property copyright "x"\nvoid OnTick() { iMA(NULL,0,14,0,0,0,0); OrderSend(); }',
     "mql"),
    ("the quick brown fox", "unknown"),
    ("", "unknown"),
])
def test_format_detection(text, expected):
    detected, _confidence, evidence = detect_format(text)
    assert detected == expected
    assert evidence


def test_a_recognised_but_unsupported_language_refuses_with_its_name():
    report = import_strategy(
        '#property copyright "x"\nvoid OnTick() { iMA(NULL,0,1,0,0,0,0); '
        'OrderSend(); }')
    assert report.detected == "mql"
    assert not report.faithful
    assert any("MQL" in e for e in report.errors)


def test_this_applications_own_json_round_trips():
    import json

    from tradingbacktester.strategy.builtin import BUILTIN_STRATEGIES

    original = BUILTIN_STRATEGIES["EMA Cross + RSI"]()
    report = import_strategy(json.dumps(original.to_dict()))
    assert report.detected == "json"
    assert report.faithful
    assert report.spec.name == original.name


def test_broken_json_is_an_error_not_a_crash():
    report = import_strategy('{"schema_version": 1, "name": ')
    assert not report.faithful


def test_empty_input_is_refused_politely():
    report = import_strategy("")
    assert not report.faithful
    assert report.errors


# ---------------------------------------------------------------------------
# the dialog
# ---------------------------------------------------------------------------

pytestmark_gui = pytest.mark.gui


@pytest.mark.gui
def test_the_dialog_refuses_to_backtest_a_partial_conversion(qapp, tmp_path):
    """The rule the whole feature rests on, enforced at the button."""
    from tradingbacktester.config import Workspace
    from tradingbacktester.core.timeframe import Timeframe
    from tradingbacktester.data.sample import generate_sample_data
    from tradingbacktester.strategy.storage import StrategyStore
    from tradingbacktester.ui.dialogs.import_strategy_dialog import \
        ImportStrategyDialog

    workspace = Workspace(tmp_path).ensure()
    bars = generate_sample_data("D", Timeframe.parse("1h"), n_bars=1200, seed=2)
    dialog = ImportStrategyDialog(StrategyStore(workspace), bars)

    dialog.source.setPlainText(WORKING)
    dialog.on_read()
    qapp.processEvents()
    assert dialog.backtest_button.isEnabled()
    assert dialog.save_button.isEnabled()
    assert "converted in full" in dialog.headline.text()

    dialog.source.setPlainText(
        "//@version=5\nstrategy(\"X\")\n"
        "for i = 0 to 3\n    strategy.entry(\"L\", strategy.long)\n")
    dialog.on_read()
    qapp.processEvents()
    assert not dialog.backtest_button.isEnabled(), (
        "a partial conversion must not be runnable from the dialog")
    assert not dialog.save_button.isEnabled()
    assert "PARTIALLY" in dialog.headline.text()
    dialog.close()


@pytest.mark.gui
def test_the_dialog_lists_every_line_with_its_outcome(qapp, tmp_path):
    from tradingbacktester.config import Workspace
    from tradingbacktester.strategy.storage import StrategyStore
    from tradingbacktester.ui.dialogs.import_strategy_dialog import \
        ImportStrategyDialog

    workspace = Workspace(tmp_path).ensure()
    dialog = ImportStrategyDialog(StrategyStore(workspace))
    dialog.source.setPlainText(WORKING + "plot(fast)\nvar float held = na\n")
    dialog.on_read()
    qapp.processEvents()
    outcomes = {dialog.table.item(r, 2).text()
                for r in range(dialog.table.rowCount())}
    assert {"converted", "ignored", "unsupported"} <= outcomes
    assert "unsupported" in dialog.detail.toPlainText().lower() or \
        "could not be translated" in dialog.detail.toPlainText().lower()
    dialog.close()


@pytest.mark.gui
def test_the_dialog_survives_being_handed_nonsense(qapp, tmp_path):
    from tradingbacktester.config import Workspace
    from tradingbacktester.strategy.storage import StrategyStore
    from tradingbacktester.ui.dialogs.import_strategy_dialog import \
        ImportStrategyDialog

    workspace = Workspace(tmp_path).ensure()
    dialog = ImportStrategyDialog(StrategyStore(workspace))
    for text in ("", "   ", "}{", "\x00\x01", "a = " * 5000):
        dialog.source.setPlainText(text)
        dialog.on_read()
        qapp.processEvents()
        assert not dialog.backtest_button.isEnabled()
    dialog.close()
