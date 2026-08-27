"""Dialogs and the assembled main window.

Headless, with ``QT_QPA_PLATFORM=offscreen``. These check behaviour rather than
appearance: that a dialog builds against real data, that its buttons do what
their labels say, and that the paths a user actually walks do not raise.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from tradingbacktester.config import AppSettings, Workspace
from tradingbacktester.core.types import BacktestConfig
from tradingbacktester.data.csv_loader import ColumnMapping
from tradingbacktester.data.instruments import InstrumentRegistry
from tradingbacktester.data.repository import DatasetRepository
from tradingbacktester.data.sample import generate_sample_data
from tradingbacktester.data.validation import validate_bars
from tradingbacktester.engine.backtester import Backtester
from tradingbacktester.storage.backtest_store import BacktestStore
from tradingbacktester.strategy.builtin import BUILTIN_STRATEGIES

pytestmark = pytest.mark.gui


@pytest.fixture(scope="module")
def bars():
    return generate_sample_data("NQ", "1h", n_bars=2200, seed=21)


@pytest.fixture
def registry(tmp_path) -> InstrumentRegistry:
    return InstrumentRegistry(tmp_path / "instruments.json")


def run_once(bars, name: str = "EMA Cross + RSI"):
    spec = BUILTIN_STRATEGIES[name]()
    config = BacktestConfig(starting_capital=100_000.0)
    config.warmup_bars = spec.warmup_bars()
    return Backtester(bars, spec, config).run()


# --------------------------------------------------------------------------
# Markdown and the document reader
# --------------------------------------------------------------------------

def test_markdown_escapes_html(qapp):
    from tradingbacktester.ui.dialogs.about_dialog import markdown_to_html

    out = markdown_to_html("A strategy called <script>alert(1)</script>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_markdown_handles_the_project_documents(qapp):
    from tradingbacktester.ui.dialogs.about_dialog import markdown_to_html

    root = Path(__file__).resolve().parent.parent / "docs"
    for name in ("METRICS.md", "BACKTEST_ASSUMPTIONS.md"):
        path = root / name
        if not path.exists():
            continue
        out = markdown_to_html(path.read_text(encoding="utf-8"))
        assert len(out) > 1000, name
        assert "<h1" in out or "<h2" in out, name


def test_markdown_constructs(qapp):
    from tradingbacktester.ui.dialogs.about_dialog import markdown_to_html

    out = markdown_to_html(
        "# Title\n\nSome **bold** and *italic* and `code`.\n\n"
        "- one\n- two\n\n1. first\n2. second\n\n"
        "| a | b |\n|---|---|\n| 1 | 2 |\n\n"
        "> quoted\n\n```\nfenced\n```\n\n---\n")
    for fragment in ("<h1", "<b>bold</b>", "<i>italic</i>", "<code",
                     "<ul", "<ol", "<table", "<pre", "<hr"):
        assert fragment in out, fragment


def test_about_and_document_dialogs(qapp, tmp_path):
    from tradingbacktester.ui.dialogs.about_dialog import AboutDialog, DocumentDialog

    about = AboutDialog(Workspace(tmp_path).ensure())
    about.show()
    qapp.processEvents()
    about.close()

    doc = DocumentDialog("Metrics", "METRICS.md")
    doc.show()
    qapp.processEvents()
    doc.close()

    # A missing document must explain itself, not show an empty window.
    missing = DocumentDialog("Nope", "NOT_A_REAL_DOCUMENT.md")
    assert "not installed" in missing.browser.toPlainText().lower()
    missing.close()


# --------------------------------------------------------------------------
# Import wizard
# --------------------------------------------------------------------------

def _csv(tmp_path, name: str, text: str) -> str:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


ROWS = "".join(f"2023-01-{d:02d} 09:30:00,100,101,99,100.5,1000\n" for d in range(1, 29))


@pytest.mark.parametrize("name,text", [
    ("plain.csv", "Date,Open,High,Low,Close,Volume\n" + ROWS),
    ("semicolon.csv", "Date;Open;High;Low;Close;Volume\n" + "".join(
        f"{d:02d}/01/2023 09:30;100,0;101,0;99,0;100,5;1000\n" for d in range(1, 29))),
    ("headerless.csv", "".join(
        f"2023-01-{d:02d},100.0,101.0,99.0,100.5,1000\n" for d in range(1, 29))),
    ("epoch_ms.csv", "timestamp,open,high,low,close,volume\n" + "".join(
        f"{1672651800000 + d * 3600000},100,101,99,100.5,1000\n" for d in range(1, 29))),
    ("split.csv", "Date,Time,Open,High,Low,Close,Volume\n" + "".join(
        f"2023-01-{d:02d},09:30:00,100,101,99,100.5,1000\n" for d in range(1, 29))),
    ("commented.csv", "# SYNTHETIC TEST DATA - NOT REAL MARKET DATA\n"
                      "Date,Open,High,Low,Close,Volume\n" + ROWS),
    ("novolume.csv", "Date,Open,High,Low,Close\n" + "".join(
        f"2023-01-{d:02d} 09:30:00,100,101,99,100.5\n" for d in range(1, 29))),
])
def test_import_wizard_validates_awkward_files(qapp, tmp_path, registry, name, text):
    from tradingbacktester.ui.dialogs.import_dialog import ImportWizard

    wizard = ImportWizard(registry)
    wizard._load_file(_csv(tmp_path, name, text))
    wizard._validate()
    assert wizard._validated, f"{name}: {wizard.status.text()}"
    assert wizard.timeframe is not None
    wizard.close()


def test_import_wizard_reports_a_bad_date_without_crashing(qapp, tmp_path, registry):
    from tradingbacktester.ui.dialogs.import_dialog import ImportWizard

    text = "Date,Open,High,Low,Close,Volume\n" + "".join(
        "31/02/2023 09:30,100,101,99,100.5,1000\n" for _ in range(28))
    wizard = ImportWizard(registry)
    wizard._load_file(_csv(tmp_path, "bad.csv", text))
    wizard._validate()
    assert not wizard._validated
    assert wizard.status.text()
    # The message must name the user's file, not a temporary one.
    assert "bad.csv" in wizard.status.text()
    wizard.close()


def test_import_wizard_ok_is_disabled_until_validated(qapp, tmp_path, registry):
    from tradingbacktester.ui.dialogs.import_dialog import ImportWizard

    wizard = ImportWizard(registry)
    assert not wizard.ok_button.isEnabled()
    wizard._load_file(_csv(tmp_path, "plain.csv",
                           "Date,Open,High,Low,Close,Volume\n" + ROWS))
    assert not wizard.ok_button.isEnabled()
    wizard._validate()
    assert wizard.ok_button.isEnabled()
    # Changing the mapping must invalidate it again.
    wizard._on_mapping_changed()
    assert not wizard.ok_button.isEnabled()
    wizard.close()


MT5_ROWS = "".join(
    f"2023.01.{d:02d} 09:30:00\t100.0\t101.0\t99.0\t100.5\t0\t{1000 + d}\n"
    for d in range(28, 0, -1))
MT5 = "DateTime\tOpen\tHigh\tLow\tClose\tVolume\tTickVolume\n" + MT5_ROWS


def _mapping_text(wizard) -> dict:
    return {key: box.currentText() for key, box in wizard._column_boxes.items()}


def test_import_wizard_repairs_a_scrambled_mapping(qapp, tmp_path, registry):
    """A mapping that does not match the file is corrected, not rejected.

    The combo values here are the ones a stray mouse wheel leaves behind: each
    box moved a step or two down its list.  The file is unchanged and still
    perfectly readable, so the dialog must read it.
    """
    from tradingbacktester.ui.dialogs.import_dialog import ImportWizard

    wizard = ImportWizard(registry)
    wizard._load_file(_csv(tmp_path, "5m_data.csv", MT5))
    assert _mapping_text(wizard)["close"] == "Close"

    for key, index in (("datetime", 4), ("high", 4), ("low", 4), ("close", 1)):
        wizard._column_boxes[key].setCurrentIndex(index)
    assert _mapping_text(wizard)["close"] == "DateTime"

    wizard._validate()
    assert wizard._validated, wizard.status.text()
    fixed = _mapping_text(wizard)
    assert fixed["datetime"] == "DateTime"
    assert (fixed["open"], fixed["high"], fixed["low"], fixed["close"]) == (
        "Open", "High", "Low", "Close")
    assert "corrected" in wizard.status.text().lower()
    wizard.close()


def test_import_wizard_auto_detect_button_rebuilds_the_mapping(qapp, tmp_path,
                                                               registry):
    from tradingbacktester.ui.dialogs.import_dialog import ImportWizard

    wizard = ImportWizard(registry)
    wizard._load_file(_csv(tmp_path, "5m_data.csv", MT5))
    for key in ("open", "high", "low", "close"):
        wizard._column_boxes[key].setCurrentIndex(0)
    assert _mapping_text(wizard)["close"] == "— none —"

    wizard._auto_detect()
    fixed = _mapping_text(wizard)
    assert (fixed["open"], fixed["high"], fixed["low"], fixed["close"]) == (
        "Open", "High", "Low", "Close")
    # An MT5 export writes zeros in Volume and the real figure in TickVolume.
    assert fixed["volume"] == "TickVolume"
    assert wizard._validated, wizard.status.text()
    wizard.close()


def test_import_wizard_imports_newest_first_rows_oldest_first(qapp, tmp_path,
                                                              registry):
    from tradingbacktester.data.csv_loader import load_csv
    from tradingbacktester.ui.dialogs.import_dialog import ImportWizard

    path = _csv(tmp_path, "5m_data.csv", MT5)
    wizard = ImportWizard(registry)
    wizard._load_file(path)
    wizard._validate()
    assert wizard._validated, wizard.status.text()
    bars = load_csv(path, wizard.mapping, wizard.instrument)
    assert bool(np.all(np.diff(bars.ts) > 0))
    assert float(bars.volume.sum()) > 0.0
    wizard.close()


def test_mapping_combo_ignores_the_mouse_wheel_unless_focused(qapp, tmp_path,
                                                              registry):
    """Scrolling a dialog must not silently rewrite the column mapping."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QWheelEvent

    from tradingbacktester.ui.dialogs.import_dialog import ImportWizard

    wizard = ImportWizard(registry)
    wizard._load_file(_csv(tmp_path, "plain.csv",
                           "Date,Open,High,Low,Close,Volume\n" + ROWS))
    box = wizard._column_boxes["close"]
    before = box.currentIndex()
    event = QWheelEvent(
        QPoint(5, 5), box.mapToGlobal(QPoint(5, 5)), QPoint(0, -120),
        QPoint(0, -120), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False)
    box.wheelEvent(event)
    assert box.currentIndex() == before
    assert not event.isAccepted()
    wizard.close()


