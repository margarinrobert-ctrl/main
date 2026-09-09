"""V3 -- Gate 1 on all five primaries, including the three the US30 study guide names."""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vpus30 import vpcore as V  # noqa: E402
pd.set_option("display.width", 210)


def main():
    f = V.load(); d = V.sessions(f); g = V.features(f, d)
    sess = np.sort(d.sess.unique()); cut = pd.Timestamp(sess[int(0.75 * len(sess))])
    at = g["atr"].to_numpy(); bar = g["bar_in_sess"].to_numpy()
    rng = np.random.default_rng(0)
    print("=" * 104)
    print("GATE 1 -- five primaries, stop 1.5xATR, no target, flat at the RTH close, 2.29 pts RT")
    print("Control: 50 random RTH bars, same side mix, same risk, re-simulated with the same lock")
    print("=" * 104)
    print(f"  {'primary':<12}{'block':<10}{'n':>7}{'/yr':>6}{'win':>8}{'PF':>8}{'grossPF':>9}"
          f"{'%/trade':>10}{'total%':>9}{'ctlPF':>8}{'p':>7}")
    yrs = len(sess) / 252.0
    for nm, ev in (("HVN", lambda: V.events(g, "hvn")),
                   ("LVN", lambda: V.events(g, "lvn")),
                   ("POCSHIFT", lambda: V.events_guide(f, g, d, "pocshift")),
                   ("NAKEDPOC", lambda: V.events_guide(f, g, d, "nakedpoc")),
                   ("OPENREJ", lambda: V.events_guide(f, g, d, "openrej"))):
        idx, side = ev()
        if len(idx) < 40:
            print(f"  {nm:<12}{'--':<10}{len(idx):>7}   too few events")
            continue
        t = V.walk(g, idx, side)
        for bl, sel in (("research", pd.DatetimeIndex(t.ts) < cut),
                        ("HOLDOUT", pd.DatetimeIndex(t.ts) >= cut)):
            x = t[sel]
            if len(x) < 20:
                print(f"  {nm:<12}{bl:<10}{len(x):>7}   too few")
                continue
            pool = np.flatnonzero((bar >= 2) & np.isfinite(at) &
                                  ((g.index < cut) if bl == "research" else (g.index >= cut)))
            cps = [V.pf(V.walk(g, np.sort(rng.choice(pool, size=min(len(x), len(pool)),
                                                     replace=False)),
                               rng.permutation(x.side.to_numpy())[:min(len(x), len(pool))]))
                   for _ in range(50)]
            cps = np.array(cps, dtype=float)
            yy = yrs * (0.75 if bl == "research" else 0.25)
            print(f"  {nm:<12}{bl:<10}{len(x):>7}{len(x)/yy:>6.0f}"
                  f"{float((x.pct>0).mean()):>8.4f}{V.pf(x):>8.3f}{V.pf(x,'gross_pct'):>9.3f}"
                  f"{x.pct.mean():>+10.5f}{x.pct.sum():>+9.2f}{np.nanmean(cps):>8.3f}"
                  f"{float(np.nanmean(cps >= V.pf(x))):>7.3f}")
        print()


if __name__ == "__main__":
    main()
