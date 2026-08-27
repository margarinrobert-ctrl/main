"""Custom pyqtgraph items: candles, volume, trade markers and level lines.

Two decisions shape this module.

First, the x axis is the **bar index**, not the timestamp.  Charting by timestamp
leaves a gap for every weekend and every overnight break, which is what a naive
plot of intraday data looks like and what no trading application does.  The
:class:`TimeAxisItem` turns indices back into dates for the labels.

Second, each item paints only the bars currently in view rather than caching a
``QPicture`` of the whole series.  A cached picture of 500,000 candles costs
hundreds of megabytes and stalls the first paint; clipping to the view keeps the
cost proportional to the window, so panning a million-bar dataset stays smooth.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPicture, QPolygonF

from ..theme import PALETTE


def _view_range(item: pg.GraphicsObject) -> tuple[float, float]:
    """The x range currently visible, or the whole item when there is no view."""
    vb = item.getViewBox()
    if vb is None:
        return (-np.inf, np.inf)
    (x0, x1), _ = vb.viewRange()
    return (x0, x1)


def _runs(mask) -> list[tuple[int, int]]:
    """The ``[start, stop)`` spans where *mask* is true.

    Used to break a band or a line at NaN rather than drawing a straight edge
    across the gap.
    """
    mask = np.asarray(mask, dtype=bool)
    if not mask.any():
        return []
    edges = np.flatnonzero(np.diff(np.concatenate(([False], mask, [False]))))
    return list(zip(edges[0::2].tolist(), edges[1::2].tolist()))


def _stride(item: pg.GraphicsObject, points: int) -> int:
    """How many data points share one pixel column, at least 1.

    Painting more points than the widget has pixels is work no one can see, and
    on a half-million-bar dataset it is the difference between a chart that
    opens and a window that stops answering.
    """
    vb = item.getViewBox()
    if vb is None or points <= 0:
        return 1
    width_px = float(vb.width())
    if width_px <= 1.0:
        return 1
    return max(1, int(points // max(1.0, width_px)))


def _peak(xs, values, stride: int):
    """One sample per column, the one furthest from zero."""
    n = (len(values) // stride) * stride
    if n < stride:
        return xs, values
    block = np.abs(values[:n]).reshape(-1, stride)
    pick = block.argmax(axis=1) + np.arange(0, n, stride)
    tail = np.arange(n, len(values))
    keep = np.concatenate((pick, tail)) if len(tail) else pick
    return xs[keep], values[keep]


def _envelope(xs, top, bottom, stride: int):
    """Per-column outer envelope of a band.

    Taken over *both* series rather than assuming one is always above the
    other: the caller's "upper" and "lower" are whichever outputs the indicator
    named, and a band whose edges cross -- a squeeze, a Donchian channel at a
    new extreme -- would otherwise be drawn inside out.
    """
    n = (len(top) // stride) * stride
    if n < stride:
        return xs, top, bottom
    a = top[:n].reshape(-1, stride)
    b = bottom[:n].reshape(-1, stride)
    hi = np.maximum(a.max(axis=1), b.max(axis=1))
    lo = np.minimum(a.min(axis=1), b.min(axis=1))
    x = xs[:n].reshape(-1, stride).mean(axis=1)
    if n < len(top):
        x = np.concatenate((x, xs[n:]))
        hi = np.concatenate((hi, top[n:]))
        lo = np.concatenate((lo, bottom[n:]))
    return x, hi, lo


def clip_to_view(curve) -> None:
    """Make a curve cost what is on screen rather than what is in the file.

    Without this pyqtgraph builds the whole polyline on every paint: at half a
    million bars that is seconds per indicator, on the GUI thread, which is what
    the window not painting looks like.  ``clipToView`` narrows the work to the
    visible x range and peak downsampling keeps the shape honest when zoomed
    out -- the extremes of each pixel column are kept, so a spike never
    disappears between samples.  Both recompute on every view change, so zooming
    in still shows every bar.

    Call this **after** the curve has been added to a plot.  ``clipToView``
    asks the item for its view box, and pyqtgraph caches whatever it finds; an
    item with no plot yet answers with the enclosing graphics widget, which is
    then used as a view box on the next paint and raises.
    """
    try:
        if not isinstance(curve.getViewBox(), pg.ViewBox):
            return
        curve.setClipToView(True)
        curve.setDownsampling(auto=True, method="peak")
    except Exception:            # noqa: BLE001 - a chart is not worth a crash
        pass


class CandlestickItem(pg.GraphicsObject):
    """OHLC candles with a level-of-detail switch.

    Below about three pixels per bar the bodies would collapse into a smear, so
    the item silently switches to a one-pixel-per-bar close line -- the same
    thing every professional charting package does when you zoom out.
    """

    def __init__(self, opens=None, highs=None, lows=None, closes=None,
                 up_color: str | None = None, down_color: str | None = None) -> None:
        super().__init__()
        self._o = np.empty(0); self._h = np.empty(0)
        self._l = np.empty(0); self._c = np.empty(0)
        self.up = QColor(up_color or PALETTE.long)
        self.down = QColor(down_color or PALETTE.short)
        self.mode = "candles"      # candles | bars | line | area
        self._bounds = QRectF()
        if opens is not None:
            self.set_data(opens, highs, lows, closes)

    def set_data(self, opens, highs, lows, closes) -> None:
        self._o = np.ascontiguousarray(opens, dtype="float64")
        self._h = np.ascontiguousarray(highs, dtype="float64")
        self._l = np.ascontiguousarray(lows, dtype="float64")
        self._c = np.ascontiguousarray(closes, dtype="float64")
        n = len(self._o)
        if n and np.isfinite(self._l).any() and np.isfinite(self._h).any():
            lo = float(np.nanmin(self._l)); hi = float(np.nanmax(self._h))
            self._bounds = QRectF(-0.5, lo, n, max(hi - lo, 1e-9))
        else:
            # An all-NaN series has no extent; an empty rect draws nothing
            # rather than propagating NaN into the view transform.
            self._bounds = QRectF()
        self.prepareGeometryChange()
        self.informViewBoundsChanged()
        self.update()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.update()

    def boundingRect(self) -> QRectF:  # noqa: N802 - Qt naming
        return self._bounds

    def paint(self, painter: QPainter, *_args) -> None:  # noqa: N802
        n = len(self._o)
        if n == 0:
            return
        x0, x1 = _view_range(self)
        i0 = max(0, int(np.floor(x0)) - 1)
        i1 = min(n, int(np.ceil(x1)) + 2)
        if i1 <= i0:
            return

        vb = self.getViewBox()
        px_per_bar = 6.0
        if vb is not None:
            width_px = max(1.0, vb.width())
            span = max(1e-9, x1 - x0)
            px_per_bar = width_px / span

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, px_per_bar > 2.5)
        o = self._o[i0:i1]; h = self._h[i0:i1]
        low = self._l[i0:i1]; c = self._c[i0:i1]
        idx = np.arange(i0, i1, dtype="float64")
        up_mask = c >= o

        if self.mode in ("line", "area") or px_per_bar < 2.0:
            self._paint_line(painter, idx, c, filled=(self.mode == "area"))
            return
        if self.mode == "bars":
            self._paint_ohlc_bars(painter, idx, o, h, low, c, up_mask, px_per_bar)
            return
        self._paint_candles(painter, idx, o, h, low, c, up_mask, px_per_bar)

    # -- painters --------------------------------------------------------

    #: Candle body width in bar units.  0.8 leaves a one-fifth gap between
    #: neighbours, which is the proportion every charting package settles on.
    BODY_WIDTH = 0.8

    def _paint_candles(self, painter, idx, o, h, low, c, up_mask, px_per_bar) -> None:
        half = self.BODY_WIDTH / 2.0
        # Below about three and a half pixels per bar a filled body is wider
        # than the space it has, so only the wick is drawn.
        wicks_only = px_per_bar < 3.5

        for mask, color in ((up_mask, self.up), (~up_mask, self.down)):
            if not mask.any():
                continue
            xi = idx[mask]; oi = o[mask]; hi = h[mask]; li = low[mask]; ci = c[mask]
            pen = QPen(color)
            pen.setCosmetic(True)
            pen.setWidth(1)
            painter.setPen(pen)
            for x, hh, ll in zip(xi, hi, li):
                if hh == hh and ll == ll:
                    painter.drawLine(QPointF(x, ll), QPointF(x, hh))
            if wicks_only:
                continue
            painter.setBrush(QBrush(color))
            for x, oo, cc in zip(xi, oi, ci):
                if oo != oo or cc != cc:
                    continue
                bot, top = min(oo, cc), max(oo, cc)
                height = top - bot
                if height <= 0:
                    # A doji has no body; a line marks where it opened and closed.
                    painter.drawLine(QPointF(x - half, oo), QPointF(x + half, oo))
                else:
                    painter.drawRect(QRectF(x - half, bot, self.BODY_WIDTH, height))

    def _paint_ohlc_bars(self, painter, idx, o, h, low, c, up_mask, px_per_bar) -> None:
        tick = 0.32
        for mask, color in ((up_mask, self.up), (~up_mask, self.down)):
            if not mask.any():
                continue
            pen = QPen(color)
            pen.setCosmetic(True)
            pen.setWidth(1)
            painter.setPen(pen)
            for x, oo, hh, ll, cc in zip(idx[mask], o[mask], h[mask], low[mask], c[mask]):
                painter.drawLine(QPointF(x, ll), QPointF(x, hh))
                if px_per_bar >= 3.0:
                    painter.drawLine(QPointF(x - tick, oo), QPointF(x, oo))
                    painter.drawLine(QPointF(x, cc), QPointF(x + tick, cc))

    def _paint_line(self, painter, idx, c, filled: bool) -> None:
        pen = QPen(QColor(PALETTE.accent))
        pen.setCosmetic(True)
        pen.setWidth(1)
        painter.setPen(pen)
        poly = QPolygonF([QPointF(float(x), float(y)) for x, y in zip(idx, c)
                          if y == y])
        if len(poly) < 2:
            return
        painter.drawPolyline(poly)
        if filled:
            fill = QPolygonF(poly)
            floor = float(self._bounds.top())
            fill.append(QPointF(poly[-1].x(), floor))
            fill.append(QPointF(poly[0].x(), floor))
            col = QColor(PALETTE.accent); col.setAlpha(38)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(col))
            painter.drawPolygon(fill)


class VolumeItem(pg.GraphicsObject):
    """Volume histogram, coloured by whether the bar closed up or down."""

    def __init__(self, volume=None, opens=None, closes=None) -> None:
        super().__init__()
        self._v = np.empty(0); self._up = np.empty(0, dtype=bool)
        self._bounds = QRectF()
        if volume is not None:
            self.set_data(volume, opens, closes)

    def set_data(self, volume, opens, closes) -> None:
        self._v = np.ascontiguousarray(volume, dtype="float64")
        o = np.ascontiguousarray(opens, dtype="float64")
        c = np.ascontiguousarray(closes, dtype="float64")
        self._up = c >= o
        n = len(self._v)
        top = float(np.nanmax(self._v)) if n and np.isfinite(self._v).any() else 1.0
        self._bounds = QRectF(-0.5, 0.0, max(n, 1), max(top, 1e-9))
        self.prepareGeometryChange()
        self.informViewBoundsChanged()
        self.update()

    def boundingRect(self) -> QRectF:  # noqa: N802
        return self._bounds

    def paint(self, painter: QPainter, *_args) -> None:  # noqa: N802
        n = len(self._v)
        if n == 0:
            return
        x0, x1 = _view_range(self)
        i0 = max(0, int(np.floor(x0)) - 1)
        i1 = min(n, int(np.ceil(x1)) + 2)
        if i1 <= i0:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        idx = np.arange(i0, i1, dtype="float64")
        v = self._v[i0:i1]
        up = self._up[i0:i1]
        for mask, color in ((up, QColor(PALETTE.volume_up)),
                            (~up, QColor(PALETTE.volume_down))):
            if not mask.any():
                continue
            painter.setBrush(QBrush(color))
            for x, vv in zip(idx[mask], v[mask]):
                if vv > 0:
                    painter.drawRect(QRectF(x - 0.35, 0.0, 0.7, vv))


class BandFillItem(pg.GraphicsObject):
    """The shaded area between two indicator lines, clipped to the view.

    pyqtgraph ships :class:`~pyqtgraph.FillBetweenItem` for this, and it builds
    one ``QPainterPath`` over every point in the series the moment the curves
    are set.  At 581,195 bars -- the shipped US30 5-minute file -- that single
    call takes about two seconds, and a Bollinger band draws three of them, on
    the GUI thread, before the window has painted once.  A chart with a band
    indicator and a large dataset therefore opened as a white unresponsive
    rectangle: the freeze users report.

    This follows the module's own rule instead and paints only the bars in view,
    so the cost is proportional to the window rather than to the file.  NaN runs
    (an indicator's warm-up, or a gap) break the band into separate polygons
    rather than being bridged by a straight edge across the chart.
    """

    def __init__(self, upper=None, lower=None, brush=None) -> None:
        super().__init__()
        self._a = np.empty(0)
        self._b = np.empty(0)
        self.brush = QBrush(brush if isinstance(brush, QColor) else QColor(brush)
                            if brush is not None else QColor(PALETTE.accent))
        self._bounds = QRectF()
        if upper is not None and lower is not None:
            self.set_data(upper, lower)

    def set_data(self, upper, lower) -> None:
        a = np.ascontiguousarray(upper, dtype="float64")
        b = np.ascontiguousarray(lower, dtype="float64")
        n = min(len(a), len(b))
        self._a = a[:n]
        self._b = b[:n]
        both = np.isfinite(self._a) & np.isfinite(self._b)
        if n and both.any():
            lo = float(min(self._a[both].min(), self._b[both].min()))
            hi = float(max(self._a[both].max(), self._b[both].max()))
            self._bounds = QRectF(-0.5, lo, n, max(hi - lo, 1e-9))
        else:
            self._bounds = QRectF()
        self.prepareGeometryChange()
        self.informViewBoundsChanged()
        self.update()

    def set_brush(self, brush) -> None:
        self.brush = QBrush(brush)
        self.update()

    def boundingRect(self) -> QRectF:  # noqa: N802
        return self._bounds

    def paint(self, painter: QPainter, *_args) -> None:  # noqa: N802
        n = len(self._a)
        if n == 0:
            return
        x0, x1 = _view_range(self)
        i0 = max(0, int(np.floor(x0)) - 1)
        i1 = min(n, int(np.ceil(x1)) + 2)
        if i1 <= i0 + 1:
            return
        a = self._a[i0:i1]
        b = self._b[i0:i1]
        good = np.isfinite(a) & np.isfinite(b)
        if not good.any():
            return
        stride = _stride(self, i1 - i0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.brush)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        for start, stop in _runs(good):
            if stop - start < 2:
                continue        # a single point has no area to shade
            xs = np.arange(i0 + start, i0 + stop, dtype="float64")
            top = a[start:stop]
            bottom = b[start:stop]
            if stride > 1:
                # Zoomed far enough out that many points share a pixel column.
                # Keep the outer envelope of each column so the band never looks
                # narrower than it is; the cost becomes the width of the widget
                # instead of the length of the file.
                xs, top, bottom = _envelope(xs, top, bottom, stride)
            poly = QPolygonF([QPointF(float(x), float(y))
                              for x, y in zip(xs, top)])
            for x, y in zip(xs[::-1], bottom[::-1]):
                poly.append(QPointF(float(x), float(y)))
            painter.drawPolygon(poly)


class HistogramItem(pg.GraphicsObject):
    """A signed indicator histogram (MACD, awesome oscillator), clipped to view.

    The replaced ``pg.BarGraphItem`` took a per-bar brush list, so colouring a
    histogram by sign built one ``QBrush`` per bar -- 581,195 of them for the
    shipped 5-minute file, before anything was drawn.  Two masks and two brushes
    do the same job in constant memory.
    """

    def __init__(self, values=None, color: str | None = None,
                 negative_color: str | None = None) -> None:
        super().__init__()
        self._v = np.empty(0)
        self.up = QColor(color or PALETTE.long)
        self.down = QColor(negative_color or color or PALETTE.short)
        self._bounds = QRectF()
        if values is not None:
            self.set_data(values)

    def set_data(self, values) -> None:
        self._v = np.nan_to_num(np.ascontiguousarray(values, dtype="float64"))
        n = len(self._v)
        if n:
            lo = min(0.0, float(self._v.min()))
            hi = max(0.0, float(self._v.max()))
            self._bounds = QRectF(-0.5, lo, n, max(hi - lo, 1e-9))
        else:
            self._bounds = QRectF()
        self.prepareGeometryChange()
        self.informViewBoundsChanged()
        self.update()

    def boundingRect(self) -> QRectF:  # noqa: N802
        return self._bounds

    #: Bar width in bar units, matching :class:`VolumeItem`.
    BAR_WIDTH = 0.7

    def paint(self, painter: QPainter, *_args) -> None:  # noqa: N802
        n = len(self._v)
        if n == 0:
            return
        x0, x1 = _view_range(self)
        i0 = max(0, int(np.floor(x0)) - 1)
        i1 = min(n, int(np.ceil(x1)) + 2)
        if i1 <= i0:
            return
        v = self._v[i0:i1]
        idx = np.arange(i0, i1, dtype="float64")
        stride = _stride(self, i1 - i0)
        half = self.BAR_WIDTH / 2.0
        if stride > 1:
            # One bar per pixel column, taking whichever of its values is
            # furthest from zero so a spike is never sampled away.
            idx, v = _peak(idx, v, stride)
            half = max(half, stride / 2.0)
        painter.setPen(Qt.PenStyle.NoPen)
        positive = v >= 0
        for mask, color in ((positive, self.up), (~positive, self.down)):
            if not mask.any():
                continue
            painter.setBrush(QBrush(color))
            for x, vv in zip(idx[mask], v[mask]):
                if vv == 0.0:
                    continue
                painter.drawRect(QRectF(x - half, min(0.0, vv), half * 2.0,
                                        abs(vv)))


class TradeMarkerItem(pg.GraphicsObject):
    """Entry/exit arrows plus a connecting line coloured by trade outcome.

    ``set_trades`` takes plain tuples so the item never imports the engine.
    """

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[tuple[int, float, int, float, bool, bool]] = []
        self._bounds = QRectF()
        self._show_connectors = True
        self._selected: int | None = None

    def set_trades(self, rows) -> None:
        """``rows`` = iterable of ``(entry_bar, entry_price, exit_bar, exit_price,
        is_long, is_win)``."""
        self._rows = [tuple(r) for r in rows]
        if self._rows:
            xs = [r[0] for r in self._rows] + [r[2] for r in self._rows]
            ys = [r[1] for r in self._rows] + [r[3] for r in self._rows]
            self._bounds = QRectF(min(xs) - 1, min(ys), max(xs) - min(xs) + 2,
                                  max(1e-9, max(ys) - min(ys)))
        else:
            self._bounds = QRectF()
        self.prepareGeometryChange()
        self.update()

    def set_selected(self, index: int | None) -> None:
        self._selected = index
        self.update()

    def set_connectors(self, on: bool) -> None:
        self._show_connectors = on
        self.update()

    def boundingRect(self) -> QRectF:  # noqa: N802
        return self._bounds

    def paint(self, painter: QPainter, *_args) -> None:  # noqa: N802
        if not self._rows:
            return
        vb = self.getViewBox()
        if vb is None:
            return
        x0, x1 = _view_range(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Marker size is set in pixels then converted to data units so arrows
        # keep a constant on-screen size at any zoom.
        px = vb.viewPixelSize()
        mw = px[0] * 6.0
        mh = px[1] * 11.0

        for i, (eb, ep, xb, xp, is_long, is_win) in enumerate(self._rows):
            if xb < x0 - 2 or eb > x1 + 2:
                continue
            selected = (self._selected == i)
            base = QColor(PALETTE.marker_long if is_long else PALETTE.marker_short)
            if self._show_connectors:
                line = QColor(PALETTE.long if is_win else PALETTE.short)
                line.setAlpha(210 if selected else 120)
                pen = QPen(line, 2.0 if selected else 1.0)
                pen.setCosmetic(True)
                if not selected:
                    pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.drawLine(QPointF(eb, ep), QPointF(xb, xp))

            painter.setPen(QPen(QColor("#0b0f16"), 0.8 if selected else 0.0))
            painter.setBrush(QBrush(base.lighter(125) if selected else base))
            if is_long:
                tri = QPolygonF([QPointF(eb, ep - mh * 0.35),
                                 QPointF(eb - mw, ep - mh * 1.25),
                                 QPointF(eb + mw, ep - mh * 1.25)])
            else:
                tri = QPolygonF([QPointF(eb, ep + mh * 0.35),
                                 QPointF(eb - mw, ep + mh * 1.25),
                                 QPointF(eb + mw, ep + mh * 1.25)])
            painter.drawPolygon(tri)

            exit_col = QColor(PALETTE.marker_exit)
            painter.setBrush(QBrush(exit_col))
            painter.setPen(QPen(QColor("#0b0f16"), 0.0))
            painter.drawPolygon(QPolygonF([
                QPointF(xb, xp), QPointF(xb - mw * 0.8, xp + mh * 0.55),
                QPointF(xb, xp + mh * 1.1), QPointF(xb + mw * 0.8, xp + mh * 0.55)]))


class LevelLinesItem(pg.GraphicsObject):
    """Horizontal stop and target segments spanning a trade's holding period."""

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[tuple[int, int, float | None, float | None]] = []
        self._bounds = QRectF()

    def set_levels(self, rows) -> None:
        """``rows`` = iterable of ``(entry_bar, exit_bar, stop, target)``."""
        self._rows = [tuple(r) for r in rows]
        ys = [v for r in self._rows for v in (r[2], r[3]) if v is not None]
        if self._rows and ys:
            xs = [r[0] for r in self._rows] + [r[1] for r in self._rows]
            self._bounds = QRectF(min(xs) - 1, min(ys), max(xs) - min(xs) + 2,
                                  max(1e-9, max(ys) - min(ys)))
        else:
            self._bounds = QRectF()
        self.prepareGeometryChange()
        self.update()

    def boundingRect(self) -> QRectF:  # noqa: N802
        return self._bounds

    def paint(self, painter: QPainter, *_args) -> None:  # noqa: N802
        if not self._rows:
            return
        x0, x1 = _view_range(self)
        for eb, xb, stop, target in self._rows:
            if xb < x0 - 2 or eb > x1 + 2:
                continue
            for level, colour in ((stop, PALETTE.stop_line), (target, PALETTE.target_line)):
                if level is None or level != level:
                    continue
                pen = QPen(QColor(colour), 1.0, Qt.PenStyle.DashLine)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.drawLine(QPointF(eb, level), QPointF(max(xb, eb + 0.5), level))


class SessionShadingItem(pg.GraphicsObject):
    """Vertical bands marking bars outside the tradeable session."""

    def __init__(self) -> None:
        super().__init__()
        self._spans: list[tuple[int, int]] = []
        self._bounds = QRectF()

    def set_spans(self, spans, y_lo: float = -1e12, y_hi: float = 1e12) -> None:
        self._spans = [tuple(s) for s in spans]
        if self._spans:
            self._bounds = QRectF(self._spans[0][0] - 1, y_lo,
                                  self._spans[-1][1] - self._spans[0][0] + 2, y_hi - y_lo)
        else:
            self._bounds = QRectF()
        self.prepareGeometryChange()
        self.update()

    def boundingRect(self) -> QRectF:  # noqa: N802
        return self._bounds

    def paint(self, painter: QPainter, *_args) -> None:  # noqa: N802
        if not self._spans:
            return
        vb = self.getViewBox()
        if vb is None:
            return
        (x0, x1), (y0, y1) = vb.viewRange()
        col = QColor(PALETTE.session_shade)
        col.setAlpha(150)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(col))
        for a, b in self._spans:
            if b < x0 or a > x1:
                continue
            painter.drawRect(QRectF(a - 0.5, y0, (b - a) + 1.0, y1 - y0))


