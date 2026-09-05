"""True 1-minute path simulation of a 5-minute ATME configuration, plus perturbation Monte Carlo.

WHY THIS TEST EXISTS AND WHY IT MATTERS MOST FOR THIS STRATEGY. The 5-minute engine decides three
things it cannot actually see: whether a resting limit was reached inside a bar, and -- once
filled -- whether the stop or the target came first when one bar touched both. It resolves the
second conservatively (stop wins). A limit-entry strategy lives or dies on exactly those
assumptions, because the fill is the edge.

Walking the real 1-MINUTE bars removes both assumptions. The signal is still computed on the
5-minute close (nothing about the decision changes), but every fill and every exit is then
resolved against the minute-by-minute path in the order it actually happened.

WHAT IS STILL ASSUMED, because 1-minute bars are not ticks: within a single minute a stop and a
target can still both be touched, and that residual is resolved stop-first and COUNTED, so the
remaining ambiguity is reported rather than hidden.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit


@njit(cache=True)
def _walk_1m(o1, h1, l1, c1, m1, start_idx, entry_px, stop_dist, tp_r, max_min, flat_mod,
             half_spread, slip_stop):
    """Resolve one trade on the minute path. Returns (R, why, ambiguous, minutes_held, filled)."""
    n = len(c1)
    j = start_idx
    entry = entry_px
    stop = entry - stop_dist
    target = entry + tp_r * stop_dist
    amb = 0
    while j < n and (j - start_idx) < max_min:
        hit = l1[j] <= stop
        won = h1[j] >= target
        if hit and won:
            amb = 1
        if hit:
            px = (o1[j] if o1[j] < stop else stop) - slip_stop - half_spread[j]
            return (px - entry) / stop_dist, 1, amb, j - start_idx, 1
        if won:
            px = (o1[j] if o1[j] > target else target) - half_spread[j]
            return (px - entry) / stop_dist, 2, amb, j - start_idx, 1
        if flat_mod > 0 and m1[j] >= flat_mod:
            px = c1[j] - half_spread[j]
            return (px - entry) / stop_dist, 3, amb, j - start_idx, 1
        j += 1
    jj = j if j < n else n - 1
    px = c1[jj] - half_spread[jj]
    return (px - entry) / stop_dist, 4, amb, jj - start_idx, 1


@njit(cache=True)
def run_live(o1, h1, l1, c1, m1, sig_min_idx, want_px, stop_dist,
             tp_r, wait_min, max_min, flat_mod, half_spread, slip_stop, commission):
    """For each 5-minute signal, rest a limit on the 1-minute path and manage the trade there."""
    k = len(sig_min_idx)
    R = np.zeros(k); why = np.zeros(k, np.int64); amb = np.zeros(k, np.uint8)
    filled = np.zeros(k, np.uint8); wait = np.zeros(k, np.int64); held = np.zeros(k, np.int64)
    n = len(c1)
    for t in range(k):
        s = sig_min_idx[t]
        if s <= 0 or s >= n - 2 or stop_dist[t] <= 0.0:
            continue
        want = want_px[t]
        j = s
        got = -1
        while j < n and (j - s) < wait_min:
            if l1[j] <= want:
                got = j
                break
            j += 1
        if got < 0:
            continue
        entry = (o1[got] if o1[got] < want else want) + half_spread[got]
        filled[t] = 1
        wait[t] = got - s
        r, w, a, hm, _f = _walk_1m(o1, h1, l1, c1, m1, got, entry, stop_dist[t], tp_r,
                                   max_min, flat_mod, half_spread, slip_stop)
        R[t] = r - commission / stop_dist[t]
        why[t] = w; amb[t] = a; held[t] = hm
    return R, filled, why, amb, wait, held


def perturb(R, n=20000, seed=13, price_sd=0.05, cost_scale=(0.75, 1.5), drop_frac=0.05):
    """Perturbation Monte Carlo: shock the FILLS and the COSTS, not just the order of trades.

    Three perturbations, applied together, because they are the ways this result could be wrong:
      price_sd    a per-trade shock in R units, standing for a fill worse than modelled
      cost_scale  a multiplicative cost shock drawn per PATH, standing for a mis-set spread
      drop_frac   randomly drop a fraction of trades, standing for missed or rejected fills
    """
    R = np.asarray(R, float)
    if len(R) < 30:
        return None
    rng = np.random.default_rng(seed)
    m = len(R)
    means = np.empty(n); dds = np.empty(n)
    base_cost = 0.02
    for i in range(n):
        idx = rng.random(m) >= drop_frac
        s = R[idx]
        if len(s) < 10:
            means[i] = np.nan; dds[i] = np.nan; continue
        s = s + rng.normal(0.0, price_sd, len(s))
        s = s - base_cost * rng.uniform(cost_scale[0], cost_scale[1])
        s = rng.permutation(s)
        eq = np.cumsum(s)
        means[i] = s.mean()
        dds[i] = np.max(np.maximum.accumulate(eq) - eq)
    means = means[np.isfinite(means)]; dds = dds[np.isfinite(dds)]
    return dict(paths=len(means), mean_p05=float(np.percentile(means, 5)),
                mean_p50=float(np.percentile(means, 50)),
                mean_p95=float(np.percentile(means, 95)),
                p_negative=float((means <= 0).mean()),
                dd_p50=float(np.percentile(dds, 50)),
                dd_p95=float(np.percentile(dds, 95)),
                dd_worst=float(dds.max()))
