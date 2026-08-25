"""Validation of a FROZEN rule (brief sections 32, 34, 35, 36, 46, 47, 49).

The distinction this module exists to enforce: discovery may search, validation may only measure.
Every function here takes a rule that has already been frozen -- conditions, thresholds, stop,
target, hold, window -- and reports what it does on data it did not choose. Nothing re-optimises.

STATUS LABELS (brief 46). A result is never reported as "an 80% win rate strategy". It carries one
of: INSUFFICIENT EVIDENCE, OVERFIT RISK, CANDIDATE, PROMISING, ROBUST. ROBUST requires positive
out-of-sample expectancy AND positive walk-forward aggregate AND a sample large enough to mean
something. It is deliberately hard to earn.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd

from . import labels, splits
from .analysis import eligible
from .discover import control


@dataclass
class Frozen:
    """A strategy, frozen. Nothing may modify these once validation begins (brief 49)."""
    name: str
    conds: tuple                      # condition strings, ANDed
    stop_atr: float
    rr: float
    max_hold: int
    win_lo: int
    win_hi: int
    flat_mod: int = 960
    notes: str = ""

    def describe(self):
        return (f"{self.name}\n"
                f"  entry     LONG when {' AND '.join(self.conds)}\n"
                f"  window    {self.win_lo//60:02d}:{self.win_lo%60:02d}-"
                f"{self.win_hi//60:02d}:{self.win_hi%60:02d} New York\n"
                f"  stop      {self.stop_atr}x ATR(14)\n"
                f"  target    {self.rr}R\n"
                f"  max hold  {self.max_hold} bars ({self.max_hold*15} minutes)\n"
                f"  flatten   {self.flat_mod//60:02d}:{self.flat_mod%60:02d}")


def mask_of(fz, C, d):
    mod = d["mod"]
    m = (mod >= fz.win_lo) & (mod < fz.win_hi)
    for c in fz.conds:
        m = m & C[c]
    return m


def evaluate(d, mask, fz, block, draws=300, costs=None):
    idx = eligible(d, block & mask, fz.win_lo, fz.win_hi)
    if len(idx) < 20:
        return None
    r = labels.label(d, idx, fz.stop_atr * d["atr"][idx], rr=fz.rr,
                     max_hold=fz.max_hold, flat_mod=fz.flat_mod, costs=costs)
    R = r["R"]
    if len(R) < 20:
        return None
    W, E = control(d, idx, fz.stop_atr, fz.rr, fz.max_hold, block, draws=draws, costs=costs)
    win = 100.0 * float((R > 0).mean())
    eq = np.cumsum(R)
    dd = float(np.max(np.maximum.accumulate(eq) - eq)) if len(eq) else 0.0
    return dict(n=len(R), win=win, expR=float(R.mean()),
                pf=float(R[R > 0].sum() / -R[R <= 0].sum()) if (R <= 0).any() else np.inf,
                totalR=float(R.sum()), maxdd_R=dd,
                ctrl_win=float(W.mean()) if len(W) else np.nan,
                excess=win - float(W.mean()) if len(W) else np.nan,
                excess_R=float(R.mean()) - float(E.mean()) if len(E) else np.nan,
                p_win=float((W >= win).mean()) if len(W) else np.nan,
                p_R=float((E >= R.mean()).mean()) if len(E) else np.nan,
                ambig=100.0 * float(r["ambig"].mean()), R=R)


def walk_forward(d, mask, fz, within, n_folds=6, costs=None):
    """Brief 32: rolling out-of-sample folds. Only the TEST halves are reported."""
    rows = []
    for f, tr, te in splits.walk_forward(d, n_folds=n_folds, max_hold=fz.max_hold, within=within):
        s = evaluate(d, mask, fz, te, draws=120, costs=costs)
        if s:
            ix = pd.DatetimeIndex(d["idx"])[te]
            rows.append(dict(fold=f, start=ix[0].date(), end=ix[-1].date(), n=s["n"],
                             win=s["win"], expR=s["expR"], pf=s["pf"],
                             ctrl_win=s["ctrl_win"], excess=s["excess"]))
    return pd.DataFrame(rows)


def monte_carlo(R, n=20000, seed=3, cost_jitter_R=0.02):
    """Brief 34: two different questions, which need two different resamplings.

    PERMUTING the realised trades answers "how bad could the PATH have been?" -- it reorders the
    same outcomes, so the endpoint is identical by construction and only the drawdown varies.
    Reporting an endpoint distribution from a permutation is meaningless; an earlier version of
    this function did exactly that and produced a 5th and 95th percentile 0.6R apart.

    BOOTSTRAPPING with replacement answers "how uncertain is the edge itself?" -- it is the one
    that can say whether the total could plausibly have been negative.

    A cost shock is applied per trade in both, because the cost model is an assumption.
    """
    R = np.asarray(R, float)
    if len(R) < 10:
        return None
    rng = np.random.default_rng(seed)
    m = len(R)
    # path risk: same trades, different order
    dds = np.empty(n)
    for i in range(n):
        eq = np.cumsum(rng.permutation(R) - rng.normal(0.0, cost_jitter_R, m))
        dds[i] = np.max(np.maximum.accumulate(eq) - eq)
    # edge uncertainty: resample with replacement
    boot = rng.choice(R, size=(n, m), replace=True) - rng.normal(0.0, cost_jitter_R, (n, m))
    ends = boot.sum(axis=1)
    means = boot.mean(axis=1)
    return dict(trades=m,
                median_dd_R=float(np.percentile(dds, 50)),
                p95_dd_R=float(np.percentile(dds, 95)),
                worst_dd_R=float(dds.max()),
                boot_mean_p05=float(np.percentile(means, 5)),
                boot_mean_p50=float(np.percentile(means, 50)),
                boot_mean_p95=float(np.percentile(means, 95)),
                boot_total_p05=float(np.percentile(ends, 5)),
                boot_total_p95=float(np.percentile(ends, 95)),
                p_edge_negative=float((means <= 0).mean()))


def parameter_surface(d, C, fz, block, stops=(1.0, 1.25, 1.5, 1.75, 2.0, 2.5),
                      rrs=(0.75, 1.0, 1.25, 1.5), costs=None):
    """Brief 35: is the chosen point a plateau or an isolated peak?"""
    rows = []
    for s in stops:
        for rr in rrs:
            f2 = Frozen(fz.name, fz.conds, s, rr, fz.max_hold, fz.win_lo, fz.win_hi, fz.flat_mod)
            r = evaluate(d, mask_of(f2, C, d), f2, block, draws=40, costs=costs)
            rows.append(dict(stop_atr=s, rr=rr, n=r["n"] if r else 0,
                             win=r["win"] if r else np.nan, expR=r["expR"] if r else np.nan))
    return pd.DataFrame(rows)


def status(insample, oos, wf, min_n=100):
    """Brief 46: the label a result is allowed to carry."""
    if oos is None or oos["n"] < min_n:
        return "INSUFFICIENT EVIDENCE"
    if insample and insample["expR"] > 0 and oos["expR"] <= 0:
        return "OVERFIT RISK"
    wf_ok = len(wf) >= 3 and float(wf["expR"].mean()) > 0 and float((wf["expR"] > 0).mean()) >= 0.6
    if oos["expR"] > 0 and wf_ok and oos["excess"] > 0:
        return "ROBUST"
    if oos["expR"] > 0:
        return "PROMISING"
    return "CANDIDATE" if oos["excess"] > 0 else "REJECTED"
