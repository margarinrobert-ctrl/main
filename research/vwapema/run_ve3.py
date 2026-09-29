"""TEST 3 -- the corrected neighbourhood, the long-side drop-one, and the one gradient that looked
real, tested against a random filter of the SAME SELECTIVITY.

`run_ve2` swept EMA periods against a CACHED series, so five rungs returned identical numbers --
a fake plateau, and the bug signature CLAUDE.md records. `vecore.periods()` fixes it; this file
re-reads every ladder. The locked read in `run_ve2` used the spec's own values throughout and is
unaffected.
"""
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from research.vwapema import vecore as V

RNG = np.random.default_rng(31337)
pd.set_option("display.width", 210)
print(__doc__)
D = V.build()
r = D["blk"] == 0


def sig_drop(D, side, drop=None, p=None):
    sig, P = V.triggers(D, side=side, p=p)
    if drop is None:
        return sig
    m = np.ones(D["n"], bool)
    for k in ("C1", "C2", "C3", "C4", "C5", "C6", "ambig"):
        if k != drop:
            m &= np.nan_to_num(P[k], nan=False).astype(bool)
    return m & D["rth"]


print("=" * 112)
print("DROP-ONE, LONG SIDE (research) -- which of the six conditions earns its place?")
print("=" * 112)
rows = []
full = sig_drop(D, 1)
tf = V.run(D, full, side=1); tf = tf[tf.blk == 0]; sf = V.stats(tf)
rows.append(dict(dropped="-- none (full rule) --", n=sf["n"], R=sf["R"], pf=sf["pf"], win=sf["win"],
                 totR=sf["totR"], dR=0.0))
for k in ("C1", "C2", "C3", "C4", "C5", "C6", "ambig"):
    s = sig_drop(D, 1, drop=k)
    t = V.run(D, s, side=1); t = t[t.blk == 0]; st = V.stats(t)
    rows.append(dict(dropped=k, n=st["n"], R=st["R"], pf=st["pf"], win=st["win"], totR=st["totR"],
                     dR=st["R"] - sf["R"]))
