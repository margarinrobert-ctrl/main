"""Every plain-text report must fit the width it declares.

A line that overruns is not truncated by the terminal, it wraps — and a table
row that wraps at an arbitrary column puts half a number on the next line,
which is worse than no table at all. These reports were written with the width
in mind and still drifted past it: an indicator-study paragraph reached 197
characters and a walk-forward row 144, because an f-string that fits when the
numbers are small does not when they are not.

So the widths are asserted here rather than trusted, at two widths, on real
data, for every formatter the CLI can print.
"""

from __future__ import annotations

import pytest

from tradingbacktester.core.textfmt import DEFAULT_WIDTH, fit, row


# --------------------------------------------------------------------------
# The helper
# --------------------------------------------------------------------------

def test_fit_never_returns_nothing():
    """Callers `extend` with the result; an empty list would silently drop it."""
    assert fit("") == [""]
    assert fit("   ") == [""]
    assert fit("", indent="   ") == [""]


def test_fit_hangs_the_continuations():
    lines = fit("label: " + " ".join(["word"] * 40), width=40, hang=7)
    assert len(lines) > 1
    assert lines[0].startswith("label: ")
    assert all(line.startswith(" " * 7) for line in lines[1:])
    assert all(len(line) <= 40 for line in lines)


def test_fit_does_not_break_an_identifier_in_half():
    """A broken symbol cannot be copied back out of a terminal."""
    long_name = "close_position_in_bar_over_atr_200_rank_something_long"
    lines = fit(f"feature: {long_name}", width=30)
    assert long_name in " ".join(lines)


def test_row_keeps_the_numeric_columns_in_line():
    cells = f"   {'event':<24} {'12':>7}  "
    lines = row(cells, "a verdict long enough that it has to wrap somewhere",
                width=60)
    assert len(lines) > 1
    assert all(len(line) <= 60 for line in lines)
    # Continuations align under where the prose started, not under column one.
    assert lines[1].startswith(" " * len(cells))


def test_row_without_prose_is_just_the_cells():
    assert row("   a   b   ", "") == ["   a   b"]


# --------------------------------------------------------------------------
# The reports themselves, on real data
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def bars():
    from tradingbacktester.data.bundled import find
    from tradingbacktester.data.csv_loader import load_csv, sniff_csv
    from tradingbacktester.data.instruments import default_instrument_for

    dataset = find("US30 30m")
    assert dataset is not None and dataset.exists()
    path = str(dataset.path())
    return load_csv(path, sniff_csv(path).mapping,
                    default_instrument_for("US30"))


@pytest.fixture(scope="module")
def run(bars):
    from tradingbacktester.core.types import BacktestConfig
    from tradingbacktester.engine.backtester import Backtester
    from tradingbacktester.strategy.builtin import BUILTIN_STRATEGIES

    spec = BUILTIN_STRATEGIES["MACD Trend"]()
    config = BacktestConfig(starting_capital=100_000.0)
    config.exits, config.execution = spec.exits, spec.execution
    config.session, config.costs, config.risk = spec.session, spec.costs, spec.risk
    result = Backtester(bars, spec, config).run()
    assert result.trades
    return spec, config, result


def _check(text: str, width: int, label: str) -> None:
    over = [(len(line), line) for line in text.splitlines() if len(line) > width]
    assert not over, (
        f"{label}: {len(over)} line(s) over {width} columns, "
        f"longest {max(n for n, _ in over)}: {max(over)[1][:90]!r}")
    assert text.strip(), f"{label} produced nothing"


WIDTHS = (78, 100)


@pytest.mark.parametrize("width", WIDTHS)
def test_strategy_search_report_fits(bars, width):
    from tradingbacktester.finder import find_strategies, style
    from tradingbacktester.finder.report import format_report

    report = find_strategies(bars, style("intraday"), control_draws=50)
    _check(format_report(report, width=width), width, "strategy search")


@pytest.mark.parametrize("width", WIDTHS)
def test_indicator_study_report_fits(bars, width):
    from tradingbacktester.finder import style
    from tradingbacktester.research.report import format_study
    from tradingbacktester.research.study import study_features

    study = study_features(bars, style("swing"), side=-1)
    _check(format_study(study, width=width), width, "indicator study")


