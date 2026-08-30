"""Reusable UI building blocks: form fields, sections and the error dialog.

The form fields exist so that panels do not each re-implement "a labelled spin
box that validates and reports its value".  A panel declares a list of
:class:`FieldSpec` and gets back a widget plus a ``values()`` dictionary, which
is what makes the strategy parameter editor work for parameters it has never
seen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

from PySide6.QtCore import QEvent, QObject, QSize, Qt, Signal
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (QAbstractScrollArea, QAbstractSpinBox,
                               QApplication, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton,
                               QSizePolicy, QSlider, QSpinBox, QToolButton,
                               QVBoxLayout, QWidget)

from ...core.errors import BacktesterError
from ..theme import PALETTE, Fonts


# --------------------------------------------------------------------------
# Layout helpers
# --------------------------------------------------------------------------

class _WheelGuard(QObject):
    """Stops a scroll gesture from rewriting the value it passes over.

    Qt sends a wheel event to whatever is under the pointer, so dragging the
    sidebar's scrollbar past a combo box or a spin box changes it.  Measured
    before this existed: one three-notch scroll down the left panel switched
    the selected strategy from one to another, moved starting capital from
    100,000 to 97,000, and took units per trade from 1.0 to 0.0001 -- silently,
    with the only symptom being that the chart no longer matched what the user
    thought was selected.

    The rule is that a wheel over an *unfocused* value widget belongs to the
    thing that scrolls, not to the value.  Clicking into a box first and then
    scrolling it still works, because that is unambiguous.

    The event is forwarded to the scrolling ancestor rather than swallowed --
    blocking it would fix the value and break the scrolling, which is the same
    bug wearing a different hat.  Where there is no scrolling ancestor nothing
    is changed: the defect only exists inside a scroll area.
    """

    def eventFilter(self, obj: Any, event: Any) -> bool:  # noqa: N802 - Qt
        if event.type() != QEvent.Type.Wheel:
            return False
        # Installed per-widget *and* application-wide, so the type check has to
        # happen here: application-wide it sees every wheel event in the
        # program, including the ones the chart and the tables want.
        if not isinstance(obj, _VALUE_WIDGETS):
            return False
        if obj.hasFocus():
            return False
        area = _scrolling_ancestor(obj)
        if area is None:
            return False
        clone = QWheelEvent(
            event.position(), event.globalPosition(), event.pixelDelta(),
            event.angleDelta(), event.buttons(), event.modifiers(),
            event.phase(), event.inverted())
        QApplication.sendEvent(area.viewport(), clone)
        return True


def _scrolling_ancestor(widget: Any) -> Any:
    parent = widget.parentWidget() if hasattr(widget, "parentWidget") else None
    while parent is not None:
        if isinstance(parent, QAbstractScrollArea):
            return parent
        parent = parent.parentWidget()
    return None


#: One filter for the whole application.  An event filter is stateless here, so
#: a single instance can serve every widget; it also has to outlive the widgets
#: it is installed on, which a module-level object does and a local does not.
_WHEEL_GUARD = _WheelGuard()

#: What a stray scroll must not silently rewrite.
_VALUE_WIDGETS = (QComboBox, QAbstractSpinBox, QSlider)


def install_global_wheel_guard(app: Any = None) -> None:
    """Guard every value widget in the application, including future ones.

    Installing per-widget only protects what exists at that moment, and this
    application rebuilds its forms whenever the sizing mode changes -- so the
    boxes most worth protecting are exactly the ones a one-time sweep misses.
    One filter on the application object sees every wheel event and decides by
    the target's type.
    """
    target = app or QApplication.instance()
    if target is not None:
        target.installEventFilter(_WHEEL_GUARD)


def guard_value_wheels(root: QWidget) -> int:
    """Protect every value widget under ``root`` from a passing scroll.

    Returns how many were guarded, which is what the test asserts on.  Safe to
    call repeatedly: Qt ignores a duplicate event filter installation.
    """
    guarded = 0
    for widget in root.findChildren(QWidget):
        if isinstance(widget, _VALUE_WIDGETS):
            widget.installEventFilter(_WHEEL_GUARD)
            # Without this a wheel could still give the box focus on some
            # platforms and the next notch would be "deliberate".
            if widget.focusPolicy() == Qt.FocusPolicy.WheelFocus:
                widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            guarded += 1
    if isinstance(root, _VALUE_WIDGETS):
        root.installEventFilter(_WHEEL_GUARD)
        if root.focusPolicy() == Qt.FocusPolicy.WheelFocus:
            root.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        guarded += 1
    return guarded


class SectionLabel(QLabel):
    """A small uppercase heading used inside panels."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setObjectName("SectionHeader")
        self.setFont(Fonts.section())


