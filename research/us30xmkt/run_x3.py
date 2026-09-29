"""x3 -- ONE READ of the frozen section-12 rule on markets that had no part in finding it.

THE TWO PRE-DECLARED HYPOTHESES, written here before any of these markets was read. Section 12's
two component findings are the things under test; everything else is description.

  H1  THE ADX INVERSION.  On US30, `adx<=20` beat its block's base in 12 of 12 cells and `adx>=25`
      was negative 6/6. If that is a property of the DONCHIAN-BREAKOUT GEOMETRY rather than of the
      Dow, then on a fresh market `+adx<=20` must beat `base` on per-trade mean.
      PASS on a market  := `+adx<=20` > `base` in EVERY block of that market at BOTH
                           parameterisations (US100 4 cells, NQ 4, XAU 4, US30I 2).
      The reported statistic is the SHARE OF CELLS beating base, against a chance rate of 50%.

  H2  THE EMA ALIGNMENT.  On US30, `ema13>34>89` was positive in 6 of 6 cells with the pool's most
      stable lift, while `ema13>48` -- the trigger restated at 84.2% of breakout bars -- was worth
      nothing. PASS on a market := `+ema align` > `base` in every block at both parameterisations.

  H3  THE ARM THAT MUST LOSE.  `conventional` (= +ema align +adx>=25) is in the table precisely so
      that the ADX inversion has something to be falsified against. If the inversion is real,
      `conventional` must be beaten by BOTH of its own components taken separately.

NOTHING IS SWEPT. Five arms x two parameterisations x seven blocks of four markets = 70 cells, all
declared, read once. `STUDY_V52`: a filter is a property of a GEOMETRY, not of a market -- so if a
component inverts, the geometry is checked in ATR terms first (x1 prints exactly that table).
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xm_core as X  # noqa: E402

pd.set_option("display.width", 240)
pd.set_option("display.max_columns", 60)
pd.set_option("display.max_rows", 300)

N_DRAW = 400
t0 = time.time()

print("=" * 100)
print("x3  THE FROZEN RULE ON MARKETS THAT CHOSE NOTHING -- ONE READ, 70 DECLARED CELLS")
print("=" * 100)

F = X.load_all()
BL = {m: X.blocks(F[m], m) for m in X.MARKETS}
MASK = {m: X.build_masks(F[m]["high"].to_numpy(), F[m]["low"].to_numpy(),
                         F[m]["close"].to_numpy()) for m in X.MARKETS}

READ = list(X.NEW_MARKETS)          # US30's blocks are spent; it appears only as the reference
rows, trades_store = [], {}

for m in READ + ["US30"]:
    f = F[m]
    for b, ix in BL[m].items():
        elig = X.eligible(f, ix)
        for param in ("atr", "pts"):
            base_t = X.trades(f, m, [], param=param, bm=ix, M=MASK[m])
            for arm, conds in X.ARMS:
                t = X.trades(f, m, conds, param=param, bm=ix, M=MASK[m])
                s = X.summarise(t, f"{m}|{b}|{param}|{arm}")
                s.update(market=m, block=b, param=param, arm=arm,
                         reference=(m == "US30"))
                if len(t) >= 10:
                    ctl = X.control(f, m, len(t), elig, param=param, n_draw=N_DRAW, seed=17)
                    if ctl is not None and len(ctl) > 20:
                        s["ctl_med"] = float(np.median(ctl[:, 0]))
                        s["ctl_p"] = float((ctl[:, 0] >= s["mean"]).mean())
                        s["ctl_n"] = float(np.median(ctl[:, 2]))
                    bt = X.boot_days(t, "atr_u", n=1500, seed=23)
                    s.update(boot_p=bt["p"], boot_lo=bt["lo"], boot_hi=bt["hi"])
                    trades_store[(m, b, param, arm)] = t[["date", "atr_u", "pct", "pts"]]
                rows.append(s)
        print(f"    {m:6s} {b:12s} done  ({time.time() - t0:5.0f}s)")

R = pd.DataFrame(rows)
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_cache")
os.makedirs(out, exist_ok=True)
R.to_csv(f"{out}/x3_cells.csv", index=False)
pd.concat([v.assign(market=k[0], block=k[1], param=k[2], arm=k[3])
           for k, v in trades_store.items()]).to_csv(f"{out}/x3_trades.csv", index=False)

cols = ["market", "block", "param", "arm", "n", "days", "mean", "sd", "se", "t", "mde80",
        "outside", "pf", "win", "pts", "pct", "med_min", "ctl_med", "ctl_p", "boot_p"]

print("\n" + "=" * 100)
print("ATR-UNIT PARAMETERISATION -- the matched geometry (1.6127N stop / 4.8380N target)")
print("=" * 100)
print(R[R.param == "atr"][cols].round(4).to_string(index=False))

print("\n" + "=" * 100)
print("POINTS PARAMETERISATION -- 50/150 in EACH MARKET'S OWN POINTS, i.e. a different trade")
print("=" * 100)
print(R[R.param == "pts"][cols].round(4).to_string(index=False))

print(f"\n    wrote {out}/x3_cells.csv and x3_trades.csv   ({time.time() - t0:.0f}s)")
