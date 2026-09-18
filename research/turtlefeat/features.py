"""Turtle-derived features for short-horizon intraday prediction. Causal by construction.

DESIGN RULES, all of which exist because this branch has been burned by their absence.

CAUSALITY. Every feature at bar i uses bars <= i only. Rolling extrema are computed on the
CLOSED window ending at i-1 where the concept is "the channel price must break", because a
channel that includes the current bar's own high can never be broken by it. `audit()` recomputes
every column on history truncated at i and requires an exact match; that test caught a real
look-ahead in `STUDY_SCALP_TREND.md` that inspection had missed.

SCALE-FREE. Nothing is expressed in price units. Distances are divided by ATR, widths by price,
counts by their window. A feature that means different things on a 1.1 EURUSD and a 66,000 BTC
cannot be pooled, and pooling is the whole point of a multi-market model.

NO INDICATOR ZOO. The 20/55/10 windows are HYPOTHESES, not constants -- each family is emitted at
several windows so the model can say which matters. Nothing outside the Turtle concept set is
included: RSI, MACD, Stochastic and CCI are deliberately absent and are only to be added if the
redundancy and incremental-information tests show Turtle features leave something on the table.

THE FAMILIES, matching the brief:
  channel     distance to N-bar high/low in ATR, position within the channel, channel width and
              its expansion, bars since the extreme was set
  breakout    state, magnitude, persistence, time since, false-breakout and retest behaviour
  N           true range, ATR at several spans, ATR percentile, short/long ATR ratio, expansion,
              acceleration, volatility regime
  risk        distance to 1N/2N/3N, risk-normalised momentum, volatility relative to entry
  trend       higher-high/lower-low structure, breakout sequence, slope in ATR units, rolling
              return consistency, directional persistence, distance to and slope of moving
              averages, multi-timeframe alignment
  session     minutes since open and to close, session bucket, time-of-day relative volume and
              volatility, opening-range position and breakout
  volume      relative volume, acceleration, volume during breakout, price move per unit volume
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CH_WINDOWS = (10, 20, 55)
ATR_SPANS = (5, 14, 50)
MA_SPANS = (20, 50, 200)
RET_SPANS = (3, 6, 12, 24)


def _roll_max(x, n):
    return pd.Series(x).rolling(n, min_periods=n).max().to_numpy()


def _roll_min(x, n):
    return pd.Series(x).rolling(n, min_periods=n).min().to_numpy()


def _ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def _shift(x, k=1):
    out = np.full_like(np.asarray(x, float), np.nan)
    if k < len(out):
        out[k:] = np.asarray(x, float)[:-k]
    return out


def _bars_since(mask):
    """Bars since `mask` was last True, counted causally. NaN before the first occurrence."""
    m = np.asarray(mask, bool)
    out = np.full(len(m), np.nan)
    last = -1
    for i in range(len(m)):
        if last >= 0:
            out[i] = i - last
        if m[i]:
            last = i
    return out


def build(o, h, l, c, v, idx, session_open=570, session_close=960):
    """All features for one instrument at one timeframe. Returns {name: array}."""
    o, h, l, c, v = (np.asarray(x, float) for x in (o, h, l, c, v))
    ix = pd.DatetimeIndex(idx)
    n = len(c)
    F = {}

    pc = _shift(c, 1)
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    tr[0] = h[0] - l[0]
    atr = {s: _ema(tr, s) for s in ATR_SPANS}
    a = atr[14]
    safe = np.where(a > 0, a, np.nan)

    # ---------------------------------------------------------------- N / volatility
    F["tr_over_atr"] = tr / safe
    for s in ATR_SPANS:
        F[f"atr{s}_over_price"] = atr[s] / c
    F["atr_ratio_short_long"] = atr[5] / np.where(atr[50] > 0, atr[50], np.nan)
    F["atr_expansion"] = a / np.where(_shift(a, 12) > 0, _shift(a, 12), np.nan) - 1.0
    F["atr_accel"] = F["atr_expansion"] - _shift(F["atr_expansion"], 12)
    rel = pd.Series(a / c)
    F["atr_pctile_250"] = rel.rolling(250, min_periods=50).rank(pct=True).to_numpy()
    F["atr_pctile_1000"] = rel.rolling(1000, min_periods=200).rank(pct=True).to_numpy()
    F["vol_regime"] = np.where(np.isnan(F["atr_pctile_250"]), np.nan,
                               np.digitize(np.nan_to_num(F["atr_pctile_250"], nan=-1),
                                           [0.0, 0.33, 0.67]) - 1.0)

    # ---------------------------------------------------------------- channel geometry
    for w in CH_WINDOWS:
        hi = _shift(_roll_max(h, w), 1)          # closed window: breakable by the current bar
        lo = _shift(_roll_min(l, w), 1)
        width = hi - lo
        F[f"dist_high{w}_atr"] = (c - hi) / safe
        F[f"dist_low{w}_atr"] = (c - lo) / safe
        F[f"chan{w}_pos"] = np.where(width > 0, (c - lo) / width, np.nan)
        F[f"chan{w}_width_atr"] = width / safe
        F[f"chan{w}_width_pct"] = width / c
        F[f"chan{w}_expansion"] = width / np.where(_shift(width, w) > 0, _shift(width, w), np.nan) - 1.0
        F[f"bars_since_high{w}"] = _bars_since(h >= _shift(_roll_max(h, w), 1)) / w
        F[f"bars_since_low{w}"] = _bars_since(l <= _shift(_roll_min(l, w), 1)) / w

        # ------------------------------------------------------------ breakout behaviour
        up = h >= hi
        dn = l <= lo
        F[f"brk{w}_up"] = up.astype(float)
        F[f"brk{w}_dn"] = dn.astype(float)
        F[f"brk{w}_mag_up"] = np.where(up, (h - hi) / safe, 0.0)
        F[f"brk{w}_mag_dn"] = np.where(dn, (lo - l) / safe, 0.0)
        F[f"brk{w}_since_up"] = _bars_since(up) / w
        F[f"brk{w}_since_dn"] = _bars_since(dn) / w
        F[f"brk{w}_persist_up"] = pd.Series(up.astype(float)).rolling(w, min_periods=1).sum().to_numpy() / w
        F[f"brk{w}_persist_dn"] = pd.Series(dn.astype(float)).rolling(w, min_periods=1).sum().to_numpy() / w
        # a FALSE breakout: broke out, then closed back inside the channel on the same bar
        F[f"brk{w}_false_up"] = (up & (c < hi)).astype(float)
        F[f"brk{w}_false_dn"] = (dn & (c > lo)).astype(float)
        F[f"brk{w}_false_rate_up"] = (pd.Series((up & (c < hi)).astype(float))
                                      .rolling(w * 3, min_periods=w).mean().to_numpy())
        # a RETEST: broke out within the last w bars, and price has returned to the level
        rec_up = pd.Series(up.astype(float)).rolling(w, min_periods=1).max().to_numpy() > 0
        F[f"brk{w}_retest_up"] = (rec_up & (l <= hi) & (c > hi)).astype(float)
        F[f"brk{w}_retest_dn"] = ((pd.Series(dn.astype(float)).rolling(w, min_periods=1).max()
                                   .to_numpy() > 0) & (h >= lo) & (c < lo)).astype(float)

    # ---------------------------------------------------------------- risk / N distance
    for k in (1, 2, 3):
        F[f"to_{k}N_up"] = (_shift(_roll_max(h, 20), 1) - c) / (k * safe)
        F[f"to_{k}N_dn"] = (c - _shift(_roll_min(l, 20), 1)) / (k * safe)
    for s in RET_SPANS:
        mv = c - _shift(c, s)
        F[f"move{s}_atr"] = mv / safe
        F[f"move{s}_pct"] = mv / c
        r = pd.Series(np.log(c) - np.log(_shift(c, 1)))
        F[f"ret{s}_consistency"] = (r.rolling(s, min_periods=s)
                                    .apply(lambda x: np.mean(np.sign(x)), raw=True).to_numpy())

    # ---------------------------------------------------------------- trend structure
    hh = (h > _shift(h, 1)).astype(float); ll = (l < _shift(l, 1)).astype(float)
    F["hh_rate_20"] = pd.Series(hh).rolling(20, min_periods=5).mean().to_numpy()
    F["ll_rate_20"] = pd.Series(ll).rolling(20, min_periods=5).mean().to_numpy()
    F["hh_minus_ll_20"] = F["hh_rate_20"] - F["ll_rate_20"]
    F["dir_persist_20"] = pd.Series(np.sign(c - _shift(c, 1))).rolling(20, min_periods=5).mean().to_numpy()
    for s in MA_SPANS:
        ma = _ema(c, s)
        F[f"dist_ema{s}_atr"] = (c - ma) / safe
        F[f"slope_ema{s}_atr"] = (ma - _shift(ma, 10)) / (10 * safe)
    F["ma_align"] = (np.sign(F["dist_ema20_atr"]) + np.sign(F["dist_ema50_atr"])
                     + np.sign(F["dist_ema200_atr"])) / 3.0
    F["slope_price_atr"] = (c - _shift(c, 20)) / (20 * safe)

    # ---------------------------------------------------------------- session context
    mod = (ix.hour * 60 + ix.minute).to_numpy().astype(float)
    F["min_since_open"] = mod - session_open
    F["min_to_close"] = session_close - mod
    F["sess_bucket"] = np.digitize(mod, [session_open, session_open + 90, session_close - 90]) - 1.0
    day = ((ix + pd.Timedelta(hours=7)).normalize().view("int64") // 86_400_000_000_000)
    tod = pd.DataFrame({"mod": mod, "v": v, "tr": tr, "day": day})
    gm = tod.groupby("mod")
    # expanding means by minute-of-day, shifted, so today never sees itself
    F["rvol_tod"] = (tod["v"] / gm["v"].transform(lambda s: s.expanding().mean().shift(1))).to_numpy()
    F["rvolat_tod"] = (tod["tr"] / gm["tr"].transform(lambda s: s.expanding().mean().shift(1))).to_numpy()

    # opening range: the first 30 minutes of the session, frozen once complete
    bar_min = int(np.nanmedian(np.diff(mod[mod > 0])[:200])) if n > 200 else 15
    bar_min = max(bar_min, 1)
    ork = max(int(round(30 / bar_min)), 1)
    inday = tod.groupby("day").cumcount().to_numpy()
    orh = pd.Series(h).groupby(day).transform(lambda s: s.rolling(ork, min_periods=1).max()).to_numpy()
    orl = pd.Series(l).groupby(day).transform(lambda s: s.rolling(ork, min_periods=1).min()).to_numpy()
    orh = np.where(inday >= ork, pd.Series(orh).groupby(day).transform(
        lambda s: s.shift(0).where(np.arange(len(s)) < ork).ffill()).to_numpy(), np.nan)
    orl = np.where(inday >= ork, pd.Series(orl).groupby(day).transform(
        lambda s: s.shift(0).where(np.arange(len(s)) < ork).ffill()).to_numpy(), np.nan)
    orw = orh - orl
    F["or_width_atr"] = orw / safe
    F["or_pos"] = np.where(orw > 0, (c - orl) / orw, np.nan)
    F["or_break_up"] = (h > orh).astype(float)
    F["or_break_dn"] = (l < orl).astype(float)
    F["or_break_dist_atr"] = np.where(h > orh, (h - orh) / safe,
                                      np.where(l < orl, (l - orl) / safe, 0.0))

    # ---------------------------------------------------------------- volume
    vm = pd.Series(v).rolling(50, min_periods=10).mean().to_numpy()
    F["rvol_50"] = v / np.where(vm > 0, vm, np.nan)
    F["vol_accel"] = F["rvol_50"] - _shift(F["rvol_50"], 5)
    F["vol_on_break20"] = F["rvol_50"] * F["brk20_up"]
    F["move_per_vol"] = np.abs(c - _shift(c, 1)) / safe / np.where(F["rvol_50"] > 0, F["rvol_50"], np.nan)

    return F


def audit(o, h, l, c, v, idx, checks=12, seed=4, verbose=True):
    """Truncation audit: recompute on history ending at i and require an exact match."""
    full = build(o, h, l, c, v, idx)
    rng = np.random.default_rng(seed)
    n = len(c)
    pts = rng.choice(np.arange(int(0.6 * n), n - 1), size=min(checks, n // 10), replace=False)
    bad = []
    for i in sorted(pts):
        part = build(o[:i + 1], h[:i + 1], l[:i + 1], c[:i + 1], v[:i + 1], idx[:i + 1])
        for k in full:
            a, b = full[k][i], part[k][i]
            if np.isnan(a) and np.isnan(b):
                continue
            if not np.isclose(a, b, rtol=1e-9, atol=1e-12, equal_nan=True):
                bad.append((int(i), k, float(a), float(b)))
    if verbose:
        tot = len(pts) * len(full)
        if bad:
            names = sorted({r[1] for r in bad})
            print(f"  TRUNCATION AUDIT FAILED: {len(bad)} of {tot} checks, {len(names)} features")
            for nm in names[:10]:
                ex = next(r for r in bad if r[1] == nm)
                print(f"    {nm:<28} bar {ex[0]}  full {ex[2]:+.6g}  truncated {ex[3]:+.6g}")
        else:
            print(f"  truncation audit PASSED: {len(pts)} bars x {len(full)} features = "
                  f"{tot} checks, 0 mismatches")
    return bad


# --------------------------------------------------------------------- Kalman trend state
def kalman_features(c, atr, q_level=1e-5, q_slope=1e-6, r_obs=1.0):
    """A local-level-plus-slope (constant velocity) Kalman filter on log price.

    WHY IT BELONGS IN A TURTLE FEATURE SET. Every trend measure above is a moving average or a
    channel, and both are windowed: they carry a fixed lag and they weight all bars inside the
    window alike. A Kalman filter instead maintains a STATE -- level and slope -- and updates it by
    how surprising each new bar is, so its lag adapts to the signal-to-noise ratio rather than
    being a parameter. That is a genuinely different estimator, not another smoothing constant,
    which is the only reason to add anything outside the Turtle concept set.

    Causal by construction: the state at bar i is the posterior after observing bars <= i, and
    nothing is smoothed backwards. The INNOVATION -- how far the new observation fell from the
    one-step prediction, in units of its own predicted standard deviation -- is the feature this
    adds that no moving average can express: a standardised surprise.
    """
    y = np.log(np.asarray(c, float))
    n = len(y)
    x = np.array([y[0], 0.0])
    P = np.eye(2)
    F = np.array([[1.0, 1.0], [0.0, 1.0]])
    Q = np.array([[q_level, 0.0], [0.0, q_slope]])
    H = np.array([1.0, 0.0])
    lvl = np.full(n, np.nan); slp = np.full(n, np.nan)
    innov = np.full(n, np.nan); innov_z = np.full(n, np.nan)
    for i in range(n):
        x = F @ x
        P = F @ P @ F.T + Q
        s = H @ P @ H + r_obs
        v = y[i] - H @ x
        K = (P @ H) / s
        x = x + K * v
        P = P - np.outer(K, H @ P)
        lvl[i] = x[0]; slp[i] = x[1]
        innov[i] = v; innov_z[i] = v / np.sqrt(s) if s > 0 else np.nan
    a = np.asarray(atr, float)
    safe = np.where(a > 0, a, np.nan)
    rel = safe / np.asarray(c, float)
    out = {}
    out["kf_dist_atr"] = (y - lvl) / np.where(rel > 0, rel, np.nan)
    out["kf_slope_atr"] = slp / np.where(rel > 0, rel, np.nan)
    out["kf_slope_sign"] = np.sign(slp)
    out["kf_innov_z"] = innov_z
    out["kf_innov_abs"] = np.abs(innov_z)
    out["kf_slope_accel"] = slp - _shift(slp, 10)
    out["kf_slope_persist"] = pd.Series(np.sign(slp)).rolling(20, min_periods=5).mean().to_numpy()
    return out
