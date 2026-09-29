"""The specified strategy on every instrument on disk, with its robustness and drawdown surface.

THE SPEC, EXACTLY AS ASKED: Donchian 30 entry / 20 exit, stop 1.5 x ATR, target 2R, gated by an
EWMA crossover with a 16-day fast and a 64-day slow leg. Market order at the next open, one unit.

THE DAILY LEG IS BUILT FROM EACH INSTRUMENT'S OWN SESSIONS and read STRICTLY AFTER that session has
closed -- an intraday bar sees the last completed 09:30-16:00 New York session and never its own
day. This is the only place look-ahead can enter a mixed daily/intraday rule and it is the reason
the mapping is a function rather than a shift.

EVERY RESULT IS IN R -- P&L over the trade's own stop distance -- because points are not comparable
across an index at 44,000 and gold at 2,000, and because R is inverse-volatility sizing by
construction. Dollar EV is reported alongside for the instrument being traded.
"""
from __future__ import annotations

import sys
import warnings
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v18")
import indicators as I       # noqa: E402
import costs as CO           # noqa: E402
import v16core as C          # noqa: E402

warnings.filterwarnings("ignore", message="no explicit representation of timezones")

SPEC = dict(entry_n=30, exit_n=20, atr_len=14, stop=1.5, tp_r=2.0, fast=16, slow=64)
RTH = (570, 960)
FEEDS = {"US30": "data/US30_ISO_15m.csv", "US100": "data/US100_ISO_15m.csv",
         "US30L": "data/US30_LONG_15m.csv", "XAU": "data/XAU_ISO_15m.csv"}

# A COST IS A FRACTION OF RISK, NOT A NUMBER OF POINTS, and the two only coincide inside one
# instrument. The first version of this file charged MNQ's tick size and fee stack in EVERY market:
# on gold, whose 15-minute ATR is about 1.5 USD, a 0.25 "tick" and a 1.7-point round turn is
# 54% of a 1.5xATR stop, and it printed EV of -1.55 R and a profit factor of 0.13 -- a decisive
# failure that was entirely the cost model. This is the branch's own recorded mistake, walked into
# again, and it is why every instrument now carries its own tick, point value and spread.
#   tick   the minimum price increment of the contract, in the units of THIS feed's prices
#   pv     USD per one full point of price, for one contract
#   spread assumed half-turn cost in TICKS -- still an assumption, and the one to attack first
INSTR = {
    "US30":  dict(tick=1.0,  pv=5.0,   spread=2.0, label="YM / DJ30, 1-point tick, $5/pt"),
    "US30L": dict(tick=1.0,  pv=5.0,   spread=2.0, label="YM / DJ30, 1-point tick, $5/pt"),
    "US100": dict(tick=0.25, pv=2.0,   spread=1.0, label="MNQ, 0.25 tick, $2/pt"),
    "NQ":    dict(tick=0.25, pv=2.0,   spread=1.0, label="MNQ, 0.25 tick, $2/pt"),
    "XAU":   dict(tick=0.01, pv=100.0, spread=30.0, label="XAUUSD 100oz, 0.01 tick, $100/pt, "
                                                          "0.30 USD spread"),
}
PV = {k: v["pv"] for k, v in INSTR.items()}


def _load(path):
    d = pd.read_csv(path, parse_dates=["ny"]).set_index("ny").sort_index()
    return d[~d.index.duplicated(keep="first")]


def _nq():
    d = pd.read_csv("data/NQ_1m.csv", parse_dates=["timestamp"])
    ix = d["timestamp"].dt.tz_convert("America/New_York").dt.tz_localize(None)
    f = pd.DataFrame({"open": d["open"].to_numpy(float), "high": d["high"].to_numpy(float),
                      "low": d["low"].to_numpy(float), "close": d["close"].to_numpy(float),
                      "volume": d["volume"].to_numpy(float)}, index=ix).sort_index()
    return f.resample("15min").agg({"open": "first", "high": "max", "low": "min",
                                    "close": "last", "volume": "sum"}).dropna()


def bars(name):
    return _nq() if name == "NQ" else _load(FEEDS[name])


def daily_from_15m(df):
    """One RTH bar per session plus the timestamp at which it becomes knowable (its last bar)."""
    mod = df.index.hour * 60 + df.index.minute
    r = df[(mod >= RTH[0]) & (mod < RTH[1])]
    day = r.index.normalize()
    g = r.groupby(day)
    D = pd.DataFrame({"o": g["open"].first(), "h": g["high"].max(), "l": g["low"].min(),
                      "c": g["close"].last()})
    D["known_at"] = g.apply(lambda x: x.index[-1])
    return D


