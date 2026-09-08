"""The two measurements that price the search rather than the winner.

Most of these are calibration tests: given data with a known answer, does the
statistic report it? A deflation that never deflates and a cross-validation
that never fails are both worse than not having them, because they look like
rigour.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from tradingbacktester.finder.overfit import (BlockCollector, DEFAULT_BLOCKS,
                                              MAX_CANDIDATES,
                                              MIN_TRADES_PER_BLOCK,
                                              deflated_sharpe,
                                              expected_max_sharpe, norm_cdf,
                                              norm_ppf,
                                              probability_of_overfitting)


# --------------------------------------------------------------------------
# The two normal functions
# --------------------------------------------------------------------------

@pytest.mark.parametrize("p", [1e-12, 1e-6, 0.001, 0.02424, 0.02425, 0.02426,
                               0.1, 0.3, 0.5, 0.7, 0.9, 0.97574, 0.97575,
                               0.97576, 0.999, 1 - 1e-9])
def test_the_inverse_normal_really_inverts_the_normal(p):
    """Including either side of both of Acklam's branch cut-offs."""
    assert norm_cdf(norm_ppf(p)) == pytest.approx(p, abs=1e-13, rel=1e-12)


def test_the_inverse_normal_matches_published_quantiles():
    assert norm_ppf(0.975) == pytest.approx(1.9599639845400545, abs=1e-12)
    assert norm_ppf(0.995) == pytest.approx(2.5758293035489004, abs=1e-12)
    assert norm_ppf(0.5) == pytest.approx(0.0, abs=1e-15)
    assert norm_ppf(0.025) == pytest.approx(-1.9599639845400545, abs=1e-12)


def test_the_inverse_normal_is_odd_about_a_half():
    for p in (0.01, 0.2, 0.44):
        assert norm_ppf(p) == pytest.approx(-norm_ppf(1.0 - p), abs=1e-12)


def test_degenerate_probabilities_are_infinities_not_exceptions():
    assert norm_ppf(0.0) == -math.inf
    assert norm_ppf(1.0) == math.inf
    assert math.isnan(norm_ppf(math.nan))


# --------------------------------------------------------------------------
# The best-of-N benchmark
# --------------------------------------------------------------------------

def test_the_benchmark_grows_with_the_number_of_tries():
    """The whole point: trying more things raises the bar."""
    values = [expected_max_sharpe(n, 1.0) for n in (10, 100, 1_000, 10_000)]
    assert values == sorted(values)
    assert values[0] > 0


def test_the_benchmark_grows_like_the_root_of_log_n():
    """Below sqrt(2 ln N), which is the crude bound it refines."""
    for n in (100, 1_000, 10_000):
        crude = math.sqrt(2 * math.log(n))
        assert 0.75 * crude < expected_max_sharpe(n, 1.0) < crude


def test_the_benchmark_scales_with_the_spread_across_tries():
    """A search whose trials all scored the same has nothing to deflate."""
    assert expected_max_sharpe(1_000, 4.0) == pytest.approx(
        2.0 * expected_max_sharpe(1_000, 1.0))
    assert expected_max_sharpe(1_000, 0.0) == 0.0


def test_one_try_has_no_multiplicity():
    assert expected_max_sharpe(1, 1.0) == 0.0
    assert expected_max_sharpe(0, 1.0) == 0.0


# --------------------------------------------------------------------------
# The deflated Sharpe ratio
# --------------------------------------------------------------------------

def test_a_lucky_winner_of_a_big_search_is_deflated_away():
    """The number this exists for.

    A Sharpe that looks strong against zero, from a search big enough that the
    best of it would look that strong anyway, must not survive.
    """
    rng = np.random.default_rng(4)
    returns = rng.normal(0.08, 1.0, 300)
    lonely = deflated_sharpe(returns, trials=1, trial_variance=0.0)
    crowded = deflated_sharpe(returns, trials=20_000, trial_variance=0.02)
    assert lonely.probability > crowded.probability
    assert crowded.benchmark > lonely.benchmark
    assert not crowded.significant


