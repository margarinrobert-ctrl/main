"""Chart bars at 15m / 1H for the YouTube variant, each with a pointer into the finest sub-series.

Same execution principle as `daily.py`: the DECISION is made on the chart bar, the FILL is resolved
on the finest data the feed provides. Resolution is uneven and is reported per market rather than
averaged away -- US30 and NQ resolve at 1 minute, gold at 5, US100 and BTC at 15, EURUSD at 30.

EURUSD cannot be charted at 15m: its source is 30-minute. It appears at 1H only.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")

# Gold pre-2010 is excluded with cause: 10.06% zero-range bars, median 5m volume of 14 ticks.
FIRST = {"XAUUSD": "2010-01-01"}
BASE = {"US30": 1, "NQ": 1, "XAUUSD": 5, "US100": 15, "BTC": 15, "EURUSD": 30}
CHARTS = (15, 60)
_C = {}


def _fine(market):
    tf = BASE[market]
    if market == "EURUSD":
        from edgelab import fx
        return fx.bars("EURUSD", tf)
    if market == "BTC":
        from edgelab import crypto
        return crypto.bars("BTC", tf)
    from edgelab import feeds
    return feeds.bars(market, tf)


def load(market, chart):
    if BASE[market] > chart:
        return None
    key = (market, chart)
    if key in _C:
        return _C[key]
    d = _fine(market)
    ix = pd.DatetimeIndex(d["idx"])
    key_i = np.asarray(ix.view("int64")) // (chart * 60_000_000_000)
    df = pd.DataFrame({"o": d["o"], "h": d["h"], "l": d["l"], "c": d["c"], "k": key_i})
    g = df.groupby("k", sort=True)
    bars = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last(),
                         "sub": g.size()})
    starts = np.searchsorted(key_i, bars.index.to_numpy(), side="left")
    ends = np.searchsorted(key_i, bars.index.to_numpy(), side="right")
    date = pd.to_datetime(bars.index.to_numpy() * chart * 60_000_000_000)
    if market in FIRST:
        keep = date >= pd.Timestamp(FIRST[market])
        bars, date = bars[keep], date[keep]
        starts, ends = starts[keep], ends[keep]
    out = dict(market=market, chart=chart, resolution=BASE[market], n=len(bars),
               o=bars.o.to_numpy(float), h=bars.h.to_numpy(float),
               l=bars.l.to_numpy(float), c=bars.c.to_numpy(float),
               idx=pd.DatetimeIndex(date), start=starts.astype(np.int64),
               end=ends.astype(np.int64),
               io=d["o"], ih=d["h"], il=d["l"], ic=d["c"])
    _C[key] = out
    return out


def split(b, frac=0.65):
    cut = int(frac * b["n"])
    return cut, b["idx"][cut]


def inventory(verbose=True):
    rows = []
    for chart in CHARTS:
        for m in BASE:
            b = load(m, chart)
            if b is None:
                continue
            cut, cd = split(b)
            rows.append(dict(chart=f"{chart}m", market=m, bars=b["n"], res=b["resolution"],
                             start=b["idx"][0].date(), end=b["idx"][-1].date(),
                             oos_from=cd.date()))
    df = pd.DataFrame(rows)
    if verbose:
        print(f"{'chart':>6}{'market':>9}{'bars':>10}{'res':>6}{'from':>13}{'to':>13}{'OOS from':>13}")
        for r in df.itertuples():
            print(f"{r.chart:>6}{r.market:>9}{r.bars:>10,}{r.res:>5}m{str(r.start):>13}"
                  f"{str(r.end):>13}{str(r.oos_from):>13}")
    return df


if __name__ == "__main__":
    inventory()
