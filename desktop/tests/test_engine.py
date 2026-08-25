"""Order simulation and P&L.

Every scenario here is small enough to check on paper, and each one pins down a
rule from the module docstring of :mod:`tradingbacktester.engine.backtester`.
These are the tests that decide whether the numbers this application prints mean
anything.
"""

from __future__ import annotations

import numpy as np
import pytest

from tradingbacktester.core.types import (BacktestConfig, CommissionMode,
                                          CostModel, ExecutionSettings,
                                          ExitReason, ExitSettings,
                                          IntrabarPriority, RiskSettings,
                                          SignalExecution, SizingMode,
                                          SlippageMode, SpreadMode, Side)
from tradingbacktester.engine.backtester import Backtester
from tradingbacktester.indicators.base import ParamSpec
from tradingbacktester.strategy.spec import (Always, Compare, Const, Cross,
                                             Group, Ind, IndicatorSlot, Price,
                                             StrategySpec)

from .conftest import make_bars


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def price_rule_strategy(entry_level: float, exit_level: float,
                        name: str = "Level") -> StrategySpec:
    """Long when close > entry_level; exit when close < exit_level.

    Deliberately trivial so the *engine's* behaviour, not the rule's, is what a
    failing assertion points at.
    """
    spec = StrategySpec(name=name)
    spec.entry_long = Compare(Price("close"), ">", Const(entry_level))
    spec.exit_long = Compare(Price("close"), "<", Const(exit_level))
    return spec


def one_shot_long() -> StrategySpec:
    """Enter long on exactly one bar and never exit by signal."""
    spec = StrategySpec(name="One shot")
    spec.entry_long = Compare(Price("close"), ">", Const(1e12))   # never
    return spec


#: Bars of padding prepended to every hand-built scenario.  The compiler will
#: not signal until it has a previous bar to look at, and a signal fills on the
#: bar after it, so a four-bar scenario has no room for anything to happen.
PAD = 4


def pad(values: list[float], first: float | None = None) -> list[float]:
    """Prepend ``PAD`` copies of ``first`` (default: the first value)."""
    head = values[0] if first is None else first
    return [head] * PAD + list(values)


def basic_config(**kwargs) -> BacktestConfig:
    config = BacktestConfig(starting_capital=100_000.0)
    config.risk = RiskSettings(starting_capital=100_000.0,
                               sizing_mode=SizingMode.FIXED_UNITS,
                               fixed_units=kwargs.pop("units", 1.0))
    config.costs = CostModel()
    config.execution = ExecutionSettings()
    config.exits = ExitSettings()
    for key, value in kwargs.items():
        setattr(config, key, value)
    return config


def run(bars, spec, config) -> "object":
    return Backtester(bars, spec, config).run()


# --------------------------------------------------------------------------
# 1. The arithmetic
# --------------------------------------------------------------------------

def test_single_long_trade_pnl_is_exact(simple_instrument):
    """Entry at 100, exit at 110, 2 units, point value 1, $1/side commission.

    Gross 20, commission 2, net 18, and the account ends 18 up.
    """
    # Flat at 100, then the rule turns on; the fill is the next bar's open.
    closes = pad([100, 100, 105, 108, 110, 90, 90, 90], first=99.0)
    bars = make_bars(closes, instrument=simple_instrument)
    spec = StrategySpec(name="Exact")
    spec.entry_long = Compare(Price("close"), ">=", Const(100))
    spec.exit_long = Compare(Price("close"), "<", Const(100))

    config = basic_config(units=2.0)
    config.costs = CostModel(commission_mode=CommissionMode.PER_TRADE,
                             commission_value=1.0)
    result = run(bars, spec, config)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_price == pytest.approx(100.0)
    assert trade.quantity == pytest.approx(2.0)
    assert trade.entry_bar == PAD + 1
    assert trade.gross_pnl == pytest.approx((trade.exit_price - 100.0) * 2.0)
    assert trade.commission == pytest.approx(2.0)      # one dollar each side
    assert trade.net_pnl == pytest.approx(trade.gross_pnl - 2.0)
    assert result.curves.equity[-1] == pytest.approx(100_000.0 + trade.net_pnl)


