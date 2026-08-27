"""The out-of-sample tab of the optimiser.

The Results tab ranks every combination over the whole series.  That number is
the best fit to the data it was chosen on, and on data with no edge in it the
sweep still produces one -- so read on its own it is not evidence of anything.

This panel runs the same grid over the first part of the series only, fixes the
ranking, and then measures the top few on the part that was held back.  The
locked block is scored once, after the choice is made, because a holdout that
can influence the choice is not a holdout: scoring every combination on it and
reporting the best would just be a bigger sample to overfit.

The walk-forward tab next door answers a harder question and re-optimises in
every window.  This one answers the simpler one the Results tab implies but
cannot support: what are *these* parameters worth on data they never saw?
"""

from __future__ import annotations

import math
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QDoubleSpinBox, QHBoxLayout,
                               QHeaderView, QLabel, QProgressBar, QPushButton,
                               QSpinBox, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from ...logging_setup import get_logger
from ..theme import PALETTE, Fonts, number
from ..workers import TaskRunner, holdout_task
from .common import show_error, show_info

log = get_logger(__name__)

#: Retention above this is flagged rather than celebrated.  An edge decays on a
#: block it was not chosen from; it does not appear there, and when it does the
#: usual causes are an easier period in the locked block or a leak between the
#: two.  Kept in step with ``optimize.holdout``.
WRONG_SHAPE = 1.5

_COLUMNS = ("#", "Parameters", "Research", "Trades", "Locked", "Trades",
            "Kept")


