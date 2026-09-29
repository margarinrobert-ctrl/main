"""GATE 2 -- incremental value, then ONE locked read, then deflation.

The screen in `run_feat1` produced a kept set. This file asks the only question that matters about
it: does scoring the primary's events with those features improve the UNSIZED per-event return, and
does each feature earn its place INCREMENTALLY?

  * PURGED + EMBARGOED cross-validation inside the research block. Events occupy [signal, exit] and
    those windows overlap, so a naive split leaks.
  * EVERY MODEL BESIDE A SHUFFLED-LABEL TWIN. `STUDY_V28` recorded the deepest net's shuffled twin
    earning MORE than any real model on the headline statistic -- which is how you learn the column
    is noise rather than that the model is good.
  * DROP-ONE for incremental value. A feature that does not move the score when removed is not
    contributing; it is decoration with a correlation.
  * The uplift is scored on UNSIZED returns, so no sizing rule can be mistaken for the finding, and
    against a SAME-SELECTIVITY RANDOM FILTER, so restrictiveness alone cannot produce it.
  * ONE read of the locked block, at the end, with the threshold taken from the research score
    distribution -- and the KEPT FRACTION reported, because a score that is not calibrated across
    the split makes any research threshold meaningless (STUDY_AUTOBNN kept 105 of 105).
"""
from __future__ import annotations

import os
import pickle
import sys
import time
import warnings

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "research/v61sess"))
sys.path.append("/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/mechanism-first-alpha/scripts")
from gates import meta_gate, deflated_sharpe, effective_trials, reality_check   # noqa: E402
from sklearn.linear_model import LogisticRegression, Ridge                      # noqa: E402
from sklearn.ensemble import RandomForestRegressor                              # noqa: E402
from sklearn.preprocessing import StandardScaler                                # noqa: E402
import lightgbm as lgb                                                          # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)
OUT = os.path.join(ROOT, "results/v61feat")


def line(t):
    print("\n" + "=" * 126)
    print(t)
    print("=" * 126, flush=True)


print(__doc__)
t0 = time.time()
rng = np.random.default_rng(2727)
FE = pd.read_parquet(os.path.join(OUT, "events_features.parquet"))
with open(os.path.join(OUT, "frozen.pkl"), "rb") as f:
    Z = pickle.load(f)
KEEP, PICKS, COLS = Z["keep"], Z["picks"], Z["cols"]
R = FE[FE.blk == 0].reset_index(drop=True)
L = FE[FE.blk == 1].reset_index(drop=True)
print(f"  research events {len(R)}, locked events {len(L)}")
print(f"  kept feature set ({len(KEEP)}): {', '.join(KEEP)}")


def purged_folds(n_, k=5, embargo=0.02):
    e = int(np.ceil(embargo * n_))
    bnd = np.linspace(0, n_, k + 1).astype(int)
    for i in range(k):
        a, b = bnd[i], bnd[i + 1]
        te = np.arange(a, b)
        tr = np.concatenate([np.arange(0, max(a - e, 0)), np.arange(min(b + e, n_), n_)])
        yield tr, te


def make(kind, seed=0):
    if kind == "ridge":
        return Ridge(alpha=5.0)
    if kind == "logit":
        return LogisticRegression(C=0.2, max_iter=2000)
    if kind == "rf":
        return RandomForestRegressor(n_estimators=400, max_depth=4, min_samples_leaf=25,
                                     max_features=0.5, random_state=seed, n_jobs=2)
    return lgb.LGBMRegressor(n_estimators=250, learning_rate=0.03, num_leaves=7, max_depth=3,
                             min_child_samples=30, subsample=0.8, subsample_freq=1,
                             colsample_bytree=0.7, reg_lambda=5.0, random_state=seed, verbose=-1)


def oof(Xa, ya, kind, seed=0, shuffle=False):
    n_ = len(ya)
    s = np.full(n_, np.nan)
    yy = np.random.default_rng(seed).permutation(ya) if shuffle else ya
    for tr, te in purged_folds(n_):
        if len(tr) < 40:
            continue
        m = make(kind, seed)
        if kind == "logit":
            yb = (yy > 0).astype(int)
            if len(np.unique(yb[tr])) < 2:
                continue
            sc = StandardScaler().fit(Xa[tr])
            m.fit(sc.transform(Xa[tr]), yb[tr])
            s[te] = m.predict_proba(sc.transform(Xa[te]))[:, 1]
        elif kind == "ridge":
            sc = StandardScaler().fit(Xa[tr])
            m.fit(sc.transform(Xa[tr]), yy[tr])
            s[te] = m.predict(sc.transform(Xa[te]))
        else:
            m.fit(Xa[tr], yy[tr])
            s[te] = m.predict(Xa[te])
    return s


