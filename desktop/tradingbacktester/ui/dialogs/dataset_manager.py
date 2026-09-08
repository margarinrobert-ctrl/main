"""The dataset library manager.

Imported datasets accumulate: a user tries three exports of the same symbol
before one of them maps cleanly, and a year later the workspace holds forty
files nobody can tell apart.  This dialog is where they are named, inspected and
deleted, and it reports the disk space the library is using because that is the
usual reason somebody comes looking.

Every action here goes through :class:`~tradingbacktester.data.repository.DatasetRepository`,
which persists immediately; there is no "save" button and nothing to lose by
closing the window.
"""

from __future__ import annotations

import logging
from pathlib import Path
import pandas as pd
from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QBrush, QColor, QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout,
                               QHeaderView, QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ...core.errors import BacktesterError
from ...data.repository import DatasetMeta, DatasetRepository
from ..theme import PALETTE, Fonts
from ..widgets.common import ask_text, confirm, show_error, show_info, show_warning

log = logging.getLogger(__name__)

_COLUMNS: tuple[str, ...] = ("Name", "Symbol", "Timeframe", "Bars", "First bar",
                             "Last bar", "Size", "Source")


def _format_size(num_bytes: float) -> str:
    """Bytes as a short human string: ``834 KB``, ``1.9 MB``."""
    value = float(max(0.0, num_bytes))
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024.0 or unit == "GB":
            decimals = 0 if unit == "B" or value >= 100 else 1
            return f"{value:,.{decimals}f} {unit}"
        value /= 1024.0
    return f"{value:,.1f} GB"  # pragma: no cover - unreachable, keeps mypy happy


def _format_stamp(ts_ns: int, bar_count: int) -> str:
    """A UTC timestamp for the table, or ``-`` for an empty dataset."""
    if not bar_count:
        return "-"
    return f"{pd.Timestamp(int(ts_ns), tz='UTC'):%Y-%m-%d %H:%M}"


class _SortItem(QTableWidgetItem):
    """A table cell that sorts on a number while displaying formatted text.

    Without this, ``1,000,000 bars`` sorts before ``9,999`` because Qt compares
    the displayed strings.
    """

    def __init__(self, text: str, key: float) -> None:
        super().__init__(text)
        self._key = float(key)
        self.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, _SortItem):
            return self._key < other._key
        return super().__lt__(other)  # pragma: no cover - mixed columns never occur


