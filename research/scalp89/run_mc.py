"""Monte Carlo on the best measured variant (trail OFF, everything else as configured), NQ 5m.
Perturbation with the indicators RECOMPUTED from jittered bars, execution noise, a permutation
for the path and a bootstrap for the edge. A perturbation prices noise on the trades you
selected and never the selection; here the selection is the user's, not mine."""
from __future__ import annotations
import os, sys, warnings
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s89_core as M
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
def line(t): print("\n" + "=" * 124 + f"\n{t}\n" + "=" * 124)
CFG = dict(M.CFG, trail_on=0)
D = M.build("NQ", 5, CFG); rng = np.random.default_rng(17)
ix = pd.DatetimeIndex(D["ts"])
base = M.run(D, cfg=CFG)
print(f"  trail OFF, as configured otherwise: research n {len(base[base.block=='research'])} "
      f"{M.stats(base[base.block=='research'])['pct']:+.4f} %/t PF {M.stats(base[base.block=='research'])['pf']:.3f} | "
      f"locked n {len(base[base.block=='locked'])} {M.stats(base[base.block=='locked'])['pct']:+.4f} PF {M.stats(base[base.block=='locked'])['pf']:.3f}")
for bname in ("research", "locked"):
    line(f"{bname.upper()} BLOCK")
    tb = base[base.block == bname]; v0 = tb["pct"].to_numpy(); tot0 = v0.sum()
    # A execution
    out = np.zeros(1000)
    for i in range(1000):
        t = M.run(D, cfg=CFG, cost=D["cost"] * rng.uniform(0.5, 2.0), slip=D["tick"] * rng.uniform(0.0, 2.0))
        out[i] = t[t.block == bname]["pct"].sum()
    print(f"  A. execution (slip U(0,2x), cost U(0.5x,2x)) 1000 draws: total% p5 {np.quantile(out,.05):+.2f} "
          f"p50 {np.median(out):+.2f} p95 {np.quantile(out,.95):+.2f} realised {tot0:+.2f}  P(tot>0) {(out>0).mean():.3f}")
    # B price jitter with indicators recomputed
    for sig_t in (0.5, 1.0, 2.0):
        tots, ns = [], []
        for i in range(150):
            o = D["o"] + rng.normal(0, sig_t * 0.25, D["n"]); h = D["h"] + rng.normal(0, sig_t * 0.25, D["n"])
            l = D["l"] + rng.normal(0, sig_t * 0.25, D["n"]); c = D["c"] + rng.normal(0, sig_t * 0.25, D["n"])
            hi = np.maximum(np.maximum(o, c), np.maximum(h, l)); lo = np.minimum(np.minimum(o, c), np.minimum(h, l))
            Dp = M.indicators(o, hi, lo, c, ix, CFG, cost=D["cost"], pv=D["pv"], tick=D["tick"])
            t = M.run(Dp, cfg=CFG); t = t[t.block == bname]
            tots.append(t["pct"].sum()); ns.append(len(t))
        tots = np.array(tots)
        print(f"  B. price jitter {sig_t} tick, indicators recomputed, 150 draws: trades p50 {np.median(ns):.0f}  "
              f"total% p5 {np.quantile(tots,.05):+.2f} p50 {np.median(tots):+.2f} p95 {np.quantile(tots,.95):+.2f}  "
              f"P(tot>0) {(tots>0).mean():.3f}")
    # C permutation (path) and bootstrap (edge)
    dds = np.zeros(5000)
    for i in range(5000):
        eq = np.cumsum(rng.permutation(v0)); dds[i] = -(eq - np.maximum.accumulate(eq)).min()
    eq0 = np.cumsum(v0); rd = -(eq0 - np.maximum.accumulate(eq0)).min()
    bs = np.array([rng.choice(v0, len(v0), replace=True).mean() for _ in range(5000)])
    print(f"  C. permutation: realised DD {rd:.2f}%  MC p50 {np.median(dds):.2f}  p95 {np.quantile(dds,.95):.2f}  p99 {np.quantile(dds,.99):.2f}  "
          f"realised percentile {(dds<=rd).mean():.2f}")
    print(f"     bootstrap: mean {v0.mean():+.4f}  95% CI [{np.quantile(bs,.025):+.4f}, {np.quantile(bs,.975):+.4f}]  P(mean<=0) {(bs<=0).mean():.3f}")
    # D concentration
    x = np.sort(v0)[::-1]
    print(f"  D. concentration: best 5% of trades supply {100*x[:max(1,len(x)//20)].sum()/tot0 if tot0 else float('nan'):+.0f}% of a {tot0:+.2f}% total; "
          f"best trade {x[0]:+.3f}%, worst {x[-1]:+.3f}%")
