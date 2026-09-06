"""WALK-FORWARD AND THE FORMAL OVERFITTING TEST (CSCV / PBO), on the configuration as published.

Three different questions get called "overfitting" and they need three different tests:

  1. IS THE PUBLISHED RULE ITSELF OVERFIT TO GOLD?  It cannot be in the usual sense -- its ten
     numbers came from the paper's conventions, not from this data. What CAN be asked is whether
     it is REGIME-DEPENDENT: a rolling walk-forward with NO re-selection, so nothing is fitted and
     only the market changes.
  2. IS THE SEARCH OVERFIT?  A walk-forward that RE-RUNS the selection inside every training
     window, against the published constants and against a random cell from the same menu. If
     re-selecting each fold cannot beat never selecting, the search is buying nothing.
  3. WHAT IS THE PROBABILITY OF BACKTEST OVERFITTING?  Bailey, Borwein, Lopez de Prado & Zhu's
     COMBINATORIALLY SYMMETRIC CROSS-VALIDATION. Take a matrix of per-period returns for N
     configurations, split the periods into S blocks, and over every C(S, S/2) split take the
     IS-best configuration and find its OOS rank. PBO is the share of splits where that
     configuration lands BELOW the OOS median. PBO near 0.5 means selecting the in-sample winner
     is a coin flip out of sample -- the definition of an overfit search.

Everything is computed on a per-MONTH return matrix so the blocks are contiguous time.
"""
import os, sys, json, itertools, time
from math import comb
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from research.vwapema import vecore as V

RNG = np.random.default_rng(31415)
pd.set_option("display.width", 220)
print(__doc__)
DS = {s: V.build(sess=s) for s in ("ny", "utc")}
PUB = dict(sess="ny", p=dict(V.PARAMS), tgt_R=3.0)


def monthly(cfg):
    D = DS[cfg["sess"]]
    sig, _ = V.triggers(D, side=1, p=cfg["p"])
    t = V.run(D, sig, side=1, tgt_R=cfg["tgt_R"], atr_stop=cfg["p"]["atr_stop"], p=cfg["p"])
    if len(t) == 0:
        return None
    t["m"] = pd.DatetimeIndex(t.ts).to_period("M")
    g = t.groupby("m").R.agg(["mean", "sum", "size"])
    return g


# ---------------------------------------------------------------- 1. the published rule, rolling
print("=" * 112)
print("1. THE PUBLISHED RULE, ROLLING WALK-FORWARD -- nothing re-selected, only the market changes")
print("=" * 112)
mp = monthly(PUB)
allm = pd.period_range(mp.index.min(), mp.index.max(), freq="M")
mp = mp.reindex(allm).fillna(0.0)
rows = []
W = 36                                   # 3-year training window, 1-year test
for k in range(0, len(allm) - W - 12 + 1, 12):
    tr = mp.iloc[k:k + W]; te = mp.iloc[k + W:k + W + 12]
    if te["size"].sum() < 10:
        continue
    isr = float((tr["mean"] * tr["size"]).sum() / max(tr["size"].sum(), 1))
    osr = float((te["mean"] * te["size"]).sum() / max(te["size"].sum(), 1))
    rows.append(dict(train=f"{tr.index[0]}..{tr.index[-1]}", test=f"{te.index[0]}..{te.index[-1]}",
                     n_is=int(tr["size"].sum()), IS_R=isr, n_oos=int(te["size"].sum()), OOS_R=osr,
                     WFE=osr / isr if isr > 0 else np.nan))
Wf = pd.DataFrame(rows)
print(Wf.to_string(index=False, float_format=lambda v: f"{v:8.4f}"))
print(f"\n  folds {len(Wf)}: IS positive {int((Wf.IS_R>0).sum())}, OOS positive {int((Wf.OOS_R>0).sum())}")
print(f"  mean IS {Wf.IS_R.mean():+.4f}  mean OOS {Wf.OOS_R.mean():+.4f}  "
      f"generalization gap {Wf.IS_R.mean()-Wf.OOS_R.mean():+.4f}")
print(f"  corr(IS, OOS) across folds: Pearson {np.corrcoef(Wf.IS_R, Wf.OOS_R)[0,1]:+.3f}")
print("  A NEGATIVE gap means it does BETTER out of sample -- which is not skill, it is the regime.")

# ---------------------------------------------------------------- 2. build the return matrix
print("\n" + "=" * 112)
print("2. BUILDING THE PER-MONTH RETURN MATRIX for a sample of the 108,000-cell grid")
print("=" * 112)
G = pd.read_parquet("results/vwapema/sweep100k.parquet")
POOL = 1200
samp = G.sample(POOL, random_state=11).reset_index(drop=True)
t0 = time.time()
mat, names, kept = [], [], []
for i, r in samp.iterrows():
    cfg = dict(sess=r.sess, tgt_R=float(r.tgt),
               p={"ema_slow": int(r.ema_slow), "ema_pull": int(r.ema_pull), "ema_tight": 20,
                  "atr_len": 14, "atr_stop": float(r.stop), "vol_mult": float(r.vol),
                  "range_mult": float(r["range"]), "wick_body": float(r.wick),
                  "ambig": V.PARAMS["ambig"], "tighten_R": V.PARAMS["tighten_R"]})
    g = monthly(cfg)
    if g is None or g["size"].sum() < 120:
        continue
    s = g["sum"].reindex(allm).fillna(0.0)
    mat.append(s.to_numpy()); names.append(i); kept.append(cfg)
M = np.array(mat).T                       # (months, configs)
print(f"  {M.shape[1]} configurations x {M.shape[0]} months   ({time.time()-t0:.0f}s)")
# add the published rule as a column so its rank can be read
M = np.column_stack([M, mp["sum"].to_numpy()])
kept.append(PUB); names.append("PUBLISHED")
PUB_COL = M.shape[1] - 1

