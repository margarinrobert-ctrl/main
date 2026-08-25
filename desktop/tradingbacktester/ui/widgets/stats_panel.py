"""The performance statistics panel.

Reads the metric dictionary produced by
:func:`tradingbacktester.analytics.metrics.compute_metrics` and lays it out in
labelled groups.  Any metric the analytics layer flagged as statistically
unreliable is drawn dimmed with a warning badge, because a Sharpe ratio computed
from eleven trades is not a number anyone should act on and the interface should
say so rather than presenting it like the rest.
"""

from __future__ import annotations

import math
from typing import Any, Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from ..theme import PALETTE, Fonts, duration, money, number, pct


class _MetricRow(QWidget):
    """One label/value pair with an optional reliability badge."""

    def __init__(self, label: str, tooltip: str = "") -> None:
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.name = QLabel(label)
        self.name.setFont(Fonts.body(9))
        self.name.setStyleSheet(f"color:{PALETTE.text_dim};")
        lay.addWidget(self.name)
        lay.addStretch(1)
        self.badge = QLabel("")
        self.badge.setFont(Fonts.body(7, bold=True))
        self.badge.hide()
        lay.addWidget(self.badge)
        self.value = QLabel("-")
        self.value.setFont(Fonts.numeric(9))
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight |
                                Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self.value)
        if tooltip:
            self.setToolTip(tooltip)

    def set_value(self, text: str, colour: str | None = None,
                  reliability: str = "ok", reason: str = "") -> None:
        self.value.setText(text)
        col = colour or PALETTE.text
        if reliability == "unavailable":
            col = PALETTE.text_muted
            self.badge.setText("N/A")
            self.badge.setStyleSheet(
                f"color:{PALETTE.text_muted}; border:1px solid {PALETTE.border};"
                f"border-radius:3px; padding:0 3px;")
            self.badge.show()
        elif reliability == "low_sample":
            self.badge.setText("LOW n")
            self.badge.setStyleSheet(
                f"color:{PALETTE.warning}; border:1px solid {PALETTE.warning};"
                f"border-radius:3px; padding:0 3px;")
            self.badge.show()
        else:
            self.badge.hide()
        self.value.setStyleSheet(f"color:{col};")
        if reason:
            self.setToolTip(reason)


class _Group(QFrame):
    """A titled block of metric rows."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("Card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 9)
        lay.setSpacing(3)
        head = QLabel(title)
        head.setObjectName("SectionHeader")
        head.setFont(Fonts.section())
        lay.addWidget(head)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background:{PALETTE.border};")
        lay.addWidget(line)
        lay.addSpacing(3)
        self._lay = lay
        self.rows: dict[str, _MetricRow] = {}

    def add(self, key: str, label: str, tooltip: str = "") -> _MetricRow:
        row = _MetricRow(label, tooltip)
        self.rows[key] = row
        self._lay.addWidget(row)
        return row


class _Headline(QFrame):
    """The big net-profit / return / drawdown block at the top of the panel."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Card")
        grid = QGridLayout(self)
        grid.setContentsMargins(12, 10, 12, 11)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(2)
        self._cells: dict[str, tuple[QLabel, QLabel]] = {}
        for col, (key, title) in enumerate((("net_profit", "NET PROFIT"),
                                            ("return_pct", "RETURN"),
                                            ("max_drawdown_pct", "MAX DD"))):
            cap = QLabel(title)
            cap.setFont(Fonts.section())
            cap.setStyleSheet(f"color:{PALETTE.text_muted};")
            val = QLabel("-")
            val.setFont(Fonts.numeric(14, bold=True))
            grid.addWidget(cap, 0, col)
            grid.addWidget(val, 1, col)
            grid.setColumnStretch(col, 1)
            self._cells[key] = (cap, val)

    def set(self, key: str, text: str, colour: str) -> None:
        if key in self._cells:
            self._cells[key][1].setText(text)
            self._cells[key][1].setStyleSheet(f"color:{colour};")


