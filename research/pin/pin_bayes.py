"""The Griffin-Oberoi-Oduro (2018, SSRN 3305086) Bayesian estimator for the EHO/EKOP PIN model.

WHY THIS PAPER MATTERS HERE, IN ONE PARAGRAPH.
`pin_core.py` estimates the same mixture with Yan (2009)'s four-step moment estimator. Yan's step 1
labels event periods with an EVENT STUDY over the whole sample, which is two-sided and untradeable,
so the causal replacement was "a period whose return exceeds evK trailing standard deviations" --
an ad hoc rule carrying a free parameter I had to sweep. THE GIBBS SAMPLER REMOVES THAT PARAMETER
ENTIRELY: D_t is a LATENT VARIABLE sampled from the model itself, never labelled from the return.
That is a strict reduction in free parameters on the primary, which is the thing the mechanism-first
architecture actually cares about. The paper's other two claims are also directly on point -- MLE
PIN is biased "especially in the case of liquid and frequently traded assets" (an index future is
the extreme of that), and the model can be run with the news type fixed over INTRADAY intervals
rather than days, from as few as 26 observations.

THE SAMPLER (their section 3.4), with the data augmentation:
    D_t in {1 bad, 2 good, 3 none} with weights (a*d, a(1-d), 1-a)
    B_t | D=2 ~ Pois(lb + mu),  else Pois(lb)
    S_t | D=1 ~ Pois(ls + mu),  else Pois(ls)
    conditional on the sum, the informed part is Binomial: S^i | S_t ~ Bin(S_t, mu/(mu+ls))
Conjugate priors: Beta on a and d, Gamma on mu, ls, lb, all hyper-parameters 1 as the paper sets
them. Full conditionals are their equations (5a)-(5e).

ONE CORRECTION TO THE PUBLISHED CONDITIONALS. Their (5b) reads delta ~ Be(nu + T1 + T2, T2 + tau).
That cannot be right: delta is P(bad | news), so its Beta counts bad against good and the first
shape must be T1, not T1 + T2 -- the T1 + T2 is copied from the alpha line (5a) directly above,
where it IS correct because alpha counts news against no-news. Implemented as Be(nu + T1, tau + T2)
and the typo is noted rather than reproduced; `_selftest_conditionals` checks the corrected version
recovers a known delta and the published one does not.
"""
import numpy as np

__all__ = ["gibbs", "posterior_state", "simulate", "PinFit"]


class PinFit(dict):
    """A fitted mixture: posterior means plus the full chains, so uncertainty is available."""
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as e:
            raise AttributeError(k) from e


def _cat_probs(B, S, a, d, mu, lb, ls):
    """The paper's L1/L2/L3 with the log-sum-exp trick. lgamma(B+1) and lgamma(S+1) are identical
    in all three rows -- B and S are the same data under every hypothesis -- so they cancel in the
    normalisation and never need computing. This is the same cancellation the Pine relies on."""
    lb_ = max(lb, 1e-12)
    ls_ = max(ls, 1e-12)
    mu_ = max(mu, 1e-12)
    L1 = np.log(max(a * d, 1e-300)) - (mu_ + ls_ + lb_) + B * np.log(lb_) + S * np.log(ls_ + mu_)
    L2 = np.log(max(a * (1 - d), 1e-300)) - (mu_ + ls_ + lb_) + S * np.log(ls_) \
        + B * np.log(lb_ + mu_)
    L3 = np.log(max(1 - a, 1e-300)) - (ls_ + lb_) + S * np.log(ls_) + B * np.log(lb_)
    M = np.maximum(L1, np.maximum(L2, L3))
    e1, e2, e3 = np.exp(L1 - M), np.exp(L2 - M), np.exp(L3 - M)
    t = e1 + e2 + e3
    return e1 / t, e2 / t, e3 / t


