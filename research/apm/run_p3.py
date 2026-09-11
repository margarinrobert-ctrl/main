"""P3 -- the APM rule with a HARD FLATTEN AT 11:00 NEW YORK: out of sample and walk-forward.

11:00 is where the ENTRY WINDOW ENDS, so a flatten there caps every trade at 90 minutes and turns
a hold-to-the-cash-close rule into a morning scalp. P2 measured it as the worst of six flatten
times on the marginal ($8.24 a trade against $30.93 for the cash close); this asks the two
questions that decide whether it is tradeable anyway.

Four arms throughout, so the flatten and the stop are never confounded:
    A  source          no stop, no flatten   (exits at the cash close or an opposite cross)
    B  flatten only    no stop, flat 11:00
    C  stop only       3.0N stop, no flatten (the shipped default)
    D  both            3.0N stop, flat 11:00
"""
import sys, os, time, itertools
sys.path.insert(0, "research"); sys.path.insert(0, "research/apm")
import numpy as np, pandas as pd
import apm_core as A
from apm_exits import atr_series, reprice

R = "results/apm2/"; os.makedirs(R, exist_ok=True)
FLAT = 660          # 11:00 New York
print(__doc__); t0 = time.time()
pd.set_option("display.width", 245); pd.set_option("display.max_columns", 40)

ARMS = [("A source", 0.0, 0), ("B flat 11:00", 0.0, FLAT),
        ("C stop 3N", 3.0, 0), ("D stop+flat", 3.0, FLAT)]
data = {}
for mkt in ("NQ", "US100", "US30"):
    D = A.load(mkt, 10)
    tr, _ = A.run(D, profile="USIndex")
    data[mkt] = (D, tr, A.blocks(D), atr_series(D))
    print(f"  {mkt}: {len(tr)} trades  ({time.time()-t0:.0f}s)")

print("\n" + "=" * 136)
print("P3.1  OUT OF SAMPLE -- every block, in dollars, one contract, costs in")
print("=" * 136)
rows = []
reps = {}
for mkt, (D, tr, B, atr) in data.items():
    for lab, sm, fm in ARMS:
        q = reprice(D, tr, atr, stop_mult=sm, flat_min=fm)
        reps[(mkt, lab)] = q
        for bl, m in B.items():
            s = A.metrics(q, D, m)
            if s["n"] == 0:
                continue
            sub = q[m[q["ei"].to_numpy()]]
            rows.append(dict(market=mkt, arm=lab, block=bl, n=s["n"],
                             usd_trade=s["usd"] / s["n"], usd=s["usd"], pf=s["pf"],
                             win=s["win"], sharpe=s["sharpe"], dd=s["dd"] * D["pv"],
                             ret_dd=s["ret_dd"],
                             hold_min=float(np.median((sub["xi"] - sub["ei"]) * D["tf"])),
                             worst=float(sub["pts"].min() * D["pv"])))
T = pd.DataFrame(rows)
T.to_csv(R + "p3_blocks.csv", index=False)
print("  $/trade:")
print(T.pivot_table(index="arm", columns=["market", "block"], values="usd_trade").round(2).to_string())
print("\n  return / drawdown:")
print(T.pivot_table(index="arm", columns=["market", "block"], values="ret_dd").round(2).to_string())
print("\n  MEDIAN HOLD, minutes (the flatten's mechanism):")
print(T.pivot_table(index="arm", columns=["market", "block"], values="hold_min").round(0).to_string())
print("\n  averaged over all 8 market-blocks:")
print(T.groupby("arm").agg(usd_trade=("usd_trade", "mean"), pf=("pf", "mean"),
                           win=("win", "mean"), sharpe=("sharpe", "mean"), dd=("dd", "mean"),
                           ret_dd=("ret_dd", "mean"), worst=("worst", "mean"),
                           hold=("hold_min", "mean")).round(3).to_string())
blocks_pos = T.groupby("arm").apply(lambda g: (g.usd_trade > 0).sum(), include_groups=False)
print(f"\n  blocks profitable (of 8): " + "   ".join(f"{k} {v}" for k, v in blocks_pos.items()))

