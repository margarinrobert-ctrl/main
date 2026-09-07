"""The battery: search curve, stability, walk-forward, Monte Carlo, costs, and the holdout.

Order matters. The search curve runs FIRST, because if best-of-K degrades out of sample then no
amount of walk-forward on the winner rescues it and the honest answer is a pre-specified rule.

Usage: python3 research/trend_validate.py
"""
from __future__ import annotations

import sys
from itertools import combinations

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from trend_pullback import (COST_MNQ, COST_NQ, HDR, POINT_VALUE_MNQ, POINT_VALUE_NQ, PRESPEC,
                            label, load, nw_t, row, run, stats, three_way)

RESULTS = "research/trend_search_results.parquet"
PARAM_COLS = ["ema_fast", "ema_slow", "trend_mode", "pull_mode", "pull_depth", "entry_mode",
              "stop_mode", "stop_mult", "target_mode", "target_r", "atr_lo", "atr_hi",
              "tod_start", "tod_end", "max_per_sess", "cooldown"]


def as_param(r):
    return {k: (int(r[k]) if k in ("ema_fast", "ema_slow", "trend_mode", "pull_mode", "entry_mode",
                                   "stop_mode", "target_mode", "max_per_sess", "cooldown")
                else float(r[k])) for k in PARAM_COLS}


def search_curve(df, n_draws=400, seed=20250822):
    """best-of-K on research -> its percentile in the holdout distribution, sweeping K."""
    rng = np.random.default_rng(seed)
    res = df.res_exp.to_numpy()
    hold = df.hold_exp.to_numpy()
    order = np.argsort(hold)
    pct_of = np.empty(len(hold))
    pct_of[order] = np.linspace(0, 100, len(hold))
    out = []
    n = len(df)
    Ks = [k for k in (1, 3, 10, 30, 100, 300, 1000, 3000, 10_000, 30_000, 100_000, 300_000) if k <= n]
    for K in Ks:
        pcts, holds = [], []
        for _ in range(n_draws):
            idx = rng.choice(n, size=K, replace=False) if K < n else np.arange(n)
            win = idx[np.argmax(res[idx])]
            pcts.append(pct_of[win]); holds.append(hold[win])
        out.append((K, float(np.mean(pcts)), float(np.mean(holds)), float(np.median(holds))))
    return pd.DataFrame(out, columns=["K", "holdout_pctile", "mean_holdout_exp", "median_holdout_exp"])


def neighbours(df, best_row):
    """Vary one parameter at a time around the winner: a plateau survives, a spike does not."""
    out = []
    for col in PARAM_COLS:
        m = np.ones(len(df), bool)
        for other in PARAM_COLS:
            if other != col:
                m &= df[other].to_numpy() == best_row[other]
        sub = df[m]
        if len(sub) > 1:
            out.append((col, len(sub), float(sub.res_exp.min()), float(sub.res_exp.max()),
                        float(sub.res_exp.std()), float(best_row["res_exp"]),
                        float(sub.hold_exp.mean())))
    return pd.DataFrame(out, columns=["param", "n_settings", "res_min", "res_max", "res_sd",
                                      "winner_res", "neighbour_hold_mean"])


def walk_forward(d, df, train_days=250, step_days=60, top_n=1):
    """Re-select on a rolling window, trade the next one. What a real user would have lived."""
    sess = d["sess"]
    days = np.unique(sess)
    cands = df.nlargest(4000, "res_exp")            # a tractable candidate pool
    params = [as_param(r) for _, r in cands.iterrows()]
    cached = []
    for p in params:
        side, ti, to, pnl, rm, why = run(d, p)
        cached.append((sess[ti], pnl, rm))
    stitched_pnl, stitched_r, picks = [], [], []
    start = 0
    while start + train_days + step_days <= len(days):
        tr = set(days[start:start + train_days])
        te = set(days[start + train_days:start + train_days + step_days])
        best, best_v = None, -np.inf
        for j, (ds, pnl, rm) in enumerate(cached):
            m = np.isin(ds, list(tr))
            if m.sum() >= 30 and pnl[m].mean() > best_v:
                best_v, best = pnl[m].mean(), j
        if best is not None:
            ds, pnl, rm = cached[best]
            m = np.isin(ds, list(te))
            stitched_pnl.append(pnl[m]); stitched_r.append(rm[m])
            picks.append(label(params[best]))
        start += step_days
    if not stitched_pnl:
        return None
    return (np.concatenate(stitched_pnl), np.concatenate(stitched_r), picks)


