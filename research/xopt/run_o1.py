"""O1 -- Optuna over the full space with EXCESS OVER A MATCHED CONTROL as the objective.

RESEARCH BLOCK ONLY. Every trial's locked and forward results are logged and NEVER used to choose;
they exist so the transfer can be measured, which is a diagnostic of the search and not a result.

Three objectives are run because they disagree in an informative way:
  excess      the rule's R minus the median R of a random entry with its own geometry
  excess_pf   the same, but the candidate must also clear the control's 95th percentile
  return      raw R -- included ONLY as the control arm for the search itself, so the claim that
              maximising return buys drift can be measured rather than asserted
"""
import os, sys, time
import numpy as np, pandas as pd
import optuna

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xcore as C

optuna.logging.set_verbosity(optuna.logging.WARNING)
pd.set_option("display.width", 235)
N_TRIALS = int(os.environ.get("XO_TRIALS", 700))
MIN_N = 80
LOG = []
os.makedirs("results/xopt", exist_ok=True)
print(__doc__)


def suggest(tr):
    cfg = dict(
        ema_slow=tr.suggest_int("ema_slow", 50, 400, step=10),
        ema_pull=tr.suggest_int("ema_pull", 10, 150, step=2),
        ema_tight=tr.suggest_int("ema_tight", 5, 60, step=5),
        atr_len=tr.suggest_int("atr_len", 7, 30),
        atr_stop=tr.suggest_float("atr_stop", 0.15, 4.0),
        vol_mult=tr.suggest_float("vol_mult", 0.0, 2.5),
        range_mult=tr.suggest_float("range_mult", 0.0, 1.6),
        wick_body=tr.suggest_float("wick_body", 0.75, 4.0),
        ambig=tr.suggest_float("ambig", 0.0, 0.004),
        tighten_R=tr.suggest_float("tighten_R", 0.5, 4.0),
        side=tr.suggest_categorical("side", [1, -1]),
        trail=tr.suggest_categorical("trail", [True, False]),
        tighten=tr.suggest_categorical("tighten", [True, False]),
        flatten=tr.suggest_categorical("flatten", [True, False]),
        use_vol=tr.suggest_categorical("use_vol", [True, False]),
        sess=tr.suggest_categorical("sess", ["ny", "utc"]))
    cfg["tgt_R"] = (tr.suggest_float("tgt_R", 1.0, 8.0)
                    if tr.suggest_categorical("use_tgt", [True, False]) else 0.0)
    return cfg


def make_obj(kind):
    def obj(tr):
        cfg = suggest(tr)
        r = C.evaluate(cfg, blk=0, min_n=MIN_N)
        rec = dict(study=kind, trial=tr.number, **{k: v for k, v in cfg.items()},
                   n=r["n"], R=r.get("R", np.nan), pf=r.get("pf", np.nan),
                   ctl=r.get("ctl", np.nan), excess=r.get("excess", np.nan),
                   beat_p95=r.get("beat_p95", False))
        if r["ok"]:
            l = C.evaluate(cfg, blk=1, min_n=25)
            rec.update(n_lock=l["n"], R_lock=l.get("R", np.nan),
                       excess_lock=l.get("excess", np.nan), ctl_lock=l.get("ctl", np.nan))
        LOG.append(rec)
        if not r["ok"]:
            return -1e3 - (MIN_N - r["n"])
        if kind == "excess":
            return float(r["excess"])
        if kind == "excess_pf":
            return float(r["excess"]) + (0.10 if r["beat_p95"] else -0.10)
        return float(r["R"])
    return obj


t0 = time.time()
best = {}
for kind in ("excess", "excess_pf", "return"):
    st = optuna.create_study(direction="maximize",
                             sampler=optuna.samplers.TPESampler(seed=11, multivariate=True,
                                                                n_startup_trials=80))
    st.optimize(make_obj(kind), n_trials=N_TRIALS, show_progress_bar=False)
    best[kind] = st
    print(f"  study {kind:10s}: {N_TRIALS} trials, best RESEARCH value {st.best_value:+.4f}  "
          f"({time.time()-t0:.0f}s)")

T = pd.DataFrame(LOG)
T.to_parquet("results/xopt/o1_trials.parquet")
print(f"\nTOTAL TRIALS COUNTED: {len(T)}   ({time.time()-t0:.0f}s)")

L = lambda s: print("\n" + "=" * 114 + f"\n{s}\n" + "=" * 114)

