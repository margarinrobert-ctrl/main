"""V63 stage A -- base rates, the population, the marginal per axis, and the finalists.

US100's RESEARCH BLOCK ONLY. `run_v63b.py` reads US100's later blocks, the whole of US30 and the
whole of NQ, once.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v63core as V  # noqa: E402

FLOOR = 60
SCORE = "sh_research"      # an annualised trade Sharpe: it balances per-trade edge against count
AXES = ["tf", "ema", "win", "vwap", "anchor", "weight", "atrg", "stop", "trail", "tp"]


def base_rates():
    print("=" * 112)
    print("A1. BASE RATES ON THE TRIGGER'S OWN BARS -- before any profit and loss")
    print("=" * 112)
    print("  A confirmation that passes most of the bars the trigger already fires on is the")
    print("  trigger restated. Measured on the FRESH triple-EMA stack bars (8/21/55).\n")
    for market in ("US100", "NQ"):
        for tf in (15, 30):
            D = V.build(market, tf)
            e = D["ema"][(8, 21, 55)]
            fresh = np.flatnonzero(e["stack"] & (e["since"] == 0))
            fresh = fresh[(fresh > 300) & (fresh < D["n"] - V.HOLD - 5)]
            allb = np.arange(300, D["n"] - V.HOLD - 5)
            print(f"  --- {market} {tf}m   {len(fresh):,} fresh stacks in {D['n']:,} bars "
                  f"({100*len(fresh)/D['n']:.2f}%)")
            for read in V.VWAP_READS:
                if read == "off":
                    continue
                for anc in V.ANCHORS:
                    a = V.vwap_mask(D, fresh, anc, "vol", read).mean()
                    b = V.vwap_mask(D, allb, anc, "vol", read).mean()
                    print(f"      VWAP {anc:8s} {read:18s} passes {100*a:5.1f}% of triggers "
                          f"against {100*b:5.1f}% of bars   lift {a/max(b,1e-9):.2f}")
            for g, m in (("atr>=mean", D["atr"] >= D["atr_mean"]),
                         ("atr>=1.1x mean", D["atr"] >= 1.1 * D["atr_mean"])):
                a, b = m[fresh].mean(), m[allb].mean()
                print(f"      ATR      {g:27s} passes {100*a:5.1f}% against {100*b:5.1f}%   "
                      f"lift {a/max(b,1e-9):.2f}")
            print()


def main():
    print(__doc__)
    base_rates()
    fr = []
    for tf in V.TFS:
        fr.append(V.table(V.run_market("US100", tf), "US100", tf))
        print(f"  .. US100 {tf}m swept")
    d = pd.concat(fr, ignore_index=True)
    d.to_parquet("results/v63/us100_grid.parquet", compression="zstd", index=False)
    ok = d[d["n_research"] >= FLOOR].copy()

    print("\n" + "=" * 112)
    print("A2. THE POPULATION ON US100 RESEARCH -- read this before any row of it")
    print("=" * 112)
    print(f"  cells {len(d):,}   scorable (>= {FLOOR} trades) {len(ok):,}")
    print(f"  profitable {100*(ok['pct_research']>0).mean():.1f}%   median pct/trade "
          f"{ok['pct_research'].median():+.4f}   median PF {ok['pf_research'].median():.3f}   "
          f"median Sharpe {ok['sh_research'].median():+.2f}")
    inert = []
    for a in AXES:
        g = ok.groupby(a)[SCORE].mean()
        if len(g) > 1 and (g.max() - g.min()) / max(abs(g.mean()), 1e-9) < 1e-4:
            inert.append(a)
    print(f"  inert axes: {inert if inert else 'none'}")
    print("  NOTE the anchor and weight axes collapse to one cell whenever the VWAP reading is")
    print("  `off`, so the EFFECTIVE cell count is lower than the nominal one; the marginal for")
    print("  those two axes is read over the VWAP-ON cells only, below.")

    print("\n" + "=" * 112)
    print("A3. THE MARGINAL AVERAGE PER AXIS -- annualised trade Sharpe / percent per trade")
    print("=" * 112)
    for a in AXES:
        sub = ok if a not in ("anchor", "weight") else ok[ok["vwap"] != "off"]
        g = sub.groupby(a).agg(sh=(SCORE, "mean"), per=("pct_research", "mean"),
                               pf=("pf_research", "mean"), n=("n_research", "mean"),
                               cells=(SCORE, "size")).sort_values("sh", ascending=False)
        print(f"  {a:7s} " + "   ".join(f"{k}: {v['sh']:+.2f}/{v['per']:+.4f}/PF{v['pf']:.2f}"
                                        for k, v in g.iterrows())[:190])

    print("\n  DOES THE V IN VWAP DO ANYTHING? -- the volume-weighted anchor against its")
    print("  unweighted twin, every other axis identical:")
    piv = ok[ok["vwap"] != "off"]
    key = [c for c in AXES if c != "weight"]
    a = piv[piv["weight"] == "vol"].set_index(key)[SCORE]
    b = piv[piv["weight"] == "flat"].set_index(key)[SCORE]
    j = pd.concat([a.rename("vol"), b.rename("flat")], axis=1).dropna()
    print(f"    {len(j):,} matched pairs   volume-weighted better in {100*(j['vol']>j['flat']).mean():.1f}%"
          f"   mean difference {(j['vol']-j['flat']).mean():+.4f} Sharpe")

    print("\n" + "=" * 112)
    print("A4. THE FINALISTS -- declared here, read once by run_v63b")
    print("=" * 112)
    fin = {}
    fin["F1 marginal consensus"] = {a: ok.groupby(a)[SCORE].mean().idxmax() for a in AXES}
    fin["F2 top research Sharpe"] = {a: ok.sort_values(SCORE, ascending=False).iloc[0][a]
                                     for a in AXES}
    fin["F3 top research total"] = {a: ok.sort_values("tot_research", ascending=False).iloc[0][a]
                                    for a in AXES}
    off = ok[ok["vwap"] == "off"]
    fin["F4 the same trigger with NO VWAP"] = {a: off.sort_values(SCORE, ascending=False).iloc[0][a]
                                               for a in AXES}
    rows = []
    for name, cell in fin.items():
        m = np.ones(len(ok), bool)
        for a, v in cell.items():
            m &= ok[a].to_numpy() == v
        s = ok[m]
        if not len(s):
            print(f"  {name}: NOT SCORABLE")
            continue
        r = s.iloc[0]
        rows.append(dict(name=name, **{a: r[a] for a in AXES}, n=int(r["n_research"]),
                         pct=float(r["pct_research"]), pf=float(r["pf_research"]),
                         sh=float(r["sh_research"]), tot=float(r["tot_research"])))
        print(f"  {name:34s} n {int(r['n_research']):5d}  {r['pct_research']:+.4f} %/trade  "
              f"total {r['tot_research']:+7.2f}%  PF {r['pf_research']:5.2f}  Sharpe "
              f"{r['sh_research']:+5.2f}")
        print("     " + ", ".join(f"{a}={cell[a]}" for a in AXES))
    pd.DataFrame(rows).to_csv("results/v63/finalists.csv", index=False)
    print(f"\n  MULTIPLICITY: four finalists from {len(ok):,} scorable cells on ONE market's")
    print("  research block. US30 and NQ have chosen nothing and are the test.")


if __name__ == "__main__":
    main()