#: Definition of the panel: groups, and the metrics inside them.  ``fmt`` picks
#: the formatter; ``sign`` colours the value by whether it is above zero.
_LAYOUT: tuple[tuple[str, tuple[tuple[str, str, str, bool, str], ...]], ...] = (
    ("Profit and Loss", (
        ("net_profit", "Net profit", "money", True, "Ending balance minus starting capital, after all costs"),
        ("gross_profit", "Gross profit", "money", True, "Sum of every winning trade before costs"),
        ("gross_loss", "Gross loss", "money", True, "Sum of every losing trade before costs"),
        ("return_pct", "Return", "pct", True, "Net profit as a percentage of starting capital"),
        ("cagr", "CAGR", "pct", True, "Compound annual growth rate over the tested period"),
        ("starting_balance", "Starting balance", "money", False, ""),
        ("ending_balance", "Ending balance", "money", False, ""),
        ("profit_factor", "Profit factor", "ratio", True, "Gross profit divided by gross loss; above 1 is profitable"),
        ("expectancy", "Expectancy", "money", True, "Average net profit per trade"),
        ("expectancy_r", "Expectancy (R)", "ratio", True, "Average trade result in multiples of the initial risk"),
    )),
    ("Trades", (
        ("total_trades", "Total trades", "int", False, ""),
        ("winning_trades", "Winners", "int", False, ""),
        ("losing_trades", "Losers", "int", False, ""),
        ("win_rate", "Win rate", "pct", False, "Percentage of trades closed at a profit"),
        ("avg_trade", "Average trade", "money", True, ""),
        ("avg_win", "Average win", "money", True, ""),
        ("avg_loss", "Average loss", "money", True, ""),
        ("payoff_ratio", "Payoff ratio", "ratio", False, "Average win divided by average loss"),
        ("largest_win", "Largest win", "money", True, ""),
        ("largest_loss", "Largest loss", "money", True, ""),
        ("max_consecutive_wins", "Max consecutive wins", "int", False, ""),
        ("max_consecutive_losses", "Max consecutive losses", "int", False, ""),
        ("avg_trade_duration_seconds", "Average duration", "duration", False, ""),
        ("avg_bars_held", "Average bars held", "float1", False, ""),
        ("trades_per_year", "Trades per year", "float1", False, ""),
    )),
    ("Risk", (
        ("max_drawdown", "Max drawdown", "money", True, "Largest peak-to-trough fall in equity, in cash"),
        ("max_drawdown_pct", "Max drawdown %", "pct", True, "Largest peak-to-trough fall relative to the running peak"),
        ("max_drawdown_duration_bars", "Longest drawdown", "int_bars", False, "Bars spent below the previous equity peak"),
        ("recovery_factor", "Recovery factor", "ratio", True, "Net profit divided by maximum drawdown"),
        ("sharpe_ratio", "Sharpe ratio", "ratio", True, "Annualised excess return divided by return volatility"),
        ("sortino_ratio", "Sortino ratio", "ratio", True, "Like Sharpe but penalising only downside volatility"),
        ("calmar_ratio", "Calmar ratio", "ratio", True, "Annual return divided by maximum drawdown"),
        ("annual_volatility_pct", "Annual volatility", "pct", False, ""),
        ("ulcer_index", "Ulcer index", "ratio", False, "Root mean square of the drawdown series"),
        ("sqn", "System quality (SQN)", "ratio", True, "sqrt(n) x mean(R) / stdev(R)"),
        ("kelly_fraction", "Kelly fraction", "ratio", False, "Theoretical optimal fraction of capital; treat as an upper bound"),
        ("exposure_pct", "Time in market", "pct", False, "Percentage of bars with an open position"),
    )),
    ("Costs", (
        ("total_commission", "Commission", "money_cost", False, ""),
        ("total_slippage", "Slippage", "money_cost", False, ""),
        ("total_spread_cost", "Spread", "money_cost", False, ""),
        ("total_costs", "Total costs", "money_cost", False, "What the strategy paid to trade"),
    )),
    ("Long / Short", (
        ("long_trades", "Long trades", "int", False, ""),
        ("long_win_rate", "Long win rate", "pct", False, ""),
        ("long_net_profit", "Long net profit", "money", True, ""),
        ("short_trades", "Short trades", "int", False, ""),
        ("short_win_rate", "Short win rate", "pct", False, ""),
        ("short_net_profit", "Short net profit", "money", True, ""),
    )),
    ("Excursion", (
        ("avg_mae", "Average MAE", "points", False, "Average worst adverse move while a trade was open, in price points"),
        ("avg_mfe", "Average MFE", "points", False, "Average best favourable move while a trade was open, in price points"),
        ("avg_r_multiple", "Average R", "ratio", True, ""),
        ("std_r_multiple", "R standard deviation", "ratio", False, ""),
    )),
)


