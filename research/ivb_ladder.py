"""The component ladder: does each piece of IVB actually add an edge, or just look better?

The specification asks for exactly this test -- IVB alone, IVB + retest, IVB + retest + trend --
so that is what runs first, before any parameter search. Their recommended geometry: a 09:30-10:30
initial value, a close beyond IVH/IVL, a retest that holds, a stop below the retest low, and a
target of 1.5-2x the initial range.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
from bos_choch import prep
from ivb import session_context, run

TFS = {5: None, 15: None, 30: None}
CTX = {}
CUT = None


def setup(tf, iv_min):
    global CUT
    key = (tf, iv_min)
    if key not in CTX:
        d = prep(tf)
        us, poc, vah, val, ivh, ivl, pct, trend = session_context(iv_min)
        idx = {s: i for i, s in enumerate(us)}
        sidx = np.array([idx.get(s, -1) for s in d["sess"]], np.int64)
        CTX[key] = (d, us, poc, vah, val, ivh, ivl, pct, trend, sidx)
        CUT = int(0.65 * len(us))
    return CTX[key]


def go(tf=30, iv_min=60, use_ib=1, entry_mode=1, stop_mode=3, atr_mult=1.5,
       tgt_mode=1, tp=1.5, buf_atr=0.0, trend_mode=0, rng_filter=0,
       flat_min=945, side_mode=0):
    d, us, poc, vah, val, ivh, ivl, pct, trend, sidx = setup(tf, iv_min)
    out = np.zeros((1, 20))
    run(d["o"], d["h"], d["l"], d["c"], d["mod"].astype(np.int64), sidx, d["atr"],
        vah, val, poc, ivh, ivl, pct, trend,
        iv_min, use_ib, entry_mode, stop_mode, atr_mult, tgt_mode, tp,
        buf_atr, trend_mode, rng_filter, flat_min, side_mode, CUT, out, 0)
    r = out[0]
    n = r[0] + r[7]
    if n == 0:
        return None
    net = r[1] + r[8]; w = r[2] + r[9]; gwv = r[3] + r[10]; glv = r[4] + r[11]
    return dict(n=int(n), net=net, pf=gwv / glv if glv > 0 else np.inf,
                win=100 * w / n, res=r[1], lock=r[8], nres=int(r[0]), nlock=int(r[7]),
                dd=max(r[5], r[12]),
                why=r[14:17].copy(), whyw=r[17:20].copy())


W = 104
H = (f"   {'':<44}{'n':>5}{'net $':>10}{'PF':>6}{'win%':>7}{'research':>10}"
     f"{'LOCKED':>10}{'maxDD':>9}")


def line(tag, r):
    if r is None or r["n"] == 0:
        return f"   {tag:<44}  (no trades)"
    return (f"   {tag:<44}{r['n']:>5}{r['net']:>10,.0f}{r['pf']:>6.2f}{r['win']:>7.1f}"
            f"{r['res']:>10,.0f}{r['lock']:>10,.0f}{r['dd']:>9,.0f}")


if __name__ == "__main__":
    print("=" * W)
    print("THE COMPONENT LADDER — 09:30-10:30 initial value, IVH/IVL, 30-minute bars")
    print("=" * W)
    print("   Target 1.5x the initial range, stop below the retest low, flat at 15:45, both sides.")
    print("   Each row adds ONE component to the row above it.\n")
    print(H)
    print(line("1. break and go at the next open",
               go(entry_mode=0, stop_mode=0, atr_mult=1.5)))
    print(line("2. ... wait for a retest of the level",
               go(entry_mode=1, stop_mode=0, atr_mult=1.5)))
    print(line("3. ... and stop below the retest bar",
               go(entry_mode=1, stop_mode=3)))
    print(line("4. ... and require the 60m trend to agree",
               go(entry_mode=1, stop_mode=3, trend_mode=1)))
    print(line("5. ... and only mid-sized opening ranges",
               go(entry_mode=1, stop_mode=3, trend_mode=1, rng_filter=1)))
    print()
    print("   the same ladder with a 2.0x range target:")
    print(H)
    for tag, kw in [("1. break and go", dict(entry_mode=0, stop_mode=0, atr_mult=1.5)),
                    ("2. + retest", dict(entry_mode=1, stop_mode=0, atr_mult=1.5)),
                    ("3. + structure stop", dict(entry_mode=1, stop_mode=3)),
                    ("4. + 60m trend agrees", dict(entry_mode=1, stop_mode=3, trend_mode=1)),
                    ("5. + range percentile 20-80", dict(entry_mode=1, stop_mode=3,
                                                         trend_mode=1, rng_filter=1))]:
        print(line(tag, go(tp=2.0, **kw)))
    print()
    print("=" * W)
    print("STRATEGY B — the failed breakout, which the specification flags as a second strategy")
    print("=" * W)
    print(H)
    for tp_ in (1.0, 1.5, 2.0):
        print(line(f"break, fail back inside, fade it  ({tp_:.1f}R)",
                   go(entry_mode=3, stop_mode=0, atr_mult=1.5, tgt_mode=0, tp=tp_)))
    print()
    print("=" * W)
    print("SECTION 10 — the volume-profile variant: break the VALUE AREA edge, not the high/low")
    print("=" * W)
    print(H)
    for ib, nm in ((1, "opening HIGH/LOW (IVH/IVL)"), (0, "opening VALUE AREA (VAH/VAL)")):
        print(line(f"{nm}  break and go", go(use_ib=ib, entry_mode=0, stop_mode=0, atr_mult=1.5)))
        print(line(f"{nm}  + retest", go(use_ib=ib, entry_mode=1, stop_mode=3)))
    print()
    print("=" * W)
    print("THE INITIAL VALUE WINDOW")
    print("=" * W)
    print(H)
    for iv in (15, 30, 60, 90):
        print(line(f"first {iv} minutes, break + retest",
                   go(iv_min=iv, entry_mode=1, stop_mode=3)))
