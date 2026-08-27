"""The central price chart.

A stack of x-linked pyqtgraph panels: price on top, then volume, then one panel
per non-overlay indicator.  The price panel autoscales its y axis to whatever is
horizontally in view, which is the behaviour every trading chart has and the one
pyqtgraph does not give you for free.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel,
                               QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from ...core.types import Side
from ..theme import PALETTE, Fonts, number
from .chart_items import (BandFillItem, CandlestickItem, HistogramItem,
                          LevelLinesItem, PriceAxisItem, SessionShadingItem,
                          TimeAxisItem, TradeMarkerItem, VolumeItem,
                          clip_to_view as _clip_to_view)

pg.setConfigOptions(antialias=True, background=PALETTE.app_bg,
                    foreground=PALETTE.text_dim, useOpenGL=False)


class _ChartViewBox(pg.ViewBox):
    """A view box that pans with the left mouse button and zooms the x axis only.

    pyqtgraph's default is a rubber-band zoom on left-drag and a two-axis wheel
    zoom.  Traders expect drag-to-pan and wheel-to-zoom-time, so both are
    remapped here rather than being left as a surprise.
    """

    def __init__(self, on_wheel: Callable[[float, float], None] | None = None) -> None:
        super().__init__()
        self.setMouseMode(pg.ViewBox.PanMode)
        self._on_wheel = on_wheel

    def wheelEvent(self, ev, axis=None) -> None:  # noqa: N802
        if self._on_wheel is not None:
            delta = ev.delta() if hasattr(ev, "delta") else ev.angleDelta().y()
            pos = self.mapSceneToView(ev.scenePos()).x()
            self._on_wheel(float(delta), float(pos))
            ev.accept()
            return
        super().wheelEvent(ev, axis)  # pragma: no cover - fallback


class ChartPanel:
    """One row of the chart layout."""

    def __init__(self, plot: pg.PlotItem, name: str, height_ratio: float,
                 is_price: bool = False) -> None:
        self.plot = plot
        self.name = name
        self.height_ratio = height_ratio
        self.is_price = is_price
        self.curves: list[pg.PlotDataItem] = []
        self.vline: pg.InfiniteLine | None = None
        self.legend_label: QLabel | None = None


class ChartWidget(QWidget):
    """Candles, volume, indicators, trade markers, crosshair and hover readout."""

    barHovered = Signal(int)
    tradeClicked = Signal(int)
    rangeChanged = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ChartContainer")
        self._bars: Any = None
        self._ts = np.empty(0, dtype="int64")
        self._trades: list[Any] = []
        self._panels: list[ChartPanel] = []
        #: ``{slot_ref: [(plot, item), ...]}``.  The owning plot is kept because
        #: removal has to go through PlotItem.removeItem: taking an item off the
        #: view box leaves it in the plot's own item list, so fills and curves
        #: would accumulate on every re-run until the chart crawled.
        self._indicator_curves: dict[str, list[tuple[pg.PlotItem, Any]]] = {}
        self._crosshair_on = True
        self._log_scale = False
        self._selected_trade: int | None = None
        self._timezone = "UTC"
        self._decimals = 2
        self._suppress_autoscale = False

        self._build_ui()

    # -- construction ----------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)

        self.header = self._build_header()
        outer.addWidget(self.header)

        self.layout_widget = pg.GraphicsLayoutWidget()
        self.layout_widget.setBackground(PALETTE.app_bg)
        self.layout_widget.ci.setContentsMargins(2, 4, 2, 2)
        self.layout_widget.ci.setSpacing(2)
        outer.addWidget(self.layout_widget, 1)

        self.price_axis = PriceAxisItem(self._decimals, "right")
        self._time_axes: list[TimeAxisItem] = []

        vb = _ChartViewBox(self._wheel_zoom)
        self.price_plot = self.layout_widget.addPlot(
            row=0, col=0, viewBox=vb,
            axisItems={"bottom": self._new_time_axis(), "right": self.price_axis})
        self._style_plot(self.price_plot, show_x_labels=False)
        self.price_plot.setLabel("right", "")

        self.candles = CandlestickItem()
        self.price_plot.addItem(self.candles)
        self.session_shade = SessionShadingItem()
        self.session_shade.setZValue(-20)
        self.price_plot.addItem(self.session_shade)
        self.levels = LevelLinesItem()
        self.levels.setZValue(20)
        self.price_plot.addItem(self.levels)
        self.markers = TradeMarkerItem()
        self.markers.setZValue(30)
        self.price_plot.addItem(self.markers)

        price_panel = ChartPanel(self.price_plot, "Price", 3.0, is_price=True)
        self._panels.append(price_panel)

        vol_vb = _ChartViewBox(self._wheel_zoom)
        self.volume_plot = self.layout_widget.addPlot(
            row=1, col=0, viewBox=vol_vb,
            axisItems={"bottom": self._new_time_axis(),
                       "right": PriceAxisItem(0, "right")})
        self._style_plot(self.volume_plot, show_x_labels=False)
        self.volume_item = VolumeItem()
        self.volume_plot.addItem(self.volume_item)
        self.volume_plot.setXLink(self.price_plot)
        self._panels.append(ChartPanel(self.volume_plot, "Volume", 0.8))

        self._rebuild_layout_stretch()
        self._install_crosshair()

        self.price_plot.sigXRangeChanged.connect(self._on_x_range_changed)
        self.layout_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)
        self.layout_widget.scene().sigMouseClicked.connect(self._on_mouse_clicked)

    def _build_header(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("Card")
        bar.setFixedHeight(32)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(9, 0, 9, 0)
        lay.setSpacing(12)

        self.symbol_label = QLabel("No data")
        self.symbol_label.setFont(Fonts.body(9, bold=True))
        lay.addWidget(self.symbol_label)

        self.ohlc_label = QLabel("")
        self.ohlc_label.setFont(Fonts.numeric(9))
        self.ohlc_label.setStyleSheet(f"color:{PALETTE.text_dim};")
        lay.addWidget(self.ohlc_label)

        lay.addStretch(1)

        self.indicator_legend = QLabel("")
        self.indicator_legend.setFont(Fonts.numeric(8))
        self.indicator_legend.setStyleSheet(f"color:{PALETTE.text_muted};")
        lay.addWidget(self.indicator_legend)

        from ..icons import icon

        self._type_group = QButtonGroup(self)
        self._type_group.setExclusive(True)
        for key, ico, tip in (("candles", "candles", "Candlesticks"),
                              ("bars", "ohlc-bars", "OHLC bars"),
                              ("line", "line-chart", "Line"),
                              ("area", "area-chart", "Area")):
            b = QToolButton()
            b.setCheckable(True)
            b.setToolTip(tip)
            b.setIcon(icon(ico, 17))
            b.setIconSize(QSize(17, 17))
            b.setProperty("chart_type", key)
            b.setFixedSize(26, 24)
            if key == "candles":
                b.setChecked(True)
            self._type_group.addButton(b)
            lay.addWidget(b)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color:{PALETTE.border};")
        sep.setFixedHeight(16)
        lay.addWidget(sep)
        self._type_group.buttonClicked.connect(
            lambda btn: self.set_chart_type(btn.property("chart_type")))

        for ico, tip, slot in (("zoom-in", "Zoom in", self.zoom_in),
                               ("zoom-out", "Zoom out", self.zoom_out),
                               ("fit", "Fit all bars", self.fit_all),
                               ("crosshair", "Toggle crosshair", self.toggle_crosshair)):
            b = QToolButton()
            b.setIcon(icon(ico, 17))
            b.setIconSize(QSize(17, 17))
            b.setToolTip(tip)
            b.setFixedSize(26, 24)
            b.clicked.connect(slot)
            lay.addWidget(b)
        return bar

    def _style_plot(self, plot: pg.PlotItem, show_x_labels: bool) -> None:
        plot.showGrid(x=True, y=True, alpha=0.13)
        plot.setMenuEnabled(False)
        plot.hideButtons()
        plot.showAxis("right")
        plot.hideAxis("left")
        ax_b = plot.getAxis("bottom")
        ax_b.setPen(pg.mkPen(PALETTE.border))
        ax_b.setTextPen(pg.mkPen(PALETTE.axis_text))
        ax_b.setStyle(showValues=show_x_labels, tickLength=-4)
        ax_r = plot.getAxis("right")
        ax_r.setPen(pg.mkPen(PALETTE.border))
        ax_r.setTextPen(pg.mkPen(PALETTE.axis_text))
        ax_r.setWidth(66)
        font = Fonts.numeric(8)
        ax_b.setTickFont(font)
        ax_r.setTickFont(font)
        plot.getViewBox().setDefaultPadding(0.0)
        plot.setClipToView(False)

    def _new_time_axis(self) -> TimeAxisItem:
        """A fresh date axis.

        Qt refuses to let one AxisItem belong to two plots, so every panel owns
        its own; only the bottom one draws labels and they are kept in step by
        being fed the same timestamps.
        """
        ax = TimeAxisItem("bottom")
        ax.setTickFont(Fonts.numeric(8))
        self._time_axes.append(ax)
        return ax

    def _rebuild_layout_stretch(self) -> None:
        for row, panel in enumerate(self._panels):
            self.layout_widget.ci.layout.setRowStretchFactor(
                row, max(1, int(panel.height_ratio * 10)))
        # Only the bottom panel carries the date labels; the rest keep a thin
        # axis so the panels stay aligned pixel for pixel.
        for i, panel in enumerate(self._panels):
            last = (i == len(self._panels) - 1)
            ax = panel.plot.getAxis("bottom")
            ax.setStyle(showValues=last, tickLength=-5 if last else 0)
            ax.setHeight(26 if last else 8)
            if isinstance(ax, TimeAxisItem):
                ax.set_timestamps(self._ts, self._timezone)

    def _install_crosshair(self) -> None:
        # Removal must go through the PlotItem, not the ViewBox: taking an item
        # off the view box leaves it in the plot's item list, so the crosshair
        # lines would pile up one pair per rebuild.
        for owner, existing in getattr(self, "_crosshair_items", []):
            try:
                owner.removeItem(existing)
            except Exception:
                pass
        self._crosshair_items: list[tuple[pg.PlotItem, Any]] = []
        self._vlines = []
        for panel in self._panels:
            v = pg.InfiniteLine(angle=90, movable=False,
                                pen=pg.mkPen(PALETTE.crosshair, width=1,
                                             style=Qt.PenStyle.DashLine))
            v.setZValue(50)
            v.hide()
            panel.plot.addItem(v, ignoreBounds=True)
            panel.vline = v
            self._vlines.append(v)
            self._crosshair_items.append((panel.plot, v))
        self._hline = pg.InfiniteLine(angle=0, movable=False,
                                      pen=pg.mkPen(PALETTE.crosshair, width=1,
                                                   style=Qt.PenStyle.DashLine))
        self._hline.setZValue(50)
        self._hline.hide()
        self.price_plot.addItem(self._hline, ignoreBounds=True)
        self._crosshair_items.append((self.price_plot, self._hline))

        self._price_tag = pg.TextItem(anchor=(0, 0.5), color=PALETTE.text,
                                      fill=pg.mkBrush(PALETTE.elevated),
                                      border=pg.mkPen(PALETTE.border_strong))
        self._price_tag.setFont(Fonts.numeric(8))
        self._price_tag.setZValue(55)
        self._price_tag.hide()
        self.price_plot.addItem(self._price_tag, ignoreBounds=True)
        self._crosshair_items.append((self.price_plot, self._price_tag))

    # -- data ------------------------------------------------------------

    def set_bars(self, bars: Any) -> None:
        """Show a :class:`~tradingbacktester.data.models.BarSeries`."""
        self._bars = bars
        if bars is None or len(bars) == 0:
            self.candles.set_data([], [], [], [])
            self.volume_item.set_data([], [], [])
            self.markers.set_trades([])
            self.levels.set_levels([])
            self.symbol_label.setText("No data")
            self.ohlc_label.setText("")
            self._ts = np.empty(0, dtype="int64")
            self._refresh_time_axes()
            return

        self._ts = bars.ts
        self._timezone = getattr(bars.instrument, "timezone", "UTC") or "UTC"
        self._decimals = int(getattr(bars.instrument, "price_decimals", 2))
        self.price_axis.set_decimals(self._decimals)
        self.candles.set_data(bars.open, bars.high, bars.low, bars.close)
        self.volume_item.set_data(bars.volume, bars.open, bars.close)
        self._refresh_time_axes()
        self.symbol_label.setText(
            f"{bars.instrument.symbol}  ·  {bars.timeframe.label}  ·  {len(bars):,} bars")
        self.volume_plot.setVisible(bool(np.nanmax(bars.volume) > 0))
        self.show_last(min(len(bars), 300))
        self._update_readout(len(bars) - 1)

    def _refresh_time_axes(self) -> None:
        for ax in self._time_axes:
            ax.set_timestamps(self._ts, self._timezone)

    def set_indicator_panels(self, panels: list[dict[str, Any]]) -> None:
        """Rebuild the indicator overlays and sub-panels.

        Each entry is ``{"ref", "label", "panel": "price"|"sub", "series":
        [{"name", "values", "color", "style", "width"}], "guides": [floats],
        "range": (lo, hi) | None}``.
        """
        # Remove previous curves and sub-panels.
        for entries in self._indicator_curves.values():
            for plot, item in entries:
                try:
                    plot.removeItem(item)
                except Exception:
                    pass
        self._indicator_curves.clear()
        for panel in self._panels[2:]:
            ax = panel.plot.getAxis("bottom")
            if ax in self._time_axes:
                self._time_axes.remove(ax)
            self.layout_widget.removeItem(panel.plot)
        del self._panels[2:]

        overlays = [p for p in panels if p.get("panel") == "price"]
        subs = [p for p in panels if p.get("panel") != "price"]

        for spec in overlays:
            self._add_series(self.price_plot, spec)

        for i, spec in enumerate(subs):
            vb = _ChartViewBox(self._wheel_zoom)
            plot = self.layout_widget.addPlot(
                row=2 + i, col=0, viewBox=vb,
                axisItems={"bottom": self._new_time_axis(),
                           "right": PriceAxisItem(2, "right")})
            self._style_plot(plot, show_x_labels=False)
            plot.setXLink(self.price_plot)
            for g in spec.get("guides", ()):
                line = pg.InfiniteLine(pos=float(g), angle=0, movable=False,
                                       pen=pg.mkPen(PALETTE.grid_strong, width=1,
                                                    style=Qt.PenStyle.DashLine))
                plot.addItem(line, ignoreBounds=True)
            rng = spec.get("range")
            if rng:
                plot.setYRange(float(rng[0]), float(rng[1]), padding=0.05)
                plot.getViewBox().setAutoVisible(y=False)
                plot.enableAutoRange(axis="y", enable=False)
            label = pg.TextItem(spec.get("label", spec.get("ref", "")),
                                color=PALETTE.text_muted, anchor=(0, 0))
            label.setFont(Fonts.numeric(8))
            label.setZValue(40)
            plot.addItem(label, ignoreBounds=True)
            # sigRangeChanged carries a variable number of arguments across
            # pyqtgraph versions, so bind by keyword and swallow the positionals.
            plot.getViewBox().sigRangeChanged.connect(
                lambda *_a, lbl=label, box=plot.getViewBox():
                    self._pin_label(lbl, box))
            self._add_series(plot, spec)
            self._panels.append(ChartPanel(plot, spec.get("label", ""), 1.0))

        self._rebuild_layout_stretch()
        self._install_crosshair()
        self._on_x_range_changed()

    @staticmethod
    def _pin_label(label: pg.TextItem, vb: pg.ViewBox) -> None:
        (x0, _x1), (_y0, y1) = vb.viewRange()
        label.setPos(x0, y1)

    def _add_series(self, plot: pg.PlotItem, spec: dict[str, Any]) -> None:
        """Draw one indicator's outputs, honouring the registry's drawing hints.

        Three hints go beyond a plain line and are what make a Bollinger band
        look like a band rather than three unrelated lines:

        ``fill_to``/``fill_color``
            Shade the area between this output and a named sibling.
        ``negative_color``
            Colour histogram bars by the sign of their value.
        ``colour_by``
            Colour a line by the sign of another output, which is how SuperTrend
            shows its trend flip.
        ``panel: "hidden"``
            Compute the output but do not draw it -- SuperTrend's ``direction``
            exists to colour the line, not to be a line itself.
        """
        ref = spec.get("ref", "")
        entries = self._indicator_curves.setdefault(ref, [])

        def keep(item: Any) -> Any:
            entries.append((plot, item))
            return item

        x = np.arange(len(self._ts), dtype="float64")
        series = list(spec.get("series", ()))
        by_name = {s.get("output", s.get("name", "")): np.asarray(s["values"],
                                                                  dtype="float64")
                   for s in series if s.get("values") is not None}
        drawn: dict[str, pg.PlotDataItem] = {}
        values_by_output: dict[str, np.ndarray] = {}

        for s in series:
            values = np.asarray(s["values"], dtype="float64")
            if len(values) != len(x):
                continue
            if s.get("panel") == "hidden":
                continue

            colour = s.get("color", PALETTE.accent)
            width = float(s.get("width", 1.2))
            style = {"solid": Qt.PenStyle.SolidLine, "dash": Qt.PenStyle.DashLine,
                     "dot": Qt.PenStyle.DotLine}.get(s.get("style", "solid"),
                                                     Qt.PenStyle.SolidLine)

            if s.get("kind") == "histogram":
                item = HistogramItem(values, colour, s.get("negative_color"))
                plot.addItem(item)
                keep(item)
                continue

            colour_by = s.get("colour_by")
            if colour_by and colour_by in by_name:
                for line in self._two_tone_lines(plot, x, values, by_name[colour_by],
                                                 colour,
                                                 s.get("negative_color", PALETTE.short),
                                                 width):
                    keep(line)
                continue

            pen = pg.mkPen(colour, width=width, style=style)
            curve = plot.plot(x, values, pen=pen, connect="finite",
                              name=s.get("name", ref), antialias=True)
            _clip_to_view(curve)
            curve.setZValue(10)
            keep(curve)
            output = s.get("output", s.get("name", ""))
            if output:
                drawn[output] = curve
                values_by_output[output] = values

        # Band shading, once both edges exist.
        for s in series:
            target = s.get("fill_to")
            output = s.get("output", s.get("name", ""))
            if not target or output not in drawn or target not in drawn:
                continue
            brush = pg.mkBrush(self._fill_colour(s.get("fill_color", "#4aa3ff22")))
            # Not pg.FillBetweenItem: it builds a QPainterPath over the whole
            # series the moment it is constructed, which is seconds per band on
            # a large dataset and happens before the window can paint.
            fill = BandFillItem(values_by_output[output], values_by_output[target],
                                brush=brush.color())
            fill.setZValue(-5)
            plot.addItem(fill)
            keep(fill)

    @staticmethod
    def _fill_colour(text: str) -> QColor:
        """Parse a colour that may carry a CSS-style alpha suffix.

        Qt reads an eight-digit hex string as ``#AARRGGBB``, but every stylesheet
        convention -- and the indicator library's ``fill_color`` values -- write
        ``#RRGGBBAA``.  Handing "#4aa3ff22" straight to QColor therefore produces
        a bright green band where a faint blue one was intended.
        """
        text = str(text or "").strip()
        if len(text) == 9 and text.startswith("#"):
            colour = QColor(text[:7])
            try:
                colour.setAlpha(int(text[7:9], 16))
            except ValueError:
                pass
            return colour
        return QColor(text) if text else QColor(PALETTE.accent)

    @staticmethod
    def _two_tone_lines(plot, x, values, sign_source, up_colour, down_colour,
                        width) -> list[pg.PlotDataItem]:
        """One series drawn as two curves, split where the sign flips.

        Each half is NaN outside its regime, so ``connect="finite"`` breaks the
        line there instead of drawing a stripe across the chart.
        """
        out: list[pg.PlotDataItem] = []
        up = np.where(sign_source >= 0, values, np.nan)
        down = np.where(sign_source < 0, values, np.nan)
        for data, colour in ((up, up_colour), (down, down_colour)):
            if not np.isfinite(data).any():
                continue
            curve = plot.plot(x, data, pen=pg.mkPen(colour, width=width),
                              connect="finite", antialias=True)
            _clip_to_view(curve)
            curve.setZValue(10)
            out.append(curve)
        return out

    def set_trades(self, trades: list[Any], show_levels: bool = True) -> None:
        self._trades = list(trades or [])
        rows = [(t.entry_bar, t.entry_price, t.exit_bar, t.exit_price,
                 t.side is Side.LONG, t.net_pnl > 0) for t in self._trades]
        self.markers.set_trades(rows)
        if show_levels:
            self.levels.set_levels([(t.entry_bar, t.exit_bar, t.stop_loss, t.take_profit)
                                    for t in self._trades])
        else:
            self.levels.set_levels([])

    def set_session_spans(self, spans: list[tuple[int, int]]) -> None:
        self.session_shade.set_spans(spans)

    def select_trade(self, index: int | None, centre: bool = True) -> None:
        """Highlight a trade and, optionally, scroll it into view."""
        self._selected_trade = index
        self.markers.set_selected(index)
        if index is None or not (0 <= index < len(self._trades)) or not centre:
            return
        t = self._trades[index]
        span = max(30, int((t.exit_bar - t.entry_bar) * 3))
        mid = (t.entry_bar + t.exit_bar) / 2.0
        self.price_plot.setXRange(mid - span / 2, mid + span / 2, padding=0)

    def clear(self) -> None:
        self.set_bars(None)
        self.set_indicator_panels([])
        self.set_trades([])

    # -- navigation ------------------------------------------------------

    def show_last(self, count: int) -> None:
        n = len(self._ts)
        if n == 0:
            return
        count = int(max(10, min(count, n)))
        self.price_plot.setXRange(n - count - 0.5, n + count * 0.06, padding=0)

    def fit_all(self) -> None:
        n = len(self._ts)
        if n:
            self.price_plot.setXRange(-0.5, n - 0.5, padding=0.01)

    def zoom_in(self) -> None:
        self._zoom(0.75)

    def zoom_out(self) -> None:
        self._zoom(1.0 / 0.75)

    def _zoom(self, factor: float, anchor: float | None = None) -> None:
        n = len(self._ts)
        if n == 0:
            return
        (x0, x1), _ = self.price_plot.getViewBox().viewRange()
        centre = anchor if anchor is not None else (x0 + x1) / 2.0
        half = (x1 - x0) * factor / 2.0
        half = float(np.clip(half, 5.0, max(10.0, n * 1.5)))
        self.price_plot.setXRange(centre - half, centre + half, padding=0)

    def _wheel_zoom(self, delta: float, pos: float) -> None:
        self._zoom(0.85 if delta > 0 else 1.0 / 0.85, pos)

    def goto_bar(self, index: int) -> None:
        (x0, x1), _ = self.price_plot.getViewBox().viewRange()
        half = (x1 - x0) / 2.0
        self.price_plot.setXRange(index - half, index + half, padding=0)

    def toggle_crosshair(self) -> None:
        self._crosshair_on = not self._crosshair_on
        if not self._crosshair_on:
            for v in self._vlines:
                v.hide()
            self._hline.hide()
            self._price_tag.hide()

    def set_chart_type(self, kind: str) -> None:
        self.candles.set_mode(kind)

    def set_log_scale(self, enabled: bool) -> None:
        self._log_scale = bool(enabled)
        self.price_plot.setLogMode(x=False, y=self._log_scale)

    def visible_range(self) -> tuple[int, int]:
        (x0, x1), _ = self.price_plot.getViewBox().viewRange()
        n = len(self._ts)
        return (int(max(0, np.floor(x0))), int(min(n, np.ceil(x1))))

    # -- interaction -----------------------------------------------------

    def _on_x_range_changed(self, *_args) -> None:
        """Rescale the price panel's y axis to the bars actually in view."""
        if self._bars is None or self._suppress_autoscale:
            return
        n = len(self._ts)
        if n == 0:
            return
        i0, i1 = self.visible_range()
        i0 = max(0, min(i0, n - 1))
        i1 = max(i0 + 1, min(i1, n))
        lows = self._bars.low[i0:i1]
        highs = self._bars.high[i0:i1]
        if len(lows) == 0 or not np.isfinite(lows).any():
            return
        lo = float(np.nanmin(lows)); hi = float(np.nanmax(highs))

        # Give the markers headroom so entry arrows are not clipped by the frame.
        pad = max((hi - lo) * 0.08, 1e-9)
        self._suppress_autoscale = True
        try:
            self.price_plot.setYRange(lo - pad, hi + pad, padding=0)
            vol = self._bars.volume[i0:i1]
            if len(vol) and np.isfinite(vol).any():
                top = float(np.nanmax(vol))
                self.volume_plot.setYRange(0.0, top * 1.12 if top > 0 else 1.0, padding=0)
        finally:
            self._suppress_autoscale = False
        self.rangeChanged.emit(i0, i1)

    def _on_mouse_moved(self, scene_pos) -> None:
        if not self._crosshair_on or len(self._ts) == 0:
            return
        vb = self.price_plot.getViewBox()
        if not self.price_plot.sceneBoundingRect().contains(scene_pos):
            # Still track the x position when the pointer is over a sub-panel.
            for panel in self._panels[1:]:
                if panel.plot.sceneBoundingRect().contains(scene_pos):
                    p = panel.plot.getViewBox().mapSceneToView(scene_pos)
                    self._set_crosshair(int(round(p.x())), None)
                    return
            return
        point: QPointF = vb.mapSceneToView(scene_pos)
        self._set_crosshair(int(round(point.x())), float(point.y()))

    def _set_crosshair(self, index: int, y: float | None) -> None:
        n = len(self._ts)
        if n == 0:
            return
        index = int(np.clip(index, 0, n - 1))
        for v in self._vlines:
            v.setPos(index)
            v.show()
        if y is None:
            self._hline.hide()
            self._price_tag.hide()
        else:
            self._hline.setPos(y)
            self._hline.show()
            (_x0, x1), _ = self.price_plot.getViewBox().viewRange()
            self._price_tag.setText(f"{y:,.{self._decimals}f}")
            self._price_tag.setPos(x1, y)
            self._price_tag.show()
        self._update_readout(index)
        self.barHovered.emit(index)

    def _update_readout(self, index: int) -> None:
        if self._bars is None or not (0 <= index < len(self._ts)):
            return
        import pandas as pd

        b = self._bars
        d = self._decimals
        o, h, l, c = (b.open[index], b.high[index], b.low[index], b.close[index])
        change = c - o
        col = PALETTE.long if change >= 0 else PALETTE.short
        ts = pd.Timestamp(int(self._ts[index]), tz="UTC")
        try:
            ts = ts.tz_convert(self._timezone)
        except Exception:
            pass
        vol = b.volume[index]
        vol_txt = f"  V <span style='color:{PALETTE.text_dim}'>{number(vol, 0)}</span>" \
            if vol > 0 else ""
        self.ohlc_label.setText(
            f"<span style='color:{PALETTE.text_muted}'>{ts:%Y-%m-%d %H:%M}</span>   "
            f"O <span style='color:{col}'>{o:,.{d}f}</span>  "
            f"H <span style='color:{col}'>{h:,.{d}f}</span>  "
            f"L <span style='color:{col}'>{l:,.{d}f}</span>  "
            f"C <span style='color:{col}'>{c:,.{d}f}</span>  "
            f"<span style='color:{col}'>{change:+,.{d}f}</span>"
            f"{vol_txt}")

    def _on_mouse_clicked(self, ev) -> None:
        if len(self._trades) == 0 or ev.button() != Qt.MouseButton.LeftButton:
            return
        vb = self.price_plot.getViewBox()
        if not self.price_plot.sceneBoundingRect().contains(ev.scenePos()):
            return
        p = vb.mapSceneToView(ev.scenePos())
        x, y = p.x(), p.y()
        (x0, x1), (y0, y1) = vb.viewRange()
        # Tolerance in data units equal to roughly 12 screen pixels.
        tol_x = (x1 - x0) * 0.02
        tol_y = (y1 - y0) * 0.03
        best, best_d = None, float("inf")
        for i, t in enumerate(self._trades):
            for bx, by in ((t.entry_bar, t.entry_price), (t.exit_bar, t.exit_price)):
                dx = abs(bx - x) / max(tol_x, 1e-9)
                dy = abs(by - y) / max(tol_y, 1e-9)
                d = dx * dx + dy * dy
                if d < best_d and dx < 1.6 and dy < 1.6:
                    best, best_d = i, d
        if best is not None:
            self.select_trade(best, centre=False)
            self.tradeClicked.emit(best)
