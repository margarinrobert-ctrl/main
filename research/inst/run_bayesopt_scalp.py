"""Optuna on the Donchian family under the user's constraints: entries 07:00-11:00 New York, hold
capped at FOUR HOURS, 5- or 15-minute bars. Research block only; three objectives; finalists read
ONCE on locked and scored against a random entry inside the same window at the same rate.
STUDY_V30 did this on the Turtle: 76-83% of research trials profitable, 2-71% on locked."""
import os, sys, warnings, time
import numpy as np, pandas as pd, optuna
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56", "research/v64", "research/inst"):
    sys.path.insert(0, os.path.join(ROOT, p))
import v61core as V, v64opt as O
optuna.logging.set_verbosity(optuna.logging.WARNING); warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
def line(t): print("\n" + "=" * 126 + f"\n{t}\n" + "=" * 126, flush=True)
t0 = time.time()
DD = {tf: O.build(tf) for tf in (5, 15)}
for tf, D in DD.items():
    D["win"] = (D["mod"] >= 7 * 60) & (D["mod"] < 11 * 60)
    print(f"  tf {tf}: {D['n']:,} bars, window bars {int(D['win'].sum()):,}  ({time.time()-t0:.0f}s)", flush=True)
YR, YL = V.YEARS["res"], V.YEARS["lock"]
BOUNDS = dict(ent=(5, 120), exN=(3, 80), stop=(0.5, 4.0), tp=(0.5, 6.0), hold_min=(5, 240), ma_thr=(-1.0, 4.0), chop_thr=(30.0, 70.0))
def evaluate(p):
    D = DD[p["tf"]]; ei = int(np.clip(p["ent"], O.CH_MIN, O.CH_MAX)) - O.CH_MIN; xi = int(np.clip(p["exN"], O.CH_MIN, O.CH_MAX)) - O.CH_MIN
    stop = float(p["stop"]); tp = float(p["tp"]) if p["use_tp"] else 0.0; hold = max(1, int(round(p["hold_min"] / p["tf"])))
    return D, O._walk(D["o"], D["h"], D["l"], D["c"], D["atr"], D["calm"], D["ent_all"][ei], D["exl_all"][xi], D["win"], D["d_ma"], D["chop"], D["psh_ok"], int(D["cut"]),
                      stop, stop - 1.0 if p["adapt"] else stop, tp, hold, 1 if p["use_ma"] else 0, float(p["ma_thr"]), 1 if p["use_chop"] else 0, float(p["chop_thr"]),
                      1 if p["psh"] else 0, V.COST, V.SLIP, int(D["last_bar"]))
