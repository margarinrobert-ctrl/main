"""The causal feature library (brief sections 5-13).

EVERY feature here is computed from information available at the CLOSE of its own bar. Rolling
statistics use trailing windows only; session statistics use bars already elapsed in the session;
nothing is centred, nothing is z-scored against a full-sample mean, nothing peeks at bar i+1.
`audit.py` re-checks that claim mechanically rather than trusting this docstring.

NAMING. A `tick_` prefix marks anything derived from the file's TickVolume, which is a broker tick
COUNT and not centralised exchange volume (brief section 12).

NORMALISATION. Distances are divided by ATR wherever the brief asks for it (sections 7, 9, 11),
because a 40-point distance means something different at ATR 12 and ATR 90 -- and because this
feed spans 4,700 to 24,500 index points, so raw point distances are not comparable across the
sample at all.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PERIODS = (5, 8, 10, 13, 20, 21, 34, 50, 100, 200)


def _ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def _sma(x, n):
    return pd.Series(x).rolling(n, min_periods=n).mean().to_numpy()


def _rma(x, n):
    return pd.Series(x).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()


def _rank(x, n):
    """Trailing percentile of the last value within its own n-bar window. Causal by construction."""
    return pd.Series(x).rolling(n, min_periods=max(10, n // 4)).rank(pct=True).to_numpy()


def _slope(x, n):
    return (x - np.roll(x, n)) / float(n)


def true_range(h, l, c):
    pc = np.roll(c, 1); pc[0] = c[0]
    return np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))


def build(d, verbose=False):
    """Return a dict of named causal feature arrays."""
    o, h, l, c, v = d["o"], d["h"], d["l"], d["c"], d["v"]
    mod = np.asarray(d["mod"]); idx = d["idx"]; n = len(c)
    F = {}
    tr = true_range(h, l, c)
    atr = _ema(tr, 14)
    F["atr"] = atr
    rng = h - l
    body = c - o
    prev_c = np.roll(c, 1); prev_c[0] = c[0]
    prev_h = np.roll(h, 1); prev_h[0] = h[0]
    prev_l = np.roll(l, 1); prev_l[0] = l[0]

    # ---- price / candle structure (brief 5, 13)
    with np.errstate(divide="ignore", invalid="ignore"):
        F["ret"] = np.r_[0.0, np.diff(c) / c[:-1]]
        F["logret"] = np.r_[0.0, np.diff(np.log(c))]
        F["body_atr"] = body / atr
        F["range_atr"] = rng / atr
        F["upwick_atr"] = (h - np.maximum(o, c)) / atr
        F["lowick_atr"] = (np.minimum(o, c) - l) / atr
        F["body_over_range"] = np.where(rng > 0, np.abs(body) / rng, 0.0)
        F["close_loc"] = np.where(rng > 0, (c - l) / rng, 0.5)      # 0 = at low, 1 = at high
        F["gap_prev_close_atr"] = (o - prev_c) / atr
        F["dist_prev_high_atr"] = (c - prev_h) / atr
        F["dist_prev_low_atr"] = (c - prev_l) / atr

    # ---- volatility (brief 5)
    F["atr_pctile"] = _rank(atr, 250)
    F["range_pctile"] = _rank(rng, 250)
    F["rvol_20"] = pd.Series(F["logret"]).rolling(20, min_periods=10).std().to_numpy()
    F["rvol_60"] = pd.Series(F["logret"]).rolling(60, min_periods=30).std().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        F["vol_expansion"] = F["rvol_20"] / F["rvol_60"]
        F["atr_ratio_5_50"] = _ema(tr, 5) / _ema(tr, 50)

    # ---- trend (brief 5, 23)
    for p in PERIODS:
        e = _ema(c, p)
        F[f"dist_ema{p}_atr"] = (c - e) / atr
        F[f"ema{p}_slope_atr"] = _slope(e, 5) / atr
    F["ema_align"] = ((_ema(c, 8) > _ema(c, 21)).astype(float)
                      + (_ema(c, 21) > _ema(c, 50)).astype(float)
                      + (_ema(c, 50) > _ema(c, 200)).astype(float))
    up = np.maximum(h - prev_h, 0.0); dn = np.maximum(prev_l - l, 0.0)
    pdm = np.where(up > dn, up, 0.0); ndm = np.where(dn > up, dn, 0.0)
    atr_w = _rma(tr, 14)
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi = 100.0 * _rma(pdm, 14) / atr_w
        ndi = 100.0 * _rma(ndm, 14) / atr_w
        dx = 100.0 * np.abs(pdi - ndi) / np.maximum(pdi + ndi, 1e-9)
    F["adx"] = _rma(dx, 14); F["di_plus"] = pdi; F["di_minus"] = ndi
    F["di_spread"] = pdi - ndi

    # ---- momentum (brief 6)
    diff = np.r_[0.0, np.diff(c)]
    gain = _rma(np.maximum(diff, 0.0), 14); loss = _rma(np.maximum(-diff, 0.0), 14)
    with np.errstate(divide="ignore", invalid="ignore"):
        rsi = 100.0 - 100.0 / (1.0 + gain / np.maximum(loss, 1e-9))
    F["rsi"] = rsi
    F["rsi_slope"] = _slope(rsi, 3)
    F["rsi_accel"] = _slope(rsi, 3) - np.roll(_slope(rsi, 3), 3)
    F["rsi_pctile"] = _rank(rsi, 250)
    macd = _ema(c, 12) - _ema(c, 26); sig = _ema(macd, 9)
    F["macd_hist_atr"] = (macd - sig) / atr
    F["macd_atr"] = macd / atr
    for p in (5, 10, 20):
        F[f"roc{p}_atr"] = (c - np.roll(c, p)) / atr
    ll = pd.Series(l).rolling(14, min_periods=14).min().to_numpy()
    hh = pd.Series(h).rolling(14, min_periods=14).max().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        F["stoch_k"] = 100.0 * (c - ll) / np.maximum(hh - ll, 1e-9)
        F["williams_r"] = -100.0 * (hh - c) / np.maximum(hh - ll, 1e-9)
    F["price_accel_atr"] = (F["roc5_atr"] - np.roll(F["roc5_atr"], 5))
    bull = (c > o).astype(np.int32)
    F["consec_bull"] = _streak(bull)
    F["consec_bear"] = _streak(1 - bull)

    # ---- market structure (brief 7, 11)
    for p in (10, 20, 50):
        hi = pd.Series(h).rolling(p, min_periods=p).max().to_numpy()
        lo = pd.Series(l).rolling(p, min_periods=p).min().to_numpy()
        with np.errstate(divide="ignore", invalid="ignore"):
            F[f"dist_high{p}_atr"] = (c - hi) / atr
            F[f"dist_low{p}_atr"] = (c - lo) / atr
            F[f"pos_in_range{p}"] = (c - lo) / np.maximum(hi - lo, 1e-9)
    F["higher_high"] = (h > prev_h).astype(float)
    F["higher_low"] = (l > prev_l).astype(float)
    F["bos_up"] = (c > pd.Series(h).rolling(20, min_periods=20).max().shift(1).to_numpy()).astype(float)

    # ---- tick activity (brief 12) -- a tick COUNT, not exchange volume
    F["tick_rel_20"] = v / np.maximum(pd.Series(v).rolling(20, min_periods=10).mean().to_numpy(), 1e-9)
    F["tick_pctile"] = _rank(v, 250)
    F["tick_accel"] = v / np.maximum(np.roll(v, 1), 1e-9)

    # ---- time of day (brief 8)
    F["mod"] = mod.astype(float)
    F["min_since_0700"] = mod - 420.0
    F["min_until_1100"] = 660.0 - mod
    F["bucket15"] = np.floor(mod / 15.0)
    F["bucket30"] = np.floor(mod / 30.0)

    # ---- session and prior-day context (brief 9, 10)
    F.update(_session(d, atr))
    if verbose:
        print(f"{len(F)} features on {n:,} bars")
    return F


def _streak(flag):
    out = np.zeros(len(flag), float); run = 0.0
    for i in range(len(flag)):
        run = run + 1.0 if flag[i] else 0.0
        out[i] = run
    return out


def _session(d, atr):
    """Overnight, previous-day and opening-range context. All strictly backward-looking."""
    idx = d["idx"]; o, h, l, c = d["o"], d["h"], d["l"], d["c"]; mod = np.asarray(d["mod"])
    day = pd.DatetimeIndex(idx).normalize()
    df = pd.DataFrame({"o": o, "h": h, "l": l, "c": c, "mod": mod}, index=idx)
    df["day"] = day
    F = {}

    # Previous RTH session's stats. Reindexed over EVERY calendar day present, not only days
    # that already have RTH bars -- otherwise a day whose RTH has not started yet drops out of
    # the group index and loses access to yesterday's (fully known) values.
    rth = df[(df["mod"] >= 570) & (df["mod"] < 960)]
    g = rth.groupby("day")
    alldays = pd.Index(df["day"].unique()).sort_values()
    prev = pd.DataFrame({"pdh": g["h"].max(), "pdl": g["l"].min(),
                         "pdc": g["c"].last(), "pdo": g["o"].first()}).reindex(alldays).ffill().shift(1)
    j = df.join(prev, on="day")
    with np.errstate(divide="ignore", invalid="ignore"):
        F["dist_pdh_atr"] = (c - j["pdh"].to_numpy()) / atr
        F["dist_pdl_atr"] = (c - j["pdl"].to_numpy()) / atr
        F["dist_pdc_atr"] = (c - j["pdc"].to_numpy()) / atr
        F["prev_day_ret"] = (j["pdc"] / j["pdo"] - 1.0).to_numpy()
        F["prev_day_range_atr"] = ((j["pdh"] - j["pdl"]) / atr).to_numpy()

    # overnight (18:00 prior -> 07:00) and the gap, both complete before the window opens
    on = df[(df["mod"] >= 1080) | (df["mod"] < 420)].copy()
    on["onday"] = (on.index + pd.Timedelta(hours=6)).normalize()
    og = on.groupby("onday")
    onh = og["h"].max(); onl = og["l"].min(); ono = og["o"].first(); onc = og["c"].last()
    ondf = pd.DataFrame({"onh": onh, "onl": onl, "ono": ono, "onc": onc})
    key = (df.index + pd.Timedelta(hours=6)).normalize()
    jo = ondf.reindex(key).to_numpy()
    # The overnight aggregate is complete only BETWEEN 07:00 and 18:00. Before 07:00 it is still
    # forming; from 18:00 the NEXT overnight has already begun, and a bar inside it reads its own
    # group's running high/low/last-close -- which is future data. An earlier version masked only
    # `mod >= 420` and therefore leaked on every evening bar; the truncation audit caught it on
    # US30 at bars stamped 18:30-23:15. NaN outside the complete window rather than a leaky value.
    done = (mod >= 420) & (mod < 1080)
    with np.errstate(divide="ignore", invalid="ignore"):
        F["dist_onh_atr"] = np.where(done, (c - jo[:, 0]) / atr, np.nan)
        F["dist_onl_atr"] = np.where(done, (c - jo[:, 1]) / atr, np.nan)
        F["overnight_ret"] = np.where(done, jo[:, 3] / jo[:, 2] - 1.0, np.nan)
        F["overnight_range_atr"] = np.where(done, (jo[:, 0] - jo[:, 1]) / atr, np.nan)
        F["gap_atr"] = np.where(done, (jo[:, 3] - j["pdc"].to_numpy()) / atr, np.nan)

    # session-so-far extremes within 07:00-11:00, expanding (uses only elapsed bars)
    win = df[(df["mod"] >= 420) & (df["mod"] < 660)]
    sh = win.groupby("day")["h"].cummax(); sl = win.groupby("day")["l"].cummin()
    with np.errstate(divide="ignore", invalid="ignore"):
        F["dist_sess_high_atr"] = (c - sh.reindex(df.index).to_numpy()) / atr
        F["dist_sess_low_atr"] = (c - sl.reindex(df.index).to_numpy()) / atr

    # opening ranges, each usable only AFTER it completes (brief 10)
    for mins in (15, 30, 60):
        end = 570 + mins
        orb = df[(df["mod"] >= 570) & (df["mod"] < end)]
        og2 = orb.groupby("day")
        orh = og2["h"].max().reindex(day.unique()); orl = og2["l"].min().reindex(day.unique())
        oh = pd.Series(orh).reindex(day).to_numpy(); ol = pd.Series(orl).reindex(day).to_numpy()
        live = mod >= end                                  # not known before the range closes
        with np.errstate(divide="ignore", invalid="ignore"):
            F[f"dist_orh{mins}_atr"] = np.where(live, (c - oh) / atr, np.nan)
            F[f"dist_orl{mins}_atr"] = np.where(live, (c - ol) / atr, np.nan)
            F[f"or{mins}_range_atr"] = np.where(live, (oh - ol) / atr, np.nan)
            F[f"or{mins}_broken_up"] = np.where(live, (c > oh).astype(float), np.nan)
    return F
