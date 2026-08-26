"""A printable PDF report, drawn with Qt's own painter.

The application already depends on Qt, and Qt already knows how to make a PDF,
so this module uses :class:`~PySide6.QtGui.QPdfWriter` and
:class:`~PySide6.QtGui.QPainter` and nothing else.  No reportlab, no
weasyprint, no headless browser: one fewer dependency to ship inside a Windows
installer, and one fewer thing that can fail on a machine that has never seen a
Python package index.

Everything is positioned by hand.  The layout keeps a single ``y`` cursor down
the page in device pixels; before each block is drawn it asks whether the block
still fits above the footer, and if it does not the page is finished and a new
one begun -- with the table's header row repeated, because a column of numbers
whose heading stayed on the previous page is a column of numbers nobody can
read.

The module works headless (``QT_QPA_PLATFORM=offscreen``) and does **not**
require the caller to have created a ``QApplication``: if no application object
exists one is created here and kept alive for the process, because Qt refuses to
measure a font without one.  When the desktop application is running, its
existing instance is used and nothing is created.
"""

from __future__ import annotations

import logging
import math
import os
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np
from PySide6.QtCore import QMarginsF, QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QPageLayout, QPageSize,
                           QPainter, QPainterPath, QPdfWriter, QPen)

from ..config import APP_DISPLAY_NAME, APP_VERSION
from ..core.errors import ReportError
from ..core.types import SignalExecution
from ..engine.results import BacktestResult
from ..ui.theme import PALETTE, Fonts, money as _money, pct as _pct
from .csv_export import describe_cost_model, iso_timestamps, run_header_fields
from .html_report import METRIC_GROUPS, ReportContext, decimate_indices

log = logging.getLogger(__name__)

#: The PDF is a summary, not an archive: the full blotter is the CSV export.
MAX_PDF_TRADES = 60

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

#: Applications created by this module are kept alive for the life of the
#: process; a ``QGuiApplication`` that is garbage collected takes Qt's font
#: machinery down with it and the next export segfaults.
_OWNED_APPLICATIONS: list[QGuiApplication] = []


# ==========================================================================
# Public entry point
# ==========================================================================

def export_pdf_report(result: BacktestResult, path: str | Path) -> str:
    """Render ``result`` to an A4 PDF at ``path``; returns the path written."""
    target = Path(path)
    ensure_application()
    ctx = ReportContext(result)

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ReportError(
            f"The report could not be written to {target}. Check that the folder "
            f"exists and that you have permission to write there.",
            detail=f"{type(exc).__name__}: {exc}") from exc

    writer = QPdfWriter(str(target))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageOrientation(QPageLayout.Orientation.Portrait)
    writer.setResolution(300)
    # Qt's own margins would clip drawing to the printable area, and the dark
    # ground has to reach the paper edge; the margin below is applied by the
    # canvas as a painter translation instead.
    writer.setPageMargins(QMarginsF(0.0, 0.0, 0.0, 0.0), QPageLayout.Unit.Millimeter)
    writer.setTitle(f"{result.strategy_name or 'Backtest'} — "
                    f"{result.instrument_symbol} {result.timeframe_label}".strip())
    writer.setCreator(f"{APP_DISPLAY_NAME} {APP_VERSION}")

    painter = QPainter()
    if not painter.begin(writer):
        raise ReportError(
            f"The PDF could not be created at {target}. The file may be open in "
            f"another application, or the folder may be read-only.",
            detail="QPainter.begin(QPdfWriter) returned False.")
    try:
        canvas = _Canvas(writer, painter, ctx)
        _title_block(canvas, ctx)
        _headline_block(canvas, ctx)
        _charts_block(canvas, ctx)
        _metrics_block(canvas, ctx)
        _monthly_block(canvas, ctx)
        _montecarlo_block(canvas, ctx)
        _trades_block(canvas, ctx)
        _assumptions_block(canvas, ctx)
        canvas.finish()
    finally:
        painter.end()

    log.info("Wrote PDF report to %s", target)
    return str(target)


def _needs_offscreen() -> bool:
    """True when constructing a Qt application here would abort the process.

    On Linux and the BSDs Qt's default platform plugin is X11 or Wayland, and
    with neither display available its failure is a ``qFatal`` -- the process
    aborts, and a library function that kills its caller is not one anybody can
    use from a script or a scheduled job. Windows and macOS always have a
    window system, so the question does not arise there.
    """
    if sys.platform.startswith(("win", "darwin")):
        return False
    if os.environ.get("QT_QPA_PLATFORM"):
        return False        # the caller has already chosen; respect it
    return not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def ensure_application() -> QGuiApplication:
    """Return the running Qt application, creating a minimal one if there is none.

    Font metrics, and therefore every text position in this report, are
    unavailable until a ``QGuiApplication`` exists.  Scripts and tests that only
    want a PDF should not have to know that, so this creates one on demand and
    keeps a reference to it -- including on a machine with no display at all,
    where it selects the offscreen platform first rather than aborting.
    """
    app = QGuiApplication.instance()
    if app is None:
        if _needs_offscreen():
            log.debug("No display; rendering the PDF on the offscreen platform")
            os.environ["QT_QPA_PLATFORM"] = "offscreen"
        app = QGuiApplication(sys.argv[:1] or [APP_DISPLAY_NAME])
        _OWNED_APPLICATIONS.append(app)
    Fonts.resolve()
    return app  # type: ignore[return-value]


