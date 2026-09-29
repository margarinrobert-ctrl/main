"""PHASE 0 AND THE META-LAYER FEATURES -- written before any model is trained.

PHASE 0, stated honestly and first. The mechanism-first architecture asks who is on the other
side of this trade, what forces them to trade anyway, and what would end it. **Bhatti's VWAP-EMA
rule names no counterparty.** It is a pattern -- a pullback to an EMA in a session filtered by a
VWAP, a volume spike and a candle shape -- and the paper offers no constrained flow and no risk
transfer to explain why anyone would be on the losing side of it. So this is NOT a mechanism-
derived primary. It is a fitted pattern with ten free numbers, and it inherits the full deflation
burden rather than escaping it. Everything below is labelled accordingly.

WHY THE STUDY IS RUN ANYWAY, and what it can honestly answer. The user asked for feature
engineering and deep learning to find anomalies on this event stream. Two questions are separable:
  (a) can a meta layer rescue a primary that FAILS Gate 1 out of sample?  The branch has answered
      a version of this before (`STUDY_EMA48_VWAP_DL`: on a PF-0.19 base the best subset a model
      could find was -0.30 R at PF 0.32 -- a filter makes a dead base less bad, never alive), and
      re-running it on a different family is worth one clean measurement;
  (b) do UNSUPERVISED ANOMALIES -- bars a model cannot reconstruct -- mark events that behave
      differently?  That is a genuinely new question here and it does not require the primary to
      have an edge, because the answer is interesting in both directions.

THE FEATURES ARE CONFINED TO THE META LAYER. None of them decides direction and none decides
whether an event exists; the primary emits the events and the features only score them.

EVERY UNSUPERVISED MODEL IS FITTED ON THE RESEARCH BLOCK ONLY -- the autoencoder, the isolation
forest, the Mahalanobis covariance, the HMM and the fractional-differencing order. Fitting any of
them on the whole series is the same leak class as `STUDY_V27`'s smoothed HMM decode, which read
locked PF 1.351 against a causal 0.973 on IDENTICAL trade counts.

NINE DECLARED FAMILIES, prefixes fixed so a family-importance table cannot credit one family's
weight to another (`STUDY_V32`: `vol.` already owned 71 volatility columns, so the volume family
had to become `vlm.`):
    vol.    volatility state, against a CAUSAL TIME-OF-DAY baseline rather than a trailing mean --
            NQ's RTH ATR is 2.7x its overnight ATR, so a plain `atr / sma(atr)` is a clock
            (`STUDY_VWAP_STOCH_ATR`)
    trn.    trend context: distance from the slow EMA in ATR units, slopes, efficiency ratio
    reg.    regime: CHOP, ADX, and a Baum-Welch HMM read FILTERED, never smoothed
    vlm.    participation, against the same causal time-of-day baseline
    str.    bar structure: body, wicks, close position, gaps
    clk.    the clock: minutes since the session open, minutes to the close
    hst.    how the last k instances of THIS SAME EVENT resolved -- the one family the skill names
            explicitly, and the only one that is about the event stream rather than the bar
    ffd.    fractional differencing, d chosen by ADF ON THE RESEARCH BLOCK ONLY
    anm.    THE ANOMALY FAMILY: autoencoder reconstruction error, isolation-forest score,
            Mahalanobis distance, and joint-outlier flags
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vwapema"))
import vecore as V  # noqa: E402
import ve_markets as M  # noqa: E402


# ------------------------------------------------------------------ small causal helpers
def _ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def _roll(x, n, fn="mean"):
    s = pd.Series(x).rolling(n, min_periods=max(3, n // 3))
    return getattr(s, fn)().to_numpy()


def tod_baseline(x, mod, day, min_obs=20):
    """The EXPANDING mean of `x` at this minute-of-day over PRIOR sessions only.

    A trailing mean is not a volatility baseline on a 24-hour tape: an RTH bar clears its own
    50-bar trailing mean ~99% of the time simply because RTH is busier than the overnight. This
    conditions on the clock instead, and it is causal because the running sum excludes today.
    """
    out = np.full(len(x), np.nan)
    df = pd.DataFrame({"x": x, "mod": mod, "day": day})
    for m, g in df.groupby("mod", sort=False):
        v = g.x.to_numpy(float)
        c = np.cumsum(np.nan_to_num(v))
        k = np.cumsum(np.isfinite(v).astype(float))
        prior_sum = np.concatenate(([0.0], c[:-1]))
        prior_n = np.concatenate(([0.0], k[:-1]))
        val = np.where(prior_n >= min_obs, prior_sum / np.maximum(prior_n, 1), np.nan)
        out[g.index.to_numpy()] = val
    return out


def chop(h, l, c, n=14):
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.concatenate(([c[0]], c[:-1]))),
                                      np.abs(l - np.concatenate(([c[0]], c[:-1])))))
    s = _roll(tr, n, "sum")
    rng = _roll(h, n, "max") - _roll(l, n, "min")
    with np.errstate(divide="ignore", invalid="ignore"):
        return 100.0 * np.log10(np.maximum(s, 1e-12) / np.maximum(rng, 1e-12)) / np.log10(n)


def adx(h, l, c, n=14):
    up = np.diff(h, prepend=h[0])
    dn = -np.diff(l, prepend=l[0])
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    pdi = 100 * pd.Series(pdm).ewm(alpha=1 / n, adjust=False).mean().to_numpy() / np.maximum(atr, 1e-9)
    ndi = 100 * pd.Series(ndm).ewm(alpha=1 / n, adjust=False).mean().to_numpy() / np.maximum(atr, 1e-9)
    dx = 100 * np.abs(pdi - ndi) / np.maximum(pdi + ndi, 1e-9)
    return pd.Series(dx).ewm(alpha=1 / n, adjust=False).mean().to_numpy(), pdi, ndi


def eff_ratio(c, n=20):
    num = np.abs(c - np.concatenate((np.full(n, np.nan), c[:-n])))
    den = _roll(np.abs(np.diff(c, prepend=c[0])), n, "sum")
    return num / np.maximum(den, 1e-9)


# ------------------------------------------------------------------ fractional differencing
def ffd_weights(d, thresh=1e-4, max_k=400):
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
    if k > len(x):
        return out
    lx = np.log(np.maximum(x, 1e-12))
    for i in range(k - 1, len(x)):
        out[i] = float(np.dot(w, lx[i - k + 1:i + 1]))
    return out


def adf_stat(x):
    """A plain ADF t-statistic with one lag -- enough to pick `d`, and no statsmodels dependency."""
    x = x[np.isfinite(x)]
    if len(x) < 200:
        return np.nan
    dx = np.diff(x)
    X = np.column_stack([x[:-1], np.ones(len(dx)), np.concatenate(([0.0], dx[:-1]))])
    b, *_ = np.linalg.lstsq(X, dx, rcond=None)
    r = dx - X @ b
    s2 = r @ r / max(len(dx) - X.shape[1], 1)
    xtx = np.linalg.pinv(X.T @ X)
    return float(b[0] / np.sqrt(max(s2 * xtx[0, 0], 1e-18)))


def pick_d(c, blk, grid=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)):
    """Smallest `d` whose FFD series is stationary at the 5% level, chosen ON RESEARCH ONLY."""
    m = blk == 0
    for d in grid:
        s = ffd(c[m], d)
        if np.isfinite(adf_stat(s)) and adf_stat(s) < -2.86:
            return float(d)
    return 1.0


# ------------------------------------------------------------------ a causal Gaussian HMM
class HMM:
    """Baum-Welch on the RESEARCH block, then the FILTERED posterior only.

    `hmmlearn`'s `predict` runs Viterbi over the whole sequence and labels the past with the
    future. On this branch the same leak read locked PF 1.351 against a causal 0.973 with the trade
    counts nearly identical (`STUDY_V27`), so the leak is invisible in the count.
    """

    def __init__(self, k=3, iters=40, seed=0):
        self.k, self.iters, self.rng = k, iters, np.random.default_rng(seed)

    def fit(self, x):
        x = np.asarray(x, float)
        x = x[np.isfinite(x)]
        # STANDARDISE FIRST. 15-minute log returns are ~1e-4, so an unscaled Gaussian emission
        # reaches ~400 and the scaled backward recursion divides by a scale that has underflowed to
        # 1e-300 on a single outlier bar -- the whole posterior then comes back NaN, which reads as
        # "no signal" rather than as an error (CLAUDE.md: the KAMA that returned 99.9% NaN).
        self.x_mu_, self.x_sd_ = float(x.mean()), float(max(x.std(), 1e-12))
        x = (x - self.x_mu_) / self.x_sd_
        k = self.k
        q = np.quantile(x, np.linspace(0.15, 0.85, k))
        self.mu = q.copy()
        self.sd = np.full(k, max(x.std(), 1e-6))
        self.A = np.full((k, k), 0.1 / (k - 1))
        np.fill_diagonal(self.A, 0.9)
        self.pi = np.full(k, 1.0 / k)
        for _ in range(self.iters):
            B = self._emit(x)
            a, cscale = self._fwd(B)
            b = self._bwd(B, cscale)
            g = a * b
            g /= np.maximum(g.sum(1, keepdims=True), 1e-300)
            xi = np.zeros((k, k))
            for t in range(len(x) - 1):
                m = (a[t][:, None] * self.A) * (B[t + 1] * b[t + 1])[None, :]
                xi += m / max(m.sum(), 1e-300)
            self.A = xi / np.maximum(xi.sum(1, keepdims=True), 1e-300)
            self.pi = g[0] / max(g[0].sum(), 1e-300)
            w = g / np.maximum(g.sum(0, keepdims=True), 1e-300)
            self.mu = (w * x[:, None]).sum(0)
            # a variance FLOOR, or one state collapses onto a handful of bars and its density
            # spikes, which is what makes the scaled recursions overflow
            self.sd = np.sqrt(np.maximum((w * (x[:, None] - self.mu) ** 2).sum(0), 1e-4))
            if not (np.isfinite(self.mu).all() and np.isfinite(self.sd).all()):
                raise RuntimeError("HMM diverged -- refusing to return a NaN posterior")
        return self

    def _emit(self, x):
        z = np.clip((x[:, None] - self.mu) / self.sd, -40.0, 40.0)
        b = np.exp(-0.5 * z * z) / (self.sd * np.sqrt(2 * np.pi))
        return np.maximum(b, 1e-300)

    def _fwd(self, B):
        n, k = B.shape
        a = np.zeros((n, k))
        cs = np.zeros(n)
        a[0] = self.pi * B[0]
        cs[0] = max(a[0].sum(), 1e-300)
        a[0] /= cs[0]
        for t in range(1, n):
            a[t] = (a[t - 1] @ self.A) * B[t]
            cs[t] = max(a[t].sum(), 1e-300)
            a[t] /= cs[t]
        return a, cs

    def _bwd(self, B, cs):
        n, k = B.shape
        b = np.zeros((n, k))
        b[-1] = 1.0
        for t in range(n - 2, -1, -1):
            b[t] = (self.A @ (B[t + 1] * b[t + 1])) / cs[t + 1]
            m = b[t].max()
            if m > 1e100 or not np.isfinite(m):      # renormalise rather than let it run away
                b[t] = b[t] / max(m, 1e-300)
        return b

    def filtered(self, x):
        """Forward algorithm only -- bar t's posterior uses data through t and nothing after."""
        x = np.asarray(x, float)
        good = np.isfinite(x)
        out = np.full((len(x), self.k), np.nan)
        if good.sum() == 0:
            return out
        z = (np.where(good, x, 0.0) - self.x_mu_) / self.x_sd_
        B = self._emit(z)
        a, _ = self._fwd(B)
        out[good] = a[good]
        return out

    def means(self):
        """State means back in the ORIGINAL units of the series."""
        return self.mu * self.x_sd_ + self.x_mu_


