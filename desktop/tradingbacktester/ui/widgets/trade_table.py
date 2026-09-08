"""The trade blotter: a sortable, filterable table of every closed trade.

Backed by a ``QAbstractTableModel`` over the raw list rather than a
``QTableWidget``, because a run can produce tens of thousands of trades and
building a widget per cell would stall the UI.  Sorting and filtering go through
a ``QSortFilterProxyModel`` so the underlying list is never copied or reordered.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
from PySide6.QtCore import (QAbstractTableModel, QModelIndex, QSortFilterProxyModel,
                            QSize, Qt, Signal)
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFrame, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPushButton,
                               QTableView, QVBoxLayout, QWidget)

from ...core.types import ExitReason, Side, Trade
from ..theme import PALETTE, Fonts, duration, money, number, pct


class _Column:
    __slots__ = ("key", "title", "width", "align", "kind", "tooltip")

    def __init__(self, key: str, title: str, width: int, align: str = "right",
                 kind: str = "text", tooltip: str = "") -> None:
        self.key = key
        self.title = title
        self.width = width
        self.align = align
        self.kind = kind
        self.tooltip = tooltip


COLUMNS: tuple[_Column, ...] = (
    _Column("num", "#", 52, "right", "int", "Trade number, in the order it was opened"),
    _Column("entry_time", "Entry Time", 132, "left", "time"),
    _Column("exit_time", "Exit Time", 132, "left", "time"),
    _Column("side", "Side", 56, "center", "side"),
    _Column("entry_price", "Entry", 88, "right", "price"),
    _Column("exit_price", "Exit", 88, "right", "price"),
    _Column("quantity", "Qty", 72, "right", "qty"),
    _Column("stop_loss", "Stop", 88, "right", "price"),
    _Column("take_profit", "Target", 88, "right", "price"),
    _Column("gross_pnl", "Gross P&L", 96, "right", "money_signed"),
    _Column("commission", "Comm.", 74, "right", "cost"),
    _Column("slippage_cost", "Slip.", 68, "right", "cost"),
    _Column("spread_cost", "Spread", 74, "right", "cost"),
    _Column("net_pnl", "Net P&L", 100, "right", "money_signed"),
    _Column("return_pct", "Return %", 82, "right", "pct_signed"),
    _Column("r_multiple", "R", 62, "right", "r"),
    _Column("bars_held", "Bars", 58, "right", "int"),
    _Column("duration_seconds", "Duration", 88, "right", "duration"),
    _Column("mae", "MAE", 78, "right", "points"),
    _Column("mfe", "MFE", 78, "right", "points"),
    _Column("exit_reason", "Exit Reason", 112, "left", "reason"),
    _Column("equity_after", "Equity", 100, "right", "money"),
)


class TradeTableModel(QAbstractTableModel):
    """Read-only model over a list of :class:`Trade`."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._trades: list[Trade] = []
        self._decimals = 2
        self._currency = ""
        self._timezone = "UTC"
        self._entry_dt: Any = None
        self._exit_dt: Any = None
        self._time_cache: dict[int, tuple[str, str]] = {}

    def _size_columns(self) -> None:
        """Width each column from font metrics rather than fixed pixels.

        The monospace family differs between Windows, macOS and Linux, so a
        hard-coded pixel width that fits Consolas elides under DejaVu Sans Mono.
        Measuring a representative string keeps every column readable wherever
        the application runs.
        """
        from PySide6.QtGui import QFontMetrics

        samples = {
            "num": "9999", "time": "2024-01-31 09:30", "side": "SHORT",
            "price": "199,999.99", "qty": "999.9999", "money_signed": "-$999,999.99",
            "money": "$9,999,999", "cost": "$9,999.99", "pct_signed": "-99.99%",
            "r": "-99.99", "int": "9999", "duration": "999d 23h",
            "points": "9,999.99", "reason": "Daily Loss Limit", "text": "",
        }
        body = QFontMetrics(Fonts.numeric(9))
        head = QFontMetrics(Fonts.body(9, bold=True))
        for i, col in enumerate(COLUMNS):
            needed = max(body.horizontalAdvance(samples.get(col.kind, "")) + 18,
                         head.horizontalAdvance(col.title) + 26,
                         56)
            self.table.setColumnWidth(i, int(needed))

    # -- data ------------------------------------------------------------

    def set_trades(self, trades: Sequence[Trade], decimals: int = 2,
                   currency: str = "", timezone: str = "UTC") -> None:
        import pandas as pd

        self.beginResetModel()
        self._trades = list(trades)
        self._decimals = decimals
        self._currency = currency
        self._timezone = timezone or "UTC"
        # Must be cleared, not kept: the cache is keyed on the row number, and
        # after a reload row 0 is a different trade in a possibly different
        # timezone.
        self._time_cache = {}
        # Converting the columns is vectorised and costs nothing; FORMATTING
        # them is per element, and this table is virtual -- about forty rows
        # are on screen at a time.  Formatting all of them up front spent 3.4
        # seconds on 200,000 trades to produce eighty strings anyone could
        # read, on the thread that paints the window.  So convert here, format
        # in `time_at`.
        if self._trades:
            def column(values):
                index = pd.DatetimeIndex(pd.to_datetime(
                    np.fromiter(values, dtype="int64", count=len(self._trades)),
                    unit="ns", utc=True))
                try:
                    return index.tz_convert(self._timezone)
                except Exception:
                    return index      # An unknown timezone stays in UTC.

            self._entry_dt = column(t.entry_ts for t in self._trades)
            self._exit_dt = column(t.exit_ts for t in self._trades)
        else:
            self._entry_dt = None
            self._exit_dt = None
        self.endResetModel()

    #: Seconds add width without information on bar data.
    TIME_FORMAT = "%Y-%m-%d %H:%M"

    def time_at(self, row: int) -> tuple[str, str]:
        """The entry and exit times of one row, formatted on demand.

        Cached, because the text filter reads every row and would otherwise
        reformat the whole table on each keystroke.
        """
        hit = self._time_cache.get(row)
        if hit is not None:
            return hit
        if self._entry_dt is None or not (0 <= row < len(self._trades)):
            return ("", "")
        fmt = self.TIME_FORMAT
        out = (self._entry_dt[row].strftime(fmt), self._exit_dt[row].strftime(fmt))
        self._time_cache[row] = out
        return out

    def trade_at(self, row: int) -> Trade | None:
        if 0 <= row < len(self._trades):
            return self._trades[row]
        return None

    # -- Qt model interface ----------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._trades)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation,  # noqa: N802
                   role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation is not Qt.Orientation.Horizontal:
            return None
        col = COLUMNS[section]
        if role == Qt.ItemDataRole.DisplayRole:
            return col.title
        if role == Qt.ItemDataRole.ToolTipRole and col.tooltip:
            return col.tooltip
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row, colno = index.row(), index.column()
        if row >= len(self._trades):
            return None
        t = self._trades[row]
        col = COLUMNS[colno]

        if role == Qt.ItemDataRole.UserRole:
            return self._sort_value(t, col, row)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            h = {"left": Qt.AlignmentFlag.AlignLeft,
                 "right": Qt.AlignmentFlag.AlignRight,
                 "center": Qt.AlignmentFlag.AlignHCenter}[col.align]
            return int(h | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ForegroundRole:
            return self._foreground(t, col)
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(t, col, row)
        if role == Qt.ItemDataRole.ToolTipRole:
            return (f"Trade {row + 1} — {t.side.value} {t.quantity:g} @ "
                    f"{t.entry_price:,.{self._decimals}f}\n"
                    f"Exit: {t.exit_reason.label} @ "
                    f"{t.exit_price:,.{self._decimals}f}\n"
                    f"Net: {money(t.net_pnl, self._currency)}")
        return None

    # -- cell rendering --------------------------------------------------

    def _display(self, t: Trade, col: _Column, row: int) -> str:
        d = self._decimals
        k = col.kind
        if k == "int":
            return str(row + 1) if col.key == "num" else str(int(getattr(t, col.key)))
        if k == "time":
            return self.time_at(row)[0 if col.key == "entry_time" else 1]
        if k == "side":
            return "LONG" if t.side is Side.LONG else "SHORT"
        if k == "price":
            v = getattr(t, col.key)
            return "-" if v is None or v != v else f"{v:,.{d}f}"
        if k == "qty":
            v = float(t.quantity)
            return f"{v:,.0f}" if abs(v - round(v)) < 1e-9 else f"{v:,.4f}".rstrip("0")
        if k == "money_signed":
            return money(getattr(t, col.key), self._currency)
        if k == "money":
            return money(getattr(t, col.key), self._currency)
        if k == "cost":
            v = float(getattr(t, col.key))
            return "-" if v == 0 else money(v, self._currency)
        if k == "pct_signed":
            return pct(getattr(t, col.key), 2, signed=True)
        if k == "r":
            v = t.r_multiple
            return "-" if v is None or v != v else f"{v:+.2f}"
        if k == "duration":
            return duration(t.duration_seconds)
        if k == "points":
            return f"{float(getattr(t, col.key)):,.{d}f}"
        if k == "reason":
            return t.exit_reason.label
        return str(getattr(t, col.key, ""))

    def _foreground(self, t: Trade, col: _Column) -> QBrush | None:
        if col.key in ("net_pnl", "gross_pnl", "return_pct", "r_multiple"):
            v = getattr(t, col.key)
            if v is None or v != v:
                return QBrush(QColor(PALETTE.text_muted))
            return QBrush(QColor(PALETTE.long if v > 0 else
                                 PALETTE.short if v < 0 else PALETTE.text_dim))
        if col.key == "side":
            return QBrush(QColor(PALETTE.long if t.side is Side.LONG else PALETTE.short))
        if col.key in ("commission", "slippage_cost", "spread_cost"):
            return QBrush(QColor(PALETTE.text_muted))
        if col.key == "exit_reason":
            colour = {ExitReason.STOP_LOSS: PALETTE.short,
                      ExitReason.TAKE_PROFIT: PALETTE.long,
                      ExitReason.TRAILING_STOP: PALETTE.warning,
                      ExitReason.END_OF_DATA: PALETTE.text_muted,
                      ExitReason.SESSION_END: PALETTE.info,
                      ExitReason.DAILY_LOSS_LIMIT: PALETTE.danger,
                      ExitReason.MARGIN_CALL: PALETTE.danger}.get(t.exit_reason)
            return QBrush(QColor(colour)) if colour else None
        return None

    def _sort_value(self, t: Trade, col: _Column, row: int) -> Any:
        """A comparable value so sorting is numeric, not lexicographic."""
        if col.key == "num":
            return row
        if col.key == "entry_time":
            return t.entry_ts
        if col.key == "exit_time":
            return t.exit_ts
        if col.key == "side":
            return 0 if t.side is Side.LONG else 1
        if col.key == "exit_reason":
            return t.exit_reason.value
        v = getattr(t, col.key, None)
        if v is None:
            return float("-inf")
        try:
            f = float(v)
        except (TypeError, ValueError):
            return str(v)
        return -1e308 if f != f else f


class TradeFilterProxy(QSortFilterProxyModel):
    """Filters by direction, outcome, exit reason and a free-text search."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSortRole(Qt.ItemDataRole.UserRole)
        self.side_filter = "all"
        self.outcome_filter = "all"
        self.reason_filter = "all"
        self.text_filter = ""

    def set_filters(self, side: str, outcome: str, reason: str, text: str) -> None:
        self.side_filter = side
        self.outcome_filter = outcome
        self.reason_filter = reason
        self.text_filter = text.strip().lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:  # noqa: N802
        model: TradeTableModel = self.sourceModel()  # type: ignore[assignment]
        t = model.trade_at(row)
        if t is None:
            return False
        if self.side_filter == "long" and t.side is not Side.LONG:
            return False
        if self.side_filter == "short" and t.side is not Side.SHORT:
            return False
        if self.outcome_filter == "wins" and t.net_pnl <= 0:
            return False
        if self.outcome_filter == "losses" and t.net_pnl >= 0:
            return False
        if self.reason_filter != "all" and t.exit_reason.value != self.reason_filter:
            return False
        if self.text_filter:
            hay = " ".join((
                str(row + 1), t.side.value, t.exit_reason.label,
                f"{t.entry_price}", f"{t.exit_price}", f"{t.net_pnl:.2f}",
                *model.time_at(row),
            )).lower()
            if self.text_filter not in hay:
                return False
        return True


class TradeTableWidget(QWidget):
    """Filter bar, table and a live summary of whatever is currently shown."""

    tradeSelected = Signal(int)
    """Emits the index into the *original* trade list, not the filtered view."""

    exportRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._currency = ""
        self._build_ui()

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)

        from ..icons import icon

        bar = QFrame()
        bar.setObjectName("Card")
        bar.setFixedHeight(34)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 0, 8, 0)
        bl.setSpacing(7)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search trades…")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(190)
        self.search.textChanged.connect(self._apply_filters)
        bl.addWidget(self.search)

        self.side_box = QComboBox()
        self.side_box.addItem("All sides", "all")
        self.side_box.addItem("Long only", "long")
        self.side_box.addItem("Short only", "short")
        self.side_box.currentIndexChanged.connect(self._apply_filters)
        bl.addWidget(self.side_box)

        self.outcome_box = QComboBox()
        self.outcome_box.addItem("All outcomes", "all")
        self.outcome_box.addItem("Winners", "wins")
        self.outcome_box.addItem("Losers", "losses")
        self.outcome_box.currentIndexChanged.connect(self._apply_filters)
        bl.addWidget(self.outcome_box)

        self.reason_box = QComboBox()
        self.reason_box.addItem("All exit reasons", "all")
        self.reason_box.currentIndexChanged.connect(self._apply_filters)
        bl.addWidget(self.reason_box)

        bl.addStretch(1)
        self.summary = QLabel("")
        self.summary.setFont(Fonts.numeric(9))
        bl.addWidget(self.summary)

        export = QPushButton("  Export CSV")
        export.setObjectName("Ghost")
        export.setIcon(icon("export", 15))
        export.clicked.connect(self.exportRequested.emit)
        bl.addWidget(export)
        lay.addWidget(bar)

        self.model = TradeTableModel(self)
        self.proxy = TradeFilterProxy(self)
        self.proxy.setSourceModel(self.model)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(23)
        self.table.setWordWrap(False)
        self.table.setFont(Fonts.numeric(9))
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setHighlightSections(False)
        self._size_columns()
        self.table.selectionModel().selectionChanged.connect(self._on_selection)
        lay.addWidget(self.table, 1)

    def _size_columns(self) -> None:
        """Width each column from font metrics rather than fixed pixels.

        The monospace family differs between Windows, macOS and Linux, so a
        hard-coded pixel width that fits Consolas elides under DejaVu Sans Mono.
        Measuring a representative string keeps every column readable wherever
        the application runs.
        """
        from PySide6.QtGui import QFontMetrics

        samples = {
            "num": "9999", "time": "2024-01-31 09:30", "side": "SHORT",
            "price": "199,999.99", "qty": "999.9999", "money_signed": "-$999,999.99",
            "money": "$9,999,999", "cost": "$9,999.99", "pct_signed": "-99.99%",
            "r": "-99.99", "int": "9999", "duration": "999d 23h",
            "points": "9,999.99", "reason": "Daily Loss Limit", "text": "",
        }
        body = QFontMetrics(Fonts.numeric(9))
        head = QFontMetrics(Fonts.body(9, bold=True))
        for i, col in enumerate(COLUMNS):
            needed = max(body.horizontalAdvance(samples.get(col.kind, "")) + 18,
                         head.horizontalAdvance(col.title) + 26,
                         56)
            self.table.setColumnWidth(i, int(needed))

    # -- data ------------------------------------------------------------

    def set_trades(self, trades: Sequence[Trade], decimals: int = 2,
                   currency: str = "", timezone: str = "UTC") -> None:
        self._currency = currency
        self.model.set_trades(trades, decimals, currency, timezone)
        reasons = sorted({t.exit_reason for t in trades}, key=lambda r: r.value)
        current = self.reason_box.currentData()
        self.reason_box.blockSignals(True)
        self.reason_box.clear()
        self.reason_box.addItem("All exit reasons", "all")
        for r in reasons:
            self.reason_box.addItem(r.label, r.value)
        idx = self.reason_box.findData(current)
        self.reason_box.setCurrentIndex(max(0, idx))
        self.reason_box.blockSignals(False)
        self._apply_filters()
        self.table.scrollToTop()

    def clear(self) -> None:
        self.set_trades([])

    def visible_trades(self) -> list[Trade]:
        """The trades currently passing the filters, in the displayed order."""
        out: list[Trade] = []
        for r in range(self.proxy.rowCount()):
            src = self.proxy.mapToSource(self.proxy.index(r, 0)).row()
            t = self.model.trade_at(src)
            if t is not None:
                out.append(t)
        return out

    def select_trade(self, index: int) -> None:
        """Select by index into the original list, scrolling it into view."""
        src = self.model.index(index, 0)
        proxy_index = self.proxy.mapFromSource(src)
        if not proxy_index.isValid():
            return
        self.table.selectRow(proxy_index.row())
        self.table.scrollTo(proxy_index, QAbstractItemView.ScrollHint.PositionAtCenter)

    # -- internals -------------------------------------------------------

    def _apply_filters(self) -> None:
        self.proxy.set_filters(self.side_box.currentData() or "all",
                               self.outcome_box.currentData() or "all",
                               self.reason_box.currentData() or "all",
                               self.search.text())
        self._update_summary()

    def _update_summary(self) -> None:
        trades = self.visible_trades()
        n = len(trades)
        if n == 0:
            self.summary.setText(
                f"<span style='color:{PALETTE.text_muted}'>no trades</span>")
            return
        pnl = float(np.sum([t.net_pnl for t in trades]))
        wins = sum(1 for t in trades if t.net_pnl > 0)
        wr = wins / n * 100.0
        col = PALETTE.long if pnl > 0 else PALETTE.short if pnl < 0 else PALETTE.text_dim
        total = self.model.rowCount()
        shown = f"{n:,} of {total:,}" if n != total else f"{n:,}"
        self.summary.setText(
            f"<span style='color:{PALETTE.text_muted}'>{shown} trades</span>   "
            f"<span style='color:{PALETTE.text_dim}'>win rate</span> "
            f"<span style='color:{PALETTE.text}'>{wr:.1f}%</span>   "
            f"<span style='color:{PALETTE.text_dim}'>net</span> "
            f"<span style='color:{col}'>{money(pnl, self._currency)}</span>")

    def _on_selection(self, *_args) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        src = self.proxy.mapToSource(rows[0]).row()
        self.tradeSelected.emit(src)
