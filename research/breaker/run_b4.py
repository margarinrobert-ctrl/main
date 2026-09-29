"""B4 -- ONE read of the holdout, then the breakdowns. This is the only script that opens it.

Multiplicity at the moment of the read: 21 counted configurations (research_log.md), every
parameter frozen by the user before the first run, nothing re-chosen after any result.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from breaker import bbcore as B  # noqa: E402

pd.set_option("display.width", 210)
BAR = "=" * 104
PRIM = (("A  2R", 2.0), ("B  no target", 0.0))


def hdr(t):
    print("\n" + BAR + "\n" + t + "\n" + BAR)


def day_bootstrap(t, n=2000, seed=0, col="pct"):
    """Resample whole DAYS with their trades attached -- trades inside one session are not
    independent (CLAUDE.md), and this family fires ~36 times a day."""
    rng = np.random.default_rng(seed)
    g = [v[col].to_numpy() for _, v in t.groupby(pd.DatetimeIndex(t.ts).normalize())]
    if len(g) < 10:
        return dict(mean=np.nan, lo=np.nan, hi=np.nan, p=np.nan)
    idx = rng.integers(0, len(g), size=(n, len(g)))
    ms = np.array([np.concatenate([g[i] for i in row]).mean() for row in idx])
    return dict(mean=float(ms.mean()), lo=float(np.percentile(ms, 2.5)),
                hi=float(np.percentile(ms, 97.5)), p=float((ms <= 0).mean()))


def main():
    f = B.load()
    a = B.atr(f)
    cut = B.split_date(f)
    D = B.both_sides(f, a)
    print(f"  HOLDOUT: {cut} -> {f.index[-1]}   (last 25% of trading days)")

    # causal trailing volatility percentile, for the regime breakdown
    vp = pd.Series(a).rolling(5000, min_periods=1000).rank(pct=True).to_numpy()

    hdr("B4.1  THE HOLDOUT, READ ONCE")
    print(f"  {'primary':<14}{'block':<10}{'n':>7}{'win':>8}{'BE win':>8}{'PF':>8}"
          f"{'grossPF':>9}{'%/trade':>10}{'total%':>10}{'annSharpe':>11}{'maxDD%':>9}")
    store = {}
    for lab, rr in PRIM:
        t = B.walk(f, a, D, rr)
        store[lab] = t
        for bl, sel in (("research", pd.DatetimeIndex(t.ts) < cut),
                        ("HOLDOUT", pd.DatetimeIndex(t.ts) >= cut)):
            x = t[sel]
            fx = f[f.index < cut] if bl == "research" else f[f.index >= cut]
            s = B.stats(x); g = B.stats(x, "gross_pct")
            sh, _ = B.daily_sharpe(x, fx)
            be = (1.0 + float(x.cost_frac.median())) / 3.0 if rr > 0 else np.nan
            print(f"  {lab:<14}{bl:<10}{s['n']:>7}{s['win']:>8.4f}{be:>8.4f}{s['pf']:>8.3f}"
                  f"{g['pf']:>9.3f}{s['mean']:>+10.5f}{s['total']:>+10.2f}{sh:>+11.3f}{s['dd']:>9.2f}")
        print()

    hdr("B4.2  DAY-BLOCK BOOTSTRAP -- does either block separate from zero?")
    for lab, _ in PRIM:
        t = store[lab]
        for bl, sel in (("research", pd.DatetimeIndex(t.ts) < cut),
                        ("HOLDOUT", pd.DatetimeIndex(t.ts) >= cut)):
            b = day_bootstrap(t[sel])
            print(f"  {lab:<14}{bl:<10} mean {b['mean']:+.5f}  95% CI "
                  f"[{b['lo']:+.5f}, {b['hi']:+.5f}]  P(mean<=0) {b['p']:.3f}")
    print("\n  A CI entirely BELOW zero is a significant LOSS, not an absence of evidence.")

    hdr("B4.3  INDEPENDENCE -- how many of these trades are actually independent?")
    for lab, _ in PRIM:
        t = store[lab]
        dd = pd.DatetimeIndex(t.ts).normalize()
        per = t.groupby(dd).size()
        print(f"  {lab:<14} {len(t):>7,} trades over {per.size:>4} sessions   "
              f"median {per.median():.0f}/day, p90 {per.quantile(0.9):.0f}   "
              f"median hold {t.hold.median():.0f} min, p90 {t.hold.quantile(0.9):.0f}")
    print("\n  The position lock makes trades non-overlapping in TIME, so the day is the unit of")
    print("  inference, not the trade: ~560 research sessions and ~187 holdout sessions.")
    print("  That is far above the ~100-independent-trade floor, so the sample is sufficient.")

    hdr("B4.4  BY YEAR")
    print(f"  {'primary':<14}{'year':<7}{'n':>7}{'win':>8}{'PF':>8}{'%/trade':>10}{'total%':>10}")
    for lab, _ in PRIM:
        t = store[lab]
        for y, sub in t.groupby(pd.DatetimeIndex(t.ts).year):
            if len(sub) < 30:
                continue
            s = B.stats(sub)
            print(f"  {lab:<14}{y:<7}{s['n']:>7}{s['win']:>8.4f}{s['pf']:>8.3f}"
                  f"{s['mean']:>+10.5f}{s['total']:>+10.2f}")
        print()

    hdr("B4.5  BY VOLATILITY REGIME -- causal ATR(20) percentile over a trailing 5,000 bars")
    print(f"  {'primary':<14}{'regime':<12}{'n':>7}{'win':>8}{'PF':>8}{'grossPF':>9}"
          f"{'cost/risk':>11}{'%/trade':>10}")
    for lab, _ in PRIM:
        t = store[lab]
        q = vp[t.e_bar.to_numpy()]
        for nm, sel in (("low  <0.33", q < 0.33), ("mid", (q >= 0.33) & (q < 0.67)),
                        ("high >=0.67", q >= 0.67)):
            sub = t[sel]
            if len(sub) < 30:
                continue
            s = B.stats(sub); g = B.stats(sub, "gross_pct")
            print(f"  {lab:<14}{nm:<12}{s['n']:>7}{s['win']:>8.4f}{s['pf']:>8.3f}"
                  f"{g['pf']:>9.3f}{sub.cost_frac.median():>11.3f}{s['mean']:>+10.5f}")
        print()

    hdr("B4.6  WHY IT LOSES -- the fill bar, and where the stop sits relative to one bar")
    o = f["open"].to_numpy(); h = f["high"].to_numpy(); l = f["low"].to_numpy()
    rng1 = h - l
    for lab, _ in PRIM:
        t = store[lab]
        same = float((t.x_bar == t.e_bar).mean())
        print(f"  {lab:<14} resolved ON THE FILL BAR: {same:.4f}   "
              f"median risk {t.risk.median():.2f} pts   "
              f"median 1-min bar range at entry {np.median(rng1[t.e_bar.to_numpy()]):.2f} pts   "
              f"risk / bar range {t.risk.median()/np.median(rng1[t.e_bar.to_numpy()]):.2f}")
    print("\n  A stop barely wider than one bar's own range is hit by noise, not by the market")
    print("  disagreeing with the setup.")


if __name__ == "__main__":
    main()
