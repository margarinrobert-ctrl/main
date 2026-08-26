"""The dark terminal theme: palette, fonts and the application stylesheet.

Everything visual is defined here so the look can be changed in one place and so
no widget hard-codes a colour.  The palette is deliberately low-chroma except for
the four semantic accents -- long, short, focus and warning -- because a trading
screen that colours everything ends up communicating nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette


@dataclass(frozen=True)
class Palette:
    """Every colour the application uses, as hex strings."""

    # Surfaces, darkest to lightest.
    app_bg: str = "#0b0f16"
    panel_bg: str = "#111722"
    panel_alt: str = "#151d2a"
    elevated: str = "#1b2534"
    hover: str = "#212c3d"
    pressed: str = "#182231"
    border: str = "#232f42"
    border_strong: str = "#31415a"

    # Text.
    text: str = "#e3e9f2"
    text_dim: str = "#93a1b5"
    text_muted: str = "#64748b"
    text_inverse: str = "#0b0f16"

    # Semantics.
    accent: str = "#3d8bfd"
    accent_hover: str = "#5a9dff"
    accent_dim: str = "#1f4d8f"
    long: str = "#26a69a"
    long_dim: str = "#1a6f67"
    short: str = "#ef5350"
    short_dim: str = "#9c3634"
    warning: str = "#e3a008"
    danger: str = "#f0554e"
    success: str = "#35b96b"
    info: str = "#4fa8d8"

    # Chart furniture.
    grid: str = "#1a2333"
    grid_strong: str = "#243149"
    axis_text: str = "#7b8a9e"
    crosshair: str = "#7e8ea3"
    volume_up: str = "#1f6f68"
    volume_down: str = "#7a3634"
    equity: str = "#4da3ff"
    equity_fill: str = "#183350"
    balance: str = "#7f8fa6"
    drawdown: str = "#c2413c"
    drawdown_fill: str = "#3a1a1d"
    marker_long: str = "#2ecc9a"
    marker_short: str = "#ff6b6b"
    marker_exit: str = "#c8d2e0"
    stop_line: str = "#b8474a"
    target_line: str = "#2f9e8f"
    session_shade: str = "#0e1826"

    #: Colour cycle for indicator lines, chosen to stay distinguishable on dark
    #: and to avoid the long/short greens and reds.
    series: tuple[str, ...] = (
        "#4da3ff", "#e3a008", "#b07cf0", "#4fd1c5", "#f08f4a",
        "#7dd3fc", "#f472b6", "#a3e635", "#facc15", "#94a3b8",
    )

    def series_color(self, index: int) -> str:
        return self.series[index % len(self.series)]

    def qcolor(self, name: str, alpha: int = 255) -> QColor:
        c = QColor(getattr(self, name))
        c.setAlpha(alpha)
        return c


PALETTE = Palette()


# --------------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------------

_UI_FONT_CANDIDATES = ("Segoe UI Variable Text", "Segoe UI", "Inter", "Noto Sans",
                       "DejaVu Sans", "Helvetica Neue", "Arial")
_MONO_FONT_CANDIDATES = ("Cascadia Mono", "Consolas", "JetBrains Mono", "SF Mono",
                         "Menlo", "DejaVu Sans Mono", "Liberation Mono", "Courier New")


def _first_available(candidates: Iterable[str], fallback: str) -> str:
    families = set(QFontDatabase.families())
    for name in candidates:
        if name in families:
            return name
    return fallback


class Fonts:
    """Resolved font families, chosen once at start-up."""

    ui: str = "Segoe UI"
    mono: str = "Consolas"
    _resolved = False

    @classmethod
    def resolve(cls) -> None:
        if cls._resolved:
            return
        cls.ui = _first_available(_UI_FONT_CANDIDATES, "sans-serif")
        cls.mono = _first_available(_MONO_FONT_CANDIDATES, "monospace")
        cls._resolved = True

    @classmethod
    def body(cls, size: int = 9, bold: bool = False) -> QFont:
        cls.resolve()
        f = QFont(cls.ui, size)
        f.setBold(bold)
        f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        return f

    @classmethod
    def numeric(cls, size: int = 9, bold: bool = False) -> QFont:
        """Tabular figures for anything in a column that must line up."""
        cls.resolve()
        f = QFont(cls.mono, size)
        f.setBold(bold)
        f.setStyleHint(QFont.StyleHint.Monospace)
        f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        return f

    @classmethod
    def heading(cls, size: int = 11) -> QFont:
        cls.resolve()
        f = QFont(cls.ui, size)
        f.setWeight(QFont.Weight.DemiBold)
        return f

    @classmethod
    def section(cls) -> QFont:
        """Small caps-ish label used for panel section headers."""
        cls.resolve()
        f = QFont(cls.ui, 8)
        f.setWeight(QFont.Weight.DemiBold)
        f.setCapitalization(QFont.Capitalization.AllUppercase)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
        return f


# --------------------------------------------------------------------------
# Stylesheet
# --------------------------------------------------------------------------

def stylesheet(p: Palette = PALETTE) -> str:
    """The application-wide Qt stylesheet.

    Written against object names and dynamic properties rather than deep
    descendant selectors so that individual widgets stay restyleable.
    """
    return f"""
