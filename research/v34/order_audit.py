"""How many limit orders are resting AT ONCE? The one question that decides whether V34 measures
anything a script could place.

`CLAUDE.md`: "A BACKTEST'S FILL MODEL CAN TAKE ORDERS A SCRIPT CANNOT PLACE. `eem.run`'s limit entry
scans forward from each signal in turn and fills at THAT signal's level, so a limit priced eight
bars ago outranks a nearer one priced since -- eight simultaneous resting orders with the far one
filling first. A script has ONE live order."

`_walk_limit` sets its position lock `free` only on EXIT, inside `if done == 1`. An order that is
resting and has NOT filled therefore blocks nothing, so trigger i+1 places its own order while
trigger i's is still live. With `expiry=2` the windows overlap by one bar and it barely matters.
With `expiry=18` they overlap by seventeen.

This reconstructs the order book the walker implies and counts concurrency directly, rather than
arguing about it from the source.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v34")
import intrabar as IB         # noqa: E402
import v34mech as M           # noqa: E402


def concurrency(tf, trig, side, depth, expiry):
    """For every trigger the walker would attempt, the 1-minute window its order is live for.
    Then the maximum number of windows overlapping at any minute."""
    m = IB.minute_map(tf)
    hi = m["hi"]
    n1 = len(m["c"])
    starts, ends = [], []
    for i in trig:
        s = hi[i]
        e = hi[i + expiry] if i + expiry < len(hi) else n1
        if s < e:
            starts.append(s); ends.append(min(e, n1))
    if not starts:
        return None
    s = np.array(starts); e = np.array(ends)
    edges = np.concatenate([s, e])
    delta = np.concatenate([np.ones(len(s)), -np.ones(len(e))])
    o = np.argsort(edges, kind="mergesort")
    live = np.cumsum(delta[o])
    return dict(orders=len(s), max_live=int(live.max()), mean_live=float(live.mean()),
                share_gt1=float((live > 1).mean()),
                mean_window_min=float((e - s).mean()))


if __name__ == "__main__":
    print("=" * 122)
    print("SIMULTANEOUS RESTING ORDERS implied by `_walk_limit`, by expiry.  A live script can hold "
          "ONE.")
    print("=" * 122)
    print(f"   {'cell':<16}{'expiry':>7}{'orders':>8}{'window (min)':>14}{'max live':>10}"
          f"{'mean live':>11}{'share >1 order':>16}")
    rows = []
    for tf in (5, 15):
        res, _lok, _s = M.blocks(tf)
        for sig in ("everybar", "donch"):
            t, _mod = M.signals(sig, tf, 1)
            tb = t[res[t]]
            for e in (2, 4, 6, 9, 12, 18):
                c = concurrency(tf, tb, 1, 0.75, e)
                if c is None:
                    continue
                rows.append(dict(cell=f"{sig} {tf}m L", expiry=e, **c))
                print(f"   {f'{sig} {tf}m L':<16}{e:>7}{c['orders']:>8}"
                      f"{c['mean_window_min']:>14.0f}{c['max_live']:>10}"
                      f"{c['mean_live']:>11.2f}{c['share_gt1']:>16.3f}")
    df = pd.DataFrame(rows)
    df.to_csv("research/v34/v34_concurrency.csv", index=False)
    print("\n   A script holds ONE resting order. Every row with `max live` above 1 is a backtest "
          "taking\n   orders that cannot all be placed, and the effect grows with expiry -- which "
          "is exactly the axis\n   the edge was rising on while the FILL RATE stood still.")
