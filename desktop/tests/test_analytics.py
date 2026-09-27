"""Performance metrics, equity curves and period returns.

Every expectation is computed by hand in the test so a failure points at the
formula, not at another implementation of the same formula.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from tradingbacktester.analytics.equity import (build_curves, drawdown_table,
                                                underwater_periods)
from tradingbacktester.analytics.metrics import compute_metrics
from tradingbacktester.analytics.periodic import monthly_returns, yearly_returns
from tradingbacktester.core.types import (BacktestConfig, ExitReason, Side,
                                          Trade)
from tradingbacktester.engine.results import BacktestResult

HOUR_NS = 3_600_000_000_000
START_NS = 1_672_617_600_000_000_000        # 2023-01-02 00:00 UTC


def make_trade(pnl: float, index: int = 0, side: Side = Side.LONG,
               risk: float = 10.0, equity: float = 100_000.0) -> Trade:
    entry = 100.0
    exit_ = entry + pnl
    return Trade(
        id=index, side=side, quantity=1.0,
        entry_bar=index * 4, entry_ts=START_NS + index * 4 * HOUR_NS,
        entry_price=entry,
        exit_bar=index * 4 + 2, exit_ts=START_NS + (index * 4 + 2) * HOUR_NS,
        exit_price=exit_, stop_loss=entry - risk, take_profit=entry + risk * 2,
        gross_pnl=pnl, commission=0.0, slippage_cost=0.0, spread_cost=0.0,
        net_pnl=pnl, return_pct=pnl / equity * 100.0, bars_held=2,
        duration_seconds=2 * 3600,
        exit_reason=ExitReason.TAKE_PROFIT if pnl > 0 else ExitReason.STOP_LOSS,
        mae=abs(min(pnl, 0.0)), mfe=abs(max(pnl, 0.0)),
        r_multiple=pnl / risk, equity_at_entry=equity, equity_after=equity + pnl)


def make_result(trades, equity_points, starting: float = 100_000.0,
                timeframe: str = "1h") -> BacktestResult:
    equity = np.asarray(equity_points, dtype="float64")
    ts = START_NS + np.arange(len(equity), dtype="int64") * HOUR_NS
    balance = equity.copy()
    curves = build_curves(ts, equity, balance, np.zeros(len(equity)))
    config = BacktestConfig(starting_capital=starting)
    result = BacktestResult(
        run_id="test", label="Test", strategy_name="Test",
        instrument_symbol="TEST", timeframe_label=timeframe,
        config=config, trades=list(trades), curves=curves,
        bars_processed=len(equity))
    result.metrics = compute_metrics(result)
    return result


# --------------------------------------------------------------------------
# Equity curves
# --------------------------------------------------------------------------

def test_drawdown_is_peak_to_trough():
    """[100, 110, 90, 120] falls 20 from a peak of 110: 18.1818%."""
    ts = START_NS + np.arange(4, dtype="int64") * HOUR_NS
    equity = np.array([100.0, 110.0, 90.0, 120.0])
    curves = build_curves(ts, equity, equity, np.zeros(4))
    assert np.allclose(curves.peak, [100.0, 110.0, 110.0, 120.0])
    assert curves.drawdown.min() == pytest.approx(-20.0)
    assert curves.drawdown_pct.min() == pytest.approx(-20.0 / 110.0)
    assert curves.drawdown[-1] == pytest.approx(0.0)


def test_drawdown_of_a_monotonic_curve_is_zero():
    ts = START_NS + np.arange(5, dtype="int64") * HOUR_NS
    equity = np.array([100.0, 101.0, 102.0, 103.0, 104.0])
    curves = build_curves(ts, equity, equity, np.zeros(5))
    assert np.allclose(curves.drawdown, 0.0)


def test_underwater_periods_finds_each_excursion():
    ts = START_NS + np.arange(8, dtype="int64") * HOUR_NS
    equity = np.array([100.0, 110.0, 90.0, 95.0, 115.0, 105.0, 100.0, 120.0])
    curves = build_curves(ts, equity, equity, np.zeros(8))
    periods = underwater_periods(curves)
    assert len(periods) == 2
    assert min(p["depth"] for p in periods) == pytest.approx(-20.0)


def test_drawdown_table_is_deepest_first():
    ts = START_NS + np.arange(8, dtype="int64") * HOUR_NS
    equity = np.array([100.0, 110.0, 90.0, 95.0, 115.0, 105.0, 100.0, 120.0])
    curves = build_curves(ts, equity, equity, np.zeros(8))
    rows = drawdown_table(curves, top=5)
    assert rows
    depths = [r["depth"] for r in rows]
    assert depths == sorted(depths)          # most negative first


# --------------------------------------------------------------------------
# Trade metrics
# --------------------------------------------------------------------------

def test_headline_trade_metrics_by_hand():
    """+10, -5, +15: gross 25, gross loss -5, PF 5, expectancy 6.667, WR 66.67%."""
    trades = [make_trade(10.0, 0), make_trade(-5.0, 1), make_trade(15.0, 2)]
    equity = [100_000.0, 100_010.0, 100_005.0, 100_020.0]
    result = make_result(trades, equity)
    m = result.metrics

    assert m["total_trades"] == 3
    assert m["winning_trades"] == 2
    assert m["losing_trades"] == 1
    assert m["gross_profit"] == pytest.approx(25.0)
    assert m["gross_loss"] == pytest.approx(-5.0)
    assert m["net_profit"] == pytest.approx(20.0)
    assert m["profit_factor"] == pytest.approx(5.0)
    assert m["expectancy"] == pytest.approx(20.0 / 3.0)
    assert m["win_rate"] == pytest.approx(200.0 / 3.0)
    assert m["avg_win"] == pytest.approx(12.5)
    assert m["avg_loss"] == pytest.approx(-5.0)
    assert m["largest_win"] == pytest.approx(15.0)
    assert m["largest_loss"] == pytest.approx(-5.0)
    assert m["payoff_ratio"] == pytest.approx(2.5)


def test_return_pct_is_relative_to_starting_capital():
    trades = [make_trade(1000.0, 0)]
    result = make_result(trades, [100_000.0, 101_000.0])
    assert result.metrics["return_pct"] == pytest.approx(1.0)


def test_consecutive_streaks():
    pnls = [1, 1, 1, -1, -1, 1, -1, -1, -1, -1]
    trades = [make_trade(float(p), i) for i, p in enumerate(pnls)]
    equity = [100_000.0] + list(100_000.0 + np.cumsum(pnls))
    m = make_result(trades, equity).metrics
    assert m["max_consecutive_wins"] == 3
    assert m["max_consecutive_losses"] == 4


def test_long_and_short_are_split():
    trades = [make_trade(10.0, 0, Side.LONG), make_trade(-4.0, 1, Side.LONG),
              make_trade(6.0, 2, Side.SHORT)]
    equity = [100_000.0, 100_010.0, 100_006.0, 100_012.0]
    m = make_result(trades, equity).metrics
    assert m["long_trades"] == 2
    assert m["short_trades"] == 1
    assert m["long_net_profit"] == pytest.approx(6.0)
    assert m["short_net_profit"] == pytest.approx(6.0)
    assert m["long_win_rate"] == pytest.approx(50.0)
    assert m["short_win_rate"] == pytest.approx(100.0)


def test_exit_reason_breakdown():
    trades = [make_trade(10.0, 0), make_trade(-5.0, 1), make_trade(8.0, 2)]
    equity = [100_000.0, 100_010.0, 100_005.0, 100_013.0]
    breakdown = make_result(trades, equity).metrics["exit_reason_breakdown"]
    assert "take_profit" in breakdown and "stop_loss" in breakdown
    assert breakdown["take_profit"]["count"] == 2
    assert breakdown["stop_loss"]["net_pnl"] == pytest.approx(-5.0)


# --------------------------------------------------------------------------
# Degenerate cases -- nothing may raise
# --------------------------------------------------------------------------

def test_no_trades_at_all():
    result = make_result([], [100_000.0] * 50)
    m = result.metrics
    assert m["total_trades"] == 0
    assert m["net_profit"] == pytest.approx(0.0)
    assert m["win_rate"] == pytest.approx(0.0)
    assert m["max_drawdown_pct"] == pytest.approx(0.0)
    assert m["reliability"]


def test_one_trade():
    result = make_result([make_trade(5.0, 0)], [100_000.0, 100_005.0])
    assert result.metrics["total_trades"] == 1
    assert result.metrics["reliability"].get("profit_factor") in (
        "low_sample", "unavailable")


def test_all_winning_trades_gives_infinite_profit_factor():
    trades = [make_trade(float(x), i) for i, x in enumerate([5, 7, 3])]
    equity = [100_000.0, 100_005.0, 100_012.0, 100_015.0]
    m = make_result(trades, equity).metrics
    assert math.isinf(m["profit_factor"])
    assert m["reliability"]["profit_factor"] == "unavailable"


def test_flat_equity_curve_gives_zero_sharpe_not_nan():
    result = make_result([], [100_000.0] * 200)
    sharpe = result.metrics["sharpe_ratio"]
    assert sharpe == pytest.approx(0.0) or sharpe is None
    assert not (isinstance(sharpe, float) and math.isnan(sharpe))


def test_single_bar_curve_does_not_raise():
    result = make_result([], [100_000.0])
    assert result.metrics["total_trades"] == 0


def test_all_losing_trades():
    trades = [make_trade(-2.0, i) for i in range(4)]
    equity = [100_000.0] + list(100_000.0 - np.arange(1, 5) * 2.0)
    m = make_result(trades, equity).metrics
    assert m["profit_factor"] == pytest.approx(0.0)
    assert m["win_rate"] == pytest.approx(0.0)
    assert m["net_profit"] < 0


# --------------------------------------------------------------------------
# Reliability
# --------------------------------------------------------------------------

def test_small_samples_are_flagged():
    trades = [make_trade(1.0 if i % 2 else -1.0, i) for i in range(10)]
    equity = [100_000.0] * 11
    reliability = make_result(trades, equity).metrics["reliability"]
    flagged = [k for k, v in reliability.items() if v in ("low_sample", "unavailable")]
    assert flagged, "ten trades should flag at least one ratio metric"
    assert reliability.get("profit_factor") in ("low_sample", "unavailable")


def test_large_samples_are_not_all_flagged():
    rng = np.random.default_rng(3)
    pnls = rng.normal(1.0, 5.0, 200)
    trades = [make_trade(float(p), i) for i, p in enumerate(pnls)]
    equity = [100_000.0] + list(100_000.0 + np.cumsum(pnls))
    reliability = make_result(trades, equity).metrics["reliability"]
    assert reliability.get("profit_factor") == "ok"


def test_reliability_notes_explain_themselves():
    trades = [make_trade(1.0, 0)]
    m = make_result(trades, [100_000.0, 100_001.0]).metrics
    notes = m.get("reliability_notes", {})
    assert isinstance(notes, dict)
    for key, state in m["reliability"].items():
        if state != "ok":
            assert key in notes and notes[key], key


# --------------------------------------------------------------------------
# Period returns
# --------------------------------------------------------------------------

def test_monthly_returns_shape():
    import pandas as pd

    n = 24 * 400            # a bit over a year of hourly bars
    ts = START_NS + np.arange(n, dtype="int64") * HOUR_NS
    equity = 100_000.0 + np.linspace(0, 20_000.0, n)
    curves = build_curves(ts, equity, equity, np.zeros(n))
    result = BacktestResult(config=BacktestConfig(starting_capital=100_000.0),
                            curves=curves, timeframe_label="1h")
    monthly = monthly_returns(result)
    assert monthly["years"]
    assert len(monthly["months"]) == len(monthly["years"])
    assert all(len(row) == 12 for row in monthly["months"])
    # A monotonically rising curve cannot have a negative month.
    values = [v for row in monthly["months"] for v in row
              if v is not None and v == v]
    assert values and min(values) >= -1e-9


def test_yearly_returns():
    n = 24 * 800
    ts = START_NS + np.arange(n, dtype="int64") * HOUR_NS
    equity = 100_000.0 + np.linspace(0, 30_000.0, n)
    curves = build_curves(ts, equity, equity, np.zeros(n))
    result = BacktestResult(config=BacktestConfig(starting_capital=100_000.0),
                            curves=curves, timeframe_label="1h")
    yearly = yearly_returns(result)
    assert yearly


def test_periodic_returns_on_a_short_run_do_not_raise():
    result = make_result([], [100_000.0, 100_001.0, 100_002.0])
    monthly_returns(result)
    yearly_returns(result)


# --------------------------------------------------------------------------
# Sign conventions
#
# These are the conventions the UI and the reports are written against. They are
# both defensible; what matters is that they do not silently change, because a
# drawdown that flips sign turns a red number green.
# --------------------------------------------------------------------------

def test_drawdown_sign_conventions():
    """Curves carry signed drawdown; metrics carry positive magnitudes."""
    result = make_result([], [100_000.0, 110_000.0, 90_000.0, 95_000.0])
    curves = result.curves
    assert curves.drawdown.min() < 0, "curve drawdown must be signed"
    assert curves.drawdown_pct.min() < 0, "curve drawdown_pct must be signed"

    m = result.metrics
    assert m["max_drawdown"] >= 0, "metric max_drawdown is a magnitude"
    assert m["max_drawdown_pct"] >= 0, "metric max_drawdown_pct is a magnitude"
    # 110,000 -> 90,000 is 20,000, or 18.1818% of the peak.
    assert m["max_drawdown"] == pytest.approx(20_000.0)
    assert m["max_drawdown_pct"] == pytest.approx(20_000.0 / 110_000.0 * 100.0)


def test_gross_loss_is_negative_and_gross_profit_positive():
    trades = [make_trade(10.0, 0), make_trade(-5.0, 1)]
    m = make_result(trades, [100_000.0, 100_010.0, 100_005.0]).metrics
    assert m["gross_profit"] > 0
    assert m["gross_loss"] < 0
    assert m["largest_loss"] <= 0
    assert m["avg_loss"] <= 0


def test_percentages_are_percentages_not_fractions():
    """18.18 means 18.18%, never 0.1818."""
    trades = [make_trade(1000.0, 0)]
    m = make_result(trades, [100_000.0, 101_000.0]).metrics
    assert m["return_pct"] == pytest.approx(1.0)      # 1%, not 0.01
    assert 0.0 <= m["win_rate"] <= 100.0
    assert 0.0 <= m["exposure_pct"] <= 100.0


def test_costs_are_reported_as_positive_amounts_paid():
    trades = [make_trade(10.0, 0)]
    trades[0].commission = 2.0
    trades[0].slippage_cost = 1.0
    trades[0].spread_cost = 0.5
    m = make_result(trades, [100_000.0, 100_010.0]).metrics
    assert m["total_commission"] == pytest.approx(2.0)
    assert m["total_slippage"] == pytest.approx(1.0)
    assert m["total_spread_cost"] == pytest.approx(0.5)
    assert m["total_costs"] == pytest.approx(3.5)


def test_every_documented_metric_key_is_present():
    """The stats panel and the reports index these by name."""
    required = {
        "net_profit", "gross_profit", "gross_loss", "return_pct",
        "starting_balance", "ending_balance", "total_trades", "winning_trades",
        "losing_trades", "win_rate", "avg_trade", "avg_win", "avg_loss",
        "largest_win", "largest_loss", "profit_factor", "expectancy",
        "expectancy_r", "payoff_ratio", "max_drawdown", "max_drawdown_pct",
        "max_drawdown_duration_bars", "recovery_factor", "sharpe_ratio",
        "sortino_ratio", "calmar_ratio", "cagr", "annual_volatility_pct",
        "ulcer_index", "avg_trade_duration_seconds", "max_consecutive_wins",
        "max_consecutive_losses", "avg_bars_held", "total_commission",
        "total_slippage", "total_spread_cost", "total_costs", "exposure_pct",
        "long_trades", "short_trades", "long_win_rate", "short_win_rate",
        "long_net_profit", "short_net_profit", "avg_mae", "avg_mfe",
        "avg_r_multiple", "std_r_multiple", "sqn", "kelly_fraction",
        "trades_per_year", "exit_reason_breakdown", "reliability",
    }
    trades = [make_trade(float(i - 2), i) for i in range(5)]
    m = make_result(trades, [100_000.0] * 6).metrics
    missing = sorted(required - set(m))
    assert not missing, f"metrics missing: {missing}"


def test_no_metric_is_nan():
    """A NaN anywhere in the dictionary renders as a blank cell nobody can read."""
    import math as _math

    for trades, equity in (
        ([], [100_000.0] * 10),
        ([make_trade(5.0, 0)], [100_000.0, 100_005.0]),
        ([make_trade(-5.0, i) for i in range(3)], [100_000.0] * 4),
    ):
        m = make_result(trades, equity).metrics
        bad = [k for k, v in m.items()
               if isinstance(v, float) and _math.isnan(v)]
        assert not bad, f"NaN metrics: {bad}"