@pytest.mark.parametrize("width", WIDTHS)
def test_anomaly_scan_report_fits(bars, width):
    from tradingbacktester.finder import style
    from tradingbacktester.research.anomalies import scan
    from tradingbacktester.research.report import format_anomalies

    found = scan(bars, style("intraday"), control_draws=100)
    _check(format_anomalies(found, width=width), width, "anomaly scan")


@pytest.mark.parametrize("width", WIDTHS)
def test_walk_forward_report_fits(bars, run, width):
    """Four swept parameters is 60 characters of parameter list on its own."""
    from tradingbacktester.optimize.grid import ParameterRange
    from tradingbacktester.optimize.walkforward import (format_walk_forward,
                                                        walk_forward)

    spec, config, _ = run
    result = walk_forward(bars, spec, config,
                          [ParameterRange("macd_fast", 10, 14, 2),
                           ParameterRange("macd_slow", 24, 28, 4),
                           ParameterRange("trend_period", 180, 200, 20)],
                          folds=3, minimum_trades=1)
    _check(format_walk_forward(result, bars, width=width), width, "walk-forward")


@pytest.mark.parametrize("width", WIDTHS)
def test_monte_carlo_report_fits(run, width):
    from tradingbacktester.analytics.montecarlo import (format_monte_carlo,
                                                        resample_result)

    _, _, result = run
    mc = resample_result(result, draws=300)
    _check(format_monte_carlo(mc, width=width), width, "monte carlo")


@pytest.mark.parametrize("width", WIDTHS)
def test_mirror_report_fits(bars, run, width):
    from tradingbacktester.research.mirror import format_mirror, mirror_test

    spec, config, _ = run
    report = mirror_test(bars, spec, config)
    _check(format_mirror(report, width=width), width, "mirror")


def test_the_dataset_listing_fits(tmp_path, capsys):
    """`cli data` printed a 167-character line for a shipped dataset."""
    from tradingbacktester.cli import main

    assert main(["--workspace", str(tmp_path), "data"]) == 0
    _check(capsys.readouterr().out, DEFAULT_WIDTH, "cli data")


# --------------------------------------------------------------------------
# The exported report
# --------------------------------------------------------------------------

def test_report_money_reads_as_money_not_as_a_currency_code(run):
    """Every one of ~860 figures in an exported report read "USD1,534.04"."""
    import re

    from tradingbacktester.reports.html_report import build_html_report

    _, _, result = run
    html = build_html_report(result)
    assert not re.search(r"USD[0-9]", html), "an ISO code jammed onto the digits"
    assert re.search(r"\$[0-9][0-9,]*\.[0-9]{2}", html), "no money at all?"


def test_an_unknown_currency_keeps_its_code_and_gains_a_space():
    from tradingbacktester.core.presentation import currency_symbol

    assert currency_symbol("SEK") == "SEK "
    assert currency_symbol("usd") == "$"
    assert currency_symbol("") == ""
    assert currency_symbol(None) == ""


def test_the_report_carries_the_monte_carlo_and_its_caveat(run):
    """The report is what gets shared; a lone equity curve reads as the outcome."""
    from tradingbacktester.reports.html_report import build_html_report

    _, _, result = run
    html = build_html_report(result)
    assert "What else could have happened" in html
    assert "resampled runs over these" in html
    assert "cannot tell you whether the strategy has an edge" in html
    assert "size an account against" in html


def test_the_report_still_builds_when_resampling_cannot_run(run, monkeypatch):
    """A failed resampling must cost a section, never the whole report."""
    from tradingbacktester.reports.html_report import build_html_report

    def boom(*args, **kwargs):
        raise RuntimeError("no")

    monkeypatch.setattr("tradingbacktester.analytics.montecarlo.resample_result",
                        boom)
    _, _, result = run
    html = build_html_report(result)
    assert "What else could have happened" not in html
    assert "Where the money came from" in html, "the rest must survive"


def test_the_report_makes_no_network_requests(run):
    """A self-contained report is a stated requirement, not an aspiration."""
    import re

    from tradingbacktester.reports.html_report import build_html_report

    _, _, result = run
    html = build_html_report(result)
    assert not re.findall(r'(?:src|href)\s*=\s*["\']https?://', html)
    assert not re.findall(r'url\(["\']?https?://', html)
    assert "<script" not in html


# --------------------------------------------------------------------------
# The PDF keeps its own block list, so a section added to the HTML is not
# automatically in it. That is exactly how this one was missed once.
# --------------------------------------------------------------------------

