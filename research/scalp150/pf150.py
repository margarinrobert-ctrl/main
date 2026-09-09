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
