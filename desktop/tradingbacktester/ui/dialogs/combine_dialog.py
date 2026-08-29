"""Pick several strategies, choose how they should agree, and see the result.

The dialog is built around the thing that is easy to get wrong: a combined
strategy inherits exactly one set of risk, exit, execution, session and cost
settings, and the ones it does not inherit are simply gone.  So the decisions
panel is not tucked behind a disclosure -- it is the bottom half of the
window, it fills in the moment a choice changes, and it says which strategy's
settings won and what the others had.

Nothing is saved or run until the user asks.  Preview is free and immediate
because :func:`~strategy.combine.combine_strategies` does no work on bars; it
only rewrites the specs.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog,
                               QFormLayout, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QSpinBox,
                               QSplitter, QTextBrowser, QVBoxLayout, QWidget)

from ...core.errors import BacktesterError
from ...logging_setup import get_logger
from ...strategy.combine import (COMBINE_MODES, combine_strategies,
                                 default_threshold)
from ..theme import PALETTE, Fonts
from ..widgets.common import Card, show_error, show_info

log = get_logger(__name__)

_MODE_LABELS = {
    "all": "All must agree — every strategy signals on the same bar",
    "any": "Any one is enough — the union of their signals",
    "majority": "A majority agrees — at least this many of them",
}


class CombineStrategiesDialog(QDialog):
    """Merge two or more saved or built-in strategies into a new one."""

    def __init__(self, store: Any, bars: Any = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Combine strategies")
        self.resize(1000, 760)
        self._store = store
        self._bars = bars
        self._report: Any = None
        self._specs: list[Any] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(9)

        intro = QLabel(
            "Tick two or more strategies. The result is one strategy holding "
            "one position at a time, not the strategies run side by side, so "
            "its results will not be the sum of theirs. It keeps the risk, "
            "exit, execution, session and cost settings of the strategy you "
            "choose below; everything the others set differently is listed "
            "rather than merged.")
        intro.setWordWrap(True)
        intro.setObjectName("Hint")
        intro.setFont(Fonts.body(9))
        outer.addWidget(intro)

        splitter = QSplitter(Qt.Orientation.Vertical)

        top = QWidget()
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(10)

        pick = Card("Strategies")
        self.list = QListWidget()
        self.list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self.list.itemChanged.connect(self._on_choice_changed)
        pick.add(self.list)
        top_layout.addWidget(pick, 3)

        how = Card("How they combine")
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.mode = QComboBox()
        for key in COMBINE_MODES:
            self.mode.addItem(_MODE_LABELS[key], key)
        self.mode.currentIndexChanged.connect(self._on_choice_changed)
        form.addRow("Entries", self.mode)

        self.exit_mode = QComboBox()
        for key in COMBINE_MODES:
            self.exit_mode.addItem(_MODE_LABELS[key], key)
        self.exit_mode.setCurrentIndex(COMBINE_MODES.index("any"))
        self.exit_mode.currentIndexChanged.connect(self._on_choice_changed)
        form.addRow("Exits", self.exit_mode)

        self.threshold = QSpinBox()
        self.threshold.setRange(1, 99)
        self.threshold.setEnabled(False)
        # Whether the user has ever set this by hand.  Until they have, the
        # vote count follows how many strategies are ticked; afterwards it is
        # theirs and is only ever clamped into range.  Inferring this by
        # comparing against the previous default does not work -- the box
        # starts at 1, which is a legitimate default for nothing.
        self._threshold_touched = False
        self.threshold.valueChanged.connect(self._on_threshold_edited)
        form.addRow("Votes needed", self.threshold)

        self.primary = QComboBox()
        self.primary.currentIndexChanged.connect(self._on_choice_changed)
        form.addRow("Settings from", self.primary)
        how.add_layout(form)
        hint = QLabel(
            "Exits default to 'any' on purpose: a position whose reason for "
            "existing has ended under one strategy is not one to keep open on "
            "another's rule.")
        hint.setWordWrap(True)
        hint.setObjectName("Hint")
        how.add(hint)
        top_layout.addWidget(how, 4)
        splitter.addWidget(top)

        result = Card("What this produces")
        self.headline = QLabel("Tick at least two strategies.")
        self.headline.setWordWrap(True)
        self.headline.setFont(Fonts.body(10))
        result.add(self.headline)
        self.detail = QTextBrowser()
        self.detail.setFont(Fonts.numeric(9))
        result.add(self.detail)
        splitter.addWidget(result)
        splitter.setSizes([300, 420])
        outer.addWidget(splitter, 1)

        buttons = QHBoxLayout()
        self.backtest_button = QPushButton("Backtest it")
        self.backtest_button.setEnabled(False)
        self.backtest_button.clicked.connect(self.on_backtest)
        buttons.addWidget(self.backtest_button)

        self.save_button = QPushButton("  Save to library")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.on_save)
        buttons.addWidget(self.save_button)

        buttons.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("Ghost")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        outer.addLayout(buttons)

        self._load_strategies()

    # -- populating ------------------------------------------------------

    def _load_strategies(self) -> None:
        """Every saved strategy, plus the built-in ones, as tick boxes."""
        from ...strategy.builtin import BUILTIN_STRATEGIES

        self.list.blockSignals(True)
        try:
            for entry in self._store.list():
                self._add_row(entry.name, ("saved", entry.id))
            for name in BUILTIN_STRATEGIES:
                self._add_row(f"{name}  (built in)", ("builtin", name))
        finally:
            self.list.blockSignals(False)
        self._refresh()

    def _add_row(self, label: str, payload: tuple[str, str]) -> None:
        item = QListWidgetItem(label)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Unchecked)
        item.setData(Qt.ItemDataRole.UserRole, payload)
        self.list.addItem(item)

    def _checked(self) -> list[tuple[str, str]]:
        out = []
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                out.append(item.data(Qt.ItemDataRole.UserRole))
        return out

    def _resolve(self, payload: tuple[str, str]) -> Any:
        from ...strategy.builtin import BUILTIN_STRATEGIES

        kind, key = payload
        if kind == "saved":
            return self._store.load(key)
        return BUILTIN_STRATEGIES[key]()

    # -- reacting --------------------------------------------------------

    def _on_choice_changed(self, *_args) -> None:
        self._refresh()

    def _on_threshold_edited(self, *_args) -> None:
        """Only reached for a real edit: ``_sync_threshold`` blocks signals."""
        self._threshold_touched = True
        self._refresh()

    def _refresh(self) -> None:
        """Recompute the preview.  Cheap: no bars are touched."""
        chosen = self._checked()
        mode = self.mode.currentData()
        exit_mode = self.exit_mode.currentData()
        self.threshold.setEnabled("majority" in (mode, exit_mode))

        if len(chosen) < 2:
            self._report = None
            self._specs = []
            self.headline.setText(
                f"Tick at least two strategies. {len(chosen)} ticked.")
            self.headline.setStyleSheet(f"color:{PALETTE.text_muted};")
            self.detail.setPlainText("")
            self._sync_primary([])
            self.save_button.setEnabled(False)
            self.backtest_button.setEnabled(False)
            return

        try:
            specs = [self._resolve(p) for p in chosen]
        except Exception as exc:            # noqa: BLE001 - never lose the dialog
            log.exception("Could not load a strategy for combining")
            self._fail(exc)
            return
        self._specs = specs
        names = [s.name for s in specs]
        self._sync_primary(names)
        self._sync_threshold(len(specs))

        try:
            report = combine_strategies(
                specs, mode=mode, exit_mode=exit_mode,
                primary=max(0, self.primary.currentIndex()),
                threshold=self.threshold.value())
        except BacktesterError as exc:
            self._report = None
            self.headline.setText(exc.user_message)
            self.headline.setStyleSheet(f"color:{PALETTE.warning};")
            self.detail.setPlainText(exc.detail or "")
            self.save_button.setEnabled(False)
            self.backtest_button.setEnabled(False)
            return
        except Exception as exc:            # noqa: BLE001
            log.exception("Combining strategies failed")
            self._fail(exc)
            return

        self._report = report
        self.headline.setText(report.summary())
        self.headline.setStyleSheet(f"color:{PALETTE.text};")
        self.detail.setPlainText(_detail_text(report))
        self.save_button.setEnabled(True)
        self.backtest_button.setEnabled(self._bars is not None)
        self.backtest_button.setToolTip(
            "" if self._bars is not None
            else "Load a dataset in the main window first.")

    def _fail(self, exc: Exception) -> None:
        self._report = None
        self.headline.setText("These strategies could not be combined.")
        self.headline.setStyleSheet(f"color:{PALETTE.short};")
        self.detail.setPlainText(str(exc))
        self.save_button.setEnabled(False)
        self.backtest_button.setEnabled(False)

    def _sync_primary(self, names: list[str]) -> None:
        """Keep the settings-source box in step with what is ticked.

        The current choice is preserved by name, so ticking a fourth strategy
        does not silently move whose stop loss the result uses.
        """
        wanted = self.primary.currentText()
        if [self.primary.itemText(i) for i in range(self.primary.count())] == names:
            return
        self.primary.blockSignals(True)
        try:
            self.primary.clear()
            self.primary.addItems(names)
            if wanted in names:
                self.primary.setCurrentIndex(names.index(wanted))
        finally:
            self.primary.blockSignals(False)

    def _sync_threshold(self, count: int) -> None:
        """A vote of k out of n, with k following n unless it was set by hand."""
        self.threshold.blockSignals(True)
        try:
            self.threshold.setRange(1, max(1, count))
            if not self._threshold_touched:
                self.threshold.setValue(default_threshold(count))
            elif self.threshold.value() > count:
                # Unticking a strategy can leave a hand-set vote asking for
                # more agreement than there are strategies left to give it.
                self.threshold.setValue(count)
            self.threshold.setSuffix(f" of {count}")
        finally:
            self.threshold.blockSignals(False)

    # -- acting on it ----------------------------------------------------

    def on_save(self) -> None:
        if self._report is None:
            return
        try:
            self._store.save(self._report.spec)
        except Exception as exc:            # noqa: BLE001
            log.exception("Saving a combined strategy failed")
            show_error(self, exc, "Could not save")
            return
        show_info(self, "Saved",
                  f"'{self._report.spec.name}' is in the strategy library.",
                  "Open it from the strategy picker in the main window to "
                  "chart it, edit it or run it like any other. Its "
                  "description records which strategies it came from and "
                  "which settings were used.")

    def on_backtest(self) -> None:
        """Run the combination and each of its parts on the loaded bars.

        Side by side, because a combined result read on its own says nothing:
        the question is always whether it did better than the strategies that
        went into it, on this same data.
        """
        if self._report is None or self._bars is None:
            return
        from ...core.types import BacktestConfig
        from ...engine.backtester import Backtester

        rows = [(s.name, s) for s in self._specs]
        rows.append((self._report.spec.name, self._report.spec))
        lines = [f"On the loaded data, {len(self._bars):,} bars:", ""]
        try:
            for name, spec in rows:
                config = BacktestConfig()
                config.exits, config.execution = spec.exits, spec.execution
                config.session, config.costs = spec.session, spec.costs
                config.risk = spec.risk
                config.warmup_bars = spec.warmup_bars()
                result = Backtester(self._bars, spec, config).run()
                metrics = result.metrics
                lines.append(
                    f"  {name}\n"
                    f"      {len(result.trades):,} trades, "
                    f"net {metrics.get('net_profit', float('nan')):,.2f}, "
                    f"Sharpe {metrics.get('sharpe_ratio', float('nan')):.3f}, "
                    f"max drawdown "
                    f"{metrics.get('max_drawdown_pct', float('nan')):.2f}%")
        except Exception as exc:            # noqa: BLE001
            log.exception("Backtest of a combined strategy failed")
            show_error(self, exc, "Backtest failed")
            return
        lines.append("")
        lines.append("These are backtests of this data only. A combination "
                     "that beats its parts here has not been shown to beat "
                     "them anywhere else.")
        self.detail.setPlainText("\n".join(lines) + "\n\n"
                                 + _detail_text(self._report))


def _detail_text(report: Any) -> str:
    """The rules, then every decision the merge made, in that order."""
    out: list[str] = list(report.spec.summary_lines())
    for label, items in (("Shared", report.shared),
                         ("Conflict", report.conflicts),
                         ("Note", report.notes),
                         ("Warning", report.warnings)):
        if not items:
            continue
        out.append("")
        for item in items:
            out.append(f"{label}: {item}")
    return "\n".join(out)
