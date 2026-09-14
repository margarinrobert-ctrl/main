"""V61 stage A -- the population, the marginal average per axis, and the finalists.

RESEARCH ONLY. Nothing in this file reads the locked block; `run_v61b.py` does that once.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v61core as V  # noqa: E402

FLOOR = 60                      # research trades; ranking below this buys sample-size noise
AXES = ["tf", "ent", "exN", "stop", "tp", "hold", "adapt", "cvd", "ma", "chop", "psh"]
ORDERED = ["ent", "exN", "stop", "tp", "ma", "chop"]

# THE SCORE IS PERCENT OF ENTRY PRICE, NOT R. R divides by the stop, so the stop axis can be
# gamed: halving the stop roughly doubles R for the same money. `STUDY_SWEEP_110K` measured 94%
# of an apparent contribution being exactly that, and `STUDY_V36` produced +0.67 R on trades
# LOSING 1.41 points. Both units are reported and the two disagree here, which is the point.
SCORE = "tot_res"               # total percent of price earned on the research block


def load():
    fr = []
    for tf in V.TFS:
        D = V.build(tf)
        fr.append(V.table(V.run_tf(D), tf))
        print(f"  .. tf {tf} done")
    return pd.concat(fr, ignore_index=True)


def neighbourhood_mean(d, col=SCORE):
    """The mean of a cell and its one-rung neighbours on every ORDERED axis.

    A minimum over the neighbourhood is the obvious over-correction and `STUDY_1R_PROCEDURE`
    measured it costing $18,970; `STUDY_V38` measured the MEAN beating the top row on every
    fresh-market cell. So: the mean.
    """
    key = ["tf", "ent", "exN", "stop", "tp", "hold", "adapt", "cvd", "ma", "chop", "psh"]
    idx = {tuple(r): i for i, r in enumerate(d[key].to_numpy())}
    vals = d[col].to_numpy()
    lev = {a: sorted(d[a].unique()) for a in ORDERED}
    pos = {a: {v: i for i, v in enumerate(lev[a])} for a in ORDERED}
    arr = d[key].to_numpy()
    out = np.full(len(d), np.nan)
    ki = {a: key.index(a) for a in ORDERED}
    for i in range(len(d)):
        acc = [vals[i]]
        row = list(arr[i])
        for a in ORDERED:
            j = pos[a][row[ki[a]]]
            for jj in (j - 1, j + 1):
                if 0 <= jj < len(lev[a]):
                    r2 = list(row)
                    r2[ki[a]] = lev[a][jj]
                    t = idx.get(tuple(r2))
                    if t is not None and np.isfinite(vals[t]):
                        acc.append(vals[t])
        out[i] = np.mean(acc)
    return out


def main():
    print(__doc__)
    d = load()
    d.to_parquet("results/v61/grid.parquet")
    d["tot_res"] = d["n_res"] * d["pct_res"]
    d["tot_lock"] = d["n_lock"] * d["pct_lock"]
    ok = d[d["n_res"] >= FLOOR].copy()
    print("\n" + "=" * 104)
    print("A1. THE POPULATION -- read this before any row of it")
    print("=" * 104)
    print(f"  cells swept                 {len(d):,}   ({len(V.TFS)} timeframes x "
          f"{len(d)//len(V.TFS):,})")
    print(f"  cells with >= {FLOOR} research trades  {len(ok):,}  ({100*len(ok)/len(d):.1f}%)")
    print(f"  profitable on research      {100*(ok['pct_res'] > 0).mean():.1f}%   "
          f"median pct/trade {ok['pct_res'].median():+.4f}   median total {ok['tot_res'].median():+.2f}%"
          f"   median PF {ok['pf_res'].median():.3f}")
    print(f"  the best cell is therefore the maximum of ~{int((ok['pct_res']>0).sum()):,} "
          f"profitable draws.")
    inert = []
    for a in AXES:
        g = ok.groupby(a)[SCORE].mean()
        if len(g) > 1 and (g.max() - g.min()) / max(abs(g.mean()), 1e-9) < 1e-4:
            inert.append(a)
    if inert:
        eff = len(d) // int(np.prod([d[a].nunique() for a in inert]))
        print(f"  INERT AXES (spread under 0.01% of the mean): {inert} -- the EFFECTIVE cell count "
              f"is {eff:,}, not {len(d):,}. A 240-bar maximum hold never binds: with a channel exit "
              f"and an ATR stop, one of them always fires first. `STUDY_V33`: an axis that changes "
              f"nothing must be excluded, or a stability score counts a flat line as passing rungs.")
    for tf in V.TFS:
        s = ok[ok["tf"] == tf]
        print(f"    tf {tf:2d}: {len(s):,} scorable, {100*(s['pct_res']>0).mean():.1f}% profitable, "
              f"median pct/trade {s['pct_res'].median():+.4f}, median n {s['n_res'].median():.0f}")

    print("\n" + "=" * 104)
    print("A2. THE MARGINAL AVERAGE PER AXIS -- research R, over every scorable cell at that")
    print("    setting. The top row is the maximum of a million draws; the marginal is what a")
    print("    setting DOES.")
    print("=" * 104)
    best_axis = {}
    for a in AXES:
        g = ok.groupby(a).agg(tot=(SCORE, "mean"), per=("pct_res", "mean"), R=("R_res", "mean"),
                              cnt=(SCORE, "size"))
        g = g.sort_values("tot", ascending=False)
        best_axis[a] = g.index[0]
        print(f"  {a:6s} " + "   ".join(f"{k}: {v['tot']:+.1f}%/{v['per']:+.3f}/R{v['R']:+.2f}"
                                        for k, v in g.iterrows())[:200])
    print("     each cell is  total% / pct-per-trade / mean R, ordered by total%.")
    st = ok.groupby("stop").agg(tot=(SCORE, "mean"), R=("R_res", "mean"))
    print(f"\n  THE STOP AXIS DISAGREES WITH ITSELF: in R it runs "
          + " ".join(f"{k}:{v['R']:+.3f}" for k, v in st.iterrows())
          + "  and in total percent of price it runs "
          + " ".join(f"{k}:{v['tot']:+.1f}" for k, v in st.iterrows())
          + ". R divides by the stop, so a tighter stop earns a larger R for the same money.")
    print("\n  marginal-consensus cell:", {k: best_axis[k] for k in AXES})

    print("\n" + "=" * 104)
    print("A3. THE FINALISTS -- four, declared here, read once on the locked block by run_v61b")
    print("=" * 104)
    ok["nb"] = neighbourhood_mean(ok)
    cv = ok[ok["cvd"] != "off"].copy()
    best_cvd = {a: (cv.groupby(a)[SCORE].mean().idxmax()) for a in AXES}
    fin = {}
    fin["F1 marginal consensus"] = dict(best_axis)
    fin["F2 top research total"] = {a: ok.sort_values(SCORE, ascending=False).iloc[0][a]
                                    for a in AXES}
    fin["F3 best neighbourhood mean"] = {a: ok.sort_values("nb", ascending=False).iloc[0][a]
                                         for a in AXES}
    fin["F4 top research Sharpe"] = {a: ok.sort_values("sh_res", ascending=False).iloc[0][a]
                                     for a in AXES}
    fin["F5 top research per trade"] = {a: ok.sort_values("pct_res", ascending=False).iloc[0][a]
                                        for a in AXES}
    fin["G1 CVD kept: consensus"] = dict(best_cvd)
    fin["G2 CVD kept: top total"] = {a: cv.sort_values(SCORE, ascending=False).iloc[0][a]
                                     for a in AXES}
    fin["G3 CVD kept: top Sharpe"] = {a: cv.sort_values("sh_res", ascending=False).iloc[0][a]
                                      for a in AXES}
    fin["G4 CVD kept: neighbourhood"] = {a: cv.sort_values("nb", ascending=False).iloc[0][a]
                                         for a in AXES}
    fin["S  shipped (the incumbent)"] = dict(tf=30, ent=20, exN=20, stop=2.0, tp=0.0, hold=480,
                                             adapt=0, cvd="k3w20", ma=-99.0, chop=99.0, psh=0)
    rows = []
    for name, cell in fin.items():
        m = np.ones(len(ok), bool)
        for a, v in cell.items():
            m &= ok[a].to_numpy() == v
        s = ok[m]
        if not len(s):
            print(f"  {name}: NOT SCORABLE (the consensus cell has < {FLOOR} research trades)")
            continue
        r = s.iloc[0]
        rows.append(dict(name=name, **{a: r[a] for a in AXES}, n_res=int(r["n_res"]),
                         R_res=float(r["R_res"]), pf_res=float(r["pf_res"]),
                         pct_res=float(r["pct_res"]), tot_res=float(r["tot_res"]),
                         sh_res=float(r["sh_res"]), win_res=float(r["win_res"]),
                         nb=float(r["nb"])))
        print(f"  {name:28s} n {int(r['n_res']):4d}  total {r['tot_res']:+7.2f}%  "
              f"pct/trade {r['pct_res']:+.4f}  PF {r['pf_res']:5.2f}  Sharpe {r['sh_res']:+5.2f}  "
              f"R {r['R_res']:+.3f}  win {100*r['win_res']:5.1f}%  nb {r['nb']:+.2f}")
        print(f"     {{" + ", ".join(f"{a}={cell[a]}" for a in AXES) + "}")
    pd.DataFrame(rows).to_csv("results/v61/finalists.csv", index=False)
    print("\n  MULTIPLICITY: the finalists chosen from %s scorable cells. Everything they are"
          % f"{len(ok):,}")
    print("  compared against on the locked block carries that, and the p-values are not")
    print("  corrected for it -- they are read as a ranking, not as significance.")


if __name__ == "__main__":
    main()
