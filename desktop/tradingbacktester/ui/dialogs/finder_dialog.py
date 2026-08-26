"""Find Strategies: pick data, pick a style, press go.

The whole point of this dialog is that it asks for two things and nothing
else. Everything a search needs beyond "which data" and "what kind of trading"
-- the bar size, the stop and target geometry, the session, the split, the
control, the multiplicity correction -- is decided by the protocol rather than
by the user, because those are exactly the settings that, left adjustable,
turn a search into a machine for finding coincidences.

What it gives back is deliberately not a leaderboard. Every row carries the
control it was measured against, what the locked block said, and a verdict in
plain English -- including, most of the time, "not worth trading".
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog,
                               QHBoxLayout, QHeaderView, QLabel, QProgressBar,
                               QPushButton, QRadioButton, QSizePolicy,
                               QSplitter, QTableWidget, QTableWidgetItem,
                               QTextBrowser, QVBoxLayout, QWidget)

from ...core.errors import BacktesterError, CancelledError
from ...finder import find_strategies, format_report
from ...finder.styles import STYLES
from ...logging_setup import get_logger
from ..theme import PALETTE, Fonts
from ..widgets.common import Card, show_error

log = get_logger(__name__)

_COLUMNS = ("Rule", "Trades", "Won", "Per trade", "Vs. random", "Locked block",
            "Verdict")


class FinderDialog(QDialog):
    """Search for strategies on one dataset, in one style."""

    def __init__(self, datasets: Any, instruments: Any, strategies: Any,
                 current_bars: Any = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Find Strategies")
        self.resize(1180, 800)

        self._datasets = datasets
        self._instruments = instruments
        self._strategies = strategies
        self._bars = current_bars
        self._report: Any = None
        self._worker: Any = None

        self._build_ui()
        self._fill_datasets()

    # -- construction ----------------------------------------------------

    def _build_ui(self) -> None:
        from ..icons import icon

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(9)

        intro = QLabel(
            "Pick the data and the kind of trading you want. Everything else — "
            "bar size, stop and target, session, and how the result is judged — "
            "is fixed by the method, because those are the settings that turn a "
            "search into a machine for finding coincidences.")
        intro.setWordWrap(True)
        intro.setObjectName("Hint")
        intro.setFont(Fonts.body(9))
        outer.addWidget(intro)

        top = QHBoxLayout()
        top.setSpacing(9)

        data_card = Card("Data")
        self.dataset_box = QComboBox()
        self.dataset_box.setMinimumWidth(280)
        data_card.add(self.dataset_box)
        self.dataset_detail = QLabel("")
        self.dataset_detail.setWordWrap(True)
        self.dataset_detail.setFont(Fonts.numeric(8))
        self.dataset_detail.setStyleSheet(f"color:{PALETTE.text_muted};")
        data_card.add(self.dataset_detail)
        top.addWidget(data_card, 1)

        style_card = Card("Trading style")
        self._style_buttons: list[QRadioButton] = []
        for index, style in enumerate(STYLES):
            button = QRadioButton(f"{style.label} — {style.summary}")
            button.setToolTip(style.describe())
            button.setChecked(style.key == "intraday")
            button.toggled.connect(self._on_style_changed)
            button._style = style          # type: ignore[attr-defined]
            style_card.add(button)
            self._style_buttons.append(button)
        self.style_detail = QLabel("")
        self.style_detail.setWordWrap(True)
        self.style_detail.setFont(Fonts.numeric(8))
        self.style_detail.setStyleSheet(f"color:{PALETTE.text_muted};")
        style_card.add(self.style_detail)
        top.addWidget(style_card, 1)
        outer.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(list(_COLUMNS))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setFont(Fonts.numeric(9))
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            len(_COLUMNS) - 1, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        splitter.addWidget(self.table)

        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(False)
        self.detail.setFont(Fonts.body(9))
        splitter.addWidget(self.detail)
        splitter.setSizes([300, 320])
        outer.addWidget(splitter, 1)

        self.progress = QProgressBar()
        self.progress.hide()
        outer.addWidget(self.progress)

        self.status = QLabel("Choose a dataset and a style, then press Search.")
        self.status.setWordWrap(True)
        self.status.setFont(Fonts.body(9))
        self.status.setStyleSheet(f"color:{PALETTE.text_dim};")
        outer.addWidget(self.status)

        buttons = QHBoxLayout()
        self.search_button = QPushButton("  Search")
        self.search_button.setObjectName("Primary")
        self.search_button.setIcon(icon("search", 15))
        self.search_button.setMinimumHeight(32)
        self.search_button.clicked.connect(self._search)
        buttons.addWidget(self.search_button)

        self.cancel_search = QPushButton("Stop")
        self.cancel_search.setEnabled(False)
        self.cancel_search.clicked.connect(self._cancel)
        buttons.addWidget(self.cancel_search)
        buttons.addStretch(1)

        self.save_button = QPushButton("  Save selected as a strategy")
        self.save_button.setIcon(icon("save", 15))
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._save_selected)
        buttons.addWidget(self.save_button)

        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        outer.addLayout(buttons)

        self._on_style_changed()

    # -- data ------------------------------------------------------------

    def _fill_datasets(self) -> None:
        from ...data.bundled import available

        self.dataset_box.blockSignals(True)
        self.dataset_box.clear()
        if self._bars is not None:
            self.dataset_box.addItem("The dataset currently loaded", "@current")
        try:
            for meta in self._datasets.list():
                self.dataset_box.addItem(f"{meta.name}  ({meta.describe()})",
                                         f"@stored:{meta.id}")
        except BacktesterError:
            pass
        for dataset in available():
            self.dataset_box.addItem(f"{dataset.name}  (shipped)",
                                     f"@bundled:{dataset.filename}")
        self.dataset_box.blockSignals(False)
        self.dataset_box.currentIndexChanged.connect(self._on_dataset_changed)
        self._on_dataset_changed()

    def _on_dataset_changed(self, *_args) -> None:
        from ...data.bundled import BUNDLED

        reference = self.dataset_box.currentData() or ""
        if reference.startswith("@bundled:"):
            name = reference.split(":", 1)[1]
            for dataset in BUNDLED:
                if dataset.filename == name:
                    self.dataset_detail.setText(dataset.description)
                    return
        elif reference == "@current" and self._bars is not None:
            self.dataset_detail.setText(
                f"{len(self._bars):,} bars of "
                f"{self._bars.instrument.symbol} at "
                f"{self._bars.timeframe.label}")
            return
        self.dataset_detail.setText("")

    def _on_style_changed(self, *_args) -> None:
        style = self._selected_style()
        self.style_detail.setText(f"{style.describe()}\n{style.notes}")

    def _selected_style(self):
        for button in self._style_buttons:
            if button.isChecked():
                return button._style          # type: ignore[attr-defined]
        return STYLES[0]

    def _load_bars(self):
        from ...data.bundled import BUNDLED
        from ...data.csv_loader import load_csv, sniff_csv

        reference = self.dataset_box.currentData() or ""
        if reference == "@current":
            if self._bars is None:
                raise BacktesterError("There is no dataset loaded.")
            return self._bars
        if reference.startswith("@stored:"):
            return self._datasets.load_bars(reference.split(":", 1)[1])
        if reference.startswith("@bundled:"):
            name = reference.split(":", 1)[1]
            for dataset in BUNDLED:
                if dataset.filename == name:
                    instrument = self._instruments.ensure(dataset.symbol,
                                                          dataset.asset_class)
                    profile = sniff_csv(str(dataset.path()))
                    return load_csv(str(dataset.path()), profile.mapping,
                                    instrument)
        raise BacktesterError("Choose a dataset to search.")

    # -- running ---------------------------------------------------------

    def _search(self) -> None:
        try:
            bars = self._load_bars()
        except BacktesterError as exc:
            show_error(self, exc)
            return

        style = self._selected_style()
        self.table.setRowCount(0)
        self.detail.clear()
        self.save_button.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.show()
        self.search_button.setEnabled(False)
        self.cancel_search.setEnabled(True)
        self.status.setText(
            f"Searching {len(bars):,} bars of {bars.instrument.symbol}. "
            f"This runs on a background thread; the window stays usable.")
        self.status.setStyleSheet(f"color:{PALETTE.text_dim};")

        from ..workers import TaskRunner

        self._worker = TaskRunner(self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)

        def job(progress=None, cancel=None):
            def forward(done: int, total: int, message: str) -> None:
                if cancel is not None and cancel.cancelled:
                    raise CancelledError("The search was stopped.")
                if progress is not None:
                    progress(done, total, message)
            return find_strategies(bars, style, progress=forward)

        self._worker.start(job, "Searching for strategies")

    def _cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()

    def _on_progress(self, done: int, total: int, message: str) -> None:
        if total > 0:
            self.progress.setValue(int(100 * done / total))
        if message:
            self.status.setText(message)

    def _on_failed(self, message: str, detail: str) -> None:
        self._finish_ui()
        self.status.setText(message)
        self.status.setStyleSheet(f"color:{PALETTE.danger};")
        log.error("Strategy search failed: %s\n%s", message, detail)

    def _on_cancelled(self) -> None:
        self._finish_ui()
        self.status.setText("Search stopped.")

    def _finish_ui(self) -> None:
        self.progress.hide()
        self.search_button.setEnabled(True)
        self.cancel_search.setEnabled(False)

    def _on_finished(self, report: Any) -> None:
        self._finish_ui()
        self._report = report
        self._fill_table(report)
        self.detail.setPlainText(format_report(report))
        if report.shortlist:
            worth = sum(1 for f in report.shortlist
                        if f.verdict == "worth testing further")
            self.status.setText(
                f"{report.combinations:,} combinations tried in "
                f"{report.elapsed:.0f}s. {len(report.shortlist)} shortlisted, "
                f"{worth} worth testing further. Select a row to read the "
                f"detail.")
            self.status.setStyleSheet(
                f"color:{PALETTE.success if worth else PALETTE.warning};")
        else:
            self.status.setText(
                f"{report.combinations:,} combinations tried and none survived. "
                f"That is the usual outcome of an honest search — see below for "
                f"what it would take to change it.")
            self.status.setStyleSheet(f"color:{PALETTE.warning};")

    def _fill_table(self, report: Any) -> None:
        rows = list(report.shortlist)
        self.table.setRowCount(len(rows))
        for row, finding in enumerate(rows):
            research = finding.research
            holdout = finding.holdout or {}
            excess = (finding.holdout_control.excess_per_trade
                      if finding.holdout_control else 0.0)
            cells = [
                finding.label,
                f"{int(research['trades']):,}",
                f"{research['win_rate'] * 100:.1f}%",
                f"{research['per_trade']:+,.2f}",
                f"{finding.control.excess_per_trade:+,.2f} (p={finding.control.p_value:.3f})",
                (f"{int(holdout.get('trades', 0)):,} trades, {excess:+,.2f}"
                 if holdout else "—"),
                finding.verdict,
            ]
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                          | Qt.AlignmentFlag.AlignVCenter)
                if column == len(cells) - 1:
                    item.setForeground(Qt.GlobalColor.green
                                       if finding.verdict.startswith("worth")
                                       else Qt.GlobalColor.gray)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)

    def _on_row_selected(self) -> None:
        finding = self._selected_finding()
        self.save_button.setEnabled(finding is not None and finding.spec is not None)
        if finding is None:
            return
        from ...finder.report import _finding_lines

        lines = [finding.label, ""]
        lines.extend(_finding_lines(finding, "USD"))
        self.detail.setPlainText("\n".join(lines))

    def _selected_finding(self):
        if self._report is None:
            return None
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        index = rows[0].row()
        shortlist = list(self._report.shortlist)
        return shortlist[index] if 0 <= index < len(shortlist) else None

    def _save_selected(self) -> None:
        finding = self._selected_finding()
        if finding is None or finding.spec is None:
            return
        try:
            saved = self._strategies.save(finding.spec)
        except BacktesterError as exc:
            show_error(self, exc)
            return
        self.status.setText(
            f"Saved '{saved.name}'. It is a candidate for further testing, not "
            f"a recommendation — run it, read the trades, and judge it "
            f"yourself.")
        self.status.setStyleSheet(f"color:{PALETTE.success};")
