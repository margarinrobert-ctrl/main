"""Research: pick data, pick a style, and ask one of three questions.

The whole point of this dialog is that it asks for two things and nothing
else. Everything a study needs beyond "which data" and "what kind of trading"
-- the bar size, the stop and target geometry, the session, the split, the
control, the multiplicity correction -- is decided by the protocol rather than
by the user, because those are exactly the settings that, left adjustable,
turn a search into a machine for finding coincidences.

Three tabs, three questions, one set of machinery underneath:

* **Strategies** -- is there an entry rule that beats entering at random?
* **Indicators** -- which measurements predict what a trade will pay, and is
  the prediction worth more than the spread?
* **Anomalies** -- which bars are unusual, and does anything follow them?

What they give back is deliberately not a leaderboard. Every row carries what
it was measured against, what the locked block said, and a verdict in plain
English -- including, most of the time, "nothing".
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog,
                               QHBoxLayout, QHeaderView, QLabel, QProgressBar,
                               QPushButton, QRadioButton, QSizePolicy,
                               QSplitter, QTabWidget, QTableWidget,
                               QTableWidgetItem, QTextBrowser, QVBoxLayout,
                               QWidget)

from ...core.errors import BacktesterError, CancelledError
from ...finder import find_strategies, format_report
from ...finder.styles import STYLES
from ...research import format_anomalies, format_study, scan, study_features
from ...logging_setup import get_logger
from ..theme import PALETTE, Fonts
from ..widgets.common import Card, show_error

log = get_logger(__name__)

#: The strategy table.  Robustness comes before the money on purpose: a search
#: always produces a winner, so the first thing to read about one is how much
#: of it held up, not how much it made.  Every figure in the money columns is
#: the ENGINE's, from `finder/confirm.py`, not the search's fast path.
_COLUMNS = ("Rule", "Robustness", "OOS retention", "Trades (IS | OOS)",
            "Net (IS | OOS)", "Sharpe (IS | OOS)", "Max DD (OOS)",
            "Vs. random", "Verdict")

_INDICATOR_COLUMNS = ("Indicator", "Family", "Says", "Predictive power",
                      "Worth per trade", "Locked block", "Verdict")

_ANOMALY_COLUMNS = ("Event", "Count", "Share", "Side", "Edge per trade", "p",
                    "Verdict")

#: The three questions, in the order the tabs show them.
STUDIES = (
    ("strategies", "Strategies",
     "Is there an entry rule that beats entering at random?"),
    ("indicators", "Indicators",
     "Which measurements predict what a trade pays, and by enough to cover "
     "the spread?"),
    ("anomalies", "Anomalies",
     "Which bars are unusual, and does anything follow them?"),
)


def _pair(left: Any, right: Any, fmt: str = "{:,.0f}") -> str:
    """One in-sample figure beside its out-of-sample twin, never merged.

    A single blended number is how a rule chosen on one block gets described as
    profitable; keeping the two apart makes the decay between them the thing
    the eye lands on.
    """
    import math

    def one(value: Any) -> str:
        if value is None:
            return "—"
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        if not math.isfinite(number):
            return "—"
        return fmt.format(number)

    return f"{one(left)} | {one(right)}"


def _strategy_cells(finding: Any) -> list[str]:
    """One row of the strategy table, from the engine's own numbers."""
    import math

    confirmation = getattr(finding, "confirmation", None)
    score = getattr(finding, "robustness", None)

    if score is None:
        robustness = "—"
    elif score.blocked:
        robustness = "disqualified"
    else:
        total = score.total
        robustness = ("—" if not math.isfinite(total)
                      else f"{total:.0f}/100 {score.grade}")

    retention = "—"
    if score is not None and not score.blocked:
        found = next((d for d in score.dimensions
                      if d.key == "retention" and d.applicable), None)
        if found is not None:
            retention = f"{found.score * 100:.0f}%"

    if confirmation is None or not confirmation.ran:
        trades = net = sharpe = drawdown = "not run"
    else:
        research, holdout = confirmation.research.metrics, confirmation.holdout.metrics
        trades = _pair(confirmation.research.trades, confirmation.holdout.trades)
        net = _pair(research.get("net_profit"), holdout.get("net_profit"),
                    "{:+,.0f}")
        sharpe = _pair(research.get("sharpe_ratio"), holdout.get("sharpe_ratio"),
                       "{:.2f}")
        raw = holdout.get("max_drawdown")
        drawdown = ("—" if raw is None else f"{abs(float(raw)):,.0f}")

    control = getattr(finding, "control", None)
    versus = ("—" if control is None else
              f"{control.excess_per_trade:+,.2f} (p={control.p_value:.3f})")

    return [finding.label, robustness, retention, trades, net, sharpe,
            drawdown, versus, finding.verdict]


