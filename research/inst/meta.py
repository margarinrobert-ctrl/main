"""Meta-labeling (Lopez de Prado) on the frontier's >=300-trades/yr cell: a primary rule generates
the trades, a secondary model predicts each trade's R from 37+ causal features at the signal bar,
and only the top fraction by predicted R is taken. REGRESSION ON R, not win/lose -- V28, V32 and
EMA48 all measured that a win/lose objective discards the tail a breakout earns in. Purged and
embargoed sequential folds, a shuffled-label twin beside every model, a same-selectivity random
filter as the null, and ONE pre-declared locked read (ridge, keep 60%)."""
import os, sys, warnings
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56", "research/ema48", "research/inst"):
    sys.path.insert(0, os.path.join(ROOT, p))
import v61core as V, v53abs as A, e48_features as F
from frontier import signal_sets, geometry
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
def line(t): print("\n" + "=" * 126 + f"\n{t}\n" + "=" * 126)
def pf(p): w = p > 0; return p[w].sum() / max(1e-9, -p[~w].sum())

G = pd.read_parquet("results/inst/frontier_grid.parquet")
ok = G[(G.tf == 5) & (G.hold_name == "4h") & (G.n_res >= 40) & (G.tpy_res >= 300)]
cell = ok.loc[ok.pf_res.idxmax()]
print("  primary rule (the >=300 trades/yr envelope cell on 5m):",
      {k: (int(cell[k]) if k in ("ent","exN","hold","k","w","psh","adapt") else float(cell[k])) for k in ("ent","exN","stop","tp","hold","adapt","k","w","ma","chop","psh")})
print(f"  research PF {cell.pf_res:.3f} at {cell.tpy_res:.0f} trades/yr; locked PF {cell.pf_lock:.3f} at {cell.tpy_lock:.0f}")

D = V.build(5)
rth = (D["mod"] >= 570) & (D["mod"] < 930)
rows, offs, vals, K = signal_sets(D, rth)
s_idx = K.index[(K.ent == cell.ent) & (K.k == cell.k) & (K.w == cell.w) & (K.ma == cell.ma) & (K.chop == cell.chop) & (K.psh == cell.psh)][0]
Gd = geometry(5)
g_idx = Gd.index[(Gd.exN == cell.exN) & (Gd.stop == cell.stop) & (Gd.tp == cell.tp) & (Gd.hold == cell.hold) & (Gd.adapt == cell.adapt)][0]
g1 = Gd.iloc[[g_idx]]
exlo = np.vstack([D["ex_lo"][e] for e in V.EXITS])
calm = np.zeros(D["n"], np.bool_); v = D["vpct"]; calm[np.isfinite(v)] = v[np.isfinite(v)] <= 0.5
xb, R, pts = V._tensor(D["o"], D["h"], D["l"], D["c"], D["atr"], rows.astype(np.int64), exlo, calm,
                       g1["ei"].to_numpy(np.int64), g1["shi"].to_numpy(float), g1["slo"].to_numpy(float),
                       g1["tp"].to_numpy(float), g1["hold"].to_numpy(np.int64), V.COST, V.SLIP, D["n"])
epx = D["o"][np.minimum(rows + 1, D["n"] - 1)]
# the position lock, in Python, for this one signal set x geometry
sel = vals[offs[s_idx]:offs[s_idx + 1]]
free = -1; tr = []
for kk in sel:
    if xb[kk, 0] < 0 or not np.isfinite(R[kk, 0]) or rows[kk] <= free: continue
    free = xb[kk, 0]
    tr.append((rows[kk], float(R[kk, 0]), 100.0 * float(pts[kk, 0]) / epx[kk], int(xb[kk, 0])))
T = pd.DataFrame(tr, columns=["sig", "R", "pct", "xb"])
T["research"] = T.sig < D["cut"]
print(f"  reproduced trade table: research n {int(T.research.sum())} PF {pf(T[T.research].pct.to_numpy()):.3f} | locked n {int((~T.research).sum())} PF {pf(T[~T.research].pct.to_numpy()):.3f}")

# ---- features at the signal bar ----
ix = D["ix"]
Df = dict(o=D["o"], h=D["h"], l=D["l"], c=D["c"], v=D["v"], atr=D["atr"], n=D["n"], mod=D["mod"],
          sess=(ix.year * 10000 + ix.month * 100 + ix.day).to_numpy(),
          ef=pd.Series(D["c"]).ewm(span=13, adjust=False).mean().to_numpy(),
          es=pd.Series(D["c"]).ewm(span=48, adjust=False).mean().to_numpy(), vwap=np.full(D["n"], np.nan))
rth_m = (D["mod"] >= 570) & (D["mod"] < 960); tp_ = (D["h"] + D["l"] + D["c"]) / 3
dv = pd.DataFrame({"pv": np.where(rth_m, tp_ * D["v"], 0.0), "vv": np.where(rth_m, D["v"], 0.0), "s": Df["sess"]})
g = dv.groupby("s", sort=False); vw = (g["pv"].cumsum() / g["vv"].cumsum().replace(0, np.nan)).to_numpy(); vw[~rth_m] = np.nan
Df["vwap"] = vw
Fe = F.build(Df)
extra = pd.DataFrame({"v61.d_ma": D["d_ma"], "v61.chop": D["chop"], "v61.vpct": D["vpct"],
                      "v61.psh_dist": (D["c"] - D["psh"]) / D["atr"]})
Fe = pd.concat([Fe.reset_index(drop=True), extra], axis=1)
X = Fe.iloc[T.sig.to_numpy()].reset_index(drop=True)
cov = X.notna().mean(); X = X.loc[:, cov >= 0.98]; X = X.fillna(X.median())
y = T.R.to_numpy(); ypct = T.pct.to_numpy(); res = T.research.to_numpy()
print(f"  {X.shape[1]} features after a 98% coverage floor; {len(T)} trades")

