"""Comparing saved backtests side by side.

Equity curves on top, a metric matrix beneath. Runs rarely cover exactly the
same bars, so the curves are aligned on their overlap and indexed to 100 there,
and any mismatch is stated above the chart rather than quietly plotted through.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout,
                               QHeaderView, QLabel, QSizePolicy, QSplitter,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from ...analytics.comparison import compare_results
from ...logging_setup import get_logger
from ..theme import PALETTE, Fonts, duration, money, number, pct
from .chart_items import (PriceAxisItem, TimeAxisItem,
                          clip_to_view as _clip_to_view)
from .common import clear_layout

log = get_logger(__name__)


class ComparisonView(QWidget):
    """Overlaid equity curves and a best-per-row metric table."""

    runActivated = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._results: list[Any] = []
        self._table_data: Any = None
        self._build_ui()

    # -- construction ----------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        self.headline = QLabel("Save two or more backtests, then choose "
                               "Backtest → Compare Runs.")
        self.headline.setWordWrap(True)
        self.headline.setFont(Fonts.body(10))
        self.headline.setStyleSheet(f"color:{PALETTE.text_dim};")
        outer.addWidget(self.headline)

        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setObjectName("Warning")
        self.note.setFont(Fonts.body(8))
        self.note.hide()
        outer.addWidget(self.note)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)

        chart_frame = QFrame()
        chart_frame.setObjectName("ChartContainer")
        cl = QVBoxLayout(chart_frame)
        cl.setContentsMargins(1, 1, 1, 1)
        cl.setSpacing(0)

        self.legend = QWidget()
        self.legend_layout = QHBoxLayout(self.legend)
        self.legend_layout.setContentsMargins(10, 5, 10, 4)
        self.legend_layout.setSpacing(16)
        cl.addWidget(self.legend)

        self.layout_widget = pg.GraphicsLayoutWidget()
        self.layout_widget.setBackground(PALETTE.app_bg)
        self.layout_widget.ci.setContentsMargins(2, 2, 2, 2)
        self.layout_widget.ci.setSpacing(2)
        cl.addWidget(self.layout_widget, 1)

        self.eq_axis = TimeAxisItem("bottom")
        self.dd_axis = TimeAxisItem("bottom")
        self.eq_plot = self.layout_widget.addPlot(
            row=0, col=0, axisItems={"bottom": self.eq_axis,
                                     "right": PriceAxisItem(1, "right")})
        self.dd_plot = self.layout_widget.addPlot(
            row=1, col=0, axisItems={"bottom": self.dd_axis,
                                     "right": PriceAxisItem(1, "right")})
        for plot, labelled in ((self.eq_plot, False), (self.dd_plot, True)):
            plot.showGrid(x=True, y=True, alpha=0.13)
            plot.setMenuEnabled(False)
            plot.hideButtons()
            plot.showAxis("right")
            plot.hideAxis("left")
            axis = plot.getAxis("bottom")
            axis.setStyle(showValues=labelled, tickLength=-5 if labelled else 0)
            axis.setHeight(26 if labelled else 8)
            axis.setTickFont(Fonts.numeric(8))
            plot.getAxis("right").setWidth(66)
            plot.getAxis("right").setTickFont(Fonts.numeric(8))
            plot.getViewBox().setDefaultPadding(0.0)
        self.dd_plot.setXLink(self.eq_plot)
        self.layout_widget.ci.layout.setRowStretchFactor(0, 24)
        self.layout_widget.ci.layout.setRowStretchFactor(1, 11)

        self.base_line = pg.InfiniteLine(
            pos=100.0, angle=0, movable=False,
            pen=pg.mkPen(PALETTE.text_muted, width=1, style=Qt.PenStyle.DashLine))
        self.eq_plot.addItem(self.base_line, ignoreBounds=True)
        splitter.addWidget(chart_frame)

        self.table = QTableWidget(0, 1)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setFont(Fonts.numeric(9))
        self.table.verticalHeader().setDefaultSectionSize(23)
        self.table.verticalHeader().setStyleSheet(
            f"QHeaderView::section {{ background:{PALETTE.panel_bg};"
            f"color:{PALETTE.text_dim}; border:0; padding:0 10px;"
            f"font-family:'{Fonts.ui}'; }}")
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.cellDoubleClicked.connect(
            lambda _row, column: self.runActivated.emit(column))
        splitter.addWidget(self.table)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        outer.addWidget(splitter, 1)

        self.warnings = QLabel("")
        self.warnings.setWordWrap(True)
        self.warnings.setObjectName("Hint")
        self.warnings.setFont(Fonts.body(8))
        self.warnings.hide()
        outer.addWidget(self.warnings)

    # -- data ------------------------------------------------------------

    def set_results(self, results: Sequence[Any]) -> None:
        """Show two or more :class:`BacktestResult` objects together."""
        self._results = [r for r in (results or []) if r is not None]
        self._clear_legend()
        self.eq_plot.clearPlots()
        self.dd_plot.clearPlots()

        if len(self._results) < 2:
            self.headline.setText(
                "Choose at least two saved backtests to compare. "
                "Backtest → Save Backtest keeps the current run; "
                "Backtest → Compare Runs picks which to put side by side.")
            self.table.clear()
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.note.hide()
            self.warnings.hide()
            return

        try:
            table = compare_results(self._results)
        except Exception as exc:            # pragma: no cover - defensive
            log.exception("Comparison failed")
            self.headline.setText(f"These runs could not be compared: {exc}")
            return
        self._table_data = table

        self.headline.setText(
            f"Comparing {len(table.labels)} runs. The best value in each row is "
            f"highlighted; rows where 'best' has no meaning are left plain.")
        if table.align_note:
            self.note.setText(table.align_note)
            self.note.show()
        else:
            self.note.hide()

        self._draw_curves(table)
        self._fill_table(table)

        notes = list(getattr(table, "warnings", []) or [])
        thin = [table.labels[i] for i, row in enumerate(self._results)
                if int((row.metrics or {}).get("total_trades", 0) or 0) < 30]
        if thin:
            notes.append(
                f"{', '.join(thin)} produced fewer than 30 trades. Ranking runs "
                f"by a ratio computed from that few trades mostly ranks their luck.")
        if notes:
            self.warnings.setText("  ".join(notes))
            self.warnings.show()
        else:
            self.warnings.hide()

    def clear(self) -> None:
        self.set_results([])

    # -- drawing ---------------------------------------------------------

    def _clear_legend(self) -> None:
        clear_layout(self.legend_layout)

    def _draw_curves(self, table: Any) -> None:
        curves = list(getattr(table, "equity_curves", []) or [])
        if not curves:
            return

        timezone = "UTC"
        first = self._results[0]
        instrument = getattr(getattr(first, "bars", None), "instrument", None)
        if instrument is not None:
            timezone = getattr(instrument, "timezone", "UTC") or "UTC"

        longest = max((np.asarray(c.ts, dtype="int64").size for c in curves),
                      default=0)
        reference = next((np.asarray(c.ts, dtype="int64") for c in curves
                          if np.asarray(c.ts, dtype="int64").size == longest),
                         np.empty(0, dtype="int64"))
        self.eq_axis.set_timestamps(reference, timezone)
        self.dd_axis.set_timestamps(reference, timezone)

        for index, curve in enumerate(curves):
            values = np.asarray(curve.values, dtype="float64")
            if values.size == 0:
                continue
            colour = PALETTE.series_color(index)
            x = np.arange(values.size, dtype="float64")
            # These plots auto-range, so every point of every curve is always
            # on screen at once -- and an equity curve carries one point per
            # bar, so comparing a few runs over a large dataset is millions of
            # points.  Peak downsampling draws the same shape for the cost of
            # the widget's width.  (clipToView correctly does nothing while
            # auto-range is on; it earns its keep if the user zooms in.)
            _clip_to_view(
                self.eq_plot.plot(x, values, pen=pg.mkPen(colour, width=1.7),
                                  connect="finite", antialias=True))
            _clip_to_view(
                self.dd_plot.plot(x, self._drawdown_of(values),
                                  pen=pg.mkPen(colour, width=1.2),
                                  connect="finite", antialias=True))
            self._add_legend_entry(colour, curve.label, values)

        self.legend_layout.addStretch(1)
        self.eq_plot.enableAutoRange(axis="xy", enable=True)
        self.dd_plot.enableAutoRange(axis="y", enable=True)

    @staticmethod
    def _drawdown_of(indexed: np.ndarray) -> np.ndarray:
        """Percentage drawdown of an already-indexed curve."""
        if indexed.size == 0:
            return indexed
        peak = np.maximum.accumulate(indexed)
        out = np.zeros_like(indexed)
        usable = peak > 0
        np.divide(indexed - peak, peak, out=out, where=usable)
        return out * 100.0

    def _add_legend_entry(self, colour: str, label: str,
                          values: np.ndarray) -> None:
        entry = QWidget()
        row = QHBoxLayout(entry)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        swatch = QLabel()
        swatch.setFixedSize(14, 3)
        swatch.setStyleSheet(f"background:{colour}; border-radius:1px;")
        row.addWidget(swatch)
        final = float(values[-1]) if values.size else 100.0
        text = QLabel(f"{label}   <span style='color:"
                      f"{PALETTE.long if final >= 100 else PALETTE.short}'>"
                      f"{final:,.1f}</span>")
        text.setFont(Fonts.numeric(8))
        text.setStyleSheet(f"color:{PALETTE.text_dim};")
        row.addWidget(text)
        self.legend_layout.addWidget(entry)

    # -- table -----------------------------------------------------------

    def _fill_table(self, table: Any) -> None:
        rows = list(table.rows)
        labels = list(table.labels)
        self.table.clear()
        self.table.setRowCount(len(rows))
        self.table.setColumnCount(len(labels))
        self.table.setHorizontalHeaderLabels(labels)
        self.table.setVerticalHeaderLabels([r.label for r in rows])

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setMinimumSectionSize(110)
        self.table.verticalHeader().setFixedWidth(190)

        for r, row in enumerate(rows):
            for c in range(len(labels)):
                value = row.values[c] if c < len(row.values) else None
                item = QTableWidgetItem(self._format(value, row.kind))
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight |
                                      Qt.AlignmentFlag.AlignVCenter)
                item.setForeground(QBrush(QColor(self._colour(value, row))))
                if row.best_index is not None and c == row.best_index:
                    item.setBackground(QBrush(QColor(PALETTE.elevated)))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setToolTip(f"Best {row.label.lower()} of these runs")
                state = (row.reliability or {}).get(c) if isinstance(
                    row.reliability, dict) else None
                if state in ("low_sample", "unavailable"):
                    item.setForeground(QBrush(QColor(PALETTE.text_muted)))
                    item.setToolTip(
                        "This figure is marked unreliable for that run: "
                        "too few trades or a degenerate denominator.")
                self.table.setItem(r, c, item)

    def _format(self, value: Any, kind: str) -> str:
        if value is None:
            return "-"
        if isinstance(value, float):
            if math.isnan(value):
                return "-"
            if math.isinf(value):
                return "∞" if value > 0 else "-∞"
        if kind == "money":
            return money(value)
        if kind == "pct":
            return pct(value)
        if kind == "int":
            try:
                return f"{int(value):,}"
            except (TypeError, ValueError):
                return str(value)
        if kind == "duration":
            return duration(value)
        if kind == "ratio":
            return number(value, 2)
        return number(value, 2) if isinstance(value, (int, float)) else str(value)

    @staticmethod
    def _colour(value: Any, row: Any) -> str:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return PALETTE.text
        if isinstance(value, float) and math.isnan(value):
            return PALETTE.text_muted
        if row.higher_is_better is None:
            return PALETTE.text
        if row.key in ("max_drawdown", "max_drawdown_pct", "total_costs",
                       "max_consecutive_losses", "gross_loss", "largest_loss"):
            return PALETTE.short if value else PALETTE.text_dim
        if value > 0:
            return PALETTE.long
        if value < 0:
            return PALETTE.short
        return PALETTE.text_dim