#: The last few index conversions, keyed by the array's identity and timezone.
#: A chart has one time axis per panel and they are all given the same
#: timestamps, so without this a five-panel chart converted the same half-
#: million values five times.  The array is held in the value, so an ``id``
#: reused after garbage collection cannot return another array's dates.
_DT_CACHE: dict[tuple[int, str], tuple[Any, Any]] = {}
_DT_CACHE_SIZE = 6


def _localise(ts: np.ndarray, timezone: str):
    """int64 nanoseconds -> a tz-aware ``DatetimeIndex``.

    ``pd.to_datetime`` on an integer array without ``unit`` takes the object
    path -- 0.21s for 581,195 values against 0.006s for the vectorised one, per
    axis, on the GUI thread while the window waits to paint.
    """
    import pandas as pd

    key = (id(ts), str(timezone))
    hit = _DT_CACHE.get(key)
    if hit is not None and hit[0] is ts:
        return hit[1]
    idx = pd.DatetimeIndex(pd.to_datetime(ts, unit="ns", utc=True))
    try:
        idx = idx.tz_convert(timezone)
    except Exception:
        pass          # An unknown timezone must not break the axis; stay in UTC.
    if len(_DT_CACHE) >= _DT_CACHE_SIZE:
        _DT_CACHE.pop(next(iter(_DT_CACHE)))
    _DT_CACHE[key] = (ts, idx)
    return idx


