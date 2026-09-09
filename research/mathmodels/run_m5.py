"""The drop-one says three of eight states carry it. Test the lean model, and the PORTABLE form.

Drop-one on research: removing kf.t costs -0.0252 IC, vr.ratio -0.0246, dfa.H -0.0236, while
removing ou.z, ou.kappa or pe.h IMPROVES the model. All three that carry are PERSISTENCE estimators
and the primary is a trend follower; the two mean-reversion states subtract. That is a coherent
reading, so it is worth testing directly rather than left as an ablation table.

A LightGBM cannot be written into Pine. V66 measured the portable RIDGE beating the unportable
forest, so both are run on the same three states and the ridge's constants are exported.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mathmodels import mmcore as M  # noqa: E402
from mathmodels.run_m2 import walk, walk_at, chan, COST  # noqa: E402
from mathmodels.run_m3 import oof, ic, TF, ENT, EMA, STOP, W  # noqa: E402
sys.path.append("/root/.claude/skills/synced/"
                "a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/"
                "mechanism-first-alpha/scripts")
import gates  # noqa: E402

RNG = np.random.default_rng(31337)
ND = 400
LEAN = ["kf.t", "vr.ratio", "dfa.H"]
TRIALS = 92


def day_boot(r, ts, nb=1500):
    d = pd.Series(r, index=pd.DatetimeIndex(ts).normalize())
    g = [v.to_numpy() for _, v in d.groupby(level=0)]
    out = np.empty(nb)
    for i in range(nb):
        p = RNG.integers(0, len(g), len(g))
        out[i] = np.nanmean(np.concatenate([g[j] for j in p]))
    return out


def main():
    f = M.load("US30L", TF)
    s = np.unique(f.index.normalize())
    cut = pd.Timestamp(s[int(0.75 * len(s))])
    o, h, l, c = (f[k].to_numpy() for k in ("open", "high", "low", "close"))
    at = f["atr"].to_numpy()
    xh, xl = chan(h, l, 20); eh, el = chan(h, l, ENT)
    e = pd.Series(c).ewm(span=EMA, adjust=False).mean().to_numpy()
    ou = (c > e).astype(np.int64); od = (c < e).astype(np.int64)
    eb, r, sd, hl = walk(o, h, l, c, at, eh, el, xh, xl, ou, od, STOP, COST)
    sig = eb - 1; ts = f.index[eb]
    res = np.asarray(ts < cut)
    S = M.states(f, W)
    X = S.iloc[sig][LEAN].to_numpy(float)
    med = np.nanmedian(X[res], axis=0)
    X = np.where(np.isfinite(X), X, med)
    Xr, yr = X[res], r[res]
    sr, dr = sig[res], sd[res]
    sh, dh = sig[~res], sd[~res]

    mks = {"ridge-3": lambda: Ridge(alpha=10.0),
           "lgbm-3": lambda: lgb.LGBMRegressor(n_estimators=250, num_leaves=7,
                                               learning_rate=0.03, min_child_samples=30,
                                               subsample=0.8, colsample_bytree=0.7,
                                               verbose=-1, n_jobs=4)}

    def rgate(sb, db, k):
        out = np.empty(ND)
        for i in range(ND):
            p = np.sort(RNG.choice(len(sb), size=k, replace=False))
            out[i] = np.nanmean(walk_at(o, h, l, c, at, xh, xl, sb[p].astype(np.int64),
                                        db[p].astype(np.int64), STOP, COST))
        return out

    base_r = walk_at(o, h, l, c, at, xh, xl, sr.astype(np.int64), dr.astype(np.int64), STOP, COST)
    base_h = walk_at(o, h, l, c, at, xh, xl, sh.astype(np.int64), dh.astype(np.int64), STOP, COST)
    print(f"three states {LEAN}\n")
    print(f"{'model':<10}{'blk':<10}{'n':>6}{'%/trade':>9}{'PF':>7}{'total':>9}"
          f"{'p90':>7}{'kept':>7}{'ctl':>9}{'p':>7}{'P(<=0)':>8}")
    for tag, x, tsx in (("base", base_r, ts[res]), ):
        b = day_boot(x, tsx)
        print(f"{'(none)':<10}{'research':<10}{len(x):>6}{np.nanmean(x):>9.4f}{M.pf(x):>7.3f}"
              f"{np.nansum(x):>9.2f}{np.nanpercentile(x, 90):>7.3f}{1.0:>7.2f}"
              f"{'':>9}{'':>7}{float((b <= 0).mean()):>8.3f}")
    b = day_boot(base_h, ts[~res])
    print(f"{'(none)':<10}{'HOLDOUT':<10}{len(base_h):>6}{np.nanmean(base_h):>9.4f}"
          f"{M.pf(base_h):>7.3f}{np.nansum(base_h):>9.2f}"
          f"{np.nanpercentile(base_h, 90):>7.3f}{1.0:>7.2f}{'':>9}{'':>7}"
          f"{float((b <= 0).mean()):>8.3f}")

    out = {}
    for nm, mk in mks.items():
        p = oof(Xr, yr, mk)
        icr = ic(p, yr)
        thr = float(np.nanquantile(p, 0.70))
        mr = p >= thr
        kr = walk_at(o, h, l, c, at, xh, xl, sr[mr].astype(np.int64),
                     dr[mr].astype(np.int64), STOP, COST)
        ctl = rgate(sr, dr, int(mr.sum())); bo = day_boot(kr, ts[res][mr])
        print(f"{nm:<10}{'research':<10}{int(mr.sum()):>6}{np.nanmean(kr):>9.4f}{M.pf(kr):>7.3f}"
              f"{np.nansum(kr):>9.2f}{np.nanpercentile(kr, 90):>7.3f}{mr.mean():>7.2f}"
              f"{np.nanmedian(ctl):>9.4f}{float(np.mean(ctl >= np.nanmean(kr))):>7.3f}"
              f"{float((bo <= 0).mean()):>8.3f}")
        sc = StandardScaler().fit(Xr)
        mdl = mk().fit(sc.transform(Xr), yr)
        ph = mdl.predict(sc.transform(X[~res]))
        mh = ph >= thr
        kh = walk_at(o, h, l, c, at, xh, xl, sh[mh].astype(np.int64),
                     dh[mh].astype(np.int64), STOP, COST)
        ctl = rgate(sh, dh, int(mh.sum())); bo = day_boot(kh, ts[~res][mh])
        print(f"{nm:<10}{'HOLDOUT':<10}{int(mh.sum()):>6}{np.nanmean(kh):>9.4f}{M.pf(kh):>7.3f}"
              f"{np.nansum(kh):>9.2f}{np.nanpercentile(kh, 90):>7.3f}{mh.mean():>7.2f}"
              f"{np.nanmedian(ctl):>9.4f}{float(np.mean(ctl >= np.nanmean(kh))):>7.3f}"
              f"{float((bo <= 0).mean()):>8.3f}")
        print(f"{'':10}research IC {icr:+.4f}   holdout IC {ic(ph, r[~res]):+.4f}")
        out[nm] = (kh, mdl, sc, thr)

    print("\nDEFLATION")
    for nm, (kh, mdl, sc, thr) in out.items():
        rr = kh[np.isfinite(kh)]
        sp = float(np.mean(rr) / (np.std(rr, ddof=1) + 1e-12))
        try:
            g = gates.deflated_sharpe(sp, len(rr), TRIALS, var_trials=0.0025,
                                      skew=float(pd.Series(rr).skew()),
                                      kurtosis=float(pd.Series(rr).kurtosis() + 3),
                                      avg_correlation=0.7)
            print(f"  {nm:<10} SR/trade {sp:+.4f}  E[max|noise] "
                  f"{g['expected_max_sr_under_null']:.4f}  DSR {g['dsr']:.4f}  {g['verdict']}")
        except Exception as ex:                                  # noqa: BLE001
            print(f"  {nm}: {ex}")

    print("\nTHE PORTABLE FORM -- ridge constants on the three states, research-fitted")
    sc = StandardScaler().fit(Xr)
    rg = Ridge(alpha=10.0).fit(sc.transform(Xr), yr)
    for i, cn in enumerate(LEAN):
        u = ic(Xr[:, i], yr)
        print(f"  {cn:<10} mean {sc.mean_[i]:+.6f}  scale {sc.scale_[i]:.6f}  "
              f"coef {rg.coef_[i]:+.6f}   univariate IC {u:+.4f}"
              f"{'   SIGN FLIPPED vs its own IC' if np.sign(u) != np.sign(rg.coef_[i]) else ''}")
    print(f"  intercept {rg.intercept_:+.6f}")


if __name__ == "__main__":
    main()