print("\n" + "=" * 136)
print("P3.2  THE MATCHED CONTROL WITH THE FLATTEN ON, inside each block")
print("=" * 136)
print("  The control must inherit the flatten too, or it is being asked an easier question.")
rows = []
for mkt, (D, tr, B, atr) in data.items():
    for lab, sm, fm in (("A source", 0.0, 0), ("B flat 11:00", 0.0, FLAT), ("D stop+flat", 3.0, FLAT)):
        q = reps[(mkt, lab)]
        for bl, m in B.items():
            s = A.metrics(q, D, m)
            if s["n"] < 15:
                continue
            res = A.control(D, tr, {}, m, profile="USIndex", draws=400, seed=5, mode="random")
            if res is None:
                continue
            # the control's own trades, repriced under the SAME exits -- not yet available from
            # apm_core, so the comparison below is the control WITHOUT the flatten and is therefore
            # CONSERVATIVE for arm A and OPTIMISTIC-FOR-THE-CONTROL for B and D. Flagged, not hidden.
            rows.append(dict(market=mkt, arm=lab, block=bl, n=s["n"], rule=s["mean"],
                             ctl_med=res["ctl_median"], p_unflattened_ctl=res["p"]))
C = pd.DataFrame(rows)
C.to_csv(R + "p3_controls.csv", index=False)
print(C.round(4).to_string(index=False))
print("\n  CAVEAT: apm_core's control walks the RULE's exits (cash close / opposite cross) and has")
print("  no flatten, so for arms B and D the control is being given a LONGER hold than the rule.")
print("  Read these p-values as the control's advantage, i.e. a lower bound on the rule.")

print("\n" + "=" * 136)
print("P3.3  WALK-FORWARD WITH FIXED CONSTANTS -- nothing re-selected, rolled forward")
print("=" * 136)
print("  This is the question the block split cannot answer: held completely fixed, does it earn")
print("  in every stretch, or only in the one that happened to be the research block?")
def folds(D, train_m, test_m):
    ts = pd.DatetimeIndex(D["dates"])
    d0 = pd.Timestamp(ts[0]).normalize().replace(day=1) + pd.DateOffset(months=1)
    dend = pd.Timestamp(ts[-1])
    k = lambda t: t.year * 10000 + t.month * 100 + t.day
    out, t = [], d0
    while t + pd.DateOffset(months=train_m + test_m) <= dend + pd.DateOffset(days=1):
        out.append((k(t + pd.DateOffset(months=train_m)), k(t + pd.DateOffset(months=train_m + test_m))))
        t = t + pd.DateOffset(months=test_m)
    return out

rows = []
for mkt, (D, tr, B, atr) in data.items():
    tm, sm_ = (12, 3) if mkt == "NQ" else (24, 6)
    fs = folds(D, tm, sm_)
    for lab, sm, fm in ARMS:
        q = reps[(mkt, lab)]
        key = D["key"][q["ei"].to_numpy()]
        pct = 100.0 * q["pts"].to_numpy() / q["epx"].to_numpy()
        vals, ns = [], []
        for a, b in fs:
            msk = (key >= a) & (key < b)
            if msk.sum() >= 3:
                vals.append(pct[msk].mean()); ns.append(int(msk.sum()))
        if not vals:
            continue
        vals = np.array(vals)
        rows.append(dict(market=mkt, arm=lab, folds=len(vals), pos=int((vals > 0).sum()),
                         mean_pct=vals.mean(), median_pct=float(np.median(vals)),
                         worst=vals.min(), best=vals.max(), trades=int(np.sum(ns))))
W = pd.DataFrame(rows)
W.to_csv(R + "p3_wfo_fixed.csv", index=False)
print(W.round(4).to_string(index=False))
print("\n  folds positive, by arm:")
for lab, _, _ in ARMS:
    g = W[W.arm == lab]
    print(f"    {lab:14s}  {int(g.pos.sum())}/{int(g.folds.sum())} folds positive across the "
          f"three markets, mean {g.mean_pct.mean():+.4f} %/trade")
print(f"\ntotal {time.time()-t0:.0f}s")