class TimeAxisItem(pg.AxisItem):
    """Bottom axis that labels bar indices with dates from the timestamp array.

    The label granularity adapts to the visible span, and the first tick after a
    day (or month, or year) boundary is given the longer form, which is how a
    trading chart shows you where you are without a second axis.
    """

    def __init__(self, orientation: str = "bottom", **kwargs) -> None:
        super().__init__(orientation, **kwargs)
        self._ts = np.empty(0, dtype="int64")
        self._dt = None
        self.setStyle(tickTextOffset=6, tickLength=-5, autoExpandTextSpace=True)
        self.setTextPen(pg.mkPen(PALETTE.axis_text))
        self.setPen(pg.mkPen(PALETTE.border))

    def set_timestamps(self, ts, timezone: str = "UTC") -> None:
        self._ts = np.ascontiguousarray(ts, dtype="int64")
        self._dt = _localise(self._ts, timezone) if len(self._ts) else None
        self.picture = None
        self.update()

    def tickStrings(self, values, scale, spacing):  # noqa: N802
        if self._dt is None or len(self._dt) == 0:
            return ["" for _ in values]
        n = len(self._dt)
        out: list[str] = []
        span = float(spacing) if spacing else 1.0
        for v in values:
            i = int(round(v))
            if i < 0 or i >= n:
                out.append("")
                continue
            t = self._dt[i]
            prev = self._dt[i - 1] if i > 0 else None
            new_day = prev is None or t.date() != prev.date()
            new_month = prev is None or (t.year, t.month) != (prev.year, prev.month)
            new_year = prev is None or t.year != prev.year
            if span >= 20000 or new_year:
                out.append(t.strftime("%Y"))
            elif span >= 600 or new_month:
                out.append(t.strftime("%b %Y") if span >= 200 else t.strftime("%d %b"))
            elif new_day or span >= 60:
                out.append(t.strftime("%d %b"))
            else:
                out.append(t.strftime("%H:%M"))
        return out


