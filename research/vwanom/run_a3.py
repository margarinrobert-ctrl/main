"""A3 -- the anomaly question answered directly, then ONE locked read, then the deflation.

Three separate things, in this order:
  * A3.1  THE ANOMALY LADDER. Does an event on a bar the autoencoder cannot rebuild behave
    differently from one it can? This does not need the primary to have an edge -- the answer is
    interesting either way -- and it is the only family here that cannot be accused of fitting the
    outcome, because the autoencoder never sees a label.
  * A3.2  THE PRE-DECLARED LOCKED READ. One model, one keep fraction, chosen on RESEARCH, read
    ONCE on locked and once on the reserved forward block.
  * A3.3  DEFLATION. Deflated Sharpe at the counted trial number with correlated trials collapsed
    to an effective count, and White's reality check over EVERY candidate including the losers.
"""
import os, sys, pickle
import numpy as np, pandas as pd
from scipy.stats import skew, kurtosis

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vwapema"))
SK = "/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9"
sys.path.insert(0, SK + "/mechanism-first-alpha/scripts")
sys.path.insert(0, SK + "/quant-strategy-lab/scripts")
import gates, splits
import run_a2 as A2  # noqa: F401  -- reuses prep/models/MLP/oof

RNG = np.random.default_rng(99)
pd.set_option("display.width", 235)
L = lambda s: print("\n" + "=" * 114 + f"\n{s}\n" + "=" * 114)
print(__doc__)
BUNDLE = pickle.load(open("results/vwanom/feat_cache.pkl", "rb"))
FCOLS = A2.FCOLS
ANM = [c for c in FCOLS if c.startswith("anm.")]

L("A3.1  THE ANOMALY LADDER -- quintiles of each unsupervised score, no label ever seen")
rows = []
for (mk, sd), b in BUNDLE.items():
    m, X = b["meta"], b["feat"]
    blocks = (("whole", None),) if mk == "US30_ISO" else (("research", 0), ("LOCKED", 1))
    for col in ANM:
        for bn, blk in blocks:
            sel = np.ones(len(m), bool) if blk is None else (m.blk == blk).to_numpy()
            x = X.loc[sel, col].to_numpy(float)
            y = m.loc[sel, "pct"].to_numpy()
            ok = np.isfinite(x) & np.isfinite(y)
            if ok.sum() < 100:
                continue
            q = pd.qcut(pd.Series(x[ok]), 5, labels=False, duplicates="drop")
            g = pd.DataFrame(dict(q=q, y=y[ok])).groupby("q").y.agg(["size", "mean"])
            rows.append(dict(feed=mk, cell=sd, block=bn, score=col, n=int(ok.sum()),
                             **{f"Q{i+1}": round(float(g["mean"].get(i, np.nan)), 4) for i in range(5)},
                             spread=round(float(g["mean"].iloc[-1] - g["mean"].iloc[0]), 4),
                             rho=round(float(pd.Series(x[ok]).corr(pd.Series(y[ok]), method="spearman")), 4)))
AL = pd.DataFrame(rows)
AL.to_csv("results/vwanom/a3_anomaly_ladder.csv", index=False)
for col in ANM:
    s = AL[AL.score == col]
    print(f"\n  --- {col}   (Q1 = least anomalous, Q5 = most; percent of entry price)")
    print(s[["feed", "cell", "block", "n", "Q1", "Q2", "Q3", "Q4", "Q5", "spread", "rho"]].to_string(index=False))

print("\n  SIGN CONSISTENCY of rho across every feed x cell x block cell, per score:")
print(AL.groupby("score").agg(cells=("rho", "size"), mean_rho=("rho", "mean"),
                              share_positive=("rho", lambda s: round(float((s > 0).mean()), 2)),
                              research_mean=("rho", "mean")).round(4).to_string())
print("""
  A score whose sign flips between blocks has found the block, not an anomaly. Read `share_positive`
  before any single spread: 0.5 is a coin flip over these cells and they are NOT independent
  (US100 and US30 are 0.758-correlated indices over the same calendar).""")

L("A3.2  THE PRE-DECLARED LOCKED READ")
LAD = pd.read_csv("results/vwanom/a2_ladder.csv")
SCORES = pickle.load(open("results/vwanom/a2_scores.pkl", "rb"))
real = LAD[~LAD.shuffled]
picks = {}
for (mk, sd), g in real.groupby(["feed", "cell"]):
    best = g.loc[g.ic.idxmax()]
    picks[(mk, sd)] = str(best.model)
    print(f"  {mk} {sd}: model chosen on RESEARCH IC = {best.model!r} (IC {best.ic:+.4f}); "
          f"keep fraction 0.50, declared before the read")
