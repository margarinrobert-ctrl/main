"""Parameter grids, the parallel runner and robustness ranking."""

from __future__ import annotations

import numpy as np
import pytest

from tradingbacktester.core.errors import ParameterError
from tradingbacktester.core.types import BacktestConfig
from tradingbacktester.data.sample import generate_sample_data
from tradingbacktester.optimize.grid import (ParameterRange, build_grid,
                                             check_combination_count,
                                             combination_count)
from tradingbacktester.optimize.ranking import (neighbourhood_mean,
                                                overfitting_note, rank)
from tradingbacktester.optimize.runner import (OptimizationRunner,
                                               spawn_can_reimport_main)
from tradingbacktester.strategy.builtin import BUILTIN_STRATEGIES


@pytest.fixture(scope="module")
def bars():
    return generate_sample_data("NQ", "1h", n_bars=2500, seed=13)


@pytest.fixture
def spec():
    return BUILTIN_STRATEGIES["EMA Cross + RSI"]()


# --------------------------------------------------------------------------
# Ranges and grids
# --------------------------------------------------------------------------

def test_integer_range_is_inclusive():
    assert ParameterRange("n", 10, 30, 5).values() == [10, 15, 20, 25, 30]


def test_float_range_keeps_its_last_rung():
    """Accumulating by addition drops the endpoint to floating-point drift."""
    values = ParameterRange("x", 0.1, 1.0, 0.1).values()
    assert values[-1] == pytest.approx(1.0)
    assert len(values) == 10


def test_single_value_range():
    assert ParameterRange("n", 5, 5, 1).values() == [5]


def test_combination_count_is_the_product():
    ranges = [ParameterRange("a", 1, 3, 1), ParameterRange("b", 10, 40, 10)]
    assert combination_count(ranges) == 3 * 4


def test_oversized_grid_is_refused_with_the_count(spec):
    ranges = [ParameterRange("ema_fast", 2, 400, 1),
              ParameterRange("ema_slow", 3, 800, 1)]
    with pytest.raises(ParameterError) as exc:
        check_combination_count(ranges, maximum=1000)
    assert "1,000" in str(exc.value) or "1000" in str(exc.value)


def test_grid_validates_against_the_strategy_parameters(spec):
    ranges = [ParameterRange("ema_fast", 10, 20, 5)]
    grid = build_grid(spec, ranges)
    assert len(grid) == 3
    assert all(set(row) == {"ema_fast"} for row in grid)


def test_grid_rejects_an_unknown_parameter(spec):
    with pytest.raises(ParameterError):
        build_grid(spec, [ParameterRange("not_a_parameter", 1, 3, 1)])


def test_grid_rejects_a_value_outside_the_parameter_range(spec):
    # ema_fast has a minimum of 2; zero must be refused up front.
    with pytest.raises(ParameterError):
        build_grid(spec, [ParameterRange("ema_fast", 0, 1, 1)])


# --------------------------------------------------------------------------
# The runner
# --------------------------------------------------------------------------

def test_sweep_completes_and_every_row_has_metrics(bars, spec):
    ranges = [ParameterRange("ema_fast", 10, 20, 5),
              ParameterRange("ema_slow", 40, 60, 20)]
    results = OptimizationRunner(bars, spec, BacktestConfig(), max_workers=2).run(ranges)
    assert results.completed == 6
    assert results.failed == 0
    for row in results.rows:
        assert row.error is None
        assert "net_profit" in row.metrics


def test_sweep_does_not_hang_without_an_importable_main(bars, spec):
    """The bug this test exists for.

    ``spawn`` starts a worker by re-importing ``__main__``.  Under pytest -- and
    under any interactive or embedded interpreter -- that import can fail, and
    the pool then blocks inside ``submit`` forever, leaving the Optimise dialog
    stuck with a dead Cancel button.  The runner must detect this and fall back
    to threads.
    """
    import time

    ranges = [ParameterRange("ema_fast", 10, 25, 5),
              ParameterRange("ema_slow", 40, 70, 10)]
    started = time.monotonic()
    results = OptimizationRunner(bars, spec, BacktestConfig(), max_workers=2).run(ranges)
    elapsed = time.monotonic() - started
    assert results.completed == 16
    assert elapsed < 120, f"the sweep took {elapsed:.0f}s, which suggests a stall"
    if not spawn_can_reimport_main():
        assert not results.used_processes
        assert results.warnings, "a thread fallback must tell the user"


