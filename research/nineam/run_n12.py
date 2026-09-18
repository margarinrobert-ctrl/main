"""N12 -- CLOSE THE POSITION ON AN OPPOSITE EMA CROSS, declared before it is read.

The ask was an exit rule: when the EMA pair flips against the open position, close it. That is an
EXIT POLICY, and this branch has measured three of them already, all on the same base:

    TEAM_EXIT_PF   the 1.0 ATR trail raises profit factor and raises its own COIN FLIP's profit
                   factor by as much; the channel exit is a wash; breakeven-after-1R subtracts.
                   Ranked by excess over its own twin, DOING NOTHING beat the trail in 5 of 6
                   arm x unit cells.
    run_n7         the auto breakeven beats its own OFF twin in 19 of 60 scorable cells -- 32%,
                   where chance is 50% -- and the paired delta falls monotonically with the
                   arming distance.
    STUDY_V63      removing a chandelier trail was worth 3.6x the per-trade result, because a
                   trail is a take profit wearing a stop's name.

So the prior on any rule that closes a position EARLY is poor, and the correct null is not zero.

THE DECLARED GRID, and nothing outside it is read:

    reading  off / cross / state
             "cross" fires only on the bar the pair actually FLIPS against the position.
             "state" fires on the first bar the state is against it, which for an entry taken
             while the state was already opposed is the bar right after the fill.
    pair     13/48 (the shipped reading) and 21/55 (one neighbour, so a result cannot be a spike)
    side     long / both
    geom     1.5xATR stop no target  /  100pt stop 100pt target
    block    US30L research, US30L holdout, US30I forward (a different provider, 48,937 bars)

    = 72 NOMINAL cells and 48 EFFECTIVE. The OFF arm does not read the pair at all, so "off with
    13/48" and "off with 21/55" are one cell and not two; counting them twice would correct the
    multiplicity for 24 tests that were never run (`STUDY_V41`, `STUDY_V61`, run_n7).

THREE THINGS ARE PRINTED BEFORE ANY VERDICT.

  1. E[max t | pure noise] over 48 looks, against the 2.802 detection needs. If the luckiest draw
     of a null search this wide would look like the winner, no winner can be believed.
  2. THE BINDING RATE. An exit that almost never fires is an inert axis wearing a switch, and the
     honest thing is to say so rather than to report its p-value.
  3. THE TRADE COUNT IN BOTH ARMS. This rule takes the first break per side per session, so
     closing a long early can admit a SHORT later the same day that the OFF arm never saw. An exit
     policy that changes the trade count is not a filter on the same trades, and a comparison that
     ignores that is measuring two different strategies (`STUDY_V56`, run_n7).

AND THE PLACEBO IS THE HEADLINE TEST, run separately in `run_n13.py`. A before/after cannot separate "closing at the cross helps"
from "closing early at that RATE helps" -- the second needs no forecasting at all. So every cell is
also run against an exit array carrying the SAME number of exit bars with the SAME signed mix,
placed at random bars, over 200 seeds. If the real delta sits inside that distribution, the EMA is
not doing the work. This is the random-delay placebo of the execution-overlay literature applied to
an exit instead of an entry.

CAUSALITY. The cross is read at a bar's CLOSE and the exit FILLS AT THE NEXT BAR'S OPEN, because
`strategy.close()` cannot sell the close of the bar that triggers it (`STUDY_V16`'s flat_open
lesson, where the engine was changed to match the script rather than the other way round). The stop
and the target are intrabar and therefore resolve first within the same bar.
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import na_core as N

pd.set_option("display.width", 250)
HERE = os.path.dirname(os.path.abspath(__file__))

READINGS = ["off", "cross", "state"]
PAIRS = [(13, 48), (21, 55)]
SIDES = ["long", "both"]
GEOMS = {"1.5N / none": dict(stop_a=1.5, tgt_r=0.0),
         "100pt / 100pt": dict(stop_pts=100.0, tgt_pts=100.0)}
FEEDS = ["US30L", "US30I"]
RS, RE = 540, 555          # the 09:00 bar -- the shipped default
WHY = {1: "stop", 2: "target", 3: "flat", 4: "roll", 5: "end", 6: "cross"}
NSEED = 200


def mix(t):
    v = t["why"].to_numpy()
    return {WHY[k]: round(float((v == k).mean()), 3) for k in (1, 2, 3, 6)}


def stats(t):
    e = float(t["pct"].mean())
    w = t.loc[t.pts > 0, "pts"].sum()
    lo = -t.loc[t.pts < 0, "pts"].sum()
    return e, float(w / max(lo, 1e-9))


def main():
    n_nom = len(READINGS) * len(PAIRS) * len(SIDES) * len(GEOMS) * 3
    n_off = 1 * len(PAIRS) * len(SIDES) * len(GEOMS) * 3      # off counted once per pair
    n_eff = n_nom - n_off // 2                                 # half the off rows are duplicates
    n_score = (len(READINGS) - 1) * len(PAIRS) * len(SIDES) * len(GEOMS) * 3
    print("=" * 126)
    print("N12  OPPOSITE-EMA-CROSS EXIT -- declared grid, the bars printed before the table")
    print("=" * 126)
    print(f"  declared cells: {n_nom} NOMINAL / {n_eff} EFFECTIVE, of which {n_score} are scorable")
    print("    (the OFF arm never reads the pair, so its two pair rows are ONE cell, not two)")
    print(f"  E[max t | pure noise] over {n_score} looks = {N.e_max_normal(n_score):.3f} "
          f"against the 2.802 detection needs")
    print("  prior: three exit policies measured on this base, all of them wash or worse")
    print(f"  placebo: {NSEED} seeds a cell, same number of exit bars at RANDOM bars\n")

    rows = []
    for name in FEEDS:
        f = N.load(name, 15)
        cost = N.COST[name]
        bl = N.blocks(f, name)
        rhi, rlo, _ = N.ranges(f, RS, RE)
        cxs = {}
        for (fa, sl) in PAIRS:
            for rd in ("cross", "state"):
                cxs[(fa, sl, rd)] = N.cross_exit(f, fa, sl, "ema", rd)
        for side in SIDES:
            sig, sd = N.events(f, rhi, rlo, side=side, rs=RS, re_=RE, open_m=570)
            for gname, geom in GEOMS.items():
                for rd in READINGS:
                    for (fa, sl) in PAIRS:
                        if rd == "off" and (fa, sl) != PAIRS[0]:
                            continue                      # one cell, not two
                        cx = None if rd == "off" else cxs[(fa, sl, rd)]
                        tr = N.attach_day(f, N.run(f, sig, sd, flat_m=960, cost=cost,
                                                   cx=cx, **geom))
                        for bn, msk in bl.items():
                            t = tr[msk[tr["sig"].to_numpy()]]
                            if len(t) < 25:
                                continue
                            e, pf = stats(t)
                            m = mix(t)
                            rows.append(dict(feed=name, block=bn, side=side, geom=gname,
                                             read=rd, pair=f"{fa}/{sl}", n=len(t),
                                             pct=round(e, 4), pf=round(pf, 3),
                                             win=round(float((t.pts > 0).mean()), 3),
                                             bind=m["cross"], stop=m["stop"], tgt=m["target"],
                                             flat=m["flat"], hold=round(float(
                                                 (t["xb"] - t["eb"]).mean()), 1),
                                             mde=round(N.mde(t["pct"].std(), len(t)), 4)))
    o = pd.DataFrame(rows)
    o.to_csv(os.path.join(HERE, "n12_cross_exit.csv"), index=False)

    print("=" * 126)
    print("THE BINDING RATE FIRST -- share of trades that actually exit on the cross")
    print("=" * 126)
    b = o[o.read != "off"].groupby(["read", "pair", "geom"]).agg(
        bind=("bind", "mean"), hold=("hold", "mean"), cells=("bind", "size"))
    print(b.round(3).to_string())

    for g in GEOMS:
        print(f"\n--- {g} ---")
        s = o[o.geom == g]
        print(s[["feed", "block", "side", "read", "pair", "n", "pct", "pf", "win",
                 "bind", "stop", "tgt", "flat", "hold", "mde"]].to_string(index=False))

    print("\n" + "=" * 126)
    print("PAIRED -- each reading minus its own OFF twin on identical feed/block/side/geometry")
    print("=" * 126)
    k = ["feed", "block", "side", "geom"]
    base = o[o.read == "off"].set_index(k)[["pct", "n", "pf", "stop", "flat", "hold"]]
    j = o[o.read != "off"].set_index(k).join(base, rsuffix="_0")
    j["d_pct"] = j["pct"] - j["pct_0"]
    j["d_pf"] = j["pf"] - j["pf_0"]
    j["d_n"] = j["n"] - j["n_0"]
    j["d_hold"] = j["hold"] - j["hold_0"]
    jr = j.reset_index()
    print(jr[["feed", "block", "side", "geom", "read", "pair", "n", "n_0", "d_n",
              "pct", "pct_0", "d_pct", "d_pf", "d_hold", "mde"]].round(4).to_string(index=False))

    print("\n  marginal average of the paired delta, by reading (the whole grid, never a top row):")
    mg = jr.groupby("read").agg(d_pct=("d_pct", "mean"), d_pf=("d_pf", "mean"),
                                d_n=("d_n", "mean"), d_hold=("d_hold", "mean"),
                                beats=("d_pct", lambda x: float((x > 0).mean())),
                                cells=("d_pct", "size"))
    print(mg.round(4).to_string())
    print("\n  by pair (a result that lives at one pair and not its neighbour is a spike):")
    print(jr.groupby("pair").agg(d_pct=("d_pct", "mean"),
                                 beats=("d_pct", lambda x: float((x > 0).mean())),
                                 cells=("d_pct", "size")).round(4).to_string())
    print("\n  by block (research is the only one permitted to choose):")
    print(jr.groupby(["feed", "block"]).agg(d_pct=("d_pct", "mean"),
                                            beats=("d_pct", lambda x: float((x > 0).mean())),
                                            cells=("d_pct", "size")).round(4).to_string())
    n_out = int((jr["d_pct"].abs() > jr["mde"]).sum())
    print(f"\n  cells whose paired delta exceeds its OWN minimum detectable effect: "
          f"{n_out} of {len(jr)}")
    print(f"  cells beating their own OFF twin: {int((jr.d_pct > 0).sum())} of {len(jr)} "
          f"(chance is 50%)")
    jr.to_csv(os.path.join(HERE, "n12_paired.csv"), index=False)


if __name__ == "__main__":
    main()
