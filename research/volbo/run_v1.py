"""V1 -- the arithmetic, the base rates, then Gate 1 on the raw rule. No optimisation.

The order matters. `STUDY_V69_ORB` reached a verdict from gross-vs-driftless-bound alone, and
`STUDY_V60_AROON` from a base rate, in both cases before any P&L was worth reading. So: how often
does each level even get hit, what fraction of risk is the round turn, and what win rate does the
realised payoff demand -- and only then the result.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from volbo import vbcore as V  # noqa: E402

# SETTLED IN run_v2 ON TRUE 1-MINUTE DATA: the ambiguous share at 1m is 0.000, so the entry bar
# never stops out, and 'close' reproduces the 1-minute path trade for trade (corr 1.0000, 100%
# identical exit reasons). Blanket pessimism was worth -0.1029 %/trade and flipped the sign.
AMB = "close"

pd.set_option("display.width", 220)
BAR = "=" * 112


def hdr(t):
    print("\n" + BAR + "\n" + t + "\n" + BAR)


FEEDS = ("US100L", "US30L")


def main():
    store = {}
    for nm in FEEDS:
        d = V.load(nm)
        day = V.daily_atr(d)
        store[nm] = (d, day)

    # ------------------------------------------------------------------ V1.0 the sample
    hdr("V1.0  THE SAMPLE -- and what the uploads actually are")
    print("  The three uploaded files are BYTE-IDENTICAL to feeds already in the registry:")
    print("    nasdaq_20252016_15m  sha c449dddfbc06a943 = US100_LONG_15m  (US100, NOT the Nasdaq")
    print("      future -- the registry proved that by measurement, return corr 0.9399 to US100_ISO)")
    print("    us30_20162025_15m    sha 24dcf2e1c7ba398f = US30_LONG_15m")
    print("    us30_2_year_data.rtf                      = US30_ISO_15m (a DIFFERENT provider)")
    print("  So the two long feeds have been read many times on this branch and neither carries an")
    print("  unread block. US30_ISO is the closest thing to reserved and is held back entirely.\n")
    for nm in FEEDS:
        d, day = store[nm]
        print(f"  {nm:<8}{len(d):>8,} RTH bars  {len(day):>6,} sessions  "
              f"{str(d.index[0])[:10]} -> {str(d.index[-1])[:10]}  median ATR5 {day.atr_sma.median():>8.1f}")

    # ------------------------------------------------------------------ V1.1 base rates
    hdr("V1.1  BASE RATES -- how often is each level reached at all?")
    print("  A breakout band that is hit every day is not a filter; one that is never hit has no")
    print("  sample. 0.4 x ATR(5) is the shipped multiple; the ladder shows what it selects.\n")
    print(f"  {'feed':<8}{'k':>6}{'long hit':>10}{'short hit':>11}{'both':>8}{'neither':>9}"
          f"{'trades/yr':>11}{'cost/risk':>11}")
    for nm in FEEDS:
        d, day = store[nm]
        for k in (0.2, 0.3, 0.4, 0.6, 0.8, 1.0):
            t = V.walk(d, day, k=k, cost_pts=V.RT[nm], amb_mode=AMB)
            if not len(t):
                continue
            ns = len(day.dropna(subset=["atr_sma"]))
            g = t.groupby("sess").side.agg(["count", "sum"])
            lh = float((t.side == 1).sum()) / ns
            sh = float((t.side == -1).sum()) / ns
            both = float((g["count"] == 2).sum()) / ns
            yrs = (d.index[-1] - d.index[0]).days / 365.25
            print(f"  {nm:<8}{k:>6.1f}{lh:>10.3f}{sh:>11.3f}{both:>8.3f}{1-lh-sh+both:>9.3f}"
                  f"{len(t)/yrs:>11.1f}{t.cost_frac.median():>11.4f}")
        print()

    # ------------------------------------------------------------------ V1.2 Gate 1
    hdr("V1.2  GATE 1 -- the rule as published, 0.4 x ATR(5), scored in percent of entry price")
    print("  No target, so the break-even win rate is NOT 1/(1+RR). It is set by the REALISED")
    print("  payoff ratio, which is printed beside the win rate it has to beat.\n")
    print(f"  {'feed':<8}{'block':<10}{'n':>6}{'win':>8}{'needs':>8}{'payoff':>8}{'PF':>8}"
          f"{'%/trade':>10}{'total%':>10}{'Sharpe':>8}{'maxDD':>9}{'amb':>7}")
    keep = {}
    for nm in FEEDS:
        d, day = store[nm]
        t = V.walk(d, day, k=0.4, cost_pts=V.RT[nm], amb_mode=AMB)
        keep[nm] = t
        r, lk, cut = V.split(t)
        for lab, tt in (("research", r), ("locked", lk), ("ALL", t)):
            s = V.stats(tt)
            po, be = V.payoff_breakeven(tt)
            print(f"  {nm:<8}{lab:<10}{s['n']:>6}{s['win']:>8.3f}{be:>8.3f}{po:>8.2f}"
                  f"{s['pf']:>8.3f}{s['mean']:>+10.4f}{s['total']:>+10.2f}{s['sharpe']:>8.3f}"
                  f"{s['dd']:>9.2f}{tt.amb.mean():>7.3f}")
        print()

    # ------------------------------------------------------------------ V1.3 gross vs net
    hdr("V1.3  IS COST THE BINDING CONSTRAINT? -- gross beside net, and the cost ladder")
    print("  STUDY_V69_ORB's lesson: gross is the CEILING. Read it before designing any filter.\n")
    print(f"  {'feed':<8}{'block':<10}{'grossPF':>10}{'netPF':>9}{'gross%':>10}{'net%':>10}"
          f"{'cost/risk':>11}{'0x':>9}{'2x':>9}{'4x':>9}")
    for nm in FEEDS:
        d, day = store[nm]
        for lab, sel in (("research", 0), ("locked", 1)):
            t = keep[nm]
            r, lk, _ = V.split(t)
            tt = r if lab == "research" else lk
            g = V.stats(tt, "gross_pct")
            n_ = V.stats(tt, "pct")
            mult = {}
            for m in (0.0, 2.0, 4.0):
                tm = V.walk(d, day, k=0.4, cost_pts=V.RT[nm] * m, amb_mode=AMB)
                rr, ll, _ = V.split(tm)
                mult[m] = V.stats(rr if lab == "research" else ll)["mean"]
            print(f"  {nm:<8}{lab:<10}{g['pf']:>10.3f}{n_['pf']:>9.3f}{g['mean']:>+10.4f}"
                  f"{n_['mean']:>+10.4f}{tt.cost_frac.median():>11.4f}"
                  f"{mult[0.0]:>+9.4f}{mult[2.0]:>+9.4f}{mult[4.0]:>+9.4f}")
        print()

    # ------------------------------------------------------------------ V1.4 sides and exits
    hdr("V1.4  WHERE THE MONEY COMES FROM -- side, exit reason, and the drift check")
    print(f"  {'feed':<8}{'block':<10}{'cut':<12}{'n':>6}{'win':>8}{'PF':>8}{'%/trade':>10}{'total%':>10}")
    for nm in FEEDS:
        t = keep[nm]
        r, lk, _ = V.split(t)
        for lab, tt in (("research", r), ("locked", lk)):
            for cn, sub in (("LONG", tt[tt.side == 1]), ("SHORT", tt[tt.side == -1]),
                            ("exit=stop", tt[tt.why == "stop"]), ("exit=close", tt[tt.why == "close"])):
                s = V.stats(sub)
                print(f"  {nm:<8}{lab:<10}{cn:<12}{s['n']:>6}{s['win']:>8.3f}{s['pf']:>8.3f}"
                      f"{s['mean']:>+10.4f}{s['total']:>+10.2f}")
            print()

    # ------------------------------------------------------------------ V1.5 concurrency
    hdr("V1.5  CONCURRENCY -- the article allows two live trades per market per day")
    for nm in FEEDS:
        t = keep[nm]
        g = t.groupby("sess").size()
        ov = t.groupby("sess").apply(
            lambda v: int(len(v) == 2 and v.exbar.min() > v.bar.max()), include_groups=False)
        print(f"  {nm:<8}sessions traded {len(g):>5}   two trades {int((g == 2).sum()):>5} "
              f"({(g == 2).mean():.3f})   BOTH LIVE AT ONCE {int(ov.sum()):>5} ({ov.mean():.3f})")
    print("\n  Two live positions on the same index is 2x the stated risk on those days. The")
    print("  article's '0.66% max per market per day' assumes exactly this and is correct.")


if __name__ == "__main__":
    main()
