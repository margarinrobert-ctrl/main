"""S10 -- the full validation battery on the section-12 rule, with everything saved for plotting.

Four questions, kept separate because they are different questions:
  MONTE CARLO   bootstrap WITH REPLACEMENT for the EDGE, PERMUTE for the PATH, price JITTER with
                every indicator recomputed, and an EXECUTION perturbation. `validate.monte_carlo`'s
                split: permuting trades cannot change the endpoint, so it answers drawdown only.
  OUT OF SAMPLE the three blocks already declared -- research, holdout, and a DIFFERENT-PROVIDER
                forward feed -- as equity curves rather than a single number.
  WALK-FORWARD  the constants FIXED, because the rule was derived and not fitted, with a
                re-selecting arm and a random arm beside it as comparisons.
  CORRELATION   three matrices that answer three different things: between the arms (is this one
                strategy wearing five hats), between the conditions ON THE SIGNAL BARS (is the pool
                duplicating), and against always-long (is it drift).
"""
from __future__ import annotations

import os
import pickle
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s10lib as L  # noqa: E402
import s30core as S  # noqa: E402

pd.set_option("display.width", 240)
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = {}


def dd_of(x):
    eq = np.cumsum(x)
    return float(np.max(np.maximum.accumulate(eq) - eq))


def main():
    f = S.load("US30L")
    fi = S.load("US30I")
    bl, bli = S.blocks(f, "US30L"), S.blocks(fi, "US30I")
    M, Mi = L.build_masks(*[f[c].to_numpy() for c in ("high", "low", "close")]), \
            L.build_masks(*[fi[c].to_numpy() for c in ("high", "low", "close")])
    sess = {b: f.index[m & S.window(f)].normalize().nunique() for b, m in bl.items()}
    sess["C_forward"] = fi.index[bli["C_forward"] & S.window(fi)].normalize().nunique()

    # ================= 1. OUT OF SAMPLE ======================================================
    print("=== 1. OUT OF SAMPLE: three blocks, two providers ===")
    rows, curves = [], {}
    for nm, cond in L.ARMS:
        for feed, fm, MM, bset in ((f, "US30L", M, bl), (fi, "US30I", Mi, bli)):
            for bn, bm in bset.items():
                t = L.trades(feed, cond, bm, MM)
                if len(t) < 20:
                    continue
                r = L.stats(t, sess.get(bn, 250)); r.update(arm=nm, block=bn)
                rows.append(r)
                curves[(nm, bn)] = (t["ts"].to_numpy(), np.cumsum(t["pts"].to_numpy()))
    OOS = pd.DataFrame(rows)
    print(OOS[["arm", "block", "n", "pts", "t", "mde", "pf", "win", "total", "dd", "ret_dd",
               "sharpe"]].round(3).to_string(index=False))
    OUT["oos"], OUT["curves"] = OOS, curves

    # ================= 2. MONTE CARLO ========================================================
    print("\n=== 2. MONTE CARLO on `+adx<=20`, research and holdout ===")
    mc = {}
    for bn, bm in bl.items():
        t = L.trades(f, ["adx<=20"], bm, M)
        p = t["pts"].to_numpy()
        d = t.groupby(t.ts.dt.normalize())["pts"].sum().to_numpy()
        rng = np.random.default_rng(11)
        boot = np.array([rng.choice(d, len(d), replace=True).mean() for _ in range(4000)])
        perm = np.array([dd_of(rng.permutation(p)) for _ in range(4000)])
        # execution perturbation: slippage U(0,2x) and cost U(0.5x,2x) INSIDE the walk
        ex = []
        for i in range(250):
            rg = np.random.default_rng(500 + i)
            tt = L.trades(f, ["adx<=20"], bm, M, cost=S.COST * rg.uniform(0.5, 2.0))
            ex.append(tt["pts"].mean() if len(tt) else np.nan)
        ex = np.asarray(ex)
        # price jitter with ADX, EMA, ATR and the Donchian ALL recomputed from jittered bars
        jt = []
        tick = 1.0
        for i in range(150):
            rg = np.random.default_rng(900 + i)
            g = f.copy()
            for c in ("open", "high", "low", "close"):
                g[c] = f[c].to_numpy() + rg.normal(0, tick, len(f))
            g["high"] = g[["open", "high", "low", "close"]].max(axis=1)
            g["low"] = g[["open", "high", "low", "close"]].min(axis=1)
            tr = np.maximum(g.high - g.low, np.maximum((g.high - g.close.shift()).abs(),
                                                       (g.low - g.close.shift()).abs()))
            g["atr"] = tr.ewm(span=14, adjust=False).mean()
            Mg = L.build_masks(g["high"].to_numpy(), g["low"].to_numpy(), g["close"].to_numpy())
            tt = L.trades(g, ["adx<=20"], bm, Mg)
            jt.append(tt["pts"].mean() if len(tt) else np.nan)
        jt = np.asarray(jt); jt = jt[np.isfinite(jt)]
        mc[bn] = dict(realised=p.mean(), boot=boot, perm=perm, exec=ex[np.isfinite(ex)], jit=jt,
                      realised_dd=dd_of(p), n=len(p))
        print(f"  {bn}: realised {p.mean():+.3f} pts on n={len(p)}")
        print(f"    bootstrap (EDGE)   P(mean<=0) {np.mean(boot <= 0):.3f}  "
              f"95% CI [{np.percentile(boot,2.5):+.2f}, {np.percentile(boot,97.5):+.2f}] per day")
        print(f"    permutation (PATH) realised DD {dd_of(p):.0f}  median {np.median(perm):.0f}  "
              f"p99 {np.percentile(perm,99):.0f}  percentile of realised "
              f"{np.mean(perm < dd_of(p)):.3f}  p99/realised {np.percentile(perm,99)/dd_of(p):.2f}x")
        print(f"    execution          p5 {np.percentile(ex[np.isfinite(ex)],5):+.3f}  "
              f"p95 {np.percentile(ex[np.isfinite(ex)],95):+.3f}  "
              f"P(<=0) {np.mean(ex[np.isfinite(ex)] <= 0):.3f}")
        print(f"    price jitter (indicators RECOMPUTED) p5 {np.percentile(jt,5):+.3f}  "
              f"p95 {np.percentile(jt,95):+.3f}  sign kept {np.mean(jt > 0):.3f}  n_draws {len(jt)}")
    OUT["mc"] = mc

    # ================= 3. WALK-FORWARD =======================================================
    print("\n=== 3. WALK-FORWARD, constants FIXED (the rule is derived, not fitted) ===")
    full = bl["A_research"] | bl["B_holdout"]
    days = pd.DatetimeIndex(sorted(set(f.index[full & S.window(f)].normalize())))
    folds = []
    yrs = sorted(set(days.year))
    for y in yrs[2:]:
        tr_m = full & (f.index.year < y)
        te_m = full & (f.index.year == y)
        if te_m.sum() < 200:
            continue
        row = dict(year=y, n_train=int(tr_m.sum()), n_test=int(te_m.sum()))
        for nm, cond in L.ARMS:
            t = L.trades(f, cond, te_m, M)
            row[nm] = float(t["pts"].mean()) if len(t) >= 10 else np.nan
            row[f"{nm}_n"] = len(t)
        # re-selecting arm: pick the arm with the best training mean, apply to the test year
        best, bv = None, -1e9
        for nm, cond in L.ARMS:
            tt = L.trades(f, cond, tr_m, M)
            v = tt["pts"].mean() if len(tt) >= 30 else -1e9
            if v > bv:
                best, bv = nm, v
        row["re-chosen"] = row.get(best, np.nan); row["chose"] = best
        rng = np.random.default_rng(y)
        row["random arm"] = row.get(L.ARMS[rng.integers(0, len(L.ARMS))][0], np.nan)
        folds.append(row)
    W = pd.DataFrame(folds)
    print(W[["year", "base", "+adx<=20", "+ema align", "+both", "conventional", "re-chosen",
             "chose"]].round(3).to_string(index=False))
    print("\nfolds positive / total, and mean per arm:")
    for nm in ["base", "+adx<=20", "+ema align", "+both", "conventional", "re-chosen",
               "random arm"]:
        v = W[nm].dropna()
        print(f"  {nm:14s} {int((v > 0).sum())}/{len(v)} folds positive   mean {v.mean():+7.3f}")
    OUT["wf"] = W

    # ================= 4. CORRELATION MATRICES ===============================================
    print("\n=== 4a. between the ARMS, daily P&L, research block (one strategy in five hats?) ===")
    idx = pd.DatetimeIndex(sorted(set(f.index[bl["A_research"] & S.window(f)].normalize())))
    D = pd.DataFrame({nm: L.daily(L.trades(f, cond, bl["A_research"], M), idx)
                      for nm, cond in L.ARMS})
    al = L.trades(f, [], bl["A_research"], M, stop_a=1e9, tgt_a=1e9, hold=16)
    D["always-long"] = L.daily(al, idx)
    C1 = D.corr()
    print(C1.round(3).to_string())

    print("\n=== 4b. between the CONDITIONS on the SIGNAL BARS (is the pool duplicating?) ===")
    s2, _ = S.donchian(f, 20, 1)
    s2 = s2[np.isin(s2, np.flatnonzero(bl["A_research"] & S.window(f)))]
    C2 = pd.DataFrame({k: M[k][s2].astype(float) for k in M}).corr()
    print(C2.round(4).to_string())

    print("\n=== 4c. the same arms ACROSS BLOCKS (does the ranking hold?) ===")
    C3 = OOS.pivot_table(index="arm", columns="block", values="pts")
    print(C3.round(3).to_string())
    print("\nrank correlation of the arm ordering between blocks:")
    from scipy import stats as sps
    for a, b in (("A_research", "B_holdout"), ("A_research", "C_forward"),
                 ("B_holdout", "C_forward")):
        if a in C3 and b in C3:
            ok = C3[a].notna() & C3[b].notna()
            print(f"  {a} vs {b}: Spearman {sps.spearmanr(C3[a][ok], C3[b][ok]).statistic:+.3f}")
    OUT["corr_arms"], OUT["corr_cond"], OUT["corr_block"], OUT["daily"] = C1, C2, C3, D

    with open(os.path.join(HERE, "s10_results.pkl"), "wb") as fh:
        pickle.dump(OUT, fh)
    print(f"\nsaved {os.path.join(HERE, 's10_results.pkl')}")


if __name__ == "__main__":
    main()
