"""The IB-25 retracement priced as MNQ, in dollars.

THE STUDY WAS ALREADY RUN ON MNQ ECONOMICS. This branch's "NQ" cost model uses a point value of
2.0, which IS the Micro E-mini Nasdaq-100 -- the full-size NQ is 20. So the percent-of-price
figures already describe MNQ; what was missing is the dollar view, the account view, and one
caveat that only bites once the answer is denominated in dollars.

THE CAVEAT. `STUDY_US100` established that this branch's NQ price LEVELS are synthetic: the stored
series reads about 25% above the real Nasdaq-100 early in the sample and converges to it late.
Measured here against US100 over 862 overlapping days the ratio runs **1.2563 -> 1.0182**. Percent
of price, R multiples and win rates are unaffected -- but DOLLARS ARE NOT, because a dollar figure
is points x $2 and the stored points are inflated by that same ratio. The inflation is largest
EARLY, which is the research block. Every dollar table below is therefore printed twice: as stored,
and deflated trade-by-trade by the ratio on that trade's own date.
"""
from __future__ import annotations

import os
import sys
import warnings

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "v63"))

import ib25_core as M   # noqa: E402
import v63feeds as FD   # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 240)

# Micro E-mini Nasdaq-100
PV, TICK = 2.0, 0.25            # $ per point, minimum tick in points ($0.50 a tick)
SPREAD_T, SLIP_T = 1.0, 1.0     # ticks a side
FEE_RT = 1.44                   # $ a round turn: CME + NFA + clearing + broker, per STUDY_COSTS

POST = dict(retr=0.25, stop_frac=0.50, slope_win=20, slope_thr=0.0, max_cross=99)
BEST = dict(retr=0.50, stop_frac=0.75, slope_win=60, slope_thr=0.0, max_cross=99)


def line(t):
    print("\n" + "=" * 122)
    print(t)
    print("=" * 122)


def deflator():
    """Stored NQ level / real index level, from the US100 overlap, forward-filled by date."""
    nq = FD.bars("NQ", 15)["close"]
    us = FD.bars("US100", 15)["close"]
    j = pd.concat([nq.rename("nq"), us.rename("us")], axis=1).dropna()
    r = (j["nq"] / j["us"]).resample("D").last().dropna()
    r.index = (r.index.year * 10000 + r.index.month * 100 + r.index.day)
    return r


def dollars(t, defl=None):
    """Per-trade dollars for ONE MNQ contract, optionally deflated to real index points."""
    pts = t["net_pts"].to_numpy().copy()
    if defl is not None:
        f = t["sess"].map(defl).astype(float)
        f = f.fillna(f.median()).to_numpy()
        pts = pts / f
    return pts * PV


def book(t, defl=None, equity0=5000.0):
    if len(t) == 0:
        return dict(n=0)
    d = dollars(t, defl)
    eq = equity0 + np.cumsum(d)
    dd = eq - np.maximum.accumulate(eq)
    g, b = d[d > 0].sum(), -d[d <= 0].sum()
    return dict(n=len(d), per=float(d.mean()), tot=float(d.sum()),
                pf=float(g / b) if b > 0 else np.nan, win=100.0 * float((d > 0).mean()),
                dd=float(dd.min()), best=float(d.max()), worst=float(d.min()),
                end=float(eq[-1]))


