"""The market-regime filter, on completed 15-minute bars, with hysteresis.

TWO THINGS MAKE THIS CAUSAL AND BOTH ARE EASY TO GET WRONG:

  the regime is frozen on the last 15-minute bar that has CLOSED at or before the trading bar's
  close, and forward-filled until the next one closes. The 15-minute bar CONTAINING the trading
  bar is still forming and is never read -- exactly the mapping the HTF EMA uses.

  the hysteresis is a STATE MACHINE, so it is a sequential recursion over the 15-minute bars and
  cannot be vectorised into a boolean. A trend state may only BEGIN at ADX >= adx_entry; it
  survives down to adx_exit. That asymmetry is the whole point of hysteresis and a naive
  `adx >= 25` mask is a different filter.

Wilder's DMI is implemented here rather than imported, because the branch has already been bitten
by `ta.dmi` returning [+DI, -DI, ADX] and a caller destructuring the first element as ADX.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import orb_feeds as OF  # noqa: E402

CHOP, BULL, BEAR = 0, 1, 2
NAME = {CHOP: "CHOP", BULL: "BULL", BEAR: "BEAR"}

ADX_ENTRY, ADX_EXIT = 25.0, 20.0
SLOPE_THR, DIST_THR = 0.05, 0.25
REG_TF, DMI_N, EMA_F, EMA_S, SLOPE_LAG = 15, 14, 20, 50, 3


def _w(x, n):
    return pd.Series(x).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()


def dmi(h, l, c, n=DMI_N):
    """Wilder +DI, -DI, ADX. Returned in that order and named, so nothing can be destructured
    into the wrong slot."""
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    up = h - np.roll(h, 1); up[0] = 0.0
    dn = np.roll(l, 1) - l; dn[0] = 0.0
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    atr = _w(tr, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi = 100.0 * _w(pdm, n) / atr
        ndi = 100.0 * _w(ndm, n) / atr
        dx = 100.0 * np.abs(pdi - ndi) / (pdi + ndi)
    dx = np.nan_to_num(dx, nan=0.0, posinf=0.0, neginf=0.0)
    return pdi, ndi, _w(dx, n), atr


@njit(cache=True)
def _state_machine(bull_dir, bear_dir, adx, aslope, dist, adx_entry, adx_exit,
                   slope_thr, dist_thr):
    n = len(adx)
    out = np.zeros(n, np.int64)
    st = 0
    for i in range(n):
        forced = (adx[i] < adx_exit) or (aslope[i] < slope_thr) or (dist[i] < dist_thr) \
                 or ((not bull_dir[i]) and (not bear_dir[i]))
        if forced:
            st = 0
        elif st == 0:
            if bull_dir[i] and adx[i] >= adx_entry:
                st = 1
            elif bear_dir[i] and adx[i] >= adx_entry:
                st = 2
            else:
                st = 0
        else:
            st = 1 if bull_dir[i] else 2
        out[i] = st
    return out


def regime(market, adx_entry=ADX_ENTRY, adx_exit=ADX_EXIT, slope_thr=SLOPE_THR,
           dist_thr=DIST_THR, reg_tf=REG_TF):
    """State per completed `reg_tf` bar, plus that bar's CLOSE TIME for causal forward-filling."""
    b = OF.bars(market, reg_tf)
    ix = pd.DatetimeIndex(b.index)
    h, l, c = (b[k].to_numpy(float) for k in ("high", "low", "close"))
    pdi, ndi, adx, atr = dmi(h, l, c)
    e20 = pd.Series(c).ewm(span=EMA_F, adjust=False).mean().to_numpy()
    e50 = pd.Series(c).ewm(span=EMA_S, adjust=False).mean().to_numpy()
    lag = np.r_[np.full(SLOPE_LAG, np.nan), e20[:-SLOPE_LAG]]
    with np.errstate(divide="ignore", invalid="ignore"):
        slope = (e20 - lag) / (SLOPE_LAG * atr)
        dist = np.abs(e20 - e50) / atr
    slope = np.nan_to_num(slope, nan=0.0)
    dist = np.nan_to_num(dist, nan=0.0)
    bull_dir = (e20 > e50) & (slope > slope_thr) & (pdi > ndi)
    bear_dir = (e20 < e50) & (slope < -slope_thr) & (ndi > pdi)
    st = _state_machine(bull_dir, bear_dir, adx, np.abs(slope), dist,
                        float(adx_entry), float(adx_exit), float(slope_thr), float(dist_thr))
    return dict(close_time=(ix + pd.Timedelta(minutes=reg_tf)).to_numpy(), state=st,
                adx=adx, slope=slope, dist=dist, pdi=pdi, ndi=ndi)


def on_bars(D, reg, ):
    """Forward-fill the frozen regime onto the trading bars, reading only CLOSED regime bars."""
    t_close = (pd.DatetimeIndex(D["ts"]) + pd.Timedelta(minutes=D["trade_tf"])).to_numpy()
    j = np.searchsorted(reg["close_time"], t_close, side="right") - 1
    return np.where(j >= 0, reg["state"][np.clip(j, 0, None)], CHOP)
