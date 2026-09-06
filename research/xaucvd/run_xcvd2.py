"""GOLD x DONCHIAN x CVD, part 2 -- the leakage audit, the sign-structure test, the neighbourhood,
and ONE read of block C.

THE SIGN-STRUCTURE TEST IS THE DECISIVE ONE and it is cheap. The four patterns make a DIRECTIONAL
prediction: on a LONG-only base the two BULLISH readings (exhausted sellers = price LL + CVD HL;
absorbed selling = price HL + CVD LL) should help and the two BEARISH ones should not.
`STUDY_V54_CVD_KAMA` measured exactly that on NQ -- the two bullish patterns cleared both blocks or
came close, and ABSORBED BUYING, the most bearish of the four, was the only NEGATIVE row on both
blocks, "which is the sign a long-only system predicts".

If gold's ranking does not respect that ordering, the pattern family is not measuring what it
claims to measure here, whatever any individual p-value says.
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
for p in (HERE, os.path.join(ROOT, "research"), os.path.join(ROOT, "research/xau")):
    sys.path.insert(0, p)

import xcvd                      # noqa: E402
import xau_core as X             # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 240)
OUT = os.path.join(ROOT, "results/xaucvd")
os.makedirs(OUT, exist_ok=True)


def line(t):
    print("\n" + "=" * 124)
    print(t)
    print("=" * 124, flush=True)


print(__doc__)
t0 = time.time()
rng = np.random.default_rng(9)
G54 = dict(ent=20, exN=20, stop=2.0, tp=0.0, hold=480, side=1)

line("STEP 4 -- TRUNCATION AUDIT. Recompute every feature on history ENDING at bar i")
print("  This is the test that caught the divergence fill-forward leak in STUDY_DIVERGENCE_CONFIRM")
print("  (+37 full against +999 truncated). A confirmed pivot is stamped at i+k; anything that")
print("  reaches back to the pivot bar itself would show up here.\n")
for tf in (60, 240):
    D = xcvd.build(tf)
    F = xcvd.features(D)
    bad, checked, npb = xcvd.truncation_audit(D, F, probes=25, seed=3)
    print(f"  {tf:>4}m  {len(bad):>3} mismatches over {checked:,} value comparisons on {npb} probe bars")
    for b in bad[:6]:
        print(f"         bar {b[0]}  {b[1]}  full {b[2]:.6f}  truncated {b[3]:.6f}")

line("STEP 5 -- THE SIGN STRUCTURE. On a LONG-only base the two BULLISH patterns should lead")
P = pd.read_csv(os.path.join(OUT, "patterns.csv"))
P["polarity"] = np.where(P.pattern.isin(["exhausted_sellers", "absorbed_selling"]), "BULLISH", "BEARISH")
t = P.groupby(["polarity", "pattern"]).agg(cells=("edge", "size"), mean_edge=("edge", "mean"),
                                           pos=("edge", lambda z: 100 * (z > 0).mean()),
                                           best_p=("p", "min"),
                                           mean_C=("c_edge", "mean")).reset_index()
print(t.to_string(index=False, float_format=lambda z: f"{z:9.4f}"))
bull = P[P.polarity == "BULLISH"].edge.mean()
bear = P[P.polarity == "BEARISH"].edge.mean()
print(f"\n  mean research edge  BULLISH {bull:+.5f}   BEARISH {bear:+.5f}")
print(f"  On NQ (STUDY_V54) the ordering was bullish-first and ABSORBED BUYING was the only negative")
print(f"  row on both blocks. Here the best pattern of the four is "
      f"{t.sort_values('mean_edge', ascending=False).iloc[0]['pattern'].upper()} "
      f"({t.sort_values('mean_edge', ascending=False).iloc[0]['polarity']}).")

line("STEP 6 -- THE NEIGHBOURHOOD. STUDY_V55: the k x w grid is the evidence, not the p-value")
print("  On NQ, EXHAUSTED SELLERS was positive in ALL 16 cells of the pivot-width x recency-window")
print("  grid on BOTH blocks and fell monotonically as the window widened. That coherence, not any")
print("  single cell, is what made it shippable.\n")
for pat in ("exhausted_sellers", "absorbed_buying"):
    for tf in (60, 240):
        z = P[(P.pattern == pat) & (P.tf == tf)]
        if len(z) == 0:
            continue
        piv = z.pivot_table(index="k", columns="w", values="edge")
        print(f"  {pat}  {tf}m  research edge by pivot width (k) x recency window (w):")
        print("   " + piv.to_string(float_format=lambda v: f"{v:+8.4f}").replace("\n", "\n   "))
        print(f"   cells positive {100*(z.edge > 0).mean():.0f}%   monotone in w? "
              f"{'yes' if all(piv.iloc[i].is_monotonic_decreasing for i in range(len(piv))) else 'NO'}\n")

line("STEP 7 -- BLOCK C, ONE READ, for the single BH survivor")
print("  >>> Block C has ALREADY been read once on gold by STUDY_XAU_TWO_LAYER. This is the SECOND")
print("  >>> read. It is reported as DESCRIPTIVE, and the multiplicity is stated: 229 screened cells")
print("  >>> here, plus 690 counted trials in the earlier gold study.\n")
S = pd.read_csv(os.path.join(OUT, "screen.csv"))
surv = S[S.bh].sort_values("p")
if len(surv) == 0:
    print("  no BH survivor -- nothing earned a locked read")
else:
    r = surv.iloc[0]
    print(f"  survivor: {r.feature}  on {r.geom} at {int(r.tf)}m")
    print(f"  research: base {r.base:+.5f} -> filtered {r.filt:+.5f}  (edge {r.edge:+.5f}, p {r.p:.3f}, "
          f"keeps {100*r.keep_frac:.0f}%)\n")
    D = xcvd.build(int(r.tf))
    F = xcvd.features(D)
    E = X.run(D, G54)
    sig = E.sig.to_numpy()
    x = F[r.feature].to_numpy(float)[sig]
    lok = E.blk.to_numpy() == 2
    rl = E.pct.to_numpy()[lok]
    kl = x[lok] > 0.5
    print(f"  {'arm':34s} {'n':>5} {'net %/event':>12} {'PF':>7}")
    for nm, sel in (("block C, unfiltered", np.ones(len(rl), bool)), ("block C + the filter", kl)):
        z = rl[sel]
        if len(z) < 10:
            print(f"  {nm:34s} {len(z):>5}   (too few)"); continue
        pf = z[z > 0].sum() / max(-z[z < 0].sum(), 1e-9)
        print(f"  {nm:34s} {len(z):>5} {z.mean():>12.5f} {pf:>7.3f}")
    if kl.sum() >= 10:
        obs = rl[kl].mean() - rl.mean()
        draws = np.array([rl[rng.choice(len(rl), int(kl.sum()), replace=False)].mean() - rl.mean()
                          for _ in range(2000)])
        print(f"  edge {obs:+.5f}   random filter of the same size: median {np.median(draws):+.5f}, "
              f"p {np.mean(draws >= obs):.3f}")
        print(f"  kept on block C {100*kl.mean():.0f}% against {100*r.keep_frac:.0f}% on research")

line("STEP 8 -- DOES A BETTER DELTA HELP? 60m has 4 sub-bars a chart bar, 240m has 16")
print("  If CVD carried information, the FINER delta should score better. It is the cleanest")
print("  internal check available without a 1-minute gold feed.\n")
S["fam"] = S.feature.str.split(".").str[0]
for tf in (60, 240):
    z = S[S.tf == tf]
    zd = z[z.fam == "div"]
    print(f"  {tf:>4}m ({tf//15:>2} sub-bars)  cells {len(z):>3}  p<=0.05 {int((z.p<=0.05).sum()):>2} "
          f"(chance {0.05*len(z):.1f})  mean edge {z.edge.mean():+.5f}   div-family mean {zd.edge.mean():+.5f}")
print(f"\n  runtime {time.time()-t0:.0f}s")
