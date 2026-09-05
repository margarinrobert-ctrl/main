"""Three feeds with a usable volume series, for a VWAP that is not a fiction.

`mrl_bar.Feed` returns `v` as an array of ones -- a placeholder, not volume -- so a VWAP built on
it would be an unweighted average wearing a weighted name. The CFD exports carry `Volume` as
literal ZEROS and `TickVolume` as the real series, so TICK VOLUME is what is used here and it is
labelled a PROXY everywhere it appears. NQ_1m carries true contract volume.

NQ_1m is stamped in UTC and every other feed here is already New York (`research/datasets.py`);
getting that wrong puts a 09:30 session anchor at 04:30, which is the pre-open block this branch
has measured as the worst part of the day four times.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research",):
    q = os.path.join(ROOT, p)
    if q not in sys.path:
        sys.path.insert(0, q)

FEEDS = ("US100", "US30", "NQ")
VOL_KIND = {"US100": "tick volume (a PROXY -- the Volume column is literal zeros)",
            "US30": "tick volume (a PROXY -- the Volume column is literal zeros)",
            "NQ": "true contract volume"}
# points of cost per side, and the value of a point in dollars for one unit
COST = {"NQ": (0.86, 2.0), "US100": (0.75, 1.0), "US30": (1.50, 1.0)}


def _raw(market):
    if market == "NQ":
        d = pd.read_csv("data/NQ_1m.csv")
        ix = (pd.DatetimeIndex(pd.to_datetime(d["timestamp"], utc=True))
              .tz_convert("America/New_York").tz_localize(None))
        f = pd.DataFrame({"open": d["open"].to_numpy(float), "high": d["high"].to_numpy(float),
                          "low": d["low"].to_numpy(float), "close": d["close"].to_numpy(float),
                          "volume": d["volume"].to_numpy(float)}, index=ix)
    else:
        d = pd.read_csv(f"data/{market}_LONG_15m.csv", sep="\t")
        d.columns = [c.strip().lower() for c in d.columns]
        tc = [c for c in d.columns if "date" in c or "time" in c][0]
        ix = pd.DatetimeIndex(pd.to_datetime(d[tc])) - pd.Timedelta(hours=7)
        vol = d["tickvolume"] if "tickvolume" in d.columns else d["volume"]
        f = pd.DataFrame({"open": d["open"].to_numpy(float), "high": d["high"].to_numpy(float),
                          "low": d["low"].to_numpy(float), "close": d["close"].to_numpy(float),
                          "volume": vol.to_numpy(float)}, index=ix)
    f = f.sort_index()
    return f[~f.index.duplicated(keep="first")]


def bars(market, tf):
    f = _raw(market)
    native = 1 if market == "NQ" else 15
    if tf == native:
        return f
    if tf % native:
        raise ValueError(f"{tf}m is not a multiple of {market}'s native {native}m")
    return f.resample(f"{tf}min").agg({"open": "first", "high": "max", "low": "min",
                                       "close": "last", "volume": "sum"}).dropna()


def blocks(market, ix):
    """The block split this branch already uses for each feed, so nothing is re-cut here."""
    ts = pd.DatetimeIndex(ix)
    if market == "NQ":
        key = (ts.year * 10000 + ts.month * 100 + ts.day).to_numpy()
        sess = np.where((ts.hour * 60 + ts.minute).to_numpy() >= 1080, key + 1, key)
        us = np.unique(sess)
        cut = us[int(0.65 * len(us))]
        return {"research": sess < cut, "locked": sess >= cut}
    return {"research": np.asarray(ts < "2022-01-01"),
            "validation": np.asarray((ts >= "2022-01-01") & (ts < "2024-01-01")),
            "test": np.asarray(ts >= "2024-01-01")}
