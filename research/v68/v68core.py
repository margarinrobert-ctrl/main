"""V68 -- the full quant workup on the V66/P3 cell.

THE CELL. Donchian 11-bar entry, 47-bar exit channel, 3.8xATR stop, 3.2xATR target, 96-bar hold
cap, entries 09:30-16:00 New York, NQ 15m, one position at a time. It clears a matched random entry
on the research block at p 0.030 (680 events, 353/yr) and its locked block was opened in
`STUDY_BAYESOPT_DONCHIAN`, so EVERY locked number in this study is a SECOND READ and descriptive.

THE RULES THIS BRANCH MAKES ME FOLLOW, restated because they are what the study is:
  * POPULATION SHAPE BEFORE THE TOP ROW. A grid that is 90% profitable makes its best cell the max
    of ~n draws, and `STUDY_V60` measured corr(research, locked) at -0.4426 -- when that is
    negative, selecting on research is WORSE than not selecting.
  * MARGINAL AVERAGE PER AXIS, never the top cell (`STUDY_V11`).
  * BOX EDGES. `STUDY_V64_OPTUNA` watched the optimum run to a new ceiling every time the box was
    widened -- a stop that cannot bind and a target never reached.
  * THE SURROGATE TEST (`STUDY_V30`): a random-row R^2 on a dense grid is interpolation. Hold out a
    whole AXIS VALUE.
  * DEFLATION with `var_trials` measured over the TRIAL SHARPES, per observation -- the error that
    printed 0.9919 once and 0.571 another time.
  * vectorbt is a TRANSCRIPTION CHECK FIRST. It has failed that check three times here; its
    `sl_stop` is a FRACTION OF PRICE, not an ATR multiple, and `td_stop` does not exist in 1.1.0.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61sess", "research/v66"):
    q = os.path.join(ROOT, p)
    if q not in sys.path:
        sys.path.insert(0, q)

import sess_core as SC        # noqa: E402

BASE = dict(ent=11, exN=47, stop=3.8, tp=3.2, hold=96, s_start=570, s_stop=960)


def load(tf=15):
    return SC.build(tf)


def run(D, ent=11, exN=47, stop=3.8, tp=3.2, hold=96, s_start=570, s_stop=960, block=None):
    """The cell, through sess_core's own walker with the CVD gate off."""
    g = np.ones(len(D["c"]), bool)
    t = SC.run(D, g=g, ent=int(ent), exN=int(exN), stop=float(stop), tp=float(tp),
               hold=int(hold), sess=True, s_start=int(s_start), s_stop=int(s_stop), flat=False)
    return t if block is None else t[t.blk == block]


def stats(t):
    if len(t) < 5:
        return dict(n=len(t), pct=np.nan, pf=np.nan, sharpe=np.nan, dd=np.nan, rdd=np.nan)
    x = t.pct.to_numpy()
    eq = np.cumsum(x)
    dd = float(np.max(np.maximum.accumulate(eq) - eq)) if len(eq) else np.nan
    sr = x.mean() / max(x.std(ddof=1), 1e-12)
    return dict(n=len(t), pct=float(x.mean()),
                pf=float(x[x > 0].sum() / max(-x[x < 0].sum(), 1e-9)),
                sharpe=float(sr), dd=dd, rdd=float(eq[-1] / max(dd, 1e-9)), total=float(eq[-1]))


def daily(t, D, block):
    """Zero-filled over EVERY trading day in the block -- `STUDY_V17`'s rule, so a filter is not
    paid for trading less."""
    days = np.unique(D["day"][D["blk"] == block])
    s = t[t.blk == block]
    g = s.groupby("day").pct.sum()
    return pd.Series(g.reindex(days).fillna(0.0).to_numpy(), index=days)


def control(D, n_target, seed, block=0, draws=200, **cfg):
    """Matched random entry: identical geometry, exits, costs and lock; signals forced through
    `ent_hi`; picks SORTED so the lock rejects the same way (`STUDY_V59`)."""
    c = dict(BASE); c.update(cfg)
    rng = np.random.default_rng(seed)
    n = len(D["c"])
    elig = np.flatnonzero((D["blk"] == block) & np.isfinite(D["atr"]) & (D["atr"] > 0)
                          & (D["mod"] >= c["s_start"]) & (D["mod"] < c["s_stop"]))
    xi = int(np.clip(c["exN"], 2, D["ex_lo"].shape[0] + 1)) - 2
    out = []
    for _ in range(draws):
        pick = np.sort(rng.choice(elig, min(n_target, len(elig)), replace=False))
        eh = np.full(n, 1e18)
        eh[pick] = -1e18
        sig, xb, pts, pct, R, why = SC._walk(
            D["o"], D["h"], D["l"], D["c"], D["atr"], D["mod"], eh, D["ex_lo"][xi],
            np.ones(n, bool), 1, float(c["stop"]), float(c["tp"]), int(c["hold"]),
            1, int(c["s_start"]), int(c["s_stop"]), 0,
            float(SC.COST), float(SC.SLIP), 1000, int(D["last_bar"]))
        b = D["blk"][sig] == block
        if b.sum() >= 10:
            out.append(pct[b].mean())
    return np.array(out)
