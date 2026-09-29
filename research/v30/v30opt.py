"""Bayesian optimisation over the Turtle parameter space, 07:00-11:00 New York, both sides.

THE SEARCH. Optuna's TPE sampler -- a Bayesian, model-based optimiser: it fits a density over the
parameters that produced good trials against one over the rest, and samples where their ratio is
highest. Eleven parameters, both sides, two markets, RESEARCH BLOCK ONLY. The locked block is
never seen by the optimiser and is read exactly once at the end.

WHY THE SEARCH IS NOT THE RESULT. A 110,250-configuration sweep on this branch bought +0.098 R out
of sample against the un-swept starting point's +0.097, and its in-sample-to-out-of-sample
expectancy correlation of +0.84 turned out not to be skill -- it survived within geometry cells
because the same markets rose in both blocks. So the deliverable here is not "the best trial". It
is four numbers that say whether optimising this space transfers at all:

  1. the SHARE of the trial population that is profitable, before any ranking
  2. the correlation between a trial's RESEARCH Sharpe and its LOCKED Sharpe
  3. whether a gradient-boosted surrogate trained on the research surface can PREDICT the locked
     surface -- XGBoost and LightGBM, both, since a model that cannot learn the map is direct
     evidence that the map does not exist
  4. a same-selectivity control on the winner

ROBUSTNESS IS SCORED AS A NEIGHBOURHOOD, NOT A POINT -- but not as a minimum. Taking the worst
cell in a neighbourhood is the obvious over-correction and it cost $18,970 on this branch
(STUDY_1R_PROCEDURE). The reported robust score is the MEAN of a trial and its perturbed twins.
"""
from __future__ import annotations

import sys
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v27")
sys.path.insert(0, "research/v30")
import indicators as I        # noqa: E402
import v30sim                 # noqa: E402

WIN_START, WIN_END = 7 * 60, 11 * 60          # 07:00 - 11:00 New York, flatten at 11:00


def load(market, tf=30):
    if market == "NQ":
        import fastbars
        b = fastbars.bars(tf)
        return dict(o=b["o"], h=b["h"], l=b["l"], c=b["c"], mod=b["mod"], sess=b["sess"])
    import v27run as R27
    d = pd.DataFrame(R27.load_us30())
    d["blk"] = np.arange(len(d)) // (tf // 15)
    g = d.groupby("blk")
    return dict(o=g.o.first().to_numpy(), h=g.h.max().to_numpy(), l=g.l.min().to_numpy(),
                c=g.c.last().to_numpy(), mod=g["mod"].first().to_numpy(),
                sess=g.sess.first().to_numpy())


def prep(b, p):
    h, l, c = b["h"], b["l"], b["c"]
    atr = I.rma(I.true_range(h, l, c), p["atr_len"])          # Wilder, as the Turtle defines it
    _pd, _md, adx = I.adx_di(h, l, c, 14)
    ema100 = I.ema(c, 100)
    ext = (c - ema100) / np.maximum(atr, 1e-12)
    ao = (I.sma((h + l) / 2, 5) - I.sma((h + l) / 2, 34)) / np.maximum(atr, 1e-12)
    return dict(atr=atr, adx=adx, ext=ext, ao=ao,
                ent_hi=I.shift(I.rmax(h, p["entry1"]), 1),
                ent_lo=I.shift(I.rmin(l, p["entry1"]), 1),
                ex_lo=I.shift(I.rmin(l, p["exit1"]), 1),
                ex_hi=I.shift(I.rmax(h, p["exit1"]), 1))


def score(b, p, side, block_mask, cost_pts):
    S = prep(b, p)
    R, eb = v30sim.run(b["o"], b["h"], b["l"], b["c"], b["mod"], b["sess"], S["atr"],
                       S["ent_hi"], S["ent_lo"], S["ex_lo"], S["ex_hi"], side,
                       p["atr_mult"], p["pyr_step"], p["max_units"], WIN_START, WIN_END,
                       S["adx"], p["adx_max"], S["ext"], p["ext_max"],
                       S["ao"], p["ao_min"], cost_pts, p["skip_win"])
    if len(R) == 0:
        return None
    keep = block_mask[eb]
    R, eb = R[keep], eb[keep]
    R = R[np.isfinite(R)]
    if len(R) < 25 or not (R < 0).any():
        return None
    days = b["sess"][eb[:len(R)]]
    allday = np.unique(b["sess"][(b["sess"] >= days.min()) & (b["sess"] <= days.max())])
    d = pd.Series(R).groupby(pd.Series(days)).sum().reindex(allday, fill_value=0.0).to_numpy()
    sh = float(d.mean() / d.std(ddof=1) * np.sqrt(252)) if d.std(ddof=1) > 0 else 0.0
    eq = np.cumsum(R)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    return dict(n=len(R), R=float(R.mean()), pf=float(R[R > 0].sum() / abs(R[R < 0].sum())),
                sharpe=sh, dd=dd, win=float((R > 0).mean()),
                retdd=float(R.sum() / dd) if dd > 0 else np.nan)
