"""BEFORE ANY BARRIER: is there a reversal in US30 at all, and does it obey the mechanism?

Three readings, in this order, on the RESEARCH BLOCK ONLY:

  1. COST AS A FRACTION OF RISK, and the driftless break-even each declared geometry implies.
     `STUDY_TURTLE_15M`: a cost is a fraction of risk, never a number of points.
  2. THE GEOMETRY-FREE READ. Forward return in ATR units at six horizons, signed by -sign(d), with
     a NEWEY-WEST t at lag h because the windows OVERLAP (`STUDY_V47`: the naive t is 1.9-3.2x too
     generous). Beside it the UNCONDITIONAL forward return, which is the drift this market gives
     away for free, and the CONTINUATION sign, which must be the mirror.
  3. THE MECHANISM'S OWN GRADIENT. Flow is proportional to |d|, so the reversal must GROW with |d|.
     This is the test that killed `STUDY_LEV_ETF_REBALANCE` in one run, and it is worth more than
     any p-value: a conditioning variable that predicts the opposite of its own mechanism ends the
     family whatever the headline says.
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mr30 import mr30core as M  # noqa: E402

HOR = (1, 2, 4, 8, 16, 32)
NS = (2, 4, 8, 16)
KS = (1.5, 2.5)


def nw_t(x, lag):
    """Newey-West t on the mean of an overlapping series."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 30:
        return np.nan
    e = x - x.mean()
    g0 = float(e @ e) / n
    v = g0
    for k in range(1, int(lag) + 1):
        if k >= n:
            break
        gk = float(e[k:] @ e[:-k]) / n
        v += 2.0 * (1.0 - k / (lag + 1.0)) * gk
    if v <= 0:
        return np.nan
    return float(x.mean() / np.sqrt(v / n))


def fwd_atr(f, h):
    """Forward h-bar return from THIS bar's close, in ATR(14) units at this bar. Causal label."""
    c = f["close"].to_numpy(); at = f["atr"].to_numpy()
    nxt = np.r_[c[h:], np.full(h, np.nan)]
    with np.errstate(invalid="ignore", divide="ignore"):
        return (nxt - c) / np.where(at > 0, at, np.nan)


def main():
    f = M.load("US30L")
    blk = M.blocks(f)
    res = blk["A_research"]
    atr = float(np.nanmedian(f["atr"].to_numpy()))

    print(f"US30L 15m, research block {int(res.sum())} bars, median ATR {atr:.1f} pts, "
          f"round turn {M.COST} pts")
    print("\n1. COST AS A FRACTION OF RISK, AND THE BREAK-EVEN EACH GEOMETRY IMPLIES")
    print(f"{'geometry':<22}{'cost/risk':>11}{'driftless BE':>14}{'BE after cost':>15}")
    for nm, (sa, ta) in (("SYM 1.5N / 1.5 ATR", (1.5, 1.5)), ("REV 3.0N / 1.0 ATR", (3.0, 1.0))):
        cr = M.COST / (sa * atr)
        print(f"{nm:<22}{cr:>11.4f}{sa / (sa + ta):>14.4f}"
              f"{M.breakeven(sa, ta, M.COST, atr):>15.4f}")

    print("\n2. GEOMETRY-FREE: forward return in ATR, signed by -sign(d), Newey-West t at lag h")
    print("   (a FADE that works is positive; the CONTINUATION column is its mirror and the drift")
    print("    column is what a random long earns on the same bars)")
    base = {}
    for h in HOR:
        fw = fwd_atr(f, h)
        m = res & np.isfinite(fw)
        base[h] = (float(np.nanmean(fw[m])), nw_t(fw[m], h))
    print(f"{'':22}" + "".join(f"{f'h={h}':>18}" for h in HOR))
    print(f"{'unconditional drift':<22}" +
          "".join(f"{base[h][0]:>10.4f}{base[h][1]:>8.1f}" for h in HOR))
    for n in NS:
        d = M.displacement(f, n)
        for k in KS:
            sel = res & np.isfinite(d) & (np.abs(d) >= k)
            row = f"n={n:<3d} |d|>={k:<4.1f} fade "
            cells = []
            for h in HOR:
                fw = fwd_atr(f, h)
                m = sel & np.isfinite(fw)
                x = -np.sign(d[m]) * fw[m]
                cells.append(f"{np.mean(x):>10.4f}{nw_t(x, h):>8.1f}")
            print(f"{row:<22}" + "".join(cells) + f"   n={int(sel.sum())}")

    print("\n3. THE MECHANISM'S GRADIENT: reversal by QUINTILE of |d| (fade, ATR units)")
    print("   the mechanism says this must RISE left to right; if it falls, the family is dead")
    for n in NS:
        d = M.displacement(f, n)
        m0 = res & np.isfinite(d)
        q = np.nanquantile(np.abs(d[m0]), [0.2, 0.4, 0.6, 0.8])
        for h in (4, 16):
            fw = fwd_atr(f, h)
            cells = []
            ad = np.abs(d)
            edges = np.r_[-np.inf, q, np.inf]
            for i in range(5):
                m = m0 & np.isfinite(fw) & (ad >= edges[i]) & (ad < edges[i + 1])
                cells.append(np.mean(-np.sign(d[m]) * fw[m]))
            slope = cells[-1] - cells[0]
            print(f"  n={n:<3d} h={h:<3d} " + " ".join(f"{v:>8.4f}" for v in cells) +
                  f"   Q5-Q1 {slope:>+8.4f}  {'RISES' if slope > 0 else 'FALLS'}")


if __name__ == "__main__":
    main()
