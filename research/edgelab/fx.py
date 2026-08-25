"""EURUSD 30-minute: a FIFTH instrument, an independent era, and the first MEASURED SPREAD.

WHY THIS FILE MATTERS MORE THAN "one more market". Two things it has that nothing else here does.

FIRST, IT DOES NOT OVERLAP THE NQ SAMPLE AT ALL. 2003-07-21 -> 2022-02-22, and the NQ file starts
2022-12-26. `STUDY_TREND_LONG.md` established that a second instrument over the SAME calendar is
not a second test -- 68% of NQ's triggers fired on the identical 15-minute bar on US100. That
objection cannot be raised here: there is not one shared bar. Eighteen and a half years, and every
one of them predates the sample every rule on this branch was selected on.

SECOND, IT CARRIES A `spread` COLUMN. Five studies now end at the same sentence: bid/ask is
unavailable in all four feeds, so every cost number is an assumption, and every candidate dies at
1.5x the assumed spread. This is the first feed here that reports the quoted spread per bar. It
does not settle the four index/gold assumptions directly -- it is a different asset class -- but
it turns "how wrong can an assumed spread be, and how does a real one behave?" from a guess into
a measurement. Read `spread_quality()` before using it: the column is dependable to about 2019 and
is dominated by MISSING ZEROS after that.

THE CLOCK IS DERIVED FROM FX'S OWN ANCHORS, not inherited from the index feeds. There is no 09:30
cash equity open in EURUSD, so `derive_offset`'s default anchor is meaningless here. Three
independent measurements, all agreeing on NEW YORK + 7 and all stable across DST:

  * the WEEKLY OPEN. FX opens Sunday 17:00 New York. The bar after each weekend gap lands at file
    00:00 in 964 of 984 weeks -- and separately at file hour 0 in 240 of 241 winter weeks and 241
    of 242 summer weeks, so the server follows US daylight saving.
  * the DAILY ACTIVITY MINIMUM. Mean tick volume bottoms at file hour 0 = 17:00 New York, which is
    the rollover lull to the minute.
  * the VOLATILITY PROFILE. Mean |30-minute return| peaks at file hour 16 = 09:00 New York and the
    whole 14-17 block (07:00-10:00 New York) is the LONDON/NEW YORK OVERLAP, with a secondary hump
    at file 9-11 = 02:00-04:00 New York, the London open. That is the textbook EURUSD shape, and it
    only appears at this offset.

FORMAT. A FIFTH distinct export: comma-separated with an unnamed integer index column, then
`time,open,high,low,close,tick_volume,spread,real_volume`, stamped `YYYY-MM-DD HH:MM:SS`, sorted
ASCENDING. `real_volume` is populated on only 10.5% of bars, so `tick_volume` is the activity
proxy as with the other broker feeds. Nothing else in this repository should parse this file.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FX_FEEDS = {"EURUSD": {"30": "data/EURUSD_M30.csv"}}
NY_OFFSET_H = 7          # measured three ways below; stable across DST
POINT = 1e-5             # the `spread` column is in 5th-decimal points; 10 points = 1 pip
_CACHE = {}


def _read_fx(path):
    d = pd.read_csv(path, index_col=0)
    ts = pd.to_datetime(d["time"])
    out = pd.DataFrame({"o": d["open"].to_numpy(float), "h": d["high"].to_numpy(float),
                        "l": d["low"].to_numpy(float), "c": d["close"].to_numpy(float),
                        "v": d["tick_volume"].to_numpy(float),
                        "spread": d["spread"].to_numpy(float)}, index=pd.DatetimeIndex(ts))
    return out[~out.index.duplicated()].sort_index()


def derive_fx_offset(raw, verbose=True):
    """Locate 17:00 New York from the weekly open, separately in winter and summer.

    Returns (offset_hours, ok, detail). `ok` is False when the two seasons disagree, which is what
    a broker clock NOT following US daylight saving looks like -- in that case no constant shift is
    valid and the caller must not paper over it.
    """
    ix = raw.index
    gap = pd.Series(ix).diff().dt.total_seconds().to_numpy() / 3600.0
    opens = ix[np.flatnonzero(gap > 24)]
    detail = {}
    for name, sel in (("winter", np.isin(opens.month, (12, 1, 2))),
                      ("summer", np.isin(opens.month, (6, 7, 8)))):
        h = opens.hour[sel]
        detail[name] = int(pd.Series(h).mode().iloc[0]) if len(h) else -1
    ok = detail["winter"] == detail["summer"]
    off = (detail["winter"] - 17) % 24
    if verbose:
        print(f"  EURUSD clock: weekly open at raw hour {detail['winter']} (Dec-Feb) / "
              f"{detail['summer']} (Jun-Aug) -> "
              f"{'consistent' if ok else 'INCONSISTENT, no constant shift is valid'}"
              + (f"; New York = raw - {off}h" if ok else ""))
    return off, ok, detail


def load(inst="EURUSD", tf=30, verbose=False):
    """EURUSD bars on the NEW YORK clock, oldest first, with the spread column retained."""
    key = ("fx", inst, str(tf))
    if key in _CACHE:
        return _CACHE[key]
    raw = _read_fx(FX_FEEDS[inst][str(tf)])
    off, ok, _ = derive_fx_offset(raw, verbose=verbose)
    if not ok:
        raise ValueError(f"{inst}: winter and summer disagree on the clock; a fixed shift is wrong")
    out = raw.copy()
    out.index = out.index - pd.Timedelta(hours=int(off))
    out["mod"] = out.index.hour * 60 + out.index.minute
    _CACHE[key] = out
    return out


def _ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def bars(inst="EURUSD", tf=30, atr_n=14):
    """The dict shape every engine here expects, plus `spread` in PRICE units."""
    key = ("bars", inst, tf, atr_n)
    if key in _CACHE:
        return _CACHE[key]
    df = load(inst, 30)
    if tf != 30:
        if tf % 30:
            raise ValueError("EURUSD source is 30-minute; tf must be a multiple of 30")
        g = df.resample(f"{int(tf)}min", label="left", closed="left")
        df = pd.DataFrame({"o": g["o"].first(), "h": g["h"].max(), "l": g["l"].min(),
                           "c": g["c"].last(), "v": g["v"].sum(),
                           "spread": g["spread"].mean()}).dropna()
        df["mod"] = df.index.hour * 60 + df.index.minute
    o, h, l, c = (df[k].to_numpy(float) for k in "ohlc")
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    d = dict(o=o, h=h, l=l, c=c, v=df["v"].to_numpy(float),
             spread=df["spread"].to_numpy(float) * POINT,
             mod=df["mod"].to_numpy(int), atr=_ema(tr, atr_n),
             idx=pd.DatetimeIndex(df.index), df=df)
    _CACHE[key] = d
    return d


def spread_quality(inst="EURUSD", verbose=True):
    """Per-year usability of the `spread` column. READ THIS BEFORE USING IT.

    A quoted spread of exactly zero is not a market, it is a missing value, and this feed's zero
    share is not stationary: 0.0% every year to 2013, then a rising and erratic contamination that
    reaches 74.6% in 2021 and 87.7% in the 2022 stub. The MEDIAN spread also decays smoothly from
    50 points (5.0 pips) in 2003 to 1 point by 2018, which is the real historical narrowing of
    retail FX quotes and is the main reason to believe the column is genuine where it is populated.

    Verdict by measurement rather than by eye: 2017, 2020, 2021 and the 2022 stub carry 25-88%
    zeros and are excluded whole; every other year is at or under 6.3% and keeps its populated bars
    with the zeros dropped individually. `usable_span()` applies exactly that rule.
    """
    d = load(inst, 30)
    yr = d.index.year
    rows = []
    for y in np.unique(yr):
        s = d["spread"].to_numpy()[yr == y]
        rows.append(dict(year=int(y), bars=len(s), zero_pct=100.0 * float((s == 0).mean()),
                         median_pts=float(np.median(s)), median_pips=float(np.median(s)) / 10.0))
    out = pd.DataFrame(rows)
    if verbose:
        print("  year  bars   zero%   median spread (points / pips)")
        for r in out.itertuples():
            flag = "  <- unusable" if r.zero_pct > 20 else ""
            print(f"  {r.year}  {r.bars:5d}  {r.zero_pct:5.1f}   "
                  f"{r.median_pts:5.1f} / {r.median_pips:4.2f}{flag}")
    return out


ZERO_TOLERANCE = 20.0     # percent of a year's bars quoting spread 0 before the year is dropped


def usable_span(inst="EURUSD", verbose=False):
    """Boolean mask over `bars()` selecting bars whose quoted spread can be believed.

    Two filters, not one. Whole YEARS whose zero share exceeds `ZERO_TOLERANCE` are dropped, because
    a year that is 75% missing tells you nothing about the quarter that is populated. Within the
    years that survive, individual zero-spread bars are dropped too.
    """
    d = bars(inst, 30)
    q = spread_quality(inst, verbose=False)
    bad = set(q.loc[q.zero_pct > ZERO_TOLERANCE, "year"].astype(int))
    m = ~np.isin(d["idx"].year, sorted(bad)) & (d["spread"] > 0)
    if verbose:
        print(f"  years dropped: {sorted(bad)}; {m.sum():,} of {len(m):,} bars usable "
              f"({100*m.mean():.1f}%)")
    return m


def audit(inst="EURUSD", verbose=True):
    d = load(inst, 30)
    gap = pd.Series(d.index).diff().dt.total_seconds().div(60)
    r = dict(bars=len(d), start=d.index.min(), end=d.index.max(),
             dup=int(pd.Series(d.index).duplicated().sum()),
             ohlc_bad=int(((d.h < d.l) | (d.h < d.o) | (d.h < d.c) |
                           (d.l > d.o) | (d.l > d.c)).sum()),
             nonpos=int((d[["o", "h", "l", "c"]] <= 0).any(axis=1).sum()),
             zero_range=int((d.h == d.l).sum()),
             zero_vol=int((d.v == 0).sum()),
             odd_gaps=int((gap.dropna() != 30).sum()),
             long_gaps=int((gap.dropna() > 120).sum()))
    if verbose:
        print(f"  EURUSD {r['bars']:,} bars  {r['start']} -> {r['end']}  (New York time)")
        print(f"  duplicates {r['dup']}   OHLC violations {r['ohlc_bad']}   non-positive {r['nonpos']}")
        print(f"  zero-range {r['zero_range']:,} ({100*r['zero_range']/r['bars']:.3f}%)   "
              f"zero-volume {r['zero_vol']:,}")
        print(f"  non-30m gaps {r['odd_gaps']:,}, {r['long_gaps']:,} over two hours (weekends)")
    return r


if __name__ == "__main__":
    print("\nAUDIT"); audit()
    print("\nCLOCK"); derive_fx_offset(_read_fx(FX_FEEDS["EURUSD"]["30"]), verbose=True)
    print("\nSPREAD COLUMN"); spread_quality()
