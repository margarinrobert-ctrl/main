"""Frozen baseline, out-of-sample read, cost sensitivity and the market decomposition.

NOTHING IS OPTIMISED ANYWHERE IN THIS FILE. Every parameter is the published Turtle constant. The
out-of-sample block is read exactly once, after the rules were frozen, and is not fed back.

TWO EQUITY VIEWS ARE REPORTED SIDE BY SIDE and they answer different questions:
  COMPOUNDED   the real original: units sized off current equity. Gives CAGR and a true drawdown,
               but over 21 years a trend system's compounding makes dollar figures unreadable.
  FIXED        units sized off the STARTING equity throughout. No CAGR, but expectancy, profit
               factor and the per-trade distribution are then comparable across blocks and markets
               instead of being dominated by wherever the compounding happened to be.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/turtle2")
import daily, equity, tstats as metrics
from run_baseline import market_trades, COST_BP, SLIP_BP


def book(block="is", cost_mult=1.0, systems=(1, 2), markets=None, compound=True):
    tr = []
    for m in (markets or list(daily.MARKETS)):
        for s in systems:
            tr += market_trades(m, s, block=block, cost_mult=cost_mult)
    return equity.replay(tr, compound=compound)


def line(tag, df):
    s = metrics.suite(df)
    if s is None:
        print(f"  {tag:<26} no trades"); return None
    print(f"  {tag:<26}{s['n']:>6}{s['win_pct']:>7.1f}{s['expectancy_R']:>+9.3f}"
          f"{s['pf']:>7.2f}{s['cagr_pct']:>9.1f}{s['max_dd_pct']:>8.1f}"
          f"{s['sharpe']:>7.2f}{s['sortino']:>8.2f}{100*s['top5pct']:>8.1f}")
    return s


HDR = (f"  {'':<26}{'n':>6}{'win%':>7}{'E[R]':>9}{'PF':>7}{'CAGR%':>9}"
       f"{'maxDD%':>8}{'Shrp':>7}{'Sort':>8}{'top5%':>8}")

if __name__ == "__main__":
    print("=" * 96)
    print("ORIGINAL TURTLE -- frozen rules, nothing optimised")
    print("=" * 96)

    for comp, name in ((True, "COMPOUNDED (the real original)"),
                       (False, "FIXED EQUITY (comparable expectancy)")):
        print(f"\n{name}\n{HDR}")
        for blk in ("is", "oos"):
            t = "in-sample" if blk == "is" else "OUT-OF-SAMPLE"
            line(f"S1 only, {t}", book(blk, systems=(1,), compound=comp))
            line(f"S2 only, {t}", book(blk, systems=(2,), compound=comp))
            line(f"both,    {t}", book(blk, compound=comp))

    print("\n\nHOW MUCH OF THIS IS BITCOIN? (both systems, fixed equity)")
    print(HDR)
    allm = list(daily.MARKETS)
    for blk in ("is", "oos"):
        t = "in-sample" if blk == "is" else "OUT-OF-SAMPLE"
        line(f"all 5 markets, {t}", book(blk, compound=False))
        line(f"ex-BTC, {t}", book(blk, markets=[m for m in allm if m != "BTC"], compound=False))

    print("\n\nPER MARKET, OUT-OF-SAMPLE (both systems, fixed equity)")
    print(HDR)
    for m in allm:
        line(f"{m} ({daily.ASSET_CLASS[m]})", book("oos", markets=[m], compound=False))

    print("\n\nCOST SENSITIVITY (both systems, all markets, fixed equity)")
    print(HDR)
    for cm in (0.0, 1.0, 1.5, 2.0, 3.0):
        for blk in ("is", "oos"):
            t = "in-sample" if blk == "is" else "OOS"
            line(f"cost x{cm:g}, {t}", book(blk, cost_mult=cm, compound=False))

    print("\n\nPROFITABLE YEARS AND LONG/SHORT (both systems, fixed equity)")
    for blk in ("is", "oos"):
        s = metrics.suite(book(blk, compound=False))
        t = "in-sample" if blk == "is" else "OUT-OF-SAMPLE"
        print(f"\n  {t}: {s['profitable_years']}/{s['total_years']} profitable years, "
              f"longest losing run {s['longest_losing_streak']}, "
              f"intrabar ambiguous {s['ambiguous_pct']:.2f}%")
        print(f"    long  {s['long_n']:>4} trades  E[R] {s['long_expR']:+.3f}  net ${s['long_pnl']:,.0f}")
        print(f"    short {s['short_n']:>4} trades  E[R] {s['short_expR']:+.3f}  net ${s['short_pnl']:,.0f}")
        print(f"    concentration: top1% {100*s['top1pct']:.1f}%  top5% {100*s['top5pct']:.1f}%  "
              f"top10% {100*s['top10pct']:.1f}%")
