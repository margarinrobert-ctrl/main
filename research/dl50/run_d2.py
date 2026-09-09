"""Features, audit, then the deep-learning ladder on the 150-point target -- the only one above
break-even on research. Objective is the POINTS EARNED, never win/lose.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb
import xgboost as xgb

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dl50 import d50core as D, d50feat as FE  # noqa: E402

RNG = np.random.default_rng(50150)
TGT, HOLD = 150.0, 96


def purged(n, k=5, emb=40):
    edges = np.linspace(0, n, k + 1).astype(int)
    for i in range(k):
        te = np.arange(edges[i], edges[i + 1])
        tr = np.setdiff1d(np.arange(n), np.arange(max(0, te[0] - emb), min(n, te[-1] + emb + 1)))
        yield tr, te


def oof(X, y, mk, shuffle=False, seed=0):
    p = np.full(len(y), np.nan)
    yy = np.random.default_rng(seed).permutation(y) if shuffle else y
    sc = StandardScaler()
    for tr, te in purged(len(y)):
        m = mk()
        m.fit(sc.fit_transform(X[tr]), yy[tr])
        p[te] = m.predict(sc.transform(X[te]))
    return p


def ic(a, b):
    k = np.isfinite(a) & np.isfinite(b)
    return float(pd.Series(a[k]).corr(pd.Series(b[k]), method="spearman"))


def main():
    f = D.load(15)
    sess = np.unique(f.index.normalize())
    cut = pd.Timestamp(sess[int(0.75 * len(sess))])
    eh, el, ou, od, _ = D.signals(f, 20, 200)
    o, h, l, c = (f[k].to_numpy() for k in ("open", "high", "low", "close"))
    mod = f["mod"].to_numpy().astype(np.int64)
    eb, r, sd, hl, why, amb = D.walk(o, h, l, c, eh, el, ou, od, D.STOP_PTS, TGT, HOLD,
                                     D.COST, -1, -1, mod)
    sig = eb - 1
    ts = f.index[eb]
    res = np.asarray(ts < cut)

    probes = sorted(RNG.choice(np.arange(3000, 12000), size=6, replace=False))
    Xf, bad = FE.audit(f.iloc[:12000], probes, None or list(FE.build(f.iloc[:2000]).columns))
    tot = sum(bad.values())
    print(f"TRUNCATION AUDIT  mismatches {tot} / {len(probes)*len(bad)}   " +
          (", ".join(f"{k} {v}" for k, v in bad.items() if v) if tot else "all clean"))

    X = FE.build(f)
    cols = list(X.columns)
    E = X.iloc[sig][cols].reset_index(drop=True)
    print(f"events {len(r)}  research {res.sum()}  holdout {(~res).sum()}  features {len(cols)}")

    # base rates on the trigger's own bars
    deg = []
    for cn in cols:
        v = X[cn].to_numpy()
        pop = v[np.isfinite(v)]
        sv = E[cn].to_numpy()
        if len(pop) < 1000 or np.isfinite(sv).sum() < 200:
            deg.append(cn); continue
        share = float(np.nanmean(sv > np.nanmedian(pop)))
        if share > 0.95 or share < 0.05:
            deg.append(cn)
    print(f"degenerate on the trigger's own bars: {len(deg)}  {deg}")
    cols = [x for x in cols if x not in deg]

    C = E[cols].corr().abs()
    np.fill_diagonal(C.values, 0.0)
    dup = [(a, b) for a in C.index for b in C.columns if a < b and C.loc[a, b] > 0.97]
    for a, b in dup:
        print(f"  NEAR-DUPLICATE {a} == {b}  rho {C.loc[a, b]:.4f}")
    cols = [x for x in cols if x not in {b for _, b in dup}]
    print(f"pool -> {len(cols)}")

    A = E[cols].to_numpy(float)
    med = np.nanmedian(A[res], axis=0)
    A = np.where(np.isfinite(A), A, med)
    Xr, yr = A[res], r[res]

    mks = {
        "ridge": lambda: Ridge(alpha=10.0),
        "rf": lambda: RandomForestRegressor(n_estimators=300, max_depth=4, min_samples_leaf=40,
                                            max_features=0.5, random_state=0, n_jobs=4),
        "lgbm": lambda: lgb.LGBMRegressor(n_estimators=300, num_leaves=7, learning_rate=0.03,
                                          min_child_samples=40, subsample=0.8,
                                          colsample_bytree=0.6, verbose=-1, n_jobs=4),
        "xgb_d3": lambda: xgb.XGBRegressor(n_estimators=300, max_depth=3, learning_rate=0.03,
                                           subsample=0.8, colsample_bytree=0.6, n_jobs=4,
                                           verbosity=0),
        "mlp_2x32": lambda: MLPRegressor(hidden_layer_sizes=(32, 32), alpha=1e-2, max_iter=400, random_state=0),
        "mlp_2x64": lambda: MLPRegressor(hidden_layer_sizes=(64, 64), alpha=1e-2, max_iter=400, random_state=0),
        "mlp_4x128": lambda: MLPRegressor(hidden_layer_sizes=(128,) * 4, alpha=1e-2, max_iter=400, random_state=0),
    }
    print(f"\nLADDER (objective = points earned)   {'IC':>9}{'twin':>9}{'winner':>9}")
    preds, twins = {}, 0
    for nm, mk in mks.items():
        p = oof(Xr, yr, mk); q = oof(Xr, yr, mk, True, 7)
        a, b = ic(p, yr), ic(q, yr)
        preds[nm] = p; twins += int(b > a)
        print(f"  {nm:<32}{a:>9.4f}{b:>9.4f}{('TWIN' if b > a else 'real'):>9}")
    print(f"  twin wins {twins}/{len(mks)} = {twins/len(mks):.0%}   "
          "(above 50% = the noise floor is higher than the signal)")
    np.save("research/dl50/cols.npy", np.array(cols, object))
    pd.DataFrame({k: v for k, v in preds.items()}).to_csv("research/dl50/oof.csv", index=False)


if __name__ == "__main__":
    main()
