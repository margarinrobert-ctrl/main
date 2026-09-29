"""PIN (probability of informed trading) as an INTRADAY signal -- Easley-Kiefer-O'Hara-Paperman
(1996) with Yan (2009, SSRN 1361921) as the estimator.

PHASE 0 -- THE MECHANISM, AND WHO IS ON THE OTHER SIDE.
The model names the counterparty explicitly, which is rare. Uninformed traders arrive at rates
eps_b and eps_s EVERY day whether or not an information event is happening -- they are trading for
liquidity, rebalancing or market-making obligation, not on the news. On an event day informed
traders arrive at rate mu on ONE SIDE ONLY. The uninformed are on the wrong side of that flow by
construction, because they do not know. That is a constrained-flow story: someone must trade
anyway, and cannot stop.

WHAT IS ACTUALLY TRADEABLE, AND WHAT IS NOT.
PIN itself is NOT a signal. It is the unconditional fraction of trades that are informed,
PIN = a*mu / (a*mu + eps_b + eps_s) -- a static, non-directional, cross-sectional quantity used in
asset pricing to explain expected returns over months. It says nothing about which way to trade
today. Anyone selling "PIN" as an entry signal has skipped this paragraph.

What IS directional, and IS a probability, is the POSTERIOR from the same mixture given the order
flow observed SO FAR TODAY:

    P(good | B,S)  prop  a(1-d) * Pois(B; eps_b + mu) * Pois(S; eps_s)
    P(bad  | B,S)  prop  a*d    * Pois(B; eps_b)      * Pois(S; eps_s + mu)
    P(none | B,S)  prop  (1-a)  * Pois(B; eps_b)      * Pois(S; eps_s)

That is the market maker's own belief update -- the thing EKOP's dealer computes to move quotes --
and it is the only object in the paper that has a direction attached to it.

THE B/S DEGRADATION, STATED ONCE AND CARRIED EVERYWHERE.
B and S are counts of BUYER- and SELLER-INITIATED trades, classified by Lee-Ready (1991), which
needs the QUOTE MIDPOINT. No feed on this branch carries quotes or aggressor tags -- recorded in
STUDY_V54, STUDY_XAU_CVD_FEATURES and the datasets registry. So B and S here are COUNTS OF
ONE-MINUTE BARS that closed up and down within the session. That is a proxy and it is named a
proxy in every result.

Two things make it less bad than it sounds. EKOP's own footnote 7 states that their model ignores
trade SIZE and works on counts of B and S alone, so a count is the faithful unit. And NQ_1m is the
only feed here with one-minute bars, so it is the only market this can run on at all.

CAUSALITY. Yan's step 1 identifies event days with an event study over the FULL period, which is
two-sided and cannot be traded. Here an event day is one whose session return exceeds k trailing
standard deviations, with the mean and sd computed from sessions ENDING BEFORE the day being
labelled, and every parameter (a, d, eps_b, eps_s, mu) estimated on a trailing window that closes
before the session it is used in.
"""
import sys, os
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5")
import numpy as np, pandas as pd
from scipy.special import gammaln
import s5data as S

RT_POINTS = S.RT_POINTS          # MNQ all-in round turn, 1.72 points
SLIP = S.SLIP_POINTS
PV = 2.0                         # MNQ, $2 a point


def load(tf=10, win_open=570, win_close=960):
    """NQ, decision bars of `tf` minutes plus the raw 1-minute series the B/S counts come from."""
    base = S.load_1m()
    D = S.assemble(S.resample(base, tf), tf, win_open=win_open, win_close=win_close)
    D["base"] = base
    return D


