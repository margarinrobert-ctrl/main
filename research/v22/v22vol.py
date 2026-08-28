"""A volatility-state feature family, and the honest statement of what it cannot be.

THERE IS NO VIX ON DISK AND THERE NEVER HAS BEEN. `research/datasets.py` lists thirteen registered
feeds and not one is an implied-volatility series; the container has also recycled again, so only
NQ 1-minute and 5-minute survive. Nothing here is a VIX proxy pretending to be VIX.

WHAT A REALISED FAMILY CAN AND CANNOT SUBSTITUTE FOR. Most of what a regime study uses VIX for is
the VOLATILITY STATE and its TERM STRUCTURE -- is volatility high against its own history, and is
the short horizon above or below the long one. Both are constructible from price alone and are built
below. What is NOT constructible is the VOLATILITY RISK PREMIUM -- implied minus realised -- which is
the one genuinely option-only signal and the part of VIX that carries information price does not
already contain. If that is what is wanted, an option-implied series has to be supplied; everything
else VIX is used for has a realised analogue and those analogues are what is tested here.

THE ESTIMATORS. Five variance estimators, because they disagree in an informative way:
  close-to-close  uses only closes; blind to intrabar travel
  Parkinson       uses the high-low range; ignores the open-close drift
  Garman-Klass    combines range and drift; the most efficient of the classical three
  Rogers-Satchell drift-independent, so it does not inflate in a trending market
  semivariance    downside and upside separately, and their ratio

THE ONE THAT MATTERS MOST FOR CHOP. `Parkinson / close-to-close` is a direct, mechanical chop
detector: if the intrabar range is large relative to how far the close actually travelled, price is
oscillating inside its bars. Rogers-Satchell over close-to-close says the same thing from the other
side, because RS is built to be immune to drift.

EVERY FEATURE IS CAUSAL. Each reads bars up to and including t and never past it.
"""
from __future__ import annotations

import sys
import warnings
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
import indicators as I       # noqa: E402

warnings.filterwarnings("ignore", message="no explicit representation of timezones")

HORIZONS = (5, 10, 20, 60, 120)
_EPS = 1e-12


def _roll(x, n, fn="mean"):
    s = pd.Series(x)
    return getattr(s.rolling(n), fn)().to_numpy()


def estimators(o, h, l, c, n):
    """Five variance estimators over an n-bar window, all annualisation-free (per-bar sigma)."""
    lr = np.r_[np.nan, np.diff(np.log(np.maximum(c, _EPS)))]
    cc = _roll(lr ** 2, n) ** 0.5                                   # close-to-close
    hl = np.log(np.maximum(h, _EPS) / np.maximum(l, _EPS))
    park = (_roll(hl ** 2, n) / (4.0 * np.log(2.0))) ** 0.5         # Parkinson
    co = np.log(np.maximum(c, _EPS) / np.maximum(o, _EPS))
    gk = (_roll(0.5 * hl ** 2 - (2 * np.log(2) - 1) * co ** 2, n)).clip(min=0) ** 0.5
    ho = np.log(np.maximum(h, _EPS) / np.maximum(o, _EPS))
    lo = np.log(np.maximum(l, _EPS) / np.maximum(o, _EPS))
    rs = (_roll(ho * (ho - co) + lo * (lo - co), n)).clip(min=0) ** 0.5   # Rogers-Satchell
    dn = np.where(lr < 0, lr, 0.0)
    up = np.where(lr > 0, lr, 0.0)
    semid = _roll(dn ** 2, n) ** 0.5
    semiu = _roll(up ** 2, n) ** 0.5
    return dict(cc=cc, park=park, gk=gk, rs=rs, semid=semid, semiu=semiu)


