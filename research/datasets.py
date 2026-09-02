"""THE DATASET REGISTRY -- the durable memory of every price file this branch has been given.

WHY THIS FILE EXISTS. `data/*.csv` is git-ignored (the files are large and often licensed) and the
container's disk is reclaimed between sessions. Three times now a study has restarted against an
empty `data/` with no record of what had been there, what format it was in, or what had already
been established about it. The bars themselves cannot live in git; everything ELSE about them can,
and that is what this is: format, delimiter, column meanings, exact row count and span, the derived
clock and how it was derived, the measured defects, the loader that owns it, and a sha256 so a
re-uploaded file can be proved identical to the one the studies were run on.

`verify()` checks what is on disk against this registry and names the discrepancy. `missing()`
lists what has to be re-attached. `inventory()` prints the lot.

RE-ATTACHING. Every entry records `restore_to`, the exact path the loaders search for. Uploads land
in a directory that is NOT durable and has been cleared mid-study more than once, so a file is only
safe once it is at its `restore_to` path -- and even then only until the container is recycled.

REGISTER ON ARRIVAL, NOT ON THE WAY OUT. Four files -- the two RTF-wrapped ISO index feeds, the
nine-year US100 file and the twenty-year gold file -- were used across three sessions for V12, V13,
V14 and V15 and never entered here. A recycle deleted them, and the studies that rest on them are
now unreproducible: V16 and V17 had to be run on NQ instead. Their entries exist below but carry no
byte count and no checksum, because there was nothing left to hash. `verify()` reports such an entry
as PRESENT, UNVERIFIABLE rather than pretending a re-upload matches -- everything about the file
survives except the one thing that could prove it is the same file.
"""
from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


@dataclass
class Dataset:
    key: str
    instrument: str
    timeframe_min: int
    restore_to: str
    rows: int
    span: str
    bytes: int
    sha256_16: str                  # first 16 hex chars; enough to catch a different file
    fmt: str                        # delimiter and column layout, as delivered
    columns: str
    order: str                      # ascending / descending, as delivered
    clock: str                      # the derived offset and the evidence for it
    volume: str                     # what the activity column actually is
    defects: str                    # measured, not guessed
    loader: str
    provenance: str
    notes: str = ""
    extras: dict = field(default_factory=dict)


