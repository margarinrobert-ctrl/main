"""O3 -- four Monte Carlos, the walk-forward with a random-cell arm, and the deflation.

THE FOUR MONTE CARLOS ANSWER FOUR DIFFERENT QUESTIONS and this branch has confused them before:
  * DAY-BLOCK BOOTSTRAP resamples whole days WITH THEIR TRADES ATTACHED -> the EDGE. Trades inside
    one session are not independent (`STUDY_EDGELAB`).
  * PERMUTATION reorders the realised sequence -> the PATH only. `STUDY_VALIDATE`: permuting cannot
    change the endpoint, so an endpoint distribution from it is meaningless. Its output is the
    drawdown percentile and the p99, which is the SIZING number.
  * EXECUTION PERTURBATION randomises cost and slippage INSIDE the walk -> prices execution noise.
    Run it first so the demanding tests are not mistaken for it.
  * PRICE JITTER perturbs every bar and RECOMPUTES the channels and the ATR from the jittered bars
    -> the only one that moves the SIGNAL. `STUDY_V64_MONTECARLO`: repairing the bar (high = max of
    the four, low = min) matters or the jitter creates impossible bars.

WALK-FORWARD carries a RANDOM-CELL arm, because `STUDY_V64_WFO` found the useful distinction is not
"re-select vs fixed" but "selecting from this family at all vs picking from it arbitrarily", and
WFE is normalised per quarter or it is a span ratio.

DEFLATION uses `var_trials` over the TRIAL SHARPES, per observation. Feeding it the variance of
uplifts printed 0.9919 once on this branch and an annualised Sharpe printed 0.571 another time.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "research/v68"); sys.path.insert(0, "research/v61sess")
sys.path.append("/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/mechanism-first-alpha/scripts")
from gates import deflated_sharpe, effective_trials, reality_check   # noqa: E402
import v68core as V
import sess_core as SC

t0 = time.time(); pd.set_option("display.width", 210)
def say(*a): print(*a, flush=True)
say(__doc__)
D = V.load(15)
rng = np.random.default_rng(68)

# ---------------------------------------------------------------- 1. execution perturbation
say(f"[{time.time()-t0:6.1f}s] MC1 EXECUTION -- cost U(0.5x,2x) and slippage U(0,2x) inside the walk")
c0, s0 = SC.COST, SC.SLIP
say(f"  (cost and slippage are PASSED, not assigned to the module -- a default argument binds at "
    f"definition time, and the first version of this returned p5=p50=p95 to the cent)")
for blk, nm in ((0, "research"), (1, "LOCKED")):
    tot = []
    for _ in range(300):
        t = V.run(D, block=blk, cost=c0 * rng.uniform(0.5, 2.0),
                  slip=s0 * rng.uniform(0.0, 2.0))
        tot.append(t.pct.sum())
    tot = np.array(tot)
    say(f"  {nm:>8}: total p5 {np.quantile(tot,0.05):+.2f}  p50 {np.median(tot):+.2f}  "
        f"p95 {np.quantile(tot,0.95):+.2f}   P(total<=0) {np.mean(tot<=0):.3f}")

# ---------------------------------------------------------------- 2. day-block bootstrap
say(f"\n[{time.time()-t0:6.1f}s] MC2 DAY-BLOCK BOOTSTRAP -- the EDGE (whole days, trades attached)")
BOOT = {}
for blk, nm in ((0, "research"), (1, "LOCKED")):
    t = V.run(D, block=blk)
    days = t.day.to_numpy(); ud = np.unique(days)
    m = np.empty(2000)
    for j in range(2000):
        pick = rng.choice(ud, len(ud), replace=True)
        idx = np.concatenate([np.flatnonzero(days == d) for d in pick])
        m[j] = t.pct.to_numpy()[idx].mean()
    BOOT[blk] = m
    say(f"  {nm:>8}: mean {t.pct.mean():+.5f}  95% CI [{np.quantile(m,0.025):+.5f}, "
        f"{np.quantile(m,0.975):+.5f}]   P(mean<=0) {np.mean(m<=0):.4f}")

# ---------------------------------------------------------------- 3. permutation -> the path
say(f"\n[{time.time()-t0:6.1f}s] MC3 PERMUTATION -- the PATH only; the p99 drawdown is the sizing "
    f"number")
for blk, nm in ((0, "research"), (1, "LOCKED")):
    t = V.run(D, block=blk); x = t.pct.to_numpy()
    eq = np.cumsum(x); real_dd = float(np.max(np.maximum.accumulate(eq) - eq))
    dds = np.empty(2000)
    for j in range(2000):
        p = rng.permutation(x); e = np.cumsum(p)
        dds[j] = np.max(np.maximum.accumulate(e) - e)
    pct = float(np.mean(dds <= real_dd))
    say(f"  {nm:>8}: realised DD {real_dd:.2f} = percentile {pct:.3f} of its own reshuffles   "
        f"p99 {np.quantile(dds,0.99):.2f}  ({np.quantile(dds,0.99)/max(real_dd,1e-9):.2f}x realised)")

# ---------------------------------------------------------------- 4. price jitter, signal recomputed
say(f"\n[{time.time()-t0:6.1f}s] MC4 PRICE JITTER -- OHLC perturbed, bars repaired, CHANNELS AND "
    f"ATR RECOMPUTED")
tick = 0.25
for noise in (0.5, 1.0, 2.0):
    keep = []
    for _ in range(60):
        E = dict(D)
        j = lambda a: a + rng.normal(0, noise * tick, len(a))
        o_, h_, l_, c_ = j(D["o"]), j(D["h"]), j(D["l"]), j(D["c"])
        hi = np.maximum.reduce([o_, h_, l_, c_]); lo = np.minimum.reduce([o_, h_, l_, c_])
        E["o"], E["c"], E["h"], E["l"] = o_, c_, hi, lo
        E["atr"] = SC._atr(hi, lo, c_)
        sh, sl = pd.Series(hi), pd.Series(lo)
        E["ent_hi"] = np.vstack([sh.rolling(k).max().shift(1).to_numpy()
                                 for k in range(2, D["ent_hi"].shape[0] + 2)])
        E["ex_lo"] = np.vstack([sl.rolling(k).min().shift(1).to_numpy()
                                for k in range(2, D["ex_lo"].shape[0] + 2)])
        t = V.run(E)
        keep.append((t[t.blk == 0].pct.sum(), t[t.blk == 1].pct.sum(), len(t)))
    K = np.array(keep)
    say(f"  {noise:.1f} tick: research total p5 {np.quantile(K[:,0],0.05):+.2f} "
        f"med {np.median(K[:,0]):+.2f} | locked p5 {np.quantile(K[:,1],0.05):+.2f} "
        f"med {np.median(K[:,1]):+.2f} | sign kept "
        f"{np.mean((K[:,0]>0)&(K[:,1]>0)):.3f} | trades {K[:,2].mean():.0f}")

# ---------------------------------------------------------------- 5. walk-forward
say(f"\n[{time.time()-t0:6.1f}s] WALK-FORWARD -- in-fold re-selection vs the fixed cell vs a RANDOM "
    f"cell")
GRID = [dict(ent=e, exN=x, stop=s, tp=p)
        for e in (8, 11, 15, 25) for x in (25, 47, 65) for s in (2.5, 3.8, 5.0)
        for p in (2.0, 3.2, 5.0, 0.0)]
say(f"  grid {len(GRID)} cells; folds are calendar quarters")
allt = V.run(D)
q = pd.PeriodIndex(pd.to_datetime(allt.ts), freq="Q")
allt = allt.assign(q=q.astype(str))
qs = sorted(allt.q.unique())
say(f"  {len(qs)} quarters: {qs[0]} .. {qs[-1]}")
res = {"fixed": [], "rechosen": [], "random": []}
folds = []
for i in range(4, len(qs)):
    tr, te = qs[max(0, i - 4):i], qs[i]
    best, bv = None, -1e9
    for g in GRID:
        t = V.run(D, **g)
        tq = pd.PeriodIndex(pd.to_datetime(t.ts), freq="Q").astype(str)
        s = t[np.isin(tq, tr)]
        if len(s) < 40:
            continue
        v = s.pct.sum()
        if v > bv:
            best, bv = g, v
    tb = V.run(D, **best)
    tqb = pd.PeriodIndex(pd.to_datetime(tb.ts), freq="Q").astype(str)
    rc = tb[tqb == te].pct.sum()
    fx = allt[allt.q == te].pct.sum()
    rg = GRID[rng.integers(len(GRID))]
    tr_ = V.run(D, **rg)
    tqr = pd.PeriodIndex(pd.to_datetime(tr_.ts), freq="Q").astype(str)
    rn = tr_[tqr == te].pct.sum()
    res["fixed"].append(fx); res["rechosen"].append(rc); res["random"].append(rn)
    folds.append(te)
    say(f"    {te}: fixed {fx:+.2f}  re-chosen {rc:+.2f}  random {rn:+.2f}   "
        f"(chose ent{best['ent']} ex{best['exN']} stop{best['stop']} tp{best['tp']})")
for k in res:
    a = np.array(res[k])
    say(f"  {k:>9}: total {a.sum():+.2f}   folds positive {int((a>0).sum())}/{len(a)}   "
        f"mean {a.mean():+.3f}")

# ---------------------------------------------------------------- 6. deflation
say(f"\n[{time.time()-t0:6.1f}s] DEFLATION -- var_trials over the TRIAL SHARPES, per observation")
L = pd.read_csv("results/v68/o1_trials.csv")
S = L[L.ok == 1]
sh = S.r_sh.to_numpy()
sh = sh[np.isfinite(sh)]
t = V.run(D, block=0); x = t.pct.to_numpy()
per = x.mean() / x.std(ddof=1)
trials = len(S) + 6 + 15 + 3
N = effective_trials(trials, 0.7)
ds = deflated_sharpe(per, len(x), trials, float(np.var(sh, ddof=1)),
                     float(pd.Series(x).skew()), float(pd.Series(x).kurt()) + 3.0,
                     avg_correlation=0.7)
say(f"  counted looks {trials}   effective N {N:.1f}   var over {len(sh)} trial Sharpes "
    f"{np.var(sh, ddof=1):.6f}")
for k, v in ds.items():
    say(f"    {k}: {v}")
cand = []
for g in GRID[:60]:
    tt = V.run(D, **g); s = tt[tt.blk == 0]
    if len(s) > 50:
        cand.append(np.pad(s.pct.to_numpy(), (0, 0)))
mx = min(len(c) for c in cand)
M = np.column_stack([c[:mx] for c in cand])
rc_p = reality_check(M)
say(f"  White reality check over {M.shape[1]} candidates x {mx} obs: {rc_p}")
say(f"\n[{time.time()-t0:6.1f}s] done")
