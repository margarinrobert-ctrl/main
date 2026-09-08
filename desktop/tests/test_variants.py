"""Searching a strategy's neighbourhood, and refusing to oversell the winner.

The load-bearing property is that the winner is priced for the number of tries
that found it. Taking the best of twenty-eight variants and reporting its raw
Sharpe is how a parameter sweep becomes a discovery.
"""

from __future__ import annotations

import numpy as np
import pytest

from tradingbacktester.core.errors import StrategyError
from tradingbacktester.core.types import BacktestConfig
from tradingbacktester.data.sample import generate_sample_data
from tradingbacktester.engine.backtester import Backtester
from tradingbacktester.finder.variants import (MIN_TRADES, LearnedFilter,
                                               axes_for, fit_learned_filter,
                                               search_variants)
from tradingbacktester.strategy import builtin
from tradingbacktester.strategy.spec import (Compare, Const, Ind,
                                             IndicatorSlot, Price,
                                             StrategySpec)


@pytest.fixture(scope="module")
def bars():
    return generate_sample_data("NQ", "1h", n_bars=6000, seed=11)


@pytest.fixture(scope="module")
def report(bars):
    return search_variants(builtin.macd_trend(), bars, BacktestConfig())


# --------------------------------------------------------------------------
# What gets swept
# --------------------------------------------------------------------------


def test_every_numeric_parameter_becomes_an_axis():
    spec = builtin.macd_trend()
    keys = {a.key for a in axes_for(spec)}
    for param in spec.params:
        if param.kind in ("int", "float"):
            assert f"param.{param.name}" in keys


def test_the_exit_geometry_is_swept_too():
    """Usually the bigger lever, and the one people forget to vary."""
    spec = builtin.macd_trend()
    keys = {a.key for a in axes_for(spec)}
    assert any(k.startswith("exits.") for k in keys)


def test_an_axis_never_offers_the_value_it_already_has():
    for axis in axes_for(builtin.macd_trend()):
        assert axis.current not in axis.values


def test_rungs_respect_the_parameters_own_bounds():
    for axis in axes_for(builtin.macd_trend()):
        for value in axis.values:
            assert value > 0


def test_a_strategy_with_nothing_to_sweep_says_so(bars):
    spec = StrategySpec(
        name="nothing to tune",
        indicators=[IndicatorSlot("m", "SMA", {"period": 20})],
        entry_long=Compare(Price("close"), ">", Ind("m")))
    spec.exits.stop_loss_enabled = False
    spec.exits.take_profit_enabled = False
    spec.exits.trailing_enabled = False
    spec.exits.max_bars_in_trade = 0
    out = search_variants(spec, bars, BacktestConfig())
    assert out.tried == 0
    assert any("no neighbourhood" in n for n in out.notes)


# --------------------------------------------------------------------------
# Running the search
# --------------------------------------------------------------------------


def test_the_search_tries_variants_and_keeps_the_baseline(report):
    assert report.tried > 0
    assert report.baseline.trades > 0
    assert report.baseline.label == "baseline"


def test_every_variant_differs_from_the_baseline_in_a_named_way(report):
    for variant in report.variants:
        assert variant.changes, f"{variant.label} changed nothing"
        for key in variant.changes:
            assert any(a.key == key for a in report.axes)


def test_the_search_does_not_mutate_the_strategy_it_was_given(bars):
    spec = builtin.macd_trend()
    before = spec.to_json()
    search_variants(spec, bars, BacktestConfig())
    assert spec.to_json() == before


def test_the_winner_is_priced_for_the_number_of_tries(report):
    """The whole point: best-of-N is deflated against N, not reported raw."""
    if report.best is None:
        pytest.skip("no usable variant on this fixture")
    assert report.deflated is not None
    assert report.deflated.trials == report.tried
    assert report.deflated.benchmark > 0, (
        "the best-of-N benchmark collapsed to zero, so nothing is being paid "
        "for the search")


def test_improved_requires_significance_not_merely_clearing(report):
    """Clearing the benchmark is weaker than clearing 0.95, and saying
    'survives' for the first while printing 'not significant' underneath
    invites the reader to believe the flattering half."""
    if report.deflated is None:
        pytest.skip("nothing to price")
    if report.improved:
        assert report.deflated.significant


