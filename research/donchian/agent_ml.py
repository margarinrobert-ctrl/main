"""AGENT 6 - MACHINE LEARNING QUANT.

ML is allowed ONLY as an enhancement to the Donchian breakout system: rank
breakout QUALITY, predict continuation vs failure, and filter the weak ones out.
It may never simply memorise history.

Guards, all mandatory:
  * every feature is read at the SIGNAL bar from bars <= i
  * PURGED K-fold with an EMBARGO - trades overlap in time (a 16-bar hold spans
    other trades' signal bars), so plain K-fold leaks. Purge removes training
    trades whose holding period overlaps a test trade; the embargo drops a
    further band after each test fold.
  * the model is fit ONLY inside training folds; the out-of-fold prediction is
    the only thing ever scored
  * the filtered book is compared against BOTH the matched control AND a random
    filter of identical selectivity - a model that merely trades less is not a
    model
  * research block only; the locked block is never touched
"""
import numpy as np, pandas as pd
from engine import donchian, atr, ema, true_range
from strategy import run
import lab

SYM = "NAS"
df, w, res = lab.research(SYM)
n = len(df)
c, h, l, o = df.close.values, df.high.values, df.low.values, df.open.values
tv = df.tickvol.values.astype(float)
tod = df.tod.values; sess = df.sess.values
a14 = atr(df, 14)

print("="*104)
print("AGENT 6 - MACHINE LEARNING QUANT   (breakout-quality filter, purged CV)")
print("="*104)

# ------------------------------------------------------------------ features
def zscore(x, n_):
    s = pd.Series(x)
    return ((s - s.rolling(n_).mean()) / (s.rolling(n_).std() + 1e-9)).shift(1).values

def pctile(x, n_):
    s = pd.Series(x)
    return s.rolling(n_).apply(lambda v: (v[:-1] < v[-1]).mean(), raw=True).shift(1).values

F = {}
rng_ = h - l
body = c - o
F["body_frac"]   = np.where(rng_ > 0, body / (rng_ + 1e-9), 0.0)
F["close_pos"]   = np.where(rng_ > 0, (c - l) / (rng_ + 1e-9), 0.5)
F["upper_wick"]  = np.where(rng_ > 0, (h - np.maximum(o, c)) / (rng_ + 1e-9), 0.0)
F["lower_wick"]  = np.where(rng_ > 0, (np.minimum(o, c) - l) / (rng_ + 1e-9), 0.0)
F["rng_atr"]     = rng_ / (a14 + 1e-9)
F["atr_pct250"]  = pctile(a14, 250)
F["atr_slope"]   = a14 / (pd.Series(a14).shift(8).values + 1e-9) - 1.0
for k in (1, 2, 4, 8, 16):
    F[f"ret{k}_atr"] = (c - pd.Series(c).shift(k).values) / (a14 + 1e-9)
for L in (10, 20, 40):
    hi_, lo_ = donchian(df, L)
    F[f"dwidth{L}_atr"] = (hi_ - lo_) / (a14 + 1e-9)
    F[f"dslope{L}"] = (hi_ - pd.Series(hi_).shift(8).values) / (a14 + 1e-9)
    F[f"break_dist{L}"] = np.where(c > hi_, (c - hi_) / (a14 + 1e-9),
                           np.where(c < lo_, (lo_ - c) / (a14 + 1e-9), 0.0))
for N in (20, 50, 200):
    e = ema(c, N)
    F[f"ema{N}_dist_atr"] = (c - e) / (a14 + 1e-9)
    F[f"ema{N}_slope"] = (e - pd.Series(e).shift(8).values) / (a14 + 1e-9)
