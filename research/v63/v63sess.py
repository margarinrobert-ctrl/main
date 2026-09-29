"""V63 session control -- an entry window and a hard flatten, and a walk-forward that re-chooses.

TWO MECHANICS, KEPT SEPARATE, because they are different things and this branch has measured them
behaving differently:
  ENTRY WINDOW   only take signals whose bar closes inside [start, stop). A trade opened inside the
                 window is then managed normally and may run for days.
  HARD FLATTEN   in addition, close any open position at the stop time. "Flat by 16:00" means flat
                 at the 16:00 OPEN -- `strategy.close_all()` cannot sell the close of the bar that
                 triggers it, so the engine exits at the OPEN of the first bar at or after the stop
                 minute, which is what the script will actually do.

WHAT TO EXPECT, on eleven prior measurements here: the flatten is destructive and the window is
usually destructive. V63 is the most extreme case yet -- its median WINNER holds 240 hours and
exits on the 480-bar cap -- so a daily flatten truncates every winner it has. That is a prediction,
and it is tested rather than asserted.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit, prange

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v63core as V  # noqa: E402

# New York minutes. `None` = no window.
WINDOWS = {"all hours": None, "09:30-16:00": (570, 960), "09:30-12:00": (570, 720),
           "08:00-12:00": (480, 720), "07:00-11:00": (420, 660), "09:30-11:00": (570, 660),
           "13:00-16:00": (780, 960), "03:00-12:00": (180, 720)}


@njit(cache=True, parallel=True)
def _tensor(o, h, l, c, mod, atr, rows, g_stop, g_flat, cost, slip, hold, m):
    """The V63 exit walk plus an optional hard flatten at a minute of day.

    `g_flat[g] < 0` means no flatten. Otherwise the trade closes at the OPEN of the first bar at or
    after that minute -- never at the close of the bar that triggers it, which no script can do.
    """
    N = len(rows)
    G = len(g_stop)
    xb = np.full((N, G), -1, np.int32)
    pts = np.full((N, G), np.nan, np.float32)
    why = np.zeros((N, G), np.int8)          # 0 stop, 1 cap, 2 flatten
    for kk in prange(N):
        i = rows[kk]
        a = i + 1
        anc = atr[i]
        if a < 2 or a >= m - 3 or not np.isfinite(anc) or anc <= 0:
            continue
        px = o[a] + slip
        for gg in range(G):
            lvl = px - g_stop[gg] * anc
            end = a + hold
            if end > m - 3:
                end = m - 3
            out = np.nan
            rs = 1
            j = a
            while j <= end:
                if g_flat[gg] >= 0 and j > a and mod[j] >= g_flat[gg] and mod[j - 1] < g_flat[gg]:
                    out = o[j] - slip
                    rs = 2
                    break
                if l[j] <= lvl:
                    out = (lvl if o[j] > lvl else o[j]) - slip
                    rs = 0
                    break
                j += 1
            if not np.isfinite(out):
                j = end
                out = c[j] - slip
                rs = 1
            xb[kk, gg] = j
            pts[kk, gg] = out - px - cost
            why[kk, gg] = rs
    return xb, pts, why


def base_rows(market, tf=30, cell=None):
    """The V63 FINAL trigger's own signal bars, all hours, plus the frame."""
    from run_v63d import FINAL
    cell = dict(FINAL if cell is None else cell)
    D = V.build(market, tf)
    trio = tuple(int(x) for x in str(cell["ema"]).split("/"))
    e = D["ema"][trio]
    ok = e["stack"].copy()
    ok &= e["since"] <= int(cell["win"])
    vw = D["vw"][(cell["anchor"], cell["weight"])]
    vwp = np.concatenate(([np.nan], vw[:-1]))
    ok &= np.isfinite(vw) & np.isfinite(vwp) & (D["c"] > vw) & (vw > vwp)
    am = pd.Series(D["atr"]).rolling(50).mean().to_numpy()
    ok &= np.isfinite(am) & (D["atr"] >= am)
    ok[:300] = False
    ok[-(V.HOLD + 6):] = False
    ok &= np.isfinite(D["atr"]) & (D["atr"] > 0)
    return D, np.flatnonzero(ok)


def mod_of(D):
    ix = pd.DatetimeIndex(D["ix"])
    return (ix.hour * 60 + ix.minute).to_numpy().astype(np.int64)


def walk(D, rows, stops, flats, cost_mult=1.0):
    return _tensor(D["o"], D["h"], D["l"], D["c"], mod_of(D), D["atr"], rows.astype(np.int64),
                   np.asarray(stops, float), np.asarray(flats, np.int64),
                   D["cost"] * cost_mult, D["slip"] * cost_mult, V.HOLD, D["n"])


def lock(rows, keep, xb, pts, why, epx, g):
    """The position lock over a filtered row list. Returns (bar, pct, reason)."""
    free, out = -1, []
    for k in keep:
        if xb[k, g] < 0 or not np.isfinite(pts[k, g]) or rows[k] <= free:
            continue
        free = xb[k, g]
        out.append((rows[k], 100.0 * float(pts[k, g]) / epx[k], int(why[k, g])))
    return out


def metrics(p):
    p = np.asarray(p, float)
    if len(p) < 5:
        return None
    w = p > 0
    eq = np.cumsum(p)
    return dict(n=len(p), pct=float(p.mean()), tot=float(p.sum()),
                pf=float(p[w].sum() / max(1e-9, -p[~w].sum())), win=float(w.mean()),
                dd=float(np.max(np.maximum.accumulate(eq) - eq)))
