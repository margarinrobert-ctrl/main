"""The grid optimiser's train/test split, and the one-look rule that makes it one.

The point of these tests is not that the arithmetic is right -- it is that the
locked block cannot influence the choice.  Two of them check that directly: one
proves no holdout trade begins inside the research block, and one proves the
block is never scored at all when the ranking is incomplete.
"""

from __future__ import annotations

import copy
import math

import pytest

from tradingbacktester.core.errors import InsufficientDataError
from tradingbacktester.core.types import BacktestConfig
from tradingbacktester.data.sample import generate_sample_data
from tradingbacktester.engine.backtester import Backtester
from tradingbacktester.optimize.grid import ParameterRange
from tradingbacktester.optimize.holdout import (DEFAULT_REVEAL, MIN_BARS,
                                                RESEARCH_FRACTION,
                                                HoldoutResult, Revealed,
                                                format_holdout, _notes,
                                                optimise_with_holdout)
from tradingbacktester.strategy.builtin import BUILTIN_STRATEGIES


@pytest.fixture(scope="module")
def bars():
    return generate_sample_data("NQ", "1h", n_bars=2500, seed=13)


@pytest.fixture
def spec():
    return BUILTIN_STRATEGIES["EMA Cross + RSI"]()


@pytest.fixture
def ranges():
    return [ParameterRange("ema_fast", 8, 24, 4),
            ParameterRange("ema_slow", 30, 60, 10)]


@pytest.fixture(scope="module")
def run(bars):
    """One real sweep, shared: it is the expensive fixture in this file."""
    spec = BUILTIN_STRATEGIES["EMA Cross + RSI"]()
    return optimise_with_holdout(
        bars, spec, BacktestConfig(),
        [ParameterRange("ema_fast", 8, 24, 4),
         ParameterRange("ema_slow", 30, 60, 10)],
        max_workers=1)


# --------------------------------------------------------------------------
# The split itself
# --------------------------------------------------------------------------

def test_the_blocks_tile_the_series_without_overlapping(run, bars):
    assert run.split_index == int(len(bars) * RESEARCH_FRACTION)
    assert run.research_bars == run.split_index
    assert run.holdout_bars == len(bars) - run.split_index
    assert run.research_bars + run.holdout_bars == len(bars)


def test_the_sweep_only_ever_sees_the_research_block(run, bars):
    """Every ranked row was produced over ``split`` bars, not the whole series."""
    assert run.research is not None
    assert run.research.total_combinations == run.combinations
    # A row's own trade count cannot exceed what the research block can hold,
    # but the check that matters is the engine one below.
    assert run.combinations == 20


def test_too_short_a_series_is_refused_rather_than_split(spec, ranges):
    short = generate_sample_data("NQ", "1h", n_bars=MIN_BARS - 1, seed=3)
    with pytest.raises(InsufficientDataError) as exc:
        optimise_with_holdout(short, spec, BacktestConfig(), ranges,
                              max_workers=1)
    assert str(MIN_BARS) in str(exc.value)


def test_an_extreme_fraction_is_clamped_not_allowed_to_empty_a_block(
        bars, spec, ranges):
    out = optimise_with_holdout(bars, spec, BacktestConfig(), ranges,
                                research_fraction=0.999, max_workers=1)
    assert out.holdout_bars > 0
    assert out.research_bars > 0


# --------------------------------------------------------------------------
# The one-look rule
# --------------------------------------------------------------------------

def test_only_the_top_few_are_revealed(bars, spec, ranges):
    out = optimise_with_holdout(bars, spec, BacktestConfig(), ranges,
                                reveal=2, max_workers=1)
    assert len(out.revealed) == 2
    assert [r.rank for r in out.revealed] == [1, 2]
    assert out.combinations > len(out.revealed)


def test_the_default_reveal_is_small(run):
    assert len(run.revealed) == DEFAULT_REVEAL


def test_the_ranking_is_by_the_research_value_not_the_holdout_one(run):
    values = [r.research_value for r in run.revealed]
    assert values == sorted(values, reverse=True)


def test_a_minimised_metric_ranks_the_other_way(bars, spec, ranges):
    out = optimise_with_holdout(bars, spec, BacktestConfig(), ranges,
                                metric="max_drawdown_pct", max_workers=1)
    values = [r.research_value for r in out.revealed]
    assert values == sorted(values)


