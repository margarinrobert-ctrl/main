"""The CSV import dialog.

This is where a user's own data meets the application, and it is the single
place most likely to produce a bad first experience. So it does three things
deliberately: it guesses everything it can from the file, it shows the raw rows
the parser is looking at, and when something is wrong it names the row and the
column rather than saying "invalid file".

The full file is never loaded here. Validation parses a bounded prefix; the
caller imports the whole thing on a worker thread afterwards.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                               QFileDialog, QFormLayout, QFrame, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QPushButton, QSizePolicy, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ...core.errors import BacktesterError, CsvImportError
from ...core.timeframe import Timeframe
from ...core.types import AssetClass
from ...data.autodetect import audit_mapping
from ...data.csv_loader import (ColumnMapping, load_csv, resolve_column,
                                sniff_csv)
from ...data.models import Instrument
from ...logging_setup import get_logger
from ..theme import PALETTE, Fonts
from ..widgets.common import Card, hline, show_error

log = get_logger(__name__)

#: How many rows the Validate button parses.  Enough to prove the mapping and
#: infer a timeframe, small enough to stay instant on a two-million-row file.
VALIDATE_ROWS = 500

_NONE = "— none —"

#: Short names for the mapping fields, used to label the preview columns.
_FIELD_LABELS = {"datetime": "Date/time", "date": "Date", "time": "Time",
                 "open": "Open", "high": "High", "low": "Low",
                 "close": "Close", "volume": "Volume"}


class _SteadyComboBox(QComboBox):
    """A combo box that ignores the mouse wheel unless it is focused.

    Qt's default is to change the selection on any wheel event over the widget,
    focused or not.  In a dialog this one is in -- eight combo boxes stacked in
    a grid -- one scroll gesture across them silently rewrites the column
    mapping, and the only symptom is a parse error twenty rows into the file.
    Scrolling a *focused* box is still deliberate, so that keeps working.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event: Any) -> None:      # noqa: N802 - Qt naming
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()

_TIMEZONES = ("UTC", "America/New_York", "America/Chicago", "America/Los_Angeles",
              "Europe/London", "Europe/Berlin", "Europe/Zurich", "Europe/Moscow",
              "Asia/Tokyo", "Asia/Shanghai", "Asia/Hong_Kong", "Asia/Singapore",
              "Asia/Kolkata", "Australia/Sydney")

_FORMATS = (
    ("Detect automatically", ""),
    ("2023-01-02 09:30:00", "%Y-%m-%d %H:%M:%S"),
    ("2023-01-02 09:30", "%Y-%m-%d %H:%M"),
    ("2023-01-02", "%Y-%m-%d"),
    ("02/01/2023 09:30 (day first)", "%d/%m/%Y %H:%M"),
    ("01/02/2023 09:30 (month first)", "%m/%d/%Y %H:%M"),
    ("02.01.2023 09:30", "%d.%m.%Y %H:%M"),
    ("20230102 093000", "%Y%m%d %H%M%S"),
    ("20230102", "%Y%m%d"),
    ("ISO 8601 with offset", "iso"),
    ("Epoch seconds", "epoch_s"),
    ("Epoch milliseconds", "epoch_ms"),
)


