"""Verify V52's kernel against an independent plain-Python simulation before anything is read."""
from __future__ import annotations
import sys
import numpy as np

sys.path.insert(0, "research"); sys.path.insert(0, "research/v38")
sys.path.insert(0, "research/v51"); sys.path.insert(0, "research/v52")
import v52feat as V     # noqa: E402
import run_v52 as RUN   # noqa: E402


def reference(P, cost, slip, en, xn, sn, ma, cx, ab, adx, ext, ss, cut):
    bars = np.flatnonzero(V.entry_mask(P, en))
    MA, CX, AB, SS, AD, EX = V.filter_masks(P, bars)
    keep = MA[ma] & CX[cx] & AB[ab] & AD[adx] & EX[ext] & SS[ss]
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
        fixed = px - sn * atr[i]
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
            s += (out - px - cost) / (sn * atr[i])
    return n, (s / n if n else np.nan)


def main():
    bad = 0
    for market, tf in (("US100L", 240), ("US30L", 120)):
        P = V.build(market, tf)
        ck = V.COSTS[market]
        cut = int(P["n"] * RUN.SPLIT)
        D = RUN.sweep(market, tf)
        for pick in [(20, 10, 2.0, 0, 0, 0, 0, 0, 0), (20, 10, 2.0, 0, 0, 0, 1, 1, 0),
                     (55, 20, 2.5, 4, 1, 4, 2, 2, 0), (20, 20, 1.5, 1, 3, 11, 3, 3, 3),
                     (55, 10, 3.0, 3, 0, 0, 1, 1, 8)]:
            en, xn, sn, ma, cx, ab, adx, ext, ss = pick
            row = D[(D.entN == en) & (D.exitN == xn) & (D.stopN == sn) & (D.ma == ma)
                    & (D.cx == cx) & (D.ab == ab) & (D.adx == adx) & (D.ext == ext) & (D.ss == ss)]
            assert len(row) == 1, (pick, len(row))
            rn, rR = reference(P, ck["cost"], ck["slip"], en, xn, sn, ma, cx, ab, adx, ext, ss, cut)
            tn, tR = int(row.n.iloc[0]), float(row.R.iloc[0])
            ok = (rn == tn) and (not np.isfinite(rR) or abs(rR - tR) < 1e-9)
            bad += 0 if ok else 1
            print(f"  {market:>6} {tf:>3}m ent{en:>3} exit{xn:>3} stop{sn} "
                  f"adx={V.ADX_MODES[adx]:<22} ext={V.EXT_MODES[ext]:<28} ss={ss}  "
                  f"n {rn:>5} vs {tn:>5}  R {rR:+.6f} vs {tR:+.6f}  {'ok' if ok else 'MISMATCH'}")
    print(f"\n  {'ALL MATCH -- V52 kernel verified' if bad == 0 else str(bad) + ' MISMATCHES'}")
    return bad


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
