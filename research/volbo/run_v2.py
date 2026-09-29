"""V2 -- settle the intrabar tie-break on TRUE 1-MINUTE data instead of choosing a convention.

The rule's stop sits 0.4 x a DAILY ATR from the entry, which is wide -- but the entry bar can
still span it, and on the SESSION'S FIRST BAR the stop is the bar's own open, so `low <= stop`
holds with probability 1 and carries no information. Blanket pessimism therefore destroys an
eighth of the sample for an arithmetic reason.

NQ_1m is the only feed here fine enough to answer it. Same instrument family, same rule, same
sessions: run it at ONE MINUTE, then resample THOSE BARS to fifteen minutes and run the three
conventions against it. Whichever 15m convention reproduces the 1-minute answer is the one the
US100 and US30 studies should use. `STUDY_V10_LIMIT` and `STUDY_ATME_LIVE` are the precedent --
any barrier pair that can fall inside one bar has to be walked finer before its number means
anything.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from volbo import vbcore as V  # noqa: E402

pd.set_option("display.width", 220)
BAR = "=" * 112


def hdr(t):
    print("\n" + BAR + "\n" + t + "\n" + BAR)


RT_NQ = 1.72


def main():
    n1 = V.load_nq1m(1)
    n15 = V.load_nq1m(15)
    # the DAILY frame must be identical for both, or the levels differ and nothing is comparable
    day = V.daily_atr(n1)
    print(f"  NQ 1m {len(n1):,} RTH bars / {n1.sess.nunique()} sessions   "
          f"{str(n1.index[0])[:10]} -> {str(n1.index[-1])[:10]}   median ATR5 {day.atr_sma.median():.1f}")

    hdr("V2.0  THE AMBIGUOUS SHARE AT BOTH RESOLUTIONS")
    print("  If a 1-minute bar still shows a large ambiguous share the question is not resolvable")
    print("  here either, and everything downstream is a statement about the convention.\n")
    print(f"  {'bars':<8}{'n':>6}{'first-bar entries':>20}{'amb ALL':>10}{'amb | first':>13}"
          f"{'amb | later':>13}{'bar range / risk':>18}")
    for lab, d in (("1m", n1), ("15m", n15)):
        t = V.walk(d, day, k=0.4, cost_pts=RT_NQ, amb_mode="stop")
        h = d["high"].to_numpy(); lo = d["low"].to_numpy()
        rr = float(np.median((h[t.bar.to_numpy()] - lo[t.bar.to_numpy()]) / t.risk.to_numpy()))
        f0 = t.barno == 0
        print(f"  {lab:<8}{len(t):>6}{f0.mean():>20.3f}{t.amb.mean():>10.3f}"
              f"{t[f0].amb.mean():>13.3f}{t[~f0].amb.mean():>13.3f}{rr:>18.3f}")

    hdr("V2.1  THE SAME RULE, THREE CONVENTIONS AT 15m, AGAINST THE 1-MINUTE TRUTH")
    print("  'stop'      -- every entry-bar stop touch is a full loss (blanket pessimism)")
    print("  'skipfirst' -- pessimistic EXCEPT on the session's first bar, where it is structural")
    print("  'close'     -- the entry bar can never stop out (blanket optimism)\n")
    print(f"  {'bars':<7}{'mode':<12}{'n':>6}{'win':>8}{'PF':>8}{'%/trade':>10}{'total%':>10}"
          f"{'stops':>8}{'vs 1m':>10}")
    ref = V.walk(n1, day, k=0.4, cost_pts=RT_NQ, amb_mode="stop")
    rs = V.stats(ref)
    print(f"  {'1m':<7}{'TRUE PATH':<12}{rs['n']:>6}{rs['win']:>8.3f}{rs['pf']:>8.3f}"
          f"{rs['mean']:>+10.4f}{rs['total']:>+10.2f}{(ref.why=='stop').mean():>8.3f}{'--':>10}")
    best = None
    for mode in ("stop", "skipfirst", "close"):
        t = V.walk(n15, day, k=0.4, cost_pts=RT_NQ, amb_mode=mode)
        s = V.stats(t)
        gap = s["mean"] - rs["mean"]
        print(f"  {'15m':<7}{mode:<12}{s['n']:>6}{s['win']:>8.3f}{s['pf']:>8.3f}"
              f"{s['mean']:>+10.4f}{s['total']:>+10.2f}{(t.why=='stop').mean():>8.3f}{gap:>+10.4f}")
        if best is None or abs(gap) < abs(best[1]):
            best = (mode, gap)
    print(f"\n  CLOSEST TO THE 1-MINUTE TRUTH: '{best[0]}'  (gap {best[1]:+.4f} %/trade)")

    hdr("V2.2  TRADE-FOR-TRADE -- do the two resolutions agree on the SAME trades?")
    print("  A per-trade correlation says whether 15m is a coarse view of the same strategy or a")
    print("  different one. Matched on (session, side).\n")
    for mode in ("stop", "skipfirst", "close"):
        t = V.walk(n15, day, k=0.4, cost_pts=RT_NQ, amb_mode=mode)
        m = ref.merge(t, on=["sess", "side"], suffixes=("_1", "_15"))
        if len(m) < 10:
            continue
        agree = float((m.why_1 == m.why_15).mean())
        corr = float(np.corrcoef(m.pct_1, m.pct_15)[0, 1])
        print(f"  {mode:<12}matched {len(m):>5}/{len(ref)}   same exit reason {agree:>6.3f}   "
              f"per-trade corr {corr:>7.4f}   mean 15m-1m {m.pct_15.mean()-m.pct_1.mean():>+8.4f}")

    hdr("V2.3  AND THE VERDICT ON NQ ITSELF, on the true path")
    po, be = V.payoff_breakeven(ref)
    print(f"  NQ 1-minute, 0.4 x ATR(5), 765 sessions 2022-12 -> 2025-12")
    print(f"    n {rs['n']}   win {rs['win']:.3f} against a payoff-implied break-even of {be:.3f}")
    print(f"    PF {rs['pf']:.3f}   {rs['mean']:+.4f} %/trade   total {rs['total']:+.2f}%   "
          f"Sharpe {rs['sharpe']:+.3f}")
    g = V.stats(ref, "gross_pct")
    print(f"    GROSS PF {g['pf']:.3f}  {g['mean']:+.4f} %/trade   cost/risk {ref.cost_frac.median():.4f}")
    for cn, sub in (("LONG", ref[ref.side == 1]), ("SHORT", ref[ref.side == -1])):
        s = V.stats(sub)
        print(f"    {cn:<6} n {s['n']:>5}  win {s['win']:.3f}  PF {s['pf']:.3f}  {s['mean']:+.4f} %/trade")


if __name__ == "__main__":
    main()
