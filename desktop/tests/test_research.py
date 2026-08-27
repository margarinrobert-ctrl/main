"""The indicator study and the anomaly scan.

Two things are being tested here and only one of them is the code. The other is
the statistics: an information coefficient computed without correcting for
overlapping observations will call noise a discovery, and the test below
demonstrates that on data with no edge in it at all.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from tradingbacktester.data.bundled import find as find_bundled
from tradingbacktester.data.csv_loader import load_csv, sniff_csv
from tradingbacktester.data.instruments import default_instrument_for
from tradingbacktester.finder.styles import style
from tradingbacktester.research import (DETECTORS, all_features,
                                        compute_matrix, evaluate,
                                        format_anomalies, format_study,
                                        newey_west, redundancy_groups, scan,
                                        study_features)
from tradingbacktester.research.ic import (decile_profile, rank_standardise,
                                           two_sided_p)


@pytest.fixture(scope="module")
def us30_30m():
    dataset = find_bundled("US30 30m")
    assert dataset is not None and dataset.exists()
    return load_csv(str(dataset.path()), sniff_csv(str(dataset.path())).mapping,
                    default_instrument_for("US30"))


# --------------------------------------------------------------------------
# Features
# --------------------------------------------------------------------------

def test_no_feature_can_see_the_future(us30_30m):
    """Truncate the series; every earlier value must be unchanged.

    This is the only test that matters for a feature library. A look-ahead
    here is invisible in the output and produces a beautiful, entirely
    fictional study.
    """
    features = all_features()
    full, features = compute_matrix(us30_30m, features)
    cut = len(us30_30m) - 300
    short, _ = compute_matrix(us30_30m.slice(0, cut), features)

    drifted = []
    for column, feature in enumerate(features):
        a, b = full[:cut, column], short[:, column]
        both = np.isfinite(a) & np.isfinite(b)
        if not both.any():
            continue
        if float(np.max(np.abs(a[both] - b[both]))) > 1e-9:
            drifted.append(feature.name)
    assert not drifted, f"these features changed when the future was removed: {drifted}"


def test_every_feature_produces_usable_numbers(us30_30m):
    matrix, features = compute_matrix(us30_30m)
    assert len(features) > 40
    finite = np.isfinite(matrix).mean(axis=0)
    thin = [f.name for f, share in zip(features, finite) if share < 0.5]
    assert not thin, f"mostly empty: {thin}"
    # Scale-free: nothing should be in the tens of thousands, which is what a
    # raw price would be on this instrument.
    huge = [f.name for f, column in zip(features, matrix.T)
            if np.nanmax(np.abs(column)) > 5_000]
    assert not huge, f"these look like raw prices, not scale-free: {huge}"


def test_features_have_names_families_and_descriptions():
    seen = set()
    for feature in all_features():
        assert feature.name and feature.name not in seen
        seen.add(feature.name)
        assert feature.family
        assert feature.description.endswith(".") or len(feature.description) > 20


# --------------------------------------------------------------------------
# The statistics
# --------------------------------------------------------------------------

def test_newey_west_matches_the_theory_for_an_ar1():
    """For an AR(1), the long-run standard error is sqrt((1+p)/(1-p)) times
    the naive one. The estimator has to get close to that or it is not
    correcting anything."""
    rng = np.random.default_rng(5)
    n = 50_000
    phi = 0.9
    noise = rng.normal(size=n)
    series = np.empty(n)
    series[0] = noise[0]
    for i in range(1, n):
        series[i] = phi * series[i - 1] + noise[i]

    _, naive = newey_west(series, 0)
    _, corrected = newey_west(series, 60)
    theory = math.sqrt((1 + phi) / (1 - phi))
    assert corrected > naive
    assert 0.7 * theory < corrected / naive < 1.3 * theory


def test_ignoring_overlap_turns_noise_into_discoveries():
    """The whole reason the correction exists, measured as a false-positive rate.

    A persistent feature against an overlapping forward return, with no
    relationship whatsoever between them. A 5% test should reject 5% of the
    time. Uncorrected it rejects far more often, which is exactly how an
    indicator study produces a dozen "significant" findings from nothing. One
    draw would not show this -- the naive statistic is only *sometimes* large
    -- so the rate is measured over many.
    """
    rounds = 60
    n = 5_000
    horizon = 20
    naive_rejections = 0
    corrected_rejections = 0

    for seed in range(rounds):
        rng = np.random.default_rng(1000 + seed)
        feature = np.empty(n)
        feature[0] = 0.0
        for i in range(1, n):
            feature[i] = 0.95 * feature[i - 1] + rng.normal()
        steps = rng.normal(size=n)
        forward = np.convolve(steps[::-1], np.ones(horizon),
                              mode="full")[:n][::-1]
        if evaluate("f", feature, forward, lag=0).p_value < 0.05:
            naive_rejections += 1
        if evaluate("f", feature, forward, lag=horizon).p_value < 0.05:
            corrected_rejections += 1

    naive_rate = naive_rejections / rounds
    corrected_rate = corrected_rejections / rounds
    assert naive_rate > 0.20, (
        f"the fixture did not reproduce the problem: naive rejection rate "
        f"{naive_rate:.0%}")
    assert corrected_rate < naive_rate / 2.0, (
        f"the correction did not help: {corrected_rate:.0%} against "
        f"{naive_rate:.0%}")
    assert corrected_rate < 0.25


def test_a_real_edge_is_still_found_after_the_correction():
    rng = np.random.default_rng(2)
    n = 30_000
    feature = rng.normal(size=n)
    target = 0.35 * feature + rng.normal(size=n)
    result = evaluate("f", feature, target, lag=10)
    assert result.ic > 0.25
    assert result.p_value < 0.001
    assert result.monotonic > 0.9, "a linear relationship must read as monotone"
    assert result.spread > 0


def test_rank_standardise_is_scale_free_and_handles_ties():
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    a = rank_standardise(values)
    b = rank_standardise(values * 1000.0 + 7.0)
    assert a == pytest.approx(b)
    assert a.mean() == pytest.approx(0.0)
    assert a.std() == pytest.approx(1.0)
    # Ties share a rank rather than being ordered arbitrarily.
    tied = rank_standardise(np.array([1.0, 1.0, 1.0, 2.0]))
    assert tied[0] == pytest.approx(tied[1]) == pytest.approx(tied[2])


def test_decile_profile_on_hand_countable_data():
    feature = np.arange(1000, dtype="float64")
    target = np.where(feature >= 900, 10.0, 0.0)
    means, counts = decile_profile(feature, target)
    assert counts.sum() == 1000
    assert means[-1] == pytest.approx(10.0)
    assert means[0] == pytest.approx(0.0)


def test_two_sided_p_is_the_normal_tail():
    assert two_sided_p(0.0) == pytest.approx(1.0)
    assert two_sided_p(1.96) == pytest.approx(0.05, abs=0.001)
    assert two_sided_p(-1.96) == pytest.approx(0.05, abs=0.001)


def test_redundancy_grouping_finds_restatements():
    rng = np.random.default_rng(1)
    base = rng.normal(size=5_000)
    matrix = np.column_stack([base, base * 3.0 + 1.0, -base,
                              rng.normal(size=5_000)])
    groups = redundancy_groups(matrix, ["a", "a_scaled", "a_negated", "b"])
    biggest = max(groups, key=len)
    assert set(biggest) == {"a", "a_scaled", "a_negated"}
    assert ["b"] in groups


# --------------------------------------------------------------------------
# The study
# --------------------------------------------------------------------------

def test_the_study_runs_on_real_data_and_states_its_caveats(us30_30m):
    study = study_features(us30_30m, style("intraday"), timeframe="30m")
    assert study.tested > 40
    assert 0 < study.independent <= study.tested
    assert study.horizon == style("intraday").max_bars
    assert study.cost_per_trade > 0
    assert study.research_bars > 0 and study.holdout_bars > 0

    text = format_study(study)
    assert "independent groups" in text
    assert "Newey-West" in text
    assert "round turn" in text
    unwrapped = " ".join(text.split())
    assert "not an indicator that will predict the future" in unwrapped


def test_the_study_refuses_a_dataset_that_is_too_small(us30_30m):
    from tradingbacktester.core.errors import InsufficientDataError

    with pytest.raises(InsufficientDataError):
        study_features(us30_30m.slice(0, 400), style("intraday"),
                       timeframe="30m")


def test_a_feature_that_predicts_nothing_is_labelled_as_such(us30_30m):
    study = study_features(us30_30m, style("intraday"), timeframe="30m")
    assert any(f.verdict == "predicts nothing" for f in study.findings)
    for finding in study.findings:
        assert finding.verdict, f"{finding.name} has no verdict"
        if finding.feature.family == "session" and finding.research.significant:
            assert any("time-of-day" in c for c in finding.concerns)


# --------------------------------------------------------------------------
# Anomalies
# --------------------------------------------------------------------------

def _session_mask(bars, key: str = "intraday"):
    from tradingbacktester.finder.outcomes import session_entry_mask

    chosen = style(key)
    return session_entry_mask(
        bars, bars.instrument.timezone,
        chosen.session[0] if chosen.session else None,
        chosen.session[1] if chosen.session else None,
        chosen.weekdays, chosen.flat_at_session_end)


def test_no_detector_can_see_the_future(us30_30m):
    """Truncate the series; every surviving bar must keep its answer.

    The cheapest look-ahead test there is, and it earns its place: it caught
    "the last hour of the day", which read the day's FINAL bar to decide when
    the hour started. At 14:00 you do not know 16:00 will be the last one, and
    on the final day in the file you never find out.
    """
    from tradingbacktester.research.anomalies import _fire

    cut = len(us30_30m) - 300
    short = us30_30m.slice(0, cut)
    full_mask = _session_mask(us30_30m)
    short_mask = _session_mask(short)
    drifted = []
    for detector in DETECTORS:
        full = np.asarray(_fire(detector, us30_30m, full_mask),
                          dtype=bool)[:cut]
        truncated = np.asarray(_fire(detector, short, short_mask), dtype=bool)
        if not np.array_equal(full, truncated):
            drifted.append(detector.key)
    assert not drifted, f"these detectors changed when the future was removed: {drifted}"


# --------------------------------------------------------------------------
# The calendar family
# --------------------------------------------------------------------------

def test_the_calendar_family_is_a_fixed_list_not_a_search():
    """Naming them in advance is the opposite of letting a search pick one."""
    from tradingbacktester.research.anomalies import CALENDAR_DETECTORS

    assert len(CALENDAR_DETECTORS) >= 8
    keys = {d.key for d in CALENDAR_DETECTORS}
    assert keys <= {d.key for d in DETECTORS}, "all of them must be scanned"
    assert all(d.family == "calendar" for d in CALENDAR_DETECTORS)
    # And every one of them is tested on every scan, promising or not.
    assert len({d.key for d in DETECTORS}) == len(DETECTORS)


def test_a_calendar_detector_may_fire_on_more_bars_than_a_shape_one():
    """Monday is a fifth of the sample by construction; a spike is not."""
    from tradingbacktester.research.anomalies import _MAX_SHARE

    shapes = [d for d in DETECTORS if d.family == "shape"]
    calendar = [d for d in DETECTORS if d.family == "calendar"]
    assert all(d.max_share == _MAX_SHARE for d in shapes)
    assert max(d.max_share for d in calendar) > _MAX_SHARE


@pytest.mark.parametrize("key", ["first_hour", "last_hour", "after_long_break"])
def test_a_session_detector_fires_inside_the_session(us30_30m, key):
    """"The first hour of the day" is the session's, not local midnight's.

    Without the session mask these marked the hour after midnight, which on an
    index CFD is nowhere near the open, falls entirely outside an RTH style's
    window, and scored zero bars while reading like a detector that had simply
    found nothing.
    """
    from tradingbacktester.research.anomalies import _fire

    detector = next(d for d in DETECTORS if d.key == key)
    assert detector.needs_session is True
    mask = _session_mask(us30_30m)
    fired = np.asarray(_fire(detector, us30_30m, mask), dtype=bool)
    assert fired.any(), f"{key} fired on nothing"
    assert (fired & mask).sum() == fired.sum(), \
        f"{key} fired outside the session it was given"


def test_the_last_hour_is_measured_from_the_previous_close(us30_30m):
    """Which is what a trader knows, and the only causal way to say it."""
    from tradingbacktester.research.anomalies import _fire

    detector = next(d for d in DETECTORS if d.key == "last_hour")
    mask = _session_mask(us30_30m)
    fired = np.asarray(_fire(detector, us30_30m, mask), dtype=bool)
    # The first session in the file has no previous close to measure from, so
    # nothing fires there rather than something being guessed.
    first_day = np.flatnonzero(mask)[:13]
    assert not fired[first_day].any()


def test_turn_of_month_covers_the_turn_and_not_the_middle(us30_30m):
    import pandas as pd

    from tradingbacktester.research.anomalies import _turn_of_month

    fired = np.asarray(_turn_of_month(us30_30m), dtype=bool)
    local = pd.DatetimeIndex(pd.to_datetime(us30_30m.ts, utc=True)).tz_convert(
        us30_30m.instrument.timezone)
    days = np.asarray(local.day)
    # Mid-month is never the turn; the first of the month always is.
    assert not fired[days == 15].any()
    assert fired[days == 1].all()


def test_round_number_scales_to_the_price_not_to_an_assumption(us30_30m):
    """40,000 is round for an index; 1.05 is round for a currency pair."""
    from tradingbacktester.research.anomalies import _round_number

    fired = np.asarray(_round_number(us30_30m), dtype=bool)
    assert fired.any()
    assert fired.mean() < 0.10, "a round number should be an event, not a state"


def test_the_scan_says_the_calendar_family_makes_everything_stricter(us30_30m):
    report = scan(us30_30m, style("intraday"), timeframe="30m",
                  control_draws=50)
    notes = " ".join(report.notes)
    assert "calendar effects" in notes
    assert "free lottery ticket" in notes
    assert "harder to pass" in notes
    # The multiplicity sentence counts tests, not detectors: both sides of each.
    assert f"{len(DETECTORS) * 2} tests" in notes


def test_the_scan_reports_every_detector_with_a_verdict(us30_30m):
    report = scan(us30_30m, style("intraday"), timeframe="30m",
                  control_draws=50)
    assert len(report.findings) == len(DETECTORS)
    for finding in report.findings:
        assert finding.verdict
        assert 0.0 <= finding.share <= 1.0
    text = format_anomalies(report)
    assert "MARKET ANOMALIES" in text
    assert "DATA QUALITY" in text
    assert "is not a trading signal" in text


def test_a_detector_that_almost_never_fires_is_not_judged(us30_30m):
    report = scan(us30_30m, style("intraday"), timeframe="30m",
                  control_draws=50)
    rare = [f for f in report.findings if f.count < 30]
    assert rare, "expected at least one rare detector on this sample"
    for finding in rare:
        assert "too rare" in finding.verdict
        assert finding.excess == 0.0


def test_the_scan_separates_data_problems_from_market_ones(us30_30m):
    report = scan(us30_30m, style("intraday"), timeframe="30m",
                  control_draws=50)
    # The shipped file has holiday gaps; those belong in the quality section,
    # not in the list of tradeable anomalies.
    assert report.quality
    assert any("gap" in line.lower() for line in report.quality)
    assert all(f.detector.key for f in report.findings)


def test_the_scan_finds_an_anomaly_that_really_does_pay():
    """Plant a rule the detectors can see, and require it to be found."""
    import pandas as pd

    from tradingbacktester.core.timeframe import Timeframe
    from tradingbacktester.data.models import BarSeries

    rng = np.random.default_rng(4)
    n = 30_000
    stamps = []
    t = pd.Timestamp("2015-01-02 09:30", tz="America/New_York")
    while len(stamps) < n:
        if t.dayofweek < 5 and 570 <= (t.hour * 60 + t.minute) <= 960:
            stamps.append(t)
        t += pd.Timedelta(minutes=15)
    ts = (pd.DatetimeIndex(stamps).tz_convert("UTC")
          .to_numpy(dtype="datetime64[ns]").astype("int64"))

    steps = rng.normal(0, 8.0, n)
    # Every bar that gaps up by more than an ATR is followed by a real drift.
    gap = np.zeros(n)
    marks = rng.choice(np.arange(200, n - 60), size=600, replace=False)
    for i in marks:
        gap[i] += 40.0            # a gap the detector will see
        steps[i + 1:i + 20] += 4.0  # and a drift that follows it
    steps -= steps.mean()

    close = 25_000.0 + np.cumsum(steps)
    open_ = np.empty(n)
    open_[0] = close[0]
    open_[1:] = close[:-1]
    open_ += gap
    close = close + gap
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 4.0, n))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 4.0, n))
    bars = BarSeries(ts=ts, open=open_, high=high, low=low, close=close,
                     volume=np.full(n, 1000.0),
                     instrument=default_instrument_for("US30"),
                     timeframe=Timeframe.parse("15m"))

    report = scan(bars, style("intraday"), timeframe="15m", control_draws=200)
    gaps = [f for f in report.findings if f.key == "gap_up"]
    assert gaps, "the gap detector did not report at all"
    finding = gaps[0]
    assert finding.count > 100, f"only {finding.count} gaps were detected"
    assert finding.survives_fdr, "a planted, tradeable anomaly was not found"
    assert finding.side > 0
    assert finding.excess > 0


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------

def test_cli_ranks_indicators(tmp_path, capsys):
    import json

    from tradingbacktester.cli import main

    code = main(["--workspace", str(tmp_path), "indicators", "--data",
                 "US30 30m", "--style", "intraday", "--timeframe", "30m",
                 "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["features_tested"] > 40
    assert payload["independent_features"] <= payload["features_tested"]
    assert payload["cost_per_trade"] > 0
    assert any("Newey-West" in note for note in payload["notes"])
    assert all(f["verdict"] for f in payload["findings"])


def test_cli_scans_for_anomalies(tmp_path, capsys):
    import json

    from tradingbacktester.cli import main

    code = main(["--workspace", str(tmp_path), "anomalies", "--data",
                 "US30 30m", "--timeframe", "30m", "--draws", "50", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["findings"]) == len(DETECTORS)
    assert payload["quality"], "the data-quality section was empty"
    assert all(f["verdict"] for f in payload["findings"])


def test_a_trend_feature_that_agrees_with_the_drift_is_flagged(us30_30m):
    """US30 tripled over the shipped sample; that has to be said out loud."""
    from tradingbacktester.data.bundled import find as find_bundled

    dataset = find_bundled("US30 15m")
    bars = load_csv(str(dataset.path()), sniff_csv(str(dataset.path())).mapping,
                    default_instrument_for("US30"))
    study = study_features(bars, style("swing"), timeframe="1h")
    assert study.baseline > 0, "expected a rising market in this sample"
    text = " ".join(format_study(study, top=40).split())
    assert "measuring the drift rather than predicting" in text

    trend = [f for f in study.findings
             if f.feature.family == "trend" and f.research.significant
             and f.research.ic > 0]
    assert trend, "expected some significant trend features on this sample"
    for finding in trend:
        assert any("same way the market went" in c for c in finding.concerns), \
            f"{finding.name} was not flagged as possible drift"
