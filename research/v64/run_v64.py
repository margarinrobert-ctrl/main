"""Three Optuna studies on the same space, then one locked read.

The trial count is the multiplicity and is stated everywhere. Nothing here looks at the locked
block until section F, and section F reads a set of finalists fixed in section E.
"""
from __future__ import annotations

import os
import sys
import warnings

import numpy as np
import optuna
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "v61"))

import v64opt as O   # noqa: E402
import v61core as V  # noqa: E402

optuna.logging.set_verbosity(optuna.logging.WARNING)
warnings.filterwarnings("ignore")
pd.set_option("display.width", 240)

N_TRIALS = 1500
MIN_TRADES = 40          # ~21 a year over the 1.919-year research block
N_FOLDS = 8
PENALTY = -1e6


def line(t):
    print("\n" + "=" * 122)
    print(t)
    print("=" * 122)


def suggest(tr):
    return dict(
        tf=tr.suggest_categorical("tf", [15, 30, 60]),
        ent=tr.suggest_int("ent", O.CH_MIN, O.CH_MAX),
        exN=tr.suggest_int("exN", O.CH_MIN, O.CH_MAX),
        stop=tr.suggest_float("stop", 1.0, 4.0),
        tp=tr.suggest_float("tp", 0.0, 8.0),
        hold=tr.suggest_int("hold", 120, 960),
        adapt=tr.suggest_categorical("adapt", [0, 1]),
        k=tr.suggest_int("k", O.K_MIN, O.K_MAX),
        w=tr.suggest_int("w", 3, 60),
        use_ma=tr.suggest_categorical("use_ma", [0, 1]),
        ma_thr=tr.suggest_float("ma_thr", -1.0, 3.0),
        use_chop=tr.suggest_categorical("use_chop", [0, 1]),
        chop_thr=tr.suggest_float("chop_thr", 30.0, 70.0),
        psh=tr.suggest_categorical("psh", [0, 1]),
    )


class Book:
    """Evaluates a parameter dict and remembers every trial, research columns only."""

    def __init__(self, Ds):
        self.Ds = Ds
        self.rows = []

    def res(self, p):
        D = self.Ds[p["tf"]]
        R, pct, blk, sig = O.evaluate(D, p)
        return R, pct, blk

    def record(self, p, R, pct, blk, obj):
        m = blk == 0
        rp = pct[m]
        eq = np.cumsum(rp)
        dd = float((eq - np.maximum.accumulate(eq)).min()) if len(eq) else 0.0
        g = rp[rp > 0].sum()
        b = -rp[rp <= 0].sum()
        self.rows.append(dict(**p, n_res=int(m.sum()), tot_res=float(rp.sum()),
                              pct_res=float(rp.mean()) if m.sum() else np.nan,
                              pf_res=float(g / b) if b > 0 else np.nan,
                              dd_res=dd, obj=obj))


def fold_median(pct, blk, D, n_folds=N_FOLDS):
    """Median of per-fold mean %/trade over equal TIME slices of the research block."""
    m = blk == 0
    if m.sum() < MIN_TRADES:
        return PENALTY
    idx = np.linspace(0, m.sum(), n_folds + 1).astype(int)
    v = pct[m]
    out = [v[a:b].mean() for a, b in zip(idx[:-1], idx[1:]) if b > a]
    return float(np.median(out)) if out else PENALTY


