"""OPTUNA on the V61 CVD rule with the SESSION AXIS OPEN -- objective: profit factor AND drawdown.

SEARCHED ON THE RESEARCH BLOCK ONLY. The locked block is computed for every trial and LOGGED, and
is never visible to the sampler. Finalists are read once at the end and then scored against a
random entry with their own geometry, because a search that can choose its session and its hold can
find "be in the market when the market went up" without finding a rule.

TWO OBJECTIVES, both counted as trials:
  PF     profit factor, with a floor on trades per year so it cannot buy a ratio with a tiny count
  RETDD  total points / max drawdown -- the direct statement of "more return, less drawdown"

WHAT THIS BRANCH HAS ALREADY MEASURED ABOUT DOING THIS (so the result is read in context):
  * V64 ran 6,000 Optuna trials on this exact rule and NOT ONE of six finalists beat the shipped
    presets out of sample; research Sharpe rose monotonically with search effort and locked Sharpe
    did not follow at all.
  * The MEDIAN-OF-FOLDS objective, adopted here precisely because raw return fails, was the WORST
    of the three: research +26.43% -> locked -0.07%.
  * corr(research, locked) over the exhaustive V61 grid was -0.026. A sampler concentrating in a
    good region can make that correlation look positive; that is a property of the sampler, not of
    the ranking.
So the prior is that this finds nothing that transfers. It is run because it was asked for, the
population shape is reported before any top row, and every finalist gets a control.
"""
from __future__ import annotations

import os
import sys
import time
import warnings

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import optuna                    # noqa: E402
import sess_core as S            # noqa: E402

warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.WARNING)
pd.set_option("display.width", 250)
OUT = os.path.join(ROOT, "results/v61sess")
os.makedirs(OUT, exist_ok=True)


def line(t):
    print("\n" + "=" * 126)
    print(t)
    print("=" * 126, flush=True)


print(__doc__)
t0 = time.time()
D = {15: S.build(15), 30: S.build(30)}
GC = {}


def gate_of(tf, piv, win):
    key = (tf, piv, win)
    if key not in GC:
        GC[key] = S.gate(D[tf], piv, win)[0]
    return GC[key]


YRS = {}
for tf in (15, 30):
    ix = D[tf]["ix"]
    m = D[tf]["blk"] == 0
    YRS[(tf, 0)] = (ix[m][-1] - ix[m][0]).days / 365.25
    m = D[tf]["blk"] == 1
    YRS[(tf, 1)] = (ix[m][-1] - ix[m][0]).days / 365.25


def score(p):
    tf = p["tf"]
    g = gate_of(tf, p["piv"], p["win"])
    t = S.run(D[tf], ent=p["ent"], exN=p["exn"], stop=p["stop"], tp=p["tp"], hold=480,
              piv_min=p["piv"], win_min=p["win"], touch=True,
              sess=p["sess"], s_start=p["sh"] * 60, s_stop=p["eh"] * 60, flat=p["flat"], g=g)
    out = {}
    for b in (0, 1):
        z = t[t.blk == b]
        if len(z) < 25:
            out[b] = None
            continue
        a = z.pts.to_numpy()
        cum = np.cumsum(a)
        dd = float(np.max(np.maximum.accumulate(cum) - cum))
        out[b] = dict(n=len(z), per_yr=len(z) / YRS[(tf, b)],
                      pf=float(a[a > 0].sum() / max(-a[a < 0].sum(), 1e-9)),
                      pts=float(a.sum()), dd=dd, ret_dd=float(a.sum() / max(dd, 1e-9)),
                      pct=float(z.pct.mean()), tot=float(z.pct.sum()),
                      winrate=float(100 * (a > 0).mean()))
    return out


MIN_YR = 40.0
LOG = []


def make_obj(kind):
    def obj(tr):
        p = dict(tf=tr.suggest_categorical("tf", [15, 30]),
                 ent=tr.suggest_int("ent", 10, 60),
                 exn=tr.suggest_int("exn", 8, 50),
                 stop=tr.suggest_float("stop", 1.0, 4.0),
                 tp=tr.suggest_categorical("tp", [0.0, 3.0, 4.0, 6.0, 8.0]),
                 piv=tr.suggest_categorical("piv", [30, 45, 60, 90, 120, 150]),
                 win=tr.suggest_categorical("win", [150, 300, 450, 600, 900, 1200]),
                 sess=tr.suggest_categorical("sess", [True, False]),
                 sh=tr.suggest_int("sh", 4, 12),
                 eh=tr.suggest_int("eh", 10, 20),
                 flat=tr.suggest_categorical("flat", [True, False]))
        if p["sess"] and p["eh"] <= p["sh"]:
            return -9.0
        r = score(p)
        rr, rl = r[0], r[1]
        if rr is None or rr["per_yr"] < MIN_YR:
            return -9.0
        LOG.append(dict(kind=kind, **p, r_pf=rr["pf"], r_retdd=rr["ret_dd"], r_n=rr["n"],
                        r_pyr=rr["per_yr"], r_tot=rr["tot"], r_dd=rr["dd"],
                        l_pf=(rl["pf"] if rl else np.nan), l_retdd=(rl["ret_dd"] if rl else np.nan),
                        l_tot=(rl["tot"] if rl else np.nan), l_n=(rl["n"] if rl else np.nan)))
        return rr["pf"] if kind == "PF" else rr["ret_dd"]
    return obj


