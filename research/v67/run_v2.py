"""V2 -- the HMM done causally, the max-of-N correction, and the LOCKED read.

Three jobs.

1. THE NULL PART A ACTUALLY NEEDS. Part A reported the BEST of 71 features per cell, so each |IC|
   is the maximum of 71 draws. The single shuffled twin it printed does not price that. Here the
   whole 71-feature sweep is re-run on a PERMUTED target, 40 times, and the distribution of
   max|IC| under the null is what each cell is compared against.

2. THE HMM, WITH ITS OWN LEAK DIAGNOSTIC. `STUDY_V27` measured a fit-on-all + smoothed decode at
   locked PF 1.351 against the causal version of the same model and rule at 0.973, with NEARLY
   IDENTICAL TRADE COUNTS -- the leak is invisible in the count and shows only in which bars got
   labelled. So: parameters from the RESEARCH block only, FILTERED posterior only, and the
   smoothed version computed for exactly one purpose, to report how easy the mistake is to miss.
   V27 also found the Markov apparatus collapses to the state label (Jaccard 1.0000 between
   `state==Bull` and `signal>0.3`), so that is re-tested here rather than assumed.

   And one thing V27 did not try: EXPECTED REMAINING SOJOURN TIME, 1/(1-A_ii) weighted by the
   filtered posterior. A duration feature for a duration target.

3. ONE LOCKED READ, on the targets that survive, with the multiplicity stated.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "research/v67"); sys.path.insert(0, "research/v22"); sys.path.insert(0, "research/v27")
import v67core as V
import v22vol as VV
import v27hmm as H

t0 = time.time(); pd.set_option("display.width", 220)
def say(*a): print(*a, flush=True)
say(__doc__)

D = V.load(15)
mR = D["blk"] == 0
X = pd.DataFrame(VV.build(D["o"], D["h"], D["l"], D["c"]))
FEATS = list(X.columns)
say(f"[{time.time()-t0:6.1f}s] {D['n']:,} bars, {len(FEATS)} volatility features")

# ---------------------------------------------------------------- 1. max-of-N null
say(f"\n[{time.time()-t0:6.1f}s] MAX-OF-71 NULL -- the whole sweep re-run on permuted targets")
rng = np.random.default_rng(5)
NPERM = 40
say(f"{'h':>4} {'target':>7} {'real max|IC|':>12} {'null p50':>9} {'null p95':>9} {'null max':>9} "
    f"{'verdict':>9}")
rows = []
Xa = X.to_numpy(float)
for h in V.HORIZONS:
    T = V.build_targets(D, h)
    for tg in V.TARGETS:
        y = T[tg]
        m = mR & np.isfinite(y)
        yy = y[m]
        Z = Xa[m]
        real = 0.0
        for k in range(Z.shape[1]):
            v = V.ic(Z[:, k], yy)
            if np.isfinite(v) and abs(v) > real:
                real = abs(v)
        nulls = np.empty(NPERM)
        for j in range(NPERM):
            ys = yy.copy(); rng.shuffle(ys)
            best = 0.0
            for k in range(Z.shape[1]):
                v = V.ic(Z[:, k], ys)
                if np.isfinite(v) and abs(v) > best:
                    best = abs(v)
            nulls[j] = best
        verdict = "CLEARS" if real > nulls.max() else "no"
        rows.append(dict(h=h, target=tg, real=real, p50=np.median(nulls),
                         p95=np.quantile(nulls, 0.95), mx=nulls.max(), clears=verdict))
        say(f"{h:>4} {tg:>7} {real:>12.4f} {np.median(nulls):>9.4f} "
            f"{np.quantile(nulls,0.95):>9.4f} {nulls.max():>9.4f} {verdict:>9}")
    say(f"      ... h={h} null done  [{time.time()-t0:6.1f}s]")
N = pd.DataFrame(rows)
N.to_csv("results/v67/v2_maxnull.csv", index=False)
say(f"\n  cells whose real max|IC| exceeds the LARGEST of {NPERM} null sweeps: "
    f"{int((N.clears=='CLEARS').sum())} of {len(N)}")

# ---------------------------------------------------------------- 2. the HMM
say(f"\n[{time.time()-t0:6.1f}s] HMM -- fitted on RESEARCH only, read FILTERED")
lc = np.log(np.maximum(D["c"], 1e-12))
r = np.diff(lc, prepend=lc[0])
rv = pd.Series(r).rolling(96).std(ddof=1).to_numpy()
obs = np.column_stack([r * 100.0, np.nan_to_num(rv * 100.0, nan=0.0)])
fitmask = mR & np.isfinite(obs).all(axis=1)
say(f"           fitting on {int(fitmask.sum()):,} research bars ...")
pi, A, mu, var = H.fit(obs[fitmask], K=3, iters=40, seed=0)
order = np.argsort(mu[:, 0])
say(f"           states by drift: " + "  ".join(
    f"{nm} mu={mu[k,0]:+.5f} rv={mu[k,1]:.4f} self={A[k,k]:.4f}"
    for k, nm in zip(order, ("bear", "side", "bull"))))
obs_all = np.nan_to_num(obs, nan=0.0)
filt = H.posterior_filtered(obs_all, pi, A, mu, var)
smoo = H.posterior_smoothed(obs_all, pi, A, mu, var)
agree = float(np.mean(np.argmax(filt, 1) == np.argmax(smoo, 1)))
say(f"           filtered vs SMOOTHED state agreement {100*agree:.1f}%  -- close enough to be easy "
    f"to miss, which is why STUDY_V27 measured what it costs")

# the V27 collapse test, re-run rather than assumed
sig = filt[:, order[2]] - filt[:, order[0]]
st_bull = np.argmax(filt, 1) == order[2]
sg_bull = sig > 0.3
inter = float((st_bull & sg_bull).sum()); union = float((st_bull | sg_bull).sum())
say(f"           COLLAPSE TEST: Jaccard(state==Bull, signal>0.3) = {inter/max(union,1):.4f}   "
    f"distinct values of the 1-step signal: {len(np.unique(np.round(sig,6)))}")

# the new one: expected remaining sojourn, 1/(1-A_ii), posterior-weighted
soj = np.array([1.0 / max(1.0 - A[k, k], 1e-9) for k in range(3)])
exp_soj = filt @ soj
say(f"           expected remaining sojourn: per-state {np.round(soj,1)}   "
    f"series mean {np.nanmean(exp_soj):.1f} bars, sd {np.nanstd(exp_soj):.1f}")

HF = pd.DataFrame({"hmm.p_bear": filt[:, order[0]], "hmm.p_side": filt[:, order[1]],
                   "hmm.p_bull": filt[:, order[2]], "hmm.sig": sig, "hmm.sojourn": exp_soj,
                   "hmm.entropy": -(filt * np.log(np.maximum(filt, 1e-12))).sum(axis=1)})
say(f"\n[{time.time()-t0:6.1f}s] does the HMM add anything the volatility features do not?")
say(f"{'h':>4} {'target':>7} {'best vol':>9} | " + " ".join(f"{c.split('.')[1]:>9}" for c in HF.columns))
add = []
for h in V.HORIZONS:
    T = V.build_targets(D, h)
    for tg in V.TARGETS:
        y = T[tg]; m = mR & np.isfinite(y)
        bv = N[(N.h == h) & (N.target == tg)].real.iloc[0]
        vals = [V.ic(HF[c].to_numpy(float)[m], y[m]) for c in HF.columns]
        add.append(dict(h=h, target=tg, vol=bv,
                        **{c: v for c, v in zip(HF.columns, vals)}))
        say(f"{h:>4} {tg:>7} {bv:>9.4f} | " + " ".join(f"{v:>9.4f}" for v in vals))
AD = pd.DataFrame(add)
AD.to_csv("results/v67/v2_hmm.csv", index=False)
best_h = AD[list(HF.columns)].abs().max(axis=1)
say(f"\n  cells where an HMM column beats the best of 71 volatility features: "
    f"{int((best_h > AD.vol).sum())} of {len(AD)}")
say(f"  largest HMM |IC| anywhere: {AD[list(HF.columns)].abs().max().max():.4f}   "
    f"largest volatility |IC|: {AD.vol.max():.4f}")
say(f"\n[{time.time()-t0:6.1f}s] done")
