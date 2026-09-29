"""T5 -- the PF 1.5 table (step 6), assembled from T2 (declared arms, whole sample) and T4 (the
grid's marginal-consensus cell, read once on the second half), plus the one surprise T1 found:
the Pine clamps `tfMin` to >= 1 minute, so on a 30-SECOND chart `crossBars = round(7/1) = 7`
bars = 3.5 minutes, not the 14 bars the research's 30s baseline assumes. That reading is scored
here on both halves with both nulls, labelled as a SECOND LOOK (it is one of the grid's cells).

Verdict per timeframe, on the second-half read of the consensus cell (the only read nothing was
chosen on):  (i) PF >= 1.5 and delivered/MDE >= 1 and both nulls p <= 0.05;
             (ii) PF >= 1.5 but unresolvable at this n;   (iii) PF < 1.5.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tfx_core as X   # noqa: E402

pd.set_option("display.width", 230)
P0 = dict(X.TV)
c30 = X.ctx(0.5)
alld, is_d, oos_d = X.split(c30, P0)

print("=" * 100)
print("SURPRISE -- the TradingView script's own 30s reading (crossBars = 7 bars = 3.5 min)")
print("=" * 100)
rows = []
for lab, P in (("research 30s: 14 bars", dict(P0, ma_mode="xbars", cross_bars=14)),
               ("Pine on a 30s chart: 7 bars", dict(P0, ma_mode="xbars", cross_bars=7))):
    for blk, dd in (("first", is_d), ("second", oos_d), ("all", alld)):
        r, tr = X.full_days(c30, P, dd, 400, seed=len(lab) * 7 + len(blk))
        r.update(reading=lab, block=blk); rows.append(r)
        print(f"  {lab:28s} {blk:6s} n {r['n']:3d} %/tr {r['pct']:+.4f} PF {r['pf']:.3f} win {r['win']:.3f} "
              f"ratio {r['ratio']:+.2f}  p_entry {r['p_entry']:.3f} p_gate {r['p_gate']:.3f} "
              f"P(mean<=0) {r['p_boot']:.3f}  need n {r['need']:.0f}", flush=True)
pd.DataFrame(rows).to_csv(os.path.join(HERE, "t5_pine30s.csv"), index=False)

arms = pd.read_csv(os.path.join(HERE, "t2_arms.csv"))
cons = pd.read_csv(os.path.join(HERE, "t4_consensus.csv"))
out = []
for tf in X.TFS:
    a = arms[(arms.tf == tf) & (arms.arm == ("a"))].iloc[0]
    cc = arms[(arms.tf == tf) & (arms.arm == ("c"))].iloc[0]
    s = cons[(cons.tf == tf) & (cons.block == "second")].iloc[0]
    r = cons[(cons.tf == tf) & (cons.block == "research")].iloc[0]
    if not (s.pf >= 1.5):
        v = "iii"
    elif s.ratio >= 1 and s.p_entry <= 0.05 and s.p_gate <= 0.05:
        v = "i"
    else:
        v = "ii"
    shape = "WRONG SHAPE (better on 2nd half)" if s.pct > r.pct else ""
    out.append(dict(tf=tf, cfg=s.cfg, asconf_n=a.n, asconf_pf=a.pf, armc_n=cc.n, armc_pf=cc.pf,
                    armc_ratio=cc.ratio, armc_p_entry=cc.p_entry, armc_p_gate=cc.p_gate,
                    res_n=r.n, res_pf=r.pf, sec_n=s.n, sec_pf=s.pf, sec_ratio=s.ratio,
                    sec_p_entry=s.p_entry, sec_p_gate=s.p_gate, sec_p_boot=s.p_boot,
                    sec_win=s.win, be_driftless=s.be_driftless, sec_need=s.need, verdict=v, note=shape))
V = pd.DataFrame(out)
print("\n" + "=" * 100)
print("THE PF 1.5 TABLE -- arm (a) and arm (c) over all 92 sessions; the consensus cell on each half")
print("=" * 100)
print(V.drop(columns=["cfg"]).to_string(index=False, float_format=lambda v: f"{v:.3f}"))
for _, r in V.iterrows():
    print(f"  {r.tf:>4}m consensus: {r.cfg}")
V.to_csv(os.path.join(HERE, "t5_verdict.csv"), index=False)
print("\ndone.")
