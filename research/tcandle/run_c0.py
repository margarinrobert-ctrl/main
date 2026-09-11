"""Which textbook patterns can NEVER fire on a breakout bar -- proved on the bars, not asserted.

A System 1 entry needs `high > max(high[1..20])`, and that maximum INCLUDES the previous bar's
high, so `high > high[1]` follows by arithmetic.  Every pattern whose definition requires
`high <= high[1]` is therefore unavailable on the trigger's own bars, however good it looks in a
textbook.  This is the cheapest possible version of the base-rate check: it needs no P&L, no
control and no holdout, and it removes candidates before anything is scored.

Counted across three markets and five timeframes so it is a measurement rather than a claim.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research/tcandle")
import tc_core as T, tc_feat as CF                      # noqa: E402

MKTS = ("NQ", "US100L", "US30L")


def one(mkt, tf):
    d = T.frame(mkt, tf)
    atr, adx, dist = T.context(d)
    C = T.channels(d, T.SPEC["e1"], T.SPEC["e2"], T.SPEC["x1"], T.SPEC["x2"])
    sig = T.signal_bars(d, C, np.isfinite(atr) & (atr > 0), atr)
    F = CF.build(d, atr)
    row = {"mkt": mkt, "tf": tf, "signals": len(sig),
           "h_gt_h1": float((d["h"][sig] > np.r_[np.nan, d["h"][:-1]][sig]).mean())}
    for k, v in F.items():
        u = np.unique(v[np.isfinite(v)])
        if len(u) <= 2 and set(u.tolist()) <= {0.0, 1.0}:
            row[k] = float(np.nanmean(v[sig]))
    return row


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    df = pd.DataFrame([one(m, tf) for m in MKTS for tf in T.TFS])
    df.to_csv("research/tcandle/c0_structure.csv", index=False)
    pats = [c for c in df.columns if c.startswith(("p1.", "p2.", "p3."))]
    rate = df[pats].mean().sort_values()
    print("=" * 88)
    print("PATTERN PASS RATE ON THE TRIGGER'S OWN BARS -- mean over 3 markets x 5 timeframes")
    print("=" * 88)
    print(f"`high > high[1]` holds on {df.h_gt_h1.mean()*100:.2f}% of signal bars "
          f"(min over cells {df.h_gt_h1.min()*100:.2f}%) -- it is implied by the channel break.\n")
    dead = rate[rate <= 0.001]
    print(f"NEVER FIRES on a breakout bar ({len(dead)} of {len(pats)} declared patterns):")
    for k, v in dead.items():
        mx = df[k].max()
        print(f"   {k:<24} mean {v:.5f}   worst cell {mx:.5f}")
    print("\nRARE (under 5%):")
    for k, v in rate[(rate > 0.001) & (rate < 0.05)].items():
        print(f"   {k:<24} {v:.4f}")
    print("\nCOMMON (over 50%) -- candidates for being the trigger restated:")
    for k, v in rate[rate > 0.50].items():
        print(f"   {k:<24} {v:.4f}")
    print(f"\nUSABLE MIDDLE (5%-50%): {int(((rate>=0.05)&(rate<=0.50)).sum())} patterns")
