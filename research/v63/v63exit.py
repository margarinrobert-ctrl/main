"""V63 stop-loss / take-profit optimisation -- one walk, three exit axes.

WHAT IS SWEPT, declared first:
  STOP      0.75 / 1.0 / 1.5 / 2.0 / 2.5 / 3.0 / 4.0 / 6.0 / 12.0 x ATR14 at the SIGNAL bar.
            12.0 is there so the stop CANNOT bind -- `STUDY_V43`'s rule for measuring anything a
            stop censors.
  TARGET    none, or a multiple of the STOP (0.5R .. 8R), or an absolute multiple of ATR (1 .. 8).
            BOTH parameterisations are swept because they are not the same axis: a 2R target sits
            at 3 ATR behind a 1.5N stop and at 6 ATR behind a 3N stop, so a sweep in R confounds
            the target with the stop and a sweep in ATR does not.
  PARTIAL   none, or half the position off at 1R or 2R with the remainder managed normally.
            `STUDY_V8_EXIT_OPT` found partials worth nothing on a different base -- and found a bug
            that inflated every partial result, so the ladder here counts units OPENED and the
            partial cannot re-open anything.

  9 x 15 x 3 = 405 cells a market.

TWO THINGS THAT DECIDE THE READING:
  1. SCORE IN PERCENT OF PRICE, NEVER IN R. R divides by the stop, so a tighter stop earns a larger
     R for the same money; V61 put a +2.33 R cell on top that returned +0.32%. Both are printed and
     the two axes disagree, which is the point.
  2. WHEN low <= stop AND high >= target IN THE SAME BAR, OHLC cannot say which came first. It is
     resolved as a STOP always, and the AMBIGUOUS SHARE is reported: any result whose ambiguous
     share is large is set by the tie-break, not by the market.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit, prange

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v63core as V  # noqa: E402
import v63sess as S  # noqa: E402

STOPS = (0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 6.0, 12.0)
TPS = ([(0, 0.0)] + [(1, x) for x in (0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0)]
       + [(2, x) for x in (1.0, 2.0, 3.0, 4.0, 6.0, 8.0)])
PARTIALS = (0.0, 1.0, 2.0)


def geometry():
    rows = []
    for st in STOPS:
        for mode, val in TPS:
            for pa in PARTIALS:
                rows.append(dict(stop=st, tp_mode=mode, tp_val=val, partial=pa))
    return pd.DataFrame(rows)


@njit(cache=True, parallel=True)
def walk(o, h, l, c, atr, rows, g_stop, g_mode, g_val, g_part, cost, slip, hold, m):
    """Returns points, exit bar, reason (0 stop 1 target 2 cap 3 partial-then-cap), the ambiguous
    flag, and the bar the target was first touched (-1 if never)."""
    N = len(rows)
    G = len(g_stop)
    pts = np.full((N, G), np.nan, np.float32)
    xb = np.full((N, G), -1, np.int32)
    why = np.zeros((N, G), np.int8)
    amb = np.zeros((N, G), np.int8)
    tbar = np.full((N, G), -1, np.int32)
    for kk in prange(N):
        i = rows[kk]
        a = i + 1
        anc = atr[i]
        if a < 2 or a >= m - 3 or not np.isfinite(anc) or anc <= 0:
            continue
        px = o[a] + slip
        for gg in range(G):
            risk = g_stop[gg] * anc
            if risk <= 0:
                continue
            lvl = px - risk
            if g_mode[gg] == 0:
                tgt = 1e18
            elif g_mode[gg] == 1:
                tgt = px + g_val[gg] * risk
            else:
                tgt = px + g_val[gg] * anc
            plvl = px + g_part[gg] * risk if g_part[gg] > 0.0 else 1e18
            end = a + hold
            if end > m - 3:
                end = m - 3
            size = 1.0
            realised = 0.0
            done = False
            rs = 2
            j = a
            while j <= end:
                hit_s = l[j] <= lvl
                hit_t = h[j] >= tgt
                if hit_s and hit_t:
                    amb[kk, gg] = 1
                if size > 0.75 and plvl < 1e17 and h[j] >= plvl and not hit_s:
                    fill = plvl if o[j] < plvl else o[j]
                    realised += 0.5 * (fill - slip - px - 0.5 * cost)
                    size = 0.5
                    rs = 3
                if hit_t and tbar[kk, gg] < 0:
                    tbar[kk, gg] = j
                if hit_s:
                    fill = lvl if o[j] > lvl else o[j]
                    realised += size * (fill - slip - px - 0.5 * cost)
                    xb[kk, gg] = j
                    if rs != 3:
                        rs = 0
                    done = True
                    break
                if hit_t:
                    fill = tgt if o[j] < tgt else o[j]
                    realised += size * (fill - slip - px - 0.5 * cost)
                    xb[kk, gg] = j
                    if rs != 3:
                        rs = 1
                    done = True
                    break
                j += 1
            if not done:
                j = end
                realised += size * (c[j] - slip - px - 0.5 * cost)
                xb[kk, gg] = j
                if rs != 3:
                    rs = 2
            pts[kk, gg] = realised - 0.5 * cost
            why[kk, gg] = rs
    return pts, xb, why, amb, tbar


def run(market, cost_mult=1.0):
    D, rows = S.base_rows(market)
    G = geometry()
    pts, xb, why, amb, tbar = walk(
        D["o"], D["h"], D["l"], D["c"], D["atr"], rows.astype(np.int64),
        G["stop"].to_numpy(float), G["tp_mode"].to_numpy(np.int64), G["tp_val"].to_numpy(float),
        G["partial"].to_numpy(float), D["cost"] * cost_mult, D["slip"] * cost_mult, V.HOLD,
        D["n"])
    epx = D["o"][np.minimum(rows + 1, D["n"] - 1)]
    blk = np.full(D["n"], -1, np.int64)
    names = list(D["blocks"].keys())
    for i, nm in enumerate(names):
        blk[np.asarray(D["blocks"][nm], bool)] = i
    return dict(D=D, rows=rows, G=G, pts=pts, xb=xb, why=why, amb=amb, tbar=tbar, epx=epx,
                blk=blk, names=names)


@njit(cache=True, parallel=True)
def aggregate(rows, pts, xb, why, amb, blkid, epx, atr, stop, nb):
    """Position lock per geometry, then per-block sums. Columns:
    0 n, 1 sum pct, 2 sum R, 3 gross+ pct, 4 gross- pct, 5 wins, 6 stop exits, 7 target exits,
    8 cap exits, 9 ambiguous, 10 sum bars held."""
    N, G = pts.shape
    out = np.zeros((G, nb, 11), np.float64)
    for g in prange(G):
        free = -1
        for k in range(N):
            if xb[k, g] < 0 or not np.isfinite(pts[k, g]) or rows[k] <= free:
                continue
            free = xb[k, g]
            b = blkid[k]
            if b < 0:
                continue
            pc = 100.0 * pts[k, g] / epx[k]
            r = pts[k, g] / (stop[g] * atr[k])
            out[g, b, 0] += 1.0
            out[g, b, 1] += pc
            out[g, b, 2] += r
            if pc > 0:
                out[g, b, 3] += pc
                out[g, b, 5] += 1.0
            else:
                out[g, b, 4] += -pc
            w = why[k, g]
            if w == 0:
                out[g, b, 6] += 1.0
            elif w == 1:
                out[g, b, 7] += 1.0
            elif w == 2:
                out[g, b, 8] += 1.0
            out[g, b, 9] += amb[k, g]
            out[g, b, 10] += xb[k, g] - rows[k]
    return out


def table(res, market):
    G, names = res["G"], res["names"]
    st = aggregate(res["rows"].astype(np.int64), res["pts"].astype(np.float64),
                   res["xb"].astype(np.int64), res["why"].astype(np.int64),
                   res["amb"].astype(np.int64), res["blk"][res["rows"]].astype(np.int64),
                   res["epx"].astype(np.float64), res["D"]["atr"][res["rows"]].astype(np.float64),
                   G["stop"].to_numpy(float), len(names))
    d = G.copy()
    d["market"] = market
    for bi, nm in enumerate(names):
        f = st[:, bi, :]
        n = f[:, 0]
        d[f"n_{nm}"] = n
        d[f"pct_{nm}"] = np.where(n > 0, f[:, 1] / np.maximum(n, 1), np.nan)
        d[f"R_{nm}"] = np.where(n > 0, f[:, 2] / np.maximum(n, 1), np.nan)
        d[f"pf_{nm}"] = np.where(f[:, 4] > 0, f[:, 3] / np.maximum(f[:, 4], 1e-9), np.nan)
        d[f"win_{nm}"] = np.where(n > 0, f[:, 5] / np.maximum(n, 1), np.nan)
        d[f"stopsh_{nm}"] = np.where(n > 0, f[:, 6] / np.maximum(n, 1), np.nan)
        d[f"tgtsh_{nm}"] = np.where(n > 0, f[:, 7] / np.maximum(n, 1), np.nan)
        d[f"capsh_{nm}"] = np.where(n > 0, f[:, 8] / np.maximum(n, 1), np.nan)
        d[f"amb_{nm}"] = np.where(n > 0, f[:, 9] / np.maximum(n, 1), np.nan)
        d[f"bars_{nm}"] = np.where(n > 0, f[:, 10] / np.maximum(n, 1), np.nan)
        d[f"tot_{nm}"] = n * np.nan_to_num(d[f"pct_{nm}"])
    return d


def label(r):
    tp = ("none" if r["tp_mode"] == 0 else
          (f"{r['tp_val']:g}R" if r["tp_mode"] == 1 else f"{r['tp_val']:g}ATR"))
    pa = "" if r["partial"] == 0 else f" +half@{r['partial']:g}R"
    return f"{r['stop']:g}N / {tp}{pa}"
