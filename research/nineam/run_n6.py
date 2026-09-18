"""N6 -- the range is the 09:00 BAR, not the half hour. Re-read as the shipped default.

The ask was "the 9am high and low". That is the 09:00-09:15 window -- exactly the 09:00 candle on a
15-minute chart -- with the breakout still armed only from the 09:30 cash open. The research event
stream has always kept those two separate (`events(... re_=, open_m=)`), so this is a re-read of a
cell the 16,200-grid already contained, now given its own control, bootstrap and MDE because it is
becoming the default.
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import na_core as N
from run_n2 import gate

pd.set_option("display.width", 210)
HERE = os.path.dirname(os.path.abspath(__file__))
WINS = {"09:00-09:15 (the 09:00 bar)": (540, 555), "09:00-09:30 (the half hour)": (540, 570)}
GEOMS = {"1.5N / none": dict(stop_a=1.5, tgt_r=0.0),
         "100pt / 100pt": dict(stop_pts=100.0, tgt_pts=100.0)}


def main():
    print("=" * 108)
    print("N6  THE 09:00 BAR AGAINST THE HALF HOUR -- entry armed at 09:30 in BOTH, paired on blocks")
    print("=" * 108)
    rows = []
    for name in ("US30L", "US30I", "US100L", "NQ"):
        f = N.load(name, 15)
        cost = N.COST[name]
        bl = N.blocks(f, name)
        for wname, (rs, re_) in WINS.items():
            rhi, rlo, rn = N.ranges(f, rs, re_)
            width = np.nanmedian((rhi - rlo) / f["atr"].to_numpy())
            for side in ("long", "both"):
                sig, sd = N.events(f, rhi, rlo, side=side, rs=rs, re_=re_, open_m=570)
                for gname, geom in GEOMS.items():
                    tr = N.attach_day(f, N.run(f, sig, sd, flat_m=960, cost=cost, **geom))
                    for bn, mask in bl.items():
                        t = tr[mask[tr["sig"].to_numpy()]]
                        if len(t) < 25:
                            continue
                        e = t["pct"].mean()
                        ne = N.control_entries(f, t, seed=21, n_draw=400, flat_m=960,
                                               cost=cost, **geom)
                        bo = N.boot_edge(t, n=2000, seed=5)
                        rows.append(dict(feed=name, block=bn, win=wname, side=side, geom=gname,
                                         w_atr=round(float(width), 2), n=len(t),
                                         pct=round(e, 4),
                                         pf=round(t.loc[t.pts > 0, "pts"].sum() /
                                                  max(-t.loc[t.pts < 0, "pts"].sum(), 1e-9), 3),
                                         win_r=round((t.pts > 0).mean(), 3),
                                         ctl=round(float(np.nanmedian(ne)), 4),
                                         p=round(N.pval(e, ne), 3),
                                         boot=round(float((bo <= 0).mean()), 3),
                                         mde=round(N.mde(t["pct"].std(), len(t)), 4)))
    o = pd.DataFrame(rows)
    o.to_csv(os.path.join(HERE, "n6_window.csv"), index=False)

    print("\n  median range width, in ATR at the signal bar:")
    print(o.pivot_table(index="win", columns="feed", values="w_atr").round(2).to_string())

    for g in GEOMS:
        print(f"\n--- {g} ---")
        sub = o[o.geom == g]
        print(sub[["feed", "block", "win", "side", "n", "pct", "pf", "win_r",
                   "ctl", "p", "boot", "mde"]].to_string(index=False))

    print("\n" + "=" * 108)
    print("PAIRED: the 09:00 bar minus the half hour, on identical feed / block / side / geometry")
    print("=" * 108)
    k = ["feed", "block", "side", "geom"]
    a = o[o.win.str.startswith("09:00-09:15")].set_index(k)
    b = o[o.win.str.startswith("09:00-09:30")].set_index(k)
    j = a.join(b, rsuffix="_half", how="inner")
    j["d_pct"] = j["pct"] - j["pct_half"]
    j["d_n"] = j["n"] - j["n_half"]
    print(j[["n", "n_half", "d_n", "pct", "pct_half", "d_pct", "pf", "pf_half"]]
          .round(4).to_string())
    print(f"\n  the 09:00 bar wins {int((j.d_pct > 0).sum())} of {len(j)} paired cells; "
          f"mean delta {j.d_pct.mean():+.4f} %/trade against a mean MDE of {o.mde.mean():.4f}")
    print(f"  cells clearing their control at p<=0.05: {int((o.p <= 0.05).sum())} of {len(o)} "
          f"({0.05*len(o):.1f} expected);  outside their own MDE: "
          f"{int((o.pct.abs() > o.mde).sum())} of {len(o)}")
    print(f"  E[max t | pure noise] over {len(o)} looks = {N.e_max_normal(len(o)):.3f} "
          f"against the 2.802 detection needs")


if __name__ == "__main__":
    main()
