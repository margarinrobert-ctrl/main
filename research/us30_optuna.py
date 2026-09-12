"""US30 gap fill, fifth step: an Optuna search with an objective built NOT to overfit.

Optuna (TPE) is only as honest as its objective. Maximising research-block profit would hand it
the same lottery every grid search here has failed. So:

    space       gap threshold 0.3..1.5 ATR; stop 0.5..1.5 gap; target 0.5..1.25 gap; flat 11:00
                / 12:00 / 13:00 / 14:00; the outside-prior-range filter on/off; minimum gap in
                points 0..75; sides both / long only
    objective   the RESEARCH block split into 5 contiguous session folds; per fold the net per
                trade; objective = mean over folds - 1 x std over folds (consistency-penalised),
                and -1e3 if any fold has fewer than 12 trades or the total is under 60.
                No fold, no trade, no bar from the locked block is touched.
    budget      fixed at 300 trials before starting, seed 7; the trial count is added to the
                multiplicity for the deflated Sharpe
    after       the best trial is scored on research against the matched control, its
                neighbourhood stability is measured (a plateau is required), and it is read on
                locked ONCE next to the shipped rule (gap 0.5 ATR, stop 0.75, target 1.0,
                flat 12:00, filter on, both sides, min gap 25).

    python3 research/us30_optuna.py
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import optuna

import us30_orb as U
import us30_orb2 as M2
import us30_mech as X
import us30_gap2 as G2
import us30_gap3 as G3
from us30_orb import load, sessions, split_days, metrics, fmt

optuna.logging.set_verbosity(optuna.logging.WARNING)
N_TRIALS = 300
SEED = 7
FOLDS = 5


def build(d, F, thr, stop, tgt, flat, use_filter, min_gap, sides):
    b = G2.gap_trades(d, F, thr=thr, stop=stop, tgt=tgt, flat=flat, entry="E1")
    if len(b) == 0:
        return b
    b = G3.conditions(d, F, b)
    m = b.gap.to_numpy() >= min_gap
    if use_filter:
        m &= (b.C2_inside_prior_range == False).to_numpy()
    if sides == "long":
        m &= (b.side == 1).to_numpy()
    return b[m].reset_index(drop=True)


def fold_objective(df, fold_edges):
    res = df[df.block == "research"]
    if len(res) < 60:
        return -1e3, []
    pers = []
    for lo, hi in fold_edges:
        f = res[(res.day >= lo) & (res.day < hi)]
        if len(f) < 12:
            return -1e3, []
        pers.append(f.net.mean())
    pers = np.array(pers)
    return float(pers.mean() - pers.std()), pers.tolist()


def main():
    d = load(); F = M2.session_facts(d)
    cut = split_days(d)
    rdays = np.array([dd for dd in sessions(d, 540) if dd < cut])
    edges = []
    for k in range(FOLDS):
        a = rdays[int(k * len(rdays) / FOLDS)]
        b = rdays[int((k + 1) * len(rdays) / FOLDS)] if k < FOLDS - 1 else cut
        edges.append((a, b))
    print(f"research sessions {len(rdays)}, {FOLDS} contiguous folds of ~{len(rdays) // FOLDS}; locked untouched")

    shipped = dict(thr=0.5, stop=0.75, tgt=1.0, flat=720, use_filter=True, min_gap=25.0, sides="both")
    df0 = build(d, F, **shipped)
    o0, p0 = fold_objective(df0, edges)
    print(f"shipped rule: objective {o0:.1f}  per-fold net/trade {np.round(p0, 1).tolist()}")

    def objective(trial):
        p = dict(thr=trial.suggest_float("thr", 0.3, 1.5), stop=trial.suggest_float("stop", 0.5, 1.5),
                 tgt=trial.suggest_float("tgt", 0.5, 1.25), flat=trial.suggest_categorical("flat", [660, 720, 780, 840]),
                 use_filter=trial.suggest_categorical("use_filter", [True, False]),
                 min_gap=trial.suggest_float("min_gap", 0.0, 75.0), sides=trial.suggest_categorical("sides", ["both", "long"]))
        df = build(d, F, **p)
        o, pers = fold_objective(df, edges)
        trial.set_user_attr("n", int((df.block == "research").sum()) if len(df) else 0)
        trial.set_user_attr("folds", pers)
        return o

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=SEED))
    study.enqueue_trial({k: (float(v) if isinstance(v, (int, float)) and k not in ("flat",) else v) for k, v in shipped.items()})
    study.optimize(objective, n_trials=N_TRIALS)
    tr = study.trials_dataframe()
    valid = tr[tr.value > -1e3]
    print(f"\n== OPTUNA: {N_TRIALS} trials, {len(valid)} with >= 60 research trades and >= 12 per fold ==")
    print(f"  objective (mean - std of per-fold net/trade): shipped {o0:.1f}; best {study.best_value:.1f}; "
          f"median over valid trials {valid.value.median():.1f}; 90th pct {valid.value.quantile(.9):.1f}")
    best = study.best_params
    print(f"  best params: {best}")
    print(f"  best trial per-fold: {np.round(study.best_trial.user_attrs['folds'], 1).tolist()}  n {study.best_trial.user_attrs['n']}")
    top = valid.sort_values("value", ascending=False).head(10)
    cols = [c for c in top.columns if c.startswith("params_")] + ["value", "user_attrs_n"]
    print("  top 10 trials:")
    print(top[cols].to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    print("  marginal view over valid trials (mean objective by categorical value):")
    for k in ("params_flat", "params_use_filter", "params_sides"):
        print(f"     {k[7:]:<10}" + "  ".join(f"{a}: {b:.1f}" for a, b in valid.groupby(k).value.mean().items()))
    print("  correlation of objective with each continuous parameter over valid trials:")
    for k in ("params_thr", "params_stop", "params_tgt", "params_min_gap"):
        print(f"     {k[7:]:<10} {np.corrcoef(valid[k], valid.value)[0, 1]:+.2f}")

    # neighbourhood of the best: perturb each continuous parameter +-15%, each categorical alternative
    dfb = build(d, F, **best)
    cb = X.control(d, dfb, best["flat"], draws=2000, block="research")
    print(f"\n== BEST TRIAL on research: {fmt(metrics(dfb[dfb.block == 'research']))}\n   control z {cb['z']:.2f} p {cb['p']:.3f}")
    nb = []
    for k in ("thr", "stop", "tgt", "min_gap"):
        for f in (0.85, 1.15):
            p = dict(best); p[k] = best[k] * f
            df = build(d, F, **p); o, _ = fold_objective(df, edges); nb.append(o)
    for k, alts in (("flat", [660, 720, 780, 840]), ("use_filter", [True, False]), ("sides", ["both", "long"])):
        for a in alts:
            if a == best[k]:
                continue
            p = dict(best); p[k] = a
            df = build(d, F, **p); o, _ = fold_objective(df, edges); nb.append(o)
    nb = np.array(nb); nb = nb[nb > -1e3]
    stab = float(np.median(nb) / study.best_value) if study.best_value > 0 and len(nb) else np.nan
    print(f"   neighbourhood: {len(nb)} perturbations, median objective {np.median(nb):.1f} -> stability {stab:.2f}")

    print("\n== LOCKED, read once: the Optuna pick next to the shipped rule ==")
    for nm, df, flat in (("shipped", df0, 720), ("optuna best", dfb, best["flat"])):
        loc = df[df.block == "locked"]; res = df[df.block == "research"]
        cl = X.control(d, df, flat, draws=2000, block="locked")
        w = loc.net[loc.net > 0].sum(); l = -loc.net[loc.net <= 0].sum()
        print(f"  {nm:<12} research {res.net.mean():6.1f}/trade (n {len(res)})  locked {loc.net.mean():6.1f}/trade (n {len(loc)})  "
              f"win {100 * (loc.net > 0).mean():.1f}%  PF {w / l if l > 0 else float('inf'):.2f}  maxDD {metrics(loc)['maxdd']:,.0f}  control z {cl['z']:.2f}  "
              f"long/short {loc.net[loc.side == 1].mean():.1f}/{(loc.net[loc.side == -1].mean() if (loc.side == -1).any() else float('nan')):.1f}")
    n_trials_total = 29461 + 96 + 6 + 11 + 8 + N_TRIALS
    res = dfb[dfb.block == "research"]
    sr = res.net.mean() / res.net.std()
    from scipy.stats import norm
    em = 0.5772156649; v = 0.05 ** 2
    sr0 = math.sqrt(v) * ((1 - em) * norm.ppf(1 - 1 / n_trials_total) + em * norm.ppf(1 - 1 / (n_trials_total * math.e)))
    g3 = ((res.net - res.net.mean()) ** 3).mean() / res.net.std() ** 3; g4 = ((res.net - res.net.mean()) ** 4).mean() / res.net.std() ** 4
    dsr = norm.cdf((sr - sr0) * math.sqrt(len(res) - 1) / math.sqrt(max(1 - g3 * sr + (g4 - 1) / 4 * sr * sr, 1e-9)))
    print(f"\n  deflated Sharpe of the Optuna pick, N = {n_trials_total:,} trials over everything on this file: {dsr:.3f}")
    return study


if __name__ == "__main__":
    main()
