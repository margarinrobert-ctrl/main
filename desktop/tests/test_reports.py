"""Every plain-text report must fit the width it declares.

A line that overruns is not truncated by the terminal, it wraps — and a table
row that wraps at an arbitrary column puts half a number on the next line,
which is worse than no table at all. These reports were written with the width
in mind and still drifted past it: an indicator-study paragraph reached 197
characters and a walk-forward row 144, because an f-string that fits when the
numbers are small does not when they are not.

So the widths are asserted here rather than trusted, at two widths, on real
data, for every formatter the CLI can print.
"""

from __future__ import annotations

import pytest

from tradingbacktester.core.textfmt import DEFAULT_WIDTH, fit, row


# --------------------------------------------------------------------------
# The helper
# --------------------------------------------------------------------------

def test_fit_never_returns_nothing():
    """Callers `extend` with the result; an empty list would silently drop it."""
    assert fit("") == [""]
    assert fit("   ") == [""]
    assert fit("", indent="   ") == [""]


def test_fit_hangs_the_continuations():
    lines = fit("label: " + " ".join(["word"] * 40), width=40, hang=7)
    assert len(lines) > 1
    assert lines[0].startswith("label: ")
    assert all(line.startswith(" " * 7) for line in lines[1:])
    assert all(len(line) <= 40 for line in lines)


def test_fit_does_not_break_an_identifier_in_half():
    """A broken symbol cannot be copied back out of a terminal."""
    long_name = "close_position_in_bar_over_atr_200_rank_something_long"
    lines = fit(f"feature: {long_name}", width=30)
    assert long_name in " ".join(lines)


def test_row_keeps_the_numeric_columns_in_line():
    cells = f"   {'event':<24} {'12':>7}  "
    lines = row(cells, "a verdict long enough that it has to wrap somewhere",
                width=60)
    assert len(lines) > 1
    assert all(len(line) <= 60 for line in lines)
    # Continuations align under where the prose started, not under column one.
    assert lines[1].startswith(" " * len(cells))


def test_row_without_prose_is_just_the_cells():
    assert row("   a   b   ", "") == ["   a   b"]


# --------------------------------------------------------------------------
# The reports themselves, on real data
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def bars():
    from tradingbacktester.data.bundled import find
    from tradingbacktester.data.csv_loader import load_csv, sniff_csv
    from tradingbacktester.data.instruments import default_instrument_for

    dataset = find("US30 30m")
    assert dataset is not None and dataset.exists()
    path = str(dataset.path())
    return load_csv(path, sniff_csv(path).mapping,
                    default_instrument_for("US30"))


@pytest.fixture(scope="module")
def run(bars):
    from tradingbacktester.core.types import BacktestConfig
    from tradingbacktester.engine.backtester import Backtester
    from tradingbacktester.strategy.builtin import BUILTIN_STRATEGIES

    spec = BUILTIN_STRATEGIES["MACD Trend"]()
    config = BacktestConfig(starting_capital=100_000.0)
    config.exits, config.execution = spec.exits, spec.execution
    config.session, config.costs, config.risk = spec.session, spec.costs, spec.risk
    result = Backtester(bars, spec, config).run()
    assert result.trades
    return spec, config, result


def _check(text: str, width: int, label: str) -> None:
    over = [(len(line), line) for line in text.splitlines() if len(line) > width]
    assert not over, (
        f"{label}: {len(over)} line(s) over {width} columns, "
        f"longest {max(n for n, _ in over)}: {max(over)[1][:90]!r}")
    assert text.strip(), f"{label} produced nothing"


WIDTHS = (78, 100)


@pytest.mark.parametrize("width", WIDTHS)
def test_strategy_search_report_fits(bars, width):
    from tradingbacktester.finder import find_strategies, style
    from tradingbacktester.finder.report import format_report

    report = find_strategies(bars, style("intraday"), control_draws=50)
    _check(format_report(report, width=width), width, "strategy search")


@pytest.mark.parametrize("width", WIDTHS)
def test_indicator_study_report_fits(bars, width):
    from tradingbacktester.finder import style
    from tradingbacktester.research.report import format_study
    from tradingbacktester.research.study import study_features

    study = study_features(bars, style("swing"), side=-1)
    _check(format_study(study, width=width), width, "indicator study")


@pytest.mark.parametrize("width", WIDTHS)
def test_anomaly_scan_report_fits(bars, width):
    from tradingbacktester.finder import style
    from tradingbacktester.research.anomalies import scan
    from tradingbacktester.research.report import format_anomalies

    found = scan(bars, style("intraday"), control_draws=100)
    _check(format_anomalies(found, width=width), width, "anomaly scan")


@pytest.mark.parametrize("width", WIDTHS)
def test_walk_forward_report_fits(bars, run, width):
    """Four swept parameters is 60 characters of parameter list on its own."""
    from tradingbacktester.optimize.grid import ParameterRange
    from tradingbacktester.optimize.walkforward import (format_walk_forward,
                                                        walk_forward)

    spec, config, _ = run
    result = walk_forward(bars, spec, config,
                          [ParameterRange("macd_fast", 10, 14, 2),
                           ParameterRange("macd_slow", 24, 28, 4),
                           ParameterRange("trend_period", 180, 200, 20)],
                          folds=3, minimum_trades=1)
    _check(format_walk_forward(result, bars, width=width), width, "walk-forward")


@pytest.mark.parametrize("width", WIDTHS)
def test_monte_carlo_report_fits(run, width):
    from tradingbacktester.analytics.montecarlo import (format_monte_carlo,
                                                        resample_result)

    _, _, result = run
    mc = resample_result(result, draws=300)
    _check(format_monte_carlo(mc, width=width), width, "monte carlo")


@pytest.mark.parametrize("width", WIDTHS)
def test_mirror_report_fits(bars, run, width):
    from tradingbacktester.research.mirror import format_mirror, mirror_test

    spec, config, _ = run
    report = mirror_test(bars, spec, config)
    _check(format_mirror(report, width=width), width, "mirror")


def test_the_dataset_listing_fits(tmp_path, capsys):
    """`cli data` printed a 167-character line for a shipped dataset."""
    from tradingbacktester.cli import main

    assert main(["--workspace", str(tmp_path), "data"]) == 0
    _check(capsys.readouterr().out, DEFAULT_WIDTH, "cli data")
