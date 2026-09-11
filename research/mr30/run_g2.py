"""WHERE DOES US30'S RETURN ACTUALLY LIVE? The overnight premium, with zero fitted parameters.

`run_g0` and `run_g1` closed the displacement family in both directions: the fade is negative in
every declared cell before any barrier with its own conditioning variable inverted, and the mirror
beats drift on BOTH sides on research (+0.077 / +0.078 ATR excess) and INVERTS on both
(-0.065 / -0.073) on the holdout. Neither direction survives; the 2023-25 regime that closed the
DL50 arm closes this one too.

PHASE 0 FOR THE NEXT PRIMARY. The overnight return premium is the one equity-index mechanism that
names its counterparty without any fitting: participants who will not carry inventory through the
illiquid session close out into the bell, and whoever holds it overnight is paid to bear gap risk
they cannot hedge cheaply. RISK TRANSFER again -- so negative skew is the product, not a defect.
It has ZERO tuned numbers: the session boundaries are exchange facts, the side is long by
construction, and there is nothing to search. That is the whole reason to run it here -- every US30
primary this branch has killed carried between four and ten fitted thresholds.

`STUDY_V47` tested it on NQ's three years and found intraday contributed MORE in total (+0.357 vs
+0.292 log) with overnight winning only risk-adjusted, by 0.07 Sharpe. US30 has NINE years and a
different index, and the ISO feed gives a reserved forward block from a different provider.

The table that decides it needs no strategy at all: split every session's return into its parts and
read what each part paid, with a day-block bootstrap and the cost of actually capturing it.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mr30 import mr30core as M  # noqa: E402

RTH0, RTH1 = 570, 960          # 09:30 and 16:00 New York


def sessions(f):
    """Per NY calendar day: the overnight leg (prior session's last RTH close -> this session's
    first RTH open) and the intraday leg (first RTH open -> last RTH close). All in percent."""
    g = f.copy()
    g["day"] = g.index.normalize()
    rth = g[(g["mod"] >= RTH0) & (g["mod"] < RTH1)]
    op = rth.groupby("day")["open"].first()
    cl = rth.groupby("day")["close"].last()
    nb = rth.groupby("day").size()
    d = pd.DataFrame(dict(op=op, cl=cl, nbars=nb)).dropna()
    d = d[d.nbars >= 20]                       # drop half days and broken sessions
    d["prev_cl"] = d["cl"].shift(1)
    d["gap_days"] = d.index.to_series().diff().dt.days
    d = d.dropna()
    d["overnight"] = 100.0 * (d.op - d.prev_cl) / d.prev_cl
    d["intraday"] = 100.0 * (d.cl - d.op) / d.op
    d["session"] = d.overnight + d.intraday
    return d


def boot(x, n=4000, seed=1):
    rng = np.random.default_rng(seed)
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    m = np.array([x[rng.integers(0, len(x), len(x))].mean() for _ in range(n)])
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5)), float((m <= 0).mean())


def report(nm, x, cost_pct):
    lo, hi, p0 = boot(x)
    sh = x.mean() / x.std(ddof=1) * np.sqrt(252) if x.std(ddof=1) > 0 else np.nan
    net = x.mean() - cost_pct
    print(f"  {nm:<14}{len(x):>6}{x.mean():>10.4f}{net:>10.4f}{x.std(ddof=1):>9.3f}"
          f"{sh:>8.2f}{np.mean(x > 0):>8.3f}{f'[{lo:+.4f},{hi:+.4f}]':>22}{p0:>8.3f}"
          f"{pd.Series(x).skew():>8.2f}")


def main():
    print("US30 SESSION DECOMPOSITION -- no parameters, no search, no side to choose.")
    for feed, lab in (("US30L", "US30L 2016-2025"), ("US30I", "US30_ISO forward")):
        f = M.load(feed)
        d = sessions(f)
        blk = M.blocks(f, feed)
        cost_pct = 100.0 * M.COST / float(f["close"].median())
        print(f"\n{lab}: {len(d)} sessions, {d.index[0].date()} .. {d.index[-1].date()}, "
              f"one round turn = {cost_pct:.4f}% of price")
        for bn, mask in blk.items():
            dd = d[(d.index >= f.index[mask][0]) & (d.index <= f.index[mask][-1])]
            if len(dd) < 60:
                continue
            print(f"\n  block {bn}  ({len(dd)} sessions)")
            print(f"  {'leg':<14}{'n':>6}{'mean %':>10}{'net %':>10}{'sd':>9}"
                  f"{'Sharpe':>8}{'win':>8}{'95% CI':>22}{'P(<=0)':>8}{'skew':>8}")
            for leg in ("overnight", "intraday", "session"):
                report(leg, dd[leg].to_numpy(), cost_pct)

    print("\nTHE SHARE OF THE WHOLE MOVE EACH LEG SUPPLIED (sum of log legs, US30L):")
    f = M.load("US30L"); d = sessions(f); blk = M.blocks(f)
    for bn, mask in blk.items():
        dd = d[(d.index >= f.index[mask][0]) & (d.index <= f.index[mask][-1])]
        on = np.log1p(dd.overnight / 100).sum(); it = np.log1p(dd.intraday / 100).sum()
        print(f"  {bn:<12} overnight {on:+.4f}   intraday {it:+.4f}   total {on + it:+.4f}"
              f"   overnight share {on / (on + it):>6.1%}")

    print("\nBY HOUR OF THE NEW YORK DAY (mean 15m return in bp, US30L research block only):")
    blkm = M.blocks(f)["A_research"]
    g = f[blkm].copy()
    r = 1e4 * g["close"].pct_change()
    hh = (g["mod"] // 60).to_numpy()
    tab = pd.DataFrame(dict(h=hh, r=r.to_numpy())).dropna().groupby("h").r.agg(["mean", "count"])
    for h, row in tab.iterrows():
        bar = "#" * int(max(0, round(row["mean"] * 4)))
        print(f"  {int(h):02d}:00  {row['mean']:>8.3f} bp  n={int(row['count']):>6}  {bar}")


if __name__ == "__main__":
    main()
