"""Bayesian optimisation of the Donchian breakout family on NQ 15m -- RESEARCH BLOCK ONLY -- over a
continuous space the 504,000-cell grid could not reach, then ONE locked read of the finalists with
the trial count stated. STUDY_V64 measured, on the V61 rule, that Optuna buys research score and
not locked score and that a widened box sends the optimum to its ceiling; this repeats the test
on the user's family with the session and the adaptive stop as axes, three objectives, two
samplers (TPE and a Gaussian-process sampler), fANOVA importance, and the box-edge check."""
import os, sys, warnings, time
import numpy as np, pandas as pd, optuna
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56", "research/v64", "research/inst"):
    sys.path.insert(0, os.path.join(ROOT, p))
import v61core as V, v64opt as O
optuna.logging.set_verbosity(optuna.logging.WARNING); warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
def line(t): print("\n" + "=" * 126 + f"\n{t}\n" + "=" * 126, flush=True)
t0 = time.time()
D = O.build(15); n = D["n"]; CUT = D["cut"]
RTH = (D["mod"] >= 570) & (D["mod"] < 930); ALL = np.ones(n, bool)
YR, YL = V.YEARS["res"], V.YEARS["lock"]
BOUNDS = dict(ent=(10, 120), exN=(5, 80), stop=(0.5, 4.0), tp=(1.0, 10.0), hold=(8, 960), ma_thr=(-1.0, 4.0), chop_thr=(30.0, 70.0))

def evaluate(p):
    ei = int(np.clip(p["ent"], O.CH_MIN, O.CH_MAX)) - O.CH_MIN; xi = int(np.clip(p["exN"], O.CH_MIN, O.CH_MAX)) - O.CH_MIN
    gate = RTH if p["sess"] == 1 else ALL
    stop = float(p["stop"]); tp = float(p["tp"]) if p["use_tp"] else 0.0
    return O._walk(D["o"], D["h"], D["l"], D["c"], D["atr"], D["calm"], D["ent_all"][ei], D["exl_all"][xi], gate,
                   D["d_ma"], D["chop"], D["psh_ok"], int(CUT), stop, stop - 1.0 if p["adapt"] else stop, tp, int(p["hold"]),
                   1 if p["use_ma"] else 0, float(p["ma_thr"]), 1 if p["use_chop"] else 0, float(p["chop_thr"]),
                   1 if p["psh"] else 0, V.COST, V.SLIP, int(D["last_bar"]))
