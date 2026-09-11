"""Multi-instrument feed loader: US30, US100 (MT-style exports) and NQ (this repo's own file).

THREE INSTRUMENTS, KEPT DISTINCT. US30 and US100 come from the same broker export format --
tab-separated, `DateTime Open High Low Close Volume TickVolume`, stamped `YYYY.MM.DD HH:MM:SS`,
sorted DESCENDING, `Volume` identically zero so `TickVolume` is the only activity proxy. NQ is
this repo's futures file and its price LEVELS are synthetic (see `research/us100.py`); its
returns are usable, its levels are not. Nothing is ever pooled across instruments.

THE CLOCK IS MEASURED PER FEED, NEVER INHERITED. US100 was verified at New York + 7. That does
NOT license assuming the same for US30 even from the same broker: `derive_offset` finds the shift
that puts the 09:30 New York activity step where it belongs, computed separately for winter and
summer months, and refuses to return a constant if the two disagree (which is what a broker clock
NOT following US daylight saving would look like).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MT_FEEDS = {
    "US30":  {"1": "data/US30_1m.csv", "5": "data/US30_5m.csv"},
    "US100": {"15": "data/US100_15m.csv"},
}
# XAUUSD arrives in a DIFFERENT export format from a different source: semicolon-separated,
# `Date;Open;High;Low;Close;Volume`, stamped `YYYY.MM.DD HH:MM` with no seconds, sorted
# ASCENDING, and with no TickVolume column -- its `Volume` is the activity proxy and is a tick
# count, not exchange volume. It is parsed separately rather than being forced into the MT
# reader, because silently coercing one broker's format into another's is how a timezone or a
# column meaning gets lost.
XAU_FEEDS = {"XAUUSD": {"5": "data/XAUUSD_5m.csv"}}
# Gold's activity does not key on the 09:30 cash equity open, so the anchor is measured rather
# than inherited. Two independent checks agree on New York + 7: the summer peak in mean |5-min
# return| falls at raw 15:30, which is the 08:30 New York data release to the minute; and
# corr(US30, XAUUSD) -- US30's clock being already verified -- spikes to +0.057 at a 7-hour shift
# against roughly zero at 5, 6 and 8. The raw activity step sits at hour 15, hence anchor 15-7=8.
XAU_ANCHOR_HOUR = 8
_CACHE = {}


def _read_mt(path):
    d = pd.read_csv(path, sep="\t")
    d.columns = [c.strip() for c in d.columns]
    ts = pd.to_datetime(d["DateTime"], format="%Y.%m.%d %H:%M:%S")
    out = pd.DataFrame({"o": d["Open"].to_numpy(float), "h": d["High"].to_numpy(float),
                        "l": d["Low"].to_numpy(float), "c": d["Close"].to_numpy(float),
                        "v": d["TickVolume"].to_numpy(float)}, index=ts)
    return out[~out.index.duplicated()].sort_index()


def _read_xau(path):
    d = pd.read_csv(path, sep=";")
    d.columns = [c.strip() for c in d.columns]
    ts = pd.to_datetime(d["Date"], format="%Y.%m.%d %H:%M")
    out = pd.DataFrame({"o": d["Open"].to_numpy(float), "h": d["High"].to_numpy(float),
                        "l": d["Low"].to_numpy(float), "c": d["Close"].to_numpy(float),
                        "v": d["Volume"].to_numpy(float)}, index=ts)
    return out[~out.index.duplicated()].sort_index()


def derive_offset(raw, verbose=True, tag="", anchor=None, return_steps=False):
    """Find the hour shift that puts the activity step at the anchor hour New York, per season.

    `anchor` defaults to 9 (the 09:30 cash equity open), which is right for the index feeds. For
    an instrument that does not key on that open -- gold -- pass the hour its own activity
    actually steps at, and the caller is responsible for having measured it.

    Returns (offset_hours, ok). `ok` is False when winter and summer disagree, which means the
    feed's clock does not track US daylight saving and no constant shift is valid.
    """
    tv = raw["v"].to_numpy(float)
    hour = raw.index.hour.to_numpy()
    month = raw.index.month.to_numpy()
    steps = {}
    for name, sel in (("winter", np.isin(month, (12, 1, 2))), ("summer", np.isin(month, (6, 7, 8)))):
        by = np.array([tv[sel & (hour == h)].mean() if (sel & (hour == h)).any() else 0.0
                       for h in range(24)])
        steps[name] = (int(np.argmax(np.diff(by))) + 1) % 24
    ok = steps["winter"] == steps["summer"]
    off = (steps["winter"] - (9 if anchor is None else anchor)) % 24
    if verbose:
        print(f"  {tag} clock: activity step at raw hour {steps['winter']} (Dec-Feb) / "
              f"{steps['summer']} (Jun-Aug) -> "
              f"{'consistent' if ok else 'INCONSISTENT, no constant shift is valid'}"
              + (f"; New York = raw - {off}h" if ok else ""))
    return (off, ok, steps) if return_steps else (off, ok)


def load_xau(inst="XAUUSD", tf=5, verbose=False, anchor_hour=None):
    """XAUUSD on the New York clock.

    The equity-open anchor used for the index feeds is wrong for gold: XAUUSD trades nearly 24
    hours and its largest activity step is the COMEX/US session open, not 09:30 cash equities.
    `derive_offset` is therefore given the measured anchor rather than the equity default, and
    the resulting profile is printed so the choice is visible rather than buried.
    """
    key = ("xau", inst, str(tf))
    if key in _CACHE:
        return _CACHE[key]
    raw = _read_xau(XAU_FEEDS[inst][str(tf)])
    off, ok, steps = derive_offset(raw, verbose=verbose, tag=inst, anchor=anchor_hour,
                                   return_steps=True)
    if not ok:
        raise ValueError(f"{inst}: winter and summer disagree on the clock; a fixed shift is wrong")
    out = raw.copy()
    out.index = out.index - pd.Timedelta(hours=int(off))
    out["mod"] = out.index.hour * 60 + out.index.minute
    _CACHE[key] = out
    return out


def load_mt(inst, tf, verbose=False):
    """MT-style feed on the NEW YORK clock, oldest first."""
    key = ("mt", inst, str(tf))
    if key in _CACHE:
        return _CACHE[key]
    path = MT_FEEDS[inst][str(tf)]
    raw = _read_mt(path)
    off, ok = derive_offset(raw, verbose=verbose, tag=inst)
    if not ok:
        raise ValueError(f"{inst}: winter and summer disagree on the clock; a fixed shift is wrong")
    out = raw.copy()
    out.index = out.index - pd.Timedelta(hours=int(off))
    out["mod"] = out.index.hour * 60 + out.index.minute
    _CACHE[key] = out
    return out


def resample(df, tf):
    """Resample to `tf` minutes on New York local bucket boundaries."""
    if tf == 1:
        return df
    g = df.resample(f"{int(tf)}min", label="left", closed="left")
    out = pd.DataFrame({"o": g["o"].first(), "h": g["h"].max(), "l": g["l"].min(),
                        "c": g["c"].last(), "v": g["v"].sum()}).dropna()
    out["mod"] = out.index.hour * 60 + out.index.minute
    return out


def _ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def bars(inst, tf, atr_n=14, base=None):
    """Standard dict shape for any instrument: o/h/l/c/v/mod/atr/idx/df."""
    key = ("bars", inst, tf, atr_n)
    if key in _CACHE:
        return _CACHE[key]
    if inst == "NQ":
        from oner_union import bars as nqbars
        d = nqbars(tf)
        d["idx"] = pd.DatetimeIndex(d["df"].index)
        _CACHE[key] = d
        return d
    if inst in XAU_FEEDS:
        src = base or min(int(k) for k in XAU_FEEDS[inst])
        df = resample(load_xau(inst, src, anchor_hour=XAU_ANCHOR_HOUR), tf)
    else:
        src = base or min(int(k) for k in MT_FEEDS[inst])
        df = resample(load_mt(inst, src), tf)
    o, h, l, c = (df[k].to_numpy(float) for k in "ohlc")
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    d = dict(o=o, h=h, l=l, c=c, v=df["v"].to_numpy(float),
             mod=df["mod"].to_numpy(int), atr=_ema(tr, atr_n),
             idx=pd.DatetimeIndex(df.index), df=df)
    _CACHE[key] = d
    return d


def audit(inst, tf=None):
    """Data-quality report, printed rather than assumed."""
    if inst == "NQ":
        d = bars("NQ", tf or 5); ix = d["idx"]
        o, h, l, c = d["o"], d["h"], d["l"], d["c"]; v = d["v"]
    elif inst in XAU_FEEDS:
        src = tf or min(int(k) for k in XAU_FEEDS[inst])
        df = load_xau(inst, src, anchor_hour=XAU_ANCHOR_HOUR)
        ix = pd.DatetimeIndex(df.index)
        o, h, l, c = (df[k].to_numpy(float) for k in "ohlc"); v = df["v"].to_numpy(float)
        tf = src
    else:
        src = tf or min(int(k) for k in MT_FEEDS[inst])
        df = load_mt(inst, src); ix = pd.DatetimeIndex(df.index)
        o, h, l, c = (df[k].to_numpy(float) for k in "ohlc"); v = df["v"].to_numpy(float)
        tf = src
    gaps = np.diff(ix.view(np.int64)) // 60_000_000_000
    print(f"  {inst} {tf}m: {len(ix):,} bars  {ix[0]} -> {ix[-1]}")
    print(f"     duplicates {int(ix.duplicated().sum())}   "
          f"OHLC violations {int(((h < l) | (h < o) | (h < c) | (l > o) | (l > c)).sum())}   "
          f"non-positive {int((np.minimum.reduce([o, h, l, c]) <= 0).sum())}")
    print(f"     zero-range bars {100.0 * float((h == l).mean()):.2f}%   "
          f"off-grid gaps {100.0 * float((gaps != tf).mean()):.2f}%   "
          f"gaps > 2h {int((gaps > 120).sum())}")
    print(f"     activity proxy: {'TickVolume (broker tick count)' if inst != 'NQ' else 'exchange volume'}"
          f"   median {np.median(v):.0f}")
    return ix
