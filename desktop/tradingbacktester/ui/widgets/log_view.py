"""A live view of the application log.

Two sources feed it: a Qt logging handler that captures records as they are
emitted, and the log file on disk so the panel is not empty when the window
opens.  It exists so a user can see what went wrong without hunting for a file,
while the file itself stays the authoritative record.
"""

from __future__ import annotations

import logging
from collections import deque
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QPlainTextEdit,
                               QPushButton, QToolButton, QVBoxLayout, QWidget)

from ..theme import PALETTE, Fonts

_LEVEL_COLOURS = {
    "DEBUG": PALETTE.text_muted,
    "INFO": PALETTE.text_dim,
    "WARNING": PALETTE.warning,
    "ERROR": PALETTE.danger,
    "CRITICAL": PALETTE.danger,
}


class _QtLogBridge(QObject, logging.Handler):
    """Turns log records into a Qt signal on the thread that emitted them.

    Multiple inheritance from ``QObject`` and ``Handler`` is what lets a record
    emitted on a worker thread reach the widget safely: the signal is queued
    across threads by Qt, so the widget is only ever touched from the GUI thread.
    """

    record = Signal(str, str)

    def __init__(self) -> None:
        QObject.__init__(self)
        logging.Handler.__init__(self)
        self.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s",
                                            datefmt="%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.record.emit(record.levelname, self.format(record))
        except Exception:  # pragma: no cover - a logging handler must never raise
            pass


class LogView(QWidget):
    """Filterable log output with a link to the file on disk."""

    MAX_LINES = 4000

    def __init__(self, log_file: Path | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._log_file = Path(log_file) if log_file else None
        self._buffer: deque[tuple[str, str]] = deque(maxlen=self.MAX_LINES)
        self._min_level = logging.INFO
        self._build_ui()
        self._install_handler()
        self._load_tail()

    def _build_ui(self) -> None:
        from ..icons import icon

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(5)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        label = QLabel("Level")
        label.setFont(Fonts.body(9))
        label.setStyleSheet(f"color:{PALETTE.text_dim};")
        bar.addWidget(label)
        self.level_box = QComboBox()
        for name in ("DEBUG", "INFO", "WARNING", "ERROR"):
            self.level_box.addItem(name.title(), getattr(logging, name))
        self.level_box.setCurrentIndex(1)
        self.level_box.currentIndexChanged.connect(self._on_level_changed)
        bar.addWidget(self.level_box)
        bar.addStretch(1)

        self.path_label = QLabel(str(self._log_file) if self._log_file else "")
        self.path_label.setFont(Fonts.numeric(8))
        self.path_label.setStyleSheet(f"color:{PALETTE.text_muted};")
        self.path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        bar.addWidget(self.path_label)

        open_btn = QToolButton()
        open_btn.setIcon(icon("folder-open", 15))
        open_btn.setIconSize(QSize(15, 15))
        open_btn.setToolTip("Open the log file")
        open_btn.clicked.connect(self._open_file)
        bar.addWidget(open_btn)

        clear = QToolButton()
        clear.setIcon(icon("trash", 15))
        clear.setIconSize(QSize(15, 15))
        clear.setToolTip("Clear this view (the file is not touched)")
        clear.clicked.connect(self.clear)
        bar.addWidget(clear)
        lay.addLayout(bar)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(self.MAX_LINES)
        self.output.setFont(Fonts.numeric(8))
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        lay.addWidget(self.output, 1)

    def _install_handler(self) -> None:
        self._bridge = _QtLogBridge()
        self._bridge.setLevel(logging.DEBUG)
        self._bridge.record.connect(self._append, Qt.ConnectionType.QueuedConnection)
        logging.getLogger().addHandler(self._bridge)

    def _load_tail(self, lines: int = 300) -> None:
        if self._log_file is None or not self._log_file.exists():
            return
        try:
            text = self._log_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        for line in text.splitlines()[-lines:]:
            level = next((lv for lv in _LEVEL_COLOURS if f" {lv} " in line), "INFO")
            self._append(level, line, from_file=True)

    # -- output ----------------------------------------------------------

    def _append(self, level: str, text: str, from_file: bool = False) -> None:
        self._buffer.append((level, text))
        if getattr(logging, level, logging.INFO) < self._min_level:
            return
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(_LEVEL_COLOURS.get(level, PALETTE.text_dim)))
        cursor.insertText(text + "\n", fmt)
        scrollbar = self.output.verticalScrollBar()
        # Only follow the tail when the user is already at the bottom, so
        # scrolling back to read something is not yanked away.
        if scrollbar.value() >= scrollbar.maximum() - 4:
            scrollbar.setValue(scrollbar.maximum())

    def _on_level_changed(self) -> None:
        self._min_level = self.level_box.currentData()
        self._rebuild()

    def _rebuild(self) -> None:
        self.output.clear()
        for level, text in list(self._buffer):
            if getattr(logging, level, logging.INFO) >= self._min_level:
                cursor = self.output.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                fmt = QTextCharFormat()
                fmt.setForeground(QColor(_LEVEL_COLOURS.get(level, PALETTE.text_dim)))
                cursor.insertText(text + "\n", fmt)

    def clear(self) -> None:
        self._buffer.clear()
        self.output.clear()

    def _open_file(self) -> None:
        if self._log_file is None:
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._log_file)))

    def closeEvent(self, event) -> None:  # noqa: N802
        logging.getLogger().removeHandler(self._bridge)
        super().closeEvent(event)
