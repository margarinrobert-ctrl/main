"""M2 -- OPTUNA on US100 and US30, RESEARCH BLOCKS ONLY. US30_ISO is never searched.

Same fourteen axes as the gold study (`run_optuna.py`): the paper's ten free numbers plus the
target, the side, the session reading and the flatten. Every trial's LOCKED result is logged and
never used to choose -- it exists only so the research->locked transfer correlation can be
measured, which is a diagnostic of the search and not a result.

Eleven re-optimisers have now lost to their author's constants on this branch. The search is run
because the user asked for it and because its POPULATION SHAPE and fANOVA importances are worth
having; the finalists go into M3 with the trial count attached.
"""
import os, sys, time
import numpy as np, pandas as pd
import optuna

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vecore as V, ve_markets as M

optuna.logging.set_verbosity(optuna.logging.WARNING)
pd.set_option("display.width", 230)
N_TRIALS = int(os.environ.get("VE_TRIALS", 800))
MIN_N = 100
MK = ("US100", "US30")
DS = {(k, sm): M.build(k, sess=sm) for k in MK for sm in ("ny", "utc")}
LOG = []


def params(tr):
    return dict(
        ema_slow=tr.suggest_int("ema_slow", 50, 400, step=10),
        ema_pull=tr.suggest_int("ema_pull", 10, 120, step=2),
        ema_tight=tr.suggest_int("ema_tight", 5, 60, step=5),
        atr_len=tr.suggest_int("atr_len", 7, 30),
        atr_stop=tr.suggest_float("atr_stop", 0.15, 2.5),
        vol_mult=tr.suggest_float("vol_mult", 0.8, 2.5),
        range_mult=tr.suggest_float("range_mult", 0.3, 1.6),
        wick_body=tr.suggest_float("wick_body", 0.75, 4.0),
        ambig=tr.suggest_float("ambig", 0.0, 0.004),
        tighten_R=tr.suggest_float("tighten_R", 0.5, 4.0))


def evaluate(mk, p, side, sess, tgt_R, flatten):
    D = DS[(mk, sess)]
    sig, _ = V.triggers(D, side=side, p=p)
    t = M.run(D, sig, side=side, tgt_R=tgt_R, flatten=flatten, p=p)
    a, b = t[t.blk == 0], t[t.blk == 1]
    # the PER-TRADE Sharpe of every trial, logged because the deflated Sharpe's `var_trials` is the
    # variance of the trial SHARPES and nothing else -- estimating it from anything else is how the
    # gold study first printed 0.9919 and then 0.571 for the same cell (CLAUDE.md).
    shr = float(a.R.mean() / a.R.std(ddof=1)) if len(a) > 5 and a.R.std(ddof=1) > 0 else np.nan
    return V.stats(a), V.stats(b), shr


def make_obj(mk, kind):
    def obj(tr):
        p = params(tr)
        side = tr.suggest_categorical("side", [1, -1])
        sess = tr.suggest_categorical("sess", ["ny", "utc"])
        use_t = tr.suggest_categorical("use_tgt", [True, False])
        tgt_R = tr.suggest_float("tgt_R", 1.0, 8.0) if use_t else 0.0
        flatten = tr.suggest_categorical("flatten", [True, False])
        sr, sl, shr = evaluate(mk, p, side, sess, tgt_R, flatten)
        LOG.append(dict(feed=mk, study=kind, trial=tr.number, side=side, sess=sess, tgt_R=tgt_R,
                        sharpe_res=shr,
                        flatten=flatten, **p,
                        n_res=sr["n"], R_res=sr["R"], pct_res=sr["pct"], totR_res=sr["totR"],
                        pf_res=sr["pf"], rdd_res=sr["ret_dd"], win_res=sr["win"],
                        n_lock=sl["n"], R_lock=sl["R"], pct_lock=sl["pct"],
                        totR_lock=sl["totR"], pf_lock=sl["pf"]))
        if sr["n"] < MIN_N:
            return -1e3 - (MIN_N - sr["n"])
        if kind == "totR":
            return sr["totR"]
        if kind == "pf":
            return min(sr["pf"], 5.0)
        return min(sr["ret_dd"], 25.0)
    return obj


print(__doc__)
t0 = time.time()
best = {}
for mk in MK:
    for kind in ("totR", "pf", "retdd"):
        st = optuna.create_study(direction="maximize",
                                 sampler=optuna.samplers.TPESampler(seed=17, multivariate=True,
                                                                    n_startup_trials=80))
        st.optimize(make_obj(mk, kind), n_trials=N_TRIALS, show_progress_bar=False)
        best[(mk, kind)] = st
        print(f"  {mk:6s} {kind:6s}: {N_TRIALS} trials, best RESEARCH {st.best_value:+.4f}  ({time.time()-t0:.0f}s)")

