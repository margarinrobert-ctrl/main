"""Stop loss, take profit, breakeven, trail and ATR period as sweep dimensions."""

from __future__ import annotations

import pytest

from tradingbacktester.core.errors import ParameterError
from tradingbacktester.core.types import BacktestConfig
from tradingbacktester.data.sample import generate_sample_data
from tradingbacktester.engine.backtester import Backtester
from tradingbacktester.optimize.grid import ParameterRange, build_grid
from tradingbacktester.optimize.runner import OptimizationRunner
from tradingbacktester.strategy.builtin import BUILTIN_STRATEGIES
from tradingbacktester.strategy.exit_params import (apply_exit_overrides,
                                                    exit_parameters,
                                                    split_overrides)


@pytest.fixture(scope="module")
def bars():
    return generate_sample_data("NQ", "1h", n_bars=2500, seed=11)


def _spec():
    spec = BUILTIN_STRATEGIES["EMA Cross + RSI"]()
    spec.exits.stop_loss_enabled = True
    spec.exits.stop_loss_mode = "atr"
    spec.exits.stop_loss_value = 1.5
    spec.exits.take_profit_enabled = True
    spec.exits.take_profit_mode = "atr"
    spec.exits.take_profit_value = 3.0
    spec.exits.breakeven_at_r = 1.0
    return spec


def test_only_the_exits_in_use_are_offered():
    names = [p.name for p in exit_parameters(_spec().exits)]
    assert names == ["exits.stop_loss_value", "exits.take_profit_value",
                     "exits.breakeven_at_r", "exits.breakeven_offset",
                     "exits.atr_period"]
    plain = BUILTIN_STRATEGIES["EMA Cross + RSI"]()
    plain.exits.stop_loss_enabled = plain.exits.take_profit_enabled = False
    plain.exits.trailing_enabled = False
    plain.exits.breakeven_at_r = 0.0
    plain.exits.max_bars_in_trade = 0
    assert exit_parameters(plain.exits) == []


def test_overrides_split_and_apply_without_touching_the_original():
    spec = _spec()
    params, exits = split_overrides({"ema_fast": 9, "exits.stop_loss_value": 2.5,
                                     "exits.atr_period": 20.0})
    assert params == {"ema_fast": 9}
    changed = apply_exit_overrides(spec.exits, exits)
    assert (changed.stop_loss_value, changed.atr_period) == (2.5, 20)
    assert spec.exits.stop_loss_value == 1.5
    with pytest.raises(ParameterError):
        apply_exit_overrides(spec.exits, {"stop_loss_mode": 1})
    with pytest.raises(ParameterError):
        apply_exit_overrides(spec.exits, {"atr_period": 0})


def test_a_swept_stop_changes_the_trades(bars):
    spec = _spec()
    base = Backtester(bars, spec, BacktestConfig()).run()
    tight = Backtester(bars, spec, BacktestConfig(),
                       param_overrides={"exits.stop_loss_value": 0.5}).run()
    assert spec.exits.stop_loss_value == 1.5          # the strategy is untouched
    risk_base = [abs(t.entry_price - (t.stop_loss or t.entry_price)) for t in base.trades]
    risk_tight = [abs(t.entry_price - (t.stop_loss or t.entry_price)) for t in tight.trades]
    assert sum(risk_tight) / len(risk_tight) < sum(risk_base) / len(risk_base)


def test_the_run_config_gets_the_override_too(bars):
    """The UI passes its own exits in the config; the sweep must win there."""
    spec = _spec()
    config = BacktestConfig()
    config.exits = spec.exits
    a = Backtester(bars, spec, config).run()
    b = Backtester(bars, spec, config,
                   param_overrides={"exits.take_profit_value": 12.0}).run()
    assert config.exits.take_profit_value == 3.0
    assert [t.exit_reason for t in a.trades] != [t.exit_reason for t in b.trades]


def test_grid_and_runner_sweep_exit_settings(bars):
    spec = _spec()
    ranges = [ParameterRange("exits.stop_loss_value", 1.0, 3.0, 1.0),
              ParameterRange("exits.atr_period", 10, 20, 10)]
    grid = build_grid(spec, ranges)
    assert len(grid) == 6 and grid[0] == {"exits.stop_loss_value": 1.0,
                                          "exits.atr_period": 10}
    results = OptimizationRunner(bars, spec, BacktestConfig(), max_workers=1).run(ranges)
    assert all(r.ok for r in results.rows), [r.error for r in results.rows]
    assert len({round(r.value("net_profit"), 6) for r in results.rows}) > 1
    with pytest.raises(ParameterError):
        build_grid(spec, [ParameterRange("exits.nonsense", 1, 2, 1)])


def test_holdout_and_walk_forward_accept_exit_dimensions(bars):
    from tradingbacktester.optimize.holdout import optimise_with_holdout
    from tradingbacktester.optimize.walkforward import walk_forward
    spec = _spec()
    ranges = [ParameterRange("exits.take_profit_value", 2.0, 4.0, 1.0)]
    held = optimise_with_holdout(bars, spec, BacktestConfig(), ranges, reveal=1,
                                 max_workers=1)
    assert held.revealed and "exits.take_profit_value" in held.revealed[0].params
    wf = walk_forward(bars, spec, BacktestConfig(), ranges, folds=2, minimum_trades=1)
    assert any(w.params for w in wf.windows)


def test_cli_optimise_sweeps_an_exit(tmp_path, capsys):
    from tradingbacktester.cli import main
    code = main(["--workspace", str(tmp_path), "optimize", "EMA Cross + RSI",
                 "--data", "US30 30m", "--param", "exits.stop_loss_value=1:2:0.5"])
    assert code == 0
    assert "exits.stop_loss_value" in capsys.readouterr().out


def test_the_optimiser_dialog_lists_exit_rows_unticked(qapp, bars):
    from tradingbacktester.ui.dialogs.optimizer_dialog import OptimizerDialog
    dialog = OptimizerDialog(bars, _spec(), BacktestConfig())
    names = [row["param"].name for row in dialog._rows]
    assert "exits.stop_loss_value" in names and "exits.atr_period" in names
    for row in dialog._rows:
        if row["param"].name.startswith("exits."):
            assert not row["enabled"].isChecked()
    dialog.close()


def test_a_stop_of_zero_is_not_a_sweep_value():
    """0 switches a stop off -- a different strategy, and one Apply cannot set."""
    from tradingbacktester.core.errors import ParameterError
    from tradingbacktester.optimize.grid import ParameterRange, build_grid, suggested_range
    spec = _spec()
    spec.exits.stop_loss_value = 0.5
    with pytest.raises(ParameterError) as exc:
        apply_exit_overrides(spec.exits, {"stop_loss_value": 0})
    assert "switches that exit off" in str(exc.value)
    with pytest.raises(ParameterError):
        build_grid(spec, [ParameterRange("exits.stop_loss_value", 0, 1, 0.5)])
    rows = {p.name: p for p in exit_parameters(spec.exits)}
    suggested = suggested_range(rows["exits.stop_loss_value"])
    assert suggested.start == 0.25 and 0.5 in [round(v, 6) for v in suggested.values()]
    assert rows["exits.atr_period"].maximum <= 500
