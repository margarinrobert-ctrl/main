"""Parameter sensitivity and the doubled-slippage re-run.

READ BY MARGINAL AVERAGE PER AXIS, NEVER BY THE TOP ROW. The top row of any grid is the maximum
of as many draws as the grid has cells, and with 31 trades at the base configuration a single cell
here is a handful of trades. The out-of-sample block is read ONCE, for two pre-committed
configurations: the spec as written, and the marginal consensus chosen on development+validation.
"""
from __future__ import annotations

import itertools
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import orb_core as C   # noqa: E402
import orb_run as R    # noqa: E402

pd.set_option("display.width", 240)

ATR_TF = [5, 30, 60, 240]
RATIO = [(0.3, 1.5), (0.2, 2.0), (0.3, 2.5), (0.5, 3.0), (0.0, 99.0)]
VOLM = [1.0, 1.1, 1.2, 1.4]
BUF = [0.0, 0.05, 0.10]
STOP = [0.75, 1.0, 1.5]
HTFS = [15, 30, 60]
TTF = [1, 5]

BASE = dict(atr_tf=5, ratio=(0.3, 1.5), vol=1.2, buf=0.05, stop=1.0, htf=15, ttf=5)


def line(t):
    print("\n" + "=" * 122)
    print(t)
    print("=" * 122)


def score(t, D, mask, blockname):
    sess_b = np.unique(D["sess"][mask])
    tt = t[t["sess"].isin(sess_b)] if len(t) else t
    days = pd.to_datetime(pd.Series(sess_b).astype(str), format="%Y%m%d")
    s = R.stats(tt, days)
    return {f"{blockname}_{k}": v for k, v in s.items()}