# ==========================================================================
# The page canvas
# ==========================================================================

class _Canvas:
    """A one-column page with a ``y`` cursor, a footer and manual pagination."""

    def __init__(self, writer: QPdfWriter, painter: QPainter,
                 ctx: ReportContext) -> None:
        self.writer = writer
        self.painter = painter
        self.ctx = ctx
        viewport = painter.viewport()
        #: Device pixels per millimetre, so every size below reads in millimetres.
        self.px_per_mm = writer.resolution() / 25.4
        self.page_width = float(viewport.width())
        self.page_height = float(viewport.height())
        self.margin_x = self.mm(14.0)
        self.margin_y = self.mm(12.0)
        self.width = self.page_width - 2 * self.margin_x
        self.height = self.page_height - 2 * self.margin_y
        self.footer_band = self.mm(9.0)
        self.y = 0.0
        self.page = 1
        self._start_page()

    def _start_page(self) -> None:
        """Paint the dark ground over the whole sheet and move into the margins.

        The transform is re-applied from scratch on every page rather than
        trusted to survive ``newPage()``, so the layout does not depend on which
        Qt version decides to reset the painter.
        """
        self.painter.resetTransform()
        self.painter.fillRect(QRectF(0, 0, self.page_width, self.page_height),
                              QColor(PALETTE.app_bg))
        self.painter.translate(self.margin_x, self.margin_y)

    # -- geometry --------------------------------------------------------

    def mm(self, value: float) -> float:
        return float(value) * self.px_per_mm

    @property
    def bottom(self) -> float:
        """The lowest y a block may occupy before it must move to a new page."""
        return self.height - self.footer_band

    def fits(self, height: float) -> bool:
        return self.y + height <= self.bottom

    def ensure(self, height: float, repeat: Callable[[], None] | None = None) -> None:
        """Start a new page unless ``height`` device pixels remain.

        ``repeat`` redraws whatever must appear at the top of the continuation --
        in practice a table header.
        """
        if self.fits(height):
            return
        self.new_page()
        if repeat is not None:
            repeat()

    def new_page(self) -> None:
        self._draw_footer()
        self.painter.resetTransform()
        self.writer.newPage()
        self.page += 1
        self.y = 0.0
        self._start_page()

    def finish(self) -> None:
        """Footer for the final page.  Nothing may be drawn after this."""
        self._draw_footer()

    def space(self, millimetres: float) -> None:
        self.y += self.mm(millimetres)

    # -- primitives ------------------------------------------------------

    def font(self, size: float, bold: bool = False, mono: bool = False) -> QFont:
        f = Fonts.numeric(9, bold) if mono else Fonts.body(9, bold)
        f.setPointSizeF(float(size))
        return f

    def text(self, x: float, y: float, width: float, text: str, font: QFont,
             colour: str, align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft,
             height: float | None = None) -> float:
        """Draw one line and return the height it occupied."""
        self.painter.setFont(font)
        self.painter.setPen(QPen(QColor(colour)))
        line = height if height is not None else self.line_height(font)
        rect = QRectF(x, y, width, line)
        self.painter.drawText(rect, int(align | Qt.AlignmentFlag.AlignVCenter), text)
        return line

    def paragraph(self, text: str, font: QFont, colour: str,
                  indent: float = 0.0, space_after: float = 2.0) -> None:
        """Word-wrapped text that paginates by itself.

        A paragraph too long for the space left is split at a word boundary and
        continued on the next page rather than clipped: silently dropping the
        second half of a sentence about what a backtest cannot model would be a
        poor joke.
        """
        words = str(text).split()
        if not words:
            return
        self.painter.setFont(font)
        width = self.width - indent
        flags = int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft
                    | Qt.AlignmentFlag.AlignTop)
        line = self.line_height(font)

        def height_of(chunk: str) -> float:
            return self.painter.boundingRect(QRectF(0, 0, width, self.height * 4),
                                             flags, chunk).height()

        while words:
            if self.bottom - self.y < line * 2:
                self.new_page()
                self.painter.setFont(font)
            available = self.bottom - self.y
            best, low, high = 1, 1, len(words)
            while low <= high:  # largest prefix of the paragraph that still fits
                mid = (low + high) // 2
                if height_of(" ".join(words[:mid])) <= available:
                    best, low = mid, mid + 1
                else:
                    high = mid - 1
            chunk = " ".join(words[:best])
            drawn = min(height_of(chunk), available)
            self.painter.setPen(QPen(QColor(colour)))
            self.painter.drawText(QRectF(indent, self.y, width, drawn), flags, chunk)
            self.y += drawn
            words = words[best:]
            if words:
                self.new_page()
                self.painter.setFont(font)
        self.y += self.mm(space_after)

    def line_height(self, font: QFont) -> float:
        from PySide6.QtGui import QFontMetricsF

        return QFontMetricsF(font, self.painter.device()).height()

    def rule(self, colour: str | None = None, thickness_mm: float = 0.18,
             space_after: float = 1.6) -> None:
        pen = QPen(QColor(colour or PALETTE.border))
        pen.setWidthF(self.mm(thickness_mm))
        self.painter.setPen(pen)
        self.painter.drawLine(QPointF(0.0, self.y), QPointF(self.width, self.y))
        self.y += self.mm(space_after)

    def heading(self, title: str) -> None:
        font = self.font(12.5, bold=True)
        height = self.line_height(font)
        self.ensure(height + self.mm(16.0))
        self.text(0, self.y, self.width, title, font, PALETTE.text)
        self.y += height + self.mm(0.8)
        self.rule(PALETTE.border_strong, 0.25, 2.0)

    def subheading(self, title: str) -> None:
        font = self.font(8.5, bold=True)
        height = self.line_height(font)
        self.ensure(height + self.mm(8.0))
        self.text(0, self.y, self.width, title.upper(), font, PALETTE.text_dim)
        self.y += height + self.mm(0.6)

    def box(self, rect: QRectF, fill: str, border: str | None = None) -> None:
        self.painter.setPen(QPen(QColor(border or fill)))
        self.painter.setBrush(QColor(fill))
        self.painter.drawRect(rect)
        self.painter.setBrush(Qt.BrushStyle.NoBrush)

    # -- footer ----------------------------------------------------------

    def _draw_footer(self) -> None:
        y = self.height - self.mm(6.0)
        pen = QPen(QColor(PALETTE.border))
        pen.setWidthF(self.mm(0.15))
        self.painter.setPen(pen)
        top = y - self.mm(1.5)
        self.painter.drawLine(QPointF(0.0, top), QPointF(self.width, top))
        font = self.font(6.5)
        left = (f"{self.ctx.result.strategy_name or 'Backtest'} — "
                f"{self.ctx.result.instrument_symbol} {self.ctx.result.timeframe_label}")
        self.text(0, y, self.width * 0.75, left, font, PALETTE.text_muted)
        self.text(self.width * 0.75, y, self.width * 0.25, f"Page {self.page}",
                  font, PALETTE.text_muted, Qt.AlignmentFlag.AlignRight)


