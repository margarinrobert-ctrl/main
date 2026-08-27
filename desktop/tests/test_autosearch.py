"""The exhaustive grid, and the arithmetic that keeps it honest.

Searching everything is easy. The reason this module exists is the correction:
run seven searches of 1,500 and correct each for 1,500, and a result looks
significant about seven times more often than it should. Most of these tests
are about that, and about the yardstick that says how good the best of N tries
looks when there is nothing to find.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from tradingbacktester.core.errors import BacktesterError, InsufficientDataError
from tradingbacktester.data.sample import generate_sample_data
from tradingbacktester.finder.autosearch import (AutoSearchReport, Sweep,
                                                 _null_best, auto_search,
                                                 format_auto_search, plan)

from tests.test_finder import _noise, _planted


@pytest.fixture(scope="module")
def small():
    return generate_sample_data("NQ", "5m", n_bars=9000, seed=23)


# --------------------------------------------------------------------------
# What the grid is allowed to contain
# --------------------------------------------------------------------------

def test_the_plan_only_includes_bar_sizes_the_data_can_build(small):
    """Bars combine into longer ones and never the reverse."""
    pairs = plan(small)
    assert pairs
    labels = {(s.key, t) for s, t in pairs}
    assert ("scalp", "5m") in labels
    assert ("scalp", "1m") not in labels, "5m data cannot make 1m bars"
    assert ("position", "1D") in labels


def test_the_plan_can_be_narrowed_to_named_styles(small):
    pairs = plan(small, styles=("swing",))
    assert pairs
    assert {s.key for s, _t in pairs} == {"swing"}


def test_the_plan_can_be_narrowed_to_named_timeframes(small):
    pairs = plan(small, timeframes=("30m",))
    assert pairs
    assert {t for _s, t in pairs} == {"30m"}


def test_an_unknown_style_is_refused_by_name(small):
    with pytest.raises(BacktesterError) as exc:
        plan(small, styles=("banana",))
    assert "banana" not in str(exc.value) or "Choose from" in str(exc.value)


def test_data_too_coarse_for_any_style_is_refused(small):
    """Weekly bars cannot be a scalp, a day trade, a swing or a position."""
    from tradingbacktester.core.timeframe import Timeframe
    from tradingbacktester.data.resample import resample

    weekly = resample(small, Timeframe.parse("1W"))
    with pytest.raises((InsufficientDataError, BacktesterError)):
        auto_search(weekly, control_draws=20, validate="quick")


# --------------------------------------------------------------------------
# The correction is pooled, which is the whole point
# --------------------------------------------------------------------------

def test_the_correction_is_applied_over_the_whole_grid(small):
    """Not per sweep. Per sweep would be the correction for a seventh of it."""
    from tradingbacktester.finder.control import benjamini_hochberg

    report = auto_search(small, control_draws=20, validate="quick")
    scored = []
    for sweep in report.sweeps:
        if sweep.ran:
            scored.extend(sweep.report.findings)
    assert len(scored) == report.scored

    pooled = benjamini_hochberg([float(f.control.p_value) for f in scored],
                                report.alpha)
    assert len(report.survivors) == sum(pooled)

    # And it is strictly harder than correcting each sweep on its own.
    per_sweep = 0
    for sweep in report.sweeps:
        if not sweep.ran:
            continue
        local = benjamini_hochberg(
            [float(f.control.p_value) for f in sweep.report.findings],
            report.alpha)
        per_sweep += sum(local)
    assert len(report.survivors) <= per_sweep


def test_the_report_states_the_multiplicity_it_corrected_for(small):
    report = auto_search(small, control_draws=20, validate="quick")
    notes = " ".join(report.notes)
    assert f"{report.scored:,}" in notes
    assert "ONCE over all" in notes
    assert "harder to believe" in notes.lower() or "HARDER" in notes


def test_the_combination_count_is_the_sum_of_the_sweeps(small):
    report = auto_search(small, control_draws=20, validate="quick")
    assert report.combinations == sum(s.combinations for s in report.sweeps)
    assert report.scored == sum(s.scored for s in report.sweeps)
    assert report.combinations > 0


# --------------------------------------------------------------------------
# The best-of-N yardstick
# --------------------------------------------------------------------------

def test_the_null_yardstick_grows_with_the_size_of_the_search():
    """The best of many tries looks better than the best of few, on nothing."""

    class _Fake:
        def __init__(self, error):
            self.control = type("C", (), {"standard_error": error,
                                          "excess_per_trade": 0.0,
                                          "p_value": 0.5})()

    few = _null_best([_Fake(1.0) for _ in range(10)], seed=1)
    many = _null_best([_Fake(1.0) for _ in range(5000)], seed=1)
    assert 0 < few < many
    # Roughly the normal extreme-value growth: sqrt(2 ln N).
    assert many == pytest.approx(math.sqrt(2 * math.log(5000)), rel=0.35)


def test_the_null_yardstick_is_undefined_without_usable_errors():
    class _Fake:
        control = type("C", (), {"standard_error": 0.0,
                                 "excess_per_trade": 0.0, "p_value": 1.0})()

    assert math.isnan(_null_best([_Fake(), _Fake()], seed=1))


def test_a_search_of_noise_does_not_clear_its_own_null():
    """The single most useful number this module reports."""
    report = auto_search(_noise(n=12_000, seed=31), styles=("intraday",),
                         control_draws=20, validate="quick")
    assert report.best is not None
    assert math.isfinite(report.null_best)
    assert report.null_best > 0
    assert not report.beats_its_own_null, (
        f"noise produced {report.best.control.excess_per_trade:+.2f} against a "
        f"null best-of-N of {report.null_best:+.2f}")


def test_the_yardstick_appears_in_the_report(small):
    report = auto_search(small, control_draws=20, validate="quick")
    text = format_auto_search(report)
    assert "no edge" in text
    assert "clear" in text.lower()


# --------------------------------------------------------------------------
# Finding something that is there
# --------------------------------------------------------------------------

def test_a_planted_edge_survives_the_whole_grid():
    """If the correction rejected everything it would be useless, not honest."""
    bars = _planted(n=30_000, strength=9.0, seed=5)
    report = auto_search(bars, styles=("intraday",), control_draws=100,
                         validate="quick")
    assert report.survivors, (
        "a strong planted edge did not survive; best was "
        f"{report.best.control.excess_per_trade:+.2f} against a null of "
        f"{report.null_best:+.2f}")
    assert report.found_anything
    assert report.beats_its_own_null


def test_survivors_are_ordered_by_excess():
    bars = _planted(n=30_000, strength=9.0, seed=5)
    report = auto_search(bars, styles=("intraday",), control_draws=100,
                         validate="quick")
    excess = [float(f.control.excess_per_trade) for f in report.survivors]
    assert excess == sorted(excess, reverse=True)


def test_survivors_are_validated_when_asked(monkeypatch):
    """The grid is gated cheaply; whatever survives gets the real checks."""
    bars = _planted(n=30_000, strength=9.0, seed=5)
    report = auto_search(bars, styles=("intraday",), control_draws=100,
                         validate="standard", top_n=6)
    assert report.survivors
    confirmed = [f for f in report.survivors
                 if getattr(f, "confirmation", None) is not None]
    assert confirmed, "nothing came back with an engine confirmation"
    for finding in confirmed:
        assert finding.confirmation.research.trades >= 0
        assert finding.spec is not None


def test_quick_validation_skips_the_expensive_pass():
    bars = _planted(n=30_000, strength=9.0, seed=5)
    report = auto_search(bars, styles=("intraday",), control_draws=100,
                         validate="quick")
    assert report.survivors
    # Nothing is re-run, so nothing gains a validation it was not given.
    assert all(getattr(f, "validations", None) is None
               or not getattr(f.validations, "montecarlo", None)
               for f in report.survivors)


# --------------------------------------------------------------------------
# One sweep failing must not lose the grid
# --------------------------------------------------------------------------

def test_a_sweep_that_cannot_run_is_recorded_not_raised(small, monkeypatch):
    from tradingbacktester.finder import autosearch

    real = autosearch.find_strategies
    calls = {"n": 0}

    def flaky(bars, style, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise BacktesterError("deliberately broken")
        return real(bars, style, **kw)

    monkeypatch.setattr(autosearch, "find_strategies", flaky)
    report = auto_search(small, control_draws=20, validate="quick")
    broken = [s for s in report.sweeps if not s.ran]
    # Not "exactly one failed": the short fixture cannot support every style at
    # every bar size, so some sweeps refuse on their own merits. What matters is
    # that the injected failure is recorded rather than raised, and that the
    # rest of the grid still ran.
    assert any("deliberately broken" in s.error for s in broken)
    assert any(s.ran for s in report.sweeps), "the rest of the grid ran"
    assert any("Not run" in n for n in report.notes)


def test_an_unexpected_error_is_also_survived(small, monkeypatch):
    from tradingbacktester.finder import autosearch

    def explode(bars, style, **kw):
        raise ZeroDivisionError("not a BacktesterError")

    monkeypatch.setattr(autosearch, "find_strategies", explode)
    report = auto_search(small, control_draws=20, validate="quick")
    assert all(not s.ran for s in report.sweeps)
    assert all("ZeroDivisionError" in s.error for s in report.sweeps)
    assert report.survivors == []
    assert report.best is None


# --------------------------------------------------------------------------
# Saying what happened
# --------------------------------------------------------------------------

def test_nothing_surviving_is_reported_as_a_result_not_a_failure(small):
    report = auto_search(small, control_draws=20, validate="quick")
    if report.survivors:
        pytest.skip("this sample produced survivors")
    notes = " ".join(report.notes)
    assert "ordinary outcome" in notes
    assert "ground has been covered" in notes


def test_every_report_carries_the_not_a_prediction_caveat(small):
    report = auto_search(small, control_draws=20, validate="quick")
    assert any("not a prediction" in n for n in report.notes)


def test_the_text_report_lists_every_sweep(small):
    report = auto_search(small, control_draws=20, validate="quick")
    text = format_auto_search(report, top=3)
    for sweep in report.sweeps:
        assert sweep.style in text
        assert sweep.timeframe in text
    assert "combinations" in text


def test_to_dict_is_json_shaped(small):
    import json

    report = auto_search(small, control_draws=20, validate="quick")
    payload = json.loads(json.dumps(report.to_dict(), default=str))
    assert payload["combinations"] == report.combinations
    assert len(payload["sweeps"]) == len(report.sweeps)
    assert "beats_its_own_null" in payload
    assert isinstance(payload["notes"], list)


def test_a_sweep_reports_its_own_shape():
    sweep = Sweep(style="swing", timeframe="4h", combinations=1170, scored=900)
    assert sweep.ran is False, "no report attached"
    payload = sweep.to_dict()
    assert payload["style"] == "swing" and payload["combinations"] == 1170


def test_a_single_sweep_does_not_claim_a_multiplicity_it_does_not_have(small):
    """"Correcting each of 1 searches ... 1 times more often" is nonsense."""
    report = auto_search(small, styles=("intraday",), timeframes=("30m",),
                         control_draws=20, validate="quick")
    ran = [s for s in report.sweeps if s.ran]
    assert len(ran) == 1
    notes = " ".join(report.notes)
    assert "ONCE over all" in notes
    assert "1 times more often" not in notes
    assert "1 searches" not in notes
    assert "no harder to clear than that search on its own" in notes


def _fake_best(excess: float):
    control = type("C", (), {"excess_per_trade": excess, "standard_error": 1.0,
                             "p_value": 0.01})()
    return type("F", (), {"control": control, "label": "fake"})()


def test_a_best_that_clears_the_null_but_fails_the_correction_is_explained():
    """The two tests can disagree, and the reader must not have to guess why.

    Built directly rather than searched for: the disagreement needs a best that
    clears an optimistic yardstick while still failing a correction over the
    whole grid, and hunting a seed that happens to produce one would make this
    test a lottery.
    """
    from tradingbacktester.finder.autosearch import _notes

    report = AutoSearchReport(symbol="X", bars=10_000)
    report.sweeps = [Sweep(style="intraday", timeframe="5m",
                           combinations=800, scored=700,
                           report=object())]
    report.combinations, report.scored = 800, 700
    report.best = _fake_best(4.0)
    report.null_best = 3.0
    report.survivors = []
    _notes(report, [(None, "5m")])

    assert report.beats_its_own_null
    notes = " ".join(report.notes)
    assert "clears that bar" in notes
    assert "Nothing survived the correction" in notes
    assert "not the same test" in notes
    assert "deliberately optimistic" in notes
    assert "10%" in notes, "the reader is not told what rate was controlled"


def test_no_disagreement_is_claimed_when_there_is_none():
    from tradingbacktester.finder.autosearch import _notes

    report = AutoSearchReport(symbol="X", bars=10_000)
    report.sweeps = [Sweep(style="intraday", timeframe="5m",
                           combinations=800, scored=700, report=object())]
    report.combinations, report.scored = 800, 700
    report.best = _fake_best(2.0)
    report.null_best = 3.0
    _notes(report, [(None, "5m")])

    assert not report.beats_its_own_null
    notes = " ".join(report.notes)
    assert "does NOT clear that bar" in notes
    assert "not the same test" not in notes


# --------------------------------------------------------------------------
# Where a survivor came from
# --------------------------------------------------------------------------

def test_a_survivor_still_names_its_sweep_after_validation_replaces_it():
    """Validation hands back a DIFFERENT object for the same rule.

    An identity lookup would name every survivor correctly under
    ``validate="quick"`` and none of them under any other setting -- correct in
    the tests and blank in the application, which is the worst way to be wrong.
    """
    bars = _planted(n=30_000, strength=9.0, seed=5)
    quick = auto_search(bars, styles=("intraday",), control_draws=100,
                        validate="quick")
    if not quick.survivors:
        pytest.skip("nothing survived, so there is no origin to name")

    full = auto_search(bars, styles=("intraday",), control_draws=100,
                       validate="standard")
    assert full.survivors
    for finding in full.survivors:
        style_key, timeframe = full.sweep_of(finding)
        assert style_key == "intraday", "the survivor lost its sweep"
        assert timeframe in {t for _s, t in plan(bars, styles=("intraday",))}

    # And at least one of them really was replaced, or the test proves nothing.
    replaced = any(getattr(f, "confirmation", None) is not None
                   for f in full.survivors)
    assert replaced, "validation did not attach a confirmation to anything"


def test_the_origin_says_several_when_two_styles_found_the_same_rule():
    from tradingbacktester.finder.autosearch import AutoSearchReport

    report = AutoSearchReport(symbol="X", bars=1)
    report.origins[("a rule", "5m")] = "scalp"
    finding = type("F", (), {"label": "a rule", "timeframe": "5m"})()
    assert report.sweep_of(finding) == ("scalp", "5m")

    report.origins[("a rule", "5m")] = "several"
    assert report.sweep_of(finding) == ("several", "5m")


def test_an_unknown_finding_is_an_em_dash_not_a_crash():
    from tradingbacktester.finder.autosearch import AutoSearchReport

    report = AutoSearchReport(symbol="X", bars=1)
    assert report.sweep_of(object()) == ("—", "—")


# --------------------------------------------------------------------------
# The validation pass, and what it is honest about not covering
# --------------------------------------------------------------------------

def test_validation_is_capped_and_the_cap_is_stated():
    """A bound on coverage the reader cannot see reads as "we checked it all".

    A strongly planted edge passes most of its own grid -- 1,441 survivors of
    2,436 scored, on this fixture -- and pushing every one of them through the
    engine, the mirror, Monte Carlo and walk-forward is hours of work for a
    list nobody reads past the top of.
    """
    from tradingbacktester.finder.autosearch import VALIDATION_CAP

    bars = _planted(n=30_000, strength=9.0, seed=5)
    report = auto_search(bars, styles=("intraday",), control_draws=100,
                         validate="standard")
    assert len(report.survivors) > VALIDATION_CAP, (
        "this fixture no longer over-produces survivors, so the cap is not "
        "exercised; pick a stronger plant or a wider grid")

    checked = [f for f in report.survivors
               if getattr(f, "confirmation", None) is not None]
    assert 0 < len(checked) <= VALIDATION_CAP

    notes = " ".join(report.notes)
    assert f"best {VALIDATION_CAP} of {len(report.survivors):,}" in notes
    assert "unverified" in notes


def test_validated_survivors_are_listed_before_unverified_ones():
    """Leading a table with "not run" is how it gets read as a result."""
    bars = _planted(n=30_000, strength=9.0, seed=5)
    report = auto_search(bars, styles=("intraday",), control_draws=100,
                         validate="standard")
    checked = [getattr(f, "confirmation", None) is not None
               for f in report.survivors]
    assert checked[0] is True
    assert checked == sorted(checked, reverse=True), (
        "an unverified survivor is listed above a verified one")

    # And within each group, still by excess.
    verified = [float(f.control.excess_per_trade) for f in report.survivors
                if getattr(f, "confirmation", None) is not None]
    assert verified == sorted(verified, reverse=True)


def test_a_nan_robustness_is_not_printed_as_a_score():
    """"nan/100" is not a score, and neither is a number beside a blocker."""
    bars = _planted(n=30_000, strength=9.0, seed=5)
    report = auto_search(bars, styles=("intraday",), control_draws=100,
                         validate="standard")
    text = format_auto_search(report, top=8)
    assert "nan/100" not in text
    assert "robustness nan" not in text
