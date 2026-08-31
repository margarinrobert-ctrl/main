"""Working the column layout out from the values rather than the header names.

Every fixture here is written from one list of bars, laid out differently each
time -- reordered, renamed, reversed, mislabelled.  The bars are the same, so
the test of a detector is simply whether the file it read gives them back.
"""

from __future__ import annotations

import numpy as np
import pytest

from tradingbacktester.core.types import AssetClass
from tradingbacktester.data.autodetect import (analyse_columns, audit_mapping,
                                               detect_mapping, ohlc_pass_rate,
                                               price_groups, row_direction,
                                               to_number)
from tradingbacktester.data.csv_loader import ColumnMapping, load_csv, sniff_csv
from tradingbacktester.data.models import Instrument

# --------------------------------------------------------------------------
# One set of bars, written many ways
# --------------------------------------------------------------------------

def _bars(n: int = 120) -> list[tuple[str, float, float, float, float, int]]:
    """Deterministic bars whose closes and opens join up, as real ones do."""
    import datetime as dt

    rng = np.random.default_rng(4)
    out = []
    price = 15000.0
    stamp = dt.datetime(2023, 1, 2, 9, 30)
    for i in range(n):
        open_ = price
        close = round(open_ + float(rng.normal(0, 4)), 2)
        high = round(max(open_, close) + abs(float(rng.normal(0, 2))), 2)
        low = round(min(open_, close) - abs(float(rng.normal(0, 2))), 2)
        volume = int(abs(rng.normal(2000, 400))) + 1
        out.append((stamp.strftime("%Y-%m-%d %H:%M:%S"), open_, high, low,
                    close, volume))
        price = close
        stamp += dt.timedelta(minutes=5)
    return out


BARS = _bars()


def _write(tmp_path, name: str, header: str | None, layout: str,
           sep: str = ",", reverse: bool = False, zero_volume: bool = False,
           decimal: str = ".") -> str:
    """Write BARS out in the column order named by *layout*.

    ``layout`` is a string of field letters -- ``"tohlcv"`` is the usual one --
    so a fixture states its own column order in one word.
    """
    picker = {"t": 0, "o": 1, "h": 2, "l": 3, "c": 4, "v": 5}
    lines = [header] if header else []
    rows = list(reversed(BARS)) if reverse else BARS
    for row in rows:
        cells = []
        for letter in layout:
            value = row[picker[letter]]
            if letter == "t":
                cells.append(str(value))
            elif letter == "v":
                cells.append("0" if zero_volume else str(value))
            else:
                cells.append(f"{value:.2f}".replace(".", decimal))
        lines.append(sep.join(cells))
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


@pytest.fixture
def instrument() -> Instrument:
    return Instrument(symbol="T", name="T", asset_class=AssetClass.OTHER,
                      tick_size=0.25, point_value=20.0, price_decimals=2)


def _check_against_bars(bars, reverse: bool = False) -> None:
    """The imported series must be the bars the fixture was written from."""
    expected = BARS
    assert len(bars) == len(expected)
    assert bars.open == pytest.approx([b[1] for b in expected])
    assert bars.high == pytest.approx([b[2] for b in expected])
    assert bars.low == pytest.approx([b[3] for b in expected])
    assert bars.close == pytest.approx([b[4] for b in expected])


# --------------------------------------------------------------------------
# The primitives, on values that can be checked by hand
# --------------------------------------------------------------------------

def test_to_number_reads_the_shapes_files_actually_use():
    assert to_number("1234.56") == pytest.approx(1234.56)
    assert to_number("1,234.56", thousands=",") == pytest.approx(1234.56)
    assert to_number("1.234,56", decimal=",", thousands=".") == pytest.approx(1234.56)
    assert to_number("$1 234,50", decimal=",", thousands=" ") == pytest.approx(1234.5)
    assert to_number("(42.5)") == pytest.approx(-42.5)
    assert np.isnan(to_number(""))
    assert np.isnan(to_number("not a number"))


def test_ohlc_pass_rate_counts_impossible_candles():
    # Four bars: the first three are possible, the fourth has a high under its
    # close, so exactly 3/4 of them pass.
    o = np.array([10.0, 10.0, 10.0, 10.0])
    h = np.array([11.0, 12.0, 10.5, 9.0])
    l = np.array([9.0, 9.5, 9.8, 8.0])
    c = np.array([10.5, 11.5, 10.0, 9.5])
    assert ohlc_pass_rate(o, h, l, c) == pytest.approx(0.75)
    # Swapping the high and the low fails every one of them.
    assert ohlc_pass_rate(o, l, h, c) == pytest.approx(0.0)


