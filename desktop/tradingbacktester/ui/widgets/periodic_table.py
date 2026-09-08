"""Monthly and yearly return tables, coloured as a heat map.

Reads the structures produced by :mod:`tradingbacktester.analytics.periodic`.
The colour scale is symmetric around zero and normalised to the largest
magnitude in the grid, so a good month in a quiet strategy is not painted the
same shade as a good month in a volatile one.
"""

from __future__ import annotations

from typing import Any, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QHeaderView, QLabel,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from ..theme import PALETTE, Fonts, pct

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _heat(value: float, scale: float) -> QColor:
    """Blend towards the long or short colour in proportion to ``value``."""
    if value != value or scale <= 0:
        return QColor(PALETTE.panel_bg)
    frac = max(-1.0, min(1.0, value / scale))
    base = QColor(PALETTE.panel_bg)
    target = QColor(PALETTE.long if frac >= 0 else PALETTE.short)
    weight = abs(frac) * 0.72
    return QColor(
        int(base.red() + (target.red() - base.red()) * weight),
        int(base.green() + (target.green() - base.green()) * weight),
        int(base.blue() + (target.blue() - base.blue()) * weight),
    )


class PeriodicReturnsTable(QWidget):
    """Years down the side, months across, with a total column."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)

        self.caption = QLabel(
            "Returns are computed from the equity curve at each period boundary, "
            "in UTC, and include open-position mark-to-market.")
        self.caption.setWordWrap(True)
        self.caption.setObjectName("Hint")
        self.caption.setFont(Fonts.body(8))
        lay.addWidget(self.caption)

        self.table = QTableWidget(0, len(MONTHS) + 1)
        self.table.setHorizontalHeaderLabels([*MONTHS, "Year"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setShowGrid(False)
        self.table.setFont(Fonts.numeric(8))
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.verticalHeader().setStyleSheet(
            f"QHeaderView::section {{ background:{PALETTE.elevated}; "
            f"color:{PALETTE.text_dim}; border:0; padding:0 8px; }}")
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # The year total is wider than a month and must not elide.
        header.setSectionResizeMode(12, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(12, 78)
        header.setMinimumSectionSize(46)
        header.setHighlightSections(False)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        lay.addWidget(self.table, 1)

        self.summary = QLabel("")
        self.summary.setFont(Fonts.numeric(9))
        lay.addWidget(self.summary)

    # -- data ------------------------------------------------------------

    def set_data(self, monthly: dict[str, Any] | None) -> None:
        """``monthly`` is the dict returned by ``analytics.periodic.monthly_returns``.

        Expected shape::

            {"years": [2023, 2024],
             "months": [[jan, feb, ...], [...]],   # percentages, None for no data
             "totals": {2023: 12.4, 2024: -3.1}}
        """
        self.table.clearContents()
        if not monthly or not monthly.get("years"):
            self.table.setRowCount(0)
            self.summary.setText(
                f"<span style='color:{PALETTE.text_muted}'>"
                f"Not enough data to break the results down by month.</span>")
            return

        years: Sequence[Any] = monthly["years"]
        grid: Sequence[Sequence[Any]] = monthly.get("months", [])
        totals: dict[Any, Any] = monthly.get("totals", {})

        values = [v for row in grid for v in row
                  if isinstance(v, (int, float)) and v == v]
        scale = max((abs(v) for v in values), default=1.0) or 1.0

        self.table.setRowCount(len(years))
        self.table.setVerticalHeaderLabels([str(y) for y in years])
        for r, year in enumerate(years):
            row = list(grid[r]) if r < len(grid) else [None] * 12
            for c in range(12):
                v = row[c] if c < len(row) else None
                item = QTableWidgetItem("" if v is None or v != v else pct(v, 1, True))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if v is not None and v == v:
                    item.setBackground(QBrush(_heat(float(v), scale)))
                    item.setForeground(QBrush(QColor(PALETTE.text)))
                    item.setToolTip(f"{MONTHS[c]} {year}: {pct(v, 2, True)}")
                else:
                    item.setForeground(QBrush(QColor(PALETTE.text_muted)))
                self.table.setItem(r, c, item)

            total = totals.get(year, totals.get(str(year)))
            titem = QTableWidgetItem("" if total is None else pct(total, 2, True))
            titem.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if total is not None and total == total:
                colour = PALETTE.long if total > 0 else PALETTE.short if total < 0 \
                    else PALETTE.text_dim
                titem.setForeground(QBrush(QColor(colour)))
                titem.setFont(Fonts.numeric(9, bold=True))
                titem.setBackground(QBrush(QColor(PALETTE.elevated)))
            self.table.setItem(r, 12, titem)

        positives = sum(1 for v in values if v > 0)
        best = max(values, default=float("nan"))
        worst = min(values, default=float("nan"))
        self.summary.setText(
            f"<span style='color:{PALETTE.text_dim}'>months</span> "
            f"<span style='color:{PALETTE.text}'>{len(values)}</span>   "
            f"<span style='color:{PALETTE.text_dim}'>positive</span> "
            f"<span style='color:{PALETTE.text}'>"
            f"{positives / len(values) * 100 if values else 0:.0f}%</span>   "
            f"<span style='color:{PALETTE.text_dim}'>best</span> "
            f"<span style='color:{PALETTE.long}'>{pct(best, 2, True)}</span>   "
            f"<span style='color:{PALETTE.text_dim}'>worst</span> "
            f"<span style='color:{PALETTE.short}'>{pct(worst, 2, True)}</span>")

    def clear(self) -> None:
        self.set_data(None)


class DrawdownTable(QWidget):
    """The worst drawdowns, deepest first."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)
        caption = QLabel(
            "Each excursion below the previous equity peak. Recovery is the "
            "number of bars from the trough back to that peak; a drawdown that "
            "never recovered is marked open.")
        caption.setWordWrap(True)
        caption.setObjectName("Hint")
        caption.setFont(Fonts.body(8))
        lay.addWidget(caption)

        cols = ("#", "Start", "Trough", "End", "Depth", "Depth %",
                "Length", "Recovery")
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(list(cols))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setFont(Fonts.numeric(9))
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(23)
        dh = self.table.horizontalHeader()
        dh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        # Only the trailing columns absorb spare width; the timestamps must fit.
        dh.setSectionResizeMode(len(cols) - 1, QHeaderView.ResizeMode.Stretch)
        dh.setHighlightSections(False)
        lay.addWidget(self.table, 1)

    def set_data(self, rows: Sequence[dict[str, Any]] | None,
                 currency: str = "", timezone: str = "UTC") -> None:
        import pandas as pd

        from ..theme import money

        self.table.clearContents()
        rows = list(rows or [])
        self.table.setRowCount(len(rows))

        def when(ts: Any) -> str:
            if ts is None:
                return "-"
            try:
                t = pd.Timestamp(int(ts), tz="UTC").tz_convert(timezone)
            except Exception:
                try:
                    t = pd.Timestamp(int(ts), tz="UTC")
                except Exception:
                    return "-"
            return t.strftime("%Y-%m-%d %H:%M")

        for r, row in enumerate(rows):
            depth = float(row.get("depth", 0.0) or 0.0)
            depth_pct = float(row.get("depth_pct", 0.0) or 0.0)
            recovered = row.get("recovery_bars")
            cells = (
                str(r + 1),
                when(row.get("start_ts")),
                when(row.get("trough_ts")),
                when(row.get("end_ts")) if row.get("end_ts") else "open",
                money(depth, currency),
                pct(depth_pct),
                f"{int(row.get('length_bars', 0)):,}",
                "open" if recovered is None else f"{int(recovered):,}",
            )
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter if c in (0, 5, 6, 7)
                    else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if c in (4, 5):
                    item.setForeground(QBrush(QColor(PALETTE.short)))
                self.table.setItem(r, c, item)

    def clear(self) -> None:
        self.set_data([])
