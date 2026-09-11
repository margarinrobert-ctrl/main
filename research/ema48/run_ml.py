"""Deep learning on the base strategy's trades -- against the ladder it has to beat.

THE LABEL is the R each base trade actually earned (as asked: fresh cross, VWAP state, 1.5 ATR
stop, ATR trail, flatten), read at the SIGNAL bar's features. Trades overlap in time, so a naive
K-fold trains on the answer: the CV is sequential, PURGED (any training trade whose life overlaps
the test span is dropped) and EMBARGOED (one session either side).

THE LADDER: ridge -> logistic -> LightGBM -> XGBoost -> MLP 2x64 -> MLP 4x128. Every model gets a
SHUFFLED-LABEL TWIN. If the twin scores like the model, the score is noise (STUDY_V32: the twin
beat the real model in 69% of research cells). THE ACTIONABLE NUMBER is not AUC -- it is what the
kept trades EARN: keep the top 50% / 30% by predicted R and compare realised R, PF and p90 R to the
unfiltered base and to a same-selectivity RANDOM filter (STUDY_V28: a win-rate optimiser crushes
p90 and the tail is where a trend system earns).

Research block only. The locked block is read ONCE, for the model with the best research OOF IC.
"""
from __future__ import annotations
import os, sys, warnings
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e48_core as E, e48_features as X
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score
from scipy.stats import spearmanr
import lightgbm as lgb, xgboost as xgb, torch, torch.nn as nn
torch.manual_seed(0)
def line(t): print("\n" + "=" * 124 + f"\n{t}\n" + "=" * 124)

BASE = sys.argv[1] if len(sys.argv) > 1 else "asked"        # "asked" = with the ATR trail; "notrail" = without
D = E.build("NQ", 5); F = X.build(D)
sig = E.signals(D, "cross", 5, "state")
T = E.run(D, sig, trail=(BASE == "asked")); T["sig_bar"] = T["entry_bar"] - 1
print(f"  LABEL GEOMETRY: {BASE} -- fresh 13/48 cross, VWAP state, 1.5 ATR stop, {'ATR trail 1.0/1.0' if BASE == 'asked' else 'NO trail'}, 15:55 flatten")
T = T[T["sig_bar"] >= 2000].reset_index(drop=True)
Xall = F.iloc[T["sig_bar"].to_numpy()].reset_index(drop=True)
keep_cols = [c for c in Xall.columns if Xall[c].notna().mean() > 0.98]
Xall = Xall[keep_cols].fillna(Xall[keep_cols].median())
y = T["R"].to_numpy(); yw = (y > 0).astype(int)
res = (T["block"] == "research").to_numpy(); lock = ~res
print(f"  {len(T)} trades ({res.sum()} research / {lock.sum()} locked), {len(keep_cols)} features after a 98% coverage floor")
print(f"  base research: mean R {y[res].mean():+.4f}  win {100*yw[res].mean():.1f}%  p90 R {np.quantile(y[res], .9):+.3f}")

