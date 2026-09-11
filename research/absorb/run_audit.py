"""Causality audit and base rates -- run BEFORE any P&L, per the branch's standing rule.

The truncation audit is the only honest leakage test: recompute every series on history that ENDS
at bar i and require the value at bar i to be unchanged. It has caught two real leaks on this
branch that inspection missed."""
import os, sys, warnings
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ab_core as A
warnings.filterwarnings("ignore")
def line(t): print("\n" + "=" * 110 + f"\n{t}\n" + "=" * 110)

MK, TF = "NQ", 15
D = A.build(MK, TF)
n = D["n"]

line("A. TRUNCATION AUDIT -- rebuild on history ending at bar i, compare the value AT bar i")
import v63feeds as FD
f = FD.bars(MK, TF)
rng = np.random.default_rng(0)
probes = rng.choice(np.arange(3000, n - 5), size=25, replace=False)
cols = ["mid_prev", "scaled"] + [f"lv_h.{k}" for k in ("1h", "4h", "D", "W", "M")] \
       + [f"lv_l.{k}" for k in ("1h", "4h", "D", "W", "M")]
bad = {c: 0 for c in cols}
for i in sorted(probes):
    sub = f.iloc[: i + 1]
    Ds = A.build.__wrapped__(MK, TF) if False else None
    # rebuild from the truncated frame by monkeypatching the loader
    orig = FD.bars
    FD.bars = lambda m, t, _s=sub: _s
    try:
        Dt = A.build(MK, TF)
    finally:
        FD.bars = orig
    for c in cols:
        if "." in c:
            a, b = c.split("."); fv = D[a][b][i]; tv = Dt[a][b][-1]
        else:
            fv = D[c][i]; tv = Dt[c][-1]
        if not (np.isnan(fv) and np.isnan(tv)) and not np.isclose(np.nan_to_num(fv), np.nan_to_num(tv), rtol=1e-9, atol=1e-9):
            bad[c] += 1
tot = sum(bad.values())
print(f"  {len(probes)} probe bars x {len(cols)} columns; leaking columns: "
      + (", ".join(f"{k} ({v})" for k, v in bad.items() if v) if tot else "NONE"))

line("B. BASE RATES -- what each condition actually removes, measured on the bars it would filter")
fin = np.isfinite(D["atr"]) & (D["atr"] > 0); fin[:300] = False
print(f"  all bars considered: {fin.sum():,}")
print(f"  absorption, published threshold scaledVol >= 0.1:")
print(f"    passes {100*np.nanmean((D['scaled'] >= 0.1)[fin]):.1f}% of all bars -- the threshold is nearly unconditional")
for thr in (0.1, 0.5, 1.0, 2.0, 4.0):
    sh = np.nanmean((D["scaled"] >= thr)[fin])
    print(f"    scaledVol >= {thr:>4}: {100*sh:5.1f}% of bars")
print(f"  wick geometry (the selective part):")
print(f"    upper zone (SELLING absorption): {100*D['upper_zone'][fin].mean():5.1f}%")
print(f"    lower zone (BUYING  absorption): {100*D['lower_zone'][fin].mean():5.1f}%")
print(f"  full published bubble = threshold AND zone:")
absS = (D["scaled"] >= 0.1) & D["upper_zone"]; absB = (D["scaled"] >= 0.1) & D["lower_zone"]
print(f"    selling {100*np.nanmean(absS[fin]):5.1f}%   buying {100*np.nanmean(absB[fin]):5.1f}%")

line("C. LEVEL TOUCH RATES, and the LIFT absorption has ON THOSE BARS (the number that decides it)")
print(f"  {'level':>10}  {'resist touch':>13} {'support touch':>14} | {'absorb|touch':>13} {'absorb|all':>11} {'lift':>6}")
for k in ("mid", "1h", "4h", "D", "W", "M"):
    s = A.signals(D, levels=(k,), vol_min=0.0, need_absorb=False)
    res = (s == -1); sup = (s == 1)
    # absorption base rate on those bars vs everywhere
    pr_t = np.nanmean(absS[res]) if res.sum() else np.nan
    pr_a = np.nanmean(absS[fin])
    print(f"  {k:>10}  {100*res.mean():12.2f}% {100*sup.mean():13.2f}% | {100*pr_t:12.1f}% {100*pr_a:10.1f}% {pr_t/pr_a:6.2f}x")
print("  A lift near 1.0 means absorption tells you nothing you did not already know from the touch.")

line("D. HOW MANY TRADES THE COMBINED RULE ACTUALLY PRODUCES")
for lv in (("mid",), ("1h", "4h"), ("mid", "1h", "4h"), ("mid", "1h", "4h", "D", "W", "M")):
    for na_ in (True, False):
        s = A.signals(D, levels=lv, vol_min=0.1, need_absorb=na_)
        print(f"  levels={str(lv):<34} absorption={'ON ' if na_ else 'off'}  signals {int((s!=0).sum()):>6,}"
              f"  (long {int((s==1).sum()):>5,} / short {int((s==-1).sum()):>5,})")