yR = R.pct.to_numpy()
XR = R[KEEP].to_numpy(float)
line("MODELS -- purged + embargoed 5-fold on RESEARCH, each beside a SHUFFLED-LABEL TWIN")
print("  Objective is the event's own RETURN, not win/lose. STUDY_V28/V32 measured what a win/lose")
print("  objective does to a breakout system: it raises the win rate and CUTS p90 of R, which is")
print("  exactly the tail the system earns in.\n")
print(f"  {'model':8s} {'OOF IC':>9} {'twin IC':>9} {'OOF p90 R kept':>15} {'baseline p90':>13}")
SC = {}
for kind in ("ridge", "logit", "rf", "lgbm"):
    s = oof(XR, yR, kind, seed=0)
    st = oof(XR, yR, kind, seed=0, shuffle=True)
    m = np.isfinite(s)
    icv = float(pd.Series(s[m]).corr(pd.Series(yR[m]), method="spearman"))
    ict = float(pd.Series(st[m]).corr(pd.Series(yR[m]), method="spearman"))
    SC[kind] = s
    thr = np.quantile(s[m], 0.4)
    kept = yR[m][s[m] >= thr]
    print(f"  {kind:8s} {icv:>+9.4f} {ict:>+9.4f} {np.quantile(kept,0.9):>15.4f} "
          f"{np.quantile(yR,0.9):>13.4f}")

line("GATE 2 -- unsized uplift against a bootstrap, and against a SAME-SELECTIVITY RANDOM FILTER")
print("  Keep-fractions declared in advance: 80/70/60/50/40%.\n")
print(f"  {'model':8s} {'keep':>5} {'n':>4} {'base':>9} {'filtered':>9} {'uplift':>9} "
      f"{'95% CI':>22} {'boot p':>7} {'random-filter p':>16}")
KEEPF = (0.8, 0.7, 0.6, 0.5, 0.4)
g2 = []
for kind, s in SC.items():
    m = np.isfinite(s)
    r = yR[m] / 100.0
    sm = s[m]
    for kf in KEEPF:
        thr = float(np.quantile(sm, 1 - kf))
        gg = meta_gate(r, sm, thr)
        if "unsized_uplift" not in gg:
            continue
        keep = sm >= thr
        obs = r[keep].mean() - r.mean()
        draws = np.array([r[rng.choice(len(r), int(keep.sum()), replace=False)].mean() - r.mean()
                          for _ in range(600)])
        pctl = float(np.mean(draws >= obs))
        lo, hi = gg["unsized_uplift_ci95"]
        g2.append(dict(model=kind, keep=kf, n=gg["n_kept"], base=100 * gg["unsized_mean_unfiltered"],
                       filt=100 * gg["unsized_mean_filtered"], up=100 * gg["unsized_uplift"],
                       p=gg["bootstrap_p_one_sided"], p_ctl=pctl))
        print(f"  {kind:8s} {kf:>5.0%} {gg['n_kept']:>4} {100*gg['unsized_mean_unfiltered']:>9.4f} "
              f"{100*gg['unsized_mean_filtered']:>9.4f} {100*gg['unsized_uplift']:>+9.4f} "
              f"[{100*lo:>+8.4f},{100*hi:>+8.4f}] {gg['bootstrap_p_one_sided']:>7.3f} {pctl:>16.3f}")
G2 = pd.DataFrame(g2)
G2.to_csv(os.path.join(OUT, "gate2.csv"), index=False)
print(f"\n  cells clearing BOTH nulls at p<=0.10: {int(((G2.p<=0.10)&(G2.p_ctl<=0.10)).sum())} of {len(G2)}")

line("DROP-ONE -- does each kept feature earn its place INCREMENTALLY?")
best = G2.sort_values(["p_ctl", "p"]).iloc[0] if len(G2) else None
kind, kf = best["model"], float(best["keep"])
print(f"  measured at the best Gate-2 cell: {kind} at keep {kf:.0%}\n")
print(f"  {'feature set':30s} {'OOF IC':>9} {'uplift':>9} {'delta vs full':>14}")
s_full = SC[kind]
m = np.isfinite(s_full)
r = yR[m] / 100.0
thr = float(np.quantile(s_full[m], 1 - kf))
up_full = r[s_full[m] >= thr].mean() - r.mean()
ic_full = float(pd.Series(s_full[m]).corr(pd.Series(yR[m]), method="spearman"))
print(f"  {'ALL kept features':30s} {ic_full:>+9.4f} {100*up_full:>+9.4f} {'--':>14}")
d1 = []
for f_ in KEEP:
    sub = [c for c in KEEP if c != f_]
    s2 = oof(R[sub].to_numpy(float), yR, kind, seed=0)
    m2 = np.isfinite(s2)
    r2 = yR[m2] / 100.0
    thr2 = float(np.quantile(s2[m2], 1 - kf))
    up2 = r2[s2[m2] >= thr2].mean() - r2.mean()
    ic2 = float(pd.Series(s2[m2]).corr(pd.Series(yR[m2]), method="spearman"))
    d1.append(dict(dropped=f_, ic=ic2, up=100 * up2, delta=100 * (up2 - up_full)))
    print(f"  {'minus ' + f_:30s} {ic2:>+9.4f} {100*up2:>+9.4f} {100*(up2-up_full):>+14.4f}")
