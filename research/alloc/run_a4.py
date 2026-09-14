"""A4 -- choose the LEGS inside the fold, not just the weights, and deflate the search.

A3's leg-count table ranked legs by their whole research block and then walked forward from a
day inside it, so the first folds saw the ranking that chose them. The honest version selects
the legs inside every training window. That is also the question a book actually poses: A3 said
the equal-weight book PEAKS AT THREE LEGS and decays to eleven, which is `STUDY_SEMIVARIANCE`'s
finding -- a decorrelated leg still has to have an edge -- and it has to be re-asked without the
contamination.

Everything is compared at MATCHED VOLATILITY as well as raw, because A3's largest number was
pure leverage: a mean-tilt scheme made 2.7x the money and, scaled to the equal-weight book's own
volatility, made LESS. `Sizing creates no edge` is the branch's own §9 and it applies to
allocation exactly as it applies to a single strategy.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import alloccore as C  # noqa: E402
from run_a1 import apply_w  # noqa: E402
from run_a2 import prep, ALL, MIN_RES  # noqa: E402
from run_a3 import wf, REB, MINHIST  # noqa: E402

pd.set_option("display.width", 240)


def wf_select(X, span, pick, weight_fn=None, reb=REB, minhist=MINHIST, ret_folds=False):
    """pick(Xtrain) -> the list of columns to hold this fold."""
    weight_fn = weight_fn or ALL["equal"]
    idx, pieces, folds = X.index, [], []
    for s in range(minhist, len(idx), reb):
        e = min(s + reb, len(idx))
        Xt, Xv, sv = X.iloc[:s], X.iloc[s:e], span.iloc[s:e]
        live = [c for c in X.columns if (Xt[c] != 0).sum() >= MIN_RES]
        if len(live) < 3:
            continue
        cols = pick(Xt[live])
        if not len(cols):
            cols = live
        w = np.zeros(X.shape[1])
        w[[X.columns.get_loc(c) for c in cols]] = weight_fn(Xt[cols])
        d = apply_w(Xv, sv, w)
        pieces.append(d)
        folds.append(dict(start=str(idx[s].date()), end=str(idx[e - 1].date()),
                          k=len(cols), total=float(d.sum()),
                          held=",".join(f"{c[0][:4]}/{c[1][:5]}" for c in cols)))
    out = np.concatenate(pieces)
    return (out, pd.DataFrame(folds)) if ret_folds else out


def topk(k):
    def f(Xt):
        sh = (Xt.mean() / Xt.std(ddof=1)).sort_values(ascending=False)
        return list(sh.index[:k])
    return f


def positive(Xt):
    return list(Xt.columns[Xt.mean() > 0])


def main():
    X, span, use, cut = prep()
    eq_all = wf(X, span, ALL["equal"])
    eqsd = eq_all.std(ddof=1)

    def row(nm, d, extra=None):
        st = C.stats(d)
        return dict(rule=nm, **{k: st[k] for k in ("total", "sharpe", "dd", "ret_dd")},
                    tot_volmatch=float(d.sum() * eqsd / d.std(ddof=1)), **(extra or {}))

    # ---- 1. leg selection inside the fold ---------------------------------------------------
    print("=== 1. legs chosen INSIDE every training window, equal-weighted ===")
    rows = [row("all legs", eq_all)]
    for k in range(2, len(use) + 1):
        rows.append(row(f"top {k} by train Sharpe", wf_select(X, span, topk(k))))
    rows.append(row("positive train mean", wf_select(X, span, positive)))
    R = pd.DataFrame(rows)
    print(R.round(3).to_string(index=False))

    # ---- 2. the same, with a random SUBSET of the same size ---------------------------------
    print("\n=== 2. against a RANDOM subset of the same size, 400 draws ===")
    for k in (3, 5, 8):
        real = C.stats(wf_select(X, span, topk(k)))
        sh, tv = [], []
        for seed in range(400):
            rg = np.random.default_rng(5000 + seed)
            d = wf_select(X, span, lambda Xt, rg=rg, k=k:
                          list(np.asarray(Xt.columns, object)[
                              rg.choice(Xt.shape[1], size=min(k, Xt.shape[1]), replace=False)]))
            st = C.stats(d)
            sh.append(st["sharpe"])
            tv.append(d.sum() * eqsd / d.std(ddof=1))
        sh, tv = np.asarray(sh), np.asarray(tv)
        print(f"top {k:2d}: Sharpe {real['sharpe']:+.3f} at percentile "
              f"{100*np.mean(sh < real['sharpe']):5.1f}  (random med {np.median(sh):+.3f})   "
              f"vol-matched total percentile "
              f"{100*np.mean(tv < wf_select(X, span, topk(k)).sum()*eqsd/wf_select(X, span, topk(k)).std(ddof=1)):5.1f}")

    # ---- 3. selection AND weighting together ------------------------------------------------
    print("\n=== 3. the best selection rule crossed with the weighting schemes ===")
    rows = []
    for pk_name, pk in (("all", lambda Xt: list(Xt.columns)), ("top5", topk(5)),
                        ("positive", positive)):
        for wn, wf_ in ALL.items():
            d = wf_select(X, span, pk, wf_)
            rows.append(row(f"{pk_name:9s} x {wn}", d))
    R = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    print(R.round(3).to_string(index=False))

    # ---- 4. deflate ------------------------------------------------------------------------
    print("\n=== 4. what was searched ===")
    n_trials = len(ALL) * 3 + (len(use) - 1) + 3 + 3          # schemes x picks + top-k + reb
    print(f"weighting schemes {len(ALL)}, selection rules {2 + len(use) - 1}, "
          f"rebalance frequencies 3  ->  counted looks ~{n_trials}")
    best = R.iloc[0]
    print(f"best cell: {best['rule']}  Sharpe {best['sharpe']:.3f} against equal's "
          f"{C.stats(eq_all)['sharpe']:.3f}")
    # per-observation Sharpe and the expected best of that many null draws
    sh = np.array([C.stats(wf_select(X, span, pk, wf_))["sharpe"] / np.sqrt(252)
                   for pk_name, pk in (("all", lambda Xt: list(Xt.columns)), ("top5", topk(5)),
                                       ("positive", positive))
                   for wf_ in ALL.values()])
    v = sh.var(ddof=1)
    g = 0.5772156649
    N = len(sh)
    emax = np.sqrt(v) * ((1 - g) * abs(np.percentile(np.random.default_rng(0).normal(size=200000), 100*(1-1/N)))
                         + g * abs(np.percentile(np.random.default_rng(1).normal(size=200000), 100*(1-1/(N*np.e)))))
    print(f"trial Sharpe sd (per observation) {np.sqrt(v):.5f}  ->  "
          f"E[max Sharpe | null] over {N} looks {emax:.5f}   best achieved {sh.max():.5f}")

    # ---- 5. by year ------------------------------------------------------------------------
    print("\n=== 5. the equal-weight book and the best cell, by year ===")
    d_eq, f_eq = wf(X, span, ALL["equal"], ret_folds=True)
    idx = X.index[MINHIST:MINHIST + len(d_eq)]
    best_pk = topk(5) if "top5" in str(best["rule"]) else (
        positive if "positive" in str(best["rule"]) else (lambda Xt: list(Xt.columns)))
    best_w = ALL[str(best["rule"]).split("x")[-1].strip()]
    d_bs = wf_select(X, span, best_pk, best_w)
    yr = pd.DataFrame(dict(equal=d_eq, best=d_bs[:len(d_eq)]), index=idx).groupby(idx.year).agg(
        ["sum", "count"])
    print(yr.round(3).to_string())


if __name__ == "__main__":
    main()
