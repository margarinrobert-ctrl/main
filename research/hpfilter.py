"""The Hodrick-Prescott momentum strategy, and a measurement of the leak it invites.

From the QuantConnect note "The Momentum Strategy Based On The Low Frequency Component Of Forex
Market" (Jing Wu, 2018), after Harris & Yilmaz (2009, JBF 33(9)). Extract the low-frequency
component of price with an HP filter, then apply an MA(m, n) crossover to THAT rather than to
price. The published result is already negative -- Sharpe -0.309 to 0.480 across six FX pairs,
10-15 trades in six and a half years -- and the note names the reason:

    "the entry of new data into the filter model can cause the trend line to change the trend
     through past data"

That sentence is the whole problem, and it is why this module exists. The HP filter is a
TWO-SIDED smoother: x_t is chosen jointly with every other x, so the fitted trend at time t
depends on prices at t+1, t+2, ... Run it once over a whole price history and the resulting
"trend" is not a signal, it is a partial answer key. Applied causally -- re-solved on every bar
using only prices up to that bar, keeping only the last value -- it is legitimate, and much worse.

`leak_report()` measures the difference. That is the deliverable here, not the strategy.
"""
from __future__ import annotations

import sys

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import spsolve

sys.path.insert(0, "research")


def hp_trend(x, lamb=100.0):
    """The note's own hpfilter(), verbatim in behaviour: solve (I + lamb K'K) trend = x."""
    x = np.asarray(x, float).ravel()
    n = len(x)
    if n < 5:
        return x.copy()
    I = sparse.eye(n, n)
    K = sparse.dia_matrix((np.repeat([[1.0], [-2.0], [1.0]], n, axis=1),
                           np.array([0, 1, 2])), shape=(n - 2, n))
    return spsolve((I + lamb * K.T.dot(K)).tocsc(), x)


def trend_full(x, lamb=100.0):
    """THE LEAKY ONE. One solve over the whole series -- every point sees the entire future."""
    return hp_trend(x, lamb)


def trend_causal(x, lamb=100.0, window=200):
    """The honest one. Re-solve on each bar over the trailing `window`, keep only the endpoint.

    This is what the note's own on_data does (`hpfilter(self.close[-numdays:])`) and it is
    genuinely causal: bar t is fitted from x[t-window+1 .. t] and nothing later. It is also where
    the endpoint problem lives -- the last fitted value is the least constrained point of the fit,
    so it moves as new data arrives.
    """
    x = np.asarray(x, float).ravel()
    n = len(x)
    out = np.full(n, np.nan)
    for t in range(window - 1, n):
        out[t] = hp_trend(x[t - window + 1:t + 1], lamb)[-1]
    return out


def ma_signal(trend, m=1, n=2):
    """The note's MA(m, n) rule: sign of mean(trend[-m:]) - mean(trend[-n:]), and its cross.

    Returns (state, cross) where state is +1/-1 and cross is +1 on the bar the state turns up,
    -1 on the bar it turns down, 0 otherwise. The note trades the CROSS.
    """
    t = np.asarray(trend, float)
    N = len(t)
    fast = np.full(N, np.nan)
    slow = np.full(N, np.nan)
    for i in range(N):
        if i + 1 >= m and not np.isnan(t[i - m + 1:i + 1]).any():
            fast[i] = t[i - m + 1:i + 1].mean()
        if i + 1 >= n and not np.isnan(t[i - n + 1:i + 1]).any():
            slow[i] = t[i - n + 1:i + 1].mean()
    diff = fast - slow
    state = np.where(np.isnan(diff), 0, np.sign(diff)).astype(int)
    cross = np.zeros(N, int)
    for i in range(1, N):
        if state[i] != 0 and state[i - 1] != 0 and state[i] != state[i - 1]:
            cross[i] = state[i]
    return state, cross