# ==========================================================================
# Blocks
# ==========================================================================

def _title_block(canvas: _Canvas, ctx: ReportContext) -> None:
    result = ctx.result
    title_font = canvas.font(19, bold=True)
    canvas.text(0, canvas.y, canvas.width,
                result.strategy_name or "Backtest report", title_font, PALETTE.text)
    canvas.y += canvas.line_height(title_font) + canvas.mm(0.4)

    sub_font = canvas.font(10)
    canvas.text(0, canvas.y, canvas.width,
                f"{result.instrument_symbol} {result.timeframe_label} — backtest report",
                sub_font, PALETTE.text_dim)
    canvas.y += canvas.line_height(sub_font) + canvas.mm(1.4)
    canvas.rule(PALETTE.border_strong, 0.3, 3.0)

    label_font = canvas.font(7.5)
    value_font = canvas.font(7.5, mono=True)
    row_h = canvas.line_height(value_font) * 1.15
    fields = run_header_fields(result)
    column_w = canvas.width / 2.0
    label_w = canvas.mm(24.0)
    half = (len(fields) + 1) // 2
    columns = (fields[:half], fields[half:])
    start_y = canvas.y
    lowest = start_y
    for index, column in enumerate(columns):
        y = start_y
        x = index * column_w
        for label, value in column:
            canvas.text(x, y, label_w, label, label_font, PALETTE.text_muted)
            canvas.text(x + label_w, y, column_w - label_w - canvas.mm(4.0),
                        _elide(canvas, value, value_font,
                               column_w - label_w - canvas.mm(4.0)),
                        value_font, PALETTE.text)
            y += row_h
        lowest = max(lowest, y)
    canvas.y = lowest + canvas.mm(3.0)


