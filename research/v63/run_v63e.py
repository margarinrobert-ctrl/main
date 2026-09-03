"""V63 stage E -- the maximum hold, which turned out to be LOAD-BEARING, and the exit profile.

V61 and V62 measured the 480-bar cap INERT: with a channel exit and an ATR stop, one of them always
fired first. This design has no channel exit and no target, so the cap is the exit for every trade
that does not stop out -- the median WINNER holds exactly 480 bars. An axis that binds must be
swept and reported, not inherited.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v63core as V                                                # noqa: E402
from run_v63b import res_for, geo_index, set_rows, stat            # noqa: E402
from run_v63d import FINAL                                         # noqa: E402

HOLDS = (60, 120, 240, 480, 960)


def walk(cell, market, hold, cost_mult=1.0):
    res = res_for(market, int(cell["tf"]))
    D, blk, names = res["D"], res["blk"], res["names"]
    sel, pool = set_rows(res, cell)
    rows = res["rows"]
    xb, pts = V._tensor(D["o"], D["h"], D["l"], D["c"], D["atr"], rows.astype(np.int64),
                        np.array([float(cell["stop"])]), np.array([float(cell["trail"])]),
                        np.array([float(cell["tp"])]), D["cost"] * cost_mult,
                        D["slip"] * cost_mult, hold, D["n"])
    free, out = -1, []
    for k in sel:
        if xb[k, 0] < 0 or not np.isfinite(pts[k, 0]) or rows[k] <= free:
            continue
        free = xb[k, 0]
        capped = (xb[k, 0] - rows[k]) >= hold
        out.append((blk[rows[k]], 100.0 * float(pts[k, 0]) / res["epx"][k],
                    (xb[k, 0] - rows[k]) * cell["tf"], capped))
    return out, names


def main():
    print(__doc__)
    print("=" * 118)
    print("E1. THE MAXIMUM HOLD -- pooled over the seven blocks that chose nothing")
    print("=" * 118)
    print(f"  {'hold':>6s} {'bars':>5s} {'days':>5s} | {'n':>5s} {'pct/tr':>8s} {'PF':>5s} "
          f"{'win':>6s} {'blocks +':>9s} {'capped':>7s} {'streak':>7s}")
    for hold in HOLDS:
        rows, pcts = [], []
        blocks_pos = blocks_tot = 0
        cap = []
        for m in V.FEEDSORDER:
            out, names = walk(FINAL, m, hold)
            for bi, nm in enumerate(names):
                if m == "US100" and nm == "research":
                    continue
                p = np.array([x[1] for x in out if x[0] == bi])
                if len(p) < 5:
                    continue
                blocks_tot += 1
                blocks_pos += int(p.mean() > 0)
                rows.append(p)
            cap += [x[3] for x in out]
        p = np.concatenate(rows)
        w = p > 0
        st = cur = 0
        for x in p:
            cur = cur + 1 if x <= 0 else 0
            st = max(st, cur)
        print(f"  {hold:6d} {hold:5d} {hold*FINAL['tf']/60/24:5.1f} | {len(p):5d} "
              f"{p.mean():+8.4f} {p[w].sum()/max(1e-9,-p[~w].sum()):5.2f} {100*w.mean():5.1f}% "
              f"{blocks_pos:4d}/{blocks_tot:<4d} {100*np.mean(cap):6.1f}% {st:7d}")
    print("\n  `capped` is the share of trades closed by the cap rather than by the stop. `streak`")
    print("  is the longest run of consecutive losers in the pooled out-of-sample stream -- with a")
    print("  win rate near 15% that is the number a live trader feels, not the profit factor.")

    print("\n" + "=" * 118)
    print("E2. THE EXIT PROFILE AT THE SHIPPED 480-BAR CAP")
    print("=" * 118)
    for m in V.FEEDSORDER:
        out, names = walk(FINAL, m, 480)
        p = np.array([x[1] for x in out])
        h = np.array([x[2] for x in out], float)
        c = np.array([x[3] for x in out])
        w = p > 0
        print(f"  {m:7s} n {len(p):4d}   stopped {100*(~c).mean():5.1f}% (mean {p[~c].mean():+.3f})"
              f"   capped {100*c.mean():5.1f}% (mean {p[c].mean():+.3f})   "
              f"the capped trades supply {100*p[c].sum()/max(p.sum(),1e-9):5.0f}% of net")
        print(f"  {'':7s} median hold {np.median(h)/60:5.1f} h   winners {np.median(h[w])/60:6.1f} h"
              f"   losers {np.median(h[~w])/60:5.1f} h   top 5% of trades supply "
              f"{100*np.sort(p)[::-1][:max(1,len(p)//20)].sum()/max(p.sum(),1e-9):4.0f}% of net")


if __name__ == "__main__":
    main()