F["tv_z100"]     = zscore(tv, 100)
F["tv_ratio"]    = tv / (pd.Series(tv).rolling(20).mean().shift(1).values + 1e-9)
F["tod"]         = tod.astype(float)
F["sess_elapsed"]= (tod - 420) / 240.0
# causal higher-timeframe (60m) trend: last COMPLETED 60m bar only
c60 = pd.Series(c).groupby(np.arange(n) // 4).transform("last").shift(4).values
F["htf_ret"]     = (c - c60) / (a14 + 1e-9)

FEATS = sorted(F.keys())
X_all = np.column_stack([F[k] for k in FEATS])
print(f"  {len(FEATS)} causal features built")

# ---------------------------------------------------------------- the trades
N_ENTRY, SM, TM, MH = 20, 1.5, 2.0, 16
tr = run(df, w, n_entry=N_ENTRY, stop_mult=SM, targ_mult=TM, max_hold=MH,
         cost_pts=lab.COST[SYM], slip_pts=lab.SLIP[SYM], one_per_session=False)
tr = tr[np.isin(tr.sig_bar, np.where(res)[0])].reset_index(drop=True)
sb = tr.sig_bar.values
good = ~np.isnan(X_all[sb]).any(1)
tr, sb = tr[good].reset_index(drop=True), sb[good]
X, y = X_all[sb], (tr.net.values > 0).astype(int)
hold = tr.bars.values
print(f"  {len(tr):,} research-block triggers (all triggers, not one-per-session)")
print(f"  base rate (net>0): {y.mean():.3f}   mean net: {tr.net.mean():+.2f} pts")

# ------------------------------------------------- purged K-fold with embargo
def purged_folds(sig, hold_, K=6, embargo=32):
    order = np.argsort(sig); idx = np.arange(len(sig))
    folds = np.array_split(order, K)
    out = []
    for k in range(K):
        te = folds[k]
        te_lo, te_hi = sig[te].min(), sig[te].max() + hold_[te].max()
        # purge: drop training trades whose [signal, signal+hold] overlaps the
        # test span, plus an embargo band on both sides
        tr_mask = np.ones(len(sig), bool); tr_mask[te] = False
        overlap = (sig + hold_ >= te_lo - embargo) & (sig <= te_hi + embargo)
        tr_mask &= ~overlap
        out.append((idx[tr_mask], te))
    return out

folds = purged_folds(sb, hold, K=6, embargo=32)
print(f"  purged 6-fold + 32-bar embargo: train sizes "
      f"{[len(a) for a, _ in folds]}, test sizes {[len(b) for _, b in folds]}")

import lightgbm as lgb
oof = np.full(len(y), np.nan)
imps = np.zeros(len(FEATS))
for tr_i, te_i in folds:
    if len(tr_i) < 200: continue
    m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.03, num_leaves=15,
                           min_child_samples=60, subsample=0.8, colsample_bytree=0.7,
                           reg_lambda=5.0, verbose=-1, random_state=0)
    m.fit(X[tr_i], y[tr_i])
    oof[te_i] = m.predict_proba(X[te_i])[:, 1]
    imps += m.feature_importances_
ok = ~np.isnan(oof)
print(f"\n  out-of-fold predictions: {ok.sum():,}")
from sklearn.metrics import roc_auc_score
auc = roc_auc_score(y[ok], oof[ok])
print(f"  OUT-OF-FOLD AUC        : {auc:.4f}   (0.500 = no skill)")

top = np.argsort(-imps)[:10]
print("  top features by split gain: " + ", ".join(FEATS[i] for i in top))

# ------------------------------------------------------- does it earn money?
print("\n  Filtering triggers by the model's out-of-fold score, then re-simulating.")
print(f"  {'keep top':>9} {'n':>6} {'exp':>8} {'ctrl':>8} {'excess':>8} {'z':>7} {'p':>7}   {'rand-filter p':>13}")
rng = np.random.default_rng(0)
side_all = tr.side.values
for q in (0.9, 0.75, 0.5, 0.25, 0.1):
    thr = np.nanquantile(oof[ok], 1 - q)
    sel = ok & (oof >= thr)
    if sel.sum() < 60: continue
    idx_s, side_s = sb[sel], side_all[sel]
    g, _ = lab.sig_gate(SYM, idx_s, side_s, stop_mult=SM, targ_mult=TM, max_hold=MH,
                        one_per_session=True, n_draws=250, quiet=True)
    # random filter of identical selectivity
    reals, keep_n = [], int(sel.sum())
    for d in range(300):
        pick = rng.choice(np.where(ok)[0], size=keep_n, replace=False)
        b = lab.book(SYM, sb[pick], side_all[pick], stop_mult=SM, targ_mult=TM,
                     max_hold=MH, one_per_session=True)
        b = b[np.isin(b.sig_bar, np.where(res)[0])]
        if len(b): reals.append(b.net.mean())
    reals = np.array(reals)
    pr = float((reals >= g["exp"]).mean()) if len(reals) else np.nan
    print(f"  {q:>9.0%} {g['n']:>6,} {g['exp']:>+8.2f} {g['ctrl']:>+8.2f} "
          f"{g['excess']:>+8.2f} {g['z']:>+7.2f} {g['p']:>7.4f}   {pr:>13.4f}")

print("\n" + "="*104)
print("  READING: AUC near 0.500 means the model cannot rank breakout quality.")
print("  A filter must beat BOTH the matched control (p) and a random filter of the")
print("  same selectivity (rand-filter p). Failing either is a null result.")
