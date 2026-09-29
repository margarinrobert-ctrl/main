"""The long-only 200-EMA + ADX + pullback hypothesis, answered question by question.

PRIOR. This structure has been tested twice on this branch. `STUDY_TREND_BRIEF.md` found the
200 EMA + ADX + crossover framework does not survive, that the slope condition is REDUNDANT (an
identical trade list) and that ADX contributes NEGATIVELY. `STUDY_TREND_PULLBACK_2.md` then swept
5,723,136 combinations of 46 trend states x 36 pullbacks x 24 resumptions in the 07:00-11:00 New
York window: 127 rules beat a time-matched control on research and ZERO survived the holdout,
against 6.4 expected by chance. CLAUDE.md marks it do-not-re-run.

WHAT IS NEW, and the reason to run it once more. `research/us100.py` added a second instrument
with 71,074 30-minute bars before 2022-12-26 that nothing here has ever seen -- six years covering
the 2018 selloff, COVID and the 2022 bear market. The hypothesis has never been tested on a
different instrument in a different era, and every component here is measured on BOTH.

DATA NOT AVAILABLE. This repository holds NQ and US100 only. There is no ES, YM, RTY, CL, GC or
VIX file, so the multi-market comparison, the ES/NQ cross-market question and anything keyed on
implied volatility cannot be answered here and are reported as unanswerable rather than guessed.

Everything below is causal: a condition is read on the signal bar and the fill is the next bar's
open, the same convention as every other engine in this repository.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
import indicators as I
from test_suite import PV, COMM, EC, SE, sim_core

WIN_EARLY = (420, 660)     # 07:00-11:00 New York, as briefed
WIN_RTH = (570, 660)       # 09:30-11:00, which STUDY_TREND_PULLBACK found worth 4x per trade


def features(d):
    """Every normalised feature the brief asks for that this data can support."""
    o, h, l, c, v, atr = d["o"], d["h"], d["l"], d["c"], d["v"], d["atr"]
    F = {}
    e20, e50, e200 = I.ema(c, 20), I.ema(c, 50), I.ema(c, 200)
    F["e20"], F["e50"], F["e200"] = e20, e50, e200
    F["dist200"] = (c - e200) / np.maximum(atr, 1e-9)            # (Price - EMA200) / ATR
    F["slope200"] = (e200 - I.shift(e200, 5)) / np.maximum(atr, 1e-9)   # EMA200 slope / ATR
    F["sep"] = (e20 - e50) / np.maximum(atr, 1e-9)               # EMA separation / ATR
    adx, pdi, ndi = I.adx_di(h, l, c, 14)
    F["adx"], F["pdi"], F["ndi"] = adx, pdi, ndi
    F["di"] = pdi - ndi
    vw = I.session_vwap(h, l, c, v, d["sess"])
    F["vwapd"] = (c - vw) / np.maximum(atr, 1e-9)                # distance from VWAP / ATR
    F["rvol"] = v / np.maximum(I.sma(v, 20), 1e-9)               # relative volume
    F["atr_ratio"] = atr / np.maximum(I.sma(atr, 50), 1e-9)      # volatility regime
    _u, _m, _lo, bw = I.bollinger(c)
    F["bbw"] = bw / np.maximum(I.sma(bw, 50), 1e-9)
    F["mom"] = (c - I.shift(c, 10)) / np.maximum(atr, 1e-9)
    hh20 = I.rmax(h, 20)
    F["pull_atr"] = (I.shift(hh20) - c) / np.maximum(atr, 1e-9)  # pullback depth / ATR
    ll10 = I.rmin(l, 10)
    F["retr"] = (I.shift(hh20) - c) / np.maximum(I.shift(hh20) - I.shift(ll10), 1e-9)
    F["rng_pos"] = (c - l) / np.maximum(h - l, 1e-9)
    F["body"] = np.abs(c - o) / np.maximum(h - l, 1e-9)
    return F


def regime(F, d, adx_min=25.0, slope_min=0.0, use_200=True, use_adx=True,
           use_slope=True, anti_chop=None):
    """The briefed bullish regime, with every component switchable so each can be PRICED."""
    m = np.ones(len(d["c"]), bool)
    if use_200:
        m &= F["dist200"] > 0
    if use_slope:
        m &= F["slope200"] > slope_min
    if use_adx:
        m &= F["adx"] > adx_min
    if anti_chop == "bbw":
        m &= F["bbw"] > 1.0
    elif anti_chop == "sep":
        m &= F["sep"] > 0.25
    elif anti_chop == "atr":
        m &= F["atr_ratio"] > 1.0
    return m


PULLBACKS = {
    "below EMA20": lambda F, d: d["c"] < F["e20"],
    "below EMA50": lambda F, d: d["c"] < F["e50"],
    "below VWAP": lambda F, d: F["vwapd"] < 0,
    "retrace > 1 ATR": lambda F, d: F["pull_atr"] > 1.0,
    "retrace > 38% of impulse": lambda F, d: F["retr"] > 0.382,
    "higher low (3-bar)": lambda F, d: (d["l"] > I.shift(I.rmin(d["l"], 3), 3)) & (d["c"] < I.shift(d["c"])),
    "2 down closes": lambda F, d: (d["c"] < I.shift(d["c"])) & (I.shift(d["c"]) < I.shift(d["c"], 2)),
    "volume contraction": lambda F, d: (F["rvol"] < 0.9) & (d["c"] < I.shift(d["c"])),
}

TRIGGERS = {
    "break pullback high": lambda F, d: d["c"] > I.shift(I.rmax(d["h"], 3)),
    "momentum expansion": lambda F, d: ((d["h"] - d["l"]) > 1.2 * d["atr"]) & (F["rng_pos"] > 0.66),
    "volume expansion": lambda F, d: (F["rvol"] > 1.2) & (d["c"] > d["o"]),
    "reclaim VWAP": lambda F, d: (F["vwapd"] > 0) & (I.shift(F["vwapd"]) <= 0),
    "reclaim EMA20": lambda F, d: (d["c"] > F["e20"]) & (I.shift(d["c"]) <= I.shift(F["e20"])),
    "close > prior high": lambda F, d: d["c"] > I.shift(d["h"]),
}


def recent(mask, k=6):
    """Did this happen within the last k bars, inclusive of the previous bar?

    A pullback-continuation setup is a SEQUENCE: the pullback occurs, then the trigger fires. The
    first version of this module required both on the same bar, which is close to
    self-contradictory -- "close below EMA20" and "close above the 3-bar high" rarely co-occur --
    and produced 41 triggers in three years where the honest construction produces thousands.
    """
    m = np.asarray(mask, bool)
    out = np.zeros(len(m), bool)
    acc = np.zeros(len(m), np.int32)
    c = 0
    for i in range(len(m)):
        c = k if m[i] else max(c - 1, 0)
        acc[i] = c
    out[1:] = acc[:-1] > 0            # strictly BEFORE this bar, so the trigger bar is separate
    return out


def sim(d, trig, am=2.0, tp=1.0, flat=960):
    return sim_core(d["o"], d["h"], d["l"], d["c"], d["atr"], d["mod"].astype(np.int64),
                    np.asarray(trig, np.int64), np.int64(1), float(am), float(tp),
                    np.int64(flat), np.int64(0), PV, COMM, EC, SE)


def control(d, trig, am, tp, flat, block, draws=300, seed=7):
    """Random long entries matched on minute of day -- the null the brief's regime must beat."""
    mod = d["mod"].astype(int)
    elig = np.arange(300, len(d["c"]) - 1)
    by = {}
    for b in elig:
        by.setdefault(int(mod[b]), []).append(b)
    want = {}
    for b in trig:
        want[int(mod[b])] = want.get(int(mod[b]), 0) + 1
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(draws):
        pick = [rng.choice(by[m], size=min(n, len(by[m])), replace=False)
                for m, n in want.items() if m in by and by[m]]
        if not pick:
            continue
        p, e, _x, _w, _g = sim(d, np.sort(np.concatenate(pick)), am, tp, flat)
        k = block[e]
        if k.sum() >= 10:
            out.append(100.0 * float((p[k] > 0).mean()))
    return float(np.mean(out)) if out else np.nan
