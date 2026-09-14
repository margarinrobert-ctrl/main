"""TEST 1 -- what the six conditions do, what the geometry needs, and the matched control.

RESEARCH BLOCK ONLY (2010-01 .. 2020-05). Nothing here reads the locked block.

Order is the branch's: base rates on the trigger's own bars BEFORE any P&L (five studies here have
found a proposed confirmation was the trigger restated); then the break-even the geometry implies,
because a win rate without its own bound is not a number; then the matched control, run as a GATE
and not as a final check.
"""
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from research.vwapema import vecore as V

RNG = np.random.default_rng(20260906)
pd.set_option("display.width", 210)
print(__doc__)
D = V.build()
r = D["blk"] == 0
print(f"  XAU_ISO_15m {D['n']:,} bars from {V.START}, {int(D['rth'].sum()):,} in the New York session.")
print(f"  research to {D['cut_date']} ({int((r & D['rth']).sum()):,} RTH bars), locked after.\n")

# ------------------------------------------------------------------ 1. condition base rates
print("=" * 112)
print("CONDITION BASE RATES -- how much does each of the six actually remove?")
print("=" * 112)
print("  `alone` is the share of RTH research bars the condition passes. `given the rest` is the")
print("  share it passes among bars that already satisfy the OTHER five -- a condition near 100%")
print("  there is decoration, and one near 0% is the binding constraint.\n")
rows = []
for side, nm in ((1, "LONG"), (-1, "SHORT")):
    sig, P = V.triggers(D, side=side)
    pop = r & D["rth"]
    keys = ["C1", "C2", "C3", "C4", "C5", "C6", "ambig"]
    for k in keys:
        others = np.ones(D["n"], bool)
        for k2 in keys:
            if k2 != k:
                others &= np.nan_to_num(P[k2], nan=False).astype(bool)
        others &= pop
        m = np.nan_to_num(P[k], nan=False).astype(bool)
        rows.append(dict(side=nm, cond=k, alone_pct=100 * m[pop].mean(),
                         given_rest_pct=100 * m[others].mean() if others.sum() else np.nan,
                         n_if_dropped=int(others.sum()), n_full=int((others & m).sum())))
B = pd.DataFrame(rows)
for nm in ("LONG", "SHORT"):
    print(f"  --- {nm} ---")
    print(B[B.side == nm].drop(columns="side").to_string(index=False, float_format=lambda v: f"{v:9.2f}"))
    print()
print("  C4a (pin bar) vs C4b (engulfing), share of the full signal set each supplies:")
for side, nm in ((1, "LONG"), (-1, "SHORT")):
    sig, P = V.triggers(D, side=side)
    s = sig & r
    a = np.nan_to_num(P["C4a"], nan=False).astype(bool)[s]
    b = np.nan_to_num(P["C4b"], nan=False).astype(bool)[s]
    print(f"    {nm}: n {int(s.sum())}, pin {100*a.mean():.1f}%, engulfing {100*b.mean():.1f}%, both {100*(a&b).mean():.1f}%")

# ------------------------------------------------------------------ 2. the arithmetic
print("\n" + "=" * 112)
print("THE ARITHMETIC -- cost as a fraction of risk, and the break-even the geometry implies")
print("=" * 112)
sigL, _ = V.triggers(D, side=1)
tL = V.run(D, sigL, side=1); tL = tL[tL.blk == 0]
med_risk = float(tL.risk.median())
rt = V.COST_RT + 2 * V.SLIP
print(f"  median risk (entry to initial stop): {med_risk:.3f} USD/oz    median ATR14 at signal: "
      f"{float(np.nanmedian(D['atr'][sigL & r])):.3f} USD/oz")
print(f"  round turn charged: {rt:.3f} USD/oz  =  {100*rt/med_risk:.2f}% of risk  =  {rt/med_risk:.4f} R")
print(f"  the spec assumes 0.24R of cost; measured here it is {rt/med_risk:.4f}R, "
      f"{'LOWER' if rt/med_risk < 0.24 else 'HIGHER'} -- the spec's ATR figures were wrong by its own gap 6.")
print(f"  the spec assumes a $12 15-minute ATR (its 5.1) and its cost table implies $20; measured "
      f"median is {float(np.nanmedian(D['atr'][D['rth']])):.2f}.")
c_in_R = rt / med_risk
for q in (3.0, 2.0, 1.5):
    print(f"    at a {q:.1f}R target the driftless break-even win rate is "
          f"{100*(1+c_in_R)/(1+q):.2f}%   (paper claims 45.3% at 3R)")

