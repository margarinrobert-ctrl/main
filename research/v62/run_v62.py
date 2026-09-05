"""V62 stage A -- base rates first, then the population, the marginals and the matched pairs.

RESEARCH ONLY. `run_v62b.py` reads the locked block once.

THE MATCHED-PAIRS TEST IS THE POINT. A marginal average tells you what a setting does on average
over a grid whose other axes move; a matched pair holds every other axis FIXED and switches one
condition on. The grid is built so that every filtered cell has an exact `off` twin, which makes
the ablation free -- `STUDY_V41` used the same construction to show an EMA cross helping in 42.0%
of 51,216 matched pairs on research and 50.0% on locked, which is chance.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v62core as V  # noqa: E402

FLOOR = 60
SCORE = "tot_res"
AXES = ["tf", "ent", "exN", "stop", "tp", "adapt", "cvd", "psh", "mfi", "mfi_n", "ema",
        "ema_f", "ema_s"]
PAIRKEY = ["tf", "ent", "exN", "stop", "tp", "adapt", "cvd", "psh"]


def load():
    fr = []
    for tf in V.TFS:
        D = V.build(tf)
        fr.append(V.table(V.run_tf(D), tf))
        print(f"  .. tf {tf} swept")
    return pd.concat(fr, ignore_index=True)


def matched_pairs(d, family, blk):
    """Every cell with the OTHER family off, against its own `off` twin. Returns the share of
    pairs the condition improves and the mean change, in percent of price per trade."""
    other = "ema" if family == "mfi" else "mfi"
    s = d[d[other] == "off"]
    d = s
    key = PAIRKEY + ([f"{other}_n"] if False else [])
    base = s[s[family] == "off"].set_index(PAIRKEY)[f"pct_{blk}"]
    rows = []
    for name, grp in s[s[family] != "off"].groupby([family] + ([f"{family}_n"] if family == "mfi"
                                                               else ["ema_f", "ema_s"])):
        g = grp.set_index(PAIRKEY)
        b = base.reindex(g.index)
        ok = np.isfinite(g[f"pct_{blk}"].to_numpy()) & np.isfinite(b.to_numpy())
        if ok.sum() < 20:
            continue
        dv = g[f"pct_{blk}"].to_numpy()[ok] - b.to_numpy()[ok]
        nb = d[d[family] == "off"].set_index(PAIRKEY)["n_res"].reindex(g.index).to_numpy()[ok]
        rows.append(dict(condition=" ".join(str(x) for x in np.atleast_1d(name)),
                         pairs=int(ok.sum()), helps=float((dv > 0).mean()), mean=float(dv.mean()),
                         kept=float(g["n_res"].to_numpy()[ok].sum() / max(nb.sum(), 1))))
    return pd.DataFrame(rows)


def main():
    print(__doc__)
    print("=" * 108)
    print("A1. THE BASE RATE ON THE TRIGGER'S OWN BARS -- before any profit and loss")
    print("=" * 108)
    print("  A confirmation that passes 90% of the bars the trigger already fires on is not a")
    print("  filter. `STUDY_V16`: RSI(14) >= 55 passes 94.7% of breakout bars. `STUDY_V60`: Aroon")
    print("  osc >= 0 passes 100.0%. Two lines, ahead of any sweep.\n")
    for tf in V.TFS:
        D = V.build(tf)
        br = V.base_rates(D)
        print(f"  --- {tf}-minute bars, Donchian 20 breakout bars vs all bars")
        for _, r in br.iterrows():
            flag = ("  <-- INERT, removes under 15% of signals" if r["on_breakouts"] > 0.85
                    else ("  <-- selective" if r["on_breakouts"] < 0.60 else ""))
            print(f"    {r['condition']:34s} passes {100*r['on_breakouts']:5.1f}% of breakouts "
                  f"against {100*r['on_all_bars']:5.1f}% of bars   lift {r['lift']:.2f}{flag}")
        print()

    d = load()
    d.to_parquet("results/v62/grid.parquet", compression="zstd", index=False)
    ok = d[d["n_res"] >= FLOOR].copy()
    print("=" * 108)
    print("A2. THE POPULATION")
    print("=" * 108)
    print(f"  cells swept {len(d):,}   scorable (>= {FLOOR} research trades) {len(ok):,} "
          f"({100*len(ok)/len(d):.1f}%)")
    print(f"  profitable on research {100*(ok['pct_res']>0).mean():.1f}%   median pct/trade "
          f"{ok['pct_res'].median():+.4f}   median PF {ok['pf_res'].median():.3f}")

    print("\n" + "=" * 108)
    print("A3. THE MARGINAL AVERAGE PER AXIS -- total percent of price, then percent per trade")
    print("=" * 108)
    for a in AXES:
        g = ok.groupby(a).agg(tot=(SCORE, "mean"), per=("pct_res", "mean"), n=("n_res", "mean"),
                              cnt=(SCORE, "size")).sort_values("tot", ascending=False)
        print(f"  {a:6s} " + "   ".join(f"{k}: {v['tot']:+.1f}%/{v['per']:+.4f}/n{v['n']:.0f}"
                                        for k, v in g.iterrows())[:190])

    print("\n" + "=" * 108)
    print("A4. MATCHED PAIRS ON RESEARCH -- every cell against its own `off` twin, the OTHER")
    print("    family held off, so one condition is the only difference")
    print("=" * 108)
    for fam in ("mfi", "ema"):
        mp = matched_pairs(ok, fam, "res")
        if not len(mp):
            continue
        print(f"  --- {fam.upper()}")
        for _, r in mp.sort_values("mean", ascending=False).iterrows():
            print(f"    {r['condition']:28s} {int(r['pairs']):5d} pairs   keeps "
                  f"{100*r['kept']:5.1f}% of the signals   helps {100*r['helps']:5.1f}%   "
                  f"mean change {r['mean']:+.4f} %/trade")
        mp.to_csv(f"results/v62/pairs_{fam}_res.csv", index=False)

    print("\n" + "=" * 108)
    print("A5. THE FINALISTS -- declared here, read once on the locked block by run_v62b")
    print("=" * 108)
    fin = {}
    best = {a: ok.groupby(a)[SCORE].mean().idxmax() for a in AXES}
    fin["F1 marginal consensus"] = dict(best)
    fin["F2 top research total"] = {a: ok.sort_values(SCORE, ascending=False).iloc[0][a]
                                    for a in AXES}
    fin["F3 top research Sharpe"] = {a: ok.sort_values("sh_res", ascending=False).iloc[0][a]
                                     for a in AXES}
    cv = ok[(ok["cvd"] != "off") & ((ok["mfi"] != "off") | (ok["ema"] != "off"))]
    fin["F4 CVD + a confirmation, top total"] = {a: cv.sort_values(SCORE, ascending=False).iloc[0][a]
                                                 for a in AXES}
    fin["F5 CVD + a confirmation, top Sharpe"] = {a: cv.sort_values("sh_res", ascending=False).iloc[0][a]
                                                  for a in AXES}
    fin["S  V61 incumbent (no confirmation)"] = dict(tf=30, ent=20, exN=20, stop=2.0, tp=0.0,
                                                     adapt=0, cvd="k3w20", psh=0, mfi="off",
                                                     mfi_n=0, ema="off", ema_f=0, ema_s=0)
    rows = []
    for name, cell in fin.items():
        m = np.ones(len(ok), bool)
        for a, v in cell.items():
            m &= ok[a].to_numpy() == v
        s = ok[m]
        if not len(s):
            print(f"  {name}: NOT SCORABLE at the {FLOOR}-trade floor")
            continue
        r = s.iloc[0]
        rows.append(dict(name=name, **{a: r[a] for a in AXES}, n_res=int(r["n_res"]),
                         pct_res=float(r["pct_res"]), tot_res=float(r["tot_res"]),
                         pf_res=float(r["pf_res"]), sh_res=float(r["sh_res"])))
        print(f"  {name:38s} n {int(r['n_res']):4d}  total {r['tot_res']:+7.2f}%  pct/trade "
              f"{r['pct_res']:+.4f}  PF {r['pf_res']:5.2f}  Sharpe {r['sh_res']:+5.2f}")
        print("     " + ", ".join(f"{a}={cell[a]}" for a in AXES))
    pd.DataFrame(rows).to_csv("results/v62/finalists.csv", index=False)


if __name__ == "__main__":
    main()
