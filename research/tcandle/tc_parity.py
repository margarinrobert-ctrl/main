"""The shipped Pine's candlestick expressions, rebuilt in Python and diffed against tc_feat.

A Pine port cannot be asserted by reading it.  This transcribes the SCRIPT'S OWN expressions --
including its `math.max(high - low, mintick/100)` range floor, which differs from the research's
1e-12 -- and requires them to agree with the feature module bar for bar.  It is how the first draft
was caught defining `threeW` with only the current bar's body share where the research requires all
three bodies to be majority-body.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research/tcandle")
import tc_core as T, tc_feat as CF                      # noqa: E402

MINTICK = {"NQ": 0.25, "US100L": 0.25, "US30L": 1.0, "US30I": 1.0}


def pine_side(d, mintick):
    """Exactly what the script computes, in the script's own order."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    rng = np.maximum(h - l, mintick / 100.0)
    body = np.abs(c - o)
    up_w = h - np.maximum(o, c)
    lo_w = np.minimum(o, c) - l
    body_shr = body / rng
    close_pos = (c - l) / rng
    up_shr = up_w / rng
    is_up = c > o

    def s(a, k=1):
        out = np.full(len(c), np.nan)
        out[k:] = a[:-k]
        return out

    o1, c1 = s(o), s(c)
    o2, c2 = s(o, 2), s(c, 2)
    h1, l1 = s(h), s(l)
    engulf = is_up & (c1 < o1) & (c >= o1) & (o <= c1)
    outside = (h > h1) & (l < l1)
    rng1 = np.maximum(s(h) - s(l), mintick / 100.0)
    rng2 = np.maximum(s(h, 2) - s(l, 2), mintick / 100.0)
    three_w = (is_up & (c1 > o1) & (c2 > o2) & (c > c1) & (c1 > c2)
               & (body_shr >= 0.5) & (np.abs(c1 - o1) >= 0.5 * rng1)
               & (np.abs(c2 - o2) >= 0.5 * rng2))
    spin = (body_shr <= 0.30) & (up_w >= 0.25 * rng) & (lo_w >= 0.25 * rng)
    shoot = (body <= 0.35 * rng) & (up_w >= 2.0 * body) & (lo_w <= 0.20 * rng) & (c1 < c)
    return dict(body_shr=body_shr, close_pos=close_pos, up_shr=up_shr, engulf=engulf,
                outside=outside, three_w=three_w, spin=spin, shoot=shoot)


PAIRS = [("body_shr", "shp.body_share"), ("close_pos", "shp.close_pos"),
         ("up_shr", "shp.upper_share"), ("engulf", "p2.engulf_bull"),
         ("outside", "p2.outside_bar"), ("three_w", "p3.three_white"),
         ("spin", "p1.spinning_top"), ("shoot", "p1.shooting_star")]


if __name__ == "__main__":
    ok = True
    for mkt, tf in (("NQ", 240), ("NQ", 60), ("US100L", 60), ("US30L", 120)):
        d = T.frame(mkt, tf)
        atr, _, _ = T.context(d)
        F = CF.build(d, atr)
        P = pine_side(d, MINTICK[mkt])
        sig = T.signal_bars(d, T.channels(d, 20, 55, 10, 20), np.isfinite(atr) & (atr > 0), atr)
        print(f"--- {mkt} {tf}m   {len(d['c'])} bars, {len(sig)} signal bars")
        for pk, fk in PAIRS:
            a, b = P[pk].astype(float), np.nan_to_num(F[fk], nan=0.0)
            m = np.isfinite(a) & np.isfinite(b)
            m[:3] = False
            if set(np.unique(b[m]).tolist()) <= {0.0, 1.0}:
                dis = int((a[m] != b[m]).sum())
                note = f"{dis} disagreements of {int(m.sum())}"
                ok &= dis == 0
            else:
                mx = float(np.nanmax(np.abs(a[m] - b[m])))
                note = f"max |diff| {mx:.3e}"
                ok &= mx < 1e-6
            print(f"    {pk:<10} vs {fk:<20} {note}")
        zr = int((d["h"][3:] - d["l"][3:] <= 0).sum())
        print(f"    zero-range bars (where the two range floors could differ): {zr}")
    print("\nPARITY", "OK" if ok else "FAILED")
