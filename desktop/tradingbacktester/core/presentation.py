"""The palette and the scalar formatters — the presentation layer without Qt.

These live below ``ui/`` because the HTML report needs them and needs nothing
else from the user interface: it emits a string. Reaching into ``ui.theme`` for
a colour table and a thousands separator made ``reports/`` the one package in
the application that could not be imported without PySide6, which is both
untrue to the architecture and a real constraint on anything that wants a
report from a machine with no Qt installed.

What genuinely needs Qt stays in ``ui.theme``: :class:`~tradingbacktester.ui.theme.Fonts`,
which builds ``QFont`` objects and resolves families against the installed set,
the stylesheet, and ``apply_theme``. Everything here is strings and arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: CSS font stacks for the HTML report. The families the widgets actually
#: resolve against the installed set are ``Fonts.ui`` and ``Fonts.mono``; a
#: document that will be opened on somebody else's machine wants a stack with
#: fallbacks rather than whichever font happened to be present when it was
#: written.
UI_FONT_STACK = '"Segoe UI Variable Text", "Segoe UI", Inter, "Noto Sans", system-ui, sans-serif'
MONO_FONT_STACK = '"Cascadia Mono", Consolas, "JetBrains Mono", "SF Mono", ui-monospace, monospace'


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

    def qcolor(self, name: str, alpha: int = 255) -> Any:
        """One palette entry as a ``QColor``, for the widgets that paint.

        Qt is imported inside the call rather than at the top of the module:
        the palette is a table of hex strings and everything else about it
        works without PySide6, which is what lets the HTML report use it. Only
        a widget ever asks for a QColor, and a widget has Qt by definition.
        """
        from PySide6.QtGui import QColor

        c = QColor(getattr(self, name))
        c.setAlpha(alpha)
        return c


PALETTE = Palette()


# --------------------------------------------------------------------------

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

#: Currency codes we have a symbol for. Anything else is prefixed with the code
#: and a space -- "SEK 1,234.50" -- because an ISO code jammed against the
#: digits ("SEK1,234.50") reads as a typo, and a made-up symbol would be worse
#: than either.
CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥",
                    "CHF": "CHF ", "AUD": "A$", "CAD": "C$"}


def currency_symbol(code: str) -> str:
    """The prefix to put in front of an amount in ``code``.

    A symbol where one exists, the code and a space where it does not, and an
    empty string for no currency at all. :func:`money`-style formatters take a
    *prefix*, never a code, so anything holding an instrument should pass its
    currency through here first.
    """
    text = str(code or "").strip().upper()
    if not text:
        return ""
    return CURRENCY_SYMBOLS.get(text, f"{text} ")
