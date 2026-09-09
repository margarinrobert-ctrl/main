"""V1 -- audit, base rates, then Gate 1 on the book's two tradeable primaries."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vpus30 import vpcore as V  # noqa: E402

pd.set_option("display.width", 210)
BAR = "=" * 104


def hdr(t):
    print("\n" + BAR + "\n" + t + "\n" + BAR)


def main():
    f = V.load()
    d = V.sessions(f)
    g = V.features(f, d)
    sess = np.sort(d.sess.unique())
    cut = pd.Timestamp(sess[int(0.75 * len(sess))])
    print(f"  US30 15m, RTH 09:30-16:00 NY   {len(g):,} bars over {len(d):,} sessions")
    print(f"  split {str(cut)[:10]}   (last 25% of sessions held out)")

    hdr("V1.0  TRUNCATION AUDIT -- rebuild the profile on history ENDING at session X")
    ok = 0
    for X in (500, 1200, 1900):
        dt = V.sessions(f[f["sess"] <= sess[X]])
        a = d[d.sess <= sess[X - 3]].reset_index(drop=True)
        b = dt[dt.sess <= sess[X - 3]].reset_index(drop=True)
        cols = ["poc", "vah", "val", "lo", "hi", "n_hvn", "n_lvn"]
        same = len(a) == len(b) and bool(np.allclose(a[cols].to_numpy(), b[cols].to_numpy()))
        ok += int(same)
        print(f"  ends at session {X:>5} ({str(sess[X])[:10]})   profiles {len(a):>5} vs {len(b):>5}"
              f"   identical {same}")
    print(f"  AUDIT: {ok}/3 clean")

    hdr("V1.1  BASE RATES ON THE TRIGGER'S OWN BARS -- is any feature the trigger restated?")
    print("  CLAUDE.md's rule: compute this BEFORE any P&L. A condition passing >95% of the")
    print("  trigger's bars is the trigger wearing another name.\n")
    for kind in ("hvn", "lvn"):
        idx, side = V.events(g, kind)
        print(f"  {kind.upper()}  events {len(idx):,}  ({len(idx)/ (len(sess)/252):.0f}/yr)")
        sub = g.iloc[idx]
        print(f"    {'feature':<12}{'pass rate on trigger bars':>28}{'on all bars':>14}{'lift':>8}")
        for nm, cond in (("above_va", sub.above_va > 0), ("below_va", sub.below_va > 0),
                         ("inside_va", sub.inside_va > 0), ("p_bull", sub.p_bull > 0),
                         ("p_neut", sub.p_neut > 0), ("stack5>=1", sub.stack5 >= 1)):
            allc = {"above_va": g.above_va > 0, "below_va": g.below_va > 0,
                    "inside_va": g.inside_va > 0, "p_bull": g.p_bull > 0,
                    "p_neut": g.p_neut > 0, "stack5>=1": g.stack5 >= 1}[nm]
            a1 = float(cond.mean()); a2 = float(allc.mean())
            print(f"    {nm:<12}{a1:>28.4f}{a2:>14.4f}{a1/max(a2,1e-9):>8.2f}")
        print()

    hdr("V1.2  GATE 1 -- the raw primary, costs in, against a RISK-MATCHED random entry")
    print("  Geometry declared: stop 1.5 x ATR(14), no target, flat at the RTH close, one live")
    print("  position, 2.29 pts round turn. Control: random RTH bar, same side mix, same risk.\n")
    print(f"  {'primary':<8}{'block':<10}{'n':>7}{'win':>8}{'PF':>8}{'grossPF':>9}{'%/trade':>10}"
          f"{'total%':>10}{'cost/risk':>11}{'ctl PF':>9}{'p':>7}")
    rng = np.random.default_rng(0)
    o = g["open"].to_numpy(); h = g["high"].to_numpy(); l = g["low"].to_numpy()
    c = g["close"].to_numpy(); at = g["atr"].to_numpy(); bar = g["bar_in_sess"].to_numpy()
    for kind in ("hvn", "lvn"):
        idx, side = V.events(g, kind)
        t = V.walk(g, idx, side)
        for bl, sel in (("research", pd.DatetimeIndex(t.ts) < cut),
                        ("HOLDOUT", pd.DatetimeIndex(t.ts) >= cut)):
            x = t[sel]
            if len(x) < 20:
                continue
            pool = np.flatnonzero((bar >= 2) & np.isfinite(at) &
                                  ((g.index < cut) if bl == "research" else (g.index >= cut)))
            cps = []
            for sd in range(50):
                ii = np.sort(rng.choice(pool, size=min(len(x), len(pool)), replace=False))
                ss = rng.permutation(x.side.to_numpy())[:len(ii)]
                cc = V.walk(g, ii, ss)
                cps.append(V.pf(cc))
            cps = np.array(cps)
            print(f"  {kind.upper():<8}{bl:<10}{len(x):>7}{float((x.pct>0).mean()):>8.4f}"
                  f"{V.pf(x):>8.3f}{V.pf(x,'gross_pct'):>9.3f}{x.pct.mean():>+10.5f}"
                  f"{x.pct.sum():>+10.2f}{x.cost_frac.median():>11.4f}"
                  f"{np.nanmean(cps):>9.3f}{float(np.nanmean(cps >= V.pf(x))):>7.3f}")
        print()


if __name__ == "__main__":
    main()
