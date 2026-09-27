"""A always-on strip saying what is on screen: instrument, data, strategy, state.

This exists because of a specific failure. The chart drew the selected
strategy's indicators while the blotter, the equity curve and the headline
still held the *previous* strategy's run, and nothing on screen said so -- the
window named one thing and showed another's numbers, and the user's report was
simply "the charts is not the same as selected".

The clearing is fixed in the main window. This is the other half: a line that
states, at all times and in one place, which instrument, which bars, which
strategy, and whether the results below belong to that strategy or to nothing
yet. A terminal that answers "what am I looking at" without being asked is the
difference between a tool and a puzzle.

Every field is monospace and fixed-order, so the eye learns where to look and
a changed value is noticed by its position rather than by reading the line.
"""

from __future__ import annotations

from typing import Any


from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QWidget

from ..theme import PALETTE, Fonts


class _Field(QWidget):
    """One caption-over-value pair, in the fixed slot it always occupies."""

    def __init__(self, caption: str, width: int = 0) -> None:
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)

        self.caption = QLabel(caption.upper())
        self.caption.setFont(Fonts.body(7, bold=True))
        self.caption.setStyleSheet(f"color:{PALETTE.text_muted};")
        lay.addWidget(self.caption)

        self.value = QLabel("—")
        self.value.setFont(Fonts.numeric(9))
        self.value.setStyleSheet(f"color:{PALETTE.text};")
        if width:
            self.value.setMinimumWidth(width)
        lay.addWidget(self.value)

    def set(self, text: str, colour: str | None = None) -> None:
        self.value.setText(text or "—")
        self.value.setStyleSheet(f"color:{colour or PALETTE.text};")


class ContextBar(QFrame):
    """What instrument, what data, what strategy, and whose results."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ContextBar")
        self.setStyleSheet(
            f"#ContextBar {{ background: {PALETTE.panel_alt}; "
            f"border-bottom: 1px solid {PALETTE.border}; }}")
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setFixedHeight(26)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(16)

        self.symbol = _Field("symbol", 70)
        self.timeframe = _Field("tf", 40)
        self.bars = _Field("bars", 70)
        self.span = _Field("range", 160)
        self.strategy = _Field("strategy", 150)
        self.state = _Field("showing", 130)
        for field in (self.symbol, self.timeframe, self.bars, self.span,
                      self.strategy, self.state):
            lay.addWidget(field)
        lay.addStretch(1)

        self.set_data(None)
        self.set_strategy(None)
        self.set_result(None, None)

    # -- what is loaded --------------------------------------------------

    def set_data(self, bars: Any) -> None:
        if bars is None or len(bars) == 0:
            self.symbol.set("—")
            self.timeframe.set("—")
            self.bars.set("—")
            self.span.set("no data loaded", PALETTE.text_muted)
            return
        instrument = getattr(bars, "instrument", None)
        self.symbol.set(getattr(instrument, "symbol", "?") or "?")
        timeframe = getattr(bars, "timeframe", None)
        self.timeframe.set(str(getattr(timeframe, "label", timeframe) or "?"))
        self.bars.set(f"{len(bars):,}")
        self.span.set(_span(bars), PALETTE.text_dim)

    def set_strategy(self, spec: Any) -> None:
        self.strategy.set(getattr(spec, "name", "") or "none selected",
                          PALETTE.text if spec is not None
                          else PALETTE.text_muted)

    def set_result(self, result: Any, spec_name: str | None) -> None:
        """Say whose numbers are on screen, or that there are none.

        The whole point of the strip: "showing MACD Trend" beside a picker
        that says Donchian is a contradiction the user can see, where the two
        silently disagreeing was not.
        """
        if result is None:
            self.state.set("nothing run yet", PALETTE.text_muted)
            return
        trades = len(getattr(result, "trades", ()) or ())
        net = float((getattr(result, "metrics", {}) or {}).get("net_profit", 0.0)
                    or 0.0)
        colour = (PALETTE.long if net > 0 else
                  PALETTE.short if net < 0 else PALETTE.text)
        name = spec_name or "a strategy"
        self.state.set(f"{name} · {trades:,} trades", colour)


def _span(bars: Any) -> str:
    """First and last timestamp, in the instrument's own timezone."""
    try:
        import pandas as pd

        ts = getattr(bars, "ts", None)
        if ts is None or len(ts) == 0:
            return "—"
        tz = getattr(getattr(bars, "instrument", None), "timezone", "") or "UTC"
        first = pd.Timestamp(int(ts[0]), tz="UTC").tz_convert(tz)
        last = pd.Timestamp(int(ts[-1]), tz="UTC").tz_convert(tz)
        return f"{first:%Y-%m-%d} → {last:%Y-%m-%d}"
    except Exception:                       # pragma: no cover - display only
        return "—"
