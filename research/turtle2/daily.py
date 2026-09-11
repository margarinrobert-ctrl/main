"""Daily bars on the 17:00 New York boundary, with the intraday path kept alongside.

WHY BOTH. The original Turtle system is a DAILY system -- 20- and 55-day channels, a 20-day N --
but its orders are intraday STOP orders: the entry triggers the moment price trades through the
channel, the 2N stop and the N-day exit likewise. `STUDY_ATME_LIVE.md` established on this branch
what happens when bar-level code resolves that ordering by rule instead of by sequence: the same
configuration went from PF 1.99 to 0.99. So every daily bar here carries a pointer into the
intraday series that produced it, and the engine walks that path to decide what happened first.

THE DAY BOUNDARY IS 17:00 NEW YORK on every market, the CME futures convention the Turtles
actually traded. For gold, EURUSD and BTC that is a convention rather than a native session, and
it is applied uniformly so all five markets share one calendar and the portfolio aggregates on
matching days. Moving it would change every 20- and 55-day extreme, so it is a stated choice.

INTRADAY RESOLUTION IS NOT UNIFORM and that is a real weakness of this test, reported rather than
hidden: US30 resolves at 1 minute, gold at 5, US100 and BTC at 15, EURUSD at 30. A EURUSD stop
sequence is therefore decided 30x more coarsely than a US30 one. `resolution_minutes` carries it
into every report.

NQ IS DELIBERATELY EXCLUDED. It is ~750 daily bars (three years) against US100's ~2,300 on the
same underlying at 0.874 correlation -- a near-duplicate with too little history for a 55-day
system to produce a meaningful trade count.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")

# market -> (loader tag, intraday timeframe used for path resolution)
MARKETS = {
    "XAUUSD": ("edgelab", 5),
    "EURUSD": ("fx", 30),
    "BTC":    ("crypto", 15),
    "US30":   ("edgelab", 1),
    "US100":  ("edgelab", 15),
}
ASSET_CLASS = {"XAUUSD": "metal", "EURUSD": "fx", "BTC": "crypto",
               "US30": "index", "US100": "index"}
# Gold before 2010 is excluded with cause on this branch: 10.06% zero-range bars and a median
# 5-minute volume of 14 ticks. That is a quote feed idling, not a market.
FIRST_DAY = {"XAUUSD": "2010-01-01"}
DAY_ANCHOR_H = 7          # 17:00 New York -> add 7h, then normalise
_CACHE = {}


def _intraday(market):
    tag, tf = MARKETS[market]
    if tag == "fx":
        from edgelab import fx
        d = fx.bars("EURUSD", tf)
    elif tag == "crypto":
        from edgelab import crypto
        d = crypto.bars("BTC", tf)
    else:
        from edgelab import feeds
        d = feeds.bars(market, tf)
    return d


def load(market):
    """Returns daily OHLC arrays plus, for each day, the slice of intraday bars inside it."""
    if market in _CACHE:
        return _CACHE[market]
    d = _intraday(market)
    ix = pd.DatetimeIndex(d["idx"])
    day_key = ((ix + pd.Timedelta(hours=DAY_ANCHOR_H)).normalize().view("int64")
               // 86_400_000_000_000)
    df = pd.DataFrame({"o": d["o"], "h": d["h"], "l": d["l"], "c": d["c"],
                       "v": d["v"], "day": day_key})
    g = df.groupby("day", sort=True)
    daily = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(),
                          "c": g.c.last(), "v": g.v.sum(), "bars": g.size()})
    # a day with too few intraday bars is a holiday stub, not a session
    keep = daily["bars"] >= max(2, (390 // MARKETS[market][1]) // 8)
    daily = daily[keep]
    # index of the first and last intraday bar of each surviving day
    starts = np.searchsorted(day_key, daily.index.to_numpy(), side="left")
    ends = np.searchsorted(day_key, daily.index.to_numpy(), side="right")
    date = pd.to_datetime(daily.index.to_numpy() * 86_400_000_000_000) - pd.Timedelta(
        hours=DAY_ANCHOR_H)
    if market in FIRST_DAY:
        keep2 = date >= pd.Timestamp(FIRST_DAY[market])
        daily, date = daily[keep2], date[keep2]
        starts, ends = starts[keep2], ends[keep2]
    out = dict(
        market=market, asset=ASSET_CLASS[market], resolution_minutes=MARKETS[market][1],
        o=daily.o.to_numpy(float), h=daily.h.to_numpy(float),
        l=daily.l.to_numpy(float), c=daily.c.to_numpy(float),
        v=daily.v.to_numpy(float), n=len(daily),
        date=pd.DatetimeIndex(date), day=daily.index.to_numpy(),
        start=starts.astype(np.int64), end=ends.astype(np.int64),
        io=d["o"], ih=d["h"], il=d["l"], ic=d["c"],
    )
    _CACHE[market] = out
    return out


def split(b, frac=0.65):
    """Per-market time split. The OOS tail is not to be read until the rules are frozen."""
    cut = int(frac * b["n"])
    return cut, b["date"][cut]


def inventory(verbose=True):
    rows = []
    for m in MARKETS:
        b = load(m)
        cut, cut_date = split(b)
        rows.append(dict(market=m, asset=b["asset"], days=b["n"],
                         start=b["date"][0].date(), end=b["date"][-1].date(),
                         res=b["resolution_minutes"], is_days=cut, oos_days=b["n"] - cut,
                         oos_from=cut_date.date()))
    df = pd.DataFrame(rows)
    if verbose:
        print(f"{'market':<8}{'class':<8}{'days':>7}{'from':>13}{'to':>13}"
              f"{'res':>5}{'in-samp':>9}{'OOS':>7}{'OOS from':>13}")
        for r in df.itertuples():
            print(f"{r.market:<8}{r.asset:<8}{r.days:>7,}{str(r.start):>13}{str(r.end):>13}"
                  f"{r.res:>4}m{r.is_days:>9,}{r.oos_days:>7,}{str(r.oos_from):>13}")
    return df


if __name__ == "__main__":
    inventory()