* {{
    outline: 0;
}}

QWidget {{
    background-color: {p.app_bg};
    color: {p.text};
    font-family: "{Fonts.ui}";
    font-size: 12px;
    selection-background-color: {p.accent_dim};
    selection-color: {p.text};
}}

QWidget:disabled {{ color: {p.text_muted}; }}

QMainWindow, QDialog {{ background-color: {p.app_bg}; }}

/* ---- panels ---------------------------------------------------------- */

QFrame#Panel, QWidget#Panel {{
    background-color: {p.panel_bg};
    border: 1px solid {p.border};
    border-radius: 6px;
}}

QFrame#Card {{
    background-color: {p.panel_alt};
    border: 1px solid {p.border};
    border-radius: 6px;
}}

QLabel#SectionHeader {{
    color: {p.text_dim};
    background: transparent;
    padding: 2px 0 2px 0;
}}

QLabel#PanelTitle {{
    color: {p.text};
    font-size: 13px;
    font-weight: 600;
    background: transparent;
}}

QLabel#Hint  {{ color: {p.text_muted}; background: transparent; }}
QLabel#Value {{ color: {p.text}; font-family: "{Fonts.mono}"; background: transparent; }}
QLabel#ValuePositive {{ color: {p.long}; font-family: "{Fonts.mono}"; background: transparent; }}
QLabel#ValueNegative {{ color: {p.short}; font-family: "{Fonts.mono}"; background: transparent; }}
QLabel#Warning {{ color: {p.warning}; background: transparent; }}
QLabel#Danger  {{ color: {p.danger}; background: transparent; }}
QLabel {{ background: transparent; }}

/* ---- toolbar --------------------------------------------------------- */

QToolBar {{
    background-color: {p.panel_bg};
    border: none;
    border-bottom: 1px solid {p.border};
    padding: 4px 6px;
    spacing: 4px;
}}

QToolBar::separator {{
    background: {p.border};
    width: 1px;
    margin: 5px 6px;
}}

QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 5px 9px;
    color: {p.text_dim};
}}
QToolButton:hover {{ background: {p.hover}; color: {p.text}; border-color: {p.border}; }}
QToolButton:pressed, QToolButton:checked {{
    background: {p.pressed}; color: {p.accent}; border-color: {p.border_strong};
}}
QToolButton:disabled {{ color: {p.text_muted}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}

/* ---- buttons --------------------------------------------------------- */

QPushButton {{
    background-color: {p.elevated};
    border: 1px solid {p.border_strong};
    border-radius: 4px;
    padding: 6px 14px;
    color: {p.text};
    min-height: 16px;
}}
QPushButton:hover {{ background-color: {p.hover}; border-color: {p.accent_dim}; }}
QPushButton:pressed {{ background-color: {p.pressed}; }}
QPushButton:disabled {{ background-color: {p.panel_alt}; color: {p.text_muted};
                        border-color: {p.border}; }}
QPushButton:default {{ border-color: {p.accent_dim}; }}

QPushButton#Primary {{
    background-color: {p.accent};
    border: 1px solid {p.accent};
    color: #ffffff;
    font-weight: 600;
}}
QPushButton#Primary:hover  {{ background-color: {p.accent_hover}; border-color: {p.accent_hover}; }}
QPushButton#Primary:pressed{{ background-color: {p.accent_dim}; }}
QPushButton#Primary:disabled {{ background-color: {p.accent_dim}; color: {p.text_muted};
                                border-color: {p.accent_dim}; }}

QPushButton#Danger {{
    background-color: {p.short_dim}; border-color: {p.short}; color: #ffffff;
}}
QPushButton#Danger:hover {{ background-color: {p.short}; }}

QPushButton#Ghost {{
    background: transparent; border: 1px solid {p.border};
    color: {p.text_dim};
}}
QPushButton#Ghost:hover {{ background: {p.hover}; color: {p.text}; }}

