"""DATASET INVENTORY and DATA QUALITY SCORE for every historical file in the project.

Each feed is described independently and never coerced into another's assumptions: they come from
different sources with different column meanings, different timestamp formats, different sort
orders and different session structures. Two of them do not even agree on what `Volume` means.

The quality score is a transparent deduction from 100, and every deduction is printed with the
measurement that caused it -- a single opaque number would be worse than no number.

NOTHING IS DELETED. Suspicious observations are counted and reported (brief section 9); an
outlier in a price series is as likely to be the event you want as it is to be an error.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from edgelab import feeds

FEEDS = [
    ("XAUUSD", 5, "data/XAUUSD_5m.csv", "semicolon CSV, Date;OHLC;Volume", "YYYY.MM.DD HH:MM",
     "ascending", "Volume (tick count)"),
    ("US30", 1, "data/US30_1m.csv", "MT tab export", "YYYY.MM.DD HH:MM:SS", "descending",
     "TickVolume (Volume column is identically zero)"),
    ("US30", 5, "data/US30_5m.csv", "MT tab export", "YYYY.MM.DD HH:MM:SS", "descending",
     "TickVolume (Volume column is identically zero)"),
    ("US100", 15, "data/US100_15m.csv", "MT tab export", "YYYY.MM.DD HH:MM:SS", "descending",
     "TickVolume (Volume column is identically zero)"),
    ("NQ", 5, "data/NQ_5m.csv", "repo ingest", "ISO-8601 UTC", "ascending", "exchange volume"),
]


def _quality(ix, o, h, l, c, v, tf):
    """Deductions from 100, each with the measurement that caused it."""
    notes = []
    score = 100.0
    dup = int(pd.Index(ix).duplicated().sum())
    if dup:
        d = min(20.0, dup / len(ix) * 2000)
        score -= d; notes.append(f"-{d:.1f}  {dup} duplicate timestamps")
    bad = int(((h < l) | (h < o) | (h < c) | (l > o) | (l > c)).sum())
    if bad:
        d = min(30.0, bad / len(ix) * 5000)
        score -= d; notes.append(f"-{d:.1f}  {bad} OHLC violations")
    nonpos = int((np.minimum.reduce([o, h, l, c]) <= 0).sum())
    if nonpos:
        score -= 20.0; notes.append(f"-20.0  {nonpos} non-positive prices")
    gaps = np.diff(np.asarray(ix).astype("datetime64[m]").astype(np.int64))
    offgrid = float((gaps != tf).mean())
    if offgrid > 0.02:
        d = min(15.0, (offgrid - 0.02) * 200)
        score -= d; notes.append(f"-{d:.1f}  {100*offgrid:.2f}% off-grid gaps")
    zr = float((h == l).mean())
    if zr > 0.005:
        d = min(10.0, (zr - 0.005) * 400)
        score -= d; notes.append(f"-{d:.1f}  {100*zr:.2f}% zero-range bars")
    # a return outlier beyond 20 robust sigma is flagged, never removed
    r = np.r_[0.0, np.diff(np.log(np.maximum(c, 1e-9)))]
    med = np.median(r); mad = np.median(np.abs(r - med))
    ext = int((np.abs(r - med) > 20 * 1.4826 * max(mad, 1e-12)).sum())
    if ext:
        notes.append(f"  flag  {ext} returns beyond 20 robust sigma (KEPT, not removed)")
    if v is not None and float(np.abs(v).sum()) == 0.0:
        notes.append("  flag  Volume column identically zero")
    return max(0.0, score), notes, dict(dup=dup, ohlc_bad=bad, nonpos=nonpos,
                                        offgrid=offgrid, zero_range=zr, extreme=ext)


def report():
    print("DATASET INVENTORY")
    print("=" * 100)
    rows = []
    for inst, tf, path, src, tsfmt, order, volmeaning in FEEDS:
        try:
            if inst == "NQ":
                d = feeds.bars("NQ", tf); ix = pd.DatetimeIndex(d["idx"])
                if ix.tz is not None:
                    ix = ix.tz_localize(None)
                o, h, l, c, v = d["o"], d["h"], d["l"], d["c"], d["v"]
            elif inst in feeds.XAU_FEEDS:
                df = feeds.load_xau(inst, tf, anchor_hour=feeds.XAU_ANCHOR_HOUR)
                ix = pd.DatetimeIndex(df.index)
                o, h, l, c = (df[k].to_numpy(float) for k in "ohlc"); v = df["v"].to_numpy(float)
            else:
                df = feeds.load_mt(inst, tf)
                ix = pd.DatetimeIndex(df.index)
                o, h, l, c = (df[k].to_numpy(float) for k in "ohlc"); v = df["v"].to_numpy(float)
        except Exception as e:
            print(f"\n{inst} {tf}m -- UNAVAILABLE: {str(e)[:70]}")
            continue
        score, notes, m = _quality(ix, o, h, l, c, v, tf)
        print(f"\n{inst}  {tf}-minute")
        print(f"  file            {path}")
        print(f"  source format   {src}")
        print(f"  timestamp       {tsfmt}, stored {order}")
        print(f"  timezone        New York (derived per feed, not inherited)")
        print(f"  span            {ix[0]} -> {ix[-1]}   ({(ix[-1]-ix[0]).days/365.25:.1f} years)")
        print(f"  rows            {len(ix):,}")
        print(f"  columns         open, high, low, close, volume")
        print(f"  bid/ask         NOT AVAILABLE -- spread cannot be measured, only assumed")
        print(f"  volume meaning  {volmeaning}")
        print(f"  duplicates      {m['dup']}")
        print(f"  OHLC violations {m['ohlc_bad']}")
        print(f"  missing bars    {100*m['offgrid']:.2f}% off-grid (weekends, holidays, halts)")
        print(f"  zero-range      {100*m['zero_range']:.2f}%")
        print(f"  DATA QUALITY    {score:.1f} / 100")
        for n in notes:
            print(f"     {n}")
        rows.append(dict(inst=inst, tf=tf, rows=len(ix), start=ix[0], end=ix[-1], score=score))
    print("\n" + "=" * 100)
    return pd.DataFrame(rows)
