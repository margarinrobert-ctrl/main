"""FTM_OPENING_RANGE_BREAKOUT_MNQ_v1_8_0_ALPHA2 against the RC1 already measured here.

The alpha.2 file keeps the whole 1.4.1-rc.1 parent (admission, direction model, warm-up,
sizing, managed stop, 15:30 rule, 16:00 flatten) and changes the ordered entry policy in two
places: the prior-session-disagreement branch ("H5") observes ONE completed minute instead
of two before flipping, and the intraday-continuation flip ("H2") is capped at one contract.
The direct near-VWAP action and the control action are RC1's. So the test is: the same
one-minute bars, the same simulator, two knobs -- and every difference between the two trade
lists has to come from those knobs.

Same caveats as STUDY_FTM_ORB_BACKTEST: the path is NQ not MNQ, the levels are synthetic
(basis-point features are distorted), the first ~120 eligible sessions cannot trade, and the
15-minute CFD feeds (US30, US100) cannot run a strategy whose opening range, admission test
and refinement observations are all defined on exact one-minute bars.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.ftm import ftm_sim as S                                   # noqa: E402
from research.ftm import ftm_backtest as B                              # noqa: E402

OUT = "results/ftm"
os.makedirs(OUT, exist_ok=True)

VARIANTS = {
    "RC1 (prior 2 bars, no H2 cap)": dict(prior_bars=2, h2_cap=0),
    "H5 only (prior 1 bar)": dict(prior_bars=1, h2_cap=0),
    "H2 cap only (cap 1)": dict(prior_bars=2, h2_cap=1),
    "ALPHA2 (prior 1 bar + H2 cap 1)": dict(prior_bars=1, h2_cap=1),
}


def headline(t):
    if len(t) == 0:
        return dict(n=0)
    eq = t["usd"].cumsum().to_numpy()
    w = t["usd"] > 0
    dd = B.drawdown(eq)
    d = t.set_index("time")["usd"].resample("D").sum()
    d = d[d.index.dayofweek < 5]
    p0, lo, hi = B.boot(t["R"].to_numpy())
    pf = t.loc[w, "usd"].sum() / max(-t.loc[~w, "usd"].sum(), 1e-9)
    return dict(n=len(t), net=t["usd"].sum(), pf=pf, win=w.mean(), R=t["R"].mean(),
    pts=t["pts"].mean(), dd=dd,
                rdd=t["usd"].sum() / max(-dd, 1e-9),
                sharpe=d.mean() / max(d.std(), 1e-9) * np.sqrt(252), p0=p0, lo=lo, hi=hi,
                streak=B.streaks(t["usd"].to_numpy()))


def main():
    print(__doc__)
    f = S.load_nq()
    res = {}
    for name, kw in VARIANTS.items():
        cnt, t = S.run(verbose=False, sizing="FixedDollar", **kw)
        res[name] = (cnt, t)
    print("=" * 100)
    print("FOUR VARIANTS, FixedDollar ($535 risk, cap 2, $50,000), same bars, same parent")
    print("=" * 100)
    print(f"{'variant':<34}{'n':>5}{'net $':>10}{'PF':>7}{'win':>7}{'R':>9}{'maxDD $':>10}"
          f"{'ret/DD':>8}{'Sharpe':>8}{'P(R<=0)':>9}{'streak':>7}")
    for name, (cnt, t) in res.items():
        m = headline(t)
        print(f"{name:<34}{m['n']:>5}{m['net']:>10,.0f}{m['pf']:>7.3f}{m['win']:>7.1%}"
              f"{m['R']:>+9.4f}{m['dd']:>10,.0f}{m['rdd']:>8.2f}{m['sharpe']:>8.2f}"
              f"{m['p0']:>9.3f}{m['streak']:>7}")
    rc1 = res["RC1 (prior 2 bars, no H2 cap)"][1]
    a2 = res["ALPHA2 (prior 1 bar + H2 cap 1)"][1]
    a2.to_csv(f"{OUT}/trades_alpha2.csv", index=False)

    print("\n" + "=" * 100)
    print("WHAT CHANGED, trade by trade (matched on the session date)")
    print("=" * 100)
    rc1["date"] = rc1["time"].dt.normalize(); a2["date"] = a2["time"].dt.normalize()
    m = rc1.merge(a2, on="date", how="outer", suffixes=("_rc1", "_a2"), indicator=True)
    both = m[m["_merge"] == "both"]
    same = both[(both.time_rc1 == both.time_a2) & (both.side_rc1 == both.side_a2)
                & (both.qty_rc1 == both.qty_a2) & np.isclose(both.usd_rc1, both.usd_a2)]
    print(f"  RC1 {len(rc1)} trades, ALPHA2 {len(a2)}; sessions traded by both {len(both)}, "
          f"identical trades {len(same)}, RC1 only {int((m._merge == 'left_only').sum())}, "
          f"ALPHA2 only {int((m._merge == 'right_only').sum())}")
    diff = both[~both.index.isin(same.index)]
    if len(diff):
        print(f"  {len(diff)} sessions traded differently:")
        cols = ["date", "path_rc1", "time_rc1", "side_rc1", "qty_rc1", "usd_rc1",
                "path_a2", "time_a2", "side_a2", "qty_a2", "usd_a2"]
        d = diff[cols].copy()
        d["time_rc1"] = d["time_rc1"].dt.strftime("%H:%M")
        d["time_a2"] = d["time_a2"].dt.strftime("%H:%M")
        d["date"] = d["date"].dt.strftime("%Y-%m-%d")
        print("    " + d.to_string(index=False, float_format=lambda x: f"{x:,.0f}")
              .replace("\n", "\n    "))
        print(f"  net effect of the changed sessions: RC1 ${diff.usd_rc1.sum():,.0f} -> "
              f"ALPHA2 ${diff.usd_a2.sum():,.0f}")
    only_a = m[m._merge == "right_only"]; only_r = m[m._merge == "left_only"]
    if len(only_a):
        print(f"  ALPHA2-only sessions: ${only_a.usd_a2.sum():,.0f} over {len(only_a)}")
    if len(only_r):
        print(f"  RC1-only sessions: ${only_r.usd_rc1.sum():,.0f} over {len(only_r)}")

    print("\n" + "=" * 100)
    print("ALPHA2 BY ACTION, PATH, YEAR, EXIT, SIDE")
    print("=" * 100)
    for col in ("action", "path", "reason", "side"):
        g = a2.groupby(col).agg(n=("usd", "size"), net=("usd", "sum"),
                                win=("usd", lambda x: (x > 0).mean() * 100), R=("R", "mean"),
                                qty=("qty", "mean"))
        print(f"  by {col}:")
        print("    " + g.sort_values("net", ascending=False)
              .to_string(float_format=lambda x: f"{x:,.2f}").replace("\n", "\n    "))
    yr = a2.groupby(a2["time"].dt.year).agg(n=("usd", "size"), net=("usd", "sum"),
                                            win=("usd", lambda x: (x > 0).mean() * 100),
                                            R=("R", "mean"))
    print("  by year:")
    print("    " + yr.to_string(float_format=lambda x: f"{x:,.2f}").replace("\n", "\n    "))
    us = a2["usd"].sort_values(ascending=False)
    k5 = max(1, int(len(a2) * 0.05)); k1 = max(1, int(len(a2) * 0.01))
    print(f"  concentration: top 1% ({k1}) = {us.head(k1).sum() / a2.usd.sum():.0%} of net, "
          f"top 5% ({k5}) = {us.head(k5).sum() / a2.usd.sum():.0%}")
    hh = len(a2) // 2
    print(f"  halves: first {hh} ${a2.usd[:hh].sum():,.0f} (R {a2.R[:hh].mean():+.4f}), "
          f"second ${a2.usd[hh:].sum():,.0f} (R {a2.R[hh:].mean():+.4f})")
    # the 15:30 rule's share, as in the RC1 study
    c15 = a2[a2.reason == "cond1530"]
    print(f"  the conditional 15:30 exit: {len(c15)} trades, ${c15.usd.sum():,.0f} of the "
          f"${a2.usd.sum():,.0f} net")

    print("\n" + "=" * 100)
    print("MATCHED CONTROL for ALPHA2 -- same sessions, side, stop/target/managed/15:30/flatten,")
    print("RANDOM quarter-hour entry, 1,000 draws")
    print("=" * 100)
    v = B.control(f, a2, draws=1000)
    act = a2["R"].mean()
    print(f"  rule {act:+.4f} R over {len(a2)}; control median {np.median(v):+.4f} "
          f"[{np.percentile(v, 5):+.4f}, {np.percentile(v, 95):+.4f}]; excess "
          f"{act - np.median(v):+.4f}; p(control >= rule) {float((v >= act).mean()):.3f}")

    print("\n" + "=" * 100)
    print("ALPHA2 SIZING MODES")
    print("=" * 100)
    for mode in ("FixedDollar", "ClosedEquityPercent", "ConfidenceScaledPercent"):
        cnt, t = S.run(verbose=False, sizing=mode, prior_bars=1, h2_cap=1)
        mm = headline(t)
        print(f"  {mode:<26} n {mm['n']:>4}  net ${mm['net']:>9,.0f}  PF {mm['pf']:.3f}  win "
              f"{mm['win']:.1%}  maxDD ${mm['dd']:>8,.0f}  ret/DD {mm['rdd']:.2f}  Sharpe "
              f"{mm['sharpe']:.2f}")

    print("\n" + "=" * 100)
    print("ALPHA2 control-flow census")
    print("=" * 100)
    cnt = res["ALPHA2 (prior 1 bar + H2 cap 1)"][0]
    print("   " + "  ".join(f"{k}={v}" for k, v in cnt.items() if v))
    print("   actions: " + ", ".join(f"{k} {v}" for k, v in a2.action.value_counts().items()))


if __name__ == "__main__":
    main()
