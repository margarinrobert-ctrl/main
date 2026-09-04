"""Falsification test of the central claim on the SECOND instrument.

Claim: the Donchian breakout in 07:00-11:00 New York has no GROSS directional
edge. If US30 shows a gross edge where NAS shows none, the claim is
instrument-specific rather than structural, and must be narrowed.

Breakout events co-occur across the two instruments at only Jaccard 0.23-0.28
(indep.py), so this is real partial evidence, not a re-run.

Research blocks only. Both locked blocks untouched.
"""
import numpy as np, pandas as pd
from strategy import run
from control import matched_control
import lab

print("="*112)
print("CENTRAL-CLAIM FALSIFICATION: gross edge on BOTH instruments, research blocks only")
print("="*112)
for SYM in ("NAS", "US30"):
    df, w, res = lab.research(SYM)
    COST, SLIP = lab.COST[SYM], lab.SLIP[SYM]
    atr_med = np.nanmedian(lab.atr(df, 14)[res])
    print(f"\n  --- {SYM} ---  round turn {COST+2*SLIP:.2f} pts, median ATR {atr_med:.2f} pts"
          f"  (cost = {(COST+2*SLIP)/atr_med:.3f} ATR)")
    print(f"  {'n_entry':>7} {'n':>6} {'GROSS exp':>10} {'ctrl':>8} {'excess':>8} {'z':>7} {'p':>7}"
          f"  {'gross/ATR':>10}   {'NET exp':>9}")
    for n_e in (5, 10, 20, 40, 80):
        g = run(df, w, n_entry=n_e, stop_mult=1.5, targ_mult=2.0, cost_pts=0.0, slip_pts=0.0)
        g = g[np.isin(g.sig_bar, np.where(res)[0])].reset_index(drop=True)
        nt = run(df, w, n_entry=n_e, stop_mult=1.5, targ_mult=2.0, cost_pts=COST, slip_pts=SLIP)
        nt = nt[np.isin(nt.sig_bar, np.where(res)[0])]
        if len(g) < 50: continue
        mn, p = matched_control(df, w, g, n_draws=300, seed=n_e, cost_pts=0.0, slip_pts=0.0,
                                stop_mult=1.5, targ_mult=2.0, pool_idx=res)
        z = (g.net.mean()-mn.mean())/mn.std(ddof=1)
        print(f"  {n_e:>7} {len(g):>6,} {g.net.mean():>+10.2f} {mn.mean():>+8.2f}"
              f" {g.net.mean()-mn.mean():>+8.2f} {z:>+7.2f} {p:>7.4f}"
              f"  {g.net.mean()/atr_med:>+10.3f}   {nt.net.mean():>+9.2f}")

print("\n" + "="*112)
print("VERDICT")
print("="*112)
print("  If gross expectancy is <= 0 and gross excess ~ 0 on BOTH instruments, the")
print("  central claim survives its strongest available falsification test and is")
print("  structural rather than an artefact of one instrument or one feed.")
