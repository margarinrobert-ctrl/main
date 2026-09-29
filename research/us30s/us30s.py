"""US30 at THIRTY SECONDS -- the tenth export format on this branch, and the first PARQUET.

A ninth feed and a THIRD US30 provider. `research/datasets.py` has carried "US30_1m is MISSING
from disk, so the finest US30 series is 15-minute" as a standing blocker; `STUDY_US30_SCALP_0711`
named 1-minute US30 bars as the first thing that would move its verdict, twice. This file is
finer than that by a factor of two.

WHAT IS DIFFERENT ABOUT IT, ALL MEASURED RATHER THAN ASSUMED:

1. IT IS STAMPED IN UTC, and it says so -- `ts` is `timestamp[us, tz=UTC]`. Every other US30
   file here is broker server time at New York + 7, and `NQ_1m` is the one other UTC feed. A
   loader that forgets the conversion puts a 09:30 session window at 04:30 New York, which is
   the pre-open block four separate studies measured as the worst part of the day, and V58's NQ
   table moved from 48 trades at PF 1.80 to 89 at 1.49 on exactly that error. The clock is
   re-derived here anyway and not taken from the column type: mean bar range peaks at
   minute-of-day 570 = 09:30 New York after `tz_convert('America/New_York')` (74.69 points
   against 26.65 one bar earlier), while the raw-UTC reading peaks at 13:30, which is the same
   instant. So the conversion is a true UTC -> New York one, not a fixed offset, and it handles
   daylight saving by construction.

2. THE VOLUME COLUMN IS ZERO ON THE FIRST 134,655 BARS. It begins at 2026-04-27 14:45 UTC and
   is then present on every bar. `corr(volume, high - low)` on that era is **+0.7001**, inside
   the +0.71..+0.77 band the genuine feeds measure and nowhere near `XAUUSD15_MT`'s +0.0048
   fake column -- so it IS real volume, and it is real for 4.5 months of a 13-month file.
   `usable_volume_from` is exported so no study silently averages a zero into a mean.

3. BARS WITH NO ACTIVITY ARE OMITTED. 390,552 rows against 1,135,775 possible 30-second slots
   over the span, i.e. 34.4% coverage: 92% inside 10:00-16:00 New York and 31% overnight. The
   export dialog's own estimate of 812,571 rows assumed continuous coverage and is wrong. The
   17:00 New York hour is absent entirely (the CME maintenance break) and Sunday carries 13,310
   bars (the 18:00 re-open). So a bar INDEX is not a clock here, and anything measured in bar
   counts has to be converted to minutes first (`STUDY_V57`).

4. IT IS A DIFFERENT PROVIDER FROM `US30_ISO_15m`, WHICH MATTERS BOTH WAYS. Resampled to 15
   minutes and joined on 11,882 shared New York stamps: correlation 0.999926 and a mean level
   ratio of 1.000463, but mean |diff| **26.8 points** and an exact-match share of 0.03-0.07%,
   which is chance. So it is not a re-upload of a file already here (the check
   `research/datasets.py` demands of every arrival) -- and it is also not a fresh calendar: it
   overlaps US30_ISO from 2025-08-18 to 2026-08-26, and only **2026-08-27 onward** post-dates
   every other US30 file on disk. Two providers over one calendar are a feed-parity check and
   not two tests (`STUDY_TREND_LONG`, and US30/US30_ISO already measured at daily leg
   correlation +0.922).

WHAT IT ACTUALLY UNLOCKS is the MEASUREMENT and not the sample size. `STUDY_US30_SCALP_0711`
could not resolve which barrier came first on 14.03% of its 0.5N trades, and the two conventions
read PF 0.604 against 1.056 -- a 5.27-point spread, larger than any edge in that study and
opposite in sign. That question is answerable on 30-second bars. The trade COUNT is not: a
four-hour cap holds the rate near one trade a session whatever the bar size.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))      # repo root, two levels above research/us30s
sys.path.insert(0, os.path.dirname(HERE))

SRC = "data/US30_30s.csv"
VOL_FROM = "2026-04-27 10:45:00"   # New York; before this the volume column is identically zero


def load(tf=0.5, path=None):
    """The 30-second file on a NEW YORK clock, optionally resampled.

    `tf` is in MINUTES and 0.5 is the native resolution. Resampling is done on the New York
    index so a 15-minute bar here lines up with `US30_ISO_15m`'s stamps, and `volume` SUMS while
    OHLC take first/max/min/last -- the only aggregation that is not a choice.
    """
    p = path or os.path.join(ROOT, SRC)
    d = pd.read_csv(p, parse_dates=["ny"])
    d = d.sort_values("ny").reset_index(drop=True)
    if tf and abs(tf - 0.5) > 1e-9:
        d = (d.set_index("ny")
               .resample(f"{int(round(tf))}min")
               .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                    close=("close", "last"), volume=("volume", "sum"))
               .dropna(subset=["open"]).reset_index())
    d["mod"] = d["ny"].dt.hour * 60 + d["ny"].dt.minute
    d["day"] = d["ny"].dt.strftime("%Y%m%d").astype(int)
    return d


def usable_volume_from():
    """The first New York timestamp at which `volume` is not identically zero."""
    return pd.Timestamp(VOL_FROM)


def derive_clock(d_utc):
    """Re-derive the clock rather than trusting the column type: return the New York
    minute-of-day at which mean bar range peaks. It must be 570 (= 09:30)."""
    ny = pd.to_datetime(d_utc["ts"]).dt.tz_convert("America/New_York")
    mod = ny.dt.hour * 60 + ny.dt.minute
    prof = (d_utc["high"] - d_utc["low"]).groupby(mod).mean()
    return int(prof.idxmax()), prof


def convert(src_parquet, out_csv):
    """Parquet -> the branch's CSV convention: a `ny` column of naive New York timestamps, then
    open/high/low/close/volume, ascending. Identical in shape to `data/US30_ISO_15m.csv` so
    every existing US30 loader can read it."""
    d = pd.read_parquet(src_parquet)
    assert str(d["ts"].dt.tz) == "UTC", f"expected a UTC column, got {d['ts'].dt.tz}"
    assert d["symbol"].nunique() == 1, d["symbol"].unique()
    peak, _ = derive_clock(d)
    assert peak == 570, f"clock did not derive to 09:30 New York (peak minute {peak})"
    out = pd.DataFrame({
        "ny": d["ts"].dt.tz_convert("America/New_York").dt.tz_localize(None),
        "open": d["open"], "high": d["high"], "low": d["low"],
        "close": d["close"], "volume": d["volume"]})
    out = out.sort_values("ny").reset_index(drop=True)
    out.to_csv(out_csv, index=False, float_format="%.2f")
    return out
