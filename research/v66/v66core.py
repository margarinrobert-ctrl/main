"""V66 -- deep learning on the meta layer, with the PIN mixture demoted to a FEATURE FAMILY.

WHY THIS SHAPE. `STUDY_PIN_BAYES` killed the PIN posterior as a PRIMARY: it fails Gate 1 on both
constructions and the number it produces is a dispersion reading (the placebo returns the same PIN
on information-free data at the same var/mean). `STUDY_EMA48_VWAP_DL` and `STUDY_VWANOM` both
recorded that a meta layer cannot rescue a Gate-1 failure -- a filter makes a dead base less bad,
never alive. So the deep learning goes on a primary that PASSES Gate 1, and the PIN machinery goes
where the mechanism-first architecture says objects like it belong: the meta layer, where it can
score events and can never create one.

That is also the sharpest available test of the paper. If PIN is only a dispersion statistic, a
model given the PIN family should do no better than one without it -- and the FAMILY ABLATION is
the measurement, not an opinion.

THE EVENT-COUNT CONSTRAINT IS THE REASON THE PRIMARY IS RE-CHOSEN. `STUDY_V61_FEATURES_15M` built
the strongest meta layer on this branch on the V61 CVD rule and its own conclusion was that 125
locked events cannot separate a +0.05 %/event uplift from noise, and that the fix is MORE EVENTS.
So candidate primaries are declared here, Gate 1 is run on all of them on RESEARCH ONLY, and the
one that is both eligible and has the most events is the one that gets the features.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61sess", "research/pin", "research/scalp5"):
    q = os.path.join(ROOT, p)
    if q not in sys.path:
        sys.path.insert(0, q)

import sess_core as SC        # noqa: E402

# Declared before any scoring. Each is a complete primary; none is tuned here.
CANDIDATES = {
    "P1 cvd15 gated": dict(tf=15, ent=20, exN=20, stop=2.0, tp=0.0, hold=480, gated=True),
    "P2 cvd15 ungated": dict(tf=15, ent=20, exN=20, stop=2.0, tp=0.0, hold=480, gated=False),
    "P3 bayesopt rth": dict(tf=15, ent=11, exN=47, stop=3.8, tp=3.2, hold=96, gated=False,
                            sess=True, s_start=570, s_stop=960),
    "P4 don30 ungated": dict(tf=30, ent=30, exN=20, stop=2.0, tp=0.0, hold=480, gated=False),
}


def load(tf):
    return SC.build(tf)


def primary(D, cfg):
    """The event stream. `gated` switches the V61 CVD exhausted-sellers gate on or off."""
    c = dict(cfg)
    c.pop("tf", None)
    gated = c.pop("gated", True)
    g = None
    if not gated:
        g = np.ones(len(D["c"]), bool)
    return SC.run(D, g=g, **c)


def control(D, cfg, n_target, seed, block=0, draws=200):
    """A matched random entry: identical geometry, exits, costs and position lock, entering at
    random ELIGIBLE bars instead of at breakouts.

    The break test inside the walker is `h[i] >= ent_hi[i]`, so forcing a signal is a matter of
    handing it an `ent_hi` of -1e18 at the chosen bars and +1e18 everywhere else. Everything
    downstream -- the channel exit, the ATR stop, the lock -- is untouched.

    The picks are SORTED before the walk. `STUDY_V59` recorded what happens otherwise: unsorted
    bars make the position lock reject an arbitrary share and the null's spread explodes.
    """
    rng = np.random.default_rng(seed)
    c = dict(cfg)
    c.pop("tf", None)
    c.pop("gated", None)
    n = len(D["c"])
    elig = np.flatnonzero((D["blk"] == block) & np.isfinite(D["atr"]) & (D["atr"] > 0))
    if c.get("sess"):
        mo = D["mod"][elig]
        elig = elig[(mo >= c["s_start"]) & (mo < c["s_stop"])]
    ei = int(np.clip(c["ent"], 2, D["ent_hi"].shape[0] + 1)) - 2
    xi = int(np.clip(c["exN"], 2, D["ex_lo"].shape[0] + 1)) - 2
    out = []
    for _ in range(draws):
        pick = np.sort(rng.choice(elig, min(n_target, len(elig)), replace=False))
        eh = np.full(n, 1e18)
        eh[pick] = -1e18
        sig, xb, pts, pct, R, why = SC._walk(
            D["o"], D["h"], D["l"], D["c"], D["atr"], D["mod"], eh, D["ex_lo"][xi],
            np.ones(n, bool), 1, float(c["stop"]), float(c["tp"]), int(c["hold"]),
            1 if c.get("sess") else 0, int(c.get("s_start", 0)), int(c.get("s_stop", 1440)),
            1 if c.get("flat") else 0, float(SC.COST), float(SC.SLIP), 1000, int(D["last_bar"]))
        b = D["blk"][sig] == block
        if b.sum() >= 10:
            out.append(pct[b].mean())
    return np.array(out)
