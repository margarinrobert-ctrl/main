"""V38 -- Donchian breakout + ATR stop + a linear-regression MA(50) and an MA(200), swept.

THE BRIEF: 100,000 combinations, find the most profitable version by profit factor. 113,400
configurations are declared below and every one of them is run.

WHAT THIS BRANCH ALREADY KNOWS ABOUT THESE COMPONENTS, so the result can be read against it:

  * `STUDY_V24_MA_CROSSOVER` -- an MA crossover adds nothing to a Donchian breakout: 442 of 988
    cells beat their own no-MA baseline on the holdout, 45%, where chance is 50%.
  * `STUDY_V25_LINREG_CROSS` -- `ta.linreg` fits a straight line exactly, so its RAMP LAG IS ZERO
    at every window; it sits with DEMA and TEMA, V24's two worst types. 197 of 478 linreg cells
    beat baseline on profit factor (41%) and 162 on Sharpe (34%).
  * `STUDY_SWEEP_110K` -- 110,250 configurations bought nothing: the best in-sample config scored
    +0.098 R out of sample against the un-swept starting point's +0.097.
  * `STUDY_V33_OPTIMIZER` -- 207,360 cells, and the deflated Sharpe of the winner is 0.0016
    against the trial count and 0.81 against one trial.

None of that forbids the search. It fixes how the answer must be read: by the SHARE of the grid
that is profitable and the MARGINAL AVERAGE per axis before the top row, with the top row's
selection premium stated, and with the holdout read exactly once.

DIRECTION IS FIXED LONG A PRIORI. NQ rose 89% over this sample and 81% of bars sit in a daily
uptrend; a search allowed to pick a side picks long and calls drift an edge (`CLAUDE.md` §4c).
Fixing it costs nothing here and removes a free lottery ticket from the search.

THE AXES (113,400 = 2 x 7 x 3 x 5 x 5 x 3 x 4 x 3 x 3):
    timeframe        15m, 30m
    Donchian entry   15, 20, 30, 40, 55, 70, 90          close above the prior N-bar high
    Donchian exit    10, 20, 30                          close below the prior N-bar low
    ATR stop         1.0, 1.5, 2.0, 2.5, 3.0  x ATR(14) at the SIGNAL bar
    take profit      none, 1.5R, 2R, 3R, 4R
    LRMA length      30, 50, 80                          the brief's 50, with a rung either side
    LRMA reading     off | close > value | slope > 0 | both
    MA length        150, 200, 250                       the brief's 200, with a rung either side
    MA reading       off | close > MA | LRMA value > MA

Costs are the real MNQ stack at x1.44 -- commission, exchange and NFA fees, plus a tick of
slippage charged on STOP exits only, which is where it is actually paid.

The exit outcome of a trade depends only on its SIGNAL BAR and its GEOMETRY, never on which
indicator fired, so the price is walked ONCE per (timeframe, exit channel, stop, target) -- 75
geometries a timeframe -- and every configuration becomes an array gather plus a position-lock
loop over its own signal bars. That is what makes 113,400 cells affordable.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, "research")
sys.path.insert(0, "research/v20")
import indicators as I         # noqa: E402
import fastbars as FB          # noqa: E402
import limit_entry as LE       # noqa: E402
from v20linreg import linreg   # noqa: E402

PV, TICK, COMM, EC, SE = LE.PV, LE.TICK, LE.COMM, LE.EC, LE.SE
COST_MULT = 1.44
MAX_HOLD = 500                 # bars; bounds the walk, and no config here holds near it

TFS = (15, 30)
DON_E = (15, 20, 30, 40, 55, 70, 90)
DON_X = (10, 20, 30)
STOP_N = (1.0, 1.5, 2.0, 2.5, 3.0)
TP_R = (0.0, 1.5, 2.0, 3.0, 4.0)          # 0.0 = no take profit
LR_LEN = (30, 50, 80)
LR_READ = ("off", "close>value", "slope>0", "both")
MA_LEN = (150, 200, 250)
MA_READ = ("off", "close>ma", "lrma>ma")

N_CONFIGS = (len(TFS) * len(DON_E) * len(DON_X) * len(STOP_N) * len(TP_R)
             * len(LR_LEN) * len(LR_READ) * len(MA_LEN) * len(MA_READ))


@njit(cache=True)
def _walk(o, h, l, c, atr, ex_lo, stop_n, tp_r, comm, ecpv, se, pv, max_hold, xb, pnl, why):
    """Every bar's outcome as a LONG entered at the next open, for one geometry.

    The stop is anchored to the SIGNAL bar's ATR, which is knowable when the order is written.
    Inside a bar the STOP is taken before the target -- the pessimistic branch and the only
    defensible one on OHLC.
    """
    n = len(c)
    for i in range(n - 2):
        xb[i] = -1
        a = atr[i]
        if not np.isfinite(a) or a <= 0.0:
            continue
        f = i + 1
        px = o[f]
        st = px - stop_n * a
        risk = px - st
        if risk <= 0.0:
            continue
        tg = px + tp_r * risk if tp_r > 0.0 else 1.0e18
        j = f
        last = min(f + max_hold, n - 1)
        w = 0
        xp = 0.0
        while j <= last:
            if l[j] <= st:
                xp = (o[j] if o[j] < st else st) - se
                w = 1
                break
            if h[j] >= tg:
                xp = o[j] if o[j] > tg else tg
                w = 2
                break
            if j > f and np.isfinite(ex_lo[j]) and c[j] < ex_lo[j]:
                xp = c[j]
                w = 3
                break
            j += 1
        if w == 0:
            j = last
            xp = c[j]
            w = 4
        xb[i] = j
        why[i] = w
        pnl[i] = (xp - px) * pv - comm - 2.0 * ecpv


@njit(cache=True)
def _walk_flat(o, h, l, c, mod, atr, ex_lo, stop_n, tp_r, flat_mod,
               comm, ecpv, se, pv, max_hold, xb, pnl, why):
    """As `_walk`, plus a HARD FLATTEN at a minute of day.

    The flatten fills at the CLOSE of the bar whose minute reaches the cutoff. A Pine script cannot
    do that -- `strategy.close_all()` fills at the NEXT bar's open -- so `flat_open` below is what
    the shipped script actually gets, and it is the number reported. This engine matches the
    script rather than the other way round (`CLAUDE.md`)."""
    n = len(c)
    for i in range(n - 2):
        xb[i] = -1
        a = atr[i]
        if not np.isfinite(a) or a <= 0.0:
            continue
        f = i + 1
        px = o[f]
        st = px - stop_n * a
        risk = px - st
        if risk <= 0.0:
            continue
        tg = px + tp_r * risk if tp_r > 0.0 else 1.0e18
        j = f
        last = min(f + max_hold, n - 1)
        w = 0
        xp = 0.0
        while j <= last:
            if l[j] <= st:
                xp = (o[j] if o[j] < st else st) - se
                w = 1
                break
            if h[j] >= tg:
                xp = o[j] if o[j] > tg else tg
                w = 2
                break
            if flat_mod > 0 and mod[j] >= flat_mod:
                xp = o[j]                      # the NEXT open, which is what a script gets
                w = 3
                break
            if j > f and np.isfinite(ex_lo[j]) and c[j] < ex_lo[j]:
                xp = c[j]
                w = 4
                break
            j += 1
        if w == 0:
            j = last
            xp = c[j]
            w = 5
        xb[i] = j
        why[i] = w
        pnl[i] = (xp - px) * pv - comm - 2.0 * ecpv


@njit(cache=True)
def _lock(sig, xb, pnl, out_pnl, out_sig):
    """One position at a time. A signal inside a live trade is skipped, not queued."""
    k = 0
    free = -1
    for t in range(len(sig)):
        i = sig[t]
        if i < free:
            continue
        x = xb[i]
        if x < 0:
            continue
        out_pnl[k] = pnl[i]
        out_sig[k] = i
        k += 1
        free = x
    return k


def prep(tf, d=None, pv=PV):
    """Bars plus every indicator any configuration can ask for, computed once."""
    if d is None:
        d = FB.bars(tf)
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    atr = I.ema(I.true_range(h, l, c), 14)
    P = dict(o=o, h=h, l=l, c=c, atr=atr, n=len(c), pv=float(pv),
             ts=d["ts"],
             day=(pd.to_datetime(d["ts"]).normalize().astype("int64").to_numpy()))
    P["don_hi"] = {e: I.shift(I.rmax(h, e), 1) for e in DON_E}
    P["ex_lo"] = {x: I.shift(I.rmin(l, x), 1) for x in DON_X}
    P["lr"] = {}
    for n in LR_LEN:
        v, s, _r2 = linreg(c, n)
        P["lr"][n] = (v, s)
    P["ma"] = {n: I.sma(c, n) for n in MA_LEN}
    return P


def masks(P):
    """Every distinct SIGNAL SET in the grid: 756 a timeframe, each a boolean array."""
    c = P["c"]
    out = {}
    for e in DON_E:
        brk = c > P["don_hi"][e]
        for ln in LR_LEN:
            v, s = P["lr"][ln]
            lrm = {"off": np.ones(len(c), bool), "close>value": c > v, "slope>0": s > 0,
                   "both": (c > v) & (s > 0)}
            for lr in LR_READ:
                for mn in MA_LEN:
                    ma = P["ma"][mn]
                    mam = {"off": np.ones(len(c), bool), "close>ma": c > ma, "lrma>ma": v > ma}
                    for mr in MA_READ:
                        m = brk & lrm[lr] & mam[mr]
                        m &= np.isfinite(P["atr"])
                        out[(e, ln, lr, mn, mr)] = np.flatnonzero(m).astype(np.int64)
    return out


def tensor(P):
    """The exit tensor: one walk of the bars per (exit channel, stop, target)."""
    n = P["n"]
    pv = P.get("pv", PV)
    comm, ecpv, se = COMM * COST_MULT, EC * COST_MULT * pv, SE * COST_MULT
    out = {}
    for x in DON_X:
        el = P["ex_lo"][x]
        for sn in STOP_N:
            for tp in TP_R:
                xb = np.full(n, -1, np.int64)
                pnl = np.zeros(n)
                why = np.zeros(n, np.int64)
                _walk(P["o"], P["h"], P["l"], P["c"], P["atr"], el, float(sn), float(tp),
                      comm, ecpv, se, pv, MAX_HOLD, xb, pnl, why)
                out[(x, sn, tp)] = (xb, pnl, why)
    return out


def score(pnl, days, all_days):
    """PF, expectancy and Sharpe. SHARPE IS OVER EVERY TRADING DAY IN THE BLOCK, zero-filled on
    days that did not trade -- over traded days only, a filter is PAID for trading less."""
    if len(pnl) < 20 or not (pnl < 0).any():
        return None
    w, lo = pnl[pnl > 0], pnl[pnl < 0]
    dz = pd.Series(pnl).groupby(pd.Series(days)).sum().reindex(all_days, fill_value=0.0).to_numpy()
    sd = dz.std(ddof=1)
    eq = np.cumsum(pnl)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    return dict(n=len(pnl), pf=float(w.sum() / abs(lo.sum())), usd=float(pnl.mean()),
                net=float(pnl.sum()), win=float((pnl > 0).mean()), dd=dd,
                retdd=float(pnl.sum() / dd) if dd > 0 else np.nan,
                sharpe=float(dz.mean() / sd * np.sqrt(252)) if sd > 0 else np.nan)


def tensor_stop(P, exit_n, stop_n, tp_r, flat_mod=0):
    """One geometry, with an optional hard flatten at a minute of day."""
    n = P["n"]
    pv = P.get("pv", PV)
    comm, ecpv, se = COMM * COST_MULT, EC * COST_MULT * pv, SE * COST_MULT
    el = I.shift(I.rmin(P["l"], exit_n), 1)
    xb = np.full(n, -1, np.int64)
    pnl = np.zeros(n)
    why = np.zeros(n, np.int64)
    _walk_flat(P["o"], P["h"], P["l"], P["c"], P["mod"].astype(np.int64), P["atr"], el,
               float(stop_n), float(tp_r), int(flat_mod),
               comm, ecpv, se, pv, MAX_HOLD, xb, pnl, why)
    return xb, pnl, why