if __name__ == "__main__":
    Ds = {tf: O.build(tf) for tf in (15, 30, 60)}
    print("built 15m / 30m / 60m; evaluator verified against the published V61 grid "
          "(research n157 +0.1203 %/trade +18.88%, locked n85 +0.1428 +12.14%)")

    # ------------------------------------------------------------------ study 1
    b1 = Book(Ds)

    def obj1(tr):
        p = suggest(tr)
        R, pct, blk = b1.res(p)
        m = blk == 0
        val = float(pct[m].sum()) if m.sum() >= MIN_TRADES else PENALTY
        b1.record(p, R, pct, blk, val)
        return val

    s1 = optuna.create_study(direction="maximize",
                             sampler=optuna.samplers.TPESampler(seed=7))
    s1.optimize(obj1, n_trials=N_TRIALS, show_progress_bar=False)

    # ------------------------------------------------------------------ study 2
    b2 = Book(Ds)

    def obj2(tr):
        p = suggest(tr)
        R, pct, blk = b2.res(p)
        val = fold_median(pct, blk, Ds[p["tf"]])
        b2.record(p, R, pct, blk, val)
        return val

    s2 = optuna.create_study(direction="maximize",
                             sampler=optuna.samplers.TPESampler(seed=7))
    s2.optimize(obj2, n_trials=N_TRIALS, show_progress_bar=False)

    # ------------------------------------------------------------------ study 3
    b3 = Book(Ds)

    def obj3(tr):
        p = suggest(tr)
        R, pct, blk = b3.res(p)
        m = blk == 0
        if m.sum() < MIN_TRADES:
            b3.record(p, R, pct, blk, PENALTY)
            return PENALTY, 1e6
        rp = pct[m]
        eq = np.cumsum(rp)
        dd = float(-(eq - np.maximum.accumulate(eq)).min())
        b3.record(p, R, pct, blk, float(rp.sum()))
        return float(rp.sum()), dd

    s3 = optuna.create_study(directions=["maximize", "minimize"],
                             sampler=optuna.samplers.NSGAIISampler(seed=7))
    s3.optimize(obj3, n_trials=N_TRIALS, show_progress_bar=False)

    G1, G2, G3 = (pd.DataFrame(b.rows) for b in (b1, b2, b3))
    for nm, g in (("tpe_return", G1), ("tpe_foldmedian", G2), ("nsga2", G3)):
        g.to_parquet(f"results/v64/{nm}.parquet")

    line("A. POPULATION FIRST -- what the three studies actually sampled")
    print(f"  {'study':20s}{'trials':>8s}{'scorable':>10s}{'% profitable':>14s}"
          f"{'median total %':>16s}{'median n':>10s}{'best objective':>16s}")
    for nm, g, st in (("TPE / return", G1, s1), ("TPE / fold median", G2, s2),
                      ("NSGA-II / 2 obj", G3, s3)):
        sc = g[g["n_res"] >= MIN_TRADES]
        best = (max(t.values[0] for t in st.best_trials) if nm.startswith("NSGA")
                else st.best_value)
        print(f"  {nm:20s}{len(g):>8,d}{len(sc):>10,d}{100*(sc['tot_res']>0).mean():>13.1f}%"
              f"{sc['tot_res'].median():>16.2f}{sc['n_res'].median():>10.0f}{best:>16.2f}")
    print(f"\n  the shipped incumbent scores +18.88% total on the research block, so read the")
    print(f"  'best objective' column against THAT, not against zero.")

    line("B. PARAMETER IMPORTANCE (fANOVA over the trial population)")
    for nm, st in (("TPE / return", s1), ("TPE / fold median", s2)):
        try:
            imp = optuna.importance.get_param_importances(st)
        except Exception as e:  # noqa: BLE001
            print(f"  {nm}: importance unavailable ({e})")
            continue
        print(f"\n  {nm}")
        for k, v in list(imp.items()):
            print(f"    {k:12s} {v:6.3f}  " + "#" * int(round(60 * v)))

    line("C. THE CONTINUUM -- did a finer space find anything between the grid's rungs?")
    grid_stop = np.array(V.STOPS)
    for nm, g in (("TPE / return", G1), ("TPE / fold median", G2)):
        sc = g[g["n_res"] >= MIN_TRADES].nlargest(50, "tot_res")
        d = np.abs(sc["stop"].to_numpy()[:, None] - grid_stop[None, :]).min(axis=1)
        print(f"  {nm:20s} top-50 mean distance of `stop` from the nearest grid rung "
              f"{d.mean():.3f} (a uniform draw on [1,4] averages ~0.19)")
        print(f"  {'':20s} top-50 `ent` values {sorted(sc['ent'].unique())[:12]}")
        print(f"  {'':20s} top-50 `exN` values {sorted(sc['exN'].unique())[:12]}")

    line("D. THE V30 SURROGATE TEST -- hold out a WHOLE AXIS VALUE, not random rows")
    try:
        from sklearn.ensemble import HistGradientBoostingRegressor
        from sklearn.model_selection import train_test_split
        g = pd.concat([G1, G2], ignore_index=True)
        g = g[g["n_res"] >= MIN_TRADES]
        feats = ["tf", "ent", "exN", "stop", "tp", "hold", "adapt", "k", "w",
                 "use_ma", "ma_thr", "use_chop", "chop_thr", "psh"]
        X, y = g[feats].to_numpy(float), g["tot_res"].to_numpy()
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=0)
        mdl = HistGradientBoostingRegressor(max_iter=300, random_state=0).fit(Xtr, ytr)
        print(f"  random-row 80/20 R^2            {mdl.score(Xte, yte):+.4f}   "
              f"(interpolation on a dense sample -- this is the number that misleads)")
        for ax, val in (("tf", 60), ("adapt", 1), ("psh", 1), ("use_chop", 1)):
            m = g[ax].to_numpy() == val
            if m.sum() < 50 or (~m).sum() < 50:
                continue
            mdl = HistGradientBoostingRegressor(max_iter=300,
                                                random_state=0).fit(X[~m], y[~m])
            print(f"  held out {ax}=={val:<4}            {mdl.score(X[m], y[m]):+.4f}   "
                  f"({m.sum():,} held-out trials)")
    except ImportError:
        print("  scikit-learn unavailable -- surrogate test skipped")

    line("E. THE FINALISTS, DECLARED BEFORE THE LOCKED BLOCK IS TOUCHED")
    fin = []
    fin.append(("shipped incumbent (V61 30m)",
                dict(tf=30, ent=20, exN=20, stop=2.0, tp=0.0, hold=480, adapt=0, k=3, w=20,
                     use_ma=0, ma_thr=0.0, use_chop=0, chop_thr=99.0, psh=0)))
    fin.append(("shipped 15m preset",
                dict(tf=15, ent=15, exN=30, stop=3.0, tp=6.0, hold=480, adapt=0, k=3, w=30,
                     use_ma=0, ma_thr=0.0, use_chop=0, chop_thr=99.0, psh=0)))
    for nm, st in (("TPE / return best", s1), ("TPE / fold-median best", s2)):
        fin.append((nm, dict(st.best_params)))
    pareto = sorted(s3.best_trials, key=lambda t: -t.values[0])
    if pareto:
        fin.append(("NSGA-II best return", dict(pareto[0].params)))
        knee = min(s3.best_trials,
                   key=lambda t: -(t.values[0] / t.values[1]) if t.values[1] > 0 else 0)
        fin.append(("NSGA-II knee (return/DD)", dict(knee.params)))
    # the neighbourhood centre: best mean research total over the 25 nearest TPE trials
    sc = G1[G1["n_res"] >= MIN_TRADES].reset_index(drop=True)
    cols = ["ent", "exN", "stop", "tp", "hold", "k", "w"]
    Z = ((sc[cols] - sc[cols].mean()) / sc[cols].std()).to_numpy()
    best_i, best_v = -1, -1e18
    for i in range(len(sc)):
        d = np.linalg.norm(Z - Z[i], axis=1)
        nb = np.argsort(d)[:25]
        v = sc["tot_res"].to_numpy()[nb].mean()
        if v > best_v:
            best_v, best_i = v, i
    nbc = {c: sc.loc[best_i, c] for c in
           ["tf", "ent", "exN", "stop", "tp", "hold", "adapt", "k", "w",
            "use_ma", "ma_thr", "use_chop", "chop_thr", "psh"]}
    fin.append(("neighbourhood centre (top mean of 25 nearest)", nbc))
    print(f"  {len(G1)+len(G2)+len(G3):,} trials were scored on the research block. "
          f"{len(fin)} configurations are read on the locked block.")
    for nm, p in fin:
        print(f"    {nm:44s} tf {int(p['tf']):3d}  ent {int(p['ent']):3d}  ex {int(p['exN']):3d}  "
              f"stop {float(p['stop']):.2f}  tp {float(p['tp']):.2f}  hold {int(p['hold']):3d}  "
              f"k {int(p['k'])}  w {int(p['w']):2d}  ma {int(p['use_ma'])}/{float(p['ma_thr']):+.2f}  "
              f"chop {int(p['use_chop'])}/{float(p['chop_thr']):.0f}  psh {int(p['psh'])}")

    line("F. THE ONE LOCKED READ")
    print(f"  {'configuration':46s}{'n res':>7s}{'res %/t':>10s}{'res tot':>10s}"
          f"{'n lock':>8s}{'lock %/t':>11s}{'lock tot':>10s}{'lock PF':>9s}{'lock Sharpe':>13s}")
    out = []
    for nm, p in fin:
        pp = dict(p)
        pp.setdefault("ma_thr", 0.0); pp.setdefault("chop_thr", 99.0)
        R, pct, blk, sig = O.evaluate(Ds[int(pp["tf"])], pp)
        r0, r1 = pct[blk == 0], pct[blk == 1]
        if len(r1) == 0:
            print(f"  {nm:46s}  no locked trades")
            continue
        g_, b_ = r1[r1 > 0].sum(), -r1[r1 <= 0].sum()
        sh = np.sqrt(252 * 6.5 * 60 / int(pp["tf"])) * r1.mean() / r1.std(ddof=1) \
            if r1.std(ddof=1) > 0 else np.nan
        print(f"  {nm:46s}{len(r0):>7d}{r0.mean():>10.4f}{r0.sum():>10.2f}"
              f"{len(r1):>8d}{r1.mean():>11.4f}{r1.sum():>10.2f}"
              f"{(g_/b_ if b_ > 0 else np.nan):>9.3f}{sh:>13.2f}")
        out.append(dict(name=nm, **{k: pp[k] for k in pp}, n_res=len(r0), res_tot=r0.sum(),
                        n_lock=len(r1), lock_pct=r1.mean(), lock_tot=r1.sum()))
    pd.DataFrame(out).to_parquet("results/v64/finalists.parquet")

    line("G. TRANSFER -- the whole trial population, research against locked")
    allg = pd.concat([G1, G2, G3], ignore_index=True)
    allg = allg[allg["n_res"] >= MIN_TRADES].drop_duplicates(
        subset=["tf", "ent", "exN", "stop", "tp", "hold", "adapt", "k", "w",
                "use_ma", "ma_thr", "use_chop", "chop_thr", "psh"])
    samp = allg.sample(min(2500, len(allg)), random_state=1)
    lk = []
    for _, r in samp.iterrows():
        p = {c: r[c] for c in ["tf", "ent", "exN", "stop", "tp", "hold", "adapt", "k", "w",
                               "use_ma", "ma_thr", "use_chop", "chop_thr", "psh"]}
        R, pct, blk, sig = O.evaluate(Ds[int(p["tf"])], p)
        r1 = pct[blk == 1]
        lk.append(r1.mean() if len(r1) >= 10 else np.nan)
    samp = samp.assign(lock_pct=lk).dropna(subset=["lock_pct"])
    print(f"  {len(samp):,} distinct scorable configurations re-read on the locked block")
    print(f"  corr(research %/trade, locked %/trade)  Pearson {samp['pct_res'].corr(samp['lock_pct']):+.4f}"
          f"   Spearman {samp['pct_res'].corr(samp['lock_pct'], method='spearman'):+.4f}")
    top = samp.nlargest(max(1, len(samp) // 100), "tot_res")
    print(f"  whole population mean locked %/trade  {samp['lock_pct'].mean():+.4f}")
    print(f"  TOP 1% by research total, mean locked  {top['lock_pct'].mean():+.4f}   "
          f"({100*(top['lock_pct'] > 0).mean():.0f}% of them profitable on locked)")
    samp.to_parquet("results/v64/transfer.parquet")
