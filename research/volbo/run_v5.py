"""V5 -- the account translation, the two-market book, and ONE read of the reserved forward block.

The article claims 27%/yr, -32% max drawdown and Sharpe 1.04 at 0.33% risk per trade over six
markets from 2018. That is a PORTFOLIO number on SPY/IWM/QQQ/GLD/USO/DIA, two of which are not
equities at all, and it cannot be reproduced from two correlated equity indices. What CAN be
checked is what the same sizing rule delivers on the feeds that exist here -- and whether the
mechanism survives on a provider that had no part in anything above.

US30_ISO_15m is a DIFFERENT PROVIDER over 2024-08..2026-08. It is the closest thing to reserved on
this branch (STUDY_VWAP_EMA_INDICES and STUDY_IB_US30_OPTUNA have each read it once), and it is
read ONCE here, last, with the multiplicity stated.
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
RISK = 0.0033          # the article's 0.33% of account per trade


def hdr(t):
    print("\n" + BAR + "\n" + t + "\n" + BAR)


def account(t, sessions, risk=RISK):
    """Compound the account at a fixed fraction of equity risked per trade.

    Each trade returns risk * R of the account, where R is the trade's result in units of its own
    initial stop distance -- which is what "risk 0.33% per trade" means.
    """
    daily = t.groupby("sess").R.sum().reindex(sessions).fillna(0.0)
    eq = np.cumprod(1.0 + risk * daily.to_numpy())
    yrs = len(sessions) / 252.0
    cagr = eq[-1] ** (1.0 / yrs) - 1.0
    peak = np.maximum.accumulate(eq)
    dd = float(np.max(1.0 - eq / peak))
    dr = risk * daily.to_numpy()
    sh = float(dr.mean() / max(dr.std(ddof=1), 1e-12) * np.sqrt(252))
    return dict(cagr=cagr, dd=dd, sharpe=sh, final=eq[-1], yrs=yrs, daily=daily)


def main():
    books = {}
    for nm in ("US100L", "US30L"):
        d = V.load(nm); day = V.daily_atr(d)
        t = V.walk(d, day, k=0.4, cost_pts=V.RT[nm], amb_mode=AMB)
        sess = np.sort(d.sess.unique())
        books[nm] = (t, sess, d, day)

    hdr("V5.1  THE ACCOUNT AT 0.33% RISK PER TRADE -- the article's own sizing")
    print("  The article: 27%/yr, -32% max drawdown, Sharpe 1.04, on SIX markets from 2018.")
    print("  Two correlated equity indices cannot reproduce a six-market portfolio number; this is")
    print("  what the same sizing rule delivers on what is here.\n")
    print(f"  {'feed':<10}{'block':<10}{'years':>7}{'trades/yr':>11}{'R/trade':>10}"
          f"{'CAGR':>9}{'maxDD':>9}{'Sharpe':>9}")
    for nm, (t, sess, d, day) in books.items():
        r, lk, cut = V.split(t)
        for lab, tt, ss in (("research", r, sess[sess < cut]), ("locked", lk, sess[sess >= cut]),
                            ("ALL", t, sess)):
            a = account(tt, ss)
            print(f"  {nm:<10}{lab:<10}{a['yrs']:>7.1f}{len(tt)/a['yrs']:>11.1f}"
                  f"{tt.R.mean():>+10.4f}{100*a['cagr']:>+8.2f}%{100*a['dd']:>8.2f}%"
                  f"{a['sharpe']:>+9.3f}")
        print()

    hdr("V5.2  THE TWO-MARKET BOOK -- and how little diversification two equity indices buy")
    (t1, s1, _, _), (t2, s2, _, _) = books["US100L"], books["US30L"]
    allsess = np.array(sorted(set(s1) | set(s2)))
    d1 = t1.groupby("sess").R.sum().reindex(allsess).fillna(0.0)
    d2 = t2.groupby("sess").R.sum().reindex(allsess).fillna(0.0)
    both = (d1 + d2)
    print(f"  daily R correlation between the two legs: {d1.corr(d2):+.3f}")
    print(f"  (the article's six markets include GLD and USO, which this cannot represent)\n")
    print(f"  {'arm':<22}{'years':>7}{'CAGR':>9}{'maxDD':>9}{'Sharpe':>9}{'ret/DD':>9}")
    for an, series in (("US100 alone", d1), ("US30 alone", d2), ("both, 0.33% each", both)):
        dr = RISK * series.to_numpy()
        eq = np.cumprod(1.0 + dr)
        yrs = len(series) / 252.0
        peak = np.maximum.accumulate(eq)
        dd = float(np.max(1.0 - eq / peak))
        cagr = eq[-1] ** (1.0 / yrs) - 1.0
        sh = float(dr.mean() / max(dr.std(ddof=1), 1e-12) * np.sqrt(252))
        print(f"  {an:<22}{yrs:>7.1f}{100*cagr:>+8.2f}%{100*dd:>8.2f}%{sh:>+9.3f}"
              f"{cagr/max(dd,1e-9):>9.2f}")

    hdr("V5.3  ONE READ OF THE RESERVED FORWARD BLOCK -- US30_ISO, a DIFFERENT PROVIDER")
    print("  2024-08 .. 2026-08. Nothing in this study was chosen on it. Multiplicity: the rule was")
    print("  published, not fitted here; the only choice made was the intrabar convention, and that")
    print("  was settled on NQ 1-minute data, not on this block.\n")
    di = V.load("US30I"); dayi = V.daily_atr(di)
    ti = V.walk(di, dayi, k=0.4, cost_pts=V.RT["US30I"], amb_mode=AMB)
    si = np.sort(di.sess.unique())
    s = V.stats(ti); po, be = V.payoff_breakeven(ti)
    g = V.stats(ti, "gross_pct")
    print(f"  sessions {len(si)}   trades {s['n']}   win {s['win']:.3f} against a payoff-implied "
          f"break-even of {be:.3f}")
    print(f"  PF {s['pf']:.3f} (gross {g['pf']:.3f})   {s['mean']:+.4f} %/trade   "
          f"total {s['total']:+.2f}%   Sharpe {s['sharpe']:+.3f}")
    a = account(ti, si)
    print(f"  at 0.33% risk: CAGR {100*a['cagr']:+.2f}%   maxDD {100*a['dd']:.2f}%   "
          f"Sharpe {a['sharpe']:+.3f}   over {a['yrs']:.1f} years")
    b = V.day_bootstrap(ti)
    print(f"  day-block bootstrap: mean {b['mean']:+.4f}  CI [{b['lo']:+.4f}, {b['hi']:+.4f}]  "
          f"P(mean<=0) {b['p']:.3f}")
    for cn, sub in (("LONG", ti[ti.side == 1]), ("SHORT", ti[ti.side == -1])):
        ss = V.stats(sub)
        print(f"    {cn:<6} n {ss['n']:>4}  win {ss['win']:.3f}  PF {ss['pf']:.3f}  "
              f"{ss['mean']:+.4f} %/trade")
    gi = di.groupby("sess").agg(o=("open", "first"), c=("close", "last"))
    gi["pct"] = 100.0 * (gi["c"] - gi["o"]) / gi["o"]
    print(f"  ALWAYS-IN on the same block: {gi['pct'].mean():+.4f} %/session, "
          f"total {gi['pct'].sum():+.2f}%")
    pnl = ti.groupby("sess").pct.sum().reindex(si).fillna(0.0)
    print(f"  the rule, zero-filled:       {pnl.mean():+.4f} %/session, "
          f"total {pnl.sum():+.2f}%")
    # the feasible null on the forward block
    from volbo.run_v4 import post_break
    obs = float(ti.pct.mean())
    n1b = np.array([post_break(di, dayi, ti, 0.4, V.RT["US30I"], sd).mean() for sd in range(400)])
    print(f"  N1b feasible null: median {np.median(n1b):+.4f}   "
          f"p {(n1b >= obs).mean():.3f}")


if __name__ == "__main__":
    main()
