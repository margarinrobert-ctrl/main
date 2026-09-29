"""GATE 2 -- the meta layer on one primary's events. RESEARCH ONLY. Usage: run_gate2.py <name>

  1. SCREEN: IC of every feature against the event's percent return, beside a shuffled twin;
     redundancy measured ON THE EVENTS with family-first selection; sign stability across the two
     research halves and three volatility regimes.
  2. MODELS: ridge / random forest / LightGBM with a RETURN objective (not win/lose -- STUDY_V28/V32:
     a win/lose objective cuts the tail a barrier system earns in), time-ordered purged 5-fold with
     a 5-day embargo, every model beside a shuffled-label twin.
  3. GATE 2: `meta_gate` uplift on UNSIZED returns at declared keep fractions, and against a
     SAME-SELECTIVITY RANDOM FILTER.
  4. DROP-ONE on the best cell.
  5. The PORTABLE form: a ridge on the final set with every constant exported for the Pine.
Locked is NOT read here. `run_locked.py` does that once.
"""
import os, sys, json, time
import numpy as np, pandas as pd
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
import lightgbm as lgb

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, "/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/mechanism-first-alpha/scripts")
from research.ibopt import ibfeat as IF    # noqa: E402
import gates                                 # noqa: E402

pd.set_option("display.width", 200)
name = sys.argv[1] if len(sys.argv) > 1 else "published"
X = pd.read_parquet(f"results/ibopt/feat_{name}.parquet")
cols = IF.feature_cols(X)
R = X[X.blk == 0].reset_index(drop=True)
y = R.pct.to_numpy()
rng = np.random.default_rng(5)
print(__doc__)
print(f"  primary [{name}]: research events {len(R)}, features {len(cols)}\n")
LOOKS = dict(features=len(cols))


def ic(a, b):
    m = np.isfinite(a) & np.isfinite(b)
    return float(pd.Series(a[m]).corr(pd.Series(b[m]), method="spearman")) if m.sum() > 30 else np.nan


# ---------------------------------------------------------------- 1. screen
print("=" * 108); print("SCREEN -- IC vs return beside a shuffled twin; stability across halves and vol regimes"); print("=" * 108)
ysh = rng.permutation(y)
half = np.arange(len(R)) < len(R) // 2
vq = pd.qcut(R["vol.rv20_rank"].fillna(0.5), 3, labels=False, duplicates="drop").to_numpy()
rows = []
for c in cols:
    x = R[c].to_numpy(float)
    full = ic(x, y); twin = ic(x, ysh)
    h1, h2 = ic(x[half], y[half]), ic(x[~half], y[~half])
    regs = [ic(x[vq == k], y[vq == k]) for k in range(3)]
    stable = (np.sign(h1) == np.sign(h2) == np.sign(full)) and all(np.sign(r) == np.sign(full) for r in regs if np.isfinite(r))
    # a permutation p for the IC
    null = np.array([ic(x, rng.permutation(y)) for _ in range(200)])
    p = float((np.abs(null) >= abs(full)).mean())
    rows.append(dict(feature=c, ic=full, twin=twin, p=p, h1=h1, h2=h2, stable=bool(stable),
                     nan_pct=100 * float(np.isnan(x).mean())))
S = pd.DataFrame(rows).sort_values("p")
print(S.to_string(index=False, float_format=lambda v: f"{v:8.4f}"))
print(f"\n  features at p<=0.05: {int((S.p<=0.05).sum())} of {len(S)} (chance {0.05*len(S):.1f}); "
      f"sign-stable across halves AND regimes: {int(S.stable.sum())}")

# redundancy ON THE EVENTS, family-first
print("\n  REDUNDANCY on the events (|rho| >= 0.85 pairs):")
Cm = R[cols].corr(method="spearman")
pairs = [(a, b, Cm.loc[a, b]) for i, a in enumerate(cols) for b in cols[i + 1:] if abs(Cm.loc[a, b]) >= 0.85]
for a, b, r in pairs:
    print(f"    {a:20s} {b:20s} rho {r:+.3f}")
if not pairs:
    print("    none")
# pick: by family, keep the best-p feature per family first, then add others below |rho| 0.7 with kept
keep = []
for fam in IF.FAMILIES:
    cand = S[S.feature.str.startswith(fam + ".")].sort_values("p")
    for c in cand.feature:
        if all(abs(Cm.loc[c, k]) < 0.7 for k in keep):
            keep.append(c)
kept = [c for c in keep if S.set_index("feature").loc[c, "p"] <= 0.20]
print(f"\n  kept after family-first redundancy and a p<=0.20 screen: {len(kept)}: {kept}")
LOOKS["ic_tests"] = len(cols)

# ---------------------------------------------------------------- 2. models, purged CV
print("\n" + "=" * 108); print("MODELS -- purged 5-fold (5-day embargo), return objective, shuffled twins"); print("=" * 108)
Xk = R[kept].fillna(R[kept].median()).to_numpy(float)
days = R.day.to_numpy()
folds = np.array_split(np.arange(len(R)), 5)


