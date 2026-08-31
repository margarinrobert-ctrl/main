"""The data-quality report dialog.

A :class:`~tradingbacktester.data.validation.DataQualityReport` is a list of
findings, and a bare list of findings is not much use: what a user needs to know
first is whether they can trust a backtest run on this data at all.  So the
dialog leads with that verdict, then groups the findings by severity and states
in one line what each severity *means for a backtest* -- an error invalidates
the result, a warning colours it, a note is simply worth knowing.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QGuiApplication
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from ...data.validation import (SEVERITY_ERROR, SEVERITY_INFO, SEVERITY_WARNING,
                                DataIssue, DataQualityReport)
from ..theme import PALETTE, Fonts
from ..widgets.common import Card, hline

log = logging.getLogger(__name__)


#: Group heading, one-line consequence and colour for each severity, in the
#: order a reader should meet them.
_GROUPS: tuple[tuple[str, str, str, str], ...] = (
    (SEVERITY_ERROR, "Problems",
     "A backtest on this data would be meaningless until these are fixed.",
     "danger"),
    (SEVERITY_WARNING, "Warnings",
     "A backtest will run, but read these before believing the result.",
     "warning"),
    (SEVERITY_INFO, "Notes",
     "Nothing is wrong; these are facts about the data worth knowing.",
     "info"),
)


class DataQualityDialog(QDialog):
    """Show a :class:`DataQualityReport` for the loaded dataset.

    Read-only: cleaning is done elsewhere, deliberately, so that opening this
    dialog can never change the data a result was produced from.
    """

    def __init__(self, report: DataQualityReport, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._report = report
        self.setWindowTitle("Data Quality")
        self.setMinimumSize(760, 520)
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

        usable = self._report.is_usable
        head = QHBoxLayout()
        head.setSpacing(11)
        badge = QLabel()
        badge.setPixmap(icon("check" if usable else "warning", 26,
                             PALETTE.success if usable else PALETTE.danger)
                        .pixmap(26, 26))
        badge.setAlignment(Qt.AlignmentFlag.AlignTop)
        head.addWidget(badge)

        headline = QVBoxLayout()
        headline.setSpacing(2)
        title = QLabel("This dataset is usable" if usable
                       else "This dataset has problems that make a backtest meaningless")
        title.setFont(Fonts.heading(12))
        title.setStyleSheet(
            f"color:{PALETTE.success if usable else PALETTE.danger};")
        title.setWordWrap(True)
        headline.addWidget(title)

        self._subtitle = QLabel(self._headline_detail())
        self._subtitle.setStyleSheet(f"color:{PALETTE.text_dim};")
        self._subtitle.setWordWrap(True)
        headline.addWidget(self._subtitle)
        head.addLayout(headline, 1)
        lay.addLayout(head)

        lay.addWidget(hline())

        card = Card("Findings")
        self.tree = QTreeWidget()
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(["Issue", "Severity", "Code", "Bars", "Example"])
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(False)
        self.tree.setUniformRowHeights(False)
        self.tree.setSelectionBehavior(QTreeWidget.SelectionBehavior.SelectRows)
        self.tree.setWordWrap(True)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.tree.setColumnWidth(4, 240)
        card.add(self.tree, 1)
        lay.addWidget(card, 1)

        legend = QLabel(
            "Bars is how many bars a finding affects. Example is the first "
            "affected bar, so you can go and look at it in the original file.")
        legend.setWordWrap(True)
        legend.setObjectName("Hint")
        lay.addWidget(legend)

        buttons = QHBoxLayout()
        copy = QPushButton("  Copy report")
        copy.setObjectName("Ghost")
        copy.setIcon(icon("copy", 15))
        copy.setToolTip("Copy the whole report to the clipboard as plain text")
        copy.clicked.connect(self._copy_report)
        buttons.addWidget(copy)
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("Primary")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        lay.addLayout(buttons)

    # ------------------------------------------------------------------
    # content
    # ------------------------------------------------------------------

    def _headline_detail(self) -> str:
        """The line under the verdict: what the dataset is and what was found."""
        r = self._report
        parts: list[str] = []
        if r.symbol or r.timeframe:
            parts.append(f"{r.symbol} {r.timeframe}".strip())
        parts.append(f"{r.bar_count:,} bars")
        if r.start_text and r.end_text:
            parts.append(f"{r.start_text} to {r.end_text} UTC")
        counts = (f"{len(r.errors)} problem(s), {len(r.warnings)} warning(s), "
                  f"{len(r.infos)} note(s)")
        return " · ".join(parts) + " — " + counts

    def _populate(self) -> None:
        """Fill the tree with one group per severity, worst first."""
        self.tree.clear()
        found_any = False
        for severity, heading, consequence, colour_name in _GROUPS:
            issues = [i for i in self._report.sorted_issues()
                      if i.severity == severity]
            if not issues:
                continue
            found_any = True
            colour = QColor(getattr(PALETTE, colour_name))
            group = QTreeWidgetItem(
                [f"{heading} ({len(issues)})", "", "", "", consequence])
            group.setFont(0, Fonts.body(10, bold=True))
            group.setForeground(0, QBrush(colour))
            group.setForeground(4, QBrush(QColor(PALETTE.text_dim)))
            group.setBackground(0, QBrush(QColor(PALETTE.elevated)))
            group.setBackground(1, QBrush(QColor(PALETTE.elevated)))
            group.setBackground(2, QBrush(QColor(PALETTE.elevated)))
            group.setBackground(3, QBrush(QColor(PALETTE.elevated)))
            group.setBackground(4, QBrush(QColor(PALETTE.elevated)))
            group.setToolTip(4, consequence)
            self.tree.addTopLevelItem(group)
            for issue in issues:
                group.addChild(self._issue_item(issue, colour))
            group.setExpanded(True)

        if not found_any:
            clean = QTreeWidgetItem(
                ["Nothing to report: every check passed on this dataset.",
                 "", "", "", ""])
            clean.setForeground(0, QBrush(QColor(PALETTE.success)))
            clean.setFont(0, Fonts.body(10))
            self.tree.addTopLevelItem(clean)

    def _issue_item(self, issue: DataIssue, colour: QColor) -> QTreeWidgetItem:
        """One finding as a row: message, severity, code, count and example."""
        where = issue.example_text
        if issue.example_index is not None:
            where = f"bar {issue.example_index:,}" + (f": {where}" if where else "")
        item = QTreeWidgetItem([issue.message, issue.severity.upper(), issue.code,
                                f"{issue.count:,}", where])
        item.setToolTip(0, issue.message)
        item.setToolTip(4, where)
        item.setForeground(1, QBrush(colour))
        item.setFont(1, Fonts.numeric(8, bold=True))
        item.setFont(2, Fonts.numeric(8))
        item.setFont(3, Fonts.numeric(9))
        item.setFont(4, Fonts.numeric(8))
        item.setForeground(2, QBrush(QColor(PALETTE.text_muted)))
        item.setForeground(4, QBrush(QColor(PALETTE.text_dim)))
        item.setTextAlignment(3, int(Qt.AlignmentFlag.AlignRight |
                                     Qt.AlignmentFlag.AlignVCenter))
        return item

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------

    def _copy_report(self) -> None:
        """Put the plain-text report on the clipboard.

        Users paste this into a support request or a note to themselves; the
        text form is the report's own ``summary_text`` so it stays identical to
        what goes in the log.
        """
        clipboard: Any = QGuiApplication.clipboard()
        if clipboard is None:  # pragma: no cover - no clipboard on some servers
            log.warning("No clipboard is available, so the report was not copied.")
            return
        clipboard.setText(self._report.summary_text())
        log.info("Data quality report copied to the clipboard.")
