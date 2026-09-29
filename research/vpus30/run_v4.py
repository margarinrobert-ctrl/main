"""V4 -- the 52-feature quant meta layer on NAKEDPOC, the best primary of the five."""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb, xgboost as xgb
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vpus30 import vpcore as V, vpquant as Q  # noqa: E402
from vpus30.run_v2 import purged_folds  # noqa: E402
pd.set_option("display.width", 220)


def main():
    f = V.load(); d = V.sessions(f); g = V.features(f, d)
    sess = np.sort(d.sess.unique()); cut = pd.Timestamp(sess[int(0.75 * len(sess))])
    X, dd, _ = Q.build(g, cut)
    ALL = pd.concat([g[V.FEATS], X], axis=1).replace([np.inf, -np.inf], np.nan)
    idx, side = V.events_guide(f, g, d, "nakedpoc")
    t = V.walk(g, idx, side)
    F = ALL.iloc[t.e_bar.to_numpy() - 1].reset_index(drop=True)   # SIGNAL bar, not the fill bar
    y = t.R.to_numpy(); ts = pd.DatetimeIndex(t.ts); res = np.asarray(ts < cut)
    F = F.fillna(F[res].median()).fillna(0.0)
    Xr, yr = F[res].to_numpy(), y[res]
    Xk, yk = F[~res].to_numpy(), y[~res]
    sc = StandardScaler().fit(Xr); Xrs = sc.transform(Xr)
    print("=" * 104)
    print(f"NAKEDPOC meta layer -- {ALL.shape[1]} features, purged embargoed CV, shuffled twins")
    print(f"  research {res.sum()} events / holdout {(~res).sum()}   fracdiff d {dd}")
    print("=" * 104)
    rng = np.random.default_rng(1)
    mk = {"ridge": lambda: Ridge(alpha=10.0),
          "rf": lambda: RandomForestRegressor(n_estimators=300, max_depth=4, min_samples_leaf=40,
                                              n_jobs=4, random_state=0),
          "lightgbm": lambda: lgb.LGBMRegressor(n_estimators=250, num_leaves=8, learning_rate=0.03,
                                                min_child_samples=40, verbose=-1, n_jobs=4,
                                                random_state=0),
          "xgb_d3": lambda: xgb.XGBRegressor(n_estimators=250, max_depth=3, learning_rate=0.03,
                                             min_child_weight=20, n_jobs=4, random_state=0,
                                             verbosity=0)}
    print(f"  {'model':<12}{'OOF IC':>10}{'shuffled twin':>16}{'twin wins':>11}")
    oof = {}
    for nm, mkf in mk.items():
        for tag, yy in (("real", yr), ("shuf", rng.permutation(yr))):
            p = np.full(len(yy), np.nan)
            for tr, te in purged_folds(len(yy)):
                m = mkf(); m.fit(Xrs[tr], yy[tr]); p[te] = m.predict(Xrs[te])
            ic = float(pd.Series(p).corr(pd.Series(yr), method="spearman"))
            if tag == "real":
                oof[nm] = (p, ic)
            else:
                tw = ic
        print(f"  {nm:<12}{oof[nm][1]:>+10.4f}{tw:>+16.4f}{str(tw > oof[nm][1]):>11}")
    best = max(oof, key=lambda k: oof[k][1])
    p = oof[best][0]
    print(f"\n  best {best} ({oof[best][1]:+.4f})")
    print(f"\n  GATE 2 -- veto, re-simulated, against a same-selectivity RANDOM veto")
    print(f"  {'keep':<8}{'n':>7}{'R/ev':>10}{'uplift':>10}{'PF':>8}{'rand p':>9}")
    base = float(yr.mean())
    print(f"  {'base':<8}{len(yr):>7}{base:>+10.4f}{'':>10}"
          f"{float(yr[yr>0].sum()/max(-yr[yr<0].sum(),1e-12)):>8.3f}")
    sig_bars = t.e_bar.to_numpy() - 1
    for keep in (0.7, 0.5, 0.3):
        thr = np.nanquantile(p, 1 - keep)
        sel = p >= thr
        kb = sig_bars[res][sel]; ks = t.side.to_numpy()[res][sel]
        tv_ = V.walk(g, kb, ks)
        obs = float(tv_.R.mean())
        rp = np.array([float(V.walk(g, np.sort(rng.choice(sig_bars[res], len(kb), replace=False)),
                                    rng.permutation(t.side.to_numpy()[res])[:len(kb)]).R.mean())
                       for _ in range(200)])
        print(f"  {keep:<8.2f}{len(tv_):>7}{obs:>+10.4f}{obs-base:>+10.4f}"
              f"{float(tv_.R[tv_.R>0].sum()/max(-tv_.R[tv_.R<0].sum(),1e-12)):>8.3f}"
              f"{float((rp >= obs).mean()):>9.3f}")
    m = mk[best](); m.fit(Xrs, yr); pk = m.predict(sc.transform(Xk))
    thr = np.nanquantile(p, 0.5)
    kb = sig_bars[~res][pk >= thr]; ks = t.side.to_numpy()[~res][pk >= thr]
    tkk = V.walk(g, kb, ks); tbb = V.walk(g, sig_bars[~res], t.side.to_numpy()[~res])
    print(f"\n  ONE HOLDOUT READ")
    print(f"    base    n {len(tbb):>4}  R/ev {tbb.R.mean():+.4f}  PF "
          f"{float(tbb.R[tbb.R>0].sum()/max(-tbb.R[tbb.R<0].sum(),1e-12)):.3f}")
    print(f"    kept50  n {len(tkk):>4}  R/ev {tkk.R.mean():+.4f}  PF "
          f"{float(tkk.R[tkk.R>0].sum()/max(-tkk.R[tkk.R<0].sum(),1e-12)):.3f}"
          f"   kept {len(kb)/max(len(sig_bars[~res]),1):.3f} of a 0.50 target")


if __name__ == "__main__":
    main()
