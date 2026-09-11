"""Donchian trend follower (slow, frozen) + a 1-minute mean-reversion signal as an EXECUTION
overlay. The slow strategy's thesis, risk and exit clock are untouched; only the entry timestamp
moves.

THE CONSTRUCTION THAT MAKES THE COMPARISON CLEAN. Three things are anchored to the SIGNAL bar and
are therefore identical in both arms:

  the stop LEVEL        signal close - stop_mult x ATR(signal bar). Anchoring it to the FILL price
                        would let a better fill move the stop, which changes the risk and turns an
                        execution comparison into a leverage comparison. `STUDY_V22_VOLATILITY`
                        already established the signal-close anchor is what a script can place
                        anyway (99.0% identical exit bars against the fill anchor).
  the exit CLOCK        the trade is closed `hold_min` minutes after the SIGNAL, not after the
                        fill, so both arms leave at the same wall-clock moment.
  the SIZE              one unit, set at the slow strategy's own decision time.

So the only difference between the arms is the price paid and the minutes held. That is exactly
the claim an execution overlay makes, and it is what `decompose()` is built to take apart.

IF THE STOP LEVEL IS BREACHED WHILE THE OVERLAY IS STILL WAITING, the overlay does not take the
trade at all. That is a real population change, not a modelling convenience, and it is reported
separately rather than folded into a fill-quality number.

BOTH ARMS CROSS THE SPREAD. Neither claims a passive fill, so the taker cost is identical and does
not cancel in the overlay's favour; the overlay claims a better PRICE, not a cheaper FEE.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

HERE = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(HERE, ".."), os.path.join(HERE, "..", "v63")):
    if p not in sys.path:
        sys.path.insert(0, p)

import v63feeds as FD  # noqa: E402

SLOW_TF = 30            # minutes; the trend follower's decision bars
DON = 20                # entry channel
STOP_MULT = 2.5         # x ATR14 at the signal bar
HOLD_MIN = 480 * 30     # the 480-bar cap of the slow strategy, in minutes
FAST_EMA, FAST_ATR = 20, 20


def _wilder(x, n):
    return pd.Series(x).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def build(market="NQ", fast_tf=1):
    """Slow signals on SLOW_TF bars, execution and the fast signal on `fast_tf` bars."""
    f = FD.bars(market, fast_tf)
    g = FD.bars(market, SLOW_TF)
    o, h, l, c = (f[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    fi = pd.DatetimeIndex(f.index)

    go, gh, gl, gc = (g[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    gi = pd.DatetimeIndex(g.index)
    pc = np.concatenate(([gc[0]], gc[:-1]))
    tr = np.maximum(gh - gl, np.maximum(np.abs(gh - pc), np.abs(gl - pc)))
    gatr = _wilder(tr, 14)
    don = pd.Series(gh).rolling(DON).max().shift(1).to_numpy()
    sig = np.asarray(gh > don, bool)
    sig[:300] = False
    sig &= np.isfinite(gatr) & (gatr > 0)

    # the fast signal: displacement from a short EMA, in fast-bar ATR units. Causal.
    fc = pd.Series(c)
    ema = fc.ewm(span=FAST_EMA, adjust=False).mean().to_numpy()
    fpc = np.concatenate(([c[0]], c[:-1]))
    ftr = np.maximum(h - l, np.maximum(np.abs(h - fpc), np.abs(l - fpc)))
    fatr = _wilder(ftr, FAST_ATR)
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (c - ema) / np.where(fatr > 0, fatr, np.nan)

    # map each slow signal bar's CLOSE to the first fast bar that opens after it
    sig_i = np.flatnonzero(sig)
    close_ts = gi[sig_i] + pd.Timedelta(minutes=SLOW_TF)
    pos = np.searchsorted(fi.values, close_ts.values, side="left")
    ok = (pos > 0) & (pos < len(fi) - 5)
    sig_i, pos = sig_i[ok], pos[ok]

    cost, pv = FD.COST[market]
    tick = {"NQ": 0.25, "US100": 0.1, "US30": 0.1}[market]
    return dict(market=market, fast_tf=fast_tf, o=o, h=h, l=l, c=c, z=z, fatr=fatr, ts=fi,
                n=len(c), sig_bar=pos.astype(np.int64),
                sig_close=gc[sig_i], sig_atr=gatr[sig_i], sig_ts=gi[sig_i],
                cost=cost, slip=tick, pv=pv, tick=tick,
                blocks=FD.blocks(market, fi))


@njit(cache=True)
def walk(o, h, l, c, z, sig_bar, sig_close, sig_atr, stop_mult, hold_bars, gate, K,
         rand_delay, cost, slip, lock):
    """One arm. `gate=0` is the baseline (fill at the next bar's open); `gate=1` waits for the
    fast signal to turn non-positive; `gate=2` waits a supplied number of bars (the placebo).

    Returns, per signal: entry bar, entry price, exit bar, exit price, delay in bars, and a status
    (0 filled, 1 stopped out before the overlay could enter, 2 no room in the data, 3 blocked by
    the position lock). With `lock=1` a signal is refused while a previous trade is still open,
    which is what a one-contract book actually does; each arm locks on its OWN exit bars, so the
    two arms can diverge in population -- that divergence is a real consequence of the overlay and
    is reported by `decompose()` rather than hidden.
    """
    n = len(sig_bar)
    m = len(c)
    busy_until = -1
    e_bar = np.full(n, -1, np.int64)
    e_px = np.full(n, np.nan)
    x_bar = np.full(n, -1, np.int64)
    x_px = np.full(n, np.nan)
    delay = np.zeros(n, np.int64)
    status = np.zeros(n, np.int64)
    for k in range(n):
        a = sig_bar[k]
        if lock == 1 and a <= busy_until:
            status[k] = 3               # a previous trade is still open
            continue
        stop = sig_close[k] - stop_mult * sig_atr[k]
        end = a + hold_bars
        if end > m - 2:
            status[k] = 2
            continue
        # ---- when do we enter?
        if gate == 0:
            j = a
        elif gate == 1:
            j = a
            lim = a + K
            if lim > m - 2:
                lim = m - 2
            while j < lim and z[j - 1] > 0.0:
                if l[j] <= stop:            # the thesis died while we waited
                    j = -1
                    break
                j += 1
        else:
            d = rand_delay[k]
            if d > K:
                d = K
            j = a
            lim = a + d
            if lim > m - 2:
                lim = m - 2
            while j < lim:
                if l[j] <= stop:
                    j = -1
                    break
                j += 1
        if j < 0:
            status[k] = 1
            continue
        if j > end:
            status[k] = 2
            continue
        delay[k] = j - a
        px = o[j] + slip
        e_bar[k] = j
        e_px[k] = px
        # ---- the exit: the SAME stop level and the SAME clock in both arms
        out = np.nan
        xb = -1
        i = j
        while i <= end:
            if l[i] <= stop:
                out = (stop if o[i] > stop else o[i]) - slip
                xb = i
                break
            i += 1
        if xb < 0:
            xb = end
            out = c[end] - slip
        x_bar[k] = xb
        x_px[k] = out
        if xb > busy_until:
            busy_until = xb
    return e_bar, e_px, x_bar, x_px, delay, status


def trades(D, gate=0, K=30, rand_delay=None, stop_mult=STOP_MULT, hold_min=HOLD_MIN, lock=0):
    hold_bars = int(hold_min / D["fast_tf"])
    n = len(D["sig_bar"])
    rd = np.zeros(n, np.int64) if rand_delay is None else np.asarray(rand_delay, np.int64)
    e_bar, e_px, x_bar, x_px, delay, status = walk(
        D["o"], D["h"], D["l"], D["c"], D["z"], D["sig_bar"], D["sig_close"], D["sig_atr"],
        float(stop_mult), hold_bars, int(gate), int(K), rd, D["cost"], D["slip"], int(lock))
    keep = status == 0
    ids = np.arange(n)[keep]
    t = pd.DataFrame(dict(signal_id=ids, side=1, qty=1.0,
                          entry_px=e_px[keep], exit_px=x_px[keep],
                          entry_bar=e_bar[keep], exit_bar=x_bar[keep],
                          delay=delay[keep]))
    # the round turn is charged identically in both arms: both cross the spread
    t["gross"] = t["side"] * t["qty"] * (t["exit_px"] - t["entry_px"])
    t["net"] = t["gross"] - 2 * D["cost"]
    t["ts"] = D["ts"][t["entry_bar"].to_numpy()]
    t["exit_ts"] = D["ts"][t["exit_bar"].to_numpy()]
    t["hold_min"] = (t["exit_bar"] - t["entry_bar"]) * D["fast_tf"]
    t["pct"] = 100.0 * t["net"] / t["entry_px"]
    return t, status


def daily(t, D):
    """Net PnL per calendar day, zero-filled over every day the fast series covers."""
    d = pd.Series(t["net"].to_numpy(), index=pd.DatetimeIndex(t["exit_ts"])).groupby(
        pd.DatetimeIndex(t["exit_ts"]).normalize()).sum()
    days = pd.DatetimeIndex(pd.Series(D["ts"]).dt.normalize().unique())
    return d.reindex(days).fillna(0.0)
