"""G1 -- the bar-level screen on gold. Does ANY feature predict, and do anomalous bars differ?

No primary, so no Gate 1 to contaminate: this asks whether predictive content exists at all before
anything is built on top of it. The order is data admission, then features, then the causality
audit, then the IC screen with the overlap priced, then the anomaly question, then ONE read of each
reserved block.
"""
import os, sys, time, pickle
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xdata as X, xfeat as XF

RNG = np.random.default_rng(7)
pd.set_option("display.width", 235)
os.makedirs("results/xanom", exist_ok=True)
CACHE = "results/xanom/feat_cache.pkl"
L = lambda s: print("\n" + "=" * 116 + f"\n{s}\n" + "=" * 116)
print(__doc__)

L("G1.0  DATA ADMISSION -- the volume column, the two-provider alignment, the three blocks")
print(X.volume_defect().to_string(index=False))
print("\n  the clock conversion, proved rather than assumed (every neighbouring shift collapses):")
print(X.overlap_evidence().to_string(index=False))
B = X.blocks()
print()
for k in ("research", "locked", "forward"):
    f = B[k]
    print(f"  {k:9s} {len(f):7d} bars   {f.index[0]}  ->  {f.index[-1]}"
          + ("   [MT, a DIFFERENT PROVIDER, never searched]" if k == "forward" else "   [ISO]"))
print(f"  session split at {B['cut'].date()}")

L("G1.1  FEATURES -- fitted on RESEARCH, applied unchanged to LOCKED and FORWARD")
t0 = time.time()
if os.path.exists(CACHE):
    Z = pickle.load(open(CACHE, "rb"))
    print(f"  loaded cache")
else:
    iso = B["iso"]
    fit_mask = (iso.index < B["cut"]).to_numpy()
    Xi, Yi, fitted = XF.build(iso, fit_mask=fit_mask)
    print(f"  ISO built: {Xi.shape[1]} features, ffd d={fitted['ffd_d']}, "
          f"hmm means {[f'{m:.2e}' for m in fitted['hmm'].means()]}  ({time.time()-t0:.0f}s)")
    Xm, Ym, _ = XF.build(B["mt"], fit_mask=np.zeros(len(B["mt"]), bool), models=fitted)
    print(f"  MT built with the RESEARCH-FITTED models applied unchanged  ({time.time()-t0:.0f}s)")
    Z = dict(Xi=Xi, Yi=Yi, Xm=Xm, Ym=Ym, cut=B["cut"], iso_end=B["iso"].index[-1],
             ffd_d=fitted["ffd_d"], hmm_means=fitted["hmm"].means().tolist())
    pickle.dump(Z, open(CACHE, "wb"))
Xi, Yi, Xm, Ym = Z["Xi"], Z["Yi"], Z["Xm"], Z["Ym"]
CORE = [c for c in Xi.columns if not c.startswith("vd.")]
VD = [c for c in Xi.columns if c.startswith("vd.")]
print(f"  {len(CORE)} core features (run on BOTH feeds) + {len(VD)} volume-dependent (ISO only)")

res = (Xi.index < Z["cut"]).to_numpy()
loc = ~res
fwd = (Xm.index > Z["iso_end"]).to_numpy()
print(f"  research {res.sum():,}  locked {loc.sum():,}  forward {fwd.sum():,}")

L("G1.2  CAUSALITY -- the labels are FORWARD and the features are not")
for hz in XF.HORIZONS:
    a = Yi[f"y.ret{hz}"].to_numpy()
    c = Xi["trn.ret16"].to_numpy()
    m = np.isfinite(a) & np.isfinite(c)
    print(f"  h={hz:3d}: corr(trailing 16-bar move, FORWARD {hz}-bar return) = "
          f"{np.corrcoef(c[m], a[m])[0,1]:+.4f}   (a large positive number here would mean the "
          f"label is not forward)")
print(f"  label NaN tail per horizon: " +
      ", ".join(f"h{hz} {int(Yi[f'y.ret{hz}'].isna().sum())}" for hz in XF.HORIZONS))

L("G1.3  THE IC SCREEN -- research only, Newey-West for the overlap, beside a SHUFFLED TWIN")
rows = []
for col in CORE + VD:
    x = Xi[col].to_numpy(float)[res]
    for hz in XF.HORIZONS:
        for lab in ("ret", "rng"):
            y = Yi[f"y.{lab}{hz}"].to_numpy(float)[res]
            b, t = XF.newey_west_t(x, y, lag=hz)
            m = np.isfinite(x) & np.isfinite(y)
            if m.sum() < 500:
                continue
            ic = float(pd.Series(x[m]).corr(pd.Series(y[m]), method="spearman"))
            ysh = RNG.permutation(y[m])
            icsh = float(pd.Series(x[m]).corr(pd.Series(ysh), method="spearman"))
            rows.append(dict(feat=col, fam=col.split(".")[0], label=lab, h=hz, n=int(m.sum()),
                             ic=round(ic, 4), ic_shuf=round(icsh, 4), nw_t=round(t, 2)))
S = pd.DataFrame(rows)
S.to_csv("results/xanom/g1_ic.csv", index=False)
# Benjamini-Hochberg on the Newey-West t's, per label type
from scipy import stats as st
for lab in ("ret", "rng"):
    s = S[S.label == lab].copy()
    s["p"] = 2 * (1 - st.norm.cdf(np.abs(s.nw_t)))
    s = s.sort_values("p").reset_index(drop=True)
    q = 0.10
    thr = q * (np.arange(1, len(s) + 1)) / len(s)
    passed = s.p.to_numpy() <= thr
    k = int(np.max(np.flatnonzero(passed)) + 1) if passed.any() else 0
    print(f"\n  --- label = forward {lab}:  {len(s)} tests, BH q=0.10 keeps {k}")
    print(s.head(12)[["feat", "h", "n", "ic", "ic_shuf", "nw_t", "p"]].to_string(index=False))
    S.loc[S.label == lab, "bh_pass"] = False
    if k:
        S.loc[S.index.isin(s.index[:k].map(lambda i: S[(S.label == lab)].index[i])), "bh_pass"] = True

print("\n  mean |IC| by family against its own shuffled twin (research, pooled over horizons):")
print(S.groupby(["fam", "label"]).agg(n=("ic", "size"), mean_abs_ic=("ic", lambda z: np.abs(z).mean()),
                                      shuffled=("ic_shuf", lambda z: np.abs(z).mean()),
                                      best_t=("nw_t", lambda z: np.abs(z).max())).round(4).to_string())