def test_price_groups_separate_prices_from_volume(tmp_path):
    path = _write(tmp_path, "plain.csv", "Date,Open,High,Low,Close,Volume", "tohlcv")
    profile = sniff_csv(path)
    facts = analyse_columns(profile.headers, profile.sample_rows)
    groups = price_groups(facts)
    assert groups[0] == [1, 2, 3, 4]        # the four prices, and not volume
    assert all(5 not in group for group in groups if len(group) >= 4)


def test_column_kinds_do_not_call_a_price_a_timestamp(tmp_path):
    path = _write(tmp_path, "plain.csv", "Date,Open,High,Low,Close,Volume", "tohlcv")
    profile = sniff_csv(path)
    facts = analyse_columns(profile.headers, profile.sample_rows)
    assert [f.kind for f in facts] == ["datetime", "numeric", "numeric",
                                       "numeric", "numeric", "numeric"]


def test_row_direction_reads_the_file_order(tmp_path):
    for reverse, expected in ((False, 1), (True, -1)):
        path = _write(tmp_path, f"d{int(reverse)}.csv",
                      "Date,Open,High,Low,Close,Volume", "tohlcv", reverse=reverse)
        profile = sniff_csv(path)
        facts = analyse_columns(profile.headers, profile.sample_rows)
        assert row_direction(facts[0]) == expected
        assert profile.row_order == expected


# --------------------------------------------------------------------------
# The audit leaves a correct mapping alone
# --------------------------------------------------------------------------

def test_a_correct_mapping_is_not_touched(tmp_path):
    path = _write(tmp_path, "plain.csv", "Date,Open,High,Low,Close,Volume", "tohlcv")
    profile = sniff_csv(path)
    mapping = profile.mapping
    assert (mapping.datetime, mapping.open, mapping.high, mapping.low,
            mapping.close, mapping.volume) == ("Date", "Open", "High", "Low",
                                               "Close", "Volume")
    assert profile.problems == []


def test_the_audit_reports_no_change_on_a_good_mapping(tmp_path):
    path = _write(tmp_path, "plain.csv", "Date,Open,High,Low,Close,Volume", "tohlcv")
    profile = sniff_csv(path)
    audit = audit_mapping(ColumnMapping.from_dict(profile.mapping.to_dict()),
                          profile.headers, profile.sample_rows, True)
    assert audit.changes == []
    assert audit.ok
    assert audit.pass_rate == pytest.approx(1.0)


# --------------------------------------------------------------------------
# ... and repairs a wrong one
# --------------------------------------------------------------------------

def test_headers_that_lie_are_overruled_by_the_values(tmp_path, instrument):
    # The names say close, open, high, low; the columns hold open, high, low,
    # close.  Only the data can settle it.
    path = _write(tmp_path, "lying.csv", "Time,Close,Open,High,Low,Volume",
                  "tohlcv")
    profile = sniff_csv(path)
    m = profile.mapping
    assert (m.open, m.high, m.low, m.close) == ("Close", "Open", "High", "Low")
    assert any("price columns were matched" in p for p in profile.problems)
    _check_against_bars(load_csv(path, m, instrument))


def test_headerless_file_in_an_unusual_order_is_corrected(tmp_path, instrument):
    path = _write(tmp_path, "odd.csv", None, "tcohl" + "v")
    profile = sniff_csv(path)
    m = profile.mapping
    assert (m.open, m.high, m.low, m.close) == ("2", "3", "4", "1")
    _check_against_bars(load_csv(path, m, instrument))


def test_close_before_open_is_found_by_bars_joining_up(tmp_path, instrument):
    # Nothing but the continuity of consecutive bars distinguishes these two
    # columns: both are inside the high and the low on every row.
    path = _write(tmp_path, "closefirst.csv", None, "thlco")
    profile = sniff_csv(path)
    m = profile.mapping
    assert (m.high, m.low, m.close, m.open) == ("1", "2", "3", "4")
    bars = load_csv(path, m, instrument)
    assert bars.open == pytest.approx([b[1] for b in BARS])
    assert bars.close == pytest.approx([b[4] for b in BARS])


def test_a_scrambled_mapping_is_repaired_against_the_data(tmp_path, instrument):
    path = _write(tmp_path, "plain.csv", "Date,Open,High,Low,Close,Volume", "tohlcv")
    profile = sniff_csv(path)
    # Exactly the shape a stray mouse wheel produces: fields pointing at
    # whatever happened to be next in the list.
    broken = ColumnMapping.from_dict(profile.mapping.to_dict())
    broken.datetime, broken.high, broken.low, broken.close = ("Low", "Low",
                                                              "Low", "Date")
    audit = audit_mapping(broken, profile.headers, profile.sample_rows, True)
    m = audit.mapping
    assert (m.datetime, m.open, m.high, m.low, m.close) == (
        "Date", "Open", "High", "Low", "Close")
    assert audit.changes
    _check_against_bars(load_csv(path, m, instrument))


# --------------------------------------------------------------------------
# Volume
# --------------------------------------------------------------------------

