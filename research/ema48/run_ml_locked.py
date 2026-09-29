"""Sections C and D for the AS-ASKED base, using the model the pre-declared rule chose on the
first ladder run (best research OOF IC = logistic win/lose, 0.1407; results/ema48/ml.txt A-B).
Retraining the whole ladder to re-derive a choice already made would be wasted compute."""
from __future__ import annotations
import os, sys, warnings
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e48_core as E, e48_features as X
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score
from scipy.stats import spearmanr
warnings.filterwarnings("ignore")
D = E.build("NQ", 5); F = X.build(D); sig = E.signals(D, "cross", 5, "state")
T = E.run(D, sig, trail=True); T["sig_bar"] = T["entry_bar"] - 1; T = T[T["sig_bar"] >= 2000].reset_index(drop=True)
Xa = F.iloc[T["sig_bar"].to_numpy()].reset_index(drop=True); cols = [c for c in Xa.columns if Xa[c].notna().mean() > 0.98]
Xa = Xa[cols].fillna(Xa[cols].median()); y = T["R"].to_numpy(); yw = (y > 0).astype(int)
res = (T["block"] == "research").to_numpy(); lock = ~res; rng = np.random.default_rng(3)
print("C. THE ONE LOCKED READ (as-asked base) -- logistic win/lose, chosen on research IC +0.1407 before this read")
sc = StandardScaler().fit(Xa[res]); m = LogisticRegression(C=0.1, max_iter=2000).fit(sc.transform(Xa[res]), yw[res])
p = m.predict_proba(sc.transform(Xa[lock]))[:, 1]; yy = y[lock]
print(f"  locked base: n {lock.sum()}  R {yy.mean():+.4f}  PF {yy[yy>0].sum()/-yy[yy<=0].sum():.3f}  win {100*(yy>0).mean():.1f}%  p90 {np.quantile(yy,.9):+.3f}")
print(f"  locked logistic: IC {spearmanr(p, yy).correlation:+.4f}  AUC {roc_auc_score((yy>0).astype(int), p):.3f}")
for keep in (0.5, 0.3):
    k = p >= np.quantile(p, 1 - keep); kk = yy[k]; n = int(k.sum())
    draws = np.array([rng.choice(yy, n, replace=False).mean() for _ in range(500)])
    print(f"  keep {int(100*keep)}%: n {n}  R {kk.mean():+.4f}  PF {kk[kk>0].sum()/-kk[kk<=0].sum():.3f}  win {100*(kk>0).mean():.1f}%  p90 {np.quantile(kk,.9):+.3f}   random-filter median {np.median(draws):+.4f}  p {(draws >= kk.mean()).mean():.3f}")
print("\nD. WHAT RIDGE READS on research (|coef|, standardised features)")
rm = Ridge(alpha=10.0).fit(sc.transform(Xa[res]), y[res]); co = pd.Series(rm.coef_, index=cols).sort_values(key=np.abs, ascending=False)
print("  " + "\n  ".join(f"{k:26s} {v:+.4f}" for k, v in co.head(10).items()))
