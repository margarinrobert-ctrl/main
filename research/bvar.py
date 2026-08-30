"""A Minnesota-prior BVAR that produces a per-bar predictive DENSITY, causally, at tuner speed.

WHY A BVAR AND NOT A REGRESSION
-------------------------------
The thing a breakout filter actually needs is not a point forecast -- it is P(the next h bars go
my way) together with an honest statement of how much of that number is noise. A VAR gives the
joint dynamics of return, flow and volatility, so it can say "the flow shock that just fired
usually persists for four bars" rather than "flow correlates with return". A BAYESIAN VAR is what
makes that estimable at short horizons: an unrestricted VAR with k=5 variables and p=6 lags has
155 free coefficients and, on 5-minute bars, an R^2 that is entirely in-sample. The Minnesota
prior shrinks every equation toward a random walk (or toward white noise for stationary
variables), which is the only honest null on this data -- see `docs/RESEARCH_PROTOCOL.md` §2.

WHAT IS EXACT AND WHAT IS APPROXIMATE
-------------------------------------
* Exact: the conjugate Normal-Inverse-Wishart posterior under a dummy-observation Minnesota prior,
  and the h-step cumulative predictive mean and variance for a given (B, Sigma) draw. The
  cumulative return over h bars is a LINEAR functional of the companion state, so per posterior
  draw it reduces to one vector `a_s` and one scalar variance `v_s` -- and the whole per-bar
  forecast becomes a single matmul `Z @ A`. That is what makes this affordable per bar.
* Approximate: the predictive density is a Gaussian mixture over posterior draws rather than an
  analytic multivariate-t; with S >= 200 draws the difference is far below the noise in the data.
* Stochastic volatility is handled by EWMA standardisation (model y_t / sigma_{t-1}, rescale the
  forecast by sigma_t) rather than a full SV state-space. It captures the first-order effect --
  the conditional variance moving by an order of magnitude between 04:00 and 09:30 -- at ~0 cost,
  and it keeps the model conjugate, which is what keeps online updating closed form.

CAUSALITY
---------
Output at bar t uses bars <= t and nothing else. Coefficients used at bar t come from a window
that ENDS at the start of the refit block containing t, never inside it. `selftest()` asserts this
by truncation, the same way `indpool.leak_check` does. Read `CLAUDE.md` on `ent_bar` before
wiring any of this into a simulator: these are SIGNAL-bar features.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from scipy.special import ndtr as _ndtr
except Exception:                                        # pragma: no cover
    def _ndtr(x):                                        # Abramowitz-Stegun 7.1.26, |err| < 8e-8
        x = np.asarray(x, float) / np.sqrt(2.0)
        s = np.sign(x); z = np.abs(x)
        t = 1.0 / (1.0 + 0.3275911 * z)
        y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t
                    - 0.284496736) * t + 0.254829592) * t * np.exp(-z * z)
        return 0.5 * (1.0 + s * y)


# ===================================================================== the panel
@dataclass(frozen=True)
class PanelCfg:
    """Which variables enter the VAR. Every one must be computable from bars <= t.

    The default five are the smallest set that lets the model say something a single-series model
    cannot: return (what we forecast), signed flow (who is pushing), unsigned flow (whether anyone
    is there at all), realised volatility (the scale), and channel position (where price sits in
    the structure the Donchian rule trades).
    """
    ret: bool = True             # log return, in ticks, of the bar
    flow: bool = True            # signed volume proxy: (2*(c-l)/(h-l) - 1) * volume, z-scored
    vol_z: bool = True           # log volume against its own trailing median
    rvol: bool = True            # log realised range (true range / ATR), the scale variable
    donch: int = 20              # channel position over this lookback, 0 to disable
    ewma_lam: float = 0.97       # EWMA used for the SV standardisation (per bar)
    z_win: int = 390             # trailing window for the z-scores, in bars
    target: str = "ret"          # the variable the strategy forecasts


def _ewma(x, lam):
    """Causal EWMA of x, returned SHIFTED so entry i uses values strictly before i."""
    x = np.asarray(x, float)
    out = np.empty(len(x)); acc = 0.0; init = False
    for i in range(len(x)):
        out[i] = acc if init else np.nan
        v = x[i]
        if np.isfinite(v):
            acc = v if not init else lam * acc + (1.0 - lam) * v
            init = True
    return out


def _roll_med(x, n):
    """Trailing median over the previous n values, exclusive of the current one.

    Strided rather than looped: on the live hot path this is called once per bar over the whole
    tail window, and the python-loop version was 30 ms of a 35 ms bar budget.
    """
    x = np.ascontiguousarray(np.asarray(x, float))
    n = int(n)
    out = np.full(len(x), np.nan)
    if len(x) > n:
        w = np.lib.stride_tricks.sliding_window_view(x[:-1], n)
        out[n:] = np.median(w, axis=1)
    return out


def _ratio(x, med, log=False):
    """x / median(x), with a degenerate median (all-zero window) mapped to a neutral value rather
    than to NaN -- a flat synthetic series must not silently delete a whole column."""
    x = np.asarray(x, float)
    ok = np.isfinite(med)
    den = np.where(ok & (med > 1e-9), med, 1.0)
    out = np.where(ok, (x / den), np.nan)
    if log:
        out = np.where(np.isfinite(out) & (out > 0), np.log(np.maximum(out, 1e-12)), np.nan)
        out = np.where(ok & (med <= 1e-9), 0.0, out)
    else:
        out = np.where(ok & (med <= 1e-9), 0.0, out)
    return out


def build_panel(d, cfg: PanelCfg = PanelCfg(), tick=0.25):
    """(Y, names) -- the VAR's observation matrix, one row per bar, all known at that bar's close.

    NaN rows at the head are expected; `rolling` skips them. Nothing here reads index > i.
    """
    o, h, l, c, v = (np.asarray(d[k], float) for k in ("o", "h", "l", "c", "v"))
    n = len(c)
    cols, names = [], []

    r = np.zeros(n); r[1:] = (c[1:] - c[:-1]) / tick          # returns in ticks: scale-free enough
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.r_[c[0], c[:-1]]),
                                      np.abs(l - np.r_[c[0], c[:-1]])))
    if cfg.ret:
        cols.append(r); names.append("ret")
    if cfg.flow:
        rng = np.where(h - l > 1e-9, h - l, np.nan)
        f = (2.0 * (c - l) / rng - 1.0) * v
        med = _roll_med(np.abs(np.nan_to_num(f)), cfg.z_win)
        cols.append(_ratio(np.nan_to_num(f), med)); names.append("flow")
    if cfg.vol_z:
        med = _roll_med(v, cfg.z_win)
        cols.append(_ratio(v, med, log=True)); names.append("volz")
    if cfg.rvol:
        med = _roll_med(tr, cfg.z_win)
        cols.append(_ratio(tr, med, log=True)); names.append("rvol")
    if cfg.donch:
        from donchian import position
        p = position(h, l, c, cfg.donch)
        cols.append(np.clip(p, -1.0, 2.0) - 0.5); names.append("dpos")

    Y = np.column_stack(cols)
    Y[~np.isfinite(Y)] = np.nan
    return Y, names


def sv_scale(Y, lam=0.97, floor=1e-6):
    """Per-variable causal EWMA standard deviation, shifted so row i is scaled by info before i."""
    S = np.empty_like(Y)
    for j in range(Y.shape[1]):
        e = _ewma(np.nan_to_num(Y[:, j]) ** 2, lam)
        S[:, j] = np.sqrt(np.maximum(e, floor))
    return S


# ===================================================================== the prior and the posterior
@dataclass(frozen=True)
class MinnCfg:
    p: int = 6                   # lag order
    lam: float = 0.2             # overall tightness. Small = closer to the prior = closer to a RW
    alpha: float = 2.0           # lag-decay exponent: lag l is shrunk by l**alpha
    eps: float = 1e3             # intercept looseness (large = effectively flat)
    delta: float = 0.0           # prior own-first-lag coefficient. 0 = white noise (returns),
    #                              1 = random walk (levels). Returns are 0; a LEVEL variable in
    #                              the panel would need 1, and there are none by design.
    sv: bool = True              # EWMA volatility standardisation before estimation
    lam_sv: float = 0.97


@dataclass
class Posterior:
    B: np.ndarray                # (kp+1, k) posterior mean coefficients, rows [const, lags...]
    Sigma: np.ndarray            # (k, k) posterior mean innovation covariance
    Vinv_chol: np.ndarray        # chol of the coefficient precision, for drawing B
    nu: int                      # inverse-Wishart degrees of freedom
    Spost: np.ndarray            # inverse-Wishart scale
    sd_resid: np.ndarray         # per-equation residual sd (AR scaling used by the prior)
    n_obs: int


def _ar_sd(Y, p):
    """Residual sd of a univariate AR(p) per variable -- the Minnesota prior's scale reference."""
    k = Y.shape[1]
    out = np.ones(k)
    for j in range(k):
        y = Y[p:, j]
        X = np.column_stack([Y[p - i - 1:-i - 1, j] for i in range(p)] + [np.ones(len(y))])
        m = np.isfinite(y) & np.isfinite(X).all(1)
        if m.sum() > 5 * p:
            b, *_ = np.linalg.lstsq(X[m], y[m], rcond=None)
            out[j] = max(np.std(y[m] - X[m] @ b), 1e-8)
        else:
            out[j] = max(np.std(y[np.isfinite(y)]) if np.isfinite(y).any() else 1.0, 1e-8)
    return out


