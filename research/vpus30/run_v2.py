"""V2 -- the meta layer on the LVN primary. 52 features, purged embargoed CV, shuffled twins.

The LVN primary is chosen because it is the better of the TWO tested at Gate 1 (control p 0.200
against HVN's 0.440). That is one selection and it is counted.

Objective is the R EARNED, not win/lose: a win/lose model is a win-rate optimiser and this branch
has measured it trimming the tail three separate times (V28, V32, EMA48).
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
from vpus30 import vpcore as V, vpquant as Q  # noqa: E402
sys.path.append("/root/.claude/skills/synced/"
                "a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/"
                "mechanism-first-alpha/scripts")
import gates  # noqa: E402

pd.set_option("display.width", 220)
BAR = "=" * 104


def hdr(t):
    print("\n" + BAR + "\n" + t + "\n" + BAR)


def purged_folds(n, k=5, embargo=50):
    """Contiguous folds with the training rows adjacent to each test fold removed. Labels overlap
    in time, so a plain K-fold trains on the answer."""
    edges = np.linspace(0, n, k + 1).astype(int)
    for i in range(k):
        te = np.arange(edges[i], edges[i + 1])
        tr = np.setdiff1d(np.arange(n), np.arange(max(0, te[0] - embargo),
                                                  min(n, te[-1] + embargo + 1)))
        yield tr, te


def main():
    f = V.load(); d = V.sessions(f); g = V.features(f, d)
    sess = np.sort(d.sess.unique())
    cut = pd.Timestamp(sess[int(0.75 * len(sess))])
    X, dd, hp = Q.build(g, cut)
    ALL = pd.concat([g[V.FEATS], X], axis=1)
    print(f"  features {ALL.shape[1]}  ({len(V.FEATS)} volume-profile + {X.shape[1]} quant)"
          f"   fracdiff d {dd}")

    idx, side = V.events(g, "lvn")
    t = V.walk(g, idx, side)
    sig = idx[:len(t)] if len(idx) == len(t) else None
    # rebuild the signal->trade map so features are read at the SIGNAL bar, never the fill bar
    taken = V.walk(g, idx, side, lock=True)
    ok = np.isin(np.arange(len(idx)), np.arange(len(idx)))
    E = ALL.iloc[idx].reset_index(drop=True)
    tt = V.walk(g, idx, side)
    # align: walk() drops untaken rows, so re-derive which events were taken
    eb_all, xb_all, ep, xp, rk, wy, tk = V._walk(
        g["open"].to_numpy(), g["high"].to_numpy(), g["low"].to_numpy(), g["close"].to_numpy(),
        g["atr"].to_numpy(), g["bar_in_sess"].to_numpy(),
        np.concatenate([np.full(e - s, e - s) for s, e in zip(
            np.flatnonzero(np.r_[True, g["sess"].to_numpy()[1:] != g["sess"].to_numpy()[:-1]]),
            np.r_[np.flatnonzero(np.r_[True, g["sess"].to_numpy()[1:] != g["sess"].to_numpy()[:-1]])[1:],
                  len(g)])]),
        idx, side, 1.5, 0.0, V.RT_POINTS, 1)
    m = tk == 1
    F = ALL.iloc[idx[m]].reset_index(drop=True)
    y = (side[m] * (xp[m] - ep[m]) - V.RT_POINTS) / rk[m]
    ts = g.index[eb_all[m]]
    res = np.asarray(ts < cut)
    print(f"  events taken {m.sum():,}   research {res.sum():,} / holdout {(~res).sum():,}")

    hdr("V2.1  TRUNCATION AUDIT on the quant layer")
    Xa, _, _ = Q.build(g.iloc[:40000], cut)
    lim = 39000
    bad = 0
    for cnm in X.columns:
        if cnm.startswith(("ffd.", "hmm.")):     # fitted objects: parameters are block-scoped
            continue
        a = X[cnm].to_numpy()[:lim]; b = Xa[cnm].to_numpy()[:lim]
        k = np.isfinite(a) & np.isfinite(b)
        if k.sum() and np.nanmax(np.abs(a[k] - b[k])) > 1e-9:
            bad += 1
    print(f"  rolling/causal features rebuilt on a truncated frame: {bad} mismatches "
          f"of {len([c for c in X.columns if not c.startswith(('ffd.','hmm.'))])}")
    print("  (ffd. and hmm. are excluded BY DESIGN -- their parameters are estimated on the")
    print("   research block, so a truncated refit is a different estimator, not a leak.)")

    Fv = F.replace([np.inf, -np.inf], np.nan)
    med = Fv[res].median()
    Fv = Fv.fillna(med).fillna(0.0)
    Xr, yr = Fv[res].to_numpy(), y[res]
    Xk, yk = Fv[~res].to_numpy(), y[~res]

    hdr("V2.2  MODEL LADDER -- purged embargoed CV, each model beside its SHUFFLED twin")
    print("  IC = Spearman(prediction, R earned) out of fold. The twin re-runs the identical model")
    print("  on permuted labels; a twin that wins means the noise floor is above the signal.\n")
    print(f"  {'model':<16}{'OOF IC':>10}{'shuffled twin':>16}{'twin wins':>11}")
    rng = np.random.default_rng(0)
    models = {
        "ridge": lambda: Ridge(alpha=10.0),
        "rf": lambda: RandomForestRegressor(n_estimators=300, max_depth=4, min_samples_leaf=40,
                                            n_jobs=4, random_state=0),
        "lightgbm": lambda: lgb.LGBMRegressor(n_estimators=250, num_leaves=8, learning_rate=0.03,
                                              min_child_samples=40, verbose=-1, n_jobs=4,
                                              random_state=0),
        "xgb_d3": lambda: xgb.XGBRegressor(n_estimators=250, max_depth=3, learning_rate=0.03,
                                           min_child_weight=20, n_jobs=4, random_state=0,
                                           verbosity=0),
    }
    sc = StandardScaler().fit(Xr)
    Xrs = sc.transform(Xr)
    oof = {}
    for nm, mk in models.items():
        for tag, yy in (("real", yr), ("shuf", rng.permutation(yr))):
            p = np.full(len(yy), np.nan)
            for tr, te in purged_folds(len(yy)):
                mdl = mk()
                mdl.fit(Xrs[tr], yy[tr])
                p[te] = mdl.predict(Xrs[te])
            ic = float(pd.Series(p).corr(pd.Series(yr), method="spearman"))
            if tag == "real":
                oof[nm] = (p, ic)
            else:
                twin = ic
        print(f"  {nm:<16}{oof[nm][1]:>+10.4f}{twin:>+16.4f}"
              f"{str(twin > oof[nm][1]):>11}")

    best = max(oof, key=lambda k: oof[k][1])
    print(f"\n  best by OOF IC: {best} ({oof[best][1]:+.4f})")

    hdr("V2.3  GATE 2 -- uplift on UNSIZED returns, scored as a VETO and re-simulated")
    print("  A filter is a VETO, not a subset of realised trades: refusing a signal releases the")
    print("  position lock and admits a later event the unfiltered run never saw (STUDY_AUCTION).\n")
    p = oof[best][0]
    ev_idx = idx[m]
    print(f"  {'keep':<8}{'n':>7}{'R/ev':>10}{'uplift':>10}{'PF':>8}{'boot p':>9}{'rand p':>9}")
    base_R = float(yr.mean())
    base_pf = float(yr[yr > 0].sum() / max(-yr[yr < 0].sum(), 1e-12))
    print(f"  {'base':<8}{len(yr):>7}{base_R:>+10.4f}{'':>10}{base_pf:>8.3f}")
    res_ev = ev_idx[res]
    for keep in (0.7, 0.5, 0.3):
        thr = np.nanquantile(p, 1 - keep)
        sel = p >= thr
        kept_ev = res_ev[sel]
        ks = side[m][res][sel]
        tv_ = V.walk(g, kept_ev, ks)
        obs = float(tv_.R.mean())
        # bootstrap over days
        dd_ = pd.DatetimeIndex(tv_.ts).normalize()
        grp = [v.R.to_numpy() for _, v in tv_.groupby(dd_)]
        bs = np.array([np.concatenate([grp[i] for i in rng.integers(0, len(grp), len(grp))]).mean()
                       for _ in range(800)])
        bp = float((bs <= base_R).mean())
        # same-selectivity RANDOM veto, re-simulated
        rp = []
        for s_ in range(200):
            pick = np.sort(rng.choice(len(res_ev), size=len(kept_ev), replace=False))
            cv = V.walk(g, res_ev[pick], side[m][res][pick])
            rp.append(float(cv.R.mean()))
        rp = np.array(rp)
        print(f"  {keep:<8.2f}{len(tv_):>7}{obs:>+10.4f}{obs-base_R:>+10.4f}"
              f"{float(tv_.R[tv_.R>0].sum()/max(-tv_.R[tv_.R<0].sum(),1e-12)):>8.3f}"
              f"{bp:>9.3f}{float((rp >= obs).mean()):>9.3f}")

    hdr("V2.4  ONE HOLDOUT READ + deflation")
    mdl = models[best]()
    mdl.fit(Xrs, yr)
    pk = mdl.predict(sc.transform(Xk))
    thr = np.nanquantile(oof[best][0], 0.5)
    kev = ev_idx[~res][pk >= thr]
    ks = side[m][~res][pk >= thr]
    tk_ = V.walk(g, kev, ks)
    tb_ = V.walk(g, ev_idx[~res], side[m][~res])
    print(f"  holdout base    n {len(tb_):>5}  R/ev {tb_.R.mean():+.4f}  PF "
          f"{float(tb_.R[tb_.R>0].sum()/max(-tb_.R[tb_.R<0].sum(),1e-12)):.3f}")
    print(f"  holdout kept50  n {len(tk_):>5}  R/ev {tk_.R.mean():+.4f}  PF "
          f"{float(tk_.R[tk_.R>0].sum()/max(-tk_.R[tk_.R<0].sum(),1e-12)):.3f}"
          f"   kept {len(kev)/max(len(ev_idx[~res]),1):.3f} of a 0.50 target")
    sr = np.array([oof[k][1] for k in oof])
    dsr = gates.deflated_sharpe(sr_hat=float(yr.mean() / yr.std(ddof=1)), T=len(yr),
                                n_trials=14, var_trials=float(np.var(sr, ddof=1)) + 1e-6,
                                skew=float(pd.Series(yr).skew()),
                                kurtosis=float(pd.Series(yr).kurt() + 3.0))
    print(f"\n  trials counted 14 (2 primaries x 2 geometries + 4 models x 2 twins + 3 keep rungs)")
    print(f"  SR/event {dsr['sr_hat']:+.5f}   E[max|noise] {dsr['expected_max_sr_under_null']:+.5f}"
          f"   DSR {dsr['dsr']:.4f}   {dsr['verdict']}")


if __name__ == "__main__":
    main()