def test_import_wizard_preview_names_the_mapped_field(qapp, tmp_path, registry):
    from tradingbacktester.ui.dialogs.import_dialog import ImportWizard

    wizard = ImportWizard(registry)
    wizard._load_file(_csv(tmp_path, "plain.csv",
                           "Date,Open,High,Low,Close,Volume\n" + ROWS))
    labels = [wizard.preview.horizontalHeaderItem(i).text()
              for i in range(wizard.preview.columnCount())]
    assert labels[0] == "Date\nDate/time"
    assert labels[4] == "Close\nClose"
    wizard.close()


def test_import_wizard_survives_a_junk_file(qapp, tmp_path, registry):
    from tradingbacktester.ui.dialogs.import_dialog import ImportWizard

    wizard = ImportWizard(registry)
    wizard._load_file(_csv(tmp_path, "junk.csv", "this is not a csv at all\n\n"))
    wizard._validate()
    assert not wizard._validated
    wizard.close()


# --------------------------------------------------------------------------
# Instruments
# --------------------------------------------------------------------------

def test_instrument_dialog_edits_and_persists(qapp, tmp_path):
    from tradingbacktester.ui.dialogs.instrument_dialog import InstrumentDialog

    path = tmp_path / "instruments.json"
    registry = InstrumentRegistry(path)
    dialog = InstrumentDialog(registry)
    dialog.show()
    qapp.processEvents()
    assert dialog.list.count() >= 10

    symbol = dialog._current
    dialog.form.editor("point_value").setValue(33.0)
    qapp.processEvents()
    assert registry.get(symbol).point_value == pytest.approx(33.0)
    assert InstrumentRegistry(path).get(symbol).point_value == pytest.approx(33.0)
    dialog.close()


