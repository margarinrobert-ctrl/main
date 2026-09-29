"""Verify the tensor before it is trusted. `research/v14/v14tensor.py` was verified this way and the
ONE discrepancy found -- an exit channel indexed a bar staler than the reference -- was worth 0.20
points a trade and was caught because the TRADE COUNT matched exactly while the net did not. So the
count and the mean are both required to match, and the count is the more informative of the two.

This reference is a plain Python simulation written against the spec, not a refactor of the kernel.
"""
from __future__ import annotations
import sys
import numpy as np, pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/v38"); sys.path.insert(0, "research/v51")
import v51feat as V     # noqa: E402
import run_v51 as RUN   # noqa: E402


def reference(P, cost, slip, en, xn, sn, ma, cx, ab, ss, cut):
    bars = np.flatnonzero(V.entry_mask(P, en))
    MA, CX, AB, SS = V.filter_masks(P, bars)
    keep = MA[ma] & CX[cx] & AB[ab] & SS[ss]
    o, h, l, c, atr, mod = P["o"], P["h"], P["l"], P["c"], P["atr"], P["mod"]
    elo = P["exit_lo"][xn]
    w, f = V.SESS[ss]
    fm = V.WINDOWS[w][1] if f == 1 else -1
    m = len(c)
    free, n, s = -1, 0, 0.0
    for k, i in enumerate(bars):
        if not keep[k] or i < free:
            continue
        a = i + 1
        if a >= m - 1 or not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        px = o[a] + slip
        risk = sn * atr[i]
        fixed = px - risk
        end = min(a + V.MAX_HOLD, m - 2)
        out, j = None, a
        while j <= end:
            lvl = fixed
            if np.isfinite(elo[j]) and elo[j] > lvl:
                lvl = elo[j]
            lvl = min(lvl, c[j - 1])
            if l[j] <= lvl:
                out = (lvl if o[j] > lvl else o[j]) - slip
                break
            if fm >= 0 and mod[j] >= fm:
                out = o[j + 1] - slip
                j += 1
                break
            j += 1
        if out is None:
            j = end
            out = c[j] - slip
        free = j
        if i < cut:
            n += 1
            s += (out - px - cost) / risk
    return n, (s / n if n else np.nan)


def main():
    bad = 0
    for market, tf in (("US100L", 60), ("US30L", 60), ("US100L", 30)):
        P = V.build(market, tf)
        ck = V.COSTS[market]
        cut = int(P["n"] * RUN.SPLIT)
        D = RUN.sweep_market(market, tf)
        rng = np.random.default_rng(4)
        pick = [(30, 20, 2.0, 0, 0, 0, 0), (20, 10, 2.5, 1, 1, 3, 0), (55, 30, 3.0, 5, 3, 8, 2),
                (10, 5, 1.5, 2, 2, 11, 5), (30, 10, 2.0, 4, 1, 6, 7)]
        for (en, xn, sn, ma, cx, ab, ss) in pick:
            row = D[(D.entN == en) & (D.exitN == xn) & (D.stopN == sn) & (D.ma == ma)
                    & (D.cx == cx) & (D.ab == ab) & (D.ss == ss)]
            assert len(row) == 1, (market, tf, en, xn, sn, ma, cx, ab, ss, len(row))
            rn, rR = reference(P, ck["cost"], ck["slip"], en, xn, sn, ma, cx, ab, ss, cut)
            tn, tR = int(row.n.iloc[0]), float(row.R.iloc[0])
            ok = (rn == tn) and (not np.isfinite(rR) or abs(rR - tR) < 1e-9)
            bad += 0 if ok else 1
            print(f"  {market:>6} {tf:>3}m  ent{en:>3} exit{xn:>3} stop{sn}  "
                  f"ma={V.MA200_MODES[ma]:<8} cx={V.CROSS_MODES[cx]:<8} ab={ab:<2} ss={ss}  "
                  f"n {rn:>5} vs {tn:>5}   R {rR:+.6f} vs {tR:+.6f}   {'ok' if ok else 'MISMATCH'}")
    print(f"\n  {'ALL MATCH -- tensor verified' if bad == 0 else str(bad) + ' MISMATCHES'}")
    return bad


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
