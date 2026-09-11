"""D7 -- the PORTABLE form of the 7-feature volatility score, and every constant a script needs.

A RANDOM FOREST CANNOT GO INTO PINE. `STUDY_V61_FEATURES_15M` hit this exactly and shipped a ridge
instead. So the model that scored IC 0.1407 is not the thing that can be written; what can be
written is a linear score with exported coefficients, a single-feature threshold, or a sign-aligned
count. All three are measured here, on the research block, against the RF that cannot ship -- and
the gap between them is part of the answer.

Every standardisation constant is taken from the RESEARCH block only and printed, because the Pine
has to carry them as literals and a script that standardises against its own visible history is a
different strategy on every chart.
"""
import pickle, sys, time
import numpy as np, pandas as pd, runpy
sys.path.insert(0, "research/v66")
import torch; torch.set_num_threads(1)

t0 = time.time(); pd.set_option("display.width", 210)
print(__doc__)
_m = runpy.run_path("research/v66/_mlmod.py")
oof, ic = _m["oof"], _m["ic"]
FE = pd.read_parquet("results/v66/events_features.parquet")
Z = pickle.load(open("results/v66/frozen.pkl", "rb"))
VOL = [c for c in Z["cols"] if c.startswith("vol.")]
R = FE[FE.blk == 0].reset_index(drop=True)
L = FE[FE.blk == 1].reset_index(drop=True)
y, yl = R.R.to_numpy(float), L.R.to_numpy(float)
rng = np.random.default_rng(777)
SEEDS = range(8)

def line(t):
    print("\n" + "=" * 118); print(t); print("=" * 118, flush=True)

line("D7.1  THE THREE PORTABLE FORMS against the forest that cannot ship")
rf = np.array([ic(oof(R, VOL, "rf", seed=s), y) for s in SEEDS])
rg = np.array([ic(oof(R, VOL, "ridge", seed=s), y) for s in SEEDS])
print(f"{'form':>34} {'mean IC':>9} {'sd':>8}")
print(f"{'random forest (cannot ship)':>34} {rf.mean():>9.4f} {rf.std(ddof=1):>8.4f}")
print(f"{'ridge on the same 7 (ships)':>34} {rg.mean():>9.4f} {rg.std(ddof=1):>8.4f}")

# univariate direction and IC, research only -- this is what a count form needs
line("D7.2  EACH FEATURE ALONE -- univariate Spearman on research, which fixes the count's signs")
uni = []
for c in VOL:
    x = R[c].to_numpy(float)
    r = float(pd.Series(x).corr(pd.Series(y), method="spearman"))
    uni.append(dict(feat=c, ic=r, sign=int(np.sign(r)), med=float(np.median(x)),
                    mean=float(np.mean(x)), sd=float(np.std(x, ddof=1))))
U = pd.DataFrame(uni).sort_values("ic", key=abs, ascending=False)
print(U.round(6).to_string(index=False))

line("D7.3  THE RIDGE, WITH THE CONSTANTS A SCRIPT MUST CARRY")
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
X = R[VOL].to_numpy(float)
sc = StandardScaler().fit(X)
w = _m["uniqueness"](R)
mdl = Ridge(alpha=5.0).fit(sc.transform(X), y, sample_weight=w)
print(f"  standardisation and coefficients, all fitted on RESEARCH ONLY:\n")
print(f"{'feature':>22} {'mean':>12} {'sd':>12} {'coef':>10} {'uni IC':>9}")
for c, m_, s_, b in zip(VOL, sc.mean_, np.sqrt(sc.var_), mdl.coef_):
    u = float(U[U.feat == c].ic.iloc[0])
    print(f"{c:>22} {m_:>12.6f} {s_:>12.6f} {b:>+10.5f} {u:>+9.4f}")
print(f"{'intercept':>22} {'':>12} {'':>12} {mdl.intercept_:>+10.5f}")
sr = mdl.predict(sc.transform(X))
sl = mdl.predict(sc.transform(L[VOL].to_numpy(float)))
print(f"\n  in-sample ridge score IC {ic(sr, y):.4f}   (OOF {rg.mean():.4f})")
flip = [c for c, b in zip(VOL, mdl.coef_)
        if np.sign(b) != np.sign(float(U[U.feat == c].ic.iloc[0]))]
print(f"  coefficients whose SIGN disagrees with their univariate IC: {len(flip)} of {len(VOL)}"
      + (f"  -> {', '.join(flip)}" if flip else ""))

