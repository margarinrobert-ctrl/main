"""Parameter optimisation.

The results table is the easy half. The hard half is the *robustness* column and
the note beneath it, because a grid search always produces a winner -- including
on data with no edge in it at all -- and the winner is by construction the
combination that fitted the sample's noise best. This dialog is built to make
that visible rather than to hide it behind a big green number.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                               QDoubleSpinBox, QGridLayout, QHBoxLayout,
                               QHeaderView, QLabel, QProgressBar, QPushButton,
                               QSizePolicy, QSpinBox, QSplitter, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout,
                               QWidget)

from ...core.errors import BacktesterError
from ...logging_setup import get_logger
from ...optimize.grid import ParameterRange, combination_count
from ...optimize.ranking import (RANKING_METRICS, heatmap,
                                 metric_label, neighbourhood_mean,
                                 overfitting_note, rank)
from ..theme import PALETTE, Fonts, money, number, pct
from ..widgets.common import Card, show_error, show_info
from ..widgets.holdout_panel import HoldoutPanel
from ..widgets.walkforward_panel import WalkForwardPanel
from ..workers import TaskRunner, optimize_task

log = get_logger(__name__)

#: Above this many combinations the count turns amber, above the second it
#: turns red.  Not limits -- warnings.
AMBER_COMBINATIONS = 500
RED_COMBINATIONS = 5000


class OptimizerDialog(QDialog):
    """Sweep a parameter grid and rank the results.

    After the dialog closes, :attr:`chosen_params` holds the combination the
    user picked, or ``None``.
    """

    def __init__(self, bars: Any, spec: Any, config: Any,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Optimise — {spec.name}")
        self.resize(1320, 800)

        self._bars = bars
        self._spec = spec
        self._config = config
        self._results: Any = None
        self._ranked: list[Any] = []
        self._runner = TaskRunner(self)

        self.chosen_params: dict[str, Any] | None = None

        self._build_ui()
        self._connect()
        self._update_count()

    # -- construction ----------------------------------------------------

    def _build_ui(self) -> None:
        from ..icons import icon

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(9)

        warning = QLabel(
            "Optimisation reports what would have happened on this data. The "
            "best combination in a grid search is, by construction, the one "
            "that fitted this sample's noise best — a search over enough "
            "settings finds a good-looking one even in data with no edge at "
            "all. Prefer a broad plateau of decent results to an isolated peak, "
            "and read the robustness column before the profit column.")
        warning.setWordWrap(True)
        warning.setFont(Fonts.body(9))
        warning.setStyleSheet(
            f"color:{PALETTE.warning}; background:{PALETTE.panel_alt};"
            f"border:1px solid {PALETTE.warning}; border-radius:5px; padding:9px;")
        outer.addWidget(warning)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # -- left: the grid ------------------------------------------------
        left = QWidget()
        left.setMaximumWidth(430)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(8)

        grid_card = Card("Parameters to Sweep")
        grid = QGridLayout()
        grid.setHorizontalSpacing(7)
        grid.setVerticalSpacing(4)
        for column, title in enumerate(("", "Parameter", "From", "To", "Step")):
            head = QLabel(title)
            head.setFont(Fonts.section())
            head.setStyleSheet(f"color:{PALETTE.text_muted};")
            grid.addWidget(head, 0, column)

        self._rows: list[dict[str, Any]] = []
        for index, param in enumerate(self._spec.params, start=1):
            enabled = QCheckBox()
            enabled.setChecked(index <= 2)      # two swept by default
            grid.addWidget(enabled, index, 0)

            name = QLabel(param.label or param.name)
            name.setFont(Fonts.body(9))
            name.setToolTip(param.help or param.name)
            grid.addWidget(name, index, 1)

            is_int = param.kind == "int"
            widgets = []
            start, stop, step = _suggest(param)
            for value, minimum in ((start, param.minimum), (stop, param.minimum),
                                   (step, None)):
                if is_int:
                    box: Any = QSpinBox()
                    box.setRange(int(minimum if minimum is not None else 1),
                                 int(param.maximum if param.maximum is not None
                                     else 10 ** 6))
                    box.setValue(int(round(value)))
                else:
                    box = QDoubleSpinBox()
                    box.setDecimals(4)
                    box.setRange(float(minimum if minimum is not None else -1e9),
                                 float(param.maximum if param.maximum is not None
                                       else 1e9))
                    box.setValue(float(value))
                box.setAlignment(Qt.AlignmentFlag.AlignRight)
                box.setMaximumWidth(88)
                widgets.append(box)
            step_box = widgets[2]
            step_box.setMinimum(1 if is_int else 1e-6)

            for offset, box in enumerate(widgets):
                grid.addWidget(box, index, 2 + offset)

            enabled.toggled.connect(
                lambda on, boxes=widgets: [b.setEnabled(on) for b in boxes])
            for box in widgets:
                box.setEnabled(enabled.isChecked())
            self._rows.append({"param": param, "enabled": enabled,
                               "start": widgets[0], "stop": widgets[1],
                               "step": widgets[2]})
        grid_card.add_layout(grid)

        if not self._rows:
            note = QLabel("This strategy has no parameters to sweep. Add some in "
                          "the strategy editor first.")
            note.setWordWrap(True)
            note.setObjectName("Warning")
            grid_card.add(note)
        grid_card.add(self._count_widgets())
        ll.addWidget(grid_card)

        rank_card = Card("Ranking")
        rank_grid = QGridLayout()
        rank_grid.setHorizontalSpacing(7)
        rank_grid.setVerticalSpacing(5)
        rank_grid.addWidget(self._label("Rank by"), 0, 0)
        self.metric_box = QComboBox()
        for definition in RANKING_METRICS:
            self.metric_box.addItem(definition.label, definition.key)
        index = self.metric_box.findData("net_profit")
        self.metric_box.setCurrentIndex(max(0, index))
        rank_grid.addWidget(self.metric_box, 0, 1)

        rank_grid.addWidget(self._label("Minimum trades"), 1, 0)
        self.min_trades = QSpinBox()
        self.min_trades.setRange(0, 100000)
        self.min_trades.setValue(30)
        self.min_trades.setToolTip(
            "Combinations with fewer trades than this are left out of the "
            "table. A result from five trades is not a result.")
        rank_grid.addWidget(self.min_trades, 1, 1)
        rank_grid.setColumnStretch(1, 1)
        rank_card.add_layout(rank_grid)
        ll.addWidget(rank_card)
        ll.addStretch(1)

        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.hide()
        ll.addWidget(self.progress)

        buttons = QHBoxLayout()
        self.run_button = QPushButton("  RUN OPTIMISATION")
        self.run_button.setObjectName("Primary")
        self.run_button.setIcon(icon("run", 15, "#ffffff"))
        self.run_button.setMinimumHeight(32)
        buttons.addWidget(self.run_button, 1)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("Danger")
        self.cancel_button.hide()
        buttons.addWidget(self.cancel_button)
        ll.addLayout(buttons)
        splitter.addWidget(left)

        # -- right: results -------------------------------------------------
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(7)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        self.table = QTableWidget(0, 0)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(True)
        self.table.setFont(Fonts.numeric(9))
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.doubleClicked.connect(self._apply_selected)
        self.tabs.addTab(self.table, icon("table", 15), "Results")

        self.heatmap = _HeatmapWidget()
        self.tabs.addTab(self.heatmap, icon("grid", 15), "Heat Map")

        # The walk-forward reads the same grid as the sweep on purpose: a
        # different grid here would be an answer about a different strategy.
        self.walkforward = WalkForwardPanel(
            self._bars, self._spec, self._config, self._ranges,
            lambda: (self.metric_box.currentData() or "net_profit",
                     self.min_trades.value()))
        self.tabs.addTab(self.walkforward, icon("shield", 15), "Walk-Forward")

        # Same grid again, for the question the Results tab implies but cannot
        # answer: what are THESE parameters worth on data they never saw?
        self.holdout = HoldoutPanel(
            self._bars, self._spec, self._config, self._ranges,
            lambda: (self.metric_box.currentData() or "net_profit",
                     self.min_trades.value()))
        self.tabs.addTab(self.holdout, icon("target", 15), "Out of Sample")
        rl.addWidget(self.tabs, 1)

        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setFont(Fonts.body(9))
        self.note.setStyleSheet(f"color:{PALETTE.text_dim};")
        self.note.setMinimumHeight(56)
        rl.addWidget(self.note)

        row = QHBoxLayout()
        self.status = QLabel("Choose which parameters to sweep, then press Run.")
        self.status.setFont(Fonts.body(9))
        self.status.setStyleSheet(f"color:{PALETTE.text_muted};")
        row.addWidget(self.status, 1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        self.apply_button = QPushButton("Use These Parameters")
        self.apply_button.setObjectName("Primary")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self._apply_selected)
        row.addWidget(self.apply_button)
        rl.addLayout(row)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        outer.addWidget(splitter, 1)

    def _count_widgets(self) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 4, 0, 0)
        row.setSpacing(8)
        self.count_label = QLabel("")
        self.count_label.setFont(Fonts.numeric(9, bold=True))
        row.addWidget(self.count_label)
        self.estimate_label = QLabel("")
        self.estimate_label.setFont(Fonts.body(8))
        self.estimate_label.setStyleSheet(f"color:{PALETTE.text_muted};")
        row.addWidget(self.estimate_label, 1)
        return holder

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setFont(Fonts.body(9))
        label.setStyleSheet(f"color:{PALETTE.text_dim};")
        return label

    def _connect(self) -> None:
        for row in self._rows:
            row["enabled"].toggled.connect(self._update_count)
            for key in ("start", "stop", "step"):
                row[key].valueChanged.connect(self._update_count)
        self.metric_box.currentIndexChanged.connect(self._rerank)
        self.min_trades.valueChanged.connect(self._rerank)
        self.run_button.clicked.connect(self._run)
        self.cancel_button.clicked.connect(self._runner.cancel)
        self.table.itemSelectionChanged.connect(
            lambda: self.apply_button.setEnabled(bool(self.table.selectedItems())))
        self._runner.progress.connect(self._on_progress)
        self._runner.finished.connect(self._on_finished)
        self._runner.failed.connect(self._on_failed)
        self._runner.cancelled.connect(self._on_cancelled)
        self._runner.stateChanged.connect(self._on_state)

    # -- the grid ---------------------------------------------------------

    def _ranges(self) -> list[ParameterRange]:
        out: list[ParameterRange] = []
        for row in self._rows:
            if not row["enabled"].isChecked():
                continue
            out.append(ParameterRange(row["param"].name, row["start"].value(),
                                      row["stop"].value(), row["step"].value()))
        return out

    def _update_count(self, *_args) -> None:
        ranges = self._ranges()
        if not ranges:
            self.count_label.setText("no parameters selected")
            self.count_label.setStyleSheet(f"color:{PALETTE.text_muted};")
            self.estimate_label.setText("")
            self.run_button.setEnabled(False)
            return
        try:
            total = combination_count(ranges)
        except BacktesterError as exc:
            self.count_label.setText("range is invalid")
            self.count_label.setStyleSheet(f"color:{PALETTE.danger};")
            self.estimate_label.setText(exc.user_message)
            self.run_button.setEnabled(False)
            return

        colour = (PALETTE.danger if total > RED_COMBINATIONS
                  else PALETTE.warning if total > AMBER_COMBINATIONS
                  else PALETTE.text)
        self.count_label.setText(f"{total:,} combinations")
        self.count_label.setStyleSheet(f"color:{colour};")
        self.run_button.setEnabled(total > 0)

        per_run = _rough_seconds_per_run(len(self._bars))
        seconds = total * per_run / max(1, _worker_guess())
        self.estimate_label.setText(
            f"roughly {_humanise(seconds)}"
            + ("  ·  a search this wide will find something that looks good "
               "whether or not there is anything there" if total > AMBER_COMBINATIONS
               else ""))

    # -- running ----------------------------------------------------------

    def _run(self) -> None:
        if self._runner.busy:
            return
        ranges = self._ranges()
        if not ranges:
            show_info(self, "Optimise", "Tick at least one parameter to sweep.")
            return
        self.status.setText("Running…")
        self.note.setText("")
        self._runner.start(optimize_task, self._bars, self._spec, self._config,
                           ranges, 0)

    def _on_state(self, busy: bool) -> None:
        self.progress.setVisible(busy)
        self.run_button.setEnabled(not busy)
        self.cancel_button.setVisible(busy)
        if not busy:
            self.progress.reset()
            self._update_count()

    def _on_progress(self, current: int, total: int, message: str) -> None:
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(current)
        self.progress.setFormat(f"{message}  (%p%)" if message else "%p%")

    def _on_failed(self, message: str, detail: str) -> None:
        self.status.setText("The optimisation failed.")
        show_error(self, message, "Optimisation Failed", detail)

    def _on_cancelled(self) -> None:
        self.status.setText("Cancelled. Any completed combinations are shown below.")

    def _on_finished(self, results: Any) -> None:
        self._results = results
        parts = [f"{results.completed} of {results.total_combinations} combinations",
                 f"{results.elapsed_seconds:.1f}s"]
        if results.failed:
            parts.append(f"{results.failed} failed")
        if not getattr(results, "used_processes", True):
            parts.append("ran on threads")
        self.status.setText(" · ".join(parts))
        for warning in getattr(results, "warnings", []) or []:
            log.info("Optimisation: %s", warning)
        self._rerank()

    # -- results ----------------------------------------------------------

    def _rerank(self, *_args) -> None:
        if self._results is None:
            return
        metric = self.metric_box.currentData() or "net_profit"
        self._ranked = rank(self._results, metric,
                            minimum_trades=self.min_trades.value())
        self._fill_table(metric)
        self._draw_heatmap(metric)
        try:
            self.note.setText(overfitting_note(self._results, self._ranked, metric))
        except Exception:                   # pragma: no cover - defensive
            log.debug("Could not build the overfitting note", exc_info=True)
            self.note.setText("")

    def _fill_table(self, metric: str) -> None:
        param_names = [r["param"].name for r in self._rows
                       if r["enabled"].isChecked()]
        columns = ([("rank", "#", "int"), (metric, metric_label(metric), "auto"),
                    ("__robust", "Robustness", "auto")]
                   + [(name, name, "param") for name in param_names]
                   + [("total_trades", "Trades", "int"),
                      ("net_profit", "Net profit", "money"),
                      ("profit_factor", "PF", "ratio"),
                      ("sharpe_ratio", "Sharpe", "ratio"),
                      ("max_drawdown_pct", "Max DD", "pct")])

        self.table.setSortingEnabled(False)
        self.table.clear()
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels([c[1] for c in columns])
        self.table.setRowCount(len(self._ranked))

        robust_values = [neighbourhood_mean(self._results, row, metric)
                         for row in self._ranked]
        finite = [v for v in robust_values if math.isfinite(v)]
        best_metric = (self._ranked[0].value(metric) if self._ranked
                       else float("nan"))

        for r, row in enumerate(self._ranked):
            for c, (key, _title, kind) in enumerate(columns):
                if key == "rank":
                    value: Any = r + 1
                elif key == "__robust":
                    value = robust_values[r]
                elif kind == "param":
                    value = row.params.get(key)
                else:
                    value = row.metrics.get(key)
                item = QTableWidgetItem(self._format(value, key, kind, metric))
                item.setData(Qt.ItemDataRole.UserRole,
                             value if isinstance(value, (int, float)) else 0)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight |
                                      Qt.AlignmentFlag.AlignVCenter)
                if key in ("net_profit", metric) and isinstance(value, (int, float)):
                    item.setForeground(QBrush(QColor(
                        PALETTE.long if value > 0 else PALETTE.short
                        if value < 0 else PALETTE.text_dim)))
                if key == "max_drawdown_pct" and value:
                    item.setForeground(QBrush(QColor(PALETTE.short)))
                if key == "__robust":
                    item.setToolTip(
                        "The mean of the ranking metric over the neighbouring "
                        "parameter combinations. A result close to its own "
                        "value sits on a plateau; one far below it is a spike, "
                        "and a spike is what overfitting looks like.")
                    if (math.isfinite(value) and math.isfinite(best_metric)
                            and best_metric > 0 and value < best_metric * 0.4):
                        item.setForeground(QBrush(QColor(PALETTE.warning)))
                self.table.setItem(r, c, item)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        self.table.setSortingEnabled(True)
        if self._ranked:
            self.table.selectRow(0)
        del finite

    def _format(self, value: Any, key: str, kind: str, metric: str) -> str:
        if value is None:
            return "-"
        if isinstance(value, float):
            if math.isnan(value):
                return "-"
            if math.isinf(value):
                return "∞" if value > 0 else "-∞"
        if kind == "int" or key == "total_trades":
            try:
                return f"{int(value):,}"
            except (TypeError, ValueError):
                return str(value)
        if kind == "param":
            return (f"{value:g}" if isinstance(value, float) else str(value))
        if key == "money" or key == "net_profit" or kind == "money":
            return money(value)
        if kind == "pct" or key.endswith("_pct") or key == "win_rate":
            return pct(value)
        if kind == "ratio":
            return number(value, 2)
        # The ranking metric and the robustness column follow the metric's own
        # natural units.
        if metric.endswith("_pct") or metric == "win_rate":
            return pct(value)
        if metric in ("net_profit", "expectancy"):
            return money(value)
        return number(value, 2)

    def _draw_heatmap(self, metric: str) -> None:
        try:
            data = heatmap(self._results, metric)
        except Exception:                   # pragma: no cover - defensive
            log.debug("Heat map unavailable", exc_info=True)
            data = None
        self.heatmap.set_data(data, metric_label(metric))
        self.tabs.setTabEnabled(1, data is not None)

    def _apply_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        index = rows[0].row()
        item = self.table.item(index, 0)
        if item is None:
            return
        try:
            position = int(str(item.text()).replace(",", "")) - 1
        except ValueError:
            return
        if not (0 <= position < len(self._ranked)):
            return
        self.chosen_params = dict(self._ranked[position].params)
        self.accept()

    def closeEvent(self, event) -> None:    # noqa: N802
        if self._runner.busy:
            self._runner.cancel()
            self._runner.wait(3000)
        self.walkforward.shutdown()
        self.holdout.shutdown()
        super().closeEvent(event)


# --------------------------------------------------------------------------
# Heat map
# --------------------------------------------------------------------------

class _HeatmapWidget(QWidget):
    """A grid of cells coloured by the ranking metric.

    Only meaningful for a two-parameter sweep; anything else shows an
    explanation rather than a misleading picture.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: Any = None
        self._label = ""
        self.setMinimumHeight(260)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, data: Any, label: str) -> None:
        self._data = data
        self._label = label
        self.setToolTip("")
        self.update()

    def paintEvent(self, event) -> None:    # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(self.rect(), QColor(PALETTE.panel_bg))

        if self._data is None:
            painter.setPen(QPen(QColor(PALETTE.text_muted)))
            painter.setFont(Fonts.body(10))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter,
                "A heat map needs exactly two swept parameters.\n"
                "Tick two in the grid on the left and run again.")
            painter.end()
            return

        values = np.asarray(self._data.values, dtype="float64")
        xs = list(self._data.x_values)
        ys = list(self._data.y_values)
        if values.size == 0 or not xs or not ys:
            painter.end()
            return

        margin_left, margin_bottom, margin_top, margin_right = 74, 44, 34, 18
        width = max(1, self.width() - margin_left - margin_right)
        height = max(1, self.height() - margin_top - margin_bottom)
        cell_w = width / len(xs)
        cell_h = height / len(ys)

        finite = values[np.isfinite(values)]
        low = float(finite.min()) if finite.size else 0.0
        high = float(finite.max()) if finite.size else 1.0
        span = (high - low) or 1.0

        painter.setFont(Fonts.numeric(8))
        for row, y_value in enumerate(ys):
            for column, x_value in enumerate(xs):
                value = float(values[row, column])
                rect = QRectF(margin_left + column * cell_w,
                              margin_top + (len(ys) - 1 - row) * cell_h,
                              cell_w - 1, cell_h - 1)
                if not math.isfinite(value):
                    painter.fillRect(rect, QColor(PALETTE.panel_alt))
                    continue
                painter.fillRect(rect, _heat_colour((value - low) / span))
                if cell_w > 46 and cell_h > 18:
                    painter.setPen(QPen(QColor(PALETTE.text)))
                    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter,
                                     _compact(value))

        painter.setPen(QPen(QColor(PALETTE.axis_text)))
        painter.setFont(Fonts.numeric(8))
        for column, x_value in enumerate(xs):
            painter.drawText(
                QRectF(margin_left + column * cell_w, self.height() - margin_bottom + 4,
                       cell_w, 16),
                Qt.AlignmentFlag.AlignCenter, _compact(x_value))
        for row, y_value in enumerate(ys):
            painter.drawText(
                QRectF(4, margin_top + (len(ys) - 1 - row) * cell_h,
                       margin_left - 10, cell_h),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                _compact(y_value))

        painter.setPen(QPen(QColor(PALETTE.text_dim)))
        painter.setFont(Fonts.body(9))
        painter.drawText(
            QRectF(margin_left, 6, width, 20), Qt.AlignmentFlag.AlignLeft,
            f"{self._label}   —   {getattr(self._data, 'x_name', 'x')} across, "
            f"{getattr(self._data, 'y_name', 'y')} up")
        painter.drawText(
            QRectF(margin_left, self.height() - 18, width, 16),
            Qt.AlignmentFlag.AlignRight,
            f"{_compact(low)} … {_compact(high)}")
        painter.end()


