"""The market-data section of the left configuration panel.

Owns the dataset list, the instrument, the timeframe and the date range, and it
is the place a data-quality problem surfaces: a dataset with duplicate
timestamps or broken OHLC relationships shows a warning here before anyone runs
a backtest on it.
"""

from __future__ import annotations

from typing import Any, Sequence

from PySide6.QtCore import QDate, QDateTime, QSize, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDateEdit, QGridLayout, QHBoxLayout,
                               QLabel, QPushButton, QToolButton, QVBoxLayout,
                               QWidget)

from ...core.errors import BacktesterError
from ...core.timeframe import STANDARD_TIMEFRAMES, Timeframe
from ..theme import PALETTE, Fonts
from .common import Card, SectionLabel, hline


class DataPanel(QWidget):
    """Dataset selection, timeframe and date range."""

    datasetChanged = Signal(str)
    """Emits the dataset id, or an empty string when nothing is selected."""
    timeframeChanged = Signal(object)
    rangeChanged = Signal()
    importRequested = Signal()
    sampleRequested = Signal()
    instrumentsRequested = Signal()
    qualityRequested = Signal()
    manageRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repository: Any = None
        self._bars: Any = None
        self._source_timeframe: Timeframe | None = None
        self._loading = False
        self._build_ui()

    # -- construction ----------------------------------------------------

    def _build_ui(self) -> None:
        from ..icons import icon

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        card = Card("Market Data")
        body = card.body()

        row = QHBoxLayout()
        row.setSpacing(5)
        self.dataset_box = QComboBox()
        self.dataset_box.setMinimumWidth(140)
        self.dataset_box.setToolTip("Imported datasets in this workspace")
        self.dataset_box.currentIndexChanged.connect(self._on_dataset_changed)
        row.addWidget(self.dataset_box, 1)

        manage = QToolButton()
        manage.setIcon(icon("database", 17, PALETTE.text))
        manage.setIconSize(QSize(17, 17))
        manage.setToolTip("Manage datasets")
        manage.setFixedSize(30, 26)
        manage.clicked.connect(self.manageRequested.emit)
        row.addWidget(manage)
        card.add_layout(row)

        buttons = QHBoxLayout()
        buttons.setSpacing(5)
        imp = QPushButton("  Import CSV")
        imp.setIcon(icon("import", 15))
        imp.setToolTip("Import an OHLCV CSV file and map its columns")
        imp.clicked.connect(self.importRequested.emit)
        buttons.addWidget(imp, 1)
        sample = QPushButton("Sample")
        sample.setObjectName("Ghost")
        sample.setToolTip("Load the bundled synthetic dataset "
                          "(generated test data, not real market data)")
        sample.clicked.connect(self.sampleRequested.emit)
        buttons.addWidget(sample)
        card.add_layout(buttons)

        card.add(hline())

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(5)

        grid.addWidget(self._label("Instrument"), 0, 0)
        inst_row = QHBoxLayout()
        inst_row.setSpacing(4)
        self.instrument_label = QLabel("-")
        self.instrument_label.setFont(Fonts.numeric(9))
        inst_row.addWidget(self.instrument_label, 1)
        edit_inst = QToolButton()
        edit_inst.setIcon(icon("settings", 15, PALETTE.text))
        edit_inst.setIconSize(QSize(15, 15))
        edit_inst.setFixedSize(24, 22)
        edit_inst.setToolTip("Instrument specifications (tick size, point value, "
                             "margin, session timezone)")
        edit_inst.clicked.connect(self.instrumentsRequested.emit)
        inst_row.addWidget(edit_inst)
        grid.addLayout(inst_row, 0, 1)

        grid.addWidget(self._label("Timeframe"), 1, 0)
        self.timeframe_box = QComboBox()
        self.timeframe_box.setToolTip(
            "Bars are built up from the imported timeframe. A timeframe finer "
            "than the source data cannot be produced and is greyed out.")
        self.timeframe_box.currentIndexChanged.connect(self._on_timeframe_changed)
        grid.addWidget(self.timeframe_box, 1, 1)

        grid.addWidget(self._label("From"), 2, 0)
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDisplayFormat("yyyy-MM-dd")
        self.start_date.dateChanged.connect(self._on_range_changed)
        grid.addWidget(self.start_date, 2, 1)

        grid.addWidget(self._label("To"), 3, 0)
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDisplayFormat("yyyy-MM-dd")
        self.end_date.dateChanged.connect(self._on_range_changed)
        grid.addWidget(self.end_date, 3, 1)
        grid.setColumnStretch(1, 1)
        card.add_layout(grid)

        preset_row = QHBoxLayout()
        preset_row.setSpacing(4)
        preset_row.addWidget(self._label("Range"))
        for text, months in (("All", 0), ("1Y", 12), ("6M", 6), ("3M", 3), ("1M", 1)):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(f"Use the last {text}" if months else "Use every bar")
            b.setFixedHeight(21)
            b.clicked.connect(lambda _=False, m=months: self._apply_preset(m))
            preset_row.addWidget(b)
        preset_row.addStretch(1)
        card.add_layout(preset_row)

        card.add(hline())

        self.info_label = QLabel("No dataset loaded.")
        self.info_label.setWordWrap(True)
        self.info_label.setFont(Fonts.numeric(8))
        self.info_label.setStyleSheet(f"color:{PALETTE.text_muted};")
        card.add(self.info_label)

        quality_row = QHBoxLayout()
        quality_row.setSpacing(5)
        self.quality_label = QLabel("")
        self.quality_label.setWordWrap(True)
        self.quality_label.setFont(Fonts.body(8))
        quality_row.addWidget(self.quality_label, 1)
        self.quality_btn = QToolButton()
        self.quality_btn.setText("Report")
        self.quality_btn.setToolTip("Show the full data quality report")
        self.quality_btn.clicked.connect(self.qualityRequested.emit)
        self.quality_btn.hide()
        quality_row.addWidget(self.quality_btn)
        card.add_layout(quality_row)

        lay.addWidget(card)

    @staticmethod
    def _label(text: str) -> QLabel:
        lab = QLabel(text)
        lab.setFont(Fonts.body(9))
        lab.setStyleSheet(f"color:{PALETTE.text_dim};")
        return lab

    # -- repository ------------------------------------------------------

    def set_repository(self, repository: Any) -> None:
        self._repository = repository
        self.refresh_datasets()

    def refresh_datasets(self, select_id: str | None = None) -> None:
        """Reload the dataset list, keeping the current selection where possible."""
        if self._repository is None:
            return
        keep = select_id or self.current_dataset_id()
        self._loading = True
        try:
            self.dataset_box.clear()
            try:
                items = self._repository.list()
            except BacktesterError:
                items = []
            if not items:
                self.dataset_box.addItem("No datasets — import a CSV", "")
                self.dataset_box.setEnabled(False)
            else:
                self.dataset_box.setEnabled(True)
                for meta in items:
                    label = f"{meta.symbol}  {meta.timeframe}  ·  {meta.bar_count:,} bars"
                    self.dataset_box.addItem(label, meta.id)
                    self.dataset_box.setItemData(
                        self.dataset_box.count() - 1,
                        f"{meta.name}\n{meta.source_path}", Qt.ItemDataRole.ToolTipRole)
            idx = self.dataset_box.findData(keep) if keep else -1
            self.dataset_box.setCurrentIndex(max(0, idx))
        finally:
            self._loading = False
        self._on_dataset_changed()

    def current_dataset_id(self) -> str:
        return self.dataset_box.currentData() or ""

    # -- bars ------------------------------------------------------------

    def set_bars(self, bars: Any, quality: Any = None,
                 reset_timeframe: bool = True) -> None:
        """Show the loaded source bars and populate the timeframe choices.

        ``reset_timeframe`` selects the dataset's own timeframe rather than
        keeping whatever was chosen for the previous dataset.  Without it,
        loading 5-minute data straight after daily data silently resamples the
        new dataset to daily and the user sees 257 bars where they expected
        twenty thousand.
        """
        self._bars = bars
        if bars is None:
            self.instrument_label.setText("-")
            self.info_label.setText("No dataset loaded.")
            self.quality_label.setText("")
            self.quality_btn.hide()
            self.timeframe_box.clear()
            return

        inst = bars.instrument
        self.instrument_label.setText(
            f"{inst.symbol}  ·  {inst.currency}  ·  ×{inst.point_value:g}")
        self.instrument_label.setToolTip(
            f"{inst.name}\nAsset class: {inst.asset_class.value}\n"
            f"Tick size: {inst.tick_size:g}\nPoint value: {inst.point_value:g} "
            f"{inst.currency} per point per unit\nLot size: {inst.lot_size:g}\n"
            f"Session timezone: {inst.timezone}")

        self._source_timeframe = bars.timeframe
        self._populate_timeframes(bars.timeframe, keep_current=not reset_timeframe)
        self._populate_dates(bars)
        self.info_label.setText(bars.describe())
        self._show_quality(quality)

    def _populate_timeframes(self, source: Timeframe,
                             keep_current: bool = False) -> None:
        self._loading = True
        try:
            current = self.timeframe_box.currentData() if keep_current else None
            self.timeframe_box.clear()
            options: list[Timeframe] = []
            if source not in STANDARD_TIMEFRAMES:
                options.append(source)
            options.extend(tf for tf in STANDARD_TIMEFRAMES if tf.can_build_from(source))
            if not options:
                options = [source]
            for tf in options:
                suffix = "  (source)" if tf == source else ""
                self.timeframe_box.addItem(f"{tf.display_name}{suffix}", tf)
            idx = -1
            if current is not None:
                idx = self.timeframe_box.findData(current)
            if idx < 0:
                idx = self.timeframe_box.findData(source)
            self.timeframe_box.setCurrentIndex(max(0, idx))
        finally:
            self._loading = False

    def _populate_dates(self, bars: Any) -> None:
        import pandas as pd

        self._loading = True
        try:
            start = pd.Timestamp(bars.start_ts, tz="UTC")
            end = pd.Timestamp(bars.end_ts, tz="UTC")
            qstart = QDate(start.year, start.month, start.day)
            qend = QDate(end.year, end.month, end.day)
            for edit in (self.start_date, self.end_date):
                edit.setDateRange(qstart, qend)
            self.start_date.setDate(qstart)
            self.end_date.setDate(qend)
        finally:
            self._loading = False

    def _show_quality(self, quality: Any) -> None:
        if quality is None:
            self.quality_label.setText("")
            self.quality_btn.hide()
            return
        errors = len(getattr(quality, "errors", []) or [])
        warnings = len(getattr(quality, "warnings", []) or [])
        self.quality_btn.setVisible(bool(errors or warnings))
        if errors:
            self.quality_label.setText(
                f"<span style='color:{PALETTE.danger}'>⚠ {errors} data problem"
                f"{'s' if errors != 1 else ''} found</span>")
        elif warnings:
            self.quality_label.setText(
                f"<span style='color:{PALETTE.warning}'>{warnings} data warning"
                f"{'s' if warnings != 1 else ''}</span>")
        else:
            self.quality_label.setText(
                f"<span style='color:{PALETTE.success}'>Data checks passed</span>")
            self.quality_btn.show()

    # -- selection -------------------------------------------------------

    def current_timeframe(self) -> Timeframe | None:
        return self.timeframe_box.currentData()

    def date_range_ns(self) -> tuple[int | None, int | None]:
        """The chosen range as UTC nanoseconds, end-of-day inclusive."""
        import pandas as pd

        if self._bars is None:
            return (None, None)
        s = self.start_date.date()
        e = self.end_date.date()
        start = pd.Timestamp(year=s.year(), month=s.month(), day=s.day(), tz="UTC")
        end = (pd.Timestamp(year=e.year(), month=e.month(), day=e.day(), tz="UTC")
               + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1))
        return (int(start.value), int(end.value))

    def _apply_preset(self, months: int) -> None:
        if self._bars is None:
            return
        import pandas as pd

        end = pd.Timestamp(self._bars.end_ts, tz="UTC")
        if months <= 0:
            start = pd.Timestamp(self._bars.start_ts, tz="UTC")
        else:
            start = max(pd.Timestamp(self._bars.start_ts, tz="UTC"),
                        end - pd.DateOffset(months=months))
        self._loading = True
        try:
            self.start_date.setDate(QDate(start.year, start.month, start.day))
            self.end_date.setDate(QDate(end.year, end.month, end.day))
        finally:
            self._loading = False
        self.rangeChanged.emit()

    # -- signals ---------------------------------------------------------

    def _on_dataset_changed(self, *_args) -> None:
        if not self._loading:
            self.datasetChanged.emit(self.current_dataset_id())

    def _on_timeframe_changed(self, *_args) -> None:
        if not self._loading:
            tf = self.current_timeframe()
            if tf is not None:
                self.timeframeChanged.emit(tf)

    def _on_range_changed(self, *_args) -> None:
        if self._loading:
            return
        # Keep the two dates ordered rather than letting the user create an
        # empty range and then be told it is empty.
        if self.start_date.date() > self.end_date.date():
            self._loading = True
            try:
                self.end_date.setDate(self.start_date.date())
            finally:
                self._loading = False
        self.rangeChanged.emit()
