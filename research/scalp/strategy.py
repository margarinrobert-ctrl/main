"""The trend-following intraday scalp: a breakout taken only when the tape can trend.

CONSTRUCTION, and the reasoning for each piece.

  entry      an N-bar high breakout -- the Turtle trigger, kept because the brief is explicitly
             trend-following. Mean-reversion entries scored better on this data and are excluded
             by instruction, not by measurement.
  direction  +DI over -DI, so the long is taken only in an established uptrend.
  regime     ADX above a percentile AND the Kaufman efficiency ratio above a percentile. Both are
             computed on trailing windows, both oriented so higher = more trending. This is the
             chop filter: a channel breakout's characteristic failure is the false break in a
             range, and `scalp/regime.py` exists to exclude exactly that.
  geometry   ATR-sized stop with a fixed R target and a hard max hold, plus a session flatten --
             this is what converts the multi-day Turtle into a scalp.

THRESHOLDS ARE PERCENTILES OF THE RESEARCH BLOCK, never of the whole sample, and they are frozen
before any out-of-sample block is read.
"""
from __future__ import annotations

import numpy as np

from edgelab import feeds
from scalp import core, regime


def thresholds(d, block, q_adx=0.70, q_eff=0.55, eff_key="eff_ratio_50"):
    Rg = regime.build(d)
    out = {}
    for key, q in ((("adx"), q_adx), ((eff_key), q_eff)):
        a = np.asarray(Rg[key], float)
        fin = np.isfinite(a) & np.asarray(block, bool)
        out[key] = float(np.quantile(a[fin], q))
    return out, Rg


def mask(d, lo, hi, entry_n=20, thr=None, Rg=None, use_adx=True, use_eff=True,
         use_dir=True, eff_key="eff_ratio_50"):
    """The frozen trigger mask. `thr` must come from the research block only."""
    if Rg is None:
        Rg = regime.build(d)
    m = core.breakout(d, entry_n) & core.window(d, lo, hi)
    if use_dir:
        m = m & (np.asarray(Rg["di_spread"], float) > 0)
    if use_adx and thr is not None:
        a = np.asarray(Rg["adx"], float)
        m = m & np.isfinite(a) & (a > thr["adx"])
    if use_eff and thr is not None:
        e = np.asarray(Rg[eff_key], float)
        m = m & np.isfinite(e) & (e > thr[eff_key])
    return m


def build(inst, tf, lo, hi, entry_n=20, q_adx=0.70, q_eff=0.55, eff_key="eff_ratio_50",
          use_adx=True, use_eff=True, use_dir=True):
    d = feeds.bars(inst, tf)
    B = core.blocks(inst, d)
    thr, Rg = thresholds(d, B["research"], q_adx, q_eff, eff_key)
    m = mask(d, lo, hi, entry_n, thr, Rg, use_adx, use_eff, use_dir, eff_key)
    return d, B, m, thr
