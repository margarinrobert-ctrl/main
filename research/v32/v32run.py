"""XGBoost and LightGBM on volume / absorption / exhaustion / anomaly features.

THE ASK: use gradient boosting on flow-style confirmation features to raise Sharpe and profit
factor, and lift the win rate by 5-15%.

THE WIN RATE PART IS ALREADY KNOWN TO BE ACHIEVABLE AND IS ALREADY KNOWN NOT TO BE THE POINT.
`STUDY_V28_ML_CAPACITY` measured exactly this: every model in a nine-model ladder raised the win
rate from 30-33% to 36-39% -- a 5-6 point lift, 15-20% in relative terms, the range asked for --
while on NQ all nine models turned a +0.0304 R baseline NEGATIVE. The mechanism was the TAIL:
NQ's p90 of R fell 1.740 -> 1.340 while US30's held 1.872 -> 1.896, and that difference, not AUC,
decided whether the model helped. A breakout system earns in its right tail, so a classifier
trained on win/lose is a win-rate optimiser pointed at the wrong objective.

SO THIS STUDY IS BUILT TO SEPARATE THE TWO. Every table prints WIN RATE and p90 OF R side by side,
and the primary model is trained on R ITSELF (regression), not on win/lose, because R is what PF and
Sharpe are made of. The win/lose classifier is run too, as the direct answer to the ask, and the two
are compared on the same rungs.

THE GUARDS, none optional:
  PURGED + EMBARGOED folds. Trades overlap, so a naive K-fold trains on the answer. Any training
    trade whose [signal, exit] interval touches a test interval +-50 bars is DROPPED.
  SHUFFLED-LABEL TWIN for every model. That score is the pipeline's noise floor, and in V28 the
    deepest net's shuffled twin outscored every real model on top-decile P&L.
  SAME-SELECTIVITY RANDOM CONTROL at every rung. Restrictiveness alone raises PF, so a model that
    keeps 25% of signals must beat a RANDOM 25%, not the unfiltered rule.
  THE POSITION LOCK IS RE-APPLIED after selection. A conditional split of realised trades is not a
    filter test; dropping a signal frees the engine to take the next one.
  ONE READ ON LOCKED, at the end, after everything is fixed on research.

Usage: python3 research/v32/v32run.py
"""
from __future__ import annotations

import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v27")
sys.path.insert(0, "research/v28")
sys.path.insert(0, "research/v32")
import v16core as C           # noqa: E402
import v28data as D28         # noqa: E402
import v32flow as FL          # noqa: E402
import xgboost as xgb         # noqa: E402
import lightgbm as lgb        # noqa: E402

RUNGS = (1.00, 0.75, 0.50, 0.33, 0.25, 0.10)
FOLDS = 6
EMBARGO = 50
DRAWS = 400
MIN_N = 25


# ------------------------------------------------------------------------------------------------
# data
# ------------------------------------------------------------------------------------------------
def us30_bars(tf):
    import v27run as R27
    d = pd.read_csv("data/US30_LONG_15m.csv", sep="\t")
    d["ts"] = pd.to_datetime(d.DateTime, format="%Y.%m.%d %H:%M:%S") - pd.Timedelta(hours=7)
    d = d.sort_values("ts").reset_index(drop=True)
    ny = d.ts
    d["sess"] = (ny.dt.year * 10000 + ny.dt.month * 100 + ny.dt.day).to_numpy()
    d["mod"] = (ny.dt.hour * 60 + ny.dt.minute).to_numpy()
    d = d.rename(columns={"Open": "o", "High": "h", "Low": "l", "Close": "c",
                          "TickVolume": "v"})       # `Volume` is all zeros in this feed
    if tf == 15:
        return {k: d[k].to_numpy() for k in ("ts", "o", "h", "l", "c", "v", "mod", "sess")}
    d["blk"] = np.arange(len(d)) // (tf // 15)
    g = d.groupby("blk")
    return dict(ts=g.ts.first().to_numpy(), o=g.o.first().to_numpy(), h=g.h.max().to_numpy(),
                l=g.l.min().to_numpy(), c=g.c.last().to_numpy(), v=g.v.sum().to_numpy(),
                mod=g["mod"].first().to_numpy(), sess=g.sess.first().to_numpy())