def test_instrument_dialog_reports_a_bad_value_inline(qapp, tmp_path):
    from tradingbacktester.ui.dialogs.instrument_dialog import InstrumentDialog

    registry = InstrumentRegistry(tmp_path / "instruments.json")
    dialog = InstrumentDialog(registry)
    dialog.show()
    qapp.processEvents()
    before = registry.get(dialog._current).tick_size

    dialog.form.editor("tick_size").setValue(0.0)
    qapp.processEvents()
    assert dialog.error.text(), "an impossible tick size must be reported"
    assert registry.get(dialog._current).tick_size == pytest.approx(before)

    dialog.form.editor("tick_size").setValue(0.25)
    qapp.processEvents()
    assert dialog.error.text() == ""
    dialog.close()


# --------------------------------------------------------------------------
# Strategy editor
# --------------------------------------------------------------------------

def test_strategy_editor_builds_the_worked_example(qapp, bars):
    """The specification's example, assembled through the editor's own API."""
    from tradingbacktester.indicators.base import ParamSpec
    from tradingbacktester.strategy.spec import (Compare, Cross, Ind,
                                                 IndicatorSlot, Param,
                                                 StrategySpec)
    from tradingbacktester.ui.dialogs.strategy_editor import StrategyEditor

    spec = StrategySpec(name="Built By Hand")
    editor = StrategyEditor(spec, bars=bars)
    qapp.processEvents()

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
    editor._reload_params()
    editor._reload_slots()

    editor.rule_box.setCurrentIndex(0)
    editor._reload_tree()
    editor._current_root().children.extend([
        Cross(Ind("emaFast"), "above", Ind("emaSlow")),
        Compare(Ind("rsi"), ">", Param("rsi_level")),
    ])
    editor.rule_box.setCurrentIndex(1)
    editor._reload_tree()
    editor._current_root().children.append(
        Cross(Ind("emaFast"), "below", Ind("emaSlow")))
    editor._reload_tree()

    editor.risk_panel.exit_form.set_value("stop_loss_enabled", True)
    editor.risk_panel.exit_form.set_value("stop_loss_value", 1.5)
    editor.risk_panel.exit_form.set_value("take_profit_enabled", True)
    editor.risk_panel.exit_form.set_value("take_profit_value", 3.0)
    editor._collect()

    assert spec.validate() == []
    assert spec.entry_long.describe() == \
        "emaFast crosses above emaSlow AND rsi > $rsi_level"
    assert spec.exit_long.describe() == "emaFast crosses below emaSlow"
    assert spec.exits.stop_loss_value == pytest.approx(1.5)
    assert spec.exits.take_profit_value == pytest.approx(3.0)

    config = BacktestConfig(starting_capital=100_000.0)
    config.warmup_bars = spec.warmup_bars()
    config.exits = spec.exits
    result = Backtester(bars, spec, config).run()
    assert result.metrics["total_trades"] >= 0
    editor.close()


def test_strategy_editor_preview_counts_signals(qapp, bars):
    from tradingbacktester.ui.dialogs.strategy_editor import StrategyEditor

    editor = StrategyEditor(BUILTIN_STRATEGIES["MACD Trend"](), bars=bars)
    qapp.processEvents()
    editor._preview()
    text = editor.message.text()
    assert "Long entry" in text and "warm-up" in text
    editor.close()


