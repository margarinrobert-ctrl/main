"""Institutional-standard safeguards, each pinned by the failure it prevents.

These are not style tests. Every one of them was written against a defect that
was live in the tree, and each names the wrong answer the engine used to give.
"""

from __future__ import annotations

import dataclasses

import pytest

from tradingbacktester.core.errors import DataError
from tradingbacktester.core.timeframe import Timeframe
from tradingbacktester.core.types import BacktestConfig, SessionSettings
from tradingbacktester.data.instruments import DEFAULT_INSTRUMENTS
from tradingbacktester.data.sample import generate_sample_data
from tradingbacktester.engine.backtester import Backtester
from tradingbacktester.strategy.builtin import BUILTIN_STRATEGIES


def _instrument(symbol: str):
    return next(i for i in DEFAULT_INSTRUMENTS if i.symbol == symbol)


def _bars(symbol: str = "NQ", n: int = 8000, timeframe: str = "30m"):
    return dataclasses.replace(
        generate_sample_data(symbol, Timeframe.parse(timeframe), n_bars=n,
                             seed=3),
        instrument=_instrument(symbol))


def _spec():
    return BUILTIN_STRATEGIES["EMA Cross + RSI"]()


# ---------------------------------------------------------------------------
# session timezone: the instrument's, as documented
# ---------------------------------------------------------------------------

def test_a_session_filter_uses_the_instruments_timezone_by_default():
    """SessionSettings promises "the instrument's timezone" and used to default
    to America/New_York regardless. On a CME instrument carrying
    America/Chicago that was 71 trades against 49, silently."""
    bars = _bars("NQ")
    assert bars.instrument.timezone == "America/Chicago"

    def run(**kwargs):
        spec = _spec()
        spec.session = SessionSettings(enabled=True, start="09:30", end="16:00",
                                       **kwargs)
        return len(Backtester(bars, spec, BacktestConfig()).run().trades)

    assert run() == run(timezone="America/Chicago")
    assert run() != run(timezone="America/New_York"), (
        "the fixture needs an instrument whose zone differs from New York")


def test_an_explicit_session_timezone_is_still_honoured():
    bars = _bars("NQ")
    spec = _spec()
    spec.session = SessionSettings(enabled=True, start="09:30", end="16:00",
                                   timezone="America/New_York")
    a = len(Backtester(bars, spec, BacktestConfig()).run().trades)
    spec2 = _spec()
    spec2.session = SessionSettings(enabled=True, start="09:30", end="16:00",
                                    timezone="America/Chicago")
    b = len(Backtester(bars, spec2, BacktestConfig()).run().trades)
    assert a != b, "an explicit zone must not be ignored"


def test_the_default_session_timezone_is_empty_meaning_the_instruments():
    assert SessionSettings().timezone == ""


# ---------------------------------------------------------------------------
# bar integrity: the simulation walks in order, so order must hold
# ---------------------------------------------------------------------------

def test_duplicate_timestamps_are_refused_not_run_silently():
    bars = _bars(n=2000)
    ts = bars.ts.copy()
    ts[500] = ts[499]
    with pytest.raises(DataError) as caught:
        Backtester(dataclasses.replace(bars, ts=ts), _spec(),
                   BacktestConfig()).run()
    assert "ascending" in str(caught.value)
    assert "500" in str(caught.value) or "clean_bars" in str(caught.value)


def test_out_of_order_timestamps_are_refused():
    bars = _bars(n=2000)
    ts = bars.ts.copy()
    ts[500], ts[501] = ts[501], ts[500]
    with pytest.raises(DataError):
        Backtester(dataclasses.replace(bars, ts=ts), _spec(),
                   BacktestConfig()).run()


def test_a_clean_series_raises_nothing_and_warns_about_nothing():
    result = Backtester(_bars(n=2000), _spec(), BacktestConfig()).run()
    assert not any("ascending" in w or "not a number" in w
                   for w in result.warnings)


def test_a_nan_price_is_warned_about_rather_than_ignored():
    """It used to take a 15-trade run down to 6 with no warning anywhere."""
    bars = _bars(n=2000)
    close = bars.close.copy()
    close[700] = float("nan")
    result = Backtester(dataclasses.replace(bars, close=close), _spec(),
                        BacktestConfig()).run()
    assert any("not a number" in w for w in result.warnings)


def test_a_mostly_broken_series_says_so_more_loudly():
    bars = _bars(n=2000)
    close = bars.close.copy()
    close[100:1000] = float("nan")
    result = Backtester(dataclasses.replace(bars, close=close), _spec(),
                        BacktestConfig()).run()
    warning = next(w for w in result.warnings if "not a number" in w)
    assert "description of the gaps" in warning


# ---------------------------------------------------------------------------
# the one optimistic default, measured rather than hidden
# ---------------------------------------------------------------------------

def _target_spec():
    spec = _spec()
    spec.exits.take_profit_enabled = True
    spec.exits.take_profit_mode = "atr"
    spec.exits.take_profit_value = 2.0
    return spec


def test_touch_only_fills_are_counted_and_reported():
    """limit_requires_through defaults to 0, so a target fills the moment the
    bar's range reaches it. Everything else in this engine defaults
    pessimistic; this one does not, and the run should say so."""
    result = Backtester(_bars("NQ"), _target_spec(), BacktestConfig()).run()
    warning = [w for w in result.warnings if "single touch" in w]
    assert warning, "a run whose targets filled on a touch should say so"
    assert "queue" in warning[0]


def test_the_warning_does_not_claim_the_share_bounds_the_impact():
    """One touch-only fill in 28 was worth half the net profit, because the
    trade either takes its target or runs on to its stop."""
    result = Backtester(_bars("NQ"), _target_spec(), BacktestConfig()).run()
    warning = next(w for w in result.warnings if "single touch" in w)
    assert "NOT how much of the result depends on it" in warning


def test_requiring_a_tick_through_removes_the_warning():
    config = BacktestConfig()
    config.execution.limit_requires_through = _instrument("NQ").tick_size
    result = Backtester(_bars("NQ"), _target_spec(), config).run()
    assert not any("single touch" in w for w in result.warnings)


def test_a_touch_only_fill_can_be_worth_a_win_plus_the_loss_that_replaces_it():
    """The mechanism the warning describes, asserted rather than assumed."""
    bars = _bars("NQ")
    spec = _target_spec()
    loose = Backtester(bars, spec, BacktestConfig()).run()
    config = BacktestConfig()
    config.execution.limit_requires_through = bars.instrument.tick_size
    strict = Backtester(bars, spec, config).run()

    a = [(t.entry_bar, t.exit_bar, round(t.net_pnl, 2)) for t in loose.trades]
    b = [(t.entry_bar, t.exit_bar, round(t.net_pnl, 2)) for t in strict.trades]
    differing = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    assert differing, "the fixture needs at least one fill that changes"
    index = differing[0]
    assert a[index][2] > 0 > b[index][2], (
        "the trade whose target was only touched should turn from a win into "
        "a loss when the fill is refused")