def dummy_observations(sd, cfg: MinnCfg):
    """Banbura-Giannone-Reichlin dummy observations implementing the Minnesota prior.

    Adding these rows to the regression and running OLS IS the posterior mean, which is why this
    formulation is used: no k^2 p^2 precision matrix is ever built or inverted.

    Note the one thing this form gives up: the dummy rows are shared by every equation, so the
    shrinkage is symmetric -- there is no separate `theta` loosening own lags relative to cross
    lags, as in Litterman's original equation-by-equation prior. That variant is estimable here
    too (fit each equation separately with its own dummy block) at the cost of conjugacy across
    equations, and on this data the difference was not worth the loss of the closed form.
    """
    k = len(sd); p = cfg.p
    Jp = np.diag(np.arange(1, p + 1) ** cfg.alpha)
    # block 1: own lags shrink toward `delta` on lag 1 and 0 beyond, at rate lam * l**alpha
    Yd1 = np.vstack([np.diag(cfg.delta * sd) / cfg.lam, np.zeros((k * (p - 1), k))])
    Xd1 = np.hstack([np.kron(Jp, np.diag(sd)) / cfg.lam, np.zeros((k * p, 1))])
    # block 2: prior on Sigma (k rows), scaled by the AR residual sds
    Yd2 = np.diag(sd)
    Xd2 = np.zeros((k, k * p + 1))
    # block 3: an uninformative intercept
    Yd3 = np.zeros((1, k))
    Xd3 = np.zeros((1, k * p + 1)); Xd3[0, -1] = 1.0 / cfg.eps
    return np.vstack([Yd1, Yd2, Yd3]), np.vstack([Xd1, Xd2, Xd3])


