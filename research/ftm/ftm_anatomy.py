"""Reverse-engineering FTM 1.8.0-alpha.2: where is the edge, and does it survive the tests?

Every experiment here re-runs the strategy's own simulator over the same 1.05M one-minute
NQ bars with ONE thing changed, so a difference is attributable. Stages:

  A. ANATOMY   -- drop or replace one component at a time (stop, target, managed stop, 15:30
                  exit, kNN, prior-day override, refinement, direct action, admission, regime,
                  first-signal-only, random / fixed side), each against the random-entry-time
                  control where it matters.
  B. GRID      -- 200 exit-geometry cells (stop x target x managed trigger x 15:30 on/off)
                  plus one-at-a-time ladders on the admission and direction thresholds.
  C. WALKFWD   -- anchored half-year folds over the grid, selection re-run inside each fold.
  D. CLUSTER   -- how many strategies the grid contains; trade-level k-means on the 14
                  features, fitted on 2023-24 and read on 2025.
  E. ROBUST    -- +-20% perturbation on twelve parameters, cost stress, warm-up, contiguity,
                  lookback, bootstrap, day-block bootstrap.
  F. MONTECARLO-- permutation drawdown at the shipped $535 risk, 1%-of-equity compounding,
                  and a 60-day funded-evaluation pass / bust / timeout from day-block draws.

IS = trades before 2025-01-01, OOS = 2025. Nothing is selected on 2025 except in the
walk-forward, whose folds are declared in advance.
"""
from __future__ import annotations

import multiprocessing as mp
import os
import pickle
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.ftm import ftm_sim as S                                   # noqa: E402
from research.ftm import ftm_backtest as B                              # noqa: E402

OUT = "results/ftm"
os.makedirs(OUT, exist_ok=True)
ALPHA2 = dict(prior_bars=1, h2_cap=1)
OOS_START = pd.Timestamp("2025-01-01")
TUNABLE = ["STOP_ORB_MULT", "BASE_TGT_R", "HIGH_ORB_TGT_R", "BASE_TRIG_R", "BASE_LOCK_R",
           "CT_TRIG_R", "CT_LOCK_R", "ADM_BODY", "ADM_CLOSE_LOC", "ADM_TOUCHES", "ORB_Q",
           "PRIOR_DAY_BPS", "FLIP_THRESH", "COND_LOSS_R", "COND_PROFIT_R", "MIN_STOP",
           "MAX_STOP", "WEAK_BODY", "INTRA_BPS", "PRIOR_BPS", "RC1_MAX_VWAP_BPS", "EST_RT_COST"]
BASE = {k: getattr(S, k) for k in TUNABLE}
KEEP = ["time", "side", "reason", "pts", "usd", "R", "qty", "path", "action", "orbBps",
        "stopPts", "tgtPts", "trig", "lock",
        "regime"] + [f"f{i}" for i in range(14)]

_F = None


def _cached_load():
    global _F
    if _F is None:
        _F = S._load_nq_raw()
    return _F


def _init():
    if not hasattr(S, "_load_nq_raw"):
        S._load_nq_raw = S.load_nq
        S.load_nq = _cached_load


def worker(task):
    _init()
    for k, v in BASE.items():
        setattr(S, k, v)
    for k, v in task.get("consts", {}).items():
        setattr(S, k, v)
    kw = dict(ALPHA2)
    kw.update(task.get("kwargs", {}))
    cnt, t = S.run(verbose=False, knobs=task.get("knobs"), **kw)
    return task["name"], cnt, t[KEEP].copy()


def worker_control(task):
    _init()
    f = _cached_load()
    v = B.control(f, task["trades"], draws=task.get("draws", 500), seed=task.get("seed", 17))
    return task["name"], v