class StatsPanel(QWidget):
    """The right-hand performance panel."""

    metricClicked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._currency = ""
        self._decimals = 2
        self._groups: dict[str, _Group] = {}
        self._rows: dict[str, tuple[_MetricRow, str, bool]] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        self.headline = _Headline()
        outer.addWidget(self.headline)

        self.notice = QLabel("")
        self.notice.setWordWrap(True)
        self.notice.setObjectName("Warning")
        self.notice.setFont(Fonts.body(8))
        self.notice.hide()
        outer.addWidget(self.notice)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.setSpacing(6)

        for title, metrics in _LAYOUT:
            group = _Group(title)
            for key, label, fmt, signed, tip in metrics:
                row = group.add(key, label, tip)
                self._rows[key] = (row, fmt, signed)
            self._groups[title] = group
            lay.addWidget(group)

        self.exit_group = _Group("Exit Reasons")
        lay.addWidget(self.exit_group)
        lay.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

    # -- data ------------------------------------------------------------

    def set_metrics(self, metrics: dict[str, Any] | None, currency: str = "",
                    decimals: int = 2) -> None:
        self._currency = currency
        self._decimals = decimals
        if not metrics:
            self.clear()
            return

        reliability: dict[str, str] = metrics.get("reliability", {}) or {}
        notes: dict[str, str] = metrics.get("reliability_notes", {}) or {}

        for key, (row, fmt, signed) in self._rows.items():
            value = metrics.get(key)
            text = self._format(value, fmt)
            colour = None
            if signed and isinstance(value, (int, float)) and not isinstance(value, bool):
                v = float(value)
                if key in ("max_drawdown", "max_drawdown_pct", "gross_loss",
                           "largest_loss", "avg_loss"):
                    colour = PALETTE.short if v != 0 else PALETTE.text_dim
                elif fmt == "ratio" and key in ("profit_factor", "recovery_factor",
                                                "sharpe_ratio", "sortino_ratio",
                                                "calmar_ratio", "sqn"):
                    threshold = 1.0 if key in ("profit_factor", "recovery_factor") else 0.0
                    colour = (PALETTE.long if v > threshold else
                              PALETTE.short if v < threshold else PALETTE.text_dim)
                elif v > 0:
                    colour = PALETTE.long
                elif v < 0:
                    colour = PALETTE.short
                else:
                    colour = PALETTE.text_dim
            state = reliability.get(key, "ok")
            row.set_value(text, colour, state, notes.get(key, ""))

        net = float(metrics.get("net_profit", 0.0) or 0.0)
        ret = float(metrics.get("return_pct", 0.0) or 0.0)
        dd = float(metrics.get("max_drawdown_pct", 0.0) or 0.0)
        self.headline.set("net_profit", money(net, currency),
                          PALETTE.long if net > 0 else PALETTE.short if net < 0
                          else PALETTE.text)
        self.headline.set("return_pct", pct(ret, 2, signed=True),
                          PALETTE.long if ret > 0 else PALETTE.short if ret < 0
                          else PALETTE.text)
        self.headline.set("max_drawdown_pct", pct(abs(dd)), PALETTE.short if dd else
                          PALETTE.text)

        self._set_exit_breakdown(metrics.get("exit_reason_breakdown", {}) or {})

        n = int(metrics.get("total_trades", 0) or 0)
        if n == 0:
            self._notice("This run produced no trades. Check the entry rules, the "
                         "date range and the session filter.")
        elif n < 30:
            self._notice(f"Only {n} trades. Ratios such as profit factor, Sharpe and "
                         f"win rate are dominated by noise at this sample size and are "
                         f"marked LOW n below.")
        else:
            self.notice.hide()

    def _set_exit_breakdown(self, breakdown: dict[str, Any]) -> None:
        for row in list(self.exit_group.rows.values()):
            row.setParent(None)
        self.exit_group.rows.clear()
        if not breakdown:
            row = self.exit_group.add("none", "No trades")
            row.set_value("-")
            return
        for reason, info in sorted(breakdown.items(),
                                   key=lambda kv: -abs(_as_float(kv[1], "net_pnl"))):
            label = str(reason).replace("_", " ").title()
            row = self.exit_group.add(str(reason), label)
            count = int(_as_float(info, "count"))
            pnl = _as_float(info, "net_pnl")
            colour = (PALETTE.long if pnl > 0 else PALETTE.short if pnl < 0
                      else PALETTE.text_dim)
            row.set_value(f"{count} · {money(pnl, self._currency)}", colour)

    def _notice(self, text: str) -> None:
        self.notice.setText(text)
        self.notice.show()

    def clear(self) -> None:
        for row, _fmt, _signed in self._rows.values():
            row.set_value("-", PALETTE.text_muted)
        for key in ("net_profit", "return_pct", "max_drawdown_pct"):
            self.headline.set(key, "-", PALETTE.text_muted)
        self._set_exit_breakdown({})
        self.notice.hide()

    # -- formatting ------------------------------------------------------

    def _format(self, value: Any, fmt: str) -> str:
        if value is None:
            return "-"
        if isinstance(value, float) and math.isnan(value):
            return "-"
        if fmt == "money":
            return money(value, self._currency)
        if fmt == "money_cost":
            return money(-abs(float(value)), self._currency) if value else "-"
        if fmt == "pct":
            return pct(value)
        if fmt == "int":
            return f"{int(value):,}"
        if fmt == "int_bars":
            return f"{int(value):,} bars"
        if fmt == "float1":
            return number(value, 1)
        if fmt == "ratio":
            if isinstance(value, float) and math.isinf(value):
                return "∞"
            return number(value, 2)
        if fmt == "duration":
            return duration(value)
        if fmt == "points":
            return number(value, self._decimals)
        return str(value)


def _as_float(info: Any, key: str) -> float:
    """Read a field from an exit-reason breakdown entry, whatever its shape."""
    if isinstance(info, dict):
        try:
            return float(info.get(key, 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0
    try:
        return float(info)
    except (TypeError, ValueError):
        return 0.0