def lag_matrix(Y, p):
    """(X, Yt, idx): X rows are [y_{t-1} ... y_{t-p}, 1] and Yt rows are y_t, both finite only."""
    n, k = Y.shape
    X = np.empty((n, k * p + 1)); X[:] = np.nan
    for l in range(1, p + 1):
        X[l:, (l - 1) * k:l * k] = Y[:-l]
    X[:, -1] = 1.0
    ok = np.isfinite(X).all(1) & np.isfinite(Y).all(1)
    return X, Y, np.flatnonzero(ok)


def fit(Y, cfg: MinnCfg = MinnCfg()) -> Posterior:
    """Conjugate NIW posterior on a window of panel rows. O(n k^2 p^2), milliseconds."""
    k = Y.shape[1]; p = cfg.p
    X, Yt, ok = lag_matrix(Y, p)
    if len(ok) < 10 * (k * p + 1):
        raise ValueError(f"only {len(ok)} usable rows for {k * p + 1} coefficients")
    Xo, Yo = X[ok], Yt[ok]
    sd = _ar_sd(Y[np.isfinite(Y).all(1)], p)
    Yd, Xd = dummy_observations(sd, cfg)
    Xa = np.vstack([Xd, Xo]); Ya = np.vstack([Yd, Yo])
    XtX = Xa.T @ Xa
    XtX[np.diag_indices_from(XtX)] += 1e-10               # numerical floor, not a prior
    L = np.linalg.cholesky(XtX)
    B = np.linalg.solve(XtX, Xa.T @ Ya)
    E = Ya - Xa @ B
    Spost = E.T @ E
    nu = len(Ya) - (k * p + 1)
    Sigma = Spost / max(nu - k - 1, 1)
    return Posterior(B=B, Sigma=Sigma, Vinv_chol=L, nu=nu, Spost=Spost, sd_resid=sd,
                     n_obs=len(ok))