def metrics(t):
    if len(t) == 0:
        return dict(n=0)
    r = t.R.to_numpy(); u = t.usd.to_numpy()
    w = u > 0
    eq = np.cumsum(u)
    dd = float((eq - np.maximum.accumulate(eq)).min())
    us = np.sort(u)[::-1]
    k5 = max(1, int(len(u) * 0.05))
    ins = t.time < OOS_START
    return dict(n=len(t), net=float(u.sum()), R=float(r.mean()),
                pf=float(u[w].sum() / max(-u[~w].sum(), 1e-9)), win=float(w.mean()), dd=dd,
                top5=float(us[:k5].sum() / u.sum()) if u.sum() != 0 else np.nan,
                R_is=float(r[ins].mean()) if ins.any() else np.nan,
                R_oos=float(r[~ins].mean()) if (~ins).any() else np.nan,
                n_oos=int((~ins).sum()),
                stop_share=float((t.reason == "stop").mean()),
                sumR_stop=float(r[t.reason == "stop"].sum()),
                sumR_tgt=float(r[t.reason == "target"].sum()),
                sumR_1530=float(r[t.reason == "cond1530"].sum()),
                sumR_1600=float(r[t.reason == "close1600"].sum()))


def line(name, m, ctl=None):
    if m.get("n", 0) == 0:
        return f"  {name:<44} n    0"
    s = (f"  {name:<44} n {m['n']:>4} net ${m['net']:>8,.0f} R {m['R']:+.4f} PF {m['pf']:.3f}"
         f" win {m['win']:.1%} DD ${m['dd']:>7,.0f} top5 {m['top5']:>5.0%}"
         f" IS {m['R_is']:+.3f} OOS {m['R_oos']:+.3f}")
    if ctl is not None:
        s += f" | ctl {np.median(ctl):+.4f} p {np.mean(ctl >= m['R']):.3f}"
    return s


def neighbour_mean(cells, axes, key_R):
    """+-1 neighbour mean of R on the 4-D grid, excluding the cell itself."""
    out = {}
    for key in cells:
        vals = []
        for d in range(4):
            lv = axes[d]
            i = lv.index(key[d])
            for step in (-1, 1):
                j = i + step
                if 0 <= j < len(lv):
                    k2 = list(key); k2[d] = lv[j]; k2 = tuple(k2)
                    if k2 in key_R and np.isfinite(key_R[k2]):
                        vals.append(key_R[k2])
        out[key] = float(np.mean(vals)) if vals else np.nan
    return out