class PriceAxisItem(pg.AxisItem):
    """Right-hand price axis with a fixed number of decimals."""

    def __init__(self, decimals: int = 2, orientation: str = "right", **kwargs) -> None:
        super().__init__(orientation, **kwargs)
        self.decimals = decimals
        self.setStyle(tickTextOffset=6, tickLength=-5, autoExpandTextSpace=True)
        self.setTextPen(pg.mkPen(PALETTE.axis_text))
        self.setPen(pg.mkPen(PALETTE.border))

    def set_decimals(self, decimals: int) -> None:
        self.decimals = max(0, min(8, int(decimals)))
        self.picture = None
        self.update()

    def tickStrings(self, values, scale, spacing):  # noqa: N802
        d = self.decimals
        if spacing and spacing < 10 ** (-d):
            d = min(8, d + 2)
        return [f"{v:,.{d}f}" for v in values]


class PriceTagItem(pg.GraphicsObject):
    """The floating last-price tag pinned to the right edge of the price axis."""

    def __init__(self, color: str | None = None) -> None:
        super().__init__()
        self._price: float | None = None
        self._text = ""
        self._color = QColor(color or PALETTE.accent)
        self._picture = QPicture()
        self.setZValue(60)

    def set_price(self, price: float | None, text: str, color: str | None = None) -> None:
        self._price = price
        self._text = text
        if color:
            self._color = QColor(color)
        self.prepareGeometryChange()
        self.update()

    def boundingRect(self) -> QRectF:  # noqa: N802
        vb = self.getViewBox()
        if vb is None or self._price is None:
            return QRectF()
        (x0, x1), _ = vb.viewRange()
        return QRectF(x0, self._price - 1e-6, x1 - x0, 2e-6)

    def paint(self, painter: QPainter, *_args) -> None:  # noqa: N802
        vb = self.getViewBox()
        if vb is None or self._price is None:
            return
        (x0, x1), _ = vb.viewRange()
        pen = QPen(self._color, 1.0, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawLine(QPointF(x0, self._price), QPointF(x1, self._price))