# ------------------------------------------------------------------ 3. the paper's assumed distribution vs measured
print("\n" + "=" * 112)
print("THE PAPER'S ASSUMED OUTCOME DISTRIBUTION AGAINST THE MEASURED ONE")
print("=" * 112)
print("  The paper's section 6.1 assumed full win 0.30 / partial 0.20 / breakeven 0.08 / loss 0.42.")
print("  Its Table 4 counts imply the same shape. Measured on gold, research block:\n")
lab = {0: "initial stop hit", 1: "3R target hit", 2: "trail close", 3: "held to the end"}
for side, nm in ((1, "LONG"), (-1, "SHORT")):
    sig, _ = V.triggers(D, side=side)
    t = V.run(D, sig, side=side); t = t[t.blk == 0]
    print(f"  --- {nm}: {len(t)} trades ---")
    for k in (1, 2, 0, 3):
        m = t.why == k
        if m.sum():
            print(f"    {lab[k]:18s} {int(m.sum()):4d} ({100*m.mean():5.1f}%)  mean {t.R[m].mean():+7.3f} R")
    print(f"    paper's claim: 3R target 30%, partial 20%, breakeven 8%, loss 42%; "
          f"measured target rate {100*(t.why==1).mean():.1f}%\n")

# ------------------------------------------------------------------ 4. the matched control -- the gate
print("=" * 112)
print("THE MATCHED CONTROL -- the same exit machine entered at a RANDOM New York bar")
print("=" * 112)
print("  Same side, same 0.5xATR initial stop, same 3R target, same close-only EMA trail, same")
print("  costs and the same one-position lock; only the entry BAR is random, drawn from the RTH")
print("  population at the rule's own rate and re-simulated end to end.\n")


def control(D, n_target, side, draws=400, **kw):
    idx = np.flatnonzero(r & D["rth"])
    rate = min(1.0, n_target / max(len(idx), 1))
    out = []
    for _ in range(draws):
        g = np.zeros(D["n"], bool)
        g[idx[RNG.random(len(idx)) < rate]] = True
        t = V.run(D, g, side=side, **kw); t = t[t.blk == 0]
        if len(t) >= 20:
            out.append((t.R.mean(), t.pct.mean(), t.R.sum()))
    return np.array(out)


rows = []
for side, nm in ((1, "LONG"), (-1, "SHORT")):
    sig, _ = V.triggers(D, side=side)
    t = V.run(D, sig, side=side); t = t[t.blk == 0]
    st = V.stats(t)
    ctl = control(D, st["n"], side)
    rows.append(dict(side=nm, n=st["n"], R=st["R"], pf=st["pf"], win=st["win"],
                     ctl_R=float(np.median(ctl[:, 0])), p_R=float((ctl[:, 0] >= st["R"]).mean()),
                     ctl_win=np.nan))
C = pd.DataFrame(rows)
print(C.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))

# ------------------------------------------------------------------ 5. arms
print("\n" + "=" * 112)
print("ARMS -- is it cost, is it the exit machine, is it drift?")
print("=" * 112)
rows = []
for side, nm in ((1, "LONG"), (-1, "SHORT")):
    sig, _ = V.triggers(D, side=side)
    for arm, kw in (("as specified", {}),
                    ("ZERO COST", dict(cost_rt=0.0, slip=0.0)),
                    ("spec's 0.24R cost", dict(cost_rt=0.24 * med_risk, slip=0.0)),
                    ("no 3R target", dict(tgt_R=99.0)),
                    ("no EMA20 tightening", dict(tighten=False)),
                    ("flatten at session close", dict(flatten=True)),
                    ("volume-free VWAP", {})):
        s2 = sig
        if arm == "volume-free VWAP":
            s2, _ = V.triggers(D, side=side, use_vwap_vol=False)
        t = V.run(D, s2, side=side, **kw); t = t[t.blk == 0]
        st = V.stats(t)
        rows.append(dict(side=nm, arm=arm, n=st["n"], R=st["R"], pf=st["pf"], win=st["win"], totR=st["totR"]))
A = pd.DataFrame(rows)
print(A.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))

os.makedirs("results/vwapema", exist_ok=True)
B.to_csv("results/vwapema/baserates.csv", index=False)
C.to_csv("results/vwapema/control.csv", index=False)
A.to_csv("results/vwapema/arms.csv", index=False)