class Card(QFrame):
    """A bordered block with an optional title."""

    def __init__(self, title: str = "", spacing: int = 6) -> None:
        super().__init__()
        self.setObjectName("Card")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(10, 9, 10, 10)
        self._lay.setSpacing(spacing)
        if title:
            self._lay.addWidget(SectionLabel(title))
            rule = QFrame()
            rule.setFixedHeight(1)
            rule.setStyleSheet(f"background:{PALETTE.border};")
            self._lay.addWidget(rule)

    def body(self) -> QVBoxLayout:
        return self._lay

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self._lay.addWidget(widget, stretch)
        return widget

    def add_layout(self, layout) -> None:
        self._lay.addLayout(layout)


class CollapsibleCard(QFrame):
    """A card whose body can be folded away, for the less-used settings."""

    toggled = Signal(bool)

    def __init__(self, title: str, expanded: bool = True) -> None:
        super().__init__()
        self.setObjectName("Card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 7, 10, 8)
        outer.setSpacing(5)

        from ..icons import icon

        head = QHBoxLayout()
        head.setSpacing(6)
        self._button = QToolButton()
        self._button.setIcon(icon("chevron-down" if expanded else "chevron-right",
                                  15, PALETTE.text_dim))
        self._button.setFixedSize(20, 20)
        self._button.clicked.connect(self._toggle)
        head.addWidget(self._button)
        self._title = SectionLabel(title)
        head.addWidget(self._title)
        head.addStretch(1)
        self._summary = QLabel("")
        self._summary.setFont(Fonts.numeric(8))
        self._summary.setStyleSheet(f"color:{PALETTE.text_muted};")
        head.addWidget(self._summary)
        outer.addLayout(head)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 3, 0, 0)
        self._content_layout.setSpacing(5)
        outer.addWidget(self._content)
        self._content.setVisible(expanded)
        self._expanded = expanded
        self.mousePressEvent = self._head_clicked  # type: ignore[method-assign]

    def _head_clicked(self, event) -> None:
        if event.position().y() < 26:
            self._toggle()

    def _toggle(self) -> None:
        from ..icons import icon

        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._button.setIcon(icon("chevron-down" if self._expanded else "chevron-right",
                                  15, PALETTE.text_dim))
        self.toggled.emit(self._expanded)

    def set_summary(self, text: str) -> None:
        self._summary.setText(text)

    def body(self) -> QVBoxLayout:
        return self._content_layout

    def add(self, widget: QWidget) -> QWidget:
        self._content_layout.addWidget(widget)
        return widget

    def add_layout(self, layout) -> None:
        self._content_layout.addLayout(layout)


def hline() -> QFrame:
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet(f"background:{PALETTE.border};")
    return f


# --------------------------------------------------------------------------
# Declarative form fields
# --------------------------------------------------------------------------

@dataclass
class FieldSpec:
    """One editable setting in a :class:`FormPanel`."""

    key: str
    label: str
    kind: str = "float"
    """``int``, ``float``, ``bool``, ``choice``, ``text`` or ``time``."""
    default: Any = 0
    minimum: float | None = None
    maximum: float | None = None
    step: float = 1.0
    decimals: int = 2
    suffix: str = ""
    choices: Sequence[tuple[str, Any]] = ()
    tooltip: str = ""
    enabled_by: str = ""
    """Key of a boolean field in the same form that switches this one on."""


