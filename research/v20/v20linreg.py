"""Donchian 30/20 + 2.0xATR stop + 2R target, confirmed by a 50-period linear regression.

THE SPEC, EXACTLY AS BRIEFED. Entry on a 30-bar Donchian break, exit channel 20, stop 2.0 x ATR,
target 2R, intraday, with a linear regression of length 50 as an entry CONFIRMATION: the breakout is
only taken when the regression is forecasting the move.

THE ONE PLACE THE BRIEF LEAVES A CHOICE, AND HOW IT IS HANDLED. "The regression is forecasting the
move" has four mechanical readings and picking whichever backtests best is exactly how a spec turns
into an overfit. All four are declared here in advance, all four are run, and the count is carried
into the multiplicity:

  A  slope > 0                 the fitted line is rising
  B  forecast > close          the line extrapolated one bar ahead sits above the current price
  C  close > value             price is above the fitted line
  D  slope > 0 AND close > value

Each is mirrored for the short side, so no degree of freedom is spent on direction.

WHAT IS ALREADY KNOWN AND IS NOT RE-LITIGATED. STUDY_V18 measured the same geometry on five markets
across 3,125 cells: the ATR stop axis is monotone toward WIDER on every market and the specified
2.0N sits below the middle, and no take profit beat every take profit for the sixth time, with 2R
mid-table. The prior going in is therefore that this geometry loses and the regression cannot save
it. The point of running it is to find out whether the regression adds anything ON TOP of a geometry
that is known to be weak -- which is a cleaner question than it looks, because a confirmation filter
that genuinely carries information should show up as a positive drop-one contribution whether or not
the base is profitable.
"""
from __future__ import annotations

import sys
import warnings
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v18")
sys.path.insert(0, "research/v19")
import indicators as I       # noqa: E402
import costs as CO           # noqa: E402
import v16core as C          # noqa: E402
import v18multi as V18       # noqa: E402

warnings.filterwarnings("ignore", message="no explicit representation of timezones")

SPEC = dict(entry_n=30, exit_n=20, atr_len=14, stop=2.0, tp_r=2.0, lr_len=50)
MARKETS = ["US30", "US100", "NQ", "US30L", "XAU"]
READINGS = ("A slope>0", "B forecast>close", "C close>value", "D slope>0 and close>value")
_CX: dict = {}


def linreg(c, n):
    """Rolling OLS of price on bar index. Returns (value at the last bar, slope per bar, R^2).

    Closed form on a centred x, so it is one pass of rolling sums rather than n regressions:
      slope = sum(x_i * (y_i - ybar)) / sum(x_i^2)   with x centred on the window
      value = ybar + slope * x_last
    This is what `ta.linreg(close, n, 0)` computes, and the forecast one bar ahead is value + slope.
    """
    s = pd.Series(np.asarray(c, float))
    x = np.arange(n, dtype=float)
    x -= x.mean()
    sxx = float((x * x).sum())
    ybar = s.rolling(n).mean().to_numpy()
    # sum(x_i * y_i) over each window, via a dot with a fixed kernel
    sxy = s.rolling(n).apply(lambda w: float(np.dot(x, w)), raw=True).to_numpy()
    slope = sxy / sxx
    value = ybar + slope * x[-1]
    # R^2 = (slope^2 * sxx) / sum((y-ybar)^2)
    syy = (s.rolling(n).var(ddof=0).to_numpy()) * n
    with np.errstate(divide="ignore", invalid="ignore"):
        r2 = np.where(syy > 0, (slope ** 2) * sxx / syy, np.nan)
    return value, slope, r2


