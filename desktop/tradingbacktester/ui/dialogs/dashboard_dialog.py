"""The research dashboard: what has been tried, and what survived it.

Three panes, left to right in reading order, because that is the order the
questions arrive in: which run, which experiment, which candidate.

The design constraint that shapes it: a dashboard makes things look
authoritative.  Rows in a table read as facts whether or not they are, and a
big number in a large font reads as a conclusion.  So the leftmost column of
the candidate table is the robustness grade rather than the profit, the
experiments that found NOTHING are listed beside the ones that did rather than
filtered out, and a disqualified candidate shows its blockers where the score
would otherwise be.  There is no view here that shows a return without showing
what it survived.
"""

from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog,
                               QHBoxLayout, QHeaderView, QLabel, QProgressBar,
                               QPushButton, QSpinBox, QSplitter, QTableWidget,
                               QTableWidgetItem, QTextBrowser, QVBoxLayout,
                               QWidget)

from ...logging_setup import get_logger
from ..theme import PALETTE, Fonts
from ..widgets.common import Card, confirm, show_error

log = get_logger(__name__)

_RUN_COLUMNS = ("When", "Instrument", "Style", "Experiments", "Survived",
                "Combinations", "Best")
_EXPERIMENT_COLUMNS = ("Round", "Hypothesis", "Combinations", "Shortlisted",
                       "Survived", "Outcome")
_CANDIDATE_COLUMNS = ("Robustness", "Rule", "Trades (IS | OOS)",
                      "Net (IS | OOS)", "Verdict")


def _pair(left: Any, right: Any, fmt: str = "{:,.0f}") -> str:
    def one(value: Any) -> str:
        if value is None:
            return "—"
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        return "—" if not math.isfinite(number) else fmt.format(number)

    return f"{one(left)} | {one(right)}"


