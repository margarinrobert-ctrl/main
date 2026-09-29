"""O3 -- Monte Carlo and the forward-test design for FTM alpha.2.

Four Monte Carlos, each answering a different question, and then the only thing that matters for
a decision: what a forward test of a given length can and cannot establish.
  bootstrap   -> the EDGE
  permutation -> the PATH (reordering realised trades cannot change the endpoint)
  execution   -> the FILLS (slippage and cost varied INSIDE the walk, so exits move)
  session     -> the SAMPLE (drop whole sessions, because trades cluster by day)
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/ftm")
import numpy as np, pandas as pd
from scipy import stats as sps
import ftm_sim as FS

R = "results/ftm2/"
OOS = pd.Timestamp("2025-01-01")
print(__doc__); t0 = time.time()
pd.set_option("display.width", 230)
rng = np.random.default_rng(41)

t = pd.read_parquet(R + "o1_a2.parquet")
t["time"] = pd.to_datetime(t.time)
t["day"] = t.time.dt.normalize()
blocks = {"ALL": t, "in-sample": t[t.time < OOS], "OUT-OF-SAMPLE": t[t.time >= OOS]}

print("=" * 120)
print("O3.1  BOOTSTRAP (the edge) AND PERMUTATION (the path), resampling whole SESSIONS")
print("=" * 120)
rows = []
for bl, s in blocks.items():
    grp = {d: g.usd.to_numpy() for d, g in s.groupby("day")}
    keys = list(grp)
    bo = np.empty(4000)
    for b in range(4000):
        pick = rng.choice(len(keys), len(keys))
        bo[b] = np.concatenate([grp[keys[j]] for j in pick]).mean()
    u = s.usd.to_numpy()
    eq = np.cumsum(u); rdd = float(-(eq - np.maximum.accumulate(eq)).min())
    perm = np.empty(4000)
    for b in range(4000):
        e = np.cumsum(rng.permutation(u))
        perm[b] = float(-(e - np.maximum.accumulate(e)).min())
    rows.append(dict(block=bl, n=len(s), usd_trade=u.mean(),
                     boot_lo=np.percentile(bo, 2.5), boot_hi=np.percentile(bo, 97.5),
                     P_mean_le0=(bo <= 0).mean(), real_dd=rdd,
                     mc_dd_p50=np.percentile(perm, 50), mc_dd_p99=np.percentile(perm, 99),
                     dd_pctile=(perm <= rdd).mean()))
M = pd.DataFrame(rows)
M.to_csv(R + "o3_mc.csv", index=False)
print(M.round(3).to_string(index=False))
print("  dd_pctile low = the realised path was LUCKY; high = unlucky. Size for the p99.")

print("\n" + "=" * 120)
print("O3.2  EXECUTION PERTURBATION -- slippage and cost varied INSIDE the walk")
print("=" * 120)
base_slip, base_plat, base_cost = FS.STOP_SLIP_TICKS, FS.PLATFORM_SLIP, FS.EST_RT_COST
rows = []
for mult in (0.0, 1.0, 2.0, 3.0, 4.0):
    FS.STOP_SLIP_TICKS = int(round(base_slip * mult))
    FS.PLATFORM_SLIP = int(round(base_plat * mult))
    FS.EST_RT_COST = base_cost * mult
    _, q = FS.run(verbose=False, prior_bars=1, h2_cap=1)
    q["time"] = pd.to_datetime(q.time)
    rows.append(dict(cost_mult=mult, n=len(q), net_all=q.usd.sum(),
                     net_is=q[q.time < OOS].usd.sum(), net_oos=q[q.time >= OOS].usd.sum(),
                     R_all=q.R.mean(), R_oos=q[q.time >= OOS].R.mean()))
    print(f"  ...{mult}x done {time.time()-t0:.0f}s")
FS.STOP_SLIP_TICKS, FS.PLATFORM_SLIP, FS.EST_RT_COST = base_slip, base_plat, base_cost
E = pd.DataFrame(rows)
E.to_csv(R + "o3_cost.csv", index=False)
print(E.round(3).to_string(index=False))

print("\n" + "=" * 120)
print("O3.3  SESSION DROPOUT -- how much of the result survives losing random days")
print("=" * 120)
for bl, s in blocks.items():
    days = s.day.unique()
    line = f"  {bl:>14}: "
    for keep in (0.9, 0.75, 0.5):
        tot = []
        for _ in range(600):
            sel = rng.choice(days, int(len(days) * keep), replace=False)
            tot.append(s[s.day.isin(sel)].usd.sum() / keep)
        line += f"  keep {keep:.0%}: P(>0) {np.mean(np.array(tot) > 0):.2f}"
    print(line)

print("\n" + "=" * 120)
print("O3.4  THE FORWARD TEST -- what a run of N trades can actually decide")
print("=" * 120)
oos = blocks["OUT-OF-SAMPLE"].usd.to_numpy()
ins = blocks["in-sample"].usd.to_numpy()
span = (t.time.max() - t.time.min()).days / 365.25
per_yr = len(t) / span
sd = oos.std(ddof=1)
print(f"  the rule fires {per_yr:.0f} times a year ({len(t)} trades over {span:.2f} years)")
for n in (40, 100, 159, 300):
    print(f"    {n:>4} trades = {n/per_yr*12:>4.1f} months   standard error ${sd/np.sqrt(n):>6.0f}"
          f"   95% CI half-width +/-${1.96*sd/np.sqrt(n):>6.0f}")
print(f"\n  per-trade standard deviation (OOS): ${sd:,.0f}")
print(f"  the hypotheses: in-sample ${ins.mean():.2f}, out-of-sample ${oos.mean():.2f}, "
      f"a random quarter-hour entry earns about +0.056 R")
need = int(np.ceil((1.96 * sd / oos.mean()) ** 2))
print(f"  trades needed to show the OOS mean (${oos.mean():.2f}) differs from zero at 95%: {need:,}"
      f"  = {need/per_yr:.1f} years")

print("\n  Simulated, resampling whole SESSIONS with their trades attached:")
for lab, s in (("H_is  ", blocks["in-sample"]), ("H_oos ", blocks["OUT-OF-SAMPLE"])):
    grp = {d: g.usd.to_numpy() for d, g in s.groupby("day")}
    keys = list(grp)
    for n in (40, 100, 159):
        tot = []
        for _ in range(4000):
            acc = []
            while len(acc) < n:
                acc.extend(grp[keys[rng.integers(len(keys))]])
            tot.append(np.sum(acc[:n]))
        tot = np.array(tot)
        print(f"    {lab} n={n:>3}: median ${np.median(tot):>7,.0f}   "
              f"p05 ${np.percentile(tot,5):>7,.0f}   p95 ${np.percentile(tot,95):>7,.0f}   "
              f"P(profit) {np.mean(tot>0):.0%}")

print("\n" + "=" * 120)
print("O3.5  THE STATISTIC THAT MOVES FASTEST HERE")
print("=" * 120)
w = (oos > 0).mean()
aw = oos[oos > 0].mean(); al = -oos[oos <= 0].mean()
be = al / (aw + al)
print(f"  OOS: win rate {w:.1%}, avg win ${aw:,.0f}, avg loss ${-al:,.0f}")
print(f"  This is NOT a win-rate strategy -- the payoff ratio is {aw/al:.2f}:1, so the break-even")
print(f"  win rate is {be:.1%} and it wins {w:.1%}. The edge is the PAYOFF, which converges slowly.")
print(f"  So unlike a 1:1 system, a win-rate count will NOT decide this quickly. The number to")
print(f"  watch instead is the EXIT MIX: target share and 15:30-exit share.")
mix = blocks["OUT-OF-SAMPLE"].groupby("reason").size() / len(oos)
print("  OOS exit mix to reproduce: " + ", ".join(f"{k} {v:.0%}" for k, v in mix.items()))
print(f"\ntotal {time.time()-t0:.0f}s")