def test_sweep_reports_progress(bars, spec):
    seen: list[tuple[int, int]] = []
    ranges = [ParameterRange("ema_fast", 10, 20, 5)]
    OptimizationRunner(bars, spec, BacktestConfig(), max_workers=1).run(
        ranges, progress=lambda done, total: seen.append((done, total)))
    assert seen
    assert seen[-1][1] == 3


def test_sweep_can_be_cancelled(bars, spec):
    calls = {"n": 0}

    def cancel() -> bool:
        calls["n"] += 1
        return calls["n"] > 2

    ranges = [ParameterRange("ema_fast", 10, 30, 2),
              ParameterRange("ema_slow", 40, 90, 5)]
    results = OptimizationRunner(bars, spec, BacktestConfig(), max_workers=2).run(
        ranges, cancel=cancel)
    assert results.cancelled
    assert results.completed < results.total_combinations


def test_a_failing_combination_does_not_abort_the_sweep(bars, spec):
    """One bad combination must be recorded, not fatal."""
    ranges = [ParameterRange("ema_fast", 10, 20, 5)]
    runner = OptimizationRunner(bars, spec, BacktestConfig(), max_workers=1)
    results = runner.run(ranges)
    assert results.completed + results.failed == 3


# --------------------------------------------------------------------------
# Ranking and robustness
# --------------------------------------------------------------------------

def test_ranking_orders_by_the_chosen_metric(bars, spec):
    ranges = [ParameterRange("ema_fast", 10, 25, 5),
              ParameterRange("ema_slow", 40, 70, 10)]
    results = OptimizationRunner(bars, spec, BacktestConfig(), max_workers=2).run(ranges)
    ranked = rank(results, "net_profit")
    values = [r.metrics.get("net_profit", 0.0) for r in ranked]
    assert values == sorted(values, reverse=True)


def test_ranking_can_filter_by_trade_count(bars, spec):
    ranges = [ParameterRange("ema_fast", 10, 25, 5)]
    results = OptimizationRunner(bars, spec, BacktestConfig(), max_workers=1).run(ranges)
    everything = rank(results, "net_profit", minimum_trades=0)
    filtered = rank(results, "net_profit", minimum_trades=10_000)
    assert len(filtered) <= len(everything)
    assert filtered == []


def test_drawdown_is_ranked_the_right_way_round(bars, spec):
    ranges = [ParameterRange("ema_fast", 10, 25, 5)]
    results = OptimizationRunner(bars, spec, BacktestConfig(), max_workers=1).run(ranges)
    ranked = rank(results, "max_drawdown_pct")
    depths = [abs(r.metrics.get("max_drawdown_pct", 0.0)) for r in ranked]
    assert depths == sorted(depths), "the shallowest drawdown must rank first"


def test_neighbourhood_mean_is_a_number(bars, spec):
    ranges = [ParameterRange("ema_fast", 10, 25, 5),
              ParameterRange("ema_slow", 40, 70, 10)]
    results = OptimizationRunner(bars, spec, BacktestConfig(), max_workers=2).run(ranges)
    ranked = rank(results, "net_profit")
    value = neighbourhood_mean(results, ranked[0], "net_profit")
    assert isinstance(value, float)
    assert np.isfinite(value)


def test_overfitting_note_is_written_and_names_the_count(bars, spec):
    """The warning is a requirement, not decoration."""
    ranges = [ParameterRange("ema_fast", 10, 25, 5),
              ParameterRange("ema_slow", 40, 70, 10)]
    results = OptimizationRunner(bars, spec, BacktestConfig(), max_workers=2).run(ranges)
    note = overfitting_note(results, rank(results, "net_profit"), "net_profit")
    assert isinstance(note, str) and len(note) > 60
    assert "16" in note