class DashboardDialog(QDialog):
    """Past research runs, the experiments inside them, and what survived."""

    def __init__(self, store: Any, datasets: Any = None, instruments: Any = None,
                 bars: Any = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Research dashboard")
        self.resize(1240, 860)
        self._store = store
        self._datasets = datasets
        self._instruments = instruments
        self._bars = bars
        self._runs: list[Any] = []
        self._report: dict[str, Any] | None = None
        self._worker: Any = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(9)

        intro = QLabel(
            "Every research run this workspace has kept, including the "
            "experiments that found nothing — those are what tell you the "
            "ground has been covered. Candidates are ordered by how much of "
            "them held up, never by what they made.")
        intro.setWordWrap(True)
        intro.setObjectName("Hint")
        intro.setFont(Fonts.body(9))
        outer.addWidget(intro)

        outer.addLayout(self._build_controls())

        splitter = QSplitter(Qt.Orientation.Vertical)

        runs_card = Card("Research history")
        self.runs = self._table(_RUN_COLUMNS)
        self.runs.itemSelectionChanged.connect(self._on_run_selected)
        runs_card.add(self.runs)
        splitter.addWidget(runs_card)

        middle = QSplitter(Qt.Orientation.Horizontal)
        experiments_card = Card("Experiments in this run")
        self.experiments = self._table(_EXPERIMENT_COLUMNS)
        experiments_card.add(self.experiments)
        middle.addWidget(experiments_card)

        candidates_card = Card("What survived")
        self.candidates = self._table(_CANDIDATE_COLUMNS)
        self.candidates.itemSelectionChanged.connect(self._on_candidate_selected)
        candidates_card.add(self.candidates)
        middle.addWidget(candidates_card)
        middle.setSizes([560, 640])
        splitter.addWidget(middle)

        detail_card = Card("Research report")
        self.detail = QTextBrowser()
        self.detail.setFont(Fonts.numeric(9))
        detail_card.add(self.detail)
        splitter.addWidget(detail_card)
        splitter.setSizes([180, 260, 300])
        outer.addWidget(splitter, 1)

        self.progress = QProgressBar()
        self.progress.hide()
        outer.addWidget(self.progress)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setFont(Fonts.body(9))
        outer.addWidget(self.status)

        buttons = QHBoxLayout()
        self.delete_button = QPushButton("Delete run")
        self.delete_button.setObjectName("Ghost")
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self.on_delete)
        buttons.addWidget(self.delete_button)
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("Ghost")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        outer.addLayout(buttons)

        self.refresh()

    # -- construction ----------------------------------------------------

    def _table(self, columns: tuple[str, ...]) -> QTableWidget:
        table = QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels(list(columns))
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        return table

    def _build_controls(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(9)

        row.addWidget(QLabel("New run:"))
        self.style_box = QComboBox()
        from ...finder.styles import STYLES

        for style in STYLES:
            self.style_box.addItem(style.label, style.key)
        index = self.style_box.findData("intraday")
        if index >= 0:
            self.style_box.setCurrentIndex(index)
        row.addWidget(self.style_box)

        row.addWidget(QLabel("Rounds:"))
        self.rounds = QSpinBox()
        self.rounds.setRange(1, 10)
        self.rounds.setValue(2)
        row.addWidget(self.rounds)

        row.addWidget(QLabel("Checks:"))
        self.depth = QComboBox()
        for key, label in (("quick", "quick — engine only"),
                           ("standard", "standard — + concentration, Monte "
                                        "Carlo, mirror"),
                           ("full", "full — + walk-forward (slow)")):
            self.depth.addItem(label, key)
        self.depth.setCurrentIndex(1)
        row.addWidget(self.depth)

        self.run_button = QPushButton("  Run research")
        self.run_button.clicked.connect(self.on_run)
        row.addWidget(self.run_button)

        self.cancel_button = QPushButton("Stop")
        self.cancel_button.setObjectName("Ghost")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.on_cancel)
        row.addWidget(self.cancel_button)

        row.addStretch(1)
        return row

    # -- history ---------------------------------------------------------

    def refresh(self) -> None:
        try:
            self._runs = self._store.list()
        except Exception as exc:            # noqa: BLE001 - a dashboard that
            log.exception("The research history could not be read")
            self._runs = []                 # cannot list is still a dashboard
            self.status.setText(f"The research history could not be read: {exc}")

        self.runs.setRowCount(len(self._runs))
        for row, entry in enumerate(self._runs):
            best = ("—" if entry.best_score is None
                    else f"{entry.best_score:.0f}/100")
            for column, text in enumerate((
                    entry.created_at.replace("T", " ").rstrip("Z"),
                    entry.symbol, entry.style, f"{entry.experiments:,}",
                    f"{entry.survivors:,}", f"{entry.combinations:,}", best)):
                item = QTableWidgetItem(text)
                if column and column != 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                          | Qt.AlignmentFlag.AlignVCenter)
                if column == 4 and not entry.survivors:
                    item.setForeground(QColor(PALETTE.text_muted))
                self.runs.setItem(row, column, item)
        self.runs.resizeColumnsToContents()

        if not self._runs:
            self.status.setText(
                "No research has been kept yet. Press Run research to start "
                "one, or use `cli research --save`.")
            self.detail.clear()

    def _on_run_selected(self) -> None:
        row = self.runs.currentRow()
        self.delete_button.setEnabled(0 <= row < len(self._runs))
        if not (0 <= row < len(self._runs)):
            return
        stored = self._store.load(self._runs[row].id)
        if stored is None:
            self.status.setText(
                f"Run {self._runs[row].id} is listed but its file could not be "
                f"read. It may have been moved or deleted outside the "
                f"application.")
            self.experiments.setRowCount(0)
            self.candidates.setRowCount(0)
            return
        self._report = stored.get("report", {}) or {}
        self._fill_experiments()
        self._fill_candidates()
        self.detail.setPlainText(self._run_detail())

    # -- experiments -----------------------------------------------------

    def _fill_experiments(self) -> None:
        rows = list((self._report or {}).get("experiments", []) or [])
        self.experiments.setRowCount(len(rows))
        for row, experiment in enumerate(rows):
            hypothesis = experiment.get("hypothesis", {}) or {}
            survived = len(experiment.get("survivors", []) or [])
            outcome = experiment.get("error") or experiment.get("verdict", "")
            cells = (str(experiment.get("round", 0) + 1),
                     hypothesis.get("idea", ""),
                     f"{int(experiment.get('combinations', 0)):,}",
                     f"{int(experiment.get('shortlisted', 0)):,}",
                     f"{survived:,}", outcome)
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column in (0, 2, 3, 4):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                          | Qt.AlignmentFlag.AlignVCenter)
                if experiment.get("error"):
                    item.setForeground(QColor(PALETTE.warning))
                elif not survived and column == 5:
                    item.setForeground(QColor(PALETTE.text_muted))
                self.experiments.setItem(row, column, item)
        header = self.experiments.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)

    # -- candidates ------------------------------------------------------

    def _candidates(self) -> list[dict[str, Any]]:
        """Every survivor across the run, deduplicated, best first."""
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for experiment in (self._report or {}).get("experiments", []) or []:
            for finding in experiment.get("survivors", []) or []:
                label = finding.get("label", "")
                if label in seen:
                    continue
                seen.add(label)
                out.append(finding)
        out.sort(key=lambda f: -((f.get("robustness") or {}).get("total") or 0))
        return out

    def _fill_candidates(self) -> None:
        rows = self._candidates()
        self.candidates.setRowCount(len(rows))
        for row, finding in enumerate(rows):
            score = finding.get("robustness") or {}
            confirmation = finding.get("confirmation") or {}
            research = (confirmation.get("research") or {})
            holdout = (confirmation.get("holdout") or {})

            if score.get("blocked"):
                grade = "disqualified"
            elif score.get("total") is None:
                grade = "—"
            else:
                grade = f"{score['total']:.0f}/100 {score.get('grade', '')}"

            cells = (grade, finding.get("label", ""),
                     _pair(research.get("trades"), holdout.get("trades")),
                     _pair((research.get("metrics") or {}).get("net_profit"),
                           (holdout.get("metrics") or {}).get("net_profit"),
                           "{:+,.0f}"),
                     finding.get("verdict", ""))
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column in (2, 3):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                          | Qt.AlignmentFlag.AlignVCenter)
                if column == 0:
                    item.setForeground(QColor(
                        PALETTE.short if score.get("blocked")
                        else PALETTE.long if (score.get("total") or 0) >= 75
                        else PALETTE.text))
                self.candidates.setItem(row, column, item)
        header = self.candidates.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    def _on_candidate_selected(self) -> None:
        rows = self._candidates()
        row = self.candidates.currentRow()
        if 0 <= row < len(rows):
            self.detail.setPlainText(_candidate_report(rows[row]))

    # -- the reports -----------------------------------------------------

    def _run_detail(self) -> str:
        report = self._report or {}
        out = [f"{report.get('symbol', '?')} — {report.get('style', '?')}",
               f"{len(report.get('experiments', []) or [])} experiments over "
               f"{int(report.get('total_combinations', 0)):,} combinations in "
               f"{float(report.get('elapsed_seconds', 0.0)):.1f}s.", ""]
        for note in report.get("notes", []) or []:
            out.append(note)
            out.append("")
        out.append("Select a candidate above for its full research report.")
        return "\n".join(out)

    # -- running ---------------------------------------------------------

    def on_run(self) -> None:
        if self._bars is None:
            self.status.setText(
                "Load a dataset in the main window first — research runs on "
                "the data you have open.")
            return
        from ...finder.styles import style as get_style
        from ...research.loop import run_loop
        from ..workers import TaskRunner

        chosen = get_style(self.style_box.currentData() or "intraday")
        rounds = int(self.rounds.value())
        depth = self.depth.currentData() or "standard"
        bars = self._bars

        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.show()
        self.status.setText(
            f"Running {rounds} round(s) on {len(bars):,} bars. Every "
            f"hypothesis is a real search, so this takes as long as the "
            f"searches do.")

        self._worker = TaskRunner(self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)

        def job(progress=None, cancel=None):
            def forward(done: int, total: int, message: str) -> None:
                if cancel is not None and cancel.cancelled:
                    from ...core.errors import CancelledError

                    raise CancelledError("The research was stopped.")
                if progress is not None:
                    progress(done, total, message)

            return run_loop(bars, chosen, rounds=rounds, validate=depth,
                            progress=forward)

        # No label: start(fn, *args) forwards everything to the job, and a
        # label here would bind to the job's first parameter.
        self._worker.start(job)

    def on_cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()

    def _on_progress(self, done: int, total: int, message: str) -> None:
        if total > 0:
            self.progress.setValue(int(100 * done / total))
        if message:
            self.status.setText(message)

    def _finish_ui(self) -> None:
        self.progress.hide()
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def _on_failed(self, message: str, detail: str) -> None:
        self._finish_ui()
        self.status.setText(message)
        log.error("Research run failed: %s\n%s", message, detail)

    def _on_cancelled(self) -> None:
        self._finish_ui()
        self.status.setText("Stopped. Nothing was saved.")

    def _on_finished(self, report: Any) -> None:
        self._finish_ui()
        try:
            timeframe = getattr(getattr(self._bars, "timeframe", None),
                                "label", "")
            self._store.save(report, timeframe=timeframe)
        except Exception as exc:            # noqa: BLE001
            log.exception("The research run could not be saved")
            show_error(self, exc, "Could not save the run")
        self.refresh()
        if self.runs.rowCount():
            self.runs.selectRow(0)
        survivors = len(getattr(report, "survivors", ()) or ())
        self.status.setText(
            f"Finished: {len(report.experiments)} experiments over "
            f"{report.total_combinations:,} combinations, "
            f"{survivors} candidate(s) not disqualified.")

    # -- deleting --------------------------------------------------------

    def on_delete(self) -> None:
        row = self.runs.currentRow()
        if not (0 <= row < len(self._runs)):
            return
        entry = self._runs[row]
        if not confirm(self, "Delete research run",
                       f"Delete the run from {entry.created_at}? The "
                       f"experiments it recorded — including the ones that "
                       f"found nothing — go with it.", "Delete"):
            return
        try:
            self._store.remove(entry.id)
        except Exception as exc:            # noqa: BLE001
            show_error(self, exc, "Could not delete")
            return
        self.experiments.setRowCount(0)
        self.candidates.setRowCount(0)
        self.detail.clear()
        self.refresh()


