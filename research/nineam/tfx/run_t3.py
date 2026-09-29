"""T3 -- DROP-ONE per timeframe on arm (c), declared as THE arm before any drop-one was read
(choosing the per-timeframe best arm by P&L would itself be selection). Components removed one at
a time: the fresh-cross gate, the breakeven ratchet, the opposite-cross exit. Each row carries its
MDE and a 200-draw matched random entry; the delta is paired against the full rule on the same
timeframe. Also: the share of TRIGGERS that are not breaks at all -- the first eligible bar of the
window already outside the range -- because T1/T2 showed that share grows with bar size.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tfx_core as X   # noqa: E402

pd.set_option("display.width", 220)
P0 = dict(X.TV)


def arm_c(tf):
    re_ = 545 if (tf < 1 or tf > 5) else int(round(540 + tf * np.floor(5 / tf)))
    return X.matched(tf), dict(P0, ma_mode="xmin", cross_min=7, range_end=re_)


rows = []
print("=" * 100)
print("4  DROP-ONE on arm (c) -- paired against the full rule on the same timeframe")
print("=" * 100)
for tf in X.TFS:
    (fa, sl), P = arm_c(tf)
    c = X.ctx(tf, fa, sl)
    sig_g, _ = c.sigs(P)
    first = c.mod[X.ungated(c, P)[0]].min()
    fb = float((c.mod[sig_g] == first).mean()) if len(sig_g) else np.nan
    base = None
    for lab, pp in [("full", P), ("-gate", dict(P, ma_mode="off")),
                    ("-breakeven", dict(P, be_pts=0.0, be_off=0.0)),
                    ("-xcross exit", dict(P, x_mode="off"))]:
        row, tr = X.full(c, pp, 200, seed=int(tf * 10) + len(lab))
        if base is None:
            base = row["pct"]
        row.update(tf=tf, arm=lab, delta=row["pct"] - base, first_bar_share_gated=fb)
        rows.append(row)
        print(f"  {tf:>4}m {lab:13s} n {row['n']:3d} %/tr {row['pct']:+.4f} PF {row['pf']:.3f} "
              f"win {row['win']:.3f}  delta {row['delta']:+.4f}  MDE {row['mde']:.4f} "
              f"p_entry {row.get('p_entry', np.nan):.3f}", flush=True)
    print(f"         gated triggers on the window's FIRST bar (price already beyond the range): {fb:.3f}")
res = pd.DataFrame(rows)
res.to_csv(os.path.join(HERE, "t3_dropone.csv"), index=False)
print("\n  marginal delta per component, over the 7 timeframes (NOT independent -- one sample):")
print(res[res.arm != "full"].groupby("arm")["delta"].agg(["mean", "median", lambda v: (v > 0).sum()])
      .rename(columns={"<lambda_0>": "n_tf_helps_when_removed"}).to_string(float_format=lambda v: f"{v:+.4f}"))
print("\ndone.")
