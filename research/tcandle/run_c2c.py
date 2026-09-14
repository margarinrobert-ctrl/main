"""THE UNIT DECIDES WHO WINS, and the study's first pass quoted the wrong one.

`run_c2` reported total return as the sum of `pct`, which `tc_core.run` defines PER UNIT -- the
per-trade P&L divided by the number of ladder units.  That is the right unit for comparing ENTRY
QUALITY across markets, and it is the wrong unit for "total return", because the ladder's extra
units are part of the strategy and the account books all of them.  Worse, the division is not
neutral: a Turtle ladder only adds units when the trade is already going your way, so dividing by
units penalises exactly the winners, and it does so more for a reading that holds trades longer.

This re-runs the same grid and writes BOTH, so nothing has to be taken on trust:
    tot_unit   sum of the per-unit result   (entry quality)
    tot_acct   sum of units x per-unit      (what one contract per Turtle unit actually books)
plus max drawdown and return-over-drawdown on the account series, because a reading that trades a
fifth as often will always lose a total-return race and can still be the better object.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research/tcandle")
import tc_core as T                                     # noqa: E402
from run_c2 import lengths                              # noqa: E402


def mdd(x):
    eq = np.cumsum(x)
    return float(np.max(np.maximum.accumulate(np.r_[0.0, eq]) - np.r_[0.0, eq]))


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    rows = []
    for mkt in ("NQ", "US100L", "US30L"):
        for tf in T.TFS:
            for mode in ("carried", "matched"):
                d = T.frame(mkt, tf)
                atr, adx, dist = T.context(d)
                C = T.channels(d, *lengths(tf, mode))
                base = T.gate_mask(adx, dist, 22.0, 0.0) & np.isfinite(atr) & (atr > 0)
                cut = T.split(d)
                for blk, lo, hi in (("research", 0, cut), ("locked", cut, len(d["c"]))):
                    m = base.copy(); m[:lo] = False; m[hi:] = False
                    tr = T.run(d, C, atr, m, T.COST[mkt])
                    if len(tr) < 5:
                        continue
                    u = tr["units"].to_numpy(float)
                    p = tr["pct"].to_numpy(float)
                    a = p * u
                    rows.append(dict(mkt=mkt, tf=tf, mode=mode, block=blk, n=len(tr),
                                     units=u.mean(), per_unit=p.mean(), per_acct=a.mean(),
                                     tot_unit=p.sum(), tot_acct=a.sum(), dd=mdd(a),
                                     rdd=a.sum() / max(mdd(a), 1e-9),
                                     pf=a[a > 0].sum() / max(-a[a < 0].sum(), 1e-9)))
    f = pd.DataFrame(rows)
    f.to_csv("research/tcandle/c2c_units.csv", index=False)
    print(f.to_string(index=False, float_format=lambda x: f"{x:,.3f}"))

    s = f[f.tf != 240]
    w = s.pivot_table(index=["mkt", "tf", "block"], columns="mode",
                      values=["tot_unit", "tot_acct", "dd", "rdd", "pf", "n", "per_acct"])
    print("\n" + "=" * 92)
    print("WHO WINS ON WHAT -- 24 paired cells, 240m excluded (the readings coincide there)")
    print("=" * 92)
    for col, nm, lower in (("tot_unit", "total return, PER UNIT", False),
                           ("tot_acct", "total return, ACCOUNT (all ladder units)", False),
                           ("per_acct", "per-trade account result", False),
                           ("pf", "profit factor (account)", False),
                           ("dd", "max drawdown", True),
                           ("rdd", "return / drawdown", False),
                           ("n", "trade count", False)):
        a, b = w[col]["matched"], w[col]["carried"]
        win = int((a < b).sum()) if lower else int((a > b).sum())
        print(f"  {nm:<42} matched wins {win:2d}/{len(w)}"
              f"   carried {b.mean():9.3f}   matched {a.mean():9.3f}")
    print("\nPOOLED PROFIT FACTOR (sum gross profit / sum gross loss, account units)")
    g = f.groupby(["mode", "block"]).apply(
        lambda x: pd.Series({"cells": len(x), "trades": x.n.sum(),
                             "mean cell PF": x.pf.mean(), "median cell PF": x.pf.median()}),
        include_groups=False)
    print(g.to_string(float_format=lambda v: f"{v:,.3f}"))