def monte_carlo(pnl, start_equity=50_000, n_paths=20_000, seed=20250822):
    rng = np.random.default_rng(seed)
    n = len(pnl)
    res = {}
    for mode in ("reshuffle", "resample"):
        dd = np.empty(n_paths); end = np.empty(n_paths)
        for i in range(n_paths):
            x = rng.permutation(pnl) if mode == "reshuffle" else rng.choice(pnl, n, replace=True)
            eq = start_equity + np.cumsum(x)
            peak = np.maximum.accumulate(eq)
            dd[i] = ((peak - eq) / peak).max()
            end[i] = eq[-1]
        res[mode] = dict(median_dd=float(np.median(dd)), p95_dd=float(np.percentile(dd, 95)),
                         p_loss=float((end < start_equity).mean()),
                         median_end=float(np.median(end)),
                         p5_end=float(np.percentile(end, 5)),
                         p_ruin=float((end < start_equity * 0.5).mean()))
    return res


def cost_sweep(d, p):
    out = []
    for mult in (0.0, 0.5, 1.0, 1.5, 2.0):
        side, ti, to, pnl, rm, why = run(d, p, cost=COST_NQ * mult)
        out.append((mult, COST_NQ * mult, len(pnl), float(pnl.sum()), float(pnl.mean())))
    return pd.DataFrame(out, columns=["cost_x", "cost_$", "n", "net_$", "$/trade"])


