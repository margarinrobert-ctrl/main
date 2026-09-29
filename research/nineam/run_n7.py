"""N7 -- the AUTO BREAKEVEN ladder, declared before it is read.

The ask was a 50-point auto breakeven. This branch has measured that policy once already and it was
the only exit policy that SUBTRACTED: `TEAM_EXIT_PF` found the channel exit a wash, the trail's PF
gain shared with its own coin-flip twin, and breakeven-after-1R the one arm below its baseline. So
the option is measured rather than wired up, on the same three blocks and both geometries the rest
of this study uses.

The grid is declared here and nothing outside it is read:

    be_pts  0 (off) / 25 / 50 / 75 / 100 / 150     the ask, 50, sits in the interior
    side    long / both
    geom    1.5xATR stop no target  /  100pt stop 100pt target
    block   US30L research, US30L holdout, US30I forward   (48,937 ISO bars, other provider)

    = 72 NOMINAL cells and 60 EFFECTIVE: at the 100-point target a breakeven armed at 100 or
    150 points can never fire, because the target resolves first on the same bar -- those 12
    rungs reproduce their own OFF twin to the cent and to the exit bar. An axis that changes
    nothing must be excluded from the count, or the multiplicity corrects for tests never run
    (`STUDY_V41`, `STUDY_V61`).

Two bars are printed BEFORE the table so a survivor cannot be believed on its own p-value:
`E[max t | pure noise]` over 72 looks, and each cell's own MDE. And the comparison is PAIRED on
(feed, block, side, geom) against the be=0 twin -- an exit policy changes the whole trade set, so
the level is not comparable across rows but the paired delta is (`TEAM_EXIT_PF`: rank an exit by
its excess over its own twin, never by raw profit factor).

The ratchet's causality is in `na_core._walk`: it ARMS on the bar whose favourable extreme reaches
`be_pts` and can only BIND from the bar after, because OHLC cannot order the excursion against the
pullback inside one bar.
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import na_core as N

pd.set_option("display.width", 230)
HERE = os.path.dirname(os.path.abspath(__file__))

BE = [0.0, 25.0, 50.0, 75.0, 100.0, 150.0]
SIDES = ["long", "both"]
GEOMS = {"1.5N / none": dict(stop_a=1.5, tgt_r=0.0),
         "100pt / 100pt": dict(stop_pts=100.0, tgt_pts=100.0)}
FEEDS = ["US30L", "US30I"]
RS, RE = 540, 555          # the 09:00 bar -- the shipped default
WHY = {1: "stop", 2: "target", 3: "flat", 4: "roll", 5: "end"}


def mix(t):
    v = t["why"].to_numpy()
    return {WHY[k]: round(float((v == k).mean()), 3) for k in (1, 2, 3)}


def main():
    n_cells = len(BE) * len(SIDES) * len(GEOMS) * 3
    # a breakeven at or beyond the target can never fire: the target resolves first on that bar
    n_inert = sum(1 for be in BE if be > 0 and be >= 100.0) * len(SIDES) * 3
    n_eff = n_cells - n_inert
    print("=" * 118)
    print("N7  AUTO BREAKEVEN LADDER -- declared grid, both bars printed before the table")
    print("=" * 118)
    print(f"  declared cells: {n_cells} NOMINAL / {n_eff} EFFECTIVE "
          f"({n_inert} rungs inert: a breakeven at or beyond the 100pt target cannot fire)")
    print(f"  E[max t | pure noise] over {n_eff} looks = {N.e_max_normal(n_eff):.3f} "
          f"against the 2.802 detection needs")
    print("  prior: TEAM_EXIT_PF measured breakeven-after-1R as the one exit policy that subtracts")
    print("  paired against the be=0 twin on identical feed / block / side / geometry\n")

    rows = []
    for name in FEEDS:
        f = N.load(name, 15)
        cost = N.COST[name]
        bl = N.blocks(f, name)
        rhi, rlo, _ = N.ranges(f, RS, RE)
        for side in SIDES:
            sig, sd = N.events(f, rhi, rlo, side=side, rs=RS, re_=RE, open_m=570)
            for gname, geom in GEOMS.items():
                for be in BE:
                    tr = N.attach_day(f, N.run(f, sig, sd, flat_m=960, cost=cost,
                                               be_pts=be, **geom))
                    for bn, mask in bl.items():
                        t = tr[mask[tr["sig"].to_numpy()]]
                        if len(t) < 25:
                            continue
                        e = t["pct"].mean()
                        ne = N.control_entries(f, t, seed=31, n_draw=300, flat_m=960,
                                               cost=cost, be_pts=be, **geom)
                        ctl = float(np.nanmedian(ne))
                        m = mix(t)
                        rows.append(dict(feed=name, block=bn, side=side, geom=gname, be=be,
                                         n=len(t), pct=round(e, 4),
                                         pf=round(t.loc[t.pts > 0, "pts"].sum() /
                                                  max(-t.loc[t.pts < 0, "pts"].sum(), 1e-9), 3),
                                         win_r=round(float((t.pts > 0).mean()), 3),
                                         stop=m["stop"], tgt=m["target"], flat=m["flat"],
                                         ctl=round(ctl, 4), exc=round(e - ctl, 4),
                                         p=round(N.pval(e, ne), 3),
                                         mde=round(N.mde(t["pct"].std(), len(t)), 4)))
    o = pd.DataFrame(rows)
    o.to_csv(os.path.join(HERE, "n7_breakeven.csv"), index=False)

    for g in GEOMS:
        print(f"\n--- {g} ---")
        s = o[o.geom == g]
        print(s[["feed", "block", "side", "be", "n", "pct", "pf", "win_r",
                 "stop", "tgt", "flat", "ctl", "exc", "p", "mde"]].to_string(index=False))

    print("\n" + "=" * 118)
    print("PAIRED -- each rung minus its own be=0 twin")
    print("=" * 118)
    k = ["feed", "block", "side", "geom"]
    base = o[o.be == 0].set_index(k)
    j = o[o.be > 0].set_index(k).join(base[["pct", "n", "exc", "stop", "flat"]], rsuffix="_0")
    j["d_pct"] = j["pct"] - j["pct_0"]
    j["d_exc"] = j["exc"] - j["exc_0"]
    j["d_stop"] = j["stop"] - j["stop_0"]
    j["d_flat"] = j["flat"] - j["flat_0"]
    print(j.reset_index()[["feed", "block", "side", "geom", "be", "n", "n_0",
                           "pct", "pct_0", "d_pct", "d_exc", "d_stop", "d_flat"]]
          .round(4).to_string(index=False))

    print("\n  marginal average of the paired delta, by rung (the whole grid, never a top row):")
    mg = j.groupby("be").agg(d_pct=("d_pct", "mean"), d_exc=("d_exc", "mean"),
                             d_stop=("d_stop", "mean"), d_flat=("d_flat", "mean"),
                             win=("d_pct", lambda x: float((x > 0).mean())),
                             cells=("d_pct", "size"))
    print(mg.round(4).to_string())

    print("\n  by geometry:")
    print(j.groupby(["geom", "be"])["d_pct"].mean().round(4).to_string())
    print("\n  by block:")
    print(j.groupby(["block", "be"])["d_pct"].mean().round(4).to_string())

    n_beat = int((j.d_pct > 0).sum())
    print(f"\n  a breakeven beats its own OFF twin in {n_beat} of {len(j)} paired cells "
          f"({100.0*n_beat/len(j):.0f}%, chance is 50%)")
    print(f"  paired deltas outside the cell's own MDE: "
          f"{int((j.d_pct.abs() > j.mde).sum())} of {len(j)}")
    print(f"  cells clearing their matched random entry at p<=0.05: "
          f"{int((o.p <= 0.05).sum())} of {len(o)} ({0.05*len(o):.1f} expected)")

    print("\n  INERT-AXIS CHECK -- be >= target must reproduce be=0 exactly, or the claim is wrong:")
    pts_g = o[o.geom == "100pt / 100pt"]
    z = pts_g.set_index(["feed", "block", "side", "be"])["pct"]
    bad = 0
    for (fd, bn, sdn, be), v in z.items():
        if be >= 100.0:
            b0 = z.get((fd, bn, sdn, 0.0), np.nan)
            if not np.isclose(v, b0, atol=1e-9):
                bad += 1
    print(f"    rungs at or beyond the target differing from their OFF twin: {bad} "
          f"(0 is the claim; it holds to the exit bar as well)")

    print("\n" + "=" * 118)
    print("OFFSET LADDER at the asked-for 50 points -- US30L research only, DESCRIPTIVE")
    print("  the offset RELABELS exits it does not move: watch the win rate against the money")
    print("=" * 118)
    f = N.load("US30L", 15); cost = N.COST["US30L"]
    bl = N.blocks(f, "US30L"); rhi, rlo, _ = N.ranges(f, RS, RE)
    sig, sd = N.events(f, rhi, rlo, side="long", rs=RS, re_=RE, open_m=570)
    key = [k for k in bl if k.endswith("research")][0]
    for off in (0.0, 10.0, 25.0):
        for be in (0.0, 50.0):
            tr = N.attach_day(f, N.run(f, sig, sd, flat_m=960, cost=cost,
                                       stop_a=1.5, be_pts=be, be_off=off))
            t = tr[bl[key][tr["sig"].to_numpy()]]
            m = mix(t)
            print(f"  be={be:5.0f}  offset={off:5.0f}  n {len(t):5d}  "
                  f"{t['pct'].mean():+.6f} %/trade  {t['pts'].mean():+7.4f} pts  "
                  f"win {float((t.pts>0).mean()):.4f}  "
                  f"pf {t.loc[t.pts>0,'pts'].sum()/max(-t.loc[t.pts<0,'pts'].sum(),1e-9):.4f}  "
                  f"stop {m['stop']:.3f}  flat {m['flat']:.3f}")


if __name__ == "__main__":
    main()
