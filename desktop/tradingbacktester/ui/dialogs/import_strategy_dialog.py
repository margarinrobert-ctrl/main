"""Paste a strategy, see exactly what was understood, then run it.

The design follows from one rule: the user must never leave this dialog
believing a strategy was imported when part of it was not.  So the line table
is the main surface, not an afterthought, and it shows every line of what was
pasted -- converted, ignored, or unsupported -- with the reason.  The headline
above it says *faithful* or *partial* in those words, and a partial import
cannot be backtested from here at all, because a backtest of a partial
conversion is a backtest of a strategy nobody wrote.

A partial conversion is still not a dead end.  It cannot be *run* -- that is
the rule above and it does not bend -- but it can be opened in the editor,
where the lines that did not translate are listed and the user finishes the
job by hand.  Refusing to run a half-strategy and refusing to show it are
different refusals, and only the first one is useful.

Reading happens as you type.  The conversion touches no bars and no
indicators; it is a parse, and on the largest Pine script anyone would paste
it is faster than the keystroke that triggered it.  A button that has to be
pressed before anything appears is friction for no reason, so the button is
still there for the habit but the table fills in on its own.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QTextCursor
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QFileDialog,
                               QHBoxLayout, QHeaderView, QLabel,
                               QPlainTextEdit, QPushButton, QSplitter,
                               QTableWidget, QTableWidgetItem, QTextBrowser,
                               QVBoxLayout, QWidget)

from pathlib import Path

from ...logging_setup import get_logger
from ...strategy.importer import import_strategy
from ..theme import PALETTE, Fonts
from ..widgets.common import Card, confirm, show_error, show_info

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

        tools = QHBoxLayout()
        tools.setSpacing(6)
        self.clipboard_button = QPushButton("Paste from clipboard")
        self.clipboard_button.clicked.connect(self.on_paste_clipboard)
        tools.addWidget(self.clipboard_button)
        self.file_button = QPushButton("Open a file\u2026")
        self.file_button.clicked.connect(self.on_open_file)
        tools.addWidget(self.file_button)
        self.clear_button = QPushButton("Clear")
        self.clear_button.setObjectName("Ghost")
        self.clear_button.clicked.connect(self.on_clear)
        tools.addWidget(self.clear_button)
        tools.addStretch(1)
        self.source_status = QLabel("")
        self.source_status.setObjectName("Hint")
        self.source_status.setFont(Fonts.body(9))
        tools.addWidget(self.source_status)
        source_card.add_layout(tools)

        self.source = QPlainTextEdit()
        self.source.setPlaceholderText(_PLACEHOLDER)
        self.source.setFont(Fonts.numeric(9))
        self.source.setMinimumHeight(200)
        # Read as you type, one beat after you stop.  Without the delay every
        # keystroke in the middle of a half-typed line reports a syntax error
        # the user is already fixing.
        self._reread = QTimer(self)
        self._reread.setSingleShot(True)
        self._reread.setInterval(350)
        self._reread.timeout.connect(self._auto_read)
        self.source.textChanged.connect(self._on_source_changed)
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
        # Clicking a line that did not translate puts the cursor on it. The
        # whole point of listing them is that they can be fixed, and hunting
        # for line 63 by eye in a pasted script is the slow part.
        self.table.itemSelectionChanged.connect(self._on_line_selected)
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
        self.read_button.setToolTip(
            "Pasted text is read automatically; this re-reads it now.")
        # `clicked` passes a `checked` bool, which would land in `quiet`.  It
        # happens to be False for a non-checkable button, but relying on that
        # would make the button silent the day someone makes it checkable.
        self.read_button.clicked.connect(lambda: self.on_read())
        buttons.addWidget(self.read_button)

        self.edit_button = QPushButton("Edit it\u2026")
        self.edit_button.setEnabled(False)
        self.edit_button.clicked.connect(self.on_edit)
        buttons.addWidget(self.edit_button)

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

    # -- getting text in -------------------------------------------------

    def on_paste_clipboard(self) -> None:
        """Replace the box with the clipboard and read it.

        Replace rather than insert: someone pressing this has a strategy on
        the clipboard and wants to see it, not to append it to whatever was
        there before.
        """
        clipboard = QGuiApplication.clipboard()
        text = clipboard.text() if clipboard is not None else ""
        if not text.strip():
            self.source_status.setText("The clipboard has no text in it.")
            return
        self.source.setPlainText(text)
        self.on_read()

    def on_open_file(self) -> None:
        """Load a ``.pine``/``.txt``/``.json`` file into the box and read it."""
        path, _filter = QFileDialog.getOpenFileName(
            self, "Open a strategy", "",
            "Strategies (*.pine *.txt *.json);;All files (*)")
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            log.exception("Could not read %s", path)
            show_error(self, exc, "Could not open that file")
            return
        self.source.setPlainText(text)
        self.on_read()

    def on_clear(self) -> None:
        self.source.clear()

    def _on_source_changed(self) -> None:
        """Restart the read timer, and drop any result the old text produced."""
        self._invalidate()
        text = self.source.toPlainText()
        if text.strip():
            self.source_status.setText("Reading\u2026")
            self._reread.start()
        else:
            self._reread.stop()
            self.source_status.setText("")
            self.table.setRowCount(0)
            self.detail.clear()
            self.headline.setText("Paste a strategy and it will be read here.")
            self.headline.setStyleSheet("")

    def _invalidate(self) -> None:
        """Nothing may be run or saved while the text and the report disagree."""
        self._report = None
        for button in (self.backtest_button, self.save_button,
                       self.edit_button):
            button.setEnabled(False)

    def _auto_read(self) -> None:
        """The timer's read.  Identical to the button, but never pops a dialog.

        A syntax error while someone is still typing is not an event worth a
        modal; it belongs in the headline, which is where the button's version
        would put it a moment later anyway.
        """
        self.on_read(quiet=True)

    # -- reading ---------------------------------------------------------

    def _on_line_selected(self) -> None:
        """Put the text cursor on the source line of the selected row."""
        items = self.table.selectedItems()
        if not items:
            return
        row = items[0].row()
        cell = self.table.item(row, 0)
        if cell is None:
            return
        try:
            number = int(cell.text())
        except ValueError:                  # pragma: no cover - defensive
            return
        block = self.source.document().findBlockByLineNumber(max(0, number - 1))
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        cursor.select(QTextCursor.SelectionType.LineUnderCursor)
        self.source.setTextCursor(cursor)
        self.source.centerCursor()

    def on_read(self, quiet: bool = False) -> None:
        self._reread.stop()
        text = self.source.toPlainText()
        if not text.strip():
            self.headline.setText("There is nothing to read yet.")
            self.source_status.setText("")
            return
        try:
            report = import_strategy(text)
        except Exception as exc:            # noqa: BLE001 - never lose the dialog
            log.exception("Import failed")
            self._invalidate()
            self.source_status.setText("Could not be read.")
            if quiet:
                # Mid-typing.  Say so where the answer goes, not in a modal.
                self.headline.setText(
                    "This could not be read yet. The technical detail is in "
                    "the log file.")
                self.headline.setStyleSheet(f"color:{PALETTE.warning};")
                return
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

        counts = (f"{len(report.converted)} converted, "
                  f"{len(report.unsupported)} unsupported")
        self.source_status.setText(f"Read as {report.detected} \u2014 {counts}.")

        runnable = report.faithful and report.spec is not None
        self.backtest_button.setEnabled(bool(runnable and self._bars is not None))
        self.save_button.setEnabled(bool(runnable))
        if not runnable:
            tip = ("Only a faithful conversion can be run from here. The lines "
                   "marked unsupported would have to be removed or rewritten "
                   "first \u2014 or open it with 'Edit it' and finish it by "
                   "hand.")
        elif self._bars is None:
            tip = "Load a dataset in the main window first."
        else:
            tip = ""
        self.backtest_button.setToolTip(tip)
        self.save_button.setToolTip(
            "" if runnable else
            "A partial conversion is not saved: in the library it would be "
            "indistinguishable from a whole one later. Open it with 'Edit it' "
            "and save it from there once it is finished.")

        # Editing is offered for a partial conversion too.  Refusing to *run*
        # a half-strategy is the rule; refusing to let anyone look at it or
        # finish it just makes the refusal useless.
        self.edit_button.setEnabled(report.spec is not None)
        self.edit_button.setToolTip(
            "Open this in the strategy editor."
            if report.faithful else
            "Open the part that converted in the strategy editor, where the "
            "missing rules can be added by hand.")

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
        if report.named:
            out.append("")
            out.append(
                f"{len(report.named)} hard-coded number"
                f"{'' if len(report.named) == 1 else 's'} became named "
                f"parameters, so this can be optimised, walked forward and "
                f"searched around. Each keeps the value it already had, so "
                f"what the strategy trades is unchanged:")
            for param in report.named:
                out.append(f"  • {param.describe()}")
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

    def on_edit(self) -> None:
        """Open the conversion in the strategy editor, partial or not.

        A partial one arrives with its own warning and with the untranslated
        lines listed, and it is *not* saved on the way in: whether a
        half-finished strategy belongs in the library is the user's call, made
        in the editor, after they have seen it.
        """
        if self._report is None or self._report.spec is None:
            return
        from .strategy_editor import StrategyEditor

        report = self._report
        if not report.faithful:
            missing = "\n".join(
                f"  line {line.line}: {line.detail}"
                for line in report.unsupported[:12])
            more = ("\n  \u2026and "
                    f"{len(report.unsupported) - 12} more"
                    if len(report.unsupported) > 12 else "")
            if not confirm(
                    self, "Open a partial conversion?",
                    f"{len(report.unsupported)} line"
                    f"{'' if len(report.unsupported) == 1 else 's'} could not "
                    f"be translated, so this is not the strategy that was "
                    f"pasted. Opening it in the editor lets you add the "
                    f"missing rules by hand; until you do, anything it "
                    f"produces describes something else."
                    f"\n\nNot translated:\n{missing}{more}",
                    confirm_text="Open it", danger=False):
                return

        editor = StrategyEditor(report.spec.copy(), self, self._bars)
        if editor.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self._store.save(editor.spec)
        except Exception as exc:            # noqa: BLE001
            log.exception("Saving an edited import failed")
            show_error(self, exc, "Could not save")
            return
        show_info(self, "Saved",
                  f"'{editor.spec.name}' is in the strategy library.",
                  "Open it from the strategy picker in the main window to "
                  "chart it, edit it or run it like any other.")

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
