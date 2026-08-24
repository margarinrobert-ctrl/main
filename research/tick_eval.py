"""What "On every tick" actually does to a rule, measured on the rule the question was about.

The checkboxes do two different things and only one of them is realism.

  EXITS   evaluating a resting stop or target tick by tick is MORE accurate. An order in the
          market fills when price touches it, not when a bar happens to end. research/intrabar.py
          already does this against real 1-minute paths, and for this rule it moved the result
          by +1%.

  ENTRIES evaluating the ENTRY CONDITION tick by tick is not more accurate. It is a different
          rule. "Enter when the bar CLOSES below the 5-bar low" becomes "enter the instant price
          dips below the 5-bar low", which fires on bars that close back above and would never
          have signalled. Nobody trading the written rule takes those trades.

This reconstructs the partial 60-minute bar at each 1-minute step -- running high, running low,
the current close, and a one-step ATR update -- and asks how often the rule is true INSIDE a bar
that does not satisfy it at the close.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
from bos_choch import load_bars, prep
from intrabar import minute_map

ALPHA = 2.0 / 15.0          # ta.ema(ta.tr(true), 14)


def compare(tf=60):
    m = minute_map(tf)
    d = m["d"]
    o, h, l, c, atr_ = d["o"], d["h"], d["l"], d["c"], d["atr"]
    idx = d["df"].index
    dow = np.array([t.dayofweek for t in idx])
    lo1, hi1 = m["lo"], m["hi"]
    h1, l1, c1 = m["h"], m["l"], m["c"]
    n = len(c)

    # the completed-bar rule, exactly as the script computes it
    low5 = np.full(n, np.nan)
    for i in range(5, n):
        low5[i] = l[i - 5:i].min()
    close_rule = (atr_ <= np.r_[np.nan, atr_[:-1]]) & (c < low5) & (dow == 1)
    close_rule[:300] = False

    # the same rule evaluated at every 1-minute step inside the bar
    intrabar = np.zeros(n, bool)
    first_min = np.full(n, -1, np.int64)
    for i in range(300, n):
        if dow[i] != 1 or not np.isfinite(low5[i]) or not np.isfinite(atr_[i - 1]):
            continue
        a, b = lo1[i], hi1[i]
        if b <= a:
            continue
        pc = c[i - 1]
        rh = -np.inf; rl = np.inf
        for t in range(a, b):
            rh = max(rh, h1[t]); rl = min(rl, l1[t])
            tr = max(rh - rl, abs(rh - pc), abs(rl - pc))
            atr_p = ALPHA * tr + (1 - ALPHA) * atr_[i - 1]
            if atr_p <= atr_[i - 1] and c1[t] < low5[i]:
                intrabar[i] = True
                first_min[i] = t - a
                break
    return dict(close_rule=close_rule, intrabar=intrabar, first_min=first_min, n=n)


if __name__ == "__main__":
    r = compare()
    cr, ib = r["close_rule"], r["intrabar"]
    both = cr & ib
    only_ib = ib & ~cr
    only_cr = cr & ~ib
    print(f"60-minute bars, rule = ATR falling AND close<5-bar low AND Tuesday\n")
    print(f"  bars where the rule is true AT THE CLOSE          {cr.sum():>6,}")
    print(f"  bars where it is true at some point INSIDE        {ib.sum():>6,}")
    print(f"     of those, also true at the close               {both.sum():>6,}")
    print(f"     TRUE INSIDE, FALSE AT THE CLOSE                {only_ib.sum():>6,}"
          f"   <- trades tick mode takes and the rule does not")
    print(f"     true at the close but never flagged inside     {only_cr.sum():>6,}")
    print(f"\n  Tick evaluation fires {ib.sum()/max(cr.sum(),1):.1f}x as often as the written rule.")
    print(f"  {100*only_ib.sum()/max(ib.sum(),1):.0f}% of its signals are on bars that closed "
          f"back above the 5-bar low.")
    fm = r["first_min"][only_ib]
    print(f"  Those phantom signals fire a median {np.median(fm):.0f} minutes into the "
          f"60-minute bar,\n  so the position is open for the rest of it -- a bar the rule "
          f"never wanted to be in.")
