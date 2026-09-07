"""N2 -- the model ladder on the S3 event stream, RESEARCH BLOCK ONLY.

Nine models from a ridge to a four-layer net, each fitted with purged embargoed folds, uniqueness
weights and an R objective, and each run again on SHUFFLED labels. Nothing here touches the locked
block; the locked read is N4 and it is one read.
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5"); sys.path.insert(0, "research/s3nn")
import numpy as np, pandas as pd
import nn_model as M

R = "results/s3nn/"
print(__doc__)
t0 = time.time()
pd.set_option("display.width", 240); pd.set_option("display.max_columns", 50)

names = pd.read_csv(R + "feature_names.csv", header=None)[0].tolist()
Xall = np.load(R + "X.npy")
T = pd.read_parquet(R + "train_events.parquet")

# research only
tr = T[T.blk == 0].reset_index(drop=True)
X = Xall[tr.sig.to_numpy()]
ok = np.isfinite(X).all(1)
tr, X = tr[ok].reset_index(drop=True), X[ok]
y = tr.R.to_numpy()
w = tr.u.to_numpy(); w = w / w.mean()
sig, ex = tr.sig.to_numpy(), tr.exit.to_numpy()
print(f"  training rows {len(tr)}   features {X.shape[1]}   effective n {w.sum()/w.max():.0f}")
print(f"  label = R earned;  mean {y.mean():+.4f}  sd {y.std():.3f}  p90 {np.percentile(y,90):.3f}")

folds = M.purged_folds(sig, ex, n_folds=5, embargo=0.01)
print(f"  5 purged embargoed folds: train sizes {[len(a) for a,_ in folds]}, "
      f"test sizes {[len(b) for _,b in folds]}")
print(f"  purging costs {1 - np.mean([len(a)/(len(tr)-len(b)) for a,b in folds]):.1%} of the "
      f"available training rows -- that is the price of not training on the answer")

print("\n" + "=" * 118)
print("N2.1  THE LADDER -- every model beside its own SHUFFLED-LABEL TWIN")
print("=" * 118)
from scipy.stats import spearmanr
real = M.run_oof(X, y, w, sig, ex, folds, shuffle=False)
print(f"  real ladder done {time.time()-t0:.0f}s")
fake = M.run_oof(X, y, w, sig, ex, folds, shuffle=True)
print(f"  shuffled twin done {time.time()-t0:.0f}s")

rows = []
base = dict(mean=y.mean(), pf=y[y > 0].sum() / -y[y < 0].sum(), win=(y > 0).mean(),
            p90=np.percentile(y, 90))
for nm in real:
    ic_r = spearmanr(real[nm], y).statistic
    ic_f = spearmanr(fake[nm], y).statistic
    d = dict(model=nm, ic=ic_r, ic_shuf=ic_f)
    for f in (0.3, 0.5, 0.7):
        a = M.keep_stats(y, real[nm], f)
        b = M.keep_stats(y, fake[nm], f)
        d[f"R@{int(f*100)}"] = a["mean"]; d[f"PF@{int(f*100)}"] = a["pf"]
        d[f"p90@{int(f*100)}"] = a["p90"]; d[f"shufPF@{int(f*100)}"] = b["pf"]
    rows.append(d)
L = pd.DataFrame(rows)
L.to_csv(R + "n2_ladder.csv", index=False)
print(f"\n  UNFILTERED base: R {base['mean']:+.4f}  PF {base['pf']:.3f}  "
      f"win {base['win']:.3f}  p90 {base['p90']:.3f}")
print(L.round(4).to_string(index=False))

beat = sum((L[f"shufPF@{f}"] > L[f"PF@{f}"]).sum() for f in (30, 50, 70))
tot = 3 * len(L)
print(f"\n  the SHUFFLED twin beats the real model in {beat} of {tot} cells ({beat/tot:.0%}); "
      f"above 50% means the noise floor is higher than the signal")
print(f"  IC: real mean {L.ic.mean():+.4f}   shuffled mean {L.ic_shuf.mean():+.4f}")

print("\n" + "=" * 118)
print("N2.2  DOES CAPACITY HELP?  -- the question the whole ladder exists to answer")
print("=" * 118)
cap = L[L.model.str.startswith(("ridge", "mlp"))][["model", "ic", "ic_shuf", "PF@50", "p90@50"]]
print(cap.round(4).to_string(index=False))
print("  V28 measured AUC falling monotonically with depth and a ridge/forest winning the ladder.")

np.save(R + "oof_real.npy", np.column_stack([real[k] for k in real]))
np.save(R + "oof_fake.npy", np.column_stack([fake[k] for k in fake]))
pd.Series(list(real)).to_csv(R + "model_names.csv", index=False, header=False)
tr.to_parquet(R + "n2_rows.parquet")
np.save(R + "n2_X.npy", X)
print(f"\ntotal {time.time()-t0:.0f}s")