# ------------------------------------------------------------------ the anomaly models
class AutoEncoder:
    """A small dense autoencoder on standardised bar features. RECONSTRUCTION ERROR is the feature.

    Fitted on the RESEARCH block only. The point is not to predict anything: it is to learn what an
    ordinary bar looks like, so a bar it cannot rebuild is 'anomalous' in a sense that owes nothing
    to the label. That makes it the one family here that cannot be accused of fitting the outcome.
    """

    def __init__(self, hidden=(16, 6), epochs=60, seed=0):
        self.hidden, self.epochs, self.seed = hidden, epochs, seed

    def fit(self, X):
        import torch
        torch.manual_seed(self.seed)
        torch.set_num_threads(2)
        self.mu_ = np.nanmean(X, 0)
        self.sd_ = np.nanstd(X, 0) + 1e-9
        Z = np.nan_to_num((X - self.mu_) / self.sd_, nan=0.0, posinf=0.0, neginf=0.0)
        d = Z.shape[1]
        h1, h2 = self.hidden
        self.net = torch.nn.Sequential(
            torch.nn.Linear(d, h1), torch.nn.ReLU(),
            torch.nn.Linear(h1, h2), torch.nn.ReLU(),
            torch.nn.Linear(h2, h1), torch.nn.ReLU(),
            torch.nn.Linear(h1, d))
        opt = torch.optim.Adam(self.net.parameters(), lr=1e-3)
        T = torch.tensor(Z, dtype=torch.float32)
        n = len(T)
        for _ in range(self.epochs):
            perm = torch.randperm(n)
            for i in range(0, n, 512):
                b = T[perm[i:i + 512]]
                opt.zero_grad()
                loss = ((self.net(b) - b) ** 2).mean()
                loss.backward()
                opt.step()
        return self

    def error(self, X):
        import torch
        Z = np.nan_to_num((X - self.mu_) / self.sd_, nan=0.0, posinf=0.0, neginf=0.0)
        with torch.no_grad():
            R = self.net(torch.tensor(Z, dtype=torch.float32)).numpy()
        return np.sqrt(((R - Z) ** 2).mean(1))


