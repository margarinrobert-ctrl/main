"""US30 15m: predict the MOVEMENT, and read the market's own INEFFICIENCY, not its price.

WHY THIS SHAPE. `STUDY_MR30` closed direction on this market as hard as it can be closed: with the
exposure held exactly fixed and a null that preserves each condition's own clustering, **1 of 60
declared timing cells cleared p<=0.05 where 3.0 are expected by chance**, and three primaries died
in three runs. But the same study found the one thing that DID replicate on all three US30 blocks
including a different-provider forward feed -- forward realised vol over trailing ATR running
3.0-3.7x in the calmest quintile against 1.7-1.9x in the busiest. That is a MOVEMENT fact.

`STUDY_V67` measured the split directly on NQ: over eight declared targets, range expansion scores
IC 0.602, realised vol 0.529, TIME-TO-TOUCH 0.437, MFE/MAE 0.343 -- against straightness 0.041 and
DIRECTION 0.060. How far and how fast is forecastable; which way is not. This asks whether that
holds on US30 and, crucially, whether it can be turned into a DECISION.

THE TRAP THAT KILLED THE LAST ATTEMPT, AND THE DESIGN THAT AVOIDS IT. V67 built a volatility
forecast reading **locked IC 0.7065** -- among the highest out-of-sample ICs on this branch -- put
it into the stop, and it bought ZERO, losing to its own SHUFFLED twin out of sample. The reason is
mechanical: an ATR stop ALREADY CONTAINS the volatility information, so a better estimate of the
same quantity has nothing left to add. **A movement forecast is only worth anything where it prices
a decision the ATR does not already price.** Two are declared here and neither has been tested:

  1. THE HOLD CAP. Every hold cap on this branch is a constant. Time-to-touch is the second most
     predictable target in V67's grid and it prices PATIENCE -- how long before this trade resolves
     -- which an ATR stop says nothing about.
  2. THE ANOMALY VETO. `STUDY_VWANOM` found the one thing that replicated across nine of ten
     feed x cell x block cells: an event on an UNUSUAL bar is a WORSE event, by autoencoder
     reconstruction error, Mahalanobis distance and isolation forest alike. It was never tested on
     US30 and never on a movement target.

INEFFICIENCY IS MEASURED, NOT ASSERTED. The declared family is the deviation-from-random-walk set --
Lo-MacKinlay variance ratios (VR > 1 trending, < 1 mean-reverting, = 1 efficient), rolling AR(1),
Roll's implied effective spread from the serial covariance of returns, and Amihud illiquidity. These
say how far this stretch of tape is from a martingale, which is the literal reading of the ask.

EVERY NULL IS THE HARD ONE. A permutation on OVERLAPPING targets must permute BLOCKS (`STUDY_V67`:
a free permutation put p95 at ~0.014 for every target regardless of persistence and 32 of 32 cells
cleared it, direction included). Anomaly models are fitted on the research block ONLY and never see
a label. Direction is carried as the control that must fail.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v67", "research/v22"):
    q = os.path.join(ROOT, p)
    if q not in sys.path:
        sys.path.append(q)
from mr30 import mr30core as M  # noqa: E402
from v67 import v67core as V67  # noqa: E402

HORIZONS = (4, 16, 48)                 # 1h, 4h, 12h on 15-minute bars
TARGETS = ("mag", "rv", "rng", "er", "mfe", "mae", "ttb", "dir")
VR_LAGS = (2, 4, 8, 16)
WINS = (48, 192, 768)                  # 12h, 2d, 8d


def frame(name="US30L"):
    f = M.load(name)
    return f


def D_of(f):
    return dict(o=f["open"].to_numpy(), h=f["high"].to_numpy(), l=f["low"].to_numpy(),
                c=f["close"].to_numpy(), atr=f["atr"].to_numpy())


# ---------------------------------------------------------------- the inefficiency family
def tod_baseline(f, col, min_obs=20):
    """Causal time-of-day mean -- required on a 24-hour tape (`STUDY_VWAP_STOCH_ATR`)."""
    v = f[col].to_numpy(); mod = f["mod"].to_numpy()
    out = np.full(len(v), np.nan)
    s = pd.Series(v)
    for m in np.unique(mod):
        idx = np.flatnonzero(mod == m)
        cs = s.iloc[idx].expanding().mean().shift(1).to_numpy()
        cs[np.arange(len(idx)) < min_obs] = np.nan
        out[idx] = cs
    return out


def inefficiency(f):
    """How far this stretch of tape is from a martingale. All causal, all shifted."""
    c = f["close"].to_numpy(); v = f["volume"].to_numpy()
    at = f["atr"].to_numpy(); hi = f["high"].to_numpy(); lo = f["low"].to_numpy()
    r = pd.Series(np.diff(np.log(np.maximum(c, 1e-12)), prepend=0.0))
    X = pd.DataFrame(index=f.index)
    for W in WINS:
        v1 = r.rolling(W).var(ddof=1)
        for q in VR_LAGS:
            rq = r.rolling(q).sum()
            X[f"ie.vr{q}_{W}"] = (rq.rolling(W).var(ddof=1) / (q * v1)).shift(1).to_numpy()
        # rolling AR(1) and Roll's implied spread from the SAME serial covariance
        cv = r.rolling(W).cov(r.shift(1))
        X[f"ie.ar1_{W}"] = (cv / v1).shift(1).to_numpy()
        X[f"ie.roll_{W}"] = (2.0 * np.sqrt(np.maximum(-cv, 0.0))).shift(1).to_numpy() * 1e4
        # Amihud illiquidity: |return| per unit of participation
        X[f"ie.amihud_{W}"] = (r.abs() / np.maximum(v, 1.0)).rolling(W).mean() \
            .shift(1).to_numpy() * 1e6
        # how persistent is the SIZE of the move (vol clustering) -- the other half of efficiency
        X[f"ie.absar1_{W}"] = (r.abs().rolling(W).corr(r.abs().shift(1))).shift(1).to_numpy()
    # bar-shape anomaly inputs, each against its own causal baseline
    vb = tod_baseline(f, "volume")
    X["ie.vlm_tod"] = v / np.where(vb > 0, vb, np.nan)
    rng = hi - lo
    f2 = f.assign(_rng=rng)
    rb = tod_baseline(f2, "_rng")
    X["ie.rng_tod"] = rng / np.where(rb > 0, rb, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        X["ie.eff_bar"] = np.abs(c - f["open"].to_numpy()) / np.maximum(rng, 1e-9)
        X["ie.move_per_vol"] = np.abs(r.to_numpy()) * 1e4 / np.maximum(
            v / np.where(vb > 0, vb, np.nan), 1e-9)
        X["ie.atr_tod"] = at / np.where(tod_baseline(f.assign(_a=at).rename(
            columns={"_a": "_a"}), "_a") > 0, tod_baseline(f.assign(_a=at), "_a"), np.nan)
    return X.shift(0)


def features(f):
    """71 causal volatility columns (`v22vol`) plus the declared inefficiency family."""
    from v22 import v22vol as VV
    o, h, l, c = (f[k].to_numpy() for k in ("open", "high", "low", "close"))
    base = VV.build(o, h, l, c)
    X = pd.DataFrame({f"vol.{k}": np.asarray(v, float) for k, v in base.items()}, index=f.index)
    return pd.concat([X, inefficiency(f)], axis=1)


# ---------------------------------------------------------------- nulls and statistics
def block_perm_p(x, y, n=400, block=None, seed=0):
    """Circular BLOCK permutation of the TARGET. `STUDY_V67`: a free permutation destroys the
    target's autocorrelation and makes the null far too easy -- 32 of 32 cells cleared it,
    direction included. Shifting in blocks keeps local structure and destroys only alignment."""
    rng = np.random.default_rng(seed)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 500:
        return np.nan, np.nan
    obs = abs(V67.ic(x, y))
    b = int(block or max(20, len(x) // 200))
    nb = len(y) // b
    ys = y[:nb * b].reshape(nb, b)
    xs = x[:nb * b]
    null = np.empty(n)
    for i in range(n):
        null[i] = abs(V67.ic(xs, np.roll(ys, int(rng.integers(1, nb)), axis=0).ravel()))
    return obs, float(np.mean(null >= obs))


def truncation_audit(f, cols, probes=12, seed=1):
    """Recompute every feature on history ENDING at bar i and require the value to match."""
    rng = np.random.default_rng(seed)
    full = features(f)
    idx = rng.integers(int(len(f) * 0.5), len(f) - 5, probes)
    bad = 0; tot = 0
    for i in sorted(set(int(v) for v in idx)):
        part = features(f.iloc[:i + 1])
        for cname in cols:
            a = full[cname].to_numpy()[i]
            b = part[cname].to_numpy()[-1]
            tot += 1
            if np.isfinite(a) != np.isfinite(b):
                bad += 1
            elif np.isfinite(a) and abs(a - b) > 1e-6 * max(1.0, abs(a)):
                bad += 1
    return bad, tot
