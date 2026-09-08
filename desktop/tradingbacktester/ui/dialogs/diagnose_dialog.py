"""What is wrong with this run, and how much of a book is really one bet.

Two tabs, because they answer the two questions a user has after a backtest
finishes and the number at the top is green.

The **Diagnosis** tab reads the finished run and lists measured properties of
it, worst first, each with the number that says so and the experiment that
would settle it.  It is careful never to promise that a change will help: this
application does not know that, and a suggestion phrased as a prediction is a
fabricated backtest.

The **Correlation** tab needs at least two saved runs and answers a different
question -- whether the strategies in the library are separate bets or the same
one wearing different indicators.  The matrix is coloured by magnitude so the
clusters are visible without reading any of the numbers, and the summary line
is the effective number of independent bets, which is the only number most
readers need.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QGuiApplication
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QTabWidget, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from ...analytics.correlation import CorrelationReport, correlate_results
from ...analytics.diagnose import Diagnosis, diagnose
from ..theme import PALETTE, Fonts
from ..widgets.common import Card, hline

log = logging.getLogger(__name__)

#: Heading, meaning and palette colour per severity, worst first.
_GROUPS: tuple[tuple[str, str, str, str], ...] = (
    ("blocker", "Blocking", "Read these before you read the profit — each one "
     "can make the rest of the report meaningless.", "danger"),
    ("warning", "Worth checking", "The result stands, but these say something "
     "about how much weight it will bear.", "warning"),
    ("note", "Facts about this run", "Nothing is wrong; these are properties "
     "worth knowing about what you just ran.", "info"),
    ("good", "Holds up", "These checks found nothing against it.", "success"),
)


def _colour(name: str) -> str:
    return {"danger": PALETTE.danger, "warning": PALETTE.warning,
            "info": PALETTE.text_dim, "success": PALETTE.success}.get(
                name, PALETTE.text)


class DiagnoseDialog(QDialog):
    """Diagnose the current run and correlate the runs alongside it."""

    def __init__(self, result: Any, spec: Any = None,
                 others: Sequence[Any] = (), parent: QWidget | None = None
                 ) -> None:
        super().__init__(parent)
        self._result = result
        self._spec = spec
        self._others = list(others)
        self._diagnosis: Diagnosis | None = None
        self._correlation: CorrelationReport | None = None
        self.setWindowTitle("Diagnose Strategy")
        self.setMinimumSize(880, 620)
        self._build_ui()
        self._populate()

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        from ..icons import icon

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(11)
        self._badge = QLabel()
        self._badge.setAlignment(Qt.AlignmentFlag.AlignTop)
        head.addWidget(self._badge)
        block = QVBoxLayout()
        block.setSpacing(2)
        self._title = QLabel("Measuring…")
        self._title.setFont(Fonts.heading(12))
        self._title.setWordWrap(True)
        block.addWidget(self._title)
        self._subtitle = QLabel("")
        self._subtitle.setStyleSheet(f"color:{PALETTE.text_dim};")
        self._subtitle.setWordWrap(True)
        block.addWidget(self._subtitle)
        head.addLayout(block, 1)
        lay.addLayout(head)
        lay.addWidget(hline())

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_findings_tab(), icon("search", 15),
                         "  Diagnosis")
        self.tabs.addTab(self._build_correlation_tab(), icon("compare", 15),
                         "  Correlation")
        lay.addWidget(self.tabs, 1)

        buttons = QHBoxLayout()
        copy = QPushButton("  Copy report")
        copy.setObjectName("Ghost")
        copy.setIcon(icon("copy", 15))
        copy.clicked.connect(self._copy_report)
        buttons.addWidget(copy)
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("Primary")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        lay.addLayout(buttons)

    def _build_findings_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 8, 0, 0)
        card = Card("Findings")
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Finding", "What it says"])
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(False)
        self.tree.setWordWrap(True)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tree.setColumnWidth(0, 300)
        card.add(self.tree, 1)
        lay.addWidget(card, 1)
        footer = QLabel(
            "Nothing here predicts that a change will improve the result. Each "
            "finding names a measured property of this run and the experiment "
            "that would settle it — running that experiment is what produces "
            "an answer.")
        footer.setWordWrap(True)
        footer.setObjectName("Hint")
        lay.addWidget(footer)
        return page

    def _build_correlation_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 8, 0, 0)
        self._corr_head = QLabel("")
        self._corr_head.setWordWrap(True)
        lay.addWidget(self._corr_head)

        card = Card("Return correlation")
        self.matrix = QTableWidget(0, 0)
        self.matrix.setAlternatingRowColors(False)
        self.matrix.setShowGrid(False)
        self.matrix.setFont(Fonts.numeric(9))
        self.matrix.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        card.add(self.matrix, 1)
        lay.addWidget(card, 1)

        pairs = Card("Pair by pair")
        self.pairs = QTreeWidget()
        self.pairs.setColumnCount(5)
        self.pairs.setHeaderLabels(
            ["Pair", "Correlation", "In market together", "Same side",
             "Entries coincide"])
        self.pairs.setRootIsDecorated(False)
        for column in range(1, 5):
            self.pairs.header().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents)
        self.pairs.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        pairs.add(self.pairs, 1)
        lay.addWidget(pairs, 1)

        note = QLabel(
            "A low correlation is not on its own a reason to add a strategy. A "
            "decorrelated leg with no edge of its own still raises a book's "
            "net profit while cutting its Sharpe and deepening its drawdown, "
            "and nothing in this table would show that.")
        note.setWordWrap(True)
        note.setObjectName("Hint")
        lay.addWidget(note)
        return page

    # ------------------------------------------------------------------
    # content
    # ------------------------------------------------------------------

    def _populate(self) -> None:
        from ..icons import icon

        try:
            self._diagnosis = diagnose(self._result, self._spec)
        except Exception:                       # noqa: BLE001
            log.exception("Diagnosis failed")
            self._title.setText("The diagnosis could not be completed.")
            self._subtitle.setText(
                "The details are in the log file. The backtest itself is "
                "unaffected.")
            return

        blockers = self._diagnosis.blockers
        warnings = self._diagnosis.by_severity("warning")
        healthy = not blockers and not warnings
        tone = PALETTE.success if healthy else (
            PALETTE.danger if blockers else PALETTE.warning)
        self._badge.setPixmap(
            icon("check" if healthy else "warning", 26, tone).pixmap(26, 26))
        self._title.setStyleSheet(f"color:{tone};")
        if blockers:
            self._title.setText(
                f"{len(blockers)} finding "
                f"{'changes' if len(blockers) == 1 else 'change'} what this "
                f"result means" if len(blockers) == 1 else
                f"{len(blockers)} findings change what this result means")
        elif warnings:
            self._title.setText(
                f"{len(warnings)} thing"
                f"{'' if len(warnings) == 1 else 's'} worth checking")
        else:
            self._title.setText("Nothing found against this run")
        self._subtitle.setText(
            f"{self._diagnosis.trades:,} trades measured. "
            + (self._diagnosis.control.describe()
               if self._diagnosis.control is not None
               else "The matched control did not run on this result."))

        self._fill_findings()
        self._fill_correlation()

    def _fill_findings(self) -> None:
        assert self._diagnosis is not None
        self.tree.clear()
        for severity, heading, meaning, colour in _GROUPS:
            findings = self._diagnosis.by_severity(severity)
            if not findings:
                continue
            group = QTreeWidgetItem(self.tree, [f"{heading} ({len(findings)})",
                                                meaning])
            group.setFont(0, Fonts.heading(10))
            group.setForeground(0, QBrush(QColor(_colour(colour))))
            group.setForeground(1, QBrush(QColor(PALETTE.text_dim)))
            for finding in findings:
                item = QTreeWidgetItem(group, [finding.headline,
                                               finding.measurement])
                item.setForeground(0, QBrush(QColor(_colour(colour))))
                if finding.suggestion:
                    child = QTreeWidgetItem(item, ["Try", finding.suggestion])
                    child.setForeground(0, QBrush(QColor(PALETTE.accent)))
            group.setExpanded(True)
        for note in self._diagnosis.notes:
            QTreeWidgetItem(self.tree, ["Note", note])
        self.tree.expandToDepth(1)

    def _fill_correlation(self) -> None:
        runs = [self._result] + [r for r in self._others if r is not self._result]
        if len(runs) < 2:
            self._corr_head.setText(
                "Correlation needs at least two runs. Run another strategy on "
                "this dataset and open this dialog again — one strategy is not "
                "a book, and there is nothing here to measure until there are "
                "two.")
            self.tabs.setTabEnabled(1, True)
            return
        try:
            self._correlation = correlate_results(runs)
        except Exception as exc:                # noqa: BLE001
            log.exception("Correlation failed")
            self._corr_head.setText(f"Correlation could not be computed: {exc}")
            return

        report = self._correlation
        summary = (f"{report.count} runs"
                   + (f" amount to about {report.effective_bets:.1f} "
                      f"independent bets."
                      if report.effective_bets is not None else "."))
        if (report.effective_bets is not None
                and report.effective_bets < report.count * 0.6):
            summary += (" Most of the apparent diversification is arithmetic: "
                        "these are largely the same position.")
        for note in report.notes:
            summary += f" {note}"
        self._corr_head.setText(summary)

        n = report.count
        self.matrix.setRowCount(n)
        self.matrix.setColumnCount(n)
        self.matrix.setHorizontalHeaderLabels(list(report.names))
        self.matrix.setVerticalHeaderLabels(list(report.names))
        for i in range(n):
            for j in range(n):
                value = float(report.matrix[i, j])
                item = QTableWidgetItem(
                    "—" if not np.isfinite(value) else f"{value:+.2f}")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if np.isfinite(value) and i != j:
                    item.setBackground(QBrush(_heat(value)))
                self.matrix.setItem(i, j, item)
        self.matrix.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)

        self.pairs.clear()
        for pair in sorted(report.pairs,
                           key=lambda p: -(abs(p.correlation)
                                           if p.correlation is not None else -1)):
            QTreeWidgetItem(self.pairs, [
                f"{pair.a}  ·  {pair.b}",
                "—" if pair.correlation is None else f"{pair.correlation:+.2f}",
                _pct(pair.exposure_overlap), _pct(pair.same_side_share),
                _pct(pair.entry_coincidence)])

    # ------------------------------------------------------------------

    def _copy_report(self) -> None:
        parts: list[str] = []
        if self._diagnosis is not None:
            parts.append(self._diagnosis.describe())
        if self._correlation is not None:
            parts.append(self._correlation.describe())
        QGuiApplication.clipboard().setText("\n\n".join(parts))


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.0%}"


def _heat(value: float) -> QColor:
    """Red for alike, blue for opposed, transparent for independent."""
    strength = min(1.0, abs(value))
    base = QColor(PALETTE.danger if value >= 0 else PALETTE.accent)
    base.setAlphaF(0.10 + 0.45 * strength)
    return base
