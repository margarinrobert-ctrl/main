"""V42 -- the surrogate over the grid, with its own fit quality reported first.

WHY THE FIT QUALITY COMES FIRST. `STUDY_V30_BAYES_OPT` fitted a surrogate to this branch's search
space and it explained the research block at 0.96 while predicting the holdout at 0.07. A
surrogate that fits the grid it was trained on tells you about the grid, not about the market. So
this module reports, in order: in-sample R-squared, OUT-OF-FOLD R-squared on held-out parameter
regions, and only then what the model says about where the robust regions are.

The target is the MEDIAN-OF-FOLDS score, the objective chosen for this run. The features are the
raw parameters, one-hot for the categorical gates. Nothing about the market enters the model --
it is a map of the parameter space, not a forecaster.

Usage: imported by run_v42b.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

AXES_NUM = ["tf", "entry1", "entry2", "exit1", "exit2", "atr_mult", "pyr", "units"]
AXES_CAT = ["adx", "ext", "skip"]


def design(T):
    X = T[AXES_NUM].astype(float).copy()
    for c in AXES_CAT:
        d = pd.get_dummies(T[c].astype(str), prefix=c, dtype=float)
        X = pd.concat([X, d], axis=1)
    return X


def fit_report(T, target="median_fold", seed=0):
    """Fit, and report the two numbers that decide whether the fit means anything.

    OUT-OF-FOLD IS BY PARAMETER REGION, not by random row. Random-row CV on a dense grid is
    almost interpolation -- every held-out cell has neighbours in training -- and it reports a
    number far higher than the model deserves. Holding out whole slices of an axis asks the
    question that matters: does the surrogate generalise to parameter settings it has not seen?"""
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.metrics import r2_score

    X, y = design(T), T[target].to_numpy()
    m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.06,
                                      max_leaf_nodes=63, random_state=seed)
    m.fit(X, y)
    in_r2 = r2_score(y, m.predict(X))

    rows = []
    for ax in ("tf", "entry1", "exit1", "atr_mult", "units"):
        vals = sorted(T[ax].unique())
        held = vals[len(vals) // 2]
        tr, te = T[ax] != held, T[ax] == held
        if te.sum() < 500 or tr.sum() < 500:
            continue
        mm = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.06,
                                           max_leaf_nodes=63, random_state=seed)
        mm.fit(design(T[tr]), y[tr.to_numpy()])
        rows.append(dict(axis=ax, held_out=held, n_test=int(te.sum()),
                         r2=float(r2_score(y[te.to_numpy()],
                                           mm.predict(design(T[te]))))))
    # a random-row split too, so the gap between the two is visible
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(T))
    cut = int(len(T) * 0.8)
    mr = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.06,
                                       max_leaf_nodes=63, random_state=seed)
    mr.fit(X.iloc[idx[:cut]], y[idx[:cut]])
    rand_r2 = float(r2_score(y[idx[cut:]], mr.predict(X.iloc[idx[cut:]])))
    return m, dict(in_sample_r2=float(in_r2), random_row_r2=rand_r2,
                   by_axis=pd.DataFrame(rows))


def importance(m, T, target="median_fold", seed=0, n=60000):
    from sklearn.inspection import permutation_importance
    rng = np.random.default_rng(seed)
    s = rng.choice(len(T), min(n, len(T)), replace=False)
    X = design(T.iloc[s])
    r = permutation_importance(m, X, T[target].to_numpy()[s], n_repeats=4,
                               random_state=seed, n_jobs=1)
    return (pd.DataFrame(dict(feature=X.columns, imp=r.importances_mean,
                              sd=r.importances_std))
            .sort_values("imp", ascending=False).reset_index(drop=True))