DR = pd.DataFrame(d1).sort_values("delta")
DR.to_csv(os.path.join(OUT, "dropone.csv"), index=False)
FINAL = [f for f in KEEP if float(DR[DR.dropped == f].delta.iloc[0]) < 0]
print(f"\n  features whose REMOVAL makes it worse (i.e. they contribute): {len(FINAL)} of {len(KEEP)}")
print(f"  features whose removal makes it BETTER (drop them): "
      f"{[f for f in KEEP if f not in FINAL]}")

line("THE FINAL SET, refitted, and ONE READ OF THE LOCKED BLOCK")
if len(FINAL) < 2:
    FINAL = KEEP
    print("  fewer than two features contributed; the locked read uses the full kept set.\n")
print(f"  final set ({len(FINAL)}): {', '.join(FINAL)}\n")
mdl = make(kind, 0)
XF = R[FINAL].to_numpy(float)
if kind == "logit":
    sc = StandardScaler().fit(XF); mdl.fit(sc.transform(XF), (yR > 0).astype(int))
    sR = mdl.predict_proba(sc.transform(XF))[:, 1]
    sL = mdl.predict_proba(sc.transform(L[FINAL].to_numpy(float)))[:, 1]
elif kind == "ridge":
    sc = StandardScaler().fit(XF); mdl.fit(sc.transform(XF), yR)
    sR = mdl.predict(sc.transform(XF)); sL = mdl.predict(sc.transform(L[FINAL].to_numpy(float)))
else:
    mdl.fit(XF, yR)
    sR = mdl.predict(XF); sL = mdl.predict(L[FINAL].to_numpy(float))
thrL = float(np.quantile(sR, 1 - kf))
keepL = sL >= thrL
yL = L.pct.to_numpy()
print(f"  {'arm':30s} {'n':>4} {'%/event':>10} {'PF':>7} {'total %':>9}")
for nm, sel in (("locked, unfiltered", np.ones(len(yL), bool)), ("locked + the meta filter", keepL)):
    z = L[sel]
    if len(z) < 10:
        print(f"  {nm:30s} {len(z):>4}   (too few)"); continue
    p = z.pct.to_numpy()          # percent of entry price; PF in the same unit
    print(f"  {nm:30s} {len(z):>4} {z.pct.mean():>10.4f} "
          f"{p[p>0].sum()/max(-p[p<0].sum(),1e-9):>7.3f} {z.pct.sum():>9.2f}")
if keepL.sum() >= 10:
    obs = yL[keepL].mean() - yL.mean()
    draws = np.array([yL[rng.choice(len(yL), int(keepL.sum()), replace=False)].mean() - yL.mean()
                      for _ in range(3000)])
    print(f"  uplift {obs:+.4f} %/event;  random filter of the same size: median "
          f"{np.median(draws):+.4f}, p {np.mean(draws >= obs):.3f}")
    print(f"  kept on locked {100*keepL.mean():.0f}% against the {100*kf:.0f}% the threshold was set "
          f"for -- if these differ the score is NOT calibrated across the split")

line("DEFLATION -- every look counted")
TR = dict(features_screened=len(COLS), ic_tests=len(COLS), models=4,
          keep_fractions=len(KEEPF) * 4, dropone=len(KEEP), primaries=2)
tot = sum(TR.values())
for k_, v_ in TR.items():
    print(f"  {k_:22s} {v_:>5}")
print(f"  {'TOTAL':22s} {tot:>5}")
eff = effective_trials(tot, 0.5)
rr = yL[keepL] / 100.0 if keepL.sum() >= 10 else yL / 100.0
sr = float(rr.mean() / rr.std()) if rr.std() > 0 else 0.0
var_tr = float(np.var((G2.up.to_numpy() / 100.0))) if len(G2) else 1e-6
ic_sd = float(np.std(pd.read_csv(os.path.join(OUT, "ic.csv")).ic.to_numpy()))
ds = deflated_sharpe(sr, len(rr), n_trials=int(round(eff)), var_trials=max(ic_sd ** 2, 1e-8))
print(f"\n  effective trials at rho 0.5: {eff:.0f} of {tot}")
print(f"  locked Sharpe per event {sr:.4f} on {len(rr)} events")
print(f"  DEFLATED SHARPE {ds['dsr']:.4f}  (expected max under the null {ds['expected_max_sr_under_null']:.4f})")
print("  var_trials here is the variance of the 51 feature ICs -- the population the screen actually")
print("  searched. Stating what it is measured over is the point; the same input estimated two other")
print("  ways gave 0.571 and 0.9919 on earlier studies, both wrong.")
cands = {}
for kind_, s in SC.items():
    m = np.isfinite(s); r_ = yR[m] / 100.0
    for kf_ in KEEPF:
        thr_ = float(np.quantile(s[m], 1 - kf_))
        cands[f"{kind_}@{kf_:.0%}"] = np.where(s[m] >= thr_, r_, 0.0)
rc = reality_check(np.column_stack(list(cands.values())))
print(f"\n  White's reality check over {len(cands)} candidates: best {list(cands)[rc['best_candidate']]}, "
      f"p {rc['reality_check_p']:.3f}")
print(f"  {rc['verdict']}")
print(f"\n  runtime {time.time()-t0:.0f}s")