/* ---- inputs ---------------------------------------------------------- */

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox,
QComboBox, QDateEdit, QDateTimeEdit, QTimeEdit {{
    background-color: {p.app_bg};
    border: 1px solid {p.border_strong};
    border-radius: 4px;
    padding: 4px 7px;
    color: {p.text};
    selection-background-color: {p.accent_dim};
    min-height: 17px;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QComboBox:focus, QDateEdit:focus, QDateTimeEdit:focus {{
    border-color: {p.accent};
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    background-color: {p.panel_alt}; color: {p.text_muted}; border-color: {p.border};
}}
QLineEdit[invalid="true"], QSpinBox[invalid="true"], QDoubleSpinBox[invalid="true"] {{
    border-color: {p.danger};
}}
QLineEdit#Numeric, QSpinBox, QDoubleSpinBox {{ font-family: "{Fonts.mono}"; }}

QSpinBox::up-button, QDoubleSpinBox::up-button,
QDateEdit::up-button, QDateTimeEdit::up-button {{
    subcontrol-origin: border; subcontrol-position: top right;
    width: 15px; border-left: 1px solid {p.border};
    border-top-right-radius: 4px; background: {p.panel_alt};
}}
QSpinBox::down-button, QDoubleSpinBox::down-button,
QDateEdit::down-button, QDateTimeEdit::down-button {{
    subcontrol-origin: border; subcontrol-position: bottom right;
    width: 15px; border-left: 1px solid {p.border};
    border-bottom-right-radius: 4px; background: {p.panel_alt};
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{ background: {p.hover}; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow,
QDateEdit::up-arrow, QDateTimeEdit::up-arrow {{
    width: 0; height: 0; border-left: 3px solid transparent;
    border-right: 3px solid transparent; border-bottom: 4px solid {p.text_dim};
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow,
QDateEdit::down-arrow, QDateTimeEdit::down-arrow {{
    width: 0; height: 0; border-left: 3px solid transparent;
    border-right: 3px solid transparent; border-top: 4px solid {p.text_dim};
}}

QComboBox::drop-down {{
    subcontrol-origin: padding; subcontrol-position: center right;
    width: 18px; border: none;
}}
QComboBox::down-arrow {{
    width: 0; height: 0; border-left: 4px solid transparent;
    border-right: 4px solid transparent; border-top: 5px solid {p.text_dim};
    margin-right: 6px;
}}
QComboBox::down-arrow:hover {{ border-top-color: {p.text}; }}
QComboBox QAbstractItemView {{
    background-color: {p.elevated};
    border: 1px solid {p.border_strong};
    selection-background-color: {p.accent_dim};
    outline: none;
    padding: 3px;
}}

QCheckBox, QRadioButton {{ spacing: 7px; background: transparent; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 14px; height: 14px; }}
QCheckBox::indicator {{
    border: 1px solid {p.border_strong}; border-radius: 3px; background: {p.app_bg};
}}
QCheckBox::indicator:hover {{ border-color: {p.accent}; }}
QCheckBox::indicator:checked {{
    background: {p.accent}; border-color: {p.accent};
    image: url(:/qt-project.org/styles/commonstyle/images/standardbutton-apply-16.png);
}}
QCheckBox::indicator:disabled {{ border-color: {p.border}; background: {p.panel_alt}; }}
QRadioButton::indicator {{
    border: 1px solid {p.border_strong}; border-radius: 7px; background: {p.app_bg};
}}
QRadioButton::indicator:checked {{ background: {p.accent}; border: 4px solid {p.app_bg};
                                   width: 8px; height: 8px; border-radius: 7px; }}

QSlider::groove:horizontal {{ height: 3px; background: {p.border_strong}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {p.accent}; width: 12px; margin: -5px 0; border-radius: 6px;
}}
QSlider::sub-page:horizontal {{ background: {p.accent_dim}; border-radius: 2px; }}

/* ---- group boxes ----------------------------------------------------- */

QGroupBox {{
    background-color: {p.panel_alt};
    border: 1px solid {p.border};
    border-radius: 5px;
    margin-top: 16px;
    padding: 10px 9px 9px 9px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 9px; top: 1px; padding: 0 5px;
    color: {p.text_dim}; background-color: {p.panel_alt};
    font-size: 10px; text-transform: uppercase;
}}

/* ---- tabs ------------------------------------------------------------ */

QTabWidget::pane {{
    border: 1px solid {p.border};
    border-radius: 5px;
    background-color: {p.panel_bg};
    top: -1px;
}}
QTabBar {{ qproperty-drawBase: 0; background: transparent; }}
QTabBar::tab {{
    background: transparent;
    color: {p.text_muted};
    border: 1px solid transparent;
    border-top-left-radius: 5px; border-top-right-radius: 5px;
    padding: 6px 14px; margin-right: 2px;
}}
QTabBar::tab:hover {{ color: {p.text}; background: {p.panel_alt}; }}
QTabBar::tab:selected {{
    color: {p.text}; background: {p.panel_bg};
    border-color: {p.border}; border-bottom-color: {p.panel_bg};
}}

/* ---- tables ---------------------------------------------------------- */

QTableView, QTreeView, QListView {{
    background-color: {p.panel_bg};
    alternate-background-color: {p.panel_alt};
    border: 1px solid {p.border};
    border-radius: 5px;
    gridline-color: {p.grid};
    selection-background-color: {p.accent_dim};
    selection-color: {p.text};
}}
QTableView {{ font-family: "{Fonts.mono}"; }}
QTableView::item, QTreeView::item, QListView::item {{ padding: 3px 6px; border: 0; }}
QTableView::item:selected, QTreeView::item:selected, QListView::item:selected {{
    background: {p.accent_dim};
}}
QTableView::item:hover, QTreeView::item:hover, QListView::item:hover {{ background: {p.hover}; }}

QHeaderView {{ background: transparent; }}
QHeaderView::section {{
    background-color: {p.elevated};
    color: {p.text_dim};
    border: 0;
    border-right: 1px solid {p.border};
    border-bottom: 1px solid {p.border};
    padding: 5px 7px;
    font-family: "{Fonts.ui}";
    font-weight: 600;
    font-size: 11px;
}}
QHeaderView::section:hover {{ background-color: {p.hover}; color: {p.text}; }}
QHeaderView::section:last {{ border-right: 0; }}
QHeaderView::down-arrow {{
    width: 0; height: 0; border-left: 4px solid transparent;
    border-right: 4px solid transparent; border-top: 5px solid {p.accent};
    margin-right: 5px; subcontrol-position: center right;
}}
QHeaderView::up-arrow {{
    width: 0; height: 0; border-left: 4px solid transparent;
    border-right: 4px solid transparent; border-bottom: 5px solid {p.accent};
    margin-right: 5px; subcontrol-position: center right;
}}
QTableCornerButton::section {{ background: {p.elevated}; border: 0; }}

/* ---- scrollbars ------------------------------------------------------ */

QScrollBar:vertical {{
    background: transparent; width: 11px; margin: 0; border: none;
}}
QScrollBar::handle:vertical {{
    background: {p.border_strong}; min-height: 28px;
    border-radius: 5px; margin: 2px;
}}
QScrollBar::handle:vertical:hover {{ background: {p.text_muted}; }}
QScrollBar:horizontal {{
    background: transparent; height: 11px; margin: 0; border: none;
}}
QScrollBar::handle:horizontal {{
    background: {p.border_strong}; min-width: 28px;
    border-radius: 5px; margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{ background: {p.text_muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; border: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---- splitters, docks, status bar ------------------------------------ */

QSplitter::handle {{ background: {p.app_bg}; }}
QSplitter::handle:horizontal {{ width: 5px; }}
QSplitter::handle:vertical {{ height: 5px; }}
QSplitter::handle:hover {{ background: {p.accent_dim}; }}

QDockWidget {{ titlebar-close-icon: none; titlebar-normal-icon: none;
               color: {p.text_dim}; font-weight: 600; }}
QDockWidget::title {{
    background: {p.elevated}; padding: 6px 9px; border-bottom: 1px solid {p.border};
}}

QStatusBar {{
    background: {p.panel_bg}; border-top: 1px solid {p.border}; color: {p.text_dim};
}}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ padding: 0 8px; }}

/* ---- menus ----------------------------------------------------------- */

QMenuBar {{ background: {p.panel_bg}; border-bottom: 1px solid {p.border}; padding: 2px; }}
QMenuBar::item {{ background: transparent; padding: 5px 11px; border-radius: 4px;
                  color: {p.text_dim}; }}
QMenuBar::item:selected {{ background: {p.hover}; color: {p.text}; }}

QMenu {{
    background: {p.elevated}; border: 1px solid {p.border_strong};
    border-radius: 6px; padding: 5px;
}}
QMenu::item {{ padding: 6px 26px 6px 22px; border-radius: 4px; color: {p.text}; }}
QMenu::item:selected {{ background: {p.accent_dim}; }}
QMenu::item:disabled {{ color: {p.text_muted}; }}
QMenu::separator {{ height: 1px; background: {p.border}; margin: 5px 8px; }}
QMenu::icon {{ padding-left: 6px; }}

/* ---- progress, tooltip ----------------------------------------------- */

QProgressBar {{
    background: {p.app_bg}; border: 1px solid {p.border}; border-radius: 4px;
    text-align: center; color: {p.text_dim}; height: 16px;
    font-family: "{Fonts.mono}"; font-size: 10px;
}}
QProgressBar::chunk {{ background-color: {p.accent}; border-radius: 3px; }}

QToolTip {{
    background: {p.elevated}; color: {p.text};
    border: 1px solid {p.border_strong}; border-radius: 4px; padding: 5px 8px;
}}

/* ---- misc ------------------------------------------------------------ */

QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

QLabel#StatChip {{
    background: {p.panel_alt}; border: 1px solid {p.border};
    border-radius: 4px; padding: 6px 9px;
}}

#ChartContainer {{ background: {p.app_bg}; border: 1px solid {p.border}; border-radius: 6px; }}
"""


def apply_theme(app) -> None:
    """Apply fonts, the Qt palette and the stylesheet to a ``QApplication``."""
    Fonts.resolve()
    app.setStyle("Fusion")
    app.setFont(Fonts.body(9))

    p = PALETTE
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(p.app_bg))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(p.text))
    pal.setColor(QPalette.ColorRole.Base, QColor(p.panel_bg))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(p.panel_alt))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(p.elevated))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(p.text))
    pal.setColor(QPalette.ColorRole.Text, QColor(p.text))
    pal.setColor(QPalette.ColorRole.Button, QColor(p.elevated))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(p.text))
    pal.setColor(QPalette.ColorRole.BrightText, QColor(p.danger))
    pal.setColor(QPalette.ColorRole.Link, QColor(p.accent))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(p.accent_dim))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(p.text))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(p.text_muted))
    for group in (QPalette.ColorGroup.Disabled,):
        pal.setColor(group, QPalette.ColorRole.Text, QColor(p.text_muted))
        pal.setColor(group, QPalette.ColorRole.ButtonText, QColor(p.text_muted))
        pal.setColor(group, QPalette.ColorRole.WindowText, QColor(p.text_muted))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet(p))


# --------------------------------------------------------------------------
# Value formatting used across every panel
# --------------------------------------------------------------------------

#: Currency codes we have a symbol for. Anything else prints as the bare
#: number: a made-up symbol is worse than none, and prefixing an ISO code
#: straight onto the digits ("USD99,767.71") reads as a typo.
_CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥",
                     "CHF": "CHF ", "AUD": "A$", "CAD": "C$"}


def currency_symbol(code: str) -> str:
    """The symbol for an ISO currency code, or an empty string.

    :func:`money` takes a *prefix*, not a code, so anything that has an
    instrument in hand should pass its currency through here first.
    """
    return _CURRENCY_SYMBOLS.get(str(code or "").upper(), "")


def money(value: float, currency: str = "", decimals: int = 2) -> str:
    """Format cash with a thousands separator and an explicit sign for negatives."""
    if value is None:
        return "-"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "-"
    if v != v:  # NaN
        return "-"
    if v in (float("inf"), float("-inf")):
        return "∞" if v > 0 else "-∞"
    sign = "-" if v < 0 else ""
    return f"{sign}{currency}{abs(v):,.{decimals}f}"


def pct(value: float, decimals: int = 2, signed: bool = False) -> str:
    if value is None:
        return "-"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "-"
    if v != v:
        return "-"
    if v in (float("inf"), float("-inf")):
        return "∞%" if v > 0 else "-∞%"
    return f"{v:+.{decimals}f}%" if signed else f"{v:.{decimals}f}%"


def number(value: float, decimals: int = 2) -> str:
    if value is None:
        return "-"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if v != v:
        return "-"
    if v in (float("inf"), float("-inf")):
        return "∞" if v > 0 else "-∞"
    return f"{v:,.{decimals}f}"


def duration(seconds: float) -> str:
    """Compact human duration: ``2d 4h``, ``35m``, ``18s``."""
    if seconds is None or seconds != seconds:
        return "-"
    s = int(max(0.0, float(seconds)))
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s}s" if s else f"{m}m"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h}h {m}m" if m else f"{h}h"
    d, h = divmod(h, 24)
    return f"{d}d {h}h" if h else f"{d}d"


def value_color(value: float, p: Palette = PALETTE) -> str:
    """Green above zero, red below, neutral at zero."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return p.text
    if v != v:
        return p.text_muted
    if v > 0:
        return p.long
    if v < 0:
        return p.short
    return p.text_dim
