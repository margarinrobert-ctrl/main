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

from tradingbacktester.data.sample import generate_sample_data
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


def test_a_short_dataset_is_not_told_to_use_a_smaller_bar_size():
    """It was the only advice offered, and on a daily file it is impossible."""
    from tradingbacktester.core.errors import InsufficientDataError
    from tradingbacktester.data.bundled import find as find_bundled
    from tradingbacktester.data.csv_loader import load_csv, sniff_csv
    from tradingbacktester.data.instruments import default_instrument_for
    from tradingbacktester.finder import find_strategies, style

    dataset = find_bundled("BTCUSD 1d")
    assert dataset is not None and dataset.exists()
    path = str(dataset.path())
    daily = load_csv(path, sniff_csv(path).mapping,
                     default_instrument_for("BTCUSD"))

    with pytest.raises(InsufficientDataError) as exc:
        find_strategies(daily, style("position"))
    message = exc.value.user_message
    assert "finest bar size" in message
    assert "smaller bar size" not in message
    assert "more history" in message


def test_a_resampled_dataset_is_told_the_file_has_finer_bars():
    from tradingbacktester.core.errors import InsufficientDataError
    from tradingbacktester.data.bundled import find as find_bundled
    from tradingbacktester.data.csv_loader import load_csv, sniff_csv
    from tradingbacktester.data.instruments import default_instrument_for
    from tradingbacktester.finder import find_strategies, style

    dataset = find_bundled("US30 30m")
    path = str(dataset.path())
    bars = load_csv(path, sniff_csv(path).mapping,
                    default_instrument_for("US30"))

    with pytest.raises(InsufficientDataError) as exc:
        find_strategies(bars, style("position"))
    message = exc.value.user_message
    assert "smaller bar size" in message
    assert "30m" in message, "the advice must name the file's own bar size"


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


def test_cli_run_prints_the_trade_count(tmp_path, capsys):
    """It asked for `trade_count`, which is not a metric key, so it printed
    nothing — and the trade count decides whether the rest means anything."""
    from tradingbacktester.cli import main

    assert main(["--workspace", str(tmp_path), "run", "MACD Trend",
                 "--data", "US30 30m"]) == 0
    out = capsys.readouterr().out
    assert "total trades" in out
    # A count, not a count with two decimal places.
    line = next(l for l in out.splitlines() if "total trades" in l)
    assert ".00" not in line, line


def test_cli_run_flags_metrics_the_sample_cannot_support(tmp_path, capsys):
    """A profit factor of 4.00 from six trades, printed bare, is a lie."""
    from tradingbacktester.cli import main

    assert main(["--workspace", str(tmp_path), "run", "SuperTrend Follower",
                 "--data", "BTCUSD 1d"]) == 0
    out = capsys.readouterr().out
    assert "6" in out
    profit_factor = next(l for l in out.splitlines() if "profit factor" in l)
    assert "LOW n" in profit_factor
    assert "LOW n:" in out, "the reason must be given, not just the badge"
    assert "sampling noise" in out


def test_cli_run_does_not_cry_wolf_on_a_long_run(tmp_path, capsys):
    from tradingbacktester.cli import main

    assert main(["--workspace", str(tmp_path), "run", "MACD Trend",
                 "--data", "US30 30m"]) == 0
    out = capsys.readouterr().out
    assert "405" in out
    assert "LOW n" not in out