def _heat_colour(fraction: float) -> QColor:
    """Blend from the loss colour through neutral to the profit colour."""
    fraction = max(0.0, min(1.0, fraction))
    base = QColor(PALETTE.panel_bg)
    target = QColor(PALETTE.short if fraction < 0.5 else PALETTE.long)
    weight = abs(fraction - 0.5) * 2.0 * 0.78
    return QColor(int(base.red() + (target.red() - base.red()) * weight),
                  int(base.green() + (target.green() - base.green()) * weight),
                  int(base.blue() + (target.blue() - base.blue()) * weight))


def _compact(value: Any) -> str:
    try:
        number_value = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number_value):
        return "-"
    if abs(number_value) >= 1_000_000:
        return f"{number_value / 1_000_000:,.1f}M"
    if abs(number_value) >= 1_000:
        return f"{number_value / 1_000:,.1f}k"
    if abs(number_value - round(number_value)) < 1e-9:
        return f"{int(round(number_value))}"
    return f"{number_value:,.2f}"


def _suggest(param: Any) -> tuple[float, float, float]:
    """A sensible starting range for a parameter, from its own bounds."""
    default = float(param.default if isinstance(param.default, (int, float)) else 10)
    step = float(param.step or (1 if param.kind == "int" else 0.1))
    low = default - 4 * step
    high = default + 4 * step
    if param.minimum is not None:
        low = max(low, float(param.minimum))
    if param.maximum is not None:
        high = min(high, float(param.maximum))
    if high <= low:
        high = low + step
    return low, high, max(step, (high - low) / 8 if high > low else step)


def _rough_seconds_per_run(bar_count: int) -> float:
    """A crude but honest per-combination estimate.

    Measured on this machine's engine throughput rather than guessed, and
    deliberately pessimistic: an estimate that undershoots is worse than one
    that overshoots.
    """
    return max(0.02, bar_count / 200_000.0)


def _worker_guess() -> int:
    import os

    return max(1, min(8, (os.cpu_count() or 2) - 1))


def _humanise(seconds: float) -> str:
    if seconds < 1:
        return "under a second"
    if seconds < 90:
        return f"{seconds:.0f} seconds"
    if seconds < 5400:
        return f"{seconds / 60:.0f} minutes"
    return f"{seconds / 3600:.1f} hours"
