"""The walk-forward tab of the optimiser.

A grid search always produces a winner, including on data with no edge in it,
so the number it reports is a statement about the past and not a forecast.  The
panel next to it asks the only question that turns the search into evidence:
if the parameters had been chosen on what came before, would they have made
money on what came after?

The controls are deliberately the same grid the sweep uses.  Choosing a
different grid here would answer a question about a different strategy.
"""

from __future__ import annotations

import math
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDoubleSpinBox,
                               QHBoxLayout, QHeaderView, QLabel, QProgressBar,
                               QPushButton, QSpinBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ...logging_setup import get_logger
from ..theme import PALETTE, Fonts, money, number
from ..workers import TaskRunner, walk_forward_task
from .common import show_error, show_info

log = get_logger(__name__)

#: Below this the optimisation kept so little of its in-sample profit that the
#: rest of the row is not worth reading.
WEAK_EFFICIENCY = 0.3


class WalkForwardPanel(QWidget):
    """Run a walk-forward over the optimiser's own parameter grid.

    ``ranges_fn`` returns the parameter ranges currently ticked in the sweep
    panel, and ``settings_fn`` the ranking metric and minimum trade count, so
    the two halves of the dialog can never disagree about what is being tested.
    """

    def __init__(self, bars: Any, spec: Any, config: Any,
                 ranges_fn: Callable[[], list[Any]],
                 settings_fn: Callable[[], tuple[str, int]],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bars = bars
        self._spec = spec
        self._config = config
        self._ranges_fn = ranges_fn
        self._settings_fn = settings_fn
        self._result: Any = None
        self._runner = TaskRunner(self)
        self._build()
        self._connect()

    # -- construction ----------------------------------------------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.setSpacing(8)

        explain = QLabel(
            "Choose the parameters on one block of history, trade the block "
            "that follows with them without looking, move both windows along "
            "and repeat. The out-of-sample total below is the only figure in "
            "this dialog that was not chosen with hindsight.")
        explain.setWordWrap(True)
        explain.setFont(Fonts.body(9))
        explain.setStyleSheet(f"color:{PALETTE.text_dim};")
        outer.addWidget(explain)

        controls = QHBoxLayout()
        controls.setSpacing(9)

        controls.addWidget(self._label("Folds"))
        self.folds = QSpinBox()
        self.folds.setRange(2, 24)
        self.folds.setValue(5)
        self.folds.setToolTip(
            "How many train/test pairs. More folds means shorter blocks: the "
            "out-of-sample record is longer but each optimisation sees less.")
        controls.addWidget(self.folds)

        controls.addWidget(self._label("Training share"))
        self.train = QDoubleSpinBox()
        self.train.setRange(10.0, 90.0)
        self.train.setDecimals(0)
        self.train.setSuffix(" %")
        self.train.setValue(50.0)
        self.train.setToolTip(
            "How much of the series the first training block covers. The rest "
            "is split into the test blocks.")
        controls.addWidget(self.train)

        self.anchored = QCheckBox("Anchored")
        self.anchored.setToolTip(
            "Grow the training block from the start of the data instead of "
            "sliding a fixed-length window. Anchored has more data and assumes "
            "the distant past still applies; rolling has less and adapts.")
        controls.addWidget(self.anchored)

        controls.addStretch(1)
        self.run_button = QPushButton("  RUN WALK-FORWARD")
        self.run_button.setObjectName("Primary")
        self.run_button.setMinimumHeight(30)
        controls.addWidget(self.run_button)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("Danger")
        self.cancel_button.hide()
        controls.addWidget(self.cancel_button)
        outer.addLayout(controls)

        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.hide()
        outer.addWidget(self.progress)

        self.headline = QLabel("Not run yet.")
        self.headline.setWordWrap(True)
        self.headline.setFont(Fonts.body(10, bold=True))
        self.headline.setStyleSheet(f"color:{PALETTE.text_muted};")
        outer.addWidget(self.headline)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["#", "Trained on", "Traded", "In sample", "Out of sample",
             "Trades", "Parameters chosen"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setFont(Fonts.numeric(9))
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setSectionResizeMode(
            6, QHeaderView.ResizeMode.Stretch)
        outer.addWidget(self.table, 1)

        self.notes = QLabel("")
        self.notes.setWordWrap(True)
        self.notes.setFont(Fonts.body(9))
        self.notes.setStyleSheet(f"color:{PALETTE.text_dim};")
        self.notes.setMinimumHeight(70)
        self.notes.setAlignment(Qt.AlignmentFlag.AlignTop)
        outer.addWidget(self.notes)

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setFont(Fonts.body(9))
        label.setStyleSheet(f"color:{PALETTE.text_dim};")
        return label

    def _connect(self) -> None:
        self.run_button.clicked.connect(self.run)
        self.cancel_button.clicked.connect(self._runner.cancel)
        self._runner.progress.connect(self._on_progress)
        self._runner.finished.connect(self._on_finished)
        self._runner.failed.connect(self._on_failed)
        self._runner.cancelled.connect(self._on_cancelled)
        self._runner.stateChanged.connect(self._on_state)

    # -- running ----------------------------------------------------------

    @property
    def busy(self) -> bool:
        return self._runner.busy

    def run(self) -> None:
        if self._runner.busy:
            return
        ranges = list(self._ranges_fn() or ())
        if not ranges:
            show_info(self, "Walk-forward",
                      "Tick at least one parameter to sweep. A strategy with "
                      "nothing to choose has nothing to walk forward: an "
                      "ordinary backtest already answers the question.")
            return
        metric, minimum_trades = self._settings_fn()
        self.headline.setText("Running…")
        self.headline.setStyleSheet(f"color:{PALETTE.text_muted};")
        self.notes.setText("")
        self.table.setRowCount(0)
        self._runner.start(
            walk_forward_task, self._bars, self._spec, self._config, ranges,
            folds=self.folds.value(), train_fraction=self.train.value() / 100.0,
            anchored=self.anchored.isChecked(), metric=metric,
            minimum_trades=minimum_trades)

    def _on_state(self, busy: bool) -> None:
        self.progress.setVisible(busy)
        self.run_button.setEnabled(not busy)
        self.cancel_button.setVisible(busy)
        for widget in (self.folds, self.train, self.anchored):
            widget.setEnabled(not busy)
        if not busy:
            self.progress.reset()

    def _on_progress(self, current: int, total: int, message: str) -> None:
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(current)
        self.progress.setFormat(f"{message}  (%p%)" if message else "%p%")

    def _on_failed(self, message: str, detail: str) -> None:
        self.headline.setText("The walk-forward did not run.")
        self.headline.setStyleSheet(f"color:{PALETTE.danger};")
        self.notes.setText(message)
        show_error(self, message, "Walk-Forward Failed", detail)

    def _on_cancelled(self) -> None:
        self.headline.setText("Cancelled.")
        self.headline.setStyleSheet(f"color:{PALETTE.text_muted};")

    def _on_finished(self, result: Any) -> None:
        self._result = result
        self._fill(result)

    # -- presentation ------------------------------------------------------

    def _fill(self, result: Any) -> None:
        import pandas as pd

        def stamp(index: int) -> str:
            index = max(0, min(int(index), len(self._bars) - 1))
            return str(pd.Timestamp(self._bars.ts[index], tz="UTC").date())

        self.table.setRowCount(len(result.windows))
        for row, window in enumerate(result.windows):
            trained = f"{stamp(window.train_start)} – {stamp(window.train_end - 1)}"
            traded = f"{stamp(window.test_start)} – {stamp(window.test_end - 1)}"
            self._cell(row, 0, str(window.index + 1))
            self._cell(row, 1, trained)
            self._cell(row, 2, traded)
            if window.error:
                self._cell(row, 3, window.error, colour=PALETTE.text_muted)
                for column in (4, 5, 6):
                    self._cell(row, column, "")
                continue
            self._cell(row, 3, number(window.train_metric, 2), right=True)
            self._cell(row, 4, number(window.test_metric, 2), right=True,
                       colour=(PALETTE.success if window.test_net > 0
                               else PALETTE.danger if window.test_net < 0
                               else None))
            self._cell(row, 5, f"{window.test_trades:,}", right=True)
            self._cell(row, 6, ", ".join(f"{k}={v}"
                                         for k, v in window.params.items()))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(
            6, QHeaderView.ResizeMode.Stretch)

        currency = getattr(self._bars.instrument, "currency", "USD")
        headline = (f"Out of sample: {money(result.out_of_sample_net, currency)} "
                    f"over {result.out_of_sample_trades:,} trades, "
                    f"{result.winning_windows} of {len(result.completed)} "
                    f"windows profitable.  {result.verdict()}")
        efficiency = result.efficiency
        good = (result.out_of_sample_net > 0
                and (not math.isfinite(efficiency) or efficiency >= WEAK_EFFICIENCY))
        self.headline.setText(headline)
        self.headline.setStyleSheet(
            f"color:{PALETTE.success if good else PALETTE.warning};")
        self.notes.setText("\n\n".join(result.notes))

    def _cell(self, row: int, column: int, text: str, right: bool = False,
              colour: str | None = None) -> None:
        item = QTableWidgetItem(text)
        if right:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                  | Qt.AlignmentFlag.AlignVCenter)
        if colour:
            from PySide6.QtGui import QColor

            item.setForeground(QColor(colour))
        self.table.setItem(row, column, item)

    # -- lifecycle ---------------------------------------------------------

    def shutdown(self) -> None:
        """Stop any run in flight.  Called when the dialog closes."""
        if self._runner.busy:
            self._runner.cancel()
            self._runner.wait(3000)
