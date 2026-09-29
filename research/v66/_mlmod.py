"""Shared model plumbing for D3/D4 so the two files cannot drift apart."""
import numpy as np, pandas as pd
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb, xgboost as xgb
import torch, torch.nn as nn
torch.set_num_threads(1)
_rng = np.random.default_rng(66)


def uniqueness(df):
    s = df.day.to_numpy().astype(float)
    w = np.ones(len(df))
    for i in range(len(df)):
        w[i] = 1.0 / max(1.0, np.sum(np.abs(s - s[i]) < 1e-9))
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


def _torch(Xtr, ytr, wtr, hid, depth, seed=0, epochs=220):
    torch.manual_seed(seed)
    m = MLP(Xtr.shape[1], hid, depth)
    opt = torch.optim.Adam(m.parameters(), lr=1e-3, weight_decay=1e-3)
    xt = torch.tensor(Xtr, dtype=torch.float32); yt = torch.tensor(ytr, dtype=torch.float32)
    wt = torch.tensor(wtr, dtype=torch.float32)
    for _ in range(epochs):
        opt.zero_grad()
        ((wt * (m(xt) - yt) ** 2).mean()).backward()
        opt.step()
    m.eval()
    return m


HID = {"mlp_2x32": (32, 2), "mlp_2x64": (64, 2), "mlp_4x128": (128, 4)}


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


def fit_predict(kind, Xtr, ytr, wtr, Xte, seed=0):
    if kind in HID:
        hid, depth = HID[kind]
        m = _torch(Xtr, ytr, wtr, hid, depth, seed=seed)
        with torch.no_grad():
            return m(torch.tensor(Xte, dtype=torch.float32)).numpy()
    m = _make(kind, seed)
    m.fit(Xtr, ytr, sample_weight=wtr)
    return m.predict(Xte)


def oof(df, cols, kind, seed=0, shuffle=False):
    X = df[cols].to_numpy(float); y = df.R.to_numpy(float); w = uniqueness(df)
    sc = StandardScaler().fit(X); X = sc.transform(X)
    if shuffle:
        y = y.copy(); _rng.shuffle(y)
    p = np.full(len(df), np.nan)
    for tr, te in purged_folds(len(df)):
        if len(tr) < 60:
            continue
        p[te] = fit_predict(kind, X[tr], y[tr], w[tr], X[te], seed=seed)
    return p


def fit_full(df, cols, kind, seed=0):
    X = df[cols].to_numpy(float); y = df.R.to_numpy(float); w = uniqueness(df)
    sc = StandardScaler().fit(X)
    Xs = sc.transform(X)
    if kind in HID:
        hid, depth = HID[kind]
        m = _torch(Xs, y, w, hid, depth, seed=seed)
        def pred(Z):
            with torch.no_grad():
                return m(torch.tensor(sc.transform(Z), dtype=torch.float32)).numpy()
    else:
        m = _make(kind, seed); m.fit(Xs, y, sample_weight=w)
        def pred(Z):
            return m.predict(sc.transform(Z))
    return dict(model=m, scaler=sc, predict=pred)


def ic(p, y):
    m = np.isfinite(p) & np.isfinite(y)
    return float(pd.Series(p[m]).corr(pd.Series(y[m]), method="spearman")) if m.sum() > 20 else np.nan