def main():
    t0 = time.time()
    pool = mp.Pool(4)
    print(__doc__)

    # ---------------------------------------------------------------- A. anatomy
    print("=" * 110)
    print("A. ANATOMY -- one component removed or replaced at a time (alpha.2, FixedDollar)")
    print("=" * 110)
    A = [
        ("AS SHIPPED (alpha.2)", {}),
        ("RC1 (prior 2 bars, no H2 cap)", dict(kwargs=dict(prior_bars=2, h2_cap=0))),
        ("stop placed at 2x ORB (sizing unchanged)", dict(knobs=dict(stop_place_mult=2.0))),
        ("stop placed at 4x ORB", dict(knobs=dict(stop_place_mult=4.0))),
        ("NO STOP (placed at 100x ORB)", dict(knobs=dict(stop_place_mult=100.0))),
        ("no profit target", dict(knobs=dict(target_on=False))),
        ("no managed stop", dict(knobs=dict(managed_on=False))),
        ("no 15:30 conditional exit", dict(knobs=dict(cond_exit_on=False))),
        ("STOP + 16:00 FLATTEN ONLY (no target/managed/15:30)",
         dict(knobs=dict(target_on=False, managed_on=False, cond_exit_on=False))),
        ("no kNN direction model", dict(knobs=dict(knn_on=False))),
        ("no prior-day override", dict(knobs=dict(prior_override_on=False))),
        ("RAW BREAKOUT SIDE (no kNN, no prior)", dict(knobs=dict(knn_on=False,
                                                                 prior_override_on=False))),
        ("no refinement (submit at the signal)", dict(knobs=dict(refine_on=False))),
        ("no direct action", dict(knobs=dict(direct_on=False))),
        ("no admission geometry", dict(knobs=dict(adm_geom_on=False))),
        ("no touch veto", dict(knobs=dict(adm_touch_on=False))),
        ("NO ADMISSION AT ALL", dict(knobs=dict(adm_geom_on=False, adm_touch_on=False))),
        ("always the 3R plan (no high-ORB regime)", dict(knobs=dict(high_orb_regime_on=False))),
        ("10:00 SIGNAL ONLY (later breakouts skipped)", dict(knobs=dict(first_signal_only=True))),
        ("ALWAYS LONG", dict(knobs=dict(side_mode="long"))),
        ("ALWAYS SHORT", dict(knobs=dict(side_mode="short"))),
        ("no warm-up requirement", dict(kwargs=dict(require_warm=False))),
    ] + [(f"RANDOM SIDE seed {s}", dict(knobs=dict(side_mode="random", side_seed=s)))
         for s in range(5)]
    tasks = [dict(name=n, **d) for n, d in A]
    res = {n: (c, t) for n, c, t in pool.map(worker, tasks)}
    ctl_names = ["AS SHIPPED (alpha.2)", "NO STOP (placed at 100x ORB)", "no profit target",
                 "STOP + 16:00 FLATTEN ONLY (no target/managed/15:30)",
                 "RAW BREAKOUT SIDE (no kNN, no prior)", "no refinement (submit at the signal)",
                 "NO ADMISSION AT ALL", "10:00 SIGNAL ONLY (later breakouts skipped)",
                 "ALWAYS LONG", "RANDOM SIDE seed 0", "no 15:30 conditional exit"]
    ctasks = [dict(name=n, trades=res[n][1], draws=500) for n in ctl_names]
    ctls = dict(pool.map(worker_control, ctasks))
    for n, _ in A:
        print(line(n, metrics(res[n][1]), ctls.get(n)))
    rs = [metrics(res[f"RANDOM SIDE seed {s}"][1])["R"] for s in range(5)]
    print(f"  random side, five seeds: mean R {np.mean(rs):+.4f} (min {min(rs):+.4f}, "
          f"max {max(rs):+.4f})")
    print("\n  exit split (sum of R by exit reason):")
    for n in ("AS SHIPPED (alpha.2)", "NO STOP (placed at 100x ORB)", "no profit target",
              "no 15:30 conditional exit", "STOP + 16:00 FLATTEN ONLY (no target/managed/15:30)"):
        m = metrics(res[n][1])
        print(f"    {n:<52} stop {m['sumR_stop']:+7.1f}  target {m['sumR_tgt']:+7.1f}  "
              f"15:30 {m['sumR_1530']:+7.1f}  16:00 {m['sumR_1600']:+7.1f}  "
              f"stop share {m['stop_share']:.0%}")
    shipped = res["AS SHIPPED (alpha.2)"][1]
    shipped.to_csv(f"{OUT}/anatomy_shipped_trades.csv", index=False)
    with open(f"{OUT}/anatomy_variants.pkl", "wb") as fh:
        pickle.dump({n: t for n, (c, t) in res.items()}, fh)

    # ---------------------------------------------------------------- B. grid
    print("\n" + "=" * 110)
    print("B. PARAMETER GRID -- stop x target x managed trigger x 15:30 exit (200 cells)")
    print("=" * 110)
    STOPS = [0.75, 1.0, 1.25, 1.5, 2.0]
    TGTS = [1.5, 2.0, 3.0, 4.0, 8.0]
    TRIGS = [0.75, 1.25, 2.0, "off"]
    CONDS = [True, False]
    AXES = [STOPS, TGTS, TRIGS, CONDS]
    gtasks = []
    for sm in STOPS:
        for tg in TGTS:
            for tr in TRIGS:
                for cd in CONDS:
                    consts = dict(STOP_ORB_MULT=sm, BASE_TGT_R=tg,
                                  HIGH_ORB_TGT_R=HIGH_TGT(tg))
                    if tr == "off":
                        consts.update(BASE_TRIG_R=1e9, CT_TRIG_R=1e9)
                    else:
                        consts.update(BASE_TRIG_R=tr, CT_TRIG_R=min(0.75, tr))
                    gtasks.append(dict(name=(sm, tg, tr, cd), consts=consts,
                                       knobs=dict(cond_exit_on=cd)))
    G = {n: t for n, c, t in pool.map(worker, gtasks)}
    with open(f"{OUT}/grid_trades.pkl", "wb") as fh:
        pickle.dump(G, fh)
    rows = []
    for key, t in G.items():
        m = metrics(t); m.update(stop=key[0], tgt=key[1], trig=key[2], cond=key[3]); rows.append(m)
    gdf = pd.DataFrame(rows)
    gdf.to_csv(f"{OUT}/grid_cells.csv", index=False)
    ok = gdf.n >= 30
    print(f"  cells {len(gdf)}; share R>0 {float((gdf.R > 0).mean()):.1%}; PF>1.2 "
          f"{float((gdf.pf > 1.2).mean()):.1%}; median R {gdf.R.median():+.4f}; "
          f"IS R>0 {float((gdf.R_is > 0).mean()):.1%}; OOS R>0 {float((gdf.R_oos > 0).mean()):.1%}")
    d = gdf[(gdf.stop == 1.25) & (gdf.tgt == 3.0) & (gdf.trig == 1.25) & (gdf.cond)]
    print(f"  shipped cell percentile by R: {float((gdf.R < d.R.iloc[0]).mean()):.1%}; by OOS R: "
          f"{float((gdf.R_oos < d.R_oos.iloc[0]).mean()):.1%}")
    print("  marginal mean R per axis level (IS / OOS):")
    for ax in ("stop", "tgt", "trig", "cond"):
        g = gdf.groupby(ax).agg(R_is=("R_is", "mean"), R_oos=("R_oos", "mean"), n=("n", "mean"))
        print(f"    {ax:<5} " + "  ".join(f"{k}: {r.R_is:+.3f}/{r.R_oos:+.3f} (n {r.n:.0f})"
                                         for k, r in g.iterrows()))
    from scipy.stats import spearmanr
    rho = spearmanr(gdf.R_is[ok], gdf.R_oos[ok]).correlation
    q = gdf.R_is[ok].quantile(0.9)
    top = gdf[ok & (gdf.R_is >= q)]
    print(f"  rank stability IS->OOS: Spearman {rho:+.3f}; IS top decile ({len(top)} cells) "
          f"IS {top.R_is.mean():+.3f} -> OOS {top.R_oos.mean():+.3f} "
          f"({float((top.R_oos > 0).mean()):.0%} "
          f"positive); all-cell OOS mean {gdf.R_oos[ok].mean():+.3f}")
    key_R = {k: metrics(t)["R_is"] for k, t in G.items()}
    plat = neighbour_mean(list(G), AXES, key_R)
    gdf["plateau"] = [plat[(r.stop, r.tgt, r.trig, r.cond)] for r in gdf.itertuples()]
    c = np.corrcoef(gdf.R_is[ok], gdf.plateau[ok])[0, 1]
    print(f"  neighbourhood coherence corr(cell IS R, neighbour mean) {c:.3f}")
    print("  top 5 cells by IS R -> OOS:")
    print("    " + gdf[ok].sort_values("R_is", ascending=False).head(5)[
        ["stop", "tgt", "trig", "cond", "n", "R_is", "R_oos", "pf", "plateau"]]
        .to_string(index=False, float_format=lambda x: f"{x:.3f}").replace("\n", "\n    "))
    # one-at-a-time ladders on the admission / direction thresholds
    print("\n  one-at-a-time ladders (whole sample R / n; shipped value marked *):")
    LAD = {"ADM_BODY": [0.0, 0.15, 0.30, 0.45], "ADM_CLOSE_LOC": [0.4, 0.5, 0.6, 0.7, 0.8],
           "ADM_TOUCHES": [1, 2, 3, 4, 5], "ORB_Q": [0.5, 0.75, 0.9],
           "FLIP_THRESH": [0.55, 0.65, 0.75, 2.0], "PRIOR_DAY_BPS": [150.0, 300.0, 600.0, 1e9],
           "COND_PROFIT_R": [0.5, 1.0, 1.5, 2.0], "COND_LOSS_R": [-0.5, 0.0, 0.5],
           "RC1_MAX_VWAP_BPS": [10.0, 20.0, 40.0, 1e9], "WEAK_BODY": [0.0, 0.2, 0.4]}
    ltasks = [dict(name=(k, v), consts={k: v}) for k, vs in LAD.items() for v in vs]
    L = {n: metrics(t) for n, c, t in pool.map(worker, ltasks)}
    for k, vs in LAD.items():
        cells = []
        for v in vs:
            m = L[(k, v)]
            mark = "*" if v == BASE[k] else " "
            cells.append(f"{v:g}{mark}: {m['R']:+.3f}/{m['n']}")
        print(f"    {k:<18} " + "   ".join(cells))

    # ---------------------------------------------------------------- C. walk-forward
    print("\n" + "=" * 110)
    print("C. WALK-FORWARD over the 200-cell grid -- anchored, half-year folds, selection inside")
    print("=" * 110)
    folds = [("2024-H1", "2024-01-01", "2024-07-01"), ("2024-H2", "2024-07-01", "2025-01-01"),
             ("2025-H1", "2025-01-01", "2025-07-01"), ("2025-H2", "2025-07-01", "2026-01-01")]
    DEFAULT = (1.25, 3.0, 1.25, True)
    oos = {"best": [], "plateau": [], "default": []}
    rows = []
    for fname, a, b in folds:
        a, b = pd.Timestamp(a), pd.Timestamp(b)
        tr_R = {}; tr_n = {}
        for key, t in G.items():
            tt = t[t.time < a]
            tr_R[key] = float(tt.R.mean()) if len(tt) else np.nan; tr_n[key] = len(tt)
        cand = [k for k in G if tr_n[k] >= 30]
        best = max(cand, key=lambda k: tr_R[k])
        pl = neighbour_mean(cand, AXES, tr_R)
        plateau = max(cand, key=lambda k: pl[k] if np.isfinite(pl[k]) else -9)
        for sel, key in (("best", best), ("plateau", plateau), ("default", DEFAULT)):
            te = G[key][(G[key].time >= a) & (G[key].time < b)]
            oos[sel].append(te)
            rows.append(dict(fold=fname, selector=sel, cell=key, n_tr=tr_n[key], R_tr=tr_R[key],
                             n_te=len(te), R_te=float(te.R.mean()) if len(te) else np.nan,
                             usd_te=float(te.usd.sum())))
    wf = pd.DataFrame(rows)
    wf.to_csv(f"{OUT}/walkforward.csv", index=False)
    for sel in ("best", "plateau", "default"):
        d = wf[wf.selector == sel]
        print(f"  {sel}:")
        for r in d.itertuples():
            print(f"    {r.fold}  cell {r.cell}  train n {r.n_tr:>3} R {r.R_tr:+.3f}  ->  test n "
                  f"{r.n_te:>3} R {r.R_te:+.3f}  ${r.usd_te:>7,.0f}  WFE "
                  f"{(r.R_te / r.R_tr) if r.R_tr else np.nan:.2f}")
        allt = pd.concat(oos[sel])
        print(f"    concatenated OOS: n {len(allt)} R {allt.R.mean():+.4f} ${allt.usd.sum():,.0f} "
              f"PF {allt.usd[allt.usd > 0].sum() / max(-allt.usd[allt.usd <= 0].sum(), 1e-9):.3f}; "
              f"folds positive {int((d.R_te > 0).sum())}/{len(d)}")

    # ---------------------------------------------------------------- D. clusters
    print("\n" + "=" * 110)
    print("D. CLUSTERS")
    print("=" * 110)
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform
    days = sorted(set(pd.concat(G.values()).time.dt.normalize()))
    didx = {d: i for i, d in enumerate(days)}
    keys = [k for k in G if len(G[k]) >= 30]
    M = np.zeros((len(days), len(keys)))
    for j, k in enumerate(keys):
        t = G[k]
        for d, r in zip(t.time.dt.normalize(), t.R):
            M[didx[d], j] += r
    ins = np.array([d < OOS_START for d in days])
    X = M[ins]
    sd = X.std(0); keep = sd > 0
    Cm = np.clip(np.nan_to_num(np.corrcoef(X[:, keep].T)), -1, 1)
    D = 1 - Cm; np.fill_diagonal(D, 0)
    lab = fcluster(linkage(squareform(D, checks=False), "average"), t=0.3, criterion="distance")
    ev = np.linalg.eigvalsh(Cm)[::-1]; ev = ev[ev > 0]
    ncomp = int(np.searchsorted(np.cumsum(ev) / ev.sum(), 0.9) + 1)
    off = Cm[np.triu_indices_from(Cm, 1)]
    print(f"  {int(keep.sum())} cells -> {len(set(lab))} clusters at within-corr 0.7; "
          f"{ncomp} components "
          f"explain 90% of variance; median pairwise corr {np.median(off):.3f}")
    kk = [k for k, kp in zip(keys, keep) if kp]
    cdf = pd.DataFrame(dict(key=kk, cluster=lab, R_is=[metrics(G[k])["R_is"] for k in kk],
                            R_oos=[metrics(G[k])["R_oos"] for k in kk]))
    q = cdf.R_is.quantile(0.9)
    print(f"  IS top decile spans {cdf[cdf.R_is >= q].cluster.nunique()} clusters")
    g = cdf.groupby("cluster").agg(cells=("R_is", "size"), R_is=("R_is", "mean"),
                                   R_oos=("R_oos", "mean")).sort_values("R_is", ascending=False)
    print("  clusters with >= 5 cells, IS -> OOS:")
    print("    " + g[g.cells >= 5].head(10).to_string(float_format=lambda x: f"{x:+.3f}")
          .replace("\n", "\n    "))
    # trade-level: k-means on the 14 features, fitted on IS trades of the shipped strategy
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
    fc = [f"f{i}" for i in range(14)]
    ti = shipped[shipped.time < OOS_START]; to = shipped[shipped.time >= OOS_START]
    sc = StandardScaler().fit(ti[fc])
    km = KMeans(n_clusters=4, n_init=10, random_state=0).fit(sc.transform(ti[fc]))
    li = km.labels_; lo = km.predict(sc.transform(to[fc]))
    print("  trade-level k-means (k=4) on the 14 direction features, fitted on 2023-24:")
    for c in range(4):
        a = ti.R[li == c]; b = to.R[lo == c]
        cen = pd.Series(sc.inverse_transform(km.cluster_centers_[c:c + 1])[0],
                        index=S.FEATURE_NAMES)
        desc = ", ".join(f"{k.replace('aligned_', '')} {v:+.0f}" for k, v in
                         cen[["aligned_vwap_distance_bps", "signal_elapsed_15m", "orb_bps",
                              "touch_count", "aligned_prior_ret5_bps"]].items())
        print(f"    cluster {c}: IS n {len(a):>3} R {a.mean():+.3f} | OOS n {len(b):>3} "
              f"R {b.mean() if len(b) else np.nan:+.3f} | {desc}")
    print("  per-feature tercile split on IS (top third minus bottom third of R), read on OOS:")
    rows = []
    for i, nm in enumerate(S.FEATURE_NAMES):
        x = ti[f"f{i}"]; lo_, hi_ = x.quantile(1 / 3), x.quantile(2 / 3)
        if hi_ <= lo_:
            continue
        d_is = ti.R[x >= hi_].mean() - ti.R[x <= lo_].mean()
        xo = to[f"f{i}"]
        d_oos = to.R[xo >= hi_].mean() - to.R[xo <= lo_].mean()
        rows.append(dict(feature=nm, d_is=d_is, d_oos=d_oos))
    fr = pd.DataFrame(rows).sort_values("d_is", key=abs, ascending=False)
    print("    " + fr.to_string(index=False, float_format=lambda x: f"{x:+.3f}")
          .replace("\n", "\n    "))
    agree = float((np.sign(fr.d_is) == np.sign(fr.d_oos)).mean())
    print(f"    sign agreement IS->OOS across features: {agree:.0%} (50% is chance)")

    # ---------------------------------------------------------------- E. robustness
    print("\n" + "=" * 110)
    print("E. ROBUSTNESS")
    print("=" * 110)
    PERT = ["STOP_ORB_MULT", "BASE_TGT_R", "HIGH_ORB_TGT_R", "BASE_TRIG_R", "CT_TRIG_R", "ADM_BODY",
            "ADM_CLOSE_LOC", "ORB_Q", "PRIOR_DAY_BPS", "FLIP_THRESH", "COND_PROFIT_R",
            "RC1_MAX_VWAP_BPS"]
    ptasks = [dict(name=(k, f), consts={k: BASE[k] * f}) for k in PERT for f in (0.8, 1.2)]
    P = {n: metrics(t) for n, c, t in pool.map(worker, ptasks)}
    base_m = metrics(shipped)
    print(f"  +-20% perturbation, R per trade (shipped {base_m['R']:+.4f}):")
    worst = 0
    for k in PERT:
        a, b = P[(k, 0.8)], P[(k, 1.2)]
        worst = max(worst, abs(a["R"] - base_m["R"]), abs(b["R"] - base_m["R"]))
        print(f"    {k:<18} x0.8 {a['R']:+.4f} ({a['n']})   x1.2 {b['R']:+.4f} ({b['n']})")
    print(f"    largest move {worst:.4f} R; parameters whose 20% move flips the sign: "
          f"{sum(1 for k in PERT for f in (0.8, 1.2) if P[(k, f)]['R'] <= 0)}")
    ctasks = [dict(name=("cost", c), consts=dict(EST_RT_COST=c)) for c in (0.0, 2.5, 5.0, 10.0)]
    ctasks += [dict(name=("warm", False), kwargs=dict(require_warm=False)),
               dict(name=("contig", False), kwargs=dict(strict_contig=False)),
               dict(name=("lookback", 40), kwargs=dict(orb_lookback=40)),
               dict(name=("lookback", 60), kwargs=dict(orb_lookback=60))]
    Rr = {n: metrics(t) for n, c, t in pool.map(worker, ctasks)}
    print("  per-contract round-turn reserve $0 / 2.5 / 5 / 10: " + "  ".join(
        f"{c:g}: {Rr[('cost', c)]['R']:+.4f}" for c in (0.0, 2.5, 5.0, 10.0)))
    print(f"  no warm-up {Rr[('warm', False)]['R']:+.4f} ({Rr[('warm', False)]['n']}); "
          f"loose contiguity "
          f"{Rr[('contig', False)]['R']:+.4f} ({Rr[('contig', False)]['n']}); lookback 40 "
          f"{Rr[('lookback', 40)]['R']:+.4f}; 60 {Rr[('lookback', 60)]['R']:+.4f}")
    r = shipped.R.to_numpy()
    p0, lo_, hi_ = B.boot(r)
    print(f"  bootstrap on trades: P(mean R <= 0) {p0:.3f}, 90% CI [{lo_:+.4f}, {hi_:+.4f}]")
    dr = shipped.groupby(shipped.time.dt.normalize()).agg(R=("R", "sum"), n=("R", "size"))
    rng = np.random.default_rng(3)
    idx = rng.integers(0, len(dr), (10000, len(dr)))
    mR = dr.R.to_numpy()[idx].sum(1) / dr.n.to_numpy()[idx].sum(1)
    print(f"  day-block bootstrap (whole days with their trades): P(mean R <= 0) "
          f"{float((mR <= 0).mean()):.3f}, 90% CI [{np.percentile(mR, 5):+.4f}, "
          f"{np.percentile(mR, 95):+.4f}]")
    ri = shipped.R[shipped.time < OOS_START]; ro = shipped.R[shipped.time >= OOS_START]
    print(f"  shape: IS R {ri.mean():+.4f} (n {len(ri)}) -> OOS R {ro.mean():+.4f} (n {len(ro)}); "
          + ('decays, the right shape' if ro.mean() < ri.mean()
             else 'GREW out of sample -- the wrong shape'))

    # ---------------------------------------------------------------- F. Monte Carlo
    print("\n" + "=" * 110)
    print("F. MONTE CARLO")
    print("=" * 110)
    u = shipped.usd.to_numpy(); n = len(u)
    rng = np.random.default_rng(11)
    perm = np.argsort(rng.random((10000, n)), axis=1)
    paths = np.cumsum(u[perm], axis=1)
    dd = np.max(np.maximum.accumulate(paths, axis=1) - paths, axis=1)
    real_dd = -base_m["dd"]
    print(f"  permutation (10,000) of the realised trades at the shipped $535 risk: max DD median "
          f"${np.median(dd):,.0f}, p95 ${np.percentile(dd, 95):,.0f}, "
          f"p99 ${np.percentile(dd, 99):,.0f}; "
          f"realised ${real_dd:,.0f} sits at the {float((dd <= real_dd).mean()):.0%} percentile")
    lg = np.cumsum(np.log1p(0.01 * r[perm]), axis=1)
    cdd = 1 - np.exp(-np.max(np.maximum.accumulate(lg, axis=1) - lg, axis=1))
    idx = rng.integers(0, n, (10000, n))
    eq = np.exp(np.sum(np.log1p(0.01 * r[idx]), axis=1))
    print(f"  1% of equity per trade: max DD median {np.median(cdd):.1%}, "
          f"p95 {np.percentile(cdd, 95):.1%}, "
          f"P(DD > 10%) {float((cdd > 0.10).mean()):.2f}; final equity multiple over the sample "
          f"(bootstrap) median {np.median(eq):.3f}, 5th pct {np.percentile(eq, 5):.3f}, "
          f"P(< 1) {float((eq < 1).mean()):.3f}")
    # 60-day funded evaluation: +6% target, 4% trailing floor from the equity high, on $50,000
    daily = shipped.groupby(shipped.time.dt.normalize()).usd.sum()
    allday = pd.Series(0.0, index=pd.bdate_range(shipped.time.min().normalize(),
                                                 shipped.time.max().normalize()))
    allday.loc[daily.index] = daily.values
    dv = allday.to_numpy()
    passed = busted = 0
    for d in range(10000):
        seq = dv[rng.integers(0, len(dv), 60)]
        eqc = 50000 + np.cumsum(seq); peak = np.maximum.accumulate(np.maximum(eqc, 50000))
        hit_t = np.where(eqc >= 53000)[0]; hit_b = np.where(eqc <= peak - 2000)[0]
        ft = hit_t[0] if len(hit_t) else 10 ** 6; fb = hit_b[0] if len(hit_b) else 10 ** 6
        if ft < fb and ft < 10 ** 6:
            passed += 1
        elif fb < 10 ** 6:
            busted += 1
    print(f"  60-trading-day evaluation, $50,000, +6% target, 4% trailing floor, shipped sizing: "
          f"P(pass) {passed / 10000:.1%}, P(bust) {busted / 10000:.1%}, P(neither) "
          f"{1 - (passed + busted) / 10000:.1%}")
    print(f"\n[{time.time() - t0:.0f}s]")
    pool.close()


def HIGH_TGT(tg):
    """The high-ORB regime target keeps its ratio to the baseline (1.25 : 3)."""
    return round(1.25 * tg / 3.0, 4)


if __name__ == "__main__":
    main()
