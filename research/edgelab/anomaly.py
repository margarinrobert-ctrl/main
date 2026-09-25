"""Anomaly detection and anomaly->edge analysis (brief sections 14 and 15).

THE RULE THE BRIEF INSISTS ON, and it is the right one: anomalies are NOT deleted. In a price
series the unusual observations are candidates for where the edge lives, so each is CLASSIFIED --

    NORMAL     within the trailing bulk of its own distribution
    UNUSUAL    beyond the moderate threshold
    EXTREME    beyond the far threshold

-- and then each class is measured separately. Deleting them would be discarding the hypothesis.

CAUSALITY. Every threshold is computed from a TRAILING window, so a bar is judged against the
history that preceded it and never against the full sample. A full-sample z-score would label a
2020 bar using 2024 volatility, which is both a leak and a different question.

METHODS. Robust z (median/MAD) and rolling percentile are the defaults because a plain z-score is
computed from a mean and standard deviation that the outlier itself dominates. Isolation Forest
and LOF are provided for the multivariate case (brief 14) but are fitted per fold on training rows
only, never on the whole series.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

NORMAL, UNUSUAL, EXTREME = 0, 1, 2


def robust_z(x, window=500, min_periods=100):
    """(x - trailing median) / (1.4826 * trailing MAD). Causal, outlier-resistant."""
    s = pd.Series(np.asarray(x, float))
    med = s.rolling(window, min_periods=min_periods).median()
    mad = (s - med).abs().rolling(window, min_periods=min_periods).median()
    return ((s - med) / (1.4826 * mad.replace(0, np.nan))).to_numpy()


def plain_z(x, window=500, min_periods=100):
    s = pd.Series(np.asarray(x, float))
    m = s.rolling(window, min_periods=min_periods).mean()
    sd = s.rolling(window, min_periods=min_periods).std()
    return ((s - m) / sd.replace(0, np.nan)).to_numpy()


def iqr_flag(x, window=500, min_periods=100, k=1.5):
    s = pd.Series(np.asarray(x, float))
    q1 = s.rolling(window, min_periods=min_periods).quantile(0.25)
    q3 = s.rolling(window, min_periods=min_periods).quantile(0.75)
    iqr = q3 - q1
    return ((s < q1 - k * iqr) | (s > q3 + k * iqr)).to_numpy()


def classify(x, window=500, unusual=2.5, extreme=4.0, signed=True):
    """Label each bar NORMAL / UNUSUAL / EXTREME by trailing robust z."""
    z = robust_z(x, window)
    a = np.abs(z) if not signed else z
    lab = np.full(len(z), NORMAL, np.int8)
    lab[np.abs(a) >= unusual] = UNUSUAL
    lab[np.abs(a) >= extreme] = EXTREME
    lab[~np.isfinite(z)] = NORMAL
    return lab, z


FAMILIES = {
    "bar return": lambda F, d: F["logret"],
    "candle range": lambda F, d: F["range_atr"],
    "body": lambda F, d: F["body_atr"],
    "tick activity": lambda F, d: F["tick_rel_20"],
    "volatility": lambda F, d: F["rvol_20"],
    "momentum": lambda F, d: F["roc5_atr"],
    "gap": lambda F, d: F["gap_atr"],
    "upper wick": lambda F, d: F["upwick_atr"],
    "lower wick": lambda F, d: F["lowick_atr"],
}


def build(F, d, window=500, unusual=2.5, extreme=4.0):
    """Classify every family; return {name: (label array, signed z)}."""
    out = {}
    for name, fn in FAMILIES.items():
        x = np.asarray(fn(F, d), float)
        out[name] = classify(x, window, unusual, extreme)
    return out


def edge_table(d, anoms, block, stop_k=1.5, rr=1.0, max_hold=16, min_n=40, draws=80):
    """Brief 15: for each family and class, measure the long outcome against a matched control.

    Split by SIGN, because 'an unusually large bearish candle' and 'an unusually large bullish
    candle' are different hypotheses and the brief names the first one specifically.
    """
    from .discover import score
    rows = []
    for name, (lab, z) in anoms.items():
        for cls, tag in ((UNUSUAL, "unusual"), (EXTREME, "extreme")):
            for sgn, stag in ((-1, "down"), (1, "up")):
                m = (lab == cls) & (np.sign(np.nan_to_num(z)) == sgn)
                if m.sum() < min_n:
                    continue
                s = score(d, m, block, stop_k, rr, max_hold, min_n=min_n, draws=draws)
                if s:
                    s.update(family=name, klass=tag, direction=stag)
                    rows.append(s)
    df = pd.DataFrame(rows)
    if not len(df):
        return df
    cols = ["family", "klass", "direction", "n", "win", "ctrl_win", "excess",
            "expR", "excess_R", "p_win", "ambig", "mfe", "mae"]
    return df[cols].sort_values("excess", ascending=False).reset_index(drop=True)
