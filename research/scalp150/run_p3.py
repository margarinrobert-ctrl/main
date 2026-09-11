"""P3 -- the same 972-cell declared grid, with a HARD FLATTEN at 11:00 instead of a 4-hour cap.

Same grid, same split, same costs. Only the exit rule changes, so the difference between this and
run_p2 is the price of the flatten and nothing else.
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
SCR = "/tmp/claude-0/-home-user-main/e473d7de-e277-515e-b24b-75724aaa9da5/scratchpad"


def hdr(t):
    print("\n" + BAR + "\n" + t + "\n" + BAR)


def main():
    frames = {tf: (lambda g: (g, P.atr(g)))(P.bars(tf)) for tf in P.GRID["tf"]}
    f15 = frames[15][0]
    days = pd.Series(f15.index.normalize().unique()).sort_values().to_numpy()
    cut = pd.Timestamp(days[int(0.75 * len(days))])
    yrs = (f15.index[-1] - f15.index[0]).days / 365.25
    print(f"  07:00-11:00 New York, HARD FLATTEN at 11:00 (fill at the 11:00 bar's open)")
    print(f"  split {cut}   research {0.75*yrs:.2f} yr / holdout {0.25*yrs:.2f} yr")

    rows = []
    for tf in P.GRID["tf"]:
        f, a = frames[tf]
        sigs = {("DON", en, ex): (P.sig_donchian(f, en, ex), ex) for en, ex in P.GRID["don"]}
        sigs.update({("CMMA", n, z): (P.sig_cmma(f, a, n, z), 0) for n, z in P.GRID["cmma"]})
        for key, (sg, ex_n) in sigs.items():
            for side, sl, tp in itertools.product(P.GRID["side"], P.GRID["stop"], P.GRID["tgt"]):
                t = P.run_flat(f, a, sg, ex_n, sl, tp, side=side)
                if len(t) < 60:
                    continue
                r = t[pd.DatetimeIndex(t.ts) < cut]
                k = t[pd.DatetimeIndex(t.ts) >= cut]
                if len(r) < 40 or len(k) < 15:
                    continue
                x = r.pct.to_numpy()
                rows.append(dict(tf=tf, fam=key[0], p1=key[1], p2=key[2], side=side, sl=sl, tp=tp,
                                 nr=len(r), nk=len(k), per_yr=len(r) / (0.75 * yrs),
                                 pr=P.pf(r), pk=P.pf(k), gr=P.pf(r, "gross_pct"),
                                 sr=float(x.mean() / x.std(ddof=1)),
                                 winr=float((x > 0).mean()),
                                 flat=float((r.why == 4).mean())))
        print(f"  tf {tf:>3}m done   cells {len(rows)}")
    G = pd.DataFrame(rows)

    hdr("P3.1  POPULATION under the hard flatten")
    print(f"  scorable cells                          {len(G)}")
    print(f"  research-profitable (PF > 1.00)         {(G.pr>1).mean():.3f}")
    print(f"  research PF >= 1.50                     {(G.pr>=1.5).sum()}")
    print(f"  research PF >= 1.50 AND holdout >= 1.50 {((G.pr>=1.5)&(G.pk>=1.5)).sum()}")
    print(f"  PF > 1.00 on BOTH blocks                {((G.pr>1)&(G.pk>1)).sum()}  "
          f"({((G.pr>1)&(G.pk>1)).mean():.3f})   chance {(G.pr>1).mean()*(G.pk>1).mean():.3f}")
    print(f"  corr(research PF, holdout PF)           {G.pr.corr(G.pk):+.3f}")
    print(f"  GROSS research-profitable               {(G.gr>1).mean():.3f}")
    print(f"  median share of trades exiting on the flatten  {G.flat.median():.3f}")

    hdr("P3.2  WHAT THE FLATTEN COSTS -- same grid, cap-240 vs flatten-11:00")
    old = pd.read_csv(f"{SCR}/p2grid.csv")
    m = old.merge(G, on=["tf", "fam", "p1", "p2", "side", "sl", "tp"], suffixes=("_cap", "_flat"))
    print(f"  matched cells {len(m)}")
    print(f"  mean research PF   cap {m.pr_cap.mean():.3f}  ->  flatten {m.pr_flat.mean():.3f}   "
          f"({m.pr_flat.mean()-m.pr_cap.mean():+.3f})")
    print(f"  mean holdout  PF   cap {m.pk_cap.mean():.3f}  ->  flatten {m.pk_flat.mean():.3f}   "
          f"({m.pk_flat.mean()-m.pk_cap.mean():+.3f})")
    print(f"  cells where the flatten HELPS research PF: {(m.pr_flat>m.pr_cap).mean():.3f}")
    print(f"  cells where the flatten HELPS holdout  PF: {(m.pk_flat>m.pk_cap).mean():.3f}")
    print(f"  mean trade count   cap {m.nr_cap.mean():.0f}  ->  flatten {m.nr_flat.mean():.0f}")

    hdr("P3.3  MARGINAL AVERAGE PER AXIS (research PF / holdout PF)")
    for ax in ("tf", "fam", "side", "sl", "tp"):
        mm = G.groupby(ax)[["pr", "pk"]].mean()
        print(f"  {ax:<6} " + "   ".join(f"{i}: {r.pr:.3f}/{r.pk:.3f}" for i, r in mm.iterrows()))

    hdr("P3.4  RESEARCH TOP TEN and the holdout")
    top = G.sort_values("pr", ascending=False).head(10)
    print(f"  {'tf':>4}{'fam':>6}{'p1':>6}{'p2':>6}{'side':>6}{'sl':>6}{'tp':>6}"
          f"{'n res':>7}{'/yr':>6}{'res PF':>8}{'hold PF':>9}{'win':>8}{'flat%':>7}")
    for _, r in top.iterrows():
        print(f"  {int(r.tf):>4}{r.fam:>6}{r.p1:>6}{r.p2:>6}{int(r.side):>6}{r.sl:>6}{r.tp:>6}"
              f"{int(r.nr):>7}{r.per_yr:>6.0f}{r.pr:>8.3f}{r.pk:>9.3f}{r.winr:>8.4f}{r.flat:>7.3f}")
    print(f"\n  top-10 mean: research {top.pr.mean():.3f} -> holdout {top.pk.mean():.3f}   "
          f"population holdout mean {G.pk.mean():.3f}")

    hdr("P3.5  ONE HOLDOUT READ of the research-best cell, deflated over 1,944 cumulative trials")
    b = G.loc[G.pr.idxmax()]
    print(f"  {int(b.tf)}m  {b.fam} {b.p1}/{b.p2}  side {int(b.side)}  stop {b.sl}  target {b.tp}")
    f, a = frames[int(b.tf)]
    sg = (P.sig_donchian(f, int(b.p1), int(b.p2)) if b.fam == "DON"
          else P.sig_cmma(f, a, int(b.p1), b.p2))
    t = P.run_flat(f, a, sg, int(b.p2) if b.fam == "DON" else 0, b.sl, b.tp, side=int(b.side))
    for bl, sel in (("research", pd.DatetimeIndex(t.ts) < cut),
                    ("HOLDOUT", pd.DatetimeIndex(t.ts) >= cut)):
        x = t[sel]
        eq = np.cumsum(x.pct.to_numpy())
        dd = float(np.max(np.maximum.accumulate(eq) - eq))
        print(f"    {bl:<10} n {len(x):>5}  win {float((x.pct>0).mean()):.4f}  PF {P.pf(x):.3f}  "
              f"gross {P.pf(x,'gross_pct'):.3f}  {x.pct.mean():+.5f} %/tr  total {eq[-1]:+.2f}%  "
              f"maxDD {dd:.2f}%")
    sr = G.sr.to_numpy()
    xr = t[pd.DatetimeIndex(t.ts) < cut].pct.to_numpy()
    d = gates.deflated_sharpe(sr_hat=float(xr.mean() / xr.std(ddof=1)), T=len(xr),
                              n_trials=1944, var_trials=float(np.var(sr, ddof=1)),
                              skew=float(pd.Series(xr).skew()),
                              kurtosis=float(pd.Series(xr).kurt() + 3.0))
    print(f"\n    SR/trade {d['sr_hat']:+.5f}   E[max SR | noise] "
          f"{d['expected_max_sr_under_null']:+.5f}   DSR {d['dsr']:.4f}   {d['verdict']}")
    G.to_csv(f"{SCR}/p3grid.csv", index=False)


if __name__ == "__main__":
    main()
