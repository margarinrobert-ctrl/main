"""Pasting a strategy and editing it: the friction, and one real defect.

The defect is in
``test_an_untranslatable_assignment_is_not_reported_as_converted``.  The
importer used to mark every ``x = ...`` line converted the moment the name was
bound, without anyone having tried to convert the value -- so
``higher = request.security(...)``, the one construct the dialog's own
placeholder promises will be listed rather than guessed at, was reported as
*converted*, and a script that computed it without trading on it was reported
as converted **in full**.  The line table is the whole premise of that dialog.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog

from tradingbacktester.data.sample import generate_sample_data
from tradingbacktester.strategy.builtin import ema_cross_rsi
from tradingbacktester.strategy.compiler import compile_strategy
from tradingbacktester.strategy.importer import import_strategy
from tradingbacktester.strategy.spec import StrategySpec
from tradingbacktester.ui.dialogs import strategy_editor as SE
from tradingbacktester.ui.dialogs.import_strategy_dialog import \
    ImportStrategyDialog

CLEAN = """//@version=5
strategy("EMA pullback", overlay=true)
fast = ta.ema(close, 20)
slow = ta.ema(close, 50)
r = ta.rsi(close, 14)
longCond = ta.crossover(fast, slow) and r > 50
if longCond
    strategy.entry("L", strategy.long)
plot(fast, color=color.blue)
"""

#: A higher-timeframe filter the rules actually use.
USES_SECURITY = """//@version=5
strategy("HTF filter", overlay=true)
fast = ta.ema(close, 20)
higher = request.security(syminfo.tickerid, "60", close)
longCond = ta.crossover(close, fast) and close > higher
if longCond
    strategy.entry("L", strategy.long)
"""

#: The same thing computed and then never traded on.
IGNORES_SECURITY = """//@version=5
strategy("HTF computed but unused", overlay=true)
fast = ta.ema(close, 20)
higher = request.security(syminfo.tickerid, "60", close)
longCond = ta.crossover(close, fast)
if longCond
    strategy.entry("L", strategy.long)
