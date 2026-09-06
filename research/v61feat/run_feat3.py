"""WHAT CAN ACTUALLY SHIP -- a portable form of the meta layer, measured before it is written.

A RANDOM FOREST CANNOT GO INTO PINE. Two forms can:

  COUNT   each of the eight kept features cut at its RESEARCH median, oriented by the SIGN OF ITS
          RESEARCH IC, and simply counted 0..8. No weights to transcribe, nothing to overfit, and
          the branch has shipped this shape before (STUDY_TURTLE_15M's three gates counted into a
          monotone chop score, 3/3 PF 1.58 against 0/3 0.63).
  RIDGE   a linear score. Portable exactly -- standardise with the research mean and sd, multiply by
          eight coefficients, add. Every constant is exported below so the Pine is arithmetic and
          not an approximation.

Both are measured HERE, on research, with ONE locked read at the end, so the numbers that go in the
script header are the numbers the script produces rather than the forest's.

This file also exports the two constants sets a script needs to reproduce the causal features:
the frozen HMM parameters (so Pine can run the FILTERED forward recursion itself) and the
fixed-width fracdiff weights for d = 0.8.
"""
from __future__ import annotations

import json
import os
import pickle
import sys
import time
import warnings

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "research/v61sess"))
import v61feat as V          # noqa: E402
from sklearn.linear_model import Ridge          # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)
OUT = os.path.join(ROOT, "results/v61feat")


def line(t):
    print("\n" + "=" * 126)
    print(t)
    print("=" * 126, flush=True)


print(__doc__)
t0 = time.time()
rng = np.random.default_rng(3939)
FE = pd.read_parquet(os.path.join(OUT, "events_features.parquet"))
with open(os.path.join(OUT, "frozen.pkl"), "rb") as f:
    Z = pickle.load(f)
KEEP = Z["keep"]
IC = pd.read_csv(os.path.join(OUT, "ic.csv")).set_index("feature")
R = FE[FE.blk == 0].reset_index(drop=True)
L = FE[FE.blk == 1].reset_index(drop=True)
yR, yL = R.pct.to_numpy(), L.pct.to_numpy()

line("THE EIGHT KEPT FEATURES -- direction and cut, both taken from RESEARCH only")
print(f"  {'feature':22s} {'research IC':>12} {'favourable':>11} {'research median':>16} "
      f"{'passes on research':>19}")
SPEC = []
for f in KEEP:
    ic = float(IC.loc[f, "ic"])
    med = float(np.median(R[f].to_numpy()))
    fav = "high" if ic > 0 else "low"
    ok = (R[f].to_numpy() >= med) if ic > 0 else (R[f].to_numpy() <= med)
    SPEC.append(dict(feature=f, ic=ic, median=med, favourable=fav))
    print(f"  {f:22s} {ic:>+12.4f} {fav:>11} {med:>16.6f} {100*ok.mean():>18.1f}%")


def count_score(df):
    s = np.zeros(len(df))
    for sp in SPEC:
        x = df[sp["feature"]].to_numpy(float)
        s += (x >= sp["median"]).astype(float) if sp["ic"] > 0 else (x <= sp["median"]).astype(float)
    return s


cR, cL = count_score(R), count_score(L)

line("THE COUNT COMPOSITE -- monotone? and what does each rung earn?")
print(f"  {'count':>7} {'research n':>11} {'research %/ev':>14} {'locked n':>9} {'locked %/ev':>13}")
rows = []
for k in range(9):
    mr, ml = cR == k, cL == k
    rows.append(dict(count=k, nR=int(mr.sum()), rR=float(yR[mr].mean()) if mr.sum() else np.nan,
                     nL=int(ml.sum()), rL=float(yL[ml].mean()) if ml.sum() else np.nan))
    print(f"  {k:>7} {int(mr.sum()):>11} {(yR[mr].mean() if mr.sum() else np.nan):>14.4f} "
          f"{int(ml.sum()):>9} {(yL[ml].mean() if ml.sum() else np.nan):>13.4f}")
CT = pd.DataFrame(rows)
CT.to_csv(os.path.join(OUT, "count_ladder.csv"), index=False)
ok = CT.dropna(subset=["rR"])
print(f"\n  Spearman(count, research %/event) over the rungs: "
      f"{ok['count'].corr(ok.rR, method='spearman'):+.3f}")

line("THRESHOLD LADDER -- take the trade only at count >= T. ONE locked read at the end")
print(f"  {'T':>3} {'research n':>11} {'keeps':>7} {'%/ev':>9} {'PF':>7} {'vs random p':>12} "
      f"|| {'locked n':>9} {'keeps':>7} {'%/ev':>9} {'PF':>7} {'vs random p':>12}")


def pf(x):
    return float(x[x > 0].sum() / max(-x[x < 0].sum(), 1e-9))


