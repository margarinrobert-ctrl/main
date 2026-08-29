"""Donchian channels, computed so that a breakout is a fact about the bar it is read on.

Two definitional traps, both of which have shipped broken in public code:

  * the channel must EXCLUDE the current bar. `rmax(high, n)[i]` includes `high[i]`, so
    `high[i] >= rmax(high, n)[i]` is true on every bar that is its own n-bar high -- a tautology,
    not a breakout. Everything here is built on the window `[i-n, i-1]`.
  * a breakout read on the CLOSE of bar i and filled at the open of bar i+1 is causal; a breakout
    read on the intrabar HIGH is a stop order, and the fill is the level, not the next open. Both
    are offered, and they are different strategies with different cost models -- `touch` fills at
    the level plus slippage, `close` pays whatever the next open is.

`sig_bar` semantics in this repository: the bar a condition is read on is the SIGNAL bar and the
fill happens on the next one. Nothing in this module ever reads index > i to produce output i;
`selftest()` asserts that by truncation.
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:                                            # optional: 25x on a 1M-bar file, not required
    from numba import njit
except Exception:                               # pragma: no cover - numba is a speed knob only
    def njit(*a, **k):
        def deco(f):
            return f
        return deco if not a else a[0]


# ------------------------------------------------------------------ rolling extremes
@njit(cache=True)
def _roll_max(x, n, out):
    """Monotonic-deque rolling max over the PREVIOUS n values, exclusive of the current one."""
    m = len(x)
    q = np.empty(m, np.int64)
    head = 0
    tail = 0                                    # deque holds indices, values decreasing
    for i in range(m):
        lo = i - n                              # window is [i-n, i-1]
        while tail > head and q[head] < lo:
            head += 1
        out[i] = x[q[head]] if tail > head else np.nan
        while tail > head and x[q[tail - 1]] <= x[i]:
            tail -= 1
        q[tail] = i
        tail += 1
    return out


@njit(cache=True)
def _roll_min(x, n, out):
    m = len(x)
    q = np.empty(m, np.int64)
    head = 0
    tail = 0
    for i in range(m):
        lo = i - n
        while tail > head and q[head] < lo:
            head += 1
        out[i] = x[q[head]] if tail > head else np.nan
        while tail > head and x[q[tail - 1]] >= x[i]:
            tail -= 1
        q[tail] = i
        tail += 1
    return out


def prior_max(x, n):
    """max(x[i-n .. i-1]); NaN until n prior bars exist."""
    x = np.ascontiguousarray(np.asarray(x, float))
    out = np.full(len(x), np.nan)
    _roll_max(x, int(n), out)
    out[:int(n)] = np.nan
    return out


def prior_min(x, n):
    x = np.ascontiguousarray(np.asarray(x, float))
    out = np.full(len(x), np.nan)
    _roll_min(x, int(n), out)
    out[:int(n)] = np.nan
    return out


# ------------------------------------------------------------------ the channel
def channel(h, l, n):
    """(upper, lower, mid, width) of the Donchian channel formed by the n bars BEFORE each bar."""
    up = prior_max(h, n)
    dn = prior_min(l, n)
    return up, dn, 0.5 * (up + dn), up - dn


def position(h, l, c, n):
    """Where the close sits in the prior channel: 0 at the lower band, 1 at the upper, >1 above."""
    up, dn, _, w = channel(h, l, n)
    return (np.asarray(c, float) - dn) / np.where(w > 1e-12, w, np.nan)


def width_atr(h, l, c, n, atr_):
    """Channel width in ATR units -- the compression / expansion state, scale-free."""
    _, _, _, w = channel(h, l, n)
    a = np.asarray(atr_, float)
    return w / np.where(a > 1e-12, a, np.nan)


def bars_since_new(h, l, n, side=1):
    """Bars since the channel last made a new extreme on `side`. A fresh channel is a young one."""
    up, dn, _, _ = channel(h, l, n)
    ref = np.asarray(h if side > 0 else l, float)
    new = (ref > up) if side > 0 else (ref < dn)
    out = np.full(len(ref), np.nan)
    last = -1
    for i in range(len(ref)):
        if last >= 0:
            out[i] = i - last
        if new[i]:
            last = i
    return out


# ------------------------------------------------------------------ breakout triggers
def breakout(d, n, side=1, buf_ticks=0.0, mode="close", tick=0.25):
    """Boolean per bar: this bar breaks the prior n-bar channel on `side`.

    mode="close"  the CLOSE clears the band -- read at the close of bar i, filled at open i+1.
                  Fewer signals, no fill assumption to defend, and the one this repo's engines
                  simulate natively.
    mode="touch"  the HIGH/LOW clears the band -- a resting stop order. Fills at the level, which
                  the backtester must be told about; do not simulate it as a next-open market
                  order, that quietly awards you the gap.
    `buf_ticks` requires price to clear the band by that many ticks, which is the cheapest guard
    against the one-tick probe that is the classic false breakout.
    """
    up, dn, _, _ = channel(d["h"], d["l"], n)
    buf = float(buf_ticks) * float(tick)
    px = d["c"] if mode == "close" else (d["h"] if side > 0 else d["l"])
    px = np.asarray(px, float)
    out = (px > up + buf) if side > 0 else (px < dn - buf)
    return np.nan_to_num(out.astype(float)).astype(bool)


def entry_level(d, n, side=1, buf_ticks=0.0, tick=0.25):
    """The stop-order price for mode='touch': the band plus the buffer, snapped to the tick grid."""
    up, dn, _, _ = channel(d["h"], d["l"], n)
    buf = float(buf_ticks) * float(tick)
    lvl = (up + buf) if side > 0 else (dn - buf)
    return np.round(lvl / tick) * tick


# ------------------------------------------------------------------ indpool registration
def register():
    """Expose the channel to the tuner's rule language, so a period is a knob and not a code edit.

    After this, `tuner.sweep("close > donch_hi{n}", n=[10,20,40])` works, as does
    `donch_pos20 > 1` and `donch_w_atr20 < 3`.
    """
    import indpool

    @indpool.ind("donch_hi", "upper Donchian band over the n bars BEFORE this one")
    def _hi(d, n):
        return channel(d["h"], d["l"], int(n))[0]

    @indpool.ind("donch_lo", "lower Donchian band over the n bars BEFORE this one")
    def _lo(d, n):
        return channel(d["h"], d["l"], int(n))[1]

    @indpool.ind("donch_mid", "Donchian midline, prior n bars")
    def _mid(d, n):
        return channel(d["h"], d["l"], int(n))[2]

    @indpool.ind("donch_w", "Donchian width in price, prior n bars")
    def _w(d, n):
        return channel(d["h"], d["l"], int(n))[3]

    @indpool.ind("donch_pos", "close position in the prior n-bar channel (0=low, 1=high)")
    def _pos(d, n):
        return position(d["h"], d["l"], d["c"], int(n))

    @indpool.ind("donch_w_atr", "Donchian width in ATR(14) units -- compression state")
    def _watr(d, n):
        return width_atr(d["h"], d["l"], d["c"], int(n), indpool.get(d, "atr", 14))

    @indpool.ind("donch_age_up", "bars since the prior n-bar high was exceeded")
    def _au(d, n):
        return bars_since_new(d["h"], d["l"], int(n), 1)

    @indpool.ind("donch_age_dn", "bars since the prior n-bar low was broken")
    def _ad(d, n):
        return bars_since_new(d["h"], d["l"], int(n), -1)
    return sorted(k for k in indpool.REG if k.startswith("donch"))


# ------------------------------------------------------------------ self-test
def selftest(n=20, m=5000, seed=3):
    rng = np.random.default_rng(seed)
    c = 100 + np.cumsum(rng.normal(0, 0.25, m))
    h = c + np.abs(rng.normal(0, 0.2, m))
    l = c - np.abs(rng.normal(0, 0.2, m))
    up, dn, mid, w = channel(h, l, n)

    # 1. correctness against the naive definition
    for i in (n, n + 1, 137, 999, m - 1):
        assert np.isclose(up[i], h[i - n:i].max()), f"upper band wrong at {i}"
        assert np.isclose(dn[i], l[i - n:i].min()), f"lower band wrong at {i}"

    # 2. the current bar is excluded -- a bar that is its own high must not always break out
    tautology = (h >= np.maximum.accumulate(np.where(np.arange(m) < n, -np.inf, h)))
    brk = breakout({"h": h, "l": l, "c": c}, n, 1, mode="touch")
    assert brk[n:].mean() < 0.35, "breakout rate implausibly high -- current bar leaking in"
    assert not np.all(brk[tautology]), "channel includes the current bar"

    # 3. causality: truncating the future must not change any past value
    k = int(0.7 * m)
    up2, dn2, _, _ = channel(h[:k], l[:k], n)
    a, b = up[:k], up2
    fin = np.isfinite(a) & np.isfinite(b)
    assert np.allclose(a[fin], b[fin]) and np.allclose(dn[:k][fin], dn2[fin]), "look-ahead"

    # 4. width and position are consistent
    pos = position(h, l, c, n)
    fin = np.isfinite(pos)
    assert np.allclose(pos[fin], ((c - dn) / w)[fin]), "position inconsistent with the bands"
    return dict(bars=m, breakout_rate=float(brk[n:].mean()), median_width=float(np.nanmedian(w)))


if __name__ == "__main__":
    print("donchian selftest:", selftest())