# ---------------------------------------------------------------- 3. CSCV / PBO
print("\n" + "=" * 112)
print("3. PBO -- combinatorially symmetric cross-validation (Bailey / Lopez de Prado)")
print("=" * 112)
S = 16
blocks = np.array_split(np.arange(M.shape[0]), S)
combos = list(itertools.combinations(range(S), S // 2))
print(f"  S = {S} blocks of ~{len(blocks[0])} months; C({S},{S//2}) = {len(combos):,} symmetric splits")


def perf(x):
    """Sharpe-like: mean / sd over the monthly sums, the standard CSCV statistic."""
    mu = x.mean(axis=0); sd = x.std(axis=0)
    return np.where(sd > 1e-12, mu / np.maximum(sd, 1e-12), 0.0)


lam, ranks, pub_rank_is = [], [], []
for cb in combos:
    is_idx = np.concatenate([blocks[b] for b in cb])
    os_idx = np.concatenate([blocks[b] for b in range(S) if b not in cb])
    pis, pos = perf(M[is_idx]), perf(M[os_idx])
    star = int(np.argmax(pis))
    r = float((pos < pos[star]).sum()) / max(len(pos) - 1, 1)      # OOS rank in [0,1]
    r = min(max(r, 1e-6), 1 - 1e-6)
    ranks.append(r)
    lam.append(np.log(r / (1 - r)))
    pub_rank_is.append(float((pis < pis[PUB_COL]).sum()) / max(len(pis) - 1, 1))
lam = np.array(lam); ranks = np.array(ranks)
PBO = float((lam <= 0).mean())
print(f"\n  PBO = {PBO:.3f}   (the IS-best configuration lands below the OOS median in "
      f"{100*PBO:.1f}% of splits)")
print(f"  median OOS rank of the IS winner: {np.median(ranks):.3f}   mean logit {lam.mean():+.3f}")
verdict = ("SEVERE -- selecting the in-sample winner is worse than a coin flip" if PBO >= 0.5 else
           "HIGH -- close to a coin flip" if PBO >= 0.35 else
           "MODERATE" if PBO >= 0.2 else "LOW")
print(f"  VERDICT: {verdict}")
print(f"  the published rule's own median IS rank across splits: {np.median(pub_rank_is):.3f} "
      f"(0.5 = median cell, 1.0 = best)")

# ---------------------------------------------------------------- 4. IS vs OOS degradation
print("\n" + "=" * 112)
print("4. PERFORMANCE DEGRADATION -- the IS-best cell's OOS result, over every split")
print("=" * 112)
d_is, d_os = [], []
for cb in combos[::7]:
    is_idx = np.concatenate([blocks[b] for b in cb])
    os_idx = np.concatenate([blocks[b] for b in range(S) if b not in cb])
    pis, pos = perf(M[is_idx]), perf(M[os_idx])
    star = int(np.argmax(pis))
    d_is.append(pis[star]); d_os.append(pos[star])
d_is, d_os = np.array(d_is), np.array(d_os)
print(f"  over {len(d_is)} splits: IS-best mean statistic {d_is.mean():+.4f} -> its OOS {d_os.mean():+.4f}")
print(f"  the IS winner is OOS-POSITIVE in {100*(d_os>0).mean():.1f}% of splits")
print(f"  slope of OOS on IS: {np.polyfit(d_is, d_os, 1)[0]:+.4f}  "
      f"(a flat or negative slope means IS performance does not predict OOS)")

# ---------------------------------------------------------------- 5. re-selecting walk-forward
print("\n" + "=" * 112)
print("5. WALK-FORWARD WITH THE SELECTION RE-RUN EACH FOLD, against the constants and a coin flip")
print("=" * 112)
rows = []
for k in range(0, len(allm) - W - 12 + 1, 12):
    tr_i = np.arange(k, k + W); te_i = np.arange(k + W, min(k + W + 12, len(allm)))
    if len(te_i) < 6:
        continue
    ptr = perf(M[tr_i])
    star = int(np.argmax(ptr))
    rnd = int(RNG.integers(0, M.shape[1]))
    rows.append(dict(test=f"{allm[te_i[0]]}..{allm[te_i[-1]]}",
                     chosen=float(M[te_i, star].sum()), random=float(M[te_i, rnd].sum()),
                     published=float(M[te_i, PUB_COL].sum()),
                     chosen_is=float(M[tr_i, star].sum())))
WF = pd.DataFrame(rows)
print(WF.to_string(index=False, float_format=lambda v: f"{v:9.3f}"))
for c in ("chosen", "random", "published"):
    print(f"  {c:10s} total {WF[c].sum():+8.2f} R   mean/fold {WF[c].mean():+7.3f}   "
          f"positive {int((WF[c]>0).sum())}/{len(WF)}")
print("\n  If 'chosen' does not beat 'published' and 'random', the re-selection is buying nothing.")

json.dump(dict(PBO=PBO, median_oos_rank=float(np.median(ranks)),
               pub_median_is_rank=float(np.median(pub_rank_is)),
               is_best_oos_positive=float((d_os > 0).mean()),
               slope=float(np.polyfit(d_is, d_os, 1)[0]),
               gap=float(Wf.IS_R.mean() - Wf.OOS_R.mean())),
          open("results/vwapema/pbo.json", "w"), indent=1)
np.savez_compressed("results/vwapema/pbo_arrays.npz", lam=lam, ranks=ranks, d_is=d_is, d_os=d_os)
Wf.to_csv("results/vwapema/wfo_published.csv", index=False)
WF.to_csv("results/vwapema/wfo_reselect.csv", index=False)
