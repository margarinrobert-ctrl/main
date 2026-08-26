"""Monte Carlo resampling of the run that is loaded.

A backtest draws one path. The dialog's job is to show the distribution that
path came from, and to be blunt about what resampling can and cannot answer:
it describes the range of outcomes *these trades* could have produced, and says
nothing at all about whether the strategy has an edge.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                               QDoubleSpinBox, QHBoxLayout, QHeaderView, QLabel,
                               QProgressBar, QPushButton, QSpinBox,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from ...analytics.montecarlo import RELIABLE_TRADES, METHODS
from ...logging_setup import get_logger
from ..theme import PALETTE, Fonts, money
from ..widgets.common import Card, show_error, show_info
from ..workers import TaskRunner, monte_carlo_task

log = get_logger(__name__)

_METHOD_LABELS = {
    "shuffle": "Shuffle the order",
    "bootstrap": "Resample trades (bootstrap)",
    "block": "Resample in blocks",
}
_METHOD_HELP = {
    "shuffle": "The same trades in a different order. Every draw finishes at "
               "the same equity, so this answers one question only: how much "
               "of the drawdown was the order the trades happened to arrive in?",
    "bootstrap": "Draw the same number of trades with replacement. The final "
                 "equity moves too. Assumes the trades you have are a fair "
                 "sample of the ones the strategy would take.",
    "block": "The same, but in contiguous runs, so a losing streak survives "
             "the resampling. Use this when the trades cluster by regime, "
             "which they usually do.",
}


class MonteCarloDialog(QDialog):
    """Resample the loaded run's trades and show the distribution."""

    def __init__(self, result: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Monte Carlo — resample this run's trades")
        self.resize(980, 720)
        self._result = result
        self._mc: Any = None
        self._runner = TaskRunner(self)
        self._build()
        self._connect()
        self._describe_method()

    # -- construction ------------------------------------------------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(9)

        trades = len(getattr(self._result, "trades", ()) or ())
        warning = QLabel(
            "This resamples the trades the strategy already took. It cannot "
            "tell you whether the strategy has an edge — if these trades came "
            "from a rule fitted to this data, every draw is fitted to it too. "
            "The question it answers is 'given these trades, what range of "
            "paths?', never 'will this work?'.")
        warning.setWordWrap(True)
        warning.setFont(Fonts.body(9))
        warning.setStyleSheet(
            f"color:{PALETTE.warning}; background:{PALETTE.panel_alt};"
            f"border:1px solid {PALETTE.warning}; border-radius:5px; padding:9px;")
        outer.addWidget(warning)

        controls = QHBoxLayout()
        controls.setSpacing(9)
        controls.addWidget(self._label("Method"))
        self.method = QComboBox()
        for key in METHODS:
            self.method.addItem(_METHOD_LABELS[key], key)
        self.method.setCurrentIndex(max(0, self.method.findData("block")))
        controls.addWidget(self.method)

        controls.addWidget(self._label("Draws"))
        self.draws = QSpinBox()
        self.draws.setRange(100, 200_000)
        self.draws.setSingleStep(1000)
        self.draws.setValue(5000)
        controls.addWidget(self.draws)

        self.compounded = QCheckBox("Compound")
        self.compounded.setToolTip(
            "Contribute each trade's return as a fraction of the equity it was "
            "opened against, so an early loss costs more than a late one. "
            "Unticked, each trade contributes its cash result, which is what a "
            "fixed position size produces.")
        controls.addWidget(self.compounded)

        controls.addWidget(self._label("Ruin below"))
        self.ruin = QDoubleSpinBox()
        self.ruin.setRange(0.0, 1e12)
        self.ruin.setDecimals(0)
        self.ruin.setGroupSeparatorShown(True)
        self.ruin.setValue(self._starting_capital() * 0.5)
        self.ruin.setToolTip(
            "Count a draw as ruined if its equity ever closes below this. "
            "Measured at trade closes: an open position that went far against "
            "you and came back does not appear.")
        controls.addWidget(self.ruin)

        controls.addStretch(1)
        self.run_button = QPushButton("  RUN")
        self.run_button.setObjectName("Primary")
        self.run_button.setMinimumHeight(30)
        controls.addWidget(self.run_button)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("Danger")
        self.cancel_button.hide()
        controls.addWidget(self.cancel_button)
        outer.addLayout(controls)

        self.method_help = QLabel("")
        self.method_help.setWordWrap(True)
        self.method_help.setFont(Fonts.body(9))
        self.method_help.setStyleSheet(f"color:{PALETTE.text_muted};")
        outer.addWidget(self.method_help)

        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.hide()
        outer.addWidget(self.progress)

        self.headline = QLabel(
            f"{trades:,} trades to resample."
            + ("" if trades >= RELIABLE_TRADES else
               f"  Under {RELIABLE_TRADES} trades no percentile below will mean "
               f"much: a thousand draws over {trades} numbers is still "
               f"{trades} numbers."))
        self.headline.setWordWrap(True)
        self.headline.setFont(Fonts.body(10, bold=True))
        self.headline.setStyleSheet(
            f"color:{PALETTE.text_muted if trades >= RELIABLE_TRADES else PALETTE.warning};")
        outer.addWidget(self.headline)

        table_card = Card("The distribution")
        self.table = QTableWidget(4, 6)
        self.table.setHorizontalHeaderLabels(
            ["", "5th", "25th", "median", "75th", "95th"])
        self.table.setVerticalHeaderLabels([""] * 4)
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
        self.table.setFixedHeight(4 * 23 + 30)
        table_card.add(self.table)
        outer.addWidget(table_card)

        self.histogram = _Histogram()
        outer.addWidget(self.histogram, 1)

        self.notes = QLabel("")
        self.notes.setWordWrap(True)
        self.notes.setFont(Fonts.body(9))
        self.notes.setStyleSheet(f"color:{PALETTE.text_dim};")
        self.notes.setMinimumHeight(72)
        self.notes.setAlignment(Qt.AlignmentFlag.AlignTop)
        outer.addWidget(self.notes)

        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        outer.addLayout(row)

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setFont(Fonts.body(9))
        label.setStyleSheet(f"color:{PALETTE.text_dim};")
        return label

    def _starting_capital(self) -> float:
        capital = float(getattr(getattr(self._result, "config", None),
                                "starting_capital", 0.0) or 0.0)
        if capital > 0:
            return capital
        trades = list(getattr(self._result, "trades", ()) or ())
        return float(trades[0].equity_at_entry) if trades else 100_000.0

    def _connect(self) -> None:
        self.method.currentIndexChanged.connect(self._describe_method)
        self.run_button.clicked.connect(self.run)
        self.cancel_button.clicked.connect(self._runner.cancel)
        self._runner.progress.connect(self._on_progress)
        self._runner.finished.connect(self._on_finished)
        self._runner.failed.connect(self._on_failed)
        self._runner.cancelled.connect(self._on_cancelled)
        self._runner.stateChanged.connect(self._on_state)

    def _describe_method(self, *_args) -> None:
        self.method_help.setText(
            _METHOD_HELP.get(self.method.currentData() or "", ""))

    # -- running -----------------------------------------------------------

    @property
    def busy(self) -> bool:
        return self._runner.busy

    def run(self) -> None:
        if self._runner.busy:
            return
        if not list(getattr(self._result, "trades", ()) or ()):
            show_info(self, "Monte Carlo",
                      "This run produced no trades, so there is nothing to "
                      "resample.")
            return
        self.headline.setText("Resampling…")
        self.headline.setStyleSheet(f"color:{PALETTE.text_muted};")
        self.notes.setText("")
        self._runner.start(
            monte_carlo_task, self._result,
            method=self.method.currentData() or "block",
            draws=self.draws.value(), compounded=self.compounded.isChecked(),
            ruin_level=float(self.ruin.value()))

    def _on_state(self, busy: bool) -> None:
        self.progress.setVisible(busy)
        self.run_button.setEnabled(not busy)
        self.cancel_button.setVisible(busy)
        for widget in (self.method, self.draws, self.compounded, self.ruin):
            widget.setEnabled(not busy)
        if not busy:
            self.progress.reset()

    def _on_progress(self, current: int, total: int, message: str) -> None:
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(current)
        self.progress.setFormat(f"{message}  (%p%)" if message else "%p%")

    def _on_failed(self, message: str, detail: str) -> None:
        self.headline.setText("The Monte Carlo did not run.")
        self.headline.setStyleSheet(f"color:{PALETTE.danger};")
        self.notes.setText(message)
        show_error(self, message, "Monte Carlo Failed", detail)

    def _on_cancelled(self) -> None:
        self.headline.setText("Cancelled.")
        self.headline.setStyleSheet(f"color:{PALETTE.text_muted};")

    def _on_finished(self, mc: Any) -> None:
        self._mc = mc
        self._fill(mc)

    # -- presentation ------------------------------------------------------

    def _fill(self, mc: Any) -> None:
        currency = getattr(getattr(self._result, "bars", None), "instrument", None)
        currency = getattr(currency, "currency", "") or ""
        quantiles = (5, 25, 50, 75, 95)
        rows = [
            ("Final equity", mc.percentiles(mc.final_equity, quantiles), 0),
            ("Worst drawdown", mc.percentiles(mc.max_drawdown, quantiles), 0),
            ("Worst drawdown %", mc.percentiles(mc.max_drawdown_pct, quantiles), 1),
            ("Trades under water",
             mc.percentiles(mc.longest_drawdown.astype(float), quantiles), 0),
        ]
        self.table.setRowCount(len(rows))
        for r, (label, values, decimals) in enumerate(rows):
            head = QTableWidgetItem(label)
            head.setFont(Fonts.body(9))
            self.table.setItem(r, 0, head)
            for c, q in enumerate(quantiles, start=1):
                item = QTableWidgetItem(f"{values[q]:,.{decimals}f}")
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                      | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(r, c, item)

        self.histogram.set_data(mc.final_equity, mc.observed.final_equity,
                                mc.starting_capital)

        parts = [f"The backtest finished at "
                 f"{money(mc.observed.final_equity, currency)} with a worst "
                 f"drawdown of {money(mc.observed.max_drawdown, currency)}."]
        if mc.method != "shuffle":
            parts.append(f"It finished better than "
                         f"{mc.rank_of_observed() * 100:.0f}% of the draws.")
        parts.append(f"Its drawdown was milder than "
                     f"{(1 - mc.drawdown_rank_of_observed()) * 100:.0f}% of them.")
        parts.append(f"{mc.losing_probability * 100:.1f}% of draws lost money; "
                     f"{mc.ruin_probability * 100:.1f}% closed below "
                     f"{mc.ruin_level:,.0f} at some point.")
        parts.append(mc.verdict().capitalize() + ".")
        self.headline.setText("  ".join(parts))
        good = (mc.losing_probability < 0.25 and mc.ruin_probability <= 0.05)
        self.headline.setStyleSheet(
            f"color:{PALETTE.success if good else PALETTE.warning};")
        self.notes.setText("\n\n".join(mc.notes))

    # -- lifecycle ---------------------------------------------------------

    def closeEvent(self, event) -> None:    # noqa: N802
        if self._runner.busy:
            self._runner.cancel()
            self._runner.wait(3000)
        super().closeEvent(event)


class _Histogram(QWidget):
    """Final equity across the draws, with the backtest's own result marked."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(150)
        self._counts: np.ndarray | None = None
        self._edges: np.ndarray | None = None
        self._observed = 0.0
        self._start = 0.0

    def set_data(self, values: Any, observed: float, start: float) -> None:
        values = np.asarray(values, dtype="float64")
        if values.size == 0 or not np.isfinite(values).any():
            self._counts = None
        else:
            spread = float(values.max() - values.min())
            if spread <= 0:
                # Every draw ended in the same place -- a shuffle. One bar is
                # the truth here, and pretending to a distribution is not.
                self._counts = np.array([values.size], dtype="float64")
                self._edges = np.array([values.min(), values.min()])
            else:
                counts, edges = np.histogram(values, bins=48)
                self._counts = counts.astype("float64")
                self._edges = edges
        self._observed = float(observed)
        self._start = float(start)
        self.update()

    def paintEvent(self, event) -> None:     # noqa: N802
        painter = QPainter(self)
        try:
            self._paint(painter)
        finally:
            # Qt aborts the whole backing store if a painter is still active
            # when the handler returns, so this must survive any failure above.
            painter.end()

    def _paint(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(self.rect(), QColor(PALETTE.panel_bg))
        if self._counts is None or self._edges is None:
            painter.setPen(QPen(QColor(PALETTE.text_muted)))
            painter.setFont(Fonts.body(9))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Run the resampling to see the distribution "
                             "of final equity.")
            return

        left, top = 8.0, 8.0
        right = self.width() - 8.0
        bottom = self.height() - 22.0
        width = max(1.0, right - left)
        height = max(1.0, bottom - top)
        peak = float(self._counts.max()) or 1.0
        low, high = float(self._edges[0]), float(self._edges[-1])
        span = (high - low) or 1.0

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(PALETTE.accent))
        bars = self._counts.size
        bar_width = width / bars
        for index, count in enumerate(self._counts):
            bar_height = height * (count / peak)
            painter.drawRect(QRectF(left + index * bar_width,
                                    bottom - bar_height,
                                    max(1.0, bar_width - 1.0), bar_height))

        def mark(value: float, colour: str, caption: str) -> None:
            if not (low <= value <= high):
                return
            x = left + width * ((value - low) / span)
            painter.setPen(QPen(QColor(colour), 2))
            painter.drawLine(int(x), int(top), int(x), int(bottom))
            painter.setFont(Fonts.body(8))
            painter.drawText(QRectF(x - 60, bottom + 2, 120, 18),
                             Qt.AlignmentFlag.AlignCenter, caption)

        mark(self._start, PALETTE.text_muted, "break even")
        mark(self._observed, PALETTE.warning, "the backtest")
