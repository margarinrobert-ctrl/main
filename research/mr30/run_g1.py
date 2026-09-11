"""THE MIRROR, SPLIT BY SIDE -- the test that decides whether it is worth a story at all.

`run_g0` killed the fade: every declared cell negative before any barrier, and the mechanism's own
conditioning variable (|d|, which flow is proportional to) running the WRONG WAY in 7 of 8 gradient
cells. That is the levered-ETF verdict reached in one run, and it CLOSES mean reversion as a US30
primary at 15 minutes.

Its mirror -- displacement CONTINUES -- reads +0.088 ATR at h=16 with a monotone quintile gradient.
This is the SECOND OF TWO LOOKS and is recorded, not adopted (`STUDY_LEV_ETF_REBALANCE`: writing a
new mechanism story around a side flip is exactly the failure the architecture exists to prevent).
Before any story could be written it has to survive the one thing this sample makes most likely:
US30 rose 144% over it, the unconditional 16-bar drift is +0.098 ATR at t 3.2, and a rule signed by
`sign(d)` is long whenever d > 0.

So: split by side, and give each side ITS OWN drift baseline -- an up-displacement must beat +drift
and a down-displacement must beat -drift. If continuation is positive on ONE side only, it is the
drift and there is nothing here.
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mr30 import mr30core as M  # noqa: E402
from mr30.run_g0 import fwd_atr, nw_t  # noqa: E402

HOR = (4, 8, 16, 32)
NS = (2, 4, 8, 16)
KS = (1.5, 2.5)


def main():
    f = M.load("US30L")
    blk = M.blocks(f)
    print("THE MIRROR SPLIT BY SIDE, research block. Continuation = sign(d) x forward return, ATR.")
    print("Each side is scored against ITS OWN drift baseline (long +mu, short -mu).")
    for h in HOR:
        fw = fwd_atr(f, h)
        mu = float(np.nanmean(fw[blk["A_research"] & np.isfinite(fw)]))
        print(f"\n  h={h}  unconditional drift {mu:+.4f} ATR  "
              f"(so a long must beat {mu:+.4f} and a short must beat {-mu:+.4f})")
        print(f"    {'cell':<18}{'LONG (d>0)':>22}{'excess':>9}"
              f"{'SHORT (d<0)':>22}{'excess':>9}{'both>0?':>9}")
        for n in NS:
            d = M.displacement(f, n)
            for k in KS:
                sel = blk["A_research"] & np.isfinite(d) & np.isfinite(fw) & (np.abs(d) >= k)
                up = sel & (d > 0)
                dn = sel & (d < 0)
                lu = float(np.mean(fw[up])); ld = float(np.mean(-fw[dn]))
                eu, ed = lu - mu, ld + mu
                ok = "yes" if (eu > 0 and ed > 0) else "no"
                print(f"    n={n:<3d} |d|>={k:<4.1f}"
                      f"{lu:>12.4f}{nw_t(fw[up], h):>7.1f}{f'({int(up.sum())})':>3}{eu:>9.4f}"
                      f"{ld:>12.4f}{nw_t(-fw[dn], h):>7.1f}{f'({int(dn.sum())})':>3}{ed:>9.4f}"
                      f"{ok:>9}")

    print("\nAND THE SAME READ ON THE HOLDOUT, so the shape can be seen (not a selection):")
    fw = fwd_atr(f, 16)
    for nm, m0 in blk.items():
        mu = float(np.nanmean(fw[m0 & np.isfinite(fw)]))
        d = M.displacement(f, 16)
        sel = m0 & np.isfinite(d) & np.isfinite(fw) & (np.abs(d) >= 1.5)
        up, dn = sel & (d > 0), sel & (d < 0)
        print(f"  {nm:<12} drift {mu:+.4f}   long {np.mean(fw[up]):+.4f} "
              f"(excess {np.mean(fw[up]) - mu:+.4f}, n={int(up.sum())})   "
              f"short {np.mean(-fw[dn]):+.4f} (excess {np.mean(-fw[dn]) + mu:+.4f}, "
              f"n={int(dn.sum())})")


if __name__ == "__main__":
    main()
