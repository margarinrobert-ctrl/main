"""V3 -- the nulls. Does the BREAKOUT LEVEL do anything, or is this "be in the market with a stop"?

Three nulls, hardest first.

  N1  RISK-MATCHED RANDOM ENTRY. Same sessions, same sides, entered at a RANDOM bar of the session
      with the stop placed k*ATR(5) from THAT entry, exit at the close. Risk is matched trade for
      trade, which `STUDY_TURTLE_YOUTUBE` established is required -- a control that only matches the
      exits lets the entry set the risk and then flatters or damns the rule for the wrong reason.
      This asks the sharpest question: given that we trade this day on this side, does entering AT
      THE LEVEL beat entering anywhere?

  N2  ALL-SESSION RANDOM ENTRY. The same thing without conditioning on the day the rule chose. The
      gap between N1 and N2 is how much of the result is DAY SELECTION rather than timing.

  N3  ALWAYS-IN. Buy the open, hold to the close, every session, no stop. Both indices rose ~150%
      and ~420% here, so a long intraday breakout is a drift exposure until this is priced.

Then the parameter neighbourhood, read by MARGINAL AVERAGE per axis and never by its top cell.
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
NDRAW = 400


def hdr(t):
    print("\n" + BAR + "\n" + t + "\n" + BAR)


def control(d, day, rule, k, cost, seed, restrict_days=True):
    """N1/N2: the same sides, entered at a random bar, risk matched to k*ATR."""
    rng = np.random.default_rng(seed)
    o = d["open"].to_numpy(); h = d["high"].to_numpy()
    lo = d["low"].to_numpy(); c = d["close"].to_numpy()
    sess = d["sess"].to_numpy()
    atr = day["atr_sma"].to_dict()
    starts = np.flatnonzero(np.r_[True, sess[1:] != sess[:-1]])
    ends = np.r_[starts[1:], len(sess)]
    span = {sess[s]: (s, e) for s, e in zip(starts, ends)}
    if restrict_days:
        jobs = list(zip(rule.sess.to_numpy(), rule.side.to_numpy()))
    else:
        ks = [k_ for k_ in span if np.isfinite(atr.get(k_, np.nan))]
        jobs = [(k_, s) for k_ in ks for s in (1, -1)]
    out = []
    for key, side in jobs:
        if key not in span:
            continue
        s0, s1 = span[key]
        a = atr.get(key, np.nan)
        if not np.isfinite(a) or a <= 0 or s1 - s0 < 3:
            continue
        j = int(rng.integers(s0, s1))
        ent = c[j]
        stop = ent - side * k * a
        why, ex = "close", s1 - 1
        val = c[s1 - 1]
        for e in range(j + 1, s1):
            if (side > 0 and lo[e] <= stop) or (side < 0 and h[e] >= stop):
                why, ex, val = "stop", e, stop
                break
        g = side * (val - ent) - cost
        out.append(100.0 * g / ent)
    return np.array(out)


def main():
    for nm in ("US100L", "US30L"):
        d = V.load(nm)
        day = V.daily_atr(d)
        cost = V.RT[nm]
        t = V.walk(d, day, k=0.4, cost_pts=cost, amb_mode=AMB)
        r, lk, cut = V.split(t)

        hdr(f"V3 -- {nm}")
        for lab, tt in (("research", r), ("locked", lk)):
            s = V.stats(tt)
            obs = s["mean"]
            n1 = np.array([control(d, day, tt, 0.4, cost, sd).mean() for sd in range(NDRAW)])
            n2 = np.array([control(d, day, tt, 0.4, cost, 1000 + sd,
                                   restrict_days=False).mean() for sd in range(NDRAW // 4)])
            p1 = float((n1 >= obs).mean())
            p2 = float((n2 >= obs).mean())
            print(f"\n  {lab.upper():<9} rule {obs:+.4f} %/trade on n={s['n']}, PF {s['pf']:.3f}")
            print(f"    N1  risk-matched random entry, SAME days+sides : "
                  f"median {np.median(n1):+.4f}  p {p1:.3f}   {'PASS' if p1 <= 0.05 else 'fail'}")
            print(f"    N2  risk-matched random entry, ALL days        : "
                  f"median {np.median(n2):+.4f}  p {p2:.3f}   {'PASS' if p2 <= 0.05 else 'fail'}")
            print(f"    day selection is worth {np.median(n1) - np.median(n2):+.4f} %/trade "
                  f"(N1 median - N2 median); timing is worth {obs - np.median(n1):+.4f}")

        # ---------------- N3 always-in
        g = d.groupby("sess").agg(o=("open", "first"), c=("close", "last"))
        g["pct"] = 100.0 * (g["c"] - g["o"]) / g["o"]
        gr, gl = g[g.index < cut], g[g.index >= cut]
        print(f"\n  N3  ALWAYS-IN (buy the open, sell the close, no stop, every session)")
        for lab, gg in (("research", gr), ("locked", gl)):
            print(f"    {lab:<9} n {len(gg):>5}  mean {gg['pct'].mean():+.4f} %/session  "
                  f"total {gg['pct'].sum():+.2f}%  win {(gg['pct'] > 0).mean():.3f}")

        # ---------------- daily Sharpe, zero-filled
        print(f"\n  DAILY SHARPE over EVERY session in the block, zero-filled on days that did not"
              f" trade (STUDY_V17's rule -- over traded days only a filter is paid for trading less)")
        for lab, tt, gg in (("research", r, gr), ("locked", lk, gl)):
            pnl = tt.groupby("sess").pct.sum().reindex(gg.index).fillna(0.0)
            sh = float(pnl.mean() / max(pnl.std(ddof=1), 1e-12) * np.sqrt(252))
            print(f"    {lab:<9} {len(pnl):>5} sessions   {pnl.mean():+.4f} %/session   "
                  f"annualised Sharpe {sh:+.3f}")


if __name__ == "__main__":
    main()