def test_point_value_multiplies_pnl(futures_instrument):
    """The same price move on an NQ contract is worth twenty times as much."""
    closes = pad([100, 100, 105, 110, 90, 90], first=99.0)
    spec = StrategySpec(name="PV")
    spec.entry_long = Compare(Price("close"), ">=", Const(100))
    spec.exit_long = Compare(Price("close"), "<", Const(100))

    plain = run(make_bars(closes), spec, basic_config(units=1.0))
    futures = run(make_bars(closes, instrument=futures_instrument), spec,
                  basic_config(units=1.0))
    assert futures.trades[0].gross_pnl == pytest.approx(
        plain.trades[0].gross_pnl * 20.0)


def test_short_trade_pnl_has_the_right_sign(simple_instrument):
    """A short that covers lower profits; one that covers higher loses."""
    # Enter short at 100, cover at 90.
    closes = pad([100, 100, 95, 90, 90, 90], first=101.0)
    bars = make_bars(closes, instrument=simple_instrument)
    spec = StrategySpec(name="Short")
    spec.entry_short = Compare(Price("close"), "<=", Const(100))
    spec.exit_short = Compare(Price("close"), "<", Const(92))
    config = basic_config(units=1.0)
    config.risk.allow_short = True
    config.risk.allow_long = False
    winner = run(bars, spec, config).trades[0]
    assert winner.side is Side.SHORT
    assert winner.exit_price < winner.entry_price
    assert winner.gross_pnl > 0
    assert winner.gross_pnl == pytest.approx(
        (winner.entry_price - winner.exit_price) * winner.quantity)

    # Enter short at 100, forced to cover at 110.
    closes = pad([100, 100, 105, 110, 110, 110], first=101.0)
    bars = make_bars(closes, instrument=simple_instrument)
    spec.exit_short = Compare(Price("close"), ">", Const(108))
    loser = run(bars, spec, config).trades[0]
    assert loser.exit_price > loser.entry_price
    assert loser.gross_pnl < 0
    assert loser.gross_pnl == pytest.approx(
        (loser.entry_price - loser.exit_price) * loser.quantity)


def test_equity_equals_capital_plus_cumulative_net_pnl_when_flat(random_bars):
    spec = price_rule_strategy(100.0, 99.0)
    config = basic_config(units=1.0)
    result = run(random_bars, spec, config)
    total = sum(t.net_pnl for t in result.trades)
    assert result.curves.equity[-1] == pytest.approx(100_000.0 + total, abs=1e-6)


# --------------------------------------------------------------------------
# 2. No look-ahead
# --------------------------------------------------------------------------

def test_signal_on_a_close_fills_at_the_next_open(simple_instrument):
    """The central anti-look-ahead rule."""
    opens = pad([100, 101, 102, 103, 104, 105], first=100.0)
    closes = pad([100, 101, 102, 103, 104, 90], first=100.0)
    bars = make_bars(closes, opens=opens, instrument=simple_instrument)
    spec = StrategySpec(name="Timing")
    spec.entry_long = Compare(Price("close"), ">=", Const(101))
    spec.exit_long = Compare(Price("close"), "<", Const(95))

    result = run(bars, spec, basic_config(units=1.0))
    trade = result.trades[0]
    # The rule first holds where close is 101; the fill is the NEXT bar's open.
    signal_bar = PAD + 1
    assert trade.entry_bar == signal_bar + 1
    assert trade.entry_price == pytest.approx(opens[signal_bar + 1])
    assert trade.entry_price == pytest.approx(102.0)


