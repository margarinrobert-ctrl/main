"""Building features from features, and counting how few there really are.

The point of this module is not that combining two features is clever -- it is
that doing it multiplies the number of tests without multiplying the number of
facts. So the tests here are mostly about the safeguards: that a constructed
feature cannot see the future, that a child which merely restates its parent is
thrown away before it costs anyone a correction, and that the effective
dimension is reported beside the feature count.
"""

from __future__ import annotations

import numpy as np
import pytest

from tradingbacktester.data.sample import generate_sample_data
from tradingbacktester.research.engineering import (MAX_PARENTS,
                                                    REDUNDANT_ABOVE,
                                                    STANDARDISE_WINDOW,
                                                    OPERATORS,
                                                    build_interactions,
                                                    drop_restatements,
                                                    effective_dimension)
from tradingbacktester.research.features import (Feature, all_features,
                                                 compute_matrix)


@pytest.fixture(scope="module")
def bars():
    return generate_sample_data("NQ", "30m", n_bars=3000, seed=17)


# --------------------------------------------------------------------------
# A constructed feature must not be able to see the future
# --------------------------------------------------------------------------

def test_no_constructed_feature_can_see_the_future(bars):
    """Truncate the series; every bar that survives must keep its value.

    This caught a real one. Two operators standardised their parents over the
    WHOLE series, so every value depended on bars that had not happened yet.
    On US30 30m that leak manufactured 28 'significant' features out of a
    sample that has none.
    """
    parents = all_features()[:6]
    children = build_interactions(parents)
    assert children
    cut = len(bars) - 400
    short = bars.slice(0, cut)
    drifted = []
    for child in children:
        full = np.asarray(child.values(bars), dtype="float64")[:cut]
        part = np.asarray(child.values(short), dtype="float64")
        if (np.isfinite(full) != np.isfinite(part)).any():
            drifted.append(f"{child.name} (defined on different bars)")
            continue
        both = np.isfinite(full)
        if not np.allclose(full[both], part[both]):
            drifted.append(child.name)
    assert not drifted, f"these changed when the future was removed: {drifted}"


def test_standardising_is_trailing_not_whole_series():
    """The one-line shortcut is the look-ahead; this is the guard on it."""
    from tradingbacktester.research.engineering import _standardise

    rng = np.random.default_rng(21)
    quiet = rng.normal(scale=1.0, size=600)
    values = np.concatenate([quiet, quiet + 100.0])
    out = _standardise(values)
    # A whole-series z-score would put the first half around -1 because of a
    # jump that has not happened yet. A trailing one leaves it centred on zero
    # and only reacts once the jump is inside its own window.
    settled = out[STANDARDISE_WINDOW + 50:600]
    assert abs(float(np.nanmean(settled))) < 0.2
    assert float(np.nanmax(np.abs(settled))) < 4.0
    assert float(np.nanmax(out[600:640])) > 4.0


# --------------------------------------------------------------------------
# What gets built, and what does not
# --------------------------------------------------------------------------

def test_a_symmetric_operator_is_built_once():
    """``a - b`` and ``b - a`` are the same question and one is enough.

    One is the negation of the other, so their information is identical and
    their ICs are exact mirrors. Building both doubles the multiplicity for
    nothing and fills the top of the table with pairs of the same finding.
    """
    parents = all_features()[:4]
    children = build_interactions(parents)
    names = [c.name for c in children]
    assert len(names) == len(set(names))
    for operator in OPERATORS:
        if not operator.symmetric:
            continue
        built = [n for n in names if f" {operator.label} " in n]
        pairs = {frozenset(n.split(f" {operator.label} ")) for n in built}
        assert len(built) == len(pairs), f"{operator.key} built both orders"


def test_an_asymmetric_operator_is_built_both_ways():
    """``a / b`` and ``b / a`` are different questions across a sign change."""
    parents = all_features()[:3]
    children = build_interactions(parents)
    ratios = [c.name for c in children if " ÷ " in c.name]
    pairs = {frozenset(n.split(" ÷ ")) for n in ratios}
    assert len(ratios) == 2 * len(pairs)


