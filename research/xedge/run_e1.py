"""E1 -- WHERE THE GOLD RULE'S MONEY ACTUALLY GOES, before any feature is engineered.

The script's own header says two things that decide what feature engineering is worth doing:
  * it is POSITIVE GROSS (+0.0762 R long) and negative net, so the round turn is the whole
    difference and an entry filter has to pay for itself twice;
  * 61.1% of exits are the CLOSE-ONLY TRAIL at a mean of -0.190 R, so the dominant exit is a
    LOSER and the trail -- not the entry -- is where the largest single number lives.
So this file decomposes the exits first and sweeps the exit geometry with the ENTRY FROZEN. If the
exit explains the result, an entry model is the wrong place to spend the search budget.
"""
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vwapema"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "xanom"))
import vecore as V
import xdata as XD

RNG = np.random.default_rng(3)
pd.set_option("display.width", 230)
os.makedirs("results/xedge", exist_ok=True)
L = lambda s: print("\n" + "=" * 114 + f"\n{s}\n" + "=" * 114)
print(__doc__)

D = V.build()                      # XAU_ISO_15m, the exact feed the header quotes
WHY = {0: "initial stop", 1: "3R target", 2: "EMA trail", 3: "time/end"}
BLK = (("research", 0), ("locked", 1))


def run(**kw):
    sig, _ = V.triggers(D, side=kw.pop("side", 1), p=kw.pop("p", None))
    return V.run(D, sig, **kw)


L("E1.1  THE EXIT MIX -- what each exit contributes, and what it costs")
rows = []
for side, sn in ((1, "LONG"), (-1, "SHORT")):
    t = run(side=side)
    for bn, b in BLK:
        tb = t[t.blk == b]
        if len(tb) < 30:
            continue
        for w, nm in WHY.items():
            s = tb[tb.why == w]
            if len(s) == 0:
                continue
            rows.append(dict(side=sn, block=bn, exit=nm, n=len(s),
                             share=round(100 * len(s) / len(tb), 1),
                             mean_R=round(float(s.R.mean()), 4),
                             total_R=round(float(s.R.sum()), 1),
                             share_of_net=round(100 * float(s.R.sum() / max(abs(tb.R.sum()), 1e-9)), 1)))
E = pd.DataFrame(rows)
print(E.to_string(index=False))
E.to_csv("results/xedge/e1_exitmix.csv", index=False)
print("\n  `share_of_net` is signed against the ABSOLUTE net, so it says which exit is paying and")
print("  which is bleeding. An exit taking 60% of the trades at a negative mean is the first thing")
print("  to attack, and it needs no features at all.")

L("E1.2  THE EXIT GEOMETRY SWEPT WITH THE ENTRY FROZEN -- 6 stops x 5 targets x trail on/off")
rows = []
for trail in (True, False):
    for stop in (0.25, 0.5, 1.0, 1.5, 2.5, 4.0):
        for tg in (1.0, 2.0, 3.0, 5.0, 0.0):
            p = dict(V.PARAMS); p["atr_stop"] = stop
            t = run(side=1, tgt_R=tg, atr_stop=stop, p=p, trail=trail)
            for bn, b in BLK:
                tb = t[t.blk == b]
                if len(tb) < 40:
                    continue
                st = V.stats(tb)
                rows.append(dict(trail="on" if trail else "OFF", stop=stop, target=tg, block=bn,
                                 n=st["n"], R=round(st["R"], 4), pf=round(st["pf"], 3),
                                 win=round(st["win"], 1), totR=round(st["totR"], 1),
                                 ret_dd=round(st["ret_dd"], 2)))
G = pd.DataFrame(rows)
G.to_csv("results/xedge/e1_grid.csv", index=False)
print("  MARGINAL AVERAGE PER AXIS -- never the top row (CLAUDE.md)")
for ax in ("trail", "stop", "target"):
    piv = G.pivot_table(index=ax, columns="block", values=["R", "pf", "n"], aggfunc="mean").round(4)
    print(f"\n  --- {ax}")
    print(piv.to_string())

L("E1.3  THE PUBLISHED CELL AGAINST THE BEST MARGINAL CELL")
pub = G[(G.trail == "on") & (G.stop == 0.5) & (G.target == 3.0)]
print("  as published:")
print(pub.to_string(index=False))
marg = (G.groupby(["trail", "stop", "target"])
          .apply(lambda s: s[s.block == "research"].R.mean(), include_groups=False)
          .sort_values(ascending=False))
print("\n  top 8 cells BY RESEARCH R (read as the max of 60 draws, not as a choice):")
top = marg.head(8).reset_index().rename(columns={0: "research_R"})
for _, r in top.iterrows():
    lk = G[(G.trail == r.trail) & (G.stop == r.stop) & (G.target == r.target) & (G.block == "locked")]
    print(f"    trail {r.trail:3s}  stop {r.stop:.2f}N  target {r.target:.1f}R   "
          f"research {r.research_R:+.4f}   locked {float(lk.R.iloc[0]) if len(lk) else float('nan'):+.4f}"
          f"   n {int(lk.n.iloc[0]) if len(lk) else 0}")
print("\n  corr(research R, locked R) over the whole grid: "
      f"{G.pivot_table(index=['trail','stop','target'], columns='block', values='R').corr().iloc[0,1]:+.3f}")
