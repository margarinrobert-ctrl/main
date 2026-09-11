"""OPTUNA over every free parameter the paper leaves unjustified -- RESEARCH BLOCK ONLY.

The paper names ten free numbers (200/50/20 EMA, ATR 14, 0.5 ATR stop, 1.1x volume, 0.8x range,
2x wick/body, 0.1% ambiguity band, 2.5R tightening switch) and justifies none of them. Its own
section 12 note says each one tuned must enter a trial count for a deflated Sharpe. This file
sweeps all of them plus the target, the side, the session reading and the session flatten, counts
every trial, and NEVER uses the locked block to choose -- each trial's locked result is logged so
the transfer correlation can be measured as a diagnostic of the search, which is not a result.

What this branch already knows about optimisers on this data: ten re-optimisers have now lost to
the author's constants, `STUDY_V64_OPTUNA` measured research score rising monotonically with search
effort while the locked score did not follow, and `STUDY_V30`'s surrogate fits research at rho 0.96
and predicts locked at 0.07. The search is run anyway, and read the way those studies taught.
"""
import os, sys, time, json
import numpy as np, pandas as pd
import optuna

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from research.vwapema import vecore as V

optuna.logging.set_verbosity(optuna.logging.WARNING)
pd.set_option("display.width", 220)
N_TRIALS = int(os.environ.get("VE_TRIALS", 1200))
MIN_N = 120
DS = {sm: V.build(sess=sm) for sm in ("ny", "utc")}
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


def evaluate(p, side, sess, tgt_R, flatten):
    D = DS[sess]
    sig, _ = V.triggers(D, side=side, p=p)
    t = V.run(D, sig, side=side, tgt_R=tgt_R, flatten=flatten, p=p)
    return V.stats(t[t.blk == 0]), V.stats(t[t.blk == 1])


def make_obj(kind):
    def obj(tr):
        p = params(tr)
        side = tr.suggest_categorical("side", [1, -1])
        sess = tr.suggest_categorical("sess", ["ny", "utc"])
        use_t = tr.suggest_categorical("use_tgt", [True, False])
        tgt_R = tr.suggest_float("tgt_R", 1.0, 8.0) if use_t else 0.0
        flatten = tr.suggest_categorical("flatten", [True, False])
        sr, sl = evaluate(p, side, sess, tgt_R, flatten)
        LOG.append(dict(study=kind, trial=tr.number, side=side, sess=sess, tgt_R=tgt_R,
                        flatten=flatten, **p,
                        n_res=sr["n"], R_res=sr["R"], totR_res=sr["totR"], pf_res=sr["pf"],
                        rdd_res=sr["ret_dd"], win_res=sr["win"],
                        n_lock=sl["n"], R_lock=sl["R"], totR_lock=sl["totR"], pf_lock=sl["pf"]))
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
studies = {}
for kind in ("totR", "pf", "retdd"):
    st = optuna.create_study(direction="maximize",
                             sampler=optuna.samplers.TPESampler(seed=17, multivariate=True,
                                                                n_startup_trials=100))
    st.optimize(make_obj(kind), n_trials=N_TRIALS, show_progress_bar=False)
    studies[kind] = st
    print(f"  study {kind:6s}: {N_TRIALS} trials, best RESEARCH value {st.best_value:+.4f}   ({time.time()-t0:.0f}s)")

T = pd.DataFrame(LOG)
os.makedirs("results/vwapema", exist_ok=True)
T.to_parquet("results/vwapema/optuna_trials.parquet")

