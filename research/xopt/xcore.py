"""OPTIMISE THE EXCESS OVER A MATCHED CONTROL, NOT THE RETURN.

WHY THE OBJECTIVE CHANGES. `STUDY_XEDGE` (run_e2) showed the gold rule's best exit geometry earns
+0.566 R on the locked block while a RANDOM New York entry with the identical stop, target, trail,
costs and position lock earns +0.548 -- the geometry is harvesting a metal that quadrupled and the
entry adds +0.018. Every optimiser that maximises RETURN on such a family walks straight to the
widest stop and the longest hold, because that is the most drift exposure, and this branch has now
recorded five re-optimisers losing to their author's constants for exactly that reason.

So the objective here is EXCESS = (rule R) - (median R of a matched random entry with the SAME
geometry). A configuration can only score by beating a coin flip that is given every one of its own
advantages. Maximising this cannot buy drift, because drift is in both terms.

THE TRICK THAT MAKES IT AFFORDABLE. The matched control depends ONLY on the exit geometry -- side,
stop, target, trail, tighten, flatten, session -- and NOT on the entry conditions, because it
ignores the entry entirely. So the control is computed once per geometry and cached; sweeping the
ten entry parameters then costs one rule walk per trial. Without this the control is 200 walks a
trial and the study is unrunnable.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "research", "vwapema"))
sys.path.insert(0, os.path.join(ROOT, "research", "xanom"))
import vecore as V  # noqa: E402
import xdata as XD  # noqa: E402

RNG = np.random.default_rng(2024)
_CTL: dict = {}
_D: dict = {}


def data(sess="ny"):
    if sess not in _D:
        _D[sess] = V.build(sess=sess)
    return _D[sess]


def geom_key(side, stop, tgt, trail, tighten, flatten, sess):
    return (int(side), round(float(stop), 4), round(float(tgt), 4), bool(trail),
            bool(tighten), bool(flatten), sess)


def control(side, stop, tgt, trail, tighten, flatten, sess, blk, n_target, draws=160):
    """Median R of a random New York entry with this geometry. Cached per (geometry, block, rate).

    The rate is bucketed so nearby trade counts share a cache entry -- the control's dependence on
    n is weak and bucketing is what keeps the cache from degenerating into one entry per trial.
    """
    D = data(sess)
    sel = D["rth"] if blk is None else (D["rth"] & (D["blk"] == blk))
    idx = np.flatnonzero(sel)
    rate = min(1.0, n_target / max(len(idx), 1))
    bucket = round(rate, 4)
    key = geom_key(side, stop, tgt, trail, tighten, flatten, sess) + (blk, bucket)
    if key in _CTL:
        return _CTL[key]
    out = []
    for _ in range(draws):
        g = np.zeros(D["n"], bool)
        g[idx[RNG.random(len(idx)) < bucket]] = True
        c = V.run(D, g, side=side, tgt_R=tgt, atr_stop=stop, tighten=tighten, flatten=flatten,
                  trail=trail)
        if blk is not None:
            c = c[c.blk == blk]
        if len(c) >= 15:
            out.append(c.R.mean())
    v = (float(np.median(out)), float(np.percentile(out, 95)), len(out)) if out else (np.nan,) * 3
    _CTL[key] = v
    return v


def evaluate(cfg, blk=0, min_n=60, draws=160):
    """One configuration. Returns the rule's stats, the matched control and the excess."""
    sess = cfg.get("sess", "ny")
    D = data(sess)
    p = {**V.PARAMS, **{k: v for k, v in cfg.items() if k in V.PARAMS}}
    side = int(cfg.get("side", 1))
    sig, _ = V.triggers(D, side=side, p=p, use_vwap_vol=cfg.get("use_vol", True))
    t = V.run(D, sig, side=side, tgt_R=float(cfg.get("tgt_R", 3.0)),
              atr_stop=float(p["atr_stop"]), tighten=bool(cfg.get("tighten", True)),
              flatten=bool(cfg.get("flatten", False)), trail=bool(cfg.get("trail", True)), p=p)
    tb = t if blk is None else t[t.blk == blk]
    st = V.stats(tb)
    if st["n"] < min_n:
        return dict(n=st["n"], R=np.nan, excess=np.nan, ctl=np.nan, pf=np.nan, ok=False, trades=tb)
    cm, c95, _k = control(side, p["atr_stop"], float(cfg.get("tgt_R", 3.0)),
                          bool(cfg.get("trail", True)), bool(cfg.get("tighten", True)),
                          bool(cfg.get("flatten", False)), sess, blk, st["n"], draws=draws)
    return dict(n=st["n"], R=st["R"], pf=st["pf"], ctl=cm, ctl_p95=c95,
                excess=st["R"] - cm, ok=True, trades=tb,
                beat_p95=bool(st["R"] > c95))


SPACE = dict(
    ema_slow=(50, 400, 10), ema_pull=(10, 150, 2), ema_tight=(5, 60, 5), atr_len=(7, 30, 1),
    atr_stop=(0.15, 4.0), vol_mult=(0.0, 2.5), range_mult=(0.0, 1.6), wick_body=(0.75, 4.0),
    ambig=(0.0, 0.004), tighten_R=(0.5, 4.0), tgt_R=(1.0, 8.0))
