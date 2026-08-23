"""One interface over LightGBM, XGBoost, CatBoost, scikit-learn and PyTorch.

The point of a common interface is not convenience, it is comparability: every model here is fitted
on the same purged folds, scored by the same cost-aware metric, and run against the same
shuffled-label control. Swapping a gradient booster for a neural network then answers a question
("does more capacity help?") instead of producing an incomparable number.

Every model is a CLASSIFIER over "does the long side of the barrier pay", and every one exposes
predict_proba. The dollar decision is made downstream in metrics.py, never inside the model, so the
cost model can change without retraining anything.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np


@dataclass
class Spec:
    """A named model factory plus the Optuna search space it is allowed to be tuned over."""
    name: str
    build: Callable[..., Any]
    space: Callable[[Any], dict] = field(default=lambda trial: {})
    needs_scaling: bool = False


def _lightgbm(**kw):
    from lightgbm import LGBMClassifier
    p = dict(n_estimators=300, learning_rate=0.05, num_leaves=31, max_depth=-1,
             min_child_samples=200, subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
             reg_lambda=1.0, n_jobs=-1, verbose=-1, random_state=20250822)
    p.update(kw)
    return LGBMClassifier(**p)


def _xgboost(**kw):
    from xgboost import XGBClassifier
    p = dict(n_estimators=300, learning_rate=0.05, max_depth=5, min_child_weight=50,
             subsample=0.8, colsample_bytree=0.8, reg_lambda=1.0, tree_method="hist",
             n_jobs=-1, random_state=20250822, eval_metric="logloss")
    p.update(kw)
    return XGBClassifier(**p)


def _catboost(**kw):
    from catboost import CatBoostClassifier
    p = dict(iterations=300, learning_rate=0.05, depth=5, l2_leaf_reg=3.0,
             random_seed=20250822, verbose=0, allow_writing_files=False, thread_count=-1)
    p.update(kw)
    return CatBoostClassifier(**p)


def _hist_gb(**kw):
    from sklearn.ensemble import HistGradientBoostingClassifier
    p = dict(max_iter=300, learning_rate=0.05, max_depth=5, min_samples_leaf=200,
             l2_regularization=1.0, random_state=20250822)
    p.update(kw)
    return HistGradientBoostingClassifier(**p)


def _random_forest(**kw):
    from sklearn.ensemble import RandomForestClassifier
    p = dict(n_estimators=300, max_depth=8, min_samples_leaf=200, n_jobs=-1,
             random_state=20250822)
    p.update(kw)
    return RandomForestClassifier(**p)


def _logistic(**kw):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    p = dict(C=1.0, max_iter=2000, random_state=20250822)
    p.update(kw)
    return make_pipeline(StandardScaler(), LogisticRegression(**p))


class TorchMLP:
    """A small feed-forward net with the same sklearn-ish surface as the boosters.

    Deliberately small. On 292k rows of 1-minute futures data with an AUC ceiling around 0.51, extra
    capacity buys extra ways to fit noise, and the shuffled-label control in metrics.py is what
    demonstrates that rather than an argument about it.
    """

    def __init__(self, hidden=(64, 32), epochs=12, lr=1e-3, batch=4096, dropout=0.2,
                 weight_decay=1e-4, seed=20250822):
        self.hidden = tuple(hidden); self.epochs = epochs; self.lr = lr
        self.batch = batch; self.dropout = dropout; self.weight_decay = weight_decay
        self.seed = seed
        self.mu_ = self.sd_ = self.net_ = None

    def fit(self, X, y):
        import torch
        import torch.nn as nn
        torch.manual_seed(self.seed)
        torch.set_num_threads(max(1, __import__("os").cpu_count() or 1))
        X = np.asarray(X, np.float32); y = np.asarray(y, np.float32)
        self.mu_ = X.mean(0); self.sd_ = X.std(0) + 1e-8
        Xs = (X - self.mu_) / self.sd_
        layers = []
        d = Xs.shape[1]
        for hsz in self.hidden:
            layers += [nn.Linear(d, hsz), nn.ReLU(), nn.Dropout(self.dropout)]
            d = hsz
        layers += [nn.Linear(d, 1)]
        self.net_ = nn.Sequential(*layers)
        opt = torch.optim.AdamW(self.net_.parameters(), lr=self.lr, weight_decay=self.weight_decay)
        lossf = nn.BCEWithLogitsLoss()
        xt = torch.from_numpy(Xs); yt = torch.from_numpy(y).unsqueeze(1)
        n = len(xt)
        g = torch.Generator().manual_seed(self.seed)
        for _ in range(self.epochs):
            perm = torch.randperm(n, generator=g)
            for i in range(0, n, self.batch):
                idx = perm[i:i + self.batch]
                opt.zero_grad()
                loss = lossf(self.net_(xt[idx]), yt[idx])
                loss.backward()
                opt.step()
        return self

    def predict_proba(self, X):
        import torch
        Xs = ((np.asarray(X, np.float32) - self.mu_) / self.sd_)
        self.net_.eval()
        with torch.no_grad():
            p = torch.sigmoid(self.net_(torch.from_numpy(Xs))).numpy().ravel()
        return np.column_stack([1 - p, p])


def _torch_mlp(**kw):
    return TorchMLP(**kw)


REGISTRY: dict[str, Spec] = {
    "lightgbm": Spec("lightgbm", _lightgbm, lambda t: dict(
        n_estimators=t.suggest_int("n_estimators", 100, 600, step=100),
        learning_rate=t.suggest_float("learning_rate", 0.01, 0.15, log=True),
        num_leaves=t.suggest_int("num_leaves", 15, 127, log=True),
        min_child_samples=t.suggest_int("min_child_samples", 50, 1000, log=True),
        colsample_bytree=t.suggest_float("colsample_bytree", 0.5, 1.0),
        reg_lambda=t.suggest_float("reg_lambda", 1e-2, 20.0, log=True))),
    "xgboost": Spec("xgboost", _xgboost, lambda t: dict(
        n_estimators=t.suggest_int("n_estimators", 100, 600, step=100),
        learning_rate=t.suggest_float("learning_rate", 0.01, 0.15, log=True),
        max_depth=t.suggest_int("max_depth", 3, 9),
        min_child_weight=t.suggest_int("min_child_weight", 10, 500, log=True),
        colsample_bytree=t.suggest_float("colsample_bytree", 0.5, 1.0),
        reg_lambda=t.suggest_float("reg_lambda", 1e-2, 20.0, log=True))),
    "catboost": Spec("catboost", _catboost, lambda t: dict(
        iterations=t.suggest_int("iterations", 100, 600, step=100),
        learning_rate=t.suggest_float("learning_rate", 0.01, 0.15, log=True),
        depth=t.suggest_int("depth", 3, 8),
        l2_leaf_reg=t.suggest_float("l2_leaf_reg", 1.0, 20.0, log=True))),
    "hist_gb": Spec("hist_gb", _hist_gb, lambda t: dict(
        max_iter=t.suggest_int("max_iter", 100, 600, step=100),
        learning_rate=t.suggest_float("learning_rate", 0.01, 0.15, log=True),
        max_depth=t.suggest_int("max_depth", 3, 9),
        min_samples_leaf=t.suggest_int("min_samples_leaf", 50, 1000, log=True))),
    "random_forest": Spec("random_forest", _random_forest, lambda t: dict(
        n_estimators=t.suggest_int("n_estimators", 100, 500, step=100),
        max_depth=t.suggest_int("max_depth", 4, 16),
        min_samples_leaf=t.suggest_int("min_samples_leaf", 50, 1000, log=True))),
    "logistic": Spec("logistic", _logistic, lambda t: dict(
        C=t.suggest_float("C", 1e-3, 10.0, log=True)), needs_scaling=True),
    "torch_mlp": Spec("torch_mlp", _torch_mlp, lambda t: dict(
        hidden=t.suggest_categorical("hidden", [(32,), (64, 32), (128, 64)]),
        lr=t.suggest_float("lr", 1e-4, 5e-3, log=True),
        dropout=t.suggest_float("dropout", 0.0, 0.5),
        epochs=t.suggest_int("epochs", 5, 25),
        weight_decay=t.suggest_float("weight_decay", 1e-6, 1e-2, log=True)), needs_scaling=True),
}


def make(name: str, **kw):
    if name not in REGISTRY:
        raise KeyError(f"unknown model {name!r}; have {sorted(REGISTRY)}")
    return REGISTRY[name].build(**kw)


def predict_proba(model, X) -> np.ndarray:
    return np.asarray(model.predict_proba(X))[:, 1]
