"""Vector icons drawn at runtime.

The application ships no image files.  Every icon is a small painter routine, so
icons stay crisp at any DPI, recolour themselves from the theme, and cannot go
missing from a PyInstaller bundle.  Icons are cached per (name, size, colour).
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QSize
from PySide6.QtGui import (QColor, QIcon, QLinearGradient, QPainter, QPainterPath,
                           QPen, QPixmap, QPolygonF)

from .theme import PALETTE

_cache: dict[tuple[str, int, str], QIcon] = {}
_DrawFn = Callable[[QPainter, float, QColor], None]
_drawers: dict[str, _DrawFn] = {}


def _icon(name: str) -> Callable[[_DrawFn], _DrawFn]:
    def deco(fn: _DrawFn) -> _DrawFn:
        _drawers[name] = fn
        return fn
    return deco


def _pen(c: QColor, w: float = 1.6) -> QPen:
    p = QPen(c, w)
    p.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return p


# --------------------------------------------------------------------------
# Drawing routines.  Each draws inside a 24x24 logical box; ``s`` is the scale
# from that box to the requested pixel size.
# --------------------------------------------------------------------------

@_icon("folder-open")
def _folder_open(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.6 * s))
    path = QPainterPath()
    path.moveTo(3 * s, 19 * s); path.lineTo(3 * s, 6 * s)
    path.lineTo(9 * s, 6 * s); path.lineTo(11 * s, 8.5 * s); path.lineTo(19 * s, 8.5 * s)
    p.drawPath(path)
    poly = QPolygonF([QPointF(3 * s, 19 * s), QPointF(6.5 * s, 11 * s),
                      QPointF(22 * s, 11 * s), QPointF(18.5 * s, 19 * s)])
    p.drawPolygon(poly)


@_icon("save")
def _save(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.6 * s))
    p.drawRoundedRect(QRectF(4 * s, 4 * s, 16 * s, 16 * s), 2 * s, 2 * s)
    p.drawRect(QRectF(8 * s, 4 * s, 8 * s, 5.5 * s))
    p.drawRect(QRectF(7 * s, 13 * s, 10 * s, 7 * s))


@_icon("import")
def _import(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.6 * s))
    p.drawLine(QPointF(12 * s, 3.5 * s), QPointF(12 * s, 14 * s))
    p.drawLine(QPointF(7.5 * s, 9.5 * s), QPointF(12 * s, 14.5 * s))
    p.drawLine(QPointF(16.5 * s, 9.5 * s), QPointF(12 * s, 14.5 * s))
    p.drawLine(QPointF(4 * s, 19 * s), QPointF(20 * s, 19 * s))


@_icon("export")
def _export(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.6 * s))
    p.drawLine(QPointF(12 * s, 15 * s), QPointF(12 * s, 4 * s))
    p.drawLine(QPointF(7.5 * s, 8.5 * s), QPointF(12 * s, 3.6 * s))
    p.drawLine(QPointF(16.5 * s, 8.5 * s), QPointF(12 * s, 3.6 * s))
    p.drawLine(QPointF(4 * s, 19.5 * s), QPointF(20 * s, 19.5 * s))


@_icon("run")
def _run(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawPolygon(QPolygonF([QPointF(7 * s, 4.5 * s), QPointF(20 * s, 12 * s),
                             QPointF(7 * s, 19.5 * s)]))


@_icon("stop")
def _stop(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawRoundedRect(QRectF(6 * s, 6 * s, 12 * s, 12 * s), 1.5 * s, 1.5 * s)


@_icon("candles")
def _candles(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.5 * s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(7 * s, 3.5 * s), QPointF(7 * s, 20.5 * s))
    p.drawRect(QRectF(4.5 * s, 7 * s, 5 * s, 9 * s))
    p.drawLine(QPointF(16.5 * s, 5 * s), QPointF(16.5 * s, 19 * s))
    p.setBrush(c)
    p.drawRect(QRectF(14 * s, 9 * s, 5 * s, 7 * s))


@_icon("ohlc-bars")
def _ohlc_bars(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.5 * s))
    for cx, top, bot, o, cl in ((7.5, 4.0, 17.0, 7.0, 13.0),
                                (16.5, 7.0, 20.0, 9.5, 17.0)):
        p.drawLine(QPointF(cx * s, top * s), QPointF(cx * s, bot * s))
        p.drawLine(QPointF((cx - 3.2) * s, o * s), QPointF(cx * s, o * s))
        p.drawLine(QPointF(cx * s, cl * s), QPointF((cx + 3.2) * s, cl * s))


@_icon("area-chart")
def _area_chart(p: QPainter, s: float, c: QColor) -> None:
    poly = QPolygonF([QPointF(3.5 * s, 19 * s), QPointF(3.5 * s, 14 * s),
                      QPointF(9 * s, 8.5 * s), QPointF(13.5 * s, 12.5 * s),
                      QPointF(20.5 * s, 5 * s), QPointF(20.5 * s, 19 * s)])
    fill = QColor(c); fill.setAlpha(70)
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(fill)
    p.drawPolygon(poly)
    p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(_pen(c, 1.6 * s))
    p.drawPolyline(QPolygonF([QPointF(3.5 * s, 14 * s), QPointF(9 * s, 8.5 * s),
                              QPointF(13.5 * s, 12.5 * s), QPointF(20.5 * s, 5 * s)]))


@_icon("line-chart")
def _line_chart(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.6 * s))
    p.drawPolyline(QPolygonF([QPointF(3.5 * s, 17 * s), QPointF(8.5 * s, 11 * s),
                              QPointF(12.5 * s, 14.5 * s), QPointF(20.5 * s, 5.5 * s)]))
    p.drawLine(QPointF(3.5 * s, 20.5 * s), QPointF(20.5 * s, 20.5 * s))


@_icon("strategy")
def _strategy(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.5 * s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(3 * s, 4 * s, 7 * s, 6 * s), 1.5 * s, 1.5 * s)
    p.drawRoundedRect(QRectF(14 * s, 4 * s, 7 * s, 6 * s), 1.5 * s, 1.5 * s)
    p.drawRoundedRect(QRectF(8.5 * s, 14.5 * s, 7 * s, 6 * s), 1.5 * s, 1.5 * s)
    p.drawLine(QPointF(6.5 * s, 10 * s), QPointF(11 * s, 14.5 * s))
    p.drawLine(QPointF(17.5 * s, 10 * s), QPointF(13 * s, 14.5 * s))


@_icon("optimize")
def _optimize(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.6 * s))
    for i, h in enumerate((6.0, 10.0, 4.0)):
        x = (5.5 + i * 6.5) * s
        p.drawLine(QPointF(x, 20 * s), QPointF(x, (20 - h) * s))
    p.setBrush(c)
    p.setPen(Qt.PenStyle.NoPen)
    for i, h in enumerate((6.0, 10.0, 4.0)):
        x = (5.5 + i * 6.5) * s
        p.drawEllipse(QPointF(x, (20 - h) * s), 2.0 * s, 2.0 * s)


@_icon("compare")
def _compare(p: QPainter, s: float, c: QColor) -> None:
    """Two bar groups side by side -- reads as 'A versus B' at 16px."""
    p.setPen(_pen(c, 1.4 * s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(4 * s, 11 * s, 5 * s, 9 * s))
    p.drawRect(QRectF(15 * s, 7 * s, 5 * s, 13 * s))
    p.setBrush(c)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRect(QRectF(4 * s, 15 * s, 5 * s, 5 * s))
    p.drawRect(QRectF(15 * s, 13 * s, 5 * s, 7 * s))
    p.setPen(_pen(c, 1.5 * s))
    p.drawLine(QPointF(11.2 * s, 5.5 * s), QPointF(12.8 * s, 5.5 * s))
    p.drawLine(QPointF(12 * s, 4.7 * s), QPointF(12 * s, 6.3 * s))
    p.drawLine(QPointF(11.2 * s, 8.5 * s), QPointF(12.8 * s, 8.5 * s))


@_icon("table")
def _table(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.5 * s))
    p.drawRoundedRect(QRectF(3.5 * s, 4.5 * s, 17 * s, 15 * s), 1.5 * s, 1.5 * s)
    p.drawLine(QPointF(3.5 * s, 9.5 * s), QPointF(20.5 * s, 9.5 * s))
    p.drawLine(QPointF(3.5 * s, 14.5 * s), QPointF(20.5 * s, 14.5 * s))
    p.drawLine(QPointF(12 * s, 4.5 * s), QPointF(12 * s, 19.5 * s))


@_icon("settings")
def _settings(p: QPainter, s: float, c: QColor) -> None:
    """A real gear: an outer disc with eight teeth, minus a central hole."""
    import math

    outer = QPainterPath()
    outer.addEllipse(QPointF(12 * s, 12 * s), 7.0 * s, 7.0 * s)
    for k in range(8):
        a_ = math.pi * k / 4.0
        tooth = QPainterPath()
        tooth.addRoundedRect(QRectF(-1.9 * s, -9.4 * s, 3.8 * s, 4.4 * s), 1.1 * s, 1.1 * s)
        m = tooth.toFillPolygon()
        rotated = QPolygonF([QPointF(12 * s + pt.x() * math.cos(a_) - pt.y() * math.sin(a_),
                                     12 * s + pt.x() * math.sin(a_) + pt.y() * math.cos(a_))
                             for pt in m])
        sub = QPainterPath()
        sub.addPolygon(rotated)
        outer = outer.united(sub)
    hole = QPainterPath()
    hole.addEllipse(QPointF(12 * s, 12 * s), 3.0 * s, 3.0 * s)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawPath(outer.subtracted(hole))


@_icon("trash")
def _trash(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.6 * s))
    p.drawLine(QPointF(4 * s, 6.5 * s), QPointF(20 * s, 6.5 * s))
    p.drawLine(QPointF(9.5 * s, 6.5 * s), QPointF(9.5 * s, 4 * s))
    p.drawLine(QPointF(9.5 * s, 4 * s), QPointF(14.5 * s, 4 * s))
    p.drawLine(QPointF(14.5 * s, 4 * s), QPointF(14.5 * s, 6.5 * s))
    p.drawPolyline(QPolygonF([QPointF(6 * s, 6.5 * s), QPointF(7.2 * s, 20 * s),
                              QPointF(16.8 * s, 20 * s), QPointF(18 * s, 6.5 * s)]))
    p.drawLine(QPointF(10.3 * s, 10 * s), QPointF(10.7 * s, 17 * s))
    p.drawLine(QPointF(13.7 * s, 10 * s), QPointF(13.3 * s, 17 * s))


@_icon("copy")
def _copy(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.5 * s))
    p.drawRoundedRect(QRectF(8 * s, 8 * s, 12 * s, 12 * s), 2 * s, 2 * s)
    path = QPainterPath()
    path.moveTo(15.5 * s, 4.5 * s)
    path.lineTo(5.5 * s, 4.5 * s)
    path.lineTo(5.5 * s, 15.5 * s)
    p.drawPath(path)


@_icon("rename")
def _rename(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.6 * s))
    p.drawLine(QPointF(4 * s, 20 * s), QPointF(20 * s, 20 * s))
    poly = QPolygonF([QPointF(4.5 * s, 15.5 * s), QPointF(15 * s, 5 * s),
                      QPointF(18 * s, 8 * s), QPointF(7.5 * s, 18.5 * s),
                      QPointF(4 * s, 19 * s)])
    p.drawPolygon(poly)


@_icon("plus")
def _plus(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.9 * s))
    p.drawLine(QPointF(12 * s, 5 * s), QPointF(12 * s, 19 * s))
    p.drawLine(QPointF(5 * s, 12 * s), QPointF(19 * s, 12 * s))


@_icon("minus")
def _minus(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.9 * s))
    p.drawLine(QPointF(5 * s, 12 * s), QPointF(19 * s, 12 * s))


@_icon("close")
def _close(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.8 * s))
    p.drawLine(QPointF(6 * s, 6 * s), QPointF(18 * s, 18 * s))
    p.drawLine(QPointF(18 * s, 6 * s), QPointF(6 * s, 18 * s))


@_icon("check")
def _check(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 2.0 * s))
    p.drawPolyline(QPolygonF([QPointF(5 * s, 12.5 * s), QPointF(10 * s, 17.5 * s),
                              QPointF(19 * s, 6.5 * s)]))


@_icon("refresh")
def _refresh(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.6 * s))
    rect = QRectF(4.5 * s, 4.5 * s, 15 * s, 15 * s)
    p.drawArc(rect, 60 * 16, 260 * 16)
    p.setBrush(c)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawPolygon(QPolygonF([QPointF(16.5 * s, 3 * s), QPointF(20.5 * s, 8 * s),
                             QPointF(14.5 * s, 8.5 * s)]))


@_icon("search")
def _search(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.7 * s))
    p.drawEllipse(QPointF(10.5 * s, 10.5 * s), 5.5 * s, 5.5 * s)
    p.drawLine(QPointF(14.6 * s, 14.6 * s), QPointF(20 * s, 20 * s))


@_icon("filter")
def _filter(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.6 * s))
    p.drawPolyline(QPolygonF([QPointF(4 * s, 5.5 * s), QPointF(20 * s, 5.5 * s),
                              QPointF(14 * s, 12.5 * s), QPointF(14 * s, 19.5 * s),
                              QPointF(10 * s, 17 * s), QPointF(10 * s, 12.5 * s),
                              QPointF(4 * s, 5.5 * s)]))


@_icon("info")
def _info(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.6 * s))
    p.drawEllipse(QPointF(12 * s, 12 * s), 8.2 * s, 8.2 * s)
    p.drawLine(QPointF(12 * s, 11 * s), QPointF(12 * s, 16.5 * s))
    p.setBrush(c)
    p.drawEllipse(QPointF(12 * s, 7.8 * s), 0.9 * s, 0.9 * s)


@_icon("warning")
def _warning(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.6 * s))
    p.drawPolygon(QPolygonF([QPointF(12 * s, 3.5 * s), QPointF(21.5 * s, 20 * s),
                             QPointF(2.5 * s, 20 * s)]))
    p.drawLine(QPointF(12 * s, 10 * s), QPointF(12 * s, 15 * s))
    p.setBrush(c)
    p.drawEllipse(QPointF(12 * s, 17.6 * s), 0.9 * s, 0.9 * s)


@_icon("database")
def _database(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.5 * s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QRectF(4 * s, 3.5 * s, 16 * s, 5 * s))
    p.drawLine(QPointF(4 * s, 6 * s), QPointF(4 * s, 18 * s))
    p.drawLine(QPointF(20 * s, 6 * s), QPointF(20 * s, 18 * s))
    p.drawArc(QRectF(4 * s, 15.5 * s, 16 * s, 5 * s), 180 * 16, 180 * 16)
    p.drawArc(QRectF(4 * s, 9.5 * s, 16 * s, 5 * s), 180 * 16, 180 * 16)


@_icon("report")
def _report(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.5 * s))
    path = QPainterPath()
    path.moveTo(6 * s, 3.5 * s); path.lineTo(14 * s, 3.5 * s)
    path.lineTo(18.5 * s, 8 * s); path.lineTo(18.5 * s, 20.5 * s)
    path.lineTo(6 * s, 20.5 * s); path.closeSubpath()
    p.drawPath(path)
    p.drawPolyline(QPolygonF([QPointF(14 * s, 3.5 * s), QPointF(14 * s, 8 * s),
                              QPointF(18.5 * s, 8 * s)]))
    p.drawLine(QPointF(9 * s, 17 * s), QPointF(9 * s, 12.5 * s))
    p.drawLine(QPointF(12.2 * s, 17 * s), QPointF(12.2 * s, 10.5 * s))
    p.drawLine(QPointF(15.4 * s, 17 * s), QPointF(15.4 * s, 14 * s))


@_icon("clock")
def _clock(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.6 * s))
    p.drawEllipse(QPointF(12 * s, 12 * s), 8.2 * s, 8.2 * s)
    p.drawLine(QPointF(12 * s, 7 * s), QPointF(12 * s, 12 * s))
    p.drawLine(QPointF(12 * s, 12 * s), QPointF(15.8 * s, 14 * s))


@_icon("calendar")
def _calendar(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.5 * s))
    p.drawRoundedRect(QRectF(3.5 * s, 5.5 * s, 17 * s, 15 * s), 2 * s, 2 * s)
    p.drawLine(QPointF(3.5 * s, 10 * s), QPointF(20.5 * s, 10 * s))
    p.drawLine(QPointF(8 * s, 3 * s), QPointF(8 * s, 7 * s))
    p.drawLine(QPointF(16 * s, 3 * s), QPointF(16 * s, 7 * s))


@_icon("layers")
def _layers(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.5 * s))
    p.drawPolygon(QPolygonF([QPointF(12 * s, 3.5 * s), QPointF(21 * s, 8.5 * s),
                             QPointF(12 * s, 13.5 * s), QPointF(3 * s, 8.5 * s)]))
    p.drawPolyline(QPolygonF([QPointF(3 * s, 13 * s), QPointF(12 * s, 18 * s),
                              QPointF(21 * s, 13 * s)]))
    p.drawPolyline(QPolygonF([QPointF(3 * s, 16.5 * s), QPointF(12 * s, 21.5 * s),
                              QPointF(21 * s, 16.5 * s)]))


@_icon("crosshair")
def _crosshair(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.5 * s))
    p.drawEllipse(QPointF(12 * s, 12 * s), 7 * s, 7 * s)
    p.drawLine(QPointF(12 * s, 2 * s), QPointF(12 * s, 7 * s))
    p.drawLine(QPointF(12 * s, 17 * s), QPointF(12 * s, 22 * s))
    p.drawLine(QPointF(2 * s, 12 * s), QPointF(7 * s, 12 * s))
    p.drawLine(QPointF(17 * s, 12 * s), QPointF(22 * s, 12 * s))


@_icon("zoom-in")
def _zoom_in(p: QPainter, s: float, c: QColor) -> None:
    _search(p, s, c)
    p.setPen(_pen(c, 1.6 * s))
    p.drawLine(QPointF(7.8 * s, 10.5 * s), QPointF(13.2 * s, 10.5 * s))
    p.drawLine(QPointF(10.5 * s, 7.8 * s), QPointF(10.5 * s, 13.2 * s))


@_icon("zoom-out")
def _zoom_out(p: QPainter, s: float, c: QColor) -> None:
    _search(p, s, c)
    p.setPen(_pen(c, 1.6 * s))
    p.drawLine(QPointF(7.8 * s, 10.5 * s), QPointF(13.2 * s, 10.5 * s))


@_icon("fit")
def _fit(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.7 * s))
    for (x, y, dx, dy) in ((4, 9, 0, -5), (4, 4, 5, 0), (20, 9, 0, -5), (20, 4, -5, 0),
                           (4, 15, 0, 5), (4, 20, 5, 0), (20, 15, 0, 5), (20, 20, -5, 0)):
        p.drawLine(QPointF(x * s, y * s), QPointF((x + dx) * s, (y + dy) * s))


@_icon("target")
def _target(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.5 * s))
    p.drawEllipse(QPointF(12 * s, 12 * s), 8.2 * s, 8.2 * s)
    p.drawEllipse(QPointF(12 * s, 12 * s), 4.4 * s, 4.4 * s)
    p.setBrush(c)
    p.drawEllipse(QPointF(12 * s, 12 * s), 1.4 * s, 1.4 * s)


@_icon("shield")
def _shield(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.5 * s))
    path = QPainterPath()
    path.moveTo(12 * s, 3 * s)
    path.lineTo(20 * s, 6.5 * s)
    path.lineTo(20 * s, 12 * s)
    path.quadTo(20 * s, 18.5 * s, 12 * s, 21.5 * s)
    path.quadTo(4 * s, 18.5 * s, 4 * s, 12 * s)
    path.lineTo(4 * s, 6.5 * s)
    path.closeSubpath()
    p.drawPath(path)


@_icon("chevron-down")
def _chevron_down(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.8 * s))
    p.drawPolyline(QPolygonF([QPointF(6.5 * s, 9.5 * s), QPointF(12 * s, 15 * s),
                              QPointF(17.5 * s, 9.5 * s)]))


@_icon("chevron-right")
def _chevron_right(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.8 * s))
    p.drawPolyline(QPolygonF([QPointF(9.5 * s, 6.5 * s), QPointF(15 * s, 12 * s),
                              QPointF(9.5 * s, 17.5 * s)]))


@_icon("arrow-up")
def _arrow_up(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.8 * s))
    p.drawLine(QPointF(12 * s, 19 * s), QPointF(12 * s, 5.5 * s))
    p.drawPolyline(QPolygonF([QPointF(6.5 * s, 11 * s), QPointF(12 * s, 5 * s),
                              QPointF(17.5 * s, 11 * s)]))


@_icon("arrow-down")
def _arrow_down(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.8 * s))
    p.drawLine(QPointF(12 * s, 5 * s), QPointF(12 * s, 18.5 * s))
    p.drawPolyline(QPolygonF([QPointF(6.5 * s, 13 * s), QPointF(12 * s, 19 * s),
                              QPointF(17.5 * s, 13 * s)]))


@_icon("indicator")
def _indicator(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.6 * s))
    p.drawPolyline(QPolygonF([QPointF(3 * s, 15 * s), QPointF(7 * s, 8 * s),
                              QPointF(11 * s, 16 * s), QPointF(15 * s, 6 * s),
                              QPointF(21 * s, 13 * s)]))
    dotted = _pen(c.darker(140), 1.2 * s)
    dotted.setStyle(Qt.PenStyle.DotLine)
    p.setPen(dotted)
    p.drawLine(QPointF(3 * s, 20 * s), QPointF(21 * s, 20 * s))


@_icon("grid")
def _grid(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.4 * s))
    for i in range(1, 3):
        p.drawLine(QPointF(4 * s, (4 + i * 16 / 3) * s), QPointF(20 * s, (4 + i * 16 / 3) * s))
        p.drawLine(QPointF((4 + i * 16 / 3) * s, 4 * s), QPointF((4 + i * 16 / 3) * s, 20 * s))
    p.drawRect(QRectF(4 * s, 4 * s, 16 * s, 16 * s))


@_icon("workspace")
def _workspace(p: QPainter, s: float, c: QColor) -> None:
    p.setPen(_pen(c, 1.5 * s))
    p.drawRoundedRect(QRectF(3 * s, 4 * s, 18 * s, 16 * s), 2 * s, 2 * s)
    p.drawLine(QPointF(3 * s, 9 * s), QPointF(21 * s, 9 * s))
    p.drawLine(QPointF(9 * s, 9 * s), QPointF(9 * s, 20 * s))


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def icon(name: str, size: int = 20, color: str | None = None) -> QIcon:
    """Return a cached :class:`QIcon` for ``name``.

    An unknown name returns an empty icon rather than raising -- a missing icon
    must never be the reason a window fails to open.
    """
    col = color or PALETTE.text_dim
    key = (name, size, col)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    drawer = _drawers.get(name)
    pm = QPixmap(QSize(size, size))
    pm.fill(Qt.GlobalColor.transparent)
    if drawer is not None:
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        try:
            drawer(painter, size / 24.0, QColor(col))
        finally:
            painter.end()
    ic = QIcon(pm)
    _cache[key] = ic
    return ic


def available_icons() -> list[str]:
    return sorted(_drawers)


def app_icon(size: int = 256) -> QIcon:
    """The application icon: a rising candle chart on a dark rounded tile."""
    pm = QPixmap(QSize(size, size))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    s = size / 256.0

    grad = QLinearGradient(0, 0, 0, size)
    grad.setColorAt(0.0, QColor("#18222f"))
    grad.setColorAt(1.0, QColor("#0b0f16"))
    p.setPen(QPen(QColor(PALETTE.border_strong), 4 * s))
    p.setBrush(grad)
    p.drawRoundedRect(QRectF(6 * s, 6 * s, 244 * s, 244 * s), 44 * s, 44 * s)

    # Three candles: down, up, up -- a small story rather than a generic glyph.
    def candle(cx: float, top: float, bottom: float, o: float, c_: float, up: bool) -> None:
        col = QColor(PALETTE.long if up else PALETTE.short)
        p.setPen(QPen(col, 6 * s, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(cx * s, top * s), QPointF(cx * s, bottom * s))
        p.setBrush(col)
        p.setPen(QPen(col, 4 * s))
        y0, y1 = min(o, c_), max(o, c_)
        p.drawRoundedRect(QRectF((cx - 19) * s, y0 * s, 38 * s, (y1 - y0) * s), 5 * s, 5 * s)

    candle(64, 92, 196, 112, 176, False)
    candle(128, 62, 178, 84, 150, True)
    candle(192, 44, 150, 66, 118, True)

    p.setPen(QPen(QColor(PALETTE.accent), 7 * s, Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawPolyline(QPolygonF([QPointF(46 * s, 168 * s), QPointF(110 * s, 128 * s),
                              QPointF(174 * s, 96 * s), QPointF(214 * s, 60 * s)]))
    p.end()
    return QIcon(pm)


def save_app_icon_ico(path: str) -> None:
    """Write a multi-resolution Windows .ico for the installer and the exe.

    Qt cannot write .ico, so the file is assembled by hand from PNG-compressed
    entries, which every version of Windows since Vista accepts.
    """
    import struct
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice

    sizes = (16, 24, 32, 48, 64, 128, 256)
    images: list[bytes] = []
    for sz in sizes:
        pm = app_icon(sz).pixmap(sz, sz)
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        pm.save(buf, "PNG")
        buf.close()
        images.append(bytes(ba))

    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries, blobs = b"", b""
    for sz, data in zip(sizes, images):
        w = 0 if sz >= 256 else sz
        entries += struct.pack("<BBBBHHII", w, w, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    with open(path, "wb") as fh:
        fh.write(header + entries + blobs)
