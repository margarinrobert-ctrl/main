"""Sampled optimisation: the samplers, the runner path, and the two analyses.

The tests that matter are the pair at the top: TPE must do better than random
on a surface it can learn, and every point either sampler hands out must be a
point the grid could have produced.  The first is what makes the method worth
having; the second is what lets the ranking, the heat map and the holdout read
a sampled run without knowing it was one.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from tradingbacktester.core.errors import ParameterError
from tradingbacktester.core.types import BacktestConfig
from tradingbacktester.data.sample import generate_sample_data
from tradingbacktester.optimize.grid import ParameterRange
from tradingbacktester.optimize.holdout import optimise_with_holdout
from tradingbacktester.optimize.ranking import (heatmap, neighbourhood_mean,
                                                rank)
from tradingbacktester.optimize.runner import OptimizationRunner
from tradingbacktester.optimize.sampler import (METHODS, RandomSampler,
                                                TPESampler, describe_method,
                                                grid_size, make_sampler)
from tradingbacktester.optimize.walkforward import walk_forward
from tradingbacktester.strategy.builtin import BUILTIN_STRATEGIES

RANGES = [ParameterRange("a", 0, 40, 1), ParameterRange("b", 0, 40, 1)]


def bowl(p: dict) -> float:
    """Maximum 0 at (28, 13); every other rung is negative."""
    return -((p["a"] - 28) ** 2 + (p["b"] - 13) ** 2)


def _best_after(method: str, trials: int, seeds: int = 12) -> float:
    """Mean best-so-far after ``trials`` evaluations over several seeds."""
    bests = []
    for seed in range(seeds):
        sampler = make_sampler(method, RANGES, maximise=True, seed=seed,
                               budget=trials)
        best = -math.inf
        for _ in range(trials):
            params = sampler.ask(1)[0]
            value = bowl(params)
            sampler.tell(params, value)
            best = max(best, value)
        bests.append(best)
    return float(np.mean(bests))


# --------------------------------------------------------------------------
# The samplers
# --------------------------------------------------------------------------

def test_tpe_beats_random_on_a_surface_it_can_learn():
    """Averaged over seeds, so one lucky random draw cannot decide it."""
    tpe = _best_after("tpe", 60)
    random = _best_after("random", 60)
    assert tpe > random, (tpe, random)
    # Not merely better: close to the optimum, where random is still far off.
    assert tpe > -5.0, tpe


def test_every_sampled_point_is_a_grid_rung():
    ranges = [ParameterRange("x", 0.1, 1.0, 0.1), ParameterRange("n", 5, 50, 5)]
    xs = set(ranges[0].values())
    ns = set(ranges[1].values())
    for method in ("tpe", "random"):
        sampler = make_sampler(method, ranges, seed=3, budget=40)
        for _ in range(40):
            for params in sampler.ask(1):
                assert params["x"] in xs
                assert params["n"] in ns
                sampler.tell(params, float(params["n"]) * params["x"])


def test_a_sampler_never_hands_out_the_same_point_twice():
    for method in ("tpe", "random"):
        sampler = make_sampler(method, RANGES, seed=1, budget=200)
        seen = set()
        for _ in range(50):
            for params in sampler.ask(4):
                key = (params["a"], params["b"])
                assert key not in seen
                seen.add(key)
                sampler.tell(params, bowl(params))


def test_a_sampler_is_deterministic_under_a_seed():
    def sequence(seed: int) -> list[tuple]:
        sampler = make_sampler("tpe", RANGES, seed=seed, budget=30)
        out = []
        for _ in range(30):
            params = sampler.ask(1)[0]
            sampler.tell(params, bowl(params))
            out.append((params["a"], params["b"]))
        return out

    assert sequence(7) == sequence(7)
    assert sequence(7) != sequence(8)


def test_a_small_space_is_exhausted_cleanly():
    sampler = make_sampler("tpe", [ParameterRange("x", 1, 3, 1)], seed=0, budget=10)
    got = []
    while True:
        batch = sampler.ask(5)
        if not batch:
            break
        for params in batch:
            sampler.tell(params, 0.0)
            got.append(params["x"])
    assert sorted(got) == [1, 2, 3]
    assert sampler.exhausted
    assert sampler.ask(1) == []


def test_a_failed_trial_is_told_as_the_worst_possible_result():
    sampler = make_sampler("tpe", RANGES, maximise=True, seed=1, budget=20)
    params = sampler.ask(1)[0]
    sampler.tell(params, float("nan"))
    assert sampler.observed[-1][1] == -math.inf
    minimiser = make_sampler("tpe", RANGES, maximise=False, seed=1, budget=20)
    params = minimiser.ask(1)[0]
    minimiser.tell(params, None)
    assert minimiser.observed[-1][1] == math.inf


def test_startup_trials_are_capped_by_the_budget():
    assert TPESampler(RANGES, budget=12).n_startup == 3
    assert TPESampler(RANGES, budget=200).n_startup == 10
    assert TPESampler(RANGES).n_startup == 10


def test_unknown_method_is_refused_by_name():
    with pytest.raises(ParameterError) as exc:
        make_sampler("annealing", RANGES)
    assert "grid, tpe or random" in str(exc.value)
    assert set(METHODS) == {"grid", "tpe", "random"}
    assert "Bayesian" in describe_method("tpe")


def test_grid_size_is_the_product_of_the_rungs():
    assert grid_size(RANGES) == 41 * 41
    assert grid_size([ParameterRange("x", 0.1, 1.0, 0.1)]) == 10


def test_random_sampler_is_uniform_over_the_unasked_space():
    sampler = RandomSampler([ParameterRange("x", 1, 4, 1)], True, 0)
    got = sorted(p["x"] for p in sampler.ask(4))
    assert got == [1, 2, 3, 4]


# --------------------------------------------------------------------------
# Through the runner
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def bars():
    return generate_sample_data("NQ", "1h", n_bars=2500, seed=13)


@pytest.fixture
def spec():
    return BUILTIN_STRATEGIES["EMA Cross + RSI"]()


WIDE = [ParameterRange("ema_fast", 5, 40, 1), ParameterRange("ema_slow", 30, 120, 2)]


def test_run_sampled_produces_rows_every_analysis_can_read(bars, spec):
    runner = OptimizationRunner(bars, spec, BacktestConfig(), max_workers=1)
    results = runner.run_sampled(WIDE, trials=20, method="tpe",
                                 metric="net_profit", seed=1)
    assert results.sampled
    assert results.method == "tpe"
    assert results.trials == 20
    assert results.space == 36 * 46
    assert results.total_combinations == 20
    assert len(results.rows) == 20
    assert len({(r.params["ema_fast"], r.params["ema_slow"]) for r in results.rows}) == 20
    ranked = rank(results, "net_profit")
    assert ranked
    surface = heatmap(results, "net_profit")
    assert surface is not None
    assert int(np.isfinite(surface.values).sum()) == results.completed
    assert math.isfinite(neighbourhood_mean(results, ranked[0], "net_profit"))
    assert "Bayesian" in results.summary_line()


def test_run_sampled_on_threads_matches_the_sequential_rows(bars, spec):
    """The pool changes how fast, never what: same seed, same combinations."""
    one = OptimizationRunner(bars, spec, BacktestConfig(), max_workers=1)
    two = OptimizationRunner(bars, spec, BacktestConfig(), max_workers=2)
    a = one.run_sampled(WIDE, trials=12, method="random", seed=5)
    b = two.run_sampled(WIDE, trials=12, method="random", seed=5)
    key = lambda r: (r.params["ema_fast"], r.params["ema_slow"])  # noqa: E731
    assert sorted(map(key, a.rows)) == sorted(map(key, b.rows))
    by_key_a = {key(r): r.value("net_profit") for r in a.rows}
    by_key_b = {key(r): r.value("net_profit") for r in b.rows}
    assert by_key_a == by_key_b


def test_a_budget_covering_the_space_runs_as_a_grid_and_says_so(bars, spec):
    runner = OptimizationRunner(bars, spec, BacktestConfig(), max_workers=1)
    results = runner.run_sampled([ParameterRange("ema_fast", 10, 12, 1)],
                                 trials=50, method="tpe")
    assert results.method == "grid"
    assert not results.sampled
    assert len(results.rows) == 3
    assert any("covers the whole space" in w for w in results.warnings)


def test_run_sampled_refuses_an_empty_budget(bars, spec):
    runner = OptimizationRunner(bars, spec, BacktestConfig(), max_workers=1)
    with pytest.raises(ParameterError):
        runner.run_sampled(WIDE, trials=0, method="tpe")


def test_run_sampled_can_be_cancelled(bars, spec):
    runner = OptimizationRunner(bars, spec, BacktestConfig(), max_workers=1)
    calls = {"n": 0}

    def cancel() -> bool:
        calls["n"] += 1
        return calls["n"] > 3

    results = runner.run_sampled(WIDE, trials=40, method="random", cancel=cancel)
    assert results.cancelled
    assert len(results.rows) < 40


# --------------------------------------------------------------------------
# Holdout and walk-forward
# --------------------------------------------------------------------------

def test_holdout_with_a_sampler_prices_trials_not_the_grid(bars, spec):
    result = optimise_with_holdout(bars, spec, BacktestConfig(), WIDE,
                                   method="tpe", trials=15, reveal=2,
                                   max_workers=1)
    assert result.method == "tpe"
    assert result.space == 36 * 46
    assert result.combinations == 15
    assert len(result.revealed) == 2
    note = result.notes[0]
    assert "15 of the 1,656 possible combinations" in note
    assert "Bayesian" in note
    assert "does not make what it finds any more likely to be real" in note
    assert result.to_dict()["method"] == "tpe"


def test_holdout_with_a_grid_is_unchanged(bars, spec):
    small = [ParameterRange("ema_fast", 10, 20, 5)]
    result = optimise_with_holdout(bars, spec, BacktestConfig(), small,
                                   reveal=1, max_workers=1)
    assert result.method == "grid"
    assert result.combinations == 3 == result.space
    assert "3 combinations were ranked" in result.notes[0]


def test_walk_forward_with_a_sampler_per_window(bars, spec):
    result = walk_forward(bars, spec, BacktestConfig(), WIDE, folds=3,
                          method="random", trials=6, minimum_trades=1)
    assert result.method == "random"
    assert result.combinations == 6
    assert result.space == 36 * 46
    assert len(result.windows) == 3
    assert all(w.params for w in result.windows if not w.error)


def test_walk_forward_grid_is_unchanged(bars, spec):
    small = [ParameterRange("ema_fast", 10, 20, 5)]
    result = walk_forward(bars, spec, BacktestConfig(), small, folds=3,
                          minimum_trades=1)
    assert result.method == "grid"
    assert result.combinations == 3 == result.space


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------

def test_cli_exposes_method_and_trials():
    from tradingbacktester.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["optimize", "x", "--data", "d", "--method", "tpe",
                              "--trials", "30"])
    assert args.method == "tpe" and args.trials == 30
    args = parser.parse_args(["walkforward", "x", "--data", "d", "--method",
                              "random", "--trials", "8"])
    assert args.method == "random" and args.trials == 8
    with pytest.raises(SystemExit):
        parser.parse_args(["optimize", "x", "--data", "d", "--method", "bogus"])


def test_an_error_inside_the_pooled_search_body_propagates_once(bars, spec):
    """The executor helper must not answer a caller's exception with a second
    yield -- which is what a ``yield`` inside a start-up ``try`` would do."""
    runner = OptimizationRunner(bars, spec, BacktestConfig(), max_workers=2)

    class Boom(RuntimeError):
        pass

    with pytest.raises(Boom):
        with runner._executor(2):
            raise Boom("from the body")