class FinderDialog(QDialog):
    """Search for strategies on one dataset, in one style."""

    def __init__(self, datasets: Any, instruments: Any, strategies: Any,
                 current_bars: Any = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Research")
        self.resize(1180, 800)

        self._datasets = datasets
        self._instruments = instruments
        self._strategies = strategies
        self._bars = current_bars
        self._reports: dict[str, Any] = {"strategies": None,
                                         "indicators": None,
                                         "anomalies": None}
        self._running: str = "strategies"
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

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self._tables: dict[str, QTableWidget] = {}
        self._details: dict[str, QTextBrowser] = {}
        for key, label, question in STUDIES:
            columns = {"strategies": _COLUMNS,
                       "indicators": _INDICATOR_COLUMNS,
                       "anomalies": _ANOMALY_COLUMNS}[key]
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(0, 8, 0, 0)
            layout.setSpacing(6)
            prompt = QLabel(question)
            prompt.setWordWrap(True)
            prompt.setObjectName("Hint")
            prompt.setFont(Fonts.body(9))
            layout.addWidget(prompt)

            splitter = QSplitter(Qt.Orientation.Vertical)
            table = QTableWidget(0, len(columns))
            table.setHorizontalHeaderLabels(list(columns))
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(
                QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(
                QAbstractItemView.SelectionMode.SingleSelection)
            table.setFont(Fonts.numeric(9))
            table.verticalHeader().setVisible(False)
            table.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeMode.Stretch)
            table.horizontalHeader().setSectionResizeMode(
                len(columns) - 1, QHeaderView.ResizeMode.Stretch)
            table.itemSelectionChanged.connect(self._on_row_selected)
            splitter.addWidget(table)

            detail = QTextBrowser()
            detail.setOpenExternalLinks(False)
            detail.setFont(Fonts.body(9))
            splitter.addWidget(detail)
            splitter.setSizes([290, 300])
            layout.addWidget(splitter, 1)
            self.tabs.addTab(page, label)
            self._tables[key] = table
            self._details[key] = detail
        self.tabs.currentChanged.connect(self._on_tab_changed)
        outer.addWidget(self.tabs, 1)

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

    @property
    def _study(self) -> str:
        index = max(0, self.tabs.currentIndex())
        return STUDIES[min(index, len(STUDIES) - 1)][0]

    def _on_tab_changed(self, *_args) -> None:
        self._on_row_selected()
        study = self._study
        if self._reports.get(study) is None:
            index = max(0, min(self.tabs.currentIndex(), len(STUDIES) - 1))
            self.status.setText(
                f"{STUDIES[index][2]}  Press Search to find out.")
            self.status.setStyleSheet(f"color:{PALETTE.text_dim};")

    def _search(self) -> None:
        try:
            bars = self._load_bars()
        except BacktesterError as exc:
            show_error(self, exc)
            return

        style = self._selected_style()
        study = self._study
        self._tables[study].setRowCount(0)
        self._details[study].clear()
        self.save_button.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.show()
        self.search_button.setEnabled(False)
        self.cancel_search.setEnabled(True)
        self.status.setText(
            f"Working through {len(bars):,} bars of "
            f"{bars.instrument.symbol}. This runs on a background thread; the "
            f"window stays usable.")
        self.status.setStyleSheet(f"color:{PALETTE.text_dim};")

        from ..workers import TaskRunner

        self._worker = TaskRunner(self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._running = study

        def job(progress=None, cancel=None):
            def forward(done: int, total: int, message: str) -> None:
                if cancel is not None and cancel.cancelled:
                    raise CancelledError("The study was stopped.")
                if progress is not None:
                    progress(done, total, message)

            if study == "indicators":
                return study_features(bars, style, progress=forward)
            if study == "anomalies":
                return scan(bars, style, progress=forward)
            return find_strategies(bars, style, progress=forward)

        # start(fn, *args, **kwargs) forwards everything after `fn` to the job.
        # A label passed here became job's first POSITIONAL argument, which is
        # `progress` -- and the runner then also passed progress by keyword, so
        # every study died on "got multiple values for argument 'progress'"
        # before it read a single bar. The job takes no arguments of its own.
        self._worker.start(job)

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
        log.error("Study failed: %s\n%s", message, detail)

    def _on_cancelled(self) -> None:
        self._finish_ui()
        self.status.setText("Stopped.")

    def _finish_ui(self) -> None:
        self.progress.hide()
        self.search_button.setEnabled(True)
        self.cancel_search.setEnabled(False)

    def _on_finished(self, report: Any) -> None:
        self._finish_ui()
        study = self._running or self._study
        self._reports[study] = report
        if study == "indicators":
            self._fill_indicators(report)
        elif study == "anomalies":
            self._fill_anomalies(report)
        else:
            self._fill_strategies(report)

    # -- filling the three tables ----------------------------------------

    def _put(self, table, row: int, cells: list[str], highlight: bool) -> None:
        for column, text in enumerate(cells):
            item = QTableWidgetItem(text)
            if column:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                      | Qt.AlignmentFlag.AlignVCenter)
            if column == len(cells) - 1:
                item.setForeground(Qt.GlobalColor.green if highlight
                                   else Qt.GlobalColor.gray)
            table.setItem(row, column, item)

    def _fill_strategies(self, report: Any) -> None:
        table = self._tables["strategies"]
        rows = list(report.shortlist)
        table.setRowCount(len(rows))
        for row, finding in enumerate(rows):
            self._put(table, row, _strategy_cells(finding),
                      finding.verdict.startswith("worth"))
        self._finish_table(table, "strategies", format_report(report))

        worth = sum(1 for f in rows if f.verdict == "worth testing further")
        if rows:
            self.status.setText(
                f"{report.combinations:,} combinations tried in "
                f"{report.elapsed:.0f}s. {len(rows)} shortlisted, {worth} "
                f"worth testing further. Select a row to read the detail.")
            self.status.setStyleSheet(
                f"color:{PALETTE.success if worth else PALETTE.warning};")
        else:
            self.status.setText(
                f"{report.combinations:,} combinations tried and none "
                f"survived. That is the usual outcome of an honest search — "
                f"see below for what it would take to change it.")
            self.status.setStyleSheet(f"color:{PALETTE.warning};")

    def _fill_indicators(self, study: Any) -> None:
        table = self._tables["indicators"]
        rows = [f for f in study.findings if f.research.significant][:30]
        table.setRowCount(len(rows))
        for row, finding in enumerate(rows):
            holdout = (f"IC {finding.holdout.ic:+.4f}" if finding.holdout
                       else "—")
            self._put(table, row, [
                finding.name,
                finding.feature.family,
                finding.direction,
                f"IC {finding.research.ic:+.4f} (t={finding.research.t_stat:+.1f})",
                f"{finding.research.spread:+,.2f} {study.currency}",
                holdout,
                finding.verdict,
            ], finding.verdict.startswith("predicts, and"))
        self._finish_table(table, "indicators", format_study(study, top=30))

        useful = sum(1 for f in rows
                     if f.verdict.startswith("predicts, and"))
        self.status.setText(
            f"{study.tested} features in {study.independent} independent "
            f"groups; {study.significant} predict something, {useful} by more "
            f"than the {study.cost_per_trade:,.2f} {study.currency} cost of "
            f"trading. Select a row to read the detail.")
        self.status.setStyleSheet(
            f"color:{PALETTE.success if useful else PALETTE.warning};")

    def _fill_anomalies(self, report: Any) -> None:
        table = self._tables["anomalies"]
        rows = list(report.findings)
        table.setRowCount(len(rows))
        for row, finding in enumerate(rows):
            self._put(table, row, [
                finding.label,
                f"{finding.count:,}",
                f"{finding.share * 100:.2f}%",
                "long" if finding.side > 0 else "short",
                f"{finding.excess:+,.2f} {report.currency}",
                f"{finding.p_value:.3f}",
                finding.verdict,
            ], finding.verdict.startswith("worth"))
        self._finish_table(table, "anomalies", format_anomalies(report))

        worth = sum(1 for f in rows if f.verdict.startswith("worth"))
        self.status.setText(
            f"{len(rows)} detectors on {report.bars:,} bars; {worth} worth a "
            f"closer look. Select a row to read the detail.")
        self.status.setStyleSheet(
            f"color:{PALETTE.success if worth else PALETTE.warning};")

    def _finish_table(self, table, study: str, text: str) -> None:
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._details[study].setPlainText(text)

    # -- selection --------------------------------------------------------

    def _on_row_selected(self) -> None:
        study = self._study
        finding = self._selected_finding()
        self.save_button.setEnabled(
            study == "strategies" and finding is not None
            and getattr(finding, "spec", None) is not None)
        if finding is None:
            return
        if study == "strategies":
            from ...finder.report import _finding_lines

            lines = [finding.label, ""]
            lines.extend(_finding_lines(finding, "USD"))
        elif study == "indicators":
            report = self._reports["indicators"]
            lines = [f"{finding.name}  [{finding.feature.family}]",
                     "", finding.feature.description, "",
                     finding.research.describe(report.currency,
                                               report.cost_per_trade),
                     f"deciles: bottom {finding.research.bottom_decile:+,.2f} → "
                     f"top {finding.research.top_decile:+,.2f} "
                     f"{report.currency}/trade "
                     f"(baseline {report.baseline:+,.2f})"]
            if finding.holdout is not None:
                lines.append(
                    f"locked block: IC {finding.holdout.ic:+.4f} "
                    f"(t={finding.holdout.t_stat:+.2f})")
            if len(finding.cluster) > 1:
                lines.append("measures the same thing as: "
                             + ", ".join(n for n in finding.cluster
                                         if n != finding.name))
            lines.extend(["", f"verdict: {finding.verdict}"])
            lines.extend(f"  - {c}" for c in finding.concerns)
        else:
            lines = [finding.label, "", finding.detector.description, "",
                     f"{finding.count:,} bars ({finding.share * 100:.2f}% of "
                     f"the data)",
                     f"best side: {'long' if finding.side > 0 else 'short'}, "
                     f"{finding.trades:,} trades, "
                     f"{finding.per_trade:+,.2f} per trade",
                     f"against a matched control: {finding.excess:+,.2f} "
                     f"(p={finding.p_value:.3f})",
                     f"locked block: {finding.holdout_trades:,} trades, "
                     f"{finding.holdout_excess:+,.2f} per trade",
                     "", f"verdict: {finding.verdict}"]
            if finding.detail:
                lines.extend(["", finding.detail])
        self._details[study].setPlainText("\n".join(str(x) for x in lines))

    def _selected_finding(self):
        study = self._study
        report = self._reports.get(study)
        if report is None:
            return None
        table = self._tables[study]
        rows = table.selectionModel().selectedRows()
        if not rows:
            return None
        index = rows[0].row()
        if study == "strategies":
            items = list(report.shortlist)
        elif study == "indicators":
            items = [f for f in report.findings if f.research.significant][:30]
        else:
            items = list(report.findings)
        return items[index] if 0 <= index < len(items) else None

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
