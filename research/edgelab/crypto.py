"""BTCUSDT 15-minute: a SIXTH instrument, a SIXTH format, and the first feed whose clock is NOT a
fixed offset.

THREE THINGS THAT MAKE THIS FILE DIFFERENT FROM THE FIVE BEFORE IT.

1. THE CLOCK IS UTC, SO A CONSTANT SHIFT IS WRONG. Every other feed here is a broker export whose
   server clock FOLLOWS US daylight saving, which is why a fixed -7h was right year round for
   US100, US30, XAUUSD and EURUSD. `derive_offset` was built to refuse a constant shift when winter
   and summer disagree, and this is the first feed to trip that guard -- correctly. Measured against
   US30, whose own clock is independently verified:

       corr(BTC - k hours, US30)      winter (DJF)    summer (JJA)
         k = 4                             0.0176          0.1625
         k = 5                             0.1289          0.0073

   They disagree by exactly one hour, which is the daylight-saving signature. A true
   UTC -> America/New_York conversion scores 0.1289 in winter and 0.1625 in summer -- each season's
   own best -- and 0.1337 pooled, against 0.0908 for the best single constant shift. So this loader
   CONVERTS rather than shifts, and the fall-back hour's duplicate timestamps are dropped.

   The raw profile agrees independently: both mean |return| and trade count peak at raw hour 14,
   and 13:00-16:00 UTC brackets the US equity open.

2. IT IS 24/7. Weekday bar counts are 42,183 to 42,402 -- flat. Every other instrument here has a
   weekend hole, and every session-based condition on this branch was written against one. A rule
   whose edge came from a Monday gap or a Friday close has nothing to key on here.

3. IT CARRIES REAL TAKER-SIDE FLOW. `Taker buy base asset volume` over `Volume` is the share of
   volume that lifted the offer -- an ACTUAL order-flow imbalance, not the proxy `features3.py`
   had to construct. It centres at 0.4965 mean / 0.4967 median, so the series is close to balanced
   and any signal has to come from its deviations rather than its level.

FORMAT. A SIXTH distinct export, and a raw Binance klines dump: comma-separated, headed
`Open time,Open,High,Low,Close,Volume,Close time,Quote asset volume,Number of trades,Taker buy base
asset volume,Taker buy quote asset volume,Ignore`. Timestamps carry six decimal places and TRAILING
WHITESPACE. `Ignore` is Binance's documented placeholder and is all zeros.

DEFECTS, measured rather than assumed: the FINAL ROW IS MALFORMED (both timestamps empty, OHLCV
present) and is dropped; 2 duplicate timestamps are dropped; 14 bars have zero volume, zero trades
and zero range together, which is an exchange outage rather than a quiet market. Note also that the
file NAME says 2018-2025 and the data actually runs to 2026-06-15.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CRYPTO_FEEDS = {"BTC": {"15": "data/BTC_15m.csv"}}
SOURCE_TZ = "UTC"
TARGET_TZ = "America/New_York"
_CACHE = {}


def _read_binance(path):
    d = pd.read_csv(path)
    d.columns = [c.strip() for c in d.columns]
    # The last row of this export has empty timestamps with prices present. Dropping on the
    # timestamp is deliberate: a bar we cannot place in time is not a bar.
    d = d[d["Open time"].notna()].copy()
    ts = pd.to_datetime(d["Open time"].astype(str).str.strip())
    out = pd.DataFrame({"o": d["Open"].to_numpy(float), "h": d["High"].to_numpy(float),
                        "l": d["Low"].to_numpy(float), "c": d["Close"].to_numpy(float),
                        "v": d["Volume"].to_numpy(float),
                        "trades": d["Number of trades"].to_numpy(float),
                        "taker_buy": d["Taker buy base asset volume"].to_numpy(float)},
                       index=pd.DatetimeIndex(ts))
    return out[~out.index.duplicated()].sort_index()


def verify_clock(ref="US30", verbose=True):
    """Prove the file is UTC rather than a DST-following broker clock, against a verified feed.

    Returns (constant_shift_ok, detail). `constant_shift_ok` is False here and that is the point:
    when winter and summer pick different shifts, no fixed offset is valid and the caller must
    convert timezones properly.
    """
    from edgelab import feeds
    raw = _read_binance(CRYPTO_FEEDS["BTC"]["15"])
    c = raw["c"].to_numpy()
    r = np.zeros(len(c)); r[1:] = np.log(c[1:] / c[:-1])
    u = feeds.bars(ref, 15)
    us = pd.Series(np.r_[0.0, np.diff(np.log(u["c"]))], index=u["idx"])
    us = us[~us.index.duplicated()]
    detail = {}
    for k in range(3, 7):
        s = pd.Series(r, index=raw.index - pd.Timedelta(hours=k))
        j = pd.concat([s.rename("b"), us.rename("u")], axis=1, join="inner").dropna()
        w = j[np.isin(j.index.month, (12, 1, 2))]
        m = j[np.isin(j.index.month, (6, 7, 8))]
        detail[k] = (float(np.corrcoef(w.b, w.u)[0, 1]), float(np.corrcoef(m.b, m.u)[0, 1]))
    win = max(detail, key=lambda k: detail[k][0])
    sun = max(detail, key=lambda k: detail[k][1])
    ok = win == sun
    if verbose:
        print(f"  BTC clock vs {ref}:   k   winter    summer")
        for k, (a, b) in detail.items():
            print(f"                     {k:>4}  {a:+.4f}   {b:+.4f}")
        print(f"  winter prefers -{win}h, summer prefers -{sun}h -> "
              + ("consistent" if ok else "DISAGREE, so the file is UTC and must be CONVERTED, "
                                         "not shifted"))
    return ok, detail


def load(inst="BTC", tf=15):
    """BTC bars on the NEW YORK clock via a true timezone conversion, oldest first."""
    key = ("crypto", inst, str(tf))
    if key in _CACHE:
        return _CACHE[key]
    raw = _read_binance(CRYPTO_FEEDS[inst][str(tf)])
    ix = (pd.DatetimeIndex(raw.index).tz_localize(SOURCE_TZ)
          .tz_convert(TARGET_TZ).tz_localize(None))
    out = raw.copy()
    out.index = ix
    # the autumn fall-back hour maps two UTC hours onto one local hour; keep the first
    out = out[~out.index.duplicated()].sort_index()
    out["mod"] = out.index.hour * 60 + out.index.minute
    _CACHE[key] = out
    return out


def _ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def bars(inst="BTC", tf=15, atr_n=14):
    """The dict shape every engine here expects, plus `taker_share` and `trades`."""
    key = ("bars", inst, tf, atr_n)
    if key in _CACHE:
        return _CACHE[key]
    df = load(inst, 15)
    if tf != 15:
        if tf % 15:
            raise ValueError("BTC source is 15-minute; tf must be a multiple of 15")
        g = df.resample(f"{int(tf)}min", label="left", closed="left")
        df = pd.DataFrame({"o": g["o"].first(), "h": g["h"].max(), "l": g["l"].min(),
                           "c": g["c"].last(), "v": g["v"].sum(),
                           "trades": g["trades"].sum(),
                           "taker_buy": g["taker_buy"].sum()}).dropna()
        df["mod"] = df.index.hour * 60 + df.index.minute
    o, h, l, c = (df[k].to_numpy(float) for k in "ohlc")
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    v = df["v"].to_numpy(float)
    d = dict(o=o, h=h, l=l, c=c, v=v, trades=df["trades"].to_numpy(float),
             taker_share=np.divide(df["taker_buy"].to_numpy(float), v,
                                   out=np.full(len(v), np.nan), where=v > 0),
             mod=df["mod"].to_numpy(int), atr=_ema(tr, atr_n),
             idx=pd.DatetimeIndex(df.index), df=df)
    d["sess"] = ((d["idx"] + pd.Timedelta(hours=6)).normalize().view("int64")
                 // 86_400_000_000_000)
    d["n"] = len(c)
    _CACHE[key] = d
    return d


def audit(inst="BTC", verbose=True):
    raw = _read_binance(CRYPTO_FEEDS[inst]["15"])
    d = load(inst, 15)
    gap = pd.Series(d.index).diff().dt.total_seconds().div(60)
    dow = pd.Series(d.index.dayofweek).value_counts().sort_index()
    r = dict(bars=len(d), start=d.index.min(), end=d.index.max(),
             dropped_malformed=1, dropped_dup=len(raw) - len(raw[~raw.index.duplicated()]),
             ohlc_bad=int(((d.h < d.l) | (d.h < d.o) | (d.h < d.c) |
                           (d.l > d.o) | (d.l > d.c)).sum()),
             nonpos=int((d[["o", "h", "l", "c"]] <= 0).any(axis=1).sum()),
             zero_range=int((d.h == d.l).sum()), zero_vol=int((d.v == 0).sum()),
             odd_gaps=int((gap.dropna() != 15).sum()), long_gaps=int((gap.dropna() > 120).sum()),
             dow_min=int(dow.min()), dow_max=int(dow.max()))
    if verbose:
        print(f"  BTC {r['bars']:,} bars  {r['start']} -> {r['end']}  (New York time)")
        print(f"  OHLC violations {r['ohlc_bad']}   non-positive {r['nonpos']}")
        print(f"  zero-range {r['zero_range']} ({100*r['zero_range']/r['bars']:.3f}%)   "
              f"zero-volume {r['zero_vol']}  -- these coincide: exchange outages")
        print(f"  non-15m gaps {r['odd_gaps']}, {r['long_gaps']} over two hours")
        print(f"  weekday bars {r['dow_min']:,} to {r['dow_max']:,} -- FLAT, this market is 24/7")
        ts = bars(inst, 15)["taker_share"]
        print(f"  taker-buy share  mean {np.nanmean(ts):.4f}  median {np.nanmedian(ts):.4f}")
    return r


if __name__ == "__main__":
    print("\nAUDIT"); audit()
    print("\nCLOCK"); verify_clock()
