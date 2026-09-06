"""THE DECISIVE ABLATION: is it the CVD, or is it just that a confirmed pivot happened recently?

Every one of the four patterns is "a confirmed swing point occurred in the last w bars AND the CVD
comparison at that pivot pointed a particular way". Two facts from part 2 say the second half may be
doing nothing:

  * on a LONG-only base the BEARISH patterns beat the BULLISH ones by 11x (+0.108 vs +0.009), and
    ABSORBED BUYING -- the most bearish of the four, and the ONLY row negative on both blocks when
    STUDY_V54 measured this on NQ -- is the BEST pattern here;
  * all four are positive on all three gold blocks.

A condition that works whichever way its own directional test points is not that directional test.
So this file strips the CVD out and keeps everything else:

  A  the pattern as specified                    pivot + CVD comparison
  B  ANY of the four patterns                    pivot + any CVD comparison
  C  PIVOT ONLY, no CVD at all                   "a confirmed swing low occurred in the last w bars"
  D  pivot + a COIN-FLIP standing in for the CVD comparison, at the same firing rate

If C matches A, the CVD contributes nothing and the family is a pivot-recency filter wearing an
order-flow name. D is the same question asked with the selectivity held exactly fixed.
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
for p in (HERE, os.path.join(ROOT, "research"), os.path.join(ROOT, "research/xau"),
          os.path.join(ROOT, "research/v54")):
    sys.path.insert(0, p)

import xcvd                      # noqa: E402
import xau_core as X             # noqa: E402
import v54cvd as V54             # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 240)
OUT = os.path.join(ROOT, "results/xaucvd")


def line(t):
    print("\n" + "=" * 124)
    print(t)
    print("=" * 124, flush=True)


def recent(flag, w):
    return pd.Series(flag.astype(float)).rolling(w).max().to_numpy() > 0


print(__doc__)
t0 = time.time()
rng = np.random.default_rng(31)
G = dict(ent=20, exN=20, stop=2.0, tp=0.0, hold=480, side=1)

rows = []
for tf in (60, 240):
    D = xcvd.build(tf)
    E = X.run(D, G)
    sig = E.sig.to_numpy(); r = E.pct.to_numpy(); blk = E.blk.to_numpy()
    h, l, cvd, n = D["h"], D["l"], D["cvd"], D["n"]
    for k in (2, 3, 5):
        P = V54.patterns(h, l, cvd, k, n)
        hi, lo = V54.pivots(h, k)
        _h2, lo2 = V54.pivots(l, k)
        piv_lo = np.zeros(n, bool)
        for conf, _p in lo2:
            if conf < n:
                piv_lo[conf] = True
        piv_hi = np.zeros(n, bool)
        for conf, _p in hi:
            if conf < n:
                piv_hi[conf] = True
        piv_any = piv_lo | piv_hi
        for w in (10, 20, 30):
            arms = {
                "A  exhausted_sellers (as specified)": recent(P[0], w),
                "A  absorbed_buying   (as specified)": recent(P[3], w),
                "B  ANY of the four patterns":         recent(P[0] | P[1] | P[2] | P[3], w),
                "C  PIVOT LOW only, no CVD":           recent(piv_lo, w),
                "C  ANY PIVOT only, no CVD":           recent(piv_any, w),
            }
            for an, flag in arms.items():
                x = flag[sig]
                for i, bn in enumerate(X.BLOCKS):
                    m = blk == i
                    rr, kk = r[m], x[m]
                    if kk.sum() < 25 or kk.sum() > m.sum() - 10:
                        continue
                    rows.append(dict(tf=tf, k=k, w=w, arm=an, block=bn, n=int(m.sum()),
                                     kept=int(kk.sum()), keep=kk.mean(),
                                     edge=float(rr[kk].mean() - rr.mean())))
A = pd.DataFrame(rows)
A.to_csv(os.path.join(OUT, "ablation.csv"), index=False)

line("THE ABLATION -- mean research (A+B) edge and mean block-C edge, pooled over k, w and timeframe")
res = A[A.block != "C_locked"].groupby("arm").agg(cells=("edge", "size"), keep=("keep", "mean"),
                                                  mean_edge=("edge", "mean"),
                                                  pos=("edge", lambda z: 100 * (z > 0).mean()))
lok = A[A.block == "C_locked"].groupby("arm").agg(mean_C=("edge", "mean"),
                                                  pos_C=("edge", lambda z: 100 * (z > 0).mean()))
T = res.join(lok)
print(T.to_string(float_format=lambda z: f"{z:9.4f}"))

line("THE SAME, SPLIT BY TIMEFRAME (60m = 4 sub-bars a chart bar, 240m = 16)")
for tf in (60, 240):
    z = A[(A.tf == tf) & (A.block != "C_locked")].groupby("arm").agg(
        cells=("edge", "size"), keep=("keep", "mean"), mean_edge=("edge", "mean"))
    print(f"\n  {tf}m")
    print("   " + z.to_string(float_format=lambda v: f"{v:9.4f}").replace("\n", "\n   "))

line("MATCHED HEAD-TO-HEAD: the specified pattern against PIVOT-ONLY at the SAME (k, w, tf, block)")
piv = A.pivot_table(index=["tf", "k", "w", "block"], columns="arm", values="edge")
ca, cc = "A  exhausted_sellers (as specified)", "C  PIVOT LOW only, no CVD"
cb = "A  absorbed_buying   (as specified)"
q = piv[[ca, cb, cc]].dropna()
print(f"  {len(q)} matched cells.")
print(f"  exhausted_sellers beats pivot-only in {100*(q[ca] > q[cc]).mean():.0f}% of them "
      f"(chance 50%), mean difference {(q[ca]-q[cc]).mean():+.5f}")
print(f"  absorbed_buying   beats pivot-only in {100*(q[cb] > q[cc]).mean():.0f}% of them, "
      f"mean difference {(q[cb]-q[cc]).mean():+.5f}")
print(f"\n  pivot-only mean edge {q[cc].mean():+.5f}   exhausted_sellers {q[ca].mean():+.5f}   "
      f"absorbed_buying {q[cb].mean():+.5f}")

line("D -- A COIN FLIP IN PLACE OF THE CVD COMPARISON, at the SAME firing rate. 300 draws")
print("  Take the pivot-only flag and randomly keep the same FRACTION of its pivots that the CVD")
print("  comparison keeps. If the real pattern sits inside this distribution, the CVD is decoration.\n")
print(f"  {'tf':>5} {'k':>2} {'w':>3} {'block':10s} {'real (exh.sell)':>16} {'coin p50':>10} {'coin p95':>10} {'p':>7}")
dr_rows = []
for tf in (60, 240):
    D = xcvd.build(tf)
    E = X.run(D, G)
    sig = E.sig.to_numpy(); r = E.pct.to_numpy(); blk = E.blk.to_numpy()
    h, l, cvd, n = D["h"], D["l"], D["cvd"], D["n"]
    for k in (2, 3):
        P = V54.patterns(h, l, cvd, k, n)
        _h2, lo2 = V54.pivots(l, k)
        confs = np.array([c for c, _p in lo2 if c < n])
        for w in (20,):
            real = recent(P[0], w)[sig]
            share = P[0][confs].mean() if len(confs) else 0.0
            for i, bn in enumerate(X.BLOCKS):
                m = blk == i
                rr, kk = r[m], real[m]
                if kk.sum() < 25:
                    continue
                obs = rr[kk].mean() - rr.mean()
                draws = np.empty(300)
                for d in range(300):
                    pick = confs[rng.random(len(confs)) < max(share, 1e-9)]
                    f_ = np.zeros(n, bool); f_[pick] = True
                    z = recent(f_, w)[sig][m]
                    draws[d] = rr[z].mean() - rr.mean() if 25 <= z.sum() <= m.sum() - 10 else np.nan
                pv = float(np.nanmean(draws >= obs))
                dr_rows.append(dict(tf=tf, k=k, w=w, block=bn, obs=obs, p=pv))
                print(f"  {tf:>5} {k:>2} {w:>3} {bn:10s} {obs:>+16.5f} {np.nanmedian(draws):>+10.5f} "
                      f"{np.nanquantile(draws,0.95):>+10.5f} {pv:>7.3f}")
pd.DataFrame(dr_rows).to_csv(os.path.join(OUT, "coinflip.csv"), index=False)
print(f"\n  runtime {time.time()-t0:.0f}s")
