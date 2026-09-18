"""THE ONE THING THAT REPLICATED, AND WHETHER IT IS WORTH ANYTHING.

`run_g5` killed the ATR percentile as a DIRECTION condition and killed it thoroughly: research
p 0.021, holdout **0.888**, reserved forward block **0.746**, and the MIRROR clears the holdout at
p 0.004 while failing the other two. The volatility-state sign is a property of the block, not of
the market -- the seventh time it has moved on this branch.

But the same run reproduced `STUDY_V22`'s MECHANISM on US30, monotone, on all three blocks
including a reserved forward feed from a different provider:

    forward realised vol / trailing ATR, by ATR percentile bucket
      research  3.364  2.936  2.535  2.177  1.926
      holdout   3.746  3.034  2.757  1.966  1.867
      forward   2.930  2.726  2.670  2.061  1.728

ATR(14) is backward-looking and volatility mean-reverts, so when ATR sits LOW in its own
distribution the next four hours realise 3.0-3.7x it, and when it sits HIGH only 1.7-1.9x. That is
not a direction call and no amount of it will become one. It is a statement about how far price
travels relative to the stop you just placed -- i.e. a SIZING fact, and the only thing in this
study that survived every block it was read on.

THE TEST. Strip the signal out entirely so nothing but the stop policy can move the answer: go long
at the first RTH bar of every session, exit at the last RTH bar's close or at the stop. Zero
conditions, one trade a session, no target, no search. Then vary ONLY the stop:

    fixed 1.0 / 1.5 / 2.0 / 2.5 / 3.0 N
    V22 ADAPTIVE  -- 2.5N when the ATR percentile <= 0.5, else 1.5N
    NAIVE INVERSE -- 1.5N when <= 0.5, else 2.5N

The inverse is the falsifier and is the reason to trust the result if it comes out worse: if
widening the stop in calm conditions is simply "wider stops are better" (`STUDY_V18`, monotone on
five markets), the inverse would be no worse than fixed. Scored in PERCENT OF PRICE, because R
divides by the very quantity being varied (`STUDY_V61`: the first R ranking put a +2.33 R cell on
top whose actual return was +0.32%).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mr30 import mr30core as M  # noqa: E402
from mr30.run_g2 import RTH0, RTH1, boot  # noqa: E402
from mr30.run_g5 import pct250  # noqa: E402


@njit(cache=True)
def _sess(o, h, l, c, at, ent, ex, mult, cost):
    n = len(ent)
    pts = np.zeros(n); why = np.zeros(n, np.int64); rk = np.zeros(n)
    for q in range(n):
        i = ent[q]; j = ex[q]
        e = o[i]
        risk = mult[q] * at[i - 1] if i > 0 else mult[q] * at[i]
        stop = e - risk
        px = c[j]; w = 1
        for t in range(i, j + 1):
            if l[t] <= stop:
                px = stop; w = 0
                break
        pts[q] = px - e - cost
        why[q] = w; rk[q] = risk
    return pts, why, rk


def session_bars(f):
    g = f.copy()
    g["day"] = g.index.normalize()
    pos = np.arange(len(g))
    inr = ((g["mod"] >= RTH0) & (g["mod"] < RTH1)).to_numpy()
    day = g["day"].to_numpy()
    first, last, cnt = {}, {}, {}
    for p in pos[inr]:
        d = day[p]
        if d not in first:
            first[d] = p; cnt[d] = 0
        last[d] = p; cnt[d] += 1
    ks = [d for d in sorted(first) if cnt[d] >= 20]
    return (np.array([first[d] for d in ks]), np.array([last[d] for d in ks]),
            pd.DatetimeIndex(ks))


def run(f, ent, ex, mult, cost):
    pts, why, rk = _sess(f["open"].to_numpy(), f["high"].to_numpy(), f["low"].to_numpy(),
                         f["close"].to_numpy(), f["atr"].to_numpy(),
                         ent.astype(np.int64), ex.astype(np.int64),
                         np.asarray(mult, float), float(cost))
    e = f["open"].to_numpy()[ent]
    return pd.DataFrame(dict(pts=pts, why=why, risk=rk, pct=100.0 * pts / e, R=pts / rk))


def dd(x):
    eq = np.cumsum(x)
    return float(np.max(np.maximum.accumulate(eq) - eq))


def main():
    feeds = [("US30L", "A_research"), ("US30L", "B_holdout"), ("US30I", "C_forward")]
    cache = {}
    for feed in ("US30L", "US30I"):
        f = M.load(feed)
        cache[feed] = (f, pct250(f), M.blocks(f, feed), session_bars(f))

    print("BASE: long the first RTH bar's open, out at the last RTH bar's close or the stop.")
    print("No signal, one trade a session. Only the stop policy varies.\n")
    for feed, bn in feeds:
        f, pc, blk, (ent, ex, days) = cache[feed]
        m = np.array([bool(blk[bn][i]) for i in ent])
        e_, x_ = ent[m], ex[m]
        cost = M.COST
        calm = np.nan_to_num(pc[e_ - 1] <= 0.5, nan=False).astype(bool)
        pol = {f"fixed {k}N": np.full(len(e_), k) for k in (1.0, 1.5, 2.0, 2.5, 3.0)}
        pol["V22 adaptive"] = np.where(calm, 2.5, 1.5)
        pol["naive inverse"] = np.where(calm, 1.5, 2.5)
        print(f"=== {feed} {bn}: {len(e_)} sessions, {int(calm.sum())} calm "
              f"({calm.mean():.1%}) ===")
        print(f"  {'policy':<16}{'mean %':>10}{'net pts':>10}{'stop-out':>10}{'PF':>8}"
              f"{'Sharpe':>8}{'maxDD %':>10}{'P(<=0)':>9}")
        for nm, mult in pol.items():
            t = run(f, e_, x_, mult, cost)
            sh = t.pct.mean() / t.pct.std(ddof=1) * np.sqrt(252)
            _, _, p0 = boot(t.pct.to_numpy())
            print(f"  {nm:<16}{t.pct.mean():>10.4f}{t.pts.mean():>10.2f}"
                  f"{np.mean(t.why == 0):>10.3f}{M.pf(t.pct):>8.3f}{sh:>8.2f}"
                  f"{dd(t.pct.to_numpy()):>10.2f}{p0:>9.3f}")
        print()

    print("THE FALSIFIER, STATED PLAINLY: adaptive minus fixed-2.0N and inverse minus fixed-2.0N,")
    print("in % of price. If the mechanism is real the first is positive and the second is not,")
    print("on blocks that had no part in choosing anything.")
    print(f"  {'block':<22}{'adaptive - fixed2.0':>22}{'inverse - fixed2.0':>22}")
    for feed, bn in feeds:
        f, pc, blk, (ent, ex, days) = cache[feed]
        m = np.array([bool(blk[bn][i]) for i in ent])
        e_, x_ = ent[m], ex[m]
        calm = np.nan_to_num(pc[e_ - 1] <= 0.5, nan=False).astype(bool)
        base = run(f, e_, x_, np.full(len(e_), 2.0), M.COST).pct.mean()
        a = run(f, e_, x_, np.where(calm, 2.5, 1.5), M.COST).pct.mean()
        i_ = run(f, e_, x_, np.where(calm, 1.5, 2.5), M.COST).pct.mean()
        print(f"  {feed + ' ' + bn:<22}{a - base:>22.4f}{i_ - base:>22.4f}")


if __name__ == "__main__":
    main()