DL = pd.DataFrame(rows)
print(DL.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
print("  dR > 0 means REMOVING it IMPROVES the rule.")

print("\n" + "=" * 112)
print("THE CORRECTED PARAMETER NEIGHBOURHOOD (long, research)")
print("=" * 112)
LAD = dict(ema_slow=[100, 150, 200, 250, 300], ema_pull=[20, 34, 50, 70, 100],
           ema_tight=[10, 20, 34], atr_len=[7, 14, 21],
           atr_stop=[0.25, 0.5, 0.75, 1.0, 1.5], vol_mult=[1.0, 1.1, 1.3, 1.5, 2.0],
           range_mult=[0.5, 0.8, 1.0, 1.3], wick_body=[1.0, 1.5, 2.0, 3.0])
rows = []
for k, vals in LAD.items():
    for x in vals:
        pp = {k: x}
        s, _ = V.triggers(D, side=1, p=pp)
        kw = dict(atr_stop=x) if k == "atr_stop" else {}
        t = V.run(D, s, side=1, p=pp, **kw); t = t[t.blk == 0]; st = V.stats(t)
        rows.append(dict(param=k, value=x, n=st["n"], R=st["R"], pf=st["pf"], spec=(x == V.PARAMS[k])))
for tR in (1.5, 2.0, 3.0, 4.0, 5.0, 99.0):
    s, _ = V.triggers(D, side=1)
    t = V.run(D, s, side=1, tgt_R=tR); t = t[t.blk == 0]; st = V.stats(t)
    rows.append(dict(param="target_R", value=tR, n=st["n"], R=st["R"], pf=st["pf"], spec=(tR == 3.0)))
N = pd.DataFrame(rows)
print(N.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
print(f"\n  cells positive on research: {int((N.R>0).sum())} of {len(N)}")
sp = N[N.spec]
print("  the spec's own value, per axis, and its RANK within its own ladder (1 = best):")
for k in LAD:
    sub = N[N.param == k].sort_values("R", ascending=False).reset_index(drop=True)
    rk = int(sub.index[sub.spec][0]) + 1 if sub.spec.any() else -1
    print(f"    {k:11s} spec {V.PARAMS[k]:>6}  rank {rk} of {len(sub)}   best {sub.value.iloc[0]} at R {sub.R.iloc[0]:+.4f}")

print("\n" + "=" * 112)
print("THE ONE GRADIENT THAT LOOKED REAL -- the volume filter, against a RANDOM FILTER of the")
print("SAME SELECTIVITY. `STUDY_V12`: restrictiveness alone raises a profit factor.")
print("=" * 112)
base, _ = V.triggers(D, side=1, p={"vol_mult": 0.0})     # the rule with C5 switched off
base_idx = np.flatnonzero(base & r)
rows = []
for vm in (1.0, 1.1, 1.3, 1.5, 2.0):
    s, _ = V.triggers(D, side=1, p={"vol_mult": vm})
    t = V.run(D, s, side=1); t = t[t.blk == 0]; st = V.stats(t)
    keep = int((s & r).sum())
    null = []
    for _ in range(400):
        g = np.zeros(D["n"], bool)
        g[RNG.choice(base_idx, size=min(keep, len(base_idx)), replace=False)] = True
        tt = V.run(D, g, side=1); tt = tt[tt.blk == 0]
        if len(tt) >= 20:
            null.append(tt.R.mean())
    null = np.array(null)
    rows.append(dict(vol_mult=vm, kept=keep, share=100 * keep / len(base_idx), n=st["n"], R=st["R"],
                     pf=st["pf"], rand_R=float(np.median(null)), p=float((null >= st["R"]).mean())))
VG = pd.DataFrame(rows)
print(VG.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
print("  `rand_R` keeps the same NUMBER of the C5-off signal bars at random. If the gradient is")
print("  selectivity rather than information, the random filter tracks it.")

print("\n" + "=" * 112)
print("EXIT ARCHITECTURE -- which piece is doing the work?")
print("=" * 112)
rows = []
s, _ = V.triggers(D, side=1)
for arm, kw in (("as specified (0.5N stop, 3R, EMA50 trail, EMA20 above 2.5R)", {}),
                ("no EMA20 tightening", dict(tighten=False)),
                ("no 3R target", dict(tgt_R=99.0)),
                ("no target AND no tightening", dict(tgt_R=99.0, tighten=False)),
                ("wider initial stop (1.5 ATR)", dict(atr_stop=1.5)),
                ("wider stop, no target", dict(atr_stop=1.5, tgt_R=99.0)),
                ("flatten at the session close", dict(flatten=True))):
    t = V.run(D, s, side=1, **kw); t = t[t.blk == 0]; st = V.stats(t)
    why = t.why.value_counts(normalize=True) * 100
    rows.append(dict(arm=arm, n=st["n"], R=st["R"], pf=st["pf"], win=st["win"],
                     stop_pct=float(why.get(0, 0)), tgt_pct=float(why.get(1, 0)),
                     trail_pct=float(why.get(2, 0))))
E = pd.DataFrame(rows)
print(E.to_string(index=False, float_format=lambda v: f"{v:8.3f}"))
print("\n  The close-only EMA trail is the spec's headline mechanic (its 7.1). Read `trail_pct`")
print("  beside `R`: it is where most trades end and its mean outcome is negative.")

os.makedirs("results/vwapema", exist_ok=True)
DL.to_csv("results/vwapema/dropone_long.csv", index=False)
N.to_csv("results/vwapema/neighbourhood.csv", index=False)
VG.to_csv("results/vwapema/volgradient.csv", index=False)
E.to_csv("results/vwapema/exits.csv", index=False)
