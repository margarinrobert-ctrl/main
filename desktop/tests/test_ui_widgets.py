"""Widget tests.

These run headless with ``QT_QPA_PLATFORM=offscreen``.  They do not check
appearance; they check that a widget can be constructed, fed real data, driven
through its interactions and torn down without raising -- which is what actually
breaks when a data structure changes underneath the UI.
"""

from __future__ import annotations

import numpy as np
import pytest

from tradingbacktester.core.types import ExitReason, Side, Trade
from tradingbacktester.engine.results import EquityCurves

from .conftest import make_bars

pytestmark = pytest.mark.gui


def build_trades(n: int = 25, point_value: float = 1.0) -> list[Trade]:
    """A deterministic set of trades with both winners and losers."""
    rng = np.random.default_rng(99)
    base = 1_672_617_600_000_000_000
    equity = 100_000.0
    out: list[Trade] = []
    for i in range(n):
        side = Side.LONG if i % 3 else Side.SHORT
        entry = 100.0 + rng.normal(0, 2)
        exit_ = entry + rng.normal(0.4, 2.0) * side.sign
        gross = (exit_ - entry) * side.sign * 2 * point_value
        net = gross - 2.0
        equity += net
        out.append(Trade(
            id=i, side=side, quantity=2.0,
            entry_bar=i * 6, entry_ts=base + i * 6 * 3600 * 10 ** 9,
            entry_price=entry,
            exit_bar=i * 6 + 4, exit_ts=base + (i * 6 + 4) * 3600 * 10 ** 9,
            exit_price=exit_,
            stop_loss=entry - 3 * side.sign, take_profit=entry + 6 * side.sign,
            gross_pnl=gross, commission=1.2, slippage_cost=0.5, spread_cost=0.3,
            net_pnl=net, return_pct=net / equity * 100.0, bars_held=4,
            duration_seconds=4 * 3600,
            exit_reason=[ExitReason.STOP_LOSS, ExitReason.TAKE_PROFIT,
                         ExitReason.SIGNAL][i % 3],
            mae=abs(rng.normal(2, 1)), mfe=abs(rng.normal(3, 1)),
            r_multiple=net / 6.0, equity_at_entry=equity - net,
            equity_after=equity))
    return out


def build_curves(n: int = 200) -> EquityCurves:
    rng = np.random.default_rng(7)
    ts = 1_672_617_600_000_000_000 + np.arange(n, dtype="int64") * 3600 * 10 ** 9
    equity = 100_000 + np.cumsum(rng.normal(20, 300, n))
    balance = np.maximum.accumulate(equity) - 500
    peak = np.maximum.accumulate(equity)
    drawdown = equity - peak
    return EquityCurves(ts=ts, equity=equity, balance=balance,
                        drawdown=drawdown, drawdown_pct=drawdown / peak,
                        exposure=np.where(rng.random(n) > 0.5, 1.0, 0.0),
                        peak=peak)


# --------------------------------------------------------------------------
# Chart
# --------------------------------------------------------------------------

def test_chart_accepts_bars_and_indicators(qapp, random_bars):
    from tradingbacktester.ui.widgets.chart_widget import ChartWidget

    chart = ChartWidget()
    chart.resize(1000, 600)
    chart.set_bars(random_bars)
    n = len(random_bars)
    sma = np.convolve(random_bars.close, np.ones(20) / 20, mode="full")[:n]
    sma[:19] = np.nan
    rsi = np.clip(50 + np.cumsum(np.full(n, 0.1)), 0, 100)
    chart.set_indicator_panels([
        {"ref": "sma", "label": "SMA 20", "panel": "price",
         "series": [{"name": "SMA", "values": sma, "color": "#4da3ff"}]},
        {"ref": "rsi", "label": "RSI", "panel": "sub", "range": (0, 100),
         "guides": [30, 70],
         "series": [{"name": "RSI", "values": rsi, "color": "#e3a008"}]},
    ])
    chart.show()
    qapp.processEvents()
    lo, hi = chart.visible_range()
    assert 0 <= lo < hi <= n
    chart.close()


def test_chart_handles_no_data(qapp):
    from tradingbacktester.ui.widgets.chart_widget import ChartWidget

    chart = ChartWidget()
    chart.set_bars(None)
    chart.set_indicator_panels([])
    chart.set_trades([])
    chart.fit_all()
    chart.zoom_in()
    chart.zoom_out()
    qapp.processEvents()
    chart.close()