def mahalanobis(X, fit_mask):
    mu = np.nanmean(X[fit_mask], 0)
    C = np.cov(np.nan_to_num(X[fit_mask] - mu, nan=0.0), rowvar=False)
    P = np.linalg.pinv(C + 1e-9 * np.eye(C.shape[0]))
    D = np.nan_to_num(X - mu, nan=0.0)
    return np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", D, P, D), 0.0))


# ------------------------------------------------------------------ the feature table
BAR_COLS = ["ret1", "ret4", "ret16", "rng_atr", "body_share", "close_pos", "vlm_ratio", "atr_ratio"]


def build(market, cfg, hmm_k=3, seed=0):
    """Every meta feature at the SIGNAL bar of every event the primary emits.

    `cfg` is the primary's own configuration -- it is read, never tuned here.
    """
    D = M.build(market, sess=cfg["sess"])
    sig, _ = V.triggers(D, side=cfg["side"], p=cfg["p"])
    t = M.run(D, sig, side=cfg["side"], tgt_R=cfg["tgt_R"], flatten=cfg["flatten"], p=cfg["p"])
    o, h, l, c, v = D["o"], D["h"], D["l"], D["c"], D["v"]
    mod, day, blk = D["mod"], D["day"], D["blk"]
    n = D["n"]
    F = {}

    atr14 = V._atr(h, l, c, 14)
    rng = h - l
    body = np.abs(c - o)
    pc = np.concatenate(([c[0]], c[:-1]))
    ret1 = np.concatenate(([0.0], np.diff(np.log(np.maximum(c, 1e-9)))))

    # ---- vol.  against a CAUSAL time-of-day baseline
    atr_tod = tod_baseline(atr14, mod, day)
    F["vol.atr_tod"] = atr14 / np.maximum(atr_tod, 1e-9)
    F["vol.atr_pct250"] = pd.Series(atr14).rolling(250, min_periods=60).rank(pct=True).to_numpy()
    F["vol.rv24"] = _roll(ret1 ** 2, 24, "sum") ** 0.5
    F["vol.rv96"] = _roll(ret1 ** 2, 96, "sum") ** 0.5
    F["vol.rv_ratio"] = F["vol.rv24"] / np.maximum(F["vol.rv96"], 1e-12)
    F["vol.volofvol"] = _roll(F["vol.rv24"], 48, "std")
    F["vol.atr_slope"] = (atr14 - np.concatenate((np.full(24, np.nan), atr14[:-24]))) / np.maximum(atr14, 1e-9)

    # ---- trn.
    e200, e50, e20, _a = V.periods(D, cfg["p"])
    F["trn.d_slow_atr"] = (c - e200) / np.maximum(atr14, 1e-9)
    F["trn.d_pull_atr"] = (c - e50) / np.maximum(atr14, 1e-9)
    F["trn.slope_slow"] = (e200 - np.concatenate((np.full(48, np.nan), e200[:-48]))) / np.maximum(atr14, 1e-9)
    F["trn.slope_pull"] = (e50 - np.concatenate((np.full(24, np.nan), e50[:-24]))) / np.maximum(atr14, 1e-9)
    F["trn.er20"] = eff_ratio(c, 20)
    F["trn.er96"] = eff_ratio(c, 96)
    F["trn.ret16"] = (c - np.concatenate((np.full(16, np.nan), c[:-16]))) / np.maximum(atr14, 1e-9)
    F["trn.ret96"] = (c - np.concatenate((np.full(96, np.nan), c[:-96]))) / np.maximum(atr14, 1e-9)
    F["trn.above_slow"] = (c > e200).astype(float)

    # ---- reg.
    F["reg.chop14"] = chop(h, l, c, 14)
    F["reg.chop48"] = chop(h, l, c, 48)
    ax, pdi, ndi = adx(h, l, c, 14)
    F["reg.adx14"] = ax
    F["reg.di_spread"] = pdi - ndi
    hm = HMM(k=hmm_k, seed=seed).fit(ret1[blk == 0])
    post = hm.filtered(ret1)
    order = np.argsort(hm.means())
    for j, s in enumerate(("bear", "side", "bull")[:hmm_k]):
        F[f"reg.hmm_{s}"] = post[:, order[j]]
    F["reg.hmm_drift"] = post @ hm.means()

    # ---- vlm.  same causal baseline as vol.
    v_tod = tod_baseline(v, mod, day)
    F["vlm.tod_ratio"] = v / np.maximum(v_tod, 1e-9)
    F["vlm.z96"] = (v - _roll(v, 96, "mean")) / np.maximum(_roll(v, 96, "std"), 1e-9)
    F["vlm.trend24"] = _roll(v, 24, "mean") / np.maximum(_roll(v, 96, "mean"), 1e-9)
    F["vlm.per_range"] = v / np.maximum(rng / np.maximum(atr14, 1e-9), 1e-9)

    # ---- str.
    F["str.body_share"] = body / np.maximum(rng, 1e-9)
    F["str.close_pos"] = (c - l) / np.maximum(rng, 1e-9)
    F["str.upper_wick"] = (h - np.maximum(o, c)) / np.maximum(rng, 1e-9)
    F["str.rng_atr"] = rng / np.maximum(atr14, 1e-9)
    F["str.gap_atr"] = (o - pc) / np.maximum(atr14, 1e-9)
    F["str.dir_run"] = _roll(np.sign(ret1), 8, "sum")

    # ---- clk.
    rth = D["rth"]
    sess_start = pd.Series(np.where(rth, mod, np.nan)).groupby(pd.Series(day)).transform("min").to_numpy()
    sess_stop = pd.Series(np.where(rth, mod, np.nan)).groupby(pd.Series(day)).transform("max").to_numpy()
    F["clk.since_open"] = mod - sess_start
    F["clk.to_close"] = sess_stop - mod

    # ---- ffd.  d chosen on RESEARCH only
    d = pick_d(c, blk)
    s = ffd(c, d)
    F["ffd.level"] = (s - _roll(s, 96, "mean")) / np.maximum(_roll(s, 96, "std"), 1e-9)
    F["ffd.slope"] = s - np.concatenate((np.full(24, np.nan), s[:-24]))

    # ---- anm.  every model fitted on the RESEARCH block only
    bar = np.column_stack([
        ret1,
        (c - np.concatenate((np.full(4, np.nan), c[:-4]))) / np.maximum(atr14, 1e-9),
        (c - np.concatenate((np.full(16, np.nan), c[:-16]))) / np.maximum(atr14, 1e-9),
        rng / np.maximum(atr14, 1e-9),
        body / np.maximum(rng, 1e-9),
        (c - l) / np.maximum(rng, 1e-9),
        F["vlm.tod_ratio"],
        F["vol.atr_tod"]])
    ok = np.isfinite(bar).all(1)
    fitm = ok & (blk == 0)
    ae = AutoEncoder(seed=seed).fit(bar[fitm])
    err = np.full(n, np.nan)
    err[ok] = ae.error(bar[ok])
    F["anm.ae_err"] = err
    F["anm.ae_pct"] = pd.Series(err).rolling(2000, min_periods=250).rank(pct=True).to_numpy()
    mh = np.full(n, np.nan)
    mh[ok] = mahalanobis(bar[ok], (blk == 0)[ok])
    F["anm.mahal"] = mh
    from sklearn.ensemble import IsolationForest
    iso = IsolationForest(n_estimators=200, random_state=seed, contamination="auto").fit(bar[fitm])
    sc = np.full(n, np.nan)
    sc[ok] = -iso.score_samples(bar[ok])          # higher = more anomalous
    F["anm.iso"] = sc
    # a joint outlier in (return, range, volume) -- the STUDY_V32 definition, kept for comparison
    zr = (ret1 - _roll(ret1, 250, "mean")) / np.maximum(_roll(ret1, 250, "std"), 1e-9)
    zg = (rng - _roll(rng, 250, "mean")) / np.maximum(_roll(rng, 250, "std"), 1e-9)
    zv = (v - _roll(v, 250, "mean")) / np.maximum(_roll(v, 250, "std"), 1e-9)
    F["anm.joint_z"] = np.sqrt(np.nan_to_num(zr) ** 2 + np.nan_to_num(zg) ** 2 + np.nan_to_num(zv) ** 2)
    F["anm.resid_move"] = np.nan_to_num(zr) - np.nan_to_num(zv)   # move not explained by participation

    X = pd.DataFrame(F, index=pd.DatetimeIndex(D["ix"]))

    # ---- hst.  how the last k instances of THIS event resolved (shifted, so no self-reference)
    ev = t.copy()
    ev["date"] = pd.DatetimeIndex(ev.ts).normalize()
    for k in (3, 10, 25):
        ev[f"hst.prev{k}_R"] = ev.R.shift(1).rolling(k, min_periods=2).mean()
        ev[f"hst.prev{k}_win"] = (ev.R.shift(1) > 0).rolling(k, min_periods=2).mean()
    ev["hst.gap_bars"] = ev.sig.diff()

    feat = X.iloc[ev.sig.to_numpy()].reset_index(drop=True)
    for cname in [q for q in ev.columns if q.startswith("hst.")]:
        feat[cname] = ev[cname].to_numpy()
    meta = ev[["sig", "exit_bar", "R", "pct", "blk", "ts", "date", "risk", "why"]].reset_index(drop=True)
    return D, meta, feat, dict(ffd_d=d, hmm_mu=hm.means().tolist(), hmm_diag=np.diag(hm.A).tolist())


