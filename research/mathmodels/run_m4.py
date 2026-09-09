"""ONE holdout read of the Gate-2 survivor, with calibration, drop-one, tail and deflation.

The threshold is fixed on research and applied unchanged. Everything is scored as a VETO and
re-simulated, and the null is a random gate keeping the same number of events.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
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

RNG = np.random.default_rng(4242)
ND = 400
KEEP = 0.30
TRIALS = 80


def mk():
    return lgb.LGBMRegressor(n_estimators=250, num_leaves=7, learning_rate=0.03,
                             min_child_samples=30, subsample=0.8, colsample_bytree=0.7,
                             verbose=-1, n_jobs=4)


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

    keep = list(np.load("research/mathmodels/keep.npy", allow_pickle=True))
    S = M.states(f, W)
    X = S.iloc[sig][keep].to_numpy(float)
    med = np.nanmedian(X[res], axis=0)
    X = np.where(np.isfinite(X), X, med)
    Xr, yr = X[res], r[res]
    sr, dr = sig[res], sd[res]
    sh, dh = sig[~res], sd[~res]

    print(f"features {keep}")

    # --- drop-one on research, so the holdout is read once and only once
    p_full = oof(Xr, yr, mk)
    base_ic = ic(p_full, yr)
    print(f"\nDROP-ONE (research OOF IC, full = {base_ic:.4f})")
    for i, cn in enumerate(keep):
        sub = [j for j in range(len(keep)) if j != i]
        v = ic(oof(Xr[:, sub], yr, mk), yr)
        print(f"  minus {cn:<14}{v:>9.4f}   delta {v - base_ic:+.4f}")

    thr = float(np.nanquantile(p_full, 1 - KEEP))
    m_r = p_full >= thr
    base_r = walk_at(o, h, l, c, at, xh, xl, sr.astype(np.int64), dr.astype(np.int64), STOP, COST)
    kept_r = walk_at(o, h, l, c, at, xh, xl, sr[m_r].astype(np.int64),
                     dr[m_r].astype(np.int64), STOP, COST)

    # --- fit once on research, apply to the holdout. ONE READ.
    sc = StandardScaler().fit(Xr)
    mdl = mk().fit(sc.transform(Xr), yr)
    p_h = mdl.predict(sc.transform(X[~res]))
    m_h = p_h >= thr
    base_h = walk_at(o, h, l, c, at, xh, xl, sh.astype(np.int64), dh.astype(np.int64), STOP, COST)
    kept_h = walk_at(o, h, l, c, at, xh, xl, sh[m_h].astype(np.int64),
                     dh[m_h].astype(np.int64), STOP, COST)

    def rgate(sigb, sideb, k):
        out = np.empty(ND)
        for i in range(ND):
            p = np.sort(RNG.choice(len(sigb), size=k, replace=False))
            out[i] = np.nanmean(walk_at(o, h, l, c, at, xh, xl, sigb[p].astype(np.int64),
                                        sideb[p].astype(np.int64), STOP, COST))
        return out

    print(f"\n{'':22}{'n':>6}{'%/trade':>9}{'PF':>7}{'total':>9}{'p90 R':>8}"
          f"{'ctl':>9}{'p':>7}{'P(<=0)':>8}")
    for tag, bb, kk, sb, db, mm, tsx in (
            ("research base", base_r, None, sr, dr, None, ts[res]),
            ("research kept 30%", base_r, kept_r, sr, dr, m_r, ts[res]),
            ("HOLDOUT base", base_h, None, sh, dh, None, ts[~res]),
            ("HOLDOUT kept", base_h, kept_h, sh, dh, m_h, ts[~res])):
        x = bb if kk is None else kk
        tsv = tsx if kk is None else tsx[mm]
        ctl = rgate(sb, db, int(np.isfinite(x).sum())) if kk is not None else None
        bo = day_boot(x, tsv)
        pv = float(np.mean(ctl >= np.nanmean(x))) if ctl is not None else np.nan
        print(f"{tag:<22}{int(np.isfinite(x).sum()):>6}{np.nanmean(x):>9.4f}{M.pf(x):>7.3f}"
              f"{np.nansum(x):>9.2f}{np.nanpercentile(x[np.isfinite(x)], 90):>8.3f}"
              f"{(np.nanmedian(ctl) if ctl is not None else np.nan):>9.4f}"
              f"{pv:>7.3f}{float((bo <= 0).mean()):>8.3f}")

    print(f"\n  CALIBRATION: the holdout kept {m_h.mean():.3f} against the {KEEP:.2f} it was set for")
    print(f"  holdout IC {ic(p_h, r[~res]):+.4f}")

    rr = kept_h[np.isfinite(kept_h)]
    srp = float(np.mean(rr) / (np.std(rr, ddof=1) + 1e-12))
    print(f"\nDEFLATION at {TRIALS} counted looks: per-trade Sharpe {srp:.4f} on n {len(rr)}")
    try:
        print("  " + str(gates.deflated_sharpe(srp, len(rr), TRIALS, var_trials=0.0025,
                                               skew=float(pd.Series(rr).skew()),
                                               kurtosis=float(pd.Series(rr).kurtosis() + 3),
                                               avg_correlation=0.7)))
    except Exception as ex:                                     # noqa: BLE001
        print(f"  {ex}")


if __name__ == "__main__":
    main()
