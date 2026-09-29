"""A 127,008-configuration sweep of the trend-day family, selected on RESEARCH ONLY.

WHY IT IS TWO PHASES. The day filter -- the continuous cross-session EMA, its resets, the causal
per-bucket touch test, the session trend ratio -- depends only on (EMA period, bucket length), so it
is walked ONCE per pair and cached as per-session statistics plus the EMA after every bucket. Every
other axis then costs a walk over the QUALIFIED sessions' bars only, roughly 1% of the file. Same
trick as `research/v14/v14tensor.py`.

THE ASK. Five times the shipped entry count at a profit factor near 2, holding on every market. The
shipped rule takes ~5% of sessions, so 5x means trading about a QUARTER of all sessions. Its own
loosenings already price that: dropping the untouched filter gives 3.3x at PF 1.57 and dropping both
gives 17x at PF 0.96. The sweep exists to test whether some combination does better than that line,
not to assume it does.

THE PROCEDURE. Every cell is scored on the research block of all three long feeds. Selection uses the
MINIMUM across feeds, so a cell must work everywhere rather than average out. Reserved blocks are
read once, for the survivors only, with the multiplicity stated. Grid-share and top-1000 consensus
are reported before any single row.
"""
from __future__ import annotations

import itertools
import os
import sys
import time

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, os.path.dirname(__file__))
import td_core as T  # noqa: E402

OUT = "results/trendday"
RTH_MIN = 390

GRID = dict(
    ema=(10, 15, 20, 25, 30, 40, 50),
    bucket=(15, 30),
    trend_pct=(0.0, 40.0, 50.0, 60.0, 70.0, 75.0, 80.0),
    max_touch=(0, 1, 2, 3, 6, 99),
    min_gap=(0.0, 0.10, 0.20, 0.35),
    target_frac=(0.5, 0.75, 1.0),
    stop_gap=(0.0, 1.0, 2.0),
    max_hold=(0, 8, 16),
    flat_frac=(0.75, 1.0),
)
AXES = list(GRID)
DAY_AXES = ("ema", "bucket")
TRADE_AXES = tuple(a for a in AXES if a not in DAY_AXES)


# ---------------------------------------------------------------- phase 1: the day filter
@njit(cache=True)
def day_stats(o, h, l, c, off, si, contiguous, tf, ema_n, bucket, n_sess):
    """One sequential walk. Per session: the bar range, completeness, the touch COUNT (not just a
    flag), the trend ratio, the EMA carried in, and the EMA after each completed bucket."""
    n = len(c)
    n_bar = RTH_MIN // tf
    n_bkt = RTH_MIN // bucket
    per_bkt = bucket // tf
    s_start = np.full(n_sess, -1, np.int64)
    s_len = np.zeros(n_sess, np.int64)
    complete = np.zeros(n_sess, np.bool_)
    observable = np.ones(n_sess, np.bool_)
    touch = np.zeros(n_sess, np.int64)
    ratio = np.zeros(n_sess)
    ema_in = np.full(n_sess, np.nan)
    ema_after = np.full((n_sess, n_bkt), np.nan)

    ema = np.nan; seed_sum = 0.0; seed_k = 0; ready = False
    i = 0
    while i < n:
        s = si[i]
        if s < 0:
            i += 1
            continue
        j = i
        while j < n and si[j] == s:
            j += 1
        m = j - i
        if s > 0 and not contiguous[s]:
            ema = np.nan; seed_sum = 0.0; seed_k = 0; ready = False
        s_start[s] = i
        s_len[s] = m
        ema_in[s] = ema if ready else np.nan
        ok = (m == n_bar)
        s_open = o[i]; s_hi = h[i]; s_lo = l[i]; s_cl = c[i]
        bkt_bars = 0; bkt_hi = -1e18; bkt_lo = 1e18; bkt_cl = 0.0; nb = 0
        for t in range(m):
            b = i + t
            if off[b] != t * tf:
                ok = False
            if h[b] > s_hi:
                s_hi = h[b]
            if l[b] < s_lo:
                s_lo = l[b]
            s_cl = c[b]
            if h[b] > bkt_hi:
                bkt_hi = h[b]
            if l[b] < bkt_lo:
                bkt_lo = l[b]
            bkt_cl = c[b]
            bkt_bars += 1
            if (off[b] % bucket) == (bucket - tf):
                if bkt_bars == per_bkt:
                    if not ready:
                        observable[s] = False
                    elif bkt_lo <= ema and ema <= bkt_hi:
                        touch[s] += 1
                    if not ready:
                        if seed_k < ema_n:
                            seed_sum += bkt_cl
                            seed_k += 1
                        if seed_k == ema_n:
                            ema = seed_sum / ema_n
                            ready = True
                    else:
                        a = 2.0 / (ema_n + 1.0)
                        ema = a * bkt_cl + (1.0 - a) * ema
                    if nb < n_bkt:
                        ema_after[s, nb] = ema if ready else np.nan
                    nb += 1
                else:
                    ok = False
                bkt_bars = 0; bkt_hi = -1e18; bkt_lo = 1e18
        if nb != n_bkt:
            ok = False
        rng = s_hi - s_lo
        ratio[s] = 100.0 * abs(s_cl - s_open) / rng if rng > 0 else 0.0
        complete[s] = ok and rng > 0
        if not ok:
            ema = np.nan; seed_sum = 0.0; seed_k = 0; ready = False
        i = j
    return s_start, s_len, complete, observable, touch, ratio, ema_in, ema_after