L("O1.1  DOES MAXIMISING RETURN BUY DRIFT?  the three studies compared on their own terms")
ok = T[T.n >= MIN_N]
rows = []
for kind in ("excess", "excess_pf", "return"):
    s = ok[ok.study == kind]
    if len(s) < 20:
        continue
    top = s.nlargest(max(1, len(s) // 20), "excess" if kind != "return" else "R")
    rows.append(dict(study=kind, scorable=len(s),
                     mean_R=round(float(s.R.mean()), 4), mean_ctl=round(float(s.ctl.mean()), 4),
                     mean_excess=round(float(s.excess.mean()), 4),
                     top5pct_R=round(float(top.R.mean()), 4),
                     top5pct_ctl=round(float(top.ctl.mean()), 4),
                     top5pct_excess=round(float(top.excess.mean()), 4),
                     top5pct_stop=round(float(top.atr_stop.mean()), 2),
                     top5pct_trail_on=round(float(top.trail.mean()), 2)))
P = pd.DataFrame(rows)
print(P.to_string(index=False))
P.to_csv("results/xopt/o1_studies.csv", index=False)
print("\n  If the RETURN study's top cells carry a much larger CONTROL than the EXCESS study's, the")
print("  return objective bought drift and the excess objective refused it -- which is the whole")
print("  reason the objective was changed.")

L("O1.2  POPULATION TRANSFER -- research to locked, on EXCESS not on return")
rows = []
for kind in ("excess", "excess_pf", "return"):
    s = ok[(ok.study == kind) & np.isfinite(ok.get("excess_lock", pd.Series(dtype=float)))]
    if len(s) < 30:
        continue
    rows.append(dict(study=kind, n=len(s),
                     corr_R=round(float(s.R.corr(s.R_lock)), 3),
                     corr_excess=round(float(s.excess.corr(s.excess_lock)), 3),
                     pos_res=round(100 * float((s.excess > 0).mean()), 1),
                     pos_lock=round(100 * float((s.excess_lock > 0).mean()), 1),
                     top1_res=round(float(s.nlargest(max(1, len(s)//100), "excess").excess.mean()), 4),
                     top1_lock=round(float(s.nlargest(max(1, len(s)//100), "excess").excess_lock.mean()), 4),
                     pop_lock=round(float(s.excess_lock.mean()), 4)))
Q = pd.DataFrame(rows)
print(Q.to_string(index=False))
Q.to_csv("results/xopt/o1_transfer.csv", index=False)

L("O1.3  MARGINALS on the EXCESS study -- what the whole population says, never the top row")
s = ok[ok.study == "excess"]
for ax in ("side", "trail", "tighten", "flatten", "use_vol", "sess"):
    g = s.groupby(ax).agg(n=("excess", "size"), res=("excess", "mean"),
                          lock=("excess_lock", "mean"))
    print(f"  {ax:9s}: " + " | ".join(f"{i}: res {r.res:+.4f} lock {r.lock:+.4f} (n{int(r.n)})"
                                      for i, r in g.iterrows()))
for ax in ("atr_stop", "tgt_R", "vol_mult", "range_mult", "ema_pull"):
    q = pd.qcut(s[ax], 4, duplicates="drop")
    g = s.groupby(q, observed=True).agg(res=("excess", "mean"), lock=("excess_lock", "mean"))
    print(f"  {ax:11s}: " + " | ".join(f"{str(i.left)[:5]}-{str(i.right)[:5]}: {r.res:+.3f}/{r.lock:+.3f}"
                                       for i, r in g.iterrows()))

L("O1.4  THE FINALISTS -- chosen on research EXCESS, box edges flagged, locked NOT read here")
BOX = dict(ema_slow=(50, 400), ema_pull=(10, 150), ema_tight=(5, 60), atr_len=(7, 30),
           atr_stop=(0.15, 4.0), vol_mult=(0.0, 2.5), range_mult=(0.0, 1.6),
           wick_body=(0.75, 4.0), ambig=(0.0, 0.004), tighten_R=(0.5, 4.0), tgt_R=(1.0, 8.0))
fin = []
for kind, st in best.items():
    bp = dict(st.best_params)
    edges = [k for k, (lo, hi) in BOX.items() if k in bp and (abs(bp[k]-lo) < 1e-9 or abs(bp[k]-hi) < 1e-9)]
    fin.append(dict(study=kind, value=round(st.best_value, 4), edges=",".join(edges) or "-", **bp))
F = pd.DataFrame(fin)
print(F.to_string(index=False))
F.to_csv("results/xopt/o1_finalists.csv", index=False)