def test_strategy_editor_preview_does_not_mention_undefined_rules(qapp, bars):
    """A rule that does not exist must not be reported as never firing."""
    from tradingbacktester.ui.dialogs.strategy_editor import StrategyEditor

    editor = StrategyEditor(BUILTIN_STRATEGIES["EMA Cross + RSI"](), bars=bars)
    qapp.processEvents()
    editor._preview()
    assert "Short entry" not in editor.message.text()
    editor.close()


def test_strategy_editor_renaming_an_indicator_updates_the_rules(qapp, bars):
    from tradingbacktester.ui.dialogs.strategy_editor import StrategyEditor

    spec = BUILTIN_STRATEGIES["EMA Cross + RSI"]()
    editor = StrategyEditor(spec, bars=bars)
    qapp.processEvents()
    old = spec.indicators[0].ref
    editor._rename_slot(0, "fastLine")
    assert spec.indicators[0].ref == "fastLine"
    assert old not in spec.entry_long.describe()
    assert "fastLine" in spec.entry_long.describe()
    assert spec.validate() is not None
    editor.close()


def test_strategy_editor_loads_every_builtin(qapp, bars):
    from tradingbacktester.ui.dialogs.strategy_editor import StrategyEditor

    for name, factory in BUILTIN_STRATEGIES.items():
        editor = StrategyEditor(factory(), bars=bars)
        qapp.processEvents()
        for tab in range(editor.tabs.count()):
            editor.tabs.setCurrentIndex(tab)
            qapp.processEvents()
        editor.close()


# --------------------------------------------------------------------------
# Browser, dataset manager, quality, comparison
# --------------------------------------------------------------------------

def test_backtest_browser_lists_and_guards_selection(qapp, tmp_path, bars):
    from tradingbacktester.ui.dialogs.backtest_browser import BacktestBrowser

    workspace = Workspace(tmp_path / "ws").ensure()
    store = BacktestStore(workspace)
    store.save(run_once(bars), "Run A")
    store.save(run_once(bars, "Bollinger Breakout"), "Run B")
    # A corrupt run folder must be listed, not fatal.
    broken = Path(workspace.backtests) / "broken"
    broken.mkdir(parents=True, exist_ok=True)
    (broken / "meta.json").write_text("{oops", encoding="utf-8")

    dialog = BacktestBrowser(store, multi=True)
    dialog.show()
    qapp.processEvents()
    assert dialog.table.rowCount() == 3
    dialog.table.selectRow(0)
    qapp.processEvents()
    assert not dialog.ok_button.isEnabled(), "one run is not a comparison"
    dialog.table.selectAll()
    qapp.processEvents()
    assert dialog.ok_button.isEnabled()
    dialog.close()


def test_dataset_manager_and_quality_dialogs(qapp, tmp_path, bars):
    from tradingbacktester.ui.dialogs.dataset_manager import DatasetManagerDialog
    from tradingbacktester.ui.dialogs.quality_dialog import DataQualityDialog

    workspace = Workspace(tmp_path / "ws").ensure()
    repo = DatasetRepository(workspace)
    repo.add_from_bars(bars, name="NQ hourly")
    manager = DatasetManagerDialog(repo)
    manager.show()
    qapp.processEvents()
    manager.close()

    broken = generate_sample_data("NQ", "1h", n_bars=400, seed=3)
    broken.high[10] = broken.low[10] - 5.0
    broken.ts[20] = broken.ts[19]
    report = validate_bars(broken)
    assert not report.is_usable
    dialog = DataQualityDialog(report)
    dialog.show()
    qapp.processEvents()
    dialog.close()


def test_comparison_view_with_two_runs(qapp, bars):
    from tradingbacktester.ui.widgets.comparison_view import ComparisonView

    view = ComparisonView()
    view.resize(1000, 700)
    view.set_results([run_once(bars), run_once(bars, "Bollinger Breakout")])
    view.show()
    qapp.processEvents()
    assert view.table.rowCount() > 5
    assert view.table.columnCount() == 2
    view.set_results([])            # the empty case must not raise
    qapp.processEvents()
    view.close()


def test_optimizer_dialog_runs_a_small_sweep(qapp, bars):
    import time

    from tradingbacktester.ui.dialogs.optimizer_dialog import OptimizerDialog

    spec = BUILTIN_STRATEGIES["EMA Cross + RSI"]()
    dialog = OptimizerDialog(bars, spec, BacktestConfig(starting_capital=100_000.0))
    dialog.show()
    qapp.processEvents()
    # Keep the grid tiny so the test stays quick.
    for row in dialog._rows:
        row["enabled"].setChecked(row["param"].name in ("ema_fast", "ema_slow"))
    dialog._rows[0]["start"].setValue(10)
    dialog._rows[0]["stop"].setValue(20)
    dialog._rows[0]["step"].setValue(5)
    dialog._rows[1]["start"].setValue(40)
    dialog._rows[1]["stop"].setValue(60)
    dialog._rows[1]["step"].setValue(20)
    dialog.min_trades.setValue(0)
    qapp.processEvents()
    assert "combinations" in dialog.count_label.text()

    dialog._run()
    deadline = time.monotonic() + 180
    while dialog._runner.busy and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.02)
    for _ in range(10):
        qapp.processEvents()

    assert dialog.table.rowCount() == 6
    assert dialog.note.text(), "the overfitting note is a requirement"
    assert "combinations" in dialog.note.text()
    dialog.table.selectRow(0)
    dialog._apply_selected()
    assert dialog.chosen_params
    assert set(dialog.chosen_params) == {"ema_fast", "ema_slow"}
    dialog.close()