"""


@pytest.fixture(scope="module")
def bars():
    return generate_sample_data("NQ", "1h", n_bars=1500, seed=5)


def _outcome(report, fragment):
    for line in report.lines:
        if fragment in line.source:
            return line.outcome, line.detail
    raise AssertionError(f"no line containing {fragment!r}")


# --------------------------------------------------------------------------
# The importer told the truth about assignments
# --------------------------------------------------------------------------


def test_an_untranslatable_assignment_is_not_reported_as_converted():
    report = import_strategy(USES_SECURITY)
    outcome, detail = _outcome(report, "request.security")
    assert outcome == "unsupported", (
        "request.security was reported as converted; the line table is the "
        "only thing telling the user it is missing")
    assert "request.security" in detail
    assert not report.faithful


def test_a_rule_built_on_an_untranslatable_binding_is_unsupported_too():
    report = import_strategy(USES_SECURITY)
    assert _outcome(report, "longCond =")[0] == "unsupported"
    assert _outcome(report, "strategy.entry")[0] == "unsupported"


def test_an_unused_untranslatable_line_is_ignored_not_unsupported():
    """It changes nothing about what is traded, so it is not a defect."""
    report = import_strategy(IGNORES_SECURITY)
    outcome, detail = _outcome(report, "request.security")
    assert outcome == "ignored"
    assert "no rule uses it" in detail
    assert report.faithful, "what this trades WAS fully translated"


def test_a_translated_assignment_still_says_so():
    report = import_strategy(CLEAN)
    assert _outcome(report, "fast = ta.ema")[0] == "converted"
    assert report.faithful


def test_an_assignment_nothing_uses_is_named_as_such():
    text = CLEAN.replace("plot(fast, color=color.blue)",
                         "spare = ta.sma(close, 10)")
    report = import_strategy(text)
    outcome, detail = _outcome(report, "spare =")
    assert outcome == "converted"
    assert "no rule uses it" in detail


def test_an_indicator_probe_leaves_no_slot_behind():
    """Classifying an unused line must not add an indicator to the spec."""
    text = CLEAN.replace("plot(fast, color=color.blue)",
                         "spare = ta.sma(close, 999)")
    report = import_strategy(text)
    periods = [s.params.get("period") for s in report.spec.indicators]
    assert 999 not in periods, "the probe left its indicator in the strategy"


def test_csharp_is_refused_by_name_rather_than_as_unknown():
    """Naming the language tells the reader the refusal is about the format."""
    report = import_strategy(
        "using cAlgo.API;\n"
        "namespace cAlgo.Robots\n{\n"
        "    [Robot(TimeZone = TimeZones.UTC)]\n"
        "    public class MyBot : Robot\n    {\n"
        "        protected override void OnBar()\n        {\n"
        "            ExecuteMarketOrder(TradeType.Buy, SymbolName, 1000);\n"
        "        }\n    }\n}\n")
    assert report.detected == "csharp"
    assert "C#" in report.errors[0]
    assert report.spec is None


def test_adding_csharp_detection_did_not_steal_pine():
    assert import_strategy(CLEAN).detected == "pine"


# --------------------------------------------------------------------------
# The paste dialog
# --------------------------------------------------------------------------


@pytest.fixture
def paste(qapp, tmp_path, bars):
    from tradingbacktester.storage.workspace import Workspace
    from tradingbacktester.strategy.storage import StrategyStore

    return ImportStrategyDialog(StrategyStore(Workspace(tmp_path)), bars)


def test_pasted_text_is_read_without_pressing_anything(paste):
    paste.source.setPlainText(CLEAN)
    assert paste._reread.isActive(), "the auto-read timer did not start"
    assert "Reading" in paste.source_status.text()
    paste._auto_read()
    assert "converted in full" in paste.headline.text()
    assert paste.table.rowCount() > 0


def test_editing_the_text_disarms_the_buttons_immediately(paste):
    paste.source.setPlainText(CLEAN)
    paste._auto_read()
    assert paste.save_button.isEnabled()
    paste.source.insertPlainText("\nhalf a line (")
    assert not paste.save_button.isEnabled(), "a stale report stayed saveable"
    assert not paste.backtest_button.isEnabled()
    assert not paste.edit_button.isEnabled()


def test_a_syntax_error_mid_typing_does_not_pop_a_dialog(paste, monkeypatch):
    called = []
    monkeypatch.setattr(
        "tradingbacktester.ui.dialogs.import_strategy_dialog.show_error",
        lambda *a, **k: called.append(a))
    paste.source.setPlainText("strategy(\nif ((((")
    paste._auto_read()
    assert not called, "a modal interrupted someone who was still typing"


def test_the_clipboard_button_pastes_and_reads(paste):
    QGuiApplication.clipboard().setText(CLEAN)
    paste.on_paste_clipboard()
    assert paste.source.toPlainText().startswith("//@version=5")
    assert paste.save_button.isEnabled()


def test_the_clipboard_button_says_so_when_there_is_nothing_to_paste(paste):
    QGuiApplication.clipboard().setText("")
    paste.on_paste_clipboard()
    assert "clipboard" in paste.source_status.text().lower()


def test_a_file_that_cannot_be_read_is_reported_not_raised(paste, monkeypatch,
                                                           tmp_path):
    shown = []
    monkeypatch.setattr(
        "tradingbacktester.ui.dialogs.import_strategy_dialog.QFileDialog"
        ".getOpenFileName",
        staticmethod(lambda *a, **k: (str(tmp_path / "nope.pine"), "")))
    monkeypatch.setattr(
        "tradingbacktester.ui.dialogs.import_strategy_dialog.show_error",
        lambda *a, **k: shown.append(a))
    paste.on_open_file()
    assert shown, "a missing file produced no message"


def test_a_file_is_loaded_and_read(paste, monkeypatch, tmp_path):
    path = tmp_path / "s.pine"
    path.write_text(CLEAN, encoding="utf-8")
    monkeypatch.setattr(
        "tradingbacktester.ui.dialogs.import_strategy_dialog.QFileDialog"
        ".getOpenFileName",
        staticmethod(lambda *a, **k: (str(path), "")))
    paste.on_open_file()
    assert paste.save_button.isEnabled()
    assert "converted in full" in paste.headline.text()


def test_a_partial_conversion_can_be_edited_but_not_run_or_saved(paste):
    paste.source.setPlainText(USES_SECURITY)
    paste.on_read()
    assert "PARTIALLY converted" in paste.headline.text()
    assert not paste.save_button.isEnabled()
    assert not paste.backtest_button.isEnabled()
    assert paste.edit_button.isEnabled(), (
        "refusing to RUN a half-strategy is the rule; refusing to let anyone "
        "finish it just makes the refusal useless")
    assert "finished" in paste.save_button.toolTip()


def test_opening_a_partial_conversion_asks_first(paste, monkeypatch):
    asked = []
    monkeypatch.setattr(
        "tradingbacktester.ui.dialogs.import_strategy_dialog.confirm",
        lambda *a, **k: (asked.append(a), False)[1])
    paste.source.setPlainText(USES_SECURITY)
    paste.on_read()
    paste.on_edit()
    assert asked, "a partial conversion opened without a word"
    assert "could not be translated" in asked[0][2]


def test_opening_a_faithful_conversion_does_not_ask(paste, monkeypatch):
    asked, opened = [], []
    monkeypatch.setattr(
        "tradingbacktester.ui.dialogs.import_strategy_dialog.confirm",
        lambda *a, **k: (asked.append(a), True)[1])

    class _Editor:
        spec = StrategySpec(name="edited")

        def __init__(self, *a, **k):
            opened.append(a)

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(SE, "StrategyEditor", _Editor)
    paste.source.setPlainText(CLEAN)
    paste.on_read()
    paste.on_edit()
    assert not asked
    assert opened, "the editor was never opened"


def test_editing_hands_the_editor_a_copy_not_the_report_s_own_spec(paste,
                                                                  monkeypatch):
    seen = []

    class _Editor:
        def __init__(self, spec, *a, **k):
            seen.append(spec)
            self.spec = spec

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(SE, "StrategyEditor", _Editor)
    paste.source.setPlainText(CLEAN)
    paste.on_read()
    paste.on_edit()
    assert seen and seen[0] is not paste._report.spec


def test_clicking_a_line_moves_the_cursor_to_it(paste):
    paste.source.setPlainText(USES_SECURITY)
    paste.on_read()
    row = next(r for r in range(paste.table.rowCount())
               if paste.table.item(r, 2).text() == "unsupported")
    paste.table.selectRow(row)
    line = int(paste.table.item(row, 0).text())
    assert paste.source.textCursor().blockNumber() + 1 == line


def test_clearing_empties_the_result_too(paste):
    paste.source.setPlainText(CLEAN)
    paste._auto_read()
    paste.on_clear()
    assert paste.table.rowCount() == 0
    assert not paste.save_button.isEnabled()
    assert not paste.edit_button.isEnabled()


# --------------------------------------------------------------------------
# The editor's common rules
# --------------------------------------------------------------------------


def _defaults(preset, above=True):
    return {key: (above if key == "above" else default)
            for key, _label, default, _low, _high in preset.fields}


@pytest.mark.parametrize("preset", SE._PRESETS, ids=lambda p: p.name)
def test_every_preset_builds_a_rule_that_compiles_and_fires(preset, bars):
    """A preset that produces a rule which never fires is a fake button."""
    spec = StrategySpec(name="probe")
    spec.entry_long = preset.build(spec, _defaults(preset))
    spec.validate()
    fired = int(compile_strategy(spec, bars).entry_long.sum())
    assert fired > 0, f"{preset.name} never fires at its own defaults"


@pytest.mark.parametrize("preset", [p for p in SE._PRESETS
                                    if any(k == "above" for k, *_ in p.fields)],
                         ids=lambda p: p.name)
def test_every_directional_preset_works_both_ways(preset, bars):
    for above in (True, False):
        spec = StrategySpec(name="probe")
        spec.entry_long = preset.build(spec, _defaults(preset, above))
        spec.validate()
        assert int(compile_strategy(spec, bars).entry_long.sum()) > 0


def test_a_preset_reuses_an_identical_indicator():
    preset = SE._PRESETS[0]
    spec = StrategySpec(name="twice")
    preset.build(spec, _defaults(preset))
    preset.build(spec, _defaults(preset))
    assert len(spec.indicators) == 1


def test_a_preset_with_different_numbers_adds_a_second_indicator():
    preset = SE._PRESETS[0]
    spec = StrategySpec(name="twice")
    preset.build(spec, _defaults(preset))
    preset.build(spec, {**_defaults(preset), "period": 50})
    assert len(spec.indicators) == 2
    assert len({s.ref for s in spec.indicators}) == 2


def test_a_preset_never_collides_with_a_name_already_in_the_strategy():
    preset = next(p for p in SE._PRESETS if "RSI" in p.name)
    spec = ema_cross_rsi()                # already has `rsi` and `rsi_period`
    preset.build(spec, _defaults(preset))
    preset.build(spec, {**_defaults(preset), "period": 21})
    refs = [s.ref for s in spec.indicators]
    names = [p.name for p in spec.params]
    assert len(refs) == len(set(refs))
    assert len(names) == len(set(names))
    spec.validate()


def test_a_preset_threshold_becomes_a_sweepable_parameter():
    """The point of a parameter is that the optimiser can move it."""
    preset = next(p for p in SE._PRESETS if "RSI" in p.name)
    spec = StrategySpec(name="p")
    spec.entry_long = preset.build(spec, _defaults(preset))
    param = spec.params[-1]
    assert param.minimum == 0.0 and param.maximum == 100.0, (
        "ParamSpec defaults to a minimum of 1, which silently rejects an RSI "
        "level below it at compile time")
    assert spec.param_values({param.name: 0.5})[param.name] == 0.5


def test_the_donchian_preset_reads_the_previous_bar_s_channel():
    """This bar's high is part of this bar's channel; breaking it is trivial."""
    preset = next(p for p in SE._PRESETS if "Donchian" in p.name)
    spec = StrategySpec(name="p")
    condition = preset.build(spec, _defaults(preset))
    assert condition.right.offset == 1


# --------------------------------------------------------------------------
# The editor's tree
# --------------------------------------------------------------------------


@pytest.fixture
def editor(qapp, bars):
    return SE.StrategyEditor(ema_cross_rsi(), None, bars)


def _first_child(editor):
    return editor.tree.topLevelItem(0).child(0)


def test_the_preset_picker_builds_a_form_for_every_preset(editor):
    picker = SE._PresetPicker(editor)
    for row in range(picker.list.count()):
        picker.list.setCurrentRow(row)
        assert picker.form.rowCount() == len(SE._PRESETS[row].fields)
        assert picker.blurb.text()


def test_the_picker_refuses_a_crossing_that_cannot_happen(editor, monkeypatch):
    warned = []
    monkeypatch.setattr(SE, "show_warning", lambda *a, **k: warned.append(a))
    picker = SE._PresetPicker(editor)
    picker.list.setCurrentRow(
        next(i for i, p in enumerate(SE._PRESETS) if "crosses another" in p.name))
    picker._widgets["fast"].setValue(50)
    picker._widgets["slow"].setValue(20)
    picker._accept()
    assert picker.preset is None and warned


def test_adding_a_preset_adds_its_indicator_and_its_condition(editor,
                                                              monkeypatch):
    preset = SE._PRESETS[0]
    values = _defaults(preset)

    class _Stub:
        def __init__(self, *a, **k):
            self.preset, self.values = preset, values

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(SE, "_PresetPicker", _Stub)
    slots, kids = len(editor.spec.indicators), len(editor._current_root().children)
    editor._add_preset()
    assert len(editor.spec.indicators) == slots + 1
    assert len(editor._current_root().children) == kids + 1
    editor.spec.validate()


def test_duplicating_a_node_makes_an_independent_copy(editor):
    root = editor._current_root()
    editor.tree.setCurrentItem(_first_child(editor))
    before = len(root.children)
    editor._duplicate_node()
    root = editor._current_root()
    assert len(root.children) == before + 1
    first, second = root.children[0], root.children[1]
    assert first is not second
    assert first.to_dict() == second.to_dict()
    second.direction = "below"
    assert first.direction != "below", "the copy shares state with its original"


def test_moving_a_node_swaps_it_with_its_neighbour(editor):
    order = [c.describe() for c in editor._current_root().children]
    editor.tree.setCurrentItem(_first_child(editor))
    editor._move_node(1)
    after = [c.describe() for c in editor._current_root().children]
    assert after[0] == order[1] and after[1] == order[0]


def test_moving_a_node_off_the_end_does_nothing(editor):
    order = [c.describe() for c in editor._current_root().children]
    editor.tree.setCurrentItem(_first_child(editor))
    editor._move_node(-1)
    assert [c.describe() for c in editor._current_root().children] == order


def test_the_selection_follows_the_node_that_moved(editor):
    editor.tree.setCurrentItem(_first_child(editor))
    node = editor.tree.currentItem().data(0, Qt.ItemDataRole.UserRole)
    editor._move_node(1)
    assert editor.tree.currentItem().data(0, Qt.ItemDataRole.UserRole) is node


def test_the_outermost_group_cannot_be_moved_or_duplicated(editor, monkeypatch):
    monkeypatch.setattr(SE, "show_info", lambda *a, **k: None)
    editor.tree.setCurrentItem(editor.tree.topLevelItem(0))
    before = len(editor._current_root().children)
    editor._move_node(1)
    editor._duplicate_node()
    assert len(editor._current_root().children) == before


# --------------------------------------------------------------------------
# Multi-output indicators: `[a, b, c] = ta.macd(...)`
# --------------------------------------------------------------------------

MACD_PINE = """//@version=5
strategy("m", overlay=true)
[macdLine, signalLine, hist] = ta.macd(close, 12, 26, 9)
if macdLine > signalLine
    strategy.entry("L", strategy.long)
