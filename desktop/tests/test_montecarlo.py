"""Resampling a trade sequence.

The tests here check properties rather than numbers wherever the number would
be a restatement of the implementation: a shuffle must not move the final
equity, a bootstrap must, a block bootstrap must find the losing streak that a
plain one breaks up. The arithmetic that *can* be done on paper — the drawdown
of a hand-written path, the longest run under water — is asserted exactly.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from tradingbacktester.analytics.montecarlo import (RELIABLE_TRADES,
                                                    format_monte_carlo,
                                                    resample_result,
                                                    resample_trades,
                                                    suggested_block)
from tradingbacktester.core.errors import (InsufficientDataError,
                                           ParameterError)


@pytest.fixture
def winning_trades():
    """220 trades, 55% winners of +200 against losers of -180."""
    rng = np.random.default_rng(4)
    return np.where(rng.random(220) < 0.55, 200.0, -180.0)


# --------------------------------------------------------------------------
# The arithmetic of one path
# --------------------------------------------------------------------------

def test_observed_path_is_the_backtest_itself():
    """+100, -300, +50 from 1,000: ends at 850, worst fall 300 from 1,100."""
    result = resample_trades([100.0, -300.0, 50.0], 1000.0, draws=10)
    assert result.observed.final_equity == pytest.approx(850.0)
    assert result.observed.total_return_pct == pytest.approx(-15.0)
    assert result.observed.max_drawdown == pytest.approx(300.0)
    assert result.observed.max_drawdown_pct == pytest.approx(300 / 1100 * 100)
    # Under water from trade 2 to the end: two trades.
    assert result.observed.longest_drawdown_trades == 2


def test_a_loss_on_the_first_trade_is_a_drawdown_from_the_opening_balance():
    """The account's own starting capital is the first peak, not the first trade."""
    result = resample_trades([-250.0, 100.0], 1000.0, draws=10)
    assert result.observed.max_drawdown == pytest.approx(250.0)


def test_compounding_uses_the_equity_each_trade_was_opened_against():
    """+10% then -10% from 1,000 is 990, not 1,000."""
    result = resample_trades([100.0, -110.0], 1000.0, draws=10, compounded=True,
                             returns=[0.10, -0.10])
    assert result.observed.final_equity == pytest.approx(990.0)


def test_compounded_needs_the_returns():
    with pytest.raises(ParameterError):
        resample_trades([100.0, -50.0], 1000.0, compounded=True)


def test_a_run_with_one_trade_is_refused():
    with pytest.raises(InsufficientDataError):
        resample_trades([100.0], 1000.0)


def test_zero_capital_is_refused_because_every_percentage_divides_by_it():
    with pytest.raises(ParameterError):
        resample_trades([100.0, -50.0], 0.0)


def test_an_unknown_method_names_the_ones_that_exist():
    with pytest.raises(ParameterError) as exc:
        resample_trades([100.0, -50.0], 1000.0, method="jackknife")
    for known in ("shuffle", "bootstrap", "block"):
        assert known in str(exc.value)


# --------------------------------------------------------------------------
# What each resampler is for
# --------------------------------------------------------------------------

def test_shuffling_keeps_the_final_equity_and_moves_only_the_path(winning_trades):
    """The same trades in a different order end in the same place."""
    result = resample_trades(winning_trades, 100_000.0, method="shuffle",
                             draws=500)
    assert np.allclose(result.final_equity, result.observed.final_equity)
    assert result.max_drawdown.std() > 0, "the path must vary"
    assert result.losing_probability == 0.0


def test_bootstrapping_moves_the_final_equity(winning_trades):
    """A different sample of trades ends somewhere else."""
    result = resample_trades(winning_trades, 100_000.0, method="bootstrap",
                             draws=1000)
    assert result.final_equity.std() > 0
    assert 0.0 < result.losing_probability < 0.5
    low, high = np.percentile(result.final_equity, [5, 95])
    assert low < result.observed.final_equity < high


