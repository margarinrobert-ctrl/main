"""B1 -- detection only. How many setups exist, and what does the unspecified EXPIRY cost?

No P&L here. The spec leaves the zone lifetime open, so this measures what each value is worth in
events before anything is fixed, and reports the diagnostics that decide whether the study is
runnable at all: the order-block search cap, the step-by-step attrition, and the risk the geometry
implies against a fixed 1.72-point round turn.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from breaker import bbcore as B  # noqa: E402

pd.set_option("display.width", 200)
BAR = "=" * 100


def hdr(t):
    print("\n" + BAR + "\n" + t + "\n" + BAR)


def main():
    f = B.load()
    a = B.atr(f)
    print(f"  bars {len(f):,}   {f.index[0]} -> {f.index[-1]}   (New York)")
    print(f"  ATR(20) points: p10 {np.nanpercentile(a,10):.2f}  median {np.nanmedian(a):.2f}  "
          f"p90 {np.nanpercentile(a,90):.2f}")

    hdr("B1.1  EVENT COUNT vs the EXPIRY the spec does not fix")
    print("  EXPIRY caps three waits at once: order block -> sweep, sweep -> violation,")
    print("  violation -> entry. Every value is run; none is chosen here.\n")
    print(f"  {'expiry (min)':<14}{'long':>8}{'short':>8}{'total':>8}{'per year':>10}"
          f"{'OB search capped':>18}")
    keep = {}
    for e in (30, 60, 120, 240, 480, 1440):
        L = B.detect(f, a, e, +1)
        S = B.detect(f, a, e, -1)
        keep[e] = (L, S)
        tot = len(L) + len(S)
        yrs = (f.index[-1] - f.index[0]).days / 365.25
        cap = pd.concat([L, S]).ob_capped.mean() if tot else np.nan
        print(f"  {e:<14}{len(L):>8}{len(S):>8}{tot:>8}{tot/yrs:>10.0f}{cap:>18.4f}")

    hdr("B1.2  ATTRITION -- where the four-way conjunction loses its candidates (expiry 240)")
    o = f["open"].to_numpy(); h = f["high"].to_numpy()
    l = f["low"].to_numpy(); c = f["close"].to_numpy()
    n = len(c)
    st = np.arange(n) - B.K_IMP
    ok = st >= 0
    disp = np.full(n, np.nan)
    disp[ok] = c[ok] - c[st[ok]]
    thr = np.full(n, np.nan)
    thr[ok] = B.M_IMP * a[st[ok]]
    n_up = int(np.nansum(disp >= thr))
    n_dn = int(np.nansum(disp <= -thr))
    print(f"  bars                                        {n:>10,}")
    print(f"  step 1  impulse >= {B.M_IMP} x ATR20 in {B.K_IMP} bars   "
          f"up {n_up:>8,}   down {n_dn:>8,}   ({100*(n_up+n_dn)/n:.2f}% of bars)")
    for e in (240,):
        L, S = keep[e]
        print(f"  steps 2-5 survive to a triggered entry     long {len(L):>8,}   short {len(S):>8,}")
        print(f"  (an order block is counted ONCE -- overlapping impulses re-detecting the same")
        print(f"   block are collapsed, which is why the drop is this large)")

    hdr("B1.3  THE GEOMETRY, AND WHAT A 1.72-POINT ROUND TURN IS AGAINST IT (expiry 240)")
    print("  This is the number that usually decides an intraday family on this branch.\n")
    print(f"  {'side':<8}{'n':>7}{'zone width':>13}{'risk (pts)':>12}{'risk %price':>13}"
          f"{'cost/risk':>11}{'BE win @2R':>12}")
    for lab, D in (("long", keep[240][0]), ("short", keep[240][1])):
        if not len(D):
            continue
        ob = D.ob.to_numpy()
        mid = 0.5 * (D.zlo.to_numpy() + D.zhi.to_numpy())
        buf = B.BUF_ATR * a[ob]
        far = D.zlo.to_numpy() - buf if lab == "long" else D.zhi.to_numpy() + buf
        risk = np.abs(mid - far)
        ent = o[np.minimum(D.trig.to_numpy() + 1, n - 1)]
        cf = B.RT_POINTS / risk
        be = (1.0 + np.median(cf)) / 3.0     # driftless break-even at 2R, cost in R
        print(f"  {lab:<8}{len(D):>7}{np.median(D.zhi-D.zlo):>13.2f}{np.median(risk):>12.2f}"
              f"{np.median(100*risk/ent):>13.4f}{np.median(cf):>11.3f}{be:>12.3f}")
    print("\n  BE win @2R is the DRIFTLESS break-even (1 + cost_in_R) / (1 + 2), not 33.3%.")


if __name__ == "__main__":
    main()