# ---------------------------------------------------------------- purged, embargoed sequential CV on research trades
ir = np.flatnonzero(res); n = len(ir); K = 6
sb, xb, ss = T["sig_bar"].to_numpy(), T["exit_bar"].to_numpy(), T["sess"].to_numpy()
folds = []
for k in range(K):
    te = ir[k * n // K:(k + 1) * n // K]
    lo_b, hi_b = sb[te].min(), xb[te].max(); lo_s, hi_s = ss[te].min(), ss[te].max()
    tr = np.array([i for i in ir if (xb[i] < lo_b or sb[i] > hi_b) and (ss[i] < lo_s - 1 or ss[i] > hi_s + 1)])
    folds.append((tr, te))
print(f"  {K} sequential folds, purged on trade lifetime and embargoed one session; mean train size {np.mean([len(t) for t, _ in folds]):.0f}")

class MLP(nn.Module):
    def __init__(s, d, w, depth):
        super().__init__(); L = []; p = d
        for _ in range(depth): L += [nn.Linear(p, w), nn.ReLU(), nn.Dropout(0.1)]; p = w
        L += [nn.Linear(p, 1)]; s.net = nn.Sequential(*L)
    def forward(s, x): return s.net(x).squeeze(-1)

def fit_predict(name, Xtr, ytr, Xte, cls=False):
    sc = StandardScaler().fit(Xtr); a, b = sc.transform(Xtr), sc.transform(Xte)
    if name == "ridge": return Ridge(alpha=10.0).fit(a, ytr).predict(b)
    if name == "logistic": return LogisticRegression(C=0.1, max_iter=2000).fit(a, ytr).predict_proba(b)[:, 1]
    if name == "lightgbm":
        m = (lgb.LGBMClassifier if cls else lgb.LGBMRegressor)(n_estimators=200, max_depth=3, learning_rate=0.03, min_child_samples=20, subsample=0.8, colsample_bytree=0.8, verbose=-1, random_state=0).fit(a, ytr)
        return m.predict_proba(b)[:, 1] if cls else m.predict(b)
    if name == "xgboost":
        m = (xgb.XGBClassifier if cls else xgb.XGBRegressor)(n_estimators=200, max_depth=3, learning_rate=0.03, subsample=0.8, colsample_bytree=0.8, random_state=0, verbosity=0).fit(a, ytr)
        return m.predict_proba(b)[:, 1] if cls else m.predict(b)
    w, depth = (64, 2) if name == "mlp_2x64" else (128, 4)
    m = MLP(a.shape[1], w, depth); opt = torch.optim.Adam(m.parameters(), lr=1e-3, weight_decay=1e-4)
    xa, ya = torch.tensor(a, dtype=torch.float32), torch.tensor(ytr, dtype=torch.float32)
    lossf = nn.BCEWithLogitsLoss() if cls else nn.MSELoss()
    for ep in range(200):
        m.train(); perm = torch.randperm(len(xa))
        for i in range(0, len(xa), 64):
            idx = perm[i:i + 64]; opt.zero_grad(); loss = lossf(m(xa[idx]), ya[idx]); loss.backward(); opt.step()
    m.eval()
    with torch.no_grad(): out = m(torch.tensor(b, dtype=torch.float32)).numpy()
    return 1 / (1 + np.exp(-out)) if cls else out

MODELS = ["ridge", "logistic", "lightgbm", "xgboost", "mlp_2x64", "mlp_4x128"]
rng = np.random.default_rng(3)
def oof(name, cls, shuffle=False):
    pred = np.full(len(T), np.nan)
    for tr, te in folds:
        yt = (yw if cls else y)[tr].copy()
        if shuffle: yt = rng.permutation(yt)
        pred[te] = fit_predict(name, Xall.iloc[tr].to_numpy(), yt, Xall.iloc[te].to_numpy(), cls)
    return pred

def score(pred, mask, label):
    p = pred[mask] if len(pred) == len(mask) else np.asarray(pred)
    yy, yb = y[mask], yw[mask]
    ic = spearmanr(p, yy).correlation; auc = roc_auc_score(yb, p) if len(np.unique(yb)) > 1 else np.nan
    out = dict(ic=ic, auc=auc)
    for keep in (0.5, 0.3):
        thr = np.quantile(p, 1 - keep); k = p >= thr; kept = yy[k]
        g, b = kept[kept > 0].sum(), -kept[kept <= 0].sum()
        out[f"R@{keep}"] = kept.mean(); out[f"PF@{keep}"] = g / b if b > 0 else np.nan; out[f"p90@{keep}"] = np.quantile(kept, .9); out[f"n@{keep}"] = int(k.sum())
    return out

line("A. THE LADDER on the research block -- OOF, purged and embargoed; each model beside its SHUFFLED twin")
print(f"  {'model':18s}{'objective':10s}{'IC':>8s}{'AUC':>7s} | {'R keep50':>9s}{'PF':>7s}{'p90':>7s} | {'R keep30':>9s}{'PF':>7s}{'p90':>7s} | twin IC / R keep30")
base = dict(R=y[res].mean(), PF=(y[res][y[res] > 0].sum() / -y[res][y[res] <= 0].sum()), p90=np.quantile(y[res], .9))
print(f"  {'UNFILTERED base':18s}{'':10s}{'':>8s}{'':>7s} | {base['R']:>9.4f}{base['PF']:>7.3f}{base['p90']:>7.3f} | {base['R']:>9.4f}{base['PF']:>7.3f}{base['p90']:>7.3f}")
results = {}
for cls in (False, True):
    for name in MODELS:
        if name == "ridge" and cls: continue
        if name == "logistic" and not cls: continue
        pr = oof(name, cls); pt = oof(name, cls, shuffle=True)
        s = score(pr, res, "real"); st = score(pt, res, "twin"); results[(name, cls)] = (pr, s, st)
        print(f"  {name:18s}{'win/lose' if cls else 'R':10s}{s['ic']:>8.4f}{s['auc']:>7.3f} | {s['R@0.5']:>9.4f}{s['PF@0.5']:>7.3f}{s['p90@0.5']:>7.3f} | {s['R@0.3']:>9.4f}{s['PF@0.3']:>7.3f}{s['p90@0.3']:>7.3f} | {st['ic']:+.4f} / {st['R@0.3']:+.4f}")

line("B. THE SAME-SELECTIVITY RANDOM FILTER -- what keeping 50% / 30% of trades AT RANDOM earns (500 draws)")
for keep in (0.5, 0.3):
    yy = y[res]; k = int(keep * len(yy)); draws = np.array([rng.choice(yy, k, replace=False).mean() for _ in range(500)])
    print(f"  keep {int(100*keep)}%: random-filter R median {np.median(draws):+.4f}  5-95% [{np.quantile(draws,.05):+.4f}, {np.quantile(draws,.95):+.4f}]")
    for (name, cls), (pr, s, st) in results.items():
        print(f"      {name:12s}{'win' if cls else 'R':4s} real {s[f'R@{keep}']:+.4f} (p {(draws >= s[f'R@{keep}']).mean():.3f})   twin {st[f'R@{keep}']:+.4f} (p {(draws >= st[f'R@{keep}']).mean():.3f})")

line("C. THE ONE LOCKED READ -- the model with the best research OOF IC, trained on ALL research trades")
best = max(results, key=lambda k: results[k][1]["ic"]); name, cls = best
print(f"  chosen on research IC: {name} ({'win/lose' if cls else 'R'}), IC {results[best][1]['ic']:+.4f}. Multiplicity: {len(results)} model-objective cells x 2 rungs.")
tr = np.flatnonzero(res); te = np.flatnonzero(lock)
pl = fit_predict(name, Xall.iloc[tr].to_numpy(), (yw if cls else y)[tr], Xall.iloc[te].to_numpy(), cls)
sl = score(pl, lock, "locked"); bl = dict(R=y[lock].mean(), PF=(y[lock][y[lock] > 0].sum() / -y[lock][y[lock] <= 0].sum()), p90=np.quantile(y[lock], .9))
print(f"  locked base: n {lock.sum()}  R {bl['R']:+.4f}  PF {bl['PF']:.3f}  p90 {bl['p90']:+.3f}")
print(f"  locked {name}: IC {sl['ic']:+.4f}  AUC {sl['auc']:.3f} | keep50 R {sl['R@0.5']:+.4f} PF {sl['PF@0.5']:.3f} p90 {sl['p90@0.5']:+.3f} (n {sl['n@0.5']}) | keep30 R {sl['R@0.3']:+.4f} PF {sl['PF@0.3']:.3f} p90 {sl['p90@0.3']:+.3f} (n {sl['n@0.3']})")
yy = y[lock]
for keep in (0.5, 0.3):
    k = int(keep * len(yy)); draws = np.array([rng.choice(yy, k, replace=False).mean() for _ in range(500)])
    print(f"  locked random filter keep {int(100*keep)}%: median {np.median(draws):+.4f}  ->  {name} p {(draws >= sl[f'R@{keep}']).mean():.3f}")

line("D. WHAT THE BEST MODEL READS -- top features by |ridge coefficient| on research (interpretable, not the winner)")
sc = StandardScaler().fit(Xall.iloc[tr]); rm = Ridge(alpha=10.0).fit(sc.transform(Xall.iloc[tr]), y[tr])
co = pd.Series(rm.coef_, index=Xall.columns).sort_values(key=np.abs, ascending=False)
print("  " + "\n  ".join(f"{k:26s} {v:+.4f}" for k, v in co.head(10).items()))
