"""Optuna over the continuous extension of the grid, RESEARCH half only.

Why it is worth running after an exhaustive grid (CLAUDE.md: a sampler cannot beat an exhaustive
search on the same space): the grid's SLOW-length marginal is best at its 250/300 EDGE, so the box
is widened to 600, lengths become free integers, and the cross reach free in 0.5-minute steps to
20 -- plus fANOVA importance, which a one-axis marginal cannot give. Objective = research t with a
TRADE FLOOR of 15 (the lesson TEAM_TF_ML paid for). Every trial's holdout is LOGGED, never used.
"""
import os, sys, time, json
os.environ.setdefault("OMP_NUM_THREADS", "2")
import numpy as np, pandas as pd, optuna
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import m_core as M

optuna.logging.set_verbosity(optuna.logging.WARNING)
B = M.Base()
m = len(B.side)

def evaluate(kf, nf, ks, ns, gate, xm):
    ageU = np.zeros(m, np.int64); ageD = np.zeros(m, np.int64); stS = np.zeros(m, np.bool_)
    xbO = np.zeros((3, m), np.int64); ptsO = np.zeros((3, m))
    M.pair_kernel(B.ma(kf, nf), B.ma(ks, ns), B.seg_lo, B.seg_sig, B.seg_hi, B.side, B.R, B.o, B.ent,
                  B.xb, B.pts, B.cost, ageU, ageD, stS, xbO, ptsO)
    cbs = np.array([max(1, int(round(gate / M.TF)))] if gate != "state" else [1], np.int64)
    out = np.zeros((6, 12)); hb = np.zeros(6, np.uint64)
    M.config_kernel(B.sig, B.side, B.is_res, B.ent, ageU, ageD, stS, xbO, ptsO, cbs, out, hb, 0)
    r = out[(0 if gate != "state" else 1) * 3 + ["off", "cross", "state"].index(xm)]
    def st(o6):
        n, s, s2, gw, gl = r[o6], r[o6 + 1], r[o6 + 2], r[o6 + 3], r[o6 + 4]
        if n < 2: return n, np.nan, np.nan, np.nan
        mu = s / n; sd = np.sqrt(max((s2 - n * mu * mu) / (n - 1), 1e-18))
        return n, mu, (gw / gl if gl > 0 else np.inf), mu / sd * np.sqrt(n)
    return st(0), st(6)

LOG = []
def objective(tr):
    kf = tr.suggest_categorical("fast_type", M.TYPES); ks = tr.suggest_categorical("slow_type", M.TYPES)
    nf = tr.suggest_int("fast_len", 2, 60); ns = tr.suggest_int("slow_len", nf + 3, 600)
    gm = tr.suggest_categorical("gate_mode", ["cross", "state"])
    gate = tr.suggest_float("cross_min", 0.5, 20.0, step=0.5) if gm == "cross" else "state"
    xm = tr.suggest_categorical("exit", M.EXITS)
    (nR, mR, pfR, tR), (nH, mH, pfH, tH) = evaluate(kf, nf, ks, ns, gate, xm)
    LOG.append(dict(trial=tr.number, fast_type=kf, fast_len=nf, slow_type=ks, slow_len=ns, gate=gate,
                    exit=xm, nR=nR, mR=mR, pfR=pfR, tR=tR, nH=nH, mH=mH, pfH=pfH, tH=tH))
    return tR if (nR >= 15 and np.isfinite(tR)) else -5.0

t0 = time.time()
st = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=7, multivariate=True))
st.optimize(objective, n_trials=3000)
df = pd.DataFrame(LOG); df.to_csv(os.path.join(HERE, "o1_trials.csv"), index=False)
print(f"3,000 trials in {time.time()-t0:.0f}s; best research t {st.best_value:.3f}")
bp = st.best_params; print("  best:", bp)
v = df[df.nR >= 15]
print(f"  population (n>=15): {len(v)} trials, research-profitable {np.mean(v.mR > 0):.1%}")
edge = {"slow_len": (v.loc[v.tR.idxmax(), "slow_len"], 600), "fast_len": (v.loc[v.tR.idxmax(), "fast_len"], 60)}
print(f"  box-edge check: best slow_len {edge['slow_len'][0]} of max 600, best fast_len {edge['fast_len'][0]} of max 60")
try:
    imp = optuna.importance.get_param_importances(st, evaluator=optuna.importance.FanovaImportanceEvaluator(seed=1))
    print("  fANOVA importance:", {k: round(v_, 3) for k, v_ in imp.items()})
except Exception as e:
    print("  fANOVA failed:", e)
json.dump(dict(best=bp, value=st.best_value), open(os.path.join(HERE, "o1_best.json"), "w"), indent=1)
