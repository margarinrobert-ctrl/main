"""Import tick data: every trade, kept, with bars built from it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout, QWidget)

from ...core.errors import BacktesterError
from ...data.ticks import TICK_TIMEFRAMES
from ..theme import PALETTE, Fonts
from ..widgets.common import Card
from ...data.instruments import instrument_from_filename

__all__ = ["TickImportDialog"]

_ZONES = ("UTC", "America/New_York", "America/Chicago", "Europe/London",
          "Europe/Berlin", "Asia/Tokyo", "Australia/Sydney")


class TickImportDialog(QDialog):
    """Collect what an import of ticks needs; the import itself runs in a worker.

    After ``exec()`` returns Accepted: :attr:`path`, :attr:`instrument`,
    :attr:`timezone`, :attr:`timeframe` and :attr:`name` are set.
    """

    def __init__(self, instruments: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import tick data")
        self.setMinimumWidth(620)
        self._instruments = instruments
        self.path = ""
        self.instrument = None
        self.timezone = "UTC"
        self.timeframe = "1m"
        self.name = ""

        outer = QVBoxLayout(self)
        intro = QLabel(
            "Tick data keeps every trade in order. Bars are built from it at the "
            "size you choose, and the ticks are stored with them, so a backtest "
            "can fill each stop, target and stop entry at the first trade that "
            "reaches it -- no guess about which way a bar moved.")
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color:{PALETTE.text_muted};")
        outer.addWidget(intro)

        card = Card("Tick file")
        form = QFormLayout()
        row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("A CSV of trades: time, price, volume")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(self.path_edit, 1)
        row.addWidget(browse)
        holder = QWidget()
        holder.setLayout(row)
        form.addRow("File", holder)

        self.instrument_box = QComboBox()
        try:
            items = self._instruments.all()
        except BacktesterError:
            items = []
        for inst in items:
            self.instrument_box.addItem(f"{inst.symbol} — {inst.name}", inst.symbol)
        form.addRow("Instrument", self.instrument_box)

        self.timezone_box = QComboBox()
        self.timezone_box.setEditable(True)
        self.timezone_box.addItems(_ZONES)
        self.timezone_box.setToolTip(
            "The clock the file's times are written in. Epoch timestamps are UTC "
            "by definition and ignore this.")
        form.addRow("Times are in", self.timezone_box)

        self.timeframe_box = QComboBox()
        self.timeframe_box.addItems(TICK_TIMEFRAMES)
        self.timeframe_box.setCurrentText("1m")
        form.addRow("Build bars of", self.timeframe_box)

        self.name_edit = QLineEdit()
        form.addRow("Name", self.name_edit)
        card.add_layout(form)
        outer.addWidget(card)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setFont(Fonts.body(8))
        outer.addWidget(self.status)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Import")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    # -- behaviour ----------------------------------------------------------

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a tick file", self.path_edit.text() or "",
            "Tick files (*.csv *.txt *.tsv *.csv.gz *.gz);;All files (*)")
        if path:
            self.set_path(path)

    def set_path(self, path: str) -> None:
        """Take a file and guess what the name and the header say about it."""
        self.path_edit.setText(path)
        symbols = [self.instrument_box.itemData(i)
                   for i in range(self.instrument_box.count())]
        guessed = instrument_from_filename(path, symbols)
        notes = []
        if guessed:
            self.instrument_box.setCurrentIndex(self.instrument_box.findData(guessed))
            notes.append(f"Instrument set to {guessed} from the file name; check it.")
        zone = _zone_from_header(path)
        if zone:
            self.timezone_box.setCurrentText(zone)
            notes.append(f"Times read as {zone} from the time column's name.")
        if not self.name_edit.text().strip():
            self.name_edit.setText(f"{guessed or Path(path).stem} ticks")
        self.status.setText("  ".join(notes))

    def _accept(self) -> None:
        path = self.path_edit.text().strip()
        if not path or not Path(path).is_file():
            self.status.setText("Choose a tick file that exists.")
            self.status.setStyleSheet(f"color:{PALETTE.danger};")
            return
        symbol = self.instrument_box.currentData()
        if not symbol:
            self.status.setText("Choose the instrument these ticks are.")
            self.status.setStyleSheet(f"color:{PALETTE.danger};")
            return
        try:
            self.instrument = self._instruments.get(symbol)
        except BacktesterError as exc:
            self.status.setText(exc.user_message)
            return
        self.path = path
        self.timezone = self.timezone_box.currentText().strip() or "UTC"
        self.timeframe = self.timeframe_box.currentText()
        self.name = (self.name_edit.text().strip()
                     or f"{symbol} ticks {self.timeframe}")
        self.accept()


def _zone_from_header(path: str) -> str | None:
    """The timezone the first column's header names, if it names one."""
    from ...data.csv_loader import timezone_from_header

    try:
        opener = open
        if path.lower().endswith(".gz"):
            import gzip
            opener = gzip.open
        with opener(path, "rt", encoding="utf-8-sig", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return None
    for delimiter in (",", ";", "\t", "|"):
        if delimiter in first:
            for field in first.split(delimiter):
                zone = timezone_from_header(field.strip().strip("<>"))
                if zone:
                    return zone
    return None
