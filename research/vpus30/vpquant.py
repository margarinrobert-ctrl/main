"""The advanced quant layer: 30 more causal features in six declared families, on top of the 22
volume-profile ones. Meta layer ONLY -- none of these may decide direction or whether an event
exists, which is the rule that stops a feature search laundering a dead primary.

FAMILIES (prefix -> what it is, and why it is here rather than in the primary)
  vol.    realised volatility: Parkinson, Garman-Klass, close-to-close rv, vol-of-vol, ATR ratios.
          `STUDY_V66_DL_META` found seven volatility features beat sixty-five of everything.
  tod.    the SAME quantities against a CAUSAL TIME-OF-DAY baseline. CLAUDE.md's correction:
          on a 24h tape an RTH bar clears its own trailing ATR mean ~99% of the time, so a
          trailing mean is not a volatility reading at all -- it is a clock.
  ffd.    fractional differencing at the lowest d passing ADF on the RESEARCH block only.
  hmm.    a Baum-Welch Gaussian HMM read FILTERED, never smoothed. `predict` runs Viterbi over the
          whole sequence and labels the past with the future; that is the single most common way
          an HMM backtest is wrong.
  mom.    momentum / trend context. Included expecting a NEGATIVE sign: twelve independent routes
          on this branch land on mean reversion.
  str.    structure: prior-day levels, session position, opening gap.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ------------------------------------------------------------------ fractional differencing
def ffd_weights(d, thresh=1e-4, max_k=2000):
    w = [1.0]
    for k in range(1, max_k):
        w_ = -w[-1] * (d - k + 1) / k
        if abs(w_) < thresh:
            break
        w.append(w_)
    return np.array(w[::-1])


def ffd(x, d, thresh=1e-4):
    w = ffd_weights(d, thresh)
    k = len(w)
    out = np.full(len(x), np.nan)
    for i in range(k - 1, len(x)):
        out[i] = np.dot(w, x[i - k + 1:i + 1])
    return out


def adf_stat(x):
    """Augmented Dickey-Fuller t-statistic, lag 1, no statsmodels on this box."""
    x = x[np.isfinite(x)]
    if len(x) < 100:
        return np.nan
    dy = np.diff(x)
    X = np.column_stack([x[:-1], np.ones(len(dy)), np.r_[0.0, dy[:-1]]])
    b, *_ = np.linalg.lstsq(X, dy, rcond=None)
    r = dy - X @ b
    s2 = r @ r / (len(dy) - X.shape[1])
    se = np.sqrt(s2 * np.linalg.inv(X.T @ X)[0, 0])
    return float(b[0] / se)


# ------------------------------------------------------------------ causal HMM, filtered only
def hmm_filtered(x, k=3, iters=40, seed=0):
    """Baum-Welch on standardised returns, then the FILTERED posterior (forward pass only).

    Standardising inside the fit is load-bearing: 15-minute log returns are ~1e-4, a Gaussian
    emission reaches ~400 and the scaled backward recursion divides by a scale that has already
    underflowed -- which returns ALL-NaN and reads as 'no signal' rather than as an error.
    """
    z = (x - np.nanmean(x)) / (np.nanstd(x) + 1e-12)
    z = np.nan_to_num(z)
    n = len(z)
    rng = np.random.default_rng(seed)
    mu = np.linspace(-1, 1, k) + 0.01 * rng.standard_normal(k)
    sd = np.ones(k)
    A = np.full((k, k), 1.0 / k)
    pi = np.full(k, 1.0 / k)
    for _ in range(iters):
        B = np.exp(-0.5 * ((z[:, None] - mu) / sd) ** 2) / (sd * np.sqrt(2 * np.pi))
        B = np.maximum(B, 1e-300)
        al = np.zeros((n, k)); sc = np.zeros(n)
        al[0] = pi * B[0]; sc[0] = al[0].sum(); al[0] /= sc[0]
        for t in range(1, n):
            al[t] = (al[t - 1] @ A) * B[t]
            sc[t] = al[t].sum()
            al[t] /= max(sc[t], 1e-300)
        be = np.zeros((n, k)); be[-1] = 1.0
        for t in range(n - 2, -1, -1):
            be[t] = A @ (B[t + 1] * be[t + 1])
            be[t] /= max(be[t].sum(), 1e-300)
        gam = al * be
        gam /= np.maximum(gam.sum(1, keepdims=True), 1e-300)
        xi = np.zeros((k, k))
        for t in range(n - 1):
            m = (al[t][:, None] * A) * (B[t + 1] * be[t + 1])[None, :]
            xi += m / max(m.sum(), 1e-300)
        A = xi / np.maximum(xi.sum(1, keepdims=True), 1e-300)
        pi = gam[0] / gam[0].sum()
        mu = (gam * z[:, None]).sum(0) / np.maximum(gam.sum(0), 1e-300)
        sd = np.sqrt((gam * (z[:, None] - mu) ** 2).sum(0) / np.maximum(gam.sum(0), 1e-300)) + 1e-6
    return dict(mu=mu, sd=sd, A=A, pi=pi)


def hmm_apply(x, p):
    """FILTERED posterior only -- information through t, never after."""
    z = np.nan_to_num((x - np.nanmean(x)) / (np.nanstd(x) + 1e-12))
    mu, sd, A, pi = p["mu"], p["sd"], p["A"], p["pi"]
    k = len(mu)
    B = np.exp(-0.5 * ((z[:, None] - mu) / sd) ** 2) / (sd * np.sqrt(2 * np.pi))
    B = np.maximum(B, 1e-300)
    al = np.zeros((len(z), k))
    al[0] = pi * B[0]; al[0] /= al[0].sum()
    for t in range(1, len(z)):
        al[t] = (al[t - 1] @ A) * B[t]
        al[t] /= max(al[t].sum(), 1e-300)
    return al


def tod_baseline(v, mod, min_obs=20):
    """Causal expanding mean of `v` at this minute-of-day over PRIOR sessions only."""
    out = np.full(len(v), np.nan)
    acc = {}
    for i in range(len(v)):
        m = mod[i]
        s, c = acc.get(m, (0.0, 0))
        if c >= min_obs:
            out[i] = s / c
        if np.isfinite(v[i]):
            acc[m] = (s + v[i], c + 1)
    return out


def build(g, cut):
    """All 30 quant features. `cut` fixes where d and the HMM parameters may be estimated."""
    o = g["open"].to_numpy(); h = g["high"].to_numpy()
    l = g["low"].to_numpy(); c = g["close"].to_numpy()
    tv = g["tv"].to_numpy(); at = g["atr"].to_numpy()
    mod = (g.index.hour * 60 + g.index.minute).to_numpy()
    res = g.index < cut
    X = pd.DataFrame(index=g.index)
    lr = np.r_[0.0, np.diff(np.log(c))]

    # ---- vol.
    park = np.sqrt(np.maximum(np.log(h / l) ** 2 / (4 * np.log(2)), 0))
    gk = np.sqrt(np.maximum(0.5 * np.log(h / l) ** 2 - (2 * np.log(2) - 1) * np.log(c / o) ** 2, 0))
    X["vol.park"] = park
    X["vol.gk"] = gk
    for n in (26, 78):
        X[f"vol.rv{n}"] = pd.Series(lr).rolling(n).std().to_numpy()
    X["vol.vov"] = pd.Series(X["vol.rv26"]).rolling(78).std().to_numpy()
    X["vol.atr_ratio"] = at / pd.Series(at).rolling(78).mean().to_numpy()
    X["vol.atr_rank"] = pd.Series(at).rolling(500, min_periods=100).rank(pct=True).to_numpy()
    X["vol.rng_atr"] = (h - l) / at

    # ---- tod.  the same quantities against a CAUSAL time-of-day baseline
    for nm, v in (("atr", at), ("rng", h - l), ("tv", tv), ("park", park)):
        b = tod_baseline(v, mod)
        X[f"tod.{nm}"] = v / np.where(b > 0, b, np.nan)

    # ---- ffd.  d chosen on the RESEARCH block only
    lp = np.log(c)
    best_d = None
    for dd in np.arange(0.1, 1.01, 0.1):
        s = ffd(lp, dd)
        if adf_stat(s[res]) < -2.86:            # 5% ADF critical value
            best_d = round(float(dd), 2)
            break
    best_d = best_d if best_d is not None else 1.0
    fs = ffd(lp, best_d)
    X["ffd.level"] = fs
    X["ffd.z"] = (fs - pd.Series(fs).rolling(78).mean().to_numpy()) / \
                 (pd.Series(fs).rolling(78).std().to_numpy() + 1e-12)
    X["ffd.z250"] = (fs - pd.Series(fs).rolling(250).mean().to_numpy()) / \
                    (pd.Series(fs).rolling(250).std().to_numpy() + 1e-12)

    # ---- hmm.  fitted on research, read FILTERED
    p = hmm_filtered(lr[res])
    post = hmm_apply(lr, p)
    order = np.argsort(p["mu"])
    X["hmm.bear"] = post[:, order[0]]
    X["hmm.side"] = post[:, order[1]]
    X["hmm.bull"] = post[:, order[2]]
    X["hmm.dir"] = X["hmm.bull"] - X["hmm.bear"]

    # ---- mom.
    for n in (4, 26, 78):
        X[f"mom.roc{n}"] = pd.Series(c).pct_change(n).to_numpy() * 100
    for n in (26, 78, 250):
        X[f"mom.d_ema{n}"] = (c - pd.Series(c).ewm(span=n, adjust=False).mean().to_numpy()) / at
    X["mom.rsi14"] = _rsi(c, 14)

    # ---- str.
    X["str.bar_pos"] = np.divide(c - l, np.where(h - l > 0, h - l, np.nan))
    X["str.gap"] = (o - np.r_[np.nan, c[:-1]]) / at
    X["str.sess_pos"] = g["dev_pos"].to_numpy()
    X["str.bar_i"] = g["bar_in_sess"].to_numpy()
    return X, best_d, p


def _rsi(c, n=14):
    d = np.r_[0.0, np.diff(c)]
    up = pd.Series(np.where(d > 0, d, 0.0)).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    dn = pd.Series(np.where(d < 0, -d, 0.0)).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    return 100 - 100 / (1 + up / np.maximum(dn, 1e-12))
