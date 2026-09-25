"""Build the meta-layer features on a primary's event stream and AUDIT them before any score.
Usage: python run_feat0.py <primary-name from finalists.json | published>"""
import os, sys, json, time
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from research.ibopt import ibcore as C, ibfeat as IF   # noqa: E402

name = sys.argv[1] if len(sys.argv) > 1 else "published"
KW = {"published": dict(ib_min=60, retr=0.25, stopf=0.60, tgt=0.50, flat_min=955, side="both",
                        ib_atr_min=0.0, ib_atr_max=0.0)}
if name != "published":
    KW[name] = json.load(open("results/ibopt/finalists.json"))[name]["kw"]
kw = KW[name]
F = C.build("US30L")
t = C.run(F, **kw)
t0 = time.time()
X, meta = IF.build_features(F, t, mask_fit=(F["blk"] == 0), want_smoothed=True)
print(f"[{name}] events {len(X)} (research {int((X.blk==0).sum())}, locked {int((X.blk==1).sum())}), "
      f"{len(IF.feature_cols(X))} features in {len(set(c.split('.')[0] for c in IF.feature_cols(X)))} families, "
      f"d_ffd = {meta['d_ffd']}, {time.time()-t0:.0f}s")
# leakage diagnostic: how often do the FILTERED and SMOOTHED HMM labels agree?
DF = IF.daily_frame(F)
import v27hmm as H  # noqa
dc = DF["close"].to_numpy(); dret = np.zeros(len(dc)); dret[1:] = np.diff(np.log(dc))
rv20 = pd.Series(dret).rolling(20).std().to_numpy()
obs = np.column_stack([dret * 100.0, np.nan_to_num(rv20 * 100.0, nan=0.0)])
filt = H.posterior_filtered(obs, meta["hmm"]["pi"], meta["hmm"]["A"], meta["hmm"]["mu"], meta["hmm"]["var"])[:, meta["hmm"]["order"]]
agree = (filt.argmax(1) == meta["smoothed"].argmax(1)).mean() if meta["smoothed"] is not None else np.nan
print(f"  HMM filtered vs smoothed label agreement: {100*agree:.1f}%  (STUDY_V27: the gap is the leak; only FILTERED is used)")
bad, checked = IF.truncation_audit(F, t, X, meta, n_probe=40)
print(f"  TRUNCATION AUDIT: {bad} mismatches in {checked} feature-probe checks")
os.makedirs("results/ibopt", exist_ok=True)
X.to_parquet(f"results/ibopt/feat_{name}.parquet")
json.dump(dict(d_ffd=float(meta["d_ffd"]), hmm={k: np.asarray(v).tolist() for k, v in meta["hmm"].items()}),
          open(f"results/ibopt/meta_{name}.json", "w"), indent=1)