def test_chart_navigation_and_types(qapp, random_bars):
    from tradingbacktester.ui.widgets.chart_widget import ChartWidget

    chart = ChartWidget()
    chart.resize(900, 500)
    chart.set_bars(random_bars)
    for kind in ("candles", "bars", "line", "area"):
        chart.set_chart_type(kind)
        qapp.processEvents()
    chart.show_last(50)
    lo, hi = chart.visible_range()
    assert hi - lo <= 120
    chart.fit_all()
    lo, hi = chart.visible_range()
    assert hi - lo >= len(random_bars) - 2
    chart.goto_bar(100)
    chart.toggle_crosshair()
    chart.toggle_crosshair()
    chart.close()


def test_chart_rebuilding_panels_does_not_accumulate_items(qapp, random_bars):
    """Re-running a backtest must not leave the previous run's curves behind."""
    from tradingbacktester.ui.widgets.chart_widget import ChartWidget

    chart = ChartWidget()
    chart.set_bars(random_bars)
    n = len(random_bars)
    panel = {"ref": "x", "label": "X", "panel": "sub",
             "series": [{"name": "x", "values": np.zeros(n), "color": "#fff"}]}
    for _ in range(5):
        chart.set_indicator_panels([panel])
        qapp.processEvents()
    # price + volume + exactly one sub-panel, however many times it was rebuilt
    assert len(chart._panels) == 3
    chart.close()


def test_chart_does_not_leak_items_across_rebuilds(qapp, random_bars):
    """Every re-run rebuilds the indicator panels; nothing may be left behind.

    Removing an item from the ViewBox rather than the PlotItem leaves it in the
    plot's item list, so curves, band fills and crosshair lines pile up one set
    per backtest until the chart crawls.
    """
    from pyqtgraph import FillBetweenItem

    from tradingbacktester.ui.widgets.chart_widget import ChartWidget

    chart = ChartWidget()
    chart.resize(800, 500)
    chart.set_bars(random_bars)
    baseline = len(chart.price_plot.items)

    band = {"ref": "bb", "label": "BB", "panel": "price", "series": [
        {"name": "u", "output": "upper", "values": random_bars.close + 5,
         "color": "#8f9bb3"},
        {"name": "l", "output": "lower", "values": random_bars.close - 5,
         "color": "#8f9bb3", "fill_to": "upper", "fill_color": "#4aa3ff22"}]}
    sub = {"ref": "osc", "label": "OSC", "panel": "sub", "range": (0, 100),
           "guides": [30, 70],
           "series": [{"name": "o", "output": "value",
                       "values": np.full(len(random_bars), 55.0),
                       "color": "#b07cf0"}]}
    line = {"ref": "ema", "label": "EMA", "panel": "price", "series": [
        {"name": "e", "output": "value", "values": random_bars.close,
         "color": "#4da3ff"}]}

    seen = []
    for i in range(6):
        chart.set_indicator_panels([band, sub] if i % 2 == 0 else [line])
        qapp.processEvents()
        seen.append(len(chart.price_plot.items))

    # The counts must repeat, not climb.
    assert seen[0] == seen[2] == seen[4], seen
    assert seen[1] == seen[3] == seen[5], seen

    chart.set_indicator_panels([])
    qapp.processEvents()
    assert len(chart.price_plot.items) == baseline
    assert not [i for i in chart.price_plot.items if isinstance(i, FillBetweenItem)]
    assert len(chart._panels) == 2          # price and volume only
    assert len(chart._time_axes) == 2
    chart.close()


def test_chart_parses_css_alpha_colours():
    """The indicator library writes #RRGGBBAA; Qt reads #AARRGGBB.

    Handing the string straight to QColor turns a faint blue band bright green.
    """
    from tradingbacktester.ui.widgets.chart_widget import ChartWidget

    c = ChartWidget._fill_colour("#4aa3ff22")
    assert (c.red(), c.green(), c.blue(), c.alpha()) == (0x4A, 0xA3, 0xFF, 0x22)
    solid = ChartWidget._fill_colour("#4da3ff")
    assert (solid.red(), solid.alpha()) == (0x4D, 255)


