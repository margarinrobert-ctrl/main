"""371,520 configurations: the trend-day family with a Donchian channel added three ways.

THE QUESTION. Section 12's frontier tops out at profit factor 1.41 / 1.28 / 1.20 at three, five and
eight times the shipped entry count. Can a Donchian channel push any of those rungs higher?

THE THREE USES, all causal and all at SESSION scale (a Donchian over the n COMPLETED sessions before
the one being judged):
  GATE   the qualifying session must have CLOSED at the extreme of its own recent range -- an up
         trend day in the top `dc_gate` of its channel, a down day in the bottom. This is the
         structural reading of "trend day" that the |close-open|/range ratio only approximates.
  STOP   the fade is cut if price breaks the channel AGAINST it, at the extreme or a fraction of the
         channel width beyond. The study found the entire downside is 9% of trades that never reach
         the target, so a structural stop is the one addition aimed at the actual risk.
  TARGET the fade can aim at the channel MIDPOINT instead of the live EMA. The direction still comes
         from the EMA; a mid on the wrong side of the open is skipped rather than inverted.

Adding axes to a search that already failed is how false positives are manufactured, so the gates
are unchanged from section 12: selection on RESEARCH only, scored by the WORST of the three long
feeds, a coherence requirement over every axis neighbour, and ONE read of the reserved blocks with
the multiplicity stated.
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
import td_core as T   # noqa: E402
import td_sweep as S  # noqa: E402

OUT = "results/trendday"
RTH_MIN = 390

GRID = dict(
    ema=(10, 15, 20, 25),
    trend_pct=(0.0, 40.0, 50.0, 60.0, 70.0),
    max_touch=(0, 1, 2, 3, 6, 99),
    min_gap=(0.0, 0.10),
    target_frac=(0.5, 0.75, 1.0),
    max_hold=(0, 16),
    flat_frac=(0.75, 1.0),
    dc_len=(0, 5, 10, 20, 55),
    dc_gate=(0.0, 0.70, 0.85, 0.95),
    dc_stop=(0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5),   # 0 off; 1.0 the extreme itself;
                                        # BELOW 1.0 the stop sits INSIDE the channel and can fire,
                                        # above it sits beyond and only filters the entry
    tgt_mode=(0, 1),                    # 0 the live EMA, 1 the Donchian midpoint
)
AXES = list(GRID)
BUCKET = 15


def session_ohlc(D):
    """Per-session open, high, low, close and the first bar index."""
    n_sess = D["n_sess"]
    o, h, l, c, si = D["o"], D["h"], D["l"], D["c"], D["si"]
    s_o = np.full(n_sess, np.nan); s_h = np.full(n_sess, -np.inf)
    s_l = np.full(n_sess, np.inf); s_c = np.full(n_sess, np.nan)
    first = np.full(n_sess, -1, np.int64)
    for i in range(len(c)):
        s = si[i]
        if s < 0:
            continue
        if first[s] < 0:
            first[s] = i
            s_o[s] = o[i]
        s_h[s] = max(s_h[s], h[i])
        s_l[s] = min(s_l[s], l[i])
        s_c[s] = c[i]
    return s_o, s_h, s_l, s_c, first


def donchian(s_h, s_l, n):
    """DC over the n sessions BEFORE each session. NaN until n sessions exist."""
    m = len(s_h)
    hi = np.full(m, np.nan); lo = np.full(m, np.nan)
    for s in range(n, m):
        hi[s] = s_h[s - n:s].max()
        lo[s] = s_l[s - n:s].min()
    return hi, lo


@njit(cache=True)
def trade_walk_dc(o, h, l, c, s_start, s_len, qual, ema_in, ema_after, contiguous, tf,
                  side_cost, min_gap, target_frac, max_hold, flat_off, dc_hi, dc_lo,
                  dc_stop, tgt_mode, block, out_pts, out_sess, out_why):
    """The section-12 walk plus a Donchian stop and an optional Donchian-midpoint target.
    why: 1 target, 2 clock, 3 max hold, 4 DONCHIAN STOP."""
    n_sess = len(s_start)
    n_bkt = ema_after.shape[1]
    k = 0
    for s in range(1, n_sess):
        if s_start[s] < 0 or not qual[s - 1] or not contiguous[s]:
            continue
        anchor0 = ema_in[s]
        if np.isnan(anchor0):
            continue
        i0 = s_start[s]
        m = s_len[s]
        if m < 2:
            continue
        base = o[i0]
        if base <= 0:
            continue
        side = -1 if base > anchor0 else (1 if base < anchor0 else 0)
        if side == 0:
            continue
        # the target anchor: the live EMA, or the Donchian midpoint held static
        use_dc_tgt = tgt_mode == 1
        if use_dc_tgt:
            if np.isnan(dc_hi[s]) or np.isnan(dc_lo[s]):
                continue
            tanchor = 0.5 * (dc_hi[s] + dc_lo[s])
            # a midpoint on the wrong side of the open is not a target; skip rather than invert
            if (side == 1 and tanchor <= base) or (side == -1 and tanchor >= base):
                continue
        else:
            tanchor = anchor0
        gap = abs(tanchor - base)
        if gap / base * 100.0 < min_gap:
            continue
        tgt0 = base + target_frac * (tanchor - base)
        # the Donchian stop, against the fade
        stop = np.nan
        if dc_stop > 0.0:
            if np.isnan(dc_hi[s]) or np.isnan(dc_lo[s]):
                continue
            w = dc_hi[s] - dc_lo[s]
            if w <= 0:
                continue
            stop = dc_lo[s] - (dc_stop - 1.0) * w if side == 1 else dc_hi[s] + (dc_stop - 1.0) * w
            # a stop already breached at the open is not a trade
            if (side == 1 and base <= stop) or (side == -1 and base >= stop):
                continue
        e_px = o[i0] + side * side_cost
        target = tgt0
        pnl = np.nan
        why = 0
        for p in range(0, m):
            b = i0 + p
            ob = p * tf
            bkt = ob // BUCKET
            if dc_stop > 0.0:
                if (side == 1 and l[b] <= stop) or (side == -1 and h[b] >= stop):
                    pnl = (stop - e_px) * side - side_cost
                    why = 4
                    break
            if (side == 1 and h[b] >= target) or (side == -1 and l[b] <= target):
                pnl = (target - e_px) * side - side_cost
                why = 1
                break
            if max_hold > 0 and bkt >= max_hold:
                pnl = (c[b] - e_px) * side - side_cost
                why = 3
                break
            if ob >= flat_off:
                pnl = (c[b] - e_px) * side - side_cost
                why = 2
                break
            if not use_dc_tgt and (ob % BUCKET) == (BUCKET - tf) and bkt < n_bkt:
                a = ema_after[s, bkt]
                if not np.isnan(a):
                    target = base + target_frac * (a - base)
        if np.isnan(pnl):
            b = i0 + m - 1
            pnl = (c[b] - e_px) * side - side_cost
            why = 2
        if block[s] > 0 and k < len(out_pts):
            out_pts[k] = pnl
            out_sess[k] = s
            out_why[k] = why
            k += 1
    return k


def gate_mask(s_o, s_c, dc_hi, dc_lo, g):
    """Did the session close at the extreme of its own recent channel, in its own direction?"""
    if g <= 0:
        return np.ones(len(s_c), np.bool_)
    w = dc_hi - dc_lo
    with np.errstate(invalid="ignore", divide="ignore"):
        pos = (s_c - dc_lo) / np.where(w > 0, w, np.nan)
    up = s_c > s_o
    ok = np.where(up, pos >= g, pos <= 1.0 - g)
    return np.nan_to_num(ok, nan=False).astype(np.bool_)


def sweep(market, tf=15, verbose=True):
    D = T.prep(market, tf_override=tf)
    ids, names = S.block_ids(D)
    n_sess = D["n_sess"]
    s_o, s_h, s_l, s_c, _ = session_ohlc(D)
    dc = {0: (np.full(n_sess, np.nan), np.full(n_sess, np.nan))}
    for n in GRID["dc_len"]:
        if n > 0:
            dc[n] = donchian(s_h, s_l, n)
    cap = np.zeros(40000); caps = np.zeros(40000, np.int64); cwhy = np.zeros(40000, np.int64)
    rows = []
    t0 = time.time()
    for ema_n in GRID["ema"]:
        st = S.day_stats(D["o"], D["h"], D["l"], D["c"], D["off"], D["si"], D["contiguous"],
                         tf, ema_n, BUCKET, n_sess)
        s_start, s_len, complete, observable, touch, ratio, ema_in, ema_after = st
        base_ok = complete & observable
        for dc_len in GRID["dc_len"]:
            dhi, dlo = dc[dc_len]
            gates = [0.0] if dc_len == 0 else GRID["dc_gate"]
            stops = [0.0] if dc_len == 0 else GRID["dc_stop"]
            modes = [0] if dc_len == 0 else GRID["tgt_mode"]
            for dc_g in gates:
                gm = gate_mask(s_o, s_c, dhi, dlo, dc_g)
                for trend_pct, max_touch in itertools.product(GRID["trend_pct"], GRID["max_touch"]):
                    qual = base_ok & (touch <= max_touch) & (ratio >= trend_pct) & gm
                    if qual.sum() < 5:
                        continue
                    for dc_s, tmode, min_gap, tfrac, mhold, ffrac in itertools.product(
                            stops, modes, GRID["min_gap"], GRID["target_frac"],
                            GRID["max_hold"], GRID["flat_frac"]):
                        k = trade_walk_dc(D["o"], D["h"], D["l"], D["c"], s_start, s_len, qual,
                                          ema_in, ema_after, D["contiguous"], tf, D["side"],
                                          min_gap, tfrac, mhold, int(RTH_MIN * ffrac), dhi, dlo,
                                          dc_s, tmode, ids, cap, caps, cwhy)
                        if k == 0:
                            continue
                        p = cap[:k]; b = ids[caps[:k]]; wy = cwhy[:k]
                        r = dict(ema=ema_n, trend_pct=trend_pct, max_touch=max_touch,
                                 min_gap=min_gap, target_frac=tfrac, max_hold=mhold,
                                 flat_frac=ffrac, dc_len=dc_len, dc_gate=dc_g, dc_stop=dc_s,
                                 tgt_mode=tmode)
                        for bi, nm in enumerate(names, start=1):
                            q = p[b == bi]
                            if len(q) == 0:
                                r[f"{nm}_n"] = 0; r[f"{nm}_pf"] = np.nan
                                r[f"{nm}_mean"] = np.nan; r[f"{nm}_win"] = np.nan
                                continue
                            w = q > 0
                            r[f"{nm}_n"] = len(q)
                            r[f"{nm}_pf"] = q[w].sum() / max(1e-9, -q[~w].sum())
                            r[f"{nm}_mean"] = q.mean()
                            r[f"{nm}_win"] = w.mean()
                        r["stop_share"] = float((wy == 4).mean())
                        r["clock_share"] = float((wy == 2).mean())
                        rows.append(r)
    g = pd.DataFrame(rows)
    g.to_csv(f"{OUT}/dc_{market}.csv", index=False)
    if verbose:
        print(f"  {market}: {len(g):,} cells in {time.time()-t0:.0f}s")
    return g


if __name__ == "__main__":
    sweep(sys.argv[1] if len(sys.argv) > 1 else "NQ")
