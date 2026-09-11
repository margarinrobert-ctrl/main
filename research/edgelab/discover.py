"""Setup discovery: conditional probability with a time-matched control in front (brief 27, 28, 30, 31).

WHY A CONTROL AND NOT A POPULATION MEAN. P(+1R before -1R | condition) is not interpretable on
its own, because the base rate is not 50% and is not even constant: it varies with minute of day
by 15 percentage points across this window (see `analysis.time_map`). A condition that fires
mostly at 10:30 inherits 10:30's base rate and looks predictive when it is only punctual. So
every condition is scored against RANDOM entries drawn with the SAME minute-of-day distribution,
same side, same geometry, same block. `excess` is the condition's win rate minus that control's.

CALENDAR CONDITIONS ARE BANNED (CLAUDE.md). Weekday and month partition the sample and hand the
search a free lottery; on this branch removing them was worth $8,771 on a holdout. Time-of-day is
NOT calendar in that sense -- it is the brief's subject, section 8 -- and it is handled by the
control rather than by exclusion.

THE SEARCH IS ON DISCOVERY ONLY. Validation is read after freezing; production once, at the end.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import labels
from .analysis import eligible

BANNED = ("mod", "bucket15", "bucket30", "min_since_0700", "min_until_1100")


def conditions(F, names=None, qs=(0.2, 0.4, 0.6, 0.8)):
    """Binary conditions from feature quantiles, computed on the SUPPLIED rows only.

    Thresholds come from the discovery block; they are then applied unchanged everywhere else,
    which is what makes validation and production honest.
    """
    out = {}
    for name, arr in F.items():
        if name in BANNED:
            continue
        a = np.asarray(arr, float)
        fin = np.isfinite(a)
        if fin.sum() < 500:
            continue
        u = np.unique(a[fin])
        if len(u) <= 3:                       # already binary/ternary: use it directly
            for val in u:
                if 0.02 < float((a[fin] == val).mean()) < 0.98:
                    out[f"{name}=={val:g}"] = (a == val) & fin
            continue
        for q in qs:
            t = float(np.quantile(a[fin], q))
            out[f"{name}>{t:.4g}"] = (a > t) & fin
            out[f"{name}<{t:.4g}"] = (a < t) & fin
    return out


def control(d, trig, stop_k, rr, max_hold, block, draws=200, seed=11, costs=None):
    """Random longs matched on minute of day. Returns (win% draws, E[R] draws)."""
    mod = np.asarray(d["mod"], int)
    pool = {}
    base = np.flatnonzero(block & np.isfinite(d["atr"]) & (d["atr"] > 0))
    base = base[base > 300]
    for i in base:
        pool.setdefault(int(mod[i]), []).append(i)
    want = {}
    for i in trig:
        want[int(mod[i])] = want.get(int(mod[i]), 0) + 1
    rng = np.random.default_rng(seed); W = []; E = []
    for _ in range(draws):
        pick = [rng.choice(pool[m], size=min(k, len(pool[m])), replace=False)
                for m, k in want.items() if pool.get(m)]
        if not pick:
            continue
        idx = np.sort(np.concatenate(pick))
        r = labels.label(d, idx, stop_k * d["atr"][idx], rr=rr, max_hold=max_hold, costs=costs)
        if len(r["R"]) >= 20:
            W.append(100.0 * float((r["R"] > 0).mean())); E.append(float(r["R"].mean()))
    return np.array(W), np.array(E)


def score(d, mask, block, stop_k=1.0, rr=1.0, max_hold=16, min_n=60, draws=200, costs=None):
    """Evaluate one condition mask on one block against its matched control."""
    idx = eligible(d, block & mask)
    if len(idx) < min_n:
        return None
    r = labels.label(d, idx, stop_k * d["atr"][idx], rr=rr, max_hold=max_hold, costs=costs)
    R = r["R"]
    if len(R) < min_n:
        return None
    W, E = control(d, idx, stop_k, rr, max_hold, block, draws=draws, costs=costs)
    if len(W) == 0:
        return None
    win = 100.0 * float((R > 0).mean())
    return dict(n=len(R), win=win, expR=float(R.mean()),
                pf=float(R[R > 0].sum() / -R[R <= 0].sum()) if (R <= 0).any() else np.inf,
                ctrl_win=float(W.mean()), ctrl_expR=float(E.mean()),
                excess=win - float(W.mean()), excess_R=float(R.mean()) - float(E.mean()),
                p_win=float((W >= win).mean()), p_R=float((E >= R.mean()).mean()),
                ambig=100.0 * float(r["ambig"].mean()), mfe=float(r["mfe"].mean()),
                mae=float(r["mae"].mean()), held=float(np.median(r["held"])))


def sweep(d, conds, block, stop_k=1.0, rr=1.0, max_hold=16, min_n=60, draws=60, costs=None,
          progress=None):
    """Score every condition on the block. `draws` is kept low here; survivors are re-scored."""
    rows = []
    for i, (name, m) in enumerate(conds.items()):
        s = score(d, m, block, stop_k, rr, max_hold, min_n, draws, costs)
        if s:
            s["cond"] = name
            rows.append(s)
        if progress and (i + 1) % progress == 0:
            print(f"    {i+1}/{len(conds)} conditions", flush=True)
    df = pd.DataFrame(rows)
    return df.sort_values("excess", ascending=False).reset_index(drop=True) if len(df) else df


def robust_edge_score(df):
    """Brief 31: rank by robustness, not by profit. Sample size, excess, PF and stability."""
    if not len(df):
        return df
    z = lambda s: (s - s.mean()) / (s.std() + 1e-9)
    out = df.copy()
    out["res"] = (1.2 * z(out["excess"]) + 1.0 * z(out["excess_R"])
                  + 0.6 * z(np.log(out["n"])) - 0.8 * z(out["ambig"]))
    return out.sort_values("res", ascending=False).reset_index(drop=True)
