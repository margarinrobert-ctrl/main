"""Bars for the Turtle-scalp study: load, resample, cache, split.

Resampling is anchored to **New York local midnight**, not to UTC.  For every timeframe used here
(a divisor of 60) that is identical to anchoring at the 18:00 ET futures open, so there is no
ambiguity about which convention TradingView would use; it also means a bucket boundary lands on
07:00 and 11:00 exactly, in wall clock, on both sides of every DST transition.

The research/locked split is by SESSION, first 65% research, and it is computed here so that no
search path can invent its own.  `locked()` is deliberately awkward to call by accident.
"""
from __future__ import annotations

import hashlib
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from turtle_sim import Series

DATA = os.environ.get("TURTLE_OUT", os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
CACHE = os.path.join(os.environ.get("TMPDIR", "/tmp"), "turtle_bars_cache")

RESEARCH_FRACTION = 0.65

# name -> (parquet, native timeframe minutes, first usable date, point value $, cost model)
INSTRUMENTS = {
    # US30 index future / CFD.  Identified in turtle_data.py: 1.36% mean level error against
    # published Dow levels, 94%+ for every alternative.  Costs are the YM futures line:
    # 1 tick (1.0 index point) spread + 1 point slippage + $1.24 commission on a $5/point contract.
    "US30": dict(file="US30_1m.parquet", native=1, start="2016-10-27", point_value=5.0,
                 cost_abs=2.0, cost_bp=0.0, comm=1.24, stop_slip=1.0, tick=1.0),
    # Spot gold, 100 oz.  RESEARCH_PROTOCOL §5: a 20-cent retail spread is $20 per round turn,
    # which is the highest hurdle of the three and the reason the cost sweep matters most here.
    "XAU": dict(file="XAU_5m.parquet", native=5, start="2007-01-01", point_value=100.0,
                cost_abs=0.20, cost_bp=0.0, comm=0.0, stop_slip=0.05, tick=0.01),
    # BTCUSDT perpetual/spot on Binance.  Fees are proportional, not absolute: 4 bp taker each
    # side plus 2 bp slippage = 10 bp round turn, an order of magnitude dearer in relative terms
    # than either of the others.
    "BTC": dict(file="BTC_15m.parquet", native=15, start="2018-01-01", point_value=1.0,
                cost_abs=0.0, cost_bp=10.0, comm=0.0, stop_slip=0.0005, tick=0.01),
}


def _key(name: str, tf: int) -> str:
    spec = INSTRUMENTS[name]
    p = os.path.join(DATA, spec["file"])
    st = os.stat(p)
    h = hashlib.md5(f"{name}|{tf}|{int(st.st_mtime)}|{st.st_size}|{spec['start']}|v3".encode())
    return os.path.join(CACHE, h.hexdigest() + ".npz")


def load(name: str, tf: int) -> Series:
    """OHLCV resampled to `tf` minutes, NY-anchored, with minute-of-day and session index."""
    if 60 % tf != 0 and tf % 60 != 0:
        raise ValueError(f"timeframe {tf} must divide or be a multiple of 60")
    spec = INSTRUMENTS[name]
    if tf % spec["native"] != 0:
        raise ValueError(f"{name} is native {spec['native']}m; {tf}m is not a multiple")

    os.makedirs(CACHE, exist_ok=True)
    ck = _key(name, tf)
    if os.path.exists(ck):
        z = np.load(ck, allow_pickle=False)
        return Series(z["o"], z["h"], z["l"], z["c"], z["v"], z["ny_min"], z["sess"],
                      z["ts"], name=name, tf=tf)

    df = pd.read_parquet(os.path.join(DATA, spec["file"]))
    df = df[df.ny_date >= spec["start"]].reset_index(drop=True)

    if tf == spec["native"]:
        g = df
        bucket_min = df.ny_min.to_numpy()
    else:
        bucket_min = (df.ny_min.to_numpy() // tf) * tf
        key = df.ny_date.to_numpy().astype(str)
        idx = pd.MultiIndex.from_arrays([key, bucket_min], names=("d", "m"))
        g = df.groupby(idx, sort=True).agg(
            ts=("ts", "first"), open=("open", "first"), high=("high", "max"),
            low=("low", "min"), close=("close", "last"), volume=("volume", "sum"),
            ny_date=("ny_date", "first"))
        g = g.reset_index(drop=True)
        bucket_min = np.array([m for _, m in
                               sorted({(d, m) for d, m in zip(key, bucket_min)})], dtype=np.int64)
        # groupby(sort=True) on the MultiIndex orders by (date, minute), which is chronological.
        g["ny_min"] = bucket_min

    ts = g.ts.to_numpy().astype("datetime64[m]").astype(np.int64)
    sess = pd.factorize(g.ny_date.to_numpy(), sort=True)[0].astype(np.int64)
    order = np.lexsort((g.ny_min.to_numpy(), sess))
    if not np.array_equal(order, np.arange(len(g))):
        g = g.iloc[order].reset_index(drop=True)
        ts, sess = ts[order], sess[order]

    s = Series(g.open.to_numpy(), g.high.to_numpy(), g.low.to_numpy(), g.close.to_numpy(),
               g.volume.to_numpy(), g.ny_min.to_numpy(), sess, ts, name=name, tf=tf)
    np.savez_compressed(ck, o=s.o, h=s.h, l=s.l, c=s.c, v=s.v, ny_min=s.ny_min,
                        sess=s.sess, ts=s.ts)
    return s


def split_session(s: Series, fraction: float = RESEARCH_FRACTION) -> int:
    """The session index at which the locked block begins."""
    n_sess = int(s.sess.max()) + 1
    return int(round(n_sess * fraction))


def mask_research(s: Series) -> np.ndarray:
    return s.sess < split_session(s)


def mask_locked(s: Series) -> np.ndarray:
    return s.sess >= split_session(s)


def block_of(s: Series, exit_bar: np.ndarray) -> np.ndarray:
    """0 = research, 1 = locked, keyed on the EXIT bar so a straddling trade lands in one block."""
    return (s.sess[exit_bar] >= split_session(s)).astype(np.int64)


def describe(name: str, tf: int) -> str:
    s = load(name, tf)
    cut = split_session(s)
    d = np.datetime64("1970-01-01T00:00") + s.ts.astype("timedelta64[m]")
    n_sess = int(s.sess.max()) + 1
    first_locked = d[np.searchsorted(s.sess, cut)]
    return (f"{name} {tf}m  {s.n:,} bars  {n_sess:,} sessions  "
            f"{d[0]} -> {d[-1]} UTC  research < session {cut} ({first_locked})")


if __name__ == "__main__":
    for nm, spec in INSTRUMENTS.items():
        for tf in (spec["native"], 5, 15, 30, 60):
            if tf % spec["native"] or tf < spec["native"]:
                continue
            print(describe(nm, tf))
