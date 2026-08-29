"""Building a strategy without writing code.

This dialog is what makes "strategies are data" true for a user rather than
just for the file format. Everything a :class:`StrategySpec` can express is
reachable here: indicator slots with parameters that may be literals or named
strategy parameters, four rule trees of arbitrarily nested AND/OR/NOT groups,
and the risk and exit settings the strategy carries with it.

The rule tree is the part that has to be got right. Each node is edited in a
panel beside the tree rather than in another modal, and the rule is rendered
back into English under the tree as it is built, so what the strategy *means* is
always on screen next to what it looks like.
"""

from __future__ import annotations

import copy
from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog,
                               QDoubleSpinBox, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPlainTextEdit, QPushButton,
                               QScrollArea, QSpinBox, QSplitter, QTabWidget,
                               QTableWidget, QTableWidgetItem, QToolButton,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from ...core.errors import BacktesterError, StrategyError
from ...indicators.base import ParamSpec
from ...indicators.registry import REGISTRY
from ...logging_setup import get_logger
from ...strategy.spec import (Always, Compare, Condition, ConditionGroup,
                              ConstOperand, Cross, ExprOperand,
                              IndicatorOperand, IndicatorSlot, ParamOperand,
                              PriceOperand, SessionWindow, State,
                              StrategySpec, Vote)
from ..theme import PALETTE, Fonts
from ..widgets.common import (Card, ask_text, confirm, hline, show_error,
                              show_info, show_warning)
from ..widgets.risk_panel import RiskPanel

log = get_logger(__name__)

_PRICE_FIELDS = ("close", "open", "high", "low", "volume", "hlc3", "hl2", "ohlc4")
_COMPARE_OPS = ((">", "is greater than"), (">=", "is at least"),
                ("<", "is less than"), ("<=", "is at most"),
                ("==", "equals"), ("!=", "does not equal"))
_CROSS_DIRECTIONS = (("above", "crosses above"), ("below", "crosses below"),
                     ("any", "crosses either way"))
_STATE_OPS = (("rising", "is rising"), ("falling", "is falling"),
              ("positive", "is positive"), ("negative", "is negative"),
              ("increasing_for", "has risen for N bars"),
              ("decreasing_for", "has fallen for N bars"))
_TIMEZONES = ("America/New_York", "America/Chicago", "Europe/London",
              "Europe/Berlin", "Asia/Tokyo", "Asia/Singapore", "UTC")

_RULE_SLOTS = (("entry_long", "Long entry"), ("exit_long", "Long exit"),
               ("entry_short", "Short entry"), ("exit_short", "Short exit"))


