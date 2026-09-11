"""Mathematical estimators as PRIMARIES: a parameter of a stochastic process, not an indicator.

THE DISTINCTION THIS BRANCH HAS NOT YET TESTED. Everything run here so far has been a PATTERN --
a channel, a crossover, a divergence -- or a feature pool built from those. The standing verdict is
`STUDY_FEATURES`: "features do not predict here; the harness is the asset". What has never been run
is a primary derived from a MODEL of the price process, where the entry is the implication of an
estimated parameter rather than a fitted threshold on a transform of price.

Six estimators, each of which answers a question with a known answer under a known process:

  OU    Ornstein-Uhlenbeck MLE          how fast does this revert, and to what?   (kappa, half-life,
                                        equilibrium z-score)
  DFA   detrended fluctuation analysis  is the increment process persistent?       (Hurst H)
  VR    Lo-MacKinlay variance ratio     does variance scale linearly in time?      (VR(q), robust z)
  BNS   Barndorff-Nielsen / Shephard    how much of realised variance is JUMP?     (bipower ratio)
  PE    Bandt-Pompe permutation entropy how ordered is the recent path?            (normalised H)
  KF    Kalman local level + slope      what is the state, and is the slope real?  (slope t-stat)

EVERY ONE HAS A POSITIVE CONTROL. An estimator that cannot recover a parameter it was handed cannot
be trusted on price, and three of the six are easy to get subtly wrong (the VR z-statistic, the DFA
scaling range, and the OU discretisation). `controls()` simulates a process with a KNOWN answer and
checks the estimator returns it. That runs before anything touches a price series.

CAUSALITY. Every estimator reads a window ENDING at bar i and nothing after it. `audit()` rebuilds
each value from a truncated history and requires an exact match.

NO COUNTERPARTY IS NAMED. These are model fits, not flow mechanisms, so under the mechanism-first
architecture they carry the full deflation burden and Gate 1 decides eligibility before any feature
or model is built on top.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "research"))

COST = {"US30L": 2.29, "US100L": 1.215, "NQ": 1.72}


# =================================================================================================
# estimators
# =================================================================================================
@njit(cache=True)
def ou_fit(x, n):
    """Rolling OU by exact discretisation: x_{t+1} = a + b x_t + e,  kappa = -ln(b)/dt.

    Returns (kappa, halflife, z) where z = (x_t - theta) / sigma_eq is the standardised distance
    from the fitted equilibrium. NaN wherever b is outside (0,1), i.e. no mean reversion exists.
    """
    m = len(x)
    kap = np.full(m, np.nan); hl = np.full(m, np.nan); z = np.full(m, np.nan)
    for i in range(n, m):
        sx = 0.0; sy = 0.0; sxx = 0.0; sxy = 0.0
        k = n - 1
        for j in range(i - n + 1, i):
            a0 = x[j]; a1 = x[j + 1]
            sx += a0; sy += a1; sxx += a0 * a0; sxy += a0 * a1
        den = k * sxx - sx * sx
        if den <= 0:
            continue
        b = (k * sxy - sx * sy) / den
        a = (sy - b * sx) / k
        if b <= 0.0 or b >= 1.0:
            continue
        ss = 0.0
        for j in range(i - n + 1, i):
            e = x[j + 1] - (a + b * x[j])
            ss += e * e
        sig = np.sqrt(ss / max(k - 2, 1))
        theta = a / (1.0 - b)
        seq = sig / np.sqrt(1.0 - b * b)
        kk = -np.log(b)
        kap[i] = kk
        hl[i] = np.log(2.0) / kk
        if seq > 0:
            z[i] = (x[i] - theta) / seq
    return kap, hl, z


@njit(cache=True)
def dfa_hurst(r, n, smin, smax, nscale):
    """Detrended fluctuation analysis on a rolling window of the increment series.

    The profile is the cumulative sum of the demeaned increments; each scale s splits it into
    non-overlapping windows, removes a linear trend from each, and takes the RMS. F(s) ~ s^H, so H
    is the slope of log F against log s. H = 0.5 is a random walk in the increments.
    """
    m = len(r)
    out = np.full(m, np.nan)
    scales = np.empty(nscale, np.int64)
    lg0, lg1 = np.log(smin), np.log(smax)
    for q in range(nscale):
        scales[q] = int(np.exp(lg0 + (lg1 - lg0) * q / max(nscale - 1, 1)) + 0.5)
    prof = np.empty(n)
    for i in range(n, m):
        mu = 0.0
        for j in range(n):
            mu += r[i - n + 1 + j]
        mu /= n
        c = 0.0
        for j in range(n):
            c += r[i - n + 1 + j] - mu
            prof[j] = c
        sl = 0.0; sll = 0.0; sf = 0.0; slf = 0.0; cnt = 0
        for q in range(nscale):
            s = scales[q]
            if s < 4 or s > n // 4:
                continue
            nw = n // s
            tot = 0.0
            for w in range(nw):
                sx = 0.0; sy = 0.0; sxx = 0.0; sxy = 0.0
                for t in range(s):
                    xv = float(t); yv = prof[w * s + t]
                    sx += xv; sy += yv; sxx += xv * xv; sxy += xv * yv
                dd = s * sxx - sx * sx
                if dd <= 0:
                    continue
                bb = (s * sxy - sx * sy) / dd
                aa = (sy - bb * sx) / s
                ss = 0.0
                for t in range(s):
                    e = prof[w * s + t] - (aa + bb * t)
                    ss += e * e
                tot += ss / s
            if nw <= 0 or tot <= 0:
                continue
            f = np.sqrt(tot / nw)
            if f <= 0:
                continue
            ls = np.log(float(s)); lf = np.log(f)
            sl += ls; sll += ls * ls; sf += lf; slf += ls * lf; cnt += 1
        if cnt >= 3:
            dd = cnt * sll - sl * sl
            if dd > 0:
                out[i] = (cnt * slf - sl * sf) / dd
    return out


@njit(cache=True)
def var_ratio(r, n, q):
    """Lo-MacKinlay VR(q) and the heteroskedasticity-consistent z*.

    VR = 1 under any martingale difference sequence, > 1 under positive autocorrelation
    (persistence), < 1 under reversion. The robust z is what makes it a TEST rather than a ratio.
    """
    m = len(r)
    vr = np.full(m, np.nan); zst = np.full(m, np.nan)
    for i in range(n, m):
        mu = 0.0
        for j in range(n):
            mu += r[i - n + 1 + j]
        mu /= n
        v1 = 0.0
        for j in range(n):
            d = r[i - n + 1 + j] - mu
            v1 += d * d
        v1 /= (n - 1)
        if v1 <= 0:
            continue
        nq = n - q + 1
        vq = 0.0
        for j in range(nq):
            s = 0.0
            for t in range(q):
                s += r[i - n + 1 + j + t]
            d = s - q * mu
            vq += d * d
        vq /= (q * nq)
        ratio = vq / v1
        vr[i] = ratio
        # heteroskedasticity-robust variance of VR-1
        theta = 0.0
        for k in range(1, q):
            num = 0.0; den = 0.0
            for j in range(k, n):
                a = r[i - n + 1 + j] - mu
                b = r[i - n + 1 + j - k] - mu
                num += a * a * b * b
            for j in range(n):
                d = r[i - n + 1 + j] - mu
                den += d * d
            den = den * den                     # (sum of squared deviations)^2, per Lo-MacKinlay
            if den > 0:
                dk = num / den
                w = 2.0 * (q - k) / q
                theta += w * w * dk
        if theta > 0:
            zst[i] = (ratio - 1.0) / np.sqrt(theta)
    return vr, zst


@njit(cache=True)
def bns_jump(r, n):
    """Barndorff-Nielsen / Shephard: the share of realised variance that is JUMP, and the ratio
    test statistic. BV estimates the CONTINUOUS part and is robust to jumps; RV is not."""
    m = len(r)
    share = np.full(m, np.nan); zs = np.full(m, np.nan)
    mu1 = np.sqrt(2.0 / np.pi)
    for i in range(n, m):
        rv = 0.0; bv = 0.0; qp = 0.0
        for j in range(n):
            a = r[i - n + 1 + j]
            rv += a * a
        for j in range(1, n):
            bv += abs(r[i - n + 1 + j]) * abs(r[i - n + j])
        bv /= (mu1 * mu1)
        for j in range(3, n):
            qp += (abs(r[i - n + 1 + j]) * abs(r[i - n + j]) *
                   abs(r[i - n + j - 1]) * abs(r[i - n + j - 2]))
        qp = (n / (0.7978845608 ** 4)) * qp   # quadpower quarticity carries a leading n
        if rv <= 0 or bv <= 0 or qp <= 0:
            continue
        s = 1.0 - bv / rv
        share[i] = s if s > 0 else 0.0
        denom = (((np.pi * np.pi / 4.0) + np.pi - 5.0) / n) * max(1.0, qp / (bv * bv))
        if denom > 0:
            zs[i] = s / np.sqrt(denom)
    return share, zs


@njit(cache=True)
def perm_entropy(x, n, mdim):
    """Bandt-Pompe permutation entropy, normalised to [0,1]. 1 = maximally disordered."""
    m = len(x)
    out = np.full(m, np.nan)
    nfac = 1
    for k in range(2, mdim + 1):
        nfac *= k
    cnt = np.empty(nfac, np.int64)
    perm = np.empty(mdim, np.int64)
    for i in range(n, m):
        for k in range(nfac):
            cnt[k] = 0
        tot = 0
        for j in range(n - mdim + 1):
            for a in range(mdim):
                perm[a] = a
            for a in range(mdim):
                for b in range(a + 1, mdim):
                    if x[i - n + 1 + j + perm[a]] > x[i - n + 1 + j + perm[b]]:
                        t = perm[a]; perm[a] = perm[b]; perm[b] = t
            code = 0
            for a in range(mdim):
                v = perm[a]
                sub = 0
                for b in range(a):
                    if perm[b] < v:
                        sub += 1
                f = 1
                for k in range(2, mdim - a):
                    f *= k
                code += (v - sub) * f
            if 0 <= code < nfac:
                cnt[code] += 1
                tot += 1
        if tot > 0:
            h = 0.0
            for k in range(nfac):
                if cnt[k] > 0:
                    p = cnt[k] / tot
                    h -= p * np.log(p)
            out[i] = h / np.log(float(nfac))
    return out


@njit(cache=True)
def kalman_ls(x, q_level, q_slope, r_obs):
    """Local level plus slope, filtered (never smoothed -- a smoother reads the future).

    Returns the filtered slope and its standard error, so the signal is a t-statistic on the slope
    rather than the slope itself, which is what makes it comparable across volatility regimes.
    """
    m = len(x)
    slope = np.full(m, np.nan); se = np.full(m, np.nan)
    lv = x[0]; sl = 0.0
    p00 = 1.0; p01 = 0.0; p11 = 1.0
    for i in range(1, m):
        lv = lv + sl
        p00 = p00 + 2.0 * p01 + p11 + q_level
        p01 = p01 + p11
        p11 = p11 + q_slope
        s = p00 + r_obs
        if s <= 0:
            continue
        k0 = p00 / s
        k1 = p01 / s
        v = x[i] - lv
        lv = lv + k0 * v
        sl = sl + k1 * v
        n00 = p00 - k0 * p00
        n01 = p01 - k0 * p01
        n11 = p11 - k1 * p01
        p00 = n00; p01 = n01; p11 = n11
        slope[i] = sl
        se[i] = np.sqrt(p11) if p11 > 0 else np.nan
    return slope, se


# =================================================================================================
# positive controls -- recover a known answer before touching price
# =================================================================================================
def controls(seed=0):
    rng = np.random.default_rng(seed)
    rows = []

    # OU with known kappa
    for true_hl in (20.0, 60.0):
        kap = np.log(2.0) / true_hl
        b = np.exp(-kap); theta = 5.0; sig = 0.02
        x = np.empty(60000); x[0] = theta
        for i in range(1, len(x)):
            x[i] = theta + b * (x[i - 1] - theta) + rng.normal(0, sig)
        _, hl, z = ou_fit(x, 2000)
        rows.append(dict(test="OU half-life", truth=true_hl,
                         got=float(np.nanmedian(hl[3000:])),
                         extra=f"z sd {np.nanstd(z[3000:]):.3f} (target 1.000)"))

    # DFA on a known-H series: white noise increments -> H 0.5
    r = rng.normal(size=40000)
    h = dfa_hurst(r, 2000, 8, 200, 10)
    rows.append(dict(test="DFA H, white noise", truth=0.5,
                     got=float(np.nanmedian(h[3000:])), extra=""))
    # persistent increments by construction (AR(1) with phi 0.5) -> H > 0.5
    ar = np.empty(40000); ar[0] = 0.0
    for i in range(1, len(ar)):
        ar[i] = 0.5 * ar[i - 1] + rng.normal()
    h2 = dfa_hurst(ar, 2000, 8, 200, 10)
    rows.append(dict(test="DFA H, AR(1) phi=0.5", truth=float("nan"),
                     got=float(np.nanmedian(h2[3000:])), extra="must exceed the white-noise value"))

    # variance ratio: martingale -> VR 1 and |z| calibrated
    r = rng.normal(size=40000)
    vr, zs = var_ratio(r, 1000, 4)
    rows.append(dict(test="VR(4), martingale", truth=1.0, got=float(np.nanmedian(vr[2000:])),
                     extra=f"share |z|>1.96 {float(np.nanmean(np.abs(zs[2000:]) > 1.96)):.3f}"))
    # mean-reverting increments -> VR < 1
    mr = np.empty(40000); mr[0] = 0.0
    for i in range(1, len(mr)):
        mr[i] = -0.3 * mr[i - 1] + rng.normal()
    vr2, _ = var_ratio(mr, 1000, 4)
    rows.append(dict(test="VR(4), AR(1) phi=-0.3", truth=float("nan"),
                     got=float(np.nanmedian(vr2[2000:])), extra="must be < 1"))

    # BNS: pure diffusion -> jump share ~0; with jumps -> detected
    r = rng.normal(0, 0.01, size=40000)
    s0, _ = bns_jump(r, 500)
    rj = r.copy()
    idx = rng.choice(len(rj), size=200, replace=False)
    rj[idx] += rng.normal(0, 0.08, size=200)
    s1, _ = bns_jump(rj, 500)
    rows.append(dict(test="BNS jump share", truth=0.0, got=float(np.nanmedian(s0[1000:])),
                     extra=f"with jumps {float(np.nanmedian(s1[1000:])):.3f} (must be larger)"))

    # permutation entropy: noise -> ~1, monotone ramp -> ~0
    pe_n = perm_entropy(rng.normal(size=20000), 500, 4)
    ramp = np.arange(20000, dtype=float) + rng.normal(0, 1e-9, size=20000)
    pe_r = perm_entropy(ramp, 500, 4)
    rows.append(dict(test="perm entropy, noise", truth=1.0, got=float(np.nanmedian(pe_n[1000:])),
                     extra=f"monotone ramp {float(np.nanmedian(pe_r[1000:])):.3f} (target 0.000)"))

    # Kalman: recover a known constant slope
    tru = 0.01
    x = np.cumsum(np.full(20000, tru)) + rng.normal(0, 0.5, size=20000)
    sl, se = kalman_ls(x, 1e-7, 1e-9, 0.25)
    rows.append(dict(test="Kalman slope", truth=tru, got=float(np.nanmedian(sl[5000:])), extra=""))
    return pd.DataFrame(rows)


@njit(cache=True)
def kalman_ls_var(x, q_level, q_slope, r_obs):
    """As `kalman_ls` but with a per-bar observation variance, so the tuning constant can be an
    EXPANDING estimate rather than a whole-sample one."""
    m = len(x)
    slope = np.full(m, np.nan); se = np.full(m, np.nan)
    lv = x[0]; sl = 0.0
    p00 = 1.0; p01 = 0.0; p11 = 1.0
    for i in range(1, m):
        lv = lv + sl
        p00 = p00 + 2.0 * p01 + p11 + q_level
        p01 = p01 + p11
        p11 = p11 + q_slope
        s = p00 + r_obs[i]
        if s <= 0:
            continue
        k0 = p00 / s
        k1 = p01 / s
        v = x[i] - lv
        lv = lv + k0 * v
        sl = sl + k1 * v
        n00 = p00 - k0 * p00
        n01 = p01 - k0 * p01
        n11 = p11 - k1 * p01
        p00 = n00; p01 = n01; p11 = n11
        slope[i] = sl
        se[i] = np.sqrt(p11) if p11 > 0 else np.nan
    return slope, se


def load(name, tf=30):
    from v38 import v38feeds as F
    if name == "NQ":
        d = pd.read_csv(os.path.join(ROOT, "data/NQ_1m.csv"))
        c = {x.lower(): x for x in d.columns}
        ts = pd.to_datetime(d[c.get("timestamp", c.get("datetime", list(d.columns)[0]))], utc=True)
        d.index = pd.DatetimeIndex(ts).tz_convert("America/New_York").tz_localize(None)
        f = d.rename(columns={c["open"]: "open", c["high"]: "high", c["low"]: "low",
                              c["close"]: "close"})[["open", "high", "low", "close"]]
        src = 1
    else:
        f = F.load(name)[["open", "high", "low", "close"]]
        src = 15
    if tf != src:
        f = f.resample(f"{tf}min", label="left", closed="left").agg(
            dict(open="first", high="max", low="min", close="last")).dropna()
    f = f.copy()
    h, l, c = f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy()
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    f["atr"] = pd.Series(tr).ewm(span=14, adjust=False).mean().to_numpy()
    f["mod"] = f.index.hour * 60 + f.index.minute
    return f


def states(f, W=500):
    """All six estimators on one frame, causal. Returns a DataFrame of raw states."""
    c = f["close"].to_numpy()
    lx = np.log(c)
    r = np.r_[0.0, np.diff(lx)]
    S = pd.DataFrame(index=f.index)
    kap, hl, z = ou_fit(lx, W)
    S["ou.kappa"] = kap; S["ou.halflife"] = hl; S["ou.z"] = z
    S["dfa.H"] = dfa_hurst(r, W, 8, max(10, W // 5), 10)
    vr, zs = var_ratio(r, W, 4)
    S["vr.ratio"] = vr; S["vr.z"] = zs
    sh, jz = bns_jump(r, min(W, 300))
    S["bns.share"] = sh; S["bns.z"] = jz
    S["pe.h"] = perm_entropy(lx, min(W, 400), 4)
    # r_obs from an EXPANDING variance -- a whole-sample np.nanvar here is a look-ahead constant,
    # which is exactly what the truncation audit caught on the first run.
    rv_exp = pd.Series(r).expanding(min_periods=200).var().bfill().to_numpy()
    sl, se = kalman_ls_var(lx, 1e-7, 1e-9, np.ascontiguousarray(rv_exp * 4.0 + 1e-12))
    S["kf.t"] = sl / np.where(se > 0, se, np.nan)
    return S


def pf(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return float(x[x > 0].sum() / max(-x[x < 0].sum(), 1e-12)) if len(x) >= 5 else np.nan
