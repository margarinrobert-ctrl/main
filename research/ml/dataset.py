"""Causal feature assembly and triple-barrier labels for 1-minute NQ.

Every column is computed from bars <= i and every fill is o[i+1]. The two mistakes this guards
against are the two that reversed a result in this repository within the last day:

  * a one-bar look-ahead (entering at o[i] on a signal known at bar i's close), which turned a
    -$95/trade effect into +$201/trade;
  * treating bars inside a session as independent, which turned t = -2.70 into t = +5.60.

The label is the MaxAI barrier used as a ruler: from each bar, the dollar outcome of a position
opened at the next open and closed at a stop, a target, or the session close -- whichever comes
first. It carries costs, so a model that cannot beat them shows a negative number rather than a
flattering AUC.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, "research")
import smc
from nqdata import load_bars, minute_of_day, minutes_since_open, session_index, session_slice

POINT_VALUE = 20.0
ROUND_TURN = 19.00          # 1 tick spread + 1 tick slippage per side + $4 commission
RTH_START, RTH_END = 570, 960


@njit(cache=True)
def barrier_points(o, h, l, c, sess, stop_pts, tgt_pts):
    """Long-side POINTS for a position opened at o[i+1], closed at stop/target/session close.

    Also returns the bar index of the exit, which the caller needs to set the purge horizon
    honestly rather than guessing it.
    """
    n = len(c)
    out = np.full(n, np.nan)
    exit_i = np.full(n, -1, np.int64)
    for i in range(n - 1):
        if sess[i + 1] != sess[i]:
            continue
        entry = o[i + 1]
        sp = entry - stop_pts
        tp = entry + tgt_pts
        res = np.nan
        j = i + 1
        while j < n and sess[j] == sess[i + 1]:
            if l[j] <= sp:
                res = -stop_pts
                break
            if h[j] >= tp:
                res = tgt_pts
                break
            j += 1
        if np.isnan(res):
            res = c[j - 1] - entry if j > i + 1 else 0.0
            j = j - 1
        out[i] = res
        exit_i[i] = j
    return out, exit_i


def _rolling(a, n, fn="mean"):
    s = pd.Series(a)
    r = s.rolling(n)
    return (r.mean() if fn == "mean" else r.std() if fn == "std" else r.sum()).to_numpy()


def build(path="data/NQ_1m.csv", stop_dollars=900.0, target_dollars=1500.0, atr_len=30, pivot_k=3):
    """Return (X, y_dollars, meta) where meta carries session id, timestamps and the exit bar."""
    seg = session_slice(load_bars(path), RTH_START, RTH_END)
    o = seg["open"].to_numpy(float); h = seg["high"].to_numpy(float)
    l = seg["low"].to_numpy(float);  c = seg["close"].to_numpy(float)
    v = seg["volume"].to_numpy(float)
    sess = session_index(seg.index, RTH_START)
    mod = minute_of_day(seg.index)
    mso = minutes_since_open(mod, RTH_START).astype(float)
    n = len(c)

    atr = smc.atr_series(h, l, c, atr_len)
    ph, pl, phi, pli = smc.swing_pivots(h, l, pivot_k)
    bos, choch, bias, sbos, schoch = smc.structure(c, ph, pl)
    dup, sup, ddn, sdn = smc.fair_value_gaps(h, l, atr)
    sweep, ssweep = smc.liquidity_sweeps(h, l, c, ph, pl)
    pos = smc.dealing_range(c, ph, pl)
    obd = smc.order_block_distance(o, c, h, l, bos, atr)

    # --- session VWAP, causal, reset daily ---
    tp_ = (h + l + c) / 3
    vwap = np.empty(n)
    cum_pv = cum_v = 0.0
    cur = -1
    for i in range(n):
        if sess[i] != cur:
            cur = sess[i]; cum_pv = cum_v = 0.0
        cum_pv += tp_[i] * v[i]; cum_v += v[i]
        vwap[i] = cum_pv / cum_v if cum_v > 0 else np.nan

    # --- opening range (first 30 min), usable only after it closes ---
    or_hi = np.full(n, np.nan); or_lo = np.full(n, np.nan)
    hi = -np.inf; lo = np.inf; cur = -1
    for i in range(n):
        if sess[i] != cur:
            cur = sess[i]; hi = -np.inf; lo = np.inf
        if mso[i] < 30:
            hi = max(hi, h[i]); lo = min(lo, l[i])
        elif hi > -np.inf:
            or_hi[i] = hi; or_lo[i] = lo

    # --- Chaikin Money Flow, the MaxAI feature ---
    rng = h - l
    mfm = np.where(rng > 0, ((c - l) - (h - c)) / np.where(rng > 0, rng, 1.0), 0.0)
    cmf20 = _rolling(mfm * v, 20, "sum") / np.where(_rolling(v, 20, "sum") > 0, _rolling(v, 20, "sum"), np.nan)

    logc = np.log(c)
    feats = {
        # --- price ---
        "ret_1": np.diff(logc, prepend=logc[0]),
        "ret_5": logc - np.roll(logc, 5),
        "ret_15": logc - np.roll(logc, 15),
        "ret_60": logc - np.roll(logc, 60),
        "rvol_30": _rolling(np.diff(logc, prepend=logc[0]), 30, "std"),
        "rvol_ratio": _rolling(np.diff(logc, prepend=logc[0]), 30, "std") /
                      np.where(_rolling(np.diff(logc, prepend=logc[0]), 240, "std") > 0,
                               _rolling(np.diff(logc, prepend=logc[0]), 240, "std"), np.nan),
        "atr_rel": atr / c,
        "bar_range_rel": (h - l) / np.where(atr > 0, atr, np.nan),
        "close_in_bar": np.where(rng > 0, (c - l) / np.where(rng > 0, rng, 1.0), 0.5),
        # --- location ---
        "vwap_dist": (c - vwap) / np.where(atr > 0, atr, np.nan),
        "or_pos": (c - or_lo) / np.where(or_hi - or_lo > 0, or_hi - or_lo, np.nan),
        "range_pos": pos,
        # --- volume ---
        "vol_rel": v / np.where(_rolling(v, 60) > 0, _rolling(v, 60), np.nan),
        "cmf_20": cmf20,
        # --- clock ---
        "mso": mso,
        "sin_tod": np.sin(2 * np.pi * mso / 390),
        "cos_tod": np.cos(2 * np.pi * mso / 390),
        # --- smart money concepts ---
        "bias": bias.astype(float),
        "bos": bos.astype(float),
        "choch": choch.astype(float),
        "bars_since_bos": np.minimum(sbos, 500).astype(float),
        "bars_since_choch": np.minimum(schoch, 500).astype(float),
        "sweep": sweep.astype(float),
        "bars_since_sweep": np.minimum(ssweep, 500).astype(float),
        "fvg_dist_up": np.minimum(dup, 99.0),
        "fvg_dist_dn": np.minimum(ddn, 99.0),
        "fvg_size_up": sup,
        "fvg_size_dn": sdn,
        "ob_dist": obd,
    }
    X = pd.DataFrame(feats)

    # ---- absence is information, not a reason to drop the row ----------------------------------
    # A fair-value gap exists on roughly 30% of bars; an opening-range position does not exist
    # before 10:00. Encoding "no live gap" as NaN and dropping incomplete rows requires an unfilled
    # gap on BOTH sides at once and silently cuts 292,908 bars to 4,347 -- 1.5% of the sample, and a
    # badly biased 1.5%. This is the identical mistake that cut the SMC study to 6,091 bars. Each
    # optional feature therefore gets a presence FLAG and a sentinel, and nothing is dropped for it.
    OPTIONAL = {
        "fvg_dist_up": 99.0, "fvg_dist_dn": 99.0, "fvg_size_up": 0.0, "fvg_size_dn": 0.0,
        "or_pos": 0.5, "range_pos": 0.5, "rvol_ratio": 1.0,
    }
    for col, sentinel in OPTIONAL.items():
        X[f"has_{col}"] = X[col].notna().astype(float)
        X[col] = X[col].fillna(sentinel)

    X.iloc[:60] = np.nan          # warm-up for the longest rolling window used above

    stop_pts = stop_dollars / POINT_VALUE
    tgt_pts = target_dollars / POINT_VALUE
    pts, exit_i = barrier_points(o, h, l, c, sess, stop_pts, tgt_pts)
    y_dollars = pts * POINT_VALUE - ROUND_TURN

    meta = pd.DataFrame({
        "ts": seg.index,
        "sess": sess,
        "mso": mso,
        "exit_i": exit_i,
        "bars_held": np.where(exit_i >= 0, exit_i - np.arange(n), np.nan),
        "long_dollars": y_dollars,
        "short_dollars": -pts * POINT_VALUE - ROUND_TURN,
    })

    # After the sentinel pass the only legitimate NaN is the warm-up block, so a row is dropped
    # only for a missing LABEL or an unwarmed feature -- never for an absent optional signal.
    good = np.isfinite(y_dollars) & X.notna().all(axis=1).to_numpy()
    return X[good].reset_index(drop=True), y_dollars[good], meta[good].reset_index(drop=True)


if __name__ == "__main__":
    X, y, meta = build()
    print(f"{len(X):,} rows x {X.shape[1]} features over {meta.sess.nunique()} sessions")
    print(f"label: long ${y.mean():.2f}/trade, short ${meta.short_dollars.mean():.2f}/trade, "
          f"win {100*(y>0).mean():.1f}%")
    print(f"median bars held {meta.bars_held.median():.0f}, 95th pct {meta.bars_held.quantile(.95):.0f}")
    print("features:", ", ".join(X.columns))
