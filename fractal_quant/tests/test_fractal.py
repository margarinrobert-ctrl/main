"""Sanity tests for the fractal estimators (acceptance criteria, Section 8)."""
import numpy as np

from fractal_quant.fractal import frama, hurst_dfa, hurst_rs


def _random_walk_logr(n=2000, seed=0, sigma=0.01):
    rng = np.random.default_rng(seed)
    return rng.normal(0.0, sigma, n)


def test_random_walk_hurst_rs_near_half():
    """Acceptance: random walk -> H in [0.45, 0.55] (averaged over seeds)."""
    hs = [hurst_rs(_random_walk_logr(2000, seed=s)) for s in range(8)]
    mean_h = np.mean(hs)
    assert 0.45 <= mean_h <= 0.55, f"R/S Hurst {mean_h:.3f} off random walk"


def test_random_walk_hurst_dfa_near_half():
    hs = [hurst_dfa(_random_walk_logr(2000, seed=s)) for s in range(8)]
    mean_h = np.mean(hs)
    assert 0.45 <= mean_h <= 0.55, f"DFA Hurst {mean_h:.3f} off random walk"


def test_trending_series_high_hurst():
    """A strong drift / trending series should read H > 0.5."""
    rng = np.random.default_rng(1)
    # persistent: AR(1) with positive coefficient on increments
    x = np.zeros(2000)
    for i in range(1, 2000):
        x[i] = 0.6 * x[i - 1] + rng.normal(0, 0.01)
    assert hurst_rs(x) > 0.5


def test_mean_reverting_series_low_hurst():
    """An anti-persistent (alternating) series should read H < 0.5."""
    rng = np.random.default_rng(2)
    x = np.zeros(2000)
    for i in range(1, 2000):
        x[i] = -0.5 * x[i - 1] + rng.normal(0, 0.01)
    assert hurst_rs(x) < 0.5


def test_hurst_too_short_returns_nan():
    assert np.isnan(hurst_rs(np.arange(10.0)))


def test_frama_tracks_price_and_is_finite():
    close = np.cumsum(np.ones(200)) + 100.0  # smooth uptrend
    fr = frama(close, close, close, 16)
    assert np.all(np.isfinite(fr))
    # in a steady trend FRAMA should track closely near the end
    assert abs(fr[-1] - close[-1]) < 5.0


def test_frama_odd_period_made_even():
    close = np.linspace(100, 110, 100)
    fr = frama(close, close, close, 15)  # odd -> 16
    assert fr.shape == close.shape
