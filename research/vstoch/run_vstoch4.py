"""STAGE 4 -- is it cost, or is there no edge? And the win rate against its own bound.

`CLAUDE.md`: RUN THE ZERO-COST VARIANT BEFORE CONCLUDING THERE IS NO EDGE. A rule that is
gross-positive and net-negative has a cost problem and a different fix (bigger bars, wider
barriers); a rule that is gross-NEGATIVE has no edge and no execution improvement can reach it.

And: COSTS SET A FLOOR ON THE WIN RATE. At a target of qR the driftless break-even after a round
turn of c (expressed in R) is w* = (1 + c) / (1 + q). Reading a win rate without its own bound
beside it is how a 66% win rate gets mistaken for an edge.
"""
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vstoch as V

pd.set_option("display.width", 200)
print(__doc__)
D = V.build("NQ", 15)
lo, sh, K, Dv = V.triggers(D)

print("=" * 112)
print("ZERO-COST VARIANT -- the unfiltered trigger, RTH, with fees and slippage set to zero")
print("=" * 112)
rows = []
for side_nm, trg, s in (("LONG", lo, 1), ("SHORT", sh, -1)):
    for stop, tp, hold in ((2.0, 0.0, 96), (2.0, 2.0, 96), (1.5, 1.5, 48), (3.0, 0.0, 192)):
        for lab, cost, slip in (("net", None, None), ("gross", 0.0, 0.0)):
            t = V.run(D, trg & D["rth"], side=s, stop=stop, tp=tp, hold=hold, cost=cost, slip=slip)
            t = t[t.blk == 0]
            st = V.stats(t)
            rows.append(dict(side=side_nm, geom=f"{stop}N/{tp}R/{hold}b", arm=lab,
                             n=st["n"], pct=st["pct"], pf=st["pf"], win=st["win"]))
Z = pd.DataFrame(rows).pivot_table(index=["side", "geom"], columns="arm",
                                   values=["pct", "pf"], aggfunc="first")
print(Z.to_string(float_format=lambda v: f"{v:9.4f}"))
g = pd.DataFrame(rows)
gp = g[g.arm == "gross"]
print(f"\n  GROSS-positive cells: {int((gp.pct>0).sum())} of {len(gp)}  "
      f"(LONG {int((gp[gp.side=='LONG'].pct>0).sum())}/4, SHORT {int((gp[gp.side=='SHORT'].pct>0).sum())}/4)")

print("\n" + "=" * 112)
print("COST AS A FRACTION OF RISK, and the WIN RATE AGAINST ITS OWN DRIFTLESS BOUND")
print("=" * 112)
print("  round turn = commission + 2 x slippage, in points; risk = stop x ATR at the signal bar.\n")
atr = D["atr"]; r = D["blk"] == 0
rt = D["cost"] + 2 * D["slip"]
rows = []
for stop, tp in ((1.5, 1.5), (2.0, 2.0), (2.0, 0.0), (3.0, 3.0), (3.0, 0.0)):
    med_risk = float(np.nanmedian(stop * atr[r & D["rth"] & (lo | sh)]))
    c_in_R = rt / med_risk
    q = tp / stop if tp > 0 else np.nan
    be = (1 + c_in_R) / (1 + q) * 100 if tp > 0 else np.nan
    t = V.run(D, lo & D["rth"], side=1, stop=stop, tp=tp, hold=96)
    t = t[t.blk == 0]
    rows.append(dict(geom=f"{stop}N stop / {tp}xATR tp", median_risk_pts=med_risk,
                     round_turn_pts=rt, cost_pct_of_risk=100 * c_in_R,
                     breakeven_win=be, actual_win=V.stats(t)["win"], n=V.stats(t)["n"]))
C = pd.DataFrame(rows)
print(C.to_string(index=False, float_format=lambda v: f"{v:9.3f}"))
print("\n  Cost is 1-3% of risk at these stops -- an order of magnitude below the 24% a 0.75N")
print("  scalping stop carries (`STUDY_SCALP_REQUIREMENTS`). Cost is NOT the binding constraint here.")

print("\n" + "=" * 112)
print("WHY THE VWAP CONDITION CANNOT BE A SECOND READING: it IS the stochastic state")
print("=" * 112)
pop = r & D["rth"] & np.isfinite(D["vwap"])
for nm, trg, cond in (("LONG  x close<VWAP", lo, D["c"] < D["vwap"]),
                      ("SHORT x close>VWAP", sh, D["c"] > D["vwap"])):
    m = trg & pop
    print(f"  {nm}: passes {100*cond[m].mean():5.1f}% of the trigger's own bars against "
          f"{100*cond[pop].mean():5.1f}% of bars in general -- lift {cond[m].mean()/cond[pop].mean():.2f}x")
kk = np.nan_to_num(K, nan=50.0)
print(f"\n  correlation( stochastic %K , (close-VWAP)/ATR ) on RTH research bars: "
      f"{np.corrcoef(kk[pop], np.nan_to_num(D['vwap_dist'][pop], nan=0.0))[0,1]:+.3f}")
print("  An oversold stochastic and a below-VWAP close are two readings of the same displacement.")