def test_optimizer_walk_forward_tab_runs_over_the_same_grid(qapp, bars):
    """The tab reads the sweep's own ranges, so both halves test one strategy."""
    import time

    from tradingbacktester.ui.dialogs.optimizer_dialog import OptimizerDialog

    spec = BUILTIN_STRATEGIES["EMA Cross + RSI"]()
    dialog = OptimizerDialog(bars, spec, BacktestConfig(starting_capital=100_000.0))
    dialog.show()
    qapp.processEvents()
    for row in dialog._rows:
        row["enabled"].setChecked(row["param"].name == "ema_fast")
    dialog._rows[0]["start"].setValue(10)
    dialog._rows[0]["stop"].setValue(20)
    dialog._rows[0]["step"].setValue(10)
    dialog.min_trades.setValue(1)
    qapp.processEvents()

    panel = dialog.walkforward
    assert [r.name for r in panel._ranges_fn()] == ["ema_fast"]
    panel.folds.setValue(3)
    panel.run()
    deadline = time.monotonic() + 240
    while panel.busy and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.02)
    for _ in range(10):
        qapp.processEvents()

    assert panel.table.rowCount() == 3
    assert "Out of sample:" in panel.headline.text()
    assert "not chosen with hindsight" in panel.notes.text()
    # Every window names the parameters it chose, or says why it produced none.
    for row in range(3):
        chosen = panel.table.item(row, 6).text()
        reason = panel.table.item(row, 3).text()
        assert "ema_fast=" in chosen or "trades" in reason
    dialog.close()


def test_monte_carlo_dialog_resamples_the_loaded_run(qapp, bars):
    import time

    from tradingbacktester.ui.dialogs.montecarlo_dialog import MonteCarloDialog

    run = run_once(bars)
    assert run.trades

    dialog = MonteCarloDialog(run)
    dialog.show()
    qapp.processEvents()
    assert "cannot tell you" not in dialog.headline.text()
    dialog.draws.setValue(500)
    index = dialog.method.findData("bootstrap")
    dialog.method.setCurrentIndex(index)
    qapp.processEvents()
    assert "with replacement" in dialog.method_help.text()

    dialog.run()
    deadline = time.monotonic() + 120
    while dialog.busy and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    for _ in range(10):
        qapp.processEvents()

    assert dialog.table.rowCount() == 4
    assert dialog.table.item(0, 0).text() == "Final equity"
    assert dialog.table.item(0, 3).text(), "the median column must be filled in"
    assert "of draws lost money" in dialog.headline.text()
    assert "cannot tell you whether the strategy has an edge" in dialog.notes.text()
    # The histogram must render without a paint error.
    dialog.histogram.repaint()
    qapp.processEvents()
    dialog.close()


def test_monte_carlo_dialog_says_so_when_there_are_no_trades(qapp, bars,
                                                             monkeypatch):
    from tradingbacktester.engine.results import BacktestResult
    from tradingbacktester.ui.dialogs.montecarlo_dialog import MonteCarloDialog

    said = []
    monkeypatch.setattr(
        "tradingbacktester.ui.dialogs.montecarlo_dialog.show_info",
        lambda parent, title, message: said.append(message))
    dialog = MonteCarloDialog(BacktestResult())
    dialog.run()
    qapp.processEvents()
    assert said and "nothing to resample" in said[0]
    assert not dialog.busy
    dialog.close()


def test_mirror_dialog_runs_both_series(qapp, bars):
    import time

    from tradingbacktester.ui.dialogs.mirror_dialog import MirrorDialog

    spec = BUILTIN_STRATEGIES["MACD Trend"]()
    config = BacktestConfig(starting_capital=100_000.0)
    config.exits, config.execution = spec.exits, spec.execution
    config.session, config.costs, config.risk = spec.session, spec.costs, spec.risk

    dialog = MirrorDialog(bars, spec, config)   # runs on construction
    dialog.show()
    deadline = time.monotonic() + 180
    while dialog.busy and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.02)
    for _ in range(10):
        qapp.processEvents()

    assert dialog.table.item(0, 0).text() == "Drift over the sample"
    real_drift = dialog.table.item(0, 1).text()
    mirror_drift = dialog.table.item(0, 2).text()
    assert real_drift.startswith("+") and mirror_drift.startswith("-")
    assert dialog.table.item(2, 0).text() == "Net profit"
    assert dialog.table.item(2, 2).text(), "the mirrored column must be filled in"
    assert "Direction-independent half" in dialog.split.text()
    assert "control, not a second sample" in dialog.notes.text()
    assert dialog.headline.text().endswith(".")
    dialog.close()


def test_mirror_test_needs_data_and_a_strategy(window, qapp, monkeypatch):
    said = []
    monkeypatch.setattr("tradingbacktester.ui.main_window.show_info",
                        lambda parent, title, message: said.append(message))
    window._view_bars = None
    window.on_mirror_test()
    assert said and "Load a dataset" in said[0]