# ================================================================= backtest
PV, TICK = 2.0, 0.25          # MNQ
FEE_RT = 1.44                 # itemised, research/costs.py
SLIP_RT = 2 * TICK * PV       # one tick each side, taker


def _positions(cross):
    """The note's own book: on a +1 cross go long, on -1 go short, hold until the next cross."""
    pos = np.zeros(len(cross), int)
    cur = 0
    for i, c in enumerate(cross):
        if c != 0:
            cur = c
        pos[i] = cur
    return pos


def backtest(px_close, px_open, lamb=100.0, m=1, n=2, causal=True, window=200):
    """Signal on bar t's close, fill at bar t+1's open, mark to market on closes.

    Returns per-BAR P&L in dollars for one contract, plus the position series and the fill count.
    """
    x = np.asarray(px_close, float)
    o = np.asarray(px_open, float)
    tr = trend_causal(x, lamb, window) if causal else trend_full(x, lamb)
    _s, cross = ma_signal(tr, m, n)
    pos = _positions(cross)
    held = np.roll(pos, 1)                 # signal at t's close is held from t+1
    held[0] = 0
    pnl = np.zeros(len(x))
    fills = 0
    for t in range(1, len(x)):
        pnl[t] = held[t] * (x[t] - x[t - 1]) * PV
        if held[t] != held[t - 1]:         # a turn: pay to close and to open at t's open
            turns = abs(held[t] - held[t - 1])
            pnl[t] -= turns * (FEE_RT + SLIP_RT) / 2.0
            pnl[t] -= held[t] * (o[t] - x[t - 1]) * PV * 0.0   # fill at open, mark from prior close
            fills += 1
    return pnl, held, fills, tr


def stats(pnl, ann=252):
    eq = np.cumsum(pnl)
    dd = float((np.maximum.accumulate(eq) - eq).max())
    sd = pnl.std()
    return dict(net=float(pnl.sum()), sharpe=float(pnl.mean() / sd * np.sqrt(ann)) if sd > 0 else 0.0,
                dd=dd, days=int(len(pnl)))


def leak_check(x, lamb=100.0, window=200, probes=40, seed=7, tol=1e-6, verbose=True):
    """Is this filter usable as a signal? Truncate the series and see if the past moves.

    A filter is a signal only if bar t's value would be unchanged had the series ended at bar t.
    This recomputes the trend on `x[:t+1]` for a sample of t and compares the value AT t against
    the value the full-series fit assigns to the same bar. Anything above `tol` is look-ahead.
    """
    x = np.asarray(x, float).ravel()
    rng = np.random.default_rng(seed)
    lo = max(window, 50)
    ts = np.unique(rng.integers(lo, len(x) - 1, size=probes))
    full = trend_full(x, lamb)
    d_full, d_caus = [], []
    for t in ts:
        d_full.append(abs(full[t] - hp_trend(x[:t + 1], lamb)[-1]))
        d_caus.append(abs(trend_causal(x[:t + 1], lamb, window)[t]
                          - trend_causal(x[:t + 2], lamb, window)[t]))
    d_full, d_caus = np.array(d_full), np.array(d_caus)
    scale = float(np.std(x))
    out = dict(n=len(ts), full_max=float(d_full.max()), full_mean=float(d_full.mean()),
               causal_max=float(d_caus.max()), scale=scale,
               full_leaks=bool(d_full.max() > tol), causal_leaks=bool(d_caus.max() > tol))
    if verbose:
        print(f"  leak_check on {len(ts)} probes, series sd {scale:.2f}")
        print(f"    trend_full   revises past bars by up to {out['full_max']:.4f} "
              f"({100*out['full_max']/scale:.1f}% of sd)  -> "
              f"{'LOOK-AHEAD' if out['full_leaks'] else 'clean'}")
        print(f"    trend_causal revises past bars by up to {out['causal_max']:.2e}  -> "
              f"{'LOOK-AHEAD' if out['causal_leaks'] else 'clean'}")
    return out
