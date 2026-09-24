"""T4 -- ONE DECLARED 27-CELL GRID PER TIMEFRAME on the RESEARCH half, read by marginal average;
the marginal-consensus cell read ONCE on the second half; then the PF 1.5 table (step 6).

Axes, declared from T1-T3 (the gate is the only load-bearing component, and it is defined by two
clock quantities that a chart change silently rescales):
    EMA reach in minutes (fast/slow)   3.25/12   6.5/24 (the 30s chart's)   13/48 (the 1m chart's)
    fresh-cross reach in clock minutes  3.5 (= the Pine's 7 bars on 30s)   7 (configured)   14
    last new entry (NY minute)          590   600 (configured)   615
Everything else is the user's configuration with arm (c)'s range correction. Bars are
max(1, round(min/tf)) for the fast EMA and max(2, ...) for the slow one; the cross reach is
floor(min/tf) bars, so at 15m the whole cross axis is ONE cell and the EMA axis is two.
Identical trade sets are collapsed before counting cells, so E[max t | noise] is over the cells
that were actually different.
"""
from __future__ import annotations

import itertools
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tfx_core as X   # noqa: E402

pd.set_option("display.width", 230)
P0 = dict(X.TV)
EMA = ((3.25, 12.0), (6.5, 24.0), (13.0, 48.0))
XR = (3.5, 7.0, 14.0)
END = (590, 600, 615)

c30 = X.ctx(0.5)
alld, is_d, oos_d = X.split(c30, P0)
print(f"research = first {len(is_d)} tradeable sessions (to {X.DK.from_day(is_d.max()).date()}), "
      f"second read = last {len(oos_d)} (from {X.DK.from_day(oos_d.min()).date()})")


def cellP(tf, ema, xr, end):
    re_ = 545 if (tf < 1 or tf > 5) else int(round(540 + tf * np.floor(5 / tf)))
    fa = max(1, X.half_up(ema[0] / tf)); sl = max(2, X.half_up(ema[1] / tf))
    return (fa, sl), dict(P0, ma_mode="xmin", cross_min=xr, range_end=re_, end_m=end)


allg, cons, final = [], [], []
for tf in X.TFS:
    print("\n" + "=" * 104)
    rows, keys = [], {}
    for ema, xr, end in itertools.product(EMA, XR, END):
        (fa, sl), P = cellP(tf, ema, xr, end)
        c = X.ctx(tf, fa, sl)
        tr = c.trades(P)
        t_is = X.S.sub(tr, is_d) if tr is not None else None
        s = X.stats(t_is)
        key = tuple(t_is["eb"].to_numpy()) + tuple(np.round(t_is["pts"].to_numpy(), 6)) \
            if t_is is not None and len(t_is) else ()
        keys.setdefault(key, len(keys))
        rows.append(dict(tf=tf, ema=f"{ema[0]}/{ema[1]}", xr=xr, end=end, fast=fa, slow=sl,
                         uniq=keys[key], **{k: s[k] for k in ("n", "pct", "pf", "win", "mde", "ratio")},
                         t=s["pct"] / (s["sd"] / np.sqrt(s["n"])) if s["n"] > 1 and s["sd"] > 0 else np.nan))
    g = pd.DataFrame(rows)
    eff = g["uniq"].nunique()
    emax = X.N.e_max_normal(eff)
    print(f"{tf}m  27 nominal cells, {eff} EFFECTIVE (distinct research trade sets).  "
          f"E[max t | noise] = {emax:.3f} against the 2.802 detection needs -- printed BEFORE reading")
    print(f"  research: share profitable {np.mean(g['pct'] > 0):.3f}, best |t| {np.nanmax(np.abs(g['t'])):.2f}, "
          f"median n {g['n'].median():.0f}, mean %/tr {g['pct'].mean():+.4f}")
    pick = {}
    for ax in ("ema", "xr", "end"):
        m = g.groupby(ax).agg(pct=("pct", "mean"), share=("pct", lambda v: float((v > 0).mean())),
                              pf=("pf", "median"), n=("n", "mean"))
        print(f"  marginal {ax:4s}: " + "   ".join(f"{i}: {r.pct:+.4f} ({r.share:.2f} prof, PFmed {r.pf:.2f}, n {r.n:.0f})"
                                                  for i, r in m.iterrows()))
        pick[ax] = m["pct"].idxmax()
    allg.append(g)
    ema = tuple(float(v) for v in pick["ema"].split("/"))
    (fa, sl), P = cellP(tf, ema, float(pick["xr"]), int(pick["end"]))
    c = X.ctx(tf, fa, sl)
    cfg = f"EMA {pick['ema']}min ({fa}/{sl} bars), cross<={pick['xr']}min, end {pick['end']}"
    print(f"  CONSENSUS: {cfg}")
    for blk, dd in (("research", is_d), ("second", oos_d), ("all", alld)):
        row, tr = X.full_days(c, P, dd, 400, seed=int(tf * 1000) + len(blk))
        row.update(tf=tf, block=blk, cfg=cfg, emax=emax, eff_cells=eff,
                   be_driftless=X.driftless_be(P))
        if tr is not None and len(tr):
            aw = tr.loc[tr["pts"] > 0, "pts"].mean(); al = tr.loc[tr["pts"] <= 0, "pts"].mean()
            row["be_realised"] = 1 / (1 + aw / -al) if al < 0 else np.nan
        final.append(row)
        print(f"   {blk:8s} n {row['n']:3d} %/tr {row['pct']:+.4f} PF {row['pf']:.3f} win {row['win']:.3f} "
              f"(driftless BE {row['be_driftless']:.3f}, realised-payoff BE {row.get('be_realised', np.nan):.3f})  "
              f"MDE {row['mde']:.4f} ratio {row['ratio']:+.2f}  p_entry {row['p_entry']:.3f} "
              f"p_gate {row['p_gate']:.3f} P(mean<=0) {row['p_boot']:.3f}  need n {row['need']:.0f}", flush=True)

pd.concat(allg).to_csv(os.path.join(HERE, "t4_grid.csv"), index=False)
pd.DataFrame(final).to_csv(os.path.join(HERE, "t4_consensus.csv"), index=False)
print("\ndone.")
