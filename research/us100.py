"""US100 15-minute data: loader, audit, and alignment against the NQ series.

WHY THIS MATTERS. Every study on this branch ends with the same caveat -- "one instrument in one
regime, no second market was reachable". This file is the second market, and it is also NINE
YEARS (2016-11 to 2025-10) against NQ's three, so it covers the 2018 selloff, the COVID crash and
the 2022 bear market, none of which the NQ sample contains.

AUDIT RESULTS, measured by `audit()`:
  * 206,703 bars, 0 duplicate timestamps, 0 OHLC violations, 0 non-positive prices
  * 1.40% of bar gaps are not 15 minutes; 650 exceed two hours (weekends and holidays)
  * 0.09% zero-range bars
  * `Volume` is identically zero -- an MT-style export. `TickVolume` is the only activity proxy.

TIMEZONE. The file clock is NEW YORK + 7 HOURS, and that offset is STABLE ACROSS DST: locating
the RTH-open volume jump separately in Dec-Feb and Jun-Aug puts it at 16:30 file time in both, so
the broker follows US daylight saving. A fixed -7h shift is therefore correct year round. Getting
this wrong would misplace every clock condition for half of each year.

THE PRICE-LEVEL FINDING, which is about OUR data rather than this file. On 2023-01-10 the stored
NQ series reads 13,915.8 while this feed reads 11,184.6, and the actual Nasdaq-100 closed near
11,100. The ratio between the two series declines smoothly from about 1.25 in 2022 to 1.04 in
2025 -- median 2.0 points of drift per day, with only ONE daily jump above 50 points in three
years, so it is not roll-gap back-adjustment, which would be a step function. Whatever produced
it, the consequence is the same and it is worth stating plainly:

    The stored NQ series' historical price LEVELS are synthetic. Its RETURNS are usable
    (correlation 0.88 all bars, 0.92 RTH, 0.95 overnight against this feed), its levels are not.

That matters most for anything scaling with price -- percent-of-price stops, ATR-over-price
ratios -- and for dollar magnitudes, since a 1% move maps to more points early in the sample than
late. The research block is the EARLIER 65%, so its dollar figures are inflated relative to the
locked block's, which if anything makes the "grew on locked" flag that five shipped legs carry
LARGER rather than smaller once corrected.

NO LEAD-LAG. corr(NQ return at t-k, US100 return at t) is a clean spike at k=0 (0.8815) with
nothing beside it: -0.022, 0.044, -0.015, 0.010, -0.006, 0.018 at the surrounding lags. At
15-minute resolution the information transfer between the two is already complete inside the bar,
so "NQ leads US100" is not a tradable relationship here at this sampling rate.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# The upload directory is not durable -- this file was cleared from it mid-study once already,
# which is why `find_raw` searches rather than hard-coding, and why the error names the fix.
SEARCH = ("data/US100_15m.csv",
          "/root/.claude/uploads/*/0d17f54f-15m_data.csv",
          "/root/.claude/uploads/*/*15m_data.csv",
          "/root/.claude/uploads/*/*US100*.csv",
          "/root/.claude/uploads/*/*us100*.csv")
NY_OFFSET_H = 7          # file clock = New York + 7, verified stable across DST
_C = {}


def find_raw(path=None):
    """Locate the US100 file, or say exactly what to do about it."""
    import glob, os
    if path and os.path.exists(path):
        return path
    for pat in SEARCH:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    raise FileNotFoundError(
        "US100 15-minute data not found. It was uploaded once and the upload directory has "
        "since been cleared, so it needs re-attaching. Searched: " + ", ".join(SEARCH) + ". "
        "Dropping the file at data/US100_15m.csv makes it durable across session resets, which "
        "the upload directory is not.")


RAW = None               # resolved lazily by find_raw so an absent file fails with a useful message


def load(path=None):
    """15-minute bars indexed by NEW YORK time, oldest first."""
    path = find_raw(path)
    if ("raw", path) in _C:
        return _C[("raw", path)]
    d = pd.read_csv(path, sep="\t")
    d.columns = [c.strip() for c in d.columns]
    ts = pd.to_datetime(d["DateTime"], format="%Y.%m.%d %H:%M:%S") - pd.Timedelta(hours=NY_OFFSET_H)
    out = pd.DataFrame({"o": d["Open"].to_numpy(float), "h": d["High"].to_numpy(float),
                        "l": d["Low"].to_numpy(float), "c": d["Close"].to_numpy(float),
                        "v": d["TickVolume"].to_numpy(float)}, index=ts)
    out = out[~out.index.duplicated()].sort_index()
    out["mod"] = out.index.hour * 60 + out.index.minute
    # a session runs 18:00 -> 18:00 New York, matching the futures convention used elsewhere here
    out["sess"] = (out.index + pd.Timedelta(hours=6)).normalize().view("int64") // 86_400_000_000_000
    _C[("raw", path)] = out
    return out


def audit(path=None, verbose=True):
    d = load(path)
    gap = pd.Series(d.index).diff().dt.total_seconds().div(60)
    r = dict(bars=len(d), start=d.index.min(), end=d.index.max(),
             dup=int(pd.Series(d.index).duplicated().sum()),
             ohlc_bad=int(((d.h < d.l) | (d.h < d.o) | (d.h < d.c) |
                           (d.l > d.o) | (d.l > d.c)).sum()),
             nonpos=int((d[["o", "h", "l", "c"]] <= 0).any(axis=1).sum()),
             zero_range=int((d.h == d.l).sum()),
             odd_gaps=int((gap.dropna() != 15).sum()), long_gaps=int((gap.dropna() > 120).sum()))
    if verbose:
        print(f"  US100 {r['bars']:,} bars  {r['start']} -> {r['end']}  (New York time)")
        print(f"  duplicates {r['dup']}   OHLC violations {r['ohlc_bad']}   non-positive {r['nonpos']}")
        print(f"  zero-range bars {r['zero_range']:,} ({100*r['zero_range']/r['bars']:.2f}%)")
        print(f"  non-15m gaps {r['odd_gaps']:,} ({100*r['odd_gaps']/r['bars']:.2f}%), "
              f"{r['long_gaps']:,} over two hours")
    return r


def resample(tf, path=None):
    """Aggregate to a coarser timeframe. `tf` in minutes and a multiple of 15."""
    if tf % 15:
        raise ValueError("US100 source is 15-minute; tf must be a multiple of 15")
    d = load(path)
    if tf == 15:
        return d
    g = d.resample(f"{tf}min", label="left", closed="left")
    out = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(),
                        "c": g.c.last(), "v": g.v.sum()}).dropna()
    out["mod"] = out.index.hour * 60 + out.index.minute
    out["sess"] = (out.index + pd.Timedelta(hours=6)).normalize().view("int64") // 86_400_000_000_000
    return out


def to_bars(tf, path=None, atr_n=14):
    """The dict shape the rest of this repository's engines expect."""
    import indicators as I
    d = resample(tf, path)
    o, h, l, c = (d[k].to_numpy(float) for k in "ohlc")
    return dict(o=o, h=h, l=l, c=c, v=d.v.to_numpy(float),
                atr=I.ema(I.true_range(h, l, c), atr_n),
                mod=d["mod"].to_numpy(np.int64), sess=d["sess"].to_numpy(np.int64),
                n=len(d), _key=("us100", tf), df=d)


def unseen_split(tf=30, cutoff="2022-12-26"):
    """The part of US100 that predates the NQ sample entirely -- never used to fit anything.

    Everything on this branch was selected on NQ from 2022-12-26 onward. US100 before that date is
    a different instrument in a different era, and no rule here has ever seen it. It is the closest
    thing to a genuine out-of-sample test this repository can construct.
    """
    b = to_bars(tf, atr_n=14)
    m = b["df"].index < pd.Timestamp(cutoff)
    return m, b
