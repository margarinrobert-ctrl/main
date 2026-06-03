"""Calvet-Fisher binomial Markov-Switching Multifractal (MSM) volatility model.

Reference: Calvet & Fisher (2004), "How to Forecast Long-Run Volatility:
Regime Switching and the Estimation of Multifractal Processes", J. Financial
Econometrics 2(1). Handoff Section 7.2.

Model
-----
k volatility components M_{1,t} ... M_{k,t}, each a 2-state Markov switch taking
value m0 or (2 - m0) with E[M] = 1. Component i redraws (50/50) with probability

    gamma_k = 1 - (1 - gamma_1) ** (b ** (k - 1))

Returns:  r_t = sigma * sqrt( prod_i M_{i,t} ) * eps_t,  eps ~ N(0,1).

Estimation is exact maximum likelihood via the Hamilton filter over the 2**k
latent states (feasible for k up to ~8-10). Parameters: m0 in (1,2), sigma > 0,
b > 1, gamma_1 in (0,1).

This forecasts VOLATILITY, not direction. Heavily caveated (Section 5).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

_LOG_2PI = np.log(2.0 * np.pi)


def _component_values(k: int, m0: float) -> np.ndarray:
    """For each of the 2**k states, the product of component multipliers.

    State j's bit i (0=low=m0, 1=high=2-m0) selects component i's value.
    """
    hi = 2.0 - m0
    M = 1 << k
    g = np.ones(M)
    for j in range(M):
        prod = 1.0
        for i in range(k):
            prod *= hi if (j >> i) & 1 else m0
        g[j] = prod
    return g


def _transition_matrix(k: int, b: float, gamma1: float) -> np.ndarray:
    """Full 2**k x 2**k transition matrix as Kronecker product of per-component
    2x2 matrices. Component i switches w.p. gamma_i; on a switch it redraws
    50/50, so P(stay value) = 1 - gamma_i/2."""
    mats = []
    for i in range(k):
        g_i = 1.0 - (1.0 - gamma1) ** (b ** i)
        g_i = min(max(g_i, 1e-12), 1.0)
        s = 1.0 - g_i / 2.0   # stay same value
        f = g_i / 2.0         # flip
        mats.append(np.array([[s, f], [f, s]]))
    T = mats[0]
    for i in range(1, k):
        T = np.kron(T, mats[i])
    return T


def _filter_loglik(params, r, k):
    """Negative log-likelihood via the Hamilton filter. ``params`` are the
    unconstrained reals; mapped to (m0, sigma, b, gamma1)."""
    m0, sigma, b, gamma1 = _unpack(params)
    if not (1.0 < m0 < 2.0 and sigma > 0 and b > 1.0 and 0.0 < gamma1 < 1.0):
        return 1e10
    M = 1 << k
    g = _component_values(k, m0)
    var = (sigma ** 2) * g                      # conditional variance per state
    T = _transition_matrix(k, b, gamma1)

    pi = np.full(M, 1.0 / M)                    # stationary = uniform
    ll = 0.0
    r2 = r * r
    for t in range(r.size):
        pred = pi @ T
        # gaussian densities for each state
        dens = np.exp(-0.5 * (r2[t] / var) - 0.5 * np.log(var) - 0.5 * _LOG_2PI)
        w = pred * dens
        s = w.sum()
        if s <= 0 or not np.isfinite(s):
            return 1e10
        ll += np.log(s)
        pi = w / s
    return -ll


def _pack(m0, sigma, b, gamma1):
    """Constrained -> unconstrained reals for the optimizer."""
    return np.array([
        np.log((m0 - 1.0) / (2.0 - m0)),   # logit on (1,2)
        np.log(sigma),
        np.log(b - 1.0),                   # b > 1
        np.log(gamma1 / (1.0 - gamma1)),   # logit on (0,1)
    ])


def _unpack(p):
    m0 = 1.0 + 1.0 / (1.0 + np.exp(-p[0]))         # (1,2)
    sigma = np.exp(p[1])
    b = 1.0 + np.exp(p[2])                          # >1
    gamma1 = 1.0 / (1.0 + np.exp(-p[3]))            # (0,1)
    return m0, sigma, b, gamma1


@dataclass
class MSMFit:
    k: int
    m0: float
    sigma: float
    b: float
    gamma1: float
    loglik: float
    n: int
    scale: float          # returns were multiplied by this before fitting
    _pi: np.ndarray       # final filtered state distribution
    _g: np.ndarray        # per-state multiplier product

    @property
    def n_params(self) -> int:
        return 4

    @property
    def aic(self) -> float:
        return 2 * self.n_params - 2 * self.loglik

    @property
    def bic(self) -> float:
        return self.n_params * np.log(self.n) - 2 * self.loglik

    def summary(self) -> str:
        return (f"MSM(k={self.k}): m0={self.m0:.4f} sigma={self.sigma:.5f} "
                f"b={self.b:.3f} gamma1={self.gamma1:.4f} | "
                f"LL={self.loglik:.1f} AIC={self.aic:.1f} BIC={self.bic:.1f}")


def fit(returns, k: int = 4, scale: float = 100.0, restarts: int = 4,
        seed: int = 0) -> MSMFit:
    """Maximum-likelihood fit of the binomial MSM.

    Returns are multiplied by ``scale`` (default 100 -> percent) purely for
    numerical conditioning; ``sigma`` and forecasts are returned on the
    original return scale.
    """
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    r = (r - r.mean()) * scale

    rng = np.random.default_rng(seed)
    best = None
    inits = [(1.4, r.std() or 1.0, 3.0, 0.5)]
    for _ in range(max(0, restarts - 1)):
        inits.append((1.2 + 0.6 * rng.random(),
                      (r.std() or 1.0) * (0.5 + rng.random()),
                      1.5 + 4.0 * rng.random(),
                      0.05 + 0.9 * rng.random()))

    for init in inits:
        x0 = _pack(*init)
        try:
            res = minimize(_filter_loglik, x0, args=(r, k),
                           method="Nelder-Mead",
                           options={"maxiter": 4000, "xatol": 1e-6,
                                    "fatol": 1e-6})
        except Exception:
            continue
        if best is None or res.fun < best.fun:
            best = res

    if best is None:
        raise RuntimeError("MSM optimization failed")

    m0, sigma, b, gamma1 = _unpack(best.x)

    # recover final filtered distribution for forecasting
    M = 1 << k
    g = _component_values(k, m0)
    var = (sigma ** 2) * g
    T = _transition_matrix(k, b, gamma1)
    pi = np.full(M, 1.0 / M)
    r2 = r * r
    for t in range(r.size):
        pred = pi @ T
        dens = np.exp(-0.5 * (r2[t] / var) - 0.5 * np.log(var) - 0.5 * _LOG_2PI)
        w = pred * dens
        pi = w / w.sum()

    return MSMFit(k=k, m0=float(m0), sigma=float(sigma) / scale,
                  b=float(b), gamma1=float(gamma1),
                  loglik=float(-best.fun), n=int(r.size), scale=scale,
                  _pi=pi, _g=g)


def forecast_vol(fit_obj: MSMFit, horizons=(1, 5, 10, 22, 44),
                 annualize: bool = True) -> dict:
    """Forecast volatility at the given horizons (trading days).

    For horizon H, returns annualized vol = sqrt(252 * mean daily variance)
    where the daily variance forecast i steps ahead is sigma^2 * E[g_{t+i}],
    E[g] taken under the i-step-ahead state distribution.
    """
    T = _transition_matrix(fit_obj.k, fit_obj.b, fit_obj.gamma1)
    sigma2 = fit_obj.sigma ** 2
    g = fit_obj._g
    out = {}
    for H in horizons:
        pi = fit_obj._pi.copy()
        cumvar = 0.0
        for _ in range(H):
            pi = pi @ T
            cumvar += sigma2 * float(pi @ g)
        daily_var = cumvar / H
        v = np.sqrt(daily_var)
        out[H] = np.sqrt(252) * v if annualize else v
    return out


def conditional_vol_path(fit_obj: MSMFit, returns, annualize: bool = True):
    """In-sample 1-step-ahead conditional volatility path (for plotting /
    RMSE vs realized). Re-runs the filter and reports E[sigma_t] each step."""
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    rs = (r - r.mean()) * fit_obj.scale
    M = 1 << fit_obj.k
    g = _component_values(fit_obj.k, fit_obj.m0)
    var = ((fit_obj.sigma * fit_obj.scale) ** 2) * g
    T = _transition_matrix(fit_obj.k, fit_obj.b, fit_obj.gamma1)
    pi = np.full(M, 1.0 / M)
    r2 = rs * rs
    path = np.empty(rs.size)
    for t in range(rs.size):
        pred = pi @ T
        # forecast variance for step t (before seeing r_t)
        fvar = float(pred @ var) / (fit_obj.scale ** 2)
        path[t] = np.sqrt(fvar)
        dens = np.exp(-0.5 * (r2[t] / var) - 0.5 * np.log(var) - 0.5 * _LOG_2PI)
        w = pred * dens
        pi = w / w.sum()
    if annualize:
        path = path * np.sqrt(252)
    return path


def garch_benchmark(returns, scale: float = 100.0):
    """GARCH(1,1) baseline via the `arch` package, if available.

    Returns (conditional_vol_annualized, loglik) or (None, None) if `arch`
    isn't installed. Used to benchmark MSM (Section 7.2 / 8).
    """
    try:
        from arch import arch_model
    except Exception:
        return None, None
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)] * scale
    am = arch_model(r, mean="Zero", vol="GARCH", p=1, q=1, dist="normal")
    res = am.fit(disp="off")
    cond = res.conditional_volatility / scale * np.sqrt(252)
    return np.asarray(cond), float(res.loglikelihood)
