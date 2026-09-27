"""The research loop, and the seam that stops a proposer inventing results.

The structural claim under test: **the proposer proposes, the engine
disposes.** A proposer emits a Hypothesis, and a Hypothesis has nowhere to put
a performance number. Every figure in a report comes from the engine.
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from tradingbacktester.research.loop import (Context, Experiment, Hypothesis,
                                             LoopReport, SystematicProposer,
                                             _families, run_loop)

pytestmark = pytest.mark.slow if False else pytest.mark.gui


def _bars(n: int = 12_000):
    from tradingbacktester.core.timeframe import Timeframe
    from tradingbacktester.data.sample import generate_sample_data

    return generate_sample_data("LOOP", Timeframe.parse("15m"), n_bars=n,
                                seed=13)


def _style(key: str = "intraday"):
    from tradingbacktester.finder.styles import style

    return style(key)


# ---------------------------------------------------------------------------
# the seam
# ---------------------------------------------------------------------------

def test_a_hypothesis_cannot_carry_a_performance_claim():
    """The defence against a model that hallucinates a Sharpe ratio: there is
    no field for one, so it hallucinates into nothing."""
    fields = {f.name for f in dataclasses.fields(Hypothesis)}
    forbidden = {"sharpe", "sharpe_ratio", "expected_return", "profit",
                 "net_profit", "win_rate", "return_pct", "score", "result",
                 "metrics", "performance", "profit_factor", "drawdown"}
    assert not (fields & forbidden), (
        f"Hypothesis grew a field a proposer could state a false number in: "
        f"{fields & forbidden}")


def test_every_experiment_figure_comes_from_a_finding():
    """An Experiment's numbers are counts and a score read off the engine's
    own robustness assessment — never anything a proposer supplied."""
    fields = {f.name for f in dataclasses.fields(Experiment)}
    assert "best_score" in fields
    # best_score is derived, not settable by a proposer: it is read from
    # finding.robustness.total inside _run_one.
    import inspect

    from tradingbacktester.research import loop

    source = inspect.getsource(loop._run_one)
    assert "f.robustness.total" in source
    assert "hypothesis." not in source.split("best_score")[1][:200]


# ---------------------------------------------------------------------------
# the systematic proposer
# ---------------------------------------------------------------------------

def _context(**kwargs) -> Context:
    base = dict(symbol="X", timeframe="15m", bars=10_000,
                style_key="intraday", style_label="Day trading",
                families=_families())
    base.update(kwargs)
    return Context(**base)


def test_the_first_round_tries_each_family_alone():
    out = SystematicProposer().propose(_context(round_index=0))
    assert out
    assert all(len(h.templates) == 1 for h in out)
    assert len({h.templates for h in out}) == len(out)


def test_it_never_repeats_a_hypothesis_it_has_already_run():
    proposer = SystematicProposer()
    first = proposer.propose(_context(round_index=0))
    history = [Experiment(hypothesis=h, round_index=0) for h in first]
    again = proposer.propose(_context(round_index=0, history=history))
    tried = {h.key() for h in first}
    assert not any(h.key() in tried for h in again)


def test_a_family_tested_on_both_sides_is_not_re_proposed_as_a_side_test():
    """Round 0 tests both sides, so 'try the other side' flips nothing — and
    proposing it anyway re-runs the identical search and reports one finding
    twice."""
    survivor = Experiment(
        hypothesis=Hypothesis(idea="i", templates=("breakout",),
                              sides=(1, -1)),
        round_index=0, survivors=[object()])
    out = SystematicProposer().propose(
        _context(round_index=1, history=[survivor]))
    for hypothesis in out:
        assert hypothesis.key() != survivor.hypothesis.key()
        if hypothesis.templates == ("breakout",):
            assert hypothesis.timeframe, (
                "with both sides already tested, the next variable should be "
                "the bar size")


def test_a_one_sided_survivor_is_re_proposed_on_the_other_side():
    survivor = Experiment(
        hypothesis=Hypothesis(idea="i", templates=("breakout",), sides=(1,)),
        round_index=0, survivors=[object()])
    out = SystematicProposer().propose(
        _context(round_index=1, history=[survivor]))
    assert any(h.sides == (-1,) for h in out)


def test_it_never_proposes_a_bar_size_the_data_cannot_produce():
    """Bars combine into longer ones and never split, so a finer timeframe is
    an experiment that cannot run."""
    from tradingbacktester.core.timeframe import Timeframe

    survivor = Experiment(
        hypothesis=Hypothesis(idea="i", templates=("breakout",), sides=(1, -1)),
        round_index=0, survivors=[object()])
    out = SystematicProposer().propose(
        _context(round_index=1, timeframe="30m", history=[survivor]))
    have = Timeframe.parse("30m").approx_seconds
    for hypothesis in out:
        if hypothesis.timeframe:
            assert Timeframe.parse(hypothesis.timeframe).approx_seconds >= have


def test_when_nothing_survived_it_widens_instead_of_narrowing():
    failed = [Experiment(hypothesis=Hypothesis(idea="i", templates=(f,)),
                         round_index=0)
              for f in _families()]
    out = SystematicProposer().propose(
        _context(round_index=1, history=failed))
    assert out and out[0].templates == ()
    assert "widens" in out[0].rationale


# ---------------------------------------------------------------------------
# the loop
# ---------------------------------------------------------------------------

def test_the_loop_records_failures_as_well_as_findings():
    report = run_loop(_bars(), _style(), rounds=1, validate="quick",
                      control_draws=50)
    assert report.experiments
    assert all(e.verdict or e.error for e in report.experiments), (
        "every experiment must say what happened, including the empty ones")


def test_the_loop_reports_its_own_multiplicity():
    report = run_loop(_bars(), _style(), rounds=1, validate="quick",
                      control_draws=50)
    assert report.total_combinations == sum(
        e.combinations for e in report.experiments)
    assert any("chances this loop had to be lucky" in n for n in report.notes)


def test_a_proposer_that_raises_stops_the_loop_without_losing_it():
    class Broken:
        name = "broken"

        def propose(self, context):
            raise RuntimeError("no")

    report = run_loop(_bars(2000), _style(), rounds=2, proposer=Broken(),
                      validate="quick", control_draws=20)
    assert report.experiments == []
    assert any("proposer failed" in n for n in report.notes)


def test_a_proposer_with_nothing_to_add_ends_the_loop_quietly():
    class Empty:
        name = "empty"

        def propose(self, context):
            return []

    report = run_loop(_bars(2000), _style(), rounds=3, proposer=Empty(),
                      validate="quick", control_draws=20)
    assert report.experiments == []
    assert any("nothing new to suggest" in n for n in report.notes)


def test_an_unrunnable_hypothesis_does_not_take_the_loop_down():
    class Impossible:
        name = "impossible"

        def propose(self, context):
            if context.round_index:
                return []
            return [Hypothesis(idea="a bar size this data cannot make",
                               timeframe="1m")]

    report = run_loop(_bars(2000), _style(), rounds=2, proposer=Impossible(),
                      validate="quick", control_draws=20)
    assert len(report.experiments) == 1
    assert report.experiments[0].error
    assert report.experiments[0].verdict == "could not be tested"


def test_the_same_rule_is_never_reported_as_two_findings():
    class Twice:
        name = "twice"

        def propose(self, context):
            if context.round_index:
                return []
            return [Hypothesis(idea="a", templates=("breakout",)),
                    Hypothesis(idea="b", templates=("breakout",), sides=(1,))]

    report = run_loop(_bars(), _style(), rounds=1, proposer=Twice(),
                      validate="quick", control_draws=50)
    labels = [f.label for f in report.survivors]
    assert len(labels) == len(set(labels))


def test_the_loop_always_says_it_is_not_a_prediction():
    report = run_loop(_bars(2000), _style(), rounds=1, validate="quick",
                      control_draws=20)
    assert any("not a prediction" in n for n in report.notes)


# ---------------------------------------------------------------------------
# persistence
# ---------------------------------------------------------------------------

def test_a_run_survives_being_stored_and_read_back(tmp_path):
    from tradingbacktester.config import Workspace
    from tradingbacktester.storage.research_store import ResearchStore

    workspace = Workspace(tmp_path).ensure()
    store = ResearchStore(workspace)
    assert store.list() == []

    report = run_loop(_bars(2000), _style(), rounds=1, validate="quick",
                      control_draws=20)
    row = store.save(report, timeframe="15m", note="a note")
    assert row.id
    listed = store.list()
    assert len(listed) == 1
    assert listed[0].note == "a note"
    assert listed[0].experiments == len(report.experiments)

    loaded = store.load(row.id)
    assert loaded is not None
    assert loaded["report"]["total_combinations"] == report.total_combinations


def test_a_corrupt_index_is_reported_as_empty_not_raised(tmp_path):
    from tradingbacktester.config import Workspace
    from tradingbacktester.storage.research_store import ResearchStore

    workspace = Workspace(tmp_path).ensure()
    store = ResearchStore(workspace)
    store.index_path.write_text("{not json", encoding="utf-8")
    assert store.list() == []


def test_removing_a_run_takes_its_index_row_with_it(tmp_path):
    from tradingbacktester.config import Workspace
    from tradingbacktester.storage.research_store import ResearchStore

    workspace = Workspace(tmp_path).ensure()
    store = ResearchStore(workspace)
    report = run_loop(_bars(2000), _style(), rounds=1, validate="quick",
                      control_draws=20)
    row = store.save(report)
    store.remove(row.id)
    assert store.list() == []
    assert store.load(row.id) is None


def test_a_run_id_cannot_escape_the_research_folder(tmp_path):
    from tradingbacktester.config import Workspace
    from tradingbacktester.storage.research_store import ResearchStore

    workspace = Workspace(tmp_path).ensure()
    store = ResearchStore(workspace)
    path = store.path_for("../../etc/passwd")
    assert store.dir in path.parents
