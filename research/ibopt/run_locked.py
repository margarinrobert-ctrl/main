"""THE ONE LOCKED READ -- finalists, the meta layer, deflation, and a second reserved feed.

Everything above this file was research-only. This file reads US30_LONG_15m's locked block
(2022-06-27 .. 2025-07) ONCE for every declared candidate, then US30_ISO_15m (a different
provider, 2024-08 .. 2026-08) for the span it adds beyond the LONG file. Multiplicity is stated
first and every candidate is scored against the same three nulls it faced on research.

Usage: run_locked.py <meta-primary-name>
"""
import os, sys, json
import numpy as np, pandas as pd
from sklearn.linear_model import Ridge

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, "/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/mechanism-first-alpha/scripts")
from research.ibopt import ibcore as C, ibfeat as IF          # noqa: E402
from research.ibopt.run_gate1_finalists import always_side     # noqa: E402
import gates                                                    # noqa: E402

pd.set_option("display.width", 210)
meta_name = sys.argv[1] if len(sys.argv) > 1 else "retdd"
print(__doc__)
F = C.build("US30L")
fin = json.load(open("results/ibopt/finalists.json"))
fin["published"] = dict(kw=dict(ib_min=60, retr=0.25, stopf=0.60, tgt=0.50, flat_min=955, side="both",
                                ib_atr_min=0.0, ib_atr_max=0.0))
T = pd.read_parquet("results/ibopt/optuna_trials.parquet")
spec = json.load(open(f"results/ibopt/meta_spec_{meta_name}.json"))
looks = spec["looks"]
n_trials = len(T) + 4 + sum(looks.values())
print(f"  MULTIPLICITY: {len(T)} Optuna trials + 4 primaries at Gate 1 + {sum(looks.values())} meta-layer looks "
      f"({looks}) = {n_trials} looks before this read.\n")


def score_block(Fx, kw, blk):
    t = C.run(Fx, **kw); t = t[t.blk == blk].reset_index(drop=True)
    if len(t) < 10:
        return t, C.stats(t), np.nan, np.nan, np.nan
    st = C.stats(t)
    ctl = C.control(Fx, t.day.to_numpy(), draws=1000, **kw)
    al = always_side(Fx, t, kw)
    return t, st, float((ctl >= st["pct"]).mean()), float(np.median(ctl)), float(al.mean())


print("=" * 112); print("FINALISTS ON THE LOCKED BLOCK -- research beside locked, both nulls"); print("=" * 112)
rows = []
for nm, sp in fin.items():
    kw = sp["kw"]
    for blk, bn in ((0, "research"), (1, "LOCKED")):
        t, st, p, med, al = score_block(F, kw, blk)
        g = gates.primary_gate(t.pct.to_numpy() / 100.0) if len(t) >= 30 else dict(bootstrap_p_one_sided=np.nan)
        rows.append(dict(primary=nm, block=bn, n=st["n"], pct=st["pct"], tot=st["tot"], pf=st["pf"], win=st["win"],
                         ret_dd=st["ret_dd"], boot_p=g["bootstrap_p_one_sided"], p_entry=p, ctl_med=med, always=al))