def _headline_block(canvas: _Canvas, ctx: ReportContext) -> None:
    cards = (("net_profit", "Net profit", "money", True),
             ("return_pct", "Return", "pct", True),
             ("max_drawdown_pct", "Max drawdown", "pct", True),
             ("profit_factor", "Profit factor", "ratio", True),
             ("total_trades", "Trades", "int", False),
             ("win_rate", "Win rate", "pct", False),
             ("sharpe_ratio", "Sharpe", "ratio", True),
             ("expectancy", "Expectancy", "money", True))
    gap = canvas.mm(2.0)
    card_w = (canvas.width - gap * 3) / 4.0
    card_h = canvas.mm(14.0)
    canvas.ensure(card_h * 2 + gap)
    label_font = canvas.font(6.5, bold=True)
    value_font = canvas.font(12, bold=True, mono=True)
    for i, (key, label, kind, signed) in enumerate(cards):
        row, col = divmod(i, 4)
        x = col * (card_w + gap)
        y = canvas.y + row * (card_h + gap)
        canvas.box(QRectF(x, y, card_w, card_h), PALETTE.panel_alt, PALETTE.border)
        value = ctx.metrics.get(key)
        state = ctx.reliability.get(key, "ok")
        suffix = "  LOW n" if state == "low_sample" else "  N/A" if state == "unavailable" else ""
        canvas.text(x + canvas.mm(2.0), y + canvas.mm(1.4), card_w - canvas.mm(4.0),
                    label.upper() + suffix, label_font, PALETTE.text_muted)
        canvas.text(x + canvas.mm(2.0), y + canvas.mm(6.6), card_w - canvas.mm(4.0),
                    ctx.fmt(value, kind), value_font,
                    ctx.colour_for(key, kind, value, signed))
    canvas.y += card_h * 2 + gap + canvas.mm(4.0)

    warnings = list(ctx.result.warnings or ())
    n = int(ctx.metrics.get("total_trades", 0) or 0)
    if n == 0:
        warnings.insert(0, "This run produced no trades.")
    elif n < 30:
        warnings.insert(0, f"Only {n} trades: every ratio in this report is dominated "
                           f"by noise at that sample size.")
    if warnings:
        canvas.paragraph("Warnings: " + "  •  ".join(str(w) for w in warnings),
                         canvas.font(7.5), PALETTE.warning, space_after=3.0)


def _charts_block(canvas: _Canvas, ctx: ReportContext) -> None:
    if len(ctx.equity) == 0:
        return
    canvas.heading("Equity and drawdown")
    equity_h = canvas.mm(62.0)
    dd_h = canvas.mm(34.0)
    canvas.ensure(equity_h + dd_h + canvas.mm(14.0))

    rect = QRectF(0, canvas.y, canvas.width, equity_h)
    _draw_equity_chart(canvas, ctx, rect)
    canvas.y += equity_h + canvas.mm(2.0)

    rect = QRectF(0, canvas.y, canvas.width, dd_h)
    _draw_drawdown_chart(canvas, ctx, rect)
    canvas.y += dd_h + canvas.mm(2.0)

    canvas.paragraph(
        "The shaded band on the equity chart is the distance below the previous "
        "equity peak; the panel beneath it shows the same thing as a percentage. "
        "Time spent under water is what a live trader actually experiences.",
        canvas.font(7.5), PALETTE.text_dim, space_after=4.0)


def _metrics_block(canvas: _Canvas, ctx: ReportContext) -> None:
    canvas.heading("Performance statistics")
    label_font = canvas.font(7.5)
    value_font = canvas.font(7.5, mono=True)
    row_h = canvas.line_height(value_font) * 1.25
    half = canvas.width / 2.0
    value_w = canvas.mm(30.0)

    for title, entries in METRIC_GROUPS:
        drawn = {"any": False}

        def header(title: str = title, drawn: dict = drawn) -> None:
            canvas.subheading(title + (" (continued)" if drawn["any"] else ""))
            drawn["any"] = True

        canvas.ensure(row_h * 2 + canvas.mm(6.0))
        header()
        pairs = [entries[i:i + 2] for i in range(0, len(entries), 2)]
        for pair in pairs:
            canvas.ensure(row_h, header)
            for column, entry in enumerate(pair):
                key, label, kind, signed, _explain = entry
                x = column * half
                value = ctx.metrics.get(key)
                state = ctx.reliability.get(key, "ok")
                text = ctx.fmt(value, kind)
                if state == "low_sample":
                    text += "  (low n)"
                colour = ctx.colour_for(key, kind, value, signed)
                if state == "unavailable":
                    colour = PALETTE.text_muted
                canvas.text(x, canvas.y, half - value_w - canvas.mm(3.0), label,
                            label_font, PALETTE.text_dim)
                canvas.text(x + half - value_w - canvas.mm(3.0), canvas.y, value_w,
                            text, value_font, colour, Qt.AlignmentFlag.AlignRight)
            canvas.y += row_h
        canvas.space(2.0)
    canvas.space(2.0)


