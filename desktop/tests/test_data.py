"""CSV import, validation, resampling, instruments and the sample generator."""

from __future__ import annotations

import numpy as np
import pytest

from tradingbacktester.core.errors import (CsvImportError, DataError,
                                           InsufficientDataError, TimeframeError)
from tradingbacktester.core.timeframe import Timeframe
from tradingbacktester.core.types import AssetClass
from tradingbacktester.data.csv_loader import (guess_mapping, load_csv,
                                               sniff_csv, ColumnMapping)
from tradingbacktester.data.instruments import InstrumentRegistry
from tradingbacktester.data.models import BarSeries, Instrument
from tradingbacktester.data.repository import DatasetRepository
from tradingbacktester.data.resample import available_timeframes, resample
from tradingbacktester.data.sample import generate_sample_data, write_sample_csv
from tradingbacktester.data.validation import validate_bars

from .conftest import make_bars


# --------------------------------------------------------------------------
# Instruments
# --------------------------------------------------------------------------

def test_instrument_rejects_impossible_values():
    with pytest.raises(DataError):
        Instrument(symbol="X", tick_size=0.0)
    with pytest.raises(DataError):
        Instrument(symbol="X", point_value=-1.0)
    with pytest.raises(DataError):
        Instrument(symbol="   ")


def test_instrument_rounds_to_the_tick_grid():
    nq = Instrument(symbol="NQ", tick_size=0.25, point_value=20.0)
    assert nq.round_price(15000.13) == pytest.approx(15000.25)
    assert nq.round_price(15000.12) == pytest.approx(15000.0)


def test_instrument_rounds_quantity_down_to_whole_lots():
    fx = Instrument(symbol="EURUSD", tick_size=0.00001, point_value=100000.0,
                    lot_size=0.01)
    assert fx.round_quantity(0.037) == pytest.approx(0.03)
    assert fx.round_quantity(0.0099) == pytest.approx(0.0)


def test_default_instruments_have_sane_contract_specs(tmp_path):
    registry = InstrumentRegistry(tmp_path / "instruments.json")
    symbols = {i.symbol for i in registry.all()}
    assert {"EURUSD", "BTCUSD", "SPY", "AAPL", "NQ", "ES", "MNQ"} <= symbols
    nq, mnq, es = registry.get("NQ"), registry.get("MNQ"), registry.get("ES")
    assert nq.point_value == 20.0 and nq.tick_size == 0.25
    assert mnq.point_value == 2.0            # a micro is one tenth of the mini
    assert es.point_value == 50.0
    assert registry.get("EURUSD").price_decimals == 5


def test_instrument_registry_round_trips(tmp_path):
    path = tmp_path / "instruments.json"
    registry = InstrumentRegistry(path)
    registry.add(Instrument.with_defaults("XYZ", AssetClass.EQUITY))
    registry.save()
    reloaded = InstrumentRegistry(path)
    assert reloaded.get("XYZ").asset_class is AssetClass.EQUITY


# --------------------------------------------------------------------------
# BarSeries
# --------------------------------------------------------------------------

def test_bar_series_slicing():
    bars = make_bars(list(range(100)))
    part = bars.slice(10, 20)
    assert len(part) == 10
    assert part.close[0] == 10.0


def test_bar_series_time_slice_is_inclusive():
    bars = make_bars(list(range(50)))
    part = bars.slice_time(int(bars.ts[10]), int(bars.ts[19]))
    assert len(part) == 10
    assert part.ts[0] == bars.ts[10]
    assert part.ts[-1] == bars.ts[19]


def test_bar_series_time_slice_outside_the_data_raises():
    bars = make_bars(list(range(50)))
    with pytest.raises(InsufficientDataError):
        bars.slice_time(int(bars.ts[-1]) + 10 ** 12, int(bars.ts[-1]) + 10 ** 13)


def test_bar_series_price_sources():
    bars = make_bars([10.0], [12.0], [8.0], [9.0])
    assert bars.source_array("close")[0] == 10.0
    assert bars.source_array("hlc3")[0] == pytest.approx((12 + 8 + 10) / 3)
    assert bars.source_array("hl2")[0] == pytest.approx(10.0)
    assert bars.source_array("ohlc4")[0] == pytest.approx((9 + 12 + 8 + 10) / 4)
    with pytest.raises(DataError):
        bars.source_array("nonsense")


