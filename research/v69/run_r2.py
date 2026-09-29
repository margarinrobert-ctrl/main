"""R2 -- Optuna over the strategy's OWN knobs, research block only, population before top row.

THE SPLIT. Research is the first 65% of session instances, locked the rest -- this branch's
convention. But note what that does and does not buy here: the file is `US100_LONG_15m`, which many
studies on this branch have already read, so the locked block is a SECOND read and is descriptive.
It is still worth computing, because a configuration that fails even a descriptive holdout has
failed something.

EVERY TRIAL'S LOCKED RESULT IS COMPUTED AND LOGGED AND NEVER SELECTED ON, so the transfer
correlation can be read over the sampled population -- which `STUDY_V64_OPTUNA` found more
informative than any finalist, because TPE concentrating in a good region makes the correlation look
better than the finalists behave.

THE SEARCH SPACE IS THE SCRIPT'S OWN INPUTS, not a new strategy: R:R, which sessions trade, the
weekday grid, the absolute range filter, the range PERCENTILE filter, and the two conviction tests.
The VIX filter is absent because it cannot be reproduced on this data.
"""
import os, sys, time
import numpy as np, pandas as pd, optuna
optuna.logging.set_verbosity(optuna.logging.WARNING)
sys.path.insert(0, "research/v69")
import v69core as V

t0 = time.time(); pd.set_option("display.width", 210)
def say(*a): print(*a, flush=True)
say(__doc__)
d = V.sessionize(V.load())
keys = np.sort(d.loc[d.sid >= 0, "skey"].unique())
cut = keys[int(0.65 * len(keys))]
say(f"[{time.time()-t0:5.1f}s] {len(d):,} bars, {len(keys):,} session instances, split key {cut}")

def split(t):
    return t[t.skey < cut], t[t.skey >= cut]

base = V.walk(d, cost_pts=V.RT_POINTS, **V.SHIPPED)
br, bl = split(base)
say(f"           SHIPPED baseline -- research n {len(br)} PF {V.stats(br)['pf']:.3f} "
    f"total {V.stats(br)['total']:+.2f} | locked n {len(bl)} PF {V.stats(bl)['pf']:.3f} "
    f"total {V.stats(bl)['total']:+.2f}")

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")
LOG = []
def objective(tr):
    sess = tuple(s for s in ("asia", "london", "ny") if tr.suggest_categorical(f"s_{s}", [0, 1]))
    if not sess:
        return -1e9
    cfg = dict(
        rr=tr.suggest_float("rr", 0.3, 5.0),
        sessions=sess,
        day={k: tr.suggest_categorical(f"d_{k}", ["Both", "Long", "Short", "Off"]) for k in DAYS},
        rng_min=tr.suggest_float("rng_min", 0.0, 60.0),
        rng_max=tr.suggest_float("rng_max", 0.0, 200.0),
        pen_pct=tr.suggest_float("pen_pct", 0.0, 60.0),
        close_loc=tr.suggest_float("close_loc", 0.0, 90.0),
        pct_max=tr.suggest_float("pct_max", 0.0, 100.0),
        pct_min=0.0, pct_look=tr.suggest_int("pct_look", 10, 100))
    if cfg["rng_max"] > 0 and cfg["rng_min"] > cfg["rng_max"]:
        return -1e9
    t = V.walk(d, cost_pts=V.RT_POINTS, **cfg)
    r, l = split(t)
    if len(r) < 150:
        LOG.append(dict(ok=0, n=len(r)))
        return -1e9
    sr, sl = V.stats(r), V.stats(l)
    LOG.append(dict(ok=1, n=len(r), nl=len(l), rr=cfg["rr"], sess="+".join(sess),
                    r_tot=sr["total"], r_pf=sr["pf"], r_pct=sr["pct"], r_win=sr["win"],
                    l_tot=sl["total"], l_pf=sl["pf"], l_pct=sl["pct"],
                    rng_min=cfg["rng_min"], rng_max=cfg["rng_max"], pen=cfg["pen_pct"],
                    cloc=cfg["close_loc"], pmax=cfg["pct_max"], plook=cfg["pct_look"],
                    **{f"d_{k}": cfg["day"][k] for k in DAYS}))
    return sr["total"]

N = 1200
say(f"\n[{time.time()-t0:5.1f}s] {N} TPE trials on RESEARCH TOTAL")
st = optuna.create_study(direction="maximize",
                         sampler=optuna.samplers.TPESampler(multivariate=True, seed=69))
for k in range(0, N, 200):
    st.optimize(objective, n_trials=min(200, N - k), show_progress_bar=False)
    say(f"      ... {min(k+200,N)}/{N}  best research total {st.best_value:+.2f}  "
        f"[{time.time()-t0:5.1f}s]")
L = pd.DataFrame(LOG); L.to_csv("results/v69/r2_trials.csv", index=False)
S = L[L.ok == 1].copy()
say(f"\n{'='*100}\nR2.1  POPULATION FIRST -- {len(S)} scorable of {len(L)}\n{'='*100}")
say(f"  research profitable {100*(S.r_tot>0).mean():.1f}%   locked profitable "
    f"{100*(S.l_tot>0).mean():.1f}%")
say(f"  corr(research %/trade, locked %/trade)  Pearson {S.r_pct.corr(S.l_pct):+.4f}  "
    f"Spearman {S.r_pct.corr(S.l_pct, method='spearman'):+.4f}")
top1 = S.nlargest(max(1, len(S)//100), "r_pct")
say(f"  top 1% by research: research {top1.r_pct.mean():+.5f} -> locked {top1.l_pct.mean():+.5f}   "
    f"whole population locked {S.l_pct.mean():+.5f}")
say(f"  top 100 by research: research {S.nlargest(100,'r_pct').r_pct.mean():+.5f} -> locked "
    f"{S.nlargest(100,'r_pct').l_pct.mean():+.5f}")

say(f"\n{'='*100}\nR2.2  MARGINAL AVERAGE PER AXIS -- research / locked %/trade\n{'='*100}")
say(f"  sessions traded:")
for s, g in S.groupby("sess"):
    if len(g) >= 20:
        say(f"    {s:>18}  n {len(g):>4}  research {g.r_pct.mean():+.5f}  "
            f"locked {g.l_pct.mean():+.5f}")
for ax, bins in (("rr", [0.3,0.8,1.5,2.5,5.0]), ("rng_min", [0,10,25,60]),
                 ("pen", [0,5,15,60]), ("cloc", [0,30,60,90]), ("pmax", [0,25,50,75,100])):
    q = pd.cut(S[ax], bins=bins, include_lowest=True)
    g = S.groupby(q, observed=True).agg(n=("r_pct","size"), r=("r_pct","mean"),
                                        l=("l_pct","mean"))
    say(f"  {ax}: " + "  ".join(f"{str(i):>12}={r.r:+.5f}/{r.l:+.5f}(n{int(r.n)})"
                                for i, r in g.iterrows()))
say(f"\n  weekday marginals (research %/trade by setting):")
for k in DAYS:
    g = S.groupby(f"d_{k}").r_pct.agg(["size", "mean"])
    say(f"    {k}: " + "  ".join(f"{i}={r['mean']:+.5f}(n{int(r['size'])})"
                                 for i, r in g.iterrows()))
try:
    imp = optuna.importance.get_param_importances(st)
    say(f"\n  fANOVA: " + "  ".join(f"{k} {v:.3f}" for k, v in list(imp.items())[:8]))
except Exception as e:
    say(f"  fANOVA unavailable: {e}")
say(f"\n[{time.time()-t0:5.1f}s] done")