if __name__ == "__main__":
    D = M.build("NQ")
    defl = deflator()
    rt_price = 2 * (SPREAD_T + SLIP_T) * TICK * PV      # spread + slippage, both sides, dollars
    rt_all = rt_price + FEE_RT

    line("A. THE CONTRACT, AND WHAT A ROUND TURN COSTS")
    print(f"  Micro E-mini Nasdaq-100 (MNQ): ${PV:.2f} a point, tick {TICK} points = "
          f"${TICK * PV:.2f}, so one tick is ${TICK * PV:.2f} a contract")
    print(f"  assumed price impact  {SPREAD_T:.0f} tick spread + {SLIP_T:.0f} tick slippage a side "
          f"= ${rt_price:.2f} a round turn")
    print(f"  fees                  ${FEE_RT:.2f} a round turn (CME + NFA + clearing + broker)")
    print(f"  TOTAL ROUND TURN      ${rt_all:.2f} per MNQ contract = "
          f"{rt_all / PV:.3f} points")
    print(f"  (the full-size NQ is ${PV*10:.0f} a point, so the same rule on NQ is 10x every dollar")
    print(f"   figure below with a round turn near ${rt_price*10 + 4.0:.0f} -- proportionally cheaper)")

    line("B. THE RULE AS POSTED, IN DOLLARS PER MNQ CONTRACT")
    t = M.run(D, **POST)
    print(f"  {'variant':22s}{'block':10s}{'n':>6s}{'$/trade':>10s}{'total $':>11s}"
          f"{'PF':>8s}{'win %':>8s}{'max DD $':>11s}{'best':>9s}{'worst':>9s}")
    for nm, cfg in (("as posted", POST), ("retr 0.50 / stop 0.75", BEST)):
        tt = M.run(D, **cfg)
        for b in ("research", "locked"):
            s = book(tt[tt["block"] == b])
            print(f"  {nm:22s}{b:10s}{s['n']:>6d}{s['per']:>10.2f}{s['tot']:>11.0f}"
                  f"{s['pf']:>8.3f}{s['win']:>8.1f}{s['dd']:>11.0f}{s['best']:>9.0f}"
                  f"{s['worst']:>9.0f}")

    line("C. THE SAME TABLE DEFLATED -- stored NQ levels run 1.2563 -> 1.0182 above the real index")
    print(f"  {'variant':22s}{'block':10s}{'n':>6s}{'$/trade':>10s}{'stored':>10s}"
          f"{'total $':>11s}{'stored':>11s}{'inflation':>11s}")
    for nm, cfg in (("as posted", POST), ("retr 0.50 / stop 0.75", BEST)):
        tt = M.run(D, **cfg)
        for b in ("research", "locked"):
            g = tt[tt["block"] == b]
            a = book(g, defl)
            r = book(g)
            print(f"  {nm:22s}{b:10s}{a['n']:>6d}{a['per']:>10.2f}{r['per']:>10.2f}"
                  f"{a['tot']:>11.0f}{r['tot']:>11.0f}"
                  f"{100 * (r['tot'] / a['tot'] - 1) if a['tot'] else float('nan'):>10.1f}%")
    print("\n  Percent of price, R and win rate are unaffected by the synthetic levels. Dollars are")
    print("  inflated most on the RESEARCH block, which is the early part of the sample -- so the")
    print("  deflated column is the one to read for an MNQ account.")

    line("D. THE ARITHMETIC THAT DECIDES IT, IN MNQ TERMS")
    for nm, cfg in (("as posted", POST), ("retr 0.50 / stop 0.75", BEST)):
        tt = M.run(D, **cfg)
        g = tt[tt["block"] == "research"]
        risk_pts = g["risk"].median()
        rr = cfg["retr"] / (cfg["stop_frac"] - cfg["retr"])
        gross = M.stats(g)["pts"] + 2 * (D["cost"] + D["tick"])
        print(f"\n  {nm}")
        print(f"    median risk           {risk_pts:.1f} points = ${risk_pts * PV:.2f} a contract")
        print(f"    round turn            {rt_all / PV:.3f} points = ${rt_all:.2f}  "
              f"({100 * (rt_all / PV) / risk_pts:.1f}% of risk)")
        print(f"    reward:risk           {rr:.2f}   driftless break-even win rate "
              f"{100 / (1 + rr):.1f}%   ACTUAL {M.stats(g)['win']:.1f}%")
        print(f"    gross points / trade  {gross:+.3f} = ${gross * PV:+.2f}   "
              f"net ${M.stats(g)['pts'] * PV:+.2f}")
        print(f"    break-even needs the win rate to rise "
              f"{100 / (1 + rr) - M.stats(g)['win']:+.1f} points")

    line("E. AN MNQ ACCOUNT TRADING ONE CONTRACT")
    print(f"  {'variant':22s}{'block':10s}{'trades/yr':>11s}{'$/yr':>9s}{'max DD $':>10s}"
           f"{'DD in contracts':>17s}{'account for 3x DD':>19s}")
    yrs = {"research": 1.919, "locked": 1.038}
    for nm, cfg in (("as posted", POST), ("retr 0.50 / stop 0.75", BEST)):
        tt = M.run(D, **cfg)
        for b in ("research", "locked"):
            s = book(tt[tt["block"] == b], defl)
            y = yrs[b]
            print(f"  {nm:22s}{b:10s}{s['n'] / y:>11.0f}{s['tot'] / y:>9.0f}{s['dd']:>10.0f}"
                  f"{abs(s['dd']) / (2000 * 0.02):>17.1f}{3 * abs(s['dd']):>18.0f}")
    print("\n  'DD in contracts' is the drawdown divided by 2% of a $2,000 micro account, i.e. how")
    print("  many 2%-risk units the drawdown consumes. MNQ day-trade margin is typically $50-100")
    print("  and intraday buying power is not the binding constraint here -- the drawdown is.")

    line("F. COST SENSITIVITY IN TICKS -- how wrong can the fill assumption be?")
    print(f"  {'variant':22s}{'ticks/side':>12s}{'round turn $':>14s}"
          f"{'research $/trade':>18s}{'locked $/trade':>16s}")
    for nm, cfg in (("as posted", POST), ("retr 0.50 / stop 0.75", BEST)):
        for tk in (0.0, 1.0, 2.0, 3.0, 4.0):
            slip = tk * TICK
            tt = M.run(D, cost=FEE_RT / 2 / PV, slip=slip, **cfg)
            r = book(tt[tt["block"] == "research"], defl)
            k = book(tt[tt["block"] == "locked"], defl)
            print(f"  {nm:22s}{tk:>12.0f}{2 * tk * TICK * PV + FEE_RT:>14.2f}"
                  f"{r['per']:>18.2f}{k['per']:>16.2f}")
    print("\n  Zero ticks a side is fees only and is not achievable; it is printed to show what the")
    print("  rule earns with the fill assumption removed entirely.")
