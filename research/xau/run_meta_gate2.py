"""PHASE 3 + PHASE 4 + PHASE 5. The meta layer over the V38 primary, GATE 2, and the deflation.

THE PRIMARY. Donchian 70 entry / 30 exit, 2.5 ATR stop, no target, long only, 30-minute bars --
the V38 geometry, FROZEN on other markets and never fitted on gold. Among the five frozen
geometries it is the only LONG cell that is not negative on block A (+0.00061 %/event), which is
how it was chosen: block A is the designated primary-fitting block, so choosing here keeps block B
clean for the meta layer, per the architecture's rule that the primary must be fitted on data the
meta layer does not see.

>>> GATE 1 ALREADY FAILED. On block B this primary reads +0.02766 %/event at p 0.211 (MARGINAL);
>>> across five geometries x three sides, 0 of 15 cells cleared p<=0.10 on block A and 0 of 15 on
>>> block B. The architecture's instruction at that point is to stop. The meta layer is built anyway
>>> because it was asked for, and because a completed Gate 2 on a failed Gate 1 is itself worth
>>> recording -- but NOTHING it returns can be read as rescuing the primary. That is precisely the
>>> claim the two-gate structure exists to make impossible.

THE META LAYER. Features live here and nowhere else. Trained INSIDE block B with purged, embargoed
K-fold cross-validation, every model run beside a SHUFFLED-LABEL TWIN, and scored on UNSIZED
per-event returns. Fracdiff and the HMM enter as features only; neither ever emits a signal.
"""
import os, sys, time, warnings, numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/xau"):
    sys.path.insert(0, os.path.join(ROOT, p))
sys.path.append("/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/mechanism-first-alpha/scripts")
import xau_core as X
import xau_meta as M
from gates import primary_gate, meta_gate, deflated_sharpe, effective_trials, reality_check
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb
warnings.filterwarnings("ignore"); pd.set_option("display.width", 220)
def line(t): print("\n" + "=" * 122 + f"\n{t}\n" + "=" * 122, flush=True)
OUT = os.path.join(ROOT, "results/xau"); os.makedirs(OUT, exist_ok=True)
print(__doc__)
t0 = time.time()

PRIM = dict(tf=30, ent=70, exN=30, stop=2.5, tp=0.0, hold=480, side=1)