class DatasetManagerDialog(QDialog):
    """Browse, rename, delete and locate the datasets in this workspace."""

    def __init__(self, repository: DatasetRepository,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repo = repository
        self._metas: list[DatasetMeta] = []
        self.setWindowTitle("Manage Datasets")
        self.setMinimumSize(940, 520)
        self._build_ui()
        self._reload()

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        from ..icons import icon

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(9)

        head = QHBoxLayout()
        head.setSpacing(10)
        title = QLabel("Imported datasets")
        title.setFont(Fonts.heading(12))
        head.addWidget(title)
        head.addStretch(1)
        self.total_label = QLabel("")
        self.total_label.setFont(Fonts.numeric(9))
        self.total_label.setStyleSheet(f"color:{PALETTE.text_dim};")
        head.addWidget(self.total_label)
        lay.addLayout(head)

        path_label = QLabel(f"Stored in {self._repo.dir}")
        path_label.setObjectName("Hint")
        path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(path_label)

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(list(_COLUMNS))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(_COLUMNS) - 1):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(len(_COLUMNS) - 1,
                                    QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(len(_COLUMNS) - 1, 200)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.itemDoubleClicked.connect(lambda *_: self._rename())
        lay.addWidget(self.table, 1)

        self.empty_label = QLabel(
            "No datasets yet. Close this window and use Import CSV to add one.")
        self.empty_label.setObjectName("Hint")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.empty_label)

        self.detail_label = QLabel("")
        self.detail_label.setObjectName("Hint")
        self.detail_label.setWordWrap(True)
        self.detail_label.setMinimumHeight(30)
        lay.addWidget(self.detail_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.rename_btn = QPushButton("  Rename")
        self.rename_btn.setIcon(icon("rename", 15))
        self.rename_btn.setToolTip("Change the display name of this dataset")
        self.rename_btn.clicked.connect(self._rename)
        buttons.addWidget(self.rename_btn)

        self.reveal_btn = QPushButton("  Show file")
        self.reveal_btn.setIcon(icon("folder-open", 15))
        self.reveal_btn.setToolTip(
            "Open the folder holding this dataset's source file in the "
            "system file manager")
        self.reveal_btn.clicked.connect(self._reveal)
        buttons.addWidget(self.reveal_btn)

        self.delete_btn = QPushButton("  Delete")
        self.delete_btn.setObjectName("Danger")
        self.delete_btn.setIcon(icon("trash", 15))
        self.delete_btn.setToolTip("Remove this dataset from the workspace")
        self.delete_btn.clicked.connect(self._delete)
        buttons.addWidget(self.delete_btn)

        buttons.addStretch(1)

        refresh = QPushButton("  Refresh")
        refresh.setObjectName("Ghost")
        refresh.setIcon(icon("refresh", 15))
        refresh.setIconSize(QSize(15, 15))
        refresh.setToolTip("Re-read the data folder: pick up files copied in and "
                           "forget datasets deleted outside the application")
        refresh.clicked.connect(self._refresh)
        buttons.addWidget(refresh)

        close = QPushButton("Close")
        close.setObjectName("Primary")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        lay.addLayout(buttons)

    # ------------------------------------------------------------------
    # population
    # ------------------------------------------------------------------

    def _reload(self, select_id: str = "") -> None:
        """Rebuild the table from the repository, keeping a row selected."""
        try:
            self._metas = self._repo.list()
        except BacktesterError as exc:
            show_error(self, exc)
            self._metas = []

        self.table.setSortingEnabled(False)
        self.table.clearContents()
        self.table.setRowCount(len(self._metas))
        for row, meta in enumerate(self._metas):
            self._fill_row(row, meta)
        self.table.setSortingEnabled(True)

        self.empty_label.setVisible(not self._metas)
        self.table.setVisible(bool(self._metas))

        total_bytes = sum(m.file_size for m in self._metas)
        total_bars = sum(m.bar_count for m in self._metas)
        self.total_label.setText(
            f"{len(self._metas)} dataset(s) · {total_bars:,} bars · "
            f"{_format_size(total_bytes)} on disk")

        if select_id:
            self._select_id(select_id)
        elif self._metas:
            self.table.selectRow(0)
        self._update_buttons()

    def _fill_row(self, row: int, meta: DatasetMeta) -> None:
        name = QTableWidgetItem(meta.name)
        name.setData(Qt.ItemDataRole.UserRole, meta.id)
        name.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        name.setToolTip(meta.describe())
        self.table.setItem(row, 0, name)

        symbol = QTableWidgetItem(meta.symbol)
        symbol.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        self.table.setItem(row, 1, symbol)

        timeframe = QTableWidgetItem(meta.timeframe)
        timeframe.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        self.table.setItem(row, 2, timeframe)

        bars = _SortItem(f"{meta.bar_count:,}", meta.bar_count)
        bars.setTextAlignment(int(Qt.AlignmentFlag.AlignRight |
                                  Qt.AlignmentFlag.AlignVCenter))
        self.table.setItem(row, 3, bars)

        self.table.setItem(row, 4, _SortItem(
            _format_stamp(meta.start_ts, meta.bar_count), meta.start_ts))
        self.table.setItem(row, 5, _SortItem(
            _format_stamp(meta.end_ts, meta.bar_count), meta.end_ts))

        size = _SortItem(_format_size(meta.file_size), meta.file_size)
        size.setTextAlignment(int(Qt.AlignmentFlag.AlignRight |
                                  Qt.AlignmentFlag.AlignVCenter))
        self.table.setItem(row, 6, size)

        source = QTableWidgetItem(Path(meta.source_path).name if meta.source_path
                                  else "-")
        source.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        source.setToolTip(meta.source_path or "No source file was recorded.")
        if meta.source_path and not Path(meta.source_path).exists():
            source.setForeground(QBrush(QColor(PALETTE.text_muted)))
            source.setToolTip(f"{meta.source_path}\n\nThis file is no longer "
                              f"there. The imported copy in the workspace is "
                              f"unaffected.")
        self.table.setItem(row, 7, source)

        for column in (1, 2, 3, 4, 5, 6):
            item = self.table.item(row, column)
            if item is not None:
                item.setFont(Fonts.numeric(9))

    def _select_id(self, dataset_id: str) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == dataset_id:
                self.table.selectRow(row)
                return

    # ------------------------------------------------------------------
    # selection
    # ------------------------------------------------------------------

    def _selected(self) -> DatasetMeta | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        if item is None:
            return None
        dataset_id = str(item.data(Qt.ItemDataRole.UserRole))
        return next((m for m in self._metas if m.id == dataset_id), None)

    def _update_buttons(self) -> None:
        meta = self._selected()
        for button in (self.rename_btn, self.reveal_btn, self.delete_btn):
            button.setEnabled(meta is not None)
        if meta is None:
            self.detail_label.setText("")
            return
        warnings = ""
        if meta.import_warnings:
            first = meta.import_warnings[0]
            more = (f" (+{len(meta.import_warnings) - 1} more)"
                    if len(meta.import_warnings) > 1 else "")
            warnings = f"  ·  Import note: {first}{more}"
        imported = meta.imported_at.replace("T", " ")[:19] or "unknown"
        self.detail_label.setText(
            f"{meta.describe()}  ·  imported {imported}  ·  "
            f"{meta.storage_format}{warnings}")

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------

    def _rename(self) -> None:
        meta = self._selected()
        if meta is None:
            return
        name = ask_text(self, "Rename Dataset", "New name for this dataset:",
                        meta.name)
        if name is None or name == meta.name:
            return
        try:
            self._repo.rename(meta.id, name)
        except BacktesterError as exc:
            show_error(self, exc)
            return
        log.info("Renamed dataset %s to %r", meta.id, name)
        self._reload(meta.id)

    def _delete(self) -> None:
        meta = self._selected()
        if meta is None:
            return
        if not confirm(
                self, "Delete Dataset",
                f"Delete '{meta.name}' ({meta.symbol} {meta.timeframe}, "
                f"{meta.bar_count:,} bars) from this workspace?\n\n"
                f"The imported copy is removed from the data folder. The "
                f"original file it was imported from is not touched.",
                "Delete"):
            return
        try:
            self._repo.remove(meta.id)
        except BacktesterError as exc:
            show_error(self, exc)
            return
        log.info("Deleted dataset %s (%s)", meta.id, meta.name)
        self._reload()

    def _reveal(self) -> None:
        """Open the folder holding this dataset's file in the file manager.

        The source file is what a user is usually looking for; when it has been
        moved or deleted the workspace copy is the next best thing, so that is
        offered instead of a dead end.
        """
        meta = self._selected()
        if meta is None:
            return
        target = Path(meta.source_path) if meta.source_path else None
        note = ""
        if target is None or not target.exists():
            try:
                target = self._repo.path_for(meta)
            except BacktesterError as exc:
                show_error(self, exc)
                return
            note = ("The file this dataset was imported from is no longer there, "
                    "so the workspace copy is shown instead.\n\n")
        folder = target.parent
        if not folder.exists():
            show_warning(self, "Folder Not Found",
                         f"{note}There is nothing at {folder} any more.")
            return
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        if not opened:
            # Headless machines and locked-down desktops have no file manager;
            # showing the path is still useful, so this is not an error.
            show_info(self, "File Location",
                      f"{note}This dataset's file is at:\n\n{target}",
                      detail=str(folder))
            return
        if note:
            show_info(self, "File Location", f"{note}Opened {folder}.")
        log.info("Revealed dataset file %s", target)

    def _refresh(self) -> None:
        selected = self._selected()
        try:
            self._repo.refresh()
        except BacktesterError as exc:
            show_error(self, exc)
            return
        self._reload(selected.id if selected else "")
        log.info("Dataset library refreshed: %d dataset(s)", len(self._metas))

    # ------------------------------------------------------------------
    # introspection used by tests
    # ------------------------------------------------------------------

    def datasets(self) -> list[DatasetMeta]:
        """The rows currently shown, in table order."""
        return list(self._metas)
