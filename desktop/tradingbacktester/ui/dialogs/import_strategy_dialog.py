"""Paste a strategy, see exactly what was understood, then run it.

The design follows from one rule: the user must never leave this dialog
believing a strategy was imported when part of it was not.  So the line table
is the main surface, not an afterthought, and it shows every line of what was
pasted -- converted, ignored, or unsupported -- with the reason.  The headline
above it says *faithful* or *partial* in those words, and a partial import
cannot be backtested from here at all, because a backtest of a partial
conversion is a backtest of a strategy nobody wrote.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout,
                               QHeaderView, QLabel, QPlainTextEdit,
                               QPushButton, QSplitter, QTableWidget,
                               QTableWidgetItem, QTextBrowser, QVBoxLayout,
                               QWidget)

from ...logging_setup import get_logger
from ...strategy.importer import import_strategy
from ..theme import PALETTE, Fonts
from ..widgets.common import Card, show_error, show_info

log = get_logger(__name__)

_COLUMNS = ("Line", "Source", "Outcome", "Why")

#: Colour per outcome.  Unsupported is the only one that needs to shout.
_COLOURS = {"converted": PALETTE.long, "ignored": PALETTE.text_muted,
            "unsupported": PALETTE.short}

_PLACEHOLDER = """Paste a Pine Script strategy here, or a strategy exported
from this application.

What can be imported:
  • Pine Script v4/v5/v6 built from ta.* indicators, comparisons,
    and/or/not, crossovers, and strategy.entry / close / exit
  • this application's own strategy JSON

What cannot, and will be listed rather than guessed at:
  • for/while loops, user-defined functions, var declarations
  • request.security, arrays, matrices, labels and lines
  • indicators with no equivalent here
  • position sizing, pyramiding and costs — those are set in the
    Risk and Costs panels, not imported