def truncation_audit(market, cfg, probes=12, seed=0):
    """Recompute every feature on history that ENDS at the event bar and require a match.

    The only honest leakage test on this branch: it has caught an overnight aggregate reading its
    own group's last close, a divergence feature filled forward to a FUTURE pivot's confirmation
    bar, and a session freeze in wall-clock minutes handing evening bars next-morning levels.
    """
    D, meta, feat, _ = build(market, cfg, seed=seed)
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(meta), size=min(probes, len(meta)), replace=False)
    bad = []
    raw = M.raw(market)
    for j in idx:
        i = int(meta.sig.iloc[j])
        cut = raw.iloc[:i + 1]
        Dt = V.assemble(cut, sess=cfg["sess"])
        if Dt["n"] < 600:
            continue
        # rebuild only the cheap, purely-causal columns; the fitted models are excluded because
        # refitting them on a truncated block changes the MODEL, not the causality
        c2, h2, l2 = Dt["c"], Dt["h"], Dt["l"]
        a2 = V._atr(h2, l2, c2, 14)
        for nm, val in (("reg.chop14", chop(h2, l2, c2, 14)[-1]),
                        ("reg.adx14", adx(h2, l2, c2, 14)[0][-1]),
                        ("trn.er20", eff_ratio(c2, 20)[-1]),
                        ("str.rng_atr", ((h2 - l2) / np.maximum(a2, 1e-9))[-1])):
            full = float(feat[nm].iloc[j])
            if np.isfinite(full) and np.isfinite(val) and abs(full - val) > 1e-6 * max(1.0, abs(full)):
                bad.append((nm, j, full, val))
    return bad, len(idx) * 4
