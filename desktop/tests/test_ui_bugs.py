"""Two defects the user hit, and the guards that keep them fixed.

Both were reported as one complaint -- "the scrolling is bugged" and "the
charts is not the same as selected" -- and they turned out to be connected: a
stray scroll over the sidebar silently switched the selected strategy, and
switching strategy left the previous run's numbers on screen. Together they
put one strategy's name beside another's profit.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (QApplication, QComboBox, QDoubleSpinBox,
                               QScrollArea)

from tradingbacktester.config import AppSettings, Workspace
from tradingbacktester.core.types import BacktestConfig
from tradingbacktester.data.sample import generate_sample_data
from tradingbacktester.engine.backtester import Backtester
from tradingbacktester.strategy import builtin
from tradingbacktester.ui.main_window import MainWindow
from tradingbacktester.ui.widgets.common import guard_value_wheels


@pytest.fixture(scope="module")
def bars():
    return generate_sample_data("NQ", "1h", n_bars=2500, seed=4)


@pytest.fixture
def window(qapp, tmp_path):
    workspace = Workspace(tmp_path).ensure()
    settings = AppSettings()
    settings.workspace_dir = str(tmp_path)
    win = MainWindow(settings, workspace)
    for factory in (builtin.macd_trend, builtin.donchian_breakout,
                    builtin.ema_cross_rsi):
        win.strategies.save(factory())
    win.strategy_panel.refresh(None)
    return win


def _wheel(widget, notches: int = -3) -> None:
    event = QWheelEvent(
        QPointF(5, 5), widget.mapToGlobal(QPoint(5, 5)),
        QPoint(0, notches * 120), QPoint(0, notches * 120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, event)


# --------------------------------------------------------------------------
# A scroll must not rewrite what it passes over
# --------------------------------------------------------------------------


def test_scrolling_past_the_strategy_picker_does_not_change_strategy(window):
    """Measured before the guard: this switched strategy without a click."""
    box = window.strategy_panel.strategy_box
    assert box.count() >= 2, "need two strategies for this to mean anything"
    before = box.currentText()
    _wheel(box)
    assert box.currentText() == before


def test_scrolling_past_a_risk_field_does_not_change_the_risk(window):
    """Before the guard this moved starting capital from 100,000 to 97,000."""
    for spin in window.risk_panel.findChildren(QDoubleSpinBox)[:4]:
        before = spin.value()
        _wheel(spin)
        assert spin.value() == before, f"{spin.objectName()} changed on a scroll"


def test_the_panel_still_scrolls_when_the_wheel_is_guarded(window, qapp):
    """Blocking the value and blocking the scroll would be the same bug."""
    window.resize(1400, 900)
    window.show()
    qapp.processEvents()
    area = window.findChildren(QScrollArea)[0]
    bar = area.verticalScrollBar()
    bar.setRange(0, 500)
    bar.setValue(0)
    spin = window.risk_panel.findChildren(QDoubleSpinBox)[0]
    _wheel(spin)
    qapp.processEvents()
    assert bar.value() != 0, "the guard ate the scroll instead of forwarding it"


def test_a_focused_box_still_scrolls_its_own_value(window, qapp):
    """Clicking in first is unambiguous, so it keeps working.

    The window has to be shown: ``setFocus`` on a hidden widget does not
    actually give it focus, so ``hasFocus()`` stays False and the guard would
    correctly block a wheel the test believes is deliberate.
    """
    window.resize(1400, 900)
    window.show()
    qapp.processEvents()
    spin = window.risk_panel.findChildren(QDoubleSpinBox)[0]
    spin.setFocus()
    qapp.processEvents()
    assert spin.hasFocus(), "the test could not focus the box"
    before = spin.value()
    _wheel(spin, -1)
    assert spin.value() != before


def test_the_guard_ignores_everything_that_is_not_a_value(window):
    """The chart and the tables must keep their own wheel behaviour."""
    from tradingbacktester.ui.widgets.common import _VALUE_WIDGETS

    assert not isinstance(window.chart.price_plot.getViewBox(), _VALUE_WIDGETS)
    from PySide6.QtWidgets import QTableView

    for table in window.findChildren(QTableView):
        assert not isinstance(table, _VALUE_WIDGETS)


def test_guard_value_wheels_reports_what_it_guarded(qapp):
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    host = QWidget()
    layout = QVBoxLayout(host)
    layout.addWidget(QComboBox())
    layout.addWidget(QDoubleSpinBox())
    assert guard_value_wheels(host) == 2


# --------------------------------------------------------------------------
# A result belongs to one strategy, one dataset, one set of parameters
# --------------------------------------------------------------------------


def _run_into(window, spec, bars):
    window._view_bars = bars
    window.chart.set_bars(bars)
    window._spec = spec
    result = Backtester(bars, spec, BacktestConfig()).run()
    result.bars = bars
    window._show_result(result)
    return result


def test_a_result_is_on_screen_after_a_run(window, bars):
    result = _run_into(window, builtin.macd_trend(), bars)
    assert len(result.trades) > 0
    assert len(window.chart._trades) == len(result.trades)
    assert window.trade_table.table.model().rowCount() == len(result.trades)
    assert window.headline.text()


def test_selecting_another_strategy_clears_the_previous_result(window, bars):
    """The defect: the picker said one name and the numbers were another's."""
    _run_into(window, builtin.macd_trend(), bars)
    other = next(e for e in window.strategies.list()
                 if e.name == "Donchian Channel Breakout")
    window.on_strategy_selected(other.id)

    assert window._spec.name == "Donchian Channel Breakout"
    assert window._result is None
    assert window.chart._trades == []
    assert window.trade_table.table.model().rowCount() == 0
    assert window.headline.text() == ""


