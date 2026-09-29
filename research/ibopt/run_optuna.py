"""OPTUNA on the IB primary -- RESEARCH BLOCK ONLY, population shape before any top row.

What this branch already knows about optimisers on this data: nine re-optimisers have lost to the
author's constants; `STUDY_V64_OPTUNA` measured research Sharpe rising monotonically with search
effort while locked Sharpe did not follow; `STUDY_V30` found a surrogate that fits research at
rho 0.96 and predicts locked at 0.07. So the search is run, and it is read the way those studies
taught: share of trials profitable, box-edge check, fANOVA importance, and the locked result of
every trial LOGGED TO DISK AND NEVER USED FOR SELECTION -- its only use is the population
correlation, which is a diagnostic of the search and not a result.

OBJECTIVE. Total percent of entry price on research, one unit, at a floor of 150 research trades
(~26 a year). NOT R (`STUDY_V58`: risk = (stop - retr) x range can be driven to nothing).
A second study optimises profit factor at the same floor; a third return-over-drawdown.

FINALISTS ARE NOT READ HERE. `run_locked.py` reads the locked block ONCE, for the finalists and
the meta layer together.
"""
import os, sys, json, time
import numpy as np, pandas as pd
import optuna

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from research.ibopt import ibcore as C      # noqa: E402

optuna.logging.set_verbosity(optuna.logging.WARNING)
pd.set_option("display.width", 200)
F = C.build("US30L")
MIN_N = 150
N_TRIALS = int(os.environ.get("IB_TRIALS", 1200))
LOG = []


def params(trial):
    retr = trial.suggest_float("retr", 0.0, 0.60)
    stopf = trial.suggest_float("stopf", retr + 0.10, 1.60)
    use_tgt = trial.suggest_categorical("use_tgt", [True, False])
    tgt = trial.suggest_float("tgt", 0.25, 3.0) if use_tgt else 99.0
    return dict(ib_min=trial.suggest_categorical("ib_min", [30, 45, 60, 90]),
                retr=retr, stopf=stopf, tgt=tgt,
                flat_min=trial.suggest_categorical("flat_min", [13 * 60, 15 * 60, 15 * 60 + 55]),
                side=trial.suggest_categorical("side", ["long", "short", "both"]),
                ib_atr_min=trial.suggest_float("ib_atr_min", 0.0, 1.5),
                ib_atr_max=trial.suggest_categorical("ib_atr_max", [0.0, 2.0, 3.0, 4.0]))


def evaluate(kw):
    t = C.run(F, **kw)
    r, l = t[t.blk == 0], t[t.blk == 1]
    return C.stats(r), C.stats(l)


def make_objective(kind):
    def obj(trial):
        kw = params(trial)
        sr, sl = evaluate(kw)
        rec = dict(study=kind, trial=trial.number, **kw, n_res=sr["n"], tot_res=sr["tot"],
                   pf_res=sr["pf"], rdd_res=sr["ret_dd"], pct_res=sr["pct"],
                   n_lock=sl["n"], tot_lock=sl["tot"], pf_lock=sl["pf"], rdd_lock=sl["ret_dd"])
        LOG.append(rec)
        if sr["n"] < MIN_N:
            return -50.0 - (MIN_N - sr["n"]) * 0.1
        if kind == "total":
            return sr["tot"]
        if kind == "pf":
            return sr["pf"]
        return min(sr["ret_dd"], 20.0)
    return obj


print(__doc__)
t0 = time.time()
studies = {}
for kind in ("total", "pf", "retdd"):
    st = optuna.create_study(direction="maximize",
                             sampler=optuna.samplers.TPESampler(seed=11, multivariate=True, n_startup_trials=80))
    st.optimize(make_objective(kind), n_trials=N_TRIALS, show_progress_bar=False)
    studies[kind] = st
    print(f"  study {kind:6s}: {N_TRIALS} trials, best research value {st.best_value:+.3f}  ({time.time()-t0:.0f}s)")
os.makedirs("results/ibopt", exist_ok=True)
T = pd.DataFrame(LOG)
T.to_parquet("results/ibopt/optuna_trials.parquet")

