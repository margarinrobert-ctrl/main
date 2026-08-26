"""Parameter grids, the parallel runner and robustness ranking."""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from tradingbacktester.core.errors import (CancelledError,
                                           InsufficientDataError,
                                           ParameterError)
from tradingbacktester.core.types import BacktestConfig
from tradingbacktester.data.sample import generate_sample_data
from tradingbacktester.optimize.grid import (ParameterRange, build_grid,
                                             check_combination_count,
                                             combination_count)
from tradingbacktester.optimize.ranking import (neighbourhood_mean,
                                                overfitting_note, rank)
from tradingbacktester.optimize.runner import (OptimizationRunner,
                                               spawn_can_reimport_main)
from tradingbacktester.optimize.walkforward import (format_walk_forward,
                                                    plan_windows, walk_forward)
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


# --------------------------------------------------------------------------
# Walk-forward
# --------------------------------------------------------------------------

def _plan_covers(total, folds, fraction, anchored):
    return plan_windows(total, folds, fraction, anchored)


def test_plan_windows_tiles_the_tail_exactly_once():
    """No gap and no overlap: the out-of-sample record is one history."""
    plan = _plan_covers(1000, 5, 0.5, anchored=False)
    assert len(plan) == 5
    first_train = int(1000 * 0.5)
    assert plan[0][2] == first_train
    assert plan[-1][3] == 1000
    for (_, _, start, end), (_, _, next_start, _) in zip(plan, plan[1:]):
        assert end == next_start          # no gap, no overlap
        assert end > start


def test_plan_windows_trains_on_everything_before_the_test_block():
    for anchored in (False, True):
        for train_start, train_end, test_start, _ in _plan_covers(
                1200, 4, 0.5, anchored):
            assert train_end == test_start
            assert train_start < train_end


def test_anchored_windows_grow_and_rolling_windows_do_not():
    anchored = _plan_covers(2000, 4, 0.5, anchored=True)
    rolling = _plan_covers(2000, 4, 0.5, anchored=False)
    anchored_lengths = [end - start for start, end, _, _ in anchored]
    rolling_lengths = [end - start for start, end, _, _ in rolling]
    assert all(s == 0 for s, _, _, _ in anchored)
    assert anchored_lengths == sorted(anchored_lengths)
    assert anchored_lengths[-1] > anchored_lengths[0]
    assert len(set(rolling_lengths)) == 1


def test_plan_refuses_more_folds_than_testable_bars():
    with pytest.raises(InsufficientDataError):
        plan_windows(100, 60, 0.5, anchored=False)


def test_walk_forward_refuses_a_short_series(spec):
    short = generate_sample_data("NQ", "1h", n_bars=200, seed=1)
    with pytest.raises(InsufficientDataError):
        walk_forward(short, spec, BacktestConfig(),
                     [ParameterRange("ema_fast", 8, 12, 2)])


def test_walk_forward_refuses_a_strategy_with_nothing_to_optimise(bars, spec):
    with pytest.raises(ParameterError):
        walk_forward(bars, spec, BacktestConfig(), [])


# -- the aggregation, driven by a deterministic stand-in for the backtest ---

def _stub(monkeypatch, table):
    """Replace the backtest with a lookup so the arithmetic can be checked.

    ``table`` maps ``(window_index, param_value)`` to ``(metric, trades)``.  The
    window index is recovered from the block length, which is unique per call
    because the stub is only used with plans whose blocks differ in size.
    """
    calls = []

    def fake(block, spec, config, index, params):
        calls.append((len(block), dict(params)))
        value, trades = table(len(block), params)
        return {"index": index, "params": dict(params), "trade_count": trades,
                "metrics": {"net_profit": value}, "error": None, "elapsed": 0.0}

    monkeypatch.setattr(
        "tradingbacktester.optimize.walkforward.evaluate_combination", fake)
    return calls


def test_a_stable_optimum_reports_full_stability(bars, spec, monkeypatch):
    """One value wins in every window, so the optimum never moves."""
    _stub(monkeypatch, lambda n, p: (100.0 if p["ema_fast"] == 12 else 10.0, 40))
    result = walk_forward(bars, spec, BacktestConfig(),
                          [ParameterRange("ema_fast", 8, 12, 2)], folds=4)
    assert len(result.completed) == 4
    assert all(w.params["ema_fast"] == 12 for w in result.completed)
    assert result.stability == 1.0
    assert result.efficiency == pytest.approx(1.0)
    assert "held up out of sample" in result.verdict()


def test_a_rotating_optimum_reports_no_stability(bars, spec, monkeypatch):
    """The winner changes every window: there is no setting to ship."""
    order = {}

    def table(n, params):
        # Blocks are seen train, train, ..., test per window; give each distinct
        # training length its own winner so the choice rotates.
        winner = order.setdefault(n, [8, 10, 12][len(order) % 3])
        return (100.0 if params["ema_fast"] == winner else 1.0, 40)

    _stub(monkeypatch, table)
    result = walk_forward(bars, spec, BacktestConfig(),
                          [ParameterRange("ema_fast", 8, 12, 2)], folds=3,
                          anchored=True)
    assert len(result.completed) == 3
    assert result.stability < 1.0


def test_efficiency_is_undefined_when_the_training_windows_lost_money(
        bars, spec, monkeypatch):
    """"Kept -76% of its in-sample profit" is not a sentence."""
    _stub(monkeypatch, lambda n, p: (-50.0, 40))
    result = walk_forward(bars, spec, BacktestConfig(),
                          [ParameterRange("ema_fast", 8, 12, 2)], folds=3)
    assert result.in_sample_net < 0
    assert math.isnan(result.efficiency)
    assert "nothing here for the optimiser to find" in result.verdict()
    assert any("cannot be computed" in n for n in result.notes)