class FormPanel(QWidget):
    """A grid of labelled editors built from :class:`FieldSpec` objects."""

    changed = Signal()

    def __init__(self, specs: Iterable[FieldSpec], columns: int = 1,
                 label_width: int = 0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._specs: list[FieldSpec] = list(specs)
        self._editors: dict[str, QWidget] = {}
        self._labels: dict[str, QLabel] = {}
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(9)
        grid.setVerticalSpacing(5)

        per_col = max(1, (len(self._specs) + columns - 1) // columns)
        for i, spec in enumerate(self._specs):
            col = (i // per_col) * 2
            row = i % per_col
            label = QLabel(spec.label)
            label.setFont(Fonts.body(9))
            label.setStyleSheet(f"color:{PALETTE.text_dim};")
            if label_width:
                label.setMinimumWidth(label_width)
            if spec.tooltip:
                label.setToolTip(spec.tooltip)
            editor = self._make_editor(spec)
            self._editors[spec.key] = editor
            self._labels[spec.key] = label
            if spec.kind == "bool":
                grid.addWidget(editor, row, col, 1, 2)
                label.hide()
            else:
                grid.addWidget(label, row, col)
                grid.addWidget(editor, row, col + 1)
            grid.setColumnStretch(col + 1, 1)

        for spec in self._specs:
            if spec.enabled_by:
                self._wire_dependency(spec)
        self._apply_dependencies()

    # -- editors ---------------------------------------------------------

    def _make_editor(self, spec: FieldSpec) -> QWidget:
        if spec.kind == "int":
            w = QSpinBox()
            w.setRange(int(spec.minimum if spec.minimum is not None else -10**9),
                       int(spec.maximum if spec.maximum is not None else 10**9))
            w.setSingleStep(int(max(1, spec.step)))
            w.setValue(int(spec.default))
            w.setSuffix(spec.suffix)
            w.setAlignment(Qt.AlignmentFlag.AlignRight)
            w.valueChanged.connect(self._on_changed)
        elif spec.kind == "float":
            w = QDoubleSpinBox()
            w.setDecimals(spec.decimals)
            w.setRange(float(spec.minimum if spec.minimum is not None else -1e12),
                       float(spec.maximum if spec.maximum is not None else 1e12))
            w.setSingleStep(float(spec.step))
            w.setValue(float(spec.default))
            w.setSuffix(spec.suffix)
            w.setAlignment(Qt.AlignmentFlag.AlignRight)
            w.setGroupSeparatorShown(True)
            w.valueChanged.connect(self._on_changed)
        elif spec.kind == "bool":
            w = QCheckBox(spec.label)
            w.setChecked(bool(spec.default))
            w.toggled.connect(self._on_changed)
        elif spec.kind == "choice":
            w = QComboBox()
            for text, value in spec.choices:
                w.addItem(text, value)
            idx = w.findData(spec.default)
            w.setCurrentIndex(max(0, idx))
            w.currentIndexChanged.connect(self._on_changed)
        elif spec.kind == "time":
            w = QLineEdit(str(spec.default))
            w.setInputMask("99:99")
            w.setMaximumWidth(70)
            w.textChanged.connect(self._on_changed)
        else:
            w = QLineEdit(str(spec.default))
            w.textChanged.connect(self._on_changed)
        if spec.tooltip:
            w.setToolTip(spec.tooltip)
        return w

    def _wire_dependency(self, spec: FieldSpec) -> None:
        source = self._editors.get(spec.enabled_by)
        if isinstance(source, QCheckBox):
            source.toggled.connect(lambda *_: self._apply_dependencies())

    def _apply_dependencies(self) -> None:
        for spec in self._specs:
            if not spec.enabled_by:
                continue
            source = self._editors.get(spec.enabled_by)
            on = bool(source.isChecked()) if isinstance(source, QCheckBox) else True
            self._editors[spec.key].setEnabled(on)
            self._labels[spec.key].setEnabled(on)

    def _on_changed(self, *_args) -> None:
        self._apply_dependencies()
        self.changed.emit()

    # -- values ----------------------------------------------------------

    def value(self, key: str) -> Any:
        w = self._editors[key]
        if isinstance(w, (QSpinBox, QDoubleSpinBox)):
            return w.value()
        if isinstance(w, QCheckBox):
            return w.isChecked()
        if isinstance(w, QComboBox):
            return w.currentData()
        if isinstance(w, QLineEdit):
            return w.text()
        return None

    def values(self) -> dict[str, Any]:
        return {k: self.value(k) for k in self._editors}

    def set_value(self, key: str, value: Any) -> None:
        w = self._editors.get(key)
        if w is None:
            return
        w.blockSignals(True)
        try:
            if isinstance(w, QSpinBox):
                w.setValue(int(value))
            elif isinstance(w, QDoubleSpinBox):
                w.setValue(float(value))
            elif isinstance(w, QCheckBox):
                w.setChecked(bool(value))
            elif isinstance(w, QComboBox):
                idx = w.findData(value)
                if idx < 0:
                    idx = w.findText(str(value))
                w.setCurrentIndex(max(0, idx))
            elif isinstance(w, QLineEdit):
                w.setText("" if value is None else str(value))
        finally:
            w.blockSignals(False)
        self._apply_dependencies()

    def set_values(self, values: dict[str, Any]) -> None:
        for k, v in values.items():
            self.set_value(k, v)

    def editor(self, key: str) -> QWidget | None:
        return self._editors.get(key)

    def set_enabled_keys(self, keys: Iterable[str], enabled: bool) -> None:
        for k in keys:
            if k in self._editors:
                self._editors[k].setEnabled(enabled)
                self._labels[k].setEnabled(enabled)


# --------------------------------------------------------------------------
# Error reporting
# --------------------------------------------------------------------------

class ErrorDialog(QDialog):
    """Shows a plain-language message with the technical detail folded away.

    A user should never be shown a traceback, but a user reporting a bug should
    be able to copy one, so it lives behind a Details button.
    """

    def __init__(self, title: str, message: str, detail: str = "",
                 parent: QWidget | None = None, icon_name: str = "warning",
                 colour: str | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(12)

        from ..icons import icon

        top = QHBoxLayout()
        top.setSpacing(12)
        badge = QLabel()
        badge.setPixmap(icon(icon_name, 30, colour or PALETTE.warning).pixmap(30, 30))
        badge.setAlignment(Qt.AlignmentFlag.AlignTop)
        top.addWidget(badge)
        text = QLabel(message)
        text.setWordWrap(True)
        text.setFont(Fonts.body(10))
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        top.addWidget(text, 1)
        lay.addLayout(top)

        self._detail_box = QPlainTextEdit(detail)
        self._detail_box.setReadOnly(True)
        self._detail_box.setFont(Fonts.numeric(8))
        self._detail_box.setMinimumHeight(150)
        self._detail_box.hide()
        lay.addWidget(self._detail_box)

        buttons = QHBoxLayout()
        if detail:
            self._details_btn = QPushButton("Details")
            self._details_btn.setObjectName("Ghost")
            self._details_btn.clicked.connect(self._toggle_detail)
            buttons.addWidget(self._details_btn)
            copy = QPushButton("Copy")
            copy.setObjectName("Ghost")
            copy.clicked.connect(self._copy)
            buttons.addWidget(copy)
        buttons.addStretch(1)
        ok = QPushButton("Close")
        ok.setObjectName("Primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        buttons.addWidget(ok)
        lay.addLayout(buttons)

    def _toggle_detail(self) -> None:
        visible = not self._detail_box.isVisible()
        self._detail_box.setVisible(visible)
        self._details_btn.setText("Hide details" if visible else "Details")
        self.adjustSize()

    def _copy(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self._detail_box.toPlainText())


def show_error(parent: QWidget | None, error: Exception | str,
               title: str | None = None, detail: str = "") -> None:
    """Show an error the way this application always shows errors.

    :class:`BacktesterError` carries its own user message and detail.  Anything
    else is reported generically and its repr goes into the detail box, because
    an unexpected exception type is a bug and its text is rarely fit to show.
    """
    import logging
    import traceback

    log = logging.getLogger("tradingbacktester.ui")
    if isinstance(error, BacktesterError):
        heading = title or error.title
        message = error.user_message
        tech = detail or error.detail or ""
        log.warning("%s: %s | %s", heading, message, tech)
    elif isinstance(error, str):
        heading = title or "Error"
        message = error
        tech = detail
        log.warning("%s: %s", heading, message)
    else:
        heading = title or "Unexpected Error"
        message = ("Something went wrong that the application did not expect. "
                   "The technical details have been written to the log file.")
        tech = detail or "".join(
            traceback.format_exception(type(error), error, error.__traceback__))
        log.exception("Unexpected error surfaced to the user")
    dlg = ErrorDialog(heading, message, tech, parent)
    dlg.exec()


def show_warning(parent: QWidget | None, title: str, message: str,
                 detail: str = "") -> None:
    ErrorDialog(title, message, detail, parent, "warning", PALETTE.warning).exec()


def show_info(parent: QWidget | None, title: str, message: str,
              detail: str = "") -> None:
    ErrorDialog(title, message, detail, parent, "info", PALETTE.info).exec()


def confirm(parent: QWidget | None, title: str, message: str,
            confirm_text: str = "Delete", danger: bool = True) -> bool:
    """A yes/no dialog styled for a destructive action."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setMinimumWidth(400)
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(18, 16, 18, 14)
    lay.setSpacing(14)
    text = QLabel(message)
    text.setWordWrap(True)
    text.setFont(Fonts.body(10))
    lay.addWidget(text)
    row = QHBoxLayout()
    row.addStretch(1)
    cancel = QPushButton("Cancel")
    cancel.clicked.connect(dlg.reject)
    row.addWidget(cancel)
    go = QPushButton(confirm_text)
    go.setObjectName("Danger" if danger else "Primary")
    go.setDefault(True)
    go.clicked.connect(dlg.accept)
    row.addWidget(go)
    lay.addLayout(row)
    return dlg.exec() == QDialog.DialogCode.Accepted


def ask_text(parent: QWidget | None, title: str, label: str,
             initial: str = "") -> str | None:
    """A single-line text prompt.  Returns ``None`` when cancelled."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setMinimumWidth(380)
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(18, 16, 18, 14)
    lay.setSpacing(10)
    lab = QLabel(label)
    lay.addWidget(lab)
    edit = QLineEdit(initial)
    edit.selectAll()
    lay.addWidget(edit)
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                           QDialogButtonBox.StandardButton.Cancel)
    box.accepted.connect(dlg.accept)
    box.rejected.connect(dlg.reject)
    lay.addWidget(box)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    return edit.text().strip()