REGISTRY = {

    "NQ_1m": Dataset(
        key="NQ_1m", instrument="NQ", timeframe_min=1, restore_to="data/NQ_1m.csv",
        rows=1_048_575, span="2022-12-26 18:01 -> 2025-12-11 20:52 New York",
        bytes=63_534_510, sha256_16="7a81549ba8967fc7",
        fmt="comma-separated, header `timestamp,open,high,low,close,volume`",
        columns="timestamp (UTC ISO-8601 with Z), open, high, low, close, volume",
        order="ascending",
        clock="stamped in UTC; loaders convert to New York. No derivation needed.",
        volume="real exchange volume (contracts), not a tick count",
        defects="LEVELS ARE SYNTHETIC -- a back-adjusted continuous contract. The 2022-12-31 close "
                "reads 13,696.75 where NQ front month was near 11,000, decaying to zero at the "
                "right edge. Returns, R-multiples, win rates and ATR-unit measurements are "
                "unaffected; percent-of-price stops and early-sample dollar magnitudes are not.",
        loader="research/oner_union.bars(tf) via research/edgelab/feeds.bars('NQ', tf)",
        provenance="this repository's own futures file, present before this branch began",
        notes="The research/locked split is the first 65% of SESSIONS. Four independent checks "
              "confirm it is real market data (tick grid, the double-hump volume profile, the CME "
              "weekday calendar with zero Saturday bars, and the eight largest moves landing on "
              "the correctly-dated 2025 tariff selloff)."),

    "NQ_5m": Dataset(
        key="NQ_5m", instrument="NQ", timeframe_min=5, restore_to="data/NQ_5m.csv",
        rows=210_516, span="2022-12-26 18:00 -> 2025-12-11 20:50 New York",
        bytes=12_903_907, sha256_16="4db7770f9d632411",
        fmt="comma-separated, header `timestamp,open,high,low,close,volume`",
        columns="timestamp (UTC ISO-8601 with Z), open, high, low, close, volume",
        order="ascending", clock="stamped in UTC; loaders convert to New York.",
        volume="real exchange volume", defects="same synthetic-level caveat as NQ_1m",
        loader="research/oner_union.bars(5)",
        provenance="this repository's own futures file",
        notes="The 5-minute file is the one most studies run on; NQ_1m is used to walk the true "
              "intrabar path when a barrier pair sits inside one 5-minute bar."),

    "US100_15m": Dataset(
        key="US100_15m", instrument="US100", timeframe_min=15, restore_to="data/US100_15m.csv",
        rows=206_703, span="2016-11-14 23:30 -> 2025-10-01 00:00 New York",
        bytes=11_971_933, sha256_16="c449dddfbc06a943",
        fmt="TAB-separated, header `DateTime Open High Low Close Volume TickVolume`",
        columns="DateTime `YYYY.MM.DD HH:MM:SS`, Open, High, Low, Close, Volume, TickVolume",
        order="DESCENDING as delivered",
        clock="New York + 7, DERIVED: the RTH volume jump sits at 16:30 file time in both Dec-Feb "
              "and Jun-Aug, so the broker follows US daylight saving and a fixed -7h shift is "
              "right year round.",
        volume="`Volume` is identically ZERO. `TickVolume` is the only activity proxy.",
        defects="1.40% of gaps are not 15 minutes (650 over two hours: weekends and holidays); "
                "0.09% zero-range bars; 0 duplicates, 0 OHLC violations.",
        loader="research/us100.py (and research/edgelab/feeds.bars('US100', tf))",
        provenance="user upload, 2026-08-25 (re-uploaded; an earlier copy was lost to a recycle)",
        notes="Its value is the part BEFORE 2022-12-26 -- 71,074 30-minute bars covering 2018, "
              "COVID and the 2022 bear, none of which the NQ sample contains. Over the OVERLAP it "
              "is not an independent test: 68% of NQ's triggers fire on the identical 15m bar."),

    "US30_1m": Dataset(
        key="US30_1m", instrument="US30", timeframe_min=1, restore_to="data/US30_1m.csv",
        rows=2_880_287, span="2016-10-26 18:30 -> 2025-07-15 13:34 New York",
        bytes=168_054_005, sha256_16="a11aefddfd6e9d22",
        fmt="TAB-separated, header `DateTime Open High Low Close Volume TickVolume`",
        columns="DateTime `YYYY.MM.DD HH:MM:SS`, Open, High, Low, Close, Volume, TickVolume",
        order="DESCENDING as delivered",
        clock="New York + 7, DERIVED SEPARATELY from US100's -- `derive_offset` locates the 09:30 "
              "step in winter and summer independently and refuses a constant shift if they "
              "disagree. They agreed.",
        volume="`Volume` zero; `TickVolume` is the proxy",
        defects="measured by research/edgelab/audit.py; passes the truncation audit",
        loader="research/edgelab/feeds.bars('US30', tf)",
        provenance="user upload, 2026-08-25, as a 7z archive (extract needs `pip install py7zr`)",
        notes="The most INDEPENDENT index here: 15m return correlation 0.758 vs US100 and 0.679 "
              "vs NQ, against NQ/US100's 0.874. No lead-lag at any offset."),

    "US30_5m": Dataset(
        key="US30_5m", instrument="US30", timeframe_min=5, restore_to="data/US30_5m.csv",
        rows=581_195, span="2016-10-26 18:30 -> 2025-07-15 13:30 New York",
        bytes=34_308_074, sha256_16="c76601a1a2b54878",
        fmt="TAB-separated, header `DateTime Open High Low Close Volume TickVolume`",
        columns="DateTime `YYYY.MM.DD HH:MM:SS`, Open, High, Low, Close, Volume, TickVolume",
        order="DESCENDING as delivered", clock="New York + 7, derived as for US30_1m",
        volume="`Volume` zero; `TickVolume` is the proxy",
        defects="none beyond the usual weekend gaps",
        loader="research/edgelab/feeds.bars('US30', 5)",
        provenance="user upload, 2026-08-25, as a 7z archive",
        notes="The scalp studies run here; US30_1m is for true-path re-simulation."),

    "XAUUSD_5m": Dataset(
        key="XAUUSD_5m", instrument="XAUUSD", timeframe_min=5, restore_to="data/XAUUSD_5m.csv",
        rows=1_443_451, span="2004-06-11 00:15 -> 2026-01-30 16:55 New York",
        bytes=74_361_143, sha256_16="9b0f8e72f8688da0",
        fmt="SEMICOLON-separated, header `Date;Open;High;Low;Close;Volume`",
        columns="Date `YYYY.MM.DD HH:MM` (no seconds), Open, High, Low, Close, Volume",
        order="ascending",
        clock="New York + 7, DERIVED FROM GOLD'S OWN ANCHOR -- it does not key on the 09:30 equity "
              "open. The summer peak in mean |5m return| lands at raw 15:30 = 08:30 New York to "
              "the minute, and corr(US30, XAU) spikes to +0.057 at a 7h shift against ~0 at 5/6/8.",
        volume="a TICK COUNT, not exchange volume; there is no TickVolume column",
        defects="PRE-2010 IS EXCLUDED WITH CAUSE: 10.06% zero-range bars and a median 5-minute "
                "volume of 14 ticks. That is a quote feed idling, not a market.",
        loader="research/edgelab/feeds.bars('XAUUSD', 5)",
        provenance="user upload, 2026-08-25, as a 7z archive",
        notes="The only genuinely UNCORRELATED market here: contemporaneous 5m correlation with "
              "the three indices is 0.057-0.070. Its four-way split reserves an UNTOUCHED final "
              "period (2025-01-01 -> 2026-01-30) that no search has ever read.",
        extras=dict(split="research 2010->2017, validation ->2021, test ->2024, untouched 2025+")),

    "EURUSD_M30": Dataset(
        key="EURUSD_M30", instrument="EURUSD", timeframe_min=30, restore_to="data/EURUSD_M30.csv",
        rows=230_400, span="2003-07-21 08:00 -> 2022-02-22 04:00 New York",
        bytes=16_546_557, sha256_16="671f407f6f4d7371",
        fmt="comma-separated with an UNNAMED integer index column",
        columns="index, time `YYYY-MM-DD HH:MM:SS`, open, high, low, close, tick_volume, "
                "SPREAD, real_volume",
        order="ascending",
        clock="New York + 7, DERIVED FROM FX'S OWN ANCHORS -- three of them, all agreeing and all "
              "DST-stable: the weekly open (Sunday 17:00 New York) lands at file 00:00 in 964 of "
              "984 weeks and separately in winter and summer; mean tick volume bottoms at file "
              "hour 0 = the 17:00 rollover lull; and mean |30m return| peaks at file 16 = 09:00 "
              "New York with the 14-17 block being the London/New York overlap.",
        volume="`tick_volume` is the proxy; `real_volume` is populated on only 10.5% of bars",
        defects="0 duplicates, 0 OHLC violations, 0 non-positive, 0.023% zero-range, 989 gaps over "
                "two hours (weekends). THE SPREAD COLUMN IS THE CAVEAT: a quoted spread of exactly "
                "zero is a missing value, and the zero share is 0% every year to 2013 then rises "
                "erratically to 25.2% (2017), 36.0% (2020), 74.6% (2021) and 87.7% (2022 stub).",
        loader="research/edgelab/fx.py",
        provenance="user upload, 2026-08-25, as EURUSD_M30.csv.zip",
        notes="TWO THINGS NOTHING ELSE HERE HAS. (1) It does NOT overlap the NQ sample by a single "
              "bar -- it ends 2022-02-22 and NQ starts 2022-12-26 -- so the 'same trades on a "
              "second feed' objection cannot be raised against it. (2) It reports a MEASURED "
              "SPREAD, the first on this branch; see docs/ib/STUDY_SPREAD_TRUTH.md.",
        extras=dict(spread_units="5th-decimal points; 10 points = 1 pip",
                    usable_years="all except 2017, 2020, 2021, 2022 (>20% zeros); "
                                 "190,319 of 230,400 bars = 82.6%")),
    "BTC_15m": Dataset(
        key="BTC_15m", instrument="BTC", timeframe_min=15, restore_to="data/BTC_15m.csv",
        rows=295_882, span="2017-12-31 19:00 -> 2026-06-15 19:15 New York",
        bytes=44860708, sha256_16="94ebac4008268627",
        fmt="comma-separated, a raw BINANCE KLINES dump",
        columns="Open time, Open, High, Low, Close, Volume, Close time, Quote asset volume, "
                "Number of trades, TAKER BUY BASE ASSET VOLUME, Taker buy quote asset volume, "
                "Ignore. Timestamps carry six decimals AND TRAILING WHITESPACE; `Ignore` is "
                "Binance's documented placeholder and is all zeros.",
        order="ascending",
        clock="UTC -- and this is the ONLY feed here where a CONSTANT SHIFT IS WRONG. Every other "
              "file is a broker export whose server follows US daylight saving, so a fixed -7h "
              "held year round. Measured against US30, winter prefers -5h (corr 0.1289) and "
              "summer -4h (0.1625): they disagree by exactly one hour, the DST signature. A true "
              "UTC -> America/New_York conversion scores each season's own best and 0.1337 pooled, "
              "against 0.0908 for the best single shift. The loader CONVERTS; the fall-back hour's "
              "duplicate local timestamps are dropped.",
        volume="real base-asset volume, plus `Number of trades` (median 10,986) and TAKER BUY "
               "volume -- an ACTUAL order-flow imbalance rather than the proxy `features3.py` had "
               "to construct. Taker-buy share centres at 0.4965 mean / 0.4967 median.",
        defects="THE FINAL ROW IS MALFORMED -- both timestamps empty, OHLCV present -- and is "
                "dropped; 2 duplicate timestamps dropped. 14 bars have zero volume, zero trades "
                "and zero range together, which is an exchange outage, not a quiet market. "
                "0 OHLC violations, 0 non-positive, 39 non-15m gaps (19 over two hours). Note the "
                "file NAME says 2018-2025 and the data runs to 2026-06-15.",
        loader="research/edgelab/crypto.py",
        provenance="user upload, 2026-08-25, as btc_15m_data_2018_to_2025.7z",
        notes="IT IS 24/7: weekday bar counts run 42,184 to 42,370, flat. Every other instrument "
              "here has a weekend hole and every session condition on this branch was written "
              "against one. Correlation with US30 at 15m is only +0.13 -- partially independent, "
              "well above gold's ~0.06 but far below the indices' 0.68-0.87.",
        extras=dict(order_flow="taker_share = Taker buy base asset volume / Volume")),

    # ---------------------------------------------------------------------------------------
    # THE FOUR BELOW WERE REGISTERED AFTER A CONTAINER RECYCLE HAD ALREADY DELETED THEM, so they
    # carry no checksum and no byte count. That is the lesson, not a footnote: this registry only
    # protects a file that is entered into it WHILE IT IS STILL ON DISK. Four files were used for
    # V12, V13, V14 and V15 across three sessions without ever being registered, and when the
    # container was reclaimed the studies became unreproducible -- V16 and V17 had to be run on NQ
    # instead. Register on arrival, not on the way out.
    # ---------------------------------------------------------------------------------------

    "US30_ISO_15m": Dataset(
        key="US30_ISO_15m", instrument="US30", timeframe_min=15,
        restore_to="data/US30_ISO_15m.csv",
        rows=48937, span="2024-08-19 01:45 to 2026-08-26 17:30 New York", bytes=2761204, sha256_16="f319104b7cd70a6b",
        fmt="RTF-WRAPPED CSV as delivered -- an eighth export format. NOTE the byte size recorded here is of the UNWRAPPED derivative, which depends on how the unwrapping script formats floats, so rows+span are its identity and bytes is only a hint, and the first that is not a "
            "plain text file. Unwrap it: drop the RTF header, split the body on `\\par`, strip "
            "control words with the regex `\\\\[a-zA-Z]+-?\\d* ?` and the braces, keep lines "
            "matching `^\\d{4}-\\d{2}-\\d{2}T`, then `tz_convert('America/New_York')` and save "
            "the New York timestamp as a column named `ny`.",
        columns="ISO 8601 timestamp WITH AN EXPLICIT UTC OFFSET, open, high, low, close, volume",
        order="ascending after unwrapping",
        clock="STATED, not derived -- the only feed here whose file carries its own offset. It is "
              "exactly -04:00 and -05:00, i.e. New York with daylight saving, confirmed against the "
              "09:30 equity-open volatility step.",
        volume="broker tick volume",
        defects="none measured beyond the RTF wrapper itself.",
        loader="research/v15/v15book.load, research/v14/*",
        provenance="user upload, 2026-08-26, as an RTF attachment",
        notes="Runs to 2026-08, so 27,436 of its bars post-date every other file here -- it is the "
              "only genuine forward test on the branch. Used by V12, V13, V14 and V15."),

    "US100_ISO_15m": Dataset(
        key="US100_ISO_15m", instrument="US100", timeframe_min=15,
        restore_to="data/US100_ISO_15m.csv",
        rows=51370, span="2024-08-26 07:15 to 2026-08-26 18:15 New York", bytes=3029162, sha256_16="1a6d1829afd0bdca",
        fmt="RTF-WRAPPED CSV, unwrapped exactly as US30_ISO_15m above",
        columns="ISO 8601 timestamp with an explicit UTC offset, open, high, low, close, volume",
        order="ascending after unwrapping",
        clock="STATED in the file: -04:00 / -05:00, New York with DST",
        volume="broker tick volume",
        defects="A DIFFERENT PROVIDER FROM US100_LONG_15m -- the median level gap between the two "
                "over their overlap is 11.1 points. Returns agree; levels do not.",
        loader="research/v15/v15book.load, research/v14/*",
        provenance="user upload, 2026-08-26, as an RTF attachment",
        notes="Pairs with US30_ISO_15m; the V14 grid required both instruments to agree."),

    "US100_LONG_15m": Dataset(
        key="US100_LONG_15m", instrument="US100", timeframe_min=15,
        restore_to="data/US100_LONG_15m.csv",
        rows=206703, span="2016-11 to 2025-10", bytes=11971933,
        sha256_16="c449dddfbc06a943",
        fmt="TAB-separated, delivered NEWEST FIRST",
        columns="DateTime, Open, High, Low, Close, Volume, TickVolume",
        order="DESCENDING as delivered -- sort ascending before use",
        clock="New York + 7, IDENTIFIED BY MEASUREMENT rather than stated: return correlation "
              "0.9399 against US100_ISO_15m at a -7h shift, with a median level gap of 11.1 points, "
              "against 21,780 points for US30. That is what proved it is US100 and not US30.",
        volume="tick volume; a separate TickVolume column is also present",
        defects="not re-measured after the identification.",
        loader="research/v13/*, research/us100.py",
        provenance="user upload, 2026-08-26, unlabelled -- the instrument had to be inferred; re-uploaded 2026-08-29 as `nasdaq_20252016_15m_data.csv`, row count identical, and the sha256 recorded here is from THAT delivery -- the 2026-08-26 copy was never hashed uncompressed, so a future mismatch means a different delivery, not necessarily different bars.",
        notes="NINE years against the ISO feed's two, so it is where a rule gets tested on 2018, "
              "COVID and the 2022 bear. Everything before 2022-12-26 is unseen by any NQ study."),

    "US30_LONG_15m": Dataset(
        key="US30_LONG_15m", instrument="US30", timeframe_min=15,
        restore_to="data/US30_LONG_15m.csv",
        rows=193942, span="2016-10-26 18:30 to 2025-07-15 13:30 New York", bytes=11549125,
        sha256_16="24dcf2e1c7ba398f",
        fmt="TAB-separated csv, delivered NEWEST FIRST. Re-uploaded 2026-08-29 UNCOMPRESSED; the "
            "earlier checksum e2c84cbb30347510 was of the GZIPPED delivery of the same content -- "
            "row count and span match exactly, so the bars are identical and the hash is not.",
        columns="DateTime, Open, High, Low, Close, Volume, TickVolume -- `Volume` is ZERO "
                "throughout and `TickVolume` is the real activity column",
        order="DESCENDING as delivered -- sort ascending before use",
        clock="New York + 7, DERIVED not assumed: mean tick volume by minute-of-day peaks at raw "
              "16:30/16:45/17:00/17:15, and after a -7h shift the peak lands exactly on minute 570 "
              "= 09:30 New York.",
        volume="TickVolume; the Volume column is identically zero",
        defects="not re-measured beyond the zero Volume column.",
        loader="research/v18/*",
        provenance="user upload, 2026-08-27, as US30_15m.csv.gz",
        notes="EIGHT AND A HALF YEARS of US30 against the ISO feed's two, and it ENDS 2025-07 while "
              "US30_ISO_15m BEGINS 2024-08 -- so they overlap by only eleven months and the pre-2024 "
              "history is unseen by every study on this branch."),

    "XAUUSD15_MT": Dataset(
        key="XAUUSD15_MT", instrument="XAUUSD", timeframe_min=15,
        restore_to="data/XAUUSD15_MT.csv",
        rows=100000, span="2022-06-07 04:30 to 2026-08-28 20:45 UTC", bytes=5699973,
        sha256_16="fdd173af1c92a768",
        fmt="NINTH export format -- MetaTrader 4 history export: TAB-separated, NO header, "
            "`YYYY-MM-DD HH:MM` timestamp, exactly 100,000 rows (the MT4 export cap).",
        columns="timestamp, open, high, low, close, tick volume",
        order="ASCENDING as delivered",
        clock="UTC, DERIVED from gold's own anchor and not assumed: the summer peak of mean "
              "|15m return| sits at file 12:30 and the winter peak at 13:30, and gold's 08:30 "
              "New York fixing/data anchor is 12:30 UTC in summer and 13:30 UTC in winter. So "
              "this is the SECOND feed here (after BTC) that is not a fixed New York offset: "
              "convert with a true UTC -> America/New_York conversion. Sunday bars (1,448) at "
              "the 22:00 UTC weekly open agree.",
        volume="tick volume",
        defects="none measured: 0 zero-range bars, no duplicate stamps. NOT re-verified against "
                "XAU_ISO_15m over their overlap.",
        loader="research/mrl/ (bar-level shape check only; no 1-minute path exists for gold)",
        provenance="user upload, 2026-09-02, as XAUUSD15.csv",
        notes="Four years of 15m gold ending 2026-08, i.e. it overlaps XAU_ISO_15m and extends it "
              "by nothing but carries a stated-format timestamp and a UTC clock. Uploaded during "
              "the MRL design brief."),

    "SPX_DAILY": Dataset(
        key="SPX_DAILY", instrument="SPX", timeframe_min=1440,
        restore_to="data/SPX.csv",
        rows=23323, span="1927-12-30 to 2020-11-04 (daily sessions)", bytes=1681649,
        sha256_16="54aa877d5d275b66",
        fmt="SEVENTH export format -- comma-separated Yahoo-style daily with an Adj Close column",
        columns="Date, Open, High, Low, Close, Adj Close, Volume",
        order="ASCENDING as delivered",
        clock="DATE ONLY, no intraday stamp, so no offset applies. Sessions are US equity "
              "sessions and align one-to-one with the VIX file by date.",
        volume="Volume is ZERO for the whole pre-1950 span and real thereafter; unused here.",
        defects="Adj Close equals Close throughout the VIX-overlapping era, so the split/dividend "
                "adjustment is inert on the only span this branch reads. NINETY-THREE YEARS is "
                "mostly unusable for a modern microstructure question -- only the 2012-2020 "
                "VIX overlap is read.",
        loader="research/v22/v22vix.py",
        provenance="user upload, 2026-08-28, as SPX.csv.zip and archive4.zip (identical files)",
        notes="ONLY VALUABLE FOR ITS VIX OVERLAP: 2,226 sessions 2012-01-03 to 2020-11-04 where "
              "both files carry a price. That overlap is what makes the implied-minus-realised "
              "spread computable at all on this branch."),

    "VIX_DAILY": Dataset(
        key="VIX_DAILY", instrument="VIX", timeframe_min=1440,
        restore_to="data/VIX_daily.csv",
        rows=2517, span="2012-01-03 to 2021-12-31 (daily sessions)", bytes=256270,
        sha256_16="f9359c32ff985a31",
        fmt="comma-separated Yahoo-style daily, NO Volume column",
        columns="Date, Open, High, Low, Close, Adj Close -- Adj Close == Close throughout",
        order="ASCENDING as delivered",
        clock="DATE ONLY. The VIX is a US-session index and needs no offset.",
        volume="none -- an index level has no volume",
        defects="no missing or zero closes in 2,517 rows. Close ranges 9.14 to 82.69.",
        loader="research/v22/v22vix.py",
        provenance="user upload, 2026-08-28 (uploaded twice, byte-identical)",
        notes="ZERO OVERLAP WITH EVERY FUTURES FEED ON THIS BRANCH. It ends 2021-12-31 and the NQ "
              "file begins 2022-12-26, a 360-day gap, so the VIX can NEVER be joined to NQ, "
              "US30_ISO or US100_ISO here. Its only usable partner is SPX_DAILY. Any VIX finding "
              "on this branch is therefore evidence about the equity complex at DAILY scale, "
              "transferred to intraday futures by analogy and never by a join."),

    "XAU_ISO_15m": Dataset(
        key="XAU_ISO_15m", instrument="XAUUSD", timeframe_min=15,
        restore_to="data/XAU_ISO_15m.csv",
        rows=494235, span="2004 to 2026", bytes=27637271, sha256_16="8c9ef8b42a578f6c",
        fmt="a .7z ARCHIVE of a SEMICOLON-separated csv -- `pip install py7zr` to extract",
        columns="Date;Open;High;Low;Close;Volume, timestamps formatted `%Y.%m.%d %H:%M`",
        order="ascending",
        clock="New York + 7, verified on gold's OWN anchor rather than an equity open -- the "
              "summer peak in mean |return| lands at 08:30 New York after a -7h shift.",
        volume="tick volume",
        defects="PRE-2010 IS EXCLUDED in the 5-minute source for 10.06% zero-range bars and a "
                "median 5-minute volume of 14 ticks; the same caution applies here.",
        loader="research/v13/*, research/v12ctx.py",
        provenance="user upload, 2026-08-26, as a 7z archive",
        notes="The only genuinely uncorrelated instrument on the branch -- contemporaneous "
              "correlation with the indices is 0.057-0.070."),

}


