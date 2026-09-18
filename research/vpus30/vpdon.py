"""Donchian + ATR primary on US30, with the volume profile confined to the META layer.

THE ARCHITECTURE CHANGE, AND WHY IT IS THE RIGHT ONE.
  `STUDY_VP_US30` made the volume-profile setups the PRIMARIES (HVN retracement, LVN breakout,
  POC shift, naked POC, open rejection reverse) and 0 of 10 control tests cleared. Under the
  mechanism-first architecture features belong in the META layer and may never decide direction or
  whether an opportunity exists. So here the primary is a Donchian channel break with an ATR stop --
  an object this branch has measured on US30 many times -- and all 52 profile/quant features are
  demoted to scoring events the primary already emitted.

DECLARED PRIMARY GRID (8 cells, all counted as trials):
  entry channel 20 or 55 x stop 2.0 or 3.0 ATR x side long-only or both
  exit: the opposite 20-bar channel, or the stop. NO TARGET -- 25 separate confirmations here.
  entries RTH only (the profile is a session object), exits walked on the FULL frame so a stop can
  fire overnight rather than waiting for the next session's first bar.

Everything else is inherited from `vpcore` (profiles, 22 VP features) and `vpquant` (30 quant).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit

from vpus30 import vpcore as V

RT_POINTS = V.RT_POINTS


@njit(cache=True)
def _don_walk(o, h, l, c, at, is_rth, ent_n, ex_n, sl, side_want, cost):
    """Signal on a COMPLETED RTH bar, fill at open[i+1]. Exits walk every bar, RTH or not."""
    n = len(c)
    eb = np.full(n, -1, np.int64); xb = np.full(n, -1, np.int64)
    ep = np.zeros(n); xp = np.zeros(n); rk = np.zeros(n)
    sd = np.zeros(n, np.int64); wy = np.zeros(n, np.int64); sg = np.full(n, -1, np.int64)
    cnt = 0
    last = -1
    for i in range(max(ent_n, ex_n) + 2, n - 1):
        if is_rth[i] == 0 or i <= last:
            continue
        if at[i] <= 0 or not np.isfinite(at[i]):
            continue
        hh = h[i - ent_n]; ll = l[i - ent_n]
        for q in range(i - ent_n + 1, i):
            if h[q] > hh:
                hh = h[q]
            if l[q] < ll:
                ll = l[q]
        s = 0
        if c[i] > hh:
            s = 1
        elif c[i] < ll:
            s = -1
        if s == 0:
            continue
        if side_want != 0 and s != side_want:
            continue
        j = i + 1
        ent = o[j]
        stop = ent - s * sl * at[i]
        risk = abs(ent - stop)
        if risk <= 0:
            continue
        x = -1; px = 0.0; w = 2
        for t in range(j, n):
            hs = (l[t] <= stop) if s > 0 else (h[t] >= stop)
            if hs:
                x = t; px = stop; w = 0
                break
            if t > j:
                eh = h[t - ex_n]; el = l[t - ex_n]
                for q in range(t - ex_n + 1, t):
                    if h[q] > eh:
                        eh = h[q]
                    if l[q] < el:
                        el = l[q]
                if (s > 0 and c[t] < el) or (s < 0 and c[t] > eh):
                    x = t; px = c[t]; w = 1
                    break
        if x < 0:
            x = n - 1; px = c[n - 1]; w = 2
        eb[cnt] = j; xb[cnt] = x; ep[cnt] = ent; xp[cnt] = px
        rk[cnt] = risk; sd[cnt] = s; wy[cnt] = w; sg[cnt] = i
        cnt += 1
        last = x
    return eb[:cnt], xb[:cnt], ep[:cnt], xp[:cnt], rk[:cnt], sd[:cnt], wy[:cnt], sg[:cnt]


def frame(f):
    """Full 15m frame with an RTH flag and ATR, so exits can run overnight."""
    g = f.copy()
    g["atr"] = V.atr(g, 14)
    g["is_rth"] = ((g["mod"] >= V.RTH0) & (g["mod"] < V.RTH1)).astype(np.int64)
    return g


def walk(g, ent_n=20, ex_n=20, sl=2.0, side=0, cost=RT_POINTS):
    eb, xb, ep, xp, rk, sd, wy, sg = _don_walk(
        g["open"].to_numpy(), g["high"].to_numpy(), g["low"].to_numpy(), g["close"].to_numpy(),
        g["atr"].to_numpy(), g["is_rth"].to_numpy(), int(ent_n), int(ex_n), float(sl),
        int(side), float(cost))
    t = pd.DataFrame(dict(sig=sg, e_bar=eb, x_bar=xb, ent=ep, out=xp, risk=rk, side=sd, why=wy))
    t["gross_pts"] = t.side * (t.out - t.ent)
    t["net_pts"] = t.gross_pts - cost
    t["pct"] = 100.0 * t.net_pts / t.ent
    t["gross_pct"] = 100.0 * t.gross_pts / t.ent
    t["R"] = t.net_pts / t.risk
    t["cost_frac"] = cost / t.risk
    t["hold"] = t.x_bar - t.e_bar
    t["ts"] = g.index[t.e_bar.to_numpy()]
    t["sig_ts"] = g.index[t.sig.to_numpy()]
    return t


@njit(cache=True)
def _walk_at(o, h, l, c, at, sig, side, ex_n, sl, cost):
    """Re-simulate from a GIVEN set of signal bars -- the veto/control walker. `sig` must be sorted
    (STUDY_V59: unsorted bars make the position lock reject an arbitrary share)."""
    n = len(c)
    m = len(sig)
    out = np.full(m, np.nan)
    took = np.zeros(m, np.int64)
    last = -1
    for q in range(m):
        i = sig[q]
        if i <= last or i + 1 >= n:
            continue
        if at[i] <= 0 or not np.isfinite(at[i]):
            continue
        s = side[q]
        j = i + 1
        ent = o[j]
        stop = ent - s * sl * at[i]
        risk = abs(ent - stop)
        if risk <= 0:
            continue
        x = -1; px = 0.0
        for t in range(j, n):
            hs = (l[t] <= stop) if s > 0 else (h[t] >= stop)
            if hs:
                x = t; px = stop
                break
            if t > j:
                eh = h[t - ex_n]; el = l[t - ex_n]
                for qq in range(t - ex_n + 1, t):
                    if h[qq] > eh:
                        eh = h[qq]
                    if l[qq] < el:
                        el = l[qq]
                if (s > 0 and c[t] < el) or (s < 0 and c[t] > eh):
                    x = t; px = c[t]
                    break
        if x < 0:
            x = n - 1; px = c[n - 1]
        out[q] = 100.0 * (s * (px - ent) - cost) / ent
        took[q] = 1
        last = x
    return out, took


def walk_at(g, sig, side, ex_n=20, sl=2.0, cost=RT_POINTS):
    """Re-simulated veto / control. Returns the percent-of-price series of the TAKEN trades."""
    order = np.argsort(sig)
    s_, d_ = np.asarray(sig)[order], np.asarray(side)[order]
    out, took = _walk_at(g["open"].to_numpy(), g["high"].to_numpy(), g["low"].to_numpy(),
                         g["close"].to_numpy(), g["atr"].to_numpy(),
                         s_.astype(np.int64), d_.astype(np.int64), int(ex_n), float(sl),
                         float(cost))
    k = took == 1
    return out[k], s_[k]


def pf(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return float(x[x > 0].sum() / max(-x[x < 0].sum(), 1e-12)) if len(x) >= 5 else np.nan


# ---------------------------------------------------------------------------
# Donchian / ATR feature family, read at the SIGNAL bar.
#
# Declared BEFORE any scoring. Several of these are expected to be degenerate on the trigger's
# own bars -- a breakout bar IS the N-bar extreme, so channel POSITION is forced to 1.0 the way
# `STUDY_V60` found Aroon forced to 100 and `STUDY_V62` found MACD>0 forced to ~100%. The base-rate
# check is what decides which survive into the pool; they are built anyway so the check has
# something to reject.
# ---------------------------------------------------------------------------

DON_FEATS = ["don.w20", "don.w55", "don.wr20", "don.wr55", "don.pos20", "don.pos55",
             "don.exc20", "don.exc55", "don.opp20", "don.slope55", "don.age",
             "don.atr_pct", "don.atr_r78", "don.stop_pct"]


def don_features(g, ent_n=55, ex_n=20, sl=3.0):
    """Causal channel/ATR state on the FULL frame, indexed like `g`. All values use bars < i."""
    h, l, c = g["high"].to_numpy(), g["low"].to_numpy(), g["close"].to_numpy()
    at = g["atr"].to_numpy()
    X = pd.DataFrame(index=g.index)
    hs, ls = pd.Series(h), pd.Series(l)
    for n in (20, 55):
        hh = hs.rolling(n).max().shift(1).to_numpy()
        ll = ls.rolling(n).min().shift(1).to_numpy()
        w = (hh - ll) / at
        X[f"don.w{n}"] = w
        X[f"don.wr{n}"] = w / pd.Series(w).rolling(250, min_periods=60).mean().to_numpy()
        X[f"don.pos{n}"] = np.divide(c - ll, np.where(hh - ll > 0, hh - ll, np.nan))
        X[f"don.exc{n}"] = (c - hh) / at
        if n == 20:
            X["don.opp20"] = (c - ll) / at          # distance to the EXIT channel = exit room
        else:
            X["don.slope55"] = (hh - pd.Series(hh).shift(55).to_numpy()) / at
    # bars since the last close beyond the entry channel, either side
    hh = hs.rolling(ent_n).max().shift(1).to_numpy()
    ll = ls.rolling(ent_n).min().shift(1).to_numpy()
    brk = (c > hh) | (c < ll)
    idx = np.arange(len(c))
    lastb = np.where(brk, idx, -1)
    lastb = pd.Series(lastb).replace(-1, np.nan).ffill().to_numpy()
    X["don.age"] = np.log1p(idx - np.nan_to_num(lastb, nan=0.0))
    X["don.atr_pct"] = 100.0 * at / c
    X["don.atr_r78"] = at / pd.Series(at).rolling(78).mean().to_numpy()
    X["don.stop_pct"] = 100.0 * sl * at / c
    return X