def test_a_strong_edge_survives_even_a_large_search():
    """If nothing ever passed, the statistic would be decoration."""
    rng = np.random.default_rng(4)
    returns = rng.normal(0.8, 1.0, 500)
    result = deflated_sharpe(returns, trials=10_000, trial_variance=0.02)
    assert result.clears
    assert result.significant
    assert result.probability > 0.99


def test_negative_skew_is_charged_for():
    """A strategy that wins small and often and loses hugely and rarely.

    Its Sharpe flatters it, and the deflation is where that gets priced.
    """
    kind = np.full(400, 0.30)
    nasty = np.full(400, 0.30)
    nasty[::40] = -11.0                      # ten rare, large losses
    assert nasty.mean() < kind.mean()

    plain = deflated_sharpe(kind + np.linspace(-0.01, 0.01, 400),
                            trials=500, trial_variance=0.01)
    skewed = deflated_sharpe(nasty, trials=500, trial_variance=0.01)
    assert skewed.skew < -1.0
    assert skewed.kurtosis > 3.0
    assert skewed.probability < plain.probability


def test_a_sharpe_needs_two_trades_to_exist():
    result = deflated_sharpe(np.array([5.0]), trials=100, trial_variance=1.0)
    assert result.observations == 1
    assert result.probability == 0.0
    assert "not enough trades" in result.describe()


def test_a_constant_return_series_has_no_sharpe():
    """Zero variance is not an infinite Sharpe."""
    result = deflated_sharpe(np.full(50, 3.0), trials=100, trial_variance=1.0)
    assert result.sharpe == 0.0
    assert math.isfinite(result.probability)


def test_repricing_for_a_bigger_search_equals_computing_it_that_way():
    """A sweep's finding is really selected out of the whole grid."""
    rng = np.random.default_rng(11)
    returns = rng.normal(0.05, 1.0, 400)
    direct = deflated_sharpe(returns, trials=9_000, trial_variance=0.03)
    repriced = deflated_sharpe(returns, trials=1_000, trial_variance=0.03
                               ).redeflate(9_000, 0.03)
    assert repriced.probability == pytest.approx(direct.probability, abs=1e-15)
    assert repriced.benchmark == pytest.approx(direct.benchmark, abs=1e-15)
    assert repriced.trials == 9_000


def test_repricing_for_a_bigger_search_can_only_lower_the_result():
    rng = np.random.default_rng(12)
    small = deflated_sharpe(rng.normal(0.2, 1.0, 300), trials=100,
                            trial_variance=0.05)
    assert small.redeflate(50_000, 0.05).probability <= small.probability


# --------------------------------------------------------------------------
# The probability of backtest overfitting
# --------------------------------------------------------------------------

def _matrices(values: np.ndarray):
    """``(blocks, candidates, per_block)`` of returns to the three matrices."""
    counts = np.full(values.shape[:2], float(values.shape[2]))
    return counts, values.sum(axis=2), (values ** 2).sum(axis=2)


