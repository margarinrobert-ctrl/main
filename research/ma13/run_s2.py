"""S2 -- the nulls. Nine declared cells against a random entry with identical barriers.

A matched random entry keeps the window, the side mix, the 100/100 barriers, the breakeven and the
cost, and moves only WHICH BAR the trade opens on. It is the only null that prices the barriers and
the drift at once. `E[max t | noise]` over the nine cells is printed before the table.
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import m13core as M

pd.set_option("display.width", 200)
ARMS = {"as submitted": dict(),
        "+ 13:00-16:00": dict(s0=780, s1=960),
        "+ breakeven 25 / secure 5": dict(be_pts=25.0, be_off=5.0)}


def main():
    n = len(ARMS) * 3
    print("=" * 104)
    print(f"S2  NULLS -- {n} declared cells, E[max t | noise] = {M.e_max_normal(n):.3f} "
          f"against the 2.802 detection needs")
    print("=" * 104)
    rows = []
    for name in ("US30L", "US30I"):
        f = M.load(name, 15); cost = M.COST[name]; bl = M.blocks(f, name)
        sig, sd = M.signals(f)
        for aname, kw in ARMS.items():
            tr = M.attach_day(f, M.run(f, sig, sd, cost=cost, **kw))
            for bn, mask in bl.items():
                t = tr[mask[tr["sig"].to_numpy()]]
                if len(t) < 25:
                    continue
                e = t["pct"].mean()
                nl = M.control(f, t, sig, seed=11, n_draw=250, cost=cost, **kw)
                bo = M.boot_edge(t, n=2000, seed=7)
                rows.append(dict(feed=name, block=bn, arm=aname, n=len(t),
                                 pts=round(t["pts"].mean(), 3), pct=round(e, 5),
                                 pf=round(t.loc[t.pts > 0, "pts"].sum() /
                                          max(-t.loc[t.pts < 0, "pts"].sum(), 1e-9), 3),
                                 ctl=round(float(np.nanmedian(nl)), 5),
                                 p=round(M.pval(e, nl), 3),
                                 boot=round(float((bo <= 0).mean()), 3),
                                 mde=round(M.mde(t["pct"].std(), len(t)), 5)))
    o = pd.DataFrame(rows)
    o.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "s2_nulls.csv"),
             index=False)
    print(o.to_string(index=False))
    print(f"\n  cells clearing a matched random entry at p<=0.05: "
          f"{int((o.p <= 0.05).sum())} of {len(o)} ({0.05*len(o):.1f} expected by chance)")
    print(f"  cells whose effect exceeds their OWN MDE: "
          f"{int((o.pct.abs() > o.mde).sum())} of {len(o)}")
    print(f"  cells whose day-block bootstrap excludes zero: "
          f"{int((o.boot <= 0.05).sum())} of {len(o)}")


if __name__ == "__main__":
    main()
