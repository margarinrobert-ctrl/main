"""VETO vs SUBSET -- and the shipped script is the VETO.

The parity harness surfaced this. `run_xcvd.py` scored every feature as a SUBSET: run the base
ungated, then split its realised trades by the feature. The shipped script cannot do that. It is a
VETO -- the gate decides which bars may OPEN a trade, so refusing one trade frees the position lock
and lets a LATER breakout be taken that the ungated run never saw.

CLAUDE.md has this exact rule from `STUDY_AUCTION`: "A conditional split of realised trades is not
a filter test -- filter the TRIGGERS and re-simulate." The subset number is not wrong, it answers a
different question ("among the trades this system took, did the flagged ones do better"), and the
VP/TPO handoff measured the same split from the other side (32 lock-freed trades reading PF 0.92).

Block A: 844 ungated trades, 318 kept as a subset -- but 400 events when the gate is run as a veto.
So 82 trades exist ONLY because the gate refused an earlier one. This file scores the veto properly,
against a control built the SAME way: a random gate passing the same FRACTION OF BARS, re-simulated
end to end, so the lock is re-run in the null exactly as it is in the rule.
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

import xcvd                     # noqa: E402
import xau_core as X            # noqa: E402
import v54cvd as V54            # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 240)
OUT = os.path.join(ROOT, "results/xaucvd")


def line(t):
    print("\n" + "=" * 122)
    print(t)
    print("=" * 122, flush=True)


def gate_flag(D, k, w, pat=0):
    l, h, cvd, n = D["l"], D["h"], D["cvd"], D["n"]
    P = V54.patterns(h, l, cvd, k, n)
    return pd.Series(P[pat].astype(float)).rolling(w).max().to_numpy() > 0


print(__doc__)
t0 = time.time()
rng = np.random.default_rng(77)
G = dict(ent=20, exN=20, stop=2.0, tp=0.0, hold=480, side=1)
K, W = 2, 20
D = xcvd.build(60)

base = X.run(D, G)
gate = gate_flag(D, K, W, 0)
veto = X.run(D, G, gate=gate)

line("THE SAME GATE, SCORED BOTH WAYS")
print(f"  {'block':10s} {'base n':>7} {'base %/ev':>10} | {'SUBSET n':>9} {'subset %/ev':>12} | "
      f"{'VETO n':>7} {'veto %/ev':>10} {'lock-freed':>11} {'their %/ev':>11}")
rows = []
for i, bn in enumerate(X.BLOCKS):
    b = base[base.blk == i]
    if len(b) < 20:
        continue
    x = gate[b.sig.to_numpy()]
    sub = b[x]
    v = veto[veto.blk == i]
    extra = v[~v.sig.isin(sub.sig)]
    rows.append(dict(block=bn, base_n=len(b), base=b.pct.mean(), sub_n=len(sub), sub=sub.pct.mean(),
                     veto_n=len(v), veto=v.pct.mean(), extra_n=len(extra),
                     extra=extra.pct.mean() if len(extra) else np.nan))
    print(f"  {bn:10s} {len(b):>7} {b.pct.mean():>10.5f} | {len(sub):>9} {sub.pct.mean():>12.5f} | "
          f"{len(v):>7} {v.pct.mean():>10.5f} {len(extra):>11} "
          f"{(extra.pct.mean() if len(extra) else np.nan):>11.5f}")
R = pd.DataFrame(rows)
R.to_csv(os.path.join(OUT, "veto_vs_subset.csv"), index=False)
print("\n  'lock-freed' are trades the VETO run takes that the ungated run never saw, because the")
print("  gate refused an earlier breakout and released the one-position lock.")

line("THE VETO AGAINST ITS OWN CONTROL: a RANDOM gate passing the same FRACTION OF BARS, re-simulated")
print("  This is the null the shipped script actually faces. 400 draws, the whole walk re-run each time.\n")
share = float(gate.mean())
print(f"  the real gate passes {100*share:.1f}% of bars\n")
print(f"  {'block':10s} {'rule n':>7} {'rule %/ev':>10} {'ctl n':>7} {'ctl p50':>10} {'ctl p95':>10} "
      f"{'excess':>9} {'p':>7}")
res = []
for i, bn in enumerate(X.BLOCKS):
    v = veto[veto.blk == i]
    if len(v) < 20:
        continue
    obs = v.pct.mean()
    draws = np.empty(400)
    ns = np.empty(400)
    for d in range(400):
        gr = rng.random(D["n"]) < share
        vr = X.run(D, G, gate=gr)
        vr = vr[vr.blk == i]
        draws[d] = vr.pct.mean() if len(vr) >= 20 else np.nan
        ns[d] = len(vr)
    pv = float(np.nanmean(draws >= obs))
    res.append(dict(block=bn, n=len(v), obs=obs, ctl=float(np.nanmedian(draws)), p=pv))
    print(f"  {bn:10s} {len(v):>7} {obs:>10.5f} {np.nanmedian(ns):>7.0f} {np.nanmedian(draws):>10.5f} "
          f"{np.nanquantile(draws,0.95):>10.5f} {obs-np.nanmedian(draws):>+9.5f} {pv:>7.3f}")
V = pd.DataFrame(res)
V.to_csv(os.path.join(OUT, "veto_control.csv"), index=False)

line("AND AGAINST DOING NOTHING -- the ungated base, which is the real alternative")
for i, bn in enumerate(X.BLOCKS):
    b = base[base.blk == i]
    v = veto[veto.blk == i]
    if len(b) < 20:
        continue
    tb = len(b) * b.pct.mean()
    tv = len(v) * v.pct.mean()
    pfb = b.pct[b.pct > 0].sum() / max(-b.pct[b.pct < 0].sum(), 1e-9)
    pfv = v.pct[v.pct > 0].sum() / max(-v.pct[v.pct < 0].sum(), 1e-9)
    print(f"  {bn:10s} ungated {len(b):>4} trades  PF {pfb:.3f}  total {tb:>8.2f}%   |   "
          f"gated {len(v):>4}  PF {pfv:.3f}  total {tv:>8.2f}%   "
          f"({'gate WINS' if tv > tb else 'gate LOSES total return'})")
print(f"\n  runtime {time.time()-t0:.0f}s")
