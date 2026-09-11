"""V6 -- year by year, and the ONE enhancement the article names.

The author's own tip: "I incorporate an additional rule to filter trades during periods of low
volatility." That is a single declared condition, so it is tested as one -- an ATR percentile floor
measured causally against the instrument's own trailing history -- on the RESEARCH blocks only,
against a same-selectivity random filter, and NOT re-read on the forward block. One declared test,
one reported number.
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
AMB = "close"


def hdr(t):
    print("\n" + BAR + "\n" + t + "\n" + BAR)


def main():
    hdr("V6.1  YEAR BY YEAR -- is the shape a regime or a market?")
    print(f"  {'year':<7}{'US100 %/tr':>12}{'US100 tot':>11}{'US30 %/tr':>12}{'US30 tot':>11}"
          f"{'US30_ISO':>11}{'NQ 1m':>10}")
    tabs = {}
    for nm in ("US100L", "US30L", "US30I"):
        d = V.load(nm); day = V.daily_atr(d)
        tabs[nm] = V.walk(d, day, k=0.4, cost_pts=V.RT[nm], amb_mode=AMB)
    n1 = V.load_nq1m(1)
    tabs["NQ1m"] = V.walk(n1, V.daily_atr(n1), k=0.4, cost_pts=1.72, amb_mode=AMB)
    yrs = sorted({pd.Timestamp(s).year for t in tabs.values() for s in t.sess})
    for y in yrs:
        row = []
        for nm in ("US100L", "US30L", "US30I", "NQ1m"):
            t = tabs[nm]
            sub = t[[pd.Timestamp(s).year == y for s in t.sess]]
            row.append((sub.pct.mean(), sub.pct.sum(), len(sub)) if len(sub) >= 20
                       else (np.nan, np.nan, len(sub)))
        print(f"  {y:<7}{row[0][0]:>+12.4f}{row[0][1]:>+11.2f}{row[1][0]:>+12.4f}"
              f"{row[1][1]:>+11.2f}{row[2][1]:>+11.2f}{row[3][1]:>+10.2f}")
    print("\n  positive years:", end="")
    for nm, lab in (("US100L", "US100"), ("US30L", "US30"), ("US30I", "US30_ISO"), ("NQ1m", "NQ")):
        t = tabs[nm]
        g = t.groupby([pd.Timestamp(s).year for s in t.sess]).pct.agg(["sum", "count"])
        g = g[g["count"] >= 20]
        print(f"   {lab} {(g['sum'] > 0).sum()}/{len(g)}", end="")
    print()

    hdr("V6.2  THE AUTHOR'S OWN ENHANCEMENT -- a low-volatility filter, one declared test")
    print("  ATR(5) as a percentile of its OWN trailing 250 sessions, known before the open, so it")
    print("  is causal. Each rung against a random filter keeping the same number of SESSIONS,")
    print("  re-simulated end to end (a filter is a VETO, not a subset of realised trades).")
    print("  RESEARCH BLOCKS ONLY. The forward block is not re-opened.\n")
    rng = np.random.default_rng(11)
    print(f"  {'feed':<9}{'rung':<14}{'kept%':>8}{'n':>7}{'%/trade':>10}{'PF':>8}"
          f"{'ctl med':>10}{'p':>8}")
    for nm in ("US100L", "US30L"):
        d = V.load(nm); day = V.daily_atr(d)
        t = V.walk(d, day, k=0.4, cost_pts=V.RT[nm], amb_mode=AMB)
        r, _, cut = V.split(t)
        pr = day["atr_sma"].rolling(250, min_periods=60).rank(pct=True)
        keys = np.array([k for k in day.index if k < cut])
        base = float(r.pct.mean())
        print(f"  {nm:<9}{'no filter':<14}{100.0:>8.1f}{len(r):>7}{base:>+10.4f}"
              f"{V.stats(r)['pf']:>8.3f}{'--':>10}{'--':>8}")
        for q in (0.2, 0.3, 0.4, 0.5):
            ok = set(pr[pr >= q].index)
            sub = r[r.sess.isin(ok)]
            if len(sub) < 30:
                continue
            m = sub.sess.nunique()
            pool = np.array([k for k in keys if k in set(r.sess)])
            draws = []
            for _ in range(400):
                pick = set(rng.choice(pool, size=min(m, len(pool)), replace=False).tolist())
                cc = r[r.sess.isin(pick)]
                if len(cc) >= 20:
                    draws.append(float(cc.pct.mean()))
            draws = np.array(draws)
            obs = float(sub.pct.mean())
            print(f"  {nm:<9}{f'ATR pct>={q:.1f}':<14}{100*len(sub)/len(r):>8.1f}{len(sub):>7}"
                  f"{obs:>+10.4f}{V.stats(sub)['pf']:>8.3f}{np.median(draws):>+10.4f}"
                  f"{(draws >= obs).mean():>8.3f}")
        print()


if __name__ == "__main__":
    main()