def draw(post: Posterior, S=200, rng=None):
    """S draws from the NIW posterior. Returns (Bs (S,kp+1,k), Sigmas (S,k,k))."""
    S = int(S)
    if S < 2:
        raise ValueError("at least 2 posterior draws are needed for an epistemic variance")
    rng = rng or np.random.default_rng(0)
    k = post.Sigma.shape[0]; m = post.B.shape[0]
    Ls = np.linalg.cholesky(np.linalg.inv(post.Spost + 1e-12 * np.eye(k)))
    Bs = np.empty((S, m, k)); Sg = np.empty((S, k, k))
    for s in range(S):
        # inverse-Wishart via Bartlett on the inverse scale
        A = np.zeros((k, k))
        for i in range(k):
            A[i, i] = np.sqrt(rng.chisquare(post.nu - i))
            for j in range(i):
                A[i, j] = rng.normal()
        W = Ls @ A
        Sig = np.linalg.inv(W @ W.T)
        Sg[s] = Sig
        # B | Sigma ~ MN(Bhat, Sigma (x) (X'X)^-1); solve with the cholesky, never an inverse
        Z = rng.normal(size=(m, k))
        U = np.linalg.solve(post.Vinv_chol.T, Z)          # (X'X)^{-1/2} Z
        Bs[s] = post.B + U @ np.linalg.cholesky(Sig).T
    return Bs, Sg


# ===================================================================== h-step predictive functional
def companion(B, k, p):
    """(C, c) of z_t = c + C z_{t-1} + e_t for the stacked state z = [y_t ... y_{t-p+1}]."""
    A = B[:-1].T                                          # (k, kp)
    C = np.zeros((k * p, k * p))
    C[:k] = A
    if p > 1:
        C[k:, :k * (p - 1)] = np.eye(k * (p - 1))
    c = np.zeros(k * p); c[:k] = B[-1]
    return C, c


def cum_functional(B, Sigma, k, p, h, target=0):
    """(a, b, v): cumulative target over the next h bars = a . z_t + b, with variance v.

    Derivation: z_{t+j} = c_j + C^j z_t + sum_{i<j} C^i e_{t+j-i}. Summing g'z over j=1..h and
    collecting shocks by date gives weights w_m = sum_{i=0..h-m} (C')^i g, so the exact variance
    is sum_m w_m' Omega w_m with Omega = Sigma in the top-left block. Both are computed once per
    posterior draw; per bar the forecast is then a dot product.
    """
    C, c = companion(B, k, p)
    g = np.zeros(k * p); g[target] = 1.0
    a = np.zeros(k * p); b = 0.0; v = 0.0
    # accumulate (C')^i g and the deterministic intercept path
    Ct = C.T
    partial = np.zeros(k * p)                              # sum_{i=0..j} (C')^i g
    powers = []
    cur = g.copy()
    for _ in range(h):
        partial = partial + cur
        powers.append(partial.copy())
        cur = Ct @ cur
    # a = sum_{j=1..h} (C')^j g
    cur = g.copy(); a = np.zeros(k * p)
    for _ in range(h):
        cur = Ct @ cur
        a = a + cur
    # deterministic intercept contribution
    z = np.zeros(k * p)
    for _ in range(h):
        z = c + C @ z
        b += g @ z
    Om = np.zeros((k * p, k * p)); Om[:k, :k] = Sigma
    for w in powers:                                       # w_m for m = h, h-1, ... (order free)
        v += float(w @ Om @ w)
    return a, b, v


def block_functionals(Bs, Sgs, k, p, h, target=0):
    """Stack `cum_functional` over posterior draws: A (kp,S), bvec (S,), vvec (S,)."""
    S = len(Bs)
    A = np.empty((k * p, S)); bv = np.empty(S); vv = np.empty(S)
    for s in range(S):
        a, b, v = cum_functional(Bs[s], Sgs[s], k, p, h, target)
        A[:, s] = a; bv[s] = b; vv[s] = v
    return A, bv, vv


