"""The mirror-market test: the same rule on a market that fell.

Everything in this application is measured on an instrument that went up, and a
long-biased rule inherits that whether or not it is doing anything. This dialog
runs the strategy twice — once on the data, once on the data with every log
return negated — and puts the two side by side.
"""

from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout,
                               QHeaderView, QLabel, QProgressBar, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from ...logging_setup import get_logger
from ..theme import PALETTE, Fonts, money
from ..widgets.common import Card, show_error
from ..workers import TaskRunner, mirror_task

log = get_logger(__name__)

#: Rows of the comparison: label, attribute, format, and whether bigger is
#: better for the purpose of colouring (``None`` = do not colour).
_ROWS: tuple[tuple[str, str, str, bool | None], ...] = (
    ("Drift over the sample", "drift_pct", "{:+,.1f}%", None),
    ("Trades", "trades", "{:,.0f}", None),
    ("Net profit", "net_profit", "{:+,.2f}", True),
    ("Expectancy per trade", "expectancy", "{:+,.2f}", True),
    ("Win rate", "win_rate", "{:,.1f}%", True),
    ("Profit factor", "profit_factor", "{:,.2f}", True),
    ("Max drawdown", "max_drawdown_pct", "{:,.1f}%", False),
)


class MirrorDialog(QDialog):
    """Run one strategy on a market and on its reflection."""

    def __init__(self, bars: Any, spec: Any, config: Any,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Mirror-market test — {spec.name}")
        self.resize(820, 700)
        self._bars = bars
        self._spec = spec
        self._config = config
        self._report: Any = None
        self._runner = TaskRunner(self)
        self._build()
        self._connect()
        self.run()

    # -- construction ------------------------------------------------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(9)

        explain = QLabel(
            "The mirror is this data with every log return negated: the same "
            "timestamps, the same session structure, the same bar-to-bar "
            "volatility and the same bar ranges — and the opposite drift. A "
            "rule that only makes money on the real series was betting on the "
            "direction the market happened to go.")
        explain.setWordWrap(True)
        explain.setFont(Fonts.body(9))
        explain.setStyleSheet(f"color:{PALETTE.text_dim};")
        outer.addWidget(explain)

        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.hide()
        outer.addWidget(self.progress)

        self.headline = QLabel("Running…")
        self.headline.setWordWrap(True)
        self.headline.setFont(Fonts.body(10, bold=True))
        self.headline.setStyleSheet(f"color:{PALETTE.text_muted};")
        outer.addWidget(self.headline)

        card = Card("Real against mirrored")
        self.table = QTableWidget(len(_ROWS), 3)
        self.table.setHorizontalHeaderLabels(["", "Real", "Mirrored"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setFont(Fonts.numeric(9))
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(23)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.table.setFixedHeight(len(_ROWS) * 23 + 30)
        card.add(self.table)

        self.split = QLabel("")
        self.split.setWordWrap(True)
        self.split.setFont(Fonts.numeric(9))
        self.split.setStyleSheet(f"color:{PALETTE.text};")
        card.add(self.split)
        outer.addWidget(card)

        self.notes = QLabel("")
        self.notes.setWordWrap(True)
        self.notes.setFont(Fonts.body(9))
        self.notes.setStyleSheet(f"color:{PALETTE.text_dim};")
        self.notes.setAlignment(Qt.AlignmentFlag.AlignTop)
        outer.addWidget(self.notes, 1)

        row = QHBoxLayout()
        self.rerun = QPushButton("Run Again")
        row.addWidget(self.rerun)
        row.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        outer.addLayout(row)

    def _connect(self) -> None:
        self.rerun.clicked.connect(self.run)
        self._runner.progress.connect(self._on_progress)
        self._runner.finished.connect(self._on_finished)
        self._runner.failed.connect(self._on_failed)
        self._runner.cancelled.connect(self._on_cancelled)
        self._runner.stateChanged.connect(self._on_state)

    # -- running -----------------------------------------------------------

    @property
    def busy(self) -> bool:
        return self._runner.busy

    def run(self) -> None:
        if self._runner.busy:
            return
        self.headline.setText("Running the strategy on both series…")
        self.headline.setStyleSheet(f"color:{PALETTE.text_muted};")
        self._runner.start(mirror_task, self._bars, self._spec, self._config)

    def _on_state(self, busy: bool) -> None:
        self.progress.setVisible(busy)
        self.rerun.setEnabled(not busy)
        if not busy:
            self.progress.reset()

    def _on_progress(self, current: int, total: int, message: str) -> None:
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(current)
        self.progress.setFormat(f"{message}  (%p%)" if message else "%p%")

    def _on_failed(self, message: str, detail: str) -> None:
        self.headline.setText("The mirror test did not run.")
        self.headline.setStyleSheet(f"color:{PALETTE.danger};")
        self.notes.setText(message)
        show_error(self, message, "Mirror Test Failed", detail)

    def _on_cancelled(self) -> None:
        self.headline.setText("Cancelled.")
        self.headline.setStyleSheet(f"color:{PALETTE.text_muted};")

    def _on_finished(self, report: Any) -> None:
        self._report = report
        self._fill(report)

    # -- presentation ------------------------------------------------------

    def _fill(self, report: Any) -> None:
        currency = getattr(self._bars.instrument, "currency", "") or ""
        for row, (label, key, fmt, bigger_is_better) in enumerate(_ROWS):
            head = QTableWidgetItem(label)
            head.setFont(Fonts.body(9))
            self.table.setItem(row, 0, head)
            values = (getattr(report.real, key), getattr(report.mirror, key))
            for column, value in enumerate(values, start=1):
                text = fmt.format(value) if math.isfinite(value) else "—"
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                      | Qt.AlignmentFlag.AlignVCenter)
                if bigger_is_better is not None and math.isfinite(value):
                    other = values[1 - (column - 1)]
                    if math.isfinite(other) and value != other:
                        better = (value > other) if bigger_is_better else (value < other)
                        item.setForeground(QColor(
                            PALETTE.success if better else PALETTE.danger))
                self.table.setItem(row, column, item)

        self.split.setText(
            f"Direction-independent half: "
            f"{money(report.symmetric_component, currency)}      "
            f"Direction-dependent half: "
            f"{money(report.direction_component, currency)}")

        verdict = report.verdict()
        self.headline.setText(verdict[:1].upper() + verdict[1:] + ".")
        healthy = (report.real.net_profit > 0 and report.mirror.net_profit > 0)
        self.headline.setStyleSheet(
            f"color:{PALETTE.success if healthy else PALETTE.warning};")
        self.notes.setText("\n\n".join(report.notes))

    # -- lifecycle ---------------------------------------------------------

    def closeEvent(self, event) -> None:    # noqa: N802
        if self._runner.busy:
            self._runner.cancel()
            self._runner.wait(5000)
        super().closeEvent(event)
