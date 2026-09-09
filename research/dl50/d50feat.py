"""The feature pool for the fixed-point barrier system. 42 causal columns in 7 declared families.

`geo.` IS THE FAMILY THAT MATTERS AND IT EXISTS BECAUSE OF THE GEOMETRY DRIFT. A fixed 50-point
stop is 4.23 ATR in 2016 and 1.10 ATR in 2025, so the SAME order is a wide swing stop early in the
sample and a tight scalp late. Those ratios are therefore not nuisance variables to be normalised
away -- they are the honest conditioning variables for this spec, and any model that helps by
learning them is telling you the barrier is mis-specified rather than that it has found an edge.
That distinction is checked directly by the family ablation.

The `math.` family is the six estimators from `research/mathmodels/mmcore.py`, each already
validated by recovering a known parameter from a simulated process and audited causal there.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dl50 import d50core as D  # noqa: E402
from mathmodels import mmcore as M  # noqa: E402


def tod_baseline(v, mod):
    """Mean of v at this minute-of-day over PRIOR sessions only. A trailing mean on a 24-hour tape
    is a clock, not a volatility reading -- STUDY_VWAP_STOCH_ATR measured an RTH bar clearing its
    own trailing ATR mean 98.9% of the time."""
    out = np.full(len(v), np.nan)
    acc = {}
    for i in range(len(v)):
        m = mod[i]
        s, n = acc.get(m, (0.0, 0))
        if n >= 20:
            out[i] = s / n
        if np.isfinite(v[i]):
            acc[m] = (s + v[i], n + 1)
    return out


def build(f, ent_ch=20, ema_len=200, state_w=500):
    o, h, l, c = (f[k].to_numpy() for k in ("open", "high", "low", "close"))
    at = f["atr"].to_numpy()
    mod = f["mod"].to_numpy()
    eh, el, ou, od, ema = D.signals(f, ent_ch, ema_len)
    X = pd.DataFrame(index=f.index)

    # ---- geo. the fixed barrier expressed in the units that actually move
    X["geo.stop_in_atr"] = D.STOP_PTS / at
    X["geo.stop_pct"] = 100.0 * D.STOP_PTS / c
    X["geo.atr_pct"] = 100.0 * at / c
    X["geo.tgt150_in_atr"] = 150.0 / at
    X["geo.chan_in_stop"] = (eh - el) / D.STOP_PTS

    # ---- vol.
    lr = np.r_[0.0, np.diff(np.log(c))]
    park = np.sqrt(np.maximum(np.log(h / l) ** 2 / (4 * np.log(2)), 0))
    X["vol.parkinson"] = park
    for n in (26, 96):
        X[f"vol.rv{n}"] = pd.Series(lr).rolling(n).std().to_numpy()
    X["vol.vov"] = pd.Series(X["vol.rv26"]).rolling(96).std().to_numpy()
    X["vol.atr_ratio96"] = at / pd.Series(at).rolling(96).mean().to_numpy()
    X["vol.atr_rank500"] = pd.Series(at).rolling(500, min_periods=100).rank(pct=True).to_numpy()
    X["vol.rng_atr"] = (h - l) / at
    X["vol.atr_tod"] = at / tod_baseline(at, mod)
    X["vol.rng_tod"] = (h - l) / tod_baseline(h - l, mod)

    # ---- trn.
    X["trn.d_ema200"] = (c - ema) / at
    X["trn.ema_slope"] = (ema - pd.Series(ema).shift(20).to_numpy()) / at
    X["trn.chan_w"] = (eh - el) / at
    X["trn.excess_up"] = (c - eh) / at
    X["trn.excess_dn"] = (el - c) / at
    X["trn.pos_in_chan"] = np.divide(c - el, np.where(eh - el > 0, eh - el, np.nan))
    for n in (50, 100):
        e = pd.Series(c).ewm(span=n, adjust=False).mean().to_numpy()
        X[f"trn.d_ema{n}"] = (c - e) / at

    # ---- mom.
    for n in (4, 26, 96):
        X[f"mom.roc{n}"] = pd.Series(c).pct_change(n).to_numpy() * 100
    d = np.r_[0.0, np.diff(c)]
    up = pd.Series(np.where(d > 0, d, 0.0)).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    dn = pd.Series(np.where(d < 0, -d, 0.0)).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    X["mom.rsi14"] = 100 - 100 / (1 + up / np.where(dn > 0, dn, np.nan))
    X["mom.consec"] = pd.Series(np.sign(d)).rolling(10).sum().to_numpy()

    # ---- str.
    X["str.bar_pos"] = np.divide(c - l, np.where(h - l > 0, h - l, np.nan))
    X["str.body"] = np.abs(c - o) / np.where(h - l > 0, h - l, np.nan)
    X["str.gap"] = (o - np.r_[np.nan, c[:-1]]) / at
    X["str.uwick"] = (h - np.maximum(o, c)) / np.where(h - l > 0, h - l, np.nan)

    # ---- tod.
    X["tod.min"] = mod
    X["tod.sin"] = np.sin(2 * np.pi * mod / 1440.0)
    X["tod.cos"] = np.cos(2 * np.pi * mod / 1440.0)

    # ---- math. the six validated estimators
    S = M.states(f, state_w)
    for cn in S.columns:
        X["math." + cn] = S[cn].to_numpy()
    return X


def audit(f, probes, cols, ent_ch=20, ema_len=200, state_w=500):
    """Rebuild every column from history ENDING at the bar and require an exact match."""
    full = build(f, ent_ch, ema_len, state_w)
    bad = {c: 0 for c in cols}
    for i in probes:
        sub = build(f.iloc[: i + 1], ent_ch, ema_len, state_w)
        for c in cols:
            a, b = full[c].to_numpy()[i], sub[c].to_numpy()[-1]
            if not (np.isnan(a) and np.isnan(b)) and abs(np.nan_to_num(a) - np.nan_to_num(b)) > 1e-8:
                bad[c] += 1
    return full, bad