N = 1200
BEST = {}
for kind in ("PF", "RETDD"):
    st = optuna.create_study(direction="maximize",
                             sampler=optuna.samplers.TPESampler(seed=11, multivariate=True))
    st.optimize(make_obj(kind), n_trials=N, show_progress_bar=False)
    BEST[kind] = (dict(st.best_params), st.best_value, st)
    print(f"  {kind:6s} {N} trials, best research objective {st.best_value:.4f}  "
          f"({time.time()-t0:.0f}s)")
L = pd.DataFrame(LOG)
L.to_csv(os.path.join(OUT, "optuna_trials.csv"), index=False)

line("POPULATION FIRST -- the shape of what was searched, before any top row")
for kind in ("PF", "RETDD"):
    z = L[L.kind == kind].dropna(subset=["l_pf"])
    print(f"  {kind:6s} scorable on both blocks {len(z):>5}   research PF>1 {100*(z.r_pf>1).mean():>5.1f}%   "
          f"locked PF>1 {100*(z.l_pf>1).mean():>5.1f}%")
    print(f"         corr(research PF, locked PF)  Pearson {z.r_pf.corr(z.l_pf):+.3f}   "
          f"Spearman {z.r_pf.corr(z.l_pf, method='spearman'):+.3f}")
    top = z.nlargest(max(1, len(z) // 100), "r_pf")
    print(f"         top 1% by research PF: research {top.r_pf.mean():.3f} -> locked {top.l_pf.mean():.3f}   "
          f"(whole population locked {z.l_pf.mean():.3f})")

line("THE FINALISTS, read ONCE on the locked block")
INC30 = dict(tf=30, ent=20, exn=20, stop=2.0, tp=0.0, piv=90, win=600, sess=False, sh=7, eh=11, flat=False)
INC15 = dict(INC30, tf=15)
USER30 = dict(INC30, sess=True, flat=True)
USER15 = dict(INC15, sess=True, flat=True)
cands = {"incumbent 30m as shipped": INC30, "incumbent 15m as shipped": INC15,
         "your config 30m": USER30, "your config 15m": USER15}
for kind in ("PF", "RETDD"):
    bp = dict(BEST[kind][0])
    bp["exn"] = bp.pop("exn")
    cands[f"Optuna {kind} optimum"] = bp
print(f"  {'configuration':30s} {'tf':>3} {'geometry':22s} {'session':16s} "
      f"{'blk':9s} {'n':>4} {'/yr':>4} {'PF':>6} {'total %':>8} {'maxDD $':>8} {'ret/DD':>7}")
fin = []
for nm, p in cands.items():
    r = score(p)
    geo = f"{p['ent']}/{p['exn']} {p['stop']:.1f}N tp{p['tp']:.0f}"
    ses = (f"{p['sh']:02d}-{p['eh']:02d}" + (" flat" if p["flat"] else "")) if p["sess"] else "all hours"
    for b, bn in ((0, "research"), (1, "locked")):
        if r[b] is None:
            continue
        x = r[b]
        fin.append(dict(cfg=nm, block=bn, **{f"m_{k}": v for k, v in x.items()}, **p))
        print(f"  {nm if b==0 else '':30s} {p['tf']:>3} {geo if b==0 else '':22s} "
              f"{ses if b==0 else '':16s} {bn:9s} {x['n']:>4} {x['per_yr']:>4.0f} {x['pf']:>6.3f} "
              f"{x['tot']:>+8.2f} {x['dd']*2:>8.0f} {x['ret_dd']:>7.2f}")
F = pd.DataFrame(fin)
F.to_csv(os.path.join(OUT, "finalists.csv"), index=False)

line("BOX EDGES -- an optimum sitting on a boundary is the search asking for a wider box")
for kind in ("PF", "RETDD"):
    bp = BEST[kind][0]
    edges = []
    for k, (lo, hi) in dict(ent=(10, 60), exn=(8, 50), stop=(1.0, 4.0), sh=(4, 12), eh=(10, 20)).items():
        v = bp[k]
        if abs(v - lo) < 1e-9 or abs(v - hi) < 1e-9:
            edges.append(f"{k}={v} at {'min' if abs(v-lo)<1e-9 else 'max'}")
    print(f"  {kind:6s} {bp}")
    print(f"         on the box edge: {', '.join(edges) if edges else 'none'}")
print(f"\n  runtime {time.time()-t0:.0f}s")
