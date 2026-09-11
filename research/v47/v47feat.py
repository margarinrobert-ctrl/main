"""V47 -- risk-premium and PEAD-analogue features, and an honest statement of what they are not.

WHAT THIS IS NOT, SAID FIRST BECAUSE THE NAMES PROMISE MORE THAN THE DATA CAN DELIVER.

PEAD IS NOT MEASURABLE HERE. Post-earnings announcement drift is defined on SINGLE NAMES: SUE =
(actual EPS - consensus) / sigma, then drift over ~60 days in the surprise direction. It needs
earnings dates, analyst consensus and per-stock returns. This branch has index-futures OHLCV and
nothing else. What is built below is an INDEX-LEVEL ANALOGUE OF THE MECHANISM -- underreaction to
a large information event followed by drift in its direction -- with the event identified
ENDOGENOUSLY from a standardised move. On an index those events are macro releases (CPI, FOMC,
NFP) and earnings season in aggregate. Every result is a statement about that analogue, never
about PEAD.

CLASSICAL RISK PREMIA ARE MOSTLY NOT MEASURABLE EITHER. Value, size, credit and term need a
cross-section or a bond curve. THE VARIANCE RISK PREMIUM NEEDS IMPLIED VOL, which no feed here
carries -- so `rv_term` below is a REALISED variance term structure, a proxy, and calling it the
VRP would be wrong. What genuinely survives on one futures tape is the SESSION decomposition (the
night premium), realised higher moments, the semivariance/skew asymmetry, and time-series
momentum.

TURN-OF-MONTH IS DECLARED, NOT SEARCHED. This repo bans calendar conditions from rule search
because they partition the sample and hand the search a free lottery. It is admitted here as ONE
pre-registered published hypothesis with a fixed definition, never as a grid axis, and it is
counted in the multiplicity correction like everything else.

Every feature is knowable at its own day's RTH close. `audit()` proves it by truncation.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v47")


def _z(x, n):
    s = pd.Series(x)
    return ((s - s.rolling(n, min_periods=max(5, n // 3)).mean())
            / s.rolling(n, min_periods=max(5, n // 3)).std(ddof=1)).to_numpy()


def _roll(x, n, fn, minp=None):
    return getattr(pd.Series(x).rolling(n, min_periods=minp or max(5, n // 3)), fn)().to_numpy()


def build(D):
    r = D.r_day.to_numpy()
    ron = D.r_on.to_numpy()
    rin = D.r_rth.to_numpy()
    rng = D.rng_rth.to_numpy()
    vol = D.all_vol.to_numpy()
    f = {}

    # ---------------- RISK PREMIA (what a single futures tape can actually carry) --------------
    rv5 = _roll(r, 5, "std") * np.sqrt(252)
    rv20 = _roll(r, 20, "std") * np.sqrt(252)
    rv60 = _roll(r, 60, "std") * np.sqrt(252)
    f["rp.rv20"] = rv20
    # REALISED variance term structure. NOT the variance risk premium -- that needs implied vol.
    f["rp.rv_term_5_60"] = np.where(rv60 > 0, rv5 / rv60, np.nan)
    f["rp.rv_term_20_60"] = np.where(rv60 > 0, rv20 / rv60, np.nan)
    f["rp.volofvol"] = _roll(rv20, 60, "std")

    up = np.where(r > 0, r, 0.0)
    dn = np.where(r < 0, r, 0.0)
    su = np.sqrt(_roll(up ** 2, 20, "mean"))
    sd = np.sqrt(_roll(dn ** 2, 20, "mean"))
    f["rp.semi_skew"] = np.where(su > 0, sd / su, np.nan)      # downside / upside realised vol
    f["rp.rskew60"] = _roll(r, 60, "skew")
    f["rp.rkurt60"] = _roll(r, 60, "kurt")

    # SESSION PREMIUM -- the one classical premium this data really can address
    f["rp.on_mean20"] = _roll(ron, 20, "mean")
    f["rp.rth_mean20"] = _roll(rin, 20, "mean")
    tot = _roll(r, 20, "mean")
    f["rp.on_share20"] = np.where(np.abs(tot) > 1e-9, _roll(ron, 20, "mean") / tot, np.nan)
    f["rp.on_rth_spread"] = _roll(ron, 20, "mean") - _roll(rin, 20, "mean")

    # TIME-SERIES MOMENTUM (the trend premium), raw and volatility-scaled
    for n in (20, 60, 120):
        m = _roll(r, n, "sum")
        f[f"rp.tsmom{n}"] = m
        f[f"rp.tsmom{n}_vs"] = np.where(rv20 > 0, m / rv20, np.nan)

    f["rp.range_comp"] = np.where(_roll(rng, 60, "mean") > 0, rng / _roll(rng, 60, "mean"), np.nan)
    f["rp.vol_ratio"] = np.where(_roll(vol, 60, "mean") > 0, vol / _roll(vol, 60, "mean"), np.nan)

    # TURN OF MONTH -- declared, fixed definition, one hypothesis. Never a search axis.
    dom = D.index.day.to_numpy()
    dim = D.index.days_in_month.to_numpy()
    f["rp.tom"] = ((dom >= dim - 3) | (dom <= 3)).astype(float)

    # ---------------- PEAD ANALOGUE (the mechanism, not the phenomenon) -----------------------
    # SUE analogue: the day's move standardised by trailing volatility. On an index the large
    # values are macro releases and aggregate earnings season, not a single company's surprise.
    sig = _roll(r, 60, "std")
    f["pead.sue"] = np.where(sig > 0, r / sig, np.nan)
    f["pead.abs_sue"] = np.abs(f["pead.sue"])
    sig_on = _roll(ron, 60, "std")
    # The overnight leg is where a scheduled release actually lands for a US index future.
    f["pead.sue_on"] = np.where(sig_on > 0, ron / sig_on, np.nan)
    f["pead.gap_z"] = _z(ron, 60)

    # Drift bookkeeping: how long since the last big surprise, and its sign, decayed.
    for thr in (1.5, 2.0):
        s = f["pead.sue"]
        ev = np.abs(s) >= thr
        sgn = np.where(ev, np.sign(s), 0.0)
        last_sgn = np.zeros(len(r)); since = np.full(len(r), np.nan)
        cur, age = 0.0, np.nan
        for i in range(len(r)):
            if ev[i] and np.isfinite(s[i]):
                cur, age = sgn[i], 0.0
            elif np.isfinite(age):
                age += 1.0
            last_sgn[i] = cur; since[i] = age
        f[f"pead.ev{thr}_sign"] = last_sgn
        f[f"pead.ev{thr}_since"] = since
        with np.errstate(invalid="ignore"):
            f[f"pead.ev{thr}_decay"] = last_sgn * np.exp(-since / 10.0)
    return f


FAMILIES = ("rp", "pead")


def audit(D, probes=(200, 400, 600), tol=1e-8):
    """Truncation audit -- recompute on a frame ENDING at row i and require the value to match."""
    full = build(D)
    bad = {}
    for i in probes:
        if i >= len(D):
            continue
        cut = build(D.iloc[:i + 1])
        for k in full:
            a, b = full[k][i], cut[k][i]
            if (np.isnan(a) and np.isnan(b)):
                continue
            if not np.isfinite(a) or not np.isfinite(b) or abs(a - b) > tol * max(1.0, abs(a)):
                bad.setdefault(k, []).append(i)
    return bad
