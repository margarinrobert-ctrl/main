"""Load US30 and XAUUSD as 15-minute bars, so the NQ-derived gate can be tested somewhere else.

THE GATE IS FROZEN. ADX >= 20, EMA100 distance >= 3.0 ATR, ATR(20)/mean(ATR,200) >= 1.10, three
units -- every one of those numbers was chosen on NQ research and NOTHING is refitted here. That is
the whole point: a rule that needs new constants per market has not transferred, it has been fitted
twice.

TWO FORMATS, BOTH ALREADY CHARACTERISED IN `research/datasets.py`. US30 arrives TAB-separated and
NEWEST-FIRST, which sorts to nonsense if read naively. XAUUSD is semicolon-separated with a
minute-resolution timestamp and no seconds. Both are re-sorted ascending and de-duplicated here.

CLOCKS. Neither file is in New York time and neither offset is a guess: `datasets.py` records the
evidence -- both US30 and XAUUSD are NEW YORK + 7, gold's derived from its own anchor (its summer
volatility peak lands at raw 15:30 = 08:30 New York to the minute) rather than assumed from the
equity open. `to_ny` applies that shift.

WHY IT DID NOT MATTER AND NOW DOES. The frozen-gate test reads no calendar condition, so an offset
error would have moved the session labels in the reporting and left the rule untouched -- the first
cross-market run was run without the shift for exactly that reason. **Correlation work is the
opposite case.** Comparing NQ at 09:30 New York against gold at what is really 02:30 does not
measure a weak relationship, it measures the wrong pair of bars, and the answer would come back
near zero for a reason that has nothing to do with the markets. Anything that joins two feeds on
time must apply the shift.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")


def _resample(df, minutes):
    r = df.resample(f"{minutes}min", label="left", closed="left").agg(
        {"o": "first", "h": "max", "l": "min", "c": "last", "v": "sum"}).dropna()
    return r


NY_OFFSET_HOURS = {"US30": -7, "XAUUSD": -7}   # file time -> New York; see module docstring


def load(name, tf=15, to_ny=True):
    """Returns the same dict shape `fastbars.bars` produces, so every engine here just works."""
    if name == "US30":
        df = pd.read_csv("data/US30_15m.csv", sep="\t")
        df.columns = [c.strip() for c in df.columns]
        idx = pd.to_datetime(df["DateTime"], format="%Y.%m.%d %H:%M:%S")
        df = pd.DataFrame({"o": df["Open"], "h": df["High"], "l": df["Low"],
                           "c": df["Close"], "v": df["TickVolume"]}).set_index(idx)
        df = df[~df.index.duplicated(keep="first")].sort_index()
        if to_ny:
            df.index = df.index + pd.Timedelta(hours=NY_OFFSET_HOURS["US30"])
        if tf != 15:
            df = _resample(df, tf)
    elif name == "XAUUSD":
        df = pd.read_csv("data/XAUUSD_5m.csv", sep=";")
        df.columns = [c.strip() for c in df.columns]
        idx = pd.to_datetime(df["Date"], format="%Y.%m.%d %H:%M")
        df = pd.DataFrame({"o": df["Open"], "h": df["High"], "l": df["Low"],
                           "c": df["Close"], "v": df["Volume"]}).set_index(idx)
        df = df[~df.index.duplicated(keep="first")].sort_index()
        if to_ny:
            df.index = df.index + pd.Timedelta(hours=NY_OFFSET_HOURS["XAUUSD"])
        df = _resample(df, tf)
    else:
        raise ValueError(name)

    ix = df.index
    mod = (ix.hour * 60 + ix.minute).to_numpy().astype(np.int64)
    # A "session" is a calendar day here. The split below is over sessions, matching every other
    # module, and a day boundary is good enough for that -- the gate reads no session feature.
    sess = np.asarray(ix.normalize().values).astype("datetime64[ns]").astype(np.int64)
    d = dict(o=df["o"].to_numpy(float), h=df["h"].to_numpy(float), l=df["l"].to_numpy(float),
             c=df["c"].to_numpy(float), v=df["v"].to_numpy(float), mod=mod, sess=sess,
             ts=ix.values.astype("datetime64[ns]").astype(np.int64), n=len(df))
    us = np.unique(sess)
    si = np.searchsorted(us, sess)
    return d, si, int(0.65 * len(us))


def nq_ny(tf=15):
    """NQ 15m with a NEW YORK index, because `fastbars` gives UTC timestamps and NY minutes.

    THIS BIT NIPPED ME. `fastbars.bars()` returns `ts` stamped in UTC and `mod` already converted
    to New York -- the two disagree by 5 hours in winter and 4 in summer, which is exactly DST.
    Every engine here reads `mod`, so the strategy work was always correct; the first correlation
    panel joined on `ts` and therefore compared NQ against US30 bars five hours away. It reported
    corr(NQ, US30) = 0.031 for two US equity indices, which is the tell -- a number that
    implausible is a join error, not a market fact.

    A CONSTANT SHIFT WOULD ALSO BE WRONG, for the same reason it was wrong on the BTC feed: the
    offset is -5 in winter and -4 in summer, so only a real tz conversion lands every bar.
    """
    import sys
    sys.path.insert(0, "research")
    import fastbars
    d = fastbars.bars(tf)
    ix = pd.DatetimeIndex(pd.to_datetime(d["ts"])).tz_localize("UTC").tz_convert(
        "America/New_York").tz_localize(None)
    return d, ix


def load_iso(path="data/US30_ISO_15m.csv", tf=15):
    """The ISO-8601 US30 feed: the FIRST file here whose clock is STATED, not derived.

    Every other feed on this branch had its offset inferred -- gold from its own volatility anchor,
    US30 and EURUSD from equity-open alignment, BTC from a DST-aware conversion that a constant
    shift got wrong. This one carries an explicit UTC offset per row, and the offsets present are
    exactly -4 and -5, i.e. New York with daylight saving. The 09:00 volatility peak confirms it
    independently. That removes the single largest source of silent error in cross-market work.

    It also matters for a different reason: 27,436 of its 48,937 bars fall AFTER 2025-07-15, where
    the previously studied US30 file ends. That block has never been read by any study here, which
    makes it the closest thing available to a genuine forward test.
    """
    df = pd.read_csv(path, parse_dates=["ny"]).set_index("ny").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df = df.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c", "volume": "v"})
    if tf != 15:
        df = _resample(df, tf)
    ix = df.index
    mod = (ix.hour * 60 + ix.minute).to_numpy().astype(np.int64)
    sess = np.asarray(ix.normalize().values).astype("datetime64[ns]").astype(np.int64)
    d = dict(o=df["o"].to_numpy(float), h=df["h"].to_numpy(float), l=df["l"].to_numpy(float),
             c=df["c"].to_numpy(float), v=df["v"].to_numpy(float), mod=mod, sess=sess,
             ts=ix.values.astype("datetime64[ns]").astype(np.int64), n=len(df))
    us = np.unique(sess)
    return d, np.searchsorted(us, sess), int(0.65 * len(us))
