"""The deep-learning ladder inside 07:00-11:00 with the 11:00 flatten. 150-point target."""
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
from dl50.run_d2 import oof, ic  # noqa: E402

M0, M1, FLAT, HOLD, TGT = 420, 660, 660, 96, 150.0
RNG = np.random.default_rng(70011)
ND = 400


def main():
    f = D.load(15)
    sess = np.unique(f.index.normalize())
    cut = pd.Timestamp(sess[int(0.75 * len(sess))])
    o, h, l, c = (f[k].to_numpy() for k in ("open", "high", "low", "close"))
    mod = f["mod"].to_numpy().astype(np.int64)
    eh, el, ou, od, _ = D.signals(f, 20, 200)
    eb, r, sd, hl, why, amb = D.walk(o, h, l, c, eh, el, ou, od, D.STOP_PTS, TGT, HOLD,
                                     D.COST, M0, M1, mod, FLAT)
    sig = eb - 1
    ts = f.index[eb]
    res = np.asarray(ts < cut)
    X = FE.build(f)
    cols = list(X.columns)
    E = X.iloc[sig][cols].reset_index(drop=True)
    deg = [cn for cn in cols
           if (lambda sv, pop: len(pop) < 1000 or np.isfinite(sv).sum() < 200
               or float(np.nanmean(sv > np.nanmedian(pop))) > 0.95
               or float(np.nanmean(sv > np.nanmedian(pop))) < 0.05)(
                   E[cn].to_numpy(), X[cn].to_numpy()[np.isfinite(X[cn].to_numpy())])]
    cols = [x for x in cols if x not in deg]
    C = E[cols].corr().abs(); np.fill_diagonal(C.values, 0.0)
    dup = {b for a in C.index for b in C.columns if a < b and C.loc[a, b] > 0.97}
    cols = [x for x in cols if x not in dup]
    print(f"events {len(r)}  research {res.sum()}  holdout {(~res).sum()}  "
          f"features {len(cols)}  degenerate {len(deg)} {deg}")

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
        "mlp_2x32": lambda: MLPRegressor(hidden_layer_sizes=(32, 32), alpha=1e-2, max_iter=400,
                                         random_state=0),
        "mlp_2x64": lambda: MLPRegressor(hidden_layer_sizes=(64, 64), alpha=1e-2, max_iter=400,
                                         random_state=0),
        "mlp_4x128": lambda: MLPRegressor(hidden_layer_sizes=(128,) * 4, alpha=1e-2, max_iter=400,
                                          random_state=0),
    }
    print(f"\nLADDER inside 07:00-11:00 + flatten   {'IC':>9}{'twin':>9}{'winner':>9}")
    preds, twins = {}, 0
    for nm, mk in mks.items():
        p = oof(Xr, yr, mk); q = oof(Xr, yr, mk, True, 7)
        a, b = ic(p, yr), ic(q, yr)
        preds[nm] = p; twins += int(b > a)
        print(f"  {nm:<32}{a:>9.4f}{b:>9.4f}{('TWIN' if b > a else 'real'):>9}")
    print(f"  twin wins {twins}/{len(mks)} = {twins/len(mks):.0%}")

    best = max(preds, key=lambda k: ic(preds[k], yr))
    print(f"\nGATE 2 on the best model ({best}), veto, re-simulated vs a random gate")
    sr, dr = sig[res], sd[res]
    base = D.walk_at(o, h, l, c, sr.astype(np.int64), dr.astype(np.int64), D.STOP_PTS, TGT,
                     HOLD, D.COST, mod, FLAT)
    print(f"  base n {np.isfinite(base).sum()}  pts {np.nanmean(base):.3f}  PF {D.pf(base):.3f}")
    p = preds[best]
    for kf in (0.7, 0.5, 0.3):
        thr = np.nanquantile(p, 1 - kf)
        m = p >= thr
        q = D.walk_at(o, h, l, c, sr[m].astype(np.int64), dr[m].astype(np.int64), D.STOP_PTS,
                      TGT, HOLD, D.COST, mod, FLAT)
        ctl = np.empty(ND)
        for i in range(ND):
            pick = np.sort(RNG.choice(len(sr), size=int(m.sum()), replace=False))
            ctl[i] = np.nanmean(D.walk_at(o, h, l, c, sr[pick].astype(np.int64),
                                          dr[pick].astype(np.int64), D.STOP_PTS, TGT, HOLD,
                                          D.COST, mod, FLAT))
        mu = float(np.nanmean(q))
        print(f"  keep {kf:.0%}  n {int(np.isfinite(q).sum()):>5}  pts {mu:>7.3f}  "
              f"PF {D.pf(q):.3f}  ctl {np.nanmedian(ctl):>7.3f}  p {float(np.mean(ctl>=mu)):.3f}")


if __name__ == "__main__":
    main()