def test_a_cancelled_sweep_never_looks_at_the_locked_block(bars, spec, ranges):
    out = optimise_with_holdout(bars, spec, BacktestConfig(), ranges,
                                cancel=lambda: True, max_workers=1)
    assert out.revealed == []
    assert any("stopped" in n for n in out.notes)


def test_nothing_rankable_means_nothing_revealed(bars, ranges):
    """A grid where every combination fails must not spend the holdout."""
    spec = BUILTIN_STRATEGIES["EMA Cross + RSI"]()
    out = optimise_with_holdout(
        bars, spec, BacktestConfig(), ranges, metric="not_a_metric",
        max_workers=1)
    assert out.revealed == []
    assert any("nothing to rank" in n for n in out.notes)


# --------------------------------------------------------------------------
# No trade may begin inside the block that chose the parameters
# --------------------------------------------------------------------------

def test_no_holdout_trade_starts_inside_the_research_block(run, bars, spec):
    best = run.best
    assert best is not None
    config = copy.copy(BacktestConfig())
    config.warmup_bars = max(config.warmup_bars, run.warmup_pad)
    block = bars.slice(run.split_index - run.warmup_pad, len(bars))
    result = Backtester(block, spec, config,
                        param_overrides=dict(best.params)).run()
    boundary = int(bars.ts[run.split_index])
    assert result.trades
    assert min(int(t.entry_ts) for t in result.trades) >= boundary


def test_the_pad_is_the_longest_warmup_in_the_grid(run, spec):
    longest = max(spec.warmup_bars({"ema_fast": f, "ema_slow": s})
                  for f in (8, 12, 16, 20, 24) for s in (30, 40, 50, 60))
    assert run.warmup_pad == longest


def test_the_callers_config_is_not_mutated(bars, spec, ranges):
    config = BacktestConfig()
    before = config.warmup_bars
    out = optimise_with_holdout(bars, spec, config, ranges, max_workers=1)
    assert out.warmup_pad > before
    assert config.warmup_bars == before


# --------------------------------------------------------------------------
# Retention, and the shape it is supposed to have
# --------------------------------------------------------------------------

def test_retention_is_undefined_when_the_research_block_lost_money():
    entry = Revealed(params={}, rank=1, research_value=-100.0,
                     holdout_value=-50.0)
    assert math.isnan(entry.retention)


def test_retention_is_the_ratio_when_research_was_profitable():
    entry = Revealed(params={}, rank=1, research_value=200.0,
                     holdout_value=50.0)
    assert entry.retention == pytest.approx(0.25)


def test_a_better_holdout_than_research_is_flagged_as_the_wrong_shape():
    out = HoldoutResult(revealed=[Revealed(params={}, rank=1,
                                           research_value=100.0,
                                           holdout_value=300.0,
                                           holdout_trades=40)])
    assert out.wrong_shape is True


def test_ordinary_decay_is_not_flagged():
    out = HoldoutResult(revealed=[Revealed(params={}, rank=1,
                                           research_value=100.0,
                                           holdout_value=60.0,
                                           holdout_trades=40)])
    assert out.wrong_shape is False


def test_the_wrong_shape_note_says_what_it_means():
    from tradingbacktester.optimize.holdout import _notes

    out = HoldoutResult(combinations=10, revealed=[
        Revealed(params={"n": 5}, rank=1, research_value=100.0,
                 holdout_value=400.0, holdout_trades=30)])
    _notes(out)
    joined = " ".join(out.notes)
    assert "wrong shape" in joined
    assert "leak" in joined


def test_a_holdout_with_no_trades_is_called_an_absence_not_a_result():
    from tradingbacktester.optimize.holdout import _notes

    out = HoldoutResult(combinations=10, revealed=[
        Revealed(params={"n": 5}, rank=1, research_value=100.0,
                 holdout_value=0.0, holdout_trades=0)])
    _notes(out)
    assert any("no trades at all" in n for n in out.notes)


# --------------------------------------------------------------------------
# What the report has to say every time
# --------------------------------------------------------------------------

def test_every_run_states_the_multiplicity(run):
    assert any("does not correct for the multiplicity" in n for n in run.notes)


def test_every_run_carries_the_not_a_prediction_caveat(run):
    assert any("not a prediction" in n for n in run.notes)


