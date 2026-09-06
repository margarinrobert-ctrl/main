"""BAR-LEVEL FEATURES AND ANOMALY SCORES ON GOLD -- no primary, and that is deliberate.

WHY THE BAR LEVEL AND NOT AN EVENT STREAM. `STUDY_VWANOM` built a meta layer on a fitted event
stream whose primary FAILED Gate 1 out of sample, and the architecture's own rule says a meta layer
cannot create direction skill on such a primary. The honest ordering is the reverse: measure whether
ANY predictive content exists at bar level first, and derive events from whatever survives. A
bar-level IC needs no primary, so it cannot be contaminated by one.

THE FEATURE SET IS SPLIT BY WHAT THE FORWARD BLOCK CAN CARRY (see `xdata`): the MT feed's sixth
field is bar length in minutes, not volume, so anything needing volume runs on ISO only and is one
block short of evidence BY CONSTRUCTION. `core` columns run on both feeds; `vd.` columns do not.

  core families
    vol.   volatility state -- ATR against a CAUSAL time-of-day baseline, realised vol, vol-of-vol
    trn.   trend context -- distance from EMAs in ATR units, slopes, efficiency ratio
    reg.   regime -- CHOP, ADX, and a Baum-Welch HMM read FILTERED (never smoothed)
    str.   bar structure -- body, wicks, close position, gaps, runs
    clk.   the clock -- minute of day, session phase, day of week
    ffd.   fractional differencing, d chosen by ADF ON THE RESEARCH BLOCK ONLY
    anm.   THE ANOMALY FAMILY, rebuilt WITHOUT VOLUME so it survives on the forward block
  volume-dependent
    vd.    participation against the same causal baseline, plus a volume-fed anomaly twin --
           ISO only, reported separately, never pooled with the core result

LABELS are forward log returns at h = 1, 4, 16, 96 bars and the forward realised range, so the
question "does an unusual bar predict a bigger move" is asked directly rather than inferred.
OVERLAPPING HORIZONS need Newey-West: an IC of 0.03 at h=96 with a naive t of 6.8 is a t of 2.3
once the overlap is priced (`STUDY_V47`).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vwanom"))
import xdata as X  # noqa: E402
from anomfeat import (_ema, _roll, tod_baseline, chop, adx, eff_ratio, ffd, adf_stat,  # noqa: E402
                      HMM, AutoEncoder, mahalanobis)

HORIZONS = (1, 4, 16, 96)
CORE_BAR = ["ret1", "ret4", "ret16", "rng_atr", "body_share", "close_pos", "upper_wick", "gap_atr"]


def _atr(h, l, c, n=14):
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def pick_d(c, fit_mask, grid=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)):
    for d in grid:
        s = ffd(c[fit_mask], d)
        t = adf_stat(s)
        if np.isfinite(t) and t < -2.86:
            return float(d)
    return 1.0


def build(f, fit_mask=None, models=None, seed=0):
    """Features for one frame. `fit_mask` selects the bars every unsupervised model is FITTED on;
    pass `models` from a previous call to APPLY an already-fitted set to a new feed."""
    o, h, l, c = (f[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    v = f["volume"].to_numpy(float) if "volume" in f else np.full(len(f), np.nan)
    has_vol = np.isfinite(v).mean() > 0.5
    ix = f.index
    mod = (ix.hour * 60 + ix.minute).to_numpy(np.int64)
    day = ix.normalize().values.astype("datetime64[D]").astype(np.int64)
    n = len(c)
    if fit_mask is None:
        fit_mask = np.ones(n, bool)
    F = {}

    atr14 = _atr(h, l, c, 14)
    rng = h - l
    body = np.abs(c - o)
    pc = np.concatenate(([c[0]], c[:-1]))
    ret1 = np.concatenate(([0.0], np.diff(np.log(np.maximum(c, 1e-12)))))

    # ---- vol.
    F["vol.atr_tod"] = atr14 / np.maximum(tod_baseline(atr14, mod, day), 1e-9)
    F["vol.atr_pct500"] = pd.Series(atr14).rolling(500, min_periods=100).rank(pct=True).to_numpy()
    F["vol.rv24"] = _roll(ret1 ** 2, 24, "sum") ** 0.5
    F["vol.rv96"] = _roll(ret1 ** 2, 96, "sum") ** 0.5
    F["vol.rv_ratio"] = F["vol.rv24"] / np.maximum(F["vol.rv96"], 1e-15)
    F["vol.volofvol"] = _roll(F["vol.rv24"], 96, "std")
    F["vol.atr_slope"] = (atr14 - np.concatenate((np.full(48, np.nan), atr14[:-48]))) / np.maximum(atr14, 1e-9)

    # ---- trn.
    e50, e200 = _ema(c, 50), _ema(c, 200)
    F["trn.d_e50"] = (c - e50) / np.maximum(atr14, 1e-9)
    F["trn.d_e200"] = (c - e200) / np.maximum(atr14, 1e-9)
    F["trn.slope_e200"] = (e200 - np.concatenate((np.full(96, np.nan), e200[:-96]))) / np.maximum(atr14, 1e-9)
    F["trn.er20"] = eff_ratio(c, 20)
    F["trn.er96"] = eff_ratio(c, 96)
    F["trn.ret16"] = (c - np.concatenate((np.full(16, np.nan), c[:-16]))) / np.maximum(atr14, 1e-9)
    F["trn.ret96"] = (c - np.concatenate((np.full(96, np.nan), c[:-96]))) / np.maximum(atr14, 1e-9)

    # ---- reg.
    F["reg.chop14"] = chop(h, l, c, 14)
    F["reg.chop48"] = chop(h, l, c, 48)
    ax, pdi, ndi = adx(h, l, c, 14)
    F["reg.adx14"] = ax
    F["reg.di_spread"] = pdi - ndi
    if models is not None and "hmm" in models:
        hm = models["hmm"]
    else:
        hm = HMM(k=3, seed=seed).fit(ret1[fit_mask])
    post = hm.filtered(ret1)
    order = np.argsort(hm.means())
    for j, s in enumerate(("bear", "side", "bull")):
        F[f"reg.hmm_{s}"] = post[:, order[j]]
    F["reg.hmm_drift"] = post @ hm.means()

    # ---- str.
    F["str.body_share"] = body / np.maximum(rng, 1e-9)
    F["str.close_pos"] = (c - l) / np.maximum(rng, 1e-9)
    F["str.upper_wick"] = (h - np.maximum(o, c)) / np.maximum(rng, 1e-9)
    F["str.rng_atr"] = rng / np.maximum(atr14, 1e-9)
    F["str.gap_atr"] = (o - pc) / np.maximum(atr14, 1e-9)
    F["str.dir_run"] = _roll(np.sign(ret1), 8, "sum")
    F["str.rng_z96"] = (rng - _roll(rng, 96, "mean")) / np.maximum(_roll(rng, 96, "std"), 1e-12)

    # ---- clk.
    F["clk.mod"] = mod.astype(float)
    F["clk.dow"] = ix.dayofweek.to_numpy(float)
    F["clk.is_rth"] = (((mod >= 570) & (mod < 960)) & (ix.dayofweek < 5)).astype(float)

    # ---- ffd.
    d = models["ffd_d"] if (models is not None and "ffd_d" in models) else pick_d(c, fit_mask)
    s = ffd(c, d)
    F["ffd.z96"] = (s - _roll(s, 96, "mean")) / np.maximum(_roll(s, 96, "std"), 1e-12)
    F["ffd.slope"] = s - np.concatenate((np.full(24, np.nan), s[:-24]))

    # ---- anm.  NO VOLUME, so it survives on the forward block
    bar = np.column_stack([
        ret1,
        (c - np.concatenate((np.full(4, np.nan), c[:-4]))) / np.maximum(atr14, 1e-9),
        (c - np.concatenate((np.full(16, np.nan), c[:-16]))) / np.maximum(atr14, 1e-9),
        rng / np.maximum(atr14, 1e-9),
        body / np.maximum(rng, 1e-9),
        (c - l) / np.maximum(rng, 1e-9),
        (h - np.maximum(o, c)) / np.maximum(rng, 1e-9),
        (o - pc) / np.maximum(atr14, 1e-9)])
    ok = np.isfinite(bar).all(1)
    fitb = ok & fit_mask
    if models is not None and "ae" in models:
        ae, iso_m, mu_c, P_c = models["ae"], models["iso"], models["mu"], models["P"]
    else:
        # The AE, the forest and the covariance are fitted on a CAPPED RANDOM SUBSAMPLE of the
        # research bars. Learning what an ordinary bar looks like does not need 240,000 of them,
        # and the cap is what makes the study rerunnable in minutes. The draw comes from the fit
        # mask only, so it cannot reach outside the research block.
        idx = np.flatnonzero(fitb)
        rs = np.random.default_rng(seed)
        sub = idx if len(idx) <= 60000 else rs.choice(idx, 60000, replace=False)
        ae = AutoEncoder(hidden=(16, 6), epochs=40, seed=seed).fit(bar[sub])
        from sklearn.ensemble import IsolationForest
        iso_m = IsolationForest(n_estimators=200, random_state=seed,
                                max_samples=min(50000, len(sub))).fit(bar[sub])
        mu_c = np.nanmean(bar[sub], 0)
        C = np.cov(np.nan_to_num(bar[sub] - mu_c), rowvar=False)
        P_c = np.linalg.pinv(C + 1e-9 * np.eye(C.shape[0]))
    err = np.full(n, np.nan); err[ok] = ae.error(bar[ok])
    F["anm.ae_err"] = err
    sc = np.full(n, np.nan); sc[ok] = -iso_m.score_samples(bar[ok])
    F["anm.iso"] = sc
    Dm = np.nan_to_num(bar - mu_c, nan=0.0)
    mh = np.full(n, np.nan)
    mh[ok] = np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", Dm[ok], P_c, Dm[ok]), 0.0))
    F["anm.mahal"] = mh
    zr = (ret1 - _roll(ret1, 500, "mean")) / np.maximum(_roll(ret1, 500, "std"), 1e-12)
    zg = (rng - _roll(rng, 500, "mean")) / np.maximum(_roll(rng, 500, "std"), 1e-12)
    F["anm.joint_z"] = np.sqrt(np.nan_to_num(zr) ** 2 + np.nan_to_num(zg) ** 2)
    F["anm.ae_pct500"] = pd.Series(err).rolling(500, min_periods=100).rank(pct=True).to_numpy()

    # ---- vd.  volume-dependent, ISO only
    if has_vol:
        F["vd.tod_ratio"] = v / np.maximum(tod_baseline(v, mod, day), 1e-9)
        F["vd.z96"] = (v - _roll(v, 96, "mean")) / np.maximum(_roll(v, 96, "std"), 1e-12)
        F["vd.per_range"] = v / np.maximum(rng / np.maximum(atr14, 1e-9), 1e-9)
        F["vd.trend24"] = _roll(v, 24, "mean") / np.maximum(_roll(v, 96, "mean"), 1e-9)

    Xf = pd.DataFrame(F, index=ix)

    # ---- labels: FORWARD returns and the forward realised range
    Y = {}
    for hz in HORIZONS:
        fut = np.concatenate((c[hz:], np.full(hz, np.nan)))
        Y[f"y.ret{hz}"] = np.log(np.maximum(fut, 1e-12)) - np.log(np.maximum(c, 1e-12))
        fh = pd.Series(h).rolling(hz).max().shift(-hz).to_numpy()
        fl = pd.Series(l).rolling(hz).min().shift(-hz).to_numpy()
        Y[f"y.rng{hz}"] = (fh - fl) / np.maximum(atr14, 1e-9)
    Yf = pd.DataFrame(Y, index=ix)
    fitted = dict(hmm=hm, ae=ae, iso=iso_m, mu=mu_c, P=P_c, ffd_d=d)
    return Xf, Yf, fitted


def newey_west_t(x, y, lag):
    """t-statistic on the slope of y ~ x with Newey-West standard errors -- required whenever the
    label horizon overlaps, which it does at every h > 1."""
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 200 or x.std() == 0:
        return np.nan, np.nan
    x = (x - x.mean()) / x.std()
    X = np.column_stack([np.ones(len(x)), x])
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ b
    S = (X * e[:, None]).T @ (X * e[:, None])
    for L in range(1, max(int(lag), 1) + 1):
        w = 1.0 - L / (lag + 1.0)
        A = (X[L:] * e[L:, None]).T @ (X[:-L] * e[:-L, None])
        S += w * (A + A.T)
    XtX = np.linalg.pinv(X.T @ X)
    cov = XtX @ S @ XtX
    return float(b[1]), float(b[1] / np.sqrt(max(cov[1, 1], 1e-300)))