class StrategyEditor(QDialog):
    """Edit a strategy.  The caller reads :attr:`spec` after ``Accepted``."""

    def __init__(self, spec: StrategySpec, parent: QWidget | None = None,
                 bars: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Strategy — {spec.name}")
        self.resize(1240, 840)
        self.spec = spec
        self._bars = bars
        self._loading = False

        self._build_ui()
        self._load_spec()

    # -- construction ----------------------------------------------------

    def _build_ui(self) -> None:
        from ..icons import icon

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(8)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._build_general_tab(), icon("info", 15), "General")
        self.tabs.addTab(self._build_indicator_tab(), icon("indicator", 15),
                         "Indicators")
        self.tabs.addTab(self._build_rules_tab(), icon("strategy", 15), "Rules")
        self.tabs.addTab(self._build_parameter_tab(), icon("optimize", 15),
                         "Parameters")
        self.tabs.addTab(self._build_risk_tab(), icon("shield", 15),
                         "Risk and Exits")
        outer.addWidget(self.tabs, 1)

        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setFont(Fonts.body(9))
        self.message.setMinimumHeight(30)
        outer.addWidget(self.message)

        row = QHBoxLayout()
        preview = QPushButton("  Preview Signals")
        preview.setIcon(icon("candles", 15))
        preview.setToolTip("Compile the strategy against the loaded data and "
                           "report how often each rule fires")
        preview.setEnabled(self._bars is not None)
        preview.clicked.connect(self._preview)
        row.addWidget(preview)
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        save = QPushButton("Save Strategy")
        save.setObjectName("Primary")
        save.setDefault(True)
        save.clicked.connect(self._accept)
        row.addWidget(save)
        outer.addLayout(row)

    # -- general ---------------------------------------------------------

    def _build_general_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        card = Card("Identity")
        form = QFormLayout()
        form.setHorizontalSpacing(9)
        form.setVerticalSpacing(6)
        self.name_edit = QLineEdit()
        form.addRow(self._label("Name"), self.name_edit)
        self.author_edit = QLineEdit()
        form.addRow(self._label("Author"), self.author_edit)
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("comma separated")
        form.addRow(self._label("Tags"), self.tags_edit)
        card.add_layout(form)
        card.add(self._label("Description"))
        self.description_edit = QPlainTextEdit()
        self.description_edit.setMaximumHeight(120)
        card.add(self.description_edit)
        lay.addWidget(card)

        summary_card = Card("Rules As Written")
        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setFont(Fonts.numeric(9))
        self.summary_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        summary_card.add(self.summary_label)
        lay.addWidget(summary_card)
        lay.addStretch(1)
        return page

    # -- indicators ------------------------------------------------------

    def _build_indicator_tab(self) -> QWidget:
        from ..icons import icon

        page = QWidget()
        lay = QHBoxLayout(page)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(9)

        left = QVBoxLayout()
        left.setSpacing(6)
        self.slot_list = QListWidget()
        self.slot_list.setFixedWidth(230)
        self.slot_list.setFont(Fonts.numeric(9))
        self.slot_list.currentRowChanged.connect(self._on_slot_selected)
        left.addWidget(self.slot_list, 1)
        buttons = QHBoxLayout()
        buttons.setSpacing(4)
        for ico, tip, slot in (("plus", "Add an indicator", self._add_slot),
                               ("copy", "Duplicate", self._duplicate_slot),
                               ("trash", "Remove", self._remove_slot)):
            button = QPushButton()
            button.setIcon(icon(ico, 16, PALETTE.text))
            button.setToolTip(tip)
            button.setFixedHeight(26)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        left.addLayout(buttons)
        lay.addLayout(left)

        self.slot_card = Card("Indicator")
        self.slot_form_holder = QWidget()
        self.slot_form_layout = QVBoxLayout(self.slot_form_holder)
        self.slot_form_layout.setContentsMargins(0, 0, 0, 0)
        self.slot_form_layout.setSpacing(6)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.slot_form_holder)
        self.slot_card.add(scroll, 1)
        lay.addWidget(self.slot_card, 1)
        return page

    def _rebuild_slot_editor(self) -> None:
        while self.slot_form_layout.count():
            item = self.slot_form_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        index = self.slot_list.currentRow()
        if not (0 <= index < len(self.spec.indicators)):
            return
        slot = self.spec.indicators[index]
        try:
            definition = REGISTRY.get(slot.indicator)
        except BacktesterError as exc:
            self.slot_form_layout.addWidget(QLabel(exc.user_message))
            return

        header = QLabel(f"<b>{definition.name}</b> — {definition.description}")
        header.setWordWrap(True)
        header.setStyleSheet(f"color:{PALETTE.text_dim};")
        self.slot_form_layout.addWidget(header)

        form = QFormLayout()
        form.setHorizontalSpacing(9)
        form.setVerticalSpacing(5)

        ref_edit = QLineEdit(slot.ref)
        ref_edit.setToolTip("The name rules use to refer to this indicator.")
        ref_edit.editingFinished.connect(
            lambda: self._rename_slot(index, ref_edit.text().strip()))
        form.addRow(self._label("Reference name"), ref_edit)

        if definition.uses_source:
            source_box = QComboBox()
            for field in _PRICE_FIELDS:
                source_box.addItem(field, field)
            position = source_box.findData(slot.source or definition.default_source)
            source_box.setCurrentIndex(max(0, position))
            source_box.currentIndexChanged.connect(
                lambda _i, b=source_box: self._set_slot(index, "source", b.currentData()))
            form.addRow(self._label("Price source"), source_box)

        panel_box = QComboBox()
        panel_box.addItem("Automatic", "auto")
        panel_box.addItem("On the price chart", "price")
        panel_box.addItem("Its own panel", "sub")
        panel_box.setCurrentIndex(max(0, panel_box.findData(slot.panel or "auto")))
        panel_box.currentIndexChanged.connect(
            lambda _i, b=panel_box: self._set_slot(index, "panel", b.currentData()))
        form.addRow(self._label("Draw on"), panel_box)
        self.slot_form_layout.addLayout(form)

        self.slot_form_layout.addWidget(hline())
        params_head = QLabel("PARAMETERS")
        params_head.setFont(Fonts.section())
        params_head.setStyleSheet(f"color:{PALETTE.text_dim};")
        self.slot_form_layout.addWidget(params_head)

        for param in definition.params:
            self.slot_form_layout.addWidget(
                _SlotParamRow(self, index, slot, param))

        if not definition.params:
            none = QLabel("This indicator takes no parameters.")
            none.setStyleSheet(f"color:{PALETTE.text_muted};")
            self.slot_form_layout.addWidget(none)
        self.slot_form_layout.addStretch(1)

    # -- rules -----------------------------------------------------------

    def _build_rules_tab(self) -> QWidget:
        from ..icons import icon

        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(7)

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self._label("Rule"))
        self.rule_box = QComboBox()
        for key, title in _RULE_SLOTS:
            self.rule_box.addItem(title, key)
        self.rule_box.currentIndexChanged.connect(self._reload_tree)
        top.addWidget(self.rule_box)
        top.addStretch(1)
        for text, ico, tip, slot in (
                ("Common rule", "strategy",
                 "Add a whole rule -- its indicators and its condition -- in "
                 "one step", self._add_preset),
                ("Condition", "plus", "Add a condition to the selected group",
                 self._add_condition),
                ("Group", "layers", "Add a nested AND/OR group", self._add_group),
                ("Duplicate", "copy", "Copy the selected node beside itself",
                 self._duplicate_node),
                ("Up", "arrow-up", "Move the selected node earlier",
                 lambda: self._move_node(-1)),
                ("Down", "arrow-down", "Move the selected node later",
                 lambda: self._move_node(1)),
                ("Remove", "trash", "Remove the selected node (Delete)",
                 self._remove_node)):
            button = QPushButton(f"  {text}")
            button.setIcon(icon(ico, 15))
            button.setToolTip(tip)
            button.clicked.connect(slot)
            top.addWidget(button)
        lay.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        self.tree = QTreeWidget()
        # Delete removes the selected node.  Scoped to the tree so pressing it
        # while editing a number in the panel beside it does not delete the
        # condition being edited.
        remove_key = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.tree)
        remove_key.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        remove_key.activated.connect(self._remove_node)
        self.tree.setHeaderLabels(["Rule"])
        self.tree.setFont(Fonts.numeric(9))
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.currentItemChanged.connect(self._on_node_selected)
        splitter.addWidget(self.tree)

        self.node_card = Card("Selected Node")
        self.node_holder = QWidget()
        self.node_layout = QVBoxLayout(self.node_holder)
        self.node_layout.setContentsMargins(0, 0, 0, 0)
        self.node_layout.setSpacing(6)
        self.node_card.add(self.node_holder, 1)
        splitter.addWidget(self.node_card)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)
        lay.addWidget(splitter, 1)

        self.rule_english = QLabel("")
        self.rule_english.setWordWrap(True)
        self.rule_english.setFont(Fonts.numeric(10))
        self.rule_english.setMinimumHeight(46)
        self.rule_english.setStyleSheet(
            f"background:{PALETTE.panel_alt}; border:1px solid {PALETTE.border};"
            f"border-radius:5px; padding:8px; color:{PALETTE.text};")
        lay.addWidget(self.rule_english)
        return page

    # -- parameters ------------------------------------------------------

    def _build_parameter_tab(self) -> QWidget:
        from ..icons import icon

        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(7)

        explain = QLabel(
            "Parameters are the numbers the optimiser sweeps. Give one a name "
            "here, then use it as an indicator's period or as the right-hand "
            "side of a comparison, and the whole strategy becomes tunable "
            "without editing any rule.")
        explain.setWordWrap(True)
        explain.setObjectName("Hint")
        explain.setFont(Fonts.body(9))
        lay.addWidget(explain)

        self.param_table = QTableWidget(0, 7)
        self.param_table.setHorizontalHeaderLabels(
            ["Name", "Label", "Type", "Default", "Minimum", "Maximum", "Step"])
        self.param_table.setAlternatingRowColors(True)
        self.param_table.setShowGrid(False)
        self.param_table.setFont(Fonts.numeric(9))
        self.param_table.verticalHeader().setVisible(False)
        self.param_table.verticalHeader().setDefaultSectionSize(24)
        self.param_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.param_table.itemChanged.connect(self._on_param_edited)
        lay.addWidget(self.param_table, 1)

        row = QHBoxLayout()
        for text, ico, slot in (("Add", "plus", self._add_param),
                                ("Remove", "trash", self._remove_param)):
            button = QPushButton(f"  {text}")
            button.setIcon(icon(ico, 15))
            button.clicked.connect(slot)
            row.addWidget(button)
        row.addStretch(1)
        lay.addLayout(row)
        return page

    def _build_risk_tab(self) -> QWidget:
        page = QScrollArea()
        page.setWidgetResizable(True)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(10, 10, 10, 10)
        self.risk_panel = RiskPanel()
        lay.addWidget(self.risk_panel)
        lay.addStretch(1)
        page.setWidget(inner)
        return page

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setFont(Fonts.body(9))
        label.setStyleSheet(f"color:{PALETTE.text_dim};")
        return label

    # ------------------------------------------------------------------
    # Loading and saving
    # ------------------------------------------------------------------

    def _load_spec(self) -> None:
        self._loading = True
        try:
            self.name_edit.setText(self.spec.name)
            self.author_edit.setText(self.spec.author)
            self.tags_edit.setText(", ".join(self.spec.tags))
            self.description_edit.setPlainText(self.spec.description)
            self._reload_slots()
            self._reload_params()
            self._reload_tree()
            from ...core.types import BacktestConfig

            self.risk_panel.apply_config(BacktestConfig(
                starting_capital=self.spec.risk.starting_capital,
                risk=self.spec.risk, costs=self.spec.costs,
                session=self.spec.session, exits=self.spec.exits,
                execution=self.spec.execution))
        finally:
            self._loading = False
        self._refresh_summary()

    def _collect(self) -> None:
        """Fold the editable fields back into the spec."""
        self.spec.name = self.name_edit.text().strip() or "Untitled"
        self.spec.author = self.author_edit.text().strip()
        self.spec.tags = [t.strip() for t in self.tags_edit.text().split(",")
                          if t.strip()]
        self.spec.description = self.description_edit.toPlainText().strip()
        try:
            config = self.risk_panel.build_config()
        except BacktesterError:
            return
        self.spec.risk = config.risk
        self.spec.costs = config.costs
        self.spec.exits = config.exits
        self.spec.session = config.session
        self.spec.execution = config.execution

    def _accept(self) -> None:
        self._collect()
        try:
            warnings = self.spec.validate()
        except StrategyError as exc:
            self._say(exc.user_message, PALETTE.danger)
            show_error(self, exc)
            return
        if warnings:
            show_warning(self, "Saved With Warnings",
                         "This strategy is valid but worth a second look:\n\n• "
                         + "\n• ".join(warnings))
        self.accept()

    def _preview(self) -> None:
        if self._bars is None:
            return
        self._collect()
        try:
            self.spec.validate()
            from ...strategy.compiler import compile_strategy

            compiled = compile_strategy(self.spec, self._bars)
        except BacktesterError as exc:
            self._say(exc.user_message, PALETTE.danger)
            return

        # Only report on rules the strategy actually defines: saying that a
        # short rule never fires when there is no short rule is noise, and noise
        # in a diagnostic teaches people to ignore it.
        counts = {title: int(getattr(compiled, key).sum())
                  for key, title in _RULE_SLOTS
                  if getattr(self.spec, key, None) is not None
                  and getattr(compiled, key, None) is not None}
        total = len(self._bars)
        parts = [f"{title}: {n:,}" for title, n in counts.items()]
        dead = [title for title, n in counts.items()
                if n == 0 and "entry" in title.lower()]
        text = (f"Over {total:,} bars — " + "   ".join(parts)
                + f"   (warm-up {compiled.warmup} bars)")
        if dead:
            text += (f"    {', '.join(dead)} never fires: check the thresholds, "
                     f"the session filter, and whether the indicator is still "
                     f"warming up over most of the range.")
            self._say(text, PALETTE.warning)
        else:
            self._say(text, PALETTE.success)

    def _say(self, text: str, colour: str) -> None:
        self.message.setText(text)
        self.message.setStyleSheet(f"color:{colour};")

    def _refresh_summary(self) -> None:
        lines = self.spec.summary_lines()
        self.summary_label.setText(
            "<br>".join(f"<span style='color:{PALETTE.text_dim}'>{line[:12]}</span>"
                        f"<span style='color:{PALETTE.text}'>{line[12:]}</span>"
                        for line in lines)
            or f"<span style='color:{PALETTE.text_muted}'>No rules yet.</span>")

    # ------------------------------------------------------------------
    # Indicator slots
    # ------------------------------------------------------------------

    def _reload_slots(self) -> None:
        current = self.slot_list.currentRow()
        self.slot_list.clear()
        for slot in self.spec.indicators:
            entry = QListWidgetItem(f"{slot.ref}    {slot.display_label()}")
            self.slot_list.addItem(entry)
        if self.spec.indicators:
            self.slot_list.setCurrentRow(
                min(max(0, current), len(self.spec.indicators) - 1))
        self._rebuild_slot_editor()

    def _on_slot_selected(self, *_args) -> None:
        if not self._loading:
            self._rebuild_slot_editor()

    def _add_slot(self) -> None:
        dialog = _IndicatorPicker(self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.key:
            return
        definition = REGISTRY.get(dialog.key)
        base = definition.key.lower()
        ref = base
        existing = {s.ref for s in self.spec.indicators}
        counter = 2
        while ref in existing:
            ref = f"{base}{counter}"
            counter += 1
        self.spec.indicators.append(IndicatorSlot(
            ref=ref, indicator=definition.key,
            params=dict(definition.default_params()),
            source=definition.default_source))
        self._reload_slots()
        self.slot_list.setCurrentRow(len(self.spec.indicators) - 1)
        self._refresh_summary()

    def _duplicate_slot(self) -> None:
        index = self.slot_list.currentRow()
        if not (0 <= index < len(self.spec.indicators)):
            return
        source = self.spec.indicators[index]
        existing = {s.ref for s in self.spec.indicators}
        ref, counter = f"{source.ref}2", 2
        while ref in existing:
            counter += 1
            ref = f"{source.ref}{counter}"
        clone = copy.deepcopy(source)
        clone.ref = ref
        self.spec.indicators.append(clone)
        self._reload_slots()

    def _remove_slot(self) -> None:
        index = self.slot_list.currentRow()
        if not (0 <= index < len(self.spec.indicators)):
            return
        slot = self.spec.indicators[index]
        used = set()
        for key, _title in _RULE_SLOTS:
            condition = getattr(self.spec, key, None)
            if condition is not None:
                used |= condition.referenced_indicators()
        if slot.ref in used and not confirm(
                self, "Remove Indicator",
                f"'{slot.ref}' is used by a rule. Removing it will leave the "
                f"strategy invalid until you fix that rule. Remove it anyway?",
                confirm_text="Remove"):
            return
        del self.spec.indicators[index]
        self._reload_slots()
        self._refresh_summary()

    def _rename_slot(self, index: int, new_ref: str) -> None:
        if not new_ref or not (0 <= index < len(self.spec.indicators)):
            return
        old = self.spec.indicators[index].ref
        if new_ref == old:
            return
        if any(s.ref == new_ref for s in self.spec.indicators):
            self._say(f"Another indicator is already called '{new_ref}'.",
                      PALETTE.danger)
            return
        self.spec.indicators[index].ref = new_ref
        # Rules refer to slots by name, so a rename has to follow through.
        for key, _title in _RULE_SLOTS:
            condition = getattr(self.spec, key, None)
            if condition is not None:
                _rename_in_condition(condition, old, new_ref)
        self._reload_slots()
        self._reload_tree()
        self._refresh_summary()

    def _set_slot(self, index: int, attribute: str, value: Any) -> None:
        if self._loading or not (0 <= index < len(self.spec.indicators)):
            return
        setattr(self.spec.indicators[index], attribute, value)
        self._reload_slots()

    def set_slot_param(self, index: int, name: str, value: Any) -> None:
        if not (0 <= index < len(self.spec.indicators)):
            return
        self.spec.indicators[index].params[name] = value
        item = self.slot_list.item(index)
        if item is not None:
            item.setText(f"{self.spec.indicators[index].ref}    "
                         f"{self.spec.indicators[index].display_label()}")

    def parameter_names(self) -> list[str]:
        return [p.name for p in self.spec.params]

    def indicator_refs(self) -> list[str]:
        return [s.ref for s in self.spec.indicators]

    def indicator_outputs(self, ref: str) -> list[str]:
        for slot in self.spec.indicators:
            if slot.ref == ref:
                try:
                    return list(REGISTRY.get(slot.indicator).outputs)
                except BacktesterError:
                    return ["value"]
        return ["value"]

    # ------------------------------------------------------------------
    # Rule tree
    # ------------------------------------------------------------------

    def _current_rule_key(self) -> str:
        return self.rule_box.currentData() or "entry_long"

    def _current_root(self) -> ConditionGroup:
        key = self._current_rule_key()
        condition = getattr(self.spec, key, None)
        if not isinstance(condition, ConditionGroup):
            # Every tree is rooted in an AND group so there is always somewhere
            # to add to, even when the rule is empty or a bare condition.
            root = ConditionGroup("AND", [condition] if condition is not None else [])
            setattr(self.spec, key, root)
            return root
        return condition

    def _reload_tree(self, *_args) -> None:
        self.tree.clear()
        root = self._current_root()
        item = self._add_tree_item(None, root)
        self.tree.addTopLevelItem(item)
        self.tree.expandAll()
        self.tree.setCurrentItem(item)
        self._refresh_english()

    def _add_tree_item(self, parent: QTreeWidgetItem | None,
                       node: Any) -> QTreeWidgetItem:
        item = QTreeWidgetItem([_node_title(node)])
        item.setData(0, Qt.ItemDataRole.UserRole, node)
        if parent is not None:
            parent.addChild(item)
        if isinstance(node, (ConditionGroup, Vote)):
            for child in node.children:
                self._add_tree_item(item, child)
        return item

    def _on_node_selected(self, *_args) -> None:
        while self.node_layout.count():
            entry = self.node_layout.takeAt(0)
            widget = entry.widget()
            if widget is not None:
                widget.deleteLater()
        item = self.tree.currentItem()
        if item is None:
            return
        node = item.data(0, Qt.ItemDataRole.UserRole)
        editor = _node_editor(self, node)
        if editor is not None:
            self.node_layout.addWidget(editor)
        self.node_layout.addStretch(1)

    def node_changed(self) -> None:
        """Called by a node editor after it mutates the tree."""
        item = self.tree.currentItem()
        if item is not None:
            node = item.data(0, Qt.ItemDataRole.UserRole)
            item.setText(0, _node_title(node))
        self._refresh_english()
        self._refresh_summary()

    def _refresh_english(self) -> None:
        root = self._current_root()
        title = self.rule_box.currentText()
        try:
            text = root.describe()
        except Exception:                   # pragma: no cover - defensive
            text = "(incomplete)"
        colour = PALETTE.long if "Long" in title else PALETTE.short
        self.rule_english.setText(
            f"<span style='color:{colour}'>{title}:</span> "
            f"<span style='color:{PALETTE.text}'>{text}</span>")

    def _selected_group(self) -> tuple[ConditionGroup, QTreeWidgetItem]:
        """The group a new node should be added to, and its tree item."""
        item = self.tree.currentItem()
        if item is None:
            root_item = self.tree.topLevelItem(0)
            return self._current_root(), root_item
        node = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(node, (ConditionGroup, Vote)):
            return node, item
        parent = item.parent()
        if parent is not None:
            return parent.data(0, Qt.ItemDataRole.UserRole), parent
        return self._current_root(), self.tree.topLevelItem(0)

    def _add_condition(self) -> None:
        dialog = _ConditionPicker(self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.condition is None:
            return
        group, item = self._selected_group()
        group.children.append(dialog.condition)
        child = self._add_tree_item(item, dialog.condition)
        item.setExpanded(True)
        self.tree.setCurrentItem(child)
        self._refresh_english()
        self._refresh_summary()

    def _add_group(self) -> None:
        group, item = self._selected_group()
        new_group = ConditionGroup("OR", [])
        group.children.append(new_group)
        child = self._add_tree_item(item, new_group)
        item.setExpanded(True)
        self.tree.setCurrentItem(child)
        self._refresh_english()

    def _duplicate_node(self) -> None:
        """Copy the selected node in beside itself.

        A deep copy through the dictionary form, not a shared reference: two
        tree items pointing at the same condition object look independent and
        then change together, which is the worst kind of editor bug because
        the strategy that gets saved is not the one on screen.
        """
        item = self.tree.currentItem()
        if item is None or item.parent() is None:
            show_info(self, "Duplicate",
                      "The outermost group cannot be duplicated. Select a "
                      "condition or a nested group inside it.")
            return
        parent_item = item.parent()
        parent_node = parent_item.data(0, Qt.ItemDataRole.UserRole)
        node = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(parent_node, (ConditionGroup, Vote)) or \
                node not in parent_node.children:
            return
        copy = Condition.from_dict(node.to_dict())
        parent_node.children.insert(parent_node.children.index(node) + 1, copy)
        self._reload_tree()
        self._select_node(copy)

    def _move_node(self, delta: int) -> None:
        """Move the selected node one place within its own group.

        Within its group only.  Dragging a condition out of an OR and into the
        AND above it changes what the rule means, and doing that by nudging an
        arrow key is not something anyone would intend.
        """
        item = self.tree.currentItem()
        if item is None or item.parent() is None:
            return
        parent_node = item.parent().data(0, Qt.ItemDataRole.UserRole)
        node = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(parent_node, (ConditionGroup, Vote)) or \
                node not in parent_node.children:
            return
        children = parent_node.children
        index = children.index(node)
        target = index + delta
        if not 0 <= target < len(children):
            return
        children[index], children[target] = children[target], children[index]
        self._reload_tree()
        self._select_node(node)

    def _select_node(self, node: Any) -> None:
        """Put the cursor back on ``node`` after the tree was rebuilt."""
        stack = [self.tree.topLevelItem(i)
                 for i in range(self.tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item is None:
                continue
            if item.data(0, Qt.ItemDataRole.UserRole) is node:
                self.tree.setCurrentItem(item)
                return
            stack.extend(item.child(i) for i in range(item.childCount()))

    def _add_preset(self) -> None:
        """Add a whole rule: its indicators, its parameters and its condition.

        The click count is the point.  "Price closes above a 200 EMA" is three
        objects -- a slot, a parameter and a comparison -- and building it by
        hand means the indicator tab, then the rule tab, then two operand
        editors.  Here it is one dialog and one number.
        """
        dialog = _PresetPicker(self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.preset is None:
            return
        group, item = self._selected_group()
        try:
            condition = dialog.preset.build(self.spec, dialog.values)
        except Exception as exc:            # noqa: BLE001
            log.exception("Building a preset rule failed")
            show_error(self, exc, "Could not add that rule")
            return
        group.children.append(condition)
        self._reload_slots()
        self._reload_params()
        self._reload_tree()
        self._select_node(condition)
        self._refresh_summary()

    def _remove_node(self) -> None:
        item = self.tree.currentItem()
        if item is None or item.parent() is None:
            show_info(self, "Remove", "The outermost group cannot be removed. "
                                      "Remove the conditions inside it instead.")
            return
        parent_item = item.parent()
        parent_node = parent_item.data(0, Qt.ItemDataRole.UserRole)
        node = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(parent_node, (ConditionGroup, Vote)) and \
                node in parent_node.children:
            parent_node.children.remove(node)
        parent_item.removeChild(item)
        self.tree.setCurrentItem(parent_item)
        self._refresh_english()
        self._refresh_summary()

    # ------------------------------------------------------------------
    # Strategy parameters
    # ------------------------------------------------------------------

    def _reload_params(self) -> None:
        self._loading = True
        try:
            self.param_table.setRowCount(len(self.spec.params))
            for row, param in enumerate(self.spec.params):
                cells = (param.name, param.label, param.kind,
                         param.default, param.minimum, param.maximum, param.step)
                for column, value in enumerate(cells):
                    item = QTableWidgetItem("" if value is None else str(value))
                    self.param_table.setItem(row, column, item)
        finally:
            self._loading = False

    def _on_param_edited(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        row = item.row()
        if not (0 <= row < len(self.spec.params)):
            return
        values = [self.param_table.item(row, c).text()
                  if self.param_table.item(row, c) else ""
                  for c in range(7)]
        old = self.spec.params[row]
        try:
            kind = values[2] if values[2] in ("int", "float", "bool", "choice") \
                else old.kind
            cast = int if kind == "int" else float
            new = ParamSpec(
                name=values[0].strip() or old.name,
                label=values[1].strip() or values[0].strip() or old.name,
                kind=kind,
                default=cast(values[3]) if values[3] else old.default,
                minimum=cast(values[4]) if values[4] else None,
                maximum=cast(values[5]) if values[5] else None,
                step=cast(values[6]) if values[6] else old.step,
                choices=old.choices, help=old.help)
        except (TypeError, ValueError):
            self._say(f"'{values[3]}' is not a valid {values[2]} value.",
                      PALETTE.danger)
            self._reload_params()
            return
        self.spec.params[row] = new
        if new.name != old.name:
            for slot in self.spec.indicators:
                for key, value in list(slot.params.items()):
                    if isinstance(value, str) and value == f"${old.name}":
                        slot.params[key] = f"${new.name}"
            for key, _title in _RULE_SLOTS:
                condition = getattr(self.spec, key, None)
                if condition is not None:
                    _rename_param_in_condition(condition, old.name, new.name)
            self._reload_tree()
        self._say("", PALETTE.text)
        self._rebuild_slot_editor()

    def _add_param(self) -> None:
        name = ask_text(self, "New Parameter", "Parameter name (no spaces):",
                        f"param{len(self.spec.params) + 1}")
        if not name:
            return
        clean = name.strip().replace(" ", "_")
        if any(p.name == clean for p in self.spec.params):
            self._say(f"There is already a parameter called '{clean}'.",
                      PALETTE.danger)
            return
        self.spec.params.append(
            ParamSpec(clean, clean.replace("_", " ").title(), "int", 14, 1, 500, 1))
        self._reload_params()
        self._rebuild_slot_editor()

    def _remove_param(self) -> None:
        row = self.param_table.currentRow()
        if not (0 <= row < len(self.spec.params)):
            return
        param = self.spec.params[row]
        del self.spec.params[row]
        # Any indicator still pointing at it would fail validation; fall back to
        # the literal default so the strategy stays runnable.
        for slot in self.spec.indicators:
            for key, value in list(slot.params.items()):
                if isinstance(value, str) and value == f"${param.name}":
                    slot.params[key] = param.default
        self._reload_params()
        self._rebuild_slot_editor()


# --------------------------------------------------------------------------
# Common rules
# --------------------------------------------------------------------------

class _Preset:
    """One ready-made rule: some indicator slots and the condition over them.

    Every preset builds the *same objects* the tree builds by hand -- an
    ``IndicatorSlot``, a ``ParamSpec``, a ``Compare`` or a ``Cross``.  There is
    no second rule format and nothing here the editor cannot then take apart,
    which is the only reason a preset is safe: it is a shortcut through the
    clicks, not a shortcut around the model.
    """

    def __init__(self, name: str, blurb: str, fields: tuple, build) -> None:
        self.name = name
        self.blurb = blurb
        #: ``(key, label, default, minimum, maximum)`` per number to ask for.
        self.fields = fields
        self._build = build

    def build(self, spec: StrategySpec, values: dict) -> Any:
        return self._build(_PresetContext(spec), values)


class _PresetContext:
    """Adds slots and parameters to a spec without ever colliding with one.

    A strategy that already has ``ema`` must still be able to take "price
    above an EMA" twice.  Every name goes through :meth:`unique`, and an
    identical slot -- same indicator, same parameters, same source -- is
    reused rather than added again, so applying the same preset twice does not
    compute the same average twice.
    """

    def __init__(self, spec: StrategySpec) -> None:
        self.spec = spec

    def unique(self, stem: str) -> str:
        taken = {s.ref for s in self.spec.indicators}
        if stem not in taken:
            return stem
        n = 2
        while f"{stem}{n}" in taken:
            n += 1
        return f"{stem}{n}"

    def unique_param(self, stem: str) -> str:
        taken = {p.name for p in self.spec.params}
        if stem not in taken:
            return stem
        n = 2
        while f"{stem}_{n}" in taken:
            n += 1
        return f"{stem}_{n}"

    def slot(self, key: str, params: dict, source: str = "close",
             stem: str = "") -> str:
        for existing in self.spec.indicators:
            if (existing.indicator == key and existing.params == params
                    and existing.source == source):
                return existing.ref
        ref = self.unique(stem or key.lower())
        self.spec.indicators.append(
            IndicatorSlot(ref=ref, indicator=key, params=dict(params),
                          source=source))
        return ref

    def number(self, stem: str, label: str, value: float, low: float,
               high: float, kind: str = "float") -> str:
        """A strategy parameter, so the threshold can be optimised later.

        The bounds are passed explicitly and are not optional: ``ParamSpec``
        defaults to a minimum of 1, which quietly rejects any threshold below
        it -- a 0.5% volatility level, an RSI level of 0 -- at compile time
        rather than here.  They also give the optimiser the range to sweep.
        """
        name = self.unique_param(stem)
        self.spec.params.append(
            ParamSpec(name=name, label=label, kind=kind, default=value,
                      minimum=low, maximum=high,
                      step=1 if kind == "int" else 0.1))
        return name


def _p_price_vs_ma(context, values):
    period = int(values["period"])
    ref = context.slot(values["kind"], {"period": period}, stem="trend")
    op = ">" if values["above"] else "<"
    return Compare(PriceOperand(field="close"), op, IndicatorOperand(ref=ref))


def _p_ma_cross(context, values):
    fast = context.slot(values["kind"], {"period": int(values["fast"])},
                        stem="fast")
    slow = context.slot(values["kind"], {"period": int(values["slow"])},
                        stem="slow")
    return Cross(IndicatorOperand(ref=fast),
                 "above" if values["above"] else "below",
                 IndicatorOperand(ref=slow))


def _p_rsi_level(context, values):
    ref = context.slot("RSI", {"period": int(values["period"])}, stem="rsi")
    name = context.number("rsi_level", "RSI level", float(values["level"]),
                          0.0, 100.0)
    return Cross(IndicatorOperand(ref=ref),
                 "above" if values["above"] else "below",
                 ParamOperand(name=name))


def _p_channel_break(context, values):
    ref = context.slot("DONCHIAN", {"period": int(values["period"])},
                       stem="chan")
    edge = "upper" if values["above"] else "lower"
    return Cross(PriceOperand(field="close"),
                 "above" if values["above"] else "below",
                 IndicatorOperand(ref=ref, output=edge, offset=1))


def _p_band_break(context, values):
    ref = context.slot("BBANDS", {"period": int(values["period"]),
                                  "deviation": float(values["deviation"])},
                       stem="bb")
    return Cross(PriceOperand(field="close"),
                 "above" if values["above"] else "below",
                 IndicatorOperand(ref=ref,
                                  output="upper" if values["above"] else "lower"))


def _p_macd_cross(context, values):
    ref = context.slot("MACD", {"fast": int(values["fast"]),
                                "slow": int(values["slow"]),
                                "signal": int(values["signal"])}, stem="macd")
    return Cross(IndicatorOperand(ref=ref, output="macd"),
                 "above" if values["above"] else "below",
                 IndicatorOperand(ref=ref, output="signal"))


def _p_volatility_level(context, values):
    """Normalised ATR against a threshold.

    NATR rather than ATR because the comparison has to be scale free: an ATR
    of 40 means something different on an index at 18,000 than on one at 400,
    and a rule with a raw-points threshold in it stops meaning anything the
    moment the instrument changes.  The obvious alternative -- ATR against a
    moving average of ATR -- cannot be expressed here at all: an indicator
    slot reads a price series, never another indicator's output.
    """
    ref = context.slot("NATR", {"period": int(values["period"])}, stem="natr")
    name = context.number("volatility_level", "Volatility level (%)",
                          float(values["level"]), 0.0, 50.0)
    return Compare(IndicatorOperand(ref=ref),
                   ">" if values["above"] else "<", ParamOperand(name=name))


def _p_time_window(context, values):
    return SessionWindow(start=str(values["start"]), end=str(values["end"]),
                         timezone="America/New_York")


def _p_adx_trending(context, values):
    ref = context.slot("ADX", {"period": int(values["period"])}, stem="adx")
    name = context.number("adx_level", "ADX level", float(values["level"]),
                          0.0, 100.0)
    return Compare(IndicatorOperand(ref=ref, output="adx"), ">",
                   ParamOperand(name=name))


#: Shown in the order a beginner would want them, not alphabetically.
_PRESETS: tuple[_Preset, ...] = (
    _Preset("Price is above a moving average",
            "A trend filter. Adds one moving average and compares the close "
            "to it.",
            (("kind", "Average", "EMA", ("EMA", "SMA", "WMA", "HMA"), None),
             ("period", "Period", 200, 2, 1000),
             ("above", "Direction", True, None, None)),
            _p_price_vs_ma),
    _Preset("A moving average crosses another",
            "The classic entry. Adds a fast and a slow average of the same "
            "kind and fires on the crossing, not on every bar after it.",
            (("kind", "Average", "EMA", ("EMA", "SMA", "WMA", "HMA"), None),
             ("fast", "Fast period", 20, 2, 1000),
             ("slow", "Slow period", 50, 2, 1000),
             ("above", "Direction", True, None, None)),
            _p_ma_cross),
    _Preset("RSI crosses a level",
            "Adds an RSI and a strategy parameter for the level, so the "
            "threshold can be swept by the optimiser instead of edited.",
            (("period", "RSI period", 14, 2, 500),
             ("level", "Level", 30.0, 0.0, 100.0),
             ("above", "Direction", True, None, None)),
            _p_rsi_level),
    _Preset("Price breaks a Donchian channel",
            "A breakout. Compares against the PREVIOUS bar's channel edge, "
            "because this bar's high is part of today's channel.",
            (("period", "Channel period", 20, 2, 1000),
             ("above", "Direction", True, None, None)),
            _p_channel_break),
    _Preset("Price breaks a Bollinger band",
            "Adds Bollinger bands and fires when the close crosses the outer "
            "band.",
            (("period", "Period", 20, 2, 1000),
             ("deviation", "Deviations", 2.0, 0.1, 10.0),
             ("above", "Direction", True, None, None)),
            _p_band_break),
    _Preset("MACD crosses its signal line",
            "Adds one MACD and crosses its two outputs.",
            (("fast", "Fast", 12, 2, 500), ("slow", "Slow", 26, 2, 500),
             ("signal", "Signal", 9, 2, 500),
             ("above", "Direction", True, None, None)),
            _p_macd_cross),
    _Preset("ADX says the market is trending",
            "A regime filter rather than an entry. Adds an ADX and a "
            "parameter for the level.",
            (("period", "ADX period", 14, 2, 500),
             ("level", "Level", 25.0, 0.0, 100.0)),
            _p_adx_trending),
    _Preset("Volatility is above a level",
            "A regime filter. Adds a normalised ATR -- true range as a "
            "percentage of price, so the threshold means the same thing on "
            "any instrument -- and a parameter for the level.",
            (("period", "ATR period", 14, 2, 500),
             ("level", "Level (%)", 0.5, 0.0, 50.0),
             ("above", "Direction", True, None, None)),
            _p_volatility_level),
    _Preset("Only inside a time window",
            "A session filter in New York time. Add it to an AND group "
            "alongside your entry.",
            (("start", "From", "09:30", None, None),
             ("end", "To", "11:00", None, None)),
            _p_time_window),
)


class _PresetPicker(QDialog):
    """Choose a common rule and fill in its numbers."""

    def __init__(self, editor: StrategyEditor) -> None:
        super().__init__(editor)
        self.setWindowTitle("Add a common rule")
        self.resize(620, 560)
        self.preset: _Preset | None = None
        self.values: dict[str, Any] = {}
        self._widgets: dict[str, Any] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(9)

        note = QLabel(
            "Each of these adds the indicators it needs and the condition "
            "over them, in one step. Everything it adds is an ordinary "
            "indicator and an ordinary condition, so you can take it apart "
            "afterwards.")
        note.setWordWrap(True)
        note.setObjectName("Hint")
        lay.addWidget(note)

        self.list = QListWidget()
        for preset in _PRESETS:
            self.list.addItem(QListWidgetItem(preset.name))
        self.list.currentRowChanged.connect(self._on_preset_changed)
        lay.addWidget(self.list, 1)

        self.blurb = QLabel("")
        self.blurb.setWordWrap(True)
        self.blurb.setObjectName("Hint")
        lay.addWidget(self.blurb)

        self.form_host = QWidget()
        self.form = QFormLayout(self.form_host)
        self.form.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.form_host)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        self.ok = QPushButton("Add")
        self.ok.setObjectName("Primary")
        self.ok.setDefault(True)
        self.ok.clicked.connect(self._accept)
        row.addWidget(self.ok)
        lay.addLayout(row)

        self.list.setCurrentRow(0)

    def _on_preset_changed(self, row: int) -> None:
        while self.form.rowCount():
            self.form.removeRow(0)
        self._widgets.clear()
        if not 0 <= row < len(_PRESETS):
            return
        preset = _PRESETS[row]
        self.blurb.setText(preset.blurb)
        for key, label, default, low, high in preset.fields:
            widget = self._field(key, default, low, high)
            self._widgets[key] = widget
            self.form.addRow(label, widget)

    def _field(self, key: str, default: Any, low: Any, high: Any):
        if key == "above":
            box = QComboBox()
            box.addItem("Long / above", True)
            box.addItem("Short / below", False)
            return box
        if isinstance(default, str) and isinstance(low, tuple):
            box = QComboBox()
            for choice in low:
                box.addItem(choice, choice)
            box.setCurrentIndex(max(0, list(low).index(default)))
            return box
        if isinstance(default, str):
            from PySide6.QtWidgets import QLineEdit

            edit = QLineEdit(default)
            return edit
        if isinstance(default, bool):           # pragma: no cover - none today
            box = QComboBox()
            box.addItem("Yes", True)
            box.addItem("No", False)
            return box
        if isinstance(default, int):
            spin = QSpinBox()
            spin.setRange(int(low), int(high))
            spin.setValue(int(default))
            return spin
        spin = QDoubleSpinBox()
        spin.setDecimals(2)
        spin.setRange(float(low), float(high))
        spin.setValue(float(default))
        return spin

    def _read(self, widget) -> Any:
        if isinstance(widget, QComboBox):
            return widget.currentData()
        if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            return widget.value()
        return widget.text()

    def _accept(self) -> None:
        row = self.list.currentRow()
        if not 0 <= row < len(_PRESETS):
            return
        self.preset = _PRESETS[row]
        self.values = {key: self._read(widget)
                       for key, widget in self._widgets.items()}
        # A cross of an average with itself is not a rule; catch it here
        # rather than let it into the tree as a condition that never fires.
        if "fast" in self.values and "slow" in self.values:
            if int(self.values["fast"]) >= int(self.values["slow"]):
                show_warning(self, "Those periods cross the wrong way",
                             "The fast average has to be shorter than the "
                             "slow one, or the crossing this builds is not "
                             "the one you mean.")
                self.preset = None
                return
        self.accept()


# --------------------------------------------------------------------------
# Small helpers on the condition tree
# --------------------------------------------------------------------------

def _node_title(node: Any) -> str:
    if isinstance(node, ConditionGroup):
        label = f"{'NOT ' if node.negate else ''}{node.op}"
        return f"{label}  ({len(node.children)} condition"\
               f"{'s' if len(node.children) != 1 else ''})"
    if isinstance(node, Vote):
        label = "NOT " if node.negate else ""
        return (f"{label}VOTE  (at least {int(node.threshold)} of "
                f"{len(node.children)})")
    try:
        return node.describe()
    except Exception:                       # pragma: no cover - defensive
        return type(node).__name__


def _walk_operands(condition: Any):
    for attribute in ("left", "right"):
        operand = getattr(condition, attribute, None)
        if operand is not None:
            yield operand
            if isinstance(operand, ExprOperand):
                yield from (operand.left, operand.right)


def _rename_in_condition(condition: Any, old: str, new: str) -> None:
    if isinstance(condition, (ConditionGroup, Vote)):
        for child in condition.children:
            _rename_in_condition(child, old, new)
        return
    for operand in _walk_operands(condition):
        if isinstance(operand, IndicatorOperand) and operand.ref == old:
            operand.ref = new


def _rename_param_in_condition(condition: Any, old: str, new: str) -> None:
    if isinstance(condition, (ConditionGroup, Vote)):
        for child in condition.children:
            _rename_param_in_condition(child, old, new)
        return
    for operand in _walk_operands(condition):
        if isinstance(operand, ParamOperand) and operand.name == old:
            operand.name = new


# --------------------------------------------------------------------------
# Pickers
# --------------------------------------------------------------------------

class _IndicatorPicker(QDialog):
    """Browse the registry by category."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Indicator")
        self.resize(680, 520)
        self.key = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search indicators…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Indicator", "Description"])
        self.tree.setColumnWidth(0, 230)
        self.tree.itemDoubleClicked.connect(lambda *_: self._accept())
        self.tree.currentItemChanged.connect(self._on_selected)
        lay.addWidget(self.tree, 1)
        self._populate()

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        self.ok = QPushButton("Add")
        self.ok.setObjectName("Primary")
        self.ok.setDefault(True)
        self.ok.setEnabled(False)
        self.ok.clicked.connect(self._accept)
        row.addWidget(self.ok)
        lay.addLayout(row)

    def _populate(self) -> None:
        self.tree.clear()
        for category, definitions in REGISTRY.by_category().items():
            head = QTreeWidgetItem([category, ""])
            head.setFlags(Qt.ItemFlag.ItemIsEnabled)
            for definition in definitions:
                child = QTreeWidgetItem([definition.name, definition.description])
                child.setData(0, Qt.ItemDataRole.UserRole, definition.key)
                child.setToolTip(1, definition.description)
                head.addChild(child)
            self.tree.addTopLevelItem(head)
        self.tree.expandAll()

    def _filter(self, text: str) -> None:
        needle = text.strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            head = self.tree.topLevelItem(i)
            shown = 0
            for j in range(head.childCount()):
                child = head.child(j)
                match = (not needle
                         or needle in child.text(0).lower()
                         or needle in child.text(1).lower()
                         or needle in str(child.data(0, Qt.ItemDataRole.UserRole)).lower())
                child.setHidden(not match)
                shown += int(match)
            head.setHidden(shown == 0)

    def _on_selected(self, *_args) -> None:
        item = self.tree.currentItem()
        key = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        self.key = key or ""
        self.ok.setEnabled(bool(self.key))

    def _accept(self) -> None:
        if self.key:
            self.accept()


class _ConditionPicker(QDialog):
    """Choose the kind of condition to add."""

    def __init__(self, editor: StrategyEditor) -> None:
        super().__init__(editor)
        self.setWindowTitle("Add Condition")
        self.setMinimumWidth(420)
        self._editor = editor
        self.condition: Any = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(9)
        lay.addWidget(QLabel("What kind of condition?"))

        self.kind_box = QComboBox()
        for label, key in (("Compare two things", "compare"),
                           ("One crosses another", "cross"),
                           ("A series is rising or falling", "state"),
                           ("Inside a session window", "session"),
                           ("Always true", "always")):
            self.kind_box.addItem(label, key)
        lay.addWidget(self.kind_box)

        hint = QLabel(
            "A comparison holds on every bar where it is true. A cross fires "
            "only on the bar where the relationship changes, which is usually "
            "what an entry rule wants.")
        hint.setWordWrap(True)
        hint.setObjectName("Hint")
        hint.setFont(Fonts.body(8))
        lay.addWidget(hint)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        ok = QPushButton("Add")
        ok.setObjectName("Primary")
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        row.addWidget(ok)
        lay.addLayout(row)

    def _accept(self) -> None:
        kind = self.kind_box.currentData()
        refs = self._editor.indicator_refs()
        left: Any = (IndicatorOperand(refs[0], self._editor.indicator_outputs(refs[0])[0])
                     if refs else PriceOperand("close"))
        if kind == "compare":
            self.condition = Compare(left, ">", ConstOperand(0.0))
        elif kind == "cross":
            right = (IndicatorOperand(refs[1], self._editor.indicator_outputs(refs[1])[0])
                     if len(refs) > 1 else PriceOperand("close"))
            self.condition = Cross(left, "above", right)
        elif kind == "state":
            self.condition = State(left, "rising", 1)
        elif kind == "session":
            self.condition = SessionWindow("09:30", "16:00", "America/New_York",
                                           (0, 1, 2, 3, 4))
        else:
            self.condition = Always(True)
        self.accept()


# --------------------------------------------------------------------------
# Node editors
# --------------------------------------------------------------------------

def _node_editor(editor: StrategyEditor, node: Any) -> QWidget | None:
    if isinstance(node, ConditionGroup):
        return _GroupEditor(editor, node)
    if isinstance(node, Vote):
        return _VoteEditor(editor, node)
    if isinstance(node, Compare):
        return _CompareEditor(editor, node)
    if isinstance(node, Cross):
        return _CrossEditor(editor, node)
    if isinstance(node, State):
        return _StateEditor(editor, node)
    if isinstance(node, SessionWindow):
        return _SessionEditor(editor, node)
    if isinstance(node, Always):
        return _AlwaysEditor(editor, node)
    return None


class _GroupEditor(QWidget):
    def __init__(self, editor: StrategyEditor, node: ConditionGroup) -> None:
        super().__init__()
        self._editor, self._node = editor, node
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        form = QFormLayout()
        box = QComboBox()
        box.addItem("AND — every condition must hold", "AND")
        box.addItem("OR — any condition may hold", "OR")
        box.setCurrentIndex(0 if node.op == "AND" else 1)
        box.currentIndexChanged.connect(
            lambda _i: (setattr(node, "op", box.currentData()), editor.node_changed()))
        form.addRow("Combine with", box)

        from PySide6.QtWidgets import QCheckBox

        negate = QCheckBox("Invert this group (NOT)")
        negate.setChecked(node.negate)
        negate.toggled.connect(
            lambda on: (setattr(node, "negate", on), editor.node_changed()))
        form.addRow("", negate)
        lay.addLayout(form)
        note = QLabel("Add conditions to this group with the buttons above the tree.")
        note.setWordWrap(True)
        note.setObjectName("Hint")
        lay.addWidget(note)


class _VoteEditor(QWidget):
    """The threshold on a vote, and a warning when it cannot be met.

    Votes are not built by hand here -- `combine_strategies` makes them -- but
    a combined strategy has to be as editable as any other once it is open, or
    combining is a one-way door.
    """

    def __init__(self, editor: StrategyEditor, node: Vote) -> None:
        super().__init__()
        self._editor, self._node = editor, node
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        form = QFormLayout()

        spin = QSpinBox()
        spin.setRange(1, max(1, len(node.children)))
        spin.setValue(max(1, min(int(node.threshold), len(node.children) or 1)))
        spin.setSuffix(f" of {len(node.children)}")
        spin.valueChanged.connect(
            lambda v: (setattr(node, "threshold", int(v)), editor.node_changed()))
        form.addRow("Conditions needed", spin)

        from PySide6.QtWidgets import QCheckBox

        negate = QCheckBox("Invert this vote (NOT)")
        negate.setChecked(node.negate)
        negate.toggled.connect(
            lambda on: (setattr(node, "negate", on), editor.node_changed()))
        form.addRow("", negate)
        lay.addLayout(form)

        note = QLabel(
            "True on a bar where at least this many of the conditions below "
            "hold. A condition whose indicators are still warming up does not "
            "count towards the total, and does not count against it either.")
        note.setWordWrap(True)
        note.setObjectName("Hint")
        lay.addWidget(note)
        if int(node.threshold) > len(node.children):
            bad = QLabel(
                f"This asks for {int(node.threshold)} of "
                f"{len(node.children)}, which can never happen, so the "
                f"strategy will not save until it is corrected.")
            bad.setWordWrap(True)
            bad.setStyleSheet(f"color:{PALETTE.short};")
            lay.addWidget(bad)


class _OperandEditor(QWidget):
    """A compact editor for one operand: kind, value and bar offset."""

    def __init__(self, editor: StrategyEditor, owner: Any, attribute: str) -> None:
        super().__init__()
        self._editor, self._owner, self._attribute = editor, owner, attribute
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)

        self.kind = QComboBox()
        for label, key in (("Price", "price"), ("Indicator", "indicator"),
                           ("Number", "const"), ("Parameter", "param"),
                           ("Arithmetic", "expr")):
            self.kind.addItem(label, key)
        self.kind.setFixedWidth(104)
        lay.addWidget(self.kind)

        self.value = QComboBox()
        lay.addWidget(self.value, 1)
        self.output = QComboBox()
        self.output.setFixedWidth(92)
        lay.addWidget(self.output)
        self.number = QDoubleSpinBox()
        self.number.setDecimals(4)
        self.number.setRange(-1e9, 1e9)
        self.number.setFixedWidth(104)
        lay.addWidget(self.number)
        self.offset = QSpinBox()
        self.offset.setRange(0, 500)
        self.offset.setPrefix("[")
        self.offset.setSuffix("]")
        self.offset.setFixedWidth(58)
        self.offset.setToolTip("Bars back. 1 is the previous bar.")
        lay.addWidget(self.offset)

        self._load()
        self.kind.currentIndexChanged.connect(self._on_kind)
        self.value.currentIndexChanged.connect(self._apply)
        self.output.currentIndexChanged.connect(self._apply)
        self.number.valueChanged.connect(self._apply)
        self.offset.valueChanged.connect(self._apply)

    # -- state ------------------------------------------------------------

    def _operand(self) -> Any:
        return getattr(self._owner, self._attribute)

    def _load(self) -> None:
        operand = self._operand()
        kind = ("price" if isinstance(operand, PriceOperand) else
                "indicator" if isinstance(operand, IndicatorOperand) else
                "param" if isinstance(operand, ParamOperand) else
                "expr" if isinstance(operand, ExprOperand) else "const")
        self.kind.blockSignals(True)
        self.kind.setCurrentIndex(max(0, self.kind.findData(kind)))
        self.kind.blockSignals(False)
        self._fill_value(kind, operand)
        self._show_for(kind)

    def _fill_value(self, kind: str, operand: Any) -> None:
        for widget in (self.value, self.output):
            widget.blockSignals(True)
            widget.clear()
        if kind == "price":
            for field in _PRICE_FIELDS:
                self.value.addItem(field, field)
            self.value.setCurrentIndex(max(0, self.value.findData(
                getattr(operand, "field", "close"))))
            self.offset.setValue(int(getattr(operand, "offset", 0)))
        elif kind == "indicator":
            for ref in self._editor.indicator_refs():
                self.value.addItem(ref, ref)
            ref = getattr(operand, "ref", "")
            self.value.setCurrentIndex(max(0, self.value.findData(ref)))
            chosen = self.value.currentData() or ref
            for name in self._editor.indicator_outputs(chosen):
                self.output.addItem(name, name)
            self.output.setCurrentIndex(max(0, self.output.findData(
                getattr(operand, "output", "value"))))
            self.offset.setValue(int(getattr(operand, "offset", 0)))
        elif kind == "param":
            for name in self._editor.parameter_names():
                self.value.addItem(f"${name}", name)
            self.value.setCurrentIndex(max(0, self.value.findData(
                getattr(operand, "name", ""))))
        elif kind == "const":
            self.number.blockSignals(True)
            self.number.setValue(float(getattr(operand, "value", 0.0)))
            self.number.blockSignals(False)
        for widget in (self.value, self.output):
            widget.blockSignals(False)

    def _show_for(self, kind: str) -> None:
        self.value.setVisible(kind in ("price", "indicator", "param", "expr"))
        self.output.setVisible(kind == "indicator")
        self.number.setVisible(kind == "const")
        self.offset.setVisible(kind in ("price", "indicator"))
        if kind == "expr":
            self.value.blockSignals(True)
            self.value.clear()
            self.value.addItem("edit the two sides below", "expr")
            self.value.blockSignals(False)

    # -- editing ----------------------------------------------------------

    def _on_kind(self) -> None:
        kind = self.kind.currentData()
        refs = self._editor.indicator_refs()
        params = self._editor.parameter_names()
        if kind == "price":
            operand: Any = PriceOperand("close")
        elif kind == "indicator":
            if not refs:
                show_info(self, "No Indicators",
                          "Add an indicator on the Indicators tab first.")
                self._load()
                return
            operand = IndicatorOperand(refs[0],
                                       self._editor.indicator_outputs(refs[0])[0])
        elif kind == "param":
            if not params:
                show_info(self, "No Parameters",
                          "Add a parameter on the Parameters tab first.")
                self._load()
                return
            operand = ParamOperand(params[0])
        elif kind == "expr":
            operand = ExprOperand("*", PriceOperand("close"), ConstOperand(1.0))
        else:
            operand = ConstOperand(0.0)
        setattr(self._owner, self._attribute, operand)
        self._load()
        self._editor.node_changed()
        self._rebuild_parent()

    def _apply(self) -> None:
        kind = self.kind.currentData()
        operand = self._operand()
        if kind == "price" and isinstance(operand, PriceOperand):
            operand.field = self.value.currentData() or "close"
            operand.offset = self.offset.value()
        elif kind == "indicator" and isinstance(operand, IndicatorOperand):
            new_ref = self.value.currentData() or operand.ref
            if new_ref != operand.ref:
                operand.ref = new_ref
                self._fill_value("indicator", operand)
            operand.output = self.output.currentData() or "value"
            operand.offset = self.offset.value()
        elif kind == "param" and isinstance(operand, ParamOperand):
            operand.name = self.value.currentData() or operand.name
        elif kind == "const" and isinstance(operand, ConstOperand):
            operand.value = float(self.number.value())
        self._editor.node_changed()

    def _rebuild_parent(self) -> None:
        """An Arithmetic operand needs its own two sub-editors drawn."""
        parent = self.parentWidget()
        while parent is not None and not isinstance(parent, _ConditionEditorBase):
            parent = parent.parentWidget()
        if parent is not None:
            parent.rebuild()


class _ConditionEditorBase(QWidget):
    """Shared scaffolding for the per-condition editors."""

    def __init__(self, editor: StrategyEditor, node: Any) -> None:
        super().__init__()
        self._editor, self._node = editor, node
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self.rebuild()

    def rebuild(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                _clear_layout(item.layout())
        self.build()
        self._layout.addStretch(1)

    def build(self) -> None:                # pragma: no cover - overridden
        raise NotImplementedError

    def _operand_row(self, title: str, owner: Any, attribute: str) -> None:
        label = QLabel(title)
        label.setFont(Fonts.body(9))
        label.setStyleSheet(f"color:{PALETTE.text_dim};")
        self._layout.addWidget(label)
        self._layout.addWidget(_OperandEditor(self._editor, owner, attribute))
        operand = getattr(owner, attribute)
        if isinstance(operand, ExprOperand):
            box = QComboBox()
            for symbol in ExprOperand.OPS:
                box.addItem(symbol, symbol)
            box.setCurrentIndex(max(0, box.findData(operand.op)))
            box.currentIndexChanged.connect(
                lambda _i, o=operand, b=box: (setattr(o, "op", b.currentData()),
                                              self._editor.node_changed()))
            row = QHBoxLayout()
            row.addWidget(QLabel("      operation"))
            row.addWidget(box, 1)
            self._layout.addLayout(row)
            self._layout.addWidget(_OperandEditor(self._editor, operand, "left"))
            self._layout.addWidget(_OperandEditor(self._editor, operand, "right"))


class _CompareEditor(_ConditionEditorBase):
    def build(self) -> None:
        self._operand_row("Left side", self._node, "left")
        box = QComboBox()
        for symbol, words in _COMPARE_OPS:
            box.addItem(f"{symbol}   {words}", symbol)
        box.setCurrentIndex(max(0, box.findData(self._node.op)))
        box.currentIndexChanged.connect(
            lambda _i: (setattr(self._node, "op", box.currentData()),
                        self._editor.node_changed()))
        self._layout.addWidget(box)
        self._operand_row("Right side", self._node, "right")


class _CrossEditor(_ConditionEditorBase):
    def build(self) -> None:
        self._operand_row("Left side", self._node, "left")
        box = QComboBox()
        for key, words in _CROSS_DIRECTIONS:
            box.addItem(words, key)
        box.setCurrentIndex(max(0, box.findData(self._node.direction)))
        box.currentIndexChanged.connect(
            lambda _i: (setattr(self._node, "direction", box.currentData()),
                        self._editor.node_changed()))
        self._layout.addWidget(box)
        self._operand_row("Right side", self._node, "right")
        hint = QLabel("A cross fires only on the bar where the relationship "
                      "changes, not on every bar it holds.")
        hint.setWordWrap(True)
        hint.setObjectName("Hint")
        self._layout.addWidget(hint)


class _StateEditor(_ConditionEditorBase):
    def build(self) -> None:
        self._operand_row("Series", self._node, "left")
        box = QComboBox()
        for key, words in _STATE_OPS:
            box.addItem(words, key)
        box.setCurrentIndex(max(0, box.findData(self._node.op)))
        bars = QSpinBox()
        bars.setRange(1, 500)
        bars.setValue(int(self._node.bars))
        bars.setPrefix("for ")
        bars.setSuffix(" bars")

        def apply() -> None:
            self._node.op = box.currentData()
            self._node.bars = bars.value()
            bars.setVisible(self._node.op in ("increasing_for", "decreasing_for"))
            self._editor.node_changed()

        box.currentIndexChanged.connect(lambda _i: apply())
        bars.valueChanged.connect(lambda _v: apply())
        self._layout.addWidget(box)
        self._layout.addWidget(bars)
        bars.setVisible(self._node.op in ("increasing_for", "decreasing_for"))


class _SessionEditor(_ConditionEditorBase):
    def build(self) -> None:
        from PySide6.QtWidgets import QCheckBox

        form = QFormLayout()
        start = QLineEdit(self._node.start)
        start.setInputMask("99:99")
        end = QLineEdit(self._node.end)
        end.setInputMask("99:99")
        zone = QComboBox()
        for name in _TIMEZONES:
            zone.addItem(name, name)
        zone.setCurrentIndex(max(0, zone.findData(self._node.timezone)))
        form.addRow("From", start)
        form.addRow("To", end)
        form.addRow("Timezone", zone)
        self._layout.addLayout(form)

        days_row = QHBoxLayout()
        boxes: list[Any] = []
        for index, name in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
            box = QCheckBox(name)
            box.setChecked(index in self._node.weekdays)
            days_row.addWidget(box)
            boxes.append(box)
        self._layout.addLayout(days_row)

        def apply() -> None:
            self._node.start = start.text()
            self._node.end = end.text()
            self._node.timezone = zone.currentData()
            self._node.weekdays = tuple(i for i, b in enumerate(boxes) if b.isChecked())
            self._editor.node_changed()

        for widget in (start, end):
            widget.editingFinished.connect(apply)
        zone.currentIndexChanged.connect(lambda _i: apply())
        for box in boxes:
            box.toggled.connect(lambda _on: apply())

        hint = QLabel("A window whose end is before its start wraps over midnight.")
        hint.setWordWrap(True)
        hint.setObjectName("Hint")
        self._layout.addWidget(hint)


class _AlwaysEditor(_ConditionEditorBase):
    def build(self) -> None:
        box = QComboBox()
        box.addItem("Always true", True)
        box.addItem("Never true", False)
        box.setCurrentIndex(0 if self._node.value else 1)
        box.currentIndexChanged.connect(
            lambda _i: (setattr(self._node, "value", bool(box.currentData())),
                        self._editor.node_changed()))
        self._layout.addWidget(box)


class _SlotParamRow(QWidget):
    """One indicator parameter, editable as a literal or as ``$parameter``."""

    def __init__(self, editor: StrategyEditor, index: int, slot: IndicatorSlot,
                 param: ParamSpec) -> None:
        super().__init__()
        self._editor, self._index, self._slot, self._param = editor, index, slot, param
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        label = QLabel(param.label or param.name)
        label.setFixedWidth(130)
        label.setFont(Fonts.body(9))
        label.setStyleSheet(f"color:{PALETTE.text_dim};")
        label.setToolTip(param.help or "")
        lay.addWidget(label)

        current = slot.params.get(param.name, param.default)
        linked = isinstance(current, str) and current.startswith("$")

        self.literal: Any
        if param.kind == "int":
            self.literal = QSpinBox()
            self.literal.setRange(int(param.minimum or 1), int(param.maximum or 10 ** 6))
            self.literal.setValue(int(current) if not linked else int(param.default))
        elif param.kind == "float":
            self.literal = QDoubleSpinBox()
            self.literal.setDecimals(4)
            self.literal.setRange(float(param.minimum if param.minimum is not None
                                        else -1e9),
                                  float(param.maximum if param.maximum is not None
                                        else 1e9))
            self.literal.setValue(float(current) if not linked
                                  else float(param.default))
        elif param.kind == "choice":
            self.literal = QComboBox()
            for choice in param.choices:
                self.literal.addItem(str(choice), choice)
            self.literal.setCurrentIndex(
                max(0, self.literal.findData(current if not linked else param.default)))
        else:
            self.literal = QLineEdit(str(current if not linked else param.default))
        lay.addWidget(self.literal, 1)

        self.param_box = QComboBox()
        for name in editor.parameter_names():
            self.param_box.addItem(f"${name}", name)
        lay.addWidget(self.param_box, 1)

        self.link = QToolButton()
        self.link.setCheckable(True)
        self.link.setText("$")
        self.link.setFixedSize(26, 24)
        self.link.setToolTip(
            "Drive this from a named strategy parameter so the optimiser can "
            "sweep it.")
        self.link.setChecked(linked)
        lay.addWidget(self.link)

        if linked:
            position = self.param_box.findData(str(current)[1:])
            self.param_box.setCurrentIndex(max(0, position))
        self._sync()

        self.link.toggled.connect(self._on_link)
        self.param_box.currentIndexChanged.connect(self._apply)
        for signal in ("valueChanged", "currentIndexChanged", "textChanged"):
            if hasattr(self.literal, signal):
                getattr(self.literal, signal).connect(self._apply)

    def _sync(self) -> None:
        linked = self.link.isChecked()
        self.literal.setVisible(not linked)
        self.param_box.setVisible(linked)
        self.link.setEnabled(bool(self._editor.parameter_names()) or linked)

    def _on_link(self, on: bool) -> None:
        if on and not self._editor.parameter_names():
            self.link.setChecked(False)
            show_info(self, "No Parameters",
                      "Add a parameter on the Parameters tab first, then it can "
                      "drive this value.")
            return
        self._sync()
        self._apply()

    def _apply(self, *_args) -> None:
        if self.link.isChecked():
            name = self.param_box.currentData()
            if name:
                self._editor.set_slot_param(self._index, self._param.name, f"${name}")
            return
        widget = self.literal
        if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            value: Any = widget.value()
        elif isinstance(widget, QComboBox):
            value = widget.currentData()
        else:
            value = widget.text()
        self._editor.set_slot_param(self._index, self._param.name, value)


def _clear_layout(layout: Any) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
        elif item.layout() is not None:
            _clear_layout(item.layout())