def _pdf_headings(result, path):
    """Render a PDF and record the headings and paragraphs it actually drew.

    Qt writes PDF text as glyph indices against an embedded subset, so the
    bytes cannot be searched for a phrase. Spying on the canvas is the honest
    way to assert what the document contains.
    """
    from tradingbacktester.reports import pdf_report

    headings: list[str] = []
    paragraphs: list[str] = []
    real_heading = pdf_report._Canvas.heading
    real_paragraph = pdf_report._Canvas.paragraph

    def heading(self, title):
        headings.append(title)
        return real_heading(self, title)

    def paragraph(self, text, *args, **kwargs):
        paragraphs.append(text)
        return real_paragraph(self, text, *args, **kwargs)

    pdf_report._Canvas.heading = heading
    pdf_report._Canvas.paragraph = paragraph
    try:
        pdf_report.export_pdf_report(result, str(path))
    finally:
        pdf_report._Canvas.heading = real_heading
        pdf_report._Canvas.paragraph = real_paragraph
    return headings, paragraphs


@pytest.mark.gui
def test_the_pdf_carries_the_monte_carlo_too(run, tmp_path):
    _, _, result = run
    headings, paragraphs = _pdf_headings(result, tmp_path / "r.pdf")
    assert "What else could have happened" in headings
    joined = " ".join(paragraphs)
    assert "resampled runs over these" in joined
    assert "cannot tell you whether the strategy has an edge" in joined
    assert "size an account against" in joined
    assert (tmp_path / "r.pdf").stat().st_size > 10_000


@pytest.mark.gui
def test_the_pdf_money_reads_as_money(run, tmp_path):
    import re

    _, _, result = run
    _headings, paragraphs = _pdf_headings(result, tmp_path / "r.pdf")
    joined = " ".join(paragraphs)
    assert not re.search(r"USD[0-9]", joined)
    assert re.search(r"\$[0-9][0-9,]*", joined)


@pytest.mark.gui
def test_the_pdf_still_writes_when_resampling_cannot_run(run, tmp_path,
                                                         monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("no")

    monkeypatch.setattr("tradingbacktester.analytics.montecarlo.resample_result",
                        boom)
    _, _, result = run
    headings, _paragraphs = _pdf_headings(result, tmp_path / "r.pdf")
    assert "What else could have happened" not in headings
    assert "Trades" in headings, "the rest of the document must survive"
    assert (tmp_path / "r.pdf").stat().st_size > 10_000


@pytest.mark.gui
def test_both_reports_agree_on_which_sections_exist(run, tmp_path):
    """The HTML and the PDF are the same document in two formats.

    They are assembled by two separate lists, so one can silently gain a
    section the other lacks. This does not demand identical structure — the
    PDF has no chart legend and the HTML no page footer — only that the
    analyses a reader would act on appear in both.
    """
    from tradingbacktester.reports.html_report import build_html_report

    _, _, result = run
    html = build_html_report(result)
    headings, _ = _pdf_headings(result, tmp_path / "r.pdf")
    for section in ("What else could have happened", "Trades"):
        assert section in html, f"{section} missing from the HTML report"
        assert section in headings, f"{section} missing from the PDF report"


def test_pdf_export_works_with_no_display_at_all(run, tmp_path, monkeypatch):
    """It used to abort the process — a library that kills its caller.

    Qt's default platform plugin on Linux is X11 or Wayland, and with neither
    available its failure is a `qFatal`, not an exception. That made
    `export_pdf_report` unusable from a script or a scheduled job, which is
    precisely what its own docstring promises it supports.
    """
    from tradingbacktester.reports.pdf_report import _needs_offscreen

    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr("sys.platform", "linux")
    assert _needs_offscreen() is True

    # A caller who has chosen a platform keeps it.
    monkeypatch.setenv("QT_QPA_PLATFORM", "wayland")
    assert _needs_offscreen() is False
    monkeypatch.delenv("QT_QPA_PLATFORM")

    # A display present means Qt can do its normal thing.
    monkeypatch.setenv("DISPLAY", ":0")
    assert _needs_offscreen() is False
    monkeypatch.delenv("DISPLAY")

    # Windows and macOS always have a window system.
    for platform in ("win32", "darwin"):
        monkeypatch.setattr("sys.platform", platform)
        assert _needs_offscreen() is False
