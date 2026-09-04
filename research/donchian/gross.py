"""Is this an edge destroyed by costs, or no edge at all?

Those are very different diagnoses. The first says "find a cheaper venue or a
bigger barrier"; the second says the family is dead regardless of costs. Report
GROSS expectancy (costs and slippage switched off) beside net, against a
matched control that also has costs off.
"""
import numpy as np, pandas as pd
from engine import build_walk, stats
from strategy import run
from control import matched_control
import lab, data as D

SYM = "NAS"
df, w, res = lab.research(SYM)
COST, SLIP = lab.COST[SYM], lab.SLIP[SYM]
RT = COST + 2*SLIP

print("="*108)
print(f"GROSS vs NET DECOMPOSITION - {SYM}, 07:00-11:00 New York, RESEARCH BLOCK")
print(f"  modelled round turn = {RT:.2f} pts.  median ATR(14) in window = "
      f"{np.nanmedian(lab.atr(df,14)[res]):.2f} pts")
print("="*108)
print(f"\n  {'n_entry':>7} {'n':>6} {'GROSS exp':>10} {'gross ctrl':>11} {'gross excess':>13}"
      f" {'z':>7} {'p':>7}   {'NET exp':>9}")
for n_e in (5, 10, 20, 40, 80):
    trg = run(df, w, n_entry=n_e, stop_mult=1.5, targ_mult=2.0, cost_pts=0.0, slip_pts=0.0)
    trg = trg[np.isin(trg.sig_bar, np.where(res)[0])].reset_index(drop=True)
    trn = run(df, w, n_entry=n_e, stop_mult=1.5, targ_mult=2.0, cost_pts=COST, slip_pts=SLIP)
    trn = trn[np.isin(trn.sig_bar, np.where(res)[0])]
    mn, p = matched_control(df, w, trg, n_draws=300, seed=n_e, cost_pts=0.0, slip_pts=0.0,
                            stop_mult=1.5, targ_mult=2.0, pool_idx=res)
    z = (trg.net.mean()-mn.mean())/mn.std(ddof=1)
    print(f"  {n_e:>7} {len(trg):>6,} {trg.net.mean():>+10.2f} {mn.mean():>+11.2f}"
          f" {trg.net.mean()-mn.mean():>+13.2f} {z:>+7.2f} {p:>7.4f}   {trn.net.mean():>+9.2f}")

print("\n" + "="*108)
print("READING")
print("="*108)
trg = run(df, w, n_entry=20, stop_mult=1.5, targ_mult=2.0, cost_pts=0.0, slip_pts=0.0)
trg = trg[np.isin(trg.sig_bar, np.where(res)[0])]
trn = run(df, w, n_entry=20, stop_mult=1.5, targ_mult=2.0, cost_pts=COST, slip_pts=SLIP)
trn = trn[np.isin(trn.sig_bar, np.where(res)[0])]
g, nt = trg.net.mean(), trn.net.mean()
print(f"  At n=20 the gross expectancy is {g:+.2f} pts and the net is {nt:+.2f} pts.")
print(f"  The round turn accounts for {g-nt:.2f} of that.")
print()
if g < 0.5:
    print("  The GROSS edge is essentially zero (or negative). This is NOT an edge")
    print("  destroyed by transaction costs - there is nothing for costs to destroy.")
    print("  A cheaper venue, a bigger barrier or a larger contract would not help:")
    print("  they scale the signal and the cost together, and the signal is ~0.")
else:
    print("  A positive gross edge exists and costs are what kill it. That WOULD point")
    print("  to a cheaper venue or a wider barrier as a remedy.")
print()
print("  Breakeven check: what round turn would this rule need to break even?")
for n_e in (5, 10, 20, 40, 80):
    t = run(df, w, n_entry=n_e, stop_mult=1.5, targ_mult=2.0, cost_pts=0.0, slip_pts=0.0)
    t = t[np.isin(t.sig_bar, np.where(res)[0])]
    print(f"    n={n_e:<3} gross {t.net.mean():+6.2f} pts  ->  breaks even only if the round"
          f" turn is below {max(t.net.mean(),0):.2f} pts (actual {RT:.2f})")