def test_the_parent_ceiling_is_respected():
    children = build_interactions(all_features(), max_parents=4)
    parents = set()
    for child in children:
        left, _, right = child.name.partition(" ")
        parents.add(left)
    assert len(parents) <= 4
    assert MAX_PARENTS >= 4


def test_a_child_inherits_its_slowest_parents_warmup():
    slow = Feature(name="slow", family="test", description="",
                   compute=lambda b: np.ones(len(b)), warmup=100)
    quick = Feature(name="quick", family="test", description="",
                    compute=lambda b: np.ones(len(b)), warmup=5)
    children = build_interactions([slow, quick])
    assert children
    assert all(c.warmup == 100 for c in children)


def test_a_ratio_through_zero_is_absent_not_enormous(bars):
    """Clipping would invent a reading exactly where there is least to say."""
    from tradingbacktester.research.engineering import _ratio

    n = 1200
    top = np.ones(n)
    bottom = np.linspace(-1.0, 1.0, n)
    out = _ratio(top, bottom)
    near_zero = int(np.argmin(np.abs(bottom)))
    assert np.isnan(out[near_zero]), "a ratio through zero is absent, not huge"
    assert np.isfinite(out[-1]), "and away from zero it is an ordinary number"
    # Bounded by the floor rather than by luck: compared against what an
    # unguarded division would have produced at the bar nearest zero.
    unguarded = 1.0 / abs(float(bottom[near_zero]))
    assert float(np.nanmax(np.abs(out))) < unguarded * 0.25
    # Past the trailing window's own warm-up, the bars it dropped are exactly
    # the ones nearest zero rather than a random scatter.
    warm = slice(STANDARDISE_WINDOW + 1, None)
    absolute = np.abs(bottom)[warm]
    defined = np.isfinite(out[warm])
    masked, kept = absolute[~defined], absolute[defined]
    assert masked.size and kept.size
    assert masked.max() < kept.min() * 1.5


def test_the_ratio_floor_is_trailing_so_it_cannot_see_the_future():
    """Whether a bar HAS a value must not depend on bars after it.

    A quieter look-ahead than a wrong number, and a harder one to notice: the
    values that are present all look fine, and the set of bars they are present
    on is the thing that moved.
    """
    from tradingbacktester.research.engineering import _ratio

    rng = np.random.default_rng(31)
    bottom = rng.normal(size=2000)
    top = rng.normal(size=2000)
    cut = 1400
    full = _ratio(top, bottom)[:cut]
    part = _ratio(top[:cut], bottom[:cut])
    assert np.array_equal(np.isfinite(full), np.isfinite(part))
    both = np.isfinite(full)
    assert np.allclose(full[both], part[both])


# --------------------------------------------------------------------------
# Restatements
# --------------------------------------------------------------------------

def test_a_child_that_restates_its_parent_is_dropped():
    """Testing it again spends multiplicity on a question already asked."""
    n = 800
    rng = np.random.default_rng(4)
    a = rng.normal(size=n)
    steady = np.full(n, 5.0) + rng.normal(scale=1e-6, size=n)

    parents = [
        Feature(name="a", family="test", description="", compute=lambda b: a),
        Feature(name="steady", family="test", description="",
                compute=lambda b: steady),
    ]
    # a / steady is a scaled copy of a: not a new reading.
    children = build_interactions(parents)
    bars = generate_sample_data("NQ", "30m", n_bars=n, seed=2)
    child_matrix, children = compute_matrix(bars, children)
    parent_matrix, parents = compute_matrix(bars, parents)
    keep, dropped = drop_restatements(child_matrix, children, parent_matrix,
                                      parents)
    assert dropped, "a scaled copy of a parent must not be tested as new"
    assert any("÷" in text for text in dropped)
    assert len(keep) < len(children)
    for text in dropped:
        assert "|r|" in text, "say how correlated it was, not just that it was"