def test_mismatched_column_lengths_are_rejected():
    with pytest.raises(DataError):
        BarSeries(ts=np.arange(5, dtype="int64"), open=np.zeros(5),
                  high=np.zeros(5), low=np.zeros(5), close=np.zeros(4),
                  volume=np.zeros(5), instrument=Instrument(symbol="X"),
                  timeframe=Timeframe.parse("1h"))


# --------------------------------------------------------------------------
# Resampling
# --------------------------------------------------------------------------

def test_resample_aggregates_ohlcv_correctly():
    """Twelve 5-minute bars make four 15-minute bars, checked by hand."""
    closes = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21]
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    opens = [c - 0.5 for c in closes]
    volumes = [100.0] * 12
    bars = make_bars(closes, highs, lows, opens, volumes, timeframe="5m",
                     start_ts=1_672_617_600_000_000_000)
    out = resample(bars, Timeframe.parse("15m"))
    assert len(out) == 4
    assert out.open[0] == pytest.approx(opens[0])
    assert out.high[0] == pytest.approx(max(highs[:3]))
    assert out.low[0] == pytest.approx(min(lows[:3]))
    assert out.close[0] == pytest.approx(closes[2])
    assert out.volume[0] == pytest.approx(300.0)
    assert out.ts[0] == bars.ts[0]           # labelled at the period start


def test_resample_to_the_same_timeframe_is_a_no_op():
    bars = make_bars(list(range(20)), timeframe="1h")
    out = resample(bars, Timeframe.parse("1h"))
    assert np.array_equal(out.close, bars.close)


def test_resample_refuses_to_invent_finer_bars():
    bars = make_bars(list(range(20)), timeframe="1h")
    with pytest.raises(TimeframeError):
        resample(bars, Timeframe.parse("1m"))


def test_a_partly_covered_first_period_is_not_emitted_as_a_bar():
    """Data starting mid-period would give bar 0 the wrong open, high and low."""
    # Twelve 5-minute bars starting at 00:05, so the 00:00-00:15 period is
    # missing its first five minutes and the 00:55-01:10 one its last.
    closes = list(range(10, 22))
    bars = make_bars(closes, [c + 1 for c in closes], [c - 1 for c in closes],
                     [c - 0.5 for c in closes], [100.0] * 12, timeframe="5m",
                     start_ts=1_672_617_600_000_000_000 + 300 * 10**9)
    out = resample(bars, Timeframe.parse("15m"))
    assert out.meta.get("partial_first_period_dropped") is True
    assert out.ts[0] == bars.ts[2], "the first whole period starts at 00:15"
    # And what remains really is whole: three source bars in each.
    assert out.volume[0] == pytest.approx(300.0)


def test_a_partly_covered_last_period_is_not_emitted_as_a_bar():
    """The last bar is what every open position is marked to at end of data."""
    closes = list(range(10, 24))            # 14 bars: the last period has two
    bars = make_bars(closes, [c + 1 for c in closes], [c - 1 for c in closes],
                     [c - 0.5 for c in closes], [100.0] * 14, timeframe="5m",
                     start_ts=1_672_617_600_000_000_000)
    out = resample(bars, Timeframe.parse("15m"))
    assert out.meta.get("partial_last_period_dropped") is True
    assert len(out) == 4
    assert all(v == pytest.approx(300.0) for v in out.volume)


def test_a_period_the_market_was_shut_for_is_still_a_whole_period():
    """Few bars inside a period is a fact about the period, not a gap."""
    # A whole day of 1-hour bars, but only six of them: a holiday half-day.
    # The period is fully covered by the data on both sides, so it is kept.
    closes = list(range(10, 34))
    bars = make_bars(closes, [c + 1 for c in closes], [c - 1 for c in closes],
                     [c - 0.5 for c in closes], [100.0] * 24, timeframe="1h",
                     start_ts=1_672_617_600_000_000_000)
    # 04:00-08:00 keeps a single bar; every other period is complete.
    kept = np.concatenate([np.arange(0, 5), np.arange(8, 24)])
    thin = type(bars)(ts=bars.ts[kept], open=bars.open[kept],
                      high=bars.high[kept], low=bars.low[kept],
                      close=bars.close[kept], volume=bars.volume[kept],
                      instrument=bars.instrument, timeframe=bars.timeframe,
                      source=bars.source, meta=dict(bars.meta))
    out = resample(thin, Timeframe.parse("4h"))
    assert len(out) == 6, "the thin period is a bar like any other"
    assert out.volume[1] == pytest.approx(100.0), "one bar in it, and that is fine"
    assert not out.meta.get("empty_periods_dropped")
    assert not out.meta.get("partial_first_period_dropped")
    assert not out.meta.get("partial_last_period_dropped")