def build(market="NQ", tf=30, side=1):
    """(X_flow, X_base, R, meta) at signal bars. Every column read at the SIGNAL bar."""
    Xb, R, _w, meta = D28.build(market=market, tf=tf, side=side)
    P = meta["P"]
    if market == "NQ":
        import fastbars
        b = fastbars.bars(tf)
        v = b["v"]
    else:
        v = us30_bars(tf)["v"].astype(float)
    F = FL.build(P["o"], P["h"], P["l"], P["c"], v, P["mod"], atr=P["atr"])
    sigk = meta["full_sig"]
    Xf = pd.DataFrame({k: val[sigk] for k, val in F.items()})[meta["keep"]].reset_index(drop=True)
    ok = np.isfinite(Xf.to_numpy()).all(axis=1)
    return Xf[ok].reset_index(drop=True), Xb[ok].reset_index(drop=True), R[ok], \
        dict(meta, ok=ok, rows=np.flatnonzero(meta["keep"])[ok])


def blocks(sess, frac=0.65):
    u = np.unique(sess)
    return sess < u[int(len(u) * frac)], sess >= u[int(len(u) * frac)]


# ------------------------------------------------------------------------------------------------
# scoring -- the position lock is re-applied after every selection
# ------------------------------------------------------------------------------------------------
def relock(meta, rows_sel):
    O = meta["O"]
    m = np.zeros(len(O["sig"]), bool)
    m[rows_sel] = True
    return C.take(O, m)


def stat(meta, rows_sel, P):
    idx = relock(meta, rows_sel)
    if len(idx) < MIN_N:
        return None
    r = meta["O"]["R"][idx]
    if not (r < 0).any():
        return None
    eq = np.cumsum(r)
    days = P["sess"][meta["O"]["sig"][idx]]
    allday = np.unique(P["sess"][(P["sess"] >= days.min()) & (P["sess"] <= days.max())])
    d = pd.Series(r).groupby(pd.Series(days)).sum().reindex(allday, fill_value=0.0).to_numpy()
    return dict(n=len(idx), win=float((r > 0).mean()),
                pf=float(r[r > 0].sum() / abs(r[r < 0].sum())), R=float(r.mean()),
                p90=float(np.percentile(r, 90)),
                dd=float(np.max(np.maximum.accumulate(eq) - eq)),
                sharpe=float(d.mean() / d.std(ddof=1) * np.sqrt(252)) if d.std(ddof=1) > 0
                else np.nan)


