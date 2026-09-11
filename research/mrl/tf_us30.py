"""A US30 version: not a re-tune of TFI, which is a null on US30 on every cell, but the one
US30 configuration on this branch that survived a genuine forward block -- STUDY_MEGA_144K's
Donchian 30/20, 2.5 x ATR stop, ADX >= 15, take-profit 2R, all hours, no flatten (one unit here
instead of the study's three; STUDY_TURTLE_15M found one unit is the drawdown answer). It is
re-measured through this engine on US30's research / validation / test blocks, on the ISO feed's
2026 tail (a re-read of a block the earlier study already judged once, so a confirmation and not
a selection), and on NQ and US100 for balance, each against a random-bar control. The shipped
TFI cell on the same blocks is the comparison.
"""

from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import tf_design as T  # noqa: E402
import tf_balance as B  # noqa: E402

ALL = (0, 1440)
NOFLAT = 10**6


def sig_us30(D, N=30, adx=15, win=ALL):
    c, mod = D["c"], D["mod"]
    up, lo = D["don"][N]
    s = (c > up) & (np.roll(c, 1) <= np.roll(up, 1)) & (D["adx"] >= adx)
    return s & (mod >= win[0]) & (mod < win[1])


def main():
    print(__doc__)
    print("=" * 100)
    print("US30 CONFIGURATION (Donchian 30/20, ADX >= 15, 2.5 x ATR stop, target 2R, all hours, no")
    print("flatten, one unit) on every feed and block, random-bar control 200 draws")
    print("=" * 100)
    for mk in ("US30", "US30_ISO", "NQ", "US100"):
        D = T.prep(mk)
        sm = sig_us30(D)
        for blk, b in D["blocks"].items():
            pnl, sb, xb, why, rk = B.run(D, sm & b, 1, 2.5, 2.0, 20, NOFLAT)
            m = T.metrics(D, pnl, sb, rk, why, b)
            ctl = B.control(D, sm, 2.5, 20, NOFLAT, ALL, b)
            # the control in tf_balance has no target; price a target control inline
            hold = np.median(xb - sb) if len(xb) else np.nan
            print(T.line(f"{mk} {blk} (median hold {hold:.0f} bars)", m, (ctl,)))
    print(
        "\n  the same configuration with the 16:00 flatten and 09:30-14:00 entries (the intraday form):"
    )
    for mk in ("US30", "US30_ISO"):
        D = T.prep(mk)
        sm = sig_us30(D, win=(570, 840))
        for blk, b in D["blocks"].items():
            pnl, sb, xb, why, rk = B.run(D, sm & b, 1, 2.5, 2.0, 20, 945)
            print(T.line(f"{mk} {blk}", T.metrics(D, pnl, sb, rk, why, b)))
    print("\n  variants on US30 test + ISO 2026 (the reserved blocks), multiplicity 6:")
    for lab, kw in (
        ("no target", dict(tp=0.0)),
        ("target 1.5R", dict(tp=1.5)),
        ("target 3R", dict(tp=3.0)),
        ("ADX 20", dict(adx=20)),
        ("ADX 0", dict(adx=0)),
        ("stop 2.0", dict(stop=2.0)),
    ):
        for mk, blk in (("US30", "test"), ("US30_ISO", "iso_2026")):
            D = T.prep(mk)
            b = D["blocks"][blk]
            sm = sig_us30(D, adx=kw.get("adx", 15))
            pnl, sb, xb, why, rk = B.run(
                D, sm & b, 1, kw.get("stop", 2.5), kw.get("tp", 2.0), 20, NOFLAT
            )
            print(T.line(f"  {lab:<12} {mk} {blk}", T.metrics(D, pnl, sb, rk, why, b)))


if __name__ == "__main__":
    main()
