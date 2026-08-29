"""Loaders for the three feeds restored on 2026-08-29, in the shapes the V38 engine wants.

US100_LONG_15m and US30_LONG_15m arrive TAB-separated, NEWEST FIRST, with the broker's own clock,
which `research/datasets.py` records as New York + 7 for both -- derived, not assumed, and stable
across daylight saving because the broker follows US DST. US30_ISO_15m is already unwrapped to a
New York `ny` column.

These two markets had NO PART in the V38 search. That is the whole reason to load them: US100
before 2022-12-26 is 2018, COVID and the 2022 bear, none of which the NQ sample contains, and the
US30 file is eight and a half years of a materially more independent index (15m return correlation
US30/NQ 0.679 against US100/NQ 0.874).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

NY_SHIFT_H = 7          # the broker stamp is New York + 7 on both LONG feeds
LONG = {"US100L": "data/US100_LONG_15m.csv", "US30L": "data/US30_LONG_15m.csv"}
ISO = {"US30I": "data/US30_ISO_15m.csv"}
INSTR = {"NQ": dict(tick=0.25, pv=2.0), "US100L": dict(tick=0.25, pv=2.0),
         "US30L": dict(tick=1.0, pv=5.0), "US30I": dict(tick=1.0, pv=5.0)}


def load(name):
    if name in LONG:
        d = pd.read_csv(LONG[name], sep="\t")
        ix = pd.to_datetime(d["DateTime"], format="%Y.%m.%d %H:%M:%S") \
            - pd.Timedelta(hours=NY_SHIFT_H)
        f = pd.DataFrame({"open": d["Open"].to_numpy(float), "high": d["High"].to_numpy(float),
                          "low": d["Low"].to_numpy(float), "close": d["Close"].to_numpy(float),
                          "volume": d["TickVolume"].to_numpy(float)}, index=ix)
    else:
        d = pd.read_csv(ISO[name], parse_dates=["ny"])
        f = pd.DataFrame({"open": d["open"].to_numpy(float), "high": d["high"].to_numpy(float),
                          "low": d["low"].to_numpy(float), "close": d["close"].to_numpy(float),
                          "volume": d["Volume"].to_numpy(float)}, index=d["ny"])
    f = f.sort_index()
    return f[~f.index.duplicated(keep="first")]


def resample(f, tf):
    if tf == 15:
        return f
    return f.resample(f"{tf}min").agg({"open": "first", "high": "max", "low": "min",
                                       "close": "last", "volume": "sum"}).dropna()


def frame(name, tf):
    f = resample(load(name), tf)
    return dict(o=f["open"].to_numpy(float), h=f["high"].to_numpy(float),
                l=f["low"].to_numpy(float), c=f["close"].to_numpy(float),
                ts=f.index.values.astype("datetime64[ns]").astype(np.int64),
                mod=(f.index.hour * 60 + f.index.minute).to_numpy(np.int64))