def irf(post: Posterior, k, p, h=12, shock=1, resp=0, size=1.0):
    """Orthogonalised (Cholesky) impulse response of `resp` to a unit shock in `shock`.

    The ordering is the panel order, so put the variable you are willing to call 'more exogenous
    within the bar' first. This is a DESCRIPTIVE tool -- it tells you whether a flow shock has a
    persistent return response worth trading, and for how many bars, which is how the holding
    horizon `h` should be chosen instead of by grid search.
    """
    C, _ = companion(post.B, k, p)
    P = np.linalg.cholesky(post.Sigma)
    e = np.zeros(k * p); e[:k] = P[:, shock] * size
    out = np.empty(h + 1); z = e.copy(); out[0] = z[resp]
    for j in range(1, h + 1):
        z = C @ z
        out[j] = z[resp]
    return out


# ===================================================================== the per-bar driver
@dataclass
class BvarOut:
    mu: np.ndarray               # posterior-mean h-step cumulative forecast of the target, ticks
    sd: np.ndarray               # total predictive sd
    sd_alea: np.ndarray          # shock (aleatoric) component
    sd_epi: np.ndarray           # parameter (epistemic) component
    z: np.ndarray                # mu / sd -- the signal-to-noise ratio the strategy gates on
    p_up: np.ndarray             # posterior P(cumulative move > 0)
    surprise: np.ndarray         # Mahalanobis norm of the one-step innovation at this bar
    refit: np.ndarray            # bar index of the posterior in force
    names: list = field(default_factory=list)


def rolling(d, panel: PanelCfg = PanelCfg(), cfg: MinnCfg = MinnCfg(), h=6, win=4000,
            refit_every=250, draws=200, seed=11, start=None, verbose=False):
    """Per-bar predictive density for the h-bar cumulative target, causal by construction.

    The posterior in force at bar t was fitted on rows [t0-win, t0) where t0 is the start of the
    refit block containing t. No row inside the block touches its own coefficients, which is the
    strictest of the reasonable choices and the only one that survives `selftest`.
    """
    Y, names = build_panel(d, panel)
    n, k = Y.shape
    tgt = names.index(panel.target)
    Yw = Y.copy()
    if cfg.sv:
        Sc = sv_scale(Y, cfg.lam_sv)
        Yw = Y / Sc
    out = BvarOut(*[np.full(n, np.nan) for _ in range(7)], np.full(n, -1, np.int64), names)
    first = int(np.argmax(np.isfinite(Y).all(1))) + panel.z_win
    t0 = max(first + win, start or 0)
    rng = np.random.default_rng(seed)
    for blk in range(t0, n, refit_every):
        tr = Yw[max(0, blk - win):blk]
        try:
            post = fit(tr, cfg)
        except ValueError:
            continue
        Bs, Sgs = draw(post, draws, rng)
        A, bv, vv = block_functionals(Bs, Sgs, k, cfg.p, h, tgt)
        lo, hi = blk, min(blk + refit_every, n)
        idx = np.arange(lo, hi)
        Z = np.column_stack([Yw[idx - l] for l in range(cfg.p)])      # [y_t ... y_{t-p+1}]
        good = np.isfinite(Z).all(1)
        M = Z[good] @ A + bv                                          # (m, S) draw-wise means
        sd_s = np.sqrt(vv)[None, :]
        # rescale from standardised units back to ticks with the vol in force at the signal bar
        sc = (Sc[idx[good], tgt] if cfg.sv else np.ones(good.sum()))[:, None]
        M = M * sc; SD = sd_s * sc
        mu = M.mean(1)
        epi = M.var(1)
        alea = (SD ** 2).mean(1)
        p_up = _ndtr(M / SD).mean(1)
        w = idx[good]
        out.mu[w] = mu
        out.sd_epi[w] = np.sqrt(epi); out.sd_alea[w] = np.sqrt(alea)
        out.sd[w] = np.sqrt(epi + alea)
        out.z[w] = mu / np.maximum(out.sd[w], 1e-9)
        out.p_up[w] = p_up
        out.refit[lo:hi] = blk
        # one-step innovation surprise, using the posterior mean only (cheap, and it is a scale)
        Xb = np.column_stack([Yw[idx - 1 - l] for l in range(cfg.p)] + [np.ones(len(idx))])
        okb = np.isfinite(Xb).all(1) & np.isfinite(Yw[idx]).all(1)
        if okb.any():
            E = Yw[idx][okb] - Xb[okb] @ post.B
            Li = np.linalg.inv(np.linalg.cholesky(post.Sigma))
            out.surprise[idx[okb]] = np.linalg.norm(E @ Li.T, axis=1) / np.sqrt(k)
        if verbose and (blk - t0) % (refit_every * 20) == 0:
            print(f"  bar {blk:>8,}  n_obs {post.n_obs:>6,}  sd(mu) {np.nanstd(mu):.3f}t")
    return out