def oof(model_fn, Xm, yv):
    pred = np.full(len(yv), np.nan)
    for te in folds:
        lo, hi = days[te[0]], days[te[-1]]
        tr = np.flatnonzero((days < lo - 5) | (days > hi + 5))
        mdl = model_fn(); mdl.fit(Xm[tr], yv[tr]); pred[te] = mdl.predict(Xm[te])
    return pred


MODELS = {"ridge": lambda: Ridge(alpha=10.0),
          "rf": lambda: RandomForestRegressor(n_estimators=300, min_samples_leaf=25, max_features=0.5, random_state=0, n_jobs=4),
          "lgbm": lambda: lgb.LGBMRegressor(n_estimators=200, learning_rate=0.03, num_leaves=7, min_child_samples=30,
                                            subsample=0.8, colsample_bytree=0.8, verbose=-1, random_state=0)}
scores = {}
for nm, fn in MODELS.items():
    mu = (Xk - Xk.mean(0)) / np.maximum(Xk.std(0), 1e-9)
    pr = oof(fn, mu, y); pt = oof(fn, mu, ysh)
    scores[nm] = pr
    print(f"  {nm:6s} OOF IC {ic(pr, y):+.4f}   shuffled twin {ic(pt, ysh):+.4f}")
LOOKS["models"] = len(MODELS)

# ---------------------------------------------------------------- 3. gate 2
print("\n" + "=" * 108); print("GATE 2 -- unsized uplift at declared keep fractions, vs bootstrap AND a same-selectivity random filter"); print("=" * 108)
KEEPS = (0.8, 0.7, 0.6, 0.5, 0.4)
rows = []
for nm, pr in scores.items():
    for kf in KEEPS:
        thr = np.nanquantile(pr, 1 - kf)
        g = gates.meta_gate(y / 100.0, pr, thr)
        kept_n = int((pr >= thr).sum())
        nullv = np.array([y[rng.choice(len(y), kept_n, replace=False)].mean() for _ in range(500)])
        filt_mean = y[pr >= thr].mean()
        rows.append(dict(model=nm, keep=kf, n=kept_n, base=y.mean(), filtered=filt_mean,
                         uplift=filt_mean - y.mean(), boot_p=g["bootstrap_p_one_sided"],
                         rand_filter_p=float((nullv >= filt_mean).mean())))
G2 = pd.DataFrame(rows)
print(G2.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
both = G2[(G2.boot_p <= 0.10) & (G2.rand_filter_p <= 0.10)]
print(f"\n  cells clearing BOTH nulls at p<=0.10: {len(both)} of {len(G2)}")
LOOKS["keep_fractions"] = len(G2)

# ---------------------------------------------------------------- 4. drop-one at the best cell
best = G2.sort_values("uplift", ascending=False).iloc[0]
print("\n" + "=" * 108); print(f"DROP-ONE at the best cell: {best.model} keep {best.keep:.0%}"); print("=" * 108)
fn = MODELS[best.model]
def uplift_with(feats):
    Xm = R[feats].fillna(R[feats].median()).to_numpy(float); Xm = (Xm - Xm.mean(0)) / np.maximum(Xm.std(0), 1e-9)
    pr = oof(fn, Xm, y); thr = np.nanquantile(pr, 1 - best.keep)
    return y[pr >= thr].mean() - y.mean(), ic(pr, y)
full_u, full_ic = uplift_with(kept)
print(f"  all kept ({len(kept)}): OOF IC {full_ic:+.4f} uplift {full_u:+.4f}")
drop = []
for c in kept:
    u, i2 = uplift_with([k for k in kept if k != c])
    print(f"  minus {c:20s} IC {i2:+.4f} uplift {u:+.4f}  delta {u-full_u:+.4f}")
    drop.append((c, u - full_u))
final = [c for c, d in drop if d < 0] or kept
print(f"\n  final set ({len(final)}): {final}")
LOOKS["dropone"] = len(kept)

# ---------------------------------------------------------------- 5. the portable ridge
Xf = R[final].fillna(R[final].median()); mu_ = Xf.mean(); sd_ = Xf.std().replace(0, 1)
Z = ((Xf - mu_) / sd_).to_numpy(); rd = Ridge(alpha=10.0).fit(Z, y)
score = rd.predict(Z)
thr = {f"{int(k*100)}": float(np.quantile(score, 1 - k)) for k in KEEPS}
spec = dict(primary=name, features=final, mean=mu_.to_dict(), sd=sd_.to_dict(),
            coef=dict(zip(final, rd.coef_.tolist())), intercept=float(rd.intercept_), thresholds=thr,
            best_cell=dict(model=best.model, keep=float(best.keep)), looks=LOOKS,
            fill_median=Xf.median().to_dict())
json.dump(spec, open(f"results/ibopt/meta_spec_{name}.json", "w"), indent=1)
S.to_csv(f"results/ibopt/screen_{name}.csv", index=False); G2.to_csv(f"results/ibopt/gate2_{name}.csv", index=False)
print("\n  ridge (in-sample, for the Pine): " + ", ".join(f"{k} {v:+.4f}" for k, v in zip(final, rd.coef_)))
print(f"  looks counted so far: {LOOKS}")
