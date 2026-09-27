"""Editing the instrument catalogue.

An instrument decides what a price move is worth. Getting ``point_value`` wrong
scales every cash figure in a backtest by the same factor without changing a
single price, so this dialog explains it rather than just presenting a box.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout, QWidget)

from ...core.errors import BacktesterError
from ...core.types import AssetClass
from ...data.models import Instrument
from ...logging_setup import get_logger
from ..theme import PALETTE, Fonts
from ..widgets.common import (Card, FieldSpec, FormPanel, ask_text, confirm,
                              hline, show_error)

log = get_logger(__name__)

_TIMEZONES = ("UTC", "America/New_York", "America/Chicago", "America/Los_Angeles",
              "Europe/London", "Europe/Berlin", "Europe/Zurich", "Asia/Tokyo",
              "Asia/Shanghai", "Asia/Hong_Kong", "Asia/Singapore", "Asia/Kolkata",
              "Australia/Sydney")


class InstrumentDialog(QDialog):
    """List on the left, editor on the right; changes are saved to the registry."""

    def __init__(self, registry: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Instruments")
        self.resize(920, 640)
        self._registry = registry
        self._current: str = ""
        self._loading = False
        self._build_ui()
        self._refresh()

    # -- construction ----------------------------------------------------

    def _build_ui(self) -> None:
        from ..icons import icon

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(9)

        body = QHBoxLayout()
        body.setSpacing(10)

        # -- list ---------------------------------------------------------
        left = QVBoxLayout()
        left.setSpacing(6)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.setFixedWidth(230)
        self.list.setFont(Fonts.numeric(9))
        self.list.currentItemChanged.connect(self._on_selected)
        left.addWidget(self.list, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(4)
        for text, ico, tip, slot in (
                ("", "plus", "Add an instrument", self._add),
                ("", "copy", "Duplicate the selected instrument", self._duplicate),
                ("", "trash", "Delete the selected instrument", self._delete),
                ("", "refresh", "Restore the built-in catalogue entries",
                 self._restore_defaults)):
            button = QPushButton(text)
            button.setIcon(icon(ico, 16, PALETTE.text))
            button.setToolTip(tip)
            button.setFixedHeight(26)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        left.addLayout(buttons)
        body.addLayout(left)

        # -- editor -------------------------------------------------------
        card = Card("Contract Specification")
        self.form = FormPanel([
            FieldSpec("symbol", "Symbol", "text", ""),
            FieldSpec("name", "Name", "text", ""),
            FieldSpec("asset_class", "Asset class", "choice", AssetClass.OTHER.value,
                      choices=[(a.value.replace("_", " ").title(), a.value)
                               for a in AssetClass]),
            FieldSpec("tick_size", "Tick size", "float", 0.01, 1e-9, 1e6, 0.01, 8,
                      tooltip="The smallest price increment this instrument trades in."),
            FieldSpec("point_value", "Point value", "float", 1.0, 1e-9, 1e9, 1.0, 6,
                      tooltip="Cash change per 1.0 of price movement, per unit held."),
            FieldSpec("lot_size", "Lot size", "float", 1.0, 1e-9, 1e9, 1.0, 6,
                      tooltip="Smallest tradeable quantity. Sizes round down to a "
                              "whole number of these."),
            FieldSpec("price_decimals", "Price decimals", "int", 2, 0, 8, 1),
            FieldSpec("currency", "Currency", "text", "USD"),
            FieldSpec("exchange", "Exchange", "text", ""),
            FieldSpec("timezone", "Session timezone", "choice", "UTC",
                      choices=[(z, z) for z in _TIMEZONES],
                      tooltip="Used by session filters and by VWAP's daily reset."),
            FieldSpec("margin_per_unit", "Margin per unit", "float", 0.0, 0.0, 1e9,
                      100.0, 2,
                      tooltip="Initial margin per contract. Indicative only; "
                              "brokers differ."),
            FieldSpec("default_commission", "Default commission", "float", 0.0, 0.0,
                      1e6, 0.1, 4,
                      tooltip="Seeded into the cost panel when this instrument "
                              "is loaded."),
            FieldSpec("default_spread_points", "Default spread", "float", 0.0, 0.0,
                      1e6, 0.01, 6),
            FieldSpec("notes", "Notes", "text", ""),
        ], label_width=140)
        self.form.changed.connect(self._on_edited)
        card.add(self.form)
        card.add(hline())

        explain = QLabel(
            "<b>Point value</b> is the setting that matters most. It is the cash "
            "change in the account per 1.0 of price movement per unit held: "
            "<b>1.0</b> for a share, <b>20.0</b> for an E-mini Nasdaq contract, "
            "<b>2.0</b> for the micro, <b>100000</b> for a standard forex lot. "
            "If it is wrong, every profit and loss figure is wrong by exactly "
            "that factor while every price on the chart still looks right.")
        explain.setWordWrap(True)
        explain.setObjectName("Hint")
        explain.setFont(Fonts.body(8))
        card.add(explain)

        self.error = QLabel("")
        self.error.setWordWrap(True)
        self.error.setFont(Fonts.body(9))
        self.error.setStyleSheet(f"color:{PALETTE.danger};")
        card.add(self.error)
        body.addWidget(card, 1)
        outer.addLayout(body, 1)

        row = QHBoxLayout()
        self.status = QLabel("")
        self.status.setFont(Fonts.body(9))
        self.status.setStyleSheet(f"color:{PALETTE.text_muted};")
        row.addWidget(self.status, 1)
        close = QPushButton("Done")
        close.setObjectName("Primary")
        close.setDefault(True)
        close.clicked.connect(self._finish)
        row.addWidget(close)
        outer.addLayout(row)

    # -- list ------------------------------------------------------------

    def _refresh(self, select: str = "") -> None:
        self._loading = True
        try:
            self.list.clear()
            try:
                items = self._registry.all()
            except BacktesterError as exc:
                show_error(self, exc)
                items = []
            for inst in items:
                entry = QListWidgetItem(f"{inst.symbol}    {inst.name}")
                entry.setData(Qt.ItemDataRole.UserRole, inst.symbol)
                entry.setToolTip(
                    f"{inst.name}\ntick {inst.tick_size:g} · "
                    f"point value {inst.point_value:g} {inst.currency}")
                self.list.addItem(entry)
            target = select or self._current
            for row in range(self.list.count()):
                if self.list.item(row).data(Qt.ItemDataRole.UserRole) == target:
                    self.list.setCurrentRow(row)
                    break
            else:
                if self.list.count():
                    self.list.setCurrentRow(0)
        finally:
            self._loading = False
        self._on_selected()
        self.status.setText(f"{self.list.count()} instruments in this workspace")

    def _on_selected(self, *_args) -> None:
        if self._loading:
            return
        item = self.list.currentItem()
        if item is None:
            self._current = ""
            return
        symbol = item.data(Qt.ItemDataRole.UserRole)
        try:
            inst = self._registry.get(symbol)
        except BacktesterError:
            return
        self._current = symbol
        self.error.setText("")
        self._loading = True
        try:
            self.form.set_values({
                "symbol": inst.symbol, "name": inst.name,
                "asset_class": inst.asset_class.value,
                "tick_size": inst.tick_size, "point_value": inst.point_value,
                "lot_size": inst.lot_size, "price_decimals": inst.price_decimals,
                "currency": inst.currency, "exchange": inst.exchange,
                "timezone": inst.timezone, "margin_per_unit": inst.margin_per_unit,
                "default_commission": inst.default_commission,
                "default_spread_points": inst.default_spread_points,
                "notes": inst.notes,
            })
        finally:
            self._loading = False

    # -- editing ---------------------------------------------------------

    def _on_edited(self) -> None:
        """Apply the form to the selected instrument, reporting bad values inline."""
        if self._loading or not self._current:
            return
        values = self.form.values()
        try:
            edited = Instrument(
                symbol=str(values["symbol"]).strip() or self._current,
                name=str(values["name"]).strip(),
                asset_class=AssetClass(values["asset_class"]),
                tick_size=float(values["tick_size"]),
                point_value=float(values["point_value"]),
                lot_size=float(values["lot_size"]),
                price_decimals=int(values["price_decimals"]),
                currency=str(values["currency"]).strip() or "USD",
                exchange=str(values["exchange"]).strip(),
                timezone=str(values["timezone"]),
                margin_per_unit=float(values["margin_per_unit"]),
                default_commission=float(values["default_commission"]),
                default_spread_points=float(values["default_spread_points"]),
                notes=str(values["notes"]),
            )
        except BacktesterError as exc:
            self.error.setText(exc.user_message)
            return
        except (TypeError, ValueError) as exc:
            self.error.setText(str(exc))
            return

        self.error.setText("")
        try:
            if edited.symbol != self._current:
                self._registry.remove(self._current)
                self._registry.add(edited)
            else:
                self._registry.update(edited)
            self._registry.save()
        except BacktesterError as exc:
            self.error.setText(exc.user_message)
            return
        if edited.symbol != self._current:
            self._refresh(edited.symbol)

    def _add(self) -> None:
        symbol = ask_text(self, "New Instrument", "Symbol:", "NEWSYM")
        if not symbol:
            return
        try:
            self._registry.add(Instrument.with_defaults(symbol.strip().upper()))
            self._registry.save()
        except BacktesterError as exc:
            show_error(self, exc)
            return
        self._refresh(symbol.strip().upper())

    def _duplicate(self) -> None:
        if not self._current:
            return
        symbol = ask_text(self, "Duplicate Instrument", "Symbol for the copy:",
                          f"{self._current}2")
        if not symbol:
            return
        try:
            source = self._registry.get(self._current)
            data = source.to_dict()
            data["symbol"] = symbol.strip().upper()
            self._registry.add(Instrument.from_dict(data))
            self._registry.save()
        except BacktesterError as exc:
            show_error(self, exc)
            return
        self._refresh(symbol.strip().upper())

    def _delete(self) -> None:
        if not self._current:
            return
        if not confirm(self, "Delete Instrument",
                       f"Delete {self._current}? Datasets already imported keep "
                       f"their own copy of the contract specification, so they "
                       f"will still load."):
            return
        try:
            self._registry.remove(self._current)
            self._registry.save()
        except BacktesterError as exc:
            show_error(self, exc)
            return
        self._current = ""
        self._refresh()

    def _restore_defaults(self) -> None:
        if not confirm(self, "Restore Built-in Instruments",
                       "Add back any built-in instrument that has been deleted? "
                       "Instruments you have edited are left exactly as they are.",
                       confirm_text="Restore", danger=False):
            return
        from ...data.instruments import DEFAULT_INSTRUMENTS

        added = 0
        for inst in DEFAULT_INSTRUMENTS:
            try:
                self._registry.get(inst.symbol)
            except BacktesterError:
                try:
                    self._registry.add(Instrument.from_dict(inst.to_dict()))
                    added += 1
                except BacktesterError:
                    continue
        try:
            self._registry.save()
        except BacktesterError as exc:
            show_error(self, exc)
        self._refresh()
        self.status.setText(f"{added} built-in instrument(s) restored")

    def _finish(self) -> None:
        self._on_edited()
        if self.error.text():
            return
        self.accept()