def test_chart_shows_trades_and_selection(qapp, random_bars):
    from tradingbacktester.ui.widgets.chart_widget import ChartWidget

    chart = ChartWidget()
    chart.resize(900, 500)
    chart.set_bars(random_bars)
    trades = build_trades(10)
    chart.set_trades(trades)
    chart.select_trade(3)
    qapp.processEvents()
    chart.select_trade(None)
    chart.close()


# --------------------------------------------------------------------------
# Equity
# --------------------------------------------------------------------------

def test_equity_widget_with_one_run(qapp):
    from tradingbacktester.ui.widgets.equity_widget import EquityWidget

    curves = build_curves()
    widget = EquityWidget()
    widget._starting_capital = 100_000.0
    widget.resize(900, 480)
    widget.set_series(curves.ts, [{
        "label": "Run A", "equity": curves.equity, "balance": curves.balance,
        "drawdown_pct": curves.drawdown_pct * 100.0, "color": "#4da3ff",
        "fill": True}])
    widget.show()
    qapp.processEvents()
    widget.set_cursor_bar(50)
    widget.fit_all()
    widget.clear()
    widget.close()


def test_equity_widget_with_several_runs(qapp):
    from tradingbacktester.ui.widgets.equity_widget import EquityWidget

    a, b = build_curves(), build_curves(200)
    widget = EquityWidget()
    widget.set_series(a.ts, [
        {"label": "A", "equity": a.equity, "drawdown_pct": a.drawdown_pct * 100},
        {"label": "B", "equity": b.equity * 1.02,
         "drawdown_pct": b.drawdown_pct * 100},
    ])
    qapp.processEvents()
    widget.close()


# --------------------------------------------------------------------------
# Trade table
# --------------------------------------------------------------------------

def test_trade_table_filters_and_sorts(qapp):
    from tradingbacktester.ui.widgets.trade_table import TradeTableWidget

    trades = build_trades(40)
    table = TradeTableWidget()
    table.resize(1400, 300)
    table.set_trades(trades, decimals=2, currency="$", timezone="America/New_York")
    assert table.model.rowCount() == 40
    assert table.proxy.rowCount() == 40

    table.side_box.setCurrentIndex(1)          # long only
    qapp.processEvents()
    shown = table.visible_trades()
    assert shown and all(t.side is Side.LONG for t in shown)

    table.side_box.setCurrentIndex(0)
    table.outcome_box.setCurrentIndex(2)       # losers only
    qapp.processEvents()
    shown = table.visible_trades()
    assert shown and all(t.net_pnl < 0 for t in shown)

    table.outcome_box.setCurrentIndex(0)
    table.search.setText("LONG")
    qapp.processEvents()
    assert table.proxy.rowCount() > 0

    table.search.setText("")
    from PySide6.QtCore import Qt

    table.table.sortByColumn(13, Qt.SortOrder.DescendingOrder)   # net P&L
    qapp.processEvents()
    ordered = table.visible_trades()
    assert ordered[0].net_pnl >= ordered[-1].net_pnl
    table.close()


def test_trade_table_handles_no_trades(qapp):
    from tradingbacktester.ui.widgets.trade_table import TradeTableWidget

    table = TradeTableWidget()
    table.set_trades([])
    qapp.processEvents()
    assert table.proxy.rowCount() == 0
    assert table.visible_trades() == []
    table.close()


def test_trade_table_selection_maps_through_the_filter(qapp):
    from tradingbacktester.ui.widgets.trade_table import TradeTableWidget

    trades = build_trades(30)
    received: list[int] = []
    table = TradeTableWidget()
    table.set_trades(trades)
    table.tradeSelected.connect(received.append)
    table.side_box.setCurrentIndex(1)          # filter, so proxy != source rows
    qapp.processEvents()
    table.select_trade(4)
    qapp.processEvents()
    # The signal must carry the index into the ORIGINAL list, not the view.
    assert received and received[-1] == 4
    table.close()


# --------------------------------------------------------------------------
# Stats, periodic and forms
# --------------------------------------------------------------------------

