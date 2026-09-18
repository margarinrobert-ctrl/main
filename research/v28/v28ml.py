"""The capacity ladder: does more model capacity buy anything on this label?

THE QUESTION, PUT PRECISELY. "Use deep learning to find the best parameters" is a parameter search
with more capacity. This branch has already run enormous searches -- 110,250 configurations bought
+0.098 R out of sample against the un-swept starting point's +0.097; 143,820 configurations produced
one survivor of ten finalists; 16.2M generated strategies and 142.8M SAM combinations were mostly
null. The binding constraint here has never been optimiser power. It is signal-to-noise.

So the informative experiment is not "run a deep net and report its backtest". It is a LADDER:
constant, then linear, then trees, then a shallow net, then a deep net, all on the SAME purged
folds and the SAME label. If capacity buys nothing, that is a quantitative statement about the DATA
which no amount of architecture fixes. If it buys something, the ladder shows where it starts.

EVERY MODEL IS RUN TWICE -- once on the real labels and once on SHUFFLED labels. The shuffled score
is the floor this pipeline produces from nothing: leakage, class imbalance, fold luck, and the
optimisation itself. A result has to clear its own shuffled twin, not 0.5.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, "research/v24")
sys.path.insert(0, "research/v28")
import v24ma as V             # noqa: E402
import v28data as D           # noqa: E402

from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score
import lightgbm as lgb
import xgboost as xgb
import torch
import torch.nn as nn

torch.manual_seed(0)


def mlp(depth, width, din, seed=0):
    torch.manual_seed(seed)
    layers, d = [], din
    for _ in range(depth):
        layers += [nn.Linear(d, width), nn.ReLU(), nn.Dropout(0.2)]
        d = width
    layers += [nn.Linear(d, 1)]
    return nn.Sequential(*layers)


def fit_mlp(Xtr, ytr, Xte, depth, width, epochs=60, lr=1e-3, seed=0):
    net = mlp(depth, width, Xtr.shape[1], seed)
    opt = torch.optim.Adam(net.parameters(), lr=lr, weight_decay=1e-4)
    lossf = nn.BCEWithLogitsLoss()
    xt = torch.tensor(Xtr, dtype=torch.float32)
    yt = torch.tensor(ytr, dtype=torch.float32)[:, None]
    n = len(xt)
    for _ in range(epochs):
        perm = torch.randperm(n)
        for i in range(0, n, 256):
            idx = perm[i:i + 256]
            opt.zero_grad()
            loss = lossf(net(xt[idx]), yt[idx])
            loss.backward()
            opt.step()
    net.eval()
    with torch.no_grad():
        return torch.sigmoid(net(torch.tensor(Xte, dtype=torch.float32))).numpy().ravel()


MODELS = [
    ("constant (no model)", None),
    ("logistic regression", "logit"),
    ("random forest 300", "rf"),
    ("LightGBM 400", "lgbm"),
    ("XGBoost 300 d3 (shallow)", ("xgb", 300, 3, 0.05)),
    ("XGBoost 600 d6", ("xgb", 600, 6, 0.05)),
    ("XGBoost 1200 d10 (deep)", ("xgb", 1200, 10, 0.05)),
    ("MLP 2x64 (shallow)", ("mlp", 2, 64)),
    ("MLP 4x128 (deep)", ("mlp", 4, 128)),
    ("MLP 6x256 (deeper)", ("mlp", 6, 256)),
]


def run_model(spec, Xtr, ytr, Xte):
    if spec is None:
        return np.full(len(Xte), 0.5)
    if spec == "logit":
        m = LogisticRegression(max_iter=2000, C=0.1)
        m.fit(Xtr, ytr)
        return m.predict_proba(Xte)[:, 1]
    if spec == "rf":
        m = RandomForestClassifier(n_estimators=300, min_samples_leaf=20, n_jobs=-1,
                                   random_state=0)
        m.fit(Xtr, ytr)
        return m.predict_proba(Xte)[:, 1]
    if spec == "lgbm":
        m = lgb.LGBMClassifier(n_estimators=400, learning_rate=0.03, num_leaves=15,
                               min_child_samples=40, subsample=0.8, colsample_bytree=0.6,
                               random_state=0, verbose=-1)
        m.fit(Xtr, ytr)
        return m.predict_proba(Xte)[:, 1]
    if spec[0] == "xgb":
        _, n_est, depth, lr = spec
        m = xgb.XGBClassifier(n_estimators=n_est, max_depth=depth, learning_rate=lr,
                              subsample=0.8, colsample_bytree=0.6, min_child_weight=20,
                              reg_lambda=1.0, random_state=0, n_jobs=-1,
                              tree_method="hist", eval_metric="logloss")
        m.fit(Xtr, ytr)
        return m.predict_proba(Xte)[:, 1]
    _, depth, width = spec
    return fit_mlp(Xtr, ytr, Xte, depth, width)


def ladder(X, yR, yw, meta, shuffle=False, seed=0, n_folds=6):
    Xv = X.to_numpy(float)
    rng = np.random.default_rng(seed)
    y = yw.copy()
    if shuffle:
        y = rng.permutation(y)
    out = {}
    for name, spec in MODELS:
        preds, truth, rs = [], [], []
        for tr, te in D.purged_folds(meta["sig"], meta["xb"], n_folds=n_folds):
            sc = StandardScaler().fit(Xv[tr])
            p = run_model(spec, sc.transform(Xv[tr]), y[tr], sc.transform(Xv[te]))
            preds.append(p)
            truth.append(y[te])
            rs.append(yR[te])
        p = np.concatenate(preds)
        t = np.concatenate(truth)
        r = np.concatenate(rs)
        auc = roc_auc_score(t, p) if len(np.unique(t)) > 1 else np.nan
        ic = spearmanr(p, r).statistic if len(np.unique(p)) > 1 else 0.0
        # what it is worth: trade only the top half / top decile the model likes
        med, d9 = np.median(p), np.quantile(p, 0.9)
        out[name] = dict(auc=auc, ic=ic, r_all=r.mean(),
                         r_top50=r[p >= med].mean(), r_top10=r[p >= d9].mean(),
                         n=len(r))
    return out


if __name__ == "__main__":
    X, yR, yw, meta = D.build("NQ", 30, 1)
    V.hdr("THE CAPACITY LADDER -- NQ 30m Donchian breakouts, purged walk-forward, 141 features")
    print(f"   {len(X):,} signals, {X.shape[1]} features, 6 purged+embargoed folds.")
    print(f"   Base rate {yw.mean():.1%} wins, {yR.mean():+.4f} R per trade taking every signal.\n")
    real = ladder(X, yR, yw, meta, shuffle=False)
    shuf = ladder(X, yR, yw, meta, shuffle=True, seed=11)
    print(f"   {'model':<24}{'REAL LABELS':>34}{'|':>3}{'SHUFFLED LABELS':>24}")
    print(f"   {'':<24}{'AUC':>7}{'IC':>8}{'R top50':>10}{'R top10':>9}{'|':>3}"
          f"{'AUC':>7}{'IC':>8}{'R top10':>9}")
    for name, _ in MODELS:
        a, b = real[name], shuf[name]
        print(f"   {name:<24}{a['auc']:>7.4f}{a['ic']:>+8.4f}{a['r_top50']:>+10.4f}"
              f"{a['r_top10']:>+9.4f}{'|':>3}{b['auc']:>7.4f}{b['ic']:>+8.4f}{b['r_top10']:>+9.4f}")
    print(f"\n   Taking EVERY signal earns {yR.mean():+.4f} R. A model is only worth its complexity")
    print( "   if 'R top50' or 'R top10' beats that -- and beats its own shuffled twin.")
    best = max((v["auc"], k) for k, v in real.items() if k != "constant (no model)")
    print(f"   Best AUC on real labels: {best[1]} at {best[0]:.4f}."
          f"  Its shuffled twin: {shuf[best[1]]['auc']:.4f}.")
    aucs = np.array([real[k]["auc"] for k, _ in MODELS[1:]])
    print(f"   Spread in AUC across the whole ladder (linear -> 6x256 deep): {aucs.max()-aucs.min():.4f}")


def locked_read(X, yR, yw, meta, spec, frac=0.65, top_q=0.5):
    """ONE read on the locked block. Trained on research only; nothing here is selected on."""
    u = np.unique(meta["sess"])
    cut = u[int(len(u) * frac)]
    res = meta["sess"] < cut
    lk = ~res
    Xv = X.to_numpy(float)
    sc = StandardScaler().fit(Xv[res])
    p = run_model(spec, sc.transform(Xv[res]), yw[res], sc.transform(Xv[lk]))
    thr = np.quantile(p, 1 - top_q)
    sel = p >= thr
    return dict(n_all=int(lk.sum()), r_all=float(yR[lk].mean()),
                n_sel=int(sel.sum()), r_sel=float(yR[lk][sel].mean()),
                auc=(roc_auc_score(yw[lk], p) if len(np.unique(yw[lk])) > 1 else np.nan))


def locked_table():
    V.hdr("THE LOCKED READ -- trained on research only, read ONCE. Two markets.")
    print("   `R all` is taking every breakout the rule gives. `R sel` is taking only the half the")
    print("   model prefers. The model has to beat the rule it is filtering, on unseen data.\n")
    print(f"   {'market':<8}{'model':<26}{'n all':>7}{'R all':>9}{'n sel':>7}{'R sel':>9}"
          f"{'delta':>9}{'AUC':>8}")
    for mkt, tf in (("NQ", 30), ("US30", 30)):
        try:
            X, yR, yw, meta = D.build(mkt, tf, 1)
        except Exception as e:
            print(f"   {mkt:<8}unavailable: {type(e).__name__} {e}")
            continue
        for name, spec in MODELS:
            if spec is None:
                continue
            r = locked_read(X, yR, yw, meta, spec)
            print(f"   {mkt:<8}{name:<26}{r['n_all']:>7}{r['r_all']:>+9.4f}{r['n_sel']:>7}"
                  f"{r['r_sel']:>+9.4f}{r['r_sel']-r['r_all']:>+9.4f}{r['auc']:>8.4f}")
        print()


if __name__ == "__main__":
    locked_table()


def mechanism():
    """WHY a model that genuinely beats chance on win/lose still loses money."""
    V.hdr("THE MECHANISM -- a better win-rate classifier is not a better strategy")
    print("   The label is win/lose. The P&L is not: a breakout system earns in the TAIL, so the")
    print("   trades a win-rate model dislikes are exactly the wide, slow, big ones. If the")
    print("   selected half has a HIGHER win rate and a LOWER mean R, that is the whole story.\n")
    print(f"   {'market':<8}{'model':<26}{'win% all':>10}{'win% sel':>10}{'R all':>9}"
          f"{'R sel':>9}{'p90 R all':>11}{'p90 R sel':>11}")
    for mkt, tf in (("NQ", 30), ("US30", 30)):
        try:
            X, yR, yw, meta = D.build(mkt, tf, 1)
        except Exception as e:
            print(f"   {mkt:<8}unavailable: {type(e).__name__} {e}")
            continue
        u = np.unique(meta["sess"])
        cut = u[int(len(u) * 0.65)]
        res, lk = meta["sess"] < cut, meta["sess"] >= cut
        Xv = X.to_numpy(float)
        for name, spec in (("random forest 300", "rf"), ("XGBoost 300 d3 (shallow)", ("xgb", 300, 3, 0.05))):
            sc = StandardScaler().fit(Xv[res])
            p = run_model(spec, sc.transform(Xv[res]), yw[res], sc.transform(Xv[lk]))
            sel = p >= np.median(p)
            rl, wl = yR[lk], yw[lk]
            print(f"   {mkt:<8}{name:<26}{wl.mean():>9.1%}{wl[sel].mean():>10.1%}"
                  f"{rl.mean():>+9.4f}{rl[sel].mean():>+9.4f}"
                  f"{np.quantile(rl,0.9):>+11.3f}{np.quantile(rl[sel],0.9):>+11.3f}")
    print()


if __name__ == "__main__":
    mechanism()


def selectivity_control(n_draws=400, seed=41):
    """The gate every filter on this branch has to clear: a RANDOM filter of the same selectivity.

    A model that keeps half the signals is a restrictive filter, and restrictiveness alone moves
    profit factor and mean R (STUDY_V12). The only honest question is whether the model's half beats
    a randomly chosen half of the same size, drawn from the same signals.
    """
    V.hdr("THE GATE -- the model's half against 400 RANDOM halves of the same size")
    print(f"   {'market':<8}{'model':<26}{'R sel':>9}{'ctrl mean':>11}{'ctrl p95':>10}"
          f"{'excess':>9}{'p':>7}")
    for mkt, tf in (("NQ", 30), ("US30", 30)):
        X, yR, yw, meta = D.build(mkt, tf, 1)
        u = np.unique(meta["sess"])
        cut = u[int(len(u) * 0.65)]
        res, lk = meta["sess"] < cut, meta["sess"] >= cut
        Xv = X.to_numpy(float)
        rl = yR[lk]
        rng = np.random.default_rng(seed)
        k = int(lk.sum()) // 2
        ctrl = np.array([rl[rng.choice(len(rl), k, replace=False)].mean() for _ in range(n_draws)])
        for name, spec in (("random forest 300", "rf"), ("LightGBM 400", "lgbm"),
                           ("XGBoost 300 d3 (shallow)", ("xgb", 300, 3, 0.05)),
                           ("MLP 6x256 (deeper)", ("mlp", 6, 256))):
            sc = StandardScaler().fit(Xv[res])
            p = run_model(spec, sc.transform(Xv[res]), yw[res], sc.transform(Xv[lk]))
            sel = p >= np.median(p)
            r = float(rl[sel].mean())
            print(f"   {mkt:<8}{name:<26}{r:>+9.4f}{ctrl.mean():>+11.4f}"
                  f"{np.quantile(ctrl,0.95):>+10.4f}{r-ctrl.mean():>+9.4f}"
                  f"{float((ctrl >= r).mean()):>7.3f}")
        print()
    print("   The control draws from the SAME locked signals, so it prices selectivity and the")
    print("   block's own drift at once. p is the share of random halves that did better.")


if __name__ == "__main__":
    selectivity_control()


def is_it_just_chop():
    """US30 passed the gate on all four models regardless of AUC. That is the signature of every
    model rediscovering ONE simple thing rather than four models each learning something.

    The obvious candidate is the regime state: CHOP is the only filter on this branch that has ever
    cleared a same-selectivity control on both blocks, and 74 of the 141 columns are volatility or
    regime readings. If the models' selection overlaps CHOP heavily, and CHOP alone earns the same
    excess, then 141 features and a gradient booster have reproduced a one-line condition.
    """
    import v21regime as RG
    V.hdr("IS THE US30 RESULT JUST CHOP? -- overlap with the one-line filter, and its own excess")
    for mkt in ("US30", "NQ"):
        X, yR, yw, meta = D.build(mkt, 30, 1)
        u = np.unique(meta["sess"])
        cut = u[int(len(u) * 0.65)]
        res, lk = meta["sess"] < cut, meta["sess"] >= cut
        Xv = X.to_numpy(float)
        chop = X["reg.chop14"].to_numpy()
        rl, cl = yR[lk], chop[lk]
        rng = np.random.default_rng(41)
        k = int(lk.sum()) // 2
        ctrl = np.array([rl[rng.choice(len(rl), k, replace=False)].mean() for _ in range(400)])
        # CHOP alone, matched to the SAME 50% selectivity so the comparison is like for like
        thr = np.median(cl)
        chop_sel = cl <= thr
        print(f"\n   {mkt}: {int(lk.sum())} locked signals, baseline {rl.mean():+.4f} R,"
              f" control mean {ctrl.mean():+.4f}")
        print(f"   {'selector':<30}{'n':>7}{'R':>10}{'excess':>9}{'p':>7}{'overlap w/ CHOP':>18}")
        r = float(rl[chop_sel].mean())
        print(f"   {'CHOP14 <= median (one line)':<30}{int(chop_sel.sum()):>7}{r:>+10.4f}"
              f"{r-ctrl.mean():>+9.4f}{float((ctrl>=r).mean()):>7.3f}{'1.000':>18}")
        for name, spec in (("random forest 300", "rf"), ("LightGBM 400", "lgbm"),
                           ("MLP 6x256 (deeper)", ("mlp", 6, 256))):
            sc = StandardScaler().fit(Xv[res])
            p = run_model(spec, sc.transform(Xv[res]), yw[res], sc.transform(Xv[lk]))
            sel = p >= np.median(p)
            r = float(rl[sel].mean())
            jac = (sel & chop_sel).sum() / max((sel | chop_sel).sum(), 1)
            print(f"   {name:<30}{int(sel.sum()):>7}{r:>+10.4f}{r-ctrl.mean():>+9.4f}"
                  f"{float((ctrl>=r).mean()):>7.3f}{jac:>18.3f}")


if __name__ == "__main__":
    is_it_just_chop()
