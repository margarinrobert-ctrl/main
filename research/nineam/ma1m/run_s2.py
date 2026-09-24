"""Read the sweep on the RESEARCH half only; declare the holdout picks before any is revealed."""
import os, sys, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import m_core as M
import na_core as N
from scipy.stats import spearmanr

z = np.load(os.path.join(HERE, "s1_sweep.npz"))
out, hsh, meta = z["out"].astype(np.float64), z["hsh"], z["meta"]
NC = len(out)
pid = np.arange(NC) // 48; g = (np.arange(NC) % 48) // 3; x = np.arange(NC) % 3
kf = meta[pid, 0]; ks = meta[pid, 1]; nf = meta[pid, 2]; ns = meta[pid, 3]

def block(o6):
    n = out[:, o6]; s = out[:, o6 + 1]; s2 = out[:, o6 + 2]; gw = out[:, o6 + 3]; gl = out[:, o6 + 4]
    with np.errstate(all="ignore"):
        mean = s / n; var = (s2 - n * mean ** 2) / (n - 1); t = mean / np.sqrt(var) * np.sqrt(n)
        pf = np.where(gl > 0, gw / gl, np.nan)
    return n, mean, pf, t
nR, mR, pfR, tR = block(0)
nH, mH, pfH, tH = block(6)

print("=" * 96); print(f"POPULATION -- {NC:,} configurations, RESEARCH half (first 46 of 92 sessions)"); print("=" * 96)
ok = nR >= 10
print(f"  configurations with >= 10 research trades: {ok.sum():,} ({ok.mean():.1%})")
print(f"  of those, profitable on research: {(mR[ok] > 0).mean():.1%}   PF >= 1.5: {(pfR[ok] >= 1.5).mean():.1%}   "
      f"median research PF {np.nanmedian(pfR[ok]):.3f}")
distinct = len(np.unique(hsh))
print(f"\n  DISTINCT trade sets among all {NC:,}: {distinct:,} -- the rest are the same trades under another name")
print(f"  distinct among the >= 10-trade configurations: {len(np.unique(hsh[ok])):,}")
for lab, k in [("nominal", NC), ("distinct", distinct)]:
    print(f"  E[max t | pure noise] over {k:>9,} {lab:8s} looks = {N.e_max_normal(k):.3f}   (detection needs 2.802)")

def marg(col, labels, name):
    d = pd.DataFrame({"k": col[ok], "m": mR[ok], "pf": pfR[ok], "p": mR[ok] > 0})
    r = d.groupby("k").agg(avg=("m", "mean"), pfmed=("pf", "median"), prof=("p", "mean"), cnt=("m", "size"))  # never name a column after a DataFrame method
    r.index = [labels[i] if labels is not None else i for i in r.index]
    print(f"\n  {name} -- config-mean research %/trade, median PF, share profitable")
    print("   " + "  ".join(f"{i}: {v.avg:+.4f}/{v.pfmed:.2f}/{v.prof:.0%}" for i, v in r.iterrows()))
    return r
rk = {}
rk["fast type"] = marg(kf, M.TYPES, "FAST TYPE")
rk["slow type"] = marg(ks, M.TYPES, "SLOW TYPE")
rk["fast len"] = marg(nf, None, "FAST LENGTH")
rk["slow len"] = marg(ns, None, "SLOW LENGTH")
rk["gate"] = marg(g, M.GATES, "GATE")
rk["exit"] = marg(x, M.EXITS, "EXIT")

# population transfer -- a population statistic, not a selection
both = ok & (nH >= 10)
pr = np.corrcoef(mR[both], mH[both])[0, 1]; sr = spearmanr(mR[both], mH[both]).statistic
top = both & (mR >= np.nanpercentile(mR[both], 99))
print(f"\n  TRANSFER over {both.sum():,} configs with >= 10 trades in both halves: corr(research, holdout) "
      f"{pr:+.3f} Pearson / {sr:+.3f} Spearman")
print(f"  research top 1%: research {np.nanmean(mR[top]):+.4f} -> holdout {np.nanmean(mH[top]):+.4f}   "
      f"(whole population holdout {np.nanmean(mH[both]):+.4f}; top-1% holdout-profitable {np.mean(mH[top] > 0):.0%})")

# ---------------------------------------------------------------- declared picks, BEFORE any reveal
print("\n" + "=" * 96); print("PICKS DECLARED FOR THE ONE HOLDOUT READ (holdout values not shown)"); print("=" * 96)
def row_of(kfi, ksi, a, b, gi, xi):
    p = np.flatnonzero((kf == kfi) & (ks == ksi) & (nf == a) & (ns == b) & (g == gi) & (x == xi))
    return int(p[0]) if len(p) else None
picks = {}
picks["A incumbent EMA13/EMA48 x3.5 cross-exit"] = row_of(0, 0, 13, 48, M.GATES.index("x3.5"), 1)
best = {k: int(np.argmax(v["avg"].to_numpy())) for k, v in rk.items()}
lab = {k: rk[k].index[best[k]] for k in rk}
fi, si = M.TYPES.index(lab["fast type"]), M.TYPES.index(lab["slow type"])
a, b = int(lab["fast len"]), int(lab["slow len"])
if b < a + 3:
    b = min(v for v in M.SLOW if v >= a + 3)
picks["B marginal consensus"] = row_of(fi, si, a, b, M.GATES.index(lab["gate"]), M.EXITS.index(lab["exit"]))
floor = nR >= 15                               # a TRADE FLOOR written into the rule (TEAM_TF_ML)
c = int(np.nanargmax(np.where(floor, tR, -np.inf)))
picks["C top research t, >= 15 research trades"] = c
for k, r in picks.items():
    print(f"  {k:42s} row {r}:  {M.TYPES[kf[r]]}{nf[r]} / {M.TYPES[ks[r]]}{ns[r]}  gate {M.GATES[g[r]]}  "
          f"exit {M.EXITS[x[r]]}   research n {int(nR[r])} %/tr {mR[r]:+.4f} PF {pfR[r]:.2f} t {tR[r]:.2f}")
json.dump(picks, open(os.path.join(HERE, "s2_picks.json"), "w"), indent=1)

print("\n  TOP 10 by research t (>= 15 research trades) -- the maximum of a large search, read as such:")
o = np.argsort(np.where(floor, -tR, np.inf))[:10]
for r in o:
    print(f"    {M.TYPES[kf[r]]:6s}{nf[r]:3d} / {M.TYPES[ks[r]]:6s}{ns[r]:3d}  {M.GATES[g[r]]:5s} exit {M.EXITS[x[r]]:5s}  "
          f"n {int(nR[r]):2d}  %/tr {mR[r]:+.4f}  PF {pfR[r]:5.2f}  t {tR[r]:.2f}")