def test_this_close_execution_fills_on_the_signal_bar(simple_instrument):
    opens = pad([100, 101, 102, 103, 104, 105], first=100.0)
    closes = pad([100, 101, 102, 103, 104, 90], first=100.0)
    bars = make_bars(closes, opens=opens, instrument=simple_instrument)
    spec = StrategySpec(name="Timing")
    spec.entry_long = Compare(Price("close"), ">=", Const(101))
    spec.exit_long = Compare(Price("close"), "<", Const(95))

    config = basic_config(units=1.0)
    config.execution = ExecutionSettings(signal_execution=SignalExecution.THIS_CLOSE)
    result = run(bars, spec, config)
    trade = result.trades[0]
    signal_bar = PAD + 1
    assert trade.entry_bar == signal_bar
    assert trade.entry_price == pytest.approx(101.0)


def test_truncating_the_data_does_not_change_earlier_trades(random_bars):
    """The whole-engine look-ahead test.

    Trades taken in the first half must be identical whether or not the second
    half of the data exists.
    """
    spec = price_rule_strategy(101.0, 99.0)
    config = basic_config(units=1.0)
    cut = 300

    full = run(random_bars, spec, config)
    part = run(random_bars.slice(0, cut), spec, config)

    common = [t for t in full.trades if t.exit_bar < cut - 2]
    assert common, "the scenario produced no comparable trades"
    for a, b in zip(common, part.trades):
        assert a.entry_bar == b.entry_bar
        assert a.entry_price == pytest.approx(b.entry_price)
        assert a.exit_bar == b.exit_bar
        assert a.net_pnl == pytest.approx(b.net_pnl)


# --------------------------------------------------------------------------
# 3. Stops, targets and gaps
# --------------------------------------------------------------------------

def _stop_scenario(gap_open: float, instrument):
    """Long entered at the open of bar 1 (=100), stop 1 point below."""
    opens = pad([100, 100, gap_open, 100, 100], first=100.0)
    closes = pad([100, 100, gap_open, 100, 100], first=100.0)
    highs = pad([101, 101, max(gap_open, 100), 101, 101], first=101.0)
    lows = pad([99.5, 99.5, min(gap_open, 99.5), 99.5, 99.5], first=99.5)
    bars = make_bars(closes, highs, lows, opens, instrument=instrument)
    spec = StrategySpec(name="Stop")
    spec.entry_long = Compare(Price("close"), ">=", Const(100))
    config = basic_config(units=1.0)
    config.exits = ExitSettings(stop_loss_enabled=True, stop_loss_mode="points",
                                stop_loss_value=1.0)
    config.risk.max_concurrent_positions = 1
    return bars, spec, config


def test_a_gap_through_the_stop_fills_at_the_open(simple_instrument):
    """The difference between an honest backtest and a flattering one."""
    bars, spec, config = _stop_scenario(95.0, simple_instrument)
    result = run(bars, spec, config)
    stopped = [t for t in result.trades if t.exit_reason is ExitReason.STOP_LOSS]
    assert stopped, "the stop did not trigger"
    # The stop sat at 99; the bar opened at 95, so 95 is what was obtainable.
    assert stopped[0].exit_price == pytest.approx(95.0)
    assert stopped[0].exit_price != pytest.approx(99.0)


def test_a_stop_touched_intrabar_fills_at_the_stop(simple_instrument):
    opens = pad([100, 100, 100, 100], first=100.0)
    closes = pad([100, 100, 100, 100], first=100.0)
    highs = pad([101, 101, 101, 101], first=101.0)
    # The third bar of the unpadded section dips through the stop at 99.
    lows = pad([99.5, 99.5, 98.0, 99.5], first=99.5)
    bars = make_bars(closes, highs, lows, opens, instrument=simple_instrument)
    spec = StrategySpec(name="Stop")
    spec.entry_long = Compare(Price("close"), ">=", Const(100))
    config = basic_config(units=1.0)
    config.exits = ExitSettings(stop_loss_enabled=True, stop_loss_mode="points",
                                stop_loss_value=1.0)
    result = run(bars, spec, config)
    stopped = [t for t in result.trades if t.exit_reason is ExitReason.STOP_LOSS]
    assert stopped
    assert stopped[0].exit_price == pytest.approx(99.0)


