"""Can a 07:00-11:00 scalp hold PF 1.50? The arithmetic first, then the best cell on record.

WHAT IS FROZEN, AND WHERE IT CAME FROM. The geometry is NOT chosen here -- it is the cell
`STUDY_BAYESOPT_SCALP` selected from 3,600 Optuna trials on the research block alone, and the only
one of its three objectives that cleared a random entry inside the window on BOTH blocks:

    NQ 15-minute, entries 07:00-11:00 New York, Donchian 10/10, stop 3.19 x ATR(14),
    target 2.3 x ATR(14), 230-minute hold cap, no filters.

Re-running someone else's chosen cell is not a search, so nothing here is a new trial. The point is
to measure what it actually does and put that beside what PF 1.50 would require.

THE ARITHMETIC. For a stop/target system with target = R x stop and cost c expressed in units of
risk, a win pays (R - c) and a loss costs (1 + c), so

    PF = w(R - c) / ((1 - w)(1 + c))      =>      w* = P(1 + c) / (R - c + P(1 + c))

That is the win rate the geometry demands to reach profit factor P. It is arithmetic, not a
backtest, and no indicator changes it.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from breaker import bbcore as BB  # noqa: E402  (NQ_1m loader, already audited this session)

RT_POINTS = 1.72
WIN0, WIN1 = 7 * 60, 11 * 60          # 07:00-11:00 New York, entries only


def bars(tf=15):
    f = BB.load()
    o = f.resample(f"{tf}min").agg({"open": "first", "high": "max", "low": "min",
                                    "close": "last", "volume": "sum"}).dropna()
    return o


def atr(f, n=14):
    h, lo, c = f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy()
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - lo, np.maximum(np.abs(h - pc), np.abs(lo - pc)))
    return pd.Series(tr).ewm(span=n, adjust=False).mean().to_numpy()


def req_win(P, R, c):
    """Win rate required for profit factor P at reward:risk R with cost c in units of risk."""
    return P * (1 + c) / (R - c + P * (1 + c))


@njit(cache=True)
def _walk(o, h, l, c, a, mod, ent_n, ex_n, sl, tp, cap, cost, w0, w1, side_want):
    n = len(c)
    eb = np.full(n, -1, np.int64); xb = np.full(n, -1, np.int64)
    ep = np.zeros(n); xp = np.zeros(n); rk = np.zeros(n)
    sd = np.zeros(n, np.int64); wy = np.zeros(n, np.int64); am = np.zeros(n, np.int64)
    cnt = 0
    last = -1
    for i in range(max(ent_n, ex_n) + 2, n - 1):
        if mod[i] < w0 or mod[i] >= w1:
            continue
        if i <= last:
            continue
        hh = h[i - ent_n]
        ll = l[i - ent_n]
        for q in range(i - ent_n + 1, i):
            if h[q] > hh:
                hh = h[q]
            if l[q] < ll:
                ll = l[q]
        s = 0
        if c[i] > hh and side_want >= 0:
            s = 1
        elif c[i] < ll and side_want <= 0:
            s = -1
        if s == 0:
            continue
        if a[i] <= 0:
            continue
        j = i + 1                      # fill at the NEXT bar's open, never same-bar
        ent = o[j]
        stop = ent - s * sl * a[i]
        tgt = ent + s * tp * a[i] if tp > 0 else 0.0
        risk = abs(ent - stop)
        if risk <= 0:
            continue
        lim = j + cap
        if lim > n - 1:
            lim = n - 1
        x = -1; px = 0.0; w = 3
        for t in range(j, lim + 1):
            hs = (l[t] <= stop) if s > 0 else (h[t] >= stop)
            ht = False
            if tp > 0:
                ht = (h[t] >= tgt) if s > 0 else (l[t] <= tgt)
            if hs and ht:
                am[cnt] = 1
            if hs:
                x = t; px = stop; w = 0
                break
            if ht:
                x = t; px = tgt; w = 1
                break
            if t > j:                  # Donchian channel exit
                eh = h[t - ex_n]; el = l[t - ex_n]
                for q in range(t - ex_n + 1, t):
                    if h[q] > eh:
                        eh = h[q]
                    if l[q] < el:
                        el = l[q]
                if (s > 0 and c[t] < el) or (s < 0 and c[t] > eh):
                    x = t; px = c[t]; w = 2
                    break
        if x < 0:
            x = lim; px = c[lim]; w = 3
        eb[cnt] = j; xb[cnt] = x; ep[cnt] = ent; xp[cnt] = px
        rk[cnt] = risk; sd[cnt] = s; wy[cnt] = w
        cnt += 1
        last = x
    return eb[:cnt], xb[:cnt], ep[:cnt], xp[:cnt], rk[:cnt], sd[:cnt], wy[:cnt], am[:cnt]


def run(f, a, ent_n=10, ex_n=10, sl=3.19, tp=2.3, cap=None, cost=RT_POINTS, side=0, tf=15):
    cap = int(230 / tf) if cap is None else cap
    mod = (f.index.hour * 60 + f.index.minute).to_numpy()
    eb, xb, ep, xp, rk, sd, wy, am = _walk(
        f["open"].to_numpy(), f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy(),
        a, mod, int(ent_n), int(ex_n), float(sl), float(tp), int(cap), float(cost),
        int(WIN0), int(WIN1), int(side))
    t = pd.DataFrame(dict(e_bar=eb, x_bar=xb, ent=ep, out=xp, risk=rk, side=sd, why=wy, amb=am))
    t["gross_pts"] = t.side * (t.out - t.ent)
    t["net_pts"] = t.gross_pts - cost
    t["pct"] = 100.0 * t.net_pts / t.ent
    t["gross_pct"] = 100.0 * t.gross_pts / t.ent
    t["R"] = t.net_pts / t.risk
    t["cost_frac"] = cost / t.risk
    t["ts"] = f.index[t.e_bar.to_numpy()]
    return t


def pf(t, col="pct"):
    x = t[col].to_numpy()
    if len(x) < 5:
        return np.nan
    return float(x[x > 0].sum() / max(-x[x < 0].sum(), 1e-12))


# ---------------------------------------------------------------------------------------------
# A wider, PRE-DECLARED search. The grid below is fixed here before any cell is scored, and every
# cell is reported -- the population share, not the top row, is what answers "can PF 1.50 hold".
#
# TWO trigger families, because a breakout is only half the hypothesis space and this branch has
# reached a mean-reversion conclusion by twelve independent routes:
#   DON   Donchian channel breakout, close beyond the n-bar extreme
#   CMMA  close minus its own SMA(n), in ATR units, entered AGAINST the move at -z / +z
# ---------------------------------------------------------------------------------------------

GRID = dict(
    tf=(5, 15, 30),
    side=(1, -1, 0),                                   # long only, short only, both
    stop=(1.5, 2.5, 4.0),
    tgt=(0.0, 1.5, 3.0, 6.0),                          # 0.0 = no target
    don=((5, 10), (10, 20), (20, 20), (40, 20)),       # (entry channel, exit channel)
    cmma=((20, 1.0), (20, 1.5), (50, 1.5), (50, 2.0), (100, 2.0)),
)


def sig_donchian(f, ent_n, ex_n):
    """+1 on a close above the prior ent_n-bar high, -1 below the prior low. Prior bars only."""
    h = pd.Series(f["high"]).rolling(ent_n).max().shift(1).to_numpy()
    l = pd.Series(f["low"]).rolling(ent_n).min().shift(1).to_numpy()
    c = f["close"].to_numpy()
    s = np.zeros(len(c), np.int64)
    s[c > h] = 1
    s[c < l] = -1
    return s


def sig_cmma(f, a, n, z):
    """MEAN REVERSION: buy when the close sits z ATRs BELOW its own SMA(n), sell when above."""
    c = f["close"].to_numpy()
    ma = pd.Series(c).rolling(n).mean().shift(1).to_numpy()
    d = np.divide(c - ma, np.where(a > 0, a, np.nan))
    s = np.zeros(len(c), np.int64)
    s[d <= -z] = 1
    s[d >= z] = -1
    return s


@njit(cache=True)
def _walk_sig(o, h, l, c, a, mod, sig, ex_n, sl, tp, cap, w0, w1, side_want):
    """Signal on the COMPLETED bar i, fill at open[i+1]. One live position."""
    n = len(c)
    eb = np.full(n, -1, np.int64); xb = np.full(n, -1, np.int64)
    ep = np.zeros(n); xp = np.zeros(n); rk = np.zeros(n)
    sd = np.zeros(n, np.int64); wy = np.zeros(n, np.int64); am = np.zeros(n, np.int64)
    cnt = 0
    last = -1
    for i in range(ex_n + 2, n - 1):
        if mod[i] < w0 or mod[i] >= w1:
            continue
        if i <= last:
            continue
        s = sig[i]
        if s == 0:
            continue
        if side_want != 0 and s != side_want:
            continue
        if a[i] <= 0 or not np.isfinite(a[i]):
            continue
        j = i + 1
        ent = o[j]
        stop = ent - s * sl * a[i]
        tgt = ent + s * tp * a[i] if tp > 0 else 0.0
        risk = abs(ent - stop)
        if risk <= 0:
            continue
        lim = j + cap
        if lim > n - 1:
            lim = n - 1
        x = -1; px = 0.0; w = 3
        for t in range(j, lim + 1):
            hs = (l[t] <= stop) if s > 0 else (h[t] >= stop)
            ht = False
            if tp > 0:
                ht = (h[t] >= tgt) if s > 0 else (l[t] <= tgt)
            if hs and ht:
                am[cnt] = 1
            if hs:
                x = t; px = stop; w = 0
                break
            if ht:
                x = t; px = tgt; w = 1
                break
            if t > j and ex_n > 0:
                eh = h[t - ex_n]; el = l[t - ex_n]
                for q in range(t - ex_n + 1, t):
                    if h[q] > eh:
                        eh = h[q]
                    if l[q] < el:
                        el = l[q]
                if (s > 0 and c[t] < el) or (s < 0 and c[t] > eh):
                    x = t; px = c[t]; w = 2
                    break
        if x < 0:
            x = lim; px = c[lim]; w = 3
        eb[cnt] = j; xb[cnt] = x; ep[cnt] = ent; xp[cnt] = px
        rk[cnt] = risk; sd[cnt] = s; wy[cnt] = w
        cnt += 1
        last = x
    return eb[:cnt], xb[:cnt], ep[:cnt], xp[:cnt], rk[:cnt], sd[:cnt], wy[:cnt], am[:cnt]


def run_sig(f, a, sig, ex_n, sl, tp, cap_min, side=0, cost=RT_POINTS, tf=15):
    mod = (f.index.hour * 60 + f.index.minute).to_numpy()
    eb, xb, ep, xp, rk, sd, wy, am = _walk_sig(
        f["open"].to_numpy(), f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy(),
        a, mod, sig, int(ex_n), float(sl), float(tp), int(cap_min / tf),
        int(WIN0), int(WIN1), int(side))
    t = pd.DataFrame(dict(e_bar=eb, x_bar=xb, ent=ep, out=xp, risk=rk, side=sd, why=wy, amb=am))
    t["gross_pts"] = t.side * (t.out - t.ent)
    t["net_pts"] = t.gross_pts - cost
    t["pct"] = 100.0 * t.net_pts / t.ent
    t["gross_pct"] = 100.0 * t.gross_pts / t.ent
    t["R"] = t.net_pts / t.risk
    t["cost_frac"] = cost / t.risk
    t["ts"] = f.index[t.e_bar.to_numpy()]
    return t


@njit(cache=True)
def _walk_flat(o, h, l, c, a, mod, sig, ex_n, sl, tp, w0, w1, side_want):
    """07:00-11:00 with a HARD FLATTEN at w1. Different strategy from a 4-hour hold cap.

    Two mechanics this branch has had to learn the hard way:
      * "flat at 11:00" means flat at the 11:00 OPEN -- an order submitted on the bar before. So a
        position still live when a bar's minute-of-day reaches w1 exits at THAT bar's OPEN, and no
        barrier may fire on it.
      * a signal whose FILL would land at or after the cutoff is REFUSED, not opened. Taking it and
        closing it at the same open books a zero-P&L trade and dilutes every statistic (STUDY_V60).
    """
    n = len(c)
    eb = np.full(n, -1, np.int64); xb = np.full(n, -1, np.int64)
    ep = np.zeros(n); xp = np.zeros(n); rk = np.zeros(n)
    sd = np.zeros(n, np.int64); wy = np.zeros(n, np.int64); am = np.zeros(n, np.int64)
    cnt = 0
    last = -1
    for i in range(ex_n + 2, n - 1):
        if mod[i] < w0 or mod[i] >= w1:
            continue
        if i <= last:
            continue
        s = sig[i]
        if s == 0:
            continue
        if side_want != 0 and s != side_want:
            continue
        if a[i] <= 0 or not np.isfinite(a[i]):
            continue
        j = i + 1
        if mod[j] < w0 or mod[j] >= w1:      # the fill would land outside the window -- refuse
            continue
        ent = o[j]
        stop = ent - s * sl * a[i]
        tgt = ent + s * tp * a[i] if tp > 0 else 0.0
        risk = abs(ent - stop)
        if risk <= 0:
            continue
        x = -1; px = 0.0; w = 4
        for t in range(j, n):
            if mod[t] >= w1 or mod[t] < w0:  # the flatten, at the OPEN, before any barrier
                x = t; px = o[t]; w = 4
                break
            hs = (l[t] <= stop) if s > 0 else (h[t] >= stop)
            ht = False
            if tp > 0:
                ht = (h[t] >= tgt) if s > 0 else (l[t] <= tgt)
            if hs and ht:
                am[cnt] = 1
            if hs:
                x = t; px = stop; w = 0
                break
            if ht:
                x = t; px = tgt; w = 1
                break
            if t > j and ex_n > 0:
                eh = h[t - ex_n]; el = l[t - ex_n]
                for q in range(t - ex_n + 1, t):
                    if h[q] > eh:
                        eh = h[q]
                    if l[q] < el:
                        el = l[q]
                if (s > 0 and c[t] < el) or (s < 0 and c[t] > eh):
                    x = t; px = c[t]; w = 2
                    break
        if x < 0:
            x = n - 1; px = c[n - 1]; w = 4
        eb[cnt] = j; xb[cnt] = x; ep[cnt] = ent; xp[cnt] = px
        rk[cnt] = risk; sd[cnt] = s; wy[cnt] = w
        cnt += 1
        last = x
    return eb[:cnt], xb[:cnt], ep[:cnt], xp[:cnt], rk[:cnt], sd[:cnt], wy[:cnt], am[:cnt]


def run_flat(f, a, sig, ex_n, sl, tp, side=0, cost=RT_POINTS):
    mod = (f.index.hour * 60 + f.index.minute).to_numpy()
    eb, xb, ep, xp, rk, sd, wy, am = _walk_flat(
        f["open"].to_numpy(), f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy(),
        a, mod, sig, int(ex_n), float(sl), float(tp), int(WIN0), int(WIN1), int(side))
    t = pd.DataFrame(dict(e_bar=eb, x_bar=xb, ent=ep, out=xp, risk=rk, side=sd, why=wy, amb=am))
    t["gross_pts"] = t.side * (t.out - t.ent)
    t["net_pts"] = t.gross_pts - cost
    t["pct"] = 100.0 * t.net_pts / t.ent
    t["gross_pct"] = 100.0 * t.gross_pts / t.ent
    t["R"] = t.net_pts / t.risk
    t["cost_frac"] = cost / t.risk
    t["ts"] = f.index[t.e_bar.to_numpy()]
    return t
