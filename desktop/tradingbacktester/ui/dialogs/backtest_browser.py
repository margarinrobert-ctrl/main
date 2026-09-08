"""Opening and comparing saved backtest runs."""

from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog,
                               QHBoxLayout, QHeaderView, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from ...core.errors import BacktesterError
from ...logging_setup import get_logger
from ..theme import PALETTE, Fonts, money, number, pct
from ..widgets.common import confirm, show_error

log = get_logger(__name__)

_COLUMNS = (("label", "Label", "text"),
            ("strategy_name", "Strategy", "text"),
            ("instrument_symbol", "Instrument", "text"),
            ("timeframe_label", "TF", "text"),
            ("trade_count", "Trades", "int"),
            ("net_profit", "Net profit", "money"),
            ("return_pct", "Return", "pct"),
            ("max_drawdown_pct", "Max DD", "pct"),
            ("profit_factor", "PF", "ratio"),
            ("sharpe_ratio", "Sharpe", "ratio"),
            ("created_at", "Saved", "text"))


class BacktestBrowser(QDialog):
    """Pick one saved run to open, or several to compare.

    After ``exec()`` returns ``Accepted`` the caller reads :attr:`selected_ids`
    and :attr:`include_current`.
    """

    def __init__(self, store: Any, parent: QWidget | None = None,
                 multi: bool = False, current: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Compare Backtests" if multi else "Saved Backtests")
        self.resize(1080, 560)
        self._store = store
        self._multi = multi
        self._current_result = current
        self._rows: list[Any] = []

        self.selected_ids: list[str] = []
        self.include_current: bool = bool(multi and current is not None)

        self._build_ui()
        self._refresh()

    # -- construction ----------------------------------------------------

    def _build_ui(self) -> None:
        from ..icons import icon

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(9)

        heading = QLabel(
            "Choose two or more runs to put side by side."
            if self._multi else
            "Choose a saved run to open. Its trades, curves and statistics are "
            "restored; its bars are reloaded from the dataset it used.")
        heading.setWordWrap(True)
        heading.setFont(Fonts.body(10))
        heading.setStyleSheet(f"color:{PALETTE.text_dim};")
        lay.addWidget(heading)

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels([c[1] for c in _COLUMNS])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection if self._multi
            else QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setFont(Fonts.numeric(9))
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(23)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setHighlightSections(False)
        self.table.itemSelectionChanged.connect(self._update_ok)
        self.table.doubleClicked.connect(self._accept)
        lay.addWidget(self.table, 1)

        if self._multi and self._current_result is not None:
            self.current_box = QCheckBox(
                f"Include the run currently open "
                f"({getattr(self._current_result, 'label', 'current run')})")
            self.current_box.setChecked(True)
            self.current_box.toggled.connect(self._update_ok)
            lay.addWidget(self.current_box)
        else:
            self.current_box = None

        self.status = QLabel("")
        self.status.setFont(Fonts.body(9))
        self.status.setStyleSheet(f"color:{PALETTE.text_muted};")
        lay.addWidget(self.status)

        row = QHBoxLayout()
        delete = QPushButton("  Delete")
        delete.setObjectName("Ghost")
        delete.setIcon(icon("trash", 15))
        delete.clicked.connect(self._delete)
        row.addWidget(delete)
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        self.ok_button = QPushButton("Compare" if self._multi else "Open")
        self.ok_button.setObjectName("Primary")
        self.ok_button.setDefault(True)
        self.ok_button.clicked.connect(self._accept)
        row.addWidget(self.ok_button)
        lay.addLayout(row)

    # -- data ------------------------------------------------------------

    def _refresh(self) -> None:
        try:
            self._rows = list(self._store.list())
        except BacktesterError as exc:
            show_error(self, exc)
            self._rows = []

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self._rows))
        unreadable = 0
        for r, meta in enumerate(self._rows):
            readable = getattr(meta, "readable", True)
            unreadable += 0 if readable else 1
            for c, (key, _title, kind) in enumerate(_COLUMNS):
                value = getattr(meta, key, None)
                item = QTableWidgetItem(self._format(value, kind, readable))
                item.setData(Qt.ItemDataRole.UserRole, self._sort_key(value, kind))
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                    if kind == "text" else
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if not readable:
                    item.setForeground(QBrush(QColor(PALETTE.danger)))
                    item.setToolTip(getattr(meta, "problem", "") or
                                    "This saved run could not be read.")
                elif key in ("net_profit", "return_pct"):
                    item.setForeground(QBrush(QColor(
                        PALETTE.long if (value or 0) > 0 else
                        PALETTE.short if (value or 0) < 0 else PALETTE.text_dim)))
                elif key == "max_drawdown_pct" and value:
                    item.setForeground(QBrush(QColor(PALETTE.short)))
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole + 1, meta.id)
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)

        parts = [f"{len(self._rows)} saved run{'s' if len(self._rows) != 1 else ''}"]
        if unreadable:
            parts.append(f"{unreadable} could not be read and cannot be opened")
        self.status.setText(" · ".join(parts))
        self._update_ok()

    @staticmethod
    def _format(value: Any, kind: str, readable: bool = True) -> str:
        if not readable and kind != "text":
            return "-"
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
            return f"{int(value):,}"
        if kind == "ratio":
            return number(value, 2)
        text = str(value)
        return text.replace("T", " ")[:19] if len(text) > 19 and "T" in text else text

    @staticmethod
    def _sort_key(value: Any, kind: str) -> Any:
        if kind == "text":
            return str(value or "")
        try:
            number_value = float(value)
        except (TypeError, ValueError):
            return -math.inf
        return -math.inf if math.isnan(number_value) else number_value

    # -- selection -------------------------------------------------------

    def _selected_metas(self) -> list[Any]:
        out: list[Any] = []
        for index in self.table.selectionModel().selectedRows():
            item = self.table.item(index.row(), 0)
            if item is None:
                continue
            run_id = item.data(Qt.ItemDataRole.UserRole + 1)
            meta = next((m for m in self._rows if m.id == run_id), None)
            if meta is not None:
                out.append(meta)
        return out

    def _update_ok(self) -> None:
        chosen = [m for m in self._selected_metas() if getattr(m, "readable", True)]
        extra = 1 if (self.current_box is not None and
                      self.current_box.isChecked()) else 0
        enough = (len(chosen) + extra) >= 2 if self._multi else len(chosen) == 1
        self.ok_button.setEnabled(enough)
        self.ok_button.setToolTip(
            "" if enough else
            ("Select at least two runs, or tick the current one"
             if self._multi else "Select one run"))

    def _accept(self) -> None:
        chosen = [m for m in self._selected_metas() if getattr(m, "readable", True)]
        if not chosen and not (self.current_box and self.current_box.isChecked()):
            return
        self.selected_ids = [m.id for m in chosen]
        self.include_current = bool(self.current_box and self.current_box.isChecked())
        if self._multi and len(self.selected_ids) + int(self.include_current) < 2:
            return
        self.accept()

    def _delete(self) -> None:
        chosen = self._selected_metas()
        if not chosen:
            return
        names = ", ".join(m.label or m.id for m in chosen[:4])
        if len(chosen) > 4:
            names += f" and {len(chosen) - 4} more"
        if not confirm(self, "Delete Saved Backtests",
                       f"Delete {names}? This cannot be undone. The dataset and "
                       f"the strategy are not affected."):
            return
        for meta in chosen:
            try:
                self._store.delete(meta.id)
            except BacktesterError as exc:
                show_error(self, exc)
                break
        self._refresh()
