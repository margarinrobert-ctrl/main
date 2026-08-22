"""Meta-labelling: keep the geometry, learn WHICH of its signals to skip.

The primary model (the IB geometry) decides direction and timing. A secondary classifier decides
whether to take each signal at all, from features knowable before entry. This is a different lever
from parameter search — it does not touch the geometry — and it is the one lever in
Lopez de Prado's toolkit that is genuinely about improving an existing edge rather than finding one.

It is also easy to fool yourself with, so:
  * purged + embargoed CV, never plain K-fold
  * a LOCKED holdout the model never sees until the end
  * the benchmark is "take every signal", not zero — a filter that cannot beat taking everything
    has added nothing, however good its accuracy looks
  * measured in dollars

Usage: python3 research/metalabel.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score

sys.path.insert(0, "research")
from anomalies import build_session_features
from ib_sim import COMMISSION_PTS, POINT_VALUE, TAKER_SIDE, TICK, simulate
from nqdata import load_bars, minute_of_day, minutes_since_open, session_index, session_slice
from purged_cv import PurgedKFold

FEATURES = ["ib_range", "ib_close_pos", "ib_pctile", "vol_pctile", "vol_ratio",
            "volume_pctile", "gap", "prev_ret", "weekday", "side", "entry_mso"]


def main() -> None:
    df = load_bars("data/NQ_1m.csv")
    seg = session_slice(df, 570, 960)
    mod = minute_of_day(seg.index)
    sess = session_index(seg.index, 570)
    mso = minutes_since_open(mod, 570).astype(np.int64)
    arrs = (seg["open"].to_numpy(float), seg["high"].to_numpy(float),
            seg["low"].to_numpy(float), seg["close"].to_numpy(float), sess, mso, np.zeros(len(seg)))

    # A higher-frequency primary than the 11:59 variant: meta-labelling needs samples, and 167
    # trades is not a training set. Full session, shallower entry, both sides.
    res = simulate(*arrs, 60, 25.0, 80.0, 2.0, 0, 0, 0, 1.5, 40.0, 389,
                   TICK, POINT_VALUE, TAKER_SIDE, COMMISSION_PTS)
    t = pd.DataFrame({"entryIndex": res[0], "exitIndex": res[1], "side": res[2],
                      "pnl": res[5], "r": res[6]})
    t["session"] = sess[t.entryIndex.to_numpy()]
    t["entry_mso"] = mso[t.entryIndex.to_numpy()]
    t = t.merge(build_session_features(df, seg, sess), on="session", how="left").dropna(subset=FEATURES)
    t = t.sort_values("entryIndex").reset_index(drop=True)

    n_bars = len(seg)
    lock = int(n_bars * 0.80)
    tr = t[t.exitIndex < lock].reset_index(drop=True)
    ho = t[t.entryIndex >= lock].reset_index(drop=True)
    print(f"primary model: {len(t)} signals, ${t.pnl.sum():,.0f} total, mean ${t.pnl.mean():.1f}")
    print(f"  trainable {len(tr)}  |  LOCKED holdout {len(ho)}  ({t.pnl.mean():.1f} $/trade baseline)\n")

    X = tr[FEATURES].to_numpy(float)
    y = (tr.pnl > 0).astype(int).to_numpy()
    t0, t1 = tr.entryIndex.to_numpy(), tr.exitIndex.to_numpy()
    print(f"  base rate (share of winning signals): {y.mean():.3f}")

    # ---- purged CV, to see whether the signal is learnable at all ----
    cv = PurgedKFold(n_splits=5, embargo_pct=0.01)
    aucs, gains = [], []
    for train, test in cv.split(t0, t1):
        m = GradientBoostingClassifier(n_estimators=120, max_depth=2, learning_rate=0.05,
                                       subsample=0.8, random_state=7)
        m.fit(X[train], y[train])
        p = m.predict_proba(X[test])[:, 1]
        if len(np.unique(y[test])) > 1:
            aucs.append(roc_auc_score(y[test], p))
        take = p >= 0.5
        pnl_all = tr.pnl.to_numpy()[test].mean()
        pnl_take = tr.pnl.to_numpy()[test][take].mean() if take.sum() >= 5 else np.nan
        gains.append((pnl_take, pnl_all, take.mean()))
    aucs = np.array(aucs)
    g = np.array([x for x in gains if not np.isnan(x[0])])
    print(f"  purged CV over {len(gains)} folds:")
    print(f"    AUC            {np.nanmean(aucs):.3f}  (0.500 = no information)")
    print(f"    $ / trade      filtered {np.nanmean(g[:,0]):>8,.0f}   unfiltered {np.nanmean(g[:,1]):>8,.0f}"
          f"   kept {np.nanmean(g[:,2])*100:.0f}% of signals")

    # ---- the locked holdout, once ----
    m = GradientBoostingClassifier(n_estimators=120, max_depth=2, learning_rate=0.05,
                                   subsample=0.8, random_state=7).fit(X, y)
    ph = m.predict_proba(ho[FEATURES].to_numpy(float))[:, 1]
    print(f"\n  LOCKED holdout ({len(ho)} signals), evaluated once:")
    print(f"    {'threshold':>10}{'kept':>7}{'$ / trade':>12}{'total $':>12}")
    print(f"    {'take all':>10}{len(ho):>7}{ho.pnl.mean():>12,.0f}{ho.pnl.sum():>12,.0f}")
    for thr in (0.45, 0.50, 0.55, 0.60):
        k = ph >= thr
        if k.sum() >= 5:
            print(f"    {thr:>10.2f}{int(k.sum()):>7}{ho.pnl[k].mean():>12,.0f}{ho.pnl[k].sum():>12,.0f}")
    imp = pd.Series(m.feature_importances_, index=FEATURES).sort_values(ascending=False)
    print("\n  feature importance:  " + "  ".join(f"{k} {v:.2f}" for k, v in imp.head(6).items()))


if __name__ == "__main__":
    main()
