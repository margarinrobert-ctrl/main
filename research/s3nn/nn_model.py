"""The model ladder, with the three things that decide whether any of it means anything.

1. PURGED + EMBARGOED folds. A label spans [signal, exit]; events overlap, so an ordinary K-fold
   trains on bars the validation label is still living through. Purge any training row whose span
   intersects the test span, then embargo a further window after it.
2. UNIQUENESS WEIGHTS. An overlapping-label set counted as independent rows inflates every score.
3. A SHUFFLED-LABEL TWIN beside every model. Above 50% of cells beating the real model means the
   noise floor is higher than the signal, which is the only way to learn that a column is noise.

The objective is the R the trade EARNED, not win/lose. This branch has measured four times that a
win-rate objective trims p90 of R, and a stop-and-trail system earns in the tail.
"""
import numpy as np, pandas as pd
import torch, torch.nn as nn

SEED = 7


def purged_folds(sig, exit_, n_folds=5, embargo=0.01):
    """Contiguous test folds in TIME, with training rows purged and embargoed around each."""
    n = len(sig)
    order = np.argsort(sig)
    emb = int(embargo * n)
    out = []
    bounds = np.linspace(0, n, n_folds + 1).astype(int)
    for f in range(n_folds):
        te = order[bounds[f]:bounds[f + 1]]
        t0, t1 = sig[te].min(), exit_[te].max()
        te_set = set(te.tolist())
        keep = []
        for j in order:
            if j in te_set:
                continue
            # purge: the training label's own span must not touch the test span
            if exit_[j] >= t0 and sig[j] <= t1:
                continue
            # embargo: nothing that starts just after the test block
            if t1 < sig[j] <= t1 + emb:
                continue
            keep.append(j)
        out.append((np.array(keep, dtype=int), te))
    return out


class MLP(nn.Module):
    def __init__(self, d, hidden, drop=0.2):
        super().__init__()
        layers, prev = [], d
        for h in hidden:
            layers += [nn.Linear(prev, h), nn.ReLU(), nn.Dropout(drop)]
            prev = h
        layers += [nn.Linear(prev, 1)]
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x).squeeze(-1)


def fit_mlp(Xtr, ytr, wtr, Xte, hidden, epochs=250, lr=1e-3, wd=1e-3, drop=0.2, seed=SEED):
    torch.manual_seed(seed)
    torch.set_num_threads(4)
    xt = torch.tensor(Xtr, dtype=torch.float32)
    yt = torch.tensor(ytr, dtype=torch.float32)
    wt = torch.tensor(wtr, dtype=torch.float32)
    m = MLP(Xtr.shape[1], hidden, drop)
    opt = torch.optim.AdamW(m.parameters(), lr=lr, weight_decay=wd)
    m.train()
    for _ in range(epochs):
        opt.zero_grad()
        p = m(xt)
        loss = (wt * (p - yt) ** 2).mean()
        loss.backward()
        opt.step()
    m.eval()
    with torch.no_grad():
        return m(torch.tensor(Xte, dtype=torch.float32)).numpy()


def make_models(d):
    """The ladder: linear -> regularised forest -> boosters -> nets of rising capacity.

    V28 measured AUC FALLING with depth in every family and the two best models in the whole
    ladder being a regularised random forest and a linear one. The ladder exists to find out
    whether that reproduces here, not because a deep net is expected to win."""
    from sklearn.linear_model import Ridge
    from sklearn.ensemble import RandomForestRegressor
    import lightgbm as lgb, xgboost as xgb
    return [
        ("ridge", lambda: Ridge(alpha=10.0)),
        ("rf", lambda: RandomForestRegressor(
            n_estimators=400, max_depth=4, min_samples_leaf=40, max_features=0.4,
            random_state=SEED, n_jobs=4)),
        ("lgbm", lambda: lgb.LGBMRegressor(
            n_estimators=300, num_leaves=7, learning_rate=0.03, min_child_samples=40,
            subsample=0.7, subsample_freq=1, colsample_bytree=0.6,
            reg_lambda=5.0, random_state=SEED, n_jobs=4, verbose=-1)),
        ("xgb_d3", lambda: xgb.XGBRegressor(
            n_estimators=300, max_depth=3, learning_rate=0.03, subsample=0.7,
            colsample_bytree=0.6, reg_lambda=5.0, min_child_weight=20,
            random_state=SEED, n_jobs=4, verbosity=0)),
        ("xgb_d6", lambda: xgb.XGBRegressor(
            n_estimators=300, max_depth=6, learning_rate=0.03, subsample=0.7,
            colsample_bytree=0.6, reg_lambda=5.0, min_child_weight=20,
            random_state=SEED, n_jobs=4, verbosity=0)),
        ("mlp_2x32", ("mlp", [32, 32])),
        ("mlp_2x64", ("mlp", [64, 64])),
        ("mlp_4x128", ("mlp", [128, 128, 128, 128])),
    ]


def run_oof(X, y, w, sig, exit_, folds, shuffle=False, seed=SEED):
    """Out-of-fold predictions for the whole ladder, real labels and a shuffled twin."""
    rng = np.random.default_rng(seed)
    yy = y.copy()
    if shuffle:
        yy = rng.permutation(yy)
    out = {}
    for name, spec in make_models(X.shape[1]):
        pred = np.full(len(y), np.nan)
        for tr, te in folds:
            mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
            Xtr, Xte = (X[tr] - mu) / sd, (X[te] - mu) / sd
            if isinstance(spec, tuple):
                pred[te] = fit_mlp(Xtr, yy[tr], w[tr], Xte, spec[1], seed=seed)
            else:
                m = spec()
                try:
                    m.fit(Xtr, yy[tr], sample_weight=w[tr])
                except TypeError:
                    m.fit(Xtr, yy[tr])
                pred[te] = m.predict(Xte)
        out[name] = pred
    return out


def keep_stats(r, score, frac):
    """What a keep-rule earns, with p90 of R beside it -- the column that catches a win-rate fit."""
    n = len(r)
    k = max(int(round(frac * n)), 5)
    idx = np.argsort(-score)[:k]
    s = r[idx]
    return dict(kept=len(s), frac=len(s) / n, mean=s.mean(),
                pf=s[s > 0].sum() / max(-s[s < 0].sum(), 1e-9),
                win=(s > 0).mean(), p90=np.percentile(s, 90))
