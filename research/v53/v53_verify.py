"""Verify V53's grid against an independent plain-Python simulation before anything is read."""
from __future__ import annotations
import sys
import numpy as np

sys.path.insert(0, "research"); sys.path.insert(0, "research/v51"); sys.path.insert(0, "research/v53")
import v53abs as A      # noqa: E402
import run_v53 as R     # noqa: E402


def reference(P, en, xn, sn, ma, cx, ab, cut, tf):
    bars = np.flatnonzero(R.entry_mask(P, en))
    MA, CX, AB, _SS = R.masks(P, bars, tf)
    keep = MA[ma] & CX[cx] & AB[ab]
    o, h, l, c, atr = P["o"], P["h"], P["l"], P["c"], P["atr"]
    elo = P["exit_lo"][xn]
    m = len(c)
    free, n, s = -1, 0, 0.0
    for k, i in enumerate(bars):
        if not keep[k] or i < free:
            continue
        a = i + 1
        if a >= m - 1 or not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        px = o[a] + R.SLIP
        fixed = px - sn * atr[i]
        end = min(a + R.MAX_HOLD, m - 2)
        out, j = None, a
        while j <= end:
            lvl = fixed
            if np.isfinite(elo[j]) and elo[j] > lvl:
                lvl = elo[j]
            lvl = min(lvl, c[j - 1])
            if l[j] <= lvl:
                out = (lvl if o[j] > lvl else o[j]) - R.SLIP
                break
            j += 1
        if out is None:
            j = end
            out = c[j] - R.SLIP
        free = j
        if i < cut:
            n += 1
            s += (out - px - R.COST) / (sn * atr[i])
    return n, (s / n if n else np.nan)


def main():
    f1 = A.load_1m()
    bad = 0
    for tf in (15, 60):
        P = R.build(f1, tf)
        cut = int(P["n"] * R.SPLIT)
        D = R.sweep(f1, tf)
        for (en, xn, sn, ma, cx, ab) in [(20, 10, 2.0, 0, 0, 0), (30, 20, 2.5, 3, 1, 0),
                                         (20, 20, 2.0, 0, 0, 1), (55, 30, 3.0, 1, 2, 40),
                                         (10, 5, 1.5, 4, 1, 25)]:
            row = D[(D.entN == en) & (D.exitN == xn) & (D.stopN == sn) & (D.ma == ma)
                    & (D.cx == cx) & (D.ab == ab)]
            assert len(row) == 1
            rn, rR = reference(P, en, xn, sn, ma, cx, ab, cut, tf)
            tn, tR = int(row.n.iloc[0]), float(row.R.iloc[0])
            ok = (rn == tn) and (not np.isfinite(rR) or abs(rR - tR) < 1e-9)
            bad += 0 if ok else 1
            print(f"  NQ {tf:>3}m ent{en:>3} exit{xn:>3} stop{sn} ma={R.MA_MODES[ma]:<18} "
                  f"cx={R.CX_MODES[cx]:<15} ab={R.ABS_MODES[ab][0]:<22} "
                  f"n {rn:>5} vs {tn:>5}  R {rR:+.6f} vs {tR:+.6f}  {'ok' if ok else 'MISMATCH'}")
    print(f"\n  {'ALL MATCH -- V53 grid verified' if bad == 0 else str(bad) + ' MISMATCHES'}")
    return bad


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