def bs_counts(D):
    """B and S as counts of one-minute bars closing up / down, accumulated within the session.

    Returned per DECISION BAR: the running counts as of that bar's CLOSE, so a bar's own minutes
    are included and nothing after it is. This is the quantity the market maker has seen when the
    decision is made."""
    b = D["base"]
    up = (b["close"].to_numpy() > b["open"].to_numpy()).astype(np.int64)
    dn = (b["close"].to_numpy() < b["open"].to_numpy()).astype(np.int64)
    mod1 = (b.index.hour * 60 + b.index.minute).to_numpy()
    day1 = b.index.normalize().values.astype("datetime64[D]").astype(np.int64)
    on = (mod1 >= D["win_open"]) & (mod1 < D["win_close"])
    f = pd.DataFrame({"b": np.where(on, up, 0), "s": np.where(on, dn, 0), "d": day1}, index=b.index)
    cb = f.groupby("d").b.cumsum().to_numpy().astype(float)
    cs = f.groupby("d").s.cumsum().to_numpy().astype(float)
    cb[~on] = np.nan; cs[~on] = np.nan
    B = pd.Series(cb, index=b.index).reindex(D["ix"], method="ffill").to_numpy()
    Sc = pd.Series(cs, index=b.index).reindex(D["ix"], method="ffill").to_numpy()
    return B, Sc


def session_frame(D, B, Sc):
    """One row per session: the full-session B and S, and the session return."""
    inw = D["inw"]
    idx = np.flatnonzero(inw)
    day = D["day"]
    last = {}
    for i in idx:
        last[day[i]] = i
    days = np.array(sorted(last))
    li = np.array([last[d] for d in days])
    first = {}
    for i in idx[::-1]:
        first[day[i]] = i
    fi = np.array([first[d] for d in days])
    return pd.DataFrame(dict(day=days, first=fi, last=li, B=B[li], S=Sc[li],
                             ret=(D["c"][li] / D["o"][fi] - 1.0) * 100.0))


def fit_causal(F, i, window=120, k=1.0, min_events=6):
    """EKOP parameters from sessions [i-window, i-1] ONLY -- nothing from session i or later.

    Yan's four steps, with step 1 made causal: an event day is one whose session return exceeds k
    trailing standard deviations of the window's own returns.
    """
    lo = max(0, i - window)
    w = F.iloc[lo:i]
    if len(w) < 30:
        return None
    r = w.ret.to_numpy()
    sd = r.std(ddof=1)
    if not np.isfinite(sd) or sd <= 0:
        return None
    ev = np.abs(r - r.mean()) > k * sd
    good = ev & (r > 0)
    bad = ev & (r < 0)
    if ev.sum() < min_events or good.sum() < 2 or bad.sum() < 2 or (~ev).sum() < 10:
        return None
    a = float(ev.mean())
    d = float(bad.sum() / ev.sum())
    Bv, Sv = w.B.to_numpy(), w.S.to_numpy()
    eb = float(Bv[~ev].mean())
    es = float(Sv[~ev].mean())
    # Yan eq. (5) and (6): mu from the conditional means, not from a likelihood
    b_gn = float(Bv[good | ~ev].mean())
    s_bn = float(Sv[bad | ~ev].mean())
    mu_b = (b_gn - eb) / max(1.0 - d, 1e-6)
    mu_s = (s_bn - es) / max(d, 1e-6)
    mu = 0.5 * (mu_b + mu_s)
    if not np.isfinite(mu) or mu <= 0 or eb <= 0 or es <= 0:
        return None
    pin = a * mu / (a * mu + eb + es)                       # Yan eq. (8)
    return dict(a=a, d=d, eb=eb, es=es, mu=mu, mu_b=mu_b, mu_s=mu_s, pin=pin, n=len(w),
                n_ev=int(ev.sum()))


def _lpois(k, lam):
    lam = max(lam, 1e-9)
    return k * np.log(lam) - lam - gammaln(k + 1.0)


def posterior(Bt, St, p, frac):
    """P(good), P(bad), P(none) given the flow SO FAR, with the arrival rates scaled by the
    fraction of the session elapsed -- a Poisson process observed for `frac` of its day has mean
    `frac * rate`."""
    eb, es, mu = p["eb"] * frac, p["es"] * frac, p["mu"] * frac
    lg = np.log(max(p["a"] * (1 - p["d"]), 1e-12)) + _lpois(Bt, eb + mu) + _lpois(St, es)
    lb = np.log(max(p["a"] * p["d"], 1e-12)) + _lpois(Bt, eb) + _lpois(St, es + mu)
    ln = np.log(max(1 - p["a"], 1e-12)) + _lpois(Bt, eb) + _lpois(St, es)
    m = max(lg, lb, ln)
    g, b, n = np.exp(lg - m), np.exp(lb - m), np.exp(ln - m)
    t = g + b + n
    return g / t, b / t, n / t