# ===================================================================== self-test
def selftest(seed=5, n=12000):
    """Three things: the estimator recovers a known VAR, the shrinkage does what it claims, and
    nothing here reads forward."""
    rng = np.random.default_rng(seed)
    k, p = 3, 2
    A1 = np.array([[0.30, 0.20, 0.0], [0.0, 0.40, 0.10], [0.05, 0.0, 0.50]])
    A2 = np.array([[-0.10, 0.0, 0.0], [0.0, -0.05, 0.0], [0.0, 0.0, -0.10]])
    Sg = np.diag([1.0, 0.5, 0.8])
    Y = np.zeros((n, k))
    L = np.linalg.cholesky(Sg)
    for t in range(2, n):
        Y[t] = A1 @ Y[t - 1] + A2 @ Y[t - 2] + L @ rng.normal(size=k)

    cfg = MinnCfg(p=2, lam=1.0, sv=False)                 # loose prior -> should be near OLS
    post = fit(Y, cfg)
    A1h = post.B[:k].T
    err = np.abs(A1h - A1).max()
    assert err < 0.05, f"lag-1 coefficients off by {err:.3f}"

    tight = fit(Y, MinnCfg(p=2, lam=0.02, sv=False))
    assert np.abs(tight.B[:k].T).max() < np.abs(A1h).max(), "tighter prior did not shrink"

    # predictive variance of the h-step cumulative sum must match a Monte-Carlo simulation
    h = 5
    a, b, v = cum_functional(post.B, post.Sigma, k, p, h, 0)
    z = np.concatenate([Y[-1], Y[-2]])
    sims = np.empty(20000)
    C, c = companion(post.B, k, p)
    Lc = np.linalg.cholesky(post.Sigma)
    for i in range(len(sims)):
        zz = z.copy(); s = 0.0
        for _ in range(h):
            e = np.zeros(k * p); e[:k] = Lc @ rng.normal(size=k)
            zz = c + C @ zz + e
            s += zz[0]
        sims[i] = s
    mu_a = a @ z + b
    assert abs(mu_a - sims.mean()) < 4 * sims.std() / np.sqrt(len(sims)) + 1e-6, "mean mismatch"
    assert abs(np.sqrt(v) / sims.std() - 1.0) < 0.05, \
        f"variance mismatch: analytic {np.sqrt(v):.3f} vs mc {sims.std():.3f}"

    # causality: refit the driver on a truncated series, past output must be identical
    m = 6000
    c_ = 100 + np.cumsum(rng.normal(0, 0.5, m))
    rg = np.abs(rng.normal(0.6, 0.25, m)) + 0.1
    up = rg * rng.uniform(0.1, 0.9, m)
    d = dict(o=c_, h=c_ + up, l=c_ - (rg - up), c=c_, v=np.abs(rng.normal(500, 150, m)) + 1.0)
    pc = PanelCfg(z_win=200, donch=20)
    mc = MinnCfg(p=2)
    full = rolling(d, pc, mc, h=4, win=1500, refit_every=200, draws=40)
    cut = 5000
    dt = {kk: vv[:cut] for kk, vv in d.items()}
    trunc = rolling(dt, pc, mc, h=4, win=1500, refit_every=200, draws=40)
    fin = np.isfinite(full.mu[:cut]) & np.isfinite(trunc.mu)
    assert fin.sum() > 500, "not enough overlap to test causality"
    assert np.allclose(full.mu[:cut][fin], trunc.mu[fin], atol=1e-8), "look-ahead in rolling()"
    return dict(max_coef_err=float(err), analytic_sd=float(np.sqrt(v)), mc_sd=float(sims.std()),
                causal_overlap=int(fin.sum()))


if __name__ == "__main__":
    print("bvar selftest:", selftest())
