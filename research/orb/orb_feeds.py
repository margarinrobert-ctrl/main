"""Feeds for the ORB study, with each instrument's own contract spec.

THREE THINGS DIFFER PER MARKET AND ALL THREE CHANGE THE ANSWER:

  the EXECUTION RESOLUTION. NQ has 1-minute bars, so its exits are walked minute by minute and
  the intrabar tie-break almost never binds. The three CFD feeds are 15-MINUTE ONLY, so a 1 ATR
  stop and a 1 ATR target routinely sit inside one bar and the tie-break is a real assumption.
  It is reported both ways on every market rather than asserted.

  the COST AS A FRACTION OF RISK. `STUDY_TURTLE_15M` recorded charging NQ's points in gold's
  points and calling the result a failure. Costs here are per-market and are also reported as a
  share of the 1 ATR stop, which is the only cross-market unit.

  the VOLUME SERIES. NQ carries true contract volume. The CFD exports carry `Volume` as literal
  zeros and `TickVolume` as the real series, so the session VWAP and the 1.2x volume filter on
  those feeds are PROXIES and are labelled as such everywhere.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(HERE, ".."), os.path.join(HERE, "..", "v63")):
    if p not in sys.path:
        sys.path.insert(0, p)

import v63feeds as FD  # noqa: E402

# per side: (spread, slippage, fees) in POINTS, point value, tick, native bar size, volume kind
SPEC = {
    "NQ":       dict(spread=0.25, slip=0.25, fee=0.36, pv=2.0, tick=0.25, native=1,
                     vol="true contract volume"),
    "US100":    dict(spread=0.30, slip=0.30, fee=0.15, pv=1.0, tick=0.1, native=15,
                     vol="TICK volume -- a PROXY, the Volume column is literal zeros"),
    "US30":     dict(spread=0.60, slip=0.60, fee=0.30, pv=1.0, tick=0.1, native=15,
                     vol="TICK volume -- a PROXY, the Volume column is literal zeros"),
    "US30_ISO": dict(spread=0.60, slip=0.60, fee=0.30, pv=1.0, tick=0.1, native=15,
                     vol="volume as delivered by a SECOND PROVIDER"),
}
# the branch's existing totals are 0.86 / 0.75 / 1.50 per side; the split above reproduces them.
for k, v in SPEC.items():
    v["cost_per_side"] = round(v["spread"] + v["slip"] + v["fee"], 4)


def bars(market, tf):
    if market != "US30_ISO":
        return FD.bars(market, tf)
    d = pd.read_csv("data/US30_ISO_15m.csv")
    f = pd.DataFrame({"open": d["open"].to_numpy(float), "high": d["high"].to_numpy(float),
                      "low": d["low"].to_numpy(float), "close": d["close"].to_numpy(float),
                      "volume": d["volume"].to_numpy(float)},
                     index=pd.DatetimeIndex(pd.to_datetime(d["ny"])))
    f = f.sort_index()
    f = f[~f.index.duplicated(keep="first")]
    if tf == 15:
        return f
    if tf % 15:
        raise ValueError(f"{tf}m is not a multiple of US30_ISO's native 15m")
    return f.resample(f"{tf}min").agg({"open": "first", "high": "max", "low": "min",
                                       "close": "last", "volume": "sum"}).dropna()


def blocks(market, ix):
    """The branch's existing split per feed. US30_ISO begins 2024-08 and is a SECOND PROVIDER over
    a span the other US30 file does not reach, so it is one reserved block and is read once."""
    if market == "US30_ISO":
        ts = pd.DatetimeIndex(ix)
        return {"reserved (second provider)": np.ones(len(ts), bool)}
    return FD.blocks(market, ix)
