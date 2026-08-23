"""Optuna search, with the cost of the search reported beside the result.

Optuna makes it trivial to run 500 trials. On this data that is the 225,792-configuration
experiment again: the search finds the highest number, and the highest number out of 500 draws from
a null distribution is about sqrt(2 ln 500) = 3.5 standard errors from zero by construction.

So `search()` always returns the hurdle alongside the result, `study_pbo()` measures whether the
SELECTION PROCEDURE generalises at all, and the objective is cross-validated on purged folds rather
than fitted to one split.
"""
from __future__ import annotations

import numpy as np

from .metrics import day_cluster_t, deflate, evaluate
from .splits import PurgedKFold
from .zoo import REGISTRY, predict_proba


def cv_score(model_name, params, X, y_dollars, sess, horizon, n_splits=5, embargo=0.01):
    """Mean out-of-fold lift over the take-everything policy, on purged folds."""
    spec = REGISTRY[model_name]
    cv = PurgedKFold(n_splits=n_splits, horizon=horizon, embargo=embargo)
    Xv = np.asarray(X, float)
    lab = (y_dollars > 0).astype(int)
    oof = np.full(len(Xv), np.nan)
    for tr, te in cv.split(len(Xv)):
        m = spec.build(**params)
        m.fit(Xv[tr], lab[tr])
        oof[te] = predict_proba(m, Xv[te])
    s = evaluate(oof, y_dollars, sess)
    return s, oof


def search(model_name, X, y_dollars, sess, horizon, n_trials=40, n_splits=5,
           seed=20250822, timeout=None, logger=None):
    """Run an Optuna study and return (best_params, best_score, report).

    `report` carries n_trials and the hurdle that trial count implies, so a caller cannot quote the
    tuned number without the denominator.
    """
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    spec = REGISTRY[model_name]
    trials = []

    def objective(trial):
        params = spec.space(trial)
        s, _ = cv_score(model_name, params, X, y_dollars, sess, horizon, n_splits)
        val = s.best_lift if np.isfinite(s.best_lift) else -1e9
        trials.append((val, s.t_day, params))
        return val

    study = optuna.create_study(direction="maximize",
                                sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective, n_trials=n_trials, timeout=timeout, show_progress_bar=False)

    best_params = study.best_params
    s, oof = cv_score(model_name, best_params, X, y_dollars, sess, horizon, n_splits)
    vals = np.array([t[0] for t in trials if np.isfinite(t[0])])
    report = deflate(s.t_day, len(trials))          # supplies n_trials, hurdle, t, clears
    report.update(
        best_lift=float(s.best_lift),
        spread_across_trials=float(vals.std()) if len(vals) > 1 else np.nan,
        worst_trial=float(vals.min()) if len(vals) else np.nan,
        t_day=float(s.t_day),
    )
    if logger is not None:
        for k, v in report.items():
            if isinstance(v, (int, float)):
                logger.metric(f"search_{k}", v)
    return best_params, s, report, oof


def study_pbo(model_name, X, y_dollars, sess, horizon, param_grid, n_splits=8):
    """Probability of backtest overfitting for the SELECTION, via combinatorially symmetric CV.

    Split the sample into S contiguous blocks; for every half/half partition, pick the best
    configuration on one half and record its RANK on the other. PBO is the fraction of partitions
    where the in-sample winner lands in the bottom half out of sample. A PBO near 0.5 means the
    selection carries no information; above it, the search is actively harmful.
    """
    from itertools import combinations

    Xv = np.asarray(X, float)
    lab = (y_dollars > 0).astype(int)
    n = len(Xv)
    bounds = np.linspace(0, n, n_splits + 1).astype(int)
    blocks = [np.arange(bounds[i], bounds[i + 1]) for i in range(n_splits)]

    perf = np.full((len(param_grid), n_splits), np.nan)
    spec = REGISTRY[model_name]
    for ci, params in enumerate(param_grid):
        for bi, blk in enumerate(blocks):
            tr = np.setdiff1d(np.arange(n), blk)
            lo = max(0, blk[0] - horizon); hi = min(n, blk[-1] + horizon)
            tr = tr[(tr < lo) | (tr > hi)]
            if len(tr) < 500:
                continue
            m = spec.build(**params)
            m.fit(Xv[tr], lab[tr])
            p = predict_proba(m, Xv[blk])
            s = evaluate(p, y_dollars[blk], sess[blk])
            perf[ci, bi] = s.best_lift

    ranks = []
    half = n_splits // 2
    for comb in combinations(range(n_splits), half):
        ins = list(comb)
        oos = [b for b in range(n_splits) if b not in ins]
        a = np.nanmean(perf[:, ins], axis=1)
        b = np.nanmean(perf[:, oos], axis=1)
        if np.all(np.isnan(a)) or np.all(np.isnan(b)):
            continue
        best = int(np.nanargmax(a))
        r = float(np.nanmean(b <= b[best]))     # relative rank of the in-sample winner, out of sample
        ranks.append(r)
    ranks = np.array(ranks)
    return dict(pbo=float((ranks < 0.5).mean()) if len(ranks) else np.nan,
                n_partitions=len(ranks), median_oos_rank=float(np.median(ranks)) if len(ranks) else np.nan)