def build30():
    f = X.load()
    g = f.resample("30min").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    o, h, l, c, v = (g[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    ix = pd.DatetimeIndex(g.index); n = len(c)
    d = dict(n=n, o=o, h=h, l=l, c=c, v=v, ix=ix, atr=X._atr(h, l, c),
             mod=(ix.hour * 60 + ix.minute).to_numpy(), day=(ix.year * 10000 + ix.month * 100 + ix.day).to_numpy())
    sh, sl = pd.Series(h), pd.Series(l)
    d["ent_hi"] = np.vstack([sh.rolling(k).max().shift(1).to_numpy() for k in range(2, 121)])
    d["ent_lo"] = np.vstack([sl.rolling(k).min().shift(1).to_numpy() for k in range(2, 121)])
    d["ex_lo"] = np.vstack([sl.rolling(k).min().shift(1).to_numpy() for k in range(2, 81)])
    d["ex_hi"] = np.vstack([sh.rolling(k).max().shift(1).to_numpy() for k in range(2, 81)])
    d["blk"] = np.full(n, -1, np.int64)
    for i, (nm, (a, b)) in enumerate(X.BLOCKS.items()):
        d["blk"][(ix >= a) & (ix <= b)] = i
    d["last_bar"] = n - 500
    return d


D = build30()
E = X.run(D, PRIM)
line("THE PRIMARY'S EVENT STREAM (unchanged, unfiltered, unsized)")
for i, nm in enumerate(X.BLOCKS):
    e = E[E.blk == i]
    r = primary_gate(e.pct.to_numpy() / 100.0)
    print(f"  {nm:10s} n {len(e):>4}   net {e.pct.mean():+.5f} %/event   p {r['bootstrap_p_one_sided']:.3f}   "
          f"hit {100*r['hit_rate']:.1f}%   {r['verdict'].split('--')[0].strip()}")

line("PHASE 3 -- FRACDIFF ORDER, chosen by ADF on BLOCK A ONLY")
mA = D["blk"] == 0
d_pick, dtab = M.choose_d(np.log(D["c"]), mA)
print(dtab.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
print(f"\n  chosen d = {d_pick}  (smallest on the ladder clearing the 5% MacKinnon value on block A)")

line("PHASE 3 -- HMM, Baum-Welch on BLOCK A ONLY, FILTERED posteriors everywhere")
hp = M.hmm_fit(D, mA, K=3, seed=0)
o_ = hp["order"]
print(f"  states ordered by drift (bear, side, bull):")
for k, s in zip(o_, ("bear", "side", "bull")):
    print(f"    {s:5s} mean 30m log-return x100 {hp['mu'][k,0]:+8.5f}   mean rv48 {hp['mu'][k,1]:8.5f}   "
          f"self-transition {hp['A'][k,k]:.4f}")
print(f"  log-likelihood {hp['ll']:.1f};  K=3 is one hyperparameter and is counted as a trial")

FROZEN = dict(d=d_pick, d_table=dtab, hmm=hp)
XF, meta = M.build_features(D, frozen=FROZEN, want_smoothed=True)
print(f"  fracdiff fixed window {meta['ffd_window']} bars;  {XF.shape[1]} features built")

line("LEAKAGE CHECKS")
bad, checked, nprobe = M.audit(D, XF, FROZEN, probes=60, seed=1)
print(f"  truncation audit: {len(bad)} mismatches over {checked:,} value comparisons on {nprobe} probe bars")
for b in bad[:8]:
    print(f"    bar {b[0]}  {b[1]}  full {b[2]:.6f}  truncated {b[3]:.6f}")
sm = meta["smoothed"]
fl = np.column_stack([XF.hmm_bear, XF.hmm_side, XF.hmm_bull])
ag = float(np.mean(np.argmax(fl, 1) == np.argmax(sm, 1)))
print(f"  filtered vs SMOOTHED HMM state agreement {100*ag:.1f}% -- the smoothed version reads the future")
print(f"  and is computed here only to show the two are NOT the same labelling (STUDY_V27: identical")
print(f"  trade counts, locked PF 1.351 smoothed against 0.973 causal).")

# ---------------------------------------------------------------- events x features
sig = E.sig.to_numpy()
FE = XF.iloc[sig].reset_index(drop=True)
FE["blk"] = E.blk.to_numpy(); FE["pct"] = E.pct.to_numpy(); FE["R"] = E.R.to_numpy()
FE["ts"] = E.ts.to_numpy(); FE["exit_bar"] = E.exit_bar.to_numpy(); FE["sig"] = sig
COLS = [c for c in XF.columns]
FE = FE.replace([np.inf, -np.inf], np.nan)
ok = FE[COLS].notna().all(axis=1)
print(f"\n  events with a complete feature row: {int(ok.sum())} of {len(FE)}")
FE = FE[ok].reset_index(drop=True)


def purged_folds(n_, k=5, embargo=0.02):
    """Purged + embargoed K-fold over the event sequence. Events do not overlap here (one position
    at a time), so uniqueness is 1 by construction and the purge is the embargo alone -- but it is
    applied anyway because the FEATURES at neighbouring signal bars share rolling windows."""
    e = int(np.ceil(embargo * n_))
    bnd = np.linspace(0, n_, k + 1).astype(int)
    for i in range(k):
        a, b = bnd[i], bnd[i + 1]
        te = np.arange(a, b)
        tr = np.concatenate([np.arange(0, max(a - e, 0)), np.arange(min(b + e, n_), n_)])
        yield tr, te


def oof(Xtr, y, w, model, seed=0, shuffle=False):
    n_ = len(y); s = np.full(n_, np.nan)
    rng = np.random.default_rng(seed)
    yy = rng.permutation(y) if shuffle else y
    for tr, te in purged_folds(n_):
        if len(tr) < 40 or len(np.unique(yy[tr])) < 2:
            continue
        m = make(model, seed)
        if model == "logit":
            sc = StandardScaler().fit(Xtr[tr])
            m.fit(sc.transform(Xtr[tr]), yy[tr], sample_weight=w[tr])
            s[te] = m.predict_proba(sc.transform(Xtr[te]))[:, 1]
        else:
            m.fit(Xtr[tr], yy[tr], sample_weight=w[tr])
            s[te] = m.predict_proba(Xtr[te])[:, 1]
    return s


def make(model, seed):
    if model == "logit":
        return LogisticRegression(C=0.2, max_iter=2000)
    if model == "rf":
        return RandomForestClassifier(n_estimators=400, max_depth=4, min_samples_leaf=25,
                                      max_features=0.4, random_state=seed, n_jobs=2)
    return lgb.LGBMClassifier(n_estimators=250, learning_rate=0.03, num_leaves=7, max_depth=3,
                              min_child_samples=30, subsample=0.8, subsample_freq=1,
                              colsample_bytree=0.6, reg_lambda=5.0, random_state=seed, verbose=-1)


B = FE[FE.blk == 1].reset_index(drop=True)
Xb = B[COLS].to_numpy(float); yb = (B.pct.to_numpy() > 0).astype(int); wb = np.ones(len(B))
line(f"PHASE 3 -- META MODELS on BLOCK B only ({len(B)} events), purged + embargoed 5-fold, each beside a SHUFFLED TWIN")
print(f"  {'model':10s} {'OOF AUC':>9} {'twin AUC':>9} {'OOF IC':>9} {'twin IC':>9}   (IC = Spearman of score vs %/event)")


def auc(y, s):
    m = np.isfinite(s)
    y, s = y[m], s[m]
    r = pd.Series(s).rank().to_numpy(); n1 = y.sum(); n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else np.nan


SC = {}
for mdl in ("logit", "rf", "lgbm"):
    s = oof(Xb, yb, wb, mdl, seed=0)
    st = oof(Xb, yb, wb, mdl, seed=0, shuffle=True)
    m = np.isfinite(s)
    ic = float(pd.Series(s[m]).corr(pd.Series(B.pct.to_numpy()[m]), method="spearman"))
    ict = float(pd.Series(st[m]).corr(pd.Series(B.pct.to_numpy()[m]), method="spearman"))
    SC[mdl] = s
    print(f"  {mdl:10s} {auc(yb,s):>9.4f} {auc(yb,st):>9.4f} {ic:>9.4f} {ict:>9.4f}")

line("GATE 2 -- does the meta layer improve UNSIZED per-event return? Sizing is reported, never credited")
print("  Thresholds are DECLARED as keep-fractions of the OOF score, not tuned: 80/70/60/50/40/30%.\n")
print(f"  {'model':8s} {'keep':>5} {'n':>5} {'base %/ev':>10} {'filtered':>10} {'uplift':>9} {'95% CI':>22} {'p':>7} {'sized':>9}  verdict")
KEEP = (0.8, 0.7, 0.6, 0.5, 0.4, 0.3)
g2rows = []
for mdl, s in SC.items():
    m = np.isfinite(s)
    r = B.pct.to_numpy()[m] / 100.0
    sm_ = s[m]
    sz = np.clip(sm_ / max(np.nanmean(sm_), 1e-9), 0.25, 3.0)      # confidence sizing, reported only
    for k in KEEP:
        thr = float(np.quantile(sm_, 1 - k))
        g = meta_gate(r, sm_, thr, sizes=sz)
        if "n_kept" in g and g.get("kept_fraction") is None:
            continue
        if "unsized_uplift" not in g:
            print(f"  {mdl:8s} {k:>5.0%} {g['n_kept']:>5}   {g['verdict'][:60]}"); continue
        lo, hi = g["unsized_uplift_ci95"]
        g2rows.append(dict(model=mdl, keep=k, n=g["n_kept"], base=100 * g["unsized_mean_unfiltered"],
                           filt=100 * g["unsized_mean_filtered"], up=100 * g["unsized_uplift"],
                           p=g["bootstrap_p_one_sided"], sized=100 * g.get("sized_mean_filtered", np.nan),
                           verdict=g["verdict"].split("--")[0].strip()))
        print(f"  {mdl:8s} {k:>5.0%} {g['n_kept']:>5} {100*g['unsized_mean_unfiltered']:>10.5f} "
              f"{100*g['unsized_mean_filtered']:>10.5f} {100*g['unsized_uplift']:>+9.5f} "
              f"[{100*lo:>+8.4f},{100*hi:>+8.4f}] {g['bootstrap_p_one_sided']:>7.3f} "
              f"{100*g.get('sized_mean_filtered', np.nan):>9.5f}  {g['verdict'].split('--')[0].strip()}")
G2 = pd.DataFrame(g2rows); G2.to_parquet(os.path.join(OUT, "gate2_blockB.parquet"))

line("GATE 2 CONTROL -- a RANDOM filter keeping the same fraction. 400 draws per cell")
rng = np.random.default_rng(11)
print(f"  {'model':8s} {'keep':>5} {'real uplift':>12} {'random p50':>11} {'random p95':>11} {'p':>7}")
ctl = []
for mdl, s in SC.items():
    m = np.isfinite(s); r = B.pct.to_numpy()[m]
    for k in KEEP:
        thr = float(np.quantile(s[m], 1 - k)); keep = s[m] >= thr
        obs = r[keep].mean() - r.mean()
        draws = np.array([r[rng.choice(len(r), keep.sum(), replace=False)].mean() - r.mean() for _ in range(400)])
        pv = float(np.mean(draws >= obs))
        ctl.append(dict(model=mdl, keep=k, obs=obs, p=pv))
        print(f"  {mdl:8s} {k:>5.0%} {obs:>+12.5f} {np.median(draws):>+11.5f} {np.quantile(draws,0.95):>+11.5f} {pv:>7.3f}")
CT = pd.DataFrame(ctl); CT.to_parquet(os.path.join(OUT, "gate2_control.parquet"))

# ---------------------------------------------------------------- the single locked read
line("BLOCK C -- ONE READ. The primary, the fracdiff order, the HMM parameters, the model and the")
print("  threshold are all frozen before this line. The model is refitted on ALL of block B once.")
C = FE[FE.blk == 2].reset_index(drop=True)
best = G2.sort_values(["p", "up"], ascending=[True, False]).iloc[0] if len(G2) else None
print(f"\n  declared choice: the block-B cell with the lowest bootstrap p -- {best['model']} at keep {best['keep']:.0%} "
      f"(uplift {best['up']:+.5f}, p {best['p']:.3f})\n")
mdl, k = best["model"], float(best["keep"])
fit_m = make(mdl, 0)
if mdl == "logit":
    sc = StandardScaler().fit(Xb); fit_m.fit(sc.transform(Xb), yb)
    sc_c = fit_m.predict_proba(sc.transform(C[COLS].to_numpy(float)))[:, 1]
    sc_b = fit_m.predict_proba(sc.transform(Xb))[:, 1]
else:
    fit_m.fit(Xb, yb)
    sc_c = fit_m.predict_proba(C[COLS].to_numpy(float))[:, 1]
    sc_b = fit_m.predict_proba(Xb)[:, 1]
thr = float(np.quantile(sc_b, 1 - k))          # threshold from BLOCK B's own score distribution
keepC = sc_c >= thr
rC = C.pct.to_numpy()
print(f"  {'arm':34s} {'n':>5} {'net %/event':>12} {'hit':>7} {'p vs 0':>8}")
gb = primary_gate(rC / 100.0)
print(f"  {'primary, unfiltered':34s} {len(rC):>5} {rC.mean():>12.5f} {100*gb['hit_rate']:>6.1f}% {gb['bootstrap_p_one_sided']:>8.3f}")
if keepC.sum() >= 30:
    gk = primary_gate(rC[keepC] / 100.0)
    print(f"  {'primary + meta filter':34s} {int(keepC.sum()):>5} {rC[keepC].mean():>12.5f} "
          f"{100*gk['hit_rate']:>6.1f}% {gk['bootstrap_p_one_sided']:>8.3f}")
    print(f"  {'uplift':34s} {'':>5} {rC[keepC].mean()-rC.mean():>+12.5f}")
    dr = np.array([rC[rng.choice(len(rC), int(keepC.sum()), replace=False)].mean() - rC.mean() for _ in range(400)])
    print(f"  random filter of the same size: median {np.median(dr):+.5f}, p {np.mean(dr >= rC[keepC].mean()-rC.mean()):.3f}")
    print(f"  kept fraction on block C {keepC.mean():.1%} against the {k:.0%} the threshold was set for "
          f"-- if these differ the score is NOT CALIBRATED across the split (STUDY_AUTOBNN).")
else:
    print(f"  primary + meta filter: only {int(keepC.sum())} events survive -- not scorable")

# ---------------------------------------------------------------- deflation
line("PHASE 5 -- DEFLATION. Every look on gold, counted")
TRIALS = dict(optuna_primary=600, frozen_cells=45, drift_control_cells=12,
              fracdiff_d=len(M.D_LADDER), hmm_K=1, meta_models=3, meta_thresholds=len(KEEP) * 3)
tot = sum(TRIALS.values())
for k_, v_ in TRIALS.items():
    print(f"  {k_:22s} {v_:>5}")
print(f"  {'TOTAL':22s} {tot:>5}")
eff = effective_trials(tot, 0.5)
rr = rC[keepC] / 100.0 if keepC.sum() >= 30 else rC / 100.0
sr = float(rr.mean() / rr.std()) if rr.std() > 0 else 0.0
from scipy.stats import skew as _sk, kurtosis as _ku
ds = deflated_sharpe(sr, len(rr), n_trials=int(eff), var_trials=float(np.var(G2.up.to_numpy() / 100.0)) if len(G2) else 1e-6,
                     skew=float(_sk(rr)), kurtosis=float(_ku(rr, fisher=False)))
print(f"\n  effective trials at avg correlation 0.5: {eff:.0f} of {tot}")
print(f"  block-C Sharpe per event {sr:.4f} on {len(rr)} events")
print(f"  DEFLATED SHARPE {ds['dsr']:.4f}   (expected max under the null {ds['expected_max_sr_under_null']:.4f})")

line("WHITE'S REALITY CHECK across every candidate that was scored, kept not discarded")
cands = {}
for mdl, s in SC.items():
    m = np.isfinite(s); r = B.pct.to_numpy()[m] / 100.0
    for k_ in KEEP:
        thr_ = float(np.quantile(s[m], 1 - k_))
        z = np.where(s[m] >= thr_, r, 0.0)
        cands[f"{mdl}@{k_:.0%}"] = z
rc = reality_check(np.column_stack(list(cands.values())))
print(f"  candidates {len(cands)};  best {list(cands)[rc['best_candidate']]} at mean {rc['best_mean']:+.6f}")
print(f"  reality-check p {rc['reality_check_p']:.3f};  null max p95 {rc['null_max_p95']:+.6f}")
print(f"  {rc['verdict']}")
print(f"\n  runtime {time.time()-t0:.0f}s")