def test_walk_forward_tab_refuses_an_empty_grid(qapp, bars, monkeypatch):
    """Nothing to choose is a message, not a crash and not a fake result."""
    from tradingbacktester.ui.dialogs.optimizer_dialog import OptimizerDialog

    said = []
    monkeypatch.setattr(
        "tradingbacktester.ui.widgets.walkforward_panel.show_info",
        lambda parent, title, message: said.append(message))

    spec = BUILTIN_STRATEGIES["EMA Cross + RSI"]()
    dialog = OptimizerDialog(bars, spec, BacktestConfig(starting_capital=100_000.0))
    for row in dialog._rows:
        row["enabled"].setChecked(False)
    qapp.processEvents()
    dialog.walkforward.run()
    qapp.processEvents()
    assert said and "at least one parameter" in said[0]
    assert not dialog.walkforward.busy
    dialog.close()


# --------------------------------------------------------------------------
# The assembled window
# --------------------------------------------------------------------------

@pytest.fixture
def window(qapp, tmp_path):
    from tradingbacktester.logging_setup import configure_logging
    from tradingbacktester.storage.workspace import bootstrap
    from tradingbacktester.ui.main_window import MainWindow

    settings = AppSettings()
    settings.workspace_dir = str(tmp_path / "ws")
    workspace = bootstrap(settings)
    log_file = configure_logging(workspace.logs, "INFO", console=False)
    win = MainWindow(settings, workspace, log_file)
    win.resize(1500, 900)
    win._first_run()
    qapp.processEvents()
    yield win
    win.close()


def test_window_opens_with_data_and_a_strategy(window, qapp):
    assert window.datasets.list(), "the samples must be imported on first run"
    assert window.strategies.list(), "the built-ins must be seeded on first run"
    assert window._view_bars is not None
    assert window._spec is not None


def test_window_runs_a_backtest_end_to_end(window, qapp):
    import time

    window.on_run_backtest()
    deadline = time.monotonic() + 180
    while window._runner.busy and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.02)
    for _ in range(10):
        qapp.processEvents()

    result = window._result
    assert result is not None
    assert result.metrics["total_trades"] == len(result.trades)
    assert window.trade_table.model.rowCount() == len(result.trades)
    assert len(window.chart._trades) == len(result.trades)


def test_switching_strategy_keeps_the_cost_settings(window, qapp):
    """Silently zeroing costs would flatter every subsequent run."""
    window.risk_panel.cost_form.set_value("commission_value", 2.10)
    window.risk_panel.cost_form.set_value("spread_points", 0.25)
    qapp.processEvents()
    for name in ("Bollinger Breakout", "MACD Trend", "EMA Cross + RSI"):
        index = window.strategy_panel.strategy_box.findText(name)
        if index < 0:
            continue
        window.strategy_panel.strategy_box.setCurrentIndex(index)
        qapp.processEvents()
        costs = window.risk_panel.build_config().costs
        assert costs.commission_value == pytest.approx(2.10), name
        assert costs.spread_points == pytest.approx(0.25), name


def test_switching_dataset_resets_the_timeframe(window, qapp):
    """Keeping the previous dataset's timeframe silently resamples the new one."""
    metas = window.datasets.list()
    if len(metas) < 2:
        pytest.skip("needs two sample datasets")
    for meta in metas:
        index = window.data_panel.dataset_box.findData(meta.id)
        window.data_panel.dataset_box.setCurrentIndex(index)
        qapp.processEvents()
        assert window.data_panel.current_timeframe().label == meta.timeframe, meta.name


def test_monte_carlo_is_offered_only_once_there_are_trades(window, qapp,
                                                           monkeypatch):
    """A menu item that opens an empty dialog is worse than a disabled one."""
    import time

    assert not window.act_montecarlo.isEnabled()
    said = []
    monkeypatch.setattr("tradingbacktester.ui.main_window.show_info",
                        lambda parent, title, message: said.append(message))
    window.on_monte_carlo()
    assert said and "nothing to resample" in said[0]

    window.on_run_backtest()
    deadline = time.monotonic() + 180
    while window._runner.busy and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.02)
    for _ in range(10):
        qapp.processEvents()
    assert window._result is not None and window._result.trades
    assert window.act_montecarlo.isEnabled()


def test_window_survives_selecting_every_strategy(window, qapp):
    for row in range(window.strategy_panel.strategy_box.count()):
        window.strategy_panel.strategy_box.setCurrentIndex(row)
        qapp.processEvents()
        assert window._spec is not None


# --------------------------------------------------------------------------
# Find Strategies
# --------------------------------------------------------------------------

def test_finder_dialog_offers_the_shipped_data(qapp, tmp_path, registry):
    from tradingbacktester.config import Workspace
    from tradingbacktester.strategy.storage import StrategyStore
    from tradingbacktester.ui.dialogs.finder_dialog import FinderDialog

    workspace = Workspace(tmp_path).ensure()
    dialog = FinderDialog(DatasetRepository(workspace), registry,
                          StrategyStore(workspace))
    offered = [dialog.dataset_box.itemText(i)
               for i in range(dialog.dataset_box.count())]
    assert any("US30 30m" in text for text in offered)
    assert len(dialog._style_buttons) == 4
    # Day trading is the default: it is the style most people mean.
    assert dialog._selected_style().key == "intraday"
    dialog.close()


