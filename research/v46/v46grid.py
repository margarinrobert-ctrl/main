"""V46 -- the Carver-breakout parameter space, swept with a cached exit tensor.

WHY NOT vectorbt FOR THE SWEEP, STATED PLAINLY. A million vectorbt portfolio simulations over
200,000 bars is many hours on four cores; it is the wrong tool for the search and the right tool
for the CHECK. So the sweep runs on this branch's own architecture -- a trade's outcome depends
only on its SIGNAL BAR and its EXIT RULE, so the price is walked once per exit rule and every
signal set becomes an array lookup plus a position-lock loop -- and vectorbt is then run as an
INDEPENDENT SECOND ENGINE on the finalists. That is the use that has actually found things here:
`STUDY_V38` and `STUDY_V41` both caught a convention gap worth 2.1x and 22.9x that way, by
requiring the TRADE COUNT to match first and only then reading the P&L difference.

THE FACTORISATION. The exit rule is (span, smooth, exit threshold, stop, target, max hold) and the
signal set is (span, smooth, entry threshold, mode, chop). Span and smoothing appear in both, so
the walk is done per exit configuration and reused across the 48 signal sets that share it:

    3 timeframes x 8 spans x 3 smoothings x 4 exit thresholds x 5 stops x 5 targets x 3 max holds
      = 21,600 exit configurations, each ONE walk of the bars
    x 6 entry thresholds x 2 modes x 4 chop ceilings = 48 signal sets per walk
      = 1,036,800 cells

Carver's own span set is {10, 20, 40, 80, 160, 320}; 5 and 640 are declared extensions and are
flagged as such wherever the marginals are read, because his fastest variants are already the ones
he says costs eat.

SEARCH ON US100 ONLY. US30 and NQ are held back and are not read until a configuration is frozen,
which is the same protocol V42 used. The objective is the MEDIAN OF THE WALK-FORWARD FOLDS, not the
aggregate: a configuration carried by one lucky period has a low median even when its total is the
grid's best.

Usage: imported by run_v46.py
"""
from __future__ import annotations

import sys

import numpy as np
from numba import njit

sys.path.insert(0, "research")
sys.path.insert(0, "research/v38")
sys.path.insert(0, "research/v46")
import v38feeds as FD        # noqa: E402
import carver as CV          # noqa: E402

TFS = (15, 30, 60)
SPANS = (5, 10, 20, 40, 80, 160, 320, 640)      # 10-320 are Carver's; 5 and 640 are extensions
SMOOTH_DIV = (2, 4, 8)
ENTRY_THR = (0.0, 2.0, 5.0, 8.0, 10.0, 15.0)
ENTRY_MODE = ("state", "cross")
EXIT_THR = (None, 0.0, -5.0, -10.0)             # None = barriers only
STOPS = (1.0, 1.5, 2.0, 2.5, 3.0)               # ATR
TPS = (0.0, 1.0, 2.0, 3.0, 5.0)                 # R; 0 = no target
MAX_HOLD = (24, 96, 480)                        # bars
CHOP_CEIL = (100.0, 55.0, 45.0, 40.0)           # 100 = off

N_NOMINAL = (len(TFS) * len(SPANS) * len(SMOOTH_DIV) * len(EXIT_THR) * len(STOPS) * len(TPS)
             * len(MAX_HOLD) * len(ENTRY_THR) * len(ENTRY_MODE) * len(CHOP_CEIL))
N_FOLDS = 8
MIN_TRADES_PER_FOLD = 8


@njit(cache=True)
def rma(x, n):
    m = len(x); out = np.full(m, np.nan)
    a = 0.0; cnt = 0
    for i in range(m):
        v = x[i]
        if np.isnan(v):
            continue
        cnt += 1
        if cnt == 1:
            a = v
        else:
            a = a + (v - a) / n
        out[i] = a
    return out


@njit(cache=True)
def true_range(h, l, c):
    m = len(c); tr = np.empty(m)
    tr[0] = h[0] - l[0]
    for i in range(1, m):
        x = h[i] - l[i]
        y = abs(h[i] - c[i - 1])
        z = abs(l[i] - c[i - 1])
        tr[i] = max(x, max(y, z))
    return tr


