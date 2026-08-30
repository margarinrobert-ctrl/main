"""Fifty years of synthetic index-futures bars, calibrated to NQ/US30 behaviour.

WHY SYNTHETIC DATA IS USEFUL, AND WHAT IT CANNOT DO
---------------------------------------------------
It cannot tell you a strategy is profitable. A backtest on simulated bars measures the SIMULATOR,
and a generator with drift plus a long-biased rule prints money by construction. Read
`docs/ib/SKILL_DIRECTIONAL_ALPHA.md` §1 before believing any number produced from this file.

What it CAN do, and what this module exists for: give you thousands of independent samples of a
world whose properties you know exactly. That converts every "is 1.3 Sharpe good?" question into a
sampling-distribution question you can answer:

  * a MONTE CARLO over independent paths gives the distribution of a parameter's performance
    instead of one number, so "the best lookback" becomes "the lookback with the best MEAN across
    50 independent 50-year worlds, with a confidence interval".
  * an OUT-OF-SAMPLE split inside each path measures the SELECTION PROCEDURE: pick on the first
    65% of sessions, score on the rest, repeat across paths. That is the number that tells you
    whether tuning transfers, and it is not available from a single real history.
  * because the generator's parameters are known, you can ask what the strategy is actually
    harvesting -- turn the trend persistence off and a trend follower must collapse to its cost
    line. `dbt50.py` runs exactly that ablation.

WHAT IS MODELLED
----------------
    log price      r_t = mu_t + sigma_t * s(minute) * eps_t   +   bid-ask bounce
    slow drift     mu_t follows an AR(1) with a long half-life: this is the TREND, and its
                   strength is an explicit parameter, not a hidden gift. Set `trend=0` for the
                   martingale null.
    volatility     log-OU (Ornstein-Uhlenbeck) with daily persistence, so vol clusters and the
                   series has fat unconditional tails without fat innovation tails alone
    innovations    Student-t(5), standardised
    seasonality    a real intraday shape: pre-open lull, an open spike, a midday trough and a
                   close ramp, applied to both volatility and volume
    bars           each bar is built from `sub` sub-steps, so the HIGH and LOW are consistent with
                   a path rather than invented -- triple-barrier results depend entirely on this
    microstructure a bid-ask bounce term that puts a small negative autocorrelation in bar returns,
                   which is what real 5-minute index futures show
    grid           prices snapped to the 0.25 tick, and OHLC repaired so h >= max(o,c) always

`selftest()` asserts the generator hits its calibration targets rather than trusting them.
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TICK = 0.25
SESS_OPEN = 420        # 07:00 New York, in minutes from midnight
SESS_CLOSE = 960       # 16:00
DAYS_PER_YEAR = 252


def intraday_shape(mod):
    """Volatility multiplier by minute of day. Roughly the real NQ profile, normalised to mean 1.

    Four features that matter for a 07:00-11:00 strategy: the pre-open lull, the 09:30 spike, the
    08:30 data-release bump and the midday trough. A flat profile would make the session choice
    meaningless and every time-of-day result an artefact.
    """
    m = np.asarray(mod, float)
    s = np.full_like(m, 0.55)                            # pre-open baseline
    s += 0.75 * np.exp(-0.5 * ((m - 510) / 18.0) ** 2)   # 08:30 releases
    s += 1.90 * np.exp(-0.5 * ((m - 573) / 14.0) ** 2)   # 09:33 open spike
    s += 0.55 * np.exp(-0.5 * ((m - 630) / 45.0) ** 2)   # the 10:30 continuation
    s += 0.65 * np.exp(-0.5 * ((m - 950) / 22.0) ** 2)   # the close ramp
    s = np.where(m >= 570, s + 0.35, s)                  # RTH is simply busier than pre-market
    return s / 1.15


def volume_shape(mod):
    v = intraday_shape(mod) ** 1.6
    return v / v.mean()


def synth(years=50, seed=0, tf=5, start_px=15000.0, ann_vol=0.20, ann_drift=0.07,
          trend=0.10, trend_hl_days=12.0, vol_kappa=0.06, vol_eta=0.15, nu=5.0,
          bounce_ticks=0.35, sub=6, open_gap_bp=12.0):
    """One path. Returns the bar dict every other module in this repository consumes.

    years        length. 50 years x 252 days x 108 five-minute bars = 1.36M bars.
    ann_vol      target annualised volatility of daily closes.
    ann_drift    annualised log drift. Index futures rose; leaving this at 0 is the martingale
                 null and is what `dbt50.py` uses for its Stage 0 check.
    trend        AR(1) coefficient of the slow drift state, in DAILY units. 0 = no trend to follow.
                 MEASURED, not asserted: trend=0 gives VR(5) 1.01 and daily ACF(1) +0.01; the
                 default 0.10 gives VR(5) 1.14 and ACF +0.04; 0.35 gives VR(5) 1.49 and ACF +0.13.
                 A real index sits near the low end, so 0.35 is already a world far kinder to a
                 trend follower than the one it will trade. Every result must be reported against
                 the trend=0 ablation or it is a statement about this number.
    bounce_ticks size of the bid-ask bounce, which makes bar returns slightly mean-reverting.
    sub          sub-steps per bar used to form the high and low.
    """
    rng = np.random.default_rng(seed)
    bars_per_day = (SESS_CLOSE - SESS_OPEN) // tf
    n_days = int(years * DAYS_PER_YEAR)
    n = n_days * bars_per_day
    mod = np.tile(SESS_OPEN + tf * np.arange(bars_per_day), n_days).astype(np.int64)
    sess = np.repeat(np.arange(n_days), bars_per_day).astype(np.int64)

    # --- per-bar volatility: log-OU at the DAILY scale, spread over the session
    h = np.empty(n_days)
    h[0] = 0.0
    for d in range(1, n_days):                            # cheap: 12,600 steps, not 1.36M
        h[d] = (1 - vol_kappa) * h[d - 1] + vol_eta * rng.normal()
    h -= 0.5 * np.var(h)                                  # keep E[exp(h)] ~ 1 so ann_vol is honest
    daily_sig = ann_vol / np.sqrt(DAYS_PER_YEAR) * np.exp(h)
    bar_sig = np.repeat(daily_sig, bars_per_day) / np.sqrt(bars_per_day)
    bar_sig = bar_sig * intraday_shape(mod)

    # --- the slow drift state: this is the trend, and it lives at the daily scale
    phi = float(np.clip(trend, 0.0, 0.999))
    mu_d = np.zeros(n_days)
    if phi > 0:
        lam = 0.5 ** (1.0 / max(trend_hl_days, 1e-6))     # half-life in days
        w = daily_sig * np.sqrt(1 - lam ** 2) * phi
        for d in range(1, n_days):
            mu_d[d] = lam * mu_d[d - 1] + w[d] * rng.normal()
    mu_bar = np.repeat(mu_d, bars_per_day) / bars_per_day
    mu_bar += (ann_drift / DAYS_PER_YEAR) / bars_per_day

    # --- innovations: standardised Student-t, so kurtosis comes from BOTH t and the vol process
    t = rng.standard_t(nu, size=(n, sub)) / np.sqrt(nu / (nu - 2.0))
    step = (mu_bar[:, None] / sub) + (bar_sig[:, None] / np.sqrt(sub)) * t

    # --- overnight gap: the session is not continuous, so the first bar of a day carries one
    first = np.flatnonzero(mod == SESS_OPEN)
    step[first, 0] += (open_gap_bp / 1e4) * rng.standard_t(nu, size=len(first)) / \
        np.sqrt(nu / (nu - 2.0))

    logp = np.log(start_px) + np.cumsum(step.reshape(-1)).reshape(n, sub)
    path = np.exp(logp)
    o = np.empty(n); o[0] = start_px; o[1:] = path[:-1, -1]
    c = path[:, -1]
    hi = np.maximum(path.max(1), np.maximum(o, c))
    lo = np.minimum(path.min(1), np.minimum(o, c))

    # --- bid-ask bounce: applied to the CLOSE only, which is where it shows up in bar returns
    b = bounce_ticks * TICK * rng.choice([-1.0, 1.0], size=n)
    c = np.clip(c + b, lo, hi)

    q = lambda x: np.round(x / TICK) * TICK
    o, hi, lo, c = q(o), q(hi), q(lo), q(c)
    hi = np.maximum(hi, np.maximum(o, c)); lo = np.minimum(lo, np.minimum(o, c))

    vbase = 900.0 * volume_shape(mod) * np.repeat(np.exp(0.6 * h), bars_per_day)
    v = np.maximum(rng.gamma(4.0, vbase / 4.0), 1.0)

    return dict(o=o, h=hi, l=lo, c=c, v=v, mod=mod, sess=sess, n=n,
                _key=("synth50", seed, years, tf, round(trend, 4), round(ann_drift, 4)))


# ===================================================================== calibration
def stats(d, tf=5):
    """The numbers a generator has to get right before anything is measured on it."""
    c = d["c"]; sess = d["sess"]
    last = np.flatnonzero(np.r_[np.diff(sess), 1] != 0)
    dc = np.diff(np.log(c[last]))
    r = np.diff(np.log(c))
    def acf(x, k):
        x = x - x.mean()
        return float((x[k:] @ x[:-k]) / (x @ x))
    # variance ratio at 5 days, the standard trend/reversal statistic
    q = 5
    m = len(dc) // q * q
    vr = (np.var(dc[:m].reshape(-1, q).sum(1)) / q) / np.var(dc[:m])
    mod = d["mod"]
    def vol_at(lo, hi):
        m_ = (mod >= lo) & (mod < hi)
        return float(np.std(r[m_[1:]]))
    return dict(bars=len(c), years=round(len(np.unique(sess)) / DAYS_PER_YEAR, 1),
                ann_vol=float(np.std(dc) * np.sqrt(DAYS_PER_YEAR)),
                ann_drift=float(np.mean(dc) * DAYS_PER_YEAR),
                daily_kurt=float(((dc - dc.mean()) ** 4).mean() / np.var(dc) ** 2),
                daily_acf1=acf(dc, 1), bar_acf1=acf(r, 1), vr5=float(vr),
                vol_open=vol_at(570, 600), vol_mid=vol_at(720, 780), vol_pre=vol_at(420, 540),
                px_end=float(c[-1]))


def _mean_stat(key, reps=4, years=6, **kw):
    """Average a statistic over independent paths.

    Return autocorrelation and the variance ratio are extremely noisy under fat tails and
    volatility clustering: on a single 6-year path the null ACF(1) ranges over [-0.18, +0.11]
    across seeds while its mean is 0.009, and the null VR(5) has a per-path sd near 0.16. A
    single-path assertion would make this self-test a coin flip -- the same mistake as reading one
    backtest. Reps are therefore not optional here.
    """
    return float(np.mean([stats(synth(years=years, seed=1000 + i, **kw))[key]
                          for i in range(reps)]))


def selftest(years=6, seed=1):
    """Assert the calibration targets, and assert `trend` actually controls the trend."""
    d = synth(years=years, seed=seed)
    s = stats(d)
    assert 0.15 < s["ann_vol"] < 0.28, f"annualised vol {s['ann_vol']:.3f} off target"
    assert 4.0 < s["daily_kurt"] < 20.0, (f"daily kurtosis {s['daily_kurt']:.2f} is out of the "
                                          "range real index futures show (roughly 5 to 12)")
    assert s["bar_acf1"] < 0.0, f"bar ACF(1) {s['bar_acf1']:+.3f} should be negative (bounce)"
    assert s["vol_open"] > 1.6 * s["vol_mid"], "no intraday open spike"
    assert s["vol_pre"] < s["vol_mid"], "pre-market is not quieter than midday"

    reps, yrs = 6, 10
    null_acf = _mean_stat("daily_acf1", reps, yrs, trend=0.0, ann_drift=0.0)
    null_vr = _mean_stat("vr5", reps, yrs, trend=0.0, ann_drift=0.0)
    dflt_vr = _mean_stat("vr5", reps, yrs)
    hot_vr = _mean_stat("vr5", reps, yrs, trend=0.35, ann_drift=0.0)
    assert abs(null_acf) < 0.05, f"the null path has mean ACF {null_acf:+.3f}"
    assert abs(null_vr - 1.0) < 0.12, (
        f"the null VR(5) is {null_vr:.3f}, not ~1: the martingale path is not a martingale, so "
        "nothing measured on this generator can be trusted")
    assert null_vr < dflt_vr < hot_vr, "the trend parameter does not order the variance ratio"
    return dict(default=s, null_vr5=round(null_vr, 3), default_vr5=round(dflt_vr, 3),
                trend035_vr5=round(hot_vr, 3), null_daily_acf=round(null_acf, 4))


if __name__ == "__main__":
    import json
    print(json.dumps(selftest(), indent=2, default=float))