def _monthly_block(canvas: _Canvas, ctx: ReportContext) -> None:
    if not ctx.monthly:
        return
    canvas.heading("Returns by month")
    years = sorted({y for y, _m in ctx.monthly})
    weights = [1.4] + [1.0] * 12 + [1.4]
    xs, widths = _columns(canvas.width, weights)
    head_font = canvas.font(6.8, bold=True)
    cell_font = canvas.font(6.8, mono=True)
    row_h = canvas.line_height(cell_font) * 1.35

    def header() -> None:
        titles = ["Year"] + list(_MONTHS) + ["Year %"]
        canvas.box(QRectF(0, canvas.y, canvas.width, row_h), PALETTE.elevated,
                   PALETTE.border)
        for i, title in enumerate(titles):
            align = (Qt.AlignmentFlag.AlignLeft if i == 0
                     else Qt.AlignmentFlag.AlignRight)
            canvas.text(xs[i] + canvas.mm(0.6), canvas.y, widths[i] - canvas.mm(1.2),
                        title, head_font, PALETTE.text_dim, align, row_h)
        canvas.y += row_h

    canvas.ensure(row_h * 3)
    header()
    for year in years:
        canvas.ensure(row_h, header)
        canvas.text(xs[0] + canvas.mm(0.6), canvas.y, widths[0], str(year),
                    cell_font, PALETTE.text, Qt.AlignmentFlag.AlignLeft, row_h)
        for month in range(1, 13):
            value = ctx.monthly.get((year, month))
            text = "-" if value is None or value != value else _pct(value, 1, signed=True)
            colour = PALETTE.text_muted if value is None or value != value \
                else _sign_colour(value)
            canvas.text(xs[month], canvas.y, widths[month] - canvas.mm(1.0), text,
                        cell_font, colour, Qt.AlignmentFlag.AlignRight, row_h)
        total = ctx.yearly.get(year, {}).get("return_pct")
        text = "-" if total is None or total != total else _pct(total, 1, signed=True)
        canvas.text(xs[13], canvas.y, widths[13] - canvas.mm(1.0), text,
                    canvas.font(6.8, bold=True, mono=True),
                    PALETTE.text_muted if total is None or total != total
                    else _sign_colour(total), Qt.AlignmentFlag.AlignRight, row_h)
        canvas.y += row_h
        _row_rule(canvas)
    canvas.space(3.0)


def _montecarlo_block(canvas: _Canvas, ctx: ReportContext) -> None:
    """The same resampling the HTML report carries, as a printed table.

    The PDF keeps its own explicit block list rather than sharing the HTML's
    sections, so a section added there does not appear here -- which is exactly
    what happened when this one was added. Both reports are the artefact that
    gets shared, and a single equity curve shared on its own reads as the
    outcome rather than as one draw from a distribution.

    Never fatal, for the same reason as in the HTML report: a resampling that
    fails should cost this block, not the whole document.
    """
    if len(ctx.trades) < 2:
        return
    try:
        from ..analytics.montecarlo import resample_result
        from .html_report import _REPORT_DRAWS

        mc = resample_result(ctx.result, method="block", draws=_REPORT_DRAWS)
    except Exception:                       # noqa: BLE001 - see the docstring
        log.debug("Monte Carlo block skipped", exc_info=True)
        return

    canvas.heading("What else could have happened")
    canvas.paragraph(
        f"{_REPORT_DRAWS:,} resampled runs over these {len(ctx.trades):,} "
        f"trades, drawn in contiguous blocks of {mc.block_size} so that losing "
        f"streaks survive the resampling. This describes the range of paths "
        f"these trades could have produced. It cannot tell you whether the "
        f"strategy has an edge: if these trades came from a rule fitted to "
        f"this data, every draw is fitted to it too.",
        canvas.font(8), PALETTE.text_dim, space_after=3.0)

    quantiles = (5, 25, 50, 75, 95)
    rows = (
        ("Final equity", mc.percentiles(mc.final_equity, quantiles), ctx.money),
        ("Worst drawdown", mc.percentiles(mc.max_drawdown, quantiles), ctx.money),
        ("Worst drawdown %", mc.percentiles(mc.max_drawdown_pct, quantiles),
         lambda v: _pct(v, 1)),
        ("Trades under water",
         mc.percentiles(mc.longest_drawdown.astype(float), quantiles),
         lambda v: f"{v:,.0f}"),
    )
    xs, widths = _columns(canvas.width, [2.0] + [1.0] * len(quantiles))
    head_font = canvas.font(7.4, bold=True)
    cell_font = canvas.font(7.4, mono=True)
    label_font = canvas.font(7.4)
    row_h = canvas.line_height(cell_font) * 1.45

    def header() -> None:
        canvas.box(QRectF(0, canvas.y, canvas.width, row_h), PALETTE.elevated,
                   PALETTE.border)
        canvas.text(xs[0] + canvas.mm(0.6), canvas.y, widths[0], "Percentile",
                    head_font, PALETTE.text_dim, Qt.AlignmentFlag.AlignLeft,
                    row_h)
        for index, q in enumerate(quantiles, start=1):
            canvas.text(xs[index], canvas.y, widths[index] - canvas.mm(1.0),
                        f"{q}th", head_font, PALETTE.text_dim,
                        Qt.AlignmentFlag.AlignRight, row_h)
        canvas.y += row_h

    canvas.ensure(row_h * (len(rows) + 2))
    header()
    for label, values, render in rows:
        canvas.ensure(row_h, header)
        canvas.text(xs[0] + canvas.mm(0.6), canvas.y, widths[0], label,
                    label_font, PALETTE.text, Qt.AlignmentFlag.AlignLeft, row_h)
        for index, q in enumerate(quantiles, start=1):
            canvas.text(xs[index], canvas.y, widths[index] - canvas.mm(1.0),
                        render(values[q]), cell_font, PALETTE.text,
                        Qt.AlignmentFlag.AlignRight, row_h)
        canvas.y += row_h
        _row_rule(canvas)

    canvas.space(2.0)
    worst = mc.drawdown_at(95)
    canvas.paragraph(
        f"This backtest finished at {ctx.money(mc.observed.final_equity)} with "
        f"a worst drawdown of {ctx.money(mc.observed.max_drawdown)} "
        f"({_pct(mc.observed.max_drawdown_pct, 1)}). "
        f"{mc.losing_probability * 100:.1f}% of resampled runs lost money and "
        f"{mc.ruin_probability * 100:.1f}% closed below "
        f"{ctx.money(mc.ruin_level)} at some point. One run in twenty had a "
        f"drawdown worse than {ctx.money(worst)} — that is the number to size "
        f"an account against, not the "
        f"{ctx.money(mc.observed.max_drawdown)} this backtest happened to "
        f"produce.",
        canvas.font(8), PALETTE.text_dim, space_after=3.0)


