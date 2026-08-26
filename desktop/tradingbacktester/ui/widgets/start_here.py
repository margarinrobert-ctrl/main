"""The three things you have to do before a backtest means anything.

New users of a backtesting platform get stuck in the same place every time:
the window is full of panels, all of them look important, and none of them
says which one to touch first. This strip answers that, and then gets out of
the way -- it ticks each step off as it is done and hides itself once all
three are.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                               QWidget)

from ..theme import PALETTE, Fonts


class StartHere(QWidget):
    """A three-step checklist: data, strategy, run."""

    importRequested = Signal()
    findRequested = Signal()
    dismissed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StartHere")
        self.setStyleSheet(
            f"#StartHere {{ background: {PALETTE.panel_alt}; border: 1px solid "
            f"{PALETTE.border}; border-radius: 6px; }}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 9)
        outer.setSpacing(4)

        header = QHBoxLayout()
        title = QLabel("Start here")
        title.setFont(Fonts.body(10, bold=True))
        header.addWidget(title)
        header.addStretch(1)
        close = QPushButton("×")
        close.setFlat(True)
        close.setFixedSize(20, 20)
        close.setToolTip("Hide this. View ▸ Show Start Here brings it back.")
        close.clicked.connect(self._dismiss)
        header.addWidget(close)
        outer.addLayout(header)

        self._steps: list[QLabel] = []
        for text in ("Load some data",
                     "Pick or find a strategy",
                     "Press RUN BACKTEST"):
            label = QLabel(text)
            label.setFont(Fonts.body(9))
            label.setWordWrap(True)
            outer.addWidget(label)
            self._steps.append(label)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.import_button = QPushButton("Import a CSV")
        self.import_button.clicked.connect(self.importRequested)
        buttons.addWidget(self.import_button)
        self.find_button = QPushButton("Find strategies")
        self.find_button.setObjectName("Primary")
        self.find_button.clicked.connect(self.findRequested)
        buttons.addWidget(self.find_button)
        outer.addLayout(buttons)

        self.set_state(False, False, False)

    def set_state(self, has_data: bool, has_strategy: bool,
                  has_result: bool) -> None:
        """Tick the steps off, and hide the strip once all three are done."""
        for label, done, text in zip(
                self._steps, (has_data, has_strategy, has_result),
                ("Load some data", "Pick or find a strategy",
                 "Press RUN BACKTEST")):
            mark = "✓" if done else "•"
            colour = PALETTE.success if done else PALETTE.text_dim
            label.setText(f"{mark}  {text}")
            label.setStyleSheet(f"color:{colour};")
        if has_data and has_strategy and has_result:
            self.hide()

    def _dismiss(self) -> None:
        self.hide()
        self.dismissed.emit()