def stats(pct, blk, sig, tf):
    out = {}; bpd = 390 // tf
    for b, nm, yrs in ((0, "res", YR), (1, "lock", YL)):
        q = pct[blk == b]
        if len(q) < 3: out[nm] = dict(n=len(q), pf=np.nan, tot=np.nan, tpy=len(q) / yrs, sh=np.nan, win=np.nan); continue
        d = pd.Series(q).groupby(sig[blk == b] // bpd).sum()
        out[nm] = dict(n=len(q), pf=q[q > 0].sum() / max(1e-9, -q[q <= 0].sum()), tot=q.sum(), tpy=len(q) / yrs, win=100 * (q > 0).mean(),
                       sh=np.sqrt(252) * d.mean() / d.std() if len(d) > 3 and d.std() > 0 else np.nan)
    return out
def suggest(tr):
    return dict(tf=tr.suggest_categorical("tf", [5, 15]), ent=tr.suggest_int("ent", *BOUNDS["ent"]), exN=tr.suggest_int("exN", *BOUNDS["exN"]),
                stop=tr.suggest_float("stop", *BOUNDS["stop"]), use_tp=tr.suggest_categorical("use_tp", [0, 1]), tp=tr.suggest_float("tp", *BOUNDS["tp"]),
                hold_min=tr.suggest_int("hold_min", *BOUNDS["hold_min"], log=True), adapt=tr.suggest_categorical("adapt", [0, 1]),
                use_ma=tr.suggest_categorical("use_ma", [0, 1]), ma_thr=tr.suggest_float("ma_thr", *BOUNDS["ma_thr"]),
                use_chop=tr.suggest_categorical("use_chop", [0, 1]), chop_thr=tr.suggest_float("chop_thr", *BOUNDS["chop_thr"]), psh=tr.suggest_categorical("psh", [0, 1]))
LOG = []
def make_obj(kind):
    def obj(tr):
        p = suggest(tr); D, (R, pct, blk, sig) = evaluate(p); s = stats(pct, blk, sig, p["tf"])
        LOG.append(dict(study=kind, **p, **{f"{k}_res": v for k, v in s["res"].items()}, **{f"{k}_lock": v for k, v in s["lock"].items()}))
        r = s["res"]
        if r["n"] < 40: return -1e3
        if kind == "total": return r["tot"]
        if kind == "pf100": return r["pf"] if r["tpy"] >= 100 else -1e3
        return r["sh"] if np.isfinite(r["sh"]) else -1e3
    return obj
line("BASELINE -- the user's cell under the constraints (07:00-11:00 entries, 4h cap), and the window itself")
cell = dict(tf=15, ent=55, exN=30, stop=1.5, use_tp=0, tp=0.0, hold_min=240, adapt=1, use_ma=1, ma_thr=2.0, use_chop=1, chop_thr=40.0, psh=0)
D, (R, pct, blk, sig) = evaluate(cell); s = stats(pct, blk, sig, 15)
print(f"  cell 07-11/4h: research n {s['res']['n']} PF {s['res']['pf']:.3f} total {s['res']['tot']:+.2f}% | locked n {s['lock']['n']} PF {s['lock']['pf']:.3f} total {s['lock']['tot']:+.2f}%")
for tf in (5, 15):
    base = dict(tf=tf, ent=20, exN=10, stop=1.5, use_tp=0, tp=0.0, hold_min=240, adapt=0, use_ma=0, ma_thr=0, use_chop=0, chop_thr=99, psh=0)
    D, (R, pct, blk, sig) = evaluate(base); s = stats(pct, blk, sig, tf)
    print(f"  plain Donchian 20/10, 1.5N, 4h cap, {tf}m: research n {s['res']['n']} PF {s['res']['pf']:.3f} total {s['res']['tot']:+.2f}% | locked n {s['lock']['n']} PF {s['lock']['pf']:.3f} total {s['lock']['tot']:+.2f}%")
STUDIES = {}
for kind, seed in (("total", 7), ("pf100", 8), ("sharpe", 9)):
    st = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed, multivariate=True)); st.optimize(make_obj(kind), n_trials=1200, show_progress_bar=False)
    STUDIES[kind] = st; print(f"  study {kind:7s} 1200 trials  best research objective {st.best_value:+.3f}   ({time.time()-t0:.0f}s)", flush=True)
L = pd.DataFrame(LOG); L.to_parquet("results/inst/bayesopt_scalp_trials.parquet")
line("A. THE TRIAL POPULATIONS -- research vs locked over every trial")
for kind, g in L.groupby("study"):
    g = g[g.n_res >= 40]
    print(f"  {kind:7s}: {len(g):>5} scorable; profitable on research {100*(g.tot_res>0).mean():.1f}%, on locked {100*(g.tot_lock>0).mean():.1f}%; median research PF {g.pf_res.median():.3f}, locked {g.pf_lock.median():.3f}; "
          f"corr(total) {g[['tot_res','tot_lock']].corr().iloc[0,1]:+.3f}; top decile by research total -> locked {g.nlargest(len(g)//10,'tot_res').tot_lock.mean():+.2f}% vs all {g.tot_lock.mean():+.2f}%; by tf: " + ", ".join(f"{k}m {len(v)}" for k, v in g.groupby('tf')))
line("B. THE FINALISTS -- best trial per study, ONE locked read each (3,600 trials of multiplicity)")
print(f"  {'study':7s} {'tf':>3} {'ent':>4} {'exN':>4} {'stop':>5} {'tp':>5} {'hold':>5} {'ad':>2} {'ma':>6} {'chop':>6} {'psh':>3} | {'res n':>5} {'PF':>6} {'win%':>5} {'total':>8} {'Sh':>5} | {'lock n':>6} {'PF':>6} {'win%':>5} {'total':>8} {'Sh':>5} | cost/stop")
def row(kind, p):
    D, (R, pct, blk, sig) = evaluate(p); s = stats(pct, blk, sig, p["tf"]); r, l = s["res"], s["lock"]
    atr_med = np.nanmedian(D["atr"][D["win"]]); cr = 100 * (2 * V.COST + 2 * V.SLIP) / (p["stop"] * atr_med)
    print(f"  {kind:7s} {p['tf']:>3} {p['ent']:>4} {p['exN']:>4} {p['stop']:>5.2f} {(p['tp'] if p['use_tp'] else 0):>5.1f} {p['hold_min']:>5} {p['adapt']:>2} {(p['ma_thr'] if p['use_ma'] else -9):>6.2f} {(p['chop_thr'] if p['use_chop'] else 99):>6.1f} {p['psh']:>3} | "
          f"{r['n']:>5} {r['pf']:>6.3f} {r['win']:>5.1f} {r['tot']:>+8.2f} {r['sh']:>5.2f} | {l['n']:>6} {l['pf']:>6.3f} {l['win']:>5.1f} {l['tot']:>+8.2f} {l['sh']:>5.2f} | {cr:4.0f}%")
    return p
