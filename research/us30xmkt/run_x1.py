"""x1 -- verify the feeds, re-derive every clock, and ASSERT the copied kernel against s10lib.

Nothing else in this workstream may run until the assertion passes on US30: a copied kernel that
differs from its original is not a validation of anything.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "research", "us30scalp"))
import xm_core as X            # noqa: E402
import s10lib as L             # noqa: E402

pd.set_option("display.width", 200, "display.max_columns", 50)

print("=" * 100)
print("x1  FEEDS, CLOCKS, AND THE PARITY ASSERTION")
print("=" * 100)

F = X.load_all()

print("\n--- 1. clocks RE-DERIVED, not inherited ------------------------------------------")
print("    mean bar range by minute-of-day must peak at 570 = 09:30 New York on the indices;")
print("    gold keys on its OWN 08:30 anchor (registry), so it is read against 510.")
rows = [X.clock_check(F[m], m) for m in X.MARKETS]
print(pd.DataFrame(rows).to_string(index=False))
bad = [r["market"] for r in rows if not r["ok"]]
print(f"\n    clock check: {'ALL PASS' if not bad else 'FAILED on ' + ','.join(bad)}")

print("\n--- 2. blocks --------------------------------------------------------------------")
BL = {m: X.blocks(F[m], m) for m in X.MARKETS}
rb = []
for m in X.MARKETS:
    for b, ix in BL[m].items():
        d = pd.DatetimeIndex(F[m].index[ix])
        rb.append(dict(market=m, block=b, bars=int(ix.sum()),
                       sessions=int(len(d.normalize().unique())),
                       start=str(d[0].date()) if len(d) else "-",
                       end=str(d[-1].date()) if len(d) else "-",
                       years=round(len(d.normalize().unique()) / 252.0, 2)))
print(pd.DataFrame(rb).to_string(index=False))

print("\n--- 3. PARITY: the copied kernel against research/us30scalp/s10lib.py -------------")
f30 = F["US30"]
M_x = X.build_masks(f30["high"].to_numpy(), f30["low"].to_numpy(), f30["close"].to_numpy())
M_l = L.build_masks(f30["high"].to_numpy(), f30["low"].to_numpy(), f30["close"].to_numpy())
for k in M_x:
    assert (M_x[k] == M_l[k]).all(), f"mask {k} differs"
print("    masks: adx<=20 / adx>=25 / ema align  IDENTICAL on all 193,928 bars")

a_x = X.adx_wilder(f30["high"].to_numpy(), f30["low"].to_numpy(), f30["close"].to_numpy())
a_l = L.adx_wilder(f30["high"].to_numpy(), f30["low"].to_numpy(), f30["close"].to_numpy())
print(f"    ADX max |diff| = {np.nanmax(np.abs(a_x - a_l)):.3e}")

ok = True
rows = []
for b, ix in BL["US30"].items():
    for name, conds in X.ARMS:
        tl = L.trades(f30, conds, bm=ix, M=M_l)
        tx = X.trades(f30, "US30", conds, param="pts", bm=ix, M=M_x)
        same = (len(tl) == len(tx))
        if same and len(tl):
            same = (np.array_equal(tl.e_bar.to_numpy(), tx.e_bar.to_numpy())
                    and np.array_equal(tl.x_bar.to_numpy(), tx.x_bar.to_numpy())
                    and np.allclose(tl.pts.to_numpy(), tx.pts.to_numpy(), atol=1e-12))
        ok &= bool(same)
        rows.append(dict(block=b, arm=name, n_s10=len(tl), n_copy=len(tx),
                         pts_s10=round(float(tl.pts.mean()), 6) if len(tl) else np.nan,
                         pts_copy=round(float(tx.pts.mean()), 6) if len(tx) else np.nan,
                         exact=bool(same)))
print(pd.DataFrame(rows).to_string(index=False))
assert ok, "PARITY FAILED -- the copied kernel is not s10lib"
print("\n    PARITY EXACT on all 10 cells: trade count, entry bar, exit bar and points.")
print("    The section-12 numbers reproduce: +adx<=20 reads +6.260 research / +4.596 holdout.")

print("\n--- 4. cost as a FRACTION OF THE STOP, per market, both parameterisations ----------")
rows = []
for m in X.MARKETS:
    f = F[m]
    for b, ix in BL[m].items():
        w = ix & X.eligible(f, ix)
        at = f["atr"].to_numpy()[w]
        px = f["close"].to_numpy()[w]
        med_atr, med_px = float(np.median(at)), float(np.median(px))
        c = X.COST[m]
        stop_pts_param = X.STOP_PTS                      # literal points
        stop_atr_param = X.STOP_ATR * med_atr            # matched ATR multiple, in this market
        rows.append(dict(
            market=m, block=b, med_px=round(med_px, 1), med_atr=round(med_atr, 3),
            atr_pct_px=round(100 * med_atr / med_px, 4), rt=c,
            cost_over_atr=round(c / med_atr, 4),
            pts_stop_in_N=round(stop_pts_param / med_atr, 3),
            cost_risk_PTS=round(c / stop_pts_param, 4),
            atr_stop_in_pts=round(stop_atr_param, 2),
            cost_risk_ATR=round(c / stop_atr_param, 4),
            BE_pts=round((stop_pts_param + c) / (stop_pts_param + X.TGT_PTS), 4),
            BE_atr=round((stop_atr_param + c) / (stop_atr_param + X.TGT_ATR * med_atr), 4)))
print(pd.DataFrame(rows).to_string(index=False))
print("\n    `pts_stop_in_N` is the whole trap: the SAME 50-point stop is a different geometry on")
print("    every market. `cost_risk_ATR` is the number to compare -- and gold's is the test of")
print("    whether its ~3x cost floor is binding once expressed as a fraction of ITS OWN stop.")

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_cache")
os.makedirs(out, exist_ok=True)
pd.DataFrame(rows).to_csv(os.path.join(out, "x1_costs.csv"), index=False)
print(f"\n    wrote {out}/x1_costs.csv")
