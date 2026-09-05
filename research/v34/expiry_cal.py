"""How long may the order rest? A CALIBRATION, declared as one, with every rung reported.

The first V34 run used `expiry=2` chart bars, which on 5-minute bars gives a resting order TEN
MINUTES to fill and produced fill rates of 4-6%. `research/atme/` measured the mechanic at a 35%
fill rate. At 5% the test is not measuring the mechanic, it is measuring whether price reversed
almost immediately -- a different and much rarer event.

This is not a sweep for performance: the rung is chosen by FILL RATE ALONE, to match the study the
hypothesis came from, and every rung's edge is printed so the choice can be audited. Whatever rung
lands nearest 35% is then the one the five hypotheses are re-scored at, once.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v34")
import v34mech as M           # noqa: E402

EXPIRIES = (2, 4, 6, 9, 12, 18)
TARGET_FILL = 0.35


def table():
    rows = []
    for tf in M.TFS:
        res, _lok, _s = M.blocks(tf)
        for sig in M.SIGNALS:
            for side in M.SIDES:
                t, _mod = M.signals(sig, tf, side)
                tb = t[res[t]]
                for e in EXPIRIES:
                    M.EXPIRY = e
                    s = M.stat(M.run_limit(tf, tb, side, 0.75), len(tb))
                    if s:
                        rows.append(dict(tf=tf, sig=sig, side=side, expiry=e, fill=s["fill"],
                                         per_signal=s["per_signal"], per_trade=s["per_trade"],
                                         pf=s["pf"], n=s["n"]))
    M.EXPIRY = 2
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = table()
    df.to_csv("research/v34/v34_expiry.csv", index=False)
    print("=" * 118)
    print("ORDER RESTING TIME -- fill rate first, edge second.  Depth fixed at 0.75xATR(5), "
          "research block.")
    print("=" * 118)
    print(f"   {'expiry':>7}{'minutes (5m/15m)':>20}{'mean fill':>11}{'$/signal':>11}"
          f"{'$/trade':>10}{'mean PF':>10}   fill by cell")
    for e, g in df.groupby("expiry"):
        cells = "  ".join(f"{r.sig[:4]}{r.tf}{'L' if r.side > 0 else 'S'}:{r.fill:.2f}"
                          for r in g.itertuples())
        print(f"   {e:>7}{f'{5 * e}/{15 * e}':>20}{g.fill.mean():>11.3f}"
              f"{g.per_signal.mean():>+11.4f}{g.per_trade.mean():>+10.3f}{g.pf.mean():>10.3f}   "
              f"{cells}")
    by_e = df.groupby("expiry").fill.mean()
    best = int((by_e - TARGET_FILL).abs().idxmin())
    print(f"\n   Nearest the {TARGET_FILL:.0%} fill rate the hypothesis was measured at: "
          f"expiry {best} (mean fill {by_e[best]:.3f}).  That rung, and no other, is what the five "
          "hypotheses are re-scored at.")
    print(f"   For the record the edge does NOT rise monotonically with resting time: "
          + "  ".join(f"{e}:{v:+.3f}" for e, v in df.groupby('expiry').per_signal.mean().items()))