def gibbs(B, S, sweeps=1500, burn=500, thin=1, seed=0, hyper=None, init=None):
    """Sample the posterior of (a, d, mu, lb, ls) given period buy/sell counts B, S.

    Returns a PinFit with posterior means, the chains, and the PIN chain so a credible interval is
    available for free -- the paper's main practical selling point over MLE.
    """
    rng = np.random.default_rng(seed)
    B = np.asarray(B, float)
    S = np.asarray(S, float)
    ok = np.isfinite(B) & np.isfinite(S)
    B, S = B[ok], S[ok]
    T = len(B)
    if T < 10:
        return None
    h = dict(rho=1.0, phi=1.0, nu=1.0, tau=1.0, g0=1.0, b0=1.0, g1=1.0, b1=1.0, g2=1.0, b2=1.0)
    if hyper:
        h.update(hyper)

    # start from moments; the paper's point is that the ANSWER does not depend on this
    mb, ms = B.mean(), S.mean()
    if init:
        a, d, mu, lb, ls = (init[k] for k in ("a", "d", "mu", "lb", "ls"))
    else:
        a, d = 0.3, 0.5
        mu = max(0.3 * (mb + ms) / 2.0, 1e-6)
        lb, ls = max(mb - 0.15 * mb, 1e-6), max(ms - 0.15 * ms, 1e-6)
    D = rng.integers(1, 4, T)

    keep = []
    for k in range(sweeps):
        # --- data augmentation: the informed part of the count, on the side it arrives
        pB = mu / max(mu + lb, 1e-12)
        pS = mu / max(mu + ls, 1e-12)
        Bi = rng.binomial(B.astype(np.int64), min(max(pB, 0.0), 1.0))
        Si = rng.binomial(S.astype(np.int64), min(max(pS, 0.0), 1.0))
        m1, m2, m3 = D == 1, D == 2, D == 3
        T1, T2, T3 = int(m1.sum()), int(m2.sum()), int(m3.sum())

        # --- (5c) mu: informed arrivals only exist on news periods, so the rate is T1 + T2
        sh = h["g0"] + Si[m1].sum() + Bi[m2].sum()
        mu = rng.gamma(max(sh, 1e-9), 1.0 / max(T1 + T2 + h["b0"], 1e-9))
        # --- (5d) lambda_s: the uninformed sell flow, present in every period
        sh = h["g1"] + (S[m1] - Si[m1]).sum() + S[m2].sum() + S[m3].sum()
        ls = rng.gamma(max(sh, 1e-9), 1.0 / max(T + h["b1"], 1e-9))
        # --- (5e) lambda_b
        sh = h["g2"] + B[m1].sum() + (B[m2] - Bi[m2]).sum() + B[m3].sum()
        lb = rng.gamma(max(sh, 1e-9), 1.0 / max(T + h["b2"], 1e-9))
        # --- (5a) alpha: news against no-news
        a = rng.beta(h["rho"] + T1 + T2, h["phi"] + T3)
        # --- (5b) delta: bad against good. See the docstring -- the paper prints T1 + T2 here.
        d = rng.beta(h["nu"] + T1, h["tau"] + T2)

        p1, p2, p3 = _cat_probs(B, S, a, d, mu, lb, ls)
        u = rng.random(T)
        D = np.where(u < p1, 1, np.where(u < p1 + p2, 2, 3))

        if k >= burn and (k - burn) % thin == 0:
            keep.append((a, d, mu, lb, ls))

    ch = np.array(keep)
    if not len(ch):
        return None
    a_, d_, mu_, lb_, ls_ = ch.T
    pin = a_ * mu_ / (a_ * mu_ + lb_ + ls_)
    return PinFit(a=float(a_.mean()), d=float(d_.mean()), mu=float(mu_.mean()),
                  lb=float(lb_.mean()), ls=float(ls_.mean()), pin=float(pin.mean()),
                  pin_lo=float(np.quantile(pin, 0.05)), pin_hi=float(np.quantile(pin, 0.95)),
                  pin_sd=float(pin.std()), mu_sd=float(mu_.sd() if hasattr(mu_, "sd")
                                                       else mu_.std()),
                  ratio=float((mu_ / (lb_ + ls_)).mean()), n=T, chain=ch, pin_chain=pin)


def posterior_state(Bt, St, p, frac=1.0):
    """P(good), P(bad), P(none) given the flow SO FAR, arrival rates scaled by the fraction of the
    period elapsed. Identical in form to pin_core.posterior; kept separate so the two estimators
    can be compared with the SAME decision rule and only the parameters differing."""
    g, b, n = _cat_probs(np.asarray(Bt, float), np.asarray(St, float),
                         p["a"], p["d"], p["mu"] * frac, p["lb"] * frac, p["ls"] * frac)
    return g, b, n


def simulate(T=400, a=0.35, d=0.45, mu=40.0, lb=60.0, ls=55.0, seed=1):
    """Draw from the model itself, so the estimator can be checked against a KNOWN answer."""
    rng = np.random.default_rng(seed)
    u = rng.random(T)
    D = np.where(u < a * d, 1, np.where(u < a, 2, 3))
    B = rng.poisson(np.where(D == 2, lb + mu, lb))
    S = rng.poisson(np.where(D == 1, ls + mu, ls))
    return B.astype(float), S.astype(float), D


def _selftest_conditionals(seed=3):
    """The delta typo, demonstrated rather than asserted: the published Be(nu+T1+T2, T2+tau) is
    biased toward 1 because it counts every news period as 'bad'."""
    B, S, D = simulate(T=800, d=0.30, seed=seed)
    good = gibbs(B, S, sweeps=1200, burn=400, seed=seed)
    rng = np.random.default_rng(seed)
    T1, T2 = int((D == 1).sum()), int((D == 2).sum())
    published = rng.beta(1 + T1 + T2, 1 + T2, 4000).mean()
    return dict(true_d=0.30, corrected=good["d"], published_form=float(published))