row("cell", cell); FIN = {}
edge = []
for kind, st in STUDIES.items():
    p = dict(st.best_params); FIN[kind] = row(kind, p)
    for ax, (lo, hi) in BOUNDS.items():
        if (ax == "tp" and not p["use_tp"]) or (ax == "ma_thr" and not p["use_ma"]) or (ax == "chop_thr" and not p["use_chop"]): continue
        v = p[ax]; span = hi - lo
        if v <= lo + 0.05 * span or v >= hi - 0.05 * span: edge.append(f"{kind}:{ax}={v:.2f}")
print("  within 5% of a box edge: " + (", ".join(edge) if edge else "none"))
line("C. NEIGHBOURHOOD -- top-10 trials per study, research -> locked")
for kind in STUDIES:
    g = L[(L.study == kind) & (L.n_res >= 40)]; key = {"total": "tot_res", "pf100": "pf_res", "sharpe": "sh_res"}[kind]; top = g.nlargest(10, key)
    print(f"  {kind:7s}: research PF {top.pf_res.mean():.3f} total {top.tot_res.mean():+.2f}% Sh {top.sh_res.mean():.2f} -> locked PF {top.pf_lock.mean():.3f} total {top.tot_lock.mean():+.2f}% Sh {top.sh_lock.mean():.2f}  (locked-positive {100*(top.tot_lock>0).mean():.0f}%)")
line("D. RANDOM-ENTRY CONTROL inside 07:00-11:00, same geometry and rate, both blocks")
rng = np.random.default_rng(5)
def pf(q): return q[q > 0].sum() / max(1e-9, -q[q <= 0].sum())
print(f"  {'finalist':8s} {'block':8s} {'rule n':>6} {'PF':>6} {'total':>8} | {'random PF':>9} {'total':>8} {'p(PF)':>6} {'p(tot)':>6}")
for nm, p in [("cell", cell)] + list(FIN.items()):
    D, (R, pct, blk, sig) = evaluate(p); xi = int(np.clip(p["exN"], O.CH_MIN, O.CH_MAX)) - O.CH_MIN; stop = float(p["stop"]); tp = float(p["tp"]) if p["use_tp"] else 0.0; hold = max(1, int(round(p["hold_min"] / p["tf"])))
    for b, bn in ((0, "research"), (1, "locked")):
        q = pct[blk == b]; n_t = len(q)
        if n_t < 5: print(f"  {nm:8s} {bn:8s} {n_t:>6}  (too few)"); continue
        ar = np.arange(D["n"]); elig = np.flatnonzero(D["win"] & (ar >= 1000) & (ar < D["last_bar"]) & ((ar < D["cut"]) if b == 0 else (ar >= D["cut"])))
        cp, ct = [], []
        for _ in range(200):
            bars = np.sort(elig[rng.random(len(elig)) < 1.6 * n_t / len(elig)])
            r = O._walk_at(D["o"], D["h"], D["l"], D["c"], D["atr"], D["calm"], D["exl_all"][xi], bars.astype(np.int64), stop, stop - 1.0 if p["adapt"] else stop, tp, hold, V.COST, V.SLIP, int(D["last_bar"]))
            r = r[np.isfinite(r)][:n_t]; cp.append(pf(r)); ct.append(r.sum())
        cp, ct = np.array(cp), np.array(ct)
        print(f"  {nm:8s} {bn:8s} {n_t:>6} {pf(q):>6.3f} {q.sum():>+7.2f}% | {np.median(cp):>9.3f} {np.median(ct):>+7.2f}% {np.mean(cp >= pf(q)):>6.3f} {np.mean(ct >= q.sum()):>6.3f}")
line("E. fANOVA and transfer")
for kind, st in STUDIES.items():
    try:
        imp = optuna.importance.get_param_importances(st, evaluator=optuna.importance.FanovaImportanceEvaluator(seed=1)); print(f"  {kind:7s} importance: " + ", ".join(f"{k} {v:.3f}" for k, v in list(imp.items())[:7]))
    except Exception as e: print(f"  {kind}: importance failed ({type(e).__name__})")
    g = L[(L.study == kind) & (L.n_res >= 40)]; key = {"total": "tot_res", "pf100": "pf_res", "sharpe": "sh_res"}[kind]
    print(f"          transfer Spearman {g[[key,'tot_lock']].corr('spearman').iloc[0,1]:+.3f}; top-1% research -> locked total {g.nlargest(max(3,len(g)//100), key).tot_lock.mean():+.2f}% vs population {g.tot_lock.mean():+.2f}%")
print(f"\n  total runtime {time.time()-t0:.0f}s")