def test_stats_panel_renders_metrics_and_reliability(qapp):
    from tradingbacktester.ui.widgets.stats_panel import StatsPanel

    panel = StatsPanel()
    panel.set_metrics({
        "net_profit": 1234.5, "return_pct": 1.23, "max_drawdown_pct": -4.5,
        "total_trades": 12, "profit_factor": float("inf"),
        "sharpe_ratio": float("nan"),
        "exit_reason_breakdown": {"stop_loss": {"count": 5, "net_pnl": -300.0}},
        "reliability": {"profit_factor": "unavailable", "sharpe_ratio": "low_sample"},
        "reliability_notes": {"profit_factor": "no losing trades"},
    }, currency="$")
    qapp.processEvents()
    # isVisible() needs the whole ancestor chain shown; isHidden() asks only
    # whether this widget was explicitly hidden, which is what is being tested.
    assert not panel.notice.isHidden()           # 12 trades is a small sample
    panel.clear()
    panel.set_metrics(None)
    panel.close()


def test_stats_panel_survives_missing_keys(qapp):
    from tradingbacktester.ui.widgets.stats_panel import StatsPanel

    panel = StatsPanel()
    panel.set_metrics({"net_profit": 0.0})      # everything else absent
    qapp.processEvents()
    panel.close()


def test_periodic_table(qapp):
    from tradingbacktester.ui.widgets.periodic_table import (DrawdownTable,
                                                             PeriodicReturnsTable)

    table = PeriodicReturnsTable()
    table.set_data({"years": [2023, 2024],
                    "months": [[1.0] * 12, [-1.0] * 6 + [None] * 6],
                    "totals": {2023: 12.0, 2024: -6.0}})
    qapp.processEvents()
    table.set_data(None)                        # the empty case must not raise
    table.close()

    dd = DrawdownTable()
    dd.set_data([{"start_ts": 1_672_617_600_000_000_000,
                  "trough_ts": 1_672_704_000_000_000_000,
                  "end_ts": None, "depth": -500.0, "depth_pct": -5.0,
                  "length_bars": 40, "recovery_bars": None}], "$", "UTC")
    qapp.processEvents()
    dd.clear()
    dd.close()


def test_form_panel_round_trips_values(qapp):
    from tradingbacktester.ui.widgets.common import FieldSpec, FormPanel

    form = FormPanel([
        FieldSpec("n", "Count", "int", 10, 1, 100, 1),
        FieldSpec("x", "Value", "float", 1.5, 0.0, 10.0, 0.1, 2),
        FieldSpec("on", "Enabled", "bool", True),
        FieldSpec("mode", "Mode", "choice", "b",
                  choices=[("A", "a"), ("B", "b")]),
        FieldSpec("dep", "Dependent", "float", 2.0, 0.0, 5.0, 0.5, 2,
                  enabled_by="on"),
    ])
    assert form.values() == {"n": 10, "x": 1.5, "on": True, "mode": "b", "dep": 2.0}
    form.set_values({"n": 42, "x": 3.25, "on": False, "mode": "a"})
    assert form.values()["n"] == 42
    assert form.values()["mode"] == "a"
    # Turning the switch off must disable its dependent field.
    assert not form.editor("dep").isEnabled()
    form.close()


def test_risk_panel_builds_and_restores_a_config(qapp):
    from tradingbacktester.core.types import SizingMode
    from tradingbacktester.ui.widgets.risk_panel import RiskPanel

    panel = RiskPanel()
    panel.capital_form.set_value("starting_capital", 50_000.0)
    panel.capital_form.set_value("sizing_mode", SizingMode.RISK_PERCENT.value)
    panel.capital_form.set_value("risk_percent", 2.0)
    panel.cost_form.set_value("commission_value", 2.5)
    panel.exit_form.set_value("stop_loss_enabled", True)
    panel.exit_form.set_value("stop_loss_value", 1.75)

    config = panel.build_config()
    assert config.starting_capital == 50_000.0
    assert config.risk.sizing_mode is SizingMode.RISK_PERCENT
    assert config.risk.risk_percent == 2.0
    assert config.costs.commission_value == 2.5
    assert config.exits.stop_loss_enabled and config.exits.stop_loss_value == 1.75

    fresh = RiskPanel()
    fresh.apply_config(config)
    assert fresh.build_config().risk.risk_percent == 2.0
    assert fresh.build_config().exits.stop_loss_value == 1.75
    panel.close()
    fresh.close()


def test_theme_formatters():
    from tradingbacktester.ui.theme import duration, money, number, pct, value_color

    assert money(1234.5, "$") == "$1,234.50"
    assert money(-1234.5, "$") == "-$1,234.50"
    assert money(float("nan")) == "-"
    assert money(None) == "-"
    assert pct(12.3456) == "12.35%"
    assert pct(12.3456, signed=True) == "+12.35%"
    assert number(float("inf")) == "∞"
    assert duration(45) == "45s"
    assert duration(3600) == "1h"
    assert duration(90000) == "1d 1h"
    assert duration(None) == "-"
    assert value_color(1) != value_color(-1)


