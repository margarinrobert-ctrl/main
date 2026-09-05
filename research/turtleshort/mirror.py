"""The Turtle rules run LONG and SHORT on the same bars, so the mirror can be priced.

MIRRORING CODE IS TRIVIAL; MIRRORING EVIDENCE IS NOT. Every constant in the long presets --
the ADX ceiling of 22, the 3.964 and 3.193 extension caps -- was fitted on long trades. Reusing
them on shorts is not "the same strategy in the other direction", it is an unfitted guess wearing
fitted numbers. This module measures the mirror directly instead of assuming it.

The two sides are run on the SAME bars with the SAME geometry so the comparison is clean, and each
is scored against its own matched control -- random entries, same side, same stop geometry, same
minute-of-day distribution, same ATR at entry -- because on a sample where the index rose, a long
book earns by existing and a short book loses by existing. Without the control the mirror would
look bad for a reason that has nothing to do with the rules.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/donchian")
import fastbars, indicators as I, costs  # noqa: E402

RT = costs.model("MNQ", "discount").round_turn_points()


def channels(h, l, e1=20, e2=55, x1=10, x2=20):
    """All four Donchian channels, each EXCLUDING the current bar so a break is possible."""
    return dict(hi1=I.shift(I.rmax(h, e1), 1), hi2=I.shift(I.rmax(h, e2), 1),
                lo1=I.shift(I.rmin(l, x1), 1), lo2=I.shift(I.rmin(l, x2), 1),
                xhi1=I.shift(I.rmax(h, x1), 1), xhi2=I.shift(I.rmax(h, x2), 1),
                elo1=I.shift(I.rmin(l, e1), 1), elo2=I.shift(I.rmin(l, e2), 1))


def wilder_atr(h, l, c, n=20):
    pc = I.shift(c, 1)
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()


def run(d, side, mask, atr, C, atr_mult=2.0, pyr=0.5, max_units=4, skip_win=True, cost=RT,
        flat_mod=None, tp_r=None, e1=20, e2=55):
    """The full Turtle state machine for ONE side, including the skip-after-winner rule.

    The skip rule reads the outcome of the LAST trade, so it cannot be evaluated bar-wise -- it
    needs the sequence. That is why this is a loop and not a vectorised mask."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    n = len(c)
    rows = []
    i = 1
    last_win = False
    while i < n - 1:
        if not mask[i] or not np.isfinite(atr[i]) or atr[i] <= 0:
            i += 1
            continue
        if side > 0:
            s2 = np.isfinite(C["hi2"][i]) and h[i] > C["hi2"][i]
            s1 = np.isfinite(C["hi1"][i]) and h[i] > C["hi1"][i]
        else:
            s2 = np.isfinite(C["elo2"][i]) and l[i] < C["elo2"][i]
            s1 = np.isfinite(C["elo1"][i]) and l[i] < C["elo1"][i]
        sys_on = 2 if s2 else (1 if s1 else 0)
        if sys_on == 0:
            i += 1
            continue
        if sys_on == 1 and skip_win and last_win:
            last_win = False                    # the skip consumes itself, win or not
            i += 1
            continue

        eb = i + 1
        px = o[eb]
        a = atr[i]
        first = px
        units = 1
        stop = px - side * atr_mult * a
        nxt = px + side * pyr * a
        pnl = -cost
        j = eb
        while j < n:
            # adds first: the ladder is checked on the same bar it can be reached
            while units < max_units and ((side > 0 and h[j] >= nxt) or (side < 0 and l[j] <= nxt)):
                fill = nxt
                pnl -= cost
                units += 1
                stop = fill - side * atr_mult * a
                nxt = fill + side * pyr * a
                px = (px * (units - 1) + fill) / units   # average entry across the ladder
            # TAKE PROFIT, checked BEFORE the stop on the same bar only when it is the nearer
            # level; when both sit inside one bar's range the STOP is taken, because a bar-level
            # engine cannot know which came first and the pessimistic reading is the honest one.
            if tp_r is not None:
                tgt = px + side * tp_r * atr_mult * a
                hit_tp = (h[j] >= tgt) if side > 0 else (l[j] <= tgt)
                lvl0 = stop if not np.isfinite(ch0 := (
                    (C["lo1"][j] if sys_on == 1 else C["lo2"][j]) if side > 0 else
                    (C["xhi1"][j] if sys_on == 1 else C["xhi2"][j]))) else (
                    max(stop, ch0) if side > 0 else min(stop, ch0))
                hit_sl = (l[j] <= lvl0) if side > 0 else (h[j] >= lvl0)
                if hit_tp and not hit_sl:
                    pnl += side * (tgt - px) * units
                    rows.append((i, eb, j, side, sys_on, units, px, tgt, pnl,
                                 pnl / (atr_mult * a * units)))
                    last_win = pnl > 0
                    break
            if flat_mod is not None and d["mod"][j] >= flat_mod:
                pnl += side * (c[j] - px) * units
                rows.append((i, eb, j, side, sys_on, units, px, c[j], pnl,
                             pnl / (atr_mult * a * units)))
                last_win = pnl > 0
                break
            ch = (C["lo1"][j] if sys_on == 1 else C["lo2"][j]) if side > 0 else \
                 (C["xhi1"][j] if sys_on == 1 else C["xhi2"][j])
            lvl = stop if not np.isfinite(ch) else (max(stop, ch) if side > 0 else min(stop, ch))
            if (side > 0 and l[j] <= lvl) or (side < 0 and h[j] >= lvl):
                pnl += side * (lvl - px) * units
                rows.append((i, eb, j, side, sys_on, units, px, lvl, pnl,
                             pnl / (atr_mult * a * units)))
                last_win = pnl > 0
                break
            j += 1
        else:
            break
        i = j + 1
    # R IS NOT COMPARABLE ACROSS LADDER DEPTHS and is returned only for reference: the
    # denominator scales with `units`, so a four-unit winner is divided by four times the risk of
    # a one-unit loser. Read POINTS PER TRADE and PROFIT FACTOR, which have no such distortion.
    return pd.DataFrame(rows, columns=["sig", "ent", "exit", "side", "sys", "units",
                                       "entry", "stop", "pnl", "R"])


# A matched control is deliberately NOT provided here. On this sample it could not answer the
# question anyway: NQ rose 89% and 81% of bars sit in a daily uptrend, so a short book loses by
# existing and a control would only measure that. What the numbers below CAN establish is that the
# mirror is not rescued by its own rules; what they cannot establish is how it behaves in a market
# that falls. That needs history this branch does not have.