def test_data_covering_no_whole_period_is_refused_not_faked():
    closes = [10, 11]
    bars = make_bars(closes, [c + 1 for c in closes], [c - 1 for c in closes],
                     [c - 0.5 for c in closes], [100.0] * 2, timeframe="1h",
                     start_ts=1_672_617_600_000_000_000 + 3600 * 10**9)
    with pytest.raises(InsufficientDataError):
        resample(bars, Timeframe.parse("1D"))


def test_every_resampled_series_records_which_anchor_cut_its_bars():
    """A daily bar cut at midnight UTC is not the one a vendor would show."""
    closes = list(range(10, 34))
    bars = make_bars(closes, [c + 1 for c in closes], [c - 1 for c in closes],
                     [c - 0.5 for c in closes], [100.0] * 24, timeframe="1h",
                     start_ts=1_672_617_600_000_000_000)
    out = resample(bars, Timeframe.parse("4h"))
    assert out.meta.get("resample_anchor") == "UTC"


def test_available_timeframes_excludes_finer_ones():
    options = available_timeframes(Timeframe.parse("1h"))
    labels = {tf.label for tf in options}
    assert "1m" not in labels and "5m" not in labels
    assert "4h" in labels and "1D" in labels


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def test_clean_data_produces_no_errors():
    bars = generate_sample_data("SPY", "1d", n_bars=400, seed=3)
    report = validate_bars(bars)
    assert report.is_usable
    assert not report.errors


def test_validation_catches_high_below_low():
    bars = make_bars([100.0] * 20)
    bars.high[5] = 90.0
    bars.low[5] = 110.0
    report = validate_bars(bars)
    codes = {issue.code for issue in report.issues}
    assert any("high" in c or "ohlc" in c for c in codes), codes
    assert report.errors


def test_validation_catches_duplicate_timestamps():
    bars = make_bars([100.0] * 20)
    bars.ts[5] = bars.ts[4]
    report = validate_bars(bars)
    assert any("dup" in issue.code for issue in report.issues)


def test_validation_catches_a_body_outside_the_bar():
    bars = make_bars([100.0] * 20)
    bars.close[7] = bars.high[7] + 5.0
    report = validate_bars(bars)
    assert report.issues


def test_validation_catches_non_positive_prices():
    bars = make_bars([100.0] * 20)
    bars.low[3] = -1.0
    report = validate_bars(bars)
    assert report.issues


# --------------------------------------------------------------------------
# CSV import
# --------------------------------------------------------------------------

def _write(tmp_path, name, text, encoding="utf-8"):
    path = tmp_path / name
    path.write_text(text, encoding=encoding)
    return path


BASIC = """Date,Open,High,Low,Close,Volume
2023-01-02 09:30:00,100.0,101.0,99.0,100.5,1000
2023-01-02 10:30:00,100.5,102.0,100.0,101.5,1200
2023-01-02 11:30:00,101.5,103.0,101.0,102.5,900
"""


def test_load_basic_csv(tmp_path, simple_instrument):
    path = _write(tmp_path, "basic.csv", BASIC)
    profile = sniff_csv(path)
    assert profile.delimiter == ","
    assert profile.has_header
    bars = load_csv(path, profile.mapping, simple_instrument)
    assert len(bars) == 3
    assert bars.close[0] == pytest.approx(100.5)
    assert bars.volume[2] == pytest.approx(900.0)
    assert (np.diff(bars.ts) > 0).all()


def test_semicolon_delimited_with_comma_decimals(tmp_path, simple_instrument):
    text = ("Date;Open;High;Low;Close;Volume\n"
            "02/01/2023 09:30;100,0;101,0;99,0;100,5;1000\n"
            "02/01/2023 10:30;100,5;102,0;100,0;101,5;1200\n")
    path = _write(tmp_path, "euro.csv", text)
    profile = sniff_csv(path)
    assert profile.delimiter == ";"
    bars = load_csv(path, profile.mapping, simple_instrument)
    assert len(bars) == 2
    assert bars.close[0] == pytest.approx(100.5)