def build(o, h, l, c):
    """The whole family. Keys are the feature names used everywhere downstream."""
    f = {}
    E = {n: estimators(o, h, l, c, n) for n in HORIZONS}

    # ---- 1. LEVEL: each estimator at each horizon, in its own units
    for n in HORIZONS:
        for k, v in E[n].items():
            f[f"{k}{n}"] = v

    # ---- 2. THE CHOP RATIOS -- range-based over return-based. High = oscillating inside bars.
    for n in HORIZONS:
        f[f"park_cc{n}"] = E[n]["park"] / np.maximum(E[n]["cc"], _EPS)
        f[f"rs_cc{n}"] = E[n]["rs"] / np.maximum(E[n]["cc"], _EPS)
        f[f"gk_cc{n}"] = E[n]["gk"] / np.maximum(E[n]["cc"], _EPS)

    # ---- 3. TERM STRUCTURE -- the realised analogue of VIX over VIX3M. Above 1 = short-dated
    # volatility bid over long-dated, which on the implied curve is the stress state.
    for a, b in ((5, 20), (5, 60), (10, 60), (20, 120), (10, 120)):
        f[f"ts_cc_{a}_{b}"] = E[a]["cc"] / np.maximum(E[b]["cc"], _EPS)
        f[f"ts_park_{a}_{b}"] = E[a]["park"] / np.maximum(E[b]["park"], _EPS)

    # ---- 4. STATE -- where volatility sits in its OWN history. The percentile is the "VIX at the
    # 90th percentile" reading, and it is scale-free so it survives a regime change in absolute vol.
    for n in (20, 60):
        for w in (250, 500):
            s = pd.Series(E[n]["cc"])
            f[f"pct_cc{n}_{w}"] = s.rolling(w).apply(
                lambda x: float((x[:-1] <= x[-1]).mean()), raw=True).to_numpy()
            f[f"z_cc{n}_{w}"] = ((s - s.rolling(w).mean()) / s.rolling(w).std(ddof=0)).to_numpy()

    # ---- 5. VOL OF VOL and ACCELERATION
    for n in (20, 60):
        s = pd.Series(E[n]["cc"])
        f[f"vov{n}"] = (s.rolling(60).std(ddof=0) / np.maximum(s.rolling(60).mean(), _EPS)).to_numpy()
    f["accel"] = (E[5]["cc"] / np.maximum(E[20]["cc"], _EPS)) - \
                 (E[20]["cc"] / np.maximum(E[60]["cc"], _EPS))

    # ---- 6. SEMIVARIANCE ASYMMETRY -- downside over upside. A VIX rises on downside; this is the
    # part of that behaviour price can express.
    for n in HORIZONS:
        f[f"semi_ratio{n}"] = E[n]["semid"] / np.maximum(E[n]["semiu"], _EPS)
    return f


def forward_er(c, h):
    """THE LABEL. Efficiency ratio over the NEXT h bars: |net move| / sum |bar moves|.

    1.0 is a straight line -- price distributing directionally. Near 0 is pure chop. It is the
    thing a regime filter claims to forecast, it is defined before any feature is looked at, and it
    is deliberately NOT a P&L: a label made of returns would let a directional feature score as a
    regime forecaster.
    """
    c = np.asarray(c, float)
    n = len(c)
    step = np.abs(np.r_[0.0, np.diff(c)])
    tot = pd.Series(step).rolling(h).sum().shift(-h).to_numpy()
    net = np.abs(np.r_[c[h:], np.full(h, np.nan)] - c)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(tot > 0, net / tot, np.nan)


if __name__ == "__main__":
    sys.path.insert(0, "research")
    import fastbars
    for tf in (15, 30):
        b = fastbars.bars(tf)
        f = build(b["o"], b["h"], b["l"], b["c"])
        cov = {k: float(np.isfinite(v).mean()) for k, v in f.items()}
        print(f"{tf:>3}m  {len(f)} features   min coverage {min(cov.values()):.3f} "
              f"({min(cov, key=cov.get)})")
        for hh in (12, 24, 48):
            y = forward_er(b["c"], hh)
            print(f"       forward ER h={hh:<3} mean {np.nanmean(y):.3f}  "
                  f"p10 {np.nanpercentile(y,10):.3f}  p90 {np.nanpercentile(y,90):.3f}")