T = pd.DataFrame(LOG)
os.makedirs("results/vwapema", exist_ok=True)
T.to_parquet("results/vwapema/m2_trials.parquet")
print(f"\nTOTAL TRIALS COUNTED: {len(T)}  ({time.time()-t0:.0f}s)")

L = lambda s: print("\n" + "=" * 112 + f"\n{s}\n" + "=" * 112)

L("M2.1  POPULATION SHAPE FIRST -- never the top row")
rows = []
for mk in MK:
    for kind in ("totR", "pf", "retdd"):
        s = T[(T.feed == mk) & (T.study == kind) & (T.n_res >= MIN_N)]
        if len(s) < 30:
            continue
        s2 = s[s.n_lock >= 25]
        rows.append(dict(feed=mk, study=kind, scorable=len(s),
                         res_pos=round(100 * (s.R_res > 0).mean(), 1),
                         lock_pos=round(100 * (s2.R_lock > 0).mean(), 1),
                         corr_R=round(float(s2.R_res.corr(s2.R_lock)), 3),
                         spearman=round(float(s2.R_res.corr(s2.R_lock, method="spearman")), 3),
                         top1pct_res=round(float(s2.nlargest(max(1, len(s2)//100), "R_res").R_res.mean()), 4),
                         top1pct_lock=round(float(s2.nlargest(max(1, len(s2)//100), "R_res").R_lock.mean()), 4),
                         pop_lock=round(float(s2.R_lock.mean()), 4)))
P = pd.DataFrame(rows)
print(P.to_string(index=False))
P.to_csv("results/vwapema/m2_population.csv", index=False)
print("\nIf `top1pct_lock` is at or below `pop_lock`, selecting on research bought nothing.")

L("M2.2  MARGINALS -- what the whole grid says about each axis, not what the top row says")
for mk in MK:
    s = T[(T.feed == mk) & (T.n_res >= MIN_N) & (T.n_lock >= 25)]
    print(f"\n--- {mk}  (n={len(s)})")
    for ax in ("side", "sess", "flatten"):
        g = s.groupby(ax).agg(n=("R_res", "size"), R_res=("R_res", "mean"), R_lock=("R_lock", "mean"))
        print(f"  {ax}:", " | ".join(f"{i}: res {r.R_res:+.4f} lock {r.R_lock:+.4f} (n{int(r.n)})"
                                     for i, r in g.iterrows()))
    for ax in ("atr_stop", "tgt_R", "ema_slow", "ema_pull", "vol_mult", "range_mult"):
        q = pd.qcut(s[ax], 4, duplicates="drop")
        g = s.groupby(q, observed=True).agg(R_res=("R_res", "mean"), R_lock=("R_lock", "mean"))
        print(f"  {ax:11s}:", " | ".join(f"{str(i.left)[:5]}-{str(i.right)[:5]}: "
                                         f"{r.R_res:+.3f}/{r.R_lock:+.3f}" for i, r in g.iterrows()))

L("M2.3  fANOVA -- which axis the objective actually depends on")
rows = []
for mk in MK:
    for kind in ("totR", "pf", "retdd"):
        st = best[(mk, kind)]
        try:
            imp = optuna.importance.get_param_importances(st)
        except Exception as e:
            print(mk, kind, "importance failed:", e); continue
        for k2, v in list(imp.items())[:6]:
            rows.append(dict(feed=mk, study=kind, param=k2, importance=round(float(v), 4)))
I = pd.DataFrame(rows)
print(I.pivot_table(index="param", columns=["feed", "study"], values="importance").round(3).to_string())
I.to_csv("results/vwapema/m2_importance.csv", index=False)

L("M2.4  THE FINALISTS -- chosen on research, box edges flagged, locked NOT read here")
BOX = dict(ema_slow=(50, 400), ema_pull=(10, 120), ema_tight=(5, 60), atr_len=(7, 30),
           atr_stop=(0.15, 2.5), vol_mult=(0.8, 2.5), range_mult=(0.3, 1.6),
           wick_body=(0.75, 4.0), ambig=(0.0, 0.004), tighten_R=(0.5, 4.0), tgt_R=(1.0, 8.0))
fin = []
for mk in MK:
    for kind in ("totR", "pf", "retdd"):
        st = best[(mk, kind)]
        bp = dict(st.best_params)
        edges = [k2 for k2, (lo, hi) in BOX.items() if k2 in bp and
                 (abs(bp[k2] - lo) < 1e-9 or abs(bp[k2] - hi) < 1e-9)]
        row = dict(feed=mk, study=kind, value=round(st.best_value, 4),
                   edges=",".join(edges) if edges else "-", **bp)
        fin.append(row)
F = pd.DataFrame(fin)
print(F.to_string(index=False))
F.to_csv("results/vwapema/m2_finalists.csv", index=False)
print("\nA parameter sitting on its box limit means the optimum is outside the box -- widening it")
print("just moves the optimum to the new ceiling (STUDY_V64_OPTUNA).")
