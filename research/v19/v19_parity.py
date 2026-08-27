"""Parity for the one NEW component: the 200-day filter as a script must build it.

The order model here is V17's, already diffed against the engine at 100% signal match, 100% exit-bar
match and correlation 1.0000. The only thing V19 adds is the daily 200-period average, and that is
exactly where look-ahead enters a mixed daily/intraday rule.

THE TRAP. `request.security(syminfo.tickerid, "D", ta.sma(close,200))` returns the value of the
CURRENTLY FORMING daily bar, which on an intraday bar includes today's close-so-far. That is not
look-ahead -- today's price is known -- but it is NOT what the research computed, which keys on the
last COMPLETED daily bar. The two differ on every bar of every day, so the script must write
`ta.sma(close,200)[1]` INSIDE the security call. This checks that they agree.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v19")
import v19scale as S         # noqa: E402
from v19drift import daily_trend_state   # noqa: E402


def pine_side(P, n=200):
    """`request.security(tf, "D", ta.sma(close,200)[1], lookahead_off)` >= close, rebuilt here."""
    ts = pd.to_datetime(P["ts"])
    day = pd.Series(P["c"], index=ts).resample("1D").last().dropna()
    sma_prev = day.rolling(n).mean().shift(1)      # the [1] inside the security call
    known = day.index.to_numpy().astype("datetime64[ns]")
    pos = np.searchsorted(known, P["ts"].astype("datetime64[ns]"), side="right") - 1
    out = np.full(len(P["c"]), np.nan)
    ok = pos >= 0
    out[ok] = sma_prev.to_numpy()[pos[ok]]
    return P["c"] >= out


if __name__ == "__main__":
    print("V19: the daily filter, research construction vs what a script can build\n")
    print(f"   {'market':<8}{'bars':>10}{'research TRUE':>15}{'pine TRUE':>12}{'agreement':>12}")
    for k in ("US30L", "XAU", "US30", "US100"):
        P = S.ctx_tf(k, 60)
        a = daily_trend_state(P) == 1
        b = np.nan_to_num(pine_side(P).astype(float), nan=0).astype(bool)
        print(f"   {k:<8}{len(a):>10,}{a.mean():>14.1%}{b.mean():>12.1%}"
              f"{float((a == b).mean()):>12.4%}")
    print("\n   Any disagreement here is a day boundary, and it is the difference between the")
    print("   research rule and the rule the script runs. It has to be read, not assumed.")
