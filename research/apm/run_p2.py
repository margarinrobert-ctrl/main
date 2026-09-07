"""P2 -- what a STOP and a HARD FLATTEN would do to the APM rule, before either is shipped.

The source has NO stop, target, trail or flatten: it exits at the cash close or an opposite cross.
Adding a stop or a flatten is therefore a CHANGE TO THE STRATEGY, not a safety feature, and this
branch has recorded a flatten as destructive fifteen times and the stop axis as monotone toward
wider on eight families. So it gets measured before it gets an input.

The entry set is unaffected. Entries depend on the SHADOW (the unfiltered rule's own position),
never on the real position, and reversals never fire on this data (0 in three years), so a stop
cannot create or destroy an entry -- only change where a trade ends. That makes an exact
post-processing walk valid: take the rule's own trades and re-resolve each exit.
"""
import sys, os, time, itertools
sys.path.insert(0, "research"); sys.path.insert(0, "research/apm")
import numpy as np, pandas as pd
import apm_core as A

R = "results/apm2/"; os.makedirs(R, exist_ok=True)
print(__doc__); t0 = time.time()
pd.set_option("display.width", 240); pd.set_option("display.max_columns", 40)


from apm_exits import atr_series, reprice


MK = [("NQ", 570, 960), ("US100", 570, 960), ("US30", 570, 960)]
data = {}
for mkt, _, _ in MK:
    D = A.load(mkt, 10)
    tr, _ = A.run(D, profile="USIndex")
    data[mkt] = (D, tr, A.blocks(D), atr_series(D))
    print(f"  {mkt}: {len(tr)} trades, ATR built  ({time.time()-t0:.0f}s)")

print("\n" + "=" * 128)
print("P2.1  THE STOP AXIS -- marginal per rung, every block, $/trade")
print("=" * 128)
rows = []
for mkt, (D, tr, B, atr) in data.items():
    for sm in (0.0, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 6.0):
        q = reprice(D, tr, atr, stop_mult=sm)
        for bl, m in B.items():
            s = A.metrics(q, D, m)
            if s["n"] == 0:
                continue
            rows.append(dict(market=mkt, stop=sm, block=bl, n=s["n"], usd=s["usd"],
                             usd_trade=s["usd"] / s["n"], pf=s["pf"], win=s["win"],
                             sharpe=s["sharpe"], dd_usd=s["dd"] * D["pv"],
                             ret_dd=s["ret_dd"],
                             stopped=float((q[m[q["ei"].to_numpy()]]["exit_kind"] == "stop").mean())))
S = pd.DataFrame(rows)
S.to_csv(R + "p2_stop.csv", index=False)
piv = S.pivot_table(index="stop", columns=["market", "block"], values="usd_trade").round(2)
print("  $/trade by stop multiple:")
print(piv.to_string())
print("\n  MARGINAL over all blocks and markets:")
mg = S.groupby("stop").agg(cells=("usd", "size"), usd_trade=("usd_trade", "mean"),
                           pf=("pf", "mean"), sharpe=("sharpe", "mean"),
                           dd=("dd_usd", "mean"), ret_dd=("ret_dd", "mean"),
                           stopped=("stopped", "mean")).round(3)
print(mg.to_string())

print("\n" + "=" * 128)
print("P2.2  THE HARD FLATTEN -- marginal per time, every block, $/trade")
print("=" * 128)
rows = []
for mkt, (D, tr, B, atr) in data.items():
    for fm in (0, 660, 720, 780, 840, 900, 930):
        q = reprice(D, tr, atr, flat_min=fm)
        for bl, m in B.items():
            s = A.metrics(q, D, m)
            if s["n"] == 0:
                continue
            rows.append(dict(market=mkt, flat=fm, block=bl, n=s["n"], usd=s["usd"],
                             usd_trade=s["usd"] / s["n"], pf=s["pf"], sharpe=s["sharpe"],
                             dd_usd=s["dd"] * D["pv"], ret_dd=s["ret_dd"]))
F = pd.DataFrame(rows)
F.to_csv(R + "p2_flat.csv", index=False)
lab = {0: "off (cash close)", 660: "11:00", 720: "12:00", 780: "13:00", 840: "14:00",
       900: "15:00", 930: "15:30"}
F["flat_lab"] = F.flat.map(lab)
print("  $/trade by flatten time:")
print(F.pivot_table(index="flat", columns=["market", "block"], values="usd_trade").round(2).to_string())
print("\n  MARGINAL over all blocks and markets:")
mg = F.groupby("flat").agg(usd_trade=("usd_trade", "mean"), pf=("pf", "mean"),
                           sharpe=("sharpe", "mean"), dd=("dd_usd", "mean"),
                           ret_dd=("ret_dd", "mean")).round(3)
mg.index = [lab[i] for i in mg.index]
print(mg.to_string())

print("\n" + "=" * 128)
print("P2.3  A STOP AND A FLATTEN TOGETHER, AND A TARGET FOR COMPLETENESS")
print("=" * 128)
rows = []
for mkt, (D, tr, B, atr) in data.items():
    for sm, fm, tg in ((0.0, 0, 0.0), (3.0, 0, 0.0), (0.0, 900, 0.0), (3.0, 900, 0.0),
                       (2.0, 0, 0.0), (3.0, 0, 3.0), (3.0, 0, 6.0)):
        q = reprice(D, tr, atr, stop_mult=sm, flat_min=fm, tgt_mult=tg)
        for bl, m in B.items():
            s = A.metrics(q, D, m)
            if s["n"] == 0:
                continue
            rows.append(dict(market=mkt, cfg=f"stop {sm or '-'} / flat {lab[fm]} / tgt {tg or '-'}",
                             block=bl, usd_trade=s["usd"] / s["n"], pf=s["pf"],
                             sharpe=s["sharpe"], dd=s["dd"] * D["pv"], ret_dd=s["ret_dd"]))
X = pd.DataFrame(rows)
X.to_csv(R + "p2_combo.csv", index=False)
print(X.pivot_table(index="cfg", columns=["market", "block"], values="usd_trade").round(2).to_string())
print("\n  averaged over all 8 market-blocks:")
print(X.groupby("cfg").agg(usd_trade=("usd_trade", "mean"), pf=("pf", "mean"),
                           sharpe=("sharpe", "mean"), dd=("dd", "mean"),
                           ret_dd=("ret_dd", "mean")).round(3).to_string())
print(f"\ntotal {time.time()-t0:.0f}s")
