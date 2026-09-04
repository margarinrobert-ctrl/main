"""ADVERSARIAL AUDIT of the ML breakout-quality filter.

The claim: out-of-fold AUC 0.5785, and the top decile of triggers turns
expectancy from -2.73 to +0.15 pts/trade.

Attacks, in order of lethality:
  A. PERMUTATION TEST. Shuffle the labels and re-run the whole purged-CV
     pipeline. If shuffled AUC is not centred on 0.500, the CV structure leaks
     and the real AUC is meaningless.
  B. SEED / HYPERPARAMETER STABILITY. One AUC from one config is one draw.
  C. FEATURE ABLATION. Is the skill carried by one suspicious feature?
  D. COST STRESS on the surviving book.
  E. SUB-PERIOD. Delivered throughout, or one window?
"""
import numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
from sklearn.metrics import roc_auc_score
import lightgbm as lgb
import lab
from agent_ml import (X, y, sb, hold, FEATS, tr, purged_folds, SYM, res,
                      N_ENTRY, SM, TM, MH, df, w)

folds = purged_folds(sb, hold, K=6, embargo=32)

def fit_oof(Xd, yd, seed=0, leaves=15, mcs=60, nest=300, lr=0.03):
    oof = np.full(len(yd), np.nan)
    for tr_i, te_i in folds:
        if len(tr_i) < 200: continue
        m = lgb.LGBMClassifier(n_estimators=nest, learning_rate=lr, num_leaves=leaves,
                               min_child_samples=mcs, subsample=0.8, colsample_bytree=0.7,
                               reg_lambda=5.0, verbose=-1, random_state=seed)
        m.fit(Xd[tr_i], yd[tr_i]); oof[te_i] = m.predict_proba(Xd[te_i])[:, 1]
    ok = ~np.isnan(oof)
    return oof, roc_auc_score(yd[ok], oof[ok])

print("="*100)
print("ATTACK A - PERMUTATION TEST  (shuffle labels, re-run the entire pipeline)")
print("  If the purged CV is sound, shuffled AUC must centre on 0.500.")
print("="*100)
_, auc_real = fit_oof(X, y, seed=0)
print(f"  real AUC: {auc_real:.4f}")
rng = np.random.default_rng(7)
perm = []
for k in range(12):
    ys = rng.permutation(y)
    _, a_ = fit_oof(X, ys, seed=k)
    perm.append(a_)
perm = np.array(perm)
print(f"  shuffled AUC over {len(perm)} permutations: mean {perm.mean():.4f}  "
      f"sd {perm.std(ddof=1):.4f}  max {perm.max():.4f}")
z = (auc_real - perm.mean()) / perm.std(ddof=1)
p_perm = (perm >= auc_real).mean()
print(f"  z of real AUC vs permutation null: {z:+.2f}   p = {p_perm:.4f}")
print(f"  VERDICT: {'CV structure is sound; the AUC is real skill' if abs(perm.mean()-0.5)<0.02 else 'CV LEAKS - shuffled AUC is not 0.5, the real AUC is meaningless'}")

print("\n" + "="*100)
print("ATTACK B - SEED AND HYPERPARAMETER STABILITY")
print("="*100)
aucs = []
for seed in range(6):
    _, a_ = fit_oof(X, y, seed=seed); aucs.append(a_)
print(f"  6 random seeds        : {' '.join(f'{a:.4f}' for a in aucs)}   sd {np.std(aucs, ddof=1):.4f}")
hp = []
for leaves, mcs, lr in ((7, 100, 0.05), (31, 30, 0.02), (15, 200, 0.03), (63, 20, 0.05)):
    _, a_ = fit_oof(X, y, leaves=leaves, mcs=mcs, lr=lr)
    hp.append((leaves, mcs, lr, a_))
    print(f"  leaves={leaves:<3} min_child={mcs:<4} lr={lr:<5} -> AUC {a_:.4f}")

print("\n" + "="*100)
print("ATTACK C - FEATURE ABLATION  (drop each of the top features in turn)")
print("="*100)
oof_r, _ = fit_oof(X, y)
for f in ["tv_z100", "sess_elapsed", "dwidth40_atr", "ema200_slope", "atr_pct250"]:
    j = FEATS.index(f)
    keep = [i for i in range(len(FEATS)) if i != j]
    _, a_ = fit_oof(X[:, keep], y)
    print(f"  without {f:<16} AUC {a_:.4f}   (delta {a_-auc_real:+.4f})")
tod_j = [i for i, f in enumerate(FEATS) if f in ("tod", "sess_elapsed")]
keep = [i for i in range(len(FEATS)) if i not in tod_j]
_, a_notime = fit_oof(X[:, keep], y)
print(f"  without ANY time feature   AUC {a_notime:.4f}   (delta {a_notime-auc_real:+.4f})")

print("\n" + "="*100)
print("ATTACK D+E - the top-decile book: cost stress and sub-period consistency")
print("="*100)
ok = ~np.isnan(oof_r)
thr = np.nanquantile(oof_r[ok], 0.90)
sel = ok & (oof_r >= thr)
idx_s, side_s = sb[sel], tr.side.values[sel]
print(f"  top-decile triggers: {sel.sum():,}")
for cm in (1.0, 1.5, 2.0, 3.0):
    b = lab.book(SYM, idx_s, side_s, stop_mult=SM, targ_mult=TM, max_hold=MH,
                 one_per_session=True, cost_mult=cm)
    b = b[np.isin(b.sig_bar, np.where(res)[0])]
    print(f"    cost x{cm:<4} n={len(b):>5,}  exp={b.net.mean():>+7.2f} pts")
b = lab.book(SYM, idx_s, side_s, stop_mult=SM, targ_mult=TM, max_hold=MH, one_per_session=True)
b = b[np.isin(b.sig_bar, np.where(res)[0])]
ss = df.sess.values[b.sig_bar.values]
qs = np.quantile(ss, [0, 1/3, 2/3, 1.0])
print("  sub-periods (contiguous thirds of the research block):")
for i in range(3):
    m = (ss >= qs[i]) & (ss <= qs[i+1] if i == 2 else ss < qs[i+1])
    print(f"    third {i+1}: n={m.sum():>4,}  exp={b.net.values[m].mean():>+7.2f} pts")