def test_a_shuffle_is_a_permutation_and_a_bootstrap_is_not():
    """Directly: the multiset of trades must survive a shuffle unchanged."""
    from tradingbacktester.analytics.montecarlo import _indices

    rng = np.random.default_rng(0)
    shuffled = _indices("shuffle", rng, 50, 40, 3)
    assert shuffled.shape == (50, 40)
    for row in shuffled:
        assert sorted(row.tolist()) == list(range(40))
    drawn = _indices("bootstrap", rng, 200, 40, 3)
    assert any(len(set(row.tolist())) < 40 for row in drawn)


def test_block_sampling_draws_contiguous_runs():
    from tradingbacktester.analytics.montecarlo import _indices

    rng = np.random.default_rng(0)
    index = _indices("block", rng, 100, 60, 6)
    assert index.shape == (100, 60)
    # Every position inside a block follows the one before it.
    for row in index:
        blocks = row.reshape(10, 6)
        assert np.all(np.diff(blocks, axis=1) == 1)


def test_block_bootstrap_finds_a_losing_streak_a_plain_one_breaks_up():
    """The whole reason the block method exists.

    A trade sequence with genuine clustering — a long run of losses in the
    middle — has a drawdown that survives block sampling and is destroyed by
    sampling trades independently.
    """
    trades = ([120.0] * 120) + ([-100.0] * 60) + ([120.0] * 120)
    plain = resample_trades(trades, 100_000.0, method="bootstrap", draws=2000,
                            seed=7)
    blocked = resample_trades(trades, 100_000.0, method="block", draws=2000,
                              block_size=30, seed=7)
    assert blocked.drawdown_at(95) > plain.drawdown_at(95) * 1.5


def test_suggested_block_grows_with_the_sample_but_slowly():
    assert suggested_block(8) == 2
    assert suggested_block(1000) == 10
    assert suggested_block(27) < suggested_block(1000)


# --------------------------------------------------------------------------
# The distribution as reported
# --------------------------------------------------------------------------

def test_the_backtest_sits_where_the_rank_says_it_does(winning_trades):
    result = resample_trades(winning_trades, 100_000.0, method="bootstrap",
                             draws=2000)
    rank = result.rank_of_observed()
    assert rank == pytest.approx(
        float(np.mean(result.final_equity <= result.observed.final_equity)))
    assert 0.0 <= rank <= 1.0


def test_ruin_counts_paths_that_went_below_the_level_at_any_point():
    """A path that recovers still counts: it was below the level on the way."""
    # -900 and +100 from 1,000 against a level of 500. Either order dips below
    # it — 100 then 200, or 1,100 then 200 — so every draw must be counted,
    # even though every draw also ends at 200.
    result = resample_trades([-900.0, 100.0], 1000.0, method="shuffle",
                             draws=200, ruin_level=500.0)
    assert result.ruin_probability == 1.0
    assert all(f == pytest.approx(200.0) for f in result.final_equity)


def test_a_path_that_never_reaches_the_level_is_not_counted():
    result = resample_trades([-100.0, 200.0], 1000.0, method="shuffle",
                             draws=200, ruin_level=500.0)
    assert result.ruin_probability == 0.0


def test_the_default_ruin_level_is_half_the_account():
    result = resample_trades([100.0, -50.0], 10_000.0, draws=10)
    assert result.ruin_level == pytest.approx(5000.0)


def test_longest_run_under_water_is_counted_in_trades():
    from tradingbacktester.analytics.montecarlo import _longest_true_run

    mask = np.array([[True, True, False, True, True, True, False],
                     [False, False, False, False, False, False, False],
                     [True, True, True, True, True, True, True]])
    assert _longest_true_run(mask).tolist() == [3, 0, 7]


def test_chunking_does_not_change_the_answer(monkeypatch, winning_trades):
    """The draws are processed in chunks; the totals must not depend on the size."""
    import tradingbacktester.analytics.montecarlo as mc

    monkeypatch.setattr(mc, "_CHUNK", 1000)
    whole = mc.resample_trades(winning_trades, 100_000.0, draws=600, seed=3)
    monkeypatch.setattr(mc, "_CHUNK", 7)
    split = mc.resample_trades(winning_trades, 100_000.0, draws=600, seed=3)
    assert whole.final_equity.size == split.final_equity.size == 600
    # A different chunking draws different random numbers, so compare the
    # distribution rather than the draws.
    assert whole.final_equity.mean() == pytest.approx(
        split.final_equity.mean(), rel=0.02)


