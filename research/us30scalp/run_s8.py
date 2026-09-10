"""S8 -- the formal close: does ANY cell in the whole space reach the detection threshold, and
what is the noise floor of the search that would have to find it?

S7 produced the governing arithmetic. At this window's per-trade dispersion (157 pts) and trade
rate (272/yr), the minimum detectable effect at 80% power on the six-year research block is
**10.74 points a trade**, while a profit factor of 1.2 requires **+10.61** and 1.5 requires
**+23.62**. So the frontier inverts the usual complaint: anything worth trading here is easy to
detect and anything hard to detect is not worth trading. Six years is not a small sample for a
PF-1.5 rule -- it is a large one. It is only insufficient for edges too small to trade.

That reframes the search itself. A configuration must clear t = 2.802 to be detectable at all, and
a SEARCH over N configurations has its own noise floor: the largest t a null produces over N draws
grows like sqrt(2 ln N). If that floor exceeds the detection threshold, the search cannot
distinguish a real edge from its own best draw no matter what it finds. Both are computed here.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from scipy import stats as sps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s30core as S  # noqa: E402
from run_s7 import cell, PTS, TGT, HOLDS, Z80  # noqa: E402

pd.set_option("display.width", 250)
EULER = 0.5772156649


def e_max_normal(n):
    """E[max of n iid standard normals] -- Bailey/Lopez de Prado's expression."""
    if n < 2:
        return 0.0
    a = sps.norm.ppf(1 - 1.0 / n)
    b = sps.norm.ppf(1 - 1.0 / (n * np.e))
    return (1 - EULER) * a + EULER * b


def main():
    f = S.load("US30L")
    bl = S.blocks(f, "US30L")
    res, hol = bl["A_research"], bl["B_holdout"]
    win = S.window(f)
    nsess = f.index[res & win].normalize().nunique()

    # ---- 1. the whole space, every trigger ---------------------------------------------------
    print("=== 1. every declared trigger x the full 168-cell geometry space, research only ===")
    rows = []
    for nm, fn in S.TRIGGERS.items():
        s2, d2 = fn(f)
        keep = np.isin(s2, np.flatnonzero(res))
        sig, sd = s2[keep], d2[keep]
        for st in PTS:
            for tg in TGT:
                for hd in HOLDS:
                    r = cell(f, sig, sd, st, tg, hd, nsess)
                    if r is None:
                        continue
                    r["trigger"] = nm
                    rows.append(r)
    G = pd.DataFrame(rows)
    N = len(G)
    print(f"{N:,} scorable cells   profitable {100*(G.pts > 0).mean():.1f}%   "
          f"best t {G.t.max():.3f}   best Sharpe {G.sharpe.max():.3f}   best PF {G.pf.max():.3f}")

    print("\nbest cell per trigger, by t:")
    B = G.sort_values("t", ascending=False).groupby("trigger").head(1).sort_values(
        "t", ascending=False)
    print(B[["trigger", "stop", "target", "hold_h", "n", "pts", "sd", "t", "sharpe", "pf",
             "win", "med_min"]].round(3).to_string(index=False))

    # ---- 2. the detection threshold against the search's own noise floor ---------------------
    print("\n=== 2. detection threshold vs the noise floor of a search this size ===")
    print(f"  detectable at 80% power requires        t >= {Z80:.3f}")
    print(f"  best t achieved over {N:,} cells         t  = {G.t.max():.3f}")
    for n_tr in (168, N, 5000):
        print(f"  E[max t | pure noise] over {n_tr:>6,} trials = {e_max_normal(n_tr):.3f}"
              f"   (sqrt(2 ln N) = {np.sqrt(2*np.log(n_tr)):.3f})")
    print(f"\n  -> the search's own best-of-{N:,} noise draw is {e_max_normal(N):.3f} t, which "
          f"EXCEEDS\n     the {Z80:.3f} needed for detectability: over a space this size a "
          f"detectable edge and\n     the search's luckiest draw are the same number, so the "
          f"search cannot separate them.")
    print(f"  cells reaching t >= {Z80:.3f}: {int((G.t >= Z80).sum())} of {N:,}")
    print(f"  cells reaching t >= {e_max_normal(N):.3f} (the noise floor): "
          f"{int((G.t >= e_max_normal(N)).sum())} of {N:,}")

    # ---- 3. deflated Sharpe over the counted trial population --------------------------------
    print("\n=== 3. deflated Sharpe over the trial population actually run ===")
    sh_daily = G["sharpe"].to_numpy() / np.sqrt(252)          # per-observation
    v = np.nanvar(sh_daily, ddof=1)
    best = np.nanmax(sh_daily)
    emax = np.sqrt(v) * e_max_normal(N)
    print(f"  trial Sharpe sd (per session) {np.sqrt(v):.5f} over {N:,} cells")
    print(f"  E[max Sharpe | null]          {emax:.5f}")
    print(f"  best achieved                 {best:.5f}  "
          f"({'ABOVE' if best > emax else 'BELOW'} its own noise floor)")
    # add the earlier studies' looks to the count
    total_looks = N + 21 + 7 + 8 + 175 + 14
    print(f"  counted looks including S1-S7: {total_looks:,}   "
          f"E[max|null] at that count {np.sqrt(v)*e_max_normal(total_looks):.5f}")

    # ---- 4. the population shape, which decides how to read any top row ----------------------
    print("\n=== 4. how much of the space is positive, per trigger ===")
    P = G.groupby("trigger").agg(cells=("pts", "size"), pos=("pts", lambda x: float((x > 0).mean())),
                                 mean_t=("t", "mean"), best_t=("t", "max"),
                                 mean_pts=("pts", "mean")).round(4)
    print(P.sort_values("best_t", ascending=False).to_string())

    # ---- 5. research-to-holdout transfer across the whole space ------------------------------
    print("\n=== 5. does the research ranking transfer? (the diagnostic that needs no top row) ===")
    hs = []
    nsess_h = f.index[hol & win].normalize().nunique()
    for _, r in G.iterrows():
        s2, d2 = S.TRIGGERS[r.trigger](f)
        k = np.isin(s2, np.flatnonzero(hol))
        h = cell(f, s2[k], d2[k], r.stop, r.target, int(r.hold_h * 4), nsess_h)
        hs.append(h["pts"] if h else np.nan)
    G["hold_pts"] = hs
    ok = G.hold_pts.notna()
    print(f"  corr(research pts, holdout pts) over {int(ok.sum()):,} cells: "
          f"{np.corrcoef(G.pts[ok], G.hold_pts[ok])[0,1]:+.4f} Pearson / "
          f"{sps.spearmanr(G.pts[ok], G.hold_pts[ok]).statistic:+.4f} Spearman")
    q = G[ok].nlargest(max(1, int(0.01 * ok.sum())), "pts")
    print(f"  top 1% by research pts: research {q.pts.mean():+.3f} -> holdout "
          f"{q.hold_pts.mean():+.3f}   whole population holdout {G.hold_pts[ok].mean():+.3f}")
    print(f"  holdout-profitable share: whole population {100*(G.hold_pts[ok] > 0).mean():.1f}%, "
          f"research top 1% {100*(q.hold_pts > 0).mean():.1f}%")
    G.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "s8_grid.csv"), index=False)


if __name__ == "__main__":
    main()