def test_the_headline_never_claims_survival_without_significance(report):
    text = report.headline()
    if "survives the correction" in text:
        assert report.deflated is not None and report.deflated.significant
    if report.deflated is not None and not report.deflated.significant:
        assert "does NOT survive" in text


def test_a_variant_with_too_few_trades_is_not_judged(report):
    for variant in report.variants:
        if variant.trades < MIN_TRADES:
            assert not variant.usable
    assert all(v.trades >= MIN_TRADES for v in report.usable)


def test_progress_can_stop_the_search_and_it_stays_honest(bars):
    """A stopped search is priced for what it tried, not what it planned."""
    def stop_after_four(done, total, label):
        return done <= 4

    out = search_variants(builtin.macd_trend(), bars, BacktestConfig(),
                          progress=stop_after_four)
    assert out.tried <= 4
    assert any("Stopped after" in n for n in out.notes)
    if out.deflated is not None:
        assert out.deflated.trials == out.tried


def test_a_broken_variant_is_recorded_not_raised(bars, monkeypatch):
    """A 400-variant walk that dies on variant three and reports nothing is a
    worse outcome than one that records the failure and carries on."""
    import tradingbacktester.finder.variants as V

    calls = {"n": 0}
    real = V._score

    def flaky(spec, bars_, config, label, changes):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("engine exploded")
        return real(spec, bars_, config, label, changes)

    monkeypatch.setattr(V, "_score", flaky)
    # The baseline is scored first, so the injected failure lands on a variant.
    out = V.search_variants(builtin.macd_trend(), bars, BacktestConfig())
    assert out.tried > 1, "the search stopped at the first failure"
    broken = [v for v in out.variants if v.error]
    assert len(broken) == 1
    assert "engine exploded" in broken[0].error
    assert not broken[0].usable
    # And the rest of the walk still happened.
    assert len(out.usable) > 0


def test_a_strategy_that_cannot_run_at_all_is_refused_clearly(bars):
    spec = builtin.macd_trend()
    spec.indicators[0].indicator = "NOT_AN_INDICATOR"
    with pytest.raises(StrategyError, match="nothing to improve"):
        search_variants(spec, bars, BacktestConfig())


def test_no_data_is_refused_before_anything_runs():
    with pytest.raises(StrategyError, match="Load a dataset"):
        search_variants(builtin.macd_trend(), None, BacktestConfig())


def test_the_report_reads_as_sentences(report):
    lines = report.lines()
    assert lines and all(isinstance(line, str) for line in lines)
    assert "Baseline" in "\n".join(lines)


# --------------------------------------------------------------------------
# The learned filter
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def trades(bars):
    return list(Backtester(bars, builtin.macd_trend(), BacktestConfig()).run().trades)


def test_the_model_is_scored_on_trades_it_never_saw(trades):
    model = fit_learned_filter(trades)
    if model is None:
        pytest.skip("too few trades on this fixture")
    assert model.train_trades + model.test_trades < len(trades), (
        "train and test overlap, or the purge gap was not applied")


def test_too_few_trades_returns_nothing_rather_than_a_fitted_lie():
    """Fitting on everything and scoring on the same data is the failure this
    guards: it always looks excellent."""
    assert fit_learned_filter([]) is None
    assert fit_learned_filter(list(range(10))) is None


def test_the_features_contain_nothing_known_only_after_the_exit(trades):
    """MAE, MFE, bars held and the exit price are outcomes. A model given any
    of them predicts the winner perfectly and generalises to nothing."""
    model = fit_learned_filter(trades)
    if model is None:
        pytest.skip("too few trades")
    banned = ("exit", "mae", "mfe", "bars", "pnl", "return", "duration",
              "reason")
    for name in model.features:
        assert not any(word in name.lower() for word in banned), name


def test_a_model_that_rejects_everything_is_called_out_not_praised():
    """Accuracy equal to the losing rate is the majority-class trap, and the
    describe() text has to name it rather than print 69% and stop."""
    model = LearnedFilter(
        features=["bias"], weights=np.zeros(1), train_trades=200,
        test_trades=100, base_rate=0.314, accuracy=0.686,
        kept_win_rate=0.0, kept_fraction=0.0)
    assert model.degenerate
    text = model.describe()
    assert "rejected every held-out trade" in text
    assert "not skill" in text
    assert not model.beats_base_rate


