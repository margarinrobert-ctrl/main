"""T3 -- the four Monte Carlos, on both declared 10-minute readings.

A bootstrap prices the EDGE, a permutation prices the PATH, an execution perturbation prices the
fills and a price jitter with the signal RECOMPUTED prices the rule's own fragility. They answer
different questions and reporting one as the other is how a drawdown study gets sold as an edge
study (STUDY_V31).
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5"); sys.path.insert(0, "research/s310")
import numpy as np, pandas as pd
import s5sig as SG, s5data as S
import t10core as T

R = "results/s310/"
print(__doc__); t0 = time.time()
pd.set_option("display.width", 240)
D, F, base = T.build(10)
D5, F5, _ = T.build(5)

CELLS = [("10m CARRY k3/w20", D, F, T.CARRY),
         ("10m MATCHED k2/w10", D, F, T.MATCHED),
         ("5m reference k3/w20", D5, F5, T.CARRY)]

print("=" * 122)
print("T3.1  BOOTSTRAP (the edge) AND PERMUTATION (the path)")
print("=" * 122)
rows = []
store = {}
for lab, DD, FF, p in CELLS:
    lg, sh = SG.s3_flow_exhaustion(DD, FF, p)
    t = T.run(DD, lg, sh)
    store[lab] = (DD, FF, p, lg, sh, t)
    for b, bl in ((0, "research"), (1, "LOCKED")):
        s = t[t.blk == b]
        if len(s) < 20:
            continue
        bo, pz, ci = T.mc_bootstrap(t, DD, b, 2000)
        rdd, perm, pct = T.mc_permute(t, DD, b, 2000)
        st = T.stats(t, DD, b)
        rows.append(dict(cell=lab, block=bl, n=st["n"], pts=st["pts"], pf=st["pf"],
                         sharpe=st["sharpe"], boot_lo=ci[0], boot_hi=ci[1], P_mean_le0=pz,
                         real_dd=rdd, mc_dd_p50=np.percentile(perm, 50),
                         mc_dd_p99=np.percentile(perm, 99), dd_pctile=pct))
MC = pd.DataFrame(rows)
MC.to_csv(R + "t3_montecarlo.csv", index=False)
print(MC.round(3).to_string(index=False))
print("\n  P(mean <= 0) is the EDGE question. dd_pctile is where the REALISED drawdown sits in a")
print("  reshuffle of the strategy's own trades: low = the path was lucky, high = unlucky.")
print("  MC p99 drawdown is the sizing number, not the realised one.")

print("\n" + "=" * 122)
print("T3.2  EXECUTION PERTURBATION -- slippage U(0,2x) and cost U(0.5x,2x) INSIDE the walk")
print("=" * 122)
rows = []
for lab, DD, FF, p in CELLS:
    _, _, _, lg, sh, t = store[lab]
    for b, bl in ((0, "research"), (1, "LOCKED")):
        if len(t[t.blk == b]) < 20:
            continue
        o = T.mc_execution(DD, lg, sh, b, 250)
        rows.append(dict(cell=lab, block=bl, base_total=t[t.blk == b].pts.sum(),
                         p5=np.nanpercentile(o, 5), p50=np.nanpercentile(o, 50),
                         p95=np.nanpercentile(o, 95), P_total_le0=float(np.nanmean(o <= 0))))
EX = pd.DataFrame(rows)
EX.to_csv(R + "t3_execution.csv", index=False)
print(EX.round(2).to_string(index=False))
print("  Run this FIRST so the demanding tests below are not mistaken for it: at a 3xATR stop the")
print("  round turn is under 3% of risk, so execution noise should be nearly free here.")

print("\n" + "=" * 122)
print("T3.3  PRICE JITTER WITH THE PIVOTS, THE CVD AND THE ATR ALL RECOMPUTED")
print("=" * 122)
print("  This is the only perturbation that moves the SIGNAL. Anything that survives execution")
print("  noise and dies here is fragile in the rule, not in the fills.")
rows = []
for lab, DD, FF, p in CELLS:
    for ticks in (0.5, 1.0, 2.0):
        for b, bl in ((0, "research"), (1, "LOCKED")):
            o = T.mc_jitter_fast(DD, base, b, p, ticks=ticks, n=400)
            base_t = store[lab][5]
            bt = base_t[base_t.blk == b].pts.sum()
            rows.append(dict(cell=lab, block=bl, ticks=ticks, base_total=bt,
                             p5=np.nanpercentile(o, 5), p50=np.nanpercentile(o, 50),
                             p95=np.nanpercentile(o, 95),
                             sign_kept=float(np.nanmean(np.sign(o) == np.sign(bt)))))
        print(f"  ...{lab} at {ticks} ticks done {time.time()-t0:.0f}s")
JT = pd.DataFrame(rows)
JT.to_csv(R + "t3_jitter.csv", index=False)
print(JT.round(2).to_string(index=False))
print(f"\ntotal {time.time()-t0:.0f}s")