def control(meta, pool_rows, k, P, draws=DRAWS, seed=19):
    """Random filters keeping the SAME NUMBER of signals from the SAME pool, same position lock."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(draws):
        s = stat(meta, rng.choice(pool_rows, size=k, replace=False), P)
        if s is not None:
            out.append((s["pf"], s["win"], s["sharpe"], s["R"]))
    a = np.array(out)
    return dict(pf=a[:, 0], win=a[:, 1], sharpe=a[:, 2], R=a[:, 3])


# ------------------------------------------------------------------------------------------------
# models -- shallow, because V28 found capacity monotonically harmful here
# ------------------------------------------------------------------------------------------------
def make(name, task):
    if name == "xgb":
        kw = dict(n_estimators=300, max_depth=3, learning_rate=0.03, subsample=0.8,
                  colsample_bytree=0.6, reg_lambda=5.0, min_child_weight=10, n_jobs=4,
                  verbosity=0, random_state=0)
        return xgb.XGBClassifier(**kw) if task == "win" else xgb.XGBRegressor(**kw)
    kw = dict(n_estimators=300, num_leaves=7, learning_rate=0.03, subsample=0.8,
              subsample_freq=1, colsample_bytree=0.6, reg_lambda=5.0, min_child_samples=20,
              n_jobs=4, verbose=-1, random_state=0)
    return lgb.LGBMClassifier(**kw) if task == "win" else lgb.LGBMRegressor(**kw)


def oof(X, y, sig, xb, name, task, shuffle=False, seed=0):
    """Out-of-fold predictions under PURGED + EMBARGOED folds."""
    p = np.full(len(y), np.nan)
    yy = np.random.default_rng(seed).permutation(y) if shuffle else y
    for tr, te in D28.purged_folds(sig, xb, n_folds=FOLDS, embargo=EMBARGO):
        m = make(name, task)
        m.fit(X.iloc[tr], yy[tr])
        p[te] = (m.predict_proba(X.iloc[te])[:, 1] if task == "win"
                 else m.predict(X.iloc[te]))
    return p


def ladder(meta, rows, pred, P, base_pool):
    """Keep the top q of signals by prediction, at each rung, with the lock re-applied."""
    out = {}
    order = np.argsort(-pred)
    for q in RUNGS:
        k = max(MIN_N, int(round(q * len(pred))))
        if k > len(pred):
            continue
        out[q] = (stat(meta, rows[order[:k]], P), k)
    return out


def hdr(t):
    print("\n" + "=" * 130)
    print(t)
    print("=" * 130)


SETS = ("FLOW", "BASE", "FLOW+BASE")
MODELS = ("xgb", "lgbm")


def run_market(market, tf, side=1):
    Xf, Xb, R, meta = build(market, tf, side)
    P = meta["P"]
    sess = meta["sess"][meta["ok"]]
    res, lk = blocks(sess)
    rows = meta["rows"]
    sig, xb = meta["sig"][meta["ok"]], meta["xb"][meta["ok"]]
    sets = {"FLOW": Xf, "BASE": Xb, "FLOW+BASE": pd.concat([Xf, Xb], axis=1)}

    hdr(f"{market} {tf}m  Donchian 30/20 long, 2.0N, no target, real cost  |  "
        f"{len(R):,} signals, {Xf.shape[1]} flow columns, {Xb.shape[1]} base columns  |  "
        f"research {int(res.sum()):,} / locked {int(lk.sum()):,}")

    base = stat(meta, rows[res], P)
    print(f"   BASELINE research (no model):  n {base['n']:>4}  win {base['win']:>6.3f}"
          f"  PF {base['pf']:>6.3f}  Sharpe {base['sharpe']:>+6.2f}  R {base['R']:>+7.4f}"
          f"  p90 {base['p90']:>+6.3f}  DD {base['dd']:>6.1f}")

    ri = np.flatnonzero(res)
    pool_r = rows[ri]
    ctrl_cache = {}
    store = {}

    for task, lab in (("R", "trained on R (regression) -- the objective PF and Sharpe are made of"),
                      ("win", "trained on WIN/LOSE (classification) -- the objective asked for")):
        hdr(f"{market} {tf}m   MODEL {lab}")
        print(f"   {'set':<10}{'model':<7}{'keep':>6}{'n':>6}{'win%':>7}{'PF':>7}{'Sharpe':>8}"
              f"{'R/trade':>9}{'p90 R':>8}{'DD':>7}{'  ':>2}{'p(PF)':>7}{'p(win)':>8}"
              f"{'shuf PF':>9}")
        for sname in SETS:
            X = sets[sname].iloc[ri].reset_index(drop=True)
            for mname in MODELS:
                pr = oof(X, R[ri] if task == "R" else (R[ri] > 0).astype(int),
                         sig[ri], xb[ri], mname, task)
                ps = oof(X, R[ri] if task == "R" else (R[ri] > 0).astype(int),
                         sig[ri], xb[ri], mname, task, shuffle=True, seed=7)
                good = np.isfinite(pr) & np.isfinite(ps)
                L = ladder(meta, pool_r[good], pr[good], P, pool_r)
                Ls = ladder(meta, pool_r[good], ps[good], P, pool_r)
                store[(task, sname, mname)] = L
                for q in RUNGS:
                    s, k = L.get(q, (None, 0))
                    if s is None:
                        continue
                    if k not in ctrl_cache:
                        ctrl_cache[k] = control(meta, pool_r[good], k, P)
                    cc = ctrl_cache[k]
                    ss = Ls.get(q, (None, 0))[0]
                    print(f"   {sname:<10}{mname:<7}{q:>6.0%}{s['n']:>6}{s['win']:>7.3f}"
                          f"{s['pf']:>7.3f}{s['sharpe']:>+8.2f}{s['R']:>+9.4f}{s['p90']:>+8.3f}"
                          f"{s['dd']:>7.1f}{'  ':>2}{float((cc['pf'] >= s['pf']).mean()):>7.3f}"
                          f"{float((cc['win'] >= s['win']).mean()):>8.3f}"
                          f"{(ss['pf'] if ss else np.nan):>9.3f}")
    return dict(Xf=Xf, Xb=Xb, R=R, meta=meta, P=P, res=res, lk=lk, rows=rows, sig=sig, xb=xb,
                sets=sets, store=store, base=base)


def locked_read(D, market, tf):
    """ONE read. Fit on ALL of research, predict locked, same rungs, same control."""
    meta, P, rows = D["meta"], D["P"], D["rows"]
    ri, li = np.flatnonzero(D["res"]), np.flatnonzero(D["lk"])
    R = D["R"]
    base_r = stat(meta, rows[ri], P)
    base_l = stat(meta, rows[li], P)
    hdr(f"{market} {tf}m   THE LOCKED READ -- fit on all of research, predicted once")
    print(f"   BASELINE  research  n {base_r['n']:>4} win {base_r['win']:.3f} PF {base_r['pf']:.3f}"
          f" Sharpe {base_r['sharpe']:+.2f} R {base_r['R']:+.4f} p90 {base_r['p90']:+.3f}")
    print(f"   BASELINE  locked    n {base_l['n']:>4} win {base_l['win']:.3f} PF {base_l['pf']:.3f}"
          f" Sharpe {base_l['sharpe']:+.2f} R {base_l['R']:+.4f} p90 {base_l['p90']:+.3f}")
    print(f"\n   {'task':<5}{'set':<10}{'model':<7}{'keep':>6}{'n':>6}{'win%':>7}{'d win':>8}"
          f"{'PF':>7}{'Sharpe':>8}{'R/trade':>9}{'p90 R':>8}{'DD':>7}{'  ':>2}{'p(PF)':>7}"
          f"{'p(win)':>8}")
    cc_cache = {}
    for task in ("R", "win"):
        y = R[ri] if task == "R" else (R[ri] > 0).astype(int)
        for sname in SETS:
            for mname in MODELS:
                m = make(mname, task)
                m.fit(D["sets"][sname].iloc[ri], y)
                Xl = D["sets"][sname].iloc[li]
                pl = (m.predict_proba(Xl)[:, 1] if task == "win" else m.predict(Xl))
                order = np.argsort(-pl)
                for q in RUNGS:
                    k = max(MIN_N, int(round(q * len(pl))))
                    if k > len(pl):
                        continue
                    s = stat(meta, rows[li][order[:k]], P)
                    if s is None:
                        continue
                    if k not in cc_cache:
                        cc_cache[k] = control(meta, rows[li], k, P)
                    cc = cc_cache[k]
                    print(f"   {task:<5}{sname:<10}{mname:<7}{q:>6.0%}{s['n']:>6}{s['win']:>7.3f}"
                          f"{s['win'] - base_l['win']:>+8.3f}{s['pf']:>7.3f}{s['sharpe']:>+8.2f}"
                          f"{s['R']:>+9.4f}{s['p90']:>+8.3f}{s['dd']:>7.1f}{'  ':>2}"
                          f"{float((cc['pf'] >= s['pf']).mean()):>7.3f}"
                          f"{float((cc['win'] >= s['win']).mean()):>8.3f}")


def importances(D, market, tf, sname="FLOW+BASE"):
    ri = np.flatnonzero(D["res"])
    m = make("lgbm", "R")
    m.fit(D["sets"][sname].iloc[ri], D["R"][ri])
    imp = pd.Series(m.feature_importances_, index=D["sets"][sname].columns).sort_values(
        ascending=False)
    hdr(f"{market} {tf}m   WHAT THE MODEL USES  (LightGBM gain split count, research only -- "
        "ranking on both blocks produced a false family in STUDY_FEATURES)")
    fam = imp.groupby([c.split(".")[0] for c in imp.index]).sum()
    tot = fam.sum()
    print("   by family: " + "   ".join(f"{k} {v / tot:.1%}" for k, v in
                                        fam.sort_values(ascending=False).items()))
    print("   top 20:")
    for k, v in imp.head(20).items():
        print(f"      {k:<32}{v:>8.0f}")


if __name__ == "__main__":
    for market, tf in (("NQ", 30), ("US30", 30)):
        D = run_market(market, tf)
        importances(D, market, tf)
        locked_read(D, market, tf)
