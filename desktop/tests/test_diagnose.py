"""The diagnosis has to be a measurement, not an opinion.

Two properties are load-bearing and both are easy to lose in a refactor:

* every finding carries the numbers that produced it, so a reader can check it;
* nothing claims that acting on a finding will improve anything, because this
  application cannot know that and saying so would be a fabricated backtest.

The rest is per-check: each one must fire on a case built to trigger it and
stay quiet on one built not to.
"""

from __future__ import annotations

import numpy as np
import pytest

from tradingbacktester.analytics.diagnose import (MIN_TRADES, SEVERITIES,
                                                  diagnose, matched_control)
from tradingbacktester.core.types import (BacktestConfig, CommissionMode,
                                          CostModel)
from tradingbacktester.data.sample import generate_sample_data
from tradingbacktester.engine.backtester import Backtester
from tradingbacktester.strategy import builtin


@pytest.fixture(scope="module")
def bars():
    return generate_sample_data("US100", "15m", n_bars=8000, seed=3)


@pytest.fixture(scope="module")
def run(bars):
    return Backtester(bars, builtin.donchian_breakout(), BacktestConfig()).run()


@pytest.fixture(scope="module")
def costed(bars):
    config = BacktestConfig(costs=CostModel(
        commission_mode=CommissionMode.PER_TRADE, commission_value=2.0))
    return Backtester(bars, builtin.donchian_breakout(), config).run()


def _keys(diagnosis):
    return {f.key for f in diagnosis.findings}


def _find(diagnosis, key):
    return next((f for f in diagnosis.findings if f.key == key), None)


# --------------------------------------------------------------------------
# the two properties that matter
# --------------------------------------------------------------------------

def test_every_finding_carries_its_numbers(run):
    diagnosis = diagnose(run, draws=200)
    assert diagnosis.findings
    for finding in diagnosis.findings:
        assert finding.measurement.strip(), finding.headline
        assert any(ch.isdigit() for ch in finding.measurement), (
            f"'{finding.headline}' states no number, so it cannot be checked")
        assert finding.severity in SEVERITIES


def test_nothing_promises_an_improvement(run):
    text = diagnose(run, draws=200).describe().lower()
    assert "none of the above predicts" in text
    for promise in ("will improve", "will increase your", "guarantees",
                    "you will make", "this will make it more profitable"):
        assert promise not in text


def test_suggestions_are_experiments_not_conclusions(run):
    for finding in diagnose(run, draws=200).findings:
        if not finding.suggestion:
            continue
        assert not finding.suggestion.lower().startswith("this will"), (
            finding.suggestion)


# --------------------------------------------------------------------------
# the matched control
# --------------------------------------------------------------------------

def test_the_control_reports_both_sides_and_a_caveat(run):
    control = matched_control(run, draws=300)
    assert control is not None
    assert control.trades > 0
    assert control.excess_per_trade == pytest.approx(
        control.actual_per_trade - control.control_per_trade)
    assert 0.0 < control.p_value <= 1.0
    assert "no stop and no target" in control.caveat


def test_the_control_never_reports_a_p_value_of_zero(run):
    control = matched_control(run, draws=50)
    assert control.p_value >= 1.0 / 51


def test_the_control_is_deterministic_for_a_seed(run):
    a = matched_control(run, draws=200, seed=7)
    b = matched_control(run, draws=200, seed=7)
    assert a.control_per_trade == pytest.approx(b.control_per_trade)


def test_the_control_declines_rather_than_guessing_on_a_bare_result():
    assert matched_control(_Bare()) is None


# --------------------------------------------------------------------------
# per check
# --------------------------------------------------------------------------

def test_too_few_trades_blocks_everything_else():
    # A short series, so the run is thin by construction rather than by luck.
    short = generate_sample_data("US100", "15m", n_bars=700, seed=5)
    result = Backtester(short, builtin.rsi_mean_reversion(),
                        BacktestConfig()).run()
    assert 0 < len(result.trades) < MIN_TRADES, (
        f"the fixture took {len(result.trades)} trades; it must be thin "
        f"but not empty for this to test anything")
    finding = _find(diagnose(result, draws=100), "sample")
    assert finding is not None and finding.severity == "blocker"
    assert str(len(result.trades)) in finding.measurement


def test_a_run_with_no_trades_says_so_and_stops():
    from tradingbacktester.strategy.spec import (Compare, ConstOperand,
                                                 PriceOperand)

    bars = generate_sample_data("US100", "15m", n_bars=400, seed=1)
    spec = builtin.donchian_breakout()
    # An entry that can never fire, rather than no entry at all -- a strategy
    # with no entry rule is rejected by validate() before it reaches here.
    spec.entry_long = Compare(PriceOperand("close"), ">",
                              ConstOperand(1e12))
    spec.entry_short = None
    diagnosis = diagnose(Backtester(bars, spec, BacktestConfig()).run(),
                         draws=50)
    assert diagnosis.trades == 0
    assert _keys(diagnosis) == {"sample"}
    assert "no trades" in diagnosis.describe()


def test_a_costless_run_is_a_blocker(run):
    finding = _find(diagnose(run, control=False), "costs")
    assert finding is not None and finding.severity == "blocker"
    assert "paid nothing" in finding.headline


def test_a_costed_run_is_not(costed):
    finding = _find(diagnose(costed, control=False), "costs")
    assert finding is not None and finding.severity != "blocker"
    assert "twice the costs" in finding.measurement


def test_concentration_is_measured_against_the_remainder(run):
    finding = _find(diagnose(run, control=False), "concentration")
    assert finding is not None
    assert "%" in finding.measurement