def test_an_all_zero_volume_column_loses_to_a_real_one(tmp_path, instrument):
    header = "DateTime\tOpen\tHigh\tLow\tClose\tVolume\tTickVolume"
    lines = [header]
    for stamp, o, h, l, c, v in reversed(BARS):
        stamp = stamp.replace("-", ".")
        lines.append(f"{stamp}\t{o:.2f}\t{h:.2f}\t{l:.2f}\t{c:.2f}\t0\t{v}")
    path = tmp_path / "mt5.csv"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    profile = sniff_csv(str(path))
    assert profile.delimiter == "\t"
    assert profile.mapping.volume == "TickVolume"
    assert profile.row_order == -1
    assert any("zero on every row" in p for p in profile.problems)

    bars = load_csv(str(path), profile.mapping, instrument)
    _check_against_bars(bars)
    assert bars.volume == pytest.approx([b[5] for b in BARS])
    assert bool(np.all(np.diff(bars.ts) > 0))


def test_a_real_volume_column_is_kept(tmp_path):
    path = _write(tmp_path, "plain.csv", "Date,Open,High,Low,Close,Volume", "tohlcv")
    profile = sniff_csv(path)
    assert profile.mapping.volume == "Volume"


def test_an_only_zero_volume_is_reported_but_still_used(tmp_path):
    path = _write(tmp_path, "zero.csv", "Date,Open,High,Low,Close,Volume",
                  "tohlcv", zero_volume=True)
    profile = sniff_csv(path)
    assert profile.mapping.volume == "Volume"
    assert any("zero on every row" in p for p in profile.problems)


# --------------------------------------------------------------------------
# Refusing to guess
# --------------------------------------------------------------------------

def test_comma_decimals_are_not_mistaken_for_text(tmp_path, instrument):
    path = _write(tmp_path, "euro.csv", "Datum;Open;High;Low;Close;Volume",
                  "tohlcv", sep=";", decimal=",")
    profile = sniff_csv(path)
    assert profile.decimal == ","
    m = profile.mapping
    assert (m.open, m.high, m.low, m.close) == ("Open", "High", "Low", "Close")
    _check_against_bars(load_csv(path, m, instrument))


def test_a_file_with_no_prices_keeps_its_mapping(tmp_path):
    path = tmp_path / "text.csv"
    path.write_text("Date,Open,High,Low,Close,Volume\n"
                    + "".join(f"2023-01-{d:02d},a,b,c,d,e\n" for d in range(1, 20)),
                    encoding="utf-8")
    profile = sniff_csv(str(path))
    # Nothing was provable, so the names stand and the loader reports the real
    # problem rather than the detector inventing a different one.
    assert profile.mapping.close == "Close"
    assert not audit_mapping(ColumnMapping.from_dict(profile.mapping.to_dict()),
                             profile.headers, profile.sample_rows, True).ok


def test_detection_survives_an_empty_sample():
    result = detect_mapping([], [], True)
    assert result.mapping.close is None
    assert not result.ok


def test_a_wide_bid_ask_file_takes_one_candle(tmp_path, instrument):
    header = ("Date,BidOpen,BidHigh,BidLow,BidClose,"
              "AskOpen,AskHigh,AskLow,AskClose,Volume")
    lines = [header]
    for stamp, o, h, l, c, v in BARS:
        lines.append(f"{stamp},{o:.2f},{h:.2f},{l:.2f},{c:.2f},"
                     f"{o + 0.25:.2f},{h + 0.25:.2f},{l + 0.25:.2f},"
                     f"{c + 0.25:.2f},{v}")
    path = tmp_path / "bidask.csv"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    profile = sniff_csv(str(path))
    bars = load_csv(str(path), profile.mapping, instrument)
    assert len(bars) == len(BARS)
    # Whichever side was chosen, it must be one side and a real candle.
    assert bool(np.all(bars.high >= np.maximum(bars.open, bars.close) - 1e-9))
    assert bool(np.all(bars.low <= np.minimum(bars.open, bars.close) + 1e-9))


def test_a_few_missing_prices_do_not_move_the_columns(tmp_path):
    """A gap in the data is not evidence that the columns are wrong."""
    lines = ["Date,Open,High,Low,Close,Volume"]
    for i, (stamp, o, h, l, c, v) in enumerate(BARS):
        if i % 20 == 7:
            lines.append(f"{stamp},{o:.2f},,{l:.2f},{c:.2f},{v}")
        else:
            lines.append(f"{stamp},{o:.2f},{h:.2f},{l:.2f},{c:.2f},{v}")
    path = tmp_path / "gappy.csv"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    profile = sniff_csv(str(path))
    m = profile.mapping
    assert (m.open, m.high, m.low, m.close) == ("Open", "High", "Low", "Close")
    assert not any("price columns were matched" in p for p in profile.problems)
