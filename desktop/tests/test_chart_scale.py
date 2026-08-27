"""The chart at scale: the freeze this file exists to prevent.

A user reported the application opening as a white, unresponsive window.  The
cause was not packaging or the window system: it was the chart doing work
proportional to the *file* rather than to the screen.  ``pg.FillBetweenItem``
builds one ``QPainterPath`` over every point the moment it is constructed --
about two seconds for the shipped 581,195-bar US30 5-minute dataset, three
times over for a Bollinger band -- and ``pg.BarGraphItem`` was handed one
``QBrush`` per bar to colour a histogram by sign.  All of it ran on the GUI
thread before the window could paint.

So these tests assert two different things.  The unit tests below fix the
behaviour of the replacements, and :func:`test_a_large_chart_opens_promptly`
puts a wall-clock ceiling on the whole path, because the defect was never a
wrong pixel -- it was time.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

pytestmark = pytest.mark.gui

pg = pytest.importorskip("pyqtgraph")

from tradingbacktester.ui.widgets.chart_items import (  # noqa: E402
    BandFillItem, HistogramItem, _envelope, _peak, _runs, _stride,
    clip_to_view)


# ---------------------------------------------------------------------------
# the helpers
# ---------------------------------------------------------------------------

def test_runs_finds_every_span_of_true():
    assert _runs([0, 1, 1, 0, 1, 0, 0, 1, 1, 1]) == [(1, 3), (4, 5), (7, 10)]


def test_runs_handles_the_empty_and_the_all_false_case():
    assert _runs([]) == []
    assert _runs([0, 0, 0]) == []
    assert _runs([1, 1, 1]) == [(0, 3)]


def test_peak_keeps_the_extreme_of_each_column():
    # A spike sampled away is a spike the user never sees.  Peak selection takes
    # the value furthest from zero in each column, so it survives.
    xs = np.arange(9, dtype="float64")
    values = np.array([1.0, -8.0, 2.0, 3.0, 0.5, 1.0, -2.0, 7.0, 1.0])
    kept_x, kept_v = _peak(xs, values, 3)
    assert list(kept_v) == [-8.0, 3.0, 7.0]
    assert list(kept_x) == [1.0, 3.0, 7.0]


def test_peak_leaves_a_short_series_alone():
    xs = np.arange(2, dtype="float64")
    values = np.array([1.0, 2.0])
    kept_x, kept_v = _peak(xs, values, 5)
    assert list(kept_v) == [1.0, 2.0]


def test_peak_keeps_the_ragged_tail():
    xs = np.arange(7, dtype="float64")
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 99.0])
    _, kept = _peak(xs, values, 3)
    assert 99.0 in list(kept)


def test_envelope_contains_both_edges_whichever_is_on_top():
    a = np.array([3.0, 1.0, 4.0, 1.0, 5.0, 9.0])
    b = np.array([1.0, 2.0, 1.0, 2.0, 1.0, 2.0])
    x = np.arange(6, dtype="float64")
    forward = _envelope(x, a, b, 2)
    reversed_ = _envelope(x, b, a, 2)
    # The band between two curves does not care which was named "upper": a
    # Donchian channel at a new extreme, or a squeeze, crosses its own edges.
    for got, expected_hi, expected_lo in ((forward, [3, 4, 9], [1, 1, 1]),
                                          (reversed_, [3, 4, 9], [1, 1, 1])):
        _, hi, lo = got
        assert list(hi) == expected_hi
        assert list(lo) == expected_lo


def test_stride_is_one_without_a_view():
    assert _stride(BandFillItem(), 10_000) == 1


def test_clip_to_view_declines_an_item_that_has_no_plot(qapp):
    # pyqtgraph caches whatever getViewBox() answers, and an item with no plot
    # answers with the enclosing graphics widget -- which then raises on the
    # next paint.  The helper must refuse rather than arm that.
    curve = pg.PlotDataItem(np.arange(10.0), np.arange(10.0))
    clip_to_view(curve)
    assert curve.opts["clipToView"] is False


def test_clip_to_view_arms_an_item_that_is_in_a_plot(qapp):
    win = pg.GraphicsLayoutWidget()
    plot = win.addPlot()
    curve = plot.plot(np.arange(10.0), np.arange(10.0))
    clip_to_view(curve)
    assert curve.opts["clipToView"] is True
    assert curve.opts["autoDownsample"] is True
    win.close()


# ---------------------------------------------------------------------------
# the items
# ---------------------------------------------------------------------------

def test_band_fill_bounds_ignore_the_warmup_nans(qapp):
    upper = np.array([np.nan, np.nan, 5.0, 6.0, 7.0])
    lower = np.array([np.nan, np.nan, 1.0, 2.0, 3.0])
    item = BandFillItem(upper, lower)
    rect = item.boundingRect()
    assert rect.top() == pytest.approx(1.0)
    assert rect.bottom() == pytest.approx(7.0)


def test_band_fill_of_an_all_nan_series_has_no_extent(qapp):
    nans = np.full(50, np.nan)
    assert BandFillItem(nans, nans).boundingRect().isEmpty()


def test_band_fill_of_nothing_draws_nothing(qapp):
    item = BandFillItem()
    assert item.boundingRect().isEmpty()
    assert len(item._a) == 0


def test_band_fill_truncates_to_the_shorter_edge(qapp):
    item = BandFillItem(np.arange(10.0), np.arange(4.0))
    assert len(item._a) == len(item._b) == 4


def test_histogram_bounds_always_span_zero(qapp):
    # The bars are drawn from the zero line, so a series that never goes
    # negative still needs zero inside the box or the bars are clipped away.
    item = HistogramItem(np.array([3.0, 5.0, 4.0]))
    rect = item.boundingRect()
    assert rect.top() == pytest.approx(0.0)
    assert rect.bottom() == pytest.approx(5.0)


def test_histogram_treats_nan_as_no_bar(qapp):
    item = HistogramItem(np.array([np.nan, 2.0, np.nan]))
    assert np.isfinite(item._v).all()
    assert item.boundingRect().bottom() == pytest.approx(2.0)


def test_histogram_of_nothing_is_empty(qapp):
    assert HistogramItem(np.empty(0)).boundingRect().isEmpty()


# ---------------------------------------------------------------------------
# the regression that matters
# ---------------------------------------------------------------------------

#: Half a million bars is the shipped US30 5-minute file.  Anything the chart
#: does that is proportional to that number, rather than to the width of the
#: widget, is a freeze waiting for a user with a large dataset.
BIG = 500_000

#: Generous: this runs headless on a shared CI runner.  The defect it guards
#: against took the same path from twenty-one seconds to under two, so a
#: three-second ceiling catches a regression long before a user would.
BUDGET_SECONDS = 3.0


def _band(n: int):
    rng = np.random.default_rng(4)
    mid = np.cumsum(rng.normal(0.0, 1.0, n)) + 1000.0
    width = 5.0 + np.abs(np.sin(np.arange(n) / 500.0)) * 5.0
    upper, lower = mid + width, mid - width
    upper[:200] = np.nan          # an indicator's warm-up
    lower[:200] = np.nan
    return upper, lower


def test_a_band_over_half_a_million_bars_is_built_promptly(qapp):
    upper, lower = _band(BIG)
    started = time.monotonic()
    for _ in range(3):            # a Bollinger band is three of these
        BandFillItem(upper, lower)
    elapsed = time.monotonic() - started
    assert elapsed < BUDGET_SECONDS, (
        f"three bands over {BIG:,} bars took {elapsed:.1f}s to build; "
        f"pg.FillBetweenItem took about two seconds each, which is the "
        f"white-screen freeze this replaced")


def test_a_histogram_over_half_a_million_bars_is_built_promptly(qapp):
    rng = np.random.default_rng(5)
    values = np.cumsum(rng.normal(0.0, 1.0, BIG))
    started = time.monotonic()
    HistogramItem(values, "#2ecc71", "#e74c3c")
    elapsed = time.monotonic() - started
    # Tighter than BUDGET_SECONDS on purpose: the replaced BarGraphItem took
    # 1.5s here, so a three-second ceiling would have let the defect through.
    assert elapsed < 0.5, (
        f"a {BIG:,}-bar histogram took {elapsed:.2f}s; the replaced "
        f"BarGraphItem was handed one QBrush per bar and took 1.5s")


def test_painting_a_band_costs_the_view_not_the_file(qapp):
    """The whole point: zooming out must not cost more than zooming in."""
    from PySide6.QtGui import QColor, QImage, QPainter

    upper, lower = _band(BIG)
    win = pg.GraphicsLayoutWidget()
    win.resize(900, 400)
    plot = win.addPlot()
    plot.addItem(BandFillItem(upper, lower, brush=QColor("#4aa3ff")))
    finite = np.isfinite(upper)
    plot.setYRange(float(lower[finite].min()), float(upper[finite].max()),
                   padding=0.02)
    win.show()

    def paint(x0: float, x1: float) -> float:
        plot.setXRange(x0, x1, padding=0)
        qapp.processEvents()
        image = QImage(900, 400, QImage.Format.Format_ARGB32)
        image.fill(QColor("black"))
        painter = QPainter(image)
        started = time.monotonic()
        win.render(painter)
        taken = time.monotonic() - started
        painter.end()
        return taken

    zoomed_in = paint(1000.0, 1300.0)
    zoomed_out = paint(0.0, float(BIG))
    win.close()
    assert zoomed_out < BUDGET_SECONDS, (
        f"painting the whole {BIG:,}-bar band took {zoomed_out:.1f}s")
    # Not a strict ratio -- a paint has a fixed cost that dominates when the
    # data is small -- but the two must be the same order of magnitude.  Before
    # the fix the zoomed-out paint was hundreds of times the zoomed-in one.
    assert zoomed_out < max(zoomed_in * 20.0, 0.5), (
        f"zoomed out {zoomed_out:.3f}s against {zoomed_in:.3f}s zoomed in: "
        f"the cost is still following the file rather than the view")


# ---------------------------------------------------------------------------
# the whole launch, which is what the user reported
# ---------------------------------------------------------------------------

#: What a second launch is allowed to cost when the remembered dataset is a
#: large one.  Measured on the 200,000-bar dataset this test builds: 6.53s
#: before the fix, 1.22s after.  Four seconds sits between them with room for a
#: shared CI runner, and it is set from those two numbers rather than picked --
#: a ceiling above the defect is not a regression test.  (The user's report was
#: the shipped 581,195-bar file, where the same path took 21s and Windows
#: paints the window white and titles it "Not Responding".)
LAUNCH_BUDGET_SECONDS = 4.0


def test_reopening_on_a_large_dataset_does_not_freeze(tmp_path, qapp):
    """Open, import a large dataset, then reopen the way a user would.

    The first run is not the interesting one: it seeds small samples.  The
    freeze arrived on the *next* launch, once a large dataset was the one the
    application remembered, because the chart then drew the whole file before
    the window could paint.
    """
    from tradingbacktester.config import AppSettings
    from tradingbacktester.core.timeframe import Timeframe
    from tradingbacktester.data.sample import generate_sample_data
    from tradingbacktester.storage.workspace import bootstrap
    from tradingbacktester.ui.main_window import MainWindow

    settings = AppSettings()
    settings.workspace_dir = str(tmp_path / "ws")
    workspace = bootstrap(settings)

    window = MainWindow(settings, workspace, None)
    window.resize(1400, 860)
    window.show()
    window._first_run()
    qapp.processEvents()

    bars = generate_sample_data("BIG", Timeframe.parse("5m"), n_bars=200_000,
                                seed=3)
    meta = window.datasets.add_from_bars(bars, name="BIG 5m")
    settings.last_dataset = meta.id
    window.close()
    qapp.processEvents()

    started = time.monotonic()
    reopened = MainWindow(settings, workspace, None)
    reopened.resize(1400, 860)
    reopened.show()
    reopened._first_run()
    qapp.processEvents()
    elapsed = time.monotonic() - started
    print(f"\nreopen on {len(bars):,} bars: {elapsed:.2f}s "
          f"(budget {LAUNCH_BUDGET_SECONDS:.0f}s)")

    assert reopened._view_bars is not None, "the remembered dataset never opened"
    assert len(reopened._view_bars) == len(bars)
    reopened.close()
    qapp.processEvents()
    assert elapsed < LAUNCH_BUDGET_SECONDS, (
        f"reopening on a {len(bars):,}-bar dataset took {elapsed:.1f}s. That "
        f"is the white unresponsive window the user reported; the chart is "
        f"doing work proportional to the file again")


def test_the_dataset_cache_serves_the_second_read(tmp_path, qapp):
    """Opening reads the remembered dataset more than once; parsing it twice is
    a second of the launch spent on nothing."""
    from tradingbacktester.core.timeframe import Timeframe
    from tradingbacktester.data.repository import DatasetRepository
    from tradingbacktester.data.sample import generate_sample_data
    from tradingbacktester.storage.workspace import Workspace

    workspace = Workspace(tmp_path / "ws")
    workspace.ensure()
    repo = DatasetRepository(workspace)
    bars = generate_sample_data("C", Timeframe.parse("1h"), n_bars=500, seed=1)
    meta = repo.add_from_bars(bars, name="C 1h")

    first = repo.load_bars(meta.id)
    second = repo.load_bars(meta.id)
    assert second is first, "the second read re-parsed the file"

    repo.forget_cached_bars()
    third = repo.load_bars(meta.id)
    assert third is not first
    assert np.array_equal(third.close, first.close)


def test_the_dataset_cache_notices_the_file_changing(tmp_path, qapp):
    """Re-importing over a dataset must not serve the old bars back."""
    from tradingbacktester.core.timeframe import Timeframe
    from tradingbacktester.data.repository import DatasetRepository
    from tradingbacktester.data.sample import generate_sample_data
    from tradingbacktester.storage.workspace import Workspace

    workspace = Workspace(tmp_path / "ws")
    workspace.ensure()
    repo = DatasetRepository(workspace)
    original = generate_sample_data("C", Timeframe.parse("1h"), n_bars=500, seed=1)
    meta = repo.add_from_bars(original, name="C 1h")
    repo.load_bars(meta.id)

    replacement = generate_sample_data("C", Timeframe.parse("1h"), n_bars=800,
                                       seed=2)
    repo.remove(meta.id)
    new_meta = repo.add_from_bars(replacement, name="C 1h")
    assert len(repo.load_bars(new_meta.id)) == 800


# ---------------------------------------------------------------------------
# a saved window position that cannot be used
# ---------------------------------------------------------------------------
#
# Qt 6 already clamps a geometry restored onto a monitor that is no longer
# attached -- saving at (-9000, -9000) and restoring gives a position on the
# remaining screen -- so that case needs no code here and gets no test
# pretending otherwise.  What is NOT handled is a settings file whose saved
# fields are not what the reader expects, and that one is fatal: it raises
# inside MainWindow.__init__, so there is no window at all.


def _settings_and_workspace(tmp_path):
    from tradingbacktester.config import AppSettings
    from tradingbacktester.storage.workspace import bootstrap

    settings = AppSettings()
    settings.workspace_dir = str(tmp_path / "ws")
    return settings, bootstrap(settings)


@pytest.mark.parametrize("saved", ["caf\u00e9", "\u2014dash", "not base64!!", ""])
def test_an_unreadable_saved_geometry_still_opens_a_window(saved, tmp_path, qapp):
    """Non-ASCII in the field raises UnicodeEncodeError on the .encode("ascii")
    the restore does, and it raises during construction -- so before this the
    application did not open at all, it failed."""
    from tradingbacktester.ui.main_window import MainWindow

    settings, workspace = _settings_and_workspace(tmp_path)
    settings.window_geometry = saved
    settings.window_state = saved
    window = MainWindow(settings, workspace, None)
    window.show()
    qapp.processEvents()
    assert window.isVisible()
    assert window.width() > 0 and window.height() > 0
    window.close()
    qapp.processEvents()


def test_the_on_screen_check_rejects_a_window_off_the_desktop(tmp_path, qapp):
    """The guard's own logic, tested directly rather than through Qt's restore.

    It is defence in depth behind Qt's clamping: a window that ends up off the
    desktop is invisible, and so is every modal dialog centred on it, which is
    an application that never answers and never says why.
    """
    from tradingbacktester.ui.main_window import MainWindow

    settings, workspace = _settings_and_workspace(tmp_path)
    window = MainWindow(settings, workspace, None)
    window.resize(900, 600)
    window.move(-9000, -9000)
    qapp.processEvents()
    assert not window._on_a_screen()

    window._centre_on_primary()
    qapp.processEvents()
    assert window._on_a_screen()
    window.close()
    qapp.processEvents()
