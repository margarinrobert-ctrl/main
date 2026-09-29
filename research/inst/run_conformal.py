"""Conformalized quantile regression (CQR) + a regularised random forest, on the Donchian 55/30 cell.

WHY THIS MODEL. AutoBNN's meta-label failed on CALIBRATION: its posterior means shifted between
blocks, so the research cut kept 105 of 105 locked trades. Split-conformal prediction gives a
distribution-free guarantee -- the calibrated lower bound covers the realised R at the stated rate
whatever the model -- so the keep rule can be 'calibrated lower bound of R > 0' with NO threshold
chosen on research. CQR (Romano, Patterson, Candes 2019) conformalizes a quantile regressor.

WHY MORE DATA. 192 trades cannot train anything. The model is trained on EVERY Donchian-55 RTH
breakout bar with the cell's own exit geometry (the loosest set the cell is a subset of), R per bar
from the tensor, with LOPEZ DE PRADO uniqueness weights (1 / number of concurrently open labels)
because overlapping trades are not independent samples. Purged + embargoed sequential folds.

Features: the 37 truncation-audited causal features from research/ema48 plus V61's MA distance,
CHOP and volatility percentile. Label: R. Twins on shuffled labels. Null: random subset of the
same size. ONE pre-declared locked read per model: CQR lower bound (90% coverage) > 0."""
import os, sys, warnings, time
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56", "research/inst", "research/ema48", "research/v63", "research/scalp89"):
    sys.path.insert(0, os.path.join(ROOT, p))
import v61core as V
from donchian500k import signal_sets, geometry
import e48_features as EF
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
def line(t): print("\n" + "=" * 126 + f"\n{t}\n" + "=" * 126, flush=True)
t0 = time.time()
try:
    import lightgbm as lgb; HAVE_LGB = True
except Exception: HAVE_LGB = False
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
print("lightgbm:", HAVE_LGB)

D = V.build(15); rth = (D["mod"] >= 570) & (D["mod"] < 930); CUT = D["cut"]; n = D["n"]
Gd = geometry(15); rows, offs, vals, K = signal_sets(D, rth)
exlo = np.vstack([D["ex_lo"][e] for e in V.EXITS])
calm = np.zeros(n, np.bool_); v = D["vpct"]; calm[np.isfinite(v)] = v[np.isfinite(v)] <= 0.5
gi = int(np.flatnonzero((Gd.exN == 30) & (Gd.stop == 1.5) & (Gd.tp == 0.0) & (Gd.hold_name == "swing") & (Gd.adapt == 1))[0])
g1 = Gd.iloc[[gi]]
xb, R, pts = V._tensor(D["o"], D["h"], D["l"], D["c"], D["atr"], rows.astype(np.int64), exlo, calm,
                       g1["ei"].to_numpy(np.int64), g1["shi"].to_numpy(float), g1["slo"].to_numpy(float),
                       g1["tp"].to_numpy(float), g1["hold"].to_numpy(np.int64), V.COST, V.SLIP, n)
epx = D["o"][np.minimum(rows + 1, n - 1)]
fam = vals[offs[int(np.flatnonzero((K.ent == 55) & (K.ma == -99.0) & (K.chop == 99.0))[0])]: offs[int(np.flatnonzero((K.ent == 55) & (K.ma == -99.0) & (K.chop == 99.0))[0]) + 1]]
cel = vals[offs[int(np.flatnonzero((K.ent == 55) & (K.ma == 2.0) & (K.chop == 40.0))[0])]: offs[int(np.flatnonzero((K.ent == 55) & (K.ma == 2.0) & (K.chop == 40.0))[0]) + 1]]
print(f"family (Donchian-55 RTH, no filters) signal bars: {len(fam):,}; the cell's: {len(cel):,}")

