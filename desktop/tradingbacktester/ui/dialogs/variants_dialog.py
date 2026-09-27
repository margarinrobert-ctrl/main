"""Better versions of the strategy you have selected, honestly priced.

The dialog exists because "try a few settings and keep the best" is what
everyone does anyway, and doing it by hand hides the one fact that decides
whether the result means anything: how many settings were tried. Twenty-eight
tries and the best one is a different claim from one try and it worked, and
only the first is what actually happened.

So the count is on screen the whole time, the winner is deflated against it,
and the headline says *does NOT survive* in those words whenever it does not.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QLabel,
                               QProgressBar, QPushButton, QTableWidget,
                               QTableWidgetItem, QTextBrowser, QVBoxLayout,
                               QWidget)

from ...core.errors import BacktesterError
from ...logging_setup import get_logger
from ..theme import PALETTE, Fonts
from ..widgets.common import Card, show_error, show_info

log = get_logger(__name__)

_COLUMNS = ("Change", "Trades", "Per trade", "vs current", "Sharpe", "Max DD")

#: Qt sorts on this role when it is present, so the numbers sort as numbers.
_SORT_ROLE = Qt.ItemDataRole.UserRole + 1

#: How long to wait for a stopped search before giving up on it.  The search
#: only checks its stop flag between variants, so on a large dataset one
#: variant can still be running when the dialog closes.
_STOP_WAIT_MS = 5000

#: Searches that outlived their dialog.
#:
#: Destroying a running QThread aborts the whole process -- Qt calls
#: ``qFatal``, and the application dies with no dialog, no log line and no
#: chance to save.  Closing this dialog mid-search did exactly that.  A search
#: that will not stop in time is therefore parked here, where a reference
#: outlives the dialog, and is collected once it has actually finished.
_ORPHANS: set[QThread] = set()


def _prune_orphans() -> None:
    for thread in list(_ORPHANS):
        if thread.isFinished():
            thread.wait(0)
            _ORPHANS.discard(thread)


class _SortableItem(QTableWidgetItem):
    """A cell that sorts on its value and displays its formatting."""

    def __lt__(self, other: Any) -> bool:
        mine = self.data(_SORT_ROLE)
        theirs = other.data(_SORT_ROLE)
        if mine is None or theirs is None:
            return super().__lt__(other)
        try:
            return mine < theirs
        except TypeError:                   # pragma: no cover - mixed types
            return str(mine) < str(theirs)


class _SearchThread(QThread):
    """Runs the walk off the UI thread so the window keeps answering."""

    progressed = Signal(int, int, str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, spec: Any, bars: Any, config: Any) -> None:
        super().__init__()
        self._spec, self._bars, self._config = spec, bars, config
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:                  # noqa: D102 - QThread entry point
        from ...finder.variants import search_variants

        def progress(done: int, total: int, label: str) -> bool:
            self.progressed.emit(done, total, label)
            return not self._stop

        try:
            report = search_variants(self._spec, self._bars, self._config,
                                     progress=progress)
        except BacktesterError as exc:
            self.failed.emit(exc.user_message)
            return
        except Exception as exc:            # noqa: BLE001 - never lose the dialog
            log.exception("Variant search failed")
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.finished_ok.emit(report)


class VariantsDialog(QDialog):
    """Search one strategy's neighbourhood and price what wins."""

    def __init__(self, spec: Any, bars: Any, config: Any,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Better versions — {spec.name}")
        self.resize(1080, 760)
        self._spec, self._bars, self._config = spec, bars, config
        self._report: Any = None
        self._thread: _SearchThread | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(9)

        intro = QLabel(
            "Each numeric parameter and each exit level is moved up and down "
            "its own scale, one change at a time, then the best few together. "
            "Every variant is compared with the strategy you already have, "
            "and the winner is then priced for how many were tried — because "
            "the best of thirty tries beats the best of one for reasons that "
            "have nothing to do with skill.")
        intro.setWordWrap(True)
        intro.setObjectName("Hint")
        intro.setFont(Fonts.body(9))
        outer.addWidget(intro)

        self.headline = QLabel("Press Search to begin.")
        self.headline.setWordWrap(True)
        self.headline.setFont(Fonts.body(10))
        outer.addWidget(self.headline)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(True)
        outer.addWidget(self.progress)

        table_card = Card("What was tried")
        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(list(_COLUMNS))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        table_card.add(self.table)
        outer.addWidget(table_card, 1)

        detail_card = Card("What it means")
        self.detail = QTextBrowser()
        self.detail.setFont(Fonts.numeric(9))
        self.detail.setMaximumHeight(190)
        detail_card.add(self.detail)
        outer.addWidget(detail_card)

        buttons = QHBoxLayout()
        self.search_button = QPushButton("  Search")
        self.search_button.setObjectName("Primary")
        self.search_button.clicked.connect(self.on_search)
        buttons.addWidget(self.search_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.on_stop)
        buttons.addWidget(self.stop_button)

        self.keep_button = QPushButton("Save the winner as a new strategy")
        self.keep_button.setEnabled(False)
        self.keep_button.clicked.connect(self.on_keep)
        buttons.addWidget(self.keep_button)

        buttons.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("Ghost")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        outer.addLayout(buttons)

    # -- running ---------------------------------------------------------

    def on_search(self) -> None:
        if self._thread is not None:
            return
        self.table.setRowCount(0)
        self.detail.clear()
        self.headline.setText("Searching…")
        self.headline.setStyleSheet(f"color:{PALETTE.text};")
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.search_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.keep_button.setEnabled(False)

        self._thread = _SearchThread(self._spec, self._bars, self._config)
        self._thread.progressed.connect(self._on_progress)
        self._thread.finished_ok.connect(self._on_done)
        self._thread.failed.connect(self._on_failed)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()

    def on_stop(self) -> None:
        if self._thread is not None:
            self._thread.stop()
            self.headline.setText("Stopping after the current variant…")

    # -- closing, without taking the application with it -----------------

    def _release_search(self) -> None:
        """Make it safe for this dialog to be destroyed.

        Qt aborts the process outright when a running QThread is destroyed, so
        closing the dialog while the search was still walking killed the whole
        application. The search is asked to stop and waited for; if it will not
        stop in time it is parked in :data:`_ORPHANS` rather than destroyed,
        with its signals disconnected so it cannot touch a dialog that is on
        its way out.
        """
        _prune_orphans()
        thread = self._thread
        if thread is None:
            return
        self._thread = None
        thread.stop()
        for signal in (thread.progressed, thread.finished_ok, thread.failed,
                       thread.finished):
            try:
                signal.disconnect()
            except (RuntimeError, TypeError):   # already disconnected
                pass
        if not thread.wait(_STOP_WAIT_MS):
            log.info("A variant search outlived its dialog; letting it finish.")
            _ORPHANS.add(thread)

    def done(self, code: int) -> None:      # noqa: D102 - QDialog override
        self._release_search()
        super().done(code)

    def closeEvent(self, event: Any) -> None:   # noqa: D102 - QWidget override
        self._release_search()
        super().closeEvent(event)

    def _on_progress(self, done: int, total: int, label: str) -> None:
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(done)
        self.progress.setFormat(f"%v of %m — {label}")

    def _on_thread_finished(self) -> None:
        self._thread = None
        self.progress.setVisible(False)
        self.search_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def _on_failed(self, message: str) -> None:
        self.headline.setText(message)
        self.headline.setStyleSheet(f"color:{PALETTE.short};")

    def _on_done(self, report: Any) -> None:
        self._report = report
        self._fill(report)

    # -- showing it ------------------------------------------------------

    def _fill(self, report: Any) -> None:
        rows = [report.baseline] + sorted(report.usable,
                                          key=lambda v: -v.per_trade)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for row, variant in enumerate(rows):
            is_baseline = variant is report.baseline
            is_winner = variant is report.best and not is_baseline
            cells = (
                "The strategy you have" if is_baseline else variant.label,
                f"{variant.trades:,}",
                f"{variant.per_trade:+,.2f}",
                "—" if is_baseline else f"{variant.excess_per_trade:+,.2f}",
                f"{variant.sharpe:+.4f}",
                f"{variant.max_drawdown_pct:,.2f}%",
            )
            # Sort keys, not display strings.  A table sorted on the rendered
            # text puts "-703.32" above "+356.42" because "-" precedes "+",
            # which silently reverses the ranking the whole dialog is for.
            keys = (variant.label, variant.trades, variant.per_trade,
                    variant.excess_per_trade, variant.sharpe,
                    variant.max_drawdown_pct)
            for column, text in enumerate(cells):
                item = _SortableItem()
                item.setData(Qt.ItemDataRole.DisplayRole, text)
                item.setData(_SORT_ROLE, keys[column])
                if column:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                          | Qt.AlignmentFlag.AlignVCenter)
                    item.setFont(Fonts.numeric(9))
                if is_baseline:
                    item.setForeground(_colour(PALETTE.text_muted))
                elif is_winner:
                    item.setForeground(_colour(PALETTE.long))
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self.table.setSortingEnabled(True)
        # Best per trade first, which is the order the dialog is read in.
        self.table.sortItems(2, Qt.SortOrder.DescendingOrder)

        self.headline.setText(report.headline())
        # Green only for a result that cleared the 0.95 threshold. Anything
        # else is amber, including "clears the benchmark but is not
        # significant", because that is not a green light.
        self.headline.setStyleSheet(
            f"color:{PALETTE.long if report.improved else PALETTE.warning};")
        self.detail.setPlainText("\n".join(report.lines()))
        self.keep_button.setEnabled(
            report.best is not None and report.best.trades > 0)
        self.keep_button.setToolTip(
            "" if report.improved else
            "This variant did not survive the correction. Saving it is "
            "allowed — it may still be worth testing on other data — but it "
            "is not a finding.")

    def on_keep(self) -> None:
        """Save the winner, named so it can never be mistaken for the original."""
        if self._report is None or self._report.best is None:
            return
        winner = self._report.best
        spec = winner.spec.copy(f"{self._spec.name} — {winner.label}")
        verdict = ("survived" if self._report.improved else
                   "did NOT survive")
        spec.description = (
            f"A variant of '{self._spec.name}' found by searching "
            f"{self._report.tried} of them.\n"
            f"Change: {winner.label}.\n"
            f"It {verdict} being priced for that search.\n"
            f"{self._report.deflated.describe() if self._report.deflated else ''}"
        ).strip()
        spec.tags = list(spec.tags) + ["variant"]
        store = getattr(self.parent(), "strategies", None)
        if store is None:
            show_error(self, "No strategy library is open.", "Could not save")
            return
        try:
            store.save(spec)
        except Exception as exc:            # noqa: BLE001
            log.exception("Saving a variant failed")
            show_error(self, exc, "Could not save")
            return
        show_info(self, "Saved", f"'{spec.name}' is in the strategy library.",
                  "Its description records how many variants were tried and "
                  "whether it survived the correction, so the number is not "
                  "separated from what produced it.")


def _colour(value: str) -> Any:
    from PySide6.QtGui import QColor

    return QColor(value)