def _both_barriers_scenario(priority: IntrabarPriority, instrument):
    """One bar whose range covers both a 1-point stop and a 2-point target."""
    opens = pad([100, 100, 100, 100], first=100.0)
    closes = pad([100, 100, 100.5, 100], first=100.0)
    highs = pad([100.2, 100.2, 103.0, 100.2], first=100.2)
    lows = pad([99.9, 99.9, 98.0, 99.9], first=99.9)
    bars = make_bars(closes, highs, lows, opens, instrument=instrument)
    spec = StrategySpec(name="Both")
    spec.entry_long = Compare(Price("close"), ">=", Const(100))
    config = basic_config(units=1.0)
    config.exits = ExitSettings(stop_loss_enabled=True, stop_loss_mode="points",
                                stop_loss_value=1.0,
                                take_profit_enabled=True,
                                take_profit_mode="points", take_profit_value=2.0)
    config.execution = ExecutionSettings(intrabar_priority=priority)
    return bars, spec, config


def test_both_barriers_pessimistic_takes_the_stop(simple_instrument):
    bars, spec, config = _both_barriers_scenario(IntrabarPriority.PESSIMISTIC,
                                                 simple_instrument)
    result = run(bars, spec, config)
    assert result.trades[0].exit_reason is ExitReason.STOP_LOSS


def test_both_barriers_optimistic_takes_the_target(simple_instrument):
    bars, spec, config = _both_barriers_scenario(IntrabarPriority.OPTIMISTIC,
                                                 simple_instrument)
    result = run(bars, spec, config)
    assert result.trades[0].exit_reason is ExitReason.TAKE_PROFIT


def test_pessimistic_never_beats_optimistic(random_bars):
    """Whatever the data, the conservative assumption cannot earn more."""
    spec = price_rule_strategy(100.0, 95.0)
    base = basic_config(units=1.0)
    base.exits = ExitSettings(stop_loss_enabled=True, stop_loss_mode="atr",
                              stop_loss_value=1.0, take_profit_enabled=True,
                              take_profit_mode="atr", take_profit_value=2.0)

    base.execution = ExecutionSettings(intrabar_priority=IntrabarPriority.PESSIMISTIC)
    pessimistic = run(random_bars, spec, base)
    base.execution = ExecutionSettings(intrabar_priority=IntrabarPriority.OPTIMISTIC)
    optimistic = run(random_bars, spec, base)

    assert pessimistic.curves.equity[-1] <= optimistic.curves.equity[-1] + 1e-6


def test_take_profit_triggers(simple_instrument):
    opens = pad([100, 100, 100, 100], first=100.0)
    closes = pad([100, 100, 102, 100], first=100.0)
    highs = pad([100.2, 100.2, 103.0, 100.2], first=100.2)
    lows = pad([99.9, 99.9, 99.8, 99.9], first=99.9)
    bars = make_bars(closes, highs, lows, opens, instrument=simple_instrument)
    spec = StrategySpec(name="TP")
    spec.entry_long = Compare(Price("close"), ">=", Const(100))
    config = basic_config(units=1.0)
    config.exits = ExitSettings(take_profit_enabled=True,
                                take_profit_mode="points", take_profit_value=2.0)
    result = run(bars, spec, config)
    assert result.trades[0].exit_reason is ExitReason.TAKE_PROFIT
    assert result.trades[0].exit_price == pytest.approx(102.0)


def test_time_stop_closes_the_position(random_bars):
    spec = price_rule_strategy(100.0, -1e9)      # never exits by signal
    config = basic_config(units=1.0)
    config.exits = ExitSettings(max_bars_in_trade=5)
    result = run(random_bars, spec, config)
    timed = [t for t in result.trades if t.exit_reason is ExitReason.TIME_STOP]
    assert timed
    assert all(t.bars_held <= 6 for t in timed)


# --------------------------------------------------------------------------
# 4. Costs
# --------------------------------------------------------------------------