def _trades_block(canvas: _Canvas, ctx: ReportContext) -> None:
    if not ctx.trades:
        canvas.heading("Trades")
        canvas.paragraph("This run closed no trades.", canvas.font(8),
                         PALETTE.text_muted)
        return
    canvas.heading("Trades")
    shown = ctx.trades[:MAX_PDF_TRADES]
    _utc, local_entry = iso_timestamps([t.entry_ts for t in shown], ctx.timezone)
    _utc2, local_exit = iso_timestamps([t.exit_ts for t in shown], ctx.timezone)
    del _utc, _utc2

    titles = ("#", "Entry", "Exit", "Side", "Qty", "Entry px", "Exit px",
              "Net P&L", "Return", "R", "Bars", "Exit reason")
    weights = (0.5, 2.1, 2.1, 0.7, 0.7, 1.2, 1.2, 1.4, 1.0, 0.7, 0.6, 1.7)
    aligns = (Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignLeft,
              Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignLeft,
              Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignRight,
              Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignRight,
              Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignRight,
              Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignLeft)
    xs, widths = _columns(canvas.width, weights)
    head_font = canvas.font(6.6, bold=True)
    cell_font = canvas.font(6.6, mono=True)
    row_h = canvas.line_height(cell_font) * 1.3

    def header() -> None:
        canvas.box(QRectF(0, canvas.y, canvas.width, row_h), PALETTE.elevated,
                   PALETTE.border)
        for i, title in enumerate(titles):
            canvas.text(xs[i] + canvas.mm(0.6), canvas.y, widths[i] - canvas.mm(1.2),
                        title, head_font, PALETTE.text_dim, aligns[i], row_h)
        canvas.y += row_h

    canvas.ensure(row_h * 3)
    header()
    d = ctx.decimals
    for i, trade in enumerate(shown):
        canvas.ensure(row_h, header)
        r = ("-" if trade.r_multiple is None or trade.r_multiple != trade.r_multiple
             else f"{float(trade.r_multiple):+.2f}")
        cells = (str(i + 1),
                 local_entry[i][:16].replace("T", " "),
                 local_exit[i][:16].replace("T", " "),
                 trade.side.value.upper(),
                 _qty(trade.quantity),
                 f"{trade.entry_price:,.{d}f}",
                 f"{trade.exit_price:,.{d}f}",
                 _money(trade.net_pnl, ctx.currency),
                 _pct(trade.return_pct, 2, signed=True),
                 r,
                 f"{int(trade.bars_held):,}",
                 trade.exit_reason.label)
        colours = (PALETTE.text_muted, PALETTE.text, PALETTE.text,
                   PALETTE.long if trade.side.value == "long" else PALETTE.short,
                   PALETTE.text, PALETTE.text, PALETTE.text,
                   _sign_colour(trade.net_pnl), _sign_colour(trade.return_pct),
                   PALETTE.text, PALETTE.text_muted, PALETTE.text_dim)
        for c, text in enumerate(cells):
            canvas.text(xs[c] + canvas.mm(0.6), canvas.y, widths[c] - canvas.mm(1.2),
                        text, cell_font, colours[c], aligns[c], row_h)
        canvas.y += row_h
        _row_rule(canvas)
    canvas.space(1.5)
    if len(ctx.trades) > MAX_PDF_TRADES:
        canvas.paragraph(
            f"Showing the first {MAX_PDF_TRADES} of {len(ctx.trades):,} trades. "
            f"Export the trades to CSV for the complete list.",
            canvas.font(7.5), PALETTE.warning, space_after=3.0)


