"""P2 -- the wide pre-declared search. 972 cells, both trigger families, 3 timeframes, 3 sides.

Selection on the RESEARCH block only. The holdout is read ONCE at the end, for whatever the
research block declares best, and the reading is deflated for the whole 972-cell search.
"""
from __future__ import annotations

import itertools
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scalp150 import pf150 as P  # noqa: E402
sys.path.append("/root/.claude/skills/synced/"
                "a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/"
                "mechanism-first-alpha/scripts")
import gates  # noqa: E402

pd.set_option("display.width", 220)
BAR = "=" * 104
CAP_MIN = 240          # entries 07:00-11:00, nothing held past 4 hours -- the scalp constraint


def hdr(t):
    print("\n" + BAR + "\n" + t + "\n" + BAR)


def main():
    frames = {}
    for tf in P.GRID["tf"]:
        f = P.bars(tf)
        frames[tf] = (f, P.atr(f))
    f15 = frames[15][0]
    days = pd.Series(f15.index.normalize().unique()).sort_values().to_numpy()
    cut = pd.Timestamp(days[int(0.75 * len(days))])
    yrs = (f15.index[-1] - f15.index[0]).days / 365.25
    print(f"  split {cut}   research {0.75*yrs:.2f} yr / holdout {0.25*yrs:.2f} yr")
    print(f"  declared grid: 972 cells  (3 tf x 3 side x 3 stop x 4 target x 9 triggers)")

    rows = []
    for tf in P.GRID["tf"]:
        f, a = frames[tf]
        sigs = {}
        for en, ex in P.GRID["don"]:
            sigs[("DON", en, ex)] = (P.sig_donchian(f, en, ex), ex)
        for n, z in P.GRID["cmma"]:
            sigs[("CMMA", n, z)] = (P.sig_cmma(f, a, n, z), 0)
        for key, (sg, ex_n) in sigs.items():
            for side, sl, tp in itertools.product(P.GRID["side"], P.GRID["stop"], P.GRID["tgt"]):
                t = P.run_sig(f, a, sg, ex_n, sl, tp, CAP_MIN, side=side, tf=tf)
                if len(t) < 60:
                    continue
                r = t[pd.DatetimeIndex(t.ts) < cut]
                k = t[pd.DatetimeIndex(t.ts) >= cut]
                if len(r) < 40 or len(k) < 15:
                    continue
                x = r.pct.to_numpy()
                rows.append(dict(tf=tf, fam=key[0], p1=key[1], p2=key[2], side=side, sl=sl, tp=tp,
                                 nr=len(r), nk=len(k), per_yr=len(r) / (0.75 * yrs),
                                 pr=P.pf(r), pk=P.pf(k),
                                 gr=P.pf(r, "gross_pct"), gk=P.pf(k, "gross_pct"),
                                 mr=float(x.mean()), sr=float(x.mean() / x.std(ddof=1)),
                                 winr=float((x > 0).mean())))
        print(f"  tf {tf:>3}m done   cells so far {len(rows)}")
    G = pd.DataFrame(rows)

    hdr("P2.1  THE POPULATION -- read this before any top row")
    print(f"  scorable cells                          {len(G)}")
    print(f"  research-profitable (PF > 1.00)         {(G.pr>1).mean():.3f}")
    print(f"  research PF >= 1.50                     {(G.pr>=1.5).sum()}  "
          f"({(G.pr>=1.5).mean():.4f})")
    print(f"  research PF >= 1.50 AND holdout >= 1.50 {((G.pr>=1.5)&(G.pk>=1.5)).sum()}")
    print(f"  PF > 1.00 on BOTH blocks                {((G.pr>1)&(G.pk>1)).sum()}  "
          f"({((G.pr>1)&(G.pk>1)).mean():.3f})   chance if independent "
          f"{(G.pr>1).mean()*(G.pk>1).mean():.3f}")
    print(f"  corr(research PF, holdout PF)           {G.pr.corr(G.pk):+.3f} Pearson / "
          f"{G.pr.corr(G.pk, method='spearman'):+.3f} Spearman")
    print(f"  GROSS research-profitable               {(G.gr>1).mean():.3f}   "
          f"(cost is {'not ' if (G.gr>1).mean()<0.55 else ''}the binding constraint)")

    hdr("P2.2  MARGINAL AVERAGE PER AXIS -- never the top cell")
    for ax in ("tf", "fam", "side", "sl", "tp"):
        m = G.groupby(ax)[["pr", "pk"]].mean()
        print(f"  {ax:<6} " + "   ".join(f"{i}: {r.pr:.3f}/{r.pk:.3f}" for i, r in m.iterrows()))
    print("\n  (research PF / holdout PF)")

    hdr("P2.3  THE RESEARCH TOP TEN, AND WHAT THEY DO ON THE HOLDOUT")
    top = G.sort_values("pr", ascending=False).head(10)
    print(f"  {'tf':>4}{'fam':>6}{'p1':>6}{'p2':>6}{'side':>6}{'sl':>6}{'tp':>6}"
          f"{'n res':>7}{'/yr':>6}{'res PF':>8}{'hold PF':>9}{'res win':>9}")
    for _, r in top.iterrows():
        print(f"  {int(r.tf):>4}{r.fam:>6}{r.p1:>6}{r.p2:>6}{int(r.side):>6}{r.sl:>6}{r.tp:>6}"
              f"{int(r.nr):>7}{r.per_yr:>6.0f}{r.pr:>8.3f}{r.pk:>9.3f}{r.winr:>9.4f}")
    print(f"\n  top-10 mean: research {top.pr.mean():.3f} -> holdout {top.pk.mean():.3f}   "
          f"whole population holdout mean {G.pk.mean():.3f}")

    hdr("P2.4  ONE HOLDOUT READ of the research-best cell, deflated for all 972 trials")
    b = G.loc[G.pr.idxmax()]
    print(f"  declared best on research: tf {int(b.tf)}m  {b.fam} {b.p1}/{b.p2}  side {int(b.side)}"
          f"  stop {b.sl}  target {b.tp}")
    f, a = frames[int(b.tf)]
    sg = (P.sig_donchian(f, int(b.p1), int(b.p2)) if b.fam == "DON"
          else P.sig_cmma(f, a, int(b.p1), b.p2))
    ex = int(b.p2) if b.fam == "DON" else 0
    t = P.run_sig(f, a, sg, ex, b.sl, b.tp, CAP_MIN, side=int(b.side), tf=int(b.tf))
    for bl, sel in (("research", pd.DatetimeIndex(t.ts) < cut),
                    ("HOLDOUT", pd.DatetimeIndex(t.ts) >= cut)):
        x = t[sel]
        eq = np.cumsum(x.pct.to_numpy())
        dd = float(np.max(np.maximum.accumulate(eq) - eq))
        print(f"    {bl:<10} n {len(x):>5}  win {float((x.pct>0).mean()):.4f}  PF {P.pf(x):.3f}  "
              f"gross PF {P.pf(x,'gross_pct'):.3f}  {x.pct.mean():+.5f} %/trade  "
              f"total {eq[-1]:+.2f}%  maxDD {dd:.2f}%")
    sr = G.sr.to_numpy()
    xr = t[pd.DatetimeIndex(t.ts) < cut].pct.to_numpy()
    d = gates.deflated_sharpe(sr_hat=float(xr.mean() / xr.std(ddof=1)), T=len(xr),
                              n_trials=len(G), var_trials=float(np.var(sr, ddof=1)),
                              skew=float(pd.Series(xr).skew()),
                              kurtosis=float(pd.Series(xr).kurt() + 3.0))
    print(f"\n    trials {len(G)}   var over trial Sharpes {np.var(sr, ddof=1):.3e}")
    print(f"    SR/trade {d['sr_hat']:+.5f}   E[max SR | noise] {d['expected_max_sr_under_null']:+.5f}"
          f"   DSR {d['dsr']:.4f}")
    print(f"    {d['verdict']}")
    G.to_csv("/tmp/claude-0/-home-user-main/e473d7de-e277-515e-b24b-75724aaa9da5/scratchpad/p2grid.csv",
             index=False)


if __name__ == "__main__":
    main()