rows = []
for (mk, sd), nm in picks.items():
    for blk, bn in ((0, "research"), (1, "LOCKED")):
        X, y, meta, hold = A2.prep(mk, sd, blk)
        if len(y) < 60:
            continue
        if blk == 0:
            p = SCORES[(mk, sd, nm)]
        else:
            Xtr, ytr, _mt, h2 = A2.prep(mk, sd, 0)
            make = dict(list(A2.models().items()) +
                        [("mlp 2x64", lambda: A2.MLP((64, 64), seed=0)),
                         ("mlp 4x128", lambda: A2.MLP((128, 128, 128, 128), seed=0))])[nm]
            mdl = make(); mdl.fit(Xtr, ytr)
            p = mdl.predict(X)
            thr_res = float(np.nanquantile(SCORES[(mk, sd, nm)], 0.5))
        thr = float(np.nanquantile(p, 0.5)) if blk == 0 else thr_res
        keep = np.isfinite(p) & (p >= thr)
        g = gates.meta_gate(y, np.nan_to_num(p, nan=-1e18), thr)
        rows.append(dict(feed=mk, cell=sd, model=nm, block=bn, n=len(y), n_kept=int(keep.sum()),
                         kept_frac=round(float(keep.mean()), 3),
                         base=round(1e2 * y.mean(), 4), kept=round(1e2 * y[keep].mean(), 4),
                         uplift=round(1e2 * float(g["unsized_uplift"]), 4),
                         boot_p=round(float(g["bootstrap_p_one_sided"]), 3),
                         p90_base=round(1e2 * np.percentile(y, 90), 3),
                         p90_kept=round(1e2 * np.percentile(y[keep], 90), 3)))
L2 = pd.DataFrame(rows)
print("\n" + L2.to_string(index=False))
L2.to_csv("results/vwanom/a3_locked.csv", index=False)
print("""
  THE KEPT FRACTION IS THE CALIBRATION CHECK. A research threshold applied to a locked block should
  keep roughly the fraction it was set for. `STUDY_AUTOBNN` kept 105 of 105 because the posterior
  means were not comparable across the split; `STUDY_V61_FEATURES_15M` kept 45% against a 40%
  target, which is what a calibrated score looks like.""")

L("A3.3  DEFLATION -- the trial count, the effective count, and the reality check")
CAND = pickle.load(open("results/vwanom/a2_candidates.pkl", "rb"))
keys = sorted(CAND)
n_min = min(len(CAND[k]) for k in keys)
Rmat = np.column_stack([CAND[k][:n_min] for k in keys])
cc = np.corrcoef(Rmat, rowvar=False)
avg_corr = float((cc.sum() - len(keys)) / (len(keys) * (len(keys) - 1)))
eff = gates.effective_trials(len(keys), avg_corr)
sr = np.array([CAND[k].mean() / max(CAND[k].std(ddof=1), 1e-12) for k in keys])
best_i = int(np.argmax(sr))
vt = float(np.var(sr))
print(f"  candidates evaluated M = {len(keys)}   avg pairwise correlation {avg_corr:+.3f}   "
      f"effective N = {eff:.1f}")
print(f"  var(trial Sharpes) = {vt:.6f};  E[max Sharpe | pure noise] over {eff:.0f} effective "
      f"trials = {gates.expected_max_sharpe(vt, max(eff, 2)):.4f}")
print(f"  best candidate: {keys[best_i]}  Sharpe/event {sr[best_i]:+.4f}")
d = gates.deflated_sharpe(float(sr[best_i]), n_min, max(eff, 2), vt,
                          float(skew(Rmat[:, best_i])), float(kurtosis(Rmat[:, best_i], fisher=False)))
print(f"  DEFLATED SHARPE = {float(d if np.isscalar(d) else d.get('dsr', np.nan)):.4f}")
rc = gates.reality_check(Rmat)
print(f"  WHITE REALITY CHECK p = {rc if np.isscalar(rc) else rc.get('p_value', rc)}")
print("""
  Both procedures are deliberately conservative and the skill says to report that plainly rather
  than hunting for a softer test: a t of 3.8 fails the reality check when it was the best of 200.""")
