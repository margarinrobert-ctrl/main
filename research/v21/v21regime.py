"""ADX and CHOP on the V20 base: do either, or both, add an edge -- and what does the top of a
profit-factor ranking actually mean?

THE TRAP IN THE QUESTION, STATED UP FRONT. Ranking a grid by profit factor selects for
RESTRICTIVENESS, not for edge. Any filter that keeps fewer trades raises the mean of what it keeps
by construction, and the top of a 110-cell sort is the maximum of 110 draws. So the top-20 table is
produced as asked, and it is produced WITH the three columns that make it readable:
  * the TRADE COUNT, because PF 3.0 on eleven trades is not a finding;
  * a p-value against a RANDOM FILTER OF THE SAME SELECTIVITY, which is the only null that a
    restrictive condition cannot beat by being restrictive;
  * the same cell read on the LOCKED block, which is where a ranking artefact goes to die.
The share of the grid that is profitable and the population median are printed BEFORE any ranking.

WHAT THIS BRANCH ALREADY KNOWS AND IS BEING RE-TESTED, NOT ASSUMED. `STUDY_V13` found ADX >= 25 as a
standalone trigger scoring p 0.994 and CHOP <= 50 scoring p 0.990 -- the two worst rows of an
18-signal battery -- while the two TOGETHER with an efficiency-ratio floor took a Donchian 30/20
breakout from PF 1.04 to 1.24. So the prior is: neither alone, possibly something together. The
point of re-running is that the base is different (V20 carries a linear-regression confirmation) and
the market set is wider.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v20")
import indicators as I       # noqa: E402
import v16core as C          # noqa: E402
import v20linreg as L        # noqa: E402

RNG = np.random.default_rng(20260828)
TF = 30
PICK = "C close>value"
ADX_GRID = [0, 10, 15, 18, 20, 22, 25, 28, 30, 35, 40]
CHOP_GRID = [100, 70, 65, 60, 55, 50, 45, 40, 35, 30]
_R: dict = {}


def chop(h, l, c, n=14):
    """Choppiness index: 100 * log10(sum(TR,n) / range(n)) / log10(n). LOW = trending."""
    tr = I.true_range(h, l, c)
    s = pd.Series(tr).rolling(n).sum().to_numpy()
    rng = (pd.Series(h).rolling(n).max().to_numpy()
           - pd.Series(l).rolling(n).min().to_numpy())
    with np.errstate(divide="ignore", invalid="ignore"):
        return 100.0 * np.log10(s / np.maximum(rng, 1e-9)) / np.log10(n)


def ctx(name, tf=TF):
    if (name, tf) in _R:
        return _R[(name, tf)]
    P = L.ctx(name, tf)
    P = dict(P)
    P["adx"] = I.adx_di(P["h"], P["l"], P["c"], 14)[0]
    P["chop"] = chop(P["h"], P["l"], P["c"], 14)
    _R[(name, tf)] = P
    return P


def mask(P, adx_min, chop_max, side=1):
    m = np.ones(len(P["c"]), bool)
    if adx_min > 0:
        m &= np.nan_to_num(P["adx"], nan=-1.0) >= adx_min
    if chop_max < 100:
        m &= np.nan_to_num(P["chop"], nan=999.0) <= chop_max
    return m


def run(P, adx_min, chop_max, block, side=1):
    sig_all = C.signals(P, side)
    keep = block[sig_all] & L.confirm(P, PICK, side)[sig_all] & mask(P, adx_min, chop_max)[sig_all]
    sig = sig_all[keep]
    O = C.outcomes(P, side, sig, stop_mult=L.SPEC["stop"], tp_r=L.SPEC["tp_r"])
    return O, C.take(O, np.ones(len(sig), bool))


def pooled(rows):
    """Trades from every market, in R, concatenated -- PF across markets in points is meaningless."""
    r = np.concatenate(rows) if rows else np.array([0.0])
    w, lo = r[r > 0], r[r < 0]
    pf = float(w.sum() / abs(lo.sum())) if len(lo) and lo.sum() != 0 else np.nan
    return r, pf


def selectivity_control(P, block, base_idx, base_O, k, draws=400, seed=7):
    """A random filter of the same selectivity, drawn from the UNFILTERED signal population.

    This is the null a restrictive condition cannot beat by being restrictive: if the ADX/CHOP cell
    keeps k of the base's n trades, draw k of the same n at random and see where the real k falls.
    """
    n = len(base_idx)
    if k < 8 or k >= n:
        return np.array([]), np.nan
    r = base_O["R"][base_idx]
    rng = np.random.default_rng(seed + k)
    out = np.empty(draws)
    for d in range(draws):
        pick = rng.choice(n, size=k, replace=False)
        x = r[pick]
        w, lo = x[x > 0], x[x < 0]
        out[d] = float(w.sum() / abs(lo.sum())) if len(lo) and lo.sum() != 0 else np.nan
    return out, np.nan
