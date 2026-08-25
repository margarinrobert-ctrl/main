"""Equity, balance, drawdown and the underwater plot.

Three linked panels sharing the price chart's bar-index x axis so that a point
on the equity curve lines up with the candle that produced it.  Multiple runs
can be overlaid on the same axes, which is what the comparison view uses.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QToolButton,
                               QVBoxLayout, QWidget)

from ..theme import PALETTE, Fonts, money, pct
from .chart_items import PriceAxisItem, TimeAxisItem


class EquityWidget(QWidget):
    """Equity curve on top, drawdown beneath, with an optional balance line."""

    barHovered = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ChartContainer")
        self._ts = np.empty(0, dtype="int64")
        self._series: list[dict[str, Any]] = []
        self._timezone = "UTC"
        self._show_balance = True
        self._log_scale = False
        self._starting_capital = 0.0
        self._build_ui()

    # -- construction ----------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)

        from ..icons import icon

        header = QFrame()
        header.setObjectName("Card")
        header.setFixedHeight(32)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(9, 0, 9, 0)
        hl.setSpacing(12)
        self.title = QLabel("Equity")
        self.title.setFont(Fonts.body(9, bold=True))
        hl.addWidget(self.title)
        self.readout = QLabel("")
        self.readout.setFont(Fonts.numeric(9))
        hl.addWidget(self.readout)
        hl.addStretch(1)

        self.balance_btn = QToolButton()
        self.balance_btn.setText("Balance")
        self.balance_btn.setCheckable(True)
        self.balance_btn.setChecked(True)
        self.balance_btn.setToolTip("Show the realised balance line as well as equity")
        self.balance_btn.clicked.connect(self._toggle_balance)
        hl.addWidget(self.balance_btn)

        self.log_btn = QToolButton()
        self.log_btn.setText("Log")
        self.log_btn.setCheckable(True)
        self.log_btn.setToolTip("Logarithmic equity scale")
        self.log_btn.clicked.connect(self._toggle_log)
        hl.addWidget(self.log_btn)

        fit = QToolButton()
        fit.setIcon(icon("fit", 17))
        fit.setIconSize(QSize(17, 17))
        fit.setToolTip("Fit")
        fit.clicked.connect(self.fit_all)
        hl.addWidget(fit)
        outer.addWidget(header)

        self.layout_widget = pg.GraphicsLayoutWidget()
        self.layout_widget.setBackground(PALETTE.app_bg)
        self.layout_widget.ci.setContentsMargins(2, 4, 2, 2)
        self.layout_widget.ci.setSpacing(2)
        outer.addWidget(self.layout_widget, 1)

        self.eq_axis = TimeAxisItem("bottom")
        self.dd_axis = TimeAxisItem("bottom")

        self.eq_plot = self.layout_widget.addPlot(
            row=0, col=0, axisItems={"bottom": self.eq_axis,
                                     "right": PriceAxisItem(0, "right")})
        self.dd_plot = self.layout_widget.addPlot(
            row=1, col=0, axisItems={"bottom": self.dd_axis,
                                     "right": PriceAxisItem(1, "right")})
        for p, show in ((self.eq_plot, False), (self.dd_plot, True)):
            p.showGrid(x=True, y=True, alpha=0.13)
            p.setMenuEnabled(False)
            p.hideButtons()
            p.showAxis("right")
            p.hideAxis("left")
            ax = p.getAxis("bottom")
            ax.setStyle(showValues=show, tickLength=-5 if show else 0)
            ax.setHeight(26 if show else 8)
            ax.setTickFont(Fonts.numeric(8))
            p.getAxis("right").setWidth(74)
            p.getAxis("right").setTickFont(Fonts.numeric(8))
            p.getViewBox().setDefaultPadding(0.0)
        self.dd_plot.setXLink(self.eq_plot)
        self.layout_widget.ci.layout.setRowStretchFactor(0, 26)
        self.layout_widget.ci.layout.setRowStretchFactor(1, 11)

        self.start_line = pg.InfiniteLine(
            angle=0, movable=False,
            pen=pg.mkPen(PALETTE.text_muted, width=1, style=Qt.PenStyle.DashLine))
        self.eq_plot.addItem(self.start_line, ignoreBounds=True)

        self._vline_eq = pg.InfiniteLine(
            angle=90, movable=False,
            pen=pg.mkPen(PALETTE.crosshair, width=1, style=Qt.PenStyle.DashLine))
        self._vline_dd = pg.InfiniteLine(
            angle=90, movable=False,
            pen=pg.mkPen(PALETTE.crosshair, width=1, style=Qt.PenStyle.DashLine))
        for line, plot in ((self._vline_eq, self.eq_plot), (self._vline_dd, self.dd_plot)):
            line.hide()
            line.setZValue(50)
            plot.addItem(line, ignoreBounds=True)
        self.layout_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)

    # -- data ------------------------------------------------------------

    def set_result(self, result: Any) -> None:
        """Show one backtest."""
        if result is None or result.curves is None or len(result.curves) == 0:
            self.clear()
            return
        c = result.curves
        self._starting_capital = float(result.config.starting_capital)
        self.set_series(
            c.ts,
            [{"label": result.label or result.strategy_name or "Equity",
              "equity": c.equity, "balance": c.balance,
              "drawdown_pct": c.drawdown_pct * 100.0,
              "color": PALETTE.equity, "fill": True}],
            timezone=getattr(getattr(result.bars, "instrument", None), "timezone", "UTC"),
        )

    def set_series(self, ts, series: Sequence[dict[str, Any]],
                   timezone: str = "UTC") -> None:
        """Show one or more runs on the same axes.

        Each entry needs ``label``, ``equity`` and ``drawdown_pct``; ``balance``
        and ``fill`` are optional.
        """
        self._ts = np.ascontiguousarray(ts, dtype="int64")
        self._series = [dict(s) for s in series]
        self._timezone = timezone or "UTC"
        self.eq_axis.set_timestamps(self._ts, self._timezone)
        self.dd_axis.set_timestamps(self._ts, self._timezone)

        self.eq_plot.clearPlots()
        self.dd_plot.clearPlots()
        x = np.arange(len(self._ts), dtype="float64")

        for i, s in enumerate(self._series):
            colour = s.get("color") or PALETTE.series_color(i)
            eq = np.asarray(s["equity"], dtype="float64")
            if s.get("fill", False) and len(self._series) == 1:
                base = pg.PlotDataItem(
                    x, np.full_like(eq, self._starting_capital or float(eq[0])),
                    pen=pg.mkPen(None))
                curve = pg.PlotDataItem(x, eq, pen=pg.mkPen(colour, width=1.6))
                fill = pg.FillBetweenItem(curve, base,
                                          brush=pg.mkBrush(QColor(PALETTE.equity_fill)))
                self.eq_plot.addItem(fill)
                self.eq_plot.addItem(curve)
            else:
                self.eq_plot.plot(x, eq, pen=pg.mkPen(colour, width=1.6),
                                  name=s.get("label", ""), antialias=True)
            if self._show_balance and s.get("balance") is not None and len(self._series) == 1:
                self.eq_plot.plot(x, np.asarray(s["balance"], dtype="float64"),
                                  pen=pg.mkPen(PALETTE.balance, width=1.0,
                                               style=Qt.PenStyle.DashLine),
                                  name="Balance", antialias=True)

            dd = np.asarray(s["drawdown_pct"], dtype="float64")
            dd_colour = colour if len(self._series) > 1 else PALETTE.drawdown
            dd_curve = pg.PlotDataItem(x, dd, pen=pg.mkPen(dd_colour, width=1.2))
            if len(self._series) == 1:
                zero = pg.PlotDataItem(x, np.zeros_like(dd), pen=pg.mkPen(None))
                self.dd_plot.addItem(pg.FillBetweenItem(
                    dd_curve, zero, brush=pg.mkBrush(QColor(PALETTE.drawdown_fill))))
            self.dd_plot.addItem(dd_curve)

        self.start_line.setPos(self._starting_capital)
        self.start_line.setVisible(self._starting_capital > 0 and len(self._series) == 1)
        self.fit_all()
        self._update_readout(len(self._ts) - 1)

    def clear(self) -> None:
        self._ts = np.empty(0, dtype="int64")
        self._series = []
        self.eq_plot.clearPlots()
        self.dd_plot.clearPlots()
        self.readout.setText("")
        self.start_line.setVisible(False)

    # -- view ------------------------------------------------------------

    def fit_all(self) -> None:
        n = len(self._ts)
        if n == 0:
            return
        self.eq_plot.setXRange(0, n - 1, padding=0.005)
        eqs = [np.asarray(s["equity"], dtype="float64") for s in self._series]
        if eqs:
            lo = min(float(np.nanmin(e)) for e in eqs)
            hi = max(float(np.nanmax(e)) for e in eqs)
            lo = min(lo, self._starting_capital) if self._starting_capital else lo
            hi = max(hi, self._starting_capital) if self._starting_capital else hi
            pad = max((hi - lo) * 0.06, abs(hi) * 1e-4, 1e-9)
            self.eq_plot.setYRange(lo - pad, hi + pad, padding=0)
        dds = [np.asarray(s["drawdown_pct"], dtype="float64") for s in self._series]
        if dds:
            worst = min(float(np.nanmin(d)) for d in dds)
            self.dd_plot.setYRange(min(worst * 1.1, -0.1), 0.0, padding=0)

    def _toggle_balance(self) -> None:
        self._show_balance = self.balance_btn.isChecked()
        if self._series:
            self.set_series(self._ts, self._series, self._timezone)

    def _toggle_log(self) -> None:
        self._log_scale = self.log_btn.isChecked()
        self.eq_plot.setLogMode(x=False, y=self._log_scale)

    # -- interaction -----------------------------------------------------

    def _on_mouse_moved(self, scene_pos) -> None:
        if len(self._ts) == 0:
            return
        for plot in (self.eq_plot, self.dd_plot):
            if plot.sceneBoundingRect().contains(scene_pos):
                x = plot.getViewBox().mapSceneToView(scene_pos).x()
                i = int(np.clip(round(x), 0, len(self._ts) - 1))
                self._vline_eq.setPos(i); self._vline_eq.show()
                self._vline_dd.setPos(i); self._vline_dd.show()
                self._update_readout(i)
                self.barHovered.emit(i)
                return

    def set_cursor_bar(self, index: int) -> None:
        """Move the crosshair from an external source, e.g. the price chart."""
        if len(self._ts) == 0:
            return
        i = int(np.clip(index, 0, len(self._ts) - 1))
        self._vline_eq.setPos(i); self._vline_eq.show()
        self._vline_dd.setPos(i); self._vline_dd.show()
        self._update_readout(i)

    def _update_readout(self, index: int) -> None:
        if not self._series or not (0 <= index < len(self._ts)):
            return
        import pandas as pd

        ts = pd.Timestamp(int(self._ts[index]), tz="UTC")
        try:
            ts = ts.tz_convert(self._timezone)
        except Exception:
            pass
        parts = [f"<span style='color:{PALETTE.text_muted}'>{ts:%Y-%m-%d %H:%M}</span>"]
        for i, s in enumerate(self._series):
            eq = float(np.asarray(s["equity"])[index])
            dd = float(np.asarray(s["drawdown_pct"])[index])
            colour = s.get("color") or PALETTE.series_color(i)
            change = eq - self._starting_capital if self._starting_capital else 0.0
            change_col = PALETTE.long if change >= 0 else PALETTE.short
            label = f"<span style='color:{colour}'>{s.get('label', '')}</span> " \
                if len(self._series) > 1 else ""
            parts.append(
                f"{label}<span style='color:{PALETTE.text}'>{money(eq)}</span>"
                f"  <span style='color:{change_col}'>{money(change)}</span>"
                f"  <span style='color:{PALETTE.drawdown}'>DD {pct(dd)}</span>")
        self.readout.setText("   ".join(parts))
