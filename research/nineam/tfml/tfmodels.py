"""The model ladder, folds and weights, shared by T3..T5 so the runners cannot drift apart.

Folds: CHRONOLOGICAL, GROUPED BY SESSION, with a one-session embargo either side of the test block.
Every label here ends at the 11:00 flatten of its own session, so no label spans two sessions and
purging reduces to the grouping; the embargo covers serial correlation between adjacent sessions.
Weights: Lopez de Prado uniqueness within a timeframe (events on one session whose [signal, exit]
windows overlap share weight), times 1/k for a (session, side) break that appears at k timeframes of
the same dataset -- the pooled set is seven views of one set of breaks, not seven samples.
"""
from __future__ import annotations

import os
for _k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_k, "2")
import warnings

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb
import xgboost as xgb

warnings.filterwarnings("ignore")
MODELS = ("ridge", "rf", "lgbm", "xgb_d3", "mlp_2x32", "mlp_2x64", "mlp_4x128")


def weights(df):
    w = np.ones(len(df))
    ts = df["t_sig"].to_numpy(); te = df["t_exit"].to_numpy()
    for tf in df["tf"].unique():
        idx = np.flatnonzero(df["tf"].to_numpy() == tf)
        for d in np.unique(df["day"].to_numpy()[idx]):
            j = idx[df["day"].to_numpy()[idx] == d]
            for a in j:
                conc = sum(1 for b in j if ts[b] < te[a] and te[b] > ts[a])
                w[a] = 1.0 / max(conc, 1)
    k = df.groupby(["day", "side"])["tf"].transform("size").to_numpy()
    w = w / k
    return w / w.mean()


def folds(days, k=5, embargo=1):
    u = np.array(sorted(np.unique(days)))
    edges = np.linspace(0, len(u), k + 1).astype(int)
    for j in range(k):
        te_d = u[edges[j]:edges[j + 1]]
        lo = max(0, edges[j] - embargo); hi = min(len(u), edges[j + 1] + embargo)
        tr_d = np.r_[u[:lo], u[hi:]]
        yield np.flatnonzero(np.isin(days, tr_d)), np.flatnonzero(np.isin(days, te_d))


def make(name, seed=0):
    if name == "ridge":
        return Ridge(alpha=10.0)
    if name == "rf":
        return RandomForestRegressor(n_estimators=300, max_depth=3, min_samples_leaf=8,
                                     max_features=0.5, random_state=seed, n_jobs=2)
    if name == "lgbm":
        return lgb.LGBMRegressor(n_estimators=200, learning_rate=0.03, num_leaves=4,
                                 min_child_samples=10, subsample=0.8, subsample_freq=1,
                                 colsample_bytree=0.8, reg_lambda=5.0, random_state=seed,
                                 num_threads=2, verbose=-1)
    if name == "xgb_d3":
        return xgb.XGBRegressor(n_estimators=200, learning_rate=0.03, max_depth=3,
                                min_child_weight=5, subsample=0.8, colsample_bytree=0.8,
                                reg_lambda=5.0, random_state=seed, nthread=2, verbosity=0)
    hid = {"mlp_2x32": (32, 32), "mlp_2x64": (64, 64), "mlp_4x128": (128,) * 4}[name]
    return MLPRegressor(hidden_layer_sizes=hid, alpha=1e-2, early_stopping=True,
                        validation_fraction=0.2, n_iter_no_change=20, max_iter=2000,
                        learning_rate_init=1e-3, random_state=seed)


SCALED = {"ridge", "mlp_2x32", "mlp_2x64", "mlp_4x128"}


def fit_predict(name, Xtr, ytr, wtr, Xte, seed=0):
    imp = SimpleImputer(strategy="median").fit(Xtr)
    A = imp.transform(Xtr); B = imp.transform(Xte)
    if name in SCALED:
        sc = StandardScaler().fit(A); A = sc.transform(A); B = sc.transform(B)
    m = make(name, seed)
    ys = ytr
    if name.startswith("mlp"):
        # standardise the target too: raw pct is ~0.1 wide and the net otherwise barely moves
        mu, sd = ytr.mean(), ytr.std() + 1e-12
        m.fit(A, (ytr - mu) / sd, sample_weight=wtr)
        return m.predict(B) * sd + mu, m
    m.fit(A, ys, sample_weight=wtr)
    return m.predict(B), m


def oof(name, X, y, w, days, seed=0, k=5):
    out = np.full(len(y), np.nan)
    for tr, te in folds(days, k):
        if len(tr) < 10 or len(te) == 0:
            continue
        out[te], _ = fit_predict(name, X[tr], y[tr], w[tr], X[te], seed)
    return out


def ic(a, b):
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 5 or np.nanstd(a[m]) == 0:
        return np.nan
    return float(spearmanr(a[m], b[m]).statistic)