@njit(cache=True)
def chop_idx(h, l, c, n):
    """CHOP(n) = 100*log10(sum TR / range) / log10(n). Higher = choppier."""
    m = len(c)
    tr = true_range(h, l, c)
    out = np.full(m, np.nan)
    ln = np.log10(float(n))
    for i in range(n - 1, m):
        s = 0.0; hi = h[i - n + 1]; lo = l[i - n + 1]
        for j in range(i - n + 1, i + 1):
            s += tr[j]
            if h[j] > hi:
                hi = h[j]
            if l[j] < lo:
                lo = l[j]
        rg = hi - lo
        if rg > 0 and s > 0:
            out[i] = 100.0 * np.log10(s / rg) / ln
    return out


@njit(cache=True)
def walk_exits(o, h, l, c, atr, fc, exit_thr, use_exit, stop_n, tp_r, max_hold,
               cost_pts, slip_pts):
    """For EVERY bar as a hypothetical signal, the exit bar and the P&L in points.

    Long only. Fill at the next open. The stop is `stop_n` ATR below the fill, the target `tp_r`
    times that risk above it, and the trade also closes on a forecast falling below `exit_thr` or
    at `max_hold` bars. When the stop and the target both fall inside one bar the STOP is taken --
    a bar cannot say which came first, so the pessimistic convention is used and the ambiguous
    share is counted separately."""
    m = len(c)
    xb = np.full(m, -1, np.int64)
    pnl = np.full(m, np.nan)
    amb = np.zeros(m, np.int64)
    for i in range(m):
        if i + 1 >= m or not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        px = o[i + 1] + slip_pts
        risk = stop_n * atr[i]
        stop = px - risk
        tgt = px + tp_r * risk if tp_r > 0 else 1e18
        j = i + 1
        end = min(m - 1, i + 1 + max_hold)
        out = 0.0; done = False
        while j <= end:
            hit_s = l[j] <= stop
            hit_t = h[j] >= tgt
            if hit_s and hit_t:
                amb[i] = 1
            if hit_s:
                out = stop - slip_pts; done = True
                break
            if hit_t:
                out = tgt - slip_pts; done = True
                break
            if use_exit and np.isfinite(fc[j]) and fc[j] < exit_thr:
                out = c[j] - slip_pts; done = True
                break
            j += 1
        if not done:
            j = end
            out = c[j] - slip_pts
        xb[i] = j
        pnl[i] = out - px - cost_pts
    return xb, pnl, amb


@njit(cache=True)
def lock_and_score(sig, xb, pnl, fold, n_folds):
    """One position at a time, in signal order. Returns aggregates and per-fold nets."""
    n_tr = 0; net = 0.0; gw = 0.0; gl = 0.0; nw = 0
    f_net = np.zeros(n_folds); f_n = np.zeros(n_folds, np.int64)
    last = -1
    for k in range(len(sig)):
        i = sig[k]
        if i <= last or xb[i] < 0 or not np.isfinite(pnl[i]):
            continue
        p = pnl[i]
        n_tr += 1; net += p
        if p > 0:
            gw += p; nw += 1
        else:
            gl -= p
        fi = fold[i]
        f_net[fi] += p; f_n[fi] += 1
        last = xb[i]
    return n_tr, net, gw, gl, nw, f_net, f_n


def prep(market, tf, cost_pts, slip_pts):
    d = FD.frame(market, tf)
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    atr = rma(true_range(h, l, c), 14)
    ch = chop_idx(h, l, c, 14)
    n = len(c)
    ts = d["ts"]
    fold = np.searchsorted(np.quantile(ts, np.linspace(0, 1, N_FOLDS + 1)[1:-1]), ts).astype(np.int64)
    fc = {}
    for s in SPANS:
        for sd in SMOOTH_DIV:
            fc[(s, sd)] = CV.forecast(c, s, sd)
    return dict(o=o, h=h, l=l, c=c, atr=atr, chop=ch, fc=fc, n=n, ts=ts, fold=fold,
                cost=cost_pts, slip=slip_pts, tf=tf, market=market)


def signal_bars(P, span, sd, thr, mode, chop_ceil, block):
    f = P["fc"][(span, sd)]
    if mode == "state":
        m = f >= thr
    else:
        m = (f >= thr) & (np.roll(f, 1) < thr)
        m[0] = False
    m &= np.isfinite(f)
    if chop_ceil < 100.0:
        m &= np.isfinite(P["chop"]) & (P["chop"] <= chop_ceil)
    m &= block
    m &= np.isfinite(P["atr"]) & (P["atr"] > 0)
    return np.flatnonzero(m).astype(np.int64)