"""


def test_tuple_destructuring_parses_at_all():
    """It did not. `_MULTI` named the outputs of MACD, Bollinger Bands, DMI,
    Stochastic and SuperTrend from the day the importer was written, and the
    parser rejected the only syntax Pine has for reaching them, so the whole
    table was unreachable."""
    from tradingbacktester.strategy.pine_parse import parse

    statement = parse("[m, s, h] = ta.macd(close, 12, 26, 9)")[0]
    assert statement.kind == "tuple_assignment"
    assert statement.targets == ("m", "s", "h")


def test_a_macd_written_the_way_pine_writes_it_imports():
    report = import_strategy(MACD_PINE)
    assert report.faithful, [l.detail for l in report.unsupported]
    assert [s.indicator for s in report.spec.indicators] == ["MACD"]
    assert report.spec.entry_long.describe() == "macd1.macd > macd1.signal"


def test_bollinger_and_dmi_import_too():
    for text, indicator in (
        ('[mid, up, lo] = ta.bb(close, 20, 2)\nif close > up\n'
         '    strategy.entry("L", strategy.long)\n', "BBANDS"),
        ('[dp, dm, adxv] = ta.dmi(14, 14)\nif adxv > 25\n'
         '    strategy.entry("L", strategy.long)\n', "ADX"),
    ):
        report = import_strategy(
            f'//@version=5\nstrategy("t", overlay=true)\n{text}')
        assert report.faithful, [l.detail for l in report.unsupported]
        assert [s.indicator for s in report.spec.indicators] == [indicator]


def test_the_three_outputs_share_one_indicator_slot():
    """They are three views of one computation. Three slots would compute it
    three times and hand the optimiser three names for one knob."""
    report = import_strategy(MACD_PINE.replace(
        "if macdLine > signalLine",
        "if macdLine > signalLine and hist > 0"))
    assert report.faithful
    assert len(report.spec.indicators) == 1
    text = report.spec.entry_long.describe()
    assert "macd1.macd" in text and "macd1.signal" in text and "macd1.histogram" in text


def test_a_tuple_from_something_unmappable_is_refused_by_name():
    report = import_strategy(
        '//@version=5\nstrategy("t", overlay=true)\n'
        '[a, b] = ta.nonsense(1, 2)\nif a > b\n'
        '    strategy.entry("L", strategy.long)\n')
    assert not report.faithful
    assert any("does not return a tuple" in l.detail
               for l in report.unsupported)


def test_an_index_expression_is_still_an_index_not_a_tuple_target():
    """`[1]` at the head of a line must not be mistaken for destructuring."""
    from tradingbacktester.strategy.pine_parse import parse

    statement = parse("x = close[1]")[0]
    assert statement.kind == "assignment"
    assert statement.targets == ()


def test_a_var_tuple_is_still_refused_for_carrying_state():
    report = import_strategy(
        '//@version=5\nstrategy("t", overlay=true)\n'
        'var [a, b] = ta.macd(close, 12, 26, 9)\n'
        'if a > b\n    strategy.entry("L", strategy.long)\n')
    assert not report.faithful


def test_the_turtle_gate_the_user_pasted_now_converts():
    """The ADX + extension gate from the script that reported 87 unsupported
    lines. The `switch` presets are what it could not read; flattened to their
    constants, the whole gate comes across."""
    report = import_strategy("""//@version=5
strategy("Turtle Long-Only T1", overlay = true)
atrN     = ta.atr(20)
entryHi1 = ta.highest(high, 20)
entryHi2 = ta.highest(high, 55)
exitLo1  = ta.lowest(low, 10)
ema100   = ta.ema(close, 100)
[diPlus, diMinus, adxVal] = ta.dmi(14, 14)
adxOk    = adxVal < 22.0
extOk    = close - ema100 < 3.964 * atrN
breakout = high > entryHi1[1] or high > entryHi2[1]
longSignal = breakout and adxOk and extOk
exitSignal = low < exitLo1[1]
if longSignal
    strategy.entry("L", strategy.long)
if exitSignal
    strategy.close("L")
""")
    assert report.faithful, [l.detail for l in report.unsupported]
    kinds = {s.indicator for s in report.spec.indicators}
    assert {"ADX", "HIGHEST", "LOWEST", "EMA", "ATR"} <= kinds
    assert report.spec.validate() == []
