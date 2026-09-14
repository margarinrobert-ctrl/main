"""x5 -- the diagnostics that decide how a replication should be READ.

Three cheap measurements that this branch has learned to take before crediting or dismissing a
cross-market result.

  1. BASE RATE ON THE TRIGGER'S OWN BARS. `STUDY_V60`/`STUDY_V16`/`STUDY_V62`: a confirmation that
     the trigger already implies cannot add anything, and the base rate says so in two lines. If
     `ema align` passes 90% of breakout bars on a market it is the trigger restated there and its
     "replication" means nothing.
  2. THE KEPT SHARE ACROSS MARKETS AND BLOCKS. `STUDY_MR30`: `atr_pct250 <= 0.2` failed to transfer
     because its kept share drifted 0.318 -> 0.212 -> 0.142, i.e. it was not the same filter on
     each block. A FIXED ADX threshold is exposed to exactly that, so the ADX distribution is
     printed per market.
  3. THE SIGNAL-BAR CORRELATION between the two conditions. US30 measured -0.1185, which is why
     they stack at all. If they are collinear on another market, `+both` is not two filters there.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xm_core as X  # noqa: E402

pd.set_option("display.width", 240)
pd.set_option("display.max_columns", 60)

print("=" * 100)
print("x5  BASE RATES, KEPT SHARES, AND THE CONDITION CORRELATION -- per market")
print("=" * 100)

F = X.load_all()
BL = {m: X.blocks(F[m], m) for m in X.MARKETS}

rows, adxrows = [], []
for m in X.MARKETS:
    f = F[m]
    h, l, c = f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy()
    M = X.build_masks(h, l, c)
    a = X.adx_wilder(h, l, c)
    sig, _ = X.signals(f, [], M=M)
    mod = f["mod"].to_numpy()
    inw = (mod >= X.W0) & (mod < X.W1)
    sig = sig[inw[sig]]
    for b, ix in BL[m].items():
        s = sig[ix[sig]]
        pool = np.flatnonzero(inw & ix & np.isfinite(f["atr"].to_numpy()))
        for cond in ("adx<=20", "adx>=25", "ema align"):
            on_sig = float(M[cond][s].mean())
            on_all = float(M[cond][pool].mean())
            rows.append(dict(market=m, block=b, cond=cond, n_sig=len(s),
                             pass_on_signal=on_sig, pass_on_window=on_all,
                             lift=on_sig / max(on_all, 1e-9)))
        adxrows.append(dict(market=m, block=b, n_sig=len(s),
                            adx_med_sig=float(np.nanmedian(a[s])),
                            adx_med_window=float(np.nanmedian(a[pool])),
                            adx_p25=float(np.nanpercentile(a[s], 25)),
                            adx_p75=float(np.nanpercentile(a[s], 75)),
                            rho_adx_ema=float(np.corrcoef(
                                M["adx<=20"][s].astype(float),
                                M["ema align"][s].astype(float))[0, 1])
                            if len(s) > 30 else np.nan))

B = pd.DataFrame(rows)
print("\n--- 1. base rate on the trigger's own bars, and the lift over all in-window bars ---")
for cond in ("adx<=20", "adx>=25", "ema align"):
    print(f"\n  {cond}")
    print(B[B.cond == cond][["market", "block", "n_sig", "pass_on_signal",
                             "pass_on_window", "lift"]].round(4).to_string(index=False))

print("\n--- 2. the ADX distribution on breakout bars, and the two conditions' correlation --")
A = pd.DataFrame(adxrows)
print(A.round(4).to_string(index=False))
print("\n    `pass_on_signal` for adx<=20 IS the kept share. If it moves a lot between markets the")
print("    fixed threshold is not the same filter on each -- which is what a transfer test needs")
print("    to know before it credits or blames the condition.")
print("    `rho_adx_ema` on US30 was -0.1185 in section 13; near zero means two genuine axes.")

C = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_cache")
os.makedirs(C, exist_ok=True)
B.to_csv(f"{C}/x5_baserates.csv", index=False)
A.to_csv(f"{C}/x5_adx.csv", index=False)
print(f"\n    wrote {C}/x5_*.csv")