def test_money_takes_a_symbol_not_a_currency_code():
    """`money(v, "USD")` gives "USD1,234.50", which reads as a typo."""
    from tradingbacktester.ui.theme import currency_symbol, money

    assert currency_symbol("USD") == "$"
    assert currency_symbol("usd") == "$", "the code's case must not matter"
    # An unknown code keeps its information but gains the space it needs.
    assert currency_symbol("SEK") == "SEK "
    assert currency_symbol("") == "" and currency_symbol(None) == ""
    assert money(1234.5, currency_symbol("EUR")) == "€1,234.50"
    assert money(-1234.5, currency_symbol("SEK")) == "-SEK 1,234.50"


def test_every_icon_renders(qapp):
    from tradingbacktester.ui.icons import available_icons, icon

    names = available_icons()
    assert len(names) > 30
    for name in names:
        assert not icon(name, 20).isNull(), name
    # An unknown name must give an empty icon, never an exception.
    icon("no-such-icon", 16)


def test_stats_panel_shows_the_market_neutral_group(qapp):
    """A Sharpe on raw cash cannot tell an edge from leverage; the panel says so."""
    from PySide6.QtWidgets import QLabel

    from tradingbacktester.analytics.metrics import compute_metrics
    from tradingbacktester.core.types import BacktestConfig
    from tradingbacktester.data.sample import generate_sample_data
    from tradingbacktester.engine.backtester import Backtester
    from tradingbacktester.strategy.builtin import BUILTIN_STRATEGIES
    from tradingbacktester.ui.theme import PALETTE
    from tradingbacktester.ui.widgets.stats_panel import StatsPanel, _MetricRow

    bars = generate_sample_data("NQ", "1h", n_bars=3000, seed=5)
    spec = BUILTIN_STRATEGIES["EMA Cross + RSI"]()
    config = BacktestConfig(starting_capital=100_000.0)
    config.exits, config.execution = spec.exits, spec.execution
    config.session, config.costs, config.risk = spec.session, spec.costs, spec.risk
    result = Backtester(bars, spec, config).run()

    panel = StatsPanel()
    panel.set_metrics(compute_metrics(result), currency="$")
    qapp.processEvents()

    shown = {}
    for row in panel.findChildren(_MetricRow):
        labels = row.findChildren(QLabel)
        if len(labels) >= 2:
            shown[labels[0].text()] = labels[-1].text()

    for label in ("Residual Sharpe", "Market share of P&L", "Beta to the window",
                  "Best sub-period share", "Sessions"):
        assert label in shown, f"{label} missing from the panel"
    # A fraction rendered as a percentage, not as 0.87%.
    assert shown["Market share of P&L"].endswith("%")
    assert shown["Sessions"].replace(",", "").isdigit()


def test_a_fraction_renders_as_a_percentage_not_as_itself():
    """`pct(0.87)` is "0.87%", which would be wrong by a factor of a hundred."""
    from tradingbacktester.ui.widgets.stats_panel import StatsPanel

    panel = StatsPanel.__new__(StatsPanel)      # no Qt needed for the formatter
    panel._currency = "$"
    assert panel._format(0.8672, "pct_unit") == "86.72%"
    assert panel._format(0.8672, "pct") == "0.87%"
    assert panel._format(None, "pct_unit") == "-"


def test_the_two_diagnostics_go_amber_past_their_limit_not_green():
    """A high beta share is a warning, not an achievement."""
    import math

    from tradingbacktester.ui.theme import PALETTE
    from tradingbacktester.ui.widgets.stats_panel import _limit_colour

    assert _limit_colour("beta_pnl_share", 0.87) == PALETTE.warning
    assert _limit_colour("beta_pnl_share", 0.10) == PALETTE.text_dim
    assert _limit_colour("concentration", 0.90) == PALETTE.warning
    assert _limit_colour("concentration", 0.25) == PALETTE.text_dim
    assert _limit_colour("beta_pnl_share", float("nan")) == PALETTE.text_dim
    assert _limit_colour("beta_pnl_share", None) is None
