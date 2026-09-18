"""The specified strategy: Donchian 30/20, 1.5xATR stop, 2R target, gated by a DAILY EWMAC 16/64.

THE ONE DESIGN DECISION THAT HAD TO BE MADE. The brief says the crossover is "long term 64 daily
and the short term 16 days" -- Carver's EWMAC(16,64) -- while the Donchian 30/20 and the ATR stop
are intraday constructs. Mixing them needs the daily average computed on DAILY bars and then read
by an intraday bar, and that mapping is where look-ahead lives. It is done with the same
strictly-before rule the branch already uses for daily trend states: an intraday bar sees the last
RTH session whose close timestamp is EARLIER than the bar's own, never its own day.

Both readings are produced, because they answer different questions:
  DAILY   the literal reading -- Donchian 30/20 and EWMAC(16,64) both on daily bars. Only ~740
          sessions exist here, so the trade count is small and the standard errors are large.
  INTRADAY the practical one -- the Donchian breakout on 15m/30m/60m bars with the DAILY EWMAC as
          a regime gate. More trades, and it is the shape everything else on this branch is in.

The exits are the engine's: the working stop is the NEARER of 1.5 x ATR and the 20-bar opposite
channel, capped at the previous close, and the target sits at 2R measured off that same stop
distance. Costs are the itemised MNQ stack with bar-speed slippage.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v18")
import indicators as I       # noqa: E402
import v16core as C          # noqa: E402
import warnings              # noqa: E402
import daily_trend as DT     # noqa: E402

# `known_at` carries a tz and numpy's datetime64 does not; the conversion is deliberate and the
# warning fires once per mapped series, which drowns the output.
warnings.filterwarnings("ignore", message="no explicit representation of timezones")

_CTX: dict = {}

SPEC = dict(entry_n=30, exit_n=20, atr_len=14, stop=1.5, tp_r=2.0, fast=16, slow=64)


def daily_frame():
    """One RTH bar per session, with the timestamp at which it became knowable."""
    D = DT.daily_bars()
    return D


def ewmac(c, fast, slow, vol_n=64):
    """Carver's EWMAC: the raw crossover, and the volatility-normalised version.

    The raw difference is in price units and is not comparable across regimes; dividing by the
    rolling standard deviation of price changes is what makes a single threshold mean the same
    thing in 2023 and 2025. Both are returned because the brief names the crossover, not the
    normalisation, and the normalisation is a choice that has to be shown rather than assumed.
    """
    raw = I.ema(c, fast) - I.ema(c, slow)
    sd = pd.Series(np.r_[np.nan, np.diff(c)]).rolling(vol_n).std(ddof=0).to_numpy()
    return raw, raw / np.maximum(sd * np.sqrt(vol_n), 1e-12)


def daily_ctx(fast=16, slow=64):
    D = daily_frame()
    c = D["c"].to_numpy(float)
    raw, norm = ewmac(c, fast, slow)
    return D, raw, norm


def map_to_bars(P, values, D):
    """Read a daily series on intraday bars, STRICTLY AFTER that session has closed."""
    ts = pd.to_datetime(P["b"]["ts"]).to_numpy().astype("datetime64[ns]")
    known = pd.to_datetime(D["known_at"]).to_numpy().astype("datetime64[ns]")
    pos = np.searchsorted(known, ts, side="left") - 1
    out = np.full(len(P["c"]), np.nan)
    ok = pos >= 0
    out[ok] = np.asarray(values, float)[pos[ok]]
    return out


def intraday_ctx(tf, spec=SPEC):
    key = (tf, spec["entry_n"], spec["exit_n"], spec["atr_len"], spec["fast"], spec["slow"])
    if key in _CTX:
        return _CTX[key]
    P = C.prep(tf, entry_n=spec["entry_n"], exit_n=spec["exit_n"], atr_len=spec["atr_len"])
    D, raw, norm = daily_ctx(spec["fast"], spec["slow"])
    P["ewmac"] = map_to_bars(P, raw, D)
    P["ewmac_n"] = map_to_bars(P, norm, D)
    P["D"] = D
    _CTX[key] = P
    return P


def daily_bars_as_P(spec=SPEC, broker="discount"):
    """The daily series packaged like an intraday one, so the SAME engine runs both readings."""
    import costs as CO
    D = daily_frame()
    o, h, l, c = (D[k].to_numpy(float) for k in ("o", "h", "l", "c"))
    n = len(c)
    atr = I.ema(I.true_range(h, l, c), spec["atr_len"])
    cost = CO.model("MNQ", broker)
    mod = np.full(n, 570, np.int64)          # one bar a session; minute-of-day is constant
    f_taker, f_stop = CO.friction_arrays(cost, h, l, c, mod)
    P = dict(o=o, h=h, l=l, c=c, mod=mod, atr=atr,
             sess=np.arange(n, dtype=np.int64),
             ts=pd.to_datetime(D.index).to_numpy().astype("datetime64[ns]").astype(np.int64),
             ent_hi=I.shift(I.rmax(h, spec["entry_n"]), 1),
             ent_lo=I.shift(I.rmin(l, spec["entry_n"]), 1),
             ex_lo=I.shift(I.rmin(l, spec["exit_n"]), 1),
             ex_hi=I.shift(I.rmax(h, spec["exit_n"]), 1),
             fee2=2.0 * cost.fee_points(), f_taker=f_taker, f_stop=f_stop, cost=cost)
    P["b"] = dict(v=D["v"].to_numpy(float), ts=P["ts"])
    raw, norm = ewmac(c, spec["fast"], spec["slow"])
    P["ewmac"], P["ewmac_n"] = raw, norm
    P["D"] = D
    return P


def gate(P, side, mode="on"):
    """The EWMAC filter, mirrored by side. `off` is the ungated control."""
    if mode == "off":
        return np.ones(len(P["c"]), bool)
    x = P["ewmac"]
    return np.nan_to_num(side * x, nan=-np.inf) > 0


def run(P, side=1, spec=SPEC, block=None, gate_mode="on", stop=None, tp_r=None):
    sig_all = C.signals(P, side)
    m = np.ones(len(sig_all), bool) if block is None else block[sig_all]
    m &= gate(P, side, gate_mode)[sig_all]
    sig = sig_all[m]
    O = C.outcomes(P, side, sig, stop_mult=spec["stop"] if stop is None else stop,
                   tp_r=spec["tp_r"] if tp_r is None else tp_r)
    return O, C.take(O, np.ones(len(sig), bool))


def blocks(P, frac=0.65):
    u = np.unique(P["sess"])
    cut = u[int(len(u) * frac)]
    return P["sess"] < cut, P["sess"] >= cut


def daily_R(P, O, idx, block):
    """R per trading day over EVERY day in the block, zero-filled -- Sharpe must not reward idling."""
    days = np.unique(P["sess"][block])
    s = pd.Series(0.0, index=days)
    if len(idx):
        got = pd.Series(O["R"][idx]).groupby(P["sess"][O["sig"][idx]]).sum()
        s.loc[got.index] = got.to_numpy()
    return s


def metrics(P, O, idx, block, ann=252):
    """EV, profit factor and drawdown, plus what is needed to judge them."""
    d = daily_R(P, O, idx, block)
    p = d.to_numpy()
    r = O["R"][idx] if len(idx) else np.array([])
    eq = p.cumsum()
    dd_curve = np.maximum.accumulate(eq) - eq
    dd = float(dd_curve.max()) if len(eq) else 0.0
    wins, losses = r[r > 0], r[r < 0]
    out = dict(
        n=len(idx), days=int(len(d)),
        ev=float(r.mean()) if len(r) else np.nan,               # EXPECTED VALUE per trade, in R
        ev_dollar=np.nan,
        med=float(np.median(r)) if len(r) else np.nan,
        win=float((r > 0).mean()) if len(r) else np.nan,
        avg_win=float(wins.mean()) if len(wins) else np.nan,
        avg_loss=float(losses.mean()) if len(losses) else np.nan,
        pf=float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else np.nan,
        net=float(r.sum()) if len(r) else 0.0,
        dd=dd, ret_dd=float(p.sum() / dd) if dd > 0 else np.nan,
        sharpe=float(p.mean() / p.std(ddof=1) * np.sqrt(ann)) if p.std(ddof=1) > 0 else np.nan,
        ulcer=float(np.sqrt((dd_curve ** 2).mean())) if len(eq) else np.nan,
        worst_day=float(p.min()) if len(p) else np.nan,
    )
    out["mar"] = out["net"] / out["dd"] if out["dd"] > 0 else np.nan
    if len(r):
        # EV in dollars: R is P&L over the trade's own stop distance, so a dollar EV needs the
        # stop distance in points at each signal bar and the contract's point value.
        pts = out["ev"] * float(np.nanmean(P["atr"][O["sig"][idx]])) * SPEC["stop"]
        out["ev_dollar"] = pts * P["cost"].pv
    return out