class ImportWizard(QDialog):
    """Choose a file, map its columns, and prove the mapping works.

    After ``exec()`` returns ``Accepted`` the caller reads :attr:`path`,
    :attr:`mapping`, :attr:`instrument` and :attr:`timeframe`.
    """

    def __init__(self, instruments: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import Market Data")
        self.resize(1080, 780)

        self._instruments = instruments
        self._profile: Any = None
        self._validated = False

        self.path: str = ""
        self.mapping: ColumnMapping = ColumnMapping()
        self.instrument: Instrument | None = None
        self.timeframe: Timeframe | None = None

        self._build_ui()
        self._set_status("Choose a CSV file to begin.", PALETTE.text_dim)
        self._update_ok()

    # -- construction ----------------------------------------------------

    def _build_ui(self) -> None:
        from ..icons import icon

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(9)

        # -- file ---------------------------------------------------------
        file_row = QHBoxLayout()
        file_row.setSpacing(7)
        label = QLabel("CSV file")
        label.setFont(Fonts.body(9))
        label.setStyleSheet(f"color:{PALETTE.text_dim};")
        file_row.addWidget(label)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Choose a file, or paste a path here")
        self.path_edit.editingFinished.connect(
            lambda: self._load_file(self.path_edit.text().strip()))
        file_row.addWidget(self.path_edit, 1)
        browse = QPushButton("  Browse…")
        browse.setIcon(icon("folder-open", 15))
        browse.clicked.connect(self._browse)
        file_row.addWidget(browse)
        outer.addLayout(file_row)

        self.detected = QLabel("")
        self.detected.setFont(Fonts.numeric(8))
        self.detected.setStyleSheet(f"color:{PALETTE.text_muted};")
        self.detected.setWordWrap(True)
        outer.addWidget(self.detected)

        # -- preview ------------------------------------------------------
        preview_card = Card("File Preview")
        self.preview = QTableWidget(0, 0)
        self.preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.preview.setFont(Fonts.numeric(8))
        self.preview.setShowGrid(False)
        self.preview.setMinimumHeight(180)
        self.preview.verticalHeader().setDefaultSectionSize(20)
        self.preview.horizontalHeader().setStretchLastSection(True)
        preview_card.add(self.preview)
        outer.addWidget(preview_card, 1)

        # -- mapping + options --------------------------------------------
        columns = QHBoxLayout()
        columns.setSpacing(9)

        map_card = Card("Column Mapping")
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(5)
        self._column_boxes: dict[str, QComboBox] = {}
        fields = (("datetime", "Date / time", "One column holding the bar's timestamp"),
                  ("date", "Date column", "Use with a separate time column"),
                  ("time", "Time column", "Use with a separate date column"),
                  ("open", "Open", ""), ("high", "High", ""),
                  ("low", "Low", ""), ("close", "Close (required)", ""),
                  ("volume", "Volume", "Optional; missing volume is imported as zero"))
        for row, (key, text, tip) in enumerate(fields):
            name = QLabel(text)
            name.setFont(Fonts.body(9))
            name.setStyleSheet(f"color:{PALETTE.text_dim};")
            if tip:
                name.setToolTip(tip)
            box = _SteadyComboBox()
            box.currentIndexChanged.connect(self._on_mapping_changed)
            if tip:
                box.setToolTip(tip)
            grid.addWidget(name, row, 0)
            grid.addWidget(box, row, 1)
            grid.setColumnStretch(1, 1)
            self._column_boxes[key] = box
        map_card.add_layout(grid)
        columns.addWidget(map_card, 1)

        opt_card = Card("Parsing Options")
        form = QFormLayout()
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(5)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.format_box = _SteadyComboBox()
        self.format_box.setEditable(True)
        for text, value in _FORMATS:
            self.format_box.addItem(text, value)
        self.format_box.setToolTip(
            "A Python strftime pattern, or one of the presets. Leave on "
            "'Detect automatically' unless the guess is wrong.")
        self.format_box.currentIndexChanged.connect(self._on_mapping_changed)
        self.format_box.lineEdit().editingFinished.connect(self._on_mapping_changed)
        form.addRow(self._label("Timestamp format"), self.format_box)

        self.timezone_box = _SteadyComboBox()
        self.timezone_box.setEditable(True)
        for zone in _TIMEZONES:
            self.timezone_box.addItem(zone)
        self.timezone_box.setToolTip(
            "The timezone the file's timestamps are written in. Timestamps that "
            "already carry an offset ignore this and are converted from it.")
        self.timezone_box.currentIndexChanged.connect(self._on_mapping_changed)
        form.addRow(self._label("Source timezone"), self.timezone_box)

        self.dayfirst = QCheckBox("Dates are day first (31/12/2023)")
        self.dayfirst.toggled.connect(self._on_mapping_changed)
        form.addRow("", self.dayfirst)

        self.decimal_box = _SteadyComboBox()
        self.decimal_box.addItem("Point   1234.56", ".")
        self.decimal_box.addItem("Comma   1234,56", ",")
        self.decimal_box.currentIndexChanged.connect(self._on_mapping_changed)
        form.addRow(self._label("Decimal separator"), self.decimal_box)

        self.thousands_box = _SteadyComboBox()
        self.thousands_box.addItem("None", "")
        self.thousands_box.addItem("Comma   1,234", ",")
        self.thousands_box.addItem("Point   1.234", ".")
        self.thousands_box.addItem("Space   1 234", " ")
        self.thousands_box.currentIndexChanged.connect(self._on_mapping_changed)
        form.addRow(self._label("Thousands separator"), self.thousands_box)

        opt_card.add_layout(form)
        opt_card.add(hline())

        inst_row = QHBoxLayout()
        inst_row.setSpacing(6)
        self.instrument_box = _SteadyComboBox()
        self.instrument_box.setToolTip(
            "The instrument decides tick size and point value, which decide "
            "what a price move is worth in cash.")
        self.instrument_box.currentIndexChanged.connect(self._on_instrument_changed)
        inst_row.addWidget(self.instrument_box, 1)
        new_inst = QPushButton("New…")
        new_inst.setObjectName("Ghost")
        new_inst.setToolTip("Define an instrument this file needs")
        new_inst.clicked.connect(self._new_instrument)
        inst_row.addWidget(new_inst)
        opt_card.add(self._label("Instrument"))
        opt_card.add_layout(inst_row)

        self.instrument_detail = QLabel("")
        self.instrument_detail.setFont(Fonts.numeric(8))
        self.instrument_detail.setStyleSheet(f"color:{PALETTE.text_muted};")
        self.instrument_detail.setWordWrap(True)
        opt_card.add(self.instrument_detail)

        columns.addWidget(opt_card, 1)
        outer.addLayout(columns)

        # -- status + buttons ---------------------------------------------
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setFont(Fonts.body(9))
        self.status.setMinimumHeight(34)
        self.status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        outer.addWidget(self.status)

        buttons = QHBoxLayout()
        self.detect_button = QPushButton("  Auto-detect columns")
        self.detect_button.setIcon(icon("search", 15))
        self.detect_button.setToolTip(
            "Read the file again and work out the columns from the values: "
            "which one holds the timestamps, which four are the candle, and "
            "which holds a volume that is not all zeros.")
        self.detect_button.clicked.connect(self._auto_detect)
        buttons.addWidget(self.detect_button)
        self.validate_button = QPushButton("  Validate")
        self.validate_button.setIcon(icon("check", 15))
        self.validate_button.setToolTip(
            f"Parse the first {VALIDATE_ROWS} rows with these settings")
        self.validate_button.clicked.connect(self._validate)
        buttons.addWidget(self.validate_button)
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self.ok_button = QPushButton("Import")
        self.ok_button.setObjectName("Primary")
        self.ok_button.setDefault(True)
        self.ok_button.clicked.connect(self._accept)
        buttons.addWidget(self.ok_button)
        outer.addLayout(buttons)

        self._refresh_instruments()

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setFont(Fonts.body(9))
        label.setStyleSheet(f"color:{PALETTE.text_dim};")
        return label

    # -- file handling ---------------------------------------------------

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a market data file", self.path_edit.text() or "",
            "Data files (*.csv *.txt *.tsv *.csv.gz *.gz);;All files (*)")
        if path:
            self._load_file(path)

    def _load_file(self, path: str) -> None:
        if not path:
            return
        if not Path(path).is_file():
            self._set_status(f"There is no file at {path}.", PALETTE.danger)
            return
        self.path_edit.setText(path)
        self.path = path
        try:
            self._profile = sniff_csv(path)
        except Exception as exc:            # sniff_csv is documented never to raise
            log.exception("Sniffing failed")
            self._set_status(f"This file could not be inspected: {exc}",
                             PALETTE.danger)
            return

        self._describe_profile()
        self._fill_preview()
        self._fill_columns()
        self._apply_profile_options()
        self._validated = False
        self._update_ok()
        if self._profile.problems:
            self._set_status("  ".join(self._profile.problems[:3]), PALETTE.warning)
        else:
            self._set_status(
                "Check the mapping below, then press Validate.", PALETTE.text_dim)

    def _describe_profile(self) -> None:
        p = self._profile
        size_mb = (p.file_size or 0) / (1024 * 1024)
        delimiter = {",": "comma", ";": "semicolon", "\t": "tab",
                     "|": "pipe"}.get(p.delimiter, repr(p.delimiter))
        self.detected.setText(
            f"{Path(p.path).name} · {size_mb:,.1f} MB · about {p.row_estimate:,} rows"
            f" · {delimiter}-separated · "
            f"{'header row detected' if p.has_header else 'no header row'}"
            f" · {p.encoding}"
            + (f" · timestamps look like {p.datetime_format}" if p.datetime_format else ""))

    def _fill_preview(self) -> None:
        rows = list(self._profile.sample_rows or [])[:60]
        width = max((len(r) for r in rows), default=0)
        self.preview.clear()
        self.preview.setRowCount(len(rows))
        self.preview.setColumnCount(width)
        headers = list(self._profile.headers or [])
        headers += [f"Column {i + 1}" for i in range(len(headers), width)]
        self.preview.setHorizontalHeaderLabels(
            [f"{h}\n·" for h in headers[:width]])
        self.preview.setVerticalHeaderLabels([str(i + 1) for i in range(len(rows))])
        for r, row in enumerate(rows):
            for c in range(width):
                text = str(row[c]) if c < len(row) else ""
                item = QTableWidgetItem(text)
                if r == 0 and self._profile.has_header:
                    item.setForeground(Qt.GlobalColor.white)
                self.preview.setItem(r, c, item)
        self.preview.resizeColumnsToContents()

    def _column_choices(self) -> list[tuple[str, str]]:
        """``(display, reference)`` for every column, plus the 'none' entry.

        The loader accepts a header name or a stringified index, so a headerless
        file still maps cleanly.
        """
        p = self._profile
        out: list[tuple[str, str]] = [(_NONE, "")]
        headers = list(p.headers or [])
        count = p.column_count or len(headers)
        for index in range(count):
            display = (str(headers[index]) if index < len(headers) and headers[index]
                       else f"Column {index + 1}")
            # A headerless file has display names but no *names*: the loader
            # addresses its columns by index, and so must the mapping, or the
            # sniffer's own guess will not match anything in this combo.
            reference = str(headers[index]) if (p.has_header and index < len(headers)
                                                and headers[index]) else str(index)
            out.append((display, reference))
        return out

    def _fill_columns(self, mapping: ColumnMapping | None = None) -> None:
        choices = self._column_choices()
        guess = mapping if mapping is not None else self._profile.mapping
        for key, box in self._column_boxes.items():
            box.blockSignals(True)
            box.clear()
            for display, value in choices:
                box.addItem(display, value)
            box.setCurrentIndex(self._choice_index(box, getattr(guess, key, None)))
            box.blockSignals(False)
        self._annotate_preview()

    def _choice_index(self, box: QComboBox, wanted: Any) -> int:
        """Which entry of *box* a mapping reference means.

        ``findData`` alone is not enough: a mapping may address a column by
        name where the combo holds indices, or the other way round, and a
        silent fall back to "none" would look exactly like a column the
        sniffer failed to find.  The loader resolves a reference either way,
        so this resolves it the same way the loader will.
        """
        if wanted in (None, ""):
            return 0
        found = box.findData(str(wanted))
        if found >= 0:
            return found
        headers = [str(h) for h in (self._profile.headers or [])]
        index = resolve_column(headers, str(wanted))
        if index is not None and 0 <= index + 1 < box.count():
            return index + 1
        return 0

    def _annotate_preview(self) -> None:
        """Write each column's mapped field into the preview header.

        Reading a mapping off eight combo boxes and checking it against the
        rows above them is exactly the kind of cross-referencing people get
        wrong.  Putting the field on the column says it once, where the values
        are.
        """
        if self._profile is None:
            return
        assigned: dict[int, list[str]] = {}
        headers = [str(h) for h in (self._profile.headers or [])]
        for key, box in self._column_boxes.items():
            reference = box.currentData()
            if not reference:
                continue
            index = resolve_column(headers, str(reference))
            if index is None:
                continue
            assigned.setdefault(index, []).append(_FIELD_LABELS.get(key, key))
        labels: list[str] = []
        for index in range(self.preview.columnCount()):
            name = (headers[index] if index < len(headers)
                    else f"Column {index + 1}")
            fields = assigned.get(index)
            labels.append(f"{name}\n{' + '.join(fields)}" if fields
                          else f"{name}\n·")
        self.preview.setHorizontalHeaderLabels(labels)

    def _apply_profile_options(self) -> None:
        p = self._profile
        self.format_box.blockSignals(True)
        index = self.format_box.findData(p.datetime_format or "")
        if index >= 0:
            self.format_box.setCurrentIndex(index)
        elif p.datetime_format:
            self.format_box.setEditText(p.datetime_format)
        else:
            self.format_box.setCurrentIndex(0)
        self.format_box.blockSignals(False)

        self.timezone_box.blockSignals(True)
        zone = getattr(p.mapping, "timezone", "") or "UTC"
        pos = self.timezone_box.findText(zone)
        if pos >= 0:
            self.timezone_box.setCurrentIndex(pos)
        else:
            self.timezone_box.setEditText(zone)
        self.timezone_box.blockSignals(False)

        for widget, value, attribute in (
                (self.decimal_box, p.decimal or ".", "currentIndex"),
                (self.thousands_box, p.thousands or "", "currentIndex")):
            widget.blockSignals(True)
            found = widget.findData(value)
            widget.setCurrentIndex(max(0, found))
            widget.blockSignals(False)

        self.dayfirst.blockSignals(True)
        self.dayfirst.setChecked(bool(p.dayfirst))
        self.dayfirst.setText(
            "Dates are day first (31/12/2023)"
            + ("  — proven by the data" if getattr(p, "dayfirst_proven", False)
               else ""))
        self.dayfirst.blockSignals(False)

    # -- instruments -----------------------------------------------------

    def _refresh_instruments(self, select: str = "") -> None:
        self.instrument_box.blockSignals(True)
        self.instrument_box.clear()
        try:
            items = self._instruments.all()
        except BacktesterError:
            items = []
        for inst in items:
            self.instrument_box.addItem(f"{inst.symbol} — {inst.name}", inst.symbol)
        index = self.instrument_box.findData(select) if select else -1
        self.instrument_box.setCurrentIndex(max(0, index))
        self.instrument_box.blockSignals(False)
        self._on_instrument_changed()

    def _on_instrument_changed(self) -> None:
        symbol = self.instrument_box.currentData()
        if not symbol:
            self.instrument = None
            self.instrument_detail.setText("")
            return
        try:
            self.instrument = self._instruments.get(symbol)
        except BacktesterError:
            self.instrument = None
            return
        i = self.instrument
        self.instrument_detail.setText(
            f"tick {i.tick_size:g} · point value {i.point_value:g} {i.currency} "
            f"per point per unit · lot {i.lot_size:g} · {i.price_decimals} dp · "
            f"{i.timezone}")
        # A file's own timezone is usually the instrument's session timezone.
        if self._profile is not None and not getattr(
                self._profile.mapping, "timezone", ""):
            pos = self.timezone_box.findText(i.timezone)
            if pos >= 0:
                self.timezone_box.setCurrentIndex(pos)
        self._invalidate()

    def _new_instrument(self) -> None:
        dialog = _NewInstrumentDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.instrument is None:
            return
        try:
            self._instruments.add(dialog.instrument)
            self._instruments.save()
        except BacktesterError as exc:
            show_error(self, exc)
            return
        self._refresh_instruments(dialog.instrument.symbol)

    # -- mapping and validation ------------------------------------------

    def _on_mapping_changed(self, *_args) -> None:
        self._invalidate()

    def _invalidate(self) -> None:
        if self._validated:
            self._set_status("The settings changed. Press Validate again.",
                             PALETTE.text_dim)
        self._validated = False
        self._update_ok()

    def _build_mapping(self) -> ColumnMapping:
        p = self._profile
        raw_format = self.format_box.currentData()
        if raw_format is None or self.format_box.currentText() not in \
                [text for text, _ in _FORMATS]:
            raw_format = self.format_box.currentText().strip()
        if raw_format in ("", "Detect automatically"):
            raw_format = None

        mapping = ColumnMapping(
            datetime=self._column_boxes["datetime"].currentData() or None,
            date=self._column_boxes["date"].currentData() or None,
            time=self._column_boxes["time"].currentData() or None,
            open=self._column_boxes["open"].currentData() or None,
            high=self._column_boxes["high"].currentData() or None,
            low=self._column_boxes["low"].currentData() or None,
            close=self._column_boxes["close"].currentData() or None,
            volume=self._column_boxes["volume"].currentData() or None,
            datetime_format=raw_format,
            timezone=self.timezone_box.currentText().strip() or "UTC",
            decimal=self.decimal_box.currentData() or ".",
            thousands=self.thousands_box.currentData() or "",
            dayfirst=self.dayfirst.isChecked(),
        )
        # Carry the file-level settings the sniffer worked out.
        for attribute in ("delimiter", "has_header", "encoding", "comment_char",
                          "skip_rows"):
            if hasattr(mapping, attribute) and p is not None:
                setattr(mapping, attribute, getattr(p, attribute, None))
        return mapping

    def _validate(self, prefix_message: str = "") -> None:
        """Parse a prefix of the file with the settings on screen.

        If that fails, the mapping is checked against the values and, when the
        two disagree, corrected and tried once more.  A wrong mapping is the
        single most common reason an import fails, and the file itself holds
        the evidence for what the right one is -- so the dialog uses it rather
        than handing the user a parse error and a grid of eight combo boxes.
        """
        if self._profile is None:
            self._set_status("Choose a file first.", PALETTE.warning)
            return
        if self.instrument is None:
            self._set_status("Choose an instrument, or create one.", PALETTE.warning)
            return

        mapping = self._build_mapping()
        if not (mapping.datetime or (mapping.date and mapping.time) or mapping.date):
            self._set_status(
                "Map a date/time column, or a separate date and time pair, so "
                "the bars can be placed in time.", PALETTE.danger)
            return
        if not mapping.close:
            self._set_status(
                "Map the closing-price column. Nothing can substitute for it.",
                PALETTE.danger)
            return

        bars, failure = self._try_load(mapping)
        repaired: list[str] = []
        if bars is None:
            candidate, changes = self._repair_mapping(mapping)
            if changes:
                retry, retry_failure = self._try_load(candidate)
                if retry is not None:
                    bars, mapping, repaired = retry, candidate, changes
                    self._apply_mapping(mapping)
                else:
                    log.info("Repaired mapping also failed: %s", retry_failure)
        if bars is None:
            self._validated = False
            self._update_ok()
            self._set_status(failure, PALETTE.danger)
            return

        self.mapping = mapping
        self.timeframe = bars.timeframe
        self._validated = True
        self._update_ok()

        import pandas as pd

        first = pd.Timestamp(bars.start_ts, tz="UTC")
        last = pd.Timestamp(bars.end_ts, tz="UTC")
        warnings = list(bars.meta.get("warnings") or [])
        message = (
            f"{prefix_message}Parsed {len(bars):,} of the first "
            f"{VALIDATE_ROWS:,} rows. Timeframe looks like "
            f"{bars.timeframe.display_name}. First bar {first:%Y-%m-%d %H:%M} "
            f"UTC, last {last:%Y-%m-%d %H:%M} UTC.")
        if repaired:
            self._set_status(
                "The column mapping did not match the file and was corrected: "
                + "  ".join(repaired) + "  " + message, PALETTE.warning)
        elif warnings:
            self._set_status(message + "  " + "  ".join(warnings[:2]),
                             PALETTE.warning)
        else:
            self._set_status(message + "  Ready to import.", PALETTE.success)

    def _try_load(self, mapping: ColumnMapping) -> tuple[Any, str]:
        """Parse the prefix with *mapping*: ``(bars, "")`` or ``(None, why)``."""
        prefix = _write_prefix(self.path, VALIDATE_ROWS,
                               getattr(self._profile, "encoding", "utf-8"))
        try:
            return load_csv(prefix, mapping, self.instrument), ""
        except CsvImportError as exc:
            detail = f"\n{exc.detail}" if exc.detail else ""
            return None, f"{exc.user_message}{detail}"
        except BacktesterError as exc:
            return None, exc.user_message
        except Exception as exc:            # pragma: no cover - defensive
            log.exception("Validation failed unexpectedly")
            return None, f"This file could not be read: {exc}"
        finally:
            import shutil

            shutil.rmtree(Path(prefix).parent, ignore_errors=True)

    def _auto_detect(self) -> None:
        """Re-read the file and take the mapping the values imply.

        This is the same code path the dialog uses when a file is first
        chosen, so pressing it can only ever produce a mapping the importer
        itself would have produced -- there is no second, parallel guesser to
        disagree with the first.
        """
        if self._profile is None or not self.path:
            self._set_status("Choose a file first.", PALETTE.warning)
            return
        try:
            self._profile = sniff_csv(self.path)
        except Exception as exc:            # pragma: no cover - defensive
            log.exception("Re-sniffing failed")
            self._set_status(f"This file could not be inspected: {exc}",
                             PALETTE.danger)
            return
        self._describe_profile()
        self._fill_preview()
        self._fill_columns()
        self._apply_profile_options()
        self._validated = False
        self._update_ok()
        notes = list(self._profile.problems or [])
        if self.instrument is not None:
            self._validate(prefix_message="Columns detected from the file. ")
        elif notes:
            self._set_status("  ".join(notes[:3]), PALETTE.warning)
        else:
            self._set_status("Columns detected from the file. Press Validate.",
                             PALETTE.text_dim)

    def _repair_mapping(self, mapping: ColumnMapping) -> tuple[ColumnMapping, list[str]]:
        """Check a mapping against the sample rows and correct what is wrong.

        Returns the mapping to try instead and the sentences describing every
        change.  An empty list means the mapping already agreed with the data
        and nothing was touched.
        """
        candidate = ColumnMapping.from_dict(mapping.to_dict())
        try:
            audit = audit_mapping(candidate, self._profile.headers or [],
                                  self._profile.sample_rows or [],
                                  bool(self._profile.has_header))
        except Exception:                   # pragma: no cover - defensive
            log.exception("Column audit failed")
            return mapping, []
        return audit.mapping, list(audit.changes)

    def _apply_mapping(self, mapping: ColumnMapping) -> None:
        """Show *mapping* in the combo boxes without re-reading the file."""
        self._fill_columns(mapping)

    def _set_status(self, text: str, colour: str) -> None:
        self.status.setText(text)
        self.status.setStyleSheet(f"color:{colour};")

    def _update_ok(self) -> None:
        self.ok_button.setEnabled(self._validated)
        self.ok_button.setToolTip(
            "" if self._validated else "Press Validate first")

    def _accept(self) -> None:
        if not self._validated:
            self._validate()
            if not self._validated:
                return
        self.accept()