print("\n" + "=" * 108)
print("POPULATION SHAPE -- before any top row")
print("=" * 108)
T["use_tgt"] = T.tgt < 90
ok = T[T.n_res >= MIN_N]
print(f"  trials {len(T)}, with >= {MIN_N} research trades {len(ok)} ({100*len(ok)/len(T):.1f}%)")
print(f"  share of scorable trials profitable on research: {100*(ok.tot_res>0).mean():.1f}%")
print(f"  research total: median {ok.tot_res.median():+.2f}%  p90 {ok.tot_res.quantile(.9):+.2f}%  max {ok.tot_res.max():+.2f}%")
fin = ok[np.isfinite(ok.tot_lock)]
print(f"  corr(research total, locked total) over {len(fin)} trials: Pearson {np.corrcoef(fin.tot_res, fin.tot_lock)[0,1]:+.3f}, "
      f"Spearman {fin[['tot_res','tot_lock']].corr(method='spearman').iloc[0,1]:+.3f}   [diagnostic of the search; not a selection]")
top = fin.sort_values("tot_res", ascending=False).head(max(5, len(fin) // 100))
print(f"  top 1% by research total: research mean {top.tot_res.mean():+.2f}% -> locked mean {top.tot_lock.mean():+.2f}%  "
      f"against the whole population's locked mean {fin.tot_lock.mean():+.2f}%")

print("\n" + "=" * 108)
print("MARGINALS over all scorable trials -- what a setting does across everything else")
print("=" * 108)
for ax in ("side", "ib_min", "flat_min", "use_tgt", "ib_atr_max"):
    m = ok.groupby(ax).agg(n=("tot_res", "size"), tot_res=("tot_res", "mean"), pf_res=("pf_res", "mean"),
                          share_pos=("tot_res", lambda x: 100 * (x > 0).mean()))
    print(f"\n  --- {ax} ---"); print(m.to_string(float_format=lambda v: f"{v:8.3f}"))
for ax, edges in (("retr", [0, .1, .2, .3, .4, .5, .6]), ("stopf", [0, .4, .6, .8, 1.0, 1.3, 1.6]),
                  ("ib_atr_min", [0, .25, .5, .75, 1.0, 1.5])):
    b = pd.cut(ok[ax], edges, include_lowest=True)
    m = ok.groupby(b, observed=True).agg(n=("tot_res", "size"), tot_res=("tot_res", "mean"), pf_res=("pf_res", "mean"),
                                         share_pos=("tot_res", lambda x: 100 * (x > 0).mean()))
    print(f"\n  --- {ax} (binned) ---"); print(m.to_string(float_format=lambda v: f"{v:8.3f}"))

print("\n" + "=" * 108)
print("FINALISTS (research only) -- box-edge check and fANOVA importance")
print("=" * 108)
finalists = {}
for kind, st in studies.items():
    bp = st.best_params
    kw = dict(ib_min=bp["ib_min"], retr=bp["retr"], stopf=bp["stopf"],
              tgt=bp["tgt"] if bp["use_tgt"] else 99.0, flat_min=bp["flat_min"], side=bp["side"],
              ib_atr_min=bp["ib_atr_min"], ib_atr_max=bp["ib_atr_max"])
    sr, _ = evaluate(kw)
    edges = []
    if bp["retr"] > 0.57 or bp["retr"] < 0.03: edges.append("retr")
    if bp["stopf"] > 1.55 or bp["stopf"] < bp["retr"] + 0.13: edges.append("stopf")
    if bp["use_tgt"] and (bp["tgt"] > 2.9 or bp["tgt"] < 0.35): edges.append("tgt")
    if bp["ib_atr_min"] > 1.45: edges.append("ib_atr_min")
    finalists[kind] = dict(kw=kw, research=sr, box_edges=edges)
    print(f"\n  [{kind}] {kw}")
    print(f"     research n {sr['n']} total {sr['tot']:+.2f}% PF {sr['pf']:.3f} ret/DD {sr['ret_dd']:.2f} win {sr['win']:.1f}%   "
          f"box edges: {edges if edges else 'none'}")
    try:
        imp = optuna.importance.get_param_importances(st, evaluator=optuna.importance.FanovaImportanceEvaluator(seed=1))
        print("     fANOVA: " + ", ".join(f"{k} {v:.3f}" for k, v in list(imp.items())[:6]))
    except Exception as e:
        print(f"     fANOVA unavailable: {e}")
json.dump(finalists, open("results/ibopt/finalists.json", "w"), indent=1, default=float)
print(f"\n  runtime {time.time()-t0:.0f}s")