# ---------------------------------------------------------------- phase 2: the trade walk
@njit(cache=True)
def trade_walk(o, h, l, c, s_start, s_len, qual, ema_in, ema_after, contiguous, tf, bucket,
               entry_off, side_cost, min_gap, target_frac, stop_gap, max_hold, flat_off,
               block, out_pts, out_sess):
    """Walk only the sessions that can trade. block: per-session block id, 0 = skip."""
    n_sess = len(s_start)
    n_bkt = ema_after.shape[1]
    fill_pos = entry_off // tf
    k = 0
    for s in range(1, n_sess):
        if s_start[s] < 0 or not qual[s - 1] or not contiguous[s]:
            continue
        anchor0 = ema_in[s]
        if np.isnan(anchor0):
            continue
        i0 = s_start[s]
        m = s_len[s]
        if fill_pos >= m:
            continue
        base = o[i0]
        if base <= 0:
            continue
        gap = abs(anchor0 - base)
        if gap / base * 100.0 < min_gap:
            continue
        side = -1 if base > anchor0 else (1 if base < anchor0 else 0)
        if side == 0:
            continue
        tgt0 = base + target_frac * (anchor0 - base)
        skip = False
        for p in range(fill_pos):
            b = i0 + p
            if (side == 1 and h[b] >= tgt0) or (side == -1 and l[b] <= tgt0):
                skip = True
                break
        if skip:
            continue
        fb = i0 + fill_pos
        e_px = o[fb] + side * side_cost
        stop = e_px - side * stop_gap * gap if stop_gap > 0.0 else np.nan
        target = tgt0
        entry_bkt = (fill_pos * tf) // bucket
        pnl = np.nan
        for p in range(fill_pos, m):
            b = i0 + p
            ob = p * tf
            bkt = ob // bucket
            if stop_gap > 0.0:
                if (side == 1 and l[b] <= stop) or (side == -1 and h[b] >= stop):
                    pnl = (stop - e_px) * side - side_cost
                    break
            if (side == 1 and h[b] >= target) or (side == -1 and l[b] <= target):
                pnl = (target - e_px) * side - side_cost
                break
            if max_hold > 0 and (bkt - entry_bkt) >= max_hold:
                pnl = (c[b] - e_px) * side - side_cost
                break
            if ob >= flat_off:
                pnl = (c[b] - e_px) * side - side_cost
                break
            # the target trails the EMA once a bucket completes
            if (ob % bucket) == (bucket - tf) and bkt < n_bkt:
                a = ema_after[s, bkt]
                if not np.isnan(a):
                    target = base + target_frac * (a - base)
        if np.isnan(pnl):
            b = i0 + m - 1
            pnl = (c[b] - e_px) * side - side_cost
        if block[s] > 0 and k < len(out_pts):
            out_pts[k] = pnl
            out_sess[k] = s
            k += 1
    return k