def test_the_same_seed_gives_the_same_distribution(winning_trades):
    a = resample_trades(winning_trades, 100_000.0, draws=500, seed=99)
    b = resample_trades(winning_trades, 100_000.0, draws=500, seed=99)
    assert np.array_equal(a.final_equity, b.final_equity)


def test_a_short_run_is_labelled_not_hidden():
    result = resample_trades([100.0, -50.0, 70.0, -20.0], 10_000.0, draws=200)
    assert result.trades < RELIABLE_TRADES
    assert any("too few" in note for note in result.notes)


def _flat(text: str) -> str:
    """The report with its line wrapping removed, for substring assertions."""
    return " ".join(text.split())


def test_the_report_says_what_it_cannot_tell_you(winning_trades):
    result = resample_trades(winning_trades, 100_000.0, draws=500)
    text = format_monte_carlo(result)
    assert "cannot tell you whether the strategy has an edge" in _flat(text)
    assert _flat(result.verdict()) in _flat(text)
    assert max(len(line) for line in text.splitlines()) <= 78


def test_the_shuffle_report_does_not_offer_a_meaningless_rank(winning_trades):
    """Every shuffled draw ends at the same equity, so that rank says nothing."""
    text = format_monte_carlo(
        resample_trades(winning_trades, 100_000.0, method="shuffle", draws=300))
    assert "it finished better than" not in text
    assert "its drawdown was milder than" in text


def test_result_is_json_serialisable(winning_trades):
    result = resample_trades(winning_trades, 100_000.0, draws=300)
    payload = json.loads(json.dumps(result.to_dict()))
    assert payload["draws"] == 300
    assert set(payload["final_equity"]) == {"5", "25", "50", "75", "95"}
    assert payload["verdict"]


def test_cancelling_stops_the_run(winning_trades):
    from tradingbacktester.core.errors import CancelledError

    class Token:
        cancelled = True

    with pytest.raises(CancelledError):
        resample_trades(winning_trades, 100_000.0, draws=5000, cancel=Token())


# --------------------------------------------------------------------------
# Against a real backtest
# --------------------------------------------------------------------------

def test_resampling_a_real_backtest_agrees_with_its_own_metrics():
    """The observed path must reproduce the run it came from."""
    from tradingbacktester.core.types import BacktestConfig
    from tradingbacktester.data.sample import generate_sample_data
    from tradingbacktester.engine.backtester import Backtester
    from tradingbacktester.strategy.builtin import BUILTIN_STRATEGIES

    bars = generate_sample_data("NQ", "1h", n_bars=3000, seed=5)
    spec = BUILTIN_STRATEGIES["EMA Cross + RSI"]()
    config = BacktestConfig(starting_capital=100_000.0)
    config.exits, config.execution = spec.exits, spec.execution
    config.session, config.costs, config.risk = spec.session, spec.costs, spec.risk
    run = Backtester(bars, spec, config).run()
    assert run.trades

    result = resample_result(run, method="bootstrap", draws=500)
    assert result.trades == len(run.trades)
    net = sum(t.net_pnl for t in run.trades)
    assert result.observed.final_equity == pytest.approx(100_000.0 + net)
    assert result.starting_capital == pytest.approx(100_000.0)
    assert math.isfinite(result.observed.max_drawdown)

    compounded = resample_result(run, draws=200, compounded=True)
    assert compounded.compounded
    assert any("Compounded" in note for note in compounded.notes)


def test_a_backtest_with_no_trades_is_refused_kindly():
    from tradingbacktester.engine.results import BacktestResult

    with pytest.raises(InsufficientDataError) as exc:
        resample_result(BacktestResult())
    assert "no trades" in str(exc.value)


def test_a_losing_backtest_is_not_described_as_having_a_profit():
    """The verdict must not talk about "the backtest's profit" when there is none."""
    losing = [-100.0] * 40 + [80.0] * 40
    result = resample_trades(losing, 100_000.0, method="bootstrap", draws=500)
    assert result.observed.final_equity < result.starting_capital
    verdict = result.verdict()
    assert "profit" not in verdict
    assert "lost money" in verdict