def test_separate_date_and_time_columns(tmp_path, simple_instrument):
    text = ("Date,Time,Open,High,Low,Close,Volume\n"
            "2023-01-02,09:30:00,100,101,99,100.5,1000\n"
            "2023-01-02,10:30:00,100.5,102,100,101.5,1200\n")
    path = _write(tmp_path, "split.csv", text)
    profile = sniff_csv(path)
    bars = load_csv(path, profile.mapping, simple_instrument)
    assert len(bars) == 2
    assert bars.ts[1] > bars.ts[0]


def test_epoch_seconds_are_detected(tmp_path, simple_instrument):
    text = ("timestamp,open,high,low,close,volume\n"
            "1672651800,100,101,99,100.5,1000\n"
            "1672655400,100.5,102,100,101.5,1200\n")
    path = _write(tmp_path, "epoch.csv", text)
    profile = sniff_csv(path)
    bars = load_csv(path, profile.mapping, simple_instrument)
    assert len(bars) == 2
    assert bars.ts[0] == 1672651800 * 10 ** 9


def test_epoch_milliseconds_are_detected(tmp_path, simple_instrument):
    text = ("timestamp,open,high,low,close,volume\n"
            "1672651800000,100,101,99,100.5,1000\n"
            "1672655400000,100.5,102,100,101.5,1200\n")
    path = _write(tmp_path, "epoch_ms.csv", text)
    profile = sniff_csv(path)
    bars = load_csv(path, profile.mapping, simple_instrument)
    assert bars.ts[0] == 1672651800 * 10 ** 9


def test_bom_is_handled(tmp_path, simple_instrument):
    path = _write(tmp_path, "bom.csv", "﻿" + BASIC)
    profile = sniff_csv(path)
    bars = load_csv(path, profile.mapping, simple_instrument)
    assert len(bars) == 3


def test_comment_lines_are_skipped(tmp_path, simple_instrument):
    path = _write(tmp_path, "commented.csv",
                  "# SYNTHETIC TEST DATA - NOT REAL MARKET DATA\n" + BASIC)
    profile = sniff_csv(path)
    bars = load_csv(path, profile.mapping, simple_instrument)
    assert len(bars) == 3


def test_missing_volume_column_is_filled_with_zero(tmp_path, simple_instrument):
    text = ("Date,Open,High,Low,Close\n"
            "2023-01-02 09:30:00,100,101,99,100.5\n"
            "2023-01-02 10:30:00,100.5,102,100,101.5\n")
    path = _write(tmp_path, "novol.csv", text)
    profile = sniff_csv(path)
    bars = load_csv(path, profile.mapping, simple_instrument)
    assert len(bars) == 2
    assert np.allclose(bars.volume, 0.0)


def test_missing_close_column_is_fatal(tmp_path, simple_instrument):
    """Close and the timestamp are the two columns nothing can substitute for."""
    text = ("Date,Open,High,Low\n"
            "2023-01-02 09:30:00,100,101,99\n")
    path = _write(tmp_path, "noclose.csv", text)
    mapping = ColumnMapping(datetime="Date", open="Open", high="High",
                            low="Low", close=None)
    with pytest.raises(CsvImportError):
        load_csv(path, mapping, simple_instrument)


def test_missing_datetime_column_is_fatal(tmp_path, simple_instrument):
    path = _write(tmp_path, "nodate.csv", BASIC)
    mapping = ColumnMapping(datetime=None, open="Open", high="High",
                            low="Low", close="Close")
    with pytest.raises(CsvImportError):
        load_csv(path, mapping, simple_instrument)


def test_missing_low_is_derived_but_warned_about(tmp_path, simple_instrument):
    """A derived low narrows every bar, which flatters stop testing.

    Refusing the file outright would block anyone holding OHC data, so the
    loader derives it -- but the caveat must reach the user, not just the log.
    """
    from tradingbacktester.data.validation import validate_bars

    text = ("Date,Open,High,Close\n"
            "2023-01-02 09:30:00,100,101,100.5\n"
            "2023-01-02 10:30:00,100.5,102,101.5\n")
    path = _write(tmp_path, "nolow.csv", text)
    mapping = ColumnMapping(datetime="Date", open="Open", high="High",
                            low=None, close="Close")
    bars = load_csv(path, mapping, simple_instrument)
    assert bars.low[0] == pytest.approx(min(bars.open[0], bars.close[0]))
    assert any("low" in w.lower() for w in bars.meta.get("warnings", []))
    report = validate_bars(bars)
    assert any(i.code == "import_warning" and "low" in i.message.lower()
               for i in report.issues)