def test_commission_reduces_net_profit_by_exactly_the_charge(simple_instrument):
    closes = pad([100, 100, 105, 110, 90, 90], first=99.0)
    bars = make_bars(closes, instrument=simple_instrument)
    spec = StrategySpec(name="Cost")
    spec.entry_long = Compare(Price("close"), ">=", Const(100))
    spec.exit_long = Compare(Price("close"), "<", Const(100))

    free = run(bars, spec, basic_config(units=3.0))
    config = basic_config(units=3.0)
    config.costs = CostModel(commission_mode=CommissionMode.PER_UNIT,
                             commission_value=0.5)
    charged = run(bars, spec, config)

    # 3 units x $0.50 x two sides = $3.00.
    assert charged.trades[0].commission == pytest.approx(3.0)
    assert charged.trades[0].net_pnl == pytest.approx(
        free.trades[0].net_pnl - 3.0)


def test_slippage_is_always_adverse(random_bars):
    spec = price_rule_strategy(100.0, 99.0)
    clean = run(random_bars, spec, basic_config(units=1.0))
    config = basic_config(units=1.0)
    config.costs = CostModel(slippage_mode=SlippageMode.FIXED_POINTS,
                             slippage_value=0.05)
    slipped = run(random_bars, spec, config)
    assert slipped.curves.equity[-1] < clean.curves.equity[-1]
    assert all(t.slippage_cost >= 0 for t in slipped.trades)


def test_spread_is_always_adverse(random_bars):
    spec = price_rule_strategy(100.0, 99.0)
    clean = run(random_bars, spec, basic_config(units=1.0))
    config = basic_config(units=1.0)
    config.costs = CostModel(spread_mode=SpreadMode.HALF_EACH_SIDE,
                             spread_points=0.10)
    charged = run(random_bars, spec, config)
    assert charged.curves.equity[-1] < clean.curves.equity[-1]
    assert all(t.spread_cost >= 0 for t in charged.trades)


def test_costs_can_never_pay_the_account(random_bars):
    """No configuration of the cost model may increase equity."""
    spec = price_rule_strategy(100.0, 99.0)
    clean = run(random_bars, spec, basic_config(units=1.0))
    for costs in (
        CostModel(commission_mode=CommissionMode.PER_UNIT, commission_value=0.1),
        CostModel(commission_mode=CommissionMode.PER_TRADE, commission_value=1.0),
        CostModel(commission_mode=CommissionMode.PERCENT_NOTIONAL,
                  commission_value=0.01),
        CostModel(spread_mode=SpreadMode.FULL_ON_ENTRY, spread_points=0.05),
        CostModel(slippage_mode=SlippageMode.PERCENT, slippage_value=0.01),
        CostModel(slippage_mode=SlippageMode.ATR_FRACTION, slippage_value=0.1),
    ):
        config = basic_config(units=1.0)
        config.costs = costs
        charged = run(random_bars, spec, config)
        assert charged.curves.equity[-1] <= clean.curves.equity[-1] + 1e-9


# --------------------------------------------------------------------------
# 5. Sizing and risk
# --------------------------------------------------------------------------

def test_risk_percent_sizing_risks_the_stated_amount(simple_instrument):
    """1% of 100,000 with a 2-point stop and point value 1 is 500 units."""
    closes = [100.0] * 12
    highs = [101.0] * 12
    lows = [99.0] * 12  # noqa: E501 -- long enough for the warm-up already
    bars = make_bars(closes, highs, lows, closes, instrument=simple_instrument)
    spec = StrategySpec(name="Risk")
    spec.entry_long = Compare(Price("close"), ">=", Const(100))

    config = basic_config()
    config.risk = RiskSettings(starting_capital=100_000.0,
                               sizing_mode=SizingMode.RISK_PERCENT,
                               risk_percent=1.0)
    config.exits = ExitSettings(stop_loss_enabled=True, stop_loss_mode="points",
                                stop_loss_value=2.0)
    result = run(bars, spec, config)
    assert result.trades or result.orders
    quantity = (result.trades[0].quantity if result.trades
                else result.orders[0].quantity)
    assert quantity == pytest.approx(500.0, rel=0.02)