def test_the_win_rate_is_always_given_its_break_even_rate(run):
    finding = _find(diagnose(run, control=False), "win_rate")
    assert finding is not None
    assert "break-even rate" in finding.measurement


def test_a_long_only_run_is_named_as_one(bars):
    spec = builtin.donchian_breakout()
    spec.entry_short = None
    spec.exit_short = None
    finding = _find(
        diagnose(Backtester(bars, spec, BacktestConfig()).run(), control=False),
        "direction")
    assert finding is not None
    assert "long-only" in finding.headline
    assert "whether or not the rule works" in finding.measurement


def test_a_strategy_with_no_parameters_is_told_how_to_get_some(run):
    from tradingbacktester.strategy.importer import import_strategy

    spec = import_strategy(
        '//@version=5\nstrategy("x")\ne = ta.ema(close, 20)\n'
        'if close > e\n    strategy.entry("L", strategy.long)\n',
        name_numbers=False).spec
    finding = _find(diagnose(run, spec, control=False), "tunable")
    assert finding is not None
    assert "Extract From The Numbers" in finding.suggestion


def test_a_parameterised_strategy_gets_no_such_finding(run):
    assert _find(diagnose(run, builtin.donchian_breakout(), control=False),
                 "tunable") is None


# --------------------------------------------------------------------------
# ordering and robustness
# --------------------------------------------------------------------------

def test_findings_come_worst_first(run):
    rank = {name: i for i, name in enumerate(SEVERITIES)}
    order = [rank[f.severity] for f in diagnose(run, draws=100).findings]
    assert order == sorted(order)


def test_a_failing_check_does_not_take_the_others_down(run, monkeypatch):
    import tradingbacktester.analytics.diagnose as module

    def boom(*_args, **_kwargs):
        raise RuntimeError("deliberate")

    monkeypatch.setattr(module, "_check_costs", boom)
    diagnosis = diagnose(run, draws=100)
    assert diagnosis.findings, "one broken check emptied the whole report"
    assert "costs" not in _keys(diagnosis)


def test_a_failing_control_is_reported_rather_than_swallowed(run, monkeypatch):
    import tradingbacktester.analytics.diagnose as module

    monkeypatch.setattr(module, "matched_control",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    diagnosis = diagnose(run, draws=50)
    assert diagnosis.control is None
    assert any("matched control" in n for n in diagnosis.notes)


class _Bare:
    trades: list = []
    bars = None
    metrics: dict = {}


# --------------------------------------------------------------------------
# The two things the first version of this report got wrong on real data
# --------------------------------------------------------------------------
#
# Run on the shipped US30 15m file, the report led with the cost model and the
# concentration while the strategy had quietly lost 1,660 over 6,661 trades --
# there was no check for "did it make money".  And the matched control quoted
# +2.57 per trade beside an actual -0.25, because it silently dropped the
# trades that opened and closed inside one bar, which are systematically the
# worst ones.


def test_a_losing_run_is_the_first_thing_said(bars):
    """A report that buries the loss under ratios is describing how it loses."""
    spec = builtin.donchian_breakout()
    result = Backtester(bars, spec, BacktestConfig()).run()
    losing = _Losing(result)
    diagnosis = diagnose(losing, control=False)
    first = diagnosis.findings[0]
    assert first.key == "outcome" and first.severity == "blocker"
    assert "lost money" in first.headline
    assert "-" in first.measurement


def test_a_profitable_run_gets_no_such_finding(run):
    if float(run.metrics.get("net_profit", 0.0)) <= 0:
        pytest.skip("this fixture did not make money")
    assert _find(diagnose(run, control=False), "outcome") is None


def test_the_control_states_what_it_could_not_match(run):
    control = matched_control(run, draws=200)
    assert control is not None
    assert control.total_trades == len(run.trades)
    if control.covers_everything:
        assert "This covers the" not in control.describe()
        return
    text = control.describe("USD")
    assert f"{control.trades:,} of {control.total_trades:,}" in text
    assert "across all of them the run made" in text
    assert f"{control.overall_per_trade:+,.2f}" in text


def test_the_control_never_quotes_a_subset_mean_alone(run):
    """The failure that mattered: +2.57 printed beside a real -0.25."""
    control = matched_control(run, draws=200)
    assert control is not None
    if control.covers_everything:
        return
    assert control.actual_per_trade != pytest.approx(control.overall_per_trade), (
        "this fixture cannot show the bias; pick one with same-bar exits")
    text = control.describe("USD")
    assert f"{control.overall_per_trade:+,.2f}" in text, (
        "the run's real per-trade figure is missing, so the matched subset's "
        "mean stands alone and reads as the result")


def test_an_even_month_split_is_a_note_not_a_pass(run):
    finding = _find(diagnose(run, control=False), "consistency")
    assert finding is not None
    months = float(run.metrics.get("profitable_months_pct", 0.0))
    if months < 40.0:
        assert finding.severity == "warning"
    elif months < 55.0:
        assert finding.severity == "note", (
            f"{months:.0f}% of months positive was called '{finding.severity}'")
    else:
        assert finding.severity == "good"


class _Losing:
    """A run wrapped so its net profit reads negative, nothing else changed."""

    def __init__(self, result):
        self._result = result
        self.metrics = dict(result.metrics)
        self.metrics["net_profit"] = -1_660.32
        self.trades = result.trades
        self.bars = result.bars

    def __getattr__(self, name):
        return getattr(self._result, name)