def test_a_genuinely_new_child_is_kept():
    n = 800
    rng = np.random.default_rng(11)
    a, b = rng.normal(size=n), rng.normal(size=n)
    parents = [
        Feature(name="a", family="test", description="", compute=lambda x: a),
        Feature(name="b", family="test", description="", compute=lambda x: b),
    ]
    bars = generate_sample_data("NQ", "30m", n_bars=n, seed=3)
    children = build_interactions(parents)
    child_matrix, children = compute_matrix(bars, children)
    parent_matrix, parents = compute_matrix(bars, parents)
    keep, _dropped = drop_restatements(child_matrix, children, parent_matrix,
                                       parents)
    assert keep, "two independent parents make children worth testing"
    assert REDUNDANT_ABOVE < 1.0


# --------------------------------------------------------------------------
# How many questions were actually asked
# --------------------------------------------------------------------------

def test_the_effective_dimension_is_smaller_than_the_feature_count(bars):
    matrix, features = compute_matrix(bars, all_features())
    dimension = effective_dimension(matrix, [f.name for f in features])
    assert dimension.features == len(features)
    assert 0 < dimension.components < dimension.features
    assert dimension.compression > 1.0
    assert "how many questions were asked" in dimension.note


def test_perfectly_correlated_columns_are_one_direction():
    base = np.linspace(0.0, 1.0, 400)[:, None]
    matrix = np.hstack([base, base * 3.0, base - 7.0])
    dimension = effective_dimension(matrix)
    assert dimension.components == 1
    assert dimension.compression == pytest.approx(3.0)


def test_independent_columns_are_not_compressed():
    rng = np.random.default_rng(5)
    matrix = rng.normal(size=(4000, 5))
    dimension = effective_dimension(matrix)
    assert dimension.components >= 4


def test_too_few_usable_bars_says_so_rather_than_guessing():
    matrix = np.full((6, 20), np.nan)
    matrix[:3] = 1.0
    dimension = effective_dimension(matrix)
    assert dimension.components == 0
    assert "too few" in dimension.note
    assert "not reported rather than guessed" in dimension.note


def test_a_constant_matrix_is_reported_not_divided_by_zero():
    dimension = effective_dimension(np.ones((500, 4)))
    assert dimension.components == 0
    assert "constant" in dimension.note


# --------------------------------------------------------------------------
# Through the study
# --------------------------------------------------------------------------

def test_the_study_reports_its_dimension_without_being_asked(bars):
    from tradingbacktester.finder.styles import style
    from tradingbacktester.research.study import study_features

    study = study_features(bars, style("intraday"), timeframe="30m")
    assert study.dimension is not None
    assert study.dimension.components > 0
    assert study.constructed == 0
    assert any("independent directions" in n for n in study.notes)


def test_interactions_are_built_from_the_research_block_only(bars):
    """Ranking parents over both blocks puts the holdout in the construction.

    Seen before in this project: a feature family ranked over both blocks
    failed on research and 'passed' on the holdout, which is the wrong shape
    and was pure leakage.
    """
    from tradingbacktester.finder.styles import style
    from tradingbacktester.research import study as study_module
    from tradingbacktester.research.study import study_features

    seen: list[slice] = []
    real = study_module.evaluate

    def spy(name, feature, target, horizon):
        seen.append(len(feature))
        return real(name, feature, target, horizon)

    study_module.evaluate = spy
    try:
        study = study_features(bars, style("intraday"), timeframe="30m",
                               interactions=4)
    finally:
        study_module.evaluate = real

    split = int(len(bars) * 0.65)
    # The parent ranking pass runs first and every one of its calls sees the
    # research block and nothing longer.
    assert seen[:54] == [split] * 54
    assert study.constructed > 0


def test_a_study_with_interactions_says_how_many_it_built(bars):
    from tradingbacktester.finder.styles import style
    from tradingbacktester.research.study import study_features

    study = study_features(bars, style("intraday"), timeframe="30m",
                           interactions=5)
    assert study.constructed > 0
    assert study.tested == 54 + study.constructed
    payload = study.to_dict()
    assert payload["constructed_features"] == study.constructed
    assert payload["dimension"]["components"] > 0
    assert isinstance(payload["dropped_as_restatements"], list)