def _assumptions_block(canvas: _Canvas, ctx: ReportContext) -> None:
    cfg = ctx.result.config
    canvas.heading("How this was simulated")
    body = canvas.font(7.8)

    timing = ("A rule was evaluated on the close of a bar and the order filled at the "
              "open of the next bar."
              if cfg.execution.signal_execution is SignalExecution.NEXT_OPEN else
              "Orders filled at the close of the same bar that produced the signal. "
              "That price was not knowable when the decision was made, so every "
              "figure in this report is an upper bound.")
    priority = {
        "pessimistic": "the stop was assumed to come first",
        "optimistic": "the target was assumed to come first",
        "ohlc_path": "an assumed open-high-low-close path decided which came first",
    }[cfg.execution.intrabar_priority.value]

    paragraphs = (
        f"Order timing. {timing}",
        f"Intrabar barriers. When a single bar's range covered both the stop and the "
        f"target, {priority}. Bar data cannot say which price came first; this is an "
        f"assumption, not a measurement.",
        "Gaps. If a bar opened beyond a resting stop or target, the fill was taken at "
        "that opening price and not at the barrier price. A stop does not protect you "
        "from a gap and this simulation does not pretend otherwise.",
        f"Costs. {_sentence(describe_cost_model(cfg.costs))}. Every one of these is "
        f"charged against the trade.",
        "What no backtest can model: your position in the order queue, partial fills, "
        "latency, how much size the book would really have absorbed, the impact of "
        "your own order on the price, and whether the instrument could have been "
        "shorted at that moment. Nor can it model the person who chose this "
        "configuration after seeing the data. If this is the best of many variants "
        "tried, the number that matters is how many were tried.",
    )
    for text in paragraphs:
        canvas.paragraph(text, body, PALETTE.text_dim, space_after=2.2)


# ==========================================================================
# Charts
# ==========================================================================

def _draw_equity_chart(canvas: _Canvas, ctx: ReportContext, rect: QRectF) -> None:
    painter = canvas.painter
    canvas.box(rect, PALETTE.panel_alt, PALETTE.border)
    gutter = canvas.mm(20.0)
    plot = QRectF(rect.left() + gutter, rect.top() + canvas.mm(2.0),
                  rect.width() - gutter - canvas.mm(3.0),
                  rect.height() - canvas.mm(9.0))

    equity = ctx.equity
    balance = ctx.balance
    peak = ctx.peak
    n = len(equity)
    start = float(ctx.result.config.starting_capital)
    lo = float(np.nanmin(np.minimum(equity, balance)))
    hi = float(np.nanmax(peak))
    lo, hi = _pad(min(lo, start), max(hi, start))
    idx = decimate_indices(equity, 4000)

    def sx(i: int) -> float:
        return plot.left() + plot.width() * (i / max(1, n - 1))

    def sy(v: float) -> float:
        return plot.top() + plot.height() * (hi - float(v)) / (hi - lo)

    _grid(canvas, plot, [(sy(v), _money(v, ctx.currency, 0))
                         for v in _ticks(lo, hi, 5)])

    band = QPainterPath()
    band.moveTo(sx(idx[0]), sy(peak[idx[0]]))
    for i in idx[1:]:
        band.lineTo(sx(i), sy(peak[i]))
    for i in reversed(idx):
        band.lineTo(sx(i), sy(equity[i]))
    band.closeSubpath()
    painter.setPen(Qt.PenStyle.NoPen)
    # Translucent rather than the flat fill colour: on a losing run the band
    # covers most of the plot and an opaque block would bury the grid under it.
    painter.setBrush(PALETTE.qcolor("drawdown", 55))
    painter.drawPath(band)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    pen = QPen(QColor(PALETTE.border_strong))
    pen.setWidthF(canvas.mm(0.15))
    pen.setStyle(Qt.PenStyle.DashLine)
    painter.setPen(pen)
    painter.drawLine(QPointF(plot.left(), sy(start)),
                     QPointF(plot.right(), sy(start)))

    _stroke(painter, [(sx(i), sy(balance[i])) for i in idx], PALETTE.balance,
            canvas.mm(0.12), Qt.PenStyle.DotLine)
    _stroke(painter, [(sx(i), sy(equity[i])) for i in idx], PALETTE.equity,
            canvas.mm(0.28))
    _time_axis(canvas, ctx, plot, n)


def _draw_drawdown_chart(canvas: _Canvas, ctx: ReportContext, rect: QRectF) -> None:
    painter = canvas.painter
    canvas.box(rect, PALETTE.panel_alt, PALETTE.border)
    gutter = canvas.mm(20.0)
    plot = QRectF(rect.left() + gutter, rect.top() + canvas.mm(2.0),
                  rect.width() - gutter - canvas.mm(3.0),
                  rect.height() - canvas.mm(9.0))
    under = ctx.underwater
    n = len(under)
    lo = min(float(np.nanmin(under)) if n else 0.0, -0.5) * 1.08
    hi = 0.0
    idx = decimate_indices(under, 4000)

    def sx(i: int) -> float:
        return plot.left() + plot.width() * (i / max(1, n - 1))

    def sy(v: float) -> float:
        return plot.top() + plot.height() * (hi - float(v)) / (hi - lo)

    _grid(canvas, plot, [(sy(v), _pct(v, 1)) for v in _ticks(lo, hi, 3)])

    area = QPainterPath()
    area.moveTo(sx(idx[0]), sy(0.0))
    for i in idx:
        area.lineTo(sx(i), sy(under[i]))
    area.lineTo(sx(idx[-1]), sy(0.0))
    area.closeSubpath()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(PALETTE.qcolor("drawdown", 90))
    painter.drawPath(area)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    _stroke(painter, [(sx(i), sy(under[i])) for i in idx], PALETTE.drawdown,
            canvas.mm(0.2))
    _time_axis(canvas, ctx, plot, n)