# ---- purged, embargoed sequential CV on research ----
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
try:
    import lightgbm as lgb; HAS_LGB = True
except Exception:
    HAS_LGB = False
Xr, yr, pr = X[res].to_numpy(float), y[res], ypct[res]; sig_r = T.sig[res].to_numpy(); xb_r = T.xb[res].to_numpy()
n = len(yr); K_ = 6; edges = np.linspace(0, n, K_ + 1).astype(int); EMB = 100  # bars
def oof(model_fn, seed=0, shuffle=False):
    rng = np.random.default_rng(seed); pred = np.full(n, np.nan)
    yy = rng.permutation(yr) if shuffle else yr
    for f in range(1, K_):                          # sequential: train on folds < f, test fold f
        te = np.arange(edges[f], edges[f + 1]); t0 = sig_r[te[0]]
        trn = np.arange(0, edges[f]); trn = trn[xb_r[trn] < t0 - EMB]   # purge trades whose life overlaps, embargo
        sc = StandardScaler().fit(Xr[trn]); m = model_fn().fit(sc.transform(Xr[trn]), yy[trn])
        pred[te] = m.predict(sc.transform(Xr[te]))
    return pred
models = {"ridge": lambda: Ridge(alpha=10.0)}
if HAS_LGB:
    models["lightgbm"] = lambda: lgb.LGBMRegressor(n_estimators=200, learning_rate=0.03, num_leaves=7, min_child_samples=40, subsample=0.8, colsample_bytree=0.8, verbose=-1)
line("A. META-LABEL LADDER on research (OOF, folds 2-6), keep the top fraction by PREDICTED R; twin = shuffled labels")
scored = np.arange(edges[1], n); yrs_res = V.YEARS["res"] * (len(scored) / n)
base_pf = pf(pr[scored]); print(f"  base (no filter) on the scored folds: n {len(scored)} PF {base_pf:.3f} pct {pr[scored].mean():+.4f} p90 R {np.quantile(yr[scored],.9):.2f}  trades/yr {len(scored)/yrs_res:.0f}")
print(f"  {'model':>9} {'IC':>7} | " + " | ".join(f"{'keep '+str(int(100*q))+'%':>28}" for q in (0.8, 0.6, 0.4)) + " | twin IC / keep60 PF")
rng0 = np.random.default_rng(5); pool = pr[scored]
def rand_keep(q, draws=400):
    k = int(q * len(pool)); return np.array([pf(pool[rng0.choice(len(pool), k, replace=False)]) for _ in range(draws)])
RK = {q: rand_keep(q) for q in (0.8, 0.6, 0.4)}
PRED = {}
for nm, fn in models.items():
    p = oof(fn); pt = oof(fn, seed=1, shuffle=True); PRED[nm] = p
    ic = np.corrcoef(p[scored], yr[scored])[0, 1]; ict = np.corrcoef(pt[scored], yr[scored])[0, 1]
    cells = []
    for q in (0.8, 0.6, 0.4):
        thr = np.quantile(p[scored], 1 - q); keep = scored[p[scored] >= thr]
        cells.append(f"PF {pf(pr[keep]):.3f} n{len(keep)} tpy {len(keep)/yrs_res:.0f} p90 {np.quantile(yr[keep],.9):.2f} p {np.mean(RK[q] >= pf(pr[keep])):.2f}")
    thr = np.quantile(pt[scored], 0.4); kt = scored[pt[scored] >= thr]
    print(f"  {nm:>9} {ic:>+7.3f} | " + " | ".join(f"{c:>28}" for c in cells) + f" | {ict:+.3f} / {pf(pr[kt]):.3f}")
print("  'p' = share of same-selectivity RANDOM subsets with a PF at least as high; the twin column is the noise floor.")

line("B. ONE LOCKED READ -- pre-declared: ridge trained on ALL research trades, keep the top 60% by predicted R")
sc = StandardScaler().fit(Xr); m = Ridge(alpha=10.0).fit(sc.transform(Xr), yr)
Xl, yl, pl_ = X[~res].to_numpy(float), y[~res], ypct[~res]; pL = m.predict(sc.transform(Xl))
thr = np.quantile(m.predict(sc.transform(Xr)), 0.4)
keep = pL >= thr; yrs_l = V.YEARS["lock"]
print(f"  locked base:      n {len(yl)} PF {pf(pl_):.3f} pct {pl_.mean():+.4f} p90 R {np.quantile(yl,.9):.2f}  trades/yr {len(yl)/yrs_l:.0f}")
print(f"  locked, kept 60%: n {int(keep.sum())} PF {pf(pl_[keep]):.3f} pct {pl_[keep].mean():+.4f} p90 R {np.quantile(yl[keep],.9) if keep.sum() else float('nan'):.2f}  trades/yr {keep.sum()/yrs_l:.0f}  IC {np.corrcoef(pL, yl)[0,1]:+.3f}")
rngl = np.random.default_rng(8); rk = np.array([pf(pl_[rngl.choice(len(pl_), int(keep.sum()), replace=False)]) for _ in range(400)])
print(f"  same-selectivity random filter on locked: median PF {np.median(rk):.3f}  p {np.mean(rk >= pf(pl_[keep])):.3f}")
coef = pd.Series(m.coef_, index=X.columns).sort_values(key=np.abs, ascending=False).head(6)
print("  largest ridge coefficients: " + ", ".join(f"{k} {v:+.2f}" for k, v in coef.items()))