def sha16(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()[:16]


def verify(check_hash=True, verbose=True):
    """Compare what is on disk with the registry. Returns {key: status}."""
    out = {}
    for k, d in REGISTRY.items():
        if not os.path.exists(d.restore_to):
            out[k] = "MISSING" + (" (no checksum on record -- see note)" if not d.sha256_16 else "")
        elif not d.sha256_16:
            # REGISTERED AFTER THE FILE WAS ALREADY GONE. Everything about it survives except the
            # bytes, so a re-upload can be checked for shape but not PROVED identical. Say so
            # rather than reporting a false match.
            out[k] = "PRESENT, UNVERIFIABLE (registered without a checksum)"
        elif os.path.getsize(d.restore_to) != d.bytes:
            out[k] = f"SIZE MISMATCH ({os.path.getsize(d.restore_to):,} vs {d.bytes:,})"
        elif check_hash and sha16(d.restore_to) != d.sha256_16:
            out[k] = "CONTENT MISMATCH (same size, different bytes)"
        else:
            out[k] = "ok"
    if verbose:
        for k, v in out.items():
            mark = "  " if v == "ok" else "!!"
            print(f"{mark} {k:<12} {v}")
        n = sum(1 for v in out.values() if v == "ok")
        print(f"   {n}/{len(out)} datasets present and identical to the studied copy")
    return out


def missing():
    return [k for k, v in verify(check_hash=False, verbose=False).items() if v != "ok"]


def inventory(verbose=True):
    if not verbose:
        return REGISTRY
    total = sum(d.bytes for d in REGISTRY.values())
    print(f"{len(REGISTRY)} datasets, {total/1e6:,.0f} MB, five distinct export formats\n")
    for d in REGISTRY.values():
        here = "on disk" if os.path.exists(d.restore_to) else "ABSENT -- re-attach"
        print(f"  {d.key:<12} {d.instrument:<7} {d.timeframe_min:>3}m  {d.rows:>10,} bars  "
              f"{d.bytes/1e6:6.1f} MB  [{here}]")
        print(f"               {d.span}")
        print(f"               {d.fmt}")
        print(f"               clock: {d.clock.splitlines()[0][:96]}")
    return REGISTRY


if __name__ == "__main__":
    inventory()
    print()
    verify()