def _candidate_report(finding: dict[str, Any]) -> str:
    """One candidate's whole story: how it did, and what it survived.

    Blockers come first and the score is withheld when one fired, because a
    number printed beside a disqualifying reason is a number someone will quote
    without the reason.
    """
    out: list[str] = [finding.get("label", ""), ""]
    score = finding.get("robustness") or {}

    if score.get("blocked"):
        out.append("DISQUALIFIED — not scored.")
        for blocker in score.get("blockers", []) or []:
            out.append(f"  - {blocker}")
        out.append("")
    else:
        total = score.get("total")
        headline = "unmeasured" if total is None else f"{total:.0f}/100"
        out.append(f"Robustness: {headline} — {score.get('grade', '')} "
                   f"({score.get('measured', 0)} of "
                   f"{len(score.get('dimensions', []) or [])} dimensions)")
        out.append("")
        for dimension in score.get("dimensions", []) or []:
            mark = ("  n/a" if not dimension.get("applicable")
                    else f"{dimension.get('score', 0.0):5.2f}")
            out.append(f"  {mark}  {dimension.get('label', '')}: "
                       f"{dimension.get('detail', '')}")
        out.append("")

    confirmation = finding.get("confirmation") or {}
    if confirmation:
        out.append("Engine backtest (research | locked):")
        research = (confirmation.get("research") or {})
        holdout = (confirmation.get("holdout") or {})
        from ...finder.confirm import HEADLINE_METRICS

        width = max(len(label) for _key, label in HEADLINE_METRICS)
        for key, label in HEADLINE_METRICS:
            left = (research.get("metrics") or {}).get(key)
            right = (holdout.get("metrics") or {}).get(key)
            if left is None and right is None:
                continue
            out.append(f"  {label:<{width}}  "
                       f"{_pair(left, right, '{:,.2f}'):>26}")
        agreement = confirmation.get("agreement") or {}
        if not agreement.get("agrees", True):
            out.append("")
            out.append(f"  The engine did not reproduce the search's own "
                       f"figure: {agreement.get('reason', '')}")
        for note in confirmation.get("notes", []) or []:
            out.append(f"  {note}")
        out.append("")

    for note in score.get("notes", []) or []:
        out.append(note)
        out.append("")
    for concern in finding.get("concerns", []) or []:
        out.append(f"Concern: {concern}")
    return "\n".join(out)
