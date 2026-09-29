"""Corrections and the two questions section F left open.

(1) SHARPE. `run_v64` annualised per-TRADE returns with a per-BAR factor, which is wrong and
    printed figures of 7-12. Sharpe is recomputed here on DAILY returns, zero-filled over every
    session in the block -- the branch's own rule, because over traded days only a filter is paid
    for trading less.
(2) THE BOX EDGES. The top configurations sit at stop ~3.8-3.9 against a ceiling of 4.0 and
    channels of 68-80 against a ceiling of 80. An optimum on the boundary is not an optimum, so
    the box is widened and the study re-run to see whether it keeps running.
(3) THE CONTROL. A locked total is not evidence until it beats a null. Every finalist is scored
    against a same-selectivity random FILTER and a random ENTRY with identical geometry.
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
MIN_TRADES = 40


def line(t):
    print("\n" + "=" * 122)
    print(t)
    print("=" * 122)


FINALS = [
    ("shipped incumbent (V61 30m)",
     dict(tf=30, ent=20, exN=20, stop=2.0, tp=0.0, hold=480, adapt=0, k=3, w=20,
          use_ma=0, ma_thr=0.0, use_chop=0, chop_thr=99.0, psh=0)),
    ("shipped 15m preset",
     dict(tf=15, ent=15, exN=30, stop=3.0, tp=6.0, hold=480, adapt=0, k=3, w=30,
          use_ma=0, ma_thr=0.0, use_chop=0, chop_thr=99.0, psh=0)),
    ("TPE / return best",
     dict(tf=15, ent=68, exN=80, stop=3.84, tp=5.73, hold=336, adapt=0, k=5, w=60,
          use_ma=0, ma_thr=-0.33, use_chop=0, chop_thr=37.0, psh=0)),
    ("TPE / fold-median best",
     dict(tf=60, ent=76, exN=68, stop=3.94, tp=5.06, hold=251, adapt=0, k=3, w=55,
          use_ma=0, ma_thr=0.19, use_chop=1, chop_thr=45.0, psh=0)),
    ("NSGA-II best return",
     dict(tf=15, ent=20, exN=34, stop=3.14, tp=5.38, hold=255, adapt=0, k=5, w=58,
          use_ma=0, ma_thr=0.34, use_chop=0, chop_thr=55.0, psh=0)),
    ("neighbourhood centre",
     dict(tf=15, ent=68, exN=77, stop=3.74, tp=5.87, hold=318, adapt=0, k=5, w=58,
          use_ma=0, ma_thr=0.14, use_chop=0, chop_thr=39.0, psh=0)),
]


if __name__ == "__main__":
    Ds = {tf: O.build(tf) for tf in (15, 30, 60)}

    line("A. SHARPE, RECOMPUTED ON DAILY RETURNS (the figures in run_v64 section F were wrong)")
    print("  A per-trade series annualised with a per-BAR factor gave 7-12. Below, each trade is")
    print("  placed on its EXIT day, summed per day and zero-filled over every session in the")
    print("  block, then annualised at sqrt(252).")
    print(f"\n  {'configuration':34s}{'res n':>7s}{'res tot%':>10s}{'res Sh':>9s}"
          f"{'lock n':>8s}{'lock tot%':>11s}{'lock %/t':>10s}{'lock PF':>9s}{'lock Sh':>9s}"
          f"{'lock maxDD%':>13s}")
    rows = []
    for nm, p in FINALS:
        D = Ds[int(p["tf"])]
        R, pct, blk, sig = O.evaluate(D, p)
        rec = dict(name=nm)
        for which, tag in ((0, "res"), (1, "lock")):
            v = pct[blk == which]
            if len(v) < 3:
                continue
            lo, hi = (0, D["cut"]) if which == 0 else (D["cut"], D["n"])
            ix = pd.DatetimeIndex(D["ix"])
            univ = ix[lo:hi].normalize().unique()
            tdays = ix[sig[blk == which]].normalize()
            daily = (pd.Series(v, index=tdays).groupby(level=0).sum()
                     .reindex(univ).fillna(0.0).to_numpy())
            sd = daily.std(ddof=1)
            eq = np.cumsum(v)
            dd = float((eq - np.maximum.accumulate(eq)).min())
            g_, b_ = v[v > 0].sum(), -v[v <= 0].sum()
            rec.update({f"{tag}_n": len(v), f"{tag}_tot": v.sum(), f"{tag}_pct": v.mean(),
                        f"{tag}_pf": g_ / b_ if b_ > 0 else np.nan,
                        f"{tag}_sh": np.sqrt(252) * daily.mean() / sd if sd > 0 else np.nan,
                        f"{tag}_dd": dd, f"{tag}_sess": len(univ)})
        rows.append(rec)
        print(f"  {nm:34s}{rec['res_n']:>7d}{rec['res_tot']:>10.2f}{rec['res_sh']:>9.2f}"
              f"{rec['lock_n']:>8d}{rec['lock_tot']:>11.2f}{rec['lock_pct']:>10.4f}"
              f"{rec['lock_pf']:>9.3f}{rec['lock_sh']:>9.2f}{rec['lock_dd']:>13.2f}")
    pd.DataFrame(rows).to_parquet("results/v64/finalists_fixed.parquet")

    line("B. THE BOX EDGES -- widen it and see whether the optimum keeps running")
    def suggest_wide(tr):
        return dict(
            tf=tr.suggest_categorical("tf", [15, 30, 60]),
            ent=tr.suggest_int("ent", 10, 150), exN=tr.suggest_int("exN", 10, 150),
            stop=tr.suggest_float("stop", 1.0, 8.0), tp=tr.suggest_float("tp", 0.0, 12.0),
            hold=tr.suggest_int("hold", 120, 960),
            adapt=tr.suggest_categorical("adapt", [0, 1]),
            k=tr.suggest_int("k", O.K_MIN, O.K_MAX), w=tr.suggest_int("w", 3, 120),
            use_ma=0, ma_thr=0.0,
            use_chop=tr.suggest_categorical("use_chop", [0, 1]),
            chop_thr=tr.suggest_float("chop_thr", 30.0, 70.0), psh=0)

    # the wider box needs wider precomputed channels
    for tf, D in Ds.items():
        sh = pd.Series(D["h"]); sl = pd.Series(D["l"])
        D["ent_all"] = np.vstack([sh.rolling(n).max().shift(1).to_numpy() for n in range(10, 151)])
        D["exl_all"] = np.vstack([sl.rolling(n).min().shift(1).to_numpy() for n in range(10, 151)])
    O.CH_MIN, O.CH_MAX = 10, 150

    keep = []

    def obj(tr):
        p = suggest_wide(tr)
        R, pct, blk, sig = O.evaluate(Ds[p["tf"]], p)
        m = blk == 0
        if m.sum() < MIN_TRADES:
            return -1e6
        v = float(pct[m].sum())
        keep.append(dict(**p, n_res=int(m.sum()), tot_res=v))
        return v

    st = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=7))
    st.optimize(obj, n_trials=1500, show_progress_bar=False)
    W = pd.DataFrame(keep)
    W.to_parquet("results/v64/wide.parquet")
    bp = st.best_params
    print(f"  1,500 more trials on a box 2-3x wider on every continuous axis.")
    print(f"  best research total {st.best_value:+.2f}% at "
          f"tf {bp['tf']} ent {bp['ent']} exN {bp['exN']} stop {bp['stop']:.2f} "
          f"tp {bp['tp']:.2f} hold {bp['hold']} k {bp['k']} w {bp['w']}")
    top = W.nlargest(50, "tot_res")
    print(f"\n  {'axis':10s}{'box':>16s}{'top-50 median':>15s}{'top-50 p90':>12s}"
          f"{'at the ceiling?':>18s}")
    for ax, lo, hi in (("ent", 10, 150), ("exN", 10, 150), ("stop", 1.0, 8.0),
                       ("tp", 0.0, 12.0), ("w", 3, 120), ("hold", 120, 960)):
        med, p90 = top[ax].median(), top[ax].quantile(0.9)
        print(f"  {ax:10s}{f'[{lo}, {hi}]':>16s}{med:>15.2f}{p90:>12.2f}"
              f"{('YES' if p90 >= lo + 0.9 * (hi - lo) else 'no'):>18s}")
    bpp = dict(bp); bpp.update(use_ma=0, ma_thr=0.0, psh=0)
    R, pct, blk, sig = O.evaluate(Ds[int(bpp["tf"])], bpp)
    print(f"\n  and on the LOCKED block that widest-box optimum reads "
          f"n {int((blk==1).sum())}  {pct[blk==1].mean():+.4f} %/trade  "
          f"total {pct[blk==1].sum():+.2f}%  against the shipped 15m preset's +17.91%")
