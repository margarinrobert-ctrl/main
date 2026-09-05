"""The frozen baseline: the original Turtle system, in-sample only. NO parameters are searched.

The out-of-sample tail is NOT read here. `run_oos.py` reads it once, after the rules are frozen.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/turtle2")
import daily, original, equity, tstats as metrics

# Half-spread + commission per side, in basis points of price. BTC's is the published Binance
# taker fee (0.10%/side) plus 1bp of spread and is the only one here that is not an assumption.
COST_BP = {"XAUUSD": 0.9, "EURUSD": 0.7, "BTC": 11.0, "US30": 0.35, "US100": 0.45}
# Stop orders are marketable and slip. Applied to every fill, because every Turtle order is a stop.
SLIP_BP = {"XAUUSD": 1.0, "EURUSD": 0.7, "BTC": 3.0, "US30": 0.5, "US100": 0.6}


def market_trades(market, system, block="is", cost_mult=1.0, use_skip=True,
                  allow_long=True, allow_short=True):
    b = daily.load(market)
    cut, _ = daily.split(b)
    ch = original.channels(b["h"], b["l"], b["c"])
    lo_in, hi_in = ("lo20", "hi20") if system == 1 else ("lo55", "hi55")
    lo_out, hi_out = ("lo10", "hi10") if system == 1 else ("lo20", "hi20")
    pw = original.shadow_ledger(b["h"], b["l"], ch["hi20"], ch["lo20"],
                                ch["hi10"], ch["lo10"], ch["N"])
    sl = slice(0, cut) if block == "is" else slice(cut, b["n"])
    off = 0 if block == "is" else cut
    args = [b["o"][sl], b["h"][sl], b["l"][sl], b["c"][sl],
            b["start"][sl] , b["end"][sl], b["io"], b["ih"], b["il"], b["ic"],
            ch[hi_in][sl], ch[lo_in][sl], ch[hi_out][sl], ch[lo_out][sl],
            ch["N"][sl], pw[sl], system, use_skip, allow_long, allow_short,
            COST_BP[market] * cost_mult, SLIP_BP[market] * cost_mult]
    res = original.run(*args)
    return equity.unit_events(res, market, system, b["date"][sl])


def portfolio(system=None, block="is", cost_mult=1.0, **kw):
    trades = []
    systems = (1, 2) if system is None else (system,)
    for m in daily.MARKETS:
        for s in systems:
            trades += market_trades(m, s, block=block, cost_mult=cost_mult, **kw)
    return equity.replay(trades)


def report(block="is", cost_mult=1.0):
    tag = "IN-SAMPLE" if block == "is" else "OUT-OF-SAMPLE"
    print(f"\n{'='*78}\n{tag}   cost x{cost_mult:g}\n{'='*78}")
    for s, name in ((1, "SYSTEM 1  (20-day breakout, 10-day exit, skip rule)"),
                    (2, "SYSTEM 2  (55-day breakout, 20-day exit, always taken)"),
                    (None, "BOTH SYSTEMS COMBINED")):
        df = portfolio(system=s, block=block, cost_mult=cost_mult)
        print(f"\n{name}")
        metrics.show(metrics.suite(df, label=name))
    return portfolio(system=None, block=block, cost_mult=cost_mult)


def by_market(block="is", cost_mult=1.0):
    print(f"\n{'market':<9}{'class':<8}{'n':>6}{'win%':>7}{'E[R]':>9}{'net $':>13}"
          f"{'PF':>7}{'long$':>12}{'short$':>12}{'amb%':>7}")
    for m in daily.MARKETS:
        tr = []
        for s in (1, 2):
            tr += market_trades(m, s, block=block, cost_mult=cost_mult)
        df = equity.replay(tr)
        st = metrics.suite(df)
        if st is None:
            print(f"{m:<9}  no trades"); continue
        print(f"{m:<9}{daily.ASSET_CLASS[m]:<8}{st['n']:>6}{st['win_pct']:>7.1f}"
              f"{st['expectancy_R']:>+9.3f}{st['long_pnl']+st['short_pnl']:>13,.0f}"
              f"{st['pf']:>7.2f}{st['long_pnl']:>12,.0f}{st['short_pnl']:>12,.0f}"
              f"{st['ambiguous_pct']:>7.2f}")


if __name__ == "__main__":
    print("MARKETS"); daily.inventory()
    report(block="is")
    print("\nBY MARKET (in-sample, both systems)"); by_market(block="is")