if __name__ == "__main__":
    cache = {}
    def get(ttf, htf, atr_tf):
        k = (ttf, htf, atr_tf)
        if k not in cache:
            cache[k] = C.build("NQ", trade_tf=ttf, htf=htf, atr_tf=atr_tf)
        return cache[k]

    rows = []
    combos = list(itertools.product(TTF, HTFS, ATR_TF, RATIO, VOLM, BUF, STOP))
    print(f"sweeping {len(combos):,} configurations "
          f"({len(TTF)}x{len(HTFS)}x{len(ATR_TF)} builds) ...")
    for ttf, htf, atr_tf, rat, vm, bf, st in combos:
        D = get(ttf, htf, atr_tf)
        blk, _ = R.blocks_of(D)
        t, _ = R.run(D, ratio_lo=rat[0], ratio_hi=rat[1], vol_mult=vm, buf_atr=bf, stop_atr=st)
        r = dict(ttf=ttf, htf=htf, atr_tf=atr_tf, ratio=f"{rat[0]}-{rat[1]}", vol=vm, buf=bf,
                 stop=st, n_all=len(t))
        for name, key in (("development", "dev"), ("validation", "val"), ("out-of-sample", "oos")):
            r.update(score(t, D, blk[name], key))
        r["is_n"] = r["dev_trades"] + r["val_trades"]
        r["is_total"] = (r.get("dev_total", 0) or 0) + (r.get("val_total", 0) or 0)
        r["is_exp"] = r["is_total"] / r["is_n"] if r["is_n"] else np.nan
        rows.append(r)
    g = pd.DataFrame(rows)
    g.to_parquet("results/orb/sweep.parquet")

    line("A. GRID SHAPE FIRST -- what share of the space is profitable, before any top row")
    sc = g[g["is_n"] >= 20]
    print(f"  {len(g):,} configurations, {len(sc):,} with at least 20 in-sample trades")
    print(f"  profitable in-sample (development + validation): "
          f"{100*(sc['is_total'] > 0).mean():.1f}%")
    print(f"  profitable on development alone:                 "
          f"{100*(sc['dev_total'] > 0).mean():.1f}%")
    print(f"  median in-sample expectancy ${sc['is_exp'].median():,.2f}/trade   "
          f"median trade count {sc['is_n'].median():.0f}")
    print(f"  in-sample to out-of-sample expectancy correlation: "
          f"Pearson {sc['is_exp'].corr(sc['oos_expectancy']):+.3f}   "
          f"Spearman {sc['is_exp'].corr(sc['oos_expectancy'], method='spearman'):+.3f}")

    line("B. THE MARGINAL AVERAGE PER AXIS -- in-sample, which is the only block that may choose")
    for ax, vals in (("ttf", TTF), ("htf", HTFS), ("atr_tf", ATR_TF),
                     ("ratio", [f"{a}-{b}" for a, b in RATIO]), ("vol", VOLM),
                     ("buf", BUF), ("stop", STOP)):
        print(f"\n  {ax}")
        for v in vals:
            m = sc[sc[ax] == v]
            if not len(m):
                print(f"    {str(v):>10s}   (no scorable cell)")
                continue
            print(f"    {str(v):>10s}   n_cells {len(m):4d}   median trades {m['is_n'].median():5.0f}"
                  f"   mean IS exp {m['is_exp'].mean():+9.2f}   median IS exp {m['is_exp'].median():+9.2f}"
                  f"   share profitable {100*(m['is_total']>0).mean():5.1f}%")

    line("C. THE TWO CONFIGURATIONS THE OUT-OF-SAMPLE BLOCK IS READ FOR")
    print("  multiplicity: 4,320 configurations were scored in-sample. Two are read out of sample:")
    print("  (1) the spec exactly as written, which chose nothing here, and (2) the marginal")
    print("  consensus -- the best setting of each axis taken independently from panel B, which is")
    print("  NOT the best cell and is not expected to be.")

    cons = {}
    for ax in ("ttf", "htf", "atr_tf", "ratio", "vol", "buf", "stop"):
        mm = sc.groupby(ax)["is_exp"].mean()
        cons[ax] = mm.idxmax()
    print(f"\n  marginal consensus: {cons}")

    out = []
    for label, cfg in (("spec as written", BASE),
                       ("marginal consensus", dict(ttf=cons["ttf"], htf=cons["htf"],
                                                   atr_tf=cons["atr_tf"],
                                                   ratio=tuple(float(x) for x in
                                                               cons["ratio"].split("-")),
                                                   vol=cons["vol"], buf=cons["buf"],
                                                   stop=cons["stop"]))):
        D = get(cfg["ttf"], cfg["htf"], cfg["atr_tf"])
        blk, _ = R.blocks_of(D)
        for slipmult, tag in ((1.0, ""), (2.0, " [2x slippage]")):
            t, _ = R.run(D, ratio_lo=cfg["ratio"][0], ratio_hi=cfg["ratio"][1],
                         vol_mult=cfg["vol"], buf_atr=cfg["buf"], stop_atr=cfg["stop"],
                         slip=C.SLIP * slipmult)
            for name in ("development", "validation", "out-of-sample"):
                sess_b = np.unique(D["sess"][blk[name]])
                tt = t[t["sess"].isin(sess_b)] if len(t) else t
                days = pd.to_datetime(pd.Series(sess_b).astype(str), format="%Y%m%d")
                out.append(dict(config=label + tag, block=name, **R.stats(tt, days)))
    o = pd.DataFrame(out)
    for cfg in o["config"].unique():
        print(f"\n  {cfg}")
        sub = o[o["config"] == cfg]
        R.table([r for _, r in sub.iterrows()], list(sub["block"]))

    line("D. DOUBLED SLIPPAGE, SIDE BY SIDE")
    print(f"  {'config':28s}{'block':16s}{'expectancy':>13s}{'2x slip':>13s}{'Δ':>11s}"
          f"{'PF':>9s}{'PF 2x':>9s}")
    for base_lab in ("spec as written", "marginal consensus"):
        for name in ("development", "validation", "out-of-sample"):
            a = o[(o["config"] == base_lab) & (o["block"] == name)].iloc[0]
            b = o[(o["config"] == base_lab + " [2x slippage]") & (o["block"] == name)].iloc[0]
            if a.get("trades", 0) == 0:
                continue
            print(f"  {base_lab:28s}{name:16s}{a['expectancy']:13,.2f}{b['expectancy']:13,.2f}"
                  f"{b['expectancy']-a['expectancy']:+11,.2f}{a['pf']:9.3f}{b['pf']:9.3f}")
    o.to_parquet("results/orb/oos_reads.parquet")

    line("E. THE TOP TEN IN-SAMPLE CELLS, AND WHAT THEY DID OUT OF SAMPLE")
    top = sc.sort_values("is_exp", ascending=False).head(10)
    print(top[["ttf", "htf", "atr_tf", "ratio", "vol", "buf", "stop", "is_n", "is_exp",
               "oos_trades", "oos_expectancy", "oos_pf"]].to_string(
        index=False, float_format=lambda v: f"{v:,.3f}"))
    print(f"\n  mean IS expectancy of the top 10 {top['is_exp'].mean():+,.2f} against "
          f"OOS {top['oos_expectancy'].mean():+,.2f}; that gap is the selection premium.")
    print("  This block is printed BECAUSE it is not the answer, not as the answer.")