def _grid(canvas: _Canvas, plot: QRectF, ticks: Sequence[tuple[float, str]]) -> None:
    pen = QPen(QColor(PALETTE.grid))
    pen.setWidthF(canvas.mm(0.1))
    font = canvas.font(6.0, mono=True)
    for y, label in ticks:
        canvas.painter.setPen(pen)
        canvas.painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
        canvas.text(plot.left() - canvas.mm(19.0), y - canvas.mm(1.5),
                    canvas.mm(18.0), label, font, PALETTE.axis_text,
                    Qt.AlignmentFlag.AlignRight, canvas.mm(3.0))


def _time_axis(canvas: _Canvas, ctx: ReportContext, plot: QRectF, n: int) -> None:
    import pandas as pd

    if n == 0 or len(ctx.ts) == 0:
        return
    pen = QPen(QColor(PALETTE.border_strong))
    pen.setWidthF(canvas.mm(0.12))
    canvas.painter.setPen(pen)
    canvas.painter.drawLine(QPointF(plot.left(), plot.bottom()),
                            QPointF(plot.right(), plot.bottom()))
    span_days = (int(ctx.ts[-1]) - int(ctx.ts[0])) / 86_400e9
    fmt = "%Y-%m-%d" if span_days > 5 else "%m-%d %H:%M"
    font = canvas.font(6.0, mono=True)
    for k in range(5):
        i = int(round((n - 1) * k / 4))
        stamp = pd.Timestamp(int(ctx.ts[min(i, len(ctx.ts) - 1)]), tz="UTC")
        try:
            stamp = stamp.tz_convert(ctx.timezone)
        except Exception:
            pass
        x = plot.left() + plot.width() * (i / max(1, n - 1))
        width = canvas.mm(24.0)
        align = (Qt.AlignmentFlag.AlignLeft if k == 0 else
                 Qt.AlignmentFlag.AlignRight if k == 4 else
                 Qt.AlignmentFlag.AlignHCenter)
        left = (x if k == 0 else x - width if k == 4 else x - width / 2.0)
        canvas.text(left, plot.bottom() + canvas.mm(0.8), width,
                    stamp.strftime(fmt), font, PALETTE.axis_text, align,
                    canvas.mm(3.5))


def _stroke(painter: QPainter, points: Sequence[tuple[float, float]], colour: str,
            width: float, style: Qt.PenStyle = Qt.PenStyle.SolidLine) -> None:
    if len(points) < 2:
        return
    path = QPainterPath()
    path.moveTo(*points[0])
    for x, y in points[1:]:
        path.lineTo(x, y)
    pen = QPen(QColor(colour))
    pen.setWidthF(width)
    pen.setStyle(style)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)


# ==========================================================================
# Small helpers
# ==========================================================================

def _columns(width: float, weights: Sequence[float]) -> tuple[list[float], list[float]]:
    """Column left edges and widths for a table, from relative weights."""
    total = float(sum(weights))
    widths = [width * (w / total) for w in weights]
    xs: list[float] = []
    x = 0.0
    for w in widths:
        xs.append(x)
        x += w
    return xs, widths


def _row_rule(canvas: _Canvas) -> None:
    pen = QPen(QColor(PALETTE.grid))
    pen.setWidthF(canvas.mm(0.08))
    canvas.painter.setPen(pen)
    canvas.painter.drawLine(QPointF(0.0, canvas.y), QPointF(canvas.width, canvas.y))


def _elide(canvas: _Canvas, text: str, font: QFont, width: float) -> str:
    """Shorten a value so a long cost-model description cannot run off the page."""
    from PySide6.QtGui import QFontMetricsF

    metrics = QFontMetricsF(font, canvas.painter.device())
    return metrics.elidedText(str(text), Qt.TextElideMode.ElideRight, width)


def _pad(lo: float, hi: float) -> tuple[float, float]:
    if not math.isfinite(lo) or not math.isfinite(hi):
        return 0.0, 1.0
    if hi - lo < 1e-9:
        pad = max(1.0, abs(hi) * 0.01)
        return lo - pad, hi + pad
    pad = (hi - lo) * 0.06
    return lo - pad, hi + pad


def _ticks(lo: float, hi: float, count: int) -> list[float]:
    if not math.isfinite(lo) or not math.isfinite(hi) or hi <= lo:
        return [lo]
    return [lo + (hi - lo) * k / count for k in range(count + 1)]


def _sentence(text: str) -> str:
    """Capitalise a fragment so it can open a sentence."""
    text = str(text)
    return text[:1].upper() + text[1:] if text else text


def _qty(value: float) -> str:
    v = float(value)
    return f"{v:,.0f}" if abs(v - round(v)) < 1e-9 else f"{v:,.4f}".rstrip("0")


def _sign_colour(value: Any) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return PALETTE.text
    if v != v:
        return PALETTE.text_muted
    return PALETTE.long if v > 0 else PALETTE.short if v < 0 else PALETTE.text_dim


__all__ = ["export_pdf_report", "ensure_application", "MAX_PDF_TRADES"]