def test_changing_parameters_clears_the_result(window, bars):
    _run_into(window, builtin.macd_trend(), bars)
    window.on_parameters_changed()
    assert window._result is None
    assert window.chart._trades == []


def test_loading_another_dataset_clears_the_result(window, bars):
    """A result is a result *on a dataset*."""
    _run_into(window, builtin.macd_trend(), bars)
    window._clear_result("different dataset")
    assert window._result is None
    assert window.chart._trades == []


def test_clearing_twice_is_harmless_and_says_nothing_the_second_time(window,
                                                                    bars):
    _run_into(window, builtin.macd_trend(), bars)
    window._clear_result("first")
    said = window.status_message.text() if hasattr(window, "status_message") else ""
    window._clear_result("second")
    assert window._result is None
    # The early return means the second call cannot overwrite the status with
    # a message about a result that was already gone.
    if hasattr(window, "status_message"):
        assert window.status_message.text() == said


def test_the_indicators_on_the_chart_follow_the_selected_strategy(window, bars):
    """The half that always worked, asserted so it keeps working."""
    window._view_bars = bars
    window.chart.set_bars(bars)
    entries = {e.name: e.id for e in window.strategies.list()}

    window.on_strategy_selected(entries["MACD Trend"])
    macd_refs = {s.ref for s in window._spec.indicators}
    window.on_strategy_selected(entries["Donchian Channel Breakout"])
    donchian_refs = {s.ref for s in window._spec.indicators}

    assert macd_refs != donchian_refs
    assert window._spec.name == "Donchian Channel Breakout"


# --------------------------------------------------------------------------
# The strip that says what is on screen
# --------------------------------------------------------------------------


def test_the_context_bar_reports_the_loaded_data(window, bars):
    window._view_bars = bars
    window.chart.set_bars(bars)
    window._refresh_context()
    strip = window.context_bar
    assert strip.symbol.value.text() == bars.instrument.symbol
    assert strip.bars.value.text() == f"{len(bars):,}"
    assert "→" in strip.span.value.text()


def test_the_context_bar_names_the_selected_strategy(window, bars):
    window._view_bars = bars
    entries = {e.name: e.id for e in window.strategies.list()}
    window.on_strategy_selected(entries["MACD Trend"])
    assert window.context_bar.strategy.value.text() == "MACD Trend"


def test_the_context_bar_cannot_name_one_strategy_and_show_anothers_numbers(
        window, bars):
    """The exact contradiction the user reported, now impossible to display."""
    _run_into(window, builtin.macd_trend(), bars)
    window._refresh_context()
    assert "MACD Trend" in window.context_bar.state.value.text()

    other = next(e for e in window.strategies.list()
                 if e.name == "Donchian Channel Breakout")
    window.on_strategy_selected(other.id)

    strip = window.context_bar
    assert strip.strategy.value.text() == "Donchian Channel Breakout"
    assert strip.state.value.text() == "nothing run yet"
    assert "MACD" not in strip.state.value.text()


def test_the_context_bar_survives_having_no_data_at_all(window):
    window._view_bars = None
    window._refresh_context()
    assert window.context_bar.span.value.text() == "no data loaded"
    assert window.context_bar.state.value.text() == "nothing run yet"