def test_empty_file_is_reported(tmp_path, simple_instrument):
    path = _write(tmp_path, "empty.csv", "")
    profile = sniff_csv(path)          # must not raise
    assert profile.problems
    with pytest.raises(CsvImportError):
        load_csv(path, profile.mapping, simple_instrument)


def test_garbage_file_is_reported_not_crashed(tmp_path, simple_instrument):
    path = _write(tmp_path, "junk.csv", "this is not a csv file at all\n\n\n")
    profile = sniff_csv(path)          # must not raise
    with pytest.raises(CsvImportError):
        load_csv(path, profile.mapping, simple_instrument)


def test_sniff_never_raises_on_a_binary_file(tmp_path):
    path = tmp_path / "binary.csv"
    path.write_bytes(bytes(range(256)) * 20)
    profile = sniff_csv(path)
    assert profile is not None


def test_guess_mapping_finds_common_header_names():
    mapping = guess_mapping(["time", "o", "h", "l", "c", "vol"])
    assert mapping.open and mapping.high and mapping.low and mapping.close


# --------------------------------------------------------------------------
# Sample data
# --------------------------------------------------------------------------

def test_sample_data_is_deterministic():
    a = generate_sample_data("NQ", "5m", n_bars=500, seed=42)
    b = generate_sample_data("NQ", "5m", n_bars=500, seed=42)
    assert np.array_equal(a.close, b.close)
    assert np.array_equal(a.ts, b.ts)


def test_sample_data_has_valid_ohlc_on_every_bar():
    bars = generate_sample_data("EURUSD", "1h", n_bars=3000, seed=1)
    assert (bars.high >= np.maximum(bars.open, bars.close) - 1e-9).all()
    assert (bars.low <= np.minimum(bars.open, bars.close) + 1e-9).all()
    assert (bars.high >= bars.low).all()
    assert (bars.close > 0).all()
    assert (np.diff(bars.ts) > 0).all()


def test_sample_data_is_labelled_synthetic():
    bars = generate_sample_data("SPY", "1d", n_bars=200, seed=2)
    assert bars.meta.get("synthetic") is True


def test_sample_csv_carries_a_synthetic_warning(tmp_path):
    path = tmp_path / "sample.csv"
    bars = generate_sample_data("SPY", "1d", n_bars=100, seed=2)
    write_sample_csv(path, bars)
    first = path.read_text(encoding="utf-8").splitlines()[0]
    assert "SYNTHETIC" in first.upper()
    assert "NOT REAL" in first.upper()


# --------------------------------------------------------------------------
# Repository
# --------------------------------------------------------------------------

def test_repository_round_trip(tmp_path):
    from tradingbacktester.config import Workspace

    workspace = Workspace(tmp_path / "ws").ensure()
    repo = DatasetRepository(workspace)
    bars = generate_sample_data("NQ", "5m", n_bars=800, seed=5)
    meta = repo.add_from_bars(bars, name="NQ test")
    assert meta.bar_count == 800
    loaded = repo.load_bars(meta.id)
    assert np.allclose(loaded.close, bars.close)
    assert np.array_equal(loaded.ts, bars.ts)
    assert loaded.instrument.symbol == "NQ"


def test_repository_survives_a_deleted_data_file(tmp_path):
    from tradingbacktester.config import Workspace

    workspace = Workspace(tmp_path / "ws").ensure()
    repo = DatasetRepository(workspace)
    bars = generate_sample_data("NQ", "5m", n_bars=200, seed=5)
    meta = repo.add_from_bars(bars, name="NQ test")
    repo.path_for(meta.id).unlink()
    assert repo.list() == []          # dropped, not crashed
    with pytest.raises(DataError):
        repo.load_bars(meta.id)


def test_repository_rename(tmp_path):
    from tradingbacktester.config import Workspace

    workspace = Workspace(tmp_path / "ws").ensure()
    repo = DatasetRepository(workspace)
    bars = generate_sample_data("NQ", "1h", n_bars=200, seed=5)
    meta = repo.add_from_bars(bars, name="before")
    repo.rename(meta.id, "after")
    assert repo.get(meta.id).name == "after"


