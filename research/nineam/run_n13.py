"""N13 -- THE PLACEBO FOR THE OPPOSITE-CROSS EXIT.

`run_n12` measured the policy against its own OFF twin and found it subtracts. That comparison
cannot answer the question that decides whether the EMA is doing any work at all, because an exit
rule changes two things at once: WHEN it closes, and THAT it closes early. The second needs no
forecasting -- a coin flip closing at the same rate would also cut the holding period, also raise
the win rate, and also change the trade count by freeing the position lock.

So every cell is re-run against an exit array carrying THE SAME NUMBER of exit bars with the SAME
signed mix, placed at RANDOM bars. If the real delta sits inside that distribution, the cross is
decoration on a mechanical early exit. This is the random-delay placebo of the execution-overlay
literature, applied to an exit instead of an entry, and it is the same instrument `TEAM_EXIT_PF`
used to find that the 1.0 ATR trail raises its own coin flip's profit factor by as much as its own.

Scoped to the shipped pair (13/48) and 100 seeds a cell -- 2 readings x 2 sides x 2 geometries x
2 feeds = 16 configurations, read on all three blocks. The pair axis is not re-run here: n12 showed
13/48 and 21/55 agree in sign on every marginal, so the placebo has nothing to separate there.
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import na_core as N

pd.set_option("display.width", 220)
HERE = os.path.dirname(os.path.abspath(__file__))
SIDES = ["long", "both"]
GEOMS = {"1.5N / none": dict(stop_a=1.5, tgt_r=0.0),
         "100pt / 100pt": dict(stop_pts=100.0, tgt_pts=100.0)}
FEEDS = ["US30L", "US30I"]
RS, RE = 540, 555
NSEED = 100


def main():
    print("=" * 118)
    print("N13  PLACEBO -- the same number of early exits, at RANDOM bars")
    print("=" * 118)
    print(f"  {NSEED} seeds a cell, pair 13/48, 16 configurations x 3 blocks\n")
    rows = []
    for name in FEEDS:
        f = N.load(name, 15); cost = N.COST[name]
        bl = N.blocks(f, name)
        rhi, rlo, _ = N.ranges(f, RS, RE)
        for side in SIDES:
            sig, sd = N.events(f, rhi, rlo, side=side, rs=RS, re_=RE, open_m=570)
            for gname, geom in GEOMS.items():
                off = N.attach_day(f, N.run(f, sig, sd, flat_m=960, cost=cost, **geom))
                for rd in ("cross", "state"):
                    cx = N.cross_exit(f, 13, 48, "ema", rd)
                    real = N.attach_day(f, N.run(f, sig, sd, flat_m=960, cost=cost,
                                                 cx=cx, **geom))
                    nul = {bn: [] for bn in bl}
                    for s_ in range(NSEED):
                        sh = N.shuffle_exit(f, cx, seed=s_)
                        t = N.attach_day(f, N.run(f, sig, sd, flat_m=960, cost=cost,
                                                  cx=sh, **geom))
                        for bn, m in bl.items():
                            u = t[m[t["sig"].to_numpy()]]
                            nul[bn].append(float(u["pct"].mean()) if len(u) >= 25 else np.nan)
                    for bn, m in bl.items():
                        r = real[m[real["sig"].to_numpy()]]
                        o0 = off[m[off["sig"].to_numpy()]]
                        if len(r) < 25 or len(o0) < 25:
                            continue
                        d = float(r["pct"].mean()) - float(o0["pct"].mean())
                        nd = np.array(nul[bn]) - float(o0["pct"].mean())
                        nd = nd[np.isfinite(nd)]
                        if nd.size < 20:
                            continue
                        rows.append(dict(
                            feed=name, block=bn, side=side, geom=gname, read=rd,
                            d_real=round(d, 4), plc_med=round(float(np.median(nd)), 4),
                            plc_p5=round(float(np.percentile(nd, 5)), 4),
                            plc_p95=round(float(np.percentile(nd, 95)), 4),
                            pctile=round(float((nd < d).mean()), 3)))
    o = pd.DataFrame(rows)
    o.to_csv(os.path.join(HERE, "n13_placebo.csv"), index=False)
    print(o.to_string(index=False))
    print("\n  marginal, by reading:")
    print(o.groupby("read").agg(d_real=("d_real", "mean"), plc_med=("plc_med", "mean"),
                                pctile=("pctile", "mean"),
                                above95=("pctile", lambda x: int((x > 0.95).sum())),
                                cells=("d_real", "size")).round(4).to_string())
    print(f"\n  cells where the real exit beats its own placebo at the 95th percentile: "
          f"{int((o.pctile > 0.95).sum())} of {len(o)}")
    print(f"  cells where the PLACEBO does better than the real exit (pctile < 0.5): "
          f"{int((o.pctile < 0.5).sum())} of {len(o)}")


if __name__ == "__main__":
    main()