lad = []
for T in range(3, 8):
    mr, ml = cR >= T, cL >= T
    if mr.sum() < 25:
        continue
    obsR = yR[mr].mean() - yR.mean()
    dR = np.array([yR[rng.choice(len(yR), int(mr.sum()), replace=False)].mean() - yR.mean()
                   for _ in range(3000)])
    pR = float(np.mean(dR >= obsR))
    if ml.sum() >= 15:
        obsL = yL[ml].mean() - yL.mean()
        dL = np.array([yL[rng.choice(len(yL), int(ml.sum()), replace=False)].mean() - yL.mean()
                       for _ in range(3000)])
        pL = float(np.mean(dL >= obsL))
    else:
        pL = np.nan
    lad.append(dict(T=T, nR=int(mr.sum()), keepR=float(mr.mean()), rR=float(yR[mr].mean()),
                    pfR=pf(yR[mr]), pR=pR, nL=int(ml.sum()), keepL=float(ml.mean()),
                    rL=float(yL[ml].mean()) if ml.sum() else np.nan,
                    pfL=pf(yL[ml]) if ml.sum() else np.nan, pL=pL))
    r = lad[-1]
    print(f"  {T:>3} {r['nR']:>11} {100*r['keepR']:>6.0f}% {r['rR']:>9.4f} {r['pfR']:>7.3f} "
          f"{r['pR']:>12.3f} || {r['nL']:>9} {100*r['keepL']:>6.0f}% {r['rL']:>9.4f} "
          f"{r['pfL']:>7.3f} {r['pL']:>12.3f}")
LAD = pd.DataFrame(lad)
LAD.to_csv(os.path.join(OUT, "count_threshold.csv"), index=False)
print(f"\n  base for reference: research {yR.mean():.4f} %/ev  PF {pf(yR):.3f}  n {len(yR)}   |   "
      f"locked {yL.mean():.4f}  PF {pf(yL):.3f}  n {len(yL)}")

line("RIDGE -- the portable linear alternative, with every constant exported")
sc = StandardScaler().fit(R[KEEP].to_numpy(float))
rd = Ridge(alpha=5.0).fit(sc.transform(R[KEEP].to_numpy(float)), yR)
sR = rd.predict(sc.transform(R[KEEP].to_numpy(float)))
sL = rd.predict(sc.transform(L[KEEP].to_numpy(float)))
print(f"  {'feature':22s} {'mean':>14} {'sd':>14} {'coefficient':>13}")
for f, m, s_, c_ in zip(KEEP, sc.mean_, np.sqrt(sc.var_), rd.coef_):
    print(f"  {f:22s} {m:>14.6f} {s_:>14.6f} {c_:>+13.6f}")
print(f"  {'intercept':22s} {'':>14} {'':>14} {rd.intercept_:>+13.6f}")
print(f"\n  {'keep':>6} {'research %/ev':>14} {'PF':>7} || {'locked n':>9} {'locked %/ev':>13} {'PF':>7} "
      f"{'vs random p':>12}")
for kf in (0.7, 0.6, 0.5, 0.4):
    thr = float(np.quantile(sR, 1 - kf))
    mr, ml = sR >= thr, sL >= thr
    if ml.sum() < 15:
        continue
    obsL = yL[ml].mean() - yL.mean()
    dL = np.array([yL[rng.choice(len(yL), int(ml.sum()), replace=False)].mean() - yL.mean()
                   for _ in range(3000)])
    print(f"  {kf:>6.0%} {yR[mr].mean():>14.4f} {pf(yR[mr]):>7.3f} || {int(ml.sum()):>9} "
          f"{yL[ml].mean():>13.4f} {pf(yL[ml]):>7.3f} {np.mean(dL >= obsL):>12.3f}")

line("CONSTANTS FOR THE SCRIPT")
hp = Z["hmm"]
o = hp["order"]
const = dict(
    features=KEEP,
    spec=[{k: (float(v) if isinstance(v, (int, float, np.floating)) else v) for k, v in sp.items()}
          for sp in SPEC],
    ridge=dict(mean=[float(x) for x in sc.mean_], sd=[float(x) for x in np.sqrt(sc.var_)],
               coef=[float(x) for x in rd.coef_], intercept=float(rd.intercept_),
               thresholds={f"{kf:.0%}": float(np.quantile(sR, 1 - kf)) for kf in (0.7, 0.6, 0.5, 0.4)}),
    hmm=dict(pi=[float(x) for x in hp["pi"][o]],
             A=[[float(hp["A"][o[i], o[j]]) for j in range(3)] for i in range(3)],
             mu=[[float(x) for x in hp["mu"][k]] for k in o],
             var=[[float(x) for x in hp["var"][k]] for k in o]),
    ffd=dict(d=float(Z["d"]), weights=[float(x) for x in V.ffd_weights(float(Z["d"]))]),
)
with open(os.path.join(OUT, "pine_constants.json"), "w") as f:
    json.dump(const, f, indent=1)
print(f"  HMM (states reordered bear/side/bull) -- pi {np.round(const['hmm']['pi'], 5)}")
print(f"    A = {np.round(const['hmm']['A'], 5).tolist()}")
print(f"    mu = {np.round(const['hmm']['mu'], 6).tolist()}")
print(f"    var = {np.round(const['hmm']['var'], 8).tolist()}")
print(f"  fracdiff d = {const['ffd']['d']}, {len(const['ffd']['weights'])} weights, "
      f"first five {np.round(const['ffd']['weights'][:5], 6).tolist()}")
print(f"\n  written to {os.path.join(OUT, 'pine_constants.json')}")
print(f"  runtime {time.time()-t0:.0f}s")
