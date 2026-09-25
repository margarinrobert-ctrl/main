"""Matched random-entry control for the two US100 60m cells that were positive on both periods.

The control keeps the SAME exit machine (stop, opposite-cross exit on the real crosses, window,
flatten) and the SAME number of long and short signal bars in each period, placed at random among
the bars that could have fired (inside the window when there is one). If the rule's entries carry
information it beats that; if the result is the exposure (a long bias in a market that rose ~5x),
the control earns it too.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mx_sim as M  # noqa: E402
import run_nas as R  # noqa: E402

CUT = pd.Timestamp("2022-12-26")
d = R.load(60)
ny = d["ny"]
nymin = (ny.dt.hour * 60 + ny.dt.minute).to_numpy()
per = (ny >= CUT).to_numpy()

cells = [("long only", dict(side="Long")),
         ("window 09:30-16:00 + flat 16:00", dict(win=(570, 960), flat=960)),
         ("defaults (reference)", {})]
g = np.random.default_rng(7)
for lab, kw in cells:
    st = {}
    M.run(d, stats=st, **kw)                       # warm
    # the rule's own signal bars
    r, ent = M.run(d, return_entries=True, **kw)
    e = pd.to_datetime(ent)
    real = [r[e < CUT].mean(), r[e >= CUT].mean()]
    # rebuild the rule's signal masks from its crosses to get counts per period
    f = M.ma(d["close"].to_numpy(), 13, "LinReg"); s = M.ma(d["close"].to_numpy(), 48, "EMA")
    up = (f > s) & (np.roll(f, 1) <= np.roll(s, 1)); dn = (f < s) & (np.roll(f, 1) >= np.roll(s, 1))
    elig = np.ones(len(d), bool)
    if "win" in kw:
        fill = nymin + 60
        elig = (fill >= kw["win"][0]) & (fill < kw["win"][1])
    nulls = [[], []]
    for _ in range(200):
        sl = np.zeros(len(d), bool); ss = np.zeros(len(d), bool)
        for blk in (False, True):
            pool = np.flatnonzero(elig & (per == blk))
            for mask, src in ((sl, up), (ss, dn)):
                k = int((src & elig & (per == blk)).sum())
                mask[g.choice(pool, k, replace=False)] = True
        rr, ee = M.run(d, return_entries=True, force_sig=(sl, ss), **kw)
        ee = pd.to_datetime(ee)
        nulls[0].append(rr[ee < CUT].mean()); nulls[1].append(rr[ee >= CUT].mean())
    for j, name in enumerate(("2016-22", "2023-25")):
        v = np.asarray(nulls[j])
        print(f"  {lab:<34s} {name}: rule {real[j]:+7.2f} pts/trade | random entry median {np.median(v):+7.2f} "
              f"[5-95% {np.percentile(v,5):+.2f}, {np.percentile(v,95):+.2f}]  p {np.mean(v >= real[j]):.3f}")
