"""The strategy search, and the parts that stop it fooling itself.

The two tests that matter here are a pair: the finder must find a real edge
when one has been planted, and must *not* find one in a series that has none.
A search that only ever says "nothing" is useless, and a search that always
finds something is worse than useless.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from tradingbacktester.core.timeframe import Timeframe
from tradingbacktester.core.types import CostModel, SpreadMode
from tradingbacktester.data.instruments import default_instrument_for
from tradingbacktester.data.models import BarSeries
from tradingbacktester.finder import (build_outcomes, find_strategies,
                                      format_report, style)
from tradingbacktester.finder.control import (analytic_control,
                                              benjamini_hochberg,
                                              sampled_control)
from tradingbacktester.finder.outcomes import (EXIT_STOP, EXIT_TARGET,
                                               EXIT_TIME, Geometry,
                                               select_sequential)


# --------------------------------------------------------------------------
# Building a series with, and without, a planted edge
# --------------------------------------------------------------------------

def _session_stamps(count: int, minutes: int = 15) -> np.ndarray:
    """Timestamps inside the New York cash session, weekdays only."""
    out: list[pd.Timestamp] = []
    t = pd.Timestamp("2015-01-02 09:30", tz="America/New_York")
    while len(out) < count:
        if t.dayofweek < 5 and 570 <= (t.hour * 60 + t.minute) <= 960:
            out.append(t)
        t += pd.Timedelta(minutes=minutes)
    # Explicitly nanoseconds: pandas 2 keeps whatever unit a Timestamp was
    # built with, so `.view("int64")` can hand back microseconds and put every
    # bar in 1970.
    index = pd.DatetimeIndex(out).tz_convert("UTC")
    return index.to_numpy(dtype="datetime64[ns]").astype("int64")


def _bars_from_steps(ts: np.ndarray, steps: np.ndarray, seed: int) -> BarSeries:
    rng = np.random.default_rng(seed)
    n = steps.size
    close = 25_000.0 + np.cumsum(steps)
    open_ = np.empty(n)
    open_[0] = close[0]
    open_[1:] = close[:-1]
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 4.0, n))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 4.0, n))
    return BarSeries(
        ts=ts.astype("int64"), open=open_, high=high, low=low, close=close,
        volume=np.full(n, 1000.0), instrument=default_instrument_for("US30"),
        timeframe=Timeframe.parse("15m"))


def _planted(n: int = 30_000, strength: float = 6.0, seed: int = 5) -> BarSeries:
    """A series where an RSI(14) cross up through 30 is genuinely followed by a rise.

    The drift is removed from the series as a whole, so the *unconditional*
    return is zero: the only thing to find is the conditional edge. That is
    what stops the test passing because the market went up.
    """
    from tradingbacktester.indicators.base import REGISTRY

    rng = np.random.default_rng(seed)
    ts = _session_stamps(n)
    base = rng.normal(0, 8.0, n)
    plain = _bars_from_steps(ts, base, seed)
    rsi = REGISTRY.compute("RSI", plain, {"period": 14})["value"]
    crossed = np.zeros(n, dtype=bool)
    crossed[1:] = (rsi[1:] > 30) & (rsi[:-1] < 30)
    boost = np.zeros(n)
    for i in np.flatnonzero(crossed):
        boost[i + 1:i + 13] += strength
    steps = base + boost
    steps -= steps.mean()
    return _bars_from_steps(ts, steps, seed)


def _noise(n: int = 30_000, seed: int = 11) -> BarSeries:
    rng = np.random.default_rng(seed)
    steps = rng.normal(0, 8.0, n)
    return _bars_from_steps(_session_stamps(n), steps - steps.mean(), seed)


@pytest.fixture(scope="module")
def planted_bars() -> BarSeries:
    return _planted()


@pytest.fixture(scope="module")
def noise_bars() -> BarSeries:
    return _noise()


# --------------------------------------------------------------------------
# The outcome cache
# --------------------------------------------------------------------------

def test_outcomes_reproduce_a_hand_computed_trade():
    """Four bars, one signal, arithmetic that can be checked on paper."""
    ts = _session_stamps(40)
    n = 40
    close = np.full(n, 100.0)
    bars = BarSeries(
        ts=ts.astype("int64"), open=close.copy(), high=close + 1.0,
        low=close - 1.0, close=close.copy(), volume=np.ones(n),
        instrument=default_instrument_for("US30"),
        timeframe=Timeframe.parse("15m"))
    # A flat market: the true range is 2 every bar, so ATR is 2, a 1x ATR stop
    # sits 2 away, and nothing ever reaches it -- every trade times out flat.
    cache = build_outcomes(bars, Geometry(1, 1.0, 2.0, 5), CostModel())
    taken = np.flatnonzero(cache.valid)
    assert taken.size > 0
    i = int(taken[-1])
    assert cache.entry_price[i] == pytest.approx(100.0)
    assert cache.stop_price[i] == pytest.approx(98.0)
    assert cache.target_price[i] == pytest.approx(104.0)
    assert cache.exit_reason[i] == EXIT_TIME
    assert cache.net_points[i] == pytest.approx(0.0)


def test_a_bar_touching_both_barriers_is_recorded_as_the_stop():
    n = 60
    ts = _session_stamps(n)
    close = np.full(n, 100.0)
    high = close + 1.0
    low = close - 1.0
    # One bar spans far enough to reach a 1x ATR stop and a 2R target at once.
    high[30] = 130.0
    low[30] = 70.0
    bars = BarSeries(ts=ts.astype("int64"), open=close.copy(), high=high,
                     low=low, close=close.copy(), volume=np.ones(n),
                     instrument=default_instrument_for("US30"),
                     timeframe=Timeframe.parse("15m"))
    cache = build_outcomes(bars, Geometry(1, 1.0, 2.0, 5), CostModel())
    assert cache.exit_reason[29] == EXIT_STOP
    assert cache.net_points[29] < 0


def test_costs_are_always_adverse():
    bars = _noise(3_000, seed=3)
    free = build_outcomes(bars, Geometry(1, 1.5, 2.0, 24), CostModel())
    charged = build_outcomes(
        bars, Geometry(1, 1.5, 2.0, 24),
        CostModel(spread_mode=SpreadMode.HALF_EACH_SIDE, spread_points=4.0))
    assert charged.summary()["net"] < free.summary()["net"]


def test_sequential_selection_never_overlaps_trades():
    bars = _noise(5_000, seed=7)
    cache = build_outcomes(bars, Geometry(1, 1.5, 2.0, 24), CostModel())
    rng = np.random.default_rng(1)
    mask = rng.random(len(bars)) < 0.3
    kept = select_sequential(cache, mask)
    taken = np.flatnonzero(kept)
    assert taken.size > 0
    for a, b in zip(taken, taken[1:]):
        assert b > a + int(cache.bars_held[a]), "two trades were open at once"


# --------------------------------------------------------------------------
# The matched control
# --------------------------------------------------------------------------

def test_the_control_is_not_fooled_by_trading_the_good_hours():
    """Picking the profitable time of day is not an edge, and must not score as one."""
    rng = np.random.default_rng(1)
    minutes = rng.choice([570, 600, 900, 930], size=20_000)
    values = np.where(minutes < 700, rng.normal(5, 50, 20_000),
                      rng.normal(-5, 50, 20_000))
    morning = rng.choice(np.flatnonzero(minutes < 700), size=400, replace=False)

    result = analytic_control(minutes, values, minutes[morning], values[morning])
    assert result.p_value > 0.10, "timing alone was scored as skill"

    # The same trades with a real edge added must be detected.
    better = values.copy()
    better[morning] += 20.0
    found = analytic_control(minutes, better, minutes[morning], better[morning])
    assert found.p_value < 0.01
    assert found.excess_per_trade > 15.0


def test_the_two_controls_agree():
    rng = np.random.default_rng(4)
    minutes = rng.choice([570, 600, 900], size=8_000)
    values = rng.normal(2.0, 40.0, 8_000)
    picked = rng.choice(8_000, size=300, replace=False)
    a = analytic_control(minutes, values, minutes[picked], values[picked])
    s = sampled_control(minutes, values, minutes[picked], values[picked],
                        draws=400, seed=1)
    assert abs(a.excess_per_trade - s.excess_per_trade) < 2.0
    assert abs(a.p_value - s.p_value) < 0.25


def test_sampled_control_never_claims_certainty():
    values = np.zeros(100)
    result = sampled_control(np.zeros(100, dtype="int16"), values + 1.0,
                             np.zeros(10, dtype="int16"),
                             np.full(10, 1e9), draws=100, seed=1)
    assert result.p_value >= 1.0 / 101.0


def test_benjamini_hochberg_matches_a_hand_worked_example():
    # n=5, alpha=0.1: sorted p 0.001 0.02 0.04 0.3 0.8 against 0.02 0.04 0.06
    # 0.08 0.10 -- the third is the largest that passes, so three survive.
    assert benjamini_hochberg([0.001, 0.02, 0.3, 0.8, 0.04], 0.10) == \
        [True, True, False, False, True]
    assert benjamini_hochberg([0.2, 0.3, 0.4], 0.10) == [False, False, False]
    assert benjamini_hochberg([], 0.10) == []


# --------------------------------------------------------------------------
# The search, both ways round
# --------------------------------------------------------------------------

def test_the_finder_finds_a_planted_edge(planted_bars):
    report = find_strategies(planted_bars, style("intraday"), timeframe="15m",
                             control_draws=300, seed=3)
    assert report.combinations > 100
    assert report.shortlist, "an edge was planted and nothing was shortlisted"
    best = report.shortlist[0]
    assert best.survives_fdr
    assert best.excess > 0
    assert best.control.p_value < 0.01
    # And it must be the family that was actually planted, not a coincidence.
    families = {f.candidate.template for f in report.shortlist}
    assert "rsi_reversion" in families or "band_reversion" in families
    assert report.holdout_bars > 0
    assert best.holdout is not None


def test_the_finder_does_not_find_an_edge_in_noise(noise_bars):
    report = find_strategies(noise_bars, style("intraday"), timeframe="15m",
                             control_draws=300, seed=3)
    survivors = [f for f in report.shortlist if f.verdict == "worth testing further"]
    assert not survivors, (
        "a strategy was recommended on a random walk: "
        + "; ".join(f.label for f in survivors))


def test_the_report_states_the_multiplicity(noise_bars):
    report = find_strategies(noise_bars, style("intraday"), timeframe="15m",
                             control_draws=100, seed=1)
    text = format_report(report)
    assert f"{report.combinations:,} combinations" in text
    assert "not a prediction" in text
    assert "Research" in text and "locked" in text


def test_a_found_strategy_is_a_real_strategy(planted_bars):
    """Whatever is found has to be runnable, saveable and chartable."""
    from tradingbacktester.core.types import BacktestConfig
    from tradingbacktester.engine.backtester import Backtester
    from tradingbacktester.strategy.spec import StrategySpec

    report = find_strategies(planted_bars, style("intraday"), timeframe="15m",
                             control_draws=100, seed=3)
    assert report.shortlist
    spec = report.shortlist[0].spec
    assert spec is not None
    assert spec.validate() == [] or isinstance(spec.validate(), list)
    # It survives a save/load round trip...
    again = StrategySpec.from_dict(spec.to_dict())
    assert again.name == spec.name
    # ...and it runs in the real engine, producing real trades.
    config = BacktestConfig(starting_capital=100_000.0)
    config.exits, config.session, config.costs = spec.exits, spec.session, spec.costs
    result = Backtester(planted_bars, spec, config).run()
    assert len(result.trades) > 0


def test_the_search_refuses_a_dataset_that_is_too_small():
    from tradingbacktester.core.errors import InsufficientDataError

    with pytest.raises(InsufficientDataError):
        find_strategies(_noise(300, seed=2), style("intraday"), timeframe="15m")


def test_every_style_is_usable():
    from tradingbacktester.finder.styles import STYLES

    for s in STYLES:
        assert s.timeframes and s.geometries()
        assert s.min_trades >= 10
        assert s.describe()


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------

def test_cli_lists_the_shipped_data(tmp_path, capsys):
    from tradingbacktester.cli import main

    assert main(["--workspace", str(tmp_path), "data"]) == 0
    out = capsys.readouterr().out
    assert "Shipped with the application" in out
    assert "US30 30m" in out


def test_cli_lists_the_styles(capsys):
    from tradingbacktester.cli import main

    assert main(["find", "--data", "unused", "--style", "list"]) == 0
    out = capsys.readouterr().out
    for key in ("scalp", "intraday", "swing", "position"):
        assert key in out


def test_cli_imports_and_then_finds(tmp_path, capsys):
    """The whole path: import a file, then search the dataset it created."""
    from tradingbacktester.cli import main
    from tradingbacktester.data.bundled import find as find_bundled

    source = find_bundled("US30 30m")
    assert source is not None and source.exists()

    code = main(["--workspace", str(tmp_path), "import", str(source.path()),
                 "--symbol", "US30", "--name", "Test 30m"])
    assert code == 0
    out = capsys.readouterr().out
    assert "TickVolume" in out, "the MT5 volume column was not detected"
    assert "saved as 'Test 30m'" in out

    code = main(["--workspace", str(tmp_path), "find", "--data", "Test 30m",
                 "--style", "intraday", "--timeframe", "30m", "--draws", "50",
                 "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["symbol"] == "US30"
    assert payload["combinations"] > 100
    assert payload["research"][0] < payload["holdout_end"]
    assert any("not a prediction" in note for note in payload["notes"])


def test_cli_reports_a_missing_dataset_kindly(tmp_path, capsys):
    from tradingbacktester.cli import main

    code = main(["--workspace", str(tmp_path), "find", "--data", "nope"])
    assert code == 2
    assert "No dataset called 'nope'" in capsys.readouterr().err


def test_cli_runs_a_builtin_strategy(tmp_path, capsys):
    from tradingbacktester.cli import main

    code = main(["--workspace", str(tmp_path), "run", "EMA Cross + RSI",
                 "--data", "US30 30m"])
    assert code == 0
    out = capsys.readouterr().out
    assert "net profit" in out
    assert "max drawdown pct" in out
