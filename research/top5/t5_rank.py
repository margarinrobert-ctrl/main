"""Rank every candidate strategy on this branch, on the SELECTION block only.

THE UNIT. Points are not comparable across instruments and dollars are not comparable across
contract specifications, so profitability is measured in PERCENT OF ENTRY PRICE. Two summaries
are reported for every feed a strategy runs on:

    pct/trade   how much one unit earns per trade, as a fraction of the price it bought
    %/yr        the sum of that over the block, divided by the block's length in years -- the
                return one unit earns per year, which is the number a trader is actually asking
                about when they say "most profitable"

THE BLOCK. Ranking is done on RESEARCH ONLY. Every one of these strategies has already had its
reserved block read once by the study that built it; ranking on the whole sample would put those
reads inside the selection and the out-of-sample table that follows would mean nothing.

Feeds are equal-weighted. US100 carries nine years and NQ carries two; summing across them would
rank the feed rather than the strategy.
"""
from __future__ import annotations

import sys
import os

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import t5_adapt as A  # noqa: E402

MIN_N = 25


def block_stats(tr, block, sessions):
    t = tr[tr["block"] == block]
    n = len(t)
    if n == 0:
        return dict(n=0)
    p = t["pct"].to_numpy()
    w = p > 0
    span = (t["ts"].max() - t["ts"].min()).days / 365.25
    yrs = max(span, sessions / 252.0) if sessions else max(span, 1e-9)
    eq = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(eq) - eq)) if n else np.nan
    daily = pd.Series(p).groupby(t["sess"].to_numpy()).sum()
    d = np.zeros(max(sessions, len(daily)))
    d[: len(daily)] = daily.to_numpy()
    sh = float(d.mean() / d.std() * np.sqrt(252)) if d.std() > 0 else np.nan
    return dict(n=n, mean=float(p.mean()), total=float(p.sum()), per_yr=float(p.sum() / yrs),
                win=float(w.mean()), pf=float(p[w].sum() / max(1e-9, -p[~w].sum())),
                sharpe=sh, dd=dd, ret_dd=float(p.sum() / dd) if dd and dd > 0 else np.nan,
                yrs=yrs, trades_yr=n / yrs)


def main():
    rows = []
    for name, spec in A.CANDIDATES.items():
        for feed in spec["feeds"]:
            try:
                b = A.bundle(name, feed)
            except Exception as e:                      # a feed a strategy cannot run on
                print(f"  !! {name} {feed}: {type(e).__name__}: {e}")
                continue
            tr, sess = b["tr"], b["sessions"]
            for blk in tr["block"].unique():
                if not blk:
                    continue
                s = block_stats(tr, blk, sess.get(blk, 0))
                s.update(strategy=name, feed=feed, block=blk,
                         selection=(blk == spec["is_block"]))
                rows.append(s)
            print(f"  .. {name:12s} {feed:9s} {len(tr):5d} trades")
    d = pd.DataFrame(rows)
    d.to_csv("results/top5/all_blocks.csv", index=False)

    print("\n" + "=" * 110)
    print("EVERY CANDIDATE, EVERY FEED, EVERY BLOCK -- percent of entry price, one unit")
    print("=" * 110)
    for name in A.CANDIDATES:
        sub = d[d["strategy"] == name]
        print(f"\n{name}  --  {A.CANDIDATES[name]['label']}")
        for _, r in sub.iterrows():
            if r["n"] == 0:
                print(f"    {r['feed']:9s} {r['block']:12s} n 0")
                continue
            tag = "IS " if r["selection"] else "OOS"
            print(f"    {r['feed']:9s} {r['block']:12s} {tag} n {int(r['n']):5d}  "
                  f"pct/trade {r['mean']:+.4f}  %/yr {r['per_yr']:+7.2f}  PF {r['pf']:5.2f}  "
                  f"win {100*r['win']:5.1f}%  Sharpe {r['sharpe']:+5.2f}  "
                  f"maxDD {r['dd']:6.2f}%  ret/DD {r['ret_dd']:5.2f}")

    print("\n" + "=" * 110)
    print("RANKING -- research block only, feeds equal-weighted, a feed needs >= %d trades" % MIN_N)
    print("=" * 110)
    sel = d[d["selection"] & (d["n"] >= MIN_N)]
    g = sel.groupby("strategy").agg(feeds=("feed", "count"), n=("n", "sum"),
                                    per_yr=("per_yr", "mean"), mean=("mean", "mean"),
                                    pf=("pf", "mean"), sharpe=("sharpe", "mean"),
                                    trades_yr=("trades_yr", "mean"))
    g = g.sort_values("per_yr", ascending=False)
    print(f"  {'strategy':14s} {'feeds':>5s} {'trades':>7s} {'%/yr':>8s} {'pct/trade':>10s} "
          f"{'PF':>6s} {'Sharpe':>7s} {'trades/yr':>10s}")
    for name, r in g.iterrows():
        print(f"  {name:14s} {int(r['feeds']):5d} {int(r['n']):7d} {r['per_yr']:+8.2f} "
              f"{r['mean']:+10.4f} {r['pf']:6.2f} {r['sharpe']:+7.2f} {r['trades_yr']:10.1f}")
    g.to_csv("results/top5/ranking.csv")
    print("\n  TOP 5:", ", ".join(list(g.index[:5])))


if __name__ == "__main__":
    main()
