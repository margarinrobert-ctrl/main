"""The research dashboard.

A dashboard makes things look authoritative: rows read as facts whether or not
they are, and a big number reads as a conclusion. These tests fix the choices
that push against that — the grade sits where the profit would, experiments
that found nothing are listed beside the ones that did, and a disqualified
candidate shows its blockers where its score would be.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.gui


@pytest.fixture
def store(tmp_path):
    from tradingbacktester.config import Workspace
    from tradingbacktester.storage.research_store import ResearchStore

    return ResearchStore(Workspace(tmp_path).ensure())


@pytest.fixture
def dashboard(qapp, store):
    from tradingbacktester.ui.dialogs.dashboard_dialog import DashboardDialog

    dialog = DashboardDialog(store)
    yield dialog
    dialog.close()
    qapp.processEvents()


def _bars(n: int = 12_000):
    from tradingbacktester.core.timeframe import Timeframe
    from tradingbacktester.data.sample import generate_sample_data

    return generate_sample_data("DASH", Timeframe.parse("15m"), n_bars=n,
                                seed=21)


def _run(rounds: int = 1):
    from tradingbacktester.finder.styles import style
    from tradingbacktester.research.loop import run_loop

    return run_loop(_bars(), style("intraday"), rounds=rounds,
                    validate="quick", control_draws=50)


# ---------------------------------------------------------------------------
# an empty dashboard is still a dashboard
# ---------------------------------------------------------------------------

def test_an_empty_history_says_so_rather_than_showing_nothing(dashboard):
    assert dashboard.runs.rowCount() == 0
    assert "No research has been kept yet" in dashboard.status.text()


def test_a_run_listed_but_missing_from_disk_is_reported(dashboard, store, qapp):
    report = _run()
    row = store.save(report)
    store.path_for(row.id).unlink()
    dashboard.refresh()
    dashboard.runs.selectRow(0)
    qapp.processEvents()
    assert "could not be read" in dashboard.status.text()


def test_a_corrupt_index_does_not_stop_the_dialog_opening(qapp, store):
    from tradingbacktester.ui.dialogs.dashboard_dialog import DashboardDialog

    store.index_path.write_text("{not json", encoding="utf-8")
    dialog = DashboardDialog(store)
    assert dialog.runs.rowCount() == 0
    dialog.close()
    qapp.processEvents()


# ---------------------------------------------------------------------------
# what it shows
# ---------------------------------------------------------------------------

def test_a_saved_run_appears_with_its_experiments(dashboard, store, qapp):
    report = _run()
    store.save(report, timeframe="15m")
    dashboard.refresh()
    dashboard.runs.selectRow(0)
    qapp.processEvents()
    assert dashboard.runs.rowCount() == 1
    assert dashboard.experiments.rowCount() == len(report.experiments)


def test_experiments_that_found_nothing_are_listed_not_filtered_out(
        dashboard, store, qapp):
    """They are what tell you the ground has been covered."""
    report = _run()
    empty = [e for e in report.experiments if not e.worked]
    assert empty, "this fixture needs at least one empty experiment"
    store.save(report)
    dashboard.refresh()
    dashboard.runs.selectRow(0)
    qapp.processEvents()
    shown = {dashboard.experiments.item(r, 1).text()
             for r in range(dashboard.experiments.rowCount())}
    for experiment in empty:
        assert experiment.hypothesis.idea in shown


def test_the_first_candidate_column_is_the_grade_not_the_profit(dashboard):
    from tradingbacktester.ui.dialogs.dashboard_dialog import \
        _CANDIDATE_COLUMNS

    assert _CANDIDATE_COLUMNS[0] == "Robustness"
    assert "Net" not in _CANDIDATE_COLUMNS[0]


def test_a_disqualified_candidate_shows_its_blockers_instead_of_a_score():
    from tradingbacktester.ui.dialogs.dashboard_dialog import _candidate_report

    text = _candidate_report({
        "label": "A rule", "verdict": "not worth trading",
        "robustness": {"blocked": True, "total": None, "grade": "disqualified",
                       "blockers": ["it lost money out of sample"],
                       "dimensions": [], "measured": 0, "notes": []},
    })
    assert "DISQUALIFIED" in text
    assert "it lost money out of sample" in text
    assert "/100" not in text, (
        "a score printed beside a disqualifying reason is a score someone "
        "will quote without the reason")


def test_a_candidate_report_shows_both_blocks_never_one_number():
    from tradingbacktester.ui.dialogs.dashboard_dialog import _candidate_report

    text = _candidate_report({
        "label": "A rule",
        "robustness": {"blocked": False, "total": 80.0, "grade": "mixed",
                       "dimensions": [], "measured": 6, "notes": []},
        "confirmation": {
            "research": {"trades": 100, "metrics": {"net_profit": 1000.0}},
            "holdout": {"trades": 50, "metrics": {"net_profit": -200.0}},
            "agreement": {"agrees": True}, "notes": []},
    })
    assert "research | locked" in text
    assert "1,000.00 | -200.00" in text


def test_an_engine_disagreement_is_surfaced_in_the_report():
    from tradingbacktester.ui.dialogs.dashboard_dialog import _candidate_report

    text = _candidate_report({
        "label": "A rule",
        "robustness": {"blocked": False, "total": 80.0, "grade": "mixed",
                       "dimensions": [], "measured": 6, "notes": []},
        "confirmation": {
            "research": {"trades": 10, "metrics": {"net_profit": 1.0}},
            "holdout": {"trades": 10, "metrics": {"net_profit": 1.0}},
            "agreement": {"agrees": False, "reason": "they differ"},
            "notes": []},
    })
    assert "did not reproduce" in text and "they differ" in text


def test_candidates_are_deduplicated_across_experiments(dashboard, store, qapp):
    report = _run(rounds=2)
    store.save(report)
    dashboard.refresh()
    dashboard.runs.selectRow(0)
    qapp.processEvents()
    labels = [dashboard.candidates.item(r, 1).text()
              for r in range(dashboard.candidates.rowCount())]
    assert len(labels) == len(set(labels))


def test_candidates_are_ordered_by_score_not_by_return(dashboard, store, qapp):
    report = _run(rounds=2)
    store.save(report)
    dashboard.refresh()
    dashboard.runs.selectRow(0)
    qapp.processEvents()
    scores = []
    for row in range(dashboard.candidates.rowCount()):
        text = dashboard.candidates.item(row, 0).text()
        scores.append(-1.0 if "disqualified" in text
                      else float(text.split("/")[0]) if "/" in text else -1.0)
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# acting on it
# ---------------------------------------------------------------------------

def test_running_without_a_dataset_says_so_rather_than_failing(dashboard):
    dashboard.on_run()
    assert "Load a dataset" in dashboard.status.text()
    assert dashboard.run_button.isEnabled()


def test_deleting_a_run_removes_it_from_the_list(dashboard, store, qapp,
                                                 monkeypatch):
    import tradingbacktester.ui.dialogs.dashboard_dialog as module

    store.save(_run())
    dashboard.refresh()
    dashboard.runs.selectRow(0)
    qapp.processEvents()
    monkeypatch.setattr(module, "confirm", lambda *a, **k: True)
    dashboard.on_delete()
    qapp.processEvents()
    assert dashboard.runs.rowCount() == 0
    assert store.list() == []


def test_declining_the_delete_confirmation_keeps_the_run(dashboard, store,
                                                         qapp, monkeypatch):
    import tradingbacktester.ui.dialogs.dashboard_dialog as module

    store.save(_run())
    dashboard.refresh()
    dashboard.runs.selectRow(0)
    qapp.processEvents()
    monkeypatch.setattr(module, "confirm", lambda *a, **k: False)
    dashboard.on_delete()
    qapp.processEvents()
    assert len(store.list()) == 1