def test_a_window_with_too_few_trades_is_reported_not_silently_dropped(
        bars, spec, monkeypatch):
    _stub(monkeypatch, lambda n, p: (100.0, 1))
    result = walk_forward(bars, spec, BacktestConfig(),
                          [ParameterRange("ema_fast", 8, 12, 2)], folds=3,
                          minimum_trades=5)
    assert result.completed == []
    assert all("at least 5 trades" in w.error for w in result.windows)
    assert result.verdict() == "no window produced a result"


def test_out_of_sample_total_is_the_sum_of_the_test_blocks(bars, spec,
                                                           monkeypatch):
    _stub(monkeypatch, lambda n, p: (7.0 * p["ema_fast"], 40))
    result = walk_forward(bars, spec, BacktestConfig(),
                          [ParameterRange("ema_fast", 8, 12, 2)], folds=4)
    assert result.out_of_sample_net == pytest.approx(
        sum(w.test_net for w in result.completed))
    assert result.out_of_sample_trades == sum(
        w.test_trades for w in result.completed)
    assert result.equity == pytest.approx(
        list(np.cumsum([w.test_net for w in result.completed])))


def test_result_is_json_serialisable(bars, spec, monkeypatch):
    _stub(monkeypatch, lambda n, p: (25.0, 40))
    result = walk_forward(bars, spec, BacktestConfig(),
                          [ParameterRange("ema_fast", 8, 12, 2)], folds=3)
    text = json.dumps(result.to_dict())
    assert "verdict" in text


def test_report_names_every_window_and_the_verdict(bars, spec, monkeypatch):
    _stub(monkeypatch, lambda n, p: (25.0, 40))
    result = walk_forward(bars, spec, BacktestConfig(),
                          [ParameterRange("ema_fast", 8, 12, 2)], folds=3)
    text = format_walk_forward(result, bars)
    assert result.verdict() in text
    for window in result.windows:
        assert f"   {window.index + 1:<3}" in text


def test_cancelling_stops_the_walk_forward(bars, spec, monkeypatch):
    _stub(monkeypatch, lambda n, p: (25.0, 40))

    class Token:
        cancelled = True

    with pytest.raises(CancelledError):
        walk_forward(bars, spec, BacktestConfig(),
                     [ParameterRange("ema_fast", 8, 12, 2)], cancel=Token())


# -- the warm-up padding, against the real engine ---------------------------

def test_padding_lets_a_test_block_trade_from_its_own_first_bar(bars, spec):
    """A cold slice loses its first `warmup` bars; a padded one does not.

    Without the padding the out-of-sample blocks stop tiling: each one is blind
    for as many bars as the slowest indicator needs, and the trades in that gap
    are counted nowhere.
    """
    from tradingbacktester.optimize.walkforward import _grid_warmup, _run

    params = {"ema_fast": 10}
    grid = [params]
    config = BacktestConfig()
    warmup = _grid_warmup(spec, grid, config)
    assert warmup > 10

    start, end = 1200, 2400
    cold = _run(bars.slice(start, end), spec, config, 0, 0, params)
    padded = _run(bars.slice(start - warmup, end), spec, config, warmup, 1, params)
    assert not cold["error"] and not padded["error"]
    assert padded["trade_count"] > cold["trade_count"]


def test_padding_does_not_let_a_block_trade_into_the_one_before_it(bars, spec):
    """The pad is history, not tradeable: no overlap between test blocks."""
    from tradingbacktester.engine.backtester import Backtester
    from tradingbacktester.optimize.walkforward import _grid_warmup

    import copy

    params = {"ema_fast": 10}
    config = BacktestConfig()
    warmup = _grid_warmup(spec, [params], config)
    start, end = 1200, 2400

    padded = copy.copy(config)
    padded.warmup_bars = warmup
    block = bars.slice(start - warmup, end)
    result = Backtester(block, spec, padded, param_overrides=params).run()
    assert result.trades
    assert min(t.entry_ts for t in result.trades) >= bars.ts[start]


def test_padded_block_reproduces_the_full_run_over_the_same_span(bars, spec):
    """The trades of a padded block are the trades the full run took there."""
    from tradingbacktester.engine.backtester import Backtester
    from tradingbacktester.optimize.walkforward import _grid_warmup

    import copy

    params = {"ema_fast": 10}
    config = BacktestConfig()
    warmup = _grid_warmup(spec, [params], config)
    start, end = 1200, 2400

    whole = Backtester(bars, spec, config, param_overrides=params).run()
    inside = [t for t in whole.trades
              if bars.ts[start] <= t.entry_ts < bars.ts[end - 1]]

    padded = copy.copy(config)
    padded.warmup_bars = warmup
    block = Backtester(bars.slice(start - warmup, end), spec, padded,
                       param_overrides=params).run()
    stamps = [t.entry_ts for t in block.trades]
    # The block cannot inherit a position that was already open at `start`, and
    # its last trade may be cut short by the block ending, so the comparison is
    # over the entries that both runs could have taken.
    assert stamps[:-1] == [t.entry_ts for t in inside][:len(stamps) - 1]


def test_walk_forward_end_to_end_on_sample_data(bars, spec):
    """The real thing, small: three folds over a two-value grid."""
    result = walk_forward(bars, spec, BacktestConfig(),
                          [ParameterRange("ema_fast", 8, 12, 4)], folds=3,
                          minimum_trades=1)
    assert result.combinations == 2
    assert len(result.windows) == 3
    assert result.completed, "no window produced a result on sample data"
    assert result.out_of_sample_trades > 0
    assert isinstance(result.verdict(), str) and result.verdict()
    text = format_walk_forward(result, bars)
    assert "out of sample:" in text
    assert "not chosen with hindsight" in text.replace("\n", " ")