def test_finder_dialog_shows_a_result_and_can_save_it(qapp, tmp_path, registry):
    from tradingbacktester.config import Workspace
    from tradingbacktester.finder import find_strategies
    from tradingbacktester.strategy.storage import StrategyStore
    from tradingbacktester.ui.dialogs.finder_dialog import FinderDialog

    workspace = Workspace(tmp_path).ensure()
    store = StrategyStore(workspace)
    dialog = FinderDialog(DatasetRepository(workspace), registry, store)
    for i in range(dialog.dataset_box.count()):
        if "US30 30m" in dialog.dataset_box.itemText(i):
            dialog.dataset_box.setCurrentIndex(i)
            break
    bars = dialog._load_bars()
    assert len(bars) > 1000

    report = find_strategies(bars, dialog._selected_style(), control_draws=50)
    dialog._running = "strategies"
    dialog._on_finished(report)
    qapp.processEvents()
    table = dialog._tables["strategies"]
    assert table.rowCount() == len(report.shortlist)
    # Whatever the verdict, the multiplicity has to be on screen.
    assert f"{report.combinations:,} combinations" in dialog.status.text()
    assert "not a prediction" in dialog._details["strategies"].toPlainText()

    if report.shortlist and report.shortlist[0].spec is not None:
        table.selectRow(0)
        qapp.processEvents()
        assert dialog.save_button.isEnabled()
        dialog._save_selected()
        assert store.list(), "the saved strategy did not reach the workspace"
        assert "not a recommendation" in dialog.status.text()
    dialog.close()


def test_finder_dialog_runs_all_three_studies(qapp, tmp_path, registry):
    """One dialog, three questions, and each of them fills its own tab."""
    from tradingbacktester.config import Workspace
    from tradingbacktester.finder import find_strategies
    from tradingbacktester.research import scan, study_features
    from tradingbacktester.strategy.storage import StrategyStore
    from tradingbacktester.ui.dialogs.finder_dialog import (STUDIES,
                                                            FinderDialog)

    workspace = Workspace(tmp_path).ensure()
    dialog = FinderDialog(DatasetRepository(workspace), registry,
                          StrategyStore(workspace))
    assert [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())] == \
        [label for _key, label, _q in STUDIES]

    for i in range(dialog.dataset_box.count()):
        if "US30 30m" in dialog.dataset_box.itemText(i):
            dialog.dataset_box.setCurrentIndex(i)
            break
    bars = dialog._load_bars()
    chosen = dialog._selected_style()

    runs = {
        "strategies": lambda: find_strategies(bars, chosen, control_draws=50),
        "indicators": lambda: study_features(bars, chosen),
        "anomalies": lambda: scan(bars, chosen, control_draws=50),
    }
    for index, (key, _label, _question) in enumerate(STUDIES):
        dialog.tabs.setCurrentIndex(index)
        dialog._running = key
        dialog._on_finished(runs[key]())
        qapp.processEvents()
        assert dialog.status.text(), f"{key} said nothing"
        assert dialog._details[key].toPlainText(), f"{key} has no detail text"
        table = dialog._tables[key]
        if table.rowCount():
            table.selectRow(0)
            qapp.processEvents()
            assert dialog._details[key].toPlainText()
        # Only a found strategy can be saved; the other two are studies.
        assert dialog.save_button.isEnabled() == (
            key == "strategies" and table.rowCount() > 0)
    dialog.close()


# --------------------------------------------------------------------------
# Simple mode and the guided start
# --------------------------------------------------------------------------

@pytest.fixture
def window(qapp, tmp_path):
    from tradingbacktester.config import AppSettings, Workspace
    from tradingbacktester.ui.main_window import MainWindow

    workspace = Workspace(tmp_path).ensure()
    settings = AppSettings()
    settings.workspace_dir = str(tmp_path)
    win = MainWindow(settings, workspace)
    win.show()
    qapp.processEvents()
    yield win
    win.close()


def test_simple_mode_hides_the_advanced_surfaces(window, qapp):
    assert window.act_simple.isChecked(), "simple mode should be the default"
    tabs = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert "Comparison" not in tabs
    assert not window.risk_panel.isVisible()
    assert window.bottom_tabs.tabText(0) == "Trades"
    assert window.bottom_tabs.isTabVisible(0)
    assert not window.bottom_tabs.isTabVisible(1)

    window.act_simple.setChecked(False)
    qapp.processEvents()
    tabs = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert "Comparison" in tabs
    assert window.risk_panel.isVisible()
    assert all(window.bottom_tabs.isTabVisible(i)
               for i in range(window.bottom_tabs.count()))

    # And back again, because a toggle that only works once is not a toggle.
    window.act_simple.setChecked(True)
    qapp.processEvents()
    assert "Comparison" not in [window.tabs.tabText(i)
                                for i in range(window.tabs.count())]


def test_the_app_opens_on_real_data_not_synthetic(window):
    assert window._bars is not None, "nothing was loaded on first run"
    assert window._bars.instrument.symbol == "US30"
    assert len(window._bars) > 10_000
    names = [m.name for m in window.datasets.list()]
    assert "US30 30m" in names
    # The half-million-bar file must NOT be imported at start-up: it takes
    # twenty seconds and this is someone's first impression.
    assert "US30 5m" not in names


def test_the_start_guide_ticks_itself_off(window, qapp):
    steps = [label.text() for label in window.start_here._steps]
    assert steps[0].startswith("✓"), "data was loaded but step one is not ticked"
    window.on_run_backtest()
    for _ in range(200):
        qapp.processEvents()
        if window._result is not None:
            break
    assert window._result is not None
    qapp.processEvents()
    assert not window.start_here.isVisible(), "the guide should hide when done"


