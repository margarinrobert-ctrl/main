"""P1 -- what PF 1.50 requires, what the best known 07:00-11:00 cell delivers, and the frontier."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scalp150 import pf150 as P  # noqa: E402
from breaker import bbcore as BB  # noqa: E402

pd.set_option("display.width", 210)
BAR = "=" * 104
WHY = {0: "stop", 1: "target", 2: "chan", 3: "cap"}


def hdr(t):
    print("\n" + BAR + "\n" + t + "\n" + BAR)


def main():
    f15 = P.bars(15)
    a15 = P.atr(f15)
    days = pd.Series(f15.index.normalize().unique()).sort_values().to_numpy()
    cut = pd.Timestamp(days[int(0.75 * len(days))])
    print(f"  NQ 15m {len(f15):,} bars  {f15.index[0]} -> {f15.index[-1]}   split {cut}")

    t = P.run(f15, a15)
    c_med = float(t.cost_frac.median())
    R = 2.3 / 3.19

    hdr("P1.1  THE ARITHMETIC -- the win rate PF 1.50 demands at this geometry")
    print(f"  stop 3.19 x ATR, target 2.3 x ATR  ->  reward:risk R = {R:.3f}")
    print(f"  measured cost as a fraction of risk, median: c = {c_med:.4f}\n")
    print(f"  {'target PF':<12}{'required win rate':>20}{'lift over driftless':>22}")
    base = P.req_win(1.0, R, c_med)
    for pp in (1.0, 1.1, 1.2, 1.3, 1.5, 2.0):
        w = P.req_win(pp, R, c_med)
        print(f"  {pp:<12.2f}{w:>20.4f}{w - base:>+22.4f}")
    print(f"\n  driftless break-even (PF 1.00 after cost): {base:.4f}")
    print(f"  ACTUAL win rate achieved by this cell:      {float((t.pct > 0).mean()):.4f}")
    print(f"  PF 1.50 therefore needs +{P.req_win(1.5, R, c_med) - float((t.pct>0).mean()):.4f} "
          f"of win rate over what the rule actually produces.")

    hdr("P1.2  THE BEST 07:00-11:00 CELL ON RECORD, RUN FRESH")
    print("  Geometry from STUDY_BAYESOPT_SCALP (3,600 Optuna trials, research block only).\n")
    print(f"  {'block':<10}{'n':>7}{'/yr':>7}{'win':>8}{'need1.5':>9}{'PF':>8}{'grossPF':>9}"
          f"{'%/trade':>10}{'total%':>10}{'maxDD%':>9}{'amb':>7}")
    yrs = (f15.index[-1] - f15.index[0]).days / 365.25
    for bl, sel in (("research", pd.DatetimeIndex(t.ts) < cut),
                    ("holdout", pd.DatetimeIndex(t.ts) >= cut),
                    ("FULL", t.ts == t.ts)):
        x = t[sel]
        yy = yrs * (0.75 if bl == "research" else 0.25 if bl == "holdout" else 1.0)
        eq = np.cumsum(x.pct.to_numpy())
        dd = float(np.max(np.maximum.accumulate(eq) - eq))
        print(f"  {bl:<10}{len(x):>7}{len(x)/yy:>7.0f}{float((x.pct>0).mean()):>8.4f}"
              f"{P.req_win(1.5, R, float(x.cost_frac.median())):>9.4f}{P.pf(x):>8.3f}"
              f"{P.pf(x,'gross_pct'):>9.3f}{x.pct.mean():>+10.5f}{eq[-1]:>+10.2f}"
              f"{dd:>9.2f}{x.amb.mean():>7.4f}")
    mix = t.why.map(WHY).value_counts(normalize=True)
    print(f"\n  exit mix: " + "  ".join(f"{k} {v:.3f}" for k, v in mix.items())
          + f"   median hold {(t.x_bar-t.e_bar).median()*15:.0f} min")

    hdr("P1.3  A RANDOM ENTRY IN THE SAME WINDOW, SAME GEOMETRY -- 50 seeds")
    o = f15["open"].to_numpy(); h = f15["high"].to_numpy()
    l = f15["low"].to_numpy(); c = f15["close"].to_numpy()
    mod = (f15.index.hour * 60 + f15.index.minute).to_numpy()
    elig = np.flatnonzero((mod >= P.WIN0) & (mod < P.WIN1) & (np.arange(len(c)) < len(c) - 20))
    for bl, lim in (("research", pd.DatetimeIndex(f15.index) < cut),
                    ("holdout", pd.DatetimeIndex(f15.index) >= cut)):
        real = t[pd.DatetimeIndex(t.ts) < cut] if bl == "research" else t[pd.DatetimeIndex(t.ts) >= cut]
        pool = elig[lim[elig]]
        obs = P.pf(real)
        got = []
        rng = np.random.default_rng(0)
        for sd in range(50):
            eb = np.sort(rng.choice(pool, size=min(len(real), len(pool)), replace=False))
            sides = rng.permutation(real.side.to_numpy())
            g, last = [], -1
            for k, b in enumerate(eb):
                if b <= last or b + 1 >= len(c):
                    continue
                s = sides[k % len(sides)]
                j = b + 1
                ent = o[j]
                aa = P.atr(f15)[b]
                stop = ent - s * 3.19 * aa
                tgt = ent + s * 2.3 * aa
                x, px = -1, 0.0
                for tt in range(j, min(j + 15, len(c) - 1)):
                    hs = (l[tt] <= stop) if s > 0 else (h[tt] >= stop)
                    ht = (h[tt] >= tgt) if s > 0 else (l[tt] <= tgt)
                    if hs:
                        x, px = tt, stop; break
                    if ht:
                        x, px = tt, tgt; break
                if x < 0:
                    x = min(j + 15, len(c) - 1); px = c[x]
                g.append(100.0 * (s * (px - ent) - P.RT_POINTS) / ent)
                last = x
            g = np.array(g)
            got.append(float(g[g > 0].sum() / max(-g[g < 0].sum(), 1e-12)))
        got = np.array(got)
        print(f"  {bl:<10} rule PF {obs:.3f}   control PF mean {got.mean():.3f} "
              f"sd {got.std(ddof=1):.3f}   p(ctl>=rule) {(got >= obs).mean():.3f}")

    hdr("P1.4  THE FRONTIER -- best PF at each minimum trade count, in this window")
    print("  Entry/exit channel, stop and target swept on the RESEARCH block; each winner then read")
    print("  on the holdout. This is the shape that answers 'can PF 1.50 hold', not any one cell.\n")
    rows = []
    for en in (5, 10, 20, 40, 80):
        for ex in (5, 10, 20, 40):
            for sl in (1.5, 2.5, 3.19, 5.0):
                for tp in (0.0, 1.5, 2.3, 4.0, 8.0):
                    tt = P.run(f15, a15, ent_n=en, ex_n=ex, sl=sl, tp=tp)
                    if len(tt) < 60:
                        continue
                    r = tt[pd.DatetimeIndex(tt.ts) < cut]
                    k = tt[pd.DatetimeIndex(tt.ts) >= cut]
                    if len(r) < 40 or len(k) < 15:
                        continue
                    rows.append(dict(en=en, ex=ex, sl=sl, tp=tp, nr=len(r), nk=len(k),
                                     pr=P.pf(r), pk=P.pf(k), per_yr=len(r) / (yrs * 0.75)))
    G = pd.DataFrame(rows)
    print(f"  cells scored {len(G)}   research-profitable {(G.pr>1).mean():.3f}   "
          f"corr(research PF, holdout PF) {G.pr.corr(G.pk):+.3f}\n")
    print(f"  {'min trades/yr':<15}{'best research PF':>18}{'that cell on holdout':>22}"
          f"{'trades/yr':>11}{'geometry':>26}")
    for mn in (25, 50, 100, 150, 200, 300):
        sub = G[G.per_yr >= mn]
        if not len(sub):
            continue
        b = sub.loc[sub.pr.idxmax()]
        print(f"  {mn:<15}{b.pr:>18.3f}{b.pk:>22.3f}{b.per_yr:>11.0f}"
              f"{f'{int(b.en)}/{int(b.ex)} sl{b.sl} tp{b.tp}':>26}")
    print(f"\n  cells reaching PF >= 1.50 on RESEARCH: {(G.pr>=1.5).sum()} of {len(G)}")
    print(f"  of those, still >= 1.50 on the HOLDOUT: {((G.pr>=1.5)&(G.pk>=1.5)).sum()}")
    print(f"  cells reaching PF >= 1.50 on BOTH with >= 100 trades/yr: "
          f"{((G.pr>=1.5)&(G.pk>=1.5)&(G.per_yr>=100)).sum()}")


if __name__ == "__main__":
    main()
