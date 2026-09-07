"""The SAM condition pool: every reading of semivariance asymmetry worth enumerating.

SAM-Fut takes ONE reading -- is the rolling sum of RS+ minus RS- negative over W days -- and
trades it as a daily state. That is one point in a large space, and the space is what a scalping
version has to be chosen from rather than inherited. Three axes, all of which change what the
signal means:

  ESTIMATOR   `i` intrabar: realized semivariance from the 1-minute returns inside each bar, which
              is what the paper does with 30-minute returns inside a day.
              `b` bar-return: from the bar's own close-to-close return. Coarser, and the only one
              a Pine script can compute without lower-timeframe data.

  NORMALISATION
              raw    sum(RS+) - sum(RS-).  Scale depends on volatility, so only its SIGN is
                     comparable across regimes -- which is why the original only ever tests < 0.
              ratio  (sum(RS+) - sum(RS-)) / (sum(RS+) + sum(RS-)).  Bounded in [-1, 1], the
                     standard relative signed variation. A threshold on this means the same thing
                     in a quiet market and a violent one, which raw SAM cannot manage.
              z      SAM standardised against its own trailing 100-bar distribution. "Unusually
                     asymmetric for this market lately", rather than "asymmetric".

  READING     state (the measure is beyond a threshold now) or cross (it just went beyond it).
              A state under a 1R barrier means "re-enter whenever flat and the regime holds"; a
              cross is the event itself. SAM-Fut is a state; a scalp is more naturally a cross.

12 windows x 2 estimators x (raw + 7 ratio thresholds + 7 z thresholds) x 2 directions x 2
readings = 1,440 conditions. Everything is causal and every rolling statistic is backward-looking.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
import indicators as I
from newsignals import bar_semivar, intrabar_semivar

WINDOWS = (2, 3, 4, 5, 6, 8, 10, 13, 16, 21, 26, 34)
RATIO_T = (-0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3)
Z_T = (-1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5)
ZLB = 100                 # trailing window the z-score standardises against


def _parts(d, tf, est):
    if est == "i":
        rp, rn, _cnt, _d = intrabar_semivar(tf)
        return rp, rn
    return bar_semivar(d)


def measures(d, tf):
    """{name: value array} for every (estimator, window, normalisation)."""
    out = {}
    for est in ("i", "b"):
        rp, rn = _parts(d, tf, est)
        for w in WINDOWS:
            sp, sn = I.rsum(rp, w), I.rsum(rn, w)
            raw = sp - sn
            tot = sp + sn
            out[f"SAM{est}{w}"] = raw
            out[f"SAR{est}{w}"] = np.where(tot > 0, raw / np.maximum(tot, 1e-18), np.nan)
            mu = I.sma(raw, ZLB)
            sd = I.rstd(raw, ZLB)
            out[f"SAZ{est}{w}"] = np.where(sd > 0, (raw - mu) / np.maximum(sd, 1e-18), np.nan)
    return out


def conditions(d, tf):
    """{name: bool array}. State and cross, both directions, for every measure and threshold."""
    M = measures(d, tf)
    S = {}
    for est in ("i", "b"):
        for w in WINDOWS:
            for pfx, thresholds in ((f"SAM{est}{w}", (0.0,)),
                                    (f"SAR{est}{w}", RATIO_T),
                                    (f"SAZ{est}{w}", Z_T)):
                v = M[pfx]
                prev = I.shift(v, 1)
                for t in thresholds:
                    lab = f"{pfx}<{t:g}" if t else f"{pfx}<0"
                    S[lab] = v < t
                    S[lab.replace("<", ">")] = v > t
                    S[f"{pfx} x-below {t:g}"] = (v < t) & (prev >= t)
                    S[f"{pfx} x-above {t:g}"] = (v > t) & (prev <= t)
    n = len(d["c"])
    for k in S:
        S[k] = np.nan_to_num(np.asarray(S[k], float), nan=0.0) > 0.5
        S[k][:max(300, ZLB + 40)] = False
    return S


PINE_PREFIX = {"SAM": "raw", "SAR": "ratio", "SAZ": "z-score"}


def pine_ok(name):
    """Only the bar-return estimator can be computed in Pine without lower-timeframe data.

    On a 5-minute chart, three years is ~214,000 bars; asking for the 1-minute bars inside each
    of them is over a million intrabars, and TradingView caps `request.security_lower_tf` at
    roughly 100,000. An intrabar-estimator rule is measurable here and not runnable there.
    """
    return name[3] == "b"


if __name__ == "__main__":
    from bos_choch import prep
    for tf in (5, 15, 30):
        d = prep(tf)
        S = conditions(d, tf)
        fire = np.array([v.mean() for v in S.values()])
        print(f"{tf:>3}m  {len(S):,} SAM conditions on {len(d['c']):,} bars   "
              f"hit rate min {fire.min():.4f}  median {np.median(fire):.4f}  max {fire.max():.4f}")
        print(f"      {sum(1 for k in S if pine_ok(k)):,} of them are Pine-computable "
              f"(bar-return estimator)")