def test_start_here_can_be_dismissed_and_restored(window, qapp):
    window.start_here._dismiss()
    qapp.processEvents()
    assert not window.start_here.isVisible()
    assert window.settings.show_start_here is False
    window.on_show_start_here()
    qapp.processEvents()
    assert window.start_here.isVisible()
    assert window.settings.show_start_here is True


# --------------------------------------------------------------------------
# Start-up: a launch that shows nothing is indistinguishable from a hang
# --------------------------------------------------------------------------

def test_the_splash_appears_before_the_workspace_is_built(qapp):
    """Seeding the workspace writes files; nothing was on screen for any of it."""
    from tradingbacktester import app as application

    splash = application._splash(qapp)
    assert splash is not None
    assert splash.isVisible()
    assert splash.pixmap().width() > 200, "a splash nobody can read is not one"
    application._say(qapp, splash, "Preparing your workspace…")
    qapp.processEvents()
    assert splash.isVisible()
    application._close_splash(splash, None)
    qapp.processEvents()
    assert not splash.isVisible()


def test_the_splash_is_never_a_reason_to_fail_a_launch(qapp, monkeypatch):
    """A cosmetic window that cannot be built must not stop the application."""
    from tradingbacktester import app as application

    monkeypatch.setattr("tradingbacktester.ui.icons.app_icon",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no")))
    assert application._splash(qapp) is None
    # And every helper tolerates the None it just got handed.
    application._say(qapp, None, "still starting")
    application._close_splash(None, None)


def test_first_run_reports_each_step_and_logs_its_timings(window, qapp, caplog):
    """A window that paints once and then stops answering reads as a freeze."""
    import logging

    said = []
    window.status = lambda message="", *a, **k: said.append(message)
    with caplog.at_level(logging.INFO, logger="tradingbacktester.ui.main_window"):
        window._first_run()
    qapp.processEvents()

    assert any("workspace" in s.lower() for s in said), said
    assert any("chart" in s.lower() for s in said), said
    logged = [r.getMessage() for r in caplog.records]
    assert any("First run:" in m for m in logged)
    assert any("First run finished in" in m for m in logged)


def test_the_self_test_now_actually_starts_the_window():
    """It used to only import the class, so a hang on startup passed CI."""
    import inspect

    from tradingbacktester.app import SELF_TEST_STARTUP_BUDGET, self_test

    source = inspect.getsource(self_test)
    assert "MainWindow(settings, workspace" in source, \
        "the self-test must construct the window, not just import the class"
    assert "_first_run()" in source
    assert SELF_TEST_STARTUP_BUDGET > 0


def test_startup_breadcrumbs_land_somewhere_findable(tmp_path, monkeypatch):
    """A launch that stalls before the workspace exists left no trace at all."""
    from tradingbacktester.logging_setup import breadcrumb, startup_log_path

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    target = startup_log_path()
    assert target.parent.is_dir()
    breadcrumb("first line")
    breadcrumb("second line")
    written = target.read_text(encoding="utf-8").splitlines()
    assert len(written) == 2
    assert written[0].endswith("first line")
    assert written[1].endswith("second line")
    # Each call opens, writes and closes: a process killed with the Task
    # Manager must not lose the line saying where it was.
    assert "second line" in target.read_text(encoding="utf-8")


def test_a_breadcrumb_never_raises(tmp_path, monkeypatch):
    """It runs on the failure path; it must not become the failure."""
    from tradingbacktester.logging_setup import breadcrumb, startup_log_path

    # A file where a directory is expected: mkdir raises, and the fallback to
    # the temp directory has to absorb it.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(blocker))
    assert startup_log_path().parent.is_dir()
    breadcrumb("this must not raise")

    # And when the path itself cannot be worked out at all.
    def boom():
        raise RuntimeError("no path")

    monkeypatch.setattr("tradingbacktester.logging_setup.startup_log_path", boom)
    breadcrumb("nor must this")              # no assertion: not raising is it


def test_startup_falls_back_to_temp_without_localappdata(monkeypatch):
    import tempfile

    from tradingbacktester.logging_setup import startup_log_path

    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    assert startup_log_path().parent == Path(tempfile.gettempdir())


def test_the_smoke_test_reports_whether_the_window_painted(qapp, tmp_path,
                                                           monkeypatch):
    """`--self-test` forces the offscreen platform and so cannot tell.

    This is the check that exercises whatever platform plugin the machine
    actually has, which is where a white-screen report lives.
    """
    from tradingbacktester.app import SMOKE_SECONDS, _smoke

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr("tradingbacktester.app.SMOKE_SECONDS", 0.2)

    class Painted:
        def isVisible(self): return True
        def width(self): return 1200
        def height(self): return 800
        def close(self): pass

    class Blank:
        def isVisible(self): return False
        def width(self): return 0
        def height(self): return 0
        def close(self): pass

    assert _smoke(qapp, Painted()) == 0
    assert _smoke(qapp, Blank()) == 1
    assert SMOKE_SECONDS > 0

    crumbs = (tmp_path / "TradingBacktester" / "startup.log").read_text("utf-8")
    assert "window is visible at 1200x800" in crumbs
    assert "painted=False" in crumbs