def ctx(name, tf_min=15, spec=SPEC):
    key = (name, tf_min, spec["entry_n"], spec["exit_n"], spec["atr_len"], spec["lr_len"])
    if key in _CX:
        return _CX[key]
    df = V18.bars(name)
    if tf_min != 15:
        df = df.resample(f"{tf_min}min").agg({"open": "first", "high": "max", "low": "min",
                                              "close": "last", "volume": "sum"}).dropna()
    o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    ix = df.index
    mod = (ix.hour * 60 + ix.minute).to_numpy(np.int64)
    inst = V18.INSTR[name]
    base = CO.model("MNQ" if inst["pv"] <= 2.0 else "MGC", "discount")
    cost = base.__class__(**{**base.__dict__, "symbol": name, "pv": inst["pv"],
                             "tick": inst["tick"], "spread_ticks": inst["spread"]})
    f_taker, f_stop = CO.friction_arrays(cost, h, l, c, mod)
    val, slp, r2 = linreg(c, spec["lr_len"])
    P = dict(o=o, h=h, l=l, c=c, mod=mod, name=name,
             sess=np.asarray(ix.normalize().values).astype("datetime64[ns]").astype(np.int64),
             ts=ix.to_numpy().astype("datetime64[ns]"),
             atr=I.ema(I.true_range(h, l, c), spec["atr_len"]),
             ent_hi=I.shift(I.rmax(h, spec["entry_n"]), 1),
             ent_lo=I.shift(I.rmin(l, spec["entry_n"]), 1),
             ex_lo=I.shift(I.rmin(l, spec["exit_n"]), 1),
             ex_hi=I.shift(I.rmax(h, spec["exit_n"]), 1),
             lr_val=val, lr_slope=slp, lr_r2=r2,
             fee2=2.0 * cost.fee_points(), f_taker=f_taker, f_stop=f_stop, cost=cost)
    P["b"] = dict(v=df["volume"].to_numpy(float), ts=P["ts"].astype(np.int64))
    _CX[key] = P
    return P


def confirm(P, reading, side):
    """The four declared readings, each mirrored by side. NaN reads as FALSE."""
    v, s, c = P["lr_val"], P["lr_slope"], P["c"]
    fc = v + s                                    # one bar ahead
    if reading is None:
        return np.ones(len(c), bool)
    k = reading[0]
    if k == "A":
        m = side * s > 0
    elif k == "B":
        m = side * (fc - c) > 0
    elif k == "C":
        m = side * (c - v) > 0
    else:
        m = (side * s > 0) & (side * (c - v) > 0)
    return np.nan_to_num(m.astype(float), nan=0).astype(bool)


def run(P, side=1, reading=None, block=None, spec=SPEC, stop=None, tp_r=None, cost_mult=1.0):
    Q = P
    if cost_mult != 1.0:
        Q = dict(P)
        Q["fee2"] = P["fee2"] * cost_mult
        Q["f_taker"] = P["f_taker"] * cost_mult
        Q["f_stop"] = P["f_stop"] * cost_mult
    sig_all = C.signals(Q, side)
    m = np.ones(len(sig_all), bool) if block is None else block[sig_all]
    m &= confirm(Q, reading, side)[sig_all]
    sig = sig_all[m]
    O = C.outcomes(Q, side, sig, stop_mult=spec["stop"] if stop is None else stop,
                   tp_r=spec["tp_r"] if tp_r is None else tp_r)
    return O, C.take(O, np.ones(len(sig), bool))


def daily_R(P, O, idx, block):
    days = np.unique(P["sess"][block])
    s = pd.Series(0.0, index=days)
    if len(idx):
        g = pd.Series(O["R"][idx]).groupby(P["sess"][O["sig"][idx]]).sum()
        s.loc[g.index] = g.to_numpy()
    return s


def metrics(P, O, idx, block):
    d = daily_R(P, O, idx, block)
    p = d.to_numpy()
    r = O["R"][idx] if len(idx) else np.array([])
    eq = p.cumsum()
    ddc = np.maximum.accumulate(eq) - eq if len(eq) else np.array([0.0])
    dd = float(ddc.max())
    w, lo = r[r > 0], r[r < 0]
    dn = p[p < 0]
    sd = p.std(ddof=1) if len(p) > 1 else 0.0
    dsd = np.sqrt((dn ** 2).mean()) if len(dn) else 0.0
    return dict(n=len(idx), days=len(d),
                ev=float(r.mean()) if len(r) else np.nan,
                pf=float(w.sum() / abs(lo.sum())) if len(lo) and lo.sum() != 0 else np.nan,
                win=float((r > 0).mean()) if len(r) else np.nan,
                net=float(r.sum()) if len(r) else 0.0, dd=dd,
                mar=float(p.sum() / dd) if dd > 0 else np.nan,
                sharpe=float(p.mean() / sd * np.sqrt(252)) if sd > 0 else np.nan,
                sortino=float(p.mean() / dsd * np.sqrt(252)) if dsd > 0 else np.nan)


def blocks(P, frac=0.65):
    u = np.unique(P["sess"])
    return P["sess"] < u[int(len(u) * frac)], P["sess"] >= u[int(len(u) * frac)]