def test_import_caveats_survive_the_library_round_trip(tmp_path, simple_instrument):
    """A derived low must still be flagged the tenth time the dataset is opened.

    Users import once and load from the library many times; a warning that only
    appears on import day is a warning nobody acts on.
    """
    from tradingbacktester.config import Workspace

    text = "Date,Open,High,Close\n" + "".join(
        f"2023-01-{d:02d} 09:30:00,100,101,100.5\n" for d in range(1, 20))
    path = _write(tmp_path, "ohc.csv", text)
    mapping = ColumnMapping(datetime="Date", open="Open", high="High",
                            low=None, close="Close")
    bars = load_csv(path, mapping, simple_instrument)

    workspace = Workspace(tmp_path / "ws").ensure()
    repo = DatasetRepository(workspace)
    meta = repo.add_from_bars(bars, name="OHC only")

    reopened = DatasetRepository(workspace)       # reads the index from disk
    reloaded = reopened.load_bars(meta.id)
    assert any("low" in w.lower() for w in reloaded.meta.get("warnings", []))
    report = validate_bars(reloaded)
    assert any(i.code == "import_warning" for i in report.issues)


# --------------------------------------------------------------------------
# Compressed files and the shipped data
# --------------------------------------------------------------------------

def test_gzipped_csv_imports_identically(tmp_path, simple_instrument):
    """A .csv.gz must give exactly the bars its plain twin gives."""
    import gzip

    text = ("Date,Open,High,Low,Close,Volume\n" + "".join(
        f"2023-01-{d:02d} 09:30:00,100,101,99,100.5,{1000 + d}\n"
        for d in range(1, 29)))
    plain = tmp_path / "bars.csv"
    plain.write_text(text, encoding="utf-8")
    packed = tmp_path / "bars.csv.gz"
    packed.write_bytes(gzip.compress(text.encode("utf-8")))

    profile = sniff_csv(str(packed))
    assert profile.delimiter == ","
    assert profile.mapping.close == "Close"

    a = load_csv(str(plain), sniff_csv(str(plain)).mapping, simple_instrument)
    b = load_csv(str(packed), profile.mapping, simple_instrument)
    assert np.array_equal(a.ts, b.ts)
    assert a.close == pytest.approx(b.close)
    assert a.volume == pytest.approx(b.volume)


def test_bundled_datasets_are_present_and_load():
    """The shipped data files must exist and import without a hand-made mapping."""
    from tradingbacktester.data.bundled import available
    from tradingbacktester.data.instruments import default_instrument_for

    datasets = available()
    assert datasets, "no market data is shipped"
    names = {d.name for d in datasets}
    assert "US30 30m" in names

    smallest = min(datasets, key=lambda d: d.path().stat().st_size)
    profile = sniff_csv(str(smallest.path()))
    instrument = default_instrument_for(smallest.symbol)
    assert instrument is not None, f"no instrument for {smallest.symbol}"
    bars = load_csv(str(smallest.path()), profile.mapping, instrument)
    assert len(bars) > 100
    # Sorted oldest first, and a real candle on every bar.
    assert bool(np.all(np.diff(bars.ts) > 0))
    assert bool(np.all(bars.high >= np.maximum(bars.open, bars.close) - 1e-9))
    assert bool(np.all(bars.low <= np.minimum(bars.open, bars.close) + 1e-9))


def test_mt5_export_uses_tick_volume_not_the_zero_column():
    """The shipped MetaTrader files carry their volume in TickVolume."""
    from tradingbacktester.data.bundled import find
    from tradingbacktester.data.instruments import default_instrument_for

    dataset = find("US30 30m")
    assert dataset is not None and dataset.exists()
    profile = sniff_csv(str(dataset.path()))
    assert profile.mapping.volume == "TickVolume"
    assert profile.row_order == -1
    bars = load_csv(str(dataset.path()), profile.mapping,
                    default_instrument_for("US30"))
    assert float(bars.volume.sum()) > 0.0


def test_a_bar_is_stamped_when_it_opened():
    """A file with both an open time and a close time must use the open."""
    from tradingbacktester.data.bundled import find

    dataset = find("BTCUSD 1D")
    assert dataset is not None and dataset.exists()
    profile = sniff_csv(str(dataset.path()))
    assert profile.mapping.datetime == "timeOpen"