def main() -> None:
    d = load()
    sess = d["sess"]
    r_m, v_m, h_m = three_way(sess)
    ndays = lambda m: len(np.unique(sess[m]))
    df = pd.read_parquet(RESULTS)

    print("=" * 112)
    print("STAGE 2 — WHAT THE SEARCH FOUND, AND WHAT THE SEARCH COST")
    print("=" * 112)
    print(f"\n  {len(df):,} evaluable configurations from a {5_038_848:,}-cell grid")
    print(f"  research $/trade: mean {df.res_exp.mean():+.2f}, sd {df.res_exp.std():.2f}, "
          f"best {df.res_exp.max():+.2f}, {100*(df.res_exp>0).mean():.1f}% profitable")
    print(f"  holdout  $/trade: mean {df.hold_exp.mean():+.2f}, sd {df.hold_exp.std():.2f}, "
          f"best {df.hold_exp.max():+.2f}, {100*(df.hold_exp>0).mean():.1f}% profitable")
    rho = df[["res_exp", "hold_exp"]].corr(method="spearman").iloc[0, 1]
    print(f"\n  Spearman rank correlation research -> holdout: {rho:+.4f}")
    print("  (this is the number that decides whether searching helps at all)")

    print("\n  THE SEARCH CURVE — best-of-K on research, then where it landed out of sample")
    print(f"  {'K':>9}{'holdout pctile':>17}{'mean $/trade':>15}{'median $/trade':>17}")
    sc = search_curve(df)
    for _, r in sc.iterrows():
        print(f"  {int(r.K):>9,}{r.holdout_pctile:>16.1f}%{r.mean_holdout_exp:>15.2f}"
              f"{r.median_holdout_exp:>17.2f}")

    best = df.loc[df.res_exp.idxmax()]
    bp = as_param(best)
    print(f"\n  best on research: {label(bp)}")
    print(f"    research ${best.res_exp:+.2f}/trade over {int(best.res_n)} trades, t={best.res_t:.2f}")
    print(f"    validation ${best.val_exp:+.2f}/trade over {int(best.val_n)} trades")
    print(f"    holdout  ${best.hold_exp:+.2f}/trade over {int(best.hold_n)} trades")
    emax = np.sqrt(2 * np.log(len(df)))
    print(f"\n  a best-of-{len(df):,} search draws E[max z] ~ {emax:.2f} from noise alone;"
          f" this config reaches t = {best.res_t:.2f}")

    # a finalist chosen on research AND validation, which is the defensible selection rule
    both = df[(df.res_exp > 0) & (df.val_exp > 0) & (df.res_n >= 100) & (df.val_n >= 50)]
    print(f"\n  configurations profitable on BOTH research and validation: {len(both):,} "
          f"({100*len(both)/len(df):.2f}%)")
    if len(both):
        fin = both.loc[(both.res_exp + both.val_exp).idxmax()]
        fp = as_param(fin)
        print(f"  finalist (best research+validation): {label(fp)}")
        print(f"    research ${fin.res_exp:+.2f}  validation ${fin.val_exp:+.2f}  "
              f"HOLDOUT ${fin.hold_exp:+.2f} over {int(fin.hold_n)} trades")
        print(f"  holdout $/trade of ALL {len(both):,} such configs: "
              f"mean ${both.hold_exp.mean():+.2f}, median ${both.hold_exp.median():+.2f}, "
              f"{100*(both.hold_exp>0).mean():.1f}% profitable")
    else:
        fin, fp = best, bp

    print("\n" + "=" * 112)
    print("STAGE 3 — ROBUSTNESS OF THE FINALIST")
    print("=" * 112 + "\n")
    print("  PARAMETER STABILITY — vary one axis at a time; a plateau survives, a spike does not")
    nb = neighbours(df, fin)
    print(f"  {'parameter':<16}{'settings':>10}{'res min':>10}{'res max':>10}{'res sd':>9}"
          f"{'winner':>9}{'nbr holdout':>13}")
    for _, r in nb.iterrows():
        print(f"  {r['param']:<16}{int(r.n_settings):>10}{r.res_min:>10.2f}{r.res_max:>10.2f}"
              f"{r.res_sd:>9.2f}{r.winner_res:>9.2f}{r.neighbour_hold_mean:>13.2f}")

    side, ti, to, pnl, rm, why = run(d, fp)
    print(f"\n  FULL-SAMPLE behaviour of the finalist")
    print(HDR)
    print(row("all", stats(pnl, rm, len(np.unique(sess)))))
    code = np.full(len(sess), -1, np.int8); code[r_m] = 0; code[v_m] = 1; code[h_m] = 2
    cc = code[ti]
    for cval, nm in ((0, "research"), (1, "validation"), (2, "LOCKED holdout")):
        m = cc == cval
        print(row(f"  {nm}", stats(pnl[m], rm[m], ndays([r_m, v_m, h_m][cval]))))
    for s, nm in ((1, "long"), (-1, "short")):
        m = side == s
        print(row(f"  {nm}", stats(pnl[m], rm[m], len(np.unique(sess)))))
    yrs = d["seg"].index[ti].year
    for y in sorted(set(yrs)):
        m = yrs == y
        print(row(f"  {y}", stats(pnl[m], rm[m], len(np.unique(sess[ti[m]])))))

    print("\n  COST SENSITIVITY")
    cs = cost_sweep(d, fp)
    print(f"  {'cost x':>8}{'$ / RT':>9}{'n':>8}{'net $':>12}{'$/trade':>10}")
    for _, r in cs.iterrows():
        print(f"  {r.cost_x:>8.1f}{r['cost_$']:>9.2f}{int(r.n):>8,}{r['net_$']:>12,.0f}{r['$/trade']:>10.2f}")
    side_m, ti_m, to_m, pnl_m, rm_m, why_m = run(d, fp, point_value=POINT_VALUE_MNQ, cost=COST_MNQ)
    print(f"\n  MNQ (${POINT_VALUE_MNQ:.0f}/pt, ${COST_MNQ:.2f} round turn): "
          f"{len(pnl_m):,} trades, ${pnl_m.sum():,.0f}, ${pnl_m.mean():.2f}/trade")

    print("\n  WALK-FORWARD — re-selecting from the top 4,000 on a rolling 250d window, 60d steps")
    wf = walk_forward(d, df)
    if wf:
        wp, wr, picks = wf
        s = stats(wp, wr, 60 * len(picks))
        print(row("stitched out-of-sample", s))
        print(f"    {len(picks)} folds; the procedure re-picked {len(set(picks))} distinct configs")
        print(f"    fixed finalist over the whole sample: ${pnl.mean():+.2f}/trade")

    print("\n  MONTE CARLO — 20,000 paths on $50,000, finalist trade list")
    mc = monte_carlo(pnl)
    for mode, r in mc.items():
        print(f"    {mode:<10} medianDD {100*r['median_dd']:>5.1f}%  p95DD {100*r['p95_dd']:>5.1f}%  "
              f"P(loss) {100*r['p_loss']:>5.1f}%  P(ruin) {100*r['p_ruin']:>4.1f}%  "
              f"median end ${r['median_end']:>10,.0f}  5th ${r['p5_end']:>10,.0f}")

    print("\n  THE SIDE-SWITCH DIAGNOSTIC — what allowing direction to be searched would have bought")
    for sm, nm in ((1, "longs only"), (-1, "shorts only")):
        s2, t2, o2, p2, r2, w2 = run(d, fp, side_mode=sm)
        c2 = code[t2]
        print(row(f"  {nm}", stats(p2, r2, len(np.unique(sess)))))
        for cval, cn in ((0, "research"), (2, "holdout")):
            m = c2 == cval
            print(row(f"      {cn}", stats(p2[m], r2[m], ndays([r_m, v_m, h_m][cval]))))


if __name__ == "__main__":
    main()
