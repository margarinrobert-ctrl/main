"""End-to-end tests: the paths a user actually takes.

Import a CSV, pick a strategy, run it, read the metrics, export the results,
save and reload the run.  These are slower than the unit tests and they are the
ones that catch a layer that changed shape underneath another.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from tradingbacktester.config import Workspace
from tradingbacktester.core.timeframe import Timeframe
from tradingbacktester.core.types import (BacktestConfig, CommissionMode,
                                          CostModel, SizingMode, SlippageMode,
                                          SpreadMode)
from tradingbacktester.data.csv_loader import load_csv, sniff_csv
from tradingbacktester.data.repository import DatasetRepository
from tradingbacktester.data.resample import resample
from tradingbacktester.data.sample import generate_sample_data, write_sample_csv
from tradingbacktester.data.validation import validate_bars
from tradingbacktester.engine.backtester import Backtester
from tradingbacktester.strategy.builtin import BUILTIN_STRATEGIES
from tradingbacktester.strategy.storage import StrategyStore

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def sample_bars():
    return generate_sample_data("NQ", "1h", n_bars=4000, seed=17)


def realistic_config(starting: float = 100_000.0) -> BacktestConfig:
    """Costs a futures trader would actually pay, not a frictionless fantasy."""
    config = BacktestConfig(starting_capital=starting)
    config.risk.sizing_mode = SizingMode.FIXED_UNITS
    config.risk.fixed_units = 1.0
    config.risk.allow_short = True
    config.costs = CostModel(commission_mode=CommissionMode.PER_UNIT,
                             commission_value=2.10,
                             spread_mode=SpreadMode.HALF_EACH_SIDE,
                             spread_points=0.25,
                             slippage_mode=SlippageMode.FIXED_POINTS,
                             slippage_value=0.25)
    return config


# --------------------------------------------------------------------------
# The whole pipeline
# --------------------------------------------------------------------------

def test_csv_to_backtest_to_report(tmp_path, sample_bars):
    """Write a CSV, import it, resample it, run a strategy, export everything."""
    csv_path = tmp_path / "SYNTHETIC_NQ_1h.csv"
    write_sample_csv(csv_path, sample_bars)

    profile = sniff_csv(csv_path)
    assert not profile.problems, profile.problems
    bars = load_csv(csv_path, profile.mapping, sample_bars.instrument)
    assert len(bars) == len(sample_bars)
    assert np.allclose(bars.close, sample_bars.close, atol=1e-6)

    report = validate_bars(bars)
    assert report.is_usable

    four_hour = resample(bars, Timeframe.parse("4h"))
    assert 0 < len(four_hour) < len(bars)

    spec = BUILTIN_STRATEGIES["EMA Cross + RSI"]()
    config = realistic_config()
    config.warmup_bars = spec.warmup_bars()
    result = Backtester(bars, spec, config).run()

    assert result.metrics["total_trades"] == len(result.trades)
    assert len(result.curves) == len(bars)
    assert result.curves.equity[0] == pytest.approx(100_000.0, abs=1.0)

    from tradingbacktester.reports.csv_export import (export_equity_csv,
                                                      export_metrics_csv,
                                                      export_trades_csv)

    trades_csv = Path(export_trades_csv(result, tmp_path / "trades.csv"))
    equity_csv = Path(export_equity_csv(result, tmp_path / "equity.csv"))
    metrics_csv = Path(export_metrics_csv(result, tmp_path / "metrics.csv"))
    for path in (trades_csv, equity_csv, metrics_csv):
        assert path.exists() and path.stat().st_size > 0

    rows = list(csv.reader(
        line for line in trades_csv.read_text(encoding="utf-8-sig").splitlines()
        if not line.startswith("#")))
    assert len(rows) >= 1
    if result.trades:
        assert len(rows) == len(result.trades) + 1     # header plus one per trade

    from tradingbacktester.reports.html_report import export_html_report

    html = Path(export_html_report(result, tmp_path / "report.html"))
    text = html.read_text(encoding="utf-8")
    assert "<html" in text.lower() or "<!doctype" in text.lower()
    assert "http://" not in text and "https://" not in text.replace(
        "http://www.w3.org", "")          # no remote asset may be referenced
    assert "<script src" not in text


def test_every_builtin_runs_on_the_sample_data(sample_bars):
    """No built-in strategy may crash, produce NaN equity, or lose the account."""
    for name, factory in BUILTIN_STRATEGIES.items():
        spec = factory()
        config = realistic_config()
        config.warmup_bars = spec.warmup_bars()
        result = Backtester(sample_bars, spec, config).run()

        assert np.isfinite(result.curves.equity).all(), name
        assert np.isfinite(result.curves.drawdown).all(), name
        assert result.metrics["total_trades"] == len(result.trades), name
        total = sum(t.net_pnl for t in result.trades)
        assert result.curves.equity[-1] == pytest.approx(100_000.0 + total,
                                                         abs=1e-4), name


def test_costs_reduce_profit_for_every_builtin(sample_bars):
    """A universal sanity check: trading is never free."""
    for name, factory in BUILTIN_STRATEGIES.items():
        spec = factory()
        free = BacktestConfig(starting_capital=100_000.0)
        free.risk.fixed_units = 1.0
        free.warmup_bars = spec.warmup_bars()
        clean = Backtester(sample_bars, spec, free).run()
        charged = Backtester(sample_bars, spec, realistic_config()).run()
        if clean.trades:
            assert charged.curves.equity[-1] <= clean.curves.equity[-1] + 1e-6, name


def test_strategy_store_round_trip(tmp_path):
    workspace = Workspace(tmp_path / "ws").ensure()
    store = StrategyStore(workspace)
    created = store.seed_builtins(BUILTIN_STRATEGIES)
    assert len(created) == len(BUILTIN_STRATEGIES)
    assert len(store.list()) == len(BUILTIN_STRATEGIES)

    entry = store.list()[0]
    spec = store.load(entry.id)
    assert spec.validate() is not None

    copy = store.duplicate(spec.id, "A Copy")
    assert copy.id != spec.id
    assert store.load(copy.id).name == "A Copy"

    renamed = store.rename(copy.id, "Renamed")
    assert store.load(renamed.id).name == "Renamed"

    exported = tmp_path / "exported.json"
    store.export_to(spec.id, exported)
    assert exported.exists()

    imported = store.import_from(exported)
    assert imported.id in {s.id for s in store.list()}

    store.delete(copy.id)
    assert copy.id not in {s.id for s in store.list()}


def test_strategy_store_reports_a_corrupt_file(tmp_path):
    workspace = Workspace(tmp_path / "ws").ensure()
    store = StrategyStore(workspace)
    store.seed_builtins(BUILTIN_STRATEGIES)
    (workspace.strategies / "broken-abc123.json").write_text("{ not json",
                                                             encoding="utf-8")
    listed = store.list()          # must not raise
    assert listed


def test_saved_backtest_round_trip(tmp_path, sample_bars):
    from tradingbacktester.storage.backtest_store import BacktestStore

    workspace = Workspace(tmp_path / "ws").ensure()
    store = BacktestStore(workspace)
    spec = BUILTIN_STRATEGIES["EMA Cross + RSI"]()
    config = realistic_config()
    config.warmup_bars = spec.warmup_bars()
    result = Backtester(sample_bars, spec, config).run()

    run_id = store.save(result, "My run")
    rows = store.list()
    assert any(r.id == run_id for r in rows)
    row = next(r for r in rows if r.id == run_id)
    assert row.label == "My run"
    assert row.trade_count == len(result.trades)

    loaded = store.load(run_id)
    assert len(loaded.trades) == len(result.trades)
    assert loaded.metrics["net_profit"] == pytest.approx(
        result.metrics["net_profit"])
    assert np.allclose(loaded.curves.equity, result.curves.equity)
    if result.trades:
        assert loaded.trades[0].side is result.trades[0].side
        assert loaded.trades[0].exit_reason is result.trades[0].exit_reason

    store.delete(run_id)
    assert not any(r.id == run_id for r in store.list())


def test_dataset_repository_and_backtest_together(tmp_path, sample_bars):
    workspace = Workspace(tmp_path / "ws").ensure()
    repo = DatasetRepository(workspace)
    meta = repo.add_from_bars(sample_bars, name="NQ hourly")
    bars = repo.load_bars(meta.id)

    spec = BUILTIN_STRATEGIES["Bollinger Breakout"]()
    config = realistic_config()
    config.warmup_bars = spec.warmup_bars()
    a = Backtester(sample_bars, spec, config).run()
    b = Backtester(bars, spec, config).run()
    # Storing and reloading must not change a single trade.
    assert len(a.trades) == len(b.trades)
    assert a.metrics["net_profit"] == pytest.approx(b.metrics["net_profit"])


def test_optimisation_over_a_small_grid(sample_bars):
    from tradingbacktester.optimize.grid import ParameterRange, build_grid
    from tradingbacktester.optimize.ranking import neighbourhood_mean, rank
    from tradingbacktester.optimize.runner import OptimizationRunner

    spec = BUILTIN_STRATEGIES["EMA Cross + RSI"]()
    ranges = [ParameterRange("ema_fast", 10, 20, 5),
              ParameterRange("ema_slow", 40, 60, 10)]
    grid = build_grid(spec, ranges)
    assert len(grid) == 3 * 3

    config = realistic_config()
    runner = OptimizationRunner(sample_bars.slice(0, 1500), spec, config,
                                max_workers=2)
    results = runner.run(ranges)
    assert len(results.rows) == 9
    assert all(row.error is None or row.metrics for row in results.rows)

    ranked = rank(results, "net_profit")
    assert len(ranked) == 9
    profits = [r.metrics.get("net_profit", 0.0) for r in ranked]
    assert profits == sorted(profits, reverse=True)
    assert isinstance(neighbourhood_mean(results, ranked[0], "net_profit"), float)


def test_a_run_can_be_cancelled(sample_bars):
    from tradingbacktester.core.errors import CancelledError

    spec = BUILTIN_STRATEGIES["EMA Cross + RSI"]()
    calls = {"n": 0}

    def cancel() -> bool:
        calls["n"] += 1
        return calls["n"] > 3

    with pytest.raises(CancelledError):
        Backtester(sample_bars, spec, realistic_config(), cancel=cancel).run()


def test_progress_is_reported(sample_bars):
    seen: list[tuple[int, int]] = []
    spec = BUILTIN_STRATEGIES["MACD Trend"]()
    Backtester(sample_bars, spec, realistic_config(),
               progress=lambda c, t: seen.append((c, t))).run()
    assert seen
    assert seen[-1][0] >= seen[0][0]
    assert seen[-1][1] == len(sample_bars)


def test_engine_speed(sample_bars):
    """A simple strategy must run at a usable rate; the UI depends on it."""
    import time

    spec = BUILTIN_STRATEGIES["EMA Cross + RSI"]()
    config = realistic_config()
    start = time.perf_counter()
    Backtester(sample_bars, spec, config).run()
    elapsed = time.perf_counter() - start
    rate = len(sample_bars) / max(elapsed, 1e-9)
    assert rate > 20_000, f"only {rate:,.0f} bars/second"