def stats(pct, blk, sig):
    out = {}
    for b, nm, yrs in ((0, "res", YR), (1, "lock", YL)):
        q = pct[blk == b]
        if len(q) < 3: out[nm] = dict(n=len(q), pf=np.nan, tot=np.nan, tpy=len(q) / yrs, sh=np.nan); continue
        d = pd.Series(q).groupby(sig[blk == b] // 26).sum()
        out[nm] = dict(n=len(q), pf=q[q > 0].sum() / max(1e-9, -q[q <= 0].sum()), tot=q.sum(), tpy=len(q) / yrs,
                       sh=np.sqrt(252) * d.mean() / d.std() if len(d) > 3 and d.std() > 0 else np.nan)
    return out
def suggest(tr):
    return dict(sess=tr.suggest_categorical("sess", [0, 1]), ent=tr.suggest_int("ent", *BOUNDS["ent"]), exN=tr.suggest_int("exN", *BOUNDS["exN"]),
                stop=tr.suggest_float("stop", *BOUNDS["stop"]), use_tp=tr.suggest_categorical("use_tp", [0, 1]), tp=tr.suggest_float("tp", *BOUNDS["tp"]),
                hold=tr.suggest_int("hold", *BOUNDS["hold"], log=True), adapt=tr.suggest_categorical("adapt", [0, 1]),
                use_ma=tr.suggest_categorical("use_ma", [0, 1]), ma_thr=tr.suggest_float("ma_thr", *BOUNDS["ma_thr"]),
                use_chop=tr.suggest_categorical("use_chop", [0, 1]), chop_thr=tr.suggest_float("chop_thr", *BOUNDS["chop_thr"]),
                psh=tr.suggest_categorical("psh", [0, 1]))
LOG = []   # every trial: params + research + locked (locked is NEVER used by an objective)
def make_obj(kind):
    def obj(tr):
        p = suggest(tr); R, pct, blk, sig = evaluate(p); s = stats(pct, blk, sig)
        LOG.append(dict(study=kind, **p, **{f"{k}_res": v for k, v in s["res"].items()}, **{f"{k}_lock": v for k, v in s["lock"].items()}))
        r = s["res"]
        if r["n"] < 40: return -1e3
        if kind == "total": return r["tot"]
        if kind == "pf100": return r["pf"] if r["tpy"] >= 100 else -1e3
        if kind == "sharpe": return r["sh"] if np.isfinite(r["sh"]) else -1e3
        if kind == "gp_total": return r["tot"]
    return obj
line("THE USER'S CELL and the grid's envelope, for reference")
cell = dict(sess=1, ent=55, exN=30, stop=1.5, use_tp=0, tp=0.0, hold=480, adapt=1, use_ma=1, ma_thr=2.0, use_chop=1, chop_thr=40.0, psh=0)
R, pct, blk, sig = evaluate(cell); s = stats(pct, blk, sig)
print(f"  cell: research n {s['res']['n']} PF {s['res']['pf']:.3f} total {s['res']['tot']:+.2f}% Sharpe {s['res']['sh']:.2f} | locked n {s['lock']['n']} PF {s['lock']['pf']:.3f} total {s['lock']['tot']:+.2f}% Sharpe {s['lock']['sh']:.2f}")
STUDIES = {}
for kind, sampler, ntr in (("total", optuna.samplers.TPESampler(seed=7, multivariate=True), 1200),
                           ("pf100", optuna.samplers.TPESampler(seed=8, multivariate=True), 1200),
                           ("sharpe", optuna.samplers.TPESampler(seed=9, multivariate=True), 1200),
                           ("gp_total", optuna.samplers.GPSampler(seed=10), 100)):
    st = optuna.create_study(direction="maximize", sampler=sampler); st.optimize(make_obj(kind), n_trials=ntr, show_progress_bar=False)
    STUDIES[kind] = st; print(f"  study {kind:9s} {ntr:>5} trials  best research objective {st.best_value:+.3f}   ({time.time()-t0:.0f}s)", flush=True)
L = pd.DataFrame(LOG); L.to_parquet("results/inst/bayesopt_trials.parquet")
line("A. THE TRIAL POPULATIONS -- research vs locked over every trial (the locked column was never an objective)")
for kind, g in L.groupby("study"):
    g = g[g.n_res >= 40]
    print(f"  {kind:9s}: {len(g):>5} scorable trials; profitable on research {100*(g.tot_res>0).mean():.1f}%, on locked {100*(g.tot_lock>0).mean():.1f}%; "
          f"corr(research total, locked total) {g[['tot_res','tot_lock']].corr().iloc[0,1]:+.3f}, corr(PF) {g[['pf_res','pf_lock']].corr().iloc[0,1]:+.3f}; "
          f"top decile by research total: locked total mean {g.nlargest(len(g)//10, 'tot_res').tot_lock.mean():+.2f}% vs all {g.tot_lock.mean():+.2f}%")
line("B. THE FINALISTS -- best trial per study, ONE locked read each (multiplicity: 3,700 trials over 4 studies)")
hdr = f"  {'study':9s} {'sess':>4} {'ent':>4} {'exN':>4} {'stop':>5} {'tp':>5} {'hold':>5} {'ad':>2} {'ma':>6} {'chop':>6} {'psh':>3} | {'res n':>5} {'PF':>6} {'total':>8} {'Sh':>5} | {'lock n':>6} {'PF':>6} {'total':>8} {'Sh':>5}"
print(hdr)
def row(kind, p, s):
    print(f"  {kind:9s} {'RTH' if p['sess'] else 'all':>4} {p['ent']:>4} {p['exN']:>4} {p['stop']:>5.2f} {(p['tp'] if p['use_tp'] else 0):>5.1f} {p['hold']:>5} {p['adapt']:>2} "
          f"{(p['ma_thr'] if p['use_ma'] else -9):>6.2f} {(p['chop_thr'] if p['use_chop'] else 99):>6.1f} {p['psh']:>3} | {s['res']['n']:>5} {s['res']['pf']:>6.3f} {s['res']['tot']:>+8.2f} {s['res']['sh']:>5.2f} | "
          f"{s['lock']['n']:>6} {s['lock']['pf']:>6.3f} {s['lock']['tot']:>+8.2f} {s['lock']['sh']:>5.2f}")
row("cell", cell, stats(*evaluate(cell)[1:]))
edge = []
for kind, st in STUDIES.items():
    p = dict(st.best_params); p["tp"] = p.get("tp", 0.0)
    R, pct, blk, sig = evaluate(p); s = stats(pct, blk, sig); row(kind, p, s)
    for ax, (lo, hi) in BOUNDS.items():
        if ax == "tp" and not p["use_tp"]: continue
        if ax == "ma_thr" and not p["use_ma"]: continue
        if ax == "chop_thr" and not p["use_chop"]: continue
        v = p[ax]; span = hi - lo
        if v <= lo + 0.05 * span or v >= hi - 0.05 * span: edge.append(f"{kind}:{ax}={v:.2f} [{lo},{hi}]")
print("  parameters within 5% of a box edge: " + (", ".join(edge) if edge else "none"))
line("C. THE NEIGHBOURHOOD OF EACH FINALIST -- top-10 trials of each study, mean research -> locked")
for kind, st in STUDIES.items():
    g = L[(L.study == kind) & (L.n_res >= 40)]
    key = {"total": "tot_res", "gp_total": "tot_res", "pf100": "pf_res", "sharpe": "sh_res"}[kind]
    top = g.nlargest(10, key)
    print(f"  {kind:9s}: top-10 research PF {top.pf_res.mean():.3f} total {top.tot_res.mean():+.2f}% Sharpe {top.sh_res.mean():.2f}  ->  locked PF {top.pf_lock.mean():.3f} total {top.tot_lock.mean():+.2f}% Sharpe {top.sh_lock.mean():.2f}   "
          f"(locked-positive {100*(top.tot_lock>0).mean():.0f}%)")
line("D. fANOVA IMPORTANCE -- which axes carry the research objective (interaction-aware)")
for kind, st in STUDIES.items():
    try:
        imp = optuna.importance.get_param_importances(st, evaluator=optuna.importance.FanovaImportanceEvaluator(seed=1))
        print(f"  {kind:9s}: " + ", ".join(f"{k} {v:.3f}" for k, v in list(imp.items())[:8]))
    except Exception as e: print(f"  {kind}: importance failed ({type(e).__name__})")
line("E. TRANSFER of the research ranking, per study (Spearman research objective vs locked total)")
for kind, g in L.groupby("study"):
    g = g[g.n_res >= 40]; key = {"total": "tot_res", "gp_total": "tot_res", "pf100": "pf_res", "sharpe": "sh_res"}[kind]
    print(f"  {kind:9s}: Spearman {g[[key, 'tot_lock']].corr('spearman').iloc[0,1]:+.3f}   top-1% research -> locked total {g.nlargest(max(3, len(g)//100), key).tot_lock.mean():+.2f}% vs population {g.tot_lock.mean():+.2f}%")
print(f"\n  total runtime {time.time()-t0:.0f}s")
