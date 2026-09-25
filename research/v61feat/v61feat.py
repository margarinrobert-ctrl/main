"""FEATURE ENGINEERING ON THE V61 CVD RULE AT 15 MINUTES -- the meta layer, and only the meta layer.

THE ARCHITECTURE, AND WHY IT IS THE ARCHITECTURE. The primary is the V61 CVD exhausted-sellers rule
on 15-minute NQ. It EMITS EVENTS. Everything in this file SCORES those events and nothing in it can
create one. That separation is the whole point: a feature layer that can also fire trades will
always find something, and the thing it finds will be the maximum of the search.

>>> FRACDIFF AND THE HMM ARE META FEATURES AND NEVER SIGNALS. Both are here, both are causal, and
>>> neither can put on a trade. The HMM is the one this branch has been burned by: `STUDY_V27_HMM`
>>> measured a fit-on-all + SMOOTHED decode at locked PF 1.351 against the CAUSAL version of the
>>> same model and rule at 0.973 -- with NEARLY IDENTICAL TRADE COUNTS, so the leak is invisible in
>>> the count and shows only in which bars got labelled. So: parameters fitted on the RESEARCH
>>> block only, and the FILTERED posterior only (forward pass, data through t). The smoothed
>>> posterior is computed for exactly one purpose, a leakage diagnostic, and never enters a model.

SEVEN DECLARED FAMILIES, fixed before any scoring, so the family count is not itself a search:
    trend      trend strength and direction persistence
    struct     breakout structure -- where this bar sits in its own channel and its own range
    mom        momentum at several horizons
    vol        volatility level, ratio and expansion
    volu       participation, against a TIME-OF-DAY baseline (a raw volume mean is a clock feature)
    regime     chop, HMM filtered posteriors, session position
    ffd        fixed-width fractional differencing of price and of the CVD

EVERY FEATURE IS READ AT THE SIGNAL BAR. `STUDY_AUCTION` recorded what reading them at the FILL bar
costs: a holdout result at p 0.0005 that replicated across nine strategies and was pure leakage.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61sess", "research/v27", "research/v18", "research/v54"):
    q = os.path.join(ROOT, p)
    if q not in sys.path:
        sys.path.insert(0, q)

import sess_core as S      # noqa: E402
import v27hmm as H         # noqa: E402
from v18diag import adf    # noqa: E402

D_LADDER = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)


# ------------------------------------------------------------------ fracdiff
def ffd_weights(d, tau=1e-4, max_k=3000):
    w = [1.0]
    for k in range(1, max_k):
        nw = -w[-1] * (d - k + 1) / k
        if abs(nw) < tau:
            break
        w.append(nw)
    return np.array(w[::-1])


def ffd(x, d, tau=1e-4):
    """Fixed-width fractional difference: out[t] uses a FIXED number of prior bars and nothing after."""
    w = ffd_weights(d, tau)
    L = len(w)
    out = np.full(len(x), np.nan)
    if L <= len(x):
        out[L - 1:] = np.convolve(np.asarray(x, float), w[::-1], mode="valid")
    return out, L


def choose_d(x, mask, tau=1e-4):
    """Smallest d on the declared ladder whose ADF t clears the 5% MacKinnon value, ON `mask` ONLY.
    Choosing d on the block the meta layer is judged on would be selection."""
    rows, pick, got = [], D_LADDER[-1], False
    for d in D_LADDER:
        f, L = ffd(x, d, tau)
        s = f[mask & np.isfinite(f)][::4][-20000:]
        t, crit, _lag = adf(s)
        c5 = crit["5%"] if isinstance(crit, dict) else -2.86
        ok = bool(np.isfinite(t) and t < c5)
        rows.append(dict(d=d, window=L, adf_t=t, crit5=c5, stationary=ok))
        if not got and ok:
            pick, got = d, True
    return pick, pd.DataFrame(rows)


# ------------------------------------------------------------------ HMM
def _hmm_obs(D):
    c = D["c"]
    r = np.zeros_like(c)
    r[1:] = np.diff(np.log(c))
    rv = pd.Series(r).rolling(96).std().to_numpy()
    return np.column_stack([r * 100.0, np.nan_to_num(rv * 100.0, nan=0.0)])


def hmm_fit(D, mask_fit, K=3, seed=0):
    """Baum-Welch on the RESEARCH block only. K is a hyperparameter and is counted as a trial."""
    x = _hmm_obs(D)[mask_fit]
    pi, A, mu, var, ll = H.fit(x[::6], K=K, iters=40, seed=seed)
    return dict(pi=pi, A=A, mu=mu, var=var, ll=ll, order=np.argsort(mu[:, 0]), K=K)


def hmm_states(D, hp, want_smoothed=False):
    """FILTERED posteriors under FROZEN parameters. Smoothed is a DIAGNOSTIC, never a feature."""
    x = _hmm_obs(D)
    filt = H.posterior_filtered(x, hp["pi"], hp["A"], hp["mu"], hp["var"])[:, hp["order"]]
    smoo = H.posterior_smoothed(x, hp["pi"], hp["A"], hp["mu"], hp["var"])[:, hp["order"]] if want_smoothed else None
    return filt, smoo


# ------------------------------------------------------------------ helpers
def _ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def _rank(x, n):
    return pd.Series(x).rolling(n).rank(pct=True).to_numpy()


def _rsi(c, n=14):
    d = np.diff(c, prepend=c[0])
    up = pd.Series(np.where(d > 0, d, 0.0)).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    dn = pd.Series(np.where(d < 0, -d, 0.0)).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    return 100.0 - 100.0 / (1.0 + up / np.maximum(dn, 1e-12))


def _adx(h, l, c, n=14):
    up = np.diff(h, prepend=h[0])
    dn = -np.diff(l, prepend=l[0])
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    a = lambda z: pd.Series(z).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    atr = np.maximum(a(tr), 1e-12)
    pdi, ndi = 100 * a(pdm) / atr, 100 * a(ndm) / atr
    dx = 100 * np.abs(pdi - ndi) / np.maximum(pdi + ndi, 1e-12)
    return a(dx), pdi, ndi


def _chop(h, l, c, n=14):
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    st = pd.Series(tr).rolling(n).sum().to_numpy()
    rng = pd.Series(h).rolling(n).max().to_numpy() - pd.Series(l).rolling(n).min().to_numpy()
    with np.errstate(all="ignore"):
        return 100.0 * np.log10(st / np.maximum(rng, 1e-12)) / np.log10(n)


def _er(c, n):
    """Kaufman efficiency ratio: net move over summed absolute moves. Trend QUALITY, not direction."""
    d = np.abs(np.diff(c, prepend=c[0]))
    net = np.abs(c - np.concatenate((np.full(n, np.nan), c[:-n])))
    return net / np.maximum(pd.Series(d).rolling(n).sum().to_numpy(), 1e-12)


def _lin_r2(c, n):
    """R^2 of an OLS fit over the last n closes -- how straight the move is."""
    s = pd.Series(c)
    x = np.arange(n, dtype=float)
    xm = x.mean()
    sxx = ((x - xm) ** 2).sum()
    def f(y):
        ym = y.mean()
        sxy = ((x - xm) * (y - ym)).sum()
        syy = ((y - ym) ** 2).sum()
        return (sxy * sxy) / (sxx * syy) if syy > 0 else np.nan
    return s.rolling(n).apply(f, raw=True).to_numpy()


def build_features(D, mask_research=None, frozen=None, want_smoothed=False):
    """Seven declared families, all causal, all read at the bar they are stamped on."""
    o, h, l, c, v = D["o"], D["h"], D["l"], D["c"], D["v"]
    atr, n, mod = D["atr"], D["n"], D["mod"]
    F = {}
    lc = np.log(c)

    if frozen is None:
        d, dtab = choose_d(lc, mask_research)
        hp = hmm_fit(D, mask_research, K=3, seed=0)
    else:
        d, dtab, hp = frozen["d"], frozen.get("d_table"), frozen["hmm"]

    # ---- trend
    ax, pdi, ndi = _adx(h, l, c, 14)
    F["trend.adx14"] = ax
    F["trend.di_diff"] = pdi - ndi
    e50, e200 = _ema(c, 50), _ema(c, 200)
    F["trend.d_ema50"] = (c - e50) / np.maximum(atr, 1e-12)
    F["trend.d_ema200"] = (c - e200) / np.maximum(atr, 1e-12)
    F["trend.slope200"] = (e200 - np.concatenate((np.full(50, np.nan), e200[:-50]))) / np.maximum(atr, 1e-12)
    F["trend.er20"] = _er(c, 20)
    F["trend.er60"] = _er(c, 60)
    F["trend.r2_50"] = _lin_r2(c, 50)
    F["trend.align"] = ((c > e50).astype(float) + (c > e200).astype(float) + (e50 > e200).astype(float))
    up = (c > o).astype(float)
    F["trend.up_share20"] = pd.Series(up).rolling(20).mean().to_numpy()

    # ---- breakout structure
    ehi20 = D["ent_hi"][20 - 2]
    F["struct.excess"] = (h - ehi20) / np.maximum(atr, 1e-12)
    F["struct.ch_width"] = (pd.Series(h).rolling(20).max().to_numpy()
                            - pd.Series(l).rolling(20).min().to_numpy()) / np.maximum(atr, 1e-12)
    F["struct.pos_in_ch"] = (c - pd.Series(l).rolling(20).min().to_numpy()) / np.maximum(
        pd.Series(h).rolling(20).max().to_numpy() - pd.Series(l).rolling(20).min().to_numpy(), 1e-12)
    F["struct.close_pos"] = (c - l) / np.maximum(h - l, 1e-12)
    F["struct.body"] = np.abs(c - o) / np.maximum(atr, 1e-12)
    F["struct.upper_wick"] = (h - np.maximum(o, c)) / np.maximum(h - l, 1e-12)
    F["struct.range_atr"] = (h - l) / np.maximum(atr, 1e-12)
    F["struct.gap_open"] = (o - np.concatenate(([c[0]], c[:-1]))) / np.maximum(atr, 1e-12)
    hi55 = pd.Series(h).rolling(55).max().shift(1).to_numpy()
    F["struct.d_hi55"] = (c - hi55) / np.maximum(atr, 1e-12)

    # ---- momentum
    for k in (5, 20, 60, 240):
        F[f"mom.roc{k}"] = 100.0 * (c / np.concatenate((np.full(k, np.nan), c[:-k])) - 1.0)
    F["mom.rsi14"] = _rsi(c, 14)
    F["mom.rsi48"] = _rsi(c, 48)
    m12, m26 = _ema(c, 12), _ema(c, 26)
    F["mom.macd_hist"] = (m12 - m26 - _ema(m12 - m26, 9)) / np.maximum(atr, 1e-12)
    F["mom.tsmom96"] = (c - np.concatenate((np.full(96, np.nan), c[:-96]))) / np.maximum(atr, 1e-12)

    # ---- volatility
    ap = atr / np.maximum(c, 1e-12)
    F["vol.atr_pct"] = ap
    F["vol.atr_rank250"] = _rank(ap, 250)
    F["vol.atr_ratio50"] = atr / np.maximum(pd.Series(atr).rolling(50).mean().to_numpy(), 1e-12)
    r1 = np.zeros(n)
    r1[1:] = np.diff(np.log(c))
    rv = pd.Series(r1).rolling(96).std().to_numpy()
    F["vol.rv96"] = rv * 100.0
    F["vol.rv_ratio"] = rv / np.maximum(pd.Series(r1).rolling(480).std().to_numpy(), 1e-12)
    with np.errstate(all="ignore"):
        pk = np.sqrt(pd.Series((np.log(h / np.maximum(l, 1e-12)) ** 2) / (4 * np.log(2))).rolling(48).mean().to_numpy())
    F["vol.parkinson"] = pk * 100.0
    F["vol.vol_of_vol"] = pd.Series(rv).rolling(96).std().to_numpy() / np.maximum(rv, 1e-12)

    # ---- participation, against a TIME-OF-DAY baseline
    dfv = pd.DataFrame({"v": v, "mod": mod})
    tod = dfv.groupby("mod")["v"].transform(lambda s: s.shift(1).expanding().mean()).to_numpy()
    F["volu.vs_tod"] = v / np.maximum(tod, 1e-9)
    F["volu.vs_ma50"] = v / np.maximum(pd.Series(v).rolling(50).mean().to_numpy(), 1e-9)
    F["volu.z50"] = (v - pd.Series(v).rolling(50).mean().to_numpy()) / np.maximum(
        pd.Series(v).rolling(50).std().to_numpy(), 1e-9)
    upv = np.where(c > o, v, 0.0)
    F["volu.up_share20"] = pd.Series(upv).rolling(20).sum().to_numpy() / np.maximum(
        pd.Series(v).rolling(20).sum().to_numpy(), 1e-9)
    F["volu.trend20"] = (pd.Series(v).rolling(20).mean().to_numpy()
                         / np.maximum(pd.Series(v).rolling(100).mean().to_numpy(), 1e-9))

    # ---- regime
    F["regime.chop14"] = _chop(h, l, c, 14)
    F["regime.chop48"] = _chop(h, l, c, 48)
    filt, smoo = hmm_states(D, hp, want_smoothed=want_smoothed)
    F["regime.hmm_bear"], F["regime.hmm_side"], F["regime.hmm_bull"] = filt[:, 0], filt[:, 1], filt[:, 2]
    F["regime.hmm_edge"] = filt[:, 2] - filt[:, 0]
    F["regime.hmm_conf"] = filt.max(axis=1)
    F["regime.tod"] = np.cos(2 * np.pi * mod / 1440.0)

    # ---- fracdiff
    fd, L = ffd(lc, d)
    F["ffd.price"] = fd
    F["ffd.price_z"] = (fd - pd.Series(fd).rolling(500).mean().to_numpy()) / np.maximum(
        pd.Series(fd).rolling(500).std().to_numpy(), 1e-12)
    cvpos = D["cv"] - np.nanmin(D["cv"]) + 1.0
    fdc, _ = ffd(np.log(cvpos), d)
    F["ffd.cvd"] = fdc
    F["ffd.cvd_z"] = (fdc - pd.Series(fdc).rolling(500).mean().to_numpy()) / np.maximum(
        pd.Series(fdc).rolling(500).std().to_numpy(), 1e-12)

    X = pd.DataFrame(F).replace([np.inf, -np.inf], np.nan)
    return X, dict(d=d, d_table=dtab, ffd_window=L, hmm=hp, smoothed=smoo)


def truncation_audit(D, XF, frozen, probes=25, seed=7):
    """Recompute every feature on history that ENDS at bar i and require the value at i to match."""
    rng = np.random.default_rng(seed)
    lo = max(4000, int(np.flatnonzero(D["blk"] == 1)[0]))
    idx = rng.choice(np.arange(lo, D["n"] - 5), size=probes, replace=False)
    bad, checked = [], 0
    for i in sorted(idx):
        cut = {}
        for k, val in D.items():
            if isinstance(val, np.ndarray) and val.ndim == 2:
                cut[k] = val[:, :i + 1]
            elif isinstance(val, (np.ndarray, pd.DatetimeIndex)) and np.ndim(val) == 1:
                cut[k] = val[:i + 1]
            else:
                cut[k] = val
        cut["n"] = i + 1
        Xi, _ = build_features(cut, frozen=frozen)
        a, b = XF.iloc[i], Xi.iloc[-1]
        for col in XF.columns:
            va, vb = a[col], b[col]
            if not np.isfinite(va) and not np.isfinite(vb):
                continue
            checked += 1
            if not np.isclose(va, vb, rtol=1e-6, atol=1e-8):
                bad.append((i, col, float(va), float(vb)))
    return bad, checked, len(idx)
