"""The one untested combination, before shipping a script: V22's adaptive stop on V24's winner.

V22 measured a volatility-adaptive stop (2.5N when the 20-bar realised-vol percentile is at or below
its 250-bar median, 1.5N above) on the PLAIN Donchian, with no CHOP filter. V24's best configuration
is the plain Donchian WITH CHOP <= 40 and a FLAT 2.0N stop. The two have never been run together,
which is a gap, not a judgement -- so it is closed here before either goes into a script.
"""
from __future__ import annotations

import sys
import numpy as np

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v21")
sys.path.insert(0, "research/v22")
sys.path.insert(0, "research/v24")
import v16core as C           # noqa: E402
import v21regime as RG        # noqa: E402
import v22vol as VV           # noqa: E402
import v24ma as V             # noqa: E402
from v22stop import STATE, merged   # noqa: E402

if __name__ == "__main__":
    for tf in (30, 15):
        P, sig, O, ch, res, lk = V.prep(tf)
        s = VV.build(P["o"], P["h"], P["l"], P["c"])[STATE][sig]
        good = np.isfinite(s)
        low = np.where(good, s <= 0.5, False)
        V.hdr(f"NQ {tf}m   V22's ADAPTIVE STOP ON V24's WINNER -- never run together before")
        print(f"   {'configuration':<42}{'RESEARCH':>28}{'|':>3}{'LOCKED':>36}")
        print(f"   {'':<42}{'n':>6}{'PF':>8}{'Shp':>7}{'DD':>7}{'|':>3}"
              f"{'n':>6}{'PF':>8}{'Shp':>7}{'R':>9}{'DD':>7}{'ret/DD':>7}")
        for lab, stop_lo, stop_hi, chop_max in (
                ("flat 2.0N, no CHOP", 2.0, 2.0, None),
                ("flat 2.0N + CHOP<=40   (V24 WINNER)", 2.0, 2.0, 40.0),
                ("ADAPTIVE 2.5/1.5, no CHOP  (V22)", 2.5, 1.5, None),
                ("ADAPTIVE 2.5/1.5 + CHOP<=40", 2.5, 1.5, 40.0),
                ("ADAPTIVE 2.5/2.0 + CHOP<=40", 2.5, 2.0, 40.0),
                ("ADAPTIVE 3.0/1.5 + CHOP<=40", 3.0, 1.5, 40.0),
                ("INVERSE 1.5/2.5 + CHOP<=40 (sign check)", 1.5, 2.5, 40.0)):
            M = merged(P, sig, stop_lo, stop_hi, low)
            cm = np.ones(len(sig), bool) if chop_max is None else (
                np.isfinite(ch) & (ch <= chop_max))
            line = f"   {lab:<42}"
            for blk in (res, lk):
                st = V.stat(P, M, cm & good & blk & (M["xb"] >= 0))
                if st is None:
                    line += f"{'--':>6}{'':>8}{'':>7}{'':>7}"
                elif blk is res:
                    line += f"{st['n']:>6}{st['pf']:>8.3f}{st['sharpe']:>7.2f}{st['dd']:>7.1f}"
                else:
                    line += (f"{st['n']:>6}{st['pf']:>8.3f}{st['sharpe']:>7.2f}"
                             f"{st['R']:>+9.4f}{st['dd']:>7.1f}{st['retdd']:>7.2f}")
                if blk is res:
                    line += f"{'|':>3}"
            print(line)
