"""Part B -- feature engineering on the forming window, and what a booster can read from it.

THE QUESTION IS DIAGNOSTIC, NOT PREDICTIVE. `ib_features.py` already showed the IB does not make
money. What has never been asked is WHAT, IF ANYTHING, ABOUT A WINDOW IS INFORMATIVE -- which is a
different question and is answered by feature importance and by a booster's out-of-fold skill, not
by a P&L table.

TWO TARGETS, because they are different mechanisms:
    DIRECTION   which side breaks first. If the window's shape predicts this, the range is a real
                auction structure. If not, the break side is a coin flip and every "IB long"
                strategy is a drift bet wearing a range.
    OUTCOME     the R of the break trade. This is the tradeable question, and V32 established that
                the two objectives are not the same: a model trained on a win/lose-style label
                raises accuracy and lowers Sharpe, because it sells the right tail.

GUARDS, unchanged from V32 because they are what make the number readable: PURGED + EMBARGOED
folds; a SHUFFLED-LABEL TWIN for every model, which is the pipeline's noise floor; and both
XGBoost and LightGBM, shallow, because V28 found capacity monotonically harmful here.

Sessions do not overlap -- one window per day, resolved inside that day -- so the purge only needs
to drop adjacent days, which is done anyway rather than assumed away.
"""
from __future__ import annotations

import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, "research")
sys.path.insert(0, "research/v35")
import v35bal as B            # noqa: E402
import lightgbm as lgb        # noqa: E402
import xgboost as xgb         # noqa: E402

FOLDS = 6
EMBARGO = 1                   # sessions
RUNGS = (1.00, 0.50, 0.25, 0.10)


def feats(T):
    cols = [c for c in T.columns if c.startswith(("f_", "z_"))]
    X = T[cols].replace([np.inf, -np.inf], np.nan)
    ok = np.isfinite(X.to_numpy()).all(axis=1)
    return X[ok].reset_index(drop=True), T[ok].reset_index(drop=True), cols


def purged_folds(n, n_folds=FOLDS, embargo=EMBARGO):
    edges = np.linspace(0, n, n_folds + 1).astype(int)
    for f in range(n_folds):
        te = np.zeros(n, bool)
        te[edges[f]:edges[f + 1]] = True
        lo = max(0, edges[f] - embargo)
        hi = min(n, edges[f + 1] + embargo)
        tr = np.ones(n, bool)
        tr[lo:hi] = False
        if tr.sum() > 100 and te.sum() > 20:
            yield np.flatnonzero(tr), np.flatnonzero(te)


def make(name, task):
    if name == "xgb":
        kw = dict(n_estimators=250, max_depth=3, learning_rate=0.03, subsample=0.8,
                  colsample_bytree=0.6, reg_lambda=5.0, min_child_weight=10, n_jobs=4,
                  verbosity=0, random_state=0)
        return xgb.XGBClassifier(**kw) if task == "dir" else xgb.XGBRegressor(**kw)
    kw = dict(n_estimators=250, num_leaves=7, learning_rate=0.03, subsample=0.8, subsample_freq=1,
              colsample_bytree=0.6, reg_lambda=5.0, min_child_samples=20, n_jobs=4, verbose=-1,
              random_state=0)
    return lgb.LGBMClassifier(**kw) if task == "dir" else lgb.LGBMRegressor(**kw)


def oof(X, y, name, task, shuffle=False, seed=0):
    p = np.full(len(y), np.nan)
    yy = np.random.default_rng(seed).permutation(y) if shuffle else y
    for tr, te in purged_folds(len(y)):
        m = make(name, task)
        m.fit(X.iloc[tr], yy[tr])
        p[te] = (m.predict_proba(X.iloc[te])[:, 1] if task == "dir" else m.predict(X.iloc[te]))
    return p


def auc(y, p):
    ok = np.isfinite(p)
    y, p = np.asarray(y)[ok], p[ok]
    if len(np.unique(y)) < 2:
        return np.nan
    o = np.argsort(p)
    r = np.empty(len(p)); r[o] = np.arange(1, len(p) + 1)
    n1 = int(y.sum()); n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def hdr(t):
    print("\n" + "=" * 122)
    print(t)
    print("=" * 122, flush=True)


def run(start=570, length=60, label="the classic IB 09:30-10:30"):
    d = B.bars(B.TF)
    T = B.outcomes(d, B.window_table(d, start, length))
    res, _lok = B.blocks(d["sess"])
    res_sess = np.unique(d["sess"][res])
    X, T, cols = feats(T)
    tr_mask = T.sess.isin(res_sess).to_numpy()
    hdr(f"{label}   {len(cols)} causal window features, {int(tr_mask.sum())} research sessions")

    # ---- DIRECTION -----------------------------------------------------------------------------
    m = tr_mask & (T.brk != 0).to_numpy()
    Xd, yd = X[m].reset_index(drop=True), (T.brk[m] > 0).astype(int).to_numpy()
    print(f"\n   DIRECTION -- which side breaks first.  base rate up {yd.mean():.3f} on "
          f"{len(yd)} sessions")
    print(f"      {'model':<8}{'AUC':>9}{'shuffled AUC':>15}   verdict")
    for name in ("xgb", "lgbm"):
        a = auc(yd, oof(Xd, yd, name, "dir"))
        s = auc(yd, oof(Xd, yd, name, "dir", shuffle=True, seed=3))
        v = "no skill" if not (a > s + 0.02 and a > 0.55) else "some skill"
        print(f"      {name:<8}{a:>9.4f}{s:>15.4f}   {v}")

    # ---- OUTCOME -------------------------------------------------------------------------------
    mo = tr_mask & T.R.notna().to_numpy()
    Xo, yo = X[mo].reset_index(drop=True), T.R[mo].to_numpy()
    base = float(yo.mean())
    print(f"\n   OUTCOME -- R of the break trade.  baseline {base:+.4f} R over {len(yo)} trades")
    print(f"      {'model':<8}{'keep':>7}{'n':>6}{'R/trade':>10}{'PF':>8}{'p90 R':>9}"
          f"{'  ':>2}{'shuffled R':>12}")
    for name in ("xgb", "lgbm"):
        p = oof(Xo, yo, name, "R")
        ps = oof(Xo, yo, name, "R", shuffle=True, seed=5)
        for q in RUNGS:
            k = max(30, int(round(q * np.isfinite(p).sum())))
            idx = np.argsort(-np.where(np.isfinite(p), p, -1e9))[:k]
            r = yo[idx]
            js = np.argsort(-np.where(np.isfinite(ps), ps, -1e9))[:k]
            pf = r[r > 0].sum() / abs(r[r < 0].sum()) if (r < 0).any() else np.nan
            print(f"      {name:<8}{q:>7.0%}{len(r):>6}{r.mean():>+10.4f}{pf:>8.3f}"
                  f"{np.percentile(r, 90):>+9.3f}{'  ':>2}{yo[js].mean():>+12.4f}")

    # ---- WHAT THE MODEL USES -------------------------------------------------------------------
    mdl = make("lgbm", "R"); mdl.fit(Xo, yo)
    imp = pd.Series(mdl.feature_importances_, index=Xo.columns, dtype=float).sort_values(
        ascending=False)
    print(f"\n   WHAT THE MODEL READS (LightGBM split gain, research only)")
    for k, v in imp.head(10).items():
        print(f"      {k:<22}{v:>8.0f}{v / imp.sum():>9.2%}")
    return T, X, imp


if __name__ == "__main__":
    run(570, 60, "the classic IB 09:30-10:30")