def ctx(name, spec=SPEC, tf_min=15):
    df = bars(name)
    o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    ix = df.index
    mod = (ix.hour * 60 + ix.minute).to_numpy(np.int64)
    sess = np.asarray(ix.normalize().values).astype("datetime64[ns]").astype(np.int64)
    atr = I.ema(I.true_range(h, l, c), spec["atr_len"])
    spec_i = INSTR[name]
    base = CO.model("MNQ" if spec_i["pv"] <= 2.0 else "MGC", "discount")
    cost = base.__class__(**{**base.__dict__, "symbol": name, "pv": spec_i["pv"],
                             "tick": spec_i["tick"], "spread_ticks": spec_i["spread"]})
    f_taker, f_stop = CO.friction_arrays(cost, h, l, c, mod)
    P = dict(o=o, h=h, l=l, c=c, mod=mod, sess=sess, atr=atr,
             ts=ix.to_numpy().astype("datetime64[ns]").astype(np.int64),
             ent_hi=I.shift(I.rmax(h, spec["entry_n"]), 1),
             ent_lo=I.shift(I.rmin(l, spec["entry_n"]), 1),
             ex_lo=I.shift(I.rmin(l, spec["exit_n"]), 1),
             ex_hi=I.shift(I.rmax(h, spec["exit_n"]), 1),
             fee2=2.0 * cost.fee_points(), f_taker=f_taker, f_stop=f_stop, cost=cost, name=name)
    P["b"] = dict(v=df["volume"].to_numpy(float), ts=P["ts"])
    D = daily_from_15m(df)
    dc = D["c"].to_numpy(float)
    raw = I.ema(dc, spec["fast"]) - I.ema(dc, spec["slow"])
    known = pd.to_datetime(D["known_at"]).to_numpy().astype("datetime64[ns]")
    pos = np.searchsorted(known, ix.to_numpy().astype("datetime64[ns]"), side="left") - 1
    e = np.full(len(c), np.nan)
    ok = pos >= 0
    e[ok] = raw[pos[ok]]
    P["ewmac"] = e
    P["D"] = D
    return P


def blocks(P, frac=0.65):
    u = np.unique(P["sess"])
    cut = u[int(len(u) * frac)]
    return P["sess"] < cut, P["sess"] >= cut


def run(P, side=1, block=None, gate=True, stop=None, tp_r=None, entry_n=None, exit_n=None):
    """Re-preps only when the channel lengths move; everything else is an argument."""
    if entry_n is not None or exit_n is not None:
        h, l = P["h"], P["l"]
        en = entry_n or SPEC["entry_n"]
        xn = exit_n or SPEC["exit_n"]
        Q = dict(P)
        Q["ent_hi"] = I.shift(I.rmax(h, en), 1)
        Q["ent_lo"] = I.shift(I.rmin(l, en), 1)
        Q["ex_lo"] = I.shift(I.rmin(l, xn), 1)
        Q["ex_hi"] = I.shift(I.rmax(h, xn), 1)
        P = Q
    sig_all = C.signals(P, side)
    m = np.ones(len(sig_all), bool) if block is None else block[sig_all]
    if gate:
        m &= np.nan_to_num(side * P["ewmac"][sig_all], nan=-np.inf) > 0
    sig = sig_all[m]
    O = C.outcomes(P, side, sig, stop_mult=SPEC["stop"] if stop is None else stop,
                   tp_r=SPEC["tp_r"] if tp_r is None else tp_r)
    return O, C.take(O, np.ones(len(sig), bool))


def daily_R(P, O, idx, block):
    days = np.unique(P["sess"][block])
    s = pd.Series(0.0, index=days)
    if len(idx):
        got = pd.Series(O["R"][idx]).groupby(P["sess"][O["sig"][idx]]).sum()
        s.loc[got.index] = got.to_numpy()
    return s


def metrics(P, O, idx, block):
    d = daily_R(P, O, idx, block)
    p = d.to_numpy()
    r = O["R"][idx] if len(idx) else np.array([])
    eq = p.cumsum()
    ddc = np.maximum.accumulate(eq) - eq if len(eq) else np.array([0.0])
    dd = float(ddc.max())
    w, lo = r[r > 0], r[r < 0]
    m = dict(n=len(idx), days=len(d),
             ev=float(r.mean()) if len(r) else np.nan,
             win=float((r > 0).mean()) if len(r) else np.nan,
             avg_w=float(w.mean()) if len(w) else np.nan,
             avg_l=float(lo.mean()) if len(lo) else np.nan,
             pf=float(w.sum() / abs(lo.sum())) if len(lo) and lo.sum() != 0 else np.nan,
             net=float(r.sum()) if len(r) else 0.0, dd=dd,
             mar=float(p.sum() / dd) if dd > 0 else np.nan,
             sharpe=float(p.mean() / p.std(ddof=1) * np.sqrt(252)) if p.std(ddof=1) > 0 else np.nan,
             ulcer=float(np.sqrt((ddc ** 2).mean())),
             worst=float(p.min()) if len(p) else np.nan)
    if len(r):
        pts = m["ev"] * float(np.nanmean(P["atr"][O["sig"][idx]])) * SPEC["stop"]
        m["ev_pts"] = pts
        m["ev_usd"] = pts * PV.get(P["name"], 2.0)
    else:
        m["ev_pts"] = m["ev_usd"] = np.nan
    return m