# ---- features: the 37 audited columns need an e48-style dict ----
ix = pd.DatetimeIndex(D["ix"]); c, h, l, o, vol = D["c"], D["h"], D["l"], D["o"], D["v"]
sess = (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy()
ef = pd.Series(c).ewm(span=13, adjust=False).mean().to_numpy(); es = pd.Series(c).ewm(span=48, adjust=False).mean().to_numpy()
tp_ = (h + l + c) / 3; dd = pd.DataFrame({"pv": np.where(rth, tp_ * vol, 0.0), "v": np.where(rth, vol, 0.0), "s": sess}); g = dd.groupby("s", sort=False)
vwap = (g["pv"].cumsum() / g["v"].cumsum().replace(0, np.nan)).to_numpy(); vwap[~rth] = np.nan
De = dict(o=o, h=h, l=l, c=c, v=vol, atr=D["atr"], ef=ef, es=es, vwap=vwap, mod=D["mod"], sess=sess, n=n)
Fe = EF.build(De); Fe = Fe.loc[:, Fe.notna().mean() >= 0.98]
X_all = np.column_stack([Fe.to_numpy(float), D["d_ma"], D["chop"], D["vpct"]]); fnames = list(Fe.columns) + ["v61.d_ma", "v61.chop", "v61.vpct"]
print(f"features: {X_all.shape[1]}  ({time.time()-t0:.0f}s)")

# ---- the training universe: every family signal bar with a finite label ----
sb_f = rows[fam]; y_f = R[fam, 0]; xb_f = xb[fam, 0]
ok_f = np.isfinite(y_f) & (xb_f > 0) & np.isfinite(X_all[sb_f]).all(1)
sb_f, y_f, xb_f = sb_f[ok_f], y_f[ok_f], xb_f[ok_f]; X_f = X_all[sb_f]
# uniqueness weights: 1 / mean number of family labels open over the label's own life
opencnt = np.zeros(n + 2); np.add.at(opencnt, sb_f + 1, 1); np.add.at(opencnt, xb_f + 1, -1); opencnt = np.cumsum(opencnt)[:n]
w_f = np.array([1.0 / max(1.0, opencnt[s:x + 1].mean()) for s, x in zip(sb_f, xb_f)])
print(f"training universe: {len(y_f):,} labelled family bars, mean concurrency {1/w_f.mean():.1f}, research {int((sb_f < CUT).sum()):,}")

# ---- the cell's position-locked trades (the thing being improved) ----
def lock(idx_list, mask=None):
    free = -1; out = []
    for j, kk in enumerate(idx_list):
        if (mask is not None and not mask[j]) or xb[kk, 0] < 0 or not np.isfinite(R[kk, 0]) or rows[kk] <= free: continue
        free = xb[kk, 0]; out.append((int(rows[kk]), int(xb[kk, 0]), float(R[kk, 0]), 100 * float(pts[kk, 0]) / epx[kk]))
    return pd.DataFrame(out, columns=["sig", "xb", "R", "pct"])
T = lock(cel); T["res"] = T.sig < CUT
def st(t):
    p = t.pct.to_numpy()
    if len(p) < 3: return dict(n=len(p), pf=np.nan, pct=np.nan, tot=np.nan, sharpe=np.nan)
    return dict(n=len(p), pf=p[p > 0].sum() / max(1e-9, -p[p <= 0].sum()), pct=p.mean(), tot=p.sum())
def fmt(s): return f"n {s['n']:>4} PF {s['pf']:6.3f} {s['pct']:+.4f}%/tr total {s['tot']:+6.2f}%"
line("THE CELL, unfiltered: research / locked")
print("  " + fmt(st(T[T.res])) + "  |  " + fmt(st(T[~T.res])))

# ---- models ----
def fit_models(Xtr, ytr, wtr, seed):
    out = {}
    if HAVE_LGB:
        prm = dict(n_estimators=300, learning_rate=0.03, num_leaves=7, min_child_samples=40, subsample=0.8, subsample_freq=1,
                   colsample_bytree=0.6, reg_lambda=5.0, verbose=-1, random_state=seed)
        out["q50"] = lgb.LGBMRegressor(objective="quantile", alpha=0.5, **prm).fit(Xtr, ytr, sample_weight=wtr)
        out["q10"] = lgb.LGBMRegressor(objective="quantile", alpha=0.10, **prm).fit(Xtr, ytr, sample_weight=wtr)
        out["q90"] = lgb.LGBMRegressor(objective="quantile", alpha=0.90, **prm).fit(Xtr, ytr, sample_weight=wtr)
    else:
        prm = dict(n_estimators=300, learning_rate=0.03, max_depth=3, min_samples_leaf=40, subsample=0.8, random_state=seed)
        out["q50"] = GradientBoostingRegressor(loss="quantile", alpha=0.5, **prm).fit(Xtr, ytr, sample_weight=wtr)
        out["q10"] = GradientBoostingRegressor(loss="quantile", alpha=0.10, **prm).fit(Xtr, ytr, sample_weight=wtr)
        out["q90"] = GradientBoostingRegressor(loss="quantile", alpha=0.90, **prm).fit(Xtr, ytr, sample_weight=wtr)
    out["rf"] = RandomForestRegressor(n_estimators=400, max_depth=4, min_samples_leaf=50, max_features=0.4, random_state=seed, n_jobs=2).fit(Xtr, ytr, sample_weight=wtr)
    return out
def cqr(models, Xcal, ycal, Xte, alpha=0.10):
    """split-conformal on the quantile pair: lower = q10 - Q, upper = q90 + Q, Q the (1-alpha) quantile
    of max(q10 - y, y - q90) on the calibration set. Coverage >= 1 - alpha, distribution-free."""
    lo_c, hi_c = models["q10"].predict(Xcal), models["q90"].predict(Xcal)
    sc = np.maximum(lo_c - ycal, ycal - hi_c); k = int(np.ceil((len(sc) + 1) * (1 - alpha))) - 1
    Q = np.sort(sc)[min(max(k, 0), len(sc) - 1)]
    return models["q10"].predict(Xte) - Q, models["q90"].predict(Xte) + Q, Q

# ---- purged, embargoed sequential folds over the FAMILY research bars; scored on the CELL's research trades ----
line("RESEARCH -- purged/embargoed folds; models trained on the family, scored on the cell's own trades")
res_f = sb_f < CUT; ridx = np.flatnonzero(res_f); folds = 6
fold_f = np.minimum((np.arange(len(ridx)) * folds) // len(ridx), folds - 1)
cell_res = T[T.res].reset_index(drop=True); cs = cell_res.sig.to_numpy()
pred = {k: np.full(len(cell_res), np.nan) for k in ("q50", "rf", "lo", "hi", "q50_sh", "rf_sh", "lo_sh")}
EMB = 30
rng = np.random.default_rng(3)
for f in range(folds):
    te_bars = ridx[fold_f == f]; first, last = sb_f[te_bars].min(), sb_f[te_bars].max()
    trn = ridx[(fold_f != f) & (xb_f[ridx] < first - EMB) | ((fold_f != f) & (sb_f[ridx] > last + EMB))]
    trn = trn[(xb_f[trn] < first - EMB) | (sb_f[trn] > last + EMB)]
    if len(trn) < 200: continue
    # calibration = the last 30% of the training bars in time
    order = trn[np.argsort(sb_f[trn])]; ncal = max(60, len(order) // 3); cal, fit = order[-ncal:], order[:-ncal]
    M = fit_models(X_f[fit], y_f[fit], w_f[fit], f)
    ysh = rng.permutation(y_f[fit]); Msh = fit_models(X_f[fit], ysh, w_f[fit], f + 50)
    cmask = (cs >= first) & (cs <= last)
    if cmask.sum() == 0: continue
    Xc = X_all[cs[cmask]]
    pred["q50"][cmask] = M["q50"].predict(Xc); pred["rf"][cmask] = M["rf"].predict(Xc)
    lo, hi, Q = cqr(M, X_f[cal], y_f[cal], Xc); pred["lo"][cmask], pred["hi"][cmask] = lo, hi
    pred["q50_sh"][cmask] = Msh["q50"].predict(Xc); pred["rf_sh"][cmask] = Msh["rf"].predict(Xc)
    losh, _, _ = cqr(Msh, X_f[cal], rng.permutation(y_f[cal]), Xc); pred["lo_sh"][cmask] = losh
    # coverage check on the cell's trades in this fold
    yc = cell_res.R.to_numpy()[cmask]
    print(f"  fold {f}: fit {len(fit):>5} cal {ncal:>4} -> cell trades {int(cmask.sum()):>3}   CQR Q {Q:+.2f}  coverage {np.mean((yc >= lo) & (yc <= hi)):.2f} (target 0.90)   ({time.time()-t0:.0f}s)", flush=True)
ok = np.isfinite(pred["q50"]); yc = cell_res.R.to_numpy()
ic = lambda a: np.corrcoef(a[ok], yc[ok])[0, 1]
print(f"\n  OOF IC on the cell's research trades: q50 {ic(pred['q50']):+.3f} (twin {ic(pred['q50_sh']):+.3f})   RF {ic(pred['rf']):+.3f} (twin {ic(pred['rf_sh']):+.3f})   CQR lower {ic(pred['lo']):+.3f} (twin {ic(pred['lo_sh']):+.3f})")
def sub(mask):
    return st(cell_res[mask])
def null_sub(k, ndraw=400):
    out = []
    for _ in range(ndraw):
        m = np.zeros(len(cell_res), bool); m[rng.choice(np.flatnonzero(ok), size=k, replace=False)] = True; out.append(sub(m)["pf"])
    return np.array(out)
base = sub(ok); print(f"  scored: {fmt(base)}")
print(f"  {'rule':40s} {'research (cell trades)':>44s} | {'random subset':>22s} | shuffled twin")
rules = [("CQR lower bound > 0  (no research cut)", pred["lo"] > 0, pred["lo_sh"] > 0),
         ("CQR lower bound > -1 R", pred["lo"] > -1, pred["lo_sh"] > -1),
         ("q50 (median R) > 0", pred["q50"] > 0, pred["q50_sh"] > 0),
         ("q50 top 60%", pred["q50"] >= np.nanquantile(pred["q50"][ok], .4), pred["q50_sh"] >= np.nanquantile(pred["q50_sh"][ok], .4)),
         ("RF top 60%", pred["rf"] >= np.nanquantile(pred["rf"][ok], .4), pred["rf_sh"] >= np.nanquantile(pred["rf_sh"][ok], .4)),
         ("RF > 0", pred["rf"] > 0, pred["rf_sh"] > 0)]
for nm, m, ms in rules:
    m = m & ok; ms = ms & ok; s = sub(m); ss = sub(ms)
    nf = null_sub(int(m.sum())) if m.sum() >= 3 else np.array([np.nan])
    print(f"  {nm:40s} {fmt(s)} | median PF {np.nanmedian(nf):.3f} p {np.mean(nf >= s['pf']):.3f} | PF {ss['pf']:.3f} n {ss['n']}")
# sizing overlay: size proportional to clipped predicted median (fractional Kelly-like), same trades
# the predicted median is negative on every trade (a 23% win rate), so size by RANK of q50, 0.5x..1.5x
rk = pd.Series(pred["q50"]).rank(pct=True).to_numpy(); sz = 0.5 + rk
p = cell_res.pct.to_numpy(); flat, sized = p[ok], (p * sz)[ok]
def shp(x): d = pd.Series(x).groupby(cell_res.sig.to_numpy()[ok] // 26).sum(); return np.sqrt(252) * d.mean() / d.std() if d.std() > 0 else np.nan
print(f"\n  sizing overlay (size = clipped q50 / its mean, same trades): flat total {flat.sum():+.2f}% Sharpe-ish {shp(flat):.2f}  |  sized total {sized.sum():+.2f}% Sharpe-ish {shp(sized):.2f}")

# ---- ONE locked read per model, pre-declared: fit on ALL research family bars (last 30% = calibration) ----
line("LOCKED -- one read, pre-declared: CQR lower bound > 0 at 90% coverage (needs no research threshold); RF > 0")
order = ridx[np.argsort(sb_f[ridx])]; ncal = len(order) // 3; cal, fit = order[-ncal:], order[:-ncal]
M = fit_models(X_f[fit], y_f[fit], w_f[fit], 7)
cell_lk = T[~T.res].reset_index(drop=True); Xl = X_all[cell_lk.sig.to_numpy()]
lo, hi, Q = cqr(M, X_f[cal], y_f[cal], Xl); yl = cell_lk.R.to_numpy()
print(f"  CQR Q {Q:+.2f}; locked coverage {np.mean((yl >= lo) & (yl <= hi)):.2f} (target 0.90); locked IC q50 {np.corrcoef(M['q50'].predict(Xl), yl)[0,1]:+.3f}  RF {np.corrcoef(M['rf'].predict(Xl), yl)[0,1]:+.3f}")
print("  base                    locked: " + fmt(st(cell_lk)))
print("  CQR lower bound > 0     locked: " + fmt(st(cell_lk[lo > 0])))
print("  CQR lower bound > -1 R  locked: " + fmt(st(cell_lk[lo > -1])))
print("  RF > 0                  locked: " + fmt(st(cell_lk[M['rf'].predict(Xl) > 0])))
# DESCRIPTIVE (a second read, not pre-declared): the research-block 'RF top 60%' cut applied to locked
rf_cut = np.nanquantile(pred["rf"][ok], .4); rl = M["rf"].predict(Xl)
print("  RF top 60% @ research cut locked (DESCRIPTIVE, second read): " + fmt(st(cell_lk[rl >= rf_cut])) + f"   (keeps {100*np.mean(rl >= rf_cut):.0f}% of locked trades)")
rk_l = pd.Series(rl).rank(pct=True).to_numpy(); pl = cell_lk.pct.to_numpy()
print(f"  sizing by RF rank on locked (0.5x..1.5x): flat total {pl.sum():+.2f}%  sized {(pl*(0.5+rk_l)).sum():+.2f}%  (descriptive)")
imp = pd.Series(M["rf"].feature_importances_, index=fnames).sort_values(ascending=False)
print("\n  RF top features: " + ", ".join(f"{k} {v:.3f}" for k, v in imp.head(8).items()))
print(f"\n  total runtime {time.time()-t0:.0f}s")