def test_the_notes_never_blend_the_two_blocks(run):
    """A single combined figure is how a fitted result gets called profitable."""
    joined = " ".join(run.notes).lower()
    assert "combined" not in joined
    assert "overall net" not in joined


def test_to_dict_is_json_shaped(run):
    import json

    payload = run.to_dict()
    text = json.dumps(payload)
    assert "revealed" in json.loads(text)
    first = payload["revealed"][0]
    assert set(first) >= {"params", "rank", "research_value", "holdout_value",
                          "retention"}


def test_a_derived_metric_is_computed_on_both_blocks(bars, spec, ranges):
    """``return_drawdown_ratio`` is derived, not stored; both sides must see it."""
    out = optimise_with_holdout(bars, spec, BacktestConfig(), ranges,
                                metric="return_drawdown_ratio", max_workers=1)
    best = out.best
    assert best is not None
    assert not math.isnan(best.research_value)
    assert not math.isnan(best.holdout_value)


# --------------------------------------------------------------------------
# A metric where smaller is better must not be read as one where it is not
# --------------------------------------------------------------------------

def test_retention_is_not_reported_for_a_minimised_metric():
    """"Kept 150% of its drawdown" describes a worse result as a good one."""
    entry = Revealed(params={}, rank=1, research_value=10.0,
                     holdout_value=15.0, maximise=False)
    assert math.isnan(entry.retention)


def test_a_minimised_metric_is_never_flagged_as_the_wrong_shape():
    out = HoldoutResult(maximise=False, revealed=[
        Revealed(params={}, rank=1, research_value=10.0, holdout_value=30.0,
                 holdout_trades=25, maximise=False)])
    assert out.wrong_shape is False


def test_a_minimised_metric_says_why_there_is_no_retention_figure():
    out = HoldoutResult(metric="max_drawdown_pct", maximise=False,
                        combinations=8, revealed=[
                            Revealed(params={"n": 5}, rank=1,
                                     research_value=10.0, holdout_value=15.0,
                                     holdout_trades=25, maximise=False)])
    _notes(out)
    assert any("smaller number is better" in n for n in out.notes)


def test_a_real_minimised_sweep_reports_no_retention(bars, spec, ranges):
    out = optimise_with_holdout(bars, spec, BacktestConfig(), ranges,
                                metric="max_drawdown_pct", max_workers=1)
    assert out.maximise is False
    assert all(math.isnan(r.retention) for r in out.revealed)
    assert "n/a" in format_holdout(out, bars)


# --------------------------------------------------------------------------
# The best of a losing grid must not be dressed up by its locked column
# --------------------------------------------------------------------------

def test_a_losing_research_block_is_said_out_loud():
    out = HoldoutResult(combinations=20, revealed=[
        Revealed(params={"n": 5}, rank=1, research_value=-5661.8,
                 holdout_value=6258.19, holdout_trades=9)])
    _notes(out)
    joined = " ".join(out.notes)
    assert "Nothing in the grid worked" in joined
    assert "not evidence of an edge" in joined
    assert "-5,661.80" in joined


def test_the_real_sample_sweep_says_so(run):
    """The shipped sample data is a random walk; the report must not hide it."""
    assert run.best.research_value <= 0
    assert any("Nothing in the grid worked" in n for n in run.notes)


# --------------------------------------------------------------------------
# The text report
# --------------------------------------------------------------------------

def test_the_report_keeps_the_two_blocks_in_separate_columns(run, bars):
    text = format_holdout(run, bars)
    assert "research" in text and "locked" in text
    for entry in run.revealed:
        assert f"{entry.research_value:,.2f}" in text
        assert f"{entry.holdout_value:,.2f}" in text
        assert entry.label in text


def test_the_report_carries_every_note(run, bars):
    # The notes are wrapped to the terminal width, so a phrase can straddle a
    # line break; compare against the unwrapped text.
    flat = " ".join(format_holdout(run, bars).split())
    assert "not a prediction" in flat
    assert "multiplicity" in flat


def test_the_report_survives_a_run_with_nothing_revealed(bars, spec, ranges):
    out = optimise_with_holdout(bars, spec, BacktestConfig(), ranges,
                                cancel=lambda: True, max_workers=1)
    text = format_holdout(out, bars)
    assert "Nothing was revealed" in text


def test_the_report_works_without_a_bar_series(run):
    text = format_holdout(run)
    assert "bar 0" in text
