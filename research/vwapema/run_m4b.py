"""M4b -- the walk-forward head-to-head re-read on the folds that POST-DATE the research cut.

M4.2's fixed arms (the published constants, and any cell chosen on the research block) had already
SEEN most of the training data of the early folds, so the comparison there is not clean. The gold
study hit the same thing and the fix is the same: report the per-fold numbers with their dates and
read the head-to-head only on the folds whose TEST window starts after the research/locked cut.
"""
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vecore as V, ve_markets as M

RNG = np.random.default_rng(909)
pd.set_option("display.width", 220)
print(__doc__)
MK = ("US100", "US30")
DS = {(k, sm): M.build(k, sess=sm) for k in MK for sm in ("ny", "utc")}
T = pd.read_parquet("results/vwapema/m2_trials.parquet")
PKEYS = list(V.PARAMS)
PUB = dict(p=dict(V.PARAMS), side=1, sess="ny", tgt_R=3.0, flatten=False)


def cfg_of(row):
    p = {k: (int(row[k]) if isinstance(V.PARAMS[k], int) else float(row[k])) for k in PKEYS}
    tg = row.get("tgt_R", 0.0)
    if not row.get("use_tgt", True) or not np.isfinite(float(tg)):
        tg = 0.0
    return dict(p=p, side=int(row["side"]), sess=str(row["sess"]), tgt_R=float(tg),
                flatten=bool(row["flatten"]))


def trades(mk, cfg):
    D = DS[(mk, cfg["sess"])]
    sig, _ = V.triggers(D, side=cfg["side"], p=cfg["p"])
    t = M.run(D, sig, side=cfg["side"], tgt_R=cfg["tgt_R"], flatten=cfg["flatten"], p=cfg["p"])
    t["ym"] = pd.DatetimeIndex(t.ts).normalize().values.astype("datetime64[M]")
    return t


rows = []
for mk in MK:
    cut = np.datetime64(DS[(mk, "ny")]["cut_date"][:7])
    s = T[(T.feed == mk) & (T.n_res >= 100)].drop_duplicates(
        subset=PKEYS + ["side", "sess", "tgt_R", "flatten"]).sample(400, random_state=3)
    pool = [cfg_of(r) for _, r in s.iterrows()]
    Mm = pd.concat([trades(mk, c).groupby("ym").R.mean().rename(i) for i, c in enumerate(pool)],
                   axis=1).sort_index()
    pubm = trades(mk, PUB).groupby("ym").R.mean()
    mons = Mm.index.to_numpy()
    for a in range(0, len(mons) - 48, 12):
        t0, t1 = mons[a + 36], mons[min(a + 48, len(mons) - 1)]
        trm = Mm.loc[(Mm.index >= mons[a]) & (Mm.index < t0)]
        tem = Mm.loc[(Mm.index >= t0) & (Mm.index < t1)]
        if len(trm) < 24 or len(tem) < 6:
            continue
        best = trm.mean().idxmax()
        rnd = int(RNG.integers(0, Mm.shape[1]))
        pm = pubm[(pubm.index >= t0) & (pubm.index < t1)]
        rows.append(dict(feed=mk, test_from=str(t0), test_to=str(t1),
                         post_cut=bool(t0 >= cut),
                         re_chosen=round(float(tem[best].mean()), 4),
                         random_cell=round(float(tem[rnd].mean()), 4),
                         published=round(float(pm.mean()), 4) if len(pm) else np.nan))
W = pd.DataFrame(rows)
print(W.to_string(index=False))
W.to_csv("results/vwapema/m4b_folds.csv", index=False)
print("\nHEAD-TO-HEAD, all folds vs POST-CUT folds only (mean OOS R per trade):")
for lbl, sub in (("all folds", W), ("post-cut only", W[W.post_cut])):
    g = sub.groupby("feed")[["re_chosen", "random_cell", "published"]].mean().round(4)
    g["folds"] = sub.groupby("feed").size()
    print(f"\n  --- {lbl}")
    print(g.to_string())
print("\nThe fixed arms saw the training data of the early folds; only the post-cut rows are a")
print("clean comparison, and there are too few of them to separate the arms.")
