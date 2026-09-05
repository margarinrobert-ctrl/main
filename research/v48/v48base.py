"""V48 -- the Donchian breakout base, and the trades a filter will be asked to sort.

THE BASE IS THIS BRANCH'S SHIPPED GEOMETRY, not a new search: Donchian entry, ATR stop, Donchian
channel exit, ONE unit, NO take profit, long only, market order at the next bar's open. That is the
V11/V24 family, and using it unchanged is what makes a filter result attributable to the FILTER.

The exit is the HIGHER of the ATR stop and the channel low, because a falling price reaches that
level first -- the same convention `research/turtle/core.py` uses and the same one the shipped Pine
implements.

NO TAKE PROFIT. Ten independent searches on this branch have now put no-target ahead of every
target tested; re-introducing one here would be a second change competing with the filter.
"""
from __future__ import annotations

import sys

import numpy as np
from numba import njit

sys.path.insert(0, "research")
sys.path.insert(0, "research/v38")
sys.path.insert(0, "research/v46")
import v38feeds as FD        # noqa: E402
import v46grid as G          # noqa: E402


@njit(cache=True)
def _walk(o, h, l, c, atr, hi_ent, lo_exit, stop_n, max_hold, cost, slip,
          sig_out, ent_out, xb_out, pnl_out, risk_out):
    """One position at a time. Returns per-trade signal bar, entry bar, exit bar, points, risk."""
    n = len(c)
    k = 0
    i = 1
    while i < n - 1:
        if (np.isfinite(atr[i]) and atr[i] > 0 and np.isfinite(hi_ent[i])
                and h[i] > hi_ent[i]):
            px = o[i + 1] + slip
            risk = stop_n * atr[i]
            stop = px - risk
            j = i + 1
            end = min(n - 1, i + 1 + max_hold)
            out = 0.0
            while j <= end:
                lvl = stop
                if np.isfinite(lo_exit[j - 1]) and lo_exit[j - 1] > lvl:
                    lvl = lo_exit[j - 1]
                if l[j] <= lvl:
                    out = (o[j] if o[j] < lvl else lvl) - slip
                    break
                j += 1
            else:
                j = end
                out = c[j] - slip
            if j > end:
                j = end
                out = c[j] - slip
            sig_out[k] = i; ent_out[k] = i + 1; xb_out[k] = j
            pnl_out[k] = out - px - cost
            risk_out[k] = risk
            k += 1
            i = j + 1
        else:
            i += 1
    return k


def trades(P, entry_n=30, exit_n=20, stop_n=2.0, max_hold=480):
    n = P["n"]
    hi = G.rma(np.zeros(1), 1)          # touch numba once so the import is exercised
    import pandas as pd
    hs = pd.Series(P["h"]).rolling(entry_n).max().shift(1).to_numpy()
    ls = pd.Series(P["l"]).rolling(exit_n).min().shift(1).to_numpy()
    cap = n // 2 + 8
    sig = np.zeros(cap, np.int64); ent = np.zeros(cap, np.int64)
    xb = np.zeros(cap, np.int64); pnl = np.zeros(cap); risk = np.zeros(cap)
    k = _walk(P["o"], P["h"], P["l"], P["c"], P["atr"], hs, ls,
              float(stop_n), int(max_hold), P["cost"], P["slip"],
              sig, ent, xb, pnl, risk)
    sl = slice(0, k)
    r = np.where(risk[sl] > 0, pnl[sl] / risk[sl], np.nan)
    return dict(sig=sig[sl], ent=ent[sl], xb=xb[sl], pnl=pnl[sl], risk=risk[sl], R=r)


def prep(market, tf):
    cost, slip = {"US100L": (0.72, 0.25), "US30L": (1.50, 0.50)}[market]
    return G.prep(market, tf, cost, slip)
