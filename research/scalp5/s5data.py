"""NQ intraday 07:00-11:00 New York -- data, clock, costs, and the arithmetic that bounds the ask.

WHY NQ AND NOT GOLD. The request is for the highest EV and Sharpe available to an intraday scalp,
and on this branch the binding constraint on every scalp has been the ROUND TURN AS A FRACTION OF
RISK, never the signal. Measured: on 15-minute gold the round turn is ~17% of a 1xATR barrier and
~31% at the 07:00 ATR, against 6% for MNQ at a 1xATR stop on 5-minute bars. That factor of three
to five is larger than any edge this branch has ever measured, so the honest place to look for a
scalp is the instrument with the cheapest risk unit -- and NQ_1m is also the only feed here with
MINUTE bars, which a barrier system needs before its numbers mean anything.

THE CLOCK IS A REAL CONVERSION, NOT A SHIFT. `NQ_1m` is stamped in UTC with a `Z` suffix while
every other feed on this branch is already New York, so a fixed offset is wrong in one season:
-4h puts the range peak at 09:31 and -5h at 08:31, which is EDT and EST. Converted properly the
peak lands at 09:30 New York year round. A loader that forgets this puts a 07:00 window at 02:00
or 03:00.

THE BREAK-EVEN THE GEOMETRY IMPLIES, computed before any rule is written. At a 1:1 payoff a system
needs w* = (S + C) / (T + S) where C is the round turn, so the tighter the stop the larger the
fixed cost looms. That table is printed by `breakeven_table` and it is the first thing to read:
it says which geometries are arithmetically alive on this instrument and which are dead before
a signal is chosen.
"""
import numpy as np, pandas as pd

NY = "America/New_York"
NQ_1M = "data/NQ_1m.csv"
# MNQ: $2 a point. The branch's measured all-in round turn is $3.44 = 1.72 points, which is
# broker commission + CME + NFA + slippage, not the COMM=1.00 broker-only figure that made every
# early result on this branch read ~44% light.
POINT_VALUE = 2.0
RT_POINTS = 1.72
SLIP_POINTS = 0.25          # per side, charged inside the walk on top of the round turn
WIN_OPEN, WIN_CLOSE = 420, 660      # 07:00 and 11:00 New York, in minutes past NY midnight
SPLIT = 0.65


def load_1m(path=NQ_1M):
    d = pd.read_csv(path)
    ix = pd.to_datetime(d["timestamp"], utc=True).dt.tz_convert(NY).dt.tz_localize(None)
    f = pd.DataFrame({k: d[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume")},
                     index=ix)
    return f[~f.index.duplicated(keep="first")].sort_index()


def resample(f, minutes):
    if minutes == 1:
        return f
    r = f.resample(f"{minutes}min", label="left", closed="left").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum"))
    return r.dropna(subset=["open"])


def assemble(f, tf_min, win_open=WIN_OPEN, win_close=WIN_CLOSE, split=SPLIT, atr_len=14):
    o, h, l, c, v = (f[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    ix = f.index
    mod = (ix.hour * 60 + ix.minute).to_numpy(np.int64)
    day = ix.normalize().values.astype("datetime64[D]").astype(np.int64)
    wd = ix.dayofweek.to_numpy()
    inw = (mod >= win_open) & (mod < win_close) & (wd < 5)
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    tr[0] = h[0] - l[0]
    atr = pd.Series(tr).ewm(alpha=1 / atr_len, adjust=False).mean().to_numpy()
    D = dict(o=o, h=h, l=l, c=c, v=v, ix=ix, mod=mod, day=day, wd=wd, inw=inw, atr=atr, tr=tr,
             n=len(c), tf=tf_min, win_open=win_open, win_close=win_close)
    us = np.unique(day[inw])
    D["cut_day"] = int(us[int(split * len(us))])
    D["blk"] = (day >= D["cut_day"]).astype(np.int64)
    D["cut_date"] = str(pd.Timestamp(D["cut_day"], unit="D").date())
    D["n_sessions"] = len(us)
    D["all_days"] = us
    lastw = np.zeros(len(c), bool)
    idx = np.flatnonzero(inw)
    if len(idx):
        dd = day[idx]
        lastw[idx[np.flatnonzero(np.diff(dd, append=dd[-1] + 1) != 0)]] = True
    D["last_win"] = lastw
    return D


def breakeven_table(D, stops=(0.5, 0.75, 1.0, 1.5, 2.0, 3.0), rr=(1.0, 1.5, 2.0)):
    """w* = (S + C) / (T + S) at each stop distance, with C the all-in round turn in points."""
    a = np.nanmedian(D["atr"][D["inw"]])
    rows = []
    for s in stops:
        S = s * a
        for r in rr:
            T = r * S
            rows.append(dict(stop_atr=s, rr=r, stop_pts=S, cost_frac_of_risk=RT_POINTS / S,
                             breakeven_win=(S + RT_POINTS) / (T + S),
                             driftless_bound=1.0 / (1.0 + r)))
    t = pd.DataFrame(rows)
    t["cost_penalty_pts"] = t.breakeven_win - t.driftless_bound
    return t, float(a)


def day_sharpe(trade_days, trade_r, all_days):
    """Sharpe over EVERY trading day in the block, ZERO-FILLED on days that did not trade.

    Over traded days only a selective rule is PAID for trading less: keep twelve days a year and
    the ratio explodes while the account earns nothing. This is the choice that makes a
    selectivity search honest (CLAUDE.md), and it is why a 3-trades-a-month design cannot win
    this comparison by being quiet."""
    s = pd.Series(trade_r).groupby(pd.Series(trade_days)).sum()
    full = pd.Series(0.0, index=pd.Index(all_days, name="day"))
    full.loc[s.index] = s.to_numpy()
    sd = full.std(ddof=1)
    return float(full.mean() / sd * np.sqrt(252)) if sd > 0 else np.nan, full