def block_ids(D):
    """Per-session block id: 1 research, 2 validation/locked, 3 test, 0 not used."""
    B = T.blocks(D)
    names = list(B)
    ids = np.zeros(D["n_sess"], np.int64)
    first_bar = np.full(D["n_sess"], -1, np.int64)
    si = D["si"]
    for i in range(len(si)):
        s = si[i]
        if s >= 0 and first_bar[s] < 0:
            first_bar[s] = i
    for bi, nm in enumerate(names, start=1):
        m = B[nm]
        ok = first_bar >= 0
        ids[ok & m[np.where(first_bar >= 0, first_bar, 0)]] = bi
    return ids, names


def sweep(market, tf=15, verbose=True):
    D = T.prep(market, tf_override=tf)
    ids, names = block_ids(D)
    n_sess = D["n_sess"]
    cap = np.zeros(20000)
    caps = np.zeros(20000, np.int64)
    rows = []
    t0 = time.time()
    for ema_n, bucket in itertools.product(GRID["ema"], GRID["bucket"]):
        st = day_stats(D["o"], D["h"], D["l"], D["c"], D["off"], D["si"], D["contiguous"],
                       tf, ema_n, bucket, n_sess)
        s_start, s_len, complete, observable, touch, ratio, ema_in, ema_after = st
        base_ok = complete & observable
        for trend_pct, max_touch in itertools.product(GRID["trend_pct"], GRID["max_touch"]):
            qual = base_ok & (touch <= max_touch) & (ratio >= trend_pct)
            if qual.sum() < 5:
                continue
            for min_gap, tfrac, sgap, mhold, ffrac in itertools.product(
                    GRID["min_gap"], GRID["target_frac"], GRID["stop_gap"], GRID["max_hold"],
                    GRID["flat_frac"]):
                k = trade_walk(D["o"], D["h"], D["l"], D["c"], s_start, s_len, qual, ema_in,
                               ema_after, D["contiguous"], tf, bucket, 0, D["side"], min_gap,
                               tfrac, sgap, mhold, int(RTH_MIN * ffrac), ids, cap, caps)
                if k == 0:
                    continue
                p = cap[:k]
                b = ids[caps[:k]]
                r = dict(ema=ema_n, bucket=bucket, trend_pct=trend_pct, max_touch=max_touch,
                         min_gap=min_gap, target_frac=tfrac, stop_gap=sgap, max_hold=mhold,
                         flat_frac=ffrac)
                for bi, nm in enumerate(names, start=1):
                    q = p[b == bi]
                    if len(q) == 0:
                        r[f"{nm}_n"] = 0; r[f"{nm}_pf"] = np.nan; r[f"{nm}_mean"] = np.nan
                        r[f"{nm}_net"] = 0.0; r[f"{nm}_win"] = np.nan
                        continue
                    w = q > 0
                    r[f"{nm}_n"] = len(q)
                    r[f"{nm}_pf"] = q[w].sum() / max(1e-9, -q[~w].sum())
                    r[f"{nm}_mean"] = q.mean()
                    r[f"{nm}_net"] = q.sum()
                    r[f"{nm}_win"] = w.mean()
                rows.append(r)
    g = pd.DataFrame(rows)
    g.to_csv(f"{OUT}/sweep_{market}.csv", index=False)
    if verbose:
        print(f"  {market}: {len(g):,} cells in {time.time()-t0:.0f}s -> {OUT}/sweep_{market}.csv")
    return g


if __name__ == "__main__":
    m = sys.argv[1] if len(sys.argv) > 1 else "NQ"
    sweep(m)
