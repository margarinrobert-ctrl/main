"""The section-13 battery, re-run on the condition sections 14-15 promoted.

Section 13 put four Monte Carlos, a fixed-constant walk-forward and three correlation
matrices on `+adx<=20`.  Sections 14-15 then showed that arm is the weaker of the two on the
reserved feed and that the condition worth carrying is the SLOW EMA INEQUALITY alone.  The
battery therefore has to be re-run on it -- an arm that has not been through the same tests is
not a comparable arm, and quoting section 13's robustness for a rule it never tested would be
the error this file exists to avoid.

Nothing is chosen here.  The rule is fixed by sections 12-15 before this runs: Donchian 20
long, 07:00-11:00 New York, flat at the 11:00 open, 50-point stop / 150-point target, and the
single condition `EMA34 > EMA89`.  `+adx<=20` is carried beside it as the incumbent, and the
unfiltered base as the floor.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "us30scalp"))
import r_lib as R  # noqa: E402
import s10lib as L  # noqa: E402
import s30core as S  # noqa: E402

pd.set_option("display.width", 220)
ARMS = [("base", []), ("+adx<=20", ["adx<=20"]), ("+ema align", ["ema align"]),
        ("+slow 34>89", ["slow34>89"])]
NEW = "+slow 34>89"


def masks(f):
    h, l, c = (f[x].to_numpy() for x in ("high", "low", "close"))
    M = L.build_masks(h, l, c)
    M["slow34>89"] = L.ema(c, 34) > L.ema(c, 89)
    return M


def dd_of(x):
    eq = np.cumsum(x)
    return float(np.max(np.maximum.accumulate(eq) - eq)) if len(x) else np.nan


def main():
    f, fi = S.load("US30L"), S.load("US30I")
    bl, bli = S.blocks(f, "US30L"), S.blocks(fi, "US30I")
    M, Mi = masks(f), masks(fi)
    sess = {b: f.index[m & S.window(f)].normalize().nunique() for b, m in bl.items()}
    sess["C_forward"] = fi.index[bli["C_forward"] & S.window(fi)].normalize().nunique()

    print("=" * 110)
    print("R5  THE SECTION-13 BATTERY ON THE CONDITION SECTIONS 14-15 PROMOTED")
    print("=" * 110)

    # ---------- 1. three blocks, two providers ----------------------------------------
    print("\n=== 1. OUT OF SAMPLE ===")
    rows, daily = [], {}
    for nm, cond in ARMS:
        for feed, MM, bset in ((f, M, bl), (fi, Mi, bli)):
            for bn, bm in bset.items():
                t = L.trades(feed, cond, bm, MM)
                if len(t) < 20:
                    continue
                r = L.stats(t, sess.get(bn, 250)); r.update(arm=nm, block=bn)
                rows.append(r)
                if bn != "C_forward" or feed is fi:
                    daily[(nm, bn)] = t
    O = pd.DataFrame(rows)
    print(O[["arm", "block", "n", "pts", "t", "mde", "pf", "win", "total", "dd", "ret_dd",
             "sharpe"]].to_string(index=False, formatters={
                 "pts": "{:+.3f}".format, "t": "{:+.3f}".format, "mde": "{:.2f}".format,
                 "pf": "{:.3f}".format, "win": "{:.3f}".format, "total": "{:+.0f}".format,
                 "dd": "{:.0f}".format, "ret_dd": "{:+.2f}".format, "sharpe": "{:+.2f}".format}))
    O.to_csv(os.path.join(HERE, "r5_oos.csv"), index=False)
    print("\n  arms positive on all three blocks:")
    for nm, _ in ARMS:
        s = O[O.arm == nm]
        print(f"    {nm:<13} {int((s.pts > 0).sum())}/{len(s)}   "
              f"spread {s.pts.min():+.3f} .. {s.pts.max():+.3f}")

    # ---------- 2. four Monte Carlos on the NEW arm ------------------------------------
    print(f"\n=== 2. MONTE CARLO on `{NEW}` ===")
    mc = {}
    for bn, bm in bl.items():
        t = L.trades(f, ["slow34>89"], bm, M)
        p = t["pts"].to_numpy()
        d = t.groupby(t.ts.dt.normalize())["pts"].sum().to_numpy()
        rng = np.random.default_rng(11)
        boot = np.array([rng.choice(d, len(d), replace=True).mean() for _ in range(4000)])
        perm = np.array([dd_of(rng.permutation(p)) for _ in range(4000)])
        ex = []
        for i in range(250):
            rg = np.random.default_rng(500 + i)
            tt = L.trades(f, ["slow34>89"], bm, M, cost=S.COST * rg.uniform(0.5, 2.0))
            ex.append(tt["pts"].mean() if len(tt) else np.nan)
        ex = np.asarray(ex); ex = ex[np.isfinite(ex)]
        jt = []
        for i in range(150):
            rg = np.random.default_rng(900 + i)
            g = f.copy()
            for c in ("open", "high", "low", "close"):
                g[c] = f[c].to_numpy() + rg.normal(0, 1.0, len(f))
            g["high"] = g[["open", "high", "low", "close"]].max(axis=1)
            g["low"] = g[["open", "high", "low", "close"]].min(axis=1)
            tr = np.maximum(g.high - g.low, np.maximum((g.high - g.close.shift()).abs(),
                                                       (g.low - g.close.shift()).abs()))
            g["atr"] = tr.ewm(span=14, adjust=False).mean()
            tt = L.trades(g, ["slow34>89"], bm, masks(g))
            jt.append(tt["pts"].mean() if len(tt) else np.nan)
        jt = np.asarray(jt); jt = jt[np.isfinite(jt)]
        rdd = dd_of(p)
        mc[bn] = dict(mean=float(p.mean()), n=len(p), boot=boot, perm=perm, ex=ex, jt=jt, dd=rdd)
        print(f"\n  {bn}: realised {p.mean():+.3f} pts on n={len(p)}")
        print(f"    bootstrap (EDGE)     P(mean<=0) {np.mean(boot <= 0):.3f}   "
              f"95% CI [{np.percentile(boot, 2.5):+.2f}, {np.percentile(boot, 97.5):+.2f}] /day")
        print(f"    permutation (PATH)   realised DD {rdd:.0f}   median {np.median(perm):.0f}   "
              f"p99 {np.percentile(perm, 99):.0f}   percentile of realised "
              f"{np.mean(perm < rdd):.3f}   p99/realised {np.percentile(perm, 99) / rdd:.2f}x")
        print(f"    execution            p5 {np.percentile(ex, 5):+.3f}   "
              f"p95 {np.percentile(ex, 95):+.3f}   P(<=0) {np.mean(ex <= 0):.3f}")
        print(f"    price jitter (all indicators RECOMPUTED)  p5 {np.percentile(jt, 5):+.3f}   "
              f"p95 {np.percentile(jt, 95):+.3f}   sign kept {np.mean(jt > 0):.3f}  "
              f"({len(jt)} draws)")
    np.save(os.path.join(HERE, "r5_mc.npy"), np.array([1]))

    # ---------- 3. fixed-constant walk-forward -----------------------------------------
    print("\n=== 3. WALK-FORWARD, constants FIXED (the rule is derived, not fitted) ===")
    full = bl["A_research"] | bl["B_holdout"]
    yrs = sorted(set(f.index[full].year))
    tab = []
    for y in yrs[2:]:
        te = full & (f.index.year == y)
        if te.sum() < 500:
            continue
        r = dict(year=y)
        for nm, cond in ARMS:
            t = L.trades(f, cond, te, M)
            r[nm] = t["pts"].sum() if len(t) else np.nan
            r[nm + " n"] = len(t)
        tab.append(r)
    W = pd.DataFrame(tab)
    print(W[["year"] + [a for a, _ in ARMS]].to_string(
        index=False, float_format=lambda x: f"{x:+.0f}"))
    print("\n  folds positive / total points:")
    for nm, _ in ARMS:
        s = W[nm].dropna()
        print(f"    {nm:<13} {int((s > 0).sum())}/{len(s)} folds   total {s.sum():+.0f}   "
              f"worst {s.min():+.0f}")
    W.to_csv(os.path.join(HERE, "r5_wf.csv"), index=False)

    # ---------- 4. correlation between the arms ----------------------------------------
    print("\n=== 4. CORRELATION between the arms on daily P&L (research + holdout) ===")
    idx = pd.DatetimeIndex(sorted(set(f.index[full & S.window(f)].normalize())))
    D = {}
    for nm, cond in ARMS:
        t = L.trades(f, cond, full, M)
        D[nm] = L.daily(t, idx)
    al = L.trades(f, [], full, M)
    D["always-long"] = L.daily(S.walk(f, *S.everybar(f, 1), **L.KW), idx)
    C = pd.DataFrame(D).corr()
    print(C.to_string(float_format=lambda x: f"{x:+.3f}"))
    C.to_csv(os.path.join(HERE, "r5_corr.csv"))
    print(f"\n  `{NEW}` vs `+adx<=20` {C.loc[NEW, '+adx<=20']:+.3f}   "
          f"vs `+ema align` {C.loc[NEW, '+ema align']:+.3f}   "
          f"vs always-long {C.loc[NEW, 'always-long']:+.3f}")


if __name__ == "__main__":
    main()