print("\n" + "=" * 116)
print("POPULATION SHAPE -- before any top row")
print("=" * 116)
ok = T[T.n_res >= MIN_N]
print(f"  trials {len(T):,}; with >= {MIN_N} research trades {len(ok):,} ({100*len(ok)/len(T):.1f}%)")
print(f"  share of scorable trials profitable on research: {100*(ok.totR_res>0).mean():.1f}%")
print(f"  research total R: median {ok.totR_res.median():+.2f}  p90 {ok.totR_res.quantile(.9):+.2f}  max {ok.totR_res.max():+.2f}")
fin = ok[np.isfinite(ok.totR_lock)]
pe = np.corrcoef(fin.totR_res, fin.totR_lock)[0, 1]
sp = fin[["totR_res", "totR_lock"]].corr(method="spearman").iloc[0, 1]
print(f"  corr(research totR, locked totR) over {len(fin):,} trials: Pearson {pe:+.3f}  Spearman {sp:+.3f}")
print("    [a diagnostic of the SEARCH -- locked was never used to select]")
top = fin.sort_values("totR_res", ascending=False).head(max(5, len(fin)//100))
print(f"  top 1% by research: research mean {top.totR_res.mean():+.2f} -> locked mean {top.totR_lock.mean():+.2f}"
      f"   against the whole population's locked mean {fin.totR_lock.mean():+.2f}")

print("\n" + "=" * 116)
print("MARGINALS over all scorable trials")
print("=" * 116)
for ax in ("side", "sess", "use_tgt" if "use_tgt" in ok.columns else "flatten", "flatten"):
    if ax not in ok.columns:
        continue
    m = ok.groupby(ax).agg(n=("R_res", "size"), R_res=("R_res", "mean"), pf_res=("pf_res", "mean"),
                           share_pos=("R_res", lambda x: 100*(x > 0).mean()), trades=("n_res", "mean"))
    print(f"\n  --- {ax} ---"); print(m.to_string(float_format=lambda v: f"{v:9.4f}"))
for ax, q in (("atr_stop", 5), ("vol_mult", 5), ("range_mult", 4), ("ema_slow", 4),
              ("ema_pull", 4), ("tgt_R", 4), ("wick_body", 4)):
    if ax not in ok.columns:
        continue
    b = pd.qcut(ok[ax], q, duplicates="drop")
    m = ok.groupby(b, observed=True).agg(n=("R_res", "size"), R_res=("R_res", "mean"),
                                         pf_res=("pf_res", "mean"),
                                         share_pos=("R_res", lambda x: 100*(x > 0).mean()))
    print(f"\n  --- {ax} (quantile bins) ---"); print(m.to_string(float_format=lambda v: f"{v:9.4f}"))

print("\n" + "=" * 116)
print("FINALISTS (research only) -- box-edge check and fANOVA importance")
print("=" * 116)
BOX = dict(ema_slow=(50, 400), ema_pull=(10, 120), ema_tight=(5, 60), atr_len=(7, 30),
           atr_stop=(0.15, 2.5), vol_mult=(0.8, 2.5), range_mult=(0.3, 1.6),
           wick_body=(0.75, 4.0), ambig=(0.0, 0.004), tighten_R=(0.5, 4.0), tgt_R=(1.0, 8.0))
fin_out = {}
for kind, st in studies.items():
    bp = dict(st.best_params)
    p = {k: bp[k] for k in ("ema_slow", "ema_pull", "ema_tight", "atr_len", "atr_stop",
                            "vol_mult", "range_mult", "wick_body", "ambig", "tighten_R")}
    cfg = dict(p=p, side=int(bp["side"]), sess=bp["sess"],
               tgt_R=float(bp["tgt_R"]) if bp["use_tgt"] else 0.0, flatten=bool(bp["flatten"]))
    sr, _ = evaluate(cfg["p"], cfg["side"], cfg["sess"], cfg["tgt_R"], cfg["flatten"])
    edges = [k for k, (lo, hi) in BOX.items()
             if k in bp and isinstance(bp[k], (int, float))
             and (bp[k] <= lo + 0.03*(hi-lo) or bp[k] >= hi - 0.03*(hi-lo))]
    fin_out[kind] = dict(cfg=cfg, research=sr, box_edges=edges)
    print(f"\n  [{kind}]  side {'long' if cfg['side']>0 else 'short'}  sess {cfg['sess']}  "
          f"tgt {cfg['tgt_R']:.2f}R  flatten {cfg['flatten']}")
    print("     " + "  ".join(f"{k}={v:.4g}" for k, v in p.items()))
    print(f"     research n {sr['n']} R {sr['R']:+.4f} totR {sr['totR']:+.2f} PF {sr['pf']:.3f} "
          f"win {sr['win']:.1f}% ret/DD {sr['ret_dd']:.2f}   box edges: {edges if edges else 'none'}")
    try:
        imp = optuna.importance.get_param_importances(
            st, evaluator=optuna.importance.FanovaImportanceEvaluator(seed=1))
        print("     fANOVA: " + ", ".join(f"{k} {v:.3f}" for k, v in list(imp.items())[:7]))
    except Exception as e:
        print("     fANOVA unavailable:", e)
json.dump(fin_out, open("results/vwapema/optuna_finalists.json", "w"), indent=1, default=float)
print(f"\n  TRIALS TAKEN: {len(T):,}   runtime {time.time()-t0:.0f}s")