def test_a_model_that_accepts_everything_is_called_out_too():
    model = LearnedFilter(
        features=["bias"], weights=np.zeros(1), train_trades=200,
        test_trades=100, base_rate=0.314, accuracy=0.314,
        kept_win_rate=0.314, kept_fraction=1.0)
    assert model.degenerate
    assert "not filtering anything" in model.describe()


def test_a_real_filter_is_compared_against_the_base_rate():
    model = LearnedFilter(
        features=["bias", "x"], weights=np.zeros(2), train_trades=200,
        test_trades=100, base_rate=0.30, accuracy=0.62,
        kept_win_rate=0.45, kept_fraction=0.4)
    assert not model.degenerate
    assert model.beats_base_rate
    text = model.describe()
    assert "45.0%" in text and "30.0%" in text and "beats" in text


# --------------------------------------------------------------------------
# The dialog
# --------------------------------------------------------------------------


@pytest.fixture
def dialog(qapp, tmp_path, bars):
    from tradingbacktester.config import AppSettings, Workspace
    from tradingbacktester.ui.dialogs.variants_dialog import VariantsDialog
    from tradingbacktester.ui.main_window import MainWindow

    workspace = Workspace(tmp_path).ensure()
    settings = AppSettings()
    settings.workspace_dir = str(tmp_path)
    window = MainWindow(settings, workspace)
    spec = builtin.macd_trend()
    window.strategies.save(spec)
    return VariantsDialog(spec, bars, BacktestConfig(), window), window, spec


def test_the_dialog_starts_with_nothing_to_save(dialog):
    d, _window, _spec = dialog
    assert not d.keep_button.isEnabled()
    assert d.table.rowCount() == 0


def test_the_dialog_lists_the_baseline_and_every_usable_variant(dialog, bars):
    d, _window, spec = dialog
    report = search_variants(spec, bars, BacktestConfig())
    d._on_done(report)
    assert d.table.rowCount() == 1 + len(report.usable)


def test_the_table_sorts_on_value_not_on_the_rendered_text(dialog, bars):
    """Sorted as text, "-703.32" ranks above "+356.42" and the whole dialog
    silently reverses."""
    from PySide6.QtCore import Qt

    d, _window, spec = dialog
    d._on_done(search_variants(spec, bars, BacktestConfig()))
    values = [float(d.table.item(r, 2).text().replace(",", ""))
              for r in range(d.table.rowCount())]
    assert values == sorted(values, reverse=True)

    d.table.sortItems(5, Qt.SortOrder.AscendingOrder)
    drawdowns = [float(d.table.item(r, 5).text().rstrip("%").replace(",", ""))
                 for r in range(d.table.rowCount())]
    assert drawdowns == sorted(drawdowns)


def test_the_headline_is_green_only_when_it_survived(dialog, bars):
    d, _window, spec = dialog
    report = search_variants(spec, bars, BacktestConfig())
    d._on_done(report)
    style = d.headline.styleSheet()
    from tradingbacktester.ui.theme import PALETTE

    if report.improved:
        assert PALETTE.long in style
    else:
        assert PALETTE.warning in style, (
            "a result that did not survive was shown in the success colour")


def test_saving_a_variant_records_how_many_were_tried(dialog, bars,
                                                      monkeypatch):
    """The number and what produced it must never be separated."""
    import tradingbacktester.ui.dialogs.variants_dialog as VD

    monkeypatch.setattr(VD, "show_info", lambda *a, **k: None)
    d, window, spec = dialog
    report = search_variants(spec, bars, BacktestConfig())
    d._on_done(report)
    if report.best is None:
        pytest.skip("nothing to save on this fixture")
    d.on_keep()

    saved = [e for e in window.strategies.list() if e.name != spec.name]
    assert len(saved) == 1
    kept = window.strategies.load(saved[0].id)
    assert str(report.tried) in kept.description
    assert ("did NOT survive" in kept.description
            or "survived" in kept.description)
    assert "variant" in kept.tags
    kept.validate()


def test_a_failed_search_says_so_without_a_traceback(dialog):
    d, _window, _spec = dialog
    d._on_failed("Load a dataset first.")
    assert "Load a dataset" in d.headline.text()
    assert "Traceback" not in d.detail.toPlainText()
