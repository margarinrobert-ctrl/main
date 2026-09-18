"""GATE 2 -- the meta layer on the Donchian+ATR event stream. Research block only.

Objective is the R EARNED (here: percent of entry price actually earned), not win/lose -- a
win/lose model is a win-rate optimiser and this branch has measured it trimming the tail four
times (V28, V32, EMA48, V66).

Every model runs beside a SHUFFLED-LABEL TWIN. Above 50% twin wins means the noise floor is
higher than the signal. Scoring is the VETO framing, re-simulated end to end, against a random
gate of the SAME selectivity -- refusing a signal releases the position lock and admits a later
breakout the unfiltered run never saw.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb
import xgboost as xgb

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vpus30 import vpdon as D  # noqa: E402
from vpus30.run_d2 import build_all, ENT_N, EX_N, SL  # noqa: E402
from vpus30.run_v2 import purged_folds  # noqa: E402

RNG = np.random.default_rng(31337)
BAR = "=" * 96


def fam(c):
    return c.split(".")[0] if "." in c else "vp"


def models():
    return {
        "ridge": lambda: Ridge(alpha=10.0),
        "rf": lambda: RandomForestRegressor(n_estimators=300, max_depth=4, min_samples_leaf=40,
                                            max_features=0.5, random_state=0, n_jobs=4),
        "lgbm": lambda: lgb.LGBMRegressor(n_estimators=250, num_leaves=7, learning_rate=0.03,
                                          min_child_samples=40, subsample=0.8,
                                          colsample_bytree=0.6, verbose=-1, n_jobs=4),
        "xgb": lambda: xgb.XGBRegressor(n_estimators=250, max_depth=3, learning_rate=0.03,
                                        subsample=0.8, colsample_bytree=0.6, n_jobs=4,
                                        verbosity=0),
    }


def oof(Xm, y, mk, shuffle=False, seed=0):
    n = len(y)
    p = np.full(n, np.nan)
    yy = y.copy()
    if shuffle:
        yy = np.random.default_rng(seed).permutation(y)
    sc = StandardScaler()
    for tr, te in purged_folds(n, 5, 40):
        m = mk()
        Xtr = sc.fit_transform(Xm[tr]); Xte = sc.transform(Xm[te])
        m.fit(Xtr, yy[tr])
        p[te] = m.predict(Xte)
    return p


def ic(a, b):
    k = np.isfinite(a) & np.isfinite(b)
    return float(pd.Series(a[k]).corr(pd.Series(b[k]), method="spearman"))


def main():
    f, g, cut, X, t, best_d = build_all()
    pool = pd.read_csv("research/vpus30/don_pool.csv", header=None)[0].tolist()
    ts = pd.DatetimeIndex(t.ts)
    res = np.asarray(ts < cut)
    sig = t.sig.to_numpy(); sd = t.side.to_numpy()
    E = X.iloc[sig][pool].reset_index(drop=True)
    y = t.pct.to_numpy()

    print(f"events {len(t)}  research {res.sum()}  holdout {(~res).sum()}  pool {len(pool)}")

    # ---- redundancy measured ON THE SIGNAL BARS
    print("\n" + BAR + "\nREDUNDANCY on the signal bars\n" + BAR)
    C = E[res].corr().abs()
    np.fill_diagonal(C.values, 0.0)
    dup = [(a, b, C.loc[a, b]) for a in C.index for b in C.columns
           if a < b and C.loc[a, b] > 0.995]
    for a, b, r in dup:
        print(f"  EXACT DUPLICATE  {a} == {b}   rho {r:.4f}")
    drop = {b for _, b, _ in dup}
    pool = [c for c in pool if c not in drop]
    E = E[pool]
    print(f"  collapsed {len(drop)} -> pool {len(pool)}")

    Xm = E.to_numpy(float)
    med = np.nanmedian(Xm[res], axis=0)
    Xm = np.where(np.isfinite(Xm), Xm, med)
    Xr, yr = Xm[res], y[res]

    # ---- ladder, each beside a shuffled twin
    print("\n" + BAR + "\nMODEL LADDER -- OOF IC on research, real vs shuffled twin\n" + BAR)
    print(f"{'model':<8}{'IC':>9}{'twin':>9}{'winner':>10}")
    preds, twins = {}, 0
    for nm, mk in models().items():
        p = oof(Xr, yr, mk)
        q = oof(Xr, yr, mk, shuffle=True, seed=7)
        a, b = ic(p, yr), ic(q, yr)
        preds[nm] = p
        twins += int(b > a)
        print(f"{nm:<8}{a:>9.4f}{b:>9.4f}{('TWIN' if b > a else 'real'):>10}")
    print(f"  twin wins {twins} of {len(preds)} = {twins/len(preds):.0%}  (above 50% = noise floor)")

    # ---- Gate 2, veto framing, same-selectivity random gate
    print("\n" + BAR + "\nGATE 2 -- veto, re-simulated, vs a random gate of the same size\n" + BAR)
    sr, dr = sig[res], sd[res]
    base_r, _ = D.walk_at(g, sr, dr, ex_n=EX_N, sl=SL)
    print(f"base (no veto): n {np.isfinite(base_r).sum()}  net% {np.nanmean(base_r):.4f}"
          f"  PF {D.pf(base_r):.3f}")

    def rand_gate(k, nd=400):
        out = np.empty(nd)
        for i in range(nd):
            pick = RNG.choice(len(sr), size=k, replace=False)
            r, _ = D.walk_at(g, sr[pick], dr[pick], ex_n=EX_N, sl=SL)
            out[i] = np.nanmean(r) if np.isfinite(r).sum() >= 5 else np.nan
        return out

    print(f"{'model':<8}{'keep':>6}{'n':>6}{'net%':>9}{'PF':>7}{'uplift':>9}{'ctl':>9}{'p':>7}")
    rows = []
    for nm, p in preds.items():
        for kf in (0.7, 0.5, 0.3):
            k = int(kf * len(sr))
            thr = np.nanquantile(p, 1 - kf)
            m = p >= thr
            r, _ = D.walk_at(g, sr[m], dr[m], ex_n=EX_N, sl=SL)
            mu = float(np.nanmean(r))
            ctl = rand_gate(int(m.sum()), 250)
            pv = float(np.nanmean(ctl >= mu))
            rows.append(dict(model=nm, keep=kf, n=int(np.isfinite(r).sum()), mu=mu,
                             pf=D.pf(r), up=mu - float(np.nanmean(base_r)),
                             ctl=float(np.nanmedian(ctl)), p=pv, thr=float(thr)))
            print(f"{nm:<8}{kf:>6.1f}{rows[-1]['n']:>6}{mu:>9.4f}{rows[-1]['pf']:>7.3f}"
                  f"{rows[-1]['up']:>9.4f}{rows[-1]['ctl']:>9.4f}{pv:>7.3f}")
    R = pd.DataFrame(rows)
    R.to_csv("research/vpus30/gate2_don.csv", index=False)
    print(f"\ncells clearing p<=0.05: {int((R.p <= 0.05).sum())} of {len(R)}"
          f"  (expected {0.05*len(R):.1f})")
    np.save("research/vpus30/don_pool_final.npy", np.array(pool, object))


if __name__ == "__main__":
    main()
