"""x_run1 -- transcription first, then the 80 DECLARED cells read by MARGINAL AVERAGE.

Nothing here is chosen. The grid is fixed in `x_lib`'s docstring and the ranking is read only
after the marginals, because `STUDY_US30_SCALP_0711` section 10 established that over a space this
size the search's own best-of-noise (t = 3.301) exceeds what detectability requires (2.802).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import x_lib as X  # noqa: E402
import s30core as S  # noqa: E402

pd.set_option("display.width", 260)
pd.set_option("display.max_rows", 200)

STOPS = [30, 50, 75, 100, 150]
TGTS = [100, 150, 200, None]
POLS = X.POLICIES
ARM = "+adx<=20"


def tname(tg):
    return "none" if tg is None else str(tg)


def main():
    f = S.load("US30L")
    bl = S.blocks(f, "US30L")
    res = bl["A_research"]
    nsess = f.index[res & S.window(f)].normalize().nunique()
    print(f"US30_LONG_15m  {len(f):,} bars  {f.index[0].date()} .. {f.index[-1].date()}")
    print(f"research block: {int(res.sum()):,} bars, {nsess} in-window sessions\n")

    print("=== 0. TRANSCRIPTION: the flatten-only policy against s30core.walk ===")
    X.parity_check(f, res)
    print("  -> the extended walker is the same engine with extra exit paths bolted on\n")

    M = X.L.build_masks(f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy())
    sig, sd = X.signals(f, ARM, res, M)
    print(f"=== arm {ARM}: {len(sig)} signal bars in the research block ===\n")
    chlo = X.chan_low(f, 10, 1)

    rows = []
    for st in STOPS:
        for tg in TGTS:
            for pol in POLS:
                for tie in (0, 1):
                    t = X.xwalk(f, sig, sd, stop=st, tgt=tg, policy=pol, tie=tie, chlo=chlo)
                    r = X.stats(t, nsess, stop=st, tgt=tg)
                    r.update(stop=st, tgt=tname(tg), policy=pol, tie=tie)
                    rows.append(r)
    G = pd.DataFrame(rows)
    G.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "x_grid.csv"), index=False)
    g0 = G[G.tie == 0].copy()

    print("=== 1. POPULATION SHAPE, before any ranking (stop-first convention, 80 cells) ===")
    print(f"  cells scorable                 {len(g0)}")
    print(f"  share with PF > 1              {float((g0.pf > 1).mean()):.1%}")
    print(f"  share with total points > 0    {float((g0.total > 0).mean()):.1%}")
    print(f"  share OUTSIDE its own MDE      {float(g0.outside_mde.mean()):.1%}")
    print(f"  median PF                      {g0.pf.median():.3f}")
    print(f"  median pts/trade               {g0.pts.median():+.3f}")
    print(f"  median total points            {g0.total.median():+.1f}")
    print(f"  trade count range              {int(g0.n.min())} .. {int(g0.n.max())}")
    print(f"  best PF anywhere               {g0.pf.max():.3f}")
    print(f"  best t anywhere                {g0.t.max():.3f}   (detectability needs 2.802)\n")

    print("=== 2. MARGINAL AVERAGE PER AXIS -- in FOUR units, never the top row ===")
    for ax, lab in (("stop", "STOP (points)"), ("tgt", "TARGET (points)"),
                    ("policy", "EXIT POLICY")):
        print(f"\n  --- {lab} ---")
        mm = g0.groupby(ax).agg(pf=("pf", "mean"), pts=("pts", "mean"), total=("total", "mean"),
                                n=("n", "mean"), dd=("dd", "mean"), ret_dd=("ret_dd", "mean"),
                                win=("win", "mean"), mde=("mde", "mean"),
                                med_min=("med_min", "mean"), sharpe=("sharpe", "mean"))
        if ax == "stop":
            mm = mm.reindex(STOPS)
        elif ax == "tgt":
            mm = mm.reindex([tname(x) for x in TGTS])
        else:
            mm = mm.reindex(POLS)
        print(mm.round(3).to_string())

    print("\n=== 3. THE ARTIFACT-1 CHECK: does anything win on PF only by trading less? ===")
    print("  correlation across the 80 cells:")
    print(f"    corr(PF, trade count)     {g0.pf.corr(g0.n):+.4f}")
    print(f"    corr(PF, total points)    {g0.pf.corr(g0.total):+.4f}")
    print(f"    corr(PF, ret/DD)          {g0.pf.corr(g0.ret_dd):+.4f}")
    print(f"    corr(pts/trade, total)    {g0.pts.corr(g0.total):+.4f}")
    print("\n  top 5 by PF, with what they cost in count and total:")
    print(g0.nlargest(5, "pf")[["stop", "tgt", "policy", "n", "pf", "pts", "total", "dd",
                                "ret_dd", "mde", "outside_mde"]].round(3).to_string(index=False))
    print("\n  top 5 by TOTAL POINTS:")
    print(g0.nlargest(5, "total")[["stop", "tgt", "policy", "n", "pf", "pts", "total", "dd",
                                   "ret_dd", "mde", "outside_mde"]].round(3).to_string(index=False))
    print("\n  top 5 by RETURN / DRAWDOWN:")
    print(g0.nlargest(5, "ret_dd")[["stop", "tgt", "policy", "n", "pf", "pts", "total", "dd",
                                    "ret_dd", "mde", "outside_mde"]].round(3).to_string(index=False))

    print("\n=== 4. THE INTRABAR TIE-BREAK: stop-first vs target-first on every cell ===")
    k = ["stop", "tgt", "policy"]
    a = g0.set_index(k)
    b = G[G.tie == 1].set_index(k)
    cmp = pd.DataFrame(dict(amb=a.amb, pts0=a.pts, pts1=b.pts, pf0=a.pf, pf1=b.pf))
    cmp["d_pts"] = cmp.pts1 - cmp.pts0
    cmp["d_pf"] = cmp.pf1 - cmp.pf0
    cmp["sign_flip"] = (np.sign(cmp.pts0) != np.sign(cmp.pts1))
    print(f"  ambiguous share, mean over cells   {cmp.amb.mean():.4%}   max {cmp.amb.max():.4%}")
    print(f"  mean |convention spread|, points   {cmp.d_pts.abs().mean():.3f}")
    print(f"  max  |convention spread|, points   {cmp.d_pts.abs().max():.3f}")
    print(f"  cells whose SIGN flips             {int(cmp.sign_flip.sum())} of {len(cmp)}")
    print("\n  the five cells the convention moves most:")
    print(cmp.reindex(cmp.d_pts.abs().sort_values(ascending=False).index)
          .head(5).round(4).to_string())

    print("\n=== 5. per-policy marginal split by whether a target is on at all ===")
    sp = g0.assign(has_tgt=g0.tgt != "none").groupby(["policy", "has_tgt"]).agg(
        pf=("pf", "mean"), pts=("pts", "mean"), total=("total", "mean"), n=("n", "mean"),
        ret_dd=("ret_dd", "mean"))
    print(sp.round(3).to_string())


if __name__ == "__main__":
    main()
