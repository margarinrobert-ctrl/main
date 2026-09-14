"""N8 -- the SECURED-POINTS rung: 5 points, against 0 / 10 / 25, on all three blocks.

A stop at the fill books MINUS the round turn, which is why a true breakeven exit paints red in a
Strategy Tester. The threshold that turns it into a win is the ROUND TURN, not zero. So the
question this asks is two-sided: does the secured distance clear the cost (arithmetic), and does
moving the stop further from the fill change the trades or only their labels (measurement).

Read the trade count before the win rate. If `d_n` is near zero the secured level is RELABELLING
exits it did not move, and a thirty-point jump in win rate is a bookkeeping change. If it grows,
the level has started acting as a small take profit and no longer is a breakeven at all -- which
is what the 25-point rung is, and no take profit has beaten every target tested 26 times here.
"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import na_core as N

pd.set_option("display.width", 200)
RS, RE = 540, 555
WHY = {1: "stop", 2: "target", 3: "flat"}
rows = []
for name in ("US30L", "US30I"):
    f = N.load(name, 15); cost = N.COST[name]
    bl = N.blocks(f, name); rhi, rlo, _ = N.ranges(f, RS, RE)
    for side in ("long", "both"):
        sig, sd = N.events(f, rhi, rlo, side=side, rs=RS, re_=RE, open_m=570)
        for off in (0.0, 5.0, 10.0, 25.0):
            tr = N.attach_day(f, N.run(f, sig, sd, flat_m=960, cost=cost,
                                       stop_a=1.5, be_pts=50.0, be_off=off))
            for bn, mask in bl.items():
                t = tr[mask[tr["sig"].to_numpy()]]
                if len(t) < 25:
                    continue
                v = t["why"].to_numpy()
                rows.append(dict(feed=name, block=bn, side=side, secure=off, n=len(t),
                                 pct=round(t["pct"].mean(), 6),
                                 pts=round(t["pts"].mean(), 4),
                                 win=round(float((t.pts > 0).mean()), 4),
                                 pf=round(t.loc[t.pts > 0, "pts"].sum() /
                                          max(-t.loc[t.pts < 0, "pts"].sum(), 1e-9), 4),
                                 stop=round(float((v == 1).mean()), 3),
                                 flat=round(float((v == 3).mean()), 3)))
o = pd.DataFrame(rows)
print("=" * 104)
print("SECURE LADDER at breakeven = 50 points, 1.5N stop, flat 16:00 -- the round turn is the bar")
print("=" * 104)
print(f"  round turn: US30 {N.COST['US30L']} points.  An exit at the fill books -{N.COST['US30L']} "
      f"and is a LOSS; an exit 5 points beyond it books +{5 - N.COST['US30L']:.2f} and is a WIN.\n")
print(o.to_string(index=False))

print("\n  paired against secure=0, on identical feed / block / side:")
k = ["feed", "block", "side"]
b = o[o.secure == 0].set_index(k)
j = o[o.secure > 0].set_index(k).join(b[["pct", "n", "win"]], rsuffix="_0")
j["d_pct"] = j["pct"] - j["pct_0"]; j["d_win"] = j["win"] - j["win_0"]; j["d_n"] = j["n"] - j["n_0"]
print(j.reset_index()[["feed", "block", "side", "secure", "n", "d_n",
                       "pct", "pct_0", "d_pct", "win", "win_0", "d_win"]].round(6).to_string(index=False))
print("\n  marginal by secured distance:")
print(j.groupby("secure").agg(d_pct=("d_pct", "mean"), d_win=("d_win", "mean"),
                              d_n=("d_n", "mean"),
                              won=("d_pct", lambda x: f"{int((x>0).sum())}/{len(x)}")).round(6).to_string())