def test_cli_walk_forward_reports_every_fold(tmp_path, capsys):
    from tradingbacktester.cli import main

    code = main(["--workspace", str(tmp_path), "walkforward", "EMA Cross + RSI",
                 "--data", "US30 30m", "--param", "ema_fast=10:20:5",
                 "--folds", "3", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["combinations"] == 3
    assert len(payload["windows"]) == 3
    assert payload["verdict"]
    assert payload["warmup"] > 0, "blocks must be handed their own warm-up"
    assert any("not chosen with hindsight" in n for n in payload["notes"])


def test_cli_walk_forward_default_grid_is_small_enough_to_run(tmp_path, capsys):
    """No --param must still do something, or say plainly why it cannot."""
    from tradingbacktester.cli import main

    code = main(["--workspace", str(tmp_path), "walkforward", "MACD Trend",
                 "--data", "US30 30m", "--folds", "2", "--json"])
    out, err = capsys.readouterr()
    if code == 0:
        payload = json.loads(out)
        assert payload["combinations"] <= 200
    else:
        assert "--param" in err


def test_cli_monte_carlo_resamples_a_real_run(tmp_path, capsys):
    from tradingbacktester.cli import main

    code = main(["--workspace", str(tmp_path), "montecarlo", "EMA Cross + RSI",
                 "--data", "US30 30m", "--method", "block", "--draws", "500",
                 "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["draws"] == 500
    assert payload["trades"] > 0
    assert payload["method"] == "block"
    assert payload["block_size"] > 1
    assert set(payload["max_drawdown"]) == {"5", "25", "50", "75", "95"}
    assert payload["verdict"]
    assert any("cannot tell you whether the strategy has an edge" in n
               for n in payload["notes"])


def test_cli_report_writes_html_and_the_trade_list(tmp_path, capsys):
    from tradingbacktester.cli import main

    target = tmp_path / "report.html"
    assert main(["--workspace", str(tmp_path), "report", "MACD Trend",
                 "--data", "US30 30m", "--out", str(target), "--trades"]) == 0
    assert target.is_file() and target.stat().st_size > 50_000
    assert (tmp_path / "report.trades.csv").is_file()
    out = capsys.readouterr().out
    assert "wrote" in out and "KB" in out
    # Explicit encoding: the report contains em-dashes and arrows, and the
    # default on the Windows runner is cp1252, not UTF-8.
    assert "What else could have happened" in target.read_text(encoding="utf-8")


def test_cli_report_picks_the_format_from_the_suffix(tmp_path, capsys):
    from tradingbacktester.cli import main

    target = tmp_path / "report.pdf"
    assert main(["--workspace", str(tmp_path), "report", "MACD Trend",
                 "--data", "US30 30m", "--out", str(target)]) == 0
    assert target.read_bytes()[:5] == b"%PDF-"
    capsys.readouterr()


def test_cli_report_format_overrides_the_suffix(tmp_path, capsys):
    from tradingbacktester.cli import main

    target = tmp_path / "named_wrong.pdf"
    assert main(["--workspace", str(tmp_path), "report", "MACD Trend",
                 "--data", "US30 30m", "--out", str(target),
                 "--format", "html"]) == 0
    assert target.read_text(encoding="utf-8").lstrip().startswith("<!DOCTYPE html")
    capsys.readouterr()


def test_cli_mirror_runs_both_sides(tmp_path, capsys):
    from tradingbacktester.cli import main

    code = main(["--workspace", str(tmp_path), "mirror", "MACD Trend",
                 "--data", "US30 30m", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["real"]["trades"] > 0
    assert payload["mirror"]["trades"] > 0
    assert payload["real"]["drift_pct"] > 0 > payload["mirror"]["drift_pct"]
    assert payload["verdict"]
    assert any("control, not a second sample" in n for n in payload["notes"])


def test_cli_mirror_flag_reflects_the_data_for_any_command(tmp_path, capsys):
    """--mirror is on every command that reads data, not only `mirror`."""
    from tradingbacktester.cli import main

    code = main(["--workspace", str(tmp_path), "run", "MACD Trend",
                 "--data", "US30 30m", "--json"])
    assert code == 0
    real = json.loads(capsys.readouterr().out)

    code = main(["--workspace", str(tmp_path), "run", "MACD Trend",
                 "--data", "US30 30m", "--mirror", "--json"])
    assert code == 0
    mirrored = json.loads(capsys.readouterr().out)
    assert mirrored["net_profit"] != real["net_profit"]
    assert mirrored["total_trades"] > 0


def test_every_data_command_takes_mirror_and_nothing_else_does():
    """--mirror is added in one place; this is what keeps that list honest."""
    from tradingbacktester.cli import build_parser

    parser = build_parser()
    sub = next(a for a in parser._subparsers._group_actions)
    for name, subparser in sub.choices.items():
        options = {o for a in subparser._actions for o in a.option_strings}
        takes_data = "--data" in options
        takes_mirror = "--mirror" in options
        if name == "mirror":
            assert takes_data and not takes_mirror, name
        elif takes_data:
            assert takes_mirror, f"{name} reads data but cannot mirror it"
        else:
            assert not takes_mirror, f"{name} has --mirror but no data to mirror"


def test_cli_mirror_flag_is_refused_on_the_mirror_command(tmp_path, capsys):
    """`mirror --mirror` would silently test the reflection of a reflection."""
    from tradingbacktester.cli import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args(["mirror", "MACD Trend", "--data", "x",
                                   "--mirror"])


def test_cli_walk_forward_explains_a_malformed_range(tmp_path, capsys):
    from tradingbacktester.cli import main

    code = main(["--workspace", str(tmp_path), "walkforward", "EMA Cross + RSI",
                 "--data", "US30 30m", "--param", "ema_fast=oops"])
    assert code == 2
    assert "start:stop:step" in capsys.readouterr().err


# --------------------------------------------------------------------------
# The families a search may look in, and the constraints a user may set
# --------------------------------------------------------------------------

def test_every_family_is_causal_and_buildable():
    """A template that cannot emit a real strategy is a number, not a result."""
    from tradingbacktester.finder.candidates import (TEMPLATES, all_candidates,
                                                     build_spec, signals_for,
                                                     warmup_for)
    from tradingbacktester.finder.search import default_costs
    from tradingbacktester.finder.styles import style as get_style

    bars = generate_sample_data("NQ", "1h", n_bars=1500, seed=5)
    chosen = get_style("swing")
    costs = default_costs(bars.instrument)
    seen: set[str] = set()
    for candidate in all_candidates():
        if candidate.template in seen:
            continue
        seen.add(candidate.template)
        signals = signals_for(bars, candidate,
                              warmup_for(candidate, chosen.atr_period))
        assert signals.dtype == bool
        assert len(signals) == len(bars)
        spec = build_spec(candidate, chosen, "1h", 1.5, 2.0, costs)
        assert spec.entry_long is not None or spec.entry_short is not None
        # It must survive a round trip through its own serialised form, or it
        # cannot be saved, charted or exported.
        from tradingbacktester.strategy.spec import StrategySpec

        assert StrategySpec.from_dict(spec.to_dict()).name == spec.name
    assert seen == {t.key for t in TEMPLATES}


def test_a_signal_reads_no_bar_after_the_one_it_fires_on():
    """Truncating the series must not change any signal that survives.

    The cheapest look-ahead test there is, and it catches the whole class:
    an indicator that peeks forward gives a different answer when the future
    is removed.
    """
    from tradingbacktester.finder.candidates import (all_candidates,
                                                     signals_for, warmup_for)

    bars = generate_sample_data("NQ", "1h", n_bars=1200, seed=9)
    cut = 900
    short = bars.slice(0, cut)
    seen: set[str] = set()
    for candidate in all_candidates():
        if candidate.template in seen:
            continue
        seen.add(candidate.template)
        warm = warmup_for(candidate, 14)
        full = signals_for(bars, candidate, warm)[:cut]
        part = signals_for(short, candidate, warm)
        assert np.array_equal(full, part), candidate.describe()


def test_a_user_may_fix_the_session_and_the_geometry():
    from tradingbacktester.finder.styles import customise, style as get_style

    base = get_style("intraday")
    tight = customise(base, session=("07:00", "11:00"), stop_atr=(1.0,),
                      target_r=(2.0,), min_trades=40)
    assert tight.session == ("07:00", "11:00")
    assert tight.geometries() == [(1.0, 2.0)]
    assert tight.min_trades == 40
    # The base style is a module-level constant; changing a copy must not
    # change it for the next search in the same process.
    assert base.session == ("09:30", "16:00")
    assert base.min_trades == 100


def test_all_hours_is_expressible():
    from tradingbacktester.finder.styles import customise

    loose = customise("intraday", session=None, flat_at_session_end=False)
    assert loose.session is None
    assert loose.flat_at_session_end is False


@pytest.mark.parametrize("field,value", [
    ("key", "mine"),                    # identity is not a constraint
    ("label", "Mine"),
    ("nonsense", 1),
])
def test_only_the_constraints_are_adjustable(field, value):
    from tradingbacktester.core.errors import StrategyError
    from tradingbacktester.finder.styles import customise

    with pytest.raises(StrategyError):
        customise("intraday", **{field: value})


@pytest.mark.parametrize("override", [
    {"session": ("7am", "11:00")},
    {"session": ("09:30",)},
    {"stop_atr": ()},
    {"target_r": ()},
    {"max_bars": 0},
    {"weekdays": (9,)},
    {"weekdays": ()},
])
def test_a_constraint_that_cannot_make_a_usable_style_is_refused(override):
    from tradingbacktester.core.errors import StrategyError
    from tradingbacktester.finder.styles import customise

    with pytest.raises(StrategyError):
        customise("intraday", **override)


def test_a_constrained_search_runs_and_reports_its_constraints():
    """End to end: the constraints reach the search and the report states them."""
    from tradingbacktester.finder import find_strategies, format_report
    from tradingbacktester.finder.styles import customise

    bars = generate_sample_data("NQ", "30m", n_bars=4000, seed=11)
    chosen = customise("intraday", session=("09:30", "12:00"), stop_atr=(1.5,),
                       target_r=(2.0,), min_trades=20)
    report = find_strategies(bars, chosen, timeframe="30m",
                             templates=("squeeze", "momentum"),
                             control_draws=50, validate="quick")
    text = format_report(report)
    assert "09:30-12:00" in text
    assert "stop 1.5-1.5x ATR" in text
    # Only the two families asked for were tried.
    for finding in report.findings:
        assert finding.candidate.template in ("squeeze", "momentum")


# --------------------------------------------------------------------------
# The fast path must be the engine, only faster
# --------------------------------------------------------------------------

def _agreement_case(style_key: str, timeframe: str, dataset_name: str):
    """Bars, mask helpers and candidate sample for one style, ready to compare."""
    from tradingbacktester.data.bundled import find as find_bundled
    from tradingbacktester.data.csv_loader import load_csv, sniff_csv
    from tradingbacktester.data.instruments import default_instrument_for
    from tradingbacktester.finder.candidates import TEMPLATES, all_candidates
    from tradingbacktester.finder.outcomes import (session_entry_mask,
                                                   session_hold_limit)
    from tradingbacktester.finder.search import default_costs, prepare_bars
    from tradingbacktester.finder.styles import style as get_style

    dataset = find_bundled(dataset_name)
    assert dataset is not None and dataset.exists()
    bars = load_csv(str(dataset.path()), sniff_csv(str(dataset.path())).mapping,
                    default_instrument_for("US30"))
    chosen = get_style(style_key)
    working = prepare_bars(bars, timeframe)
    timezone = working.instrument.timezone
    costs = default_costs(working.instrument)

    # Exactly how search.py builds them, so the test cannot pass against a
    # gate the real search does not apply.
    entry_ok = session_entry_mask(
        working, timezone,
        chosen.session[0] if chosen.session else None,
        chosen.session[1] if chosen.session else None,
        chosen.weekdays, chosen.flat_at_session_end)
    hold = None
    if chosen.session is not None and chosen.flat_at_session_end:
        hold = session_hold_limit(working, timezone, chosen.session[0],
                                  chosen.session[1], chosen.max_bars,
                                  chosen.weekdays)

    seen: set[tuple] = set()
    sample = []
    for candidate in all_candidates():
        key = (candidate.template, candidate.side)
        if key in seen:
            continue
        seen.add(key)
        sample.append(candidate)
    assert len(sample) == 2 * len(TEMPLATES), "every family, both sides"
    return working, chosen, timezone, costs, entry_ok, hold, sample


@pytest.mark.parametrize("style_key,timeframe,dataset_name", [
    # 5m is where the max-bars time stop actually binds and where a single bar
    # can span both barriers; 30m is the everyday case; the last two have no
    # session at all, which is its own code path.
    ("scalp", "5m", "US30 5m"),
    ("intraday", "30m", "US30 30m"),
    ("swing", "1h", "US30 30m"),
    ("position", "1D", "US30 30m"),
])
def test_the_fast_path_agrees_with_the_engine_on_real_data(
        style_key, timeframe, dataset_name):
    """Every candidate, every style, trade for trade, against the real simulator.

    This is the test that makes the search worth running. The cached-outcome
    path exists because it is a thousand times faster, not because it is
    authoritative, and every defect below was found by running exactly this
    comparison rather than by reading the code:

    * the entry was filled at the raw open, so the stop and target sat half a
      spread away from where the engine put them;
    * "the last bar of the session" was computed as the last bar of the
      calendar day, which on an index CFD is seven hours later;
    * entries were gated on the fill bar, but the engine gates on the signal
      bar, which added a 09:30 trade every time a rule fired at 09:00;
    * a signal on the bar a position closed was skipped, and the engine takes
      it;
    * a bar that opened through the TARGET and later reached the stop was
      recorded as a stop, when the open settles the order and the engine says
      so;
    * a crossing needed the previous bar strictly below, and the engine allows
      an exact touch -- which on a stochastic is common;
    * the max-bars time stop closed a bar early and never tested the barriers
      on the final bar;
    * a style with no session applied a weekday filter the shipped spec did
      not carry, so the strategy could not reproduce its own search result.

    The first four were caught with one style and one geometry. The last four
    were not, and could not be: they need 5-minute bars where a 12-bar limit
    binds, an oscillator pinned at its ceiling, and a style with no session.
    Hence the parametrisation.
    """
    from tradingbacktester.finder.candidates import (build_spec, signals_for,
                                                     warmup_for)
    from tradingbacktester.finder.outcomes import verify_against_engine

    (working, chosen, timezone, costs, entry_ok, hold,
     sample) = _agreement_case(style_key, timeframe, dataset_name)

    # Three corners of the style's own geometry grid, not one: the widest is
    # where the time stop binds and the narrowest is where a single bar spans
    # both barriers.
    geometries = chosen.geometries()
    corners = {geometries[0], geometries[-1], geometries[len(geometries) // 2]}

    problems = []
    traded = 0
    for stop_atr, target_r in sorted(corners):
        for candidate in sample:
            cache = build_outcomes(
                working, Geometry(candidate.side, stop_atr, target_r,
                                  chosen.max_bars, chosen.atr_period),
                costs, hold)
            mask = entry_ok & signals_for(
                working, candidate, warmup_for(candidate, chosen.atr_period))
            spec = build_spec(candidate, chosen, timeframe, stop_atr, target_r,
                              costs, instrument_timezone=timezone)
            result = verify_against_engine(working, cache, mask, spec)
            traded += int(result["fast_trades"])
            if (result["fast_only"] or result["engine_only"]
                    or result["worst_matched_difference"] > 0.01
                    or abs(result["net_difference"]) > 0.01):
                problems.append(
                    f"{candidate.describe()} @ {stop_atr}x/{target_r}R: {result}")
    assert not problems, "\n".join(problems)
    assert traded > 0, "the comparison ran but no trade was taken by either side"


def test_the_max_bars_stop_holds_for_a_full_max_bars_after_the_fill():
    """``hold_bars`` is the engine's rule, not one bar less than it.

    The engine closes a position on the first bar where
    ``bar - entry_bar >= max_bars``, and it tests the barriers on that bar
    first. So the trade occupies ``max_bars + 1`` bars and the stop and target
    are live on all of them. Counting ``max_bars`` closed every timed trade one
    bar early, at a different close, and never tested the last bar at all.
    """
    from tradingbacktester.finder.outcomes import hold_bars

    assert hold_bars(12) == 13
    assert hold_bars(1) == 2
    assert hold_bars(0) == 2       # a zero-bar trade is not a thing


def test_a_bar_that_opened_through_the_target_is_not_recorded_as_a_stop():
    """The open settles the order; the pessimistic guess is only for a tie."""
    import numpy as np

    from tradingbacktester.core.types import CostModel
    from tradingbacktester.data.models import BarSeries
    from tradingbacktester.finder.outcomes import EXIT_TARGET, build_outcomes
    from tradingbacktester.data.instruments import default_instrument_for

    # Flat bars so ATR(14) settles at 2.0, then one bar that opens below the
    # short's target and later trades above its stop. Both barriers are reached
    # on that bar -- but the target was reached first, at the open, and there is
    # nothing left to guess about.
    n = 40
    o = np.full(n, 100.0)
    h = np.full(n, 101.0)
    l = np.full(n, 99.0)
    c = np.full(n, 100.0)
    o[21], h[21], l[21], c[21] = 90.0, 130.0, 90.0, 120.0
    ts = np.arange(n, dtype="int64") * 60_000_000_000 + 1_600_000_000_000_000_000
    bars = BarSeries.from_arrays(ts, o, h, l, c, np.full(n, 1000.0),
                                 default_instrument_for("US30"))
    cache = build_outcomes(bars, Geometry(-1, 1.0, 1.0, 10, 14),
                           CostModel(), None)
    i = 19                                  # signals on 19, fills on 20 at 100
    assert cache.valid[i]
    assert float(cache.stop_price[i]) > float(cache.entry_price[i])   # a short
    assert h[21] > float(cache.stop_price[i]), "the bar must reach the stop too"
    assert o[21] < float(cache.target_price[i]), "and open through the target"
    assert int(cache.exit_reason[i]) == EXIT_TARGET
    # Filled at the open it gapped to, not at the target: better than the
    # target, and the engine says the same.
    assert float(cache.net_points[i]) == pytest.approx(100.0 - 90.0)


def test_a_crossing_from_an_exact_touch_counts_for_both_engine_and_search():
    """%K and %D sit together at 100; the cross out of that state is a cross."""
    import numpy as np

    from tradingbacktester.finder.candidates import _crossed_up

    series = np.array([1.0, 2.0, 2.0, 3.0, 3.0, 2.0])
    level = np.array([1.5, 2.0, 2.0, 2.0, 3.0, 3.0])
    got = _crossed_up(series, level)
    # bar 1: 2.0 == 2.0 is not above.  bar 3: above, previous bar was equal.
    assert got.tolist() == [False, False, False, True, False, False]


def test_a_trade_may_not_run_out_of_the_block_it_was_signalled_in():
    """A research trade that finishes in the locked block is holdout data.

    It is one trade per block -- the last one -- but its whole result lands in
    the figure every candidate is ranked on, so the ranking is decided in part
    by bars the search is not allowed to see. It also made the two layers
    disagree: the engine, handed the research block as a standalone series,
    closes that position at the block's last close, and the finder then
    reported the candidate as unconfirmed.
    """
    import numpy as np

    from tradingbacktester.finder.outcomes import (block_hold_limit,
                                               hold_bars)

    n, split, horizon = 100, 60, 10
    room = block_hold_limit(n, split, horizon)

    # A signal at 50 fills at 51 and has nine bars before the split at 60.
    assert int(room[50]) == 9
    # The last signal that can trade inside the research block.
    assert int(room[58]) == 1
    # A signal at 59 fills at 60, which is the first bar of the locked block,
    # so it gets that block's room instead -- not zero.
    assert int(room[59]) == min(hold_bars(horizon), n - 60)
    # Nothing exceeds what the time stop allows.
    assert int(room.max()) <= hold_bars(horizon)
    # The last bar has no bar to fill on.
    assert int(room[-1]) == 0


def test_the_block_boundary_shows_up_in_a_real_search():
    """End to end: the search's own number equals the engine's, to the cent."""
    from tradingbacktester.data.bundled import find as find_bundled
    from tradingbacktester.data.csv_loader import load_csv, sniff_csv
    from tradingbacktester.data.instruments import default_instrument_for
    from tradingbacktester.finder.candidates import build_spec
    from tradingbacktester.finder.confirm import confirm
    from tradingbacktester.finder.search import (default_costs,
                                                 find_strategies, prepare_bars)
    from tradingbacktester.finder.styles import style as get_style

    chosen = get_style("swing")
    dataset = find_bundled("US30 30m")
    bars = load_csv(str(dataset.path()), sniff_csv(str(dataset.path())).mapping,
                    default_instrument_for("US30"))
    report = find_strategies(bars, chosen, timeframe="1h", control_draws=25,
                             validate="quick")
    working = prepare_bars(bars, "1h")
    split = int(len(working) * 0.65)
    timezone = working.instrument.timezone
    costs = default_costs(working.instrument)

    checked = 0
    step = max(1, len(report.findings) // 8)
    for finding in report.findings[::step]:
        if getattr(finding, "spec", None) is None:
            finding.spec = build_spec(
                finding.candidate, chosen, "1h", finding.stop_atr,
                finding.target_r, costs, instrument_timezone=timezone)
        agreement = confirm(finding, working, split).agreement
        checked += 1
        assert agreement.fast_trades == agreement.engine_trades, finding.label
        assert abs(agreement.fast_per_trade
                   - agreement.engine_per_trade) < 0.01, finding.label
        assert agreement.agrees, f"{finding.label}: {agreement.reason}"
    assert checked >= 5


def test_the_session_limit_uses_the_engines_own_session():
    """A trade must be flat at the session close, not at local midnight."""
    from tradingbacktester.data.bundled import find as find_bundled
    from tradingbacktester.data.csv_loader import load_csv, sniff_csv
    from tradingbacktester.data.instruments import default_instrument_for
    from tradingbacktester.finder.outcomes import (session_arrays,
                                                   session_hold_limit)

    dataset = find_bundled("US30 30m")
    bars = load_csv(str(dataset.path()), sniff_csv(str(dataset.path())).mapping,
                    default_instrument_for("US30"))
    in_session, last = session_arrays(bars, "America/New_York", "09:30",
                                      "16:00", (0, 1, 2, 3, 4))
    # 09:30 to 16:00 exclusive is thirteen thirty-minute bars.
    assert int(in_session.sum()) > 0
    hold = session_hold_limit(bars, "America/New_York", "09:30", "16:00", 48,
                              (0, 1, 2, 3, 4))
    assert hold.max() == 13, f"session is {hold.max()} bars, expected 13"
    # A bar outside the session gives no room at all.
    assert int((hold[~in_session] > 0).sum()) < int(in_session.sum())


def test_entry_and_exit_costs_land_where_the_engine_puts_them():
    """The entry half-spread moves the barriers; it is not a P&L adjustment."""
    from tradingbacktester.core.types import CostModel, SpreadMode
    from tradingbacktester.finder.outcomes import spread_halves

    costs = CostModel(spread_mode=SpreadMode.HALF_EACH_SIDE, spread_points=2.0)
    assert spread_halves(costs) == (1.0, 1.0)
    assert spread_halves(CostModel(spread_mode=SpreadMode.FULL_ON_ENTRY,
                                   spread_points=2.0)) == (2.0, 0.0)
    assert spread_halves(CostModel()) == (0.0, 0.0)

    bars = _noise(2_000, seed=9)
    free = build_outcomes(bars, Geometry(1, 1.5, 2.0, 24), CostModel())
    charged = build_outcomes(bars, Geometry(1, 1.5, 2.0, 24), costs)
    i = int(np.flatnonzero(free.valid & charged.valid)[100])
    # A long pays the ask: the fill, and both barriers with it, move up.
    assert charged.entry_price[i] == pytest.approx(free.entry_price[i] + 1.0)
    assert charged.stop_price[i] == pytest.approx(free.stop_price[i] + 1.0)
    assert charged.target_price[i] == pytest.approx(free.target_price[i] + 1.0)


def test_the_fast_path_agrees_with_the_engine_on_session_only_data():
    """The case the 24-hour data hid: bars that exist only inside the session.

    On a file that carries every hour, a signal on the last session bar fills
    on a bar outside the session and the hold limit refuses it, so an
    incorrect entry mask went unnoticed. On a file with only session bars the
    next bar is the next morning, and the same mistake takes an overnight
    trade in a style whose whole premise is that nothing is held overnight.
    """
    import pandas as pd

    from tradingbacktester.core.timeframe import Timeframe
    from tradingbacktester.data.models import BarSeries
    from tradingbacktester.finder.candidates import (build_spec, signals_for,
                                                     warmup_for)
    from tradingbacktester.finder.outcomes import (session_entry_mask,
                                                   session_hold_limit,
                                                   verify_against_engine)
    from tradingbacktester.finder.search import default_costs

    rng = np.random.default_rng(17)
    n = 12_000
    stamps = []
    t = pd.Timestamp("2019-01-02 09:30", tz="America/New_York")
    while len(stamps) < n:
        if t.dayofweek < 5 and 570 <= (t.hour * 60 + t.minute) < 960:
            stamps.append(t)
        t += pd.Timedelta(minutes=30)
    ts = (pd.DatetimeIndex(stamps).tz_convert("UTC")
          .to_numpy(dtype="datetime64[ns]").astype("int64"))
    steps = rng.normal(0, 12.0, n)
    close = 30_000.0 + np.cumsum(steps - steps.mean())
    open_ = np.empty(n)
    open_[0] = close[0]
    open_[1:] = close[:-1]
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 6.0, n))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 6.0, n))
    bars = BarSeries(ts=ts, open=open_, high=high, low=low, close=close,
                     volume=np.full(n, 500.0),
                     instrument=default_instrument_for("US30"),
                     timeframe=Timeframe.parse("30m"))

    chosen = style("intraday")
    timezone = bars.instrument.timezone
    costs = default_costs(bars.instrument)
    entry_ok = session_entry_mask(bars, timezone, chosen.session[0],
                                  chosen.session[1], chosen.weekdays,
                                  chosen.flat_at_session_end)
    hold = session_hold_limit(bars, timezone, chosen.session[0],
                              chosen.session[1], chosen.max_bars,
                              chosen.weekdays)

    from tradingbacktester.finder.candidates import all_candidates

    seen: set[tuple] = set()
    problems = []
    for candidate in all_candidates():
        key = (candidate.template, candidate.side)
        if key in seen:
            continue
        seen.add(key)
        cache = build_outcomes(
            bars, Geometry(candidate.side, 1.5, 2.0, chosen.max_bars, 14),
            costs, hold)
        mask = entry_ok & signals_for(bars, candidate,
                                      warmup_for(candidate, chosen.atr_period))
        spec = build_spec(candidate, chosen, "30m", 1.5, 2.0, costs,
                          instrument_timezone=timezone)
        result = verify_against_engine(bars, cache, mask, spec)
        if (result["fast_only"] or result["engine_only"]
                or abs(result["net_difference"]) > 0.01):
            problems.append(f"{candidate.describe()}: {result}")
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("name,costs", [
    ("percent slippage", dict(spread_mode="HALF_EACH_SIDE", spread_points=2.0,
                              slippage_mode="PERCENT", slippage_value=0.01)),
    ("atr slippage", dict(slippage_mode="ATR_FRACTION", slippage_value=0.05)),
    ("fixed slippage", dict(slippage_mode="FIXED_POINTS", slippage_value=1.5)),
    ("percent commission", dict(commission_mode="PERCENT_NOTIONAL",
                                commission_value=0.002)),
    ("commission with a floor", dict(commission_mode="PER_UNIT",
                                     commission_value=2.0, min_commission=1.0)),
    ("all of them at once", dict(spread_mode="HALF_EACH_SIDE", spread_points=2.0,
                                 slippage_mode="PERCENT", slippage_value=0.005,
                                 commission_mode="PERCENT_NOTIONAL",
                                 commission_value=0.001, min_commission=0.5)),
])
def test_every_cost_model_agrees_with_the_engine(name, costs):
    """Each cost mode charged where the engine charges it, not where it is easy.

    Percent costs are a fraction of the price the side actually transacts at,
    so entry and exit are priced separately; the earlier version charged both
    from the bar's close, which moved the barriers.
    """
    from tradingbacktester.core.types import (CommissionMode, CostModel,
                                              SlippageMode, SpreadMode)
    from tradingbacktester.data.bundled import find as find_bundled
    from tradingbacktester.data.csv_loader import load_csv, sniff_csv
    from tradingbacktester.data.instruments import default_instrument_for
    from tradingbacktester.finder.candidates import (all_candidates, build_spec,
                                                     signals_for, warmup_for)
    from tradingbacktester.finder.outcomes import (session_entry_mask,
                                                   session_hold_limit,
                                                   verify_against_engine)
    from tradingbacktester.finder.search import prepare_bars

    enums = {"spread_mode": SpreadMode, "slippage_mode": SlippageMode,
             "commission_mode": CommissionMode}
    model = CostModel(**{k: (enums[k][v] if k in enums else v)
                         for k, v in costs.items()})

    dataset = find_bundled("US30 30m")
    bars = load_csv(str(dataset.path()), sniff_csv(str(dataset.path())).mapping,
                    default_instrument_for("US30"))
    chosen = style("intraday")
    working = prepare_bars(bars, "30m")
    timezone = working.instrument.timezone
    entry_ok = session_entry_mask(working, timezone, chosen.session[0],
                                  chosen.session[1], chosen.weekdays,
                                  chosen.flat_at_session_end)
    hold = session_hold_limit(working, timezone, chosen.session[0],
                              chosen.session[1], chosen.max_bars,
                              chosen.weekdays)

    checked = 0
    for candidate in all_candidates():
        if candidate.template not in ("breakout", "rsi_reversion"):
            continue
        checked += 1
        if checked > 4:
            break
        cache = build_outcomes(
            working, Geometry(candidate.side, 1.5, 2.0, chosen.max_bars, 14),
            model, hold)
        mask = entry_ok & signals_for(working, candidate,
                                      warmup_for(candidate, chosen.atr_period))
        spec = build_spec(candidate, chosen, "30m", 1.5, 2.0, model,
                          instrument_timezone=timezone)
        result = verify_against_engine(working, cache, mask, spec)
        assert result["fast_only"] == 0 and result["engine_only"] == 0, \
            f"{name}: {candidate.describe()} {result}"
        assert result["worst_matched_difference"] < 0.01, f"{name}: {result}"
        assert abs(result["net_difference"]) < 0.01, f"{name}: {result}"


def test_min_commission_is_a_floor_not_an_extra_charge():
    """The engine charges max(commission, minimum); adding them overcharges."""
    from tradingbacktester.core.types import CommissionMode, CostModel
    from tradingbacktester.finder.outcomes import commission_points

    bars = _noise(500, seed=3)
    price = bars.close
    instrument = bars.instrument

    both = CostModel(commission_mode=CommissionMode.PER_UNIT,
                     commission_value=2.0, min_commission=1.0)
    # 2.00 a side beats the 1.00 floor, so a round turn is 4.00, not 6.00.
    charged = commission_points(both, instrument, price)
    expected = 2.0 * 2.0 / float(instrument.point_value)
    assert charged == pytest.approx(expected)

    # And when the floor bites it is the floor that is charged.
    floored = CostModel(commission_mode=CommissionMode.PER_UNIT,
                        commission_value=0.25, min_commission=1.0)
    assert commission_points(floored, instrument, price) == pytest.approx(
        2.0 * 1.0 / float(instrument.point_value))


def test_the_summary_reports_a_median_hold_as_well_as_a_mean():
    bars = _noise(4_000, seed=8)
    cache = build_outcomes(bars, Geometry(1, 1.5, 2.0, 24), CostModel())
    summary = cache.summary()
    assert summary["trades"] > 0
    assert "median_bars" in summary
    held = cache.bars_held[cache.valid]
    assert summary["median_bars"] == pytest.approx(float(np.median(held)))
    assert summary["avg_bars"] == pytest.approx(float(held.mean()))


def test_dropping_the_diagnostic_arrays_does_not_change_any_result():
    bars = _noise(3_000, seed=12)
    full = build_outcomes(bars, Geometry(1, 1.5, 2.0, 24), CostModel(),
                          detail=True)
    lean = build_outcomes(bars, Geometry(1, 1.5, 2.0, 24), CostModel(),
                          detail=False)
    assert np.array_equal(full.valid, lean.valid)
    assert full.net_cash == pytest.approx(lean.net_cash)
    assert np.array_equal(full.exit_reason, lean.exit_reason)
    assert np.array_equal(full.bars_held, lean.bars_held)
    assert lean.entry_price.size == 0, "the lean cache still allocated detail"


def test_a_short_candidate_is_described_as_a_short_one():
    from tradingbacktester.finder.candidates import (TEMPLATES_BY_KEY,
                                                     all_candidates, build_spec)

    for key in ("rsi_reversion", "band_reversion", "breakout"):
        template = TEMPLATES_BY_KEY[key]
        assert template.describe(1) != template.describe(-1)

    short = next(c for c in all_candidates()
                 if c.template == "rsi_reversion" and c.side < 0)
    spec = build_spec(short, style("intraday"), "15m", 1.5, 2.0, CostModel())
    text = spec.description.lower()
    assert "overbought" in text and "oversold" not in text
