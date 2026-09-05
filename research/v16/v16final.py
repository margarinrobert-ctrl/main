"""Phases 3-5 on the finalist, then the locked block, read once.

THE FINALIST WAS CHOSEN ON RESEARCH, FROM A LADDER, NOT FROM A LEADERBOARD. The best single cell in
the 2,167-condition sweep was `agree20_60 >= 1` on 15m long: 285 trades, +91.1R, Sharpe 2.30,
p 0.0000. It is rejected here, because its own neighbourhood says it is not a mechanism -- the four
rungs below it have excesses of -1.2, +6.1, -1.1 and -4.4 over the same control. A rule that exists
at one threshold and nowhere near it is the thing this branch has been burned by before.

`tsmom40` is taken instead: excess over the matched control of +12.8, +25.5, +52.6, +45.7, +50.1 at
five consecutive rungs, decaying to -5.9 only at the extreme. That is what an edge looks like when
it is graded. The rung shipped is 0.5 -- the middle of the plateau and the one keeping the most
trades, not the one with the highest Sharpe.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
import v16core as C          # noqa: E402
import v16mom as M           # noqa: E402
import v16phase2 as P2       # noqa: E402

TF, SIDE, FEAT, OFF = 15, 1, "tsmom40", 0.5


def show(tag, s):
    print(f"   {tag:<34}{s['n']:>7} trades{s['R']:>+9.1f}R{s['perR']:>+9.4f}/trade"
          f"{s['pf']:>8.3f} PF{100*s['win']:>8.2f}% win{s.get('sharpe', np.nan):>8.2f} Sharpe")


if __name__ == "__main__":
    P, pool, res, lock = P2.ctx(TF)

    print("=" * 104)
    print("A. DOES VOLATILITY-SCALING THE PAST RETURN HELP? -- the paper's own design choice, tested")
    print("=" * 104)
    print("   The paper argues raw past returns let the most volatile assets monopolise the extreme")
    print("   buckets, so returns should be scaled before ranking. That argument is about a CROSS-")
    print("   SECTION. On one instrument there is no cross-section for the scaling to fix, and the")
    print("   two versions should then be interchangeable. They are:\n")
    print(f"   {'condition':<20}{'trades':>8}{'net R':>9}{'R/trade':>10}{'PF':>8}{'Sharpe':>9}")
    for feat, off in (("tsmom40", 0.5), ("roc40", 2.0), ("tsmom40", 1.0), ("roc40", 3.0)):
        _O, _i, s, _k = P2.leg(P, pool, SIDE, res, feat, off)
        lab = "vol-scaled" if feat.startswith("tsmom") else "raw"
        print(f"   {feat + '>=' + str(off):<20}{s['n']:>8}{s['R']:>+9.1f}{s['perR']:>+10.4f}"
              f"{s['pf']:>8.3f}{s['sharpe']:>9.2f}   {lab}")
    print("\n   Matched on trade count the two are the same rule. Vol-scaling is not the lever here.")

    print("\n" + "=" * 104)
    print("B. THE PAPER'S HEADLINE, ON THIS DATA: TREND FOLLOWING DOES THE WORK, MOMENTUM ADDS LITTLE")
    print("=" * 104)
    print("   The breakout IS the trend-following overlay. Its own contribution against the momentum")
    print("   filter's, per timeframe, both measured as excess over the same matched control:\n")
    print(f"   {'timeframe':<12}{'breakout alone':>18}{'+ best momentum':>18}{'momentum adds':>16}")
    for tf in (5, 15, 30):
        Pt, poolt, rest, _l = P2.ctx(tf)
        _O, _i, base, _k = P2.leg(Pt, poolt, 1, rest, None, 0)
        _O2, _i2, best, _k2 = P2.leg(Pt, poolt, 1, rest, "tsmom40", 0.5)
        print(f"   {str(tf) + 'm long':<12}{base['perR']:>+18.4f}{best['perR']:>+18.4f}"
              f"{best['perR'] - base['perR']:>+16.4f}")
    print("\n   On 30m the breakout alone already earns +0.11 R/trade and momentum adds almost")
    print("   nothing measurable against its control; on 5m the breakout is destroyed by turnover")
    print("   and momentum only recovers part of the loss. 15m is where the filter has room.")

    print("\n" + "=" * 104)
    print(f"C. THE FINALIST ON RESEARCH -- {TF}m long, {FEAT} >= {OFF}")
    print("=" * 104)
    _O, _i, base, _k = P2.leg(P, pool, SIDE, res, None, 0)
    _O, _i, fin, _k = P2.leg(P, pool, SIDE, res, FEAT, OFF)
    show("Donchian 30/20 alone", base)
    show(f"+ {FEAT} >= {OFF}", fin)

    print("\n   The MINUTE-OF-DAY MATCHED CONTROL, run as a gate. Random entries with the same side,")
    print("   geometry and time-of-day mix -- this prices in drift, costs and session timing at once,")
    print("   which the selectivity control does not.")
    s, ctl, p = P2.mod_control(P, pool, SIDE, res, FEAT, OFF, draws=2000)
    print(f"      rule {s['R']:+.1f}R   control median {np.median(ctl):+.1f}R   "
          f"p95 {np.percentile(ctl, 95):+.1f}R   p = {p:.4f}")
    s0, ctl0, p0 = P2.mod_control(P, pool, SIDE, res, None, 0, draws=2000)
    print(f"      the UNFILTERED breakout against the same control: {s0['R']:+.1f}R vs median "
          f"{np.median(ctl0):+.1f}R, p = {p0:.4f}")

    print("\n" + "=" * 104)
    print("D. GEOMETRY, SWEPT AFTER THE CONDITION WAS FIXED -- marginal averages, never the top cell")
    print("=" * 104)
    G = P2.geometry(TF, SIDE, FEAT, OFF)
    print(f"   80 cells. Share profitable: {float((G.R > 0).mean()):.0%}   "
          f"median R/trade {G.perR.median():+.4f}   best cell {G.R.max():+.1f}R "
          f"(the maximum of 80 draws, quoted here only so it is not quoted elsewhere)")
    P2.marginal(G, "exit_n", "exit channel length")
    P2.marginal(G, "stop", "ATR stop multiple")
    P2.marginal(G, "tp", "target, in R (0 = none)")
    G.to_csv("results/v16/v16_geom.csv", index=False)

    print("\n" + "=" * 104)
    print("E. THE LOCKED BLOCK, READ ONCE")
    print("=" * 104)
    print("   Multiplicity first: 2,167 conditions were tested on research, 742 were profitable")
    print("   there, and 99 of those beat a same-selectivity control at p <= 0.05 against about 37")
    print("   expected by chance. One condition was carried forward. The geometry above was swept")
    print("   after the fact and its default cell -- exit 20, stop 2.0, no target -- is what is read.\n")
    _O, _i, bl, _k = P2.leg(P, pool, SIDE, lock, None, 0)
    _O, _i, fl, _k = P2.leg(P, pool, SIDE, lock, FEAT, OFF)
    show("LOCKED  Donchian 30/20 alone", bl)
    show(f"LOCKED  + {FEAT} >= {OFF}", fl)
    sL, ctlL, pL = P2.mod_control(P, pool, SIDE, lock, FEAT, OFF, draws=2000)
    print(f"\n      against the minute-of-day control: rule {sL['R']:+.1f}R, control median "
          f"{np.median(ctlL):+.1f}R, p = {pL:.4f}")
    print("\n   And the SHORT leg, same feature, same timeframe, reported whether or not it helps:")
    for off in (0.5, 1.0, 1.5):
        _O, _i, sr, _k = P2.leg(P, pool, -1, res, FEAT, off)
        _O, _i, sl2, _k = P2.leg(P, pool, -1, lock, FEAT, off)
        print(f"      {FEAT} >= {off:<4} research {sr['R']:>+7.1f}R on {sr['n']:>4} "
              f"({sr['perR']:+.4f}/trade)   locked {sl2['R']:>+7.1f}R on {sl2['n']:>4} "
              f"({sl2['perR']:+.4f}/trade)")