Rf = pd.DataFrame(rows)
print(Rf.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
for nm in fin:
    a = Rf[(Rf.primary == nm)]
    r_, l_ = a[a.block == "research"].iloc[0], a[a.block == "LOCKED"].iloc[0]
    shape = "decays (right shape)" if l_.pct < r_.pct else "GROWS on locked (wrong shape)"
    print(f"  {nm:10s} research {r_.pct:+.4f} -> locked {l_.pct:+.4f}: {shape}")

# ---------------------------------------------------------------- the meta layer, one read
print("\n" + "=" * 112); print(f"THE META LAYER on [{meta_name}] -- ridge frozen on research, ONE read"); print("=" * 112)
X = pd.read_parquet(f"results/ibopt/feat_{meta_name}.parquet")
feats = spec["features"]
def ridge_score(df):
    Z = np.column_stack([((df[f].fillna(spec["fill_median"][f]) - spec["mean"][f]) / spec["sd"][f]).to_numpy() for f in feats])
    return Z @ np.array([spec["coef"][f] for f in feats]) + spec["intercept"]
L = X[X.blk == 1].reset_index(drop=True); Rr = X[X.blk == 0].reset_index(drop=True)
sL = ridge_score(L); yL = L.pct.to_numpy()
rng = np.random.default_rng(9)
rows = []
for kk, thr in spec["thresholds"].items():
    kf = int(kk) / 100
    m = sL >= thr; n = int(m.sum())
    if n < 10:
        rows.append(dict(keep=kf, kept_frac=n / len(L), n=n)); continue
    g = gates.meta_gate(yL / 100.0, sL, thr)
    nullv = np.array([yL[rng.choice(len(yL), n, replace=False)].mean() for _ in range(1000)])
    p = yL[m]
    rows.append(dict(keep=kf, kept_frac=n / len(L), n=n, base=yL.mean(), filtered=p.mean(), uplift=p.mean() - yL.mean(),
                     pf_base=float(yL[yL > 0].sum() / max(-yL[yL < 0].sum(), 1e-9)), pf_kept=float(p[p > 0].sum() / max(-p[p < 0].sum(), 1e-9)),
                     boot_p=g["bootstrap_p_one_sided"], rand_filter_p=float((nullv >= p.mean()).mean()),
                     total_base=yL.sum(), total_kept=p.sum()))
M = pd.DataFrame(rows)
print(M.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
print("  `kept_frac` against `keep` says whether the research score is CALIBRATED across the split (STUDY_AUTOBNN kept 105/105).")

# ---------------------------------------------------------------- deflation
print("\n" + "=" * 112); print("DEFLATION -- every look counted"); print("=" * 112)
best = fin[meta_name]["kw"]
tL = C.run(F, **best); tL = tL[tL.blk == 1]
sr = tL.pct.mean() / max(tL.pct.std(), 1e-9)
ok = T[T.n_res >= 150]
trial_sr = (ok.pct_res / 1.0).to_numpy()   # per-trade mean as a proxy; variance across trials in Sharpe units below
# per-trial Sharpe on research, estimated from mean/std of trade pct via total & n is unavailable -> use pct_res / typical sd
sd_typ = float(tL.pct.std())
var_trials = float(np.var(ok.pct_res.to_numpy() / sd_typ))
from scipy.stats import skew, kurtosis
d = gates.deflated_sharpe(sr, len(tL), n_trials, var_trials, skew=float(skew(tL.pct)), kurtosis=float(kurtosis(tL.pct, fisher=False)))
print(f"  locked per-trade Sharpe {sr:+.4f} on {len(tL)} trades; var of trial Sharpes {var_trials:.5f} over {len(ok)} scorable trials")
print(f"  DEFLATED SHARPE {d.get('dsr', float('nan')):.4f} against N = {n_trials} looks -> {d['verdict']}")
eff = gates.effective_trials(n_trials, 0.5)
d2 = gates.deflated_sharpe(sr, len(tL), eff, var_trials, skew=float(skew(tL.pct)), kurtosis=float(kurtosis(tL.pct, fisher=False)))
print(f"  at rho 0.5 effective N = {eff:.0f}: DSR {d2.get('dsr', float('nan')):.4f}")

# ---------------------------------------------------------------- second reserved feed
print("\n" + "=" * 112); print("US30_ISO_15m -- a different provider; only the span AFTER the LONG file ends is new"); print("=" * 112)
try:
    Fi = C.build("US30I")
    cut = np.datetime64("2025-07-16")
    new_days = np.flatnonzero(Fi["dates"] >= cut)
    print(f"  ISO sessions {Fi['D']}, of which {len(new_days)} postdate the LONG file")
    rows = []
    for nm, sp in fin.items():
        kw = sp["kw"]
        t = C.run(Fi, **kw); t = t[t.day.isin(new_days)].reset_index(drop=True)
        st = C.stats(t)
        if st["n"] >= 10:
            ctl = C.control(Fi, t.day.to_numpy(), draws=1000, **kw); al = always_side(Fi, t, kw)
            rows.append(dict(primary=nm, n=st["n"], pct=st["pct"], tot=st["tot"], pf=st["pf"], win=st["win"],
                             p_entry=float((ctl >= st["pct"]).mean()), ctl_med=float(np.median(ctl)), always=float(al.mean())))
        else:
            rows.append(dict(primary=nm, n=st["n"]))
    print(pd.DataFrame(rows).to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
except Exception as e:
    print(f"  unavailable: {e}")
Rf.to_csv("results/ibopt/locked_finalists.csv", index=False); M.to_csv(f"results/ibopt/locked_meta_{meta_name}.csv", index=False)
