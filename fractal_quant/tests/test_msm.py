"""Tests for the MSM volatility model (Section 7.2)."""
import numpy as np

from fractal_quant import msm


def _simulate_msm(n=3000, k=3, m0=1.4, sigma=0.01, b=3.0, gamma1=0.5, seed=0):
    """Simulate from the binomial MSM to check the estimator recovers params."""
    rng = np.random.default_rng(seed)
    hi = 2.0 - m0
    comps = rng.choice([m0, hi], size=k)
    gammas = [1.0 - (1.0 - gamma1) ** (b ** i) for i in range(k)]
    r = np.empty(n)
    for t in range(n):
        for i in range(k):
            if rng.random() < gammas[i]:
                comps[i] = rng.choice([m0, hi])
        vol = sigma * np.sqrt(np.prod(comps))
        r[t] = vol * rng.normal()
    return r


def test_msm_fit_runs_and_is_finite():
    r = _simulate_msm(n=1500, k=3, seed=1)
    fit = msm.fit(r, k=3, restarts=2)
    assert np.isfinite(fit.loglik)
    assert 1.0 < fit.m0 < 2.0
    assert fit.sigma > 0
    assert fit.b > 1.0
    assert 0.0 < fit.gamma1 < 1.0


def test_msm_recovers_sigma_scale():
    """The fitted sigma should be the right order of magnitude as the true
    unconditional daily vol (E[g]=1, so unconditional std == sigma)."""
    true_sigma = 0.012
    r = _simulate_msm(n=3000, k=3, sigma=true_sigma, seed=2)
    fit = msm.fit(r, k=3, restarts=3)
    assert 0.5 * true_sigma < fit.sigma < 2.0 * true_sigma


def test_forecast_converges_to_unconditional():
    """Long-horizon vol forecast should approach sigma*sqrt(252) (E[g]->1)."""
    r = _simulate_msm(n=2000, k=3, sigma=0.01, seed=3)
    fit = msm.fit(r, k=3, restarts=2)
    fc = msm.forecast_vol(fit, horizons=(1, 250), annualize=True)
    longrun = fit.sigma * np.sqrt(252)
    assert abs(fc[250] - longrun) < 0.5 * longrun


def test_conditional_path_length():
    r = _simulate_msm(n=800, k=2, seed=4)
    fit = msm.fit(r, k=2, restarts=1)
    path = msm.conditional_vol_path(fit, r)
    assert path.shape[0] == r.size
    assert np.all(path > 0)
