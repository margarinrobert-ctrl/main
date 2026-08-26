"""Load US30 and XAUUSD as 15-minute bars, so the NQ-derived gate can be tested somewhere else.

THE GATE IS FROZEN. ADX >= 20, EMA100 distance >= 3.0 ATR, ATR(20)/mean(ATR,200) >= 1.10, three
units -- every one of those numbers was chosen on NQ research and NOTHING is refitted here. That is
the whole point: a rule that needs new constants per market has not transferred, it has been fitted
twice.

TWO FORMATS, BOTH ALREADY CHARACTERISED IN `research/datasets.py`. US30 arrives TAB-separated and
NEWEST-FIRST, which sorts to nonsense if read naively. XAUUSD is semicolon-separated with a
minute-resolution timestamp and no seconds. Both are re-sorted ascending and de-duplicated here.

CLOCKS. Neither file is in New York time and neither offset is a guess: `datasets.py` records the
evidence for each. What matters for this test is only that minute-of-day is CONSISTENT within a
file, because the gate reads no calendar condition -- so an offset error would shift the session
boundaries in the reporting but not the rule.
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


def load(name, tf=15):
    """Returns the same dict shape `fastbars.bars` produces, so every engine here just works."""
    if name == "US30":
        df = pd.read_csv("data/US30_15m.csv", sep="\t")
        df.columns = [c.strip() for c in df.columns]
        idx = pd.to_datetime(df["DateTime"], format="%Y.%m.%d %H:%M:%S")
        df = pd.DataFrame({"o": df["Open"], "h": df["High"], "l": df["Low"],
                           "c": df["Close"], "v": df["TickVolume"]}).set_index(idx)
        df = df[~df.index.duplicated(keep="first")].sort_index()
        if tf != 15:
            df = _resample(df, tf)
    elif name == "XAUUSD":
        df = pd.read_csv("data/XAUUSD_5m.csv", sep=";")
        df.columns = [c.strip() for c in df.columns]
        idx = pd.to_datetime(df["Date"], format="%Y.%m.%d %H:%M")
        df = pd.DataFrame({"o": df["Open"], "h": df["High"], "l": df["Low"],
                           "c": df["Close"], "v": df["Volume"]}).set_index(idx)
        df = df[~df.index.duplicated(keep="first")].sort_index()
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
