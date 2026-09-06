"""The two mechanism-first gates applied to V61, which the V61/V64 studies never ran as named steps.

Gate 1  the PRIMARY alone -- the Donchian breakout with the CVD gate OFF (k=0), every event,
        equal weighted, costs in. This is the baseline the meta layer must be compared against.
Gate 2  the CVD gate as the META LAYER, judged on UNSIZED returns over the primary's own events:
        does keeping ~25% of them raise the mean per-event return, with a paired bootstrap.

Note on Gate 2's event set: the deployed gated strategy is NOT a strict subset of the primary's
trades, because a vetoed signal frees the position lock and admits a later one (15m research:
primary 967 trades, gated 409, of which ~280 are shared). Gate 2 deliberately scores the SUBSET
question -- given the primary's events, does the gate pick the better ones -- which is the
selection-skill question the skill defines. The lock-freed extras are an implementation effect and
are measured separately in results/inst/vp_next0.txt.
"""
import os, sys, warnings, numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56", "research/v64"):
    sys.path.insert(0, os.path.join(ROOT, p))
sys.path.append("/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/mechanism-first-alpha/scripts")
import v64opt as O, v61core as V
from gates import primary_gate, meta_gate
warnings.filterwarnings("ignore")
P = {"incumbent 30m": dict(tf=30, ent=20, exN=20, stop=2.0, tp=0.0, hold=480, adapt=0, k=3, w=20, use_ma=0, ma_thr=0.0, use_chop=0, chop_thr=99.0, psh=0),
     "15m preset": dict(tf=15, ent=15, exN=30, stop=3.0, tp=6.0, hold=480, adapt=0, k=3, w=30, use_ma=0, ma_thr=0.0, use_chop=0, chop_thr=99.0, psh=0)}
Ds = {tf: O.build(tf) for tf in (15, 30)}
print("GATE 1 -- the V61 PRIMARY alone (Donchian breakout, CVD gate OFF), equal-weighted, costs in\n")
print(f"  {'':34s} {'n':>5} {'mean %/trade':>13} {'95% CI':>26} {'p':>7} {'hit':>7}  verdict")
prim = {}
for nm, p in P.items():
    q = dict(p); q["k"] = 0
    R_, pct, blk, sg = O.evaluate(Ds[p["tf"]], q); prim[nm] = (pct, blk, sg)
    for blkid, bn in ((0, "research"), (1, "locked")):
        x = pct[blk == blkid] / 100.0; r = primary_gate(x, cost_per_event=0.0); lo, hi = r["net_mean_ci95"]
        print(f"  {nm+' '+bn:34s} {r['n_events']:>5} {100*r['net_mean_per_event']:>13.4f} [{100*lo:>+9.4f}, {100*hi:>+9.4f}] "
              f"{r['bootstrap_p_one_sided']:>7.3f} {100*r['hit_rate']:>6.1f}%  {r['verdict'].split('--')[0].strip()}")
print("\nGATE 2 -- the CVD gate as the meta layer, judged UNSIZED on the primary's own events\n")
print(f"  {'':34s} {'kept':>6} {'unfiltered':>11} {'filtered':>10} {'uplift':>9} {'95% CI':>24} {'p':>7}  verdict")
for nm, p in P.items():
    D = Ds[p["tf"]]; pct0, blk0, sg0 = prim[nm]
    R_, pct1, blk1, sg1 = O.evaluate(D, p)
    for blkid, bn in ((0, "research"), (1, "locked")):
        s0 = sg0[blk0 == blkid]; x0 = pct0[blk0 == blkid] / 100.0
        kept = np.isin(s0, sg1[blk1 == blkid])
        g = meta_gate(x0, kept.astype(float), 0.5); lo, hi = g["unsized_uplift_ci95"]
        print(f"  {nm+' '+bn:34s} {100*g['kept_fraction']:>5.0f}% {100*g['unsized_mean_unfiltered']:>11.4f} {100*g['unsized_mean_filtered']:>10.4f} "
              f"{100*g['unsized_uplift']:>+9.4f} [{100*lo:>+9.4f}, {100*hi:>+9.4f}] {g['bootstrap_p_one_sided']:>7.3f}  {g['verdict'].split('--')[0].strip()}")