line("D7.4  THE COUNT FORM -- sign-aligned, thresholds at the RESEARCH median")
cnt_r = np.zeros(len(R)); cnt_l = np.zeros(len(L))
for _, r_ in U.iterrows():
    c, sgn, med = r_.feat, r_["sign"], r_.med
    cnt_r += ((R[c].to_numpy(float) - med) * sgn > 0).astype(float)
    cnt_l += ((L[c].to_numpy(float) - med) * sgn > 0).astype(float)
print(f"{'T>=':>5} {'n res':>7} {'R/ev':>9} {'PF':>7} | {'n lock':>7} {'R/ev':>9} {'PF':>7}")
base_pf = y[y > 0].sum()/max(-y[y < 0].sum(), 1e-9)
lpf = yl[yl > 0].sum()/max(-yl[yl < 0].sum(), 1e-9)
print(f"{'off':>5} {len(y):>7} {y.mean():>9.4f} {base_pf:>7.3f} | {len(yl):>7} {yl.mean():>9.4f} "
      f"{lpf:>7.3f}")
crows = []
for T in range(3, 8):
    a, b = y[cnt_r >= T], yl[cnt_l >= T]
    if len(a) < 20:
        continue
    pa = a[a > 0].sum()/max(-a[a < 0].sum(), 1e-9)
    pb = b[b > 0].sum()/max(-b[b < 0].sum(), 1e-9) if len(b) > 5 else np.nan
    crows.append(dict(T=T, n=len(a), r=a.mean(), pf=pa, nl=len(b),
                      rl=b.mean() if len(b) else np.nan, pfl=pb))
    print(f"{T:>5} {len(a):>7} {a.mean():>9.4f} {pa:>7.3f} | {len(b):>7} "
          f"{(b.mean() if len(b) else np.nan):>9.4f} {pb:>7.3f}")

line("D7.5  THE RIDGE SCORE AS A GATE -- research, then the descriptive locked read")
print(f"{'keep':>6} {'thr':>10} | {'n res':>7} {'R/ev':>9} {'PF':>7} {'rand p':>8} | "
      f"{'n lock':>7} {'kept%':>7} {'R/ev':>9} {'PF':>7}")
print(f"{'off':>6} {'':>10} | {len(y):>7} {y.mean():>9.4f} {base_pf:>7.3f} {'':>8} | "
      f"{len(yl):>7} {'100.0':>7} {yl.mean():>9.4f} {lpf:>7.3f}")
grows = []
for keep in (0.7, 0.6, 0.5, 0.4, 0.3):
    thr = float(np.quantile(sr, 1 - keep))
    a = y[sr >= thr]; b = yl[sl >= thr]
    rc = np.array([y[rng.choice(len(y), len(a), replace=False)].mean() for _ in range(1000)])
    rp = float(np.mean(rc >= a.mean()))
    pa = a[a > 0].sum()/max(-a[a < 0].sum(), 1e-9)
    pb = b[b > 0].sum()/max(-b[b < 0].sum(), 1e-9) if len(b) > 5 else np.nan
    grows.append(dict(keep=keep, thr=thr, n=len(a), r=a.mean(), pf=pa, p=rp,
                      nl=len(b), keptl=len(b)/len(yl), rl=b.mean() if len(b) else np.nan, pfl=pb))
    print(f"{keep:>6.2f} {thr:>10.5f} | {len(a):>7} {a.mean():>9.4f} {pa:>7.3f} {rp:>8.3f} | "
          f"{len(b):>7} {100*len(b)/len(yl):>6.1f}% {(b.mean() if len(b) else np.nan):>9.4f} "
          f"{pb:>7.3f}")
G = pd.DataFrame(grows)
G.to_csv("results/v66/d7_ridge_gate.csv", index=False)
U.to_csv("results/v66/d7_univariate.csv", index=False)
pd.DataFrame(dict(feat=VOL, mean=sc.mean_, sd=np.sqrt(sc.var_), coef=mdl.coef_)).to_csv(
    "results/v66/d7_ridge_coefs.csv", index=False)
with open("results/v66/d7_const.pkl", "wb") as f:
    pickle.dump(dict(feats=VOL, mean=sc.mean_, sd=np.sqrt(sc.var_), coef=mdl.coef_,
                     intercept=float(mdl.intercept_), thr=G.set_index("keep").thr.to_dict(),
                     uni=U), f)
print(f"\n  research cells clearing a same-selectivity random filter at p<=0.05: "
      f"{int((G.p <= 0.05).sum())} of {len(G)}")
print(f"  locked PF at every rung: {', '.join(f'{v:.3f}' for v in G.pfl)}  "
      f"(base {lpf:.3f})")
print(f"\n[{time.time()-t0:.0f}s]")
