"""V42 -- what the shipped Pine can and cannot reproduce, measured rather than asserted.

SCOPE, STATED HONESTLY. This harness does TWO things and deliberately not a third:

  1. TRANSCRIPTION CHECK. It rebuilds each preset's signal conditions -- the two Donchian
     channels, the ADX gate, the EMA100-distance gate, the timeframe -- independently of
     `core.prep`, and diffs the resulting eligible-bar sets against the ones the engine used.
     If the rules in the Pine are the rules that produced the research, these agree exactly.

  2. NAKED-ENTRY-BAR EXPOSURE. `STUDY_PINE_PARITY` measured the one order-model gap this family
     has: the Turtle script anchors its stop to `strategy.opentrades.entry_price()`, which is only
     known at the CLOSE of the fill bar, so no exit order is live DURING that bar. That study put
     it at 4.4-13.0% of trades averaging -33 to -118 points. This harness counts, per preset, the
     trades whose exit lands on the fill bar itself -- the population that gap can touch.

  WHAT IS NOT DONE: the delayed-stop state machine is NOT re-implemented. `core.run`'s kernel is
  the Turtle ladder with re-anchoring, and a second hand-written copy of it would be a new source
  of error rather than a check on an old one. So the P&L impact of gap 2 is quoted from the study
  that measured it, not re-derived here, and this file says so rather than implying a full parity
  run took place.

Usage: python3 research/v42/pine_parity.py
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/turtle")
sys.path.insert(0, "research/v38"); sys.path.insert(0, "research/v42")
import indicators as I       # noqa: E402
import v42grid as G          # noqa: E402
from run_v42c import prep_any            # noqa: E402

CANDS = {
    "TOP-MEDIAN":    dict(tf=240, entry1=40, entry2=40, exit1=5,  exit2=30, atr_mult=2.0,
                          pyr=0.25, units=4, adx="adx>=20", ext="ext<3.193", skip=True),
    "SURROGATE":     dict(tf=240, entry1=40, entry2=40, exit1=20, exit2=30, atr_mult=2.0,
                          pyr=0.25, units=4, adx="adx<22",  ext="ext<3.964", skip=False),
    "NEIGHBOURHOOD": dict(tf=240, entry1=40, entry2=40, exit1=20, exit2=30, atr_mult=2.0,
                          pyr=0.25, units=4, adx="adx>=20", ext="ext<3.964", skip=True),
    "SPEC (T1)":     dict(tf=240, entry1=20, entry2=55, exit1=10, exit2=20, atr_mult=2.0,
                          pyr=0.5,  units=4, adx="adx<22",  ext="ext<3.964", skip=True),
}


def pine_side(P, cfg):
    """The gate and channels as the PINE computes them, rebuilt from raw OHLC.

    ta.atr(20) == rma(TR,20); ta.dmi(14,14)[2] == adx_di(...,14)[0]; ta.highest(high,n)[1] is the
    prior n-bar high. Every one of those is recomputed here rather than reused from `core.prep`,
    so agreement is evidence and not a tautology."""
    h, l, c = P["h"], P["l"], P["c"]
    atr = I.rma(I.true_range(h, l, c), 20)
    adx, _p, _m = I.adx_di(h, l, c, 14)
    ema100 = I.ema(c, 100)
    with np.errstate(divide="ignore", invalid="ignore"):
        ext = np.where(atr > 0, (c - ema100) / atr, 0.0)
    ga = (np.ones(len(c), bool) if cfg["adx"] == "off" else
          adx < 22.0 if cfg["adx"] == "adx<22" else
          adx >= 20.0 if cfg["adx"] == "adx>=20" else adx >= 25.0)
    ge = (np.ones(len(c), bool) if cfg["ext"] == "off" else
          ext < 3.193 if cfg["ext"] == "ext<3.193" else
          ext < 3.964 if cfg["ext"] == "ext<3.964" else ext >= 3.0)
    gate = ga & ge & np.isfinite(atr) & (atr > 0)
    hi1 = I.shift(I.rmax(h, cfg["entry1"]), 1)
    hi2 = I.shift(I.rmax(h, cfg["entry2"]), 1)
    return gate, hi1, hi2


def main():
    print("=" * 122)
    print("V42 PINE PARITY -- rules verified against the engine; the order-model gap quantified")
    print("=" * 122)
    print("   US100 240-minute, the block the presets were selected on.\n")
    rows = []
    for nm, cfg in CANDS.items():
        P = prep_any("US100", cfg["tf"])
        g_pine, hi1_p, hi2_p = pine_side(P, cfg)
        g_eng = P["gate"][(cfg["adx"], cfg["ext"])]
        hi1_e, hi2_e = P["hi"][cfg["entry1"]], P["hi"][cfg["entry2"]]
        gate_match = float((g_pine == g_eng).mean())
        fin = np.isfinite(hi1_e) & np.isfinite(hi1_p)
        hi1_match = float(np.allclose(hi1_p[fin], hi1_e[fin]))
        fin2 = np.isfinite(hi2_e) & np.isfinite(hi2_p)
        hi2_match = float(np.allclose(hi2_p[fin2], hi2_e[fin2]))

        pnl, risk, tin = G.run_cell(P, cfg)
        # the engine records bar_in; recover exits by re-running for bar_out
        import core
        _p, _r, _u, _sy, _w, bi, bo, _mfe, _mae = core.run(
            P["o"], P["h"], P["l"], P["c"], hi1_e, hi2_e,
            P["lo"][cfg["exit1"]], P["lo"][cfg["exit2"]], P["atr"], 120,
            float(cfg["atr_mult"]), float(cfg["pyr"]), int(cfg["units"]),
            bool(cfg["skip"]), True, True,
            P["cost"]["cost_pts"], P["cost"]["slip_pts"], g_eng, True)
        same_bar = float((bo == bi + 1).mean()) if len(bi) else np.nan
        print(f"   {nm}")
        print(f"      gate bars identical      {gate_match:>8.4%}   "
              f"({int((g_pine != g_eng).sum())} of {len(g_pine)} bars differ)")
        print(f"      entry channel 1 identical{'  yes' if hi1_match else '   NO':>9}"
              f"      entry channel 2 identical{'  yes' if hi2_match else '   NO':>9}")
        print(f"      trades exiting on the FILL BAR: {same_bar:>6.1%} of {len(bi)}  "
              f"<- the population the naked-entry-bar gap can touch\n")
        rows.append(dict(cand=nm, gate_match=gate_match, hi1=bool(hi1_match),
                         hi2=bool(hi2_match), n=len(bi), fill_bar_exits=same_bar))
    T = pd.DataFrame(rows)
    T.to_csv("results/v42/v42_pine_parity.csv", index=False)
    ok = bool((T.gate_match == 1.0).all() and T.hi1.all() and T.hi2.all())
    print("=" * 122)
    print(f"   TRANSCRIPTION: {'ALL RULES MATCH EXACTLY' if ok else 'A RULE DIFFERS -- do not ship'}")
    print(f"   ORDER MODEL:   not re-implemented here. STUDY_PINE_PARITY measured the naked "
          f"entry bar at\n                  4.4-13.0% of trades averaging -33 to -118 points; the "
          f"exposed share above\n                  is this family's own count of trades that could "
          f"be affected.")


if __name__ == "__main__":
    main()