def test_max_position_units_caps_the_size(simple_instrument):
    closes = [100.0] * 12
    bars = make_bars(closes, instrument=simple_instrument)
    spec = StrategySpec(name="Cap")
    spec.entry_long = Compare(Price("close"), ">=", Const(100))
    config = basic_config()
    config.risk = RiskSettings(starting_capital=100_000.0,
                               sizing_mode=SizingMode.PERCENT_EQUITY,
                               percent_equity=100.0, max_position_units=10.0)
    result = run(bars, spec, config)
    for trade in result.trades:
        assert trade.quantity <= 10.0 + 1e-9


def test_shorts_are_refused_when_disallowed(random_bars):
    spec = StrategySpec(name="NoShort")
    spec.entry_short = Compare(Price("close"), ">", Const(0))
    spec.exit_short = Compare(Price("close"), "<", Const(0))
    config = basic_config(units=1.0)
    config.risk.allow_short = False
    config.risk.allow_long = True
    result = run(random_bars, spec, config)
    assert not [t for t in result.trades if t.side.value == "short"]


def test_max_concurrent_positions_is_respected(random_bars):
    spec = price_rule_strategy(0.0, -1e9)      # always wants to be long
    config = basic_config(units=1.0)
    config.risk.max_concurrent_positions = 1
    result = run(random_bars, spec, config)
    # With a cap of one, no two trades may overlap in time.
    ordered = sorted(result.trades, key=lambda t: t.entry_bar)
    for a, b in zip(ordered, ordered[1:]):
        assert b.entry_bar >= a.exit_bar


# --------------------------------------------------------------------------
# 6. Bookkeeping
# --------------------------------------------------------------------------

def test_open_positions_are_closed_at_the_end_of_the_data(random_bars):
    spec = price_rule_strategy(0.0, -1e9)      # enters and never exits
    result = run(random_bars, spec, basic_config(units=1.0))
    assert result.trades
    assert result.trades[-1].exit_reason is ExitReason.END_OF_DATA
    assert result.trades[-1].exit_bar == len(random_bars) - 1


def test_mae_and_mfe_are_non_negative(random_bars):
    spec = price_rule_strategy(100.0, 99.0)
    result = run(random_bars, spec, basic_config(units=1.0))
    assert result.trades
    for trade in result.trades:
        assert trade.mae >= 0.0
        assert trade.mfe >= 0.0


def test_curves_have_one_point_per_bar(random_bars):
    spec = price_rule_strategy(100.0, 99.0)
    result = run(random_bars, spec, basic_config(units=1.0))
    assert len(result.curves) == len(random_bars)
    assert np.array_equal(result.curves.ts, random_bars.ts)
    assert (result.curves.drawdown <= 1e-9).all()
    assert (result.curves.drawdown_pct <= 1e-9).all()


def test_metrics_are_produced(random_bars):
    spec = price_rule_strategy(100.0, 99.0)
    result = run(random_bars, spec, basic_config(units=1.0))
    for key in ("net_profit", "total_trades", "win_rate", "profit_factor",
                "max_drawdown_pct", "sharpe_ratio", "reliability"):
        assert key in result.metrics, key
    assert result.metrics["total_trades"] == len(result.trades)


def test_a_strategy_that_never_fires_produces_no_trades(random_bars):
    spec = StrategySpec(name="Never")
    spec.entry_long = Compare(Price("close"), ">", Const(1e12))
    result = run(random_bars, spec, basic_config(units=1.0))
    assert result.trades == []
    assert result.metrics["total_trades"] == 0
    assert result.curves.equity[-1] == pytest.approx(100_000.0)


def test_warmup_prevents_trading_before_indicators_are_ready(random_bars):
    spec = StrategySpec(name="Warm")
    spec.indicators = [IndicatorSlot("sma", "SMA", {"period": 50})]
    spec.entry_long = Compare(Price("close"), ">", Ind("sma"))
    spec.exit_long = Compare(Price("close"), "<", Ind("sma"))
    config = basic_config(units=1.0)
    config.warmup_bars = spec.warmup_bars()
    result = run(random_bars, spec, config)
    assert result.trades
    assert min(t.entry_bar for t in result.trades) >= 50
