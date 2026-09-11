"""MONTE CARLO on the US30 read, and the NQ + US30 portfolio.

The US30 base is already known to be null against all three nulls, so the Monte Carlo here is not
asked to certify anything -- it is asked how wide the uncertainty is, which is the honest use of it
on a result that did not clear its controls.
"""
from __future__ import annotations

import os
import sys
import time
import warnings

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import us30_core as U       # noqa: E402
import sess_core as S       # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)
OUT = os.path.join(ROOT, "results/v61sess")


def line(t):
    print("\n" + "=" * 126)
    print(t)
    print("=" * 126, flush=True)


def maxdd(x):
    c = np.cumsum(x)
    return float(np.max(np.maximum.accumulate(c) - c)) if len(c) else 0.0


print(__doc__)
t0 = time.time()
rng = np.random.default_rng(9091)
CFG = dict(ent=20, exN=20, stop=2.0, tp=0.0, hold=480, piv_min=90, win_min=600, touch=True)
D60 = U.build(60)
g60, _k, _w = U.gate(D60, 90, 600)
LEG = {"US30 60m gate ON": U.run(D60, **CFG, g=g60),
       "US30 60m gate OFF": U.run(D60, **CFG, g=np.ones(D60["n"], np.bool_)),
       "US30 60m 07-11 + flatten": U.run(D60, **CFG, sess=True, s_start=7 * 60, s_stop=11 * 60,
                                         flat=True, g=g60)}

line("MONTE CARLO on US30 -- bootstrap for the edge, permutation for the path")
print(f"  {'leg':28s} {'block':8s} {'n':>4} {'mean pts':>9} {'p5':>8} {'p95':>8} {'P(mean<=0)':>12} "
      f"{'real DD':>8} {'MC p99':>8} {'p99/real':>9}")
rows = []
for nm, t in LEG.items():
    for b, bn in ((0, "block A"), (1, "block B")):
        z = t[t.blk == b]
        if len(z) < 20:
            continue
        days = z.day.to_numpy(); ud = np.unique(days)
        byd = [z.pts.to_numpy()[days == d] for d in ud]
        means = np.array([np.concatenate([byd[j] for j in rng.integers(0, len(ud), len(ud))]).mean()
                          for _ in range(2000)])
        a = z.pts.to_numpy(); real = maxdd(a)
        dd = np.array([maxdd(rng.permutation(a)) for _ in range(2000)])
        p99 = float(np.quantile(dd, .99))
        rows.append(dict(leg=nm, block=bn, n=len(z), mean=means.mean(),
                         p5=np.quantile(means, .05), p95=np.quantile(means, .95),
                         p_le0=float(np.mean(means <= 0)), real_dd=real, p99=p99))
        print(f"  {nm:28s} {bn:8s} {len(z):>4} {means.mean():>+9.2f} {np.quantile(means,.05):>+8.2f} "
              f"{np.quantile(means,.95):>+8.2f} {np.mean(means<=0):>12.3f} {real:>8.0f} {p99:>8.0f} "
              f"{p99/max(real,1e-9):>8.2f}x")
pd.DataFrame(rows).to_csv(os.path.join(OUT, "us30_mc.csv"), index=False)

line("PORTFOLIO -- is US30 a genuinely different leg, or the same trade on a second index?")
NQ = pd.read_csv(os.path.join(OUT, "daily.csv"), index_col=0)
us = LEG["US30 60m gate ON"].groupby("day").pts.sum()
usoff = LEG["US30 60m gate OFF"].groupby("day").pts.sum()
days = sorted(set(NQ.index.to_list()) | set(us.index.to_list()))
P = pd.DataFrame(index=pd.Index(days, name="day"))
for c in ("30m all hours", "15m all hours"):
    P[f"NQ {c}"] = NQ[c].reindex(days).fillna(0.0) * 2.0        # MNQ dollars
P["US30 gate ON"] = us.reindex(days).fillna(0.0) * U.PV
P["US30 gate OFF"] = usoff.reindex(days).fillna(0.0) * U.PV
ov = P[(P.index >= 20221226)]
print(f"  overlapping days (NQ's span, 2022-12-26 on): {len(ov):,}\n")
print("  daily-$ correlation on the OVERLAP -- the only span where all legs exist:")
print("   " + ov.corr().round(3).to_string().replace("\n", "\n   "))
P.to_csv(os.path.join(OUT, "portfolio_xmkt.csv"))

line("COMBINATIONS on the overlapping span, against the best single leg")
cand = {c: ov[c] for c in ov.columns}
cand["EQUAL NQ 30m + NQ 15m"] = 0.5 * (ov["NQ 30m all hours"] + ov["NQ 15m all hours"])
cand["EQUAL NQ 30m + NQ 15m + US30 gate ON"] = ov[["NQ 30m all hours", "NQ 15m all hours",
                                                   "US30 gate ON"]].mean(axis=1)
cand["EQUAL NQ 30m + NQ 15m + US30 gate OFF"] = ov[["NQ 30m all hours", "NQ 15m all hours",
                                                    "US30 gate OFF"]].mean(axis=1)
print(f"  {'combination':42s} {'$':>8} {'maxDD $':>9} {'ret/DD':>7} {'Sharpe':>7} {'PF':>6}")
res = []
for nm, s in cand.items():
    a = s.to_numpy(); nz = a[a != 0]
    if len(nz) < 20:
        continue
    dd = maxdd(a)
    res.append(dict(cfg=nm, usd=a.sum(), dd=dd, ret_dd=a.sum() / max(dd, 1e-9),
                    sharpe=a.mean() / a.std() * np.sqrt(252) if a.std() > 0 else 0.0,
                    pf=nz[nz > 0].sum() / max(-nz[nz < 0].sum(), 1e-9)))
    r = res[-1]
    print(f"  {nm:42s} {r['usd']:>8.0f} {r['dd']:>9.0f} {r['ret_dd']:>7.2f} {r['sharpe']:>7.2f} "
          f"{r['pf']:>6.3f}")
RES = pd.DataFrame(res)
RES.to_csv(os.path.join(OUT, "portfolio_xmkt_stats.csv"), index=False)
best = RES[RES.cfg.isin(ov.columns)].sort_values("ret_dd").iloc[-1]
print(f"\n  best single leg: {best.cfg} at ret/DD {best.ret_dd:.2f}")
for _, r in RES[~RES.cfg.isin(ov.columns)].iterrows():
    print(f"    {r.cfg:44s} ret/DD {r.ret_dd:>6.2f}  {'BETTER' if r.ret_dd > best.ret_dd else 'worse'}")
print(f"\n  runtime {time.time()-t0:.0f}s")
