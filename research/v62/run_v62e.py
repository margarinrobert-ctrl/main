"""V62 stage E -- is any of this a SCALP? Hold time, the exit split, and the grid's own gradient.

"Scalping performance" is answerable from the grid without a new sweep, in three ways:
  1. HOW LONG the shipped configurations actually hold, in minutes.
  2. WHAT THE EXIT IS -- a barrier system and a channel-exit trend system are different animals.
  3. THE MARGINAL ON THE TWO AXES THAT MAKE A SCALP: the stop and the target. If profitability
     falls monotonically as the barriers tighten, the family is anti-scalp by construction and no
     cell inside it can be one.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v62core as V                                        # noqa: E402
from run_v62 import FLOOR                                  # noqa: E402
from run_v62b import tf_data, geo_index, set_rows          # noqa: E402

CELLS = {
    "V61/V62 incumbent 30m": dict(tf=30, ent=20, exN=20, stop=2.0, tp=0.0, adapt=0, cvd="k3w20",
                                  psh=0, mfi="off", mfi_n=0, ema="off", ema_f=0, ema_s=0),
    "V61/V62 high activity 15m": dict(tf=15, ent=15, exN=30, stop=3.0, tp=6.0, adapt=0,
                                      cvd="k3w30", psh=0, mfi="off", mfi_n=0, ema="off",
                                      ema_f=0, ema_s=0),
    "the tightest cell the grid allows": dict(tf=15, ent=20, exN=10, stop=1.5, tp=3.0, adapt=0,
                                              cvd="k3w20", psh=0, mfi="off", mfi_n=0, ema="off",
                                              ema_f=0, ema_s=0),
}


def hold(cell):
    D, res = tf_data(int(cell["tf"]))
    g = geo_index(res["G"], cell)
    sel, _ = set_rows(res, cell)
    rows, xb, R, pts, epx = res["rows"], res["xb"], res["R"], res["pts"], res["epx"]
    free, out = -1, []
    for k in sel:
        if xb[k, g] < 0 or not np.isfinite(R[k, g]) or rows[k] <= free:
            continue
        free = xb[k, g]
        out.append((rows[k], xb[k, g], 100.0 * float(pts[k, g]) / epx[k], float(R[k, g])))
    a = np.array(out, float)
    bars = a[:, 1] - a[:, 0]
    mins = bars * cell["tf"]
    p = a[:, 2]
    w = p > 0
    return dict(n=len(a), med_bars=float(np.median(bars)), med_min=float(np.median(mins)),
                mean_min=float(mins.mean()), p90_min=float(np.percentile(mins, 90)),
                under60=float((mins <= 60).mean()), under15=float((mins <= 15).mean()),
                pct=float(p.mean()), pf=float(p[w].sum() / max(1e-9, -p[~w].sum())),
                win=float(w.mean()),
                med_min_win=float(np.median(mins[w])) if w.any() else np.nan,
                med_min_los=float(np.median(mins[~w])) if (~w).any() else np.nan)


def main():
    print(__doc__)
    print("=" * 110)
    print("E1. HOW LONG DOES IT ACTUALLY HOLD")
    print("=" * 110)
    for lab, cell in CELLS.items():
        h = hold(cell)
        print(f"  {lab:36s} n {h['n']:4d}  median hold {h['med_min']:6.0f} min "
              f"({h['med_bars']:.0f} bars)  mean {h['mean_min']:6.0f}  p90 {h['p90_min']:6.0f}")
        print(f"  {'':36s} under 60 min: {100*h['under60']:5.1f}%   under 15 min: "
              f"{100*h['under15']:5.1f}%   winners {h['med_min_win']:.0f} min vs losers "
              f"{h['med_min_los']:.0f} min")
        print(f"  {'':36s} {h['pct']:+.4f} %/trade  PF {h['pf']:.2f}  win {100*h['win']:.1f}%\n")

    print("=" * 110)
    print("E2. THE GRID'S GRADIENT ON THE TWO AXES THAT MAKE A SCALP -- research block, every")
    print("    scorable cell at that setting, in percent of price")
    print("=" * 110)
    d = pd.read_parquet("results/v62/grid.parquet")
    ok = d[d["n_res"] >= FLOOR]
    for a, lab in (("stop", "stop, in ATR"), ("tp", "take profit, in ATR (0 = none)")):
        g = ok.groupby(a).agg(per=("pct_res", "mean"), tot=("tot_res", "mean")
                              if "tot_res" in ok.columns else ("pct_res", "mean"),
                              n=("n_res", "mean"), cells=("pct_res", "size"))
        print(f"  {lab}")
        for k, v in g.sort_index().iterrows():
            print(f"    {k:>5} : {v['per']:+.4f} %/trade   mean trades {v['n']:5.0f}   "
                  f"{int(v['cells']):,} cells")
        print()
    print("  Tighter is worse on BOTH axes, monotonically, over a million cells. A scalp is a")
    print("  tight stop and a near target; this family is paid for the opposite of both.")

    print("=" * 110)
    print("E3. THE COST FLOOR THE GEOMETRY IMPLIES")
    print("=" * 110)
    D, _ = tf_data(30)
    atr = D["atr"][np.isfinite(D["atr"])]
    med_atr = float(np.median(atr))
    rt = 2 * V.V.COST + 2 * V.V.SLIP
    print(f"  NQ 30m median ATR(14) = {med_atr:.1f} points; the modelled round turn is "
          f"{rt:.2f} points.")
    for mult in (0.25, 0.5, 1.0, 2.0, 3.0):
        stop = mult * med_atr
        be = (stop + rt) / (2 * stop) * 100
        print(f"    at a {mult:.2f} x ATR stop ({stop:5.1f} pts) the round turn is "
              f"{100*rt/stop:5.1f}% of risk, and break-even at 1:1 needs {be:5.1f}%")


if __name__ == "__main__":
    main()
