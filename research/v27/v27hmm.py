"""A Gaussian Hidden Markov model, and the leak that ships with almost every published one.

WHY THIS IS NOT THE SNIPPET THAT WAS PASSED IN. The code supplied defines states by THRESHOLDING a
rolling return -- bull if the 20-day sum is above +2%, bear below -2%, sideways otherwise -- and then
counts transitions between them. That is a VISIBLE-state Markov chain: the state is a deterministic
function of data you already have, so "estimating" it is just labelling. A HIDDEN Markov model does
something different and harder: the state is never observed, and both the state sequence AND the
parameters (means, variances, transition matrix) are inferred from the observations together.

THE TRAP THAT MATTERS, AND THIS BRANCH HAS BEEN BURNED BY IT BEFORE. The standard way to read an
HMM's state is the SMOOTHED posterior P(s_t | ALL observations) or the Viterbi path, and both are
TWO-SIDED: the state assigned to bar t depends on data from bars after t. `STUDY_HP_FILTER` recorded
what that does -- the same Hodrick-Prescott trend run full-sample turned a $7,480 LOSS into a
$519,532 profit at Sharpe 12.96, and the diagnostic was the SURFACE: causal 11 of 30 parameter cells
positive, leaky 30 of 30. A real edge is a ridge on a noisy surface; a leak is a plateau.

Baum-Welch itself is worse than the HP filter in one respect: fitting the PARAMETERS on the whole
series leaks even if you then decode causally, because the means and the transition matrix were
learned from the future. So a causal HMM needs BOTH:
  1. parameters fitted on a training block that ends before the bar being labelled, and
  2. FILTERED probabilities P(s_t | observations up to t) -- the forward pass alone, no backward.

Both are implemented here, side by side, so the difference can be measured rather than assumed.

EVERYTHING IS HAND-ROLLED. `hmmlearn` is not installed and this is better without it: the forward
pass, the backward pass and the EM update are visible, so the causal boundary is auditable instead
of being a library flag someone hopes is set correctly.
"""
from __future__ import annotations

import numpy as np

_LOG0 = -1e300


def _logsumexp(a, axis=None):
    a = np.asarray(a, float)
    if axis is None:
        m = np.max(a)
        m = m if np.isfinite(m) else 0.0
        return float(m + np.log(np.sum(np.exp(a - m))))
    m = np.max(a, axis=axis, keepdims=True)
    m = np.where(np.isfinite(m), m, 0.0)
    return np.squeeze(m + np.log(np.sum(np.exp(a - m), axis=axis, keepdims=True)), axis=axis)


def _log_gauss(x, mu, var):
    """Log density of each observation under each state. x (T,D), mu (K,D), var (K,D) diagonal."""
    T, D = x.shape
    K = mu.shape[0]
    out = np.empty((T, K))
    for k in range(K):
        v = np.maximum(var[k], 1e-12)
        z = (x - mu[k]) ** 2 / v
        out[:, k] = -0.5 * (np.sum(z, axis=1) + np.sum(np.log(2 * np.pi * v)))
    return out


def forward(log_b, log_pi, log_A):
    """FILTERED log alpha. alpha[t,k] = log P(s_t = k, observations 1..t). CAUSAL BY CONSTRUCTION:
    alpha[t] depends only on log_b[0..t], so nothing after t can influence the state at t."""
    T, K = log_b.shape
    la = np.full((T, K), _LOG0)
    la[0] = log_pi + log_b[0]
    for t in range(1, T):
        la[t] = log_b[t] + _logsumexp(la[t - 1][:, None] + log_A, axis=0)
    return la


def backward(log_b, log_A):
    """log beta. beta[t,k] = log P(observations t+1..T | s_t = k). READS THE FUTURE -- it exists
    only so the smoothed (leaky) posterior can be computed and compared against the filtered one."""
    T, K = log_b.shape
    lb = np.zeros((T, K))
    for t in range(T - 2, -1, -1):
        lb[t] = _logsumexp(log_A + (log_b[t + 1] + lb[t + 1])[None, :], axis=1)
    return lb


def fit(x, K=3, iters=40, seed=0, tol=1e-4):
    """Baum-Welch on a diagonal-covariance Gaussian HMM. Returns (pi, A, mu, var, loglik)."""
    x = np.asarray(x, float)
    if x.ndim == 1:
        x = x[:, None]
    T, D = x.shape
    rng = np.random.default_rng(seed)
    # Initialise means by quantiles of the first column so states are ordered and reproducible.
    q = np.quantile(x[:, 0], np.linspace(0.1, 0.9, K))
    mu = np.repeat(x.mean(axis=0)[None, :], K, axis=0)
    mu[:, 0] = q
    var = np.repeat(x.var(axis=0)[None, :], K, axis=0) + 1e-8
    A = np.full((K, K), 1.0 / K) * 0.5 + np.eye(K) * 0.5
    A /= A.sum(axis=1, keepdims=True)
    pi = np.full(K, 1.0 / K)
    prev = -np.inf
    for _ in range(iters):
        log_b = _log_gauss(x, mu, var)
        log_A, log_pi = np.log(A + 1e-300), np.log(pi + 1e-300)
        la, lb = forward(log_b, log_pi, log_A), backward(log_b, log_A)
        ll = _logsumexp(la[-1])
        lg = la + lb
        lg -= _logsumexp(lg, axis=1)[:, None]
        g = np.exp(lg)
        # transition posteriors
        xi = np.zeros((K, K))
        for t in range(T - 1):
            m = la[t][:, None] + log_A + (log_b[t + 1] + lb[t + 1])[None, :]
            m -= _logsumexp(m.ravel())
            xi += np.exp(m)
        pi = g[0] / g[0].sum()
        A = xi / np.maximum(xi.sum(axis=1, keepdims=True), 1e-300)
        w = g.sum(axis=0)
        mu = (g.T @ x) / np.maximum(w[:, None], 1e-300)
        for k in range(K):
            d = x - mu[k]
            var[k] = (g[:, k] @ (d * d)) / max(w[k], 1e-300) + 1e-10
        if abs(ll - prev) < tol * max(1.0, abs(prev)):
            break
        prev = ll
    return pi, A, mu, var, ll


def posterior_smoothed(x, pi, A, mu, var):
    """P(s_t | ALL observations). TWO-SIDED. Use for description only -- never as a signal."""
    x = np.asarray(x, float)
    x = x[:, None] if x.ndim == 1 else x
    log_b = _log_gauss(x, mu, var)
    la = forward(log_b, np.log(pi + 1e-300), np.log(A + 1e-300))
    lb = backward(log_b, np.log(A + 1e-300))
    lg = la + lb
    lg -= _logsumexp(lg, axis=1)[:, None]
    return np.exp(lg)


def posterior_filtered(x, pi, A, mu, var):
    """P(s_t | observations up to t). CAUSAL. This is the only version a script can trade."""
    x = np.asarray(x, float)
    x = x[:, None] if x.ndim == 1 else x
    log_b = _log_gauss(x, mu, var)
    la = forward(log_b, np.log(pi + 1e-300), np.log(A + 1e-300))
    la -= _logsumexp(la, axis=1)[:, None]
    return np.exp(la)