def test_pure_noise_reports_a_coin_flip():
    """The calibration test. Selection on noise generalises half the time."""
    rng = np.random.default_rng(0)
    values = rng.normal(0.0, 1.0, size=(DEFAULT_BLOCKS, 400, 40))
    result = probability_of_overfitting(*_matrices(values), DEFAULT_BLOCKS)
    assert result.ran
    assert 0.35 < result.probability < 0.65, (
        f"selection on noise reported PBO {result.probability:.3f}, which is "
        f"not a coin flip")
    assert result.splits == math.comb(DEFAULT_BLOCKS, DEFAULT_BLOCKS // 2)


def test_a_genuine_edge_is_selected_reliably():
    rng = np.random.default_rng(0)
    values = rng.normal(0.0, 1.0, size=(DEFAULT_BLOCKS, 200, 40))
    values[:, 0, :] += 0.9                      # one candidate really is better
    result = probability_of_overfitting(*_matrices(values), DEFAULT_BLOCKS)
    assert result.probability < 0.05
    assert result.median_logit > 1.0
    assert not result.overfit


def test_an_edge_living_in_one_period_is_caught():
    """The failure this is really for: a rule made by one good stretch."""
    rng = np.random.default_rng(3)
    values = rng.normal(0.0, 1.0, size=(DEFAULT_BLOCKS, 200, 40))
    values[0, 7, :] += 2.0                      # brilliant once, ordinary after
    result = probability_of_overfitting(*_matrices(values), DEFAULT_BLOCKS)
    assert result.probability > 0.5, (
        "a rule whose whole edge came from one block was not caught: PBO "
        f"{result.probability:.3f}")
    assert result.probability_of_loss > 0.5


def test_cross_validation_is_blind_to_which_half_the_edge_was_in():
    """A limitation, asserted so nobody later mistakes it for a defence.

    The splits are combinatorial, not sequential: a candidate that was good in
    the first six blocks and absent in the last six has, on average, three of
    its good blocks in any testing half, so it still tests well. Measured
    across the whole range, the probability of overfitting responds to how
    CONCENTRATED an edge is (one block of twelve gives 0.65) and not at all to
    whether the good blocks came early or late (six of twelve gives 0.001,
    however they are arranged).

    That failure -- an edge that was real and then stopped being real -- is
    what the sequential locked block catches, and it is why this application
    keeps both. Neither one subsumes the other, and reading this number as
    protection against regime change would be a mistake.
    """
    rng = np.random.default_rng(3)

    def pbo(good_blocks):
        values = rng.normal(0.0, 1.0, size=(DEFAULT_BLOCKS, 200, 40))
        values[good_blocks, 7, :] += 2.0
        return probability_of_overfitting(*_matrices(values),
                                          DEFAULT_BLOCKS).probability

    half = DEFAULT_BLOCKS // 2
    first_half = pbo(list(range(half)))
    last_half = pbo(list(range(half, DEFAULT_BLOCKS)))
    scattered = pbo(list(range(0, DEFAULT_BLOCKS, 2)))
    assert first_half < 0.05 and last_half < 0.05 and scattered < 0.05, (
        "the measurement is responding to WHERE the good blocks are, which "
        "the combinatorial construction says it cannot be")


def test_identical_candidates_are_a_coin_flip_not_a_win():
    """Ties shared, or a grid of clones would report perfect selection."""
    values = np.tile(np.linspace(-1.0, 1.0, 40), (DEFAULT_BLOCKS, 50, 1))
    result = probability_of_overfitting(*_matrices(values), DEFAULT_BLOCKS)
    assert result.ran
    assert result.probability == pytest.approx(1.0, abs=1e-9) or \
        result.median_logit == pytest.approx(0.0, abs=1e-9)


def test_degradation_and_probability_of_loss_are_reported():
    rng = np.random.default_rng(6)
    values = rng.normal(0.0, 1.0, size=(DEFAULT_BLOCKS, 300, 40))
    result = probability_of_overfitting(*_matrices(values), DEFAULT_BLOCKS)
    assert result.degradation < 0, "the in-sample winner should decay"
    assert 0.0 <= result.probability_of_loss <= 1.0
    assert "negative" in result.describe()


def test_too_few_blocks_is_reported_not_raised():
    values = np.zeros((2, 10, 5))
    result = probability_of_overfitting(*_matrices(values), 2)
    assert not result.ran
    assert "at least four blocks" in result.reason
    assert "not measured" in result.describe()


def test_an_odd_block_count_is_rounded_down_to_even():
    """Half of thirteen is not a set of blocks."""
    rng = np.random.default_rng(2)
    values = rng.normal(0.0, 1.0, size=(12, 60, 30))
    result = probability_of_overfitting(*_matrices(values), 13)
    assert result.ran
    assert result.blocks == 12


def test_a_candidate_that_sat_out_a_block_is_dropped_not_imputed():
    """Sitting out a block is not breaking even in it."""
    rng = np.random.default_rng(7)
    values = rng.normal(0.0, 1.0, size=(DEFAULT_BLOCKS, 30, 20))
    counts, sums, squares = _matrices(values)
    counts[3, 5] = 0.0                          # candidate 5 never traded there
    counts[7, 5] = 1.0                          # and barely traded here
    result = probability_of_overfitting(counts, sums, squares, DEFAULT_BLOCKS)
    assert result.candidates == 29


def test_one_usable_candidate_is_not_a_ranking():
    rng = np.random.default_rng(8)
    values = rng.normal(0.0, 1.0, size=(DEFAULT_BLOCKS, 4, 20))
    counts, sums, squares = _matrices(values)
    counts[0, 1:] = 0.0
    result = probability_of_overfitting(counts, sums, squares, DEFAULT_BLOCKS)
    assert not result.ran
    assert "nothing to rank against" in result.reason


def test_mismatched_input_shapes_are_a_programming_error():
    with pytest.raises(ValueError):
        probability_of_overfitting(np.zeros((12, 5)), np.zeros((12, 6)),
                                   np.zeros((12, 5)))


# --------------------------------------------------------------------------
# Collecting the matrices from a search
# --------------------------------------------------------------------------

def test_the_collector_cuts_the_research_block_only():
    """A block boundary inside the locked data would deal it into training."""
    collector = BlockCollector.over(split=1200, total=2000)
    assert collector is not None
    assert collector.blocks == DEFAULT_BLOCKS
    assert (collector.block_of[:1200] >= 0).all()
    assert (collector.block_of[1200:] == -1).all()


def test_the_collector_blocks_are_contiguous_and_in_time_order():
    """Interleaved blocks would read every serial correlation as skill."""
    collector = BlockCollector.over(split=1200, total=1200)
    ids = collector.block_of[:1200]
    assert (np.diff(ids) >= 0).all(), "blocks are not in time order"
    assert set(ids.tolist()) == set(range(DEFAULT_BLOCKS))


def test_a_research_block_too_short_to_cut_gives_no_collector():
    assert BlockCollector.over(split=10, total=100) is None
    assert BlockCollector.over(split=1000, blocks=2, total=1000) is None


def test_the_collector_reproduces_the_statistics_it_stands_in_for():
    """Three bincounts must equal the mean and variance of the trades."""
    rng = np.random.default_rng(5)
    n = 1200
    collector = BlockCollector.over(split=n, total=n)
    values = rng.normal(1.0, 3.0, n)
    taken = rng.random(n) < 0.3
    collector.add(taken, values)

    assert collector.counts[0].sum() == taken.sum()
    assert collector.sums[0].sum() == pytest.approx(values[taken].sum())
    assert collector.squares[0].sum() == pytest.approx(
        (values[taken] ** 2).sum())


def test_the_collector_ignores_trades_outside_the_research_block():
    collector = BlockCollector.over(split=600, total=1000)
    values = np.ones(1000)
    taken = np.zeros(1000, dtype=bool)
    taken[500:800] = True                       # 100 of them are locked away
    collector.add(taken, values)
    assert collector.counts[0].sum() == 100


def test_a_candidate_that_never_traded_still_takes_a_column():
    """Dropping it here would misalign every later candidate's label."""
    collector = BlockCollector.over(split=1200, total=1200)
    collector.add(np.zeros(1200, dtype=bool), np.ones(1200), "silent")
    collector.add(np.ones(1200, dtype=bool), np.ones(1200), "busy")
    assert len(collector.counts) == 2
    assert collector.labels == ["silent", "busy"]
    assert collector.counts[0].sum() == 0


def test_an_empty_collector_reports_rather_than_raises():
    collector = BlockCollector.over(split=1200, total=1200)
    result = collector.result()
    assert not result.ran
    assert "no candidates" in result.reason


# --------------------------------------------------------------------------
# What the search does with them
# --------------------------------------------------------------------------

def test_a_real_search_measures_both_and_says_so():
    from tradingbacktester.finder import find_strategies, format_report
    from tradingbacktester.finder.styles import style

    from tests.test_finder import _planted

    report = find_strategies(_planted(n=30_000, strength=9.0, seed=5),
                             style("intraday"), control_draws=50,
                             validate="quick")
    assert report.overfitting is not None and report.overfitting.ran
    assert report.overfitting.blocks == DEFAULT_BLOCKS

    text = format_report(report)
    assert "Probability of backtest overfitting" in text
    if report.shortlist:
        assert report.shortlist[0].deflated is not None
        assert "deflated Sharpe" in text


def test_a_planted_edge_is_selected_reliably_by_the_real_search():
    """End to end: a real edge should give a low probability of overfitting."""
    from tradingbacktester.finder import find_strategies
    from tradingbacktester.finder.styles import style

    from tests.test_finder import _planted

    report = find_strategies(_planted(n=30_000, strength=9.0, seed=5),
                             style("intraday"), control_draws=50,
                             validate="quick")
    assert report.overfitting.probability < 0.5, (
        "a strongly planted edge reported the search as overfit: PBO "
        f"{report.overfitting.probability:.3f}")


def test_the_measurements_reach_the_serialised_form():
    from tradingbacktester.finder import find_strategies
    from tradingbacktester.finder.styles import style

    from tests.test_finder import _planted

    report = find_strategies(_planted(n=30_000, strength=9.0, seed=5),
                             style("intraday"), control_draws=50,
                             validate="quick")
    blob = report.to_dict()
    assert blob["overfitting"]["ran"] is True
    assert 0.0 <= blob["overfitting"]["pbo"] <= 1.0
    if blob["shortlist"]:
        deflated = blob["shortlist"][0]["deflated_sharpe"]
        assert deflated is not None
        assert 0.0 <= deflated["deflated_sharpe"] <= 1.0
        assert deflated["trials"] == report.tested


def test_the_grid_reprices_every_sharpe_for_the_whole_grid():
    """A sweep's trial count is the wrong benchmark for a grid's finding."""
    from tradingbacktester.finder.autosearch import auto_search

    from tests.test_finder import _planted

    report = auto_search(_planted(n=30_000, strength=9.0, seed=5),
                         styles=("intraday",), control_draws=50,
                         validate="quick")
    priced = [f for f in report.survivors if f.deflated is not None]
    assert priced, "no survivor carried a deflated Sharpe"
    for finding in priced:
        assert finding.deflated.trials == report.scored, (
            "a survivor is still priced against its own sweep, not the grid")


def test_the_grid_reports_the_worst_sweep_not_the_best():
    from tradingbacktester.finder.autosearch import auto_search

    from tests.test_finder import _planted

    report = auto_search(_planted(n=30_000, strength=9.0, seed=5),
                         styles=("intraday",), control_draws=50,
                         validate="quick")
    measured = [s.report.overfitting.probability for s in report.sweeps
                if s.ran and s.report.overfitting is not None
                and s.report.overfitting.ran]
    assert measured
    assert report.overfitting.probability == max(measured)


def test_the_grid_states_the_overfitting_probability_in_words():
    from tradingbacktester.finder.autosearch import auto_search, format_auto_search

    from tests.test_finder import _noise

    report = auto_search(_noise(n=12_000, seed=31), styles=("intraday",),
                         control_draws=20, validate="quick")
    notes = " ".join(report.notes)
    if report.overfitting is not None and report.overfitting.ran:
        assert "Probability of backtest overfitting" in notes
        assert "whether SELECTION generalises" in notes
        assert "overfitting" in format_auto_search(report)


def test_the_cross_validation_does_not_read_the_locked_block():
    """The one thing this must never do.

    Truncating the locked block away must not change the measurement: if it
    does, the cross-validation was reading data the search is not allowed to
    see.
    """
    from tradingbacktester.finder import find_strategies
    from tradingbacktester.finder.styles import style

    from tests.test_finder import _planted

    bars = _planted(n=30_000, strength=9.0, seed=5)
    full = find_strategies(bars, style("intraday"), control_draws=20,
                           validate="quick")

    # The same research block, with the locked block replaced by garbage.
    import copy

    tampered = copy.deepcopy(bars)
    split = full.research_bars
    scale = np.linspace(1.0, 4.0, len(tampered) - split)
    for name in ("open", "high", "low", "close"):
        arr = getattr(tampered, name)
        arr[split:] = arr[split:] * scale

    after = find_strategies(tampered, style("intraday"), control_draws=20,
                            validate="quick")
    assert after.overfitting.probability == pytest.approx(
        full.overfitting.probability, abs=1e-12), (
        "rewriting the locked block changed the cross-validation, so it was "
        "reading data the search must not see")


def test_the_candidate_cap_is_a_module_constant_not_a_magic_number():
    assert MAX_CANDIDATES >= 100
    assert MIN_TRADES_PER_BLOCK >= 2
    assert DEFAULT_BLOCKS % 2 == 0 and DEFAULT_BLOCKS >= 4


# --------------------------------------------------------------------------
# Purging the block boundaries
# --------------------------------------------------------------------------

def test_the_tail_of_every_block_is_purged():
    """A trade signalled here would be settled by the next block."""
    collector = BlockCollector.over(split=1200, total=1200, purge=10)
    assert collector.purged == 10
    ids = collector.block_of[:1200]
    width = 1200 // DEFAULT_BLOCKS
    for index in range(DEFAULT_BLOCKS):
        end = (index + 1) * width
        assert (ids[end - 10:end] == -1).all(), (
            f"block {index} was not purged at its tail")
        assert ids[end - 11] == index, "the purge ate more than its share"


def test_purging_only_ever_removes_bars():
    """It must not renumber or reorder anything."""
    plain = BlockCollector.over(split=1200, total=1200, purge=0)
    purged = BlockCollector.over(split=1200, total=1200, purge=10)
    kept = purged.block_of >= 0
    assert (purged.block_of[kept] == plain.block_of[kept]).all()
    assert kept.sum() < (plain.block_of >= 0).sum()


def test_a_purge_that_would_empty_a_block_is_refused():
    """The cross-validation is worth more than the last bars of each block."""
    collector = BlockCollector.over(split=1200, total=1200, purge=500)
    assert collector.purged == 0
    assert (collector.block_of[:1200] >= 0).all()


def test_purging_is_off_by_default_so_callers_opt_in():
    assert BlockCollector.over(split=1200, total=1200).purged == 0


def test_the_search_purges_by_its_own_hold_limit():
    """The two numbers must not drift apart."""
    from tradingbacktester.finder.outcomes import hold_bars
    from tradingbacktester.finder.styles import style

    import tradingbacktester.finder.search as search_module

    seen = {}
    real = BlockCollector.over

    def spy(cls, split, blocks=DEFAULT_BLOCKS, total=0, purge=0):
        seen["purge"] = purge
        return real.__func__(cls, split, blocks, total, purge)

    from tests.test_finder import _planted

    search_module.BlockCollector.over = classmethod(spy)
    try:
        search_module.find_strategies(_planted(n=30_000, seed=5),
                                      style("intraday"), control_draws=20,
                                      validate="quick")
    finally:
        search_module.BlockCollector.over = real
    assert seen["purge"] == hold_bars(style("intraday").max_bars)