class HoldoutPanel(QWidget):
    """Rank the optimiser's grid on one block and reveal the other once.

    ``ranges_fn`` returns the parameter ranges currently ticked in the sweep
    panel and ``settings_fn`` the ranking metric, so this tab and the Results
    tab can never disagree about what is being tested.
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
            "Rank the whole grid on the first part of the history, fix the "
            "ranking, and only then measure the top few on the part that was "
            "held back. The locked block is looked at once, after the choice "
            "is made — scoring every combination on it and reporting the best "
            "would make it part of the search.")
        explain.setWordWrap(True)
        explain.setFont(Fonts.body(9))
        explain.setStyleSheet(f"color:{PALETTE.text_dim};")
        outer.addWidget(explain)

        controls = QHBoxLayout()
        controls.setSpacing(9)

        controls.addWidget(self._label("Research block"))
        self.research = QDoubleSpinBox()
        self.research.setRange(20.0, 90.0)
        self.research.setDecimals(0)
        self.research.setSuffix(" %")
        self.research.setValue(65.0)
        self.research.setToolTip(
            "How much of the series chooses the parameters. The rest is held "
            "back. 65% matches the strategy finder, so the two tools do not "
            "disagree about what out of sample means.")
        controls.addWidget(self.research)

        controls.addWidget(self._label("Reveal"))
        self.reveal = QSpinBox()
        self.reveal.setRange(1, 20)
        self.reveal.setValue(3)
        self.reveal.setToolTip(
            "How many of the ranked combinations are measured on the locked "
            "block. Raising this spends the holdout: revealing all of them "
            "and picking the best is selecting on it with extra steps.")
        controls.addWidget(self.reveal)

        controls.addStretch(1)
        self.run_button = QPushButton("  RUN OUT-OF-SAMPLE TEST")
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

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(list(_COLUMNS))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setFont(Fonts.numeric(9))
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
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
            show_info(self, "Out-of-sample test",
                      "Tick at least one parameter to sweep. With nothing to "
                      "choose there is no choice to test out of sample: an "
                      "ordinary backtest already answers the question.")
            return
        metric, _minimum_trades = self._settings_fn()
        self.headline.setText("Running…")
        self.headline.setStyleSheet(f"color:{PALETTE.text_muted};")
        self.notes.setText("")
        self.table.setRowCount(0)
        self._runner.start(
            holdout_task, self._bars, self._spec, self._config, ranges,
            metric=metric, research_fraction=self.research.value() / 100.0,
            reveal=self.reveal.value())

    def _on_state(self, busy: bool) -> None:
        self.progress.setVisible(busy)
        self.run_button.setEnabled(not busy)
        self.cancel_button.setVisible(busy)
        for widget in (self.research, self.reveal):
            widget.setEnabled(not busy)
        if not busy:
            self.progress.reset()

    def _on_progress(self, current: int, total: int, message: str) -> None:
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(current)
        self.progress.setFormat(f"{message}  (%p%)" if message else "%p%")

    def _on_failed(self, message: str, detail: str) -> None:
        self.headline.setText("The out-of-sample test did not run.")
        self.headline.setStyleSheet(f"color:{PALETTE.danger};")
        self.notes.setText(message)
        show_error(self, message, "Out-of-Sample Test Failed", detail)

    def _on_cancelled(self) -> None:
        self.headline.setText("Cancelled — the locked block was not looked at.")
        self.headline.setStyleSheet(f"color:{PALETTE.text_muted};")

    def _on_finished(self, result: Any) -> None:
        self._result = result
        self._fill(result)

    # -- presentation ------------------------------------------------------

    def _fill(self, result: Any) -> None:
        self.table.setRowCount(len(result.revealed))
        for row, entry in enumerate(result.revealed):
            self._cell(row, 0, str(entry.rank))
            self._cell(row, 1, entry.label)
            if entry.error:
                self._cell(row, 2, entry.error, colour=PALETTE.text_muted)
                for column in range(3, len(_COLUMNS)):
                    self._cell(row, column, "")
                continue
            self._cell(row, 2, number(entry.research_value, 2), right=True)
            self._cell(row, 3, f"{entry.research_trades:,}", right=True)
            self._cell(row, 4, number(entry.holdout_value, 2), right=True,
                       colour=self._verdict_colour(entry))
            self._cell(row, 5, f"{entry.holdout_trades:,}", right=True)
            self._cell(row, 6, self._kept(entry), right=True)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)

        self.headline.setText(self._headline(result))
        self.headline.setStyleSheet(f"color:{self._headline_colour(result)};")
        self.notes.setText("\n\n".join(result.notes))

    @staticmethod
    def _kept(entry: Any) -> str:
        retention = entry.retention
        if not math.isfinite(retention):
            return "n/a"
        return f"{retention * 100:.0f}%"

    @staticmethod
    def _verdict_colour(entry: Any) -> str | None:
        """Green only for a locked profit that decayed from a research one.

        A locked profit off a losing research block is not a result, and
        colouring it green would say it was.
        """
        if entry.holdout_trades == 0:
            return PALETTE.text_muted
        retention = entry.retention
        if not math.isfinite(retention):
            return PALETTE.warning
        if retention > WRONG_SHAPE:
            return PALETTE.warning
        return PALETTE.success if entry.holdout_value > 0 else PALETTE.danger

    def _headline(self, result: Any) -> str:
        best = result.best
        if best is None:
            return ("Nothing was revealed on the locked block — see the notes "
                    "below for why.")
        if best.holdout_trades == 0:
            return ("The best combination took no trades at all on the locked "
                    "block, so there is no out-of-sample evidence for it.")
        if not result.maximise:
            return (f"{result.metric.replace('_', ' ')}: "
                    f"{number(best.research_value, 2)} on research, "
                    f"{number(best.holdout_value, 2)} on the locked block. "
                    f"Smaller is better for this metric, so there is no "
                    f"retention figure — read the two apart.")
        if not math.isfinite(best.retention):
            return (f"Nothing in the grid worked on the block that chose it: "
                    f"the best of {result.combinations:,} combinations scored "
                    f"{number(best.research_value, 2)} on research. The locked "
                    f"column is what the least-bad combination happened to do "
                    f"next.")
        if result.wrong_shape:
            return (f"The winner did markedly better out of sample "
                    f"({best.retention * 100:.0f}% of its research result). "
                    f"That is the wrong shape and needs explaining.")
        if best.retention <= 0:
            return ("The winner lost money on the locked block. What the sweep "
                    "found did not survive data it had not seen.")
        return (f"The winner kept {best.retention * 100:.0f}% of its research "
                f"result out of sample, over {best.holdout_trades:,} trades.")

    @staticmethod
    def _headline_colour(result: Any) -> str:
        best = result.best
        if best is None or best.holdout_trades == 0:
            return PALETTE.text_muted
        if result.wrong_shape or not result.maximise:
            return PALETTE.warning
        retention = best.retention
        if not math.isfinite(retention) or retention <= 0:
            return PALETTE.danger
        return PALETTE.success

    def _cell(self, row: int, column: int, text: str, right: bool = False,
              colour: str | None = None) -> None:
        item = QTableWidgetItem(text)
        if right:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                  | Qt.AlignmentFlag.AlignVCenter)
        if colour:
            item.setForeground(QColor(colour))
        self.table.setItem(row, column, item)

    # -- lifecycle ---------------------------------------------------------

    def shutdown(self) -> None:
        """Stop any run in flight.  Called when the dialog closes."""
        if self._runner.busy:
            self._runner.cancel()
            self._runner.wait(3000)
