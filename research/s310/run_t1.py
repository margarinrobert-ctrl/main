"""T1 -- the rule at TEN MINUTES: IS/OOS, and the bar-count-vs-minutes question first.

Before any stress test, two things have to be settled: does the rule survive the move from 5m to
10m at all, and which reading of its two BAR-COUNT parameters is the right one on the new chart.
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5"); sys.path.insert(0, "research/s310")
import numpy as np, pandas as pd
import s5data as S, s5sig as SG
import t10core as T

R = "results/s310/"; os.makedirs(R, exist_ok=True)
print(__doc__); t0 = time.time()
pd.set_option("display.width", 240); pd.set_option("display.max_columns", 40)

D10, F10, base = T.build(10)
D5, F5, _ = T.build(5)
print(f"NQ 10m: {D10['n']:,} bars, {D10['n_sessions']} window sessions, research to {D10['cut_date']}")
print(f"NQ  5m: {D5['n']:,} bars  (the reference the rule was chosen on)")

print("\n" + "=" * 122)
print("T1.0  COST AS A FRACTION OF RISK -- the number that decides whether a timeframe is tradeable")
print("=" * 122)
for lab, DD in (("5m", D5), ("10m", D10)):
    a = np.nanmedian(DD["atr"][DD["inw"]])
    risk = T.GEOM["stop"] * a
    print(f"  {lab:>4}: median ATR(14) in-window {a:6.2f} pts   3xATR stop {risk:7.2f} pts   "
          f"MNQ round turn {S.RT_POINTS:.2f} = {S.RT_POINTS/risk:6.2%} of risk   "
          f"1:1 break-even {(risk+S.RT_POINTS)/(2*risk):.3f}")
print("  A wider bar makes the fixed round turn a SMALLER fraction of risk, so if 10m fails it is")
print("  not cost -- that is the arm of the argument this table closes off in advance.")

print("\n" + "=" * 122)
print("T1.1  THE TWO READINGS OF k AND w, AND THEIR NEIGHBOURHOOD")
print("=" * 122)
print("  k and w are BAR COUNTS. On 10m the same numbers mean twice the minutes (STUDY_V57).")
rows = []
grid = [(k, w) for k in (1, 2, 3, 4, 5) for w in (5, 10, 15, 20, 30, 40)]
for k, w in grid:
    lg, sh = SG.s3_flow_exhaustion(D10, F10, dict(k=k, w=w))
    t = T.run(D10, lg, sh)
    for b in (0, 1):
        s = T.stats(t, D10, b)
        tag = ("CARRY" if (k, w) == (3, 20) else ("MATCHED" if (k, w) == (2, 10) else ""))
        rows.append(dict(k=k, w=w, tag=tag, block="research" if b == 0 else "LOCKED",
                         k_min=k * 10, w_min=w * 10, **s))
G = pd.DataFrame(rows)
G.to_csv(R + "t1_kw_grid.csv", index=False)
sc = G[G.n >= 30]
piv = sc.pivot_table(index=["k", "w"], columns="block",
                     values=["n", "pts", "pf", "sharpe"]).round(3)
print(piv.to_string())

print("\n  the two declared readings:")
for tag in ("CARRY", "MATCHED"):
    q = G[G.tag == tag]
    for _, r in q.iterrows():
        print(f"    {tag:8s} k{int(r.k)}/w{int(r.w)} = {int(r.k_min)}/{int(r.w_min)} min  "
              f"{r.block:8s}: n {int(r.n):4d}  {r.pts:+8.3f} pts  PF {r.pf:.3f}  "
              f"Sharpe {r.sharpe:+.3f}  ret/DD {r.ret_dd:+.2f}")

res = sc[sc.block == "research"]
lok = sc[sc.block == "LOCKED"]
j = res.merge(lok, on=["k", "w"], suffixes=("_r", "_l"))
print(f"\n  scorable cells (n>=30 on both blocks): {len(j)}")
print(f"  profitable on research: {(j.pts_r>0).mean():.1%}   on LOCKED: {(j.pts_l>0).mean():.1%}")
print(f"  corr(research pts, locked pts) over the grid: "
      f"{np.corrcoef(j.pts_r, j.pts_l)[0,1]:+.3f} Pearson, "
      f"{pd.Series(j.pts_r).corr(pd.Series(j.pts_l), method='spearman'):+.3f} Spearman")
print("  A NEGATIVE correlation here means selecting on research is worse than not selecting.")

print("\n" + "=" * 122)
print("T1.2  THE SAME RULE ON 5 MINUTES, FOR REFERENCE -- what is being given up")
print("=" * 122)
rows = []
for tf, DD, FF in ((5, D5, F5), (10, D10, F10)):
    for lab, p in (("carry k3/w20", T.CARRY), ("matched-min", T.MATCHED)):
        lg, sh = SG.s3_flow_exhaustion(DD, FF, p)
        t = T.run(DD, lg, sh)
        for b, bl in ((0, "research"), (1, "LOCKED")):
            rows.append(dict(tf=tf, reading=lab, k=p["k"], w=p["w"], block=bl, **T.stats(t, DD, b)))
C = pd.DataFrame(rows)
C.to_csv(R + "t1_tf_compare.csv", index=False)
print(C[["tf", "reading", "k", "w", "block", "n", "per_yr", "pts", "pf", "win", "sharpe",
         "ret_dd", "hold"]].round(3).to_string(index=False))

best = j.loc[j.pts_r.idxmax()]
print(f"\n  BEST RESEARCH CELL AT 10m: k{int(best.k)}/w{int(best.w)}  "
      f"research {best.pts_r:+.3f} pts PF {best.pf_r:.3f}  ->  "
      f"LOCKED {best.pts_l:+.3f} pts PF {best.pf_l:.3f}")
np.save(R + "kw_pairs.npy", j[["k", "w"]].to_numpy())
print(f"\ntotal {time.time()-t0:.0f}s")
