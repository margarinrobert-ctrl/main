"""O1 -- Optuna over a continuous space, RESEARCH BLOCK ONLY. Population before top row.

Every trial's locked result is computed and LOGGED and never used for selection, so the transfer
correlation can be measured over the sampled population at the end -- which is the diagnostic
`STUDY_V64_OPTUNA` found more informative than any finalist.
"""
import os, sys, time
import numpy as np, pandas as pd, optuna
optuna.logging.set_verbosity(optuna.logging.WARNING)
sys.path.insert(0, "research/v68")
import v68core as V

t0 = time.time(); pd.set_option("display.width", 200)
def say(*a): print(*a, flush=True)
say(__doc__)
D = V.load(15)
say(f"[{time.time()-t0:6.1f}s] {D['n']:,} bars, split {D['cut_day']}")
b = V.stats(V.run(D, block=0)); l = V.stats(V.run(D, block=1))
say(f"           BASELINE cell -- research n {b['n']} PF {b['pf']:.3f} %/ev {b['pct']:+.4f} "
    f"Sharpe {b['sharpe']:+.3f} | locked n {l['n']} PF {l['pf']:.3f} %/ev {l['pct']:+.4f}")

LOG = []
def objective(trial):
    cfg = dict(
        ent=trial.suggest_int("ent", 5, 60),
        exN=trial.suggest_int("exN", 5, 80),
        stop=trial.suggest_float("stop", 1.0, 8.0),
        tp=trial.suggest_float("tp", 0.0, 12.0),
        hold=trial.suggest_int("hold", 8, 480, log=True),
        s_start=trial.suggest_categorical("s_start", [540, 570, 600, 630]),
        s_stop=trial.suggest_categorical("s_stop", [780, 840, 900, 960]))
    t = V.run(D, **cfg)
    r = V.stats(t[t.blk == 0]); k = V.stats(t[t.blk == 1])
    yrs = 1.94
    if r["n"] < 60 or r["n"] / yrs < 40:
        LOG.append(dict(**cfg, ok=0, r_pct=np.nan, r_pf=np.nan, r_sh=np.nan,
                        l_pct=np.nan, l_pf=np.nan, n=r["n"]))
        return -1e9
    LOG.append(dict(**cfg, ok=1, r_pct=r["pct"], r_pf=r["pf"], r_sh=r["sharpe"],
                    l_pct=k["pct"], l_pf=k["pf"], n=r["n"]))
    return r["total"]

N = 1200
say(f"\n[{time.time()-t0:6.1f}s] {N} TPE trials on RESEARCH TOTAL, locked logged and never used")
st = optuna.create_study(direction="maximize",
                         sampler=optuna.samplers.TPESampler(multivariate=True, seed=7))
for k in range(0, N, 200):
    st.optimize(objective, n_trials=min(200, N - k), show_progress_bar=False)
    say(f"      ... {min(k+200,N)}/{N} trials  best research total {st.best_value:.2f}  "
        f"[{time.time()-t0:6.1f}s]")
L = pd.DataFrame(LOG)
L.to_csv("results/v68/o1_trials.csv", index=False)
S = L[L.ok == 1].copy()
say(f"\n[{time.time()-t0:6.1f}s] POPULATION FIRST -- {len(S)} scorable of {len(L)} trials")
say(f"  research profitable {100*(S.r_pct>0).mean():.1f}%   locked profitable "
    f"{100*(S.l_pct>0).mean():.1f}%")
say(f"  corr(research %/ev, locked %/ev)  Pearson {S.r_pct.corr(S.l_pct):+.4f}   "
    f"Spearman {S.r_pct.corr(S.l_pct, method='spearman'):+.4f}")
top = S.nlargest(max(1, len(S)//100), "r_pct")
say(f"  top 1% by research: research {top.r_pct.mean():+.4f} -> locked {top.l_pct.mean():+.4f}   "
    f"whole population locked mean {S.l_pct.mean():+.4f}")
say(f"  top 100 by research: research {S.nlargest(100,'r_pct').r_pct.mean():+.4f} -> locked "
    f"{S.nlargest(100,'r_pct').l_pct.mean():+.4f}")

say(f"\n[{time.time()-t0:6.1f}s] MARGINAL AVERAGE PER AXIS (research), never the top cell")
for ax, bins in (("ent", [5,10,15,25,40,60]), ("exN", [5,15,30,50,80]),
                 ("stop", [1,2,3,4,6,8]), ("tp", [0,1,2,3,5,12]),
                 ("hold", [8,24,96,240,480])):
    q = pd.cut(S[ax], bins=bins, include_lowest=True)
    g = S.groupby(q, observed=True).agg(n=("r_pct","size"), res=("r_pct","mean"),
                                        lock=("l_pct","mean"))
    say(f"  {ax}: " + "  ".join(f"{str(i):>12}={r.res:+.4f}/{r.lock:+.4f}(n{int(r.n)})"
                                for i, r in g.iterrows()))

say(f"\n[{time.time()-t0:6.1f}s] BOX EDGES -- did the optimum run to a wall?")
bp = st.best_params
lims = dict(ent=(5,60), exN=(5,80), stop=(1.0,8.0), tp=(0.0,12.0), hold=(8,480))
for k, (lo, hi) in lims.items():
    v = bp[k]
    frac = (v - lo) / (hi - lo)
    flag = "  <-- AT THE EDGE" if frac < 0.05 or frac > 0.95 else ""
    say(f"  {k:>6} = {v} in [{lo}, {hi}]  ({frac:.2f} of the range){flag}")
say(f"  session {bp['s_start']}-{bp['s_stop']}")

try:
    imp = optuna.importance.get_param_importances(st)
    say(f"\n  fANOVA importance: " + "  ".join(f"{k} {v:.3f}" for k, v in imp.items()))
except Exception as e:
    say(f"  fANOVA unavailable: {e}")
say(f"\n[{time.time()-t0:6.1f}s] done")