def _write_prefix(path: str, rows: int, encoding: str) -> str:
    """Copy the first ``rows`` data lines of a file to a temporary file.

    Validating against a prefix keeps the dialog instant on a very large file
    while still exercising the real loader on real bytes -- which is the point:
    a validator that reimplements the parser proves nothing about the parser.
    """
    import tempfile

    # Keep the original file name: the loader's error messages name the file,
    # and "row 3 of tmp8s2k1.csv" would tell the user nothing.
    from ...data.csv_loader import open_text

    directory = tempfile.mkdtemp(prefix="tb-validate-")
    source_name = Path(path)
    name = source_name.name or "data.csv"
    # The prefix is written as plain text, so a compressed source must lose its
    # suffix or the loader will try to decompress a file that is not compressed.
    for suffix in (".gz", ".bz2", ".xz", ".lzma"):
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
            break
    target = Path(directory) / (name or "data.csv")
    written = 0
    with open_text(source_name, encoding or "utf-8") as source, \
            open(target, "w", encoding="utf-8", newline="") as handle:
        for line in source:
            handle.write(line)
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                written += 1
            if written > rows:
                break
    return str(target)


class _NewInstrumentDialog(QDialog):
    """A compact editor for an instrument the import needs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Instrument")
        self.setMinimumWidth(430)
        self.instrument: Instrument | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(9)

        from ..widgets.common import FieldSpec, FormPanel

        self.form = FormPanel([
            FieldSpec("symbol", "Symbol", "text", "MYSYM"),
            FieldSpec("name", "Name", "text", ""),
            FieldSpec("asset_class", "Asset class", "choice", AssetClass.OTHER.value,
                      choices=[(a.value.replace("_", " ").title(), a.value)
                               for a in AssetClass]),
            FieldSpec("tick_size", "Tick size", "float", 0.01, 1e-9, 1e6, 0.01, 8),
            FieldSpec("point_value", "Point value", "float", 1.0, 1e-9, 1e9, 1.0, 6,
                      tooltip="Cash change per 1.0 of price movement per unit held: "
                              "1 for a share, 20 for an NQ future, 100000 for a "
                              "standard forex lot."),
            FieldSpec("lot_size", "Lot size", "float", 1.0, 1e-9, 1e9, 1.0, 6),
            FieldSpec("price_decimals", "Price decimals", "int", 2, 0, 8, 1),
            FieldSpec("currency", "Currency", "text", "USD"),
            FieldSpec("timezone", "Session timezone", "choice", "UTC",
                      choices=[(z, z) for z in _TIMEZONES]),
        ], label_width=130)
        lay.addWidget(self.form)

        hint = QLabel(
            "Point value is the setting that decides what a price move is worth. "
            "Get it wrong and every P&L figure is wrong by the same factor.")
        hint.setWordWrap(True)
        hint.setObjectName("Hint")
        hint.setFont(Fonts.body(8))
        lay.addWidget(hint)

        self.error = QLabel("")
        self.error.setWordWrap(True)
        self.error.setStyleSheet(f"color:{PALETTE.danger};")
        self.error.setFont(Fonts.body(9))
        lay.addWidget(self.error)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        create = QPushButton("Create")
        create.setObjectName("Primary")
        create.setDefault(True)
        create.clicked.connect(self._create)
        row.addWidget(create)
        lay.addLayout(row)

    def _create(self) -> None:
        values = self.form.values()
        try:
            self.instrument = Instrument(
                symbol=str(values["symbol"]).strip(),
                name=str(values["name"]).strip() or str(values["symbol"]).strip(),
                asset_class=AssetClass(values["asset_class"]),
                tick_size=float(values["tick_size"]),
                point_value=float(values["point_value"]),
                lot_size=float(values["lot_size"]),
                price_decimals=int(values["price_decimals"]),
                currency=str(values["currency"]).strip() or "USD",
                timezone=str(values["timezone"]),
            )
        except BacktesterError as exc:
            self.error.setText(exc.user_message)
            return
        except (TypeError, ValueError) as exc:
            self.error.setText(str(exc))
            return
        self.accept()
