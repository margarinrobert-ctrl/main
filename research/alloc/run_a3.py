"""A3 -- the walk-forward number with a null band, per fold, and the leg-count question.

A2 left one tension. A SINGLE fit has mean-variance beating equal weight by +0.35 reserved
Sharpe and sliding the cut has it winning at 9 of 10 splits; a WALK-FORWARD that re-fits at
every rebalance has it beating equal by +0.08. The walk-forward is the honest one, and the
reason the other two disagree is worth writing down: every sliding cut ends on the SAME date,
so ten "tests" share their tail and are one test with ten start points, whereas a walk-forward
uses each out-of-sample piece exactly once.

So: put a proper null band on the walk-forward (500 random allocators run through the identical
procedure, not one draw), count the folds, and then ask the two questions a book actually poses
-- how many legs, and which.
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

pd.set_option("display.width", 220)
REB, MINHIST = 252, 504


def wf(X, span, weight_fn, reb=REB, minhist=MINHIST, ret_folds=False):
    idx = X.index
    pieces, folds = [], []
    for s in range(minhist, len(idx), reb):
        e = min(s + reb, len(idx))
        Xt, Xv, sv = X.iloc[:s], X.iloc[s:e], span.iloc[s:e]
        live = (Xt != 0).sum(axis=0) >= MIN_RES
        if live.sum() < min(3, Xt.shape[1]):
            continue
        cols = list(Xt.columns[live])
        w = np.zeros(X.shape[1])
        w[[X.columns.get_loc(c) for c in cols]] = weight_fn(Xt[cols])
        d = apply_w(Xv, sv, w)
        pieces.append(d)
        folds.append(dict(start=str(idx[s].date()), end=str(idx[e - 1].date()),
                          n=len(d), total=float(d.sum()), legs=len(cols)))
    out = np.concatenate(pieces)
    return (out, pd.DataFrame(folds)) if ret_folds else out


def main():
    X, span, use, cut = prep()
    lab = [f"{k[0]}/{k[1]}" for k in use]
    print(f"{len(use)} legs, {len(X)} calendar days {X.index.min().date()}..{X.index.max().date()}")

    # ---- 1. the walk-forward against 500 random allocators ---------------------------------
    print("\n=== 1. walk-forward, against 500 random allocators run through the SAME procedure ===")
    real = {}
    for nm, fn in ALL.items():
        d, fd = wf(X, span, fn, ret_folds=True)
        real[nm] = (d, fd)
    rnd_sh, rnd_tot, rnd_rd = [], [], []
    for seed in range(500):
        rg = np.random.default_rng(1000 + seed)
        d = wf(X, span, lambda Z, rg=rg: rg.dirichlet(np.ones(Z.shape[1])))
        st = C.stats(d)
        rnd_sh.append(st["sharpe"]); rnd_tot.append(st["total"]); rnd_rd.append(st["ret_dd"])
    rnd_sh, rnd_tot, rnd_rd = map(np.asarray, (rnd_sh, rnd_tot, rnd_rd))
    print(f"random allocator: Sharpe p5 {np.percentile(rnd_sh,5):+.3f} med "
          f"{np.median(rnd_sh):+.3f} p95 {np.percentile(rnd_sh,95):+.3f} | "
          f"total med {np.median(rnd_tot):.2f} | ret/DD med {np.median(rnd_rd):.2f}")
    eqsd = real["equal"][0].std(ddof=1)
    rows = []
    for nm, (d, fd) in real.items():
        st = C.stats(d)
        rows.append(dict(scheme=nm, total=st["total"],
                         tot_volmatch=float(d.sum() * eqsd / d.std(ddof=1)),
                         sharpe=st["sharpe"], dd=st["dd"],
                         ret_dd=st["ret_dd"],
                         pct_sharpe=100 * np.mean(rnd_sh < st["sharpe"]),
                         pct_total=100 * np.mean(rnd_tot < st["total"]),
                         pct_retdd=100 * np.mean(rnd_rd < st["ret_dd"])))
    print(pd.DataFrame(rows).round(3).to_string(index=False))

    # ---- 2. per fold ------------------------------------------------------------------------
    print("\n=== 2. per fold, each scheme's total minus equal weight's ===")
    fe = real["equal"][1]
    tab = fe[["start", "end", "n", "legs"]].copy()
    tab["equal"] = fe["total"].round(3)
    for nm in ALL:
        if nm == "equal":
            continue
        tab[nm] = (real[nm][1]["total"] - fe["total"]).round(3)
    print(tab.to_string(index=False))
    print("\nfolds beaten (of %d):" % len(fe))
    for nm in ALL:
        if nm == "equal":
            continue
        w = (real[nm][1]["total"] > fe["total"]).sum()
        print(f"   {nm:16s} {w}/{len(fe)}")

    # ---- 3. how many legs? -----------------------------------------------------------------
    print("\n=== 3. is the book monotone in the number of legs? ===")
    print("    legs added in order of RESEARCH Sharpe; equal-weighted; walk-forward")
    isr = X.index <= cut
    Xr = X.loc[isr]
    sh = (Xr.mean() / Xr.std(ddof=1)).sort_values(ascending=False)
    rows = []
    for k in range(1, len(use) + 1):
        cols = list(sh.index[:k])
        d = wf(X[cols], span[cols], ALL["equal"])
        rows.append(dict(k=k, added=f"{cols[-1][0]}/{cols[-1][1]}", **C.stats(d)))
    print(pd.DataFrame(rows).round(3).to_string(index=False))

    # ---- 4. which legs? --------------------------------------------------------------------
    print("\n=== 4. drop-one: remove each leg from the equal-weight book, walk-forward ===")
    base = C.stats(wf(X, span, ALL["equal"]))
    print(f"all {len(use)} legs: total {base['total']:.3f} Sharpe {base['sharpe']:.3f} "
          f"ret/DD {base['ret_dd']:.3f}")
    rows = []
    for i, k in enumerate(use):
        cols = [c for c in X.columns if c != k]
        st = C.stats(wf(X[cols], span[cols], ALL["equal"]))
        rows.append(dict(dropped=lab[i], d_total=st["total"] - base["total"],
                         d_sharpe=st["sharpe"] - base["sharpe"],
                         d_retdd=st["ret_dd"] - base["ret_dd"]))
    print(pd.DataFrame(rows).round(3).sort_values("d_sharpe", ascending=False).to_string(index=False))

    # ---- 5. is a book worth anything over the best single leg? -----------------------------
    print("\n=== 5. the book against its own best single leg (walk-forward, same procedure) ===")
    rows = []
    for i, k in enumerate(use):
        st = C.stats(wf(X[[k]], span[[k]], ALL["equal"]))
        rows.append(dict(leg=lab[i], **st))
    S = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    print(S.round(3).to_string(index=False))
    print(f"\nbest single leg Sharpe {S['sharpe'].max():.3f} / ret_dd {S['ret_dd'].max():.3f}   "
          f"equal-weight book {base['sharpe']:.3f} / {base['ret_dd']:.3f}")


if __name__ == "__main__":
    main()
