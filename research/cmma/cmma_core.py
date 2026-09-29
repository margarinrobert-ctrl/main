"""The CMMA mean-reversion strategy from the uploaded notebook, implemented honestly.

THE STRATEGY AS BRIEFED. Daily bars: `cmma = (close - SMA(close, 5)) / ATR(5)`, bounded with
`tanh`, NEGATED so it is contrarian, scaled by a 21-day Kaufman Efficiency Ratio, smoothed with
`ewm(2)` and shifted one day. The daily target is then carried into the next session and MNQ is
exposed only 08:00-15:45 New York.

FOUR THINGS THE NOTEBOOK DOES THAT THIS MODULE DOES DIFFERENTLY, each measured rather than argued:

  1. `sr = eq.mean() / eq.std()` WHERE `eq` IS A CUMSUM. That is the mean of an equity CURVE over
     its own standard deviation, not a Sharpe ratio -- it is large whenever the curve trends and
     has no sampling interpretation at all. Sharpe here is computed on the daily RETURN series,
     annualised, with a standard error attached.
  2. `pnl = signal * (close - open)` SUMMED OVER INTRADAY BARS discards every gap between bars.
     Within a session those gaps are small, but the quantity a trader actually receives for
     holding 08:00 to 15:45 is `close[15:45] - open[08:00]`. Both are computed and compared.
  3. NO COSTS ANYWHERE. The position changes every day, so the cost is one round turn per day
     scaled by the change in target. MNQ's real round turn is $1.44 (`research/costs.py`).
  4. NO HOLDOUT. Cells 20-32 sweep MA type x length and then read a decile plot and add a
     threshold filter, all on the full sample. The last 30% is locked here before anything is
     computed.

`tanh` and `ker` both bound the signal, so the position is a CONTINUOUS target in [-1, 1] rather
than a discrete trade. Everything is therefore reported per-day on a one-contract-at-full-signal
basis, which is what makes the cost model well defined.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", ".."))

SKILL = ("/root/.claude/skills/synced/"
         "a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/"
         "quant-strategy-lab/scripts")
if os.path.isdir(SKILL):
    sys.path.insert(0, SKILL)

# MNQ contract: $2 a point, $1.44 round turn all-in (broker + exchange + NFA), one tick of
# slippage per side on a market order at 0.25 points = $0.50.
PV = 2.0
ROUND_TURN_USD = 1.44
SLIP_TICKS_PER_SIDE = 1.0
TICK = 0.25
COST_PER_ROUND_TURN_PTS = (ROUND_TURN_USD / PV) + 2 * SLIP_TICKS_PER_SIDE * TICK

SESSION = ("08:00", "15:45")
SPLIT = 0.70                       # the last 30% is the holdout and is not looked at until the end


def load_intraday(market="NQ"):
    """Intraday bars on a NEW YORK clock. NQ_1m is stamped in UTC and every other feed here is
    already New York -- the registry states it, and getting it wrong puts the session at 04:30."""
    if market == "NQ":
        d = pd.read_csv("data/NQ_1m.csv")
        tc = [c for c in d.columns if "time" in c.lower() or "date" in c.lower()][0]
        ix = (pd.DatetimeIndex(pd.to_datetime(d[tc], utc=True))
              .tz_convert("America/New_York").tz_localize(None))
        f = pd.DataFrame({k: d[[c for c in d.columns
                                if c.lower().startswith(k)][0]].to_numpy(float)
                          for k in ("open", "high", "low", "close")}, index=ix)
    else:
        d = pd.read_csv("data/US100_LONG_15m.csv", sep="\t")
        d.columns = [c.strip().lower() for c in d.columns]
        tc = [c for c in d.columns if "date" in c or "time" in c][0]
        ix = pd.DatetimeIndex(pd.to_datetime(d[tc])) - pd.Timedelta(hours=7)   # NY+7 in the file
        f = pd.DataFrame({k: d[k].to_numpy(float) for k in ("open", "high", "low", "close")},
                         index=ix)
    f = f.sort_index()
    return f[~f.index.duplicated(keep="first")]


def daily_from_intraday(f):
    """Daily OHLC. The notebook resamples with label='right', closed='right', which labels the bar
    for calendar day D at D+1 00:00. That convention is kept so the signal timing matches, and the
    mapping back to a trading date is done explicitly below rather than by index arithmetic."""
    return f.resample("1D", label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna(how="all")


def atr_wilder(d, n=5):
    pc = d["close"].shift(1)
    tr = pd.concat([d["high"] - d["low"], (d["high"] - pc).abs(),
                    (d["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()


def signal(d, ma="sma", length=5, atr_len=None, ker_len=21, smooth=2, use_tanh=True,
           use_ker=True):
    """The daily target, exactly as briefed. Returns a series indexed by TRADING DATE.

    `ewm(2)` in the notebook is `com=2` (alpha 1/3), not `span=2` -- pandas' first positional
    argument is `com`. That is kept, because it is what was run.
    """
    c = d["close"].ffill()
    m = c.rolling(length).mean() if ma == "sma" else c.ewm(length, adjust=False).mean()
    a = atr_wilder(d, atr_len or length)
    cmma = (c - m) / a.ffill()
    raw = np.tanh(cmma) if use_tanh else cmma
    s = -raw
    if use_ker:
        ker = c.diff(ker_len).abs() / c.diff().abs().rolling(ker_len).sum()
        s = ker * s
    if smooth:
        s = s.ewm(smooth, adjust=False).mean()
    s = s.shift(1)
    # a bar labelled D+1 00:00 holds calendar day D's data; after shift(1) the value at label L
    # was computed from data through the end of calendar day L-2, and is traded on date L-1.
    s.index = (s.index - pd.Timedelta(days=1)).date
    return s.dropna()


def session_pnl(f, sig, session=SESSION, mode="endpoints"):
    """Points per day from holding `sig` contracts through the session.

    mode="endpoints"  close(session end) - open(session start). What a trader receives.
    mode="barbodies"  sum of (close - open) over the session's bars, which is the notebook's
                      quantity. It silently drops every gap between bars.
    """
    w = f.between_time(session[0], session[1])
    g = w.groupby(w.index.date)
    if mode == "endpoints":
        move = g["close"].last() - g["open"].first()
    else:
        move = (w["close"] - w["open"]).groupby(w.index.date).sum()
    move = move[move.index.isin(sig.index)]
    s = sig.reindex(move.index)
    out = pd.DataFrame({"sig": s, "move": move})
    out["gross"] = out["sig"] * out["move"]
    out["turn"] = out["sig"].diff().abs().fillna(out["sig"].abs())
    out["cost"] = out["turn"] * COST_PER_ROUND_TURN_PTS
    out["net"] = out["gross"] - out["cost"]
    out.index = pd.DatetimeIndex(out.index)
    return out.dropna()


def split_at(idx, frac=SPLIT):
    k = int(len(idx) * frac)
    return idx[k]
