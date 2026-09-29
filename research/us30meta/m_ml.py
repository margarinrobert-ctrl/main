"""Model plumbing shared by M3/M4/M5 so the three files cannot drift apart.

Three things are non-negotiable here and each is a recorded failure on this branch:
  * the objective is the POINTS EARNED, never win/lose. `STUDY_V28` and `STUDY_V32`: trained on
    win/lose the win rate rises exactly as asked and p90 of R FALLS in every cell, because a
    breakout earns in the tail and a win-rate optimiser trims it.
  * purged + embargoed folds with uniqueness weights. A trade occupies [signal, exit] and those
    windows overlap, so a naive split trains on the answer.
  * every model is run beside a SHUFFLED-LABEL TWIN. `STUDY_V28`: the deepest net's shuffled twin
    scored higher than any real model on the headline statistic, which is how you learn the column
    is noise. If the twin wins more than half the cells the noise floor is above the signal.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb
import xgboost as xgb
import torch
import torch.nn as nn

torch.set_num_threads(2)

LADDER = ["ridge", "rf", "lgbm", "xgb_d3", "xgb_d6", "mlp_2x32", "mlp_2x64", "mlp_4x128"]
HID = {"mlp_2x32": (32, 2), "mlp_2x64": (64, 2), "mlp_4x128": (128, 4)}


def uniqueness(days):
    """Lopez de Prado uniqueness: a session with twelve concurrent events contributes as much as a
    session with one, not twelve times as much."""
    s = np.asarray(days, float)
    u, inv, cnt = np.unique(s, return_inverse=True, return_counts=True)
    w = 1.0 / cnt[inv]
    return w / w.mean()


def purged_folds(n, k=5, embargo=0.02):
    edges = np.linspace(0, n, k + 1).astype(int)
    emb = int(np.ceil(embargo * n))
    for j in range(k):
        te = np.arange(edges[j], edges[j + 1])
        tr = np.concatenate([np.arange(0, max(0, edges[j] - emb)),
                             np.arange(min(n, edges[j + 1] + emb), n)])
        yield tr, te


class MLP(nn.Module):
    def __init__(self, p, hid, depth):
        super().__init__()
        layers, d = [], p
        for _ in range(depth):
            layers += [nn.Linear(d, hid), nn.ReLU(), nn.Dropout(0.15)]
            d = hid
        layers += [nn.Linear(d, 1)]
        self.f = nn.Sequential(*layers)

    def forward(self, x):
        return self.f(x).squeeze(-1)


def _torch_fit(X, y, w, hid, depth, seed=0, epochs=220):
    torch.manual_seed(seed)
    m = MLP(X.shape[1], hid, depth)
    opt = torch.optim.Adam(m.parameters(), lr=1e-3, weight_decay=1e-3)
    xt = torch.tensor(X, dtype=torch.float32)
    yt = torch.tensor(y, dtype=torch.float32)
    wt = torch.tensor(w, dtype=torch.float32)
    for _ in range(epochs):
        opt.zero_grad()
        ((wt * (m(xt) - yt) ** 2).mean()).backward()
        opt.step()
    m.eval()
    return m


def _make(kind, seed):
    if kind == "ridge":
        return Ridge(alpha=5.0)
    if kind == "rf":
        return RandomForestRegressor(n_estimators=400, max_depth=4, min_samples_leaf=25,
                                     max_features=0.5, random_state=seed, n_jobs=2)
    if kind == "lgbm":
        return lgb.LGBMRegressor(n_estimators=250, learning_rate=0.03, num_leaves=7, max_depth=3,
                                 min_child_samples=30, subsample=0.8, colsample_bytree=0.6,
                                 reg_lambda=5.0, random_state=seed, verbose=-1)
    d = 3 if kind.endswith("d3") else 6
    return xgb.XGBRegressor(n_estimators=300, learning_rate=0.03, max_depth=d,
                            min_child_weight=10, subsample=0.8, colsample_bytree=0.6,
                            reg_lambda=5.0, random_state=seed, n_jobs=2, verbosity=0)


def _fit_predict(kind, Xtr, ytr, wtr, Xte, seed=0):
    if kind in HID:
        hid, depth = HID[kind]
        m = _torch_fit(Xtr, ytr, wtr, hid, depth, seed=seed)
        with torch.no_grad():
            return m(torch.tensor(Xte, dtype=torch.float32)).numpy()
    m = _make(kind, seed)
    m.fit(Xtr, ytr, sample_weight=wtr)
    return m.predict(Xte)


def _prep(df, cols):
    X = df[cols].to_numpy(float)
    med = np.nanmedian(X, axis=0)
    bad = ~np.isfinite(X)
    X[bad] = np.take(med, np.where(bad)[1])
    return np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)


def oof(df, cols, kind, seed=0, shuffle=False, ycol="y"):
    X = _prep(df, cols)
    y = df[ycol].to_numpy(float)
    w = uniqueness(df["dayi"].to_numpy())
    sc = StandardScaler().fit(X)
    X = sc.transform(X)
    if shuffle:
        rng = np.random.default_rng(1000 + seed)
        y = rng.permutation(y)
    p = np.full(len(df), np.nan)
    for tr, te in purged_folds(len(df)):
        if len(tr) < 100:
            continue
        p[te] = _fit_predict(kind, X[tr], y[tr], w[tr], X[te], seed=seed)
    return p


def fit_full(df, cols, kind, seed=0, ycol="y"):
    X = _prep(df, cols)
    y = df[ycol].to_numpy(float)
    w = uniqueness(df["dayi"].to_numpy())
    sc = StandardScaler().fit(X)
    Xs = sc.transform(X)
    if kind in HID:
        hid, depth = HID[kind]
        m = _torch_fit(Xs, y, w, hid, depth, seed=seed)

        def pred(Z):
            with torch.no_grad():
                return m(torch.tensor(sc.transform(_clean(Z, X)), dtype=torch.float32)).numpy()
    else:
        m = _make(kind, seed)
        m.fit(Xs, y, sample_weight=w)

        def pred(Z):
            return m.predict(sc.transform(_clean(Z, X)))
    return dict(model=m, scaler=sc, predict=pred)


def _clean(Z, ref):
    Z = np.asarray(Z, float).copy()
    med = np.nanmedian(ref, axis=0)
    bad = ~np.isfinite(Z)
    if bad.any():
        Z[bad] = np.take(med, np.where(bad)[1])
    return np.nan_to_num(Z, nan=0.0, posinf=0.0, neginf=0.0)


def ic(p, y):
    m = np.isfinite(p) & np.isfinite(y)
    return float(pd.Series(p[m]).corr(pd.Series(y[m]), method="spearman")) if m.sum() > 20 else np.nan
