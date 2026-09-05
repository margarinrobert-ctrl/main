"""V48 -- purged, embargoed cross-validation and three models, including the requested deep net.

WHY PURGING IS NOT OPTIONAL HERE. A trade occupies [signal bar, exit bar] and those windows OVERLAP
in time. A naive time-split leaks: a training trade still open when the test period begins shares
its price path with the test trades, so the model is scored on data it was partly fitted on. Every
fold below PURGES any training trade whose window intersects the test window and then EMBARGOES a
further block of bars after it. This is Lopez de Prado's construction and it is the difference
between an honest CV number and a flattering one.

ON "DEEP LEARNING", said plainly rather than after the fact: the research block holds roughly 500
to 2,200 trades depending on timeframe, against 39 features. That is a regime where a neural
network memorises and a linear model is hard to beat. The MLP is run BECAUSE IT WAS ASKED FOR, kept
small and regularised, and reported beside ridge and gradient boosting so the comparison is visible
rather than asserted. If the net does not beat ridge, that is the result.

THE BAR TO CLEAR IS NOT ZERO. A filter is scored against (a) taking EVERY breakout, which is the
strategy it is meant to improve, and (b) a RANDOM filter keeping the same number of trades, because
restricting the sample raises per-trade return by construction.
"""
from __future__ import annotations

import numpy as np
from scipy import stats
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler


def purged_folds(sig, xb, n_folds=5, embargo_frac=0.01):
    """Contiguous test blocks in time; training trades overlapping the test window are dropped."""
    n = len(sig)
    order = np.argsort(sig)
    bounds = np.linspace(0, n, n_folds + 1).astype(int)
    span = sig.max() - sig.min() + 1
    emb = int(span * embargo_frac)
    out = []
    for k in range(n_folds):
        te = order[bounds[k]:bounds[k + 1]]
        if len(te) < 20:
            continue
        t0, t1 = sig[te].min(), xb[te].max()
        keep = ~((xb >= t0 - emb) & (sig <= t1 + emb))
        tr = np.flatnonzero(keep)
        if len(tr) < 100:
            continue
        out.append((tr, te))
    return out


def _mlp(nin, seed=0):
    import torch
    import torch.nn as nn
    torch.manual_seed(seed)
    return nn.Sequential(nn.Linear(nin, 32), nn.ReLU(), nn.Dropout(0.3),
                         nn.Linear(32, 16), nn.ReLU(), nn.Dropout(0.3),
                         nn.Linear(16, 1))


def fit_mlp(Xtr, ytr, Xte, epochs=300, seed=0):
    import torch
    torch.manual_seed(seed)
    m = _mlp(Xtr.shape[1], seed)
    opt = torch.optim.Adam(m.parameters(), lr=1e-3, weight_decay=1e-3)
    lf = torch.nn.MSELoss()
    xt = torch.tensor(Xtr, dtype=torch.float32); yt = torch.tensor(ytr, dtype=torch.float32).view(-1, 1)
    cut = int(len(xt) * 0.8)
    xa, ya, xv, yv = xt[:cut], yt[:cut], xt[cut:], yt[cut:]
    best, best_state, bad = np.inf, None, 0
    for _ in range(epochs):
        m.train(); opt.zero_grad()
        loss = lf(m(xa), ya); loss.backward(); opt.step()
        m.eval()
        with torch.no_grad():
            v = float(lf(m(xv), yv)) if len(xv) else float(loss)
        if v < best - 1e-6:
            best, bad = v, 0
            best_state = {k: t.clone() for k, t in m.state_dict().items()}
        else:
            bad += 1
            if bad > 40:
                break
    if best_state is not None:
        m.load_state_dict(best_state)
    m.eval()
    with torch.no_grad():
        return m(torch.tensor(Xte, dtype=torch.float32)).numpy().ravel(), m


def fit_lgbm(Xtr, ytr, Xte, seed=0):
    import lightgbm as lgb
    g = lgb.LGBMRegressor(n_estimators=200, learning_rate=0.03, num_leaves=7,
                          min_child_samples=40, subsample=0.8, subsample_freq=1,
                          colsample_bytree=0.6, reg_lambda=5.0, random_state=seed, verbose=-1)
    g.fit(Xtr, ytr)
    return g.predict(Xte), g


def fit_ridge(Xtr, ytr, Xte, alpha=10.0):
    m = Ridge(alpha=alpha).fit(Xtr, ytr)
    return m.predict(Xte), m


MODELS = {"ridge": fit_ridge, "lgbm": fit_lgbm, "mlp": fit_mlp}


def cv(X, y, sig, xb, n_folds=5, seed=0):
    """Out-of-fold predictions per model, on purged folds."""
    folds = purged_folds(sig, xb, n_folds)
    oof = {k: np.full(len(y), np.nan) for k in MODELS}
    used = np.zeros(len(y), bool)
    for tr, te in folds:
        sc = StandardScaler().fit(X[tr])
        A, B = sc.transform(X[tr]), sc.transform(X[te])
        for name, fn in MODELS.items():
            p, _ = fn(A, y[tr], B) if name != "mlp" else fn(A, y[tr], B, seed=seed)
            oof[name][te] = p
        used[te] = True
    return oof, used, folds


def score_filter(R, pred, keep_frac, rng, draws=2000):
    """Top-`keep_frac` by prediction, against the full set and a same-size random subset."""
    n = len(R)
    k = max(20, int(n * keep_frac))
    idx = np.argsort(pred)[::-1][:k]
    sel = R[idx]
    base = R.mean()
    rand = np.array([R[rng.choice(n, k, replace=False)].mean() for _ in range(draws)])
    return dict(n_kept=k, kept_R=float(sel.mean()), base_R=float(base),
                lift=float(sel.mean() - base),
                p_vs_random=float(np.mean(rand >= sel.mean())),
                ic=float(stats.spearmanr(pred, R).statistic))