"""


class ImportStrategyDialog(QDialog):
    """Convert a pasted strategy, and refuse clearly when it cannot."""

    def __init__(self, store: Any, bars: Any = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import a strategy")
        self.resize(1020, 780)
        self._store = store
        self._bars = bars
        self._report: Any = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(9)

        intro = QLabel(
            "Anything that cannot be translated is listed below rather than "
            "approximated. An import that quietly drops a condition produces a "
            "backtest that looks fine and describes a strategy you did not "
            "write, so a partial conversion is never run from here.")
        intro.setWordWrap(True)
        intro.setObjectName("Hint")
        intro.setFont(Fonts.body(9))
        outer.addWidget(intro)

        splitter = QSplitter(Qt.Orientation.Vertical)

        source_card = Card("Strategy source")
        self.source = QPlainTextEdit()
        self.source.setPlaceholderText(_PLACEHOLDER)
        self.source.setFont(Fonts.numeric(9))
        self.source.setMinimumHeight(200)
        source_card.add(self.source)
        splitter.addWidget(source_card)

        result_card = Card("What was understood")
        self.headline = QLabel("Paste a strategy and press Read it.")
        self.headline.setWordWrap(True)
        self.headline.setFont(Fonts.body(10))
        result_card.add(self.headline)

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(list(_COLUMNS))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        result_card.add(self.table)

        self.detail = QTextBrowser()
        self.detail.setFont(Fonts.numeric(9))
        self.detail.setMaximumHeight(190)
        result_card.add(self.detail)
        splitter.addWidget(result_card)
        splitter.setSizes([260, 460])
        outer.addWidget(splitter, 1)

        buttons = QHBoxLayout()
        self.read_button = QPushButton("  Read it")
        self.read_button.clicked.connect(self.on_read)
        buttons.addWidget(self.read_button)

        self.backtest_button = QPushButton("Backtest it")
        self.backtest_button.setEnabled(False)
        self.backtest_button.clicked.connect(self.on_backtest)
        buttons.addWidget(self.backtest_button)

        self.save_button = QPushButton("Save to library")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.on_save)
        buttons.addWidget(self.save_button)

        buttons.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("Ghost")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        outer.addLayout(buttons)

    # -- reading ---------------------------------------------------------

    def on_read(self) -> None:
        text = self.source.toPlainText()
        if not text.strip():
            self.headline.setText("There is nothing to read yet.")
            return
        try:
            report = import_strategy(text)
        except Exception as exc:            # noqa: BLE001 - never lose the dialog
            log.exception("Import failed")
            show_error(self, exc, "Import failed")
            return
        self._report = report
        self._fill(report)

    def _fill(self, report: Any) -> None:
        rows = list(report.lines)
        self.table.setRowCount(len(rows))
        for row, line in enumerate(rows):
            colour = QColor(_COLOURS.get(line.outcome, PALETTE.text))
            for column, text in enumerate((str(line.line), line.source,
                                           line.outcome, line.detail)):
                item = QTableWidgetItem(text)
                if line.outcome == "unsupported" or column == 2:
                    item.setForeground(colour)
                self.table.setItem(row, column, item)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.resizeColumnToContents(0)
        self.table.resizeColumnToContents(2)

        self.headline.setText(self._headline(report))
        self.headline.setStyleSheet(
            f"color:{PALETTE.long if report.faithful else PALETTE.warning};")
        self.detail.setPlainText(self._detail(report))

        runnable = report.faithful and report.spec is not None
        self.backtest_button.setEnabled(bool(runnable and self._bars is not None))
        self.save_button.setEnabled(bool(runnable))
        self.backtest_button.setToolTip(
            "" if runnable else
            "Only a faithful conversion can be run from here. The lines marked "
            "unsupported would have to be removed or rewritten first."
            if not runnable else "")
        if runnable and self._bars is None:
            self.backtest_button.setToolTip(
                "Load a dataset in the main window first.")

    def _headline(self, report: Any) -> str:
        if report.errors and report.spec is None:
            return f"Not imported. {report.errors[0]}"
        counts = (f"{len(report.converted)} converted, "
                  f"{len(report.ignored)} ignored, "
                  f"{len(report.unsupported)} unsupported")
        if report.faithful:
            return (f"Read as {report.detected} and converted in full — "
                    f"{counts}. Every line that affects what this trades was "
                    f"translated.")
        return (f"Read as {report.detected}, PARTIALLY converted — {counts}. "
                f"This is not the strategy you pasted, so it cannot be "
                f"backtested from here.")

    def _detail(self, report: Any) -> str:
        out: list[str] = []
        if report.evidence:
            out.append(f"Detected as {report.detected} ({report.evidence[0]}).")
        for error in report.errors:
            out.append(f"ERROR: {error}")
        for warning in report.warnings:
            out.append(f"NOTE: {warning}")
        if report.unsupported:
            out.append("")
            out.append("Could not be translated:")
            for line in report.unsupported:
                out.append(f"  line {line.line}: {line.detail}")
        if report.spec is not None:
            out.append("")
            out.append(report.spec.describe()
                       if hasattr(report.spec, "describe")
                       else f"Strategy: {report.spec.name}")
        return "\n".join(out)

    # -- acting on it ----------------------------------------------------

    def on_backtest(self) -> None:
        if self._report is None or not self._report.faithful:
            return
        from ...core.types import BacktestConfig
        from ...engine.backtester import Backtester

        try:
            result = Backtester(self._bars, self._report.spec,
                                BacktestConfig()).run()
        except Exception as exc:            # noqa: BLE001
            log.exception("Backtest of an imported strategy failed")
            show_error(self, exc, "Backtest failed")
            return
        self.detail.setPlainText(_metrics_text(result) + "\n\n"
                                 + self.detail.toPlainText())

    def on_save(self) -> None:
        if self._report is None or self._report.spec is None:
            return
        try:
            self._store.save(self._report.spec)
        except Exception as exc:            # noqa: BLE001
            log.exception("Saving an imported strategy failed")
            show_error(self, exc, "Could not save")
            return
        show_info(self, "Saved",
                  f"'{self._report.spec.name}' is in the strategy library.",
                  "Open it from the strategy picker in the main window to "
                  "chart it, edit it or run it like any other.")


def _metrics_text(result: Any) -> str:
    """The engine's own numbers, so the dialog never states any of its own."""
    from ...finder.confirm import HEADLINE_METRICS

    metrics = getattr(result, "metrics", {}) or {}
    lines = [f"Backtested: {len(getattr(result, 'trades', ()) or ())} trades."]
    width = max(len(label) for _key, label in HEADLINE_METRICS)
    for key, label in HEADLINE_METRICS:
        value = metrics.get(key)
        if value is None:
            continue
        if isinstance(value, float):
            lines.append(f"  {label:<{width}}  {value:,.2f}")
        else:
            lines.append(f"  {label:<{width}}  {value}")
    return "\n".join(lines)
