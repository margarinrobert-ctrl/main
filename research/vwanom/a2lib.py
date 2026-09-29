"""Shared pieces for the A2 ladder and the A3 reads -- importing `run_a2` would RE-RUN the whole
ladder, because a plain module-level script has no `__main__` guard. Kept in one place so the two
files cannot drift apart on the fold construction or the model definitions."""
import os, sys, pickle
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vwapema"))
SK = "/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9"
sys.path.insert(0, SK + "/mechanism-first-alpha/scripts")
sys.path.insert(0, SK + "/quant-strategy-lab/scripts")
import gates, splits

BUNDLE = pickle.load(open("results/vwanom/feat_cache.pkl", "rb"))
FCOLS = list(BUNDLE[("US30", "LONG")]["feat"].columns)
PRIMARIES = [("US100", "SHORT"), ("US30", "LONG")]      # each cell on the market that chose it
KEEPS = (0.3, 0.5, 0.7)
CAND = {}                                                # every candidate's kept-return stream
SCORES = {}                                              # every model's OOF score vector


def prep(mk, sd, blk):
    b = BUNDLE[(mk, sd)]
    m, X = b["meta"], b["feat"]
    sel = m.blk == blk if blk is not None else np.ones(len(m), bool)
    Xs = X.loc[sel.values, FCOLS].to_numpy(float)
    mu = np.nanmedian(Xs, 0)
    Xs = np.where(np.isfinite(Xs), Xs, mu)
    y = m.loc[sel.values, "pct"].to_numpy() / 100.0
    hold = (m.loc[sel.values, "exit_bar"] - m.loc[sel.values, "sig"]).to_numpy()
    return Xs, y, m.loc[sel.values].reset_index(drop=True), int(np.median(hold))


def models(seed=0):
    from sklearn.linear_model import RidgeCV
    from sklearn.ensemble import RandomForestRegressor
    import lightgbm as lgb, xgboost as xgb
    return {
        "ridge": lambda: RidgeCV(alphas=np.logspace(-2, 3, 12)),
        "rf (regularised)": lambda: RandomForestRegressor(
            n_estimators=300, max_depth=4, min_samples_leaf=40, max_features=0.4,
            random_state=seed, n_jobs=2),
        "lightgbm d3": lambda: lgb.LGBMRegressor(
            n_estimators=250, max_depth=3, num_leaves=7, learning_rate=0.03,
            min_child_samples=40, subsample=0.8, colsample_bytree=0.6,
            random_state=seed, verbose=-1, n_jobs=2),
        "xgboost d3": lambda: xgb.XGBRegressor(
            n_estimators=250, max_depth=3, learning_rate=0.03, min_child_weight=20,
            subsample=0.8, colsample_bytree=0.6, random_state=seed, n_jobs=2, verbosity=0),
        "xgboost d6": lambda: xgb.XGBRegressor(
            n_estimators=250, max_depth=6, learning_rate=0.03, min_child_weight=10,
            subsample=0.8, colsample_bytree=0.6, random_state=seed, n_jobs=2, verbosity=0),
    }


class MLP:
    """Deep arm. Torch is pinned to two threads and the arms run SEQUENTIALLY -- two torch
    processes on four cores oversubscribe and ran 31 minutes without producing a row that one
    process produces in twelve (`STUDY_EMA48_VWAP_DL`)."""

    def __init__(self, hidden=(64, 64), epochs=120, seed=0):
        self.hidden, self.epochs, self.seed = hidden, epochs, seed

    def fit(self, X, y):
        import torch
        torch.manual_seed(self.seed)
        torch.set_num_threads(2)
        self.mu_, self.sd_ = X.mean(0), X.std(0) + 1e-9
        Z = torch.tensor((X - self.mu_) / self.sd_, dtype=torch.float32)
        Y = torch.tensor(y.reshape(-1, 1) / (y.std() + 1e-12), dtype=torch.float32)
        layers, d = [], X.shape[1]
        for h in self.hidden:
            layers += [torch.nn.Linear(d, h), torch.nn.ReLU(), torch.nn.Dropout(0.1)]
            d = h
        layers += [torch.nn.Linear(d, 1)]
        self.net = torch.nn.Sequential(*layers)
        opt = torch.optim.Adam(self.net.parameters(), lr=1e-3, weight_decay=1e-4)
        for _ in range(self.epochs):
            perm = torch.randperm(len(Z))
            for i in range(0, len(Z), 256):
                b = perm[i:i + 256]
                opt.zero_grad()
                loss = ((self.net(Z[b]) - Y[b]) ** 2).mean()
                loss.backward()
                opt.step()
        return self

    def predict(self, X):
        import torch
        Z = torch.tensor((X - self.mu_) / self.sd_, dtype=torch.float32)
        with torch.no_grad():
            return self.net(Z).numpy().ravel()


def oof(make, X, y, hold, n_splits=6, shuffle_y=False, seed=0):
    """Out-of-fold predictions under purged, embargoed folds."""
    yy = np.random.default_rng(seed).permutation(y) if shuffle_y else y
    pred = np.full(len(y), np.nan)
    for tr, te in splits.purged_kfold(len(y), n_splits=n_splits, label_horizon=hold, embargo_pct=0.01):
        if len(tr) < 80 or len(te) < 10:
            continue
        mdl = make()
        mdl.fit(X[tr], yy[tr])
        pred[te] = mdl.predict(X[te])
    return pred


