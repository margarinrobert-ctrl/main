"""The strategy section of the left configuration panel.

Shows which strategy is selected, its rules in plain language, and an editor for
its parameters that is generated from the strategy file itself.  Adding a
parameter to a strategy therefore adds a control here with no UI code changes,
which is the whole point of strategies being data.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QPushButton,
                               QToolButton, QVBoxLayout, QWidget)

from ...core.errors import BacktesterError
from ...indicators.base import ParamSpec
from ...strategy.spec import StrategySpec
from ..theme import PALETTE, Fonts
from .common import Card, FieldSpec, FormPanel, hline


def _field_for(param: ParamSpec) -> FieldSpec:
    """Turn a strategy parameter into an editable field."""
    kind = {"int": "int", "float": "float", "bool": "bool",
            "choice": "choice", "source": "choice"}.get(param.kind, "text")
    choices = tuple((c, c) for c in param.choices)
    step = param.step if param.step else (1 if kind == "int" else 0.1)
    decimals = 0 if kind == "int" else (2 if float(step) >= 0.01 else 4)
    return FieldSpec(key=param.name, label=param.label or param.name, kind=kind,
                     default=param.default, minimum=param.minimum,
                     maximum=param.maximum, step=step, decimals=decimals,
                     choices=choices, tooltip=param.help)


class StrategyPanel(QWidget):
    """Strategy selection, management and parameter editing."""

    strategySelected = Signal(str)
    parametersChanged = Signal()
    newRequested = Signal()
    editRequested = Signal()
    duplicateRequested = Signal()
    renameRequested = Signal()
    deleteRequested = Signal()
    importRequested = Signal()
    exportRequested = Signal()
    saveRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store: Any = None
        self._spec: StrategySpec | None = None
        self._form: FormPanel | None = None
        self._loading = False
        self._build_ui()

    # -- construction ----------------------------------------------------

    def _build_ui(self) -> None:
        from ..icons import icon

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.card = Card("Strategy")
        body = self.card.body()

        row = QHBoxLayout()
        row.setSpacing(5)
        self.strategy_box = QComboBox()
        self.strategy_box.setMinimumWidth(140)
        self.strategy_box.currentIndexChanged.connect(self._on_selected)
        row.addWidget(self.strategy_box, 1)
        edit = QToolButton()
        edit.setIcon(icon("strategy", 16))
        edit.setIconSize(QSize(16, 16))
        edit.setFixedSize(26, 24)
        edit.setToolTip("Edit the entry and exit rules")
        edit.clicked.connect(self.editRequested.emit)
        row.addWidget(edit)
        self.card.add_layout(row)

        tools = QHBoxLayout()
        tools.setSpacing(4)
        for ico, tip, sig in (("plus", "New strategy", self.newRequested),
                              ("copy", "Duplicate", self.duplicateRequested),
                              ("rename", "Rename", self.renameRequested),
                              ("save", "Save", self.saveRequested),
                              ("import", "Import from file", self.importRequested),
                              ("export", "Export to file", self.exportRequested),
                              ("trash", "Delete", self.deleteRequested)):
            b = QToolButton()
            b.setIcon(icon(ico, 17, PALETTE.text))
            b.setIconSize(QSize(17, 17))
            b.setToolTip(tip)
            b.setFixedSize(30, 26)
            b.clicked.connect(sig.emit)
            tools.addWidget(b)
        tools.addStretch(1)
        self.card.add_layout(tools)

        self.description = QLabel("")
        self.description.setWordWrap(True)
        self.description.setFont(Fonts.body(8))
        self.description.setStyleSheet(f"color:{PALETTE.text_muted};")
        self.card.add(self.description)

        self.card.add(hline())

        self.rules_label = QLabel("")
        self.rules_label.setWordWrap(True)
        self.rules_label.setFont(Fonts.numeric(8))
        self.rules_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self.card.add(self.rules_label)

        self.params_header = QLabel("PARAMETERS")
        self.params_header.setObjectName("SectionHeader")
        self.params_header.setFont(Fonts.section())
        self.card.add(self.params_header)

        self.params_holder = QWidget()
        self.params_layout = QVBoxLayout(self.params_holder)
        self.params_layout.setContentsMargins(0, 0, 0, 0)
        self.params_layout.setSpacing(4)
        self.card.add(self.params_holder)

        reset_row = QHBoxLayout()
        reset_row.addStretch(1)
        self.reset_btn = QToolButton()
        self.reset_btn.setText("Reset to defaults")
        self.reset_btn.clicked.connect(self._reset_params)
        reset_row.addWidget(self.reset_btn)
        self.card.add_layout(reset_row)

        self.warning_label = QLabel("")
        self.warning_label.setWordWrap(True)
        self.warning_label.setObjectName("Warning")
        self.warning_label.setFont(Fonts.body(8))
        self.warning_label.hide()
        self.card.add(self.warning_label)

        lay.addWidget(self.card)

    # -- store -----------------------------------------------------------

    def set_store(self, store: Any) -> None:
        self._store = store
        self.refresh()

    def refresh(self, select_id: str | None = None) -> None:
        if self._store is None:
            return
        keep = select_id or self.current_strategy_id()
        self._loading = True
        try:
            self.strategy_box.clear()
            try:
                entries = self._store.list()
            except BacktesterError:
                entries = []
            for entry in entries:
                name = getattr(entry, "name", None) or str(entry)
                sid = getattr(entry, "id", None) or name
                self.strategy_box.addItem(name, sid)
            idx = self.strategy_box.findData(keep) if keep else -1
            self.strategy_box.setCurrentIndex(max(0, idx))
        finally:
            self._loading = False
        self._on_selected()

    def current_strategy_id(self) -> str:
        return self.strategy_box.currentData() or ""

    # -- spec ------------------------------------------------------------

    def set_spec(self, spec: StrategySpec | None) -> None:
        """Show a strategy and rebuild its parameter editor."""
        self._spec = spec
        if spec is None:
            self.description.setText("")
            self.rules_label.setText("")
            self._rebuild_params([])
            self.warning_label.hide()
            return

        self.description.setText(spec.description or "")
        self.description.setVisible(bool(spec.description))
        self.rules_label.setText(self._render_rules(spec))
        self._rebuild_params(spec.params)

        try:
            warnings = spec.validate()
        except BacktesterError as exc:
            self.warning_label.setText(f"⚠ {exc.user_message}")
            self.warning_label.show()
            return
        if warnings:
            self.warning_label.setText("⚠ " + "\n⚠ ".join(warnings))
            self.warning_label.show()
        else:
            self.warning_label.hide()

    def spec(self) -> StrategySpec | None:
        return self._spec

    def _render_rules(self, spec: StrategySpec) -> str:
        lines: list[str] = []
        colours = {"Long entry": PALETTE.long, "Short entry": PALETTE.short,
                   "Long exit": PALETTE.text_dim, "Short exit": PALETTE.text_dim}
        for line in spec.summary_lines():
            head, _, rest = line.partition(":")
            colour = colours.get(head.strip(), PALETTE.text_muted)
            lines.append(
                f"<span style='color:{colour}'>{head.strip()}</span>"
                f"<span style='color:{PALETTE.text}'>&nbsp;{rest.strip()}</span>")
        return "<br>".join(lines) if lines else (
            f"<span style='color:{PALETTE.text_muted}'>No rules defined.</span>")

    # -- parameters ------------------------------------------------------

    def _rebuild_params(self, params: list[ParamSpec]) -> None:
        if self._form is not None:
            self._form.setParent(None)
            self._form = None
        if not params:
            self.params_header.hide()
            self.reset_btn.hide()
            return
        self.params_header.show()
        self.reset_btn.show()
        self._form = FormPanel([_field_for(p) for p in params], label_width=110)
        self._form.changed.connect(self._on_params_changed)
        self.params_layout.addWidget(self._form)

    def parameter_overrides(self) -> dict[str, Any]:
        """Current parameter values, or an empty dict when there are none."""
        if self._form is None:
            return {}
        return self._form.values()

    def set_parameter_values(self, values: dict[str, Any]) -> None:
        if self._form is not None:
            self._form.set_values(values)

    def _reset_params(self) -> None:
        if self._spec is not None and self._form is not None:
            self._form.set_values({p.name: p.default for p in self._spec.params})
            self.parametersChanged.emit()

    def _on_params_changed(self) -> None:
        if not self._loading:
            self.parametersChanged.emit()

    def _on_selected(self, *_args) -> None:
        if not self._loading:
            self.strategySelected.emit(self.current_strategy_id())
