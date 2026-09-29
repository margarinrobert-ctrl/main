"""M4 -- the three questions that all get called "overfitting", per feed.

`STUDY_VWAP_EMA_GOLD.md` section 21 separates them and they have different answers:
  1. IS THE RULE FITTED?          rolling walk-forward with NOTHING re-selected.
  2. IS THE SEARCH OVERFIT?       walk-forward with the selection RE-RUN inside every training
                                  fold, beside a RANDOM cell from the same pool and the author's
                                  fixed constants.
  3. WHAT IS P(OVERFIT)?          CSCV / PBO over a per-period return matrix and all C(S,S/2)
                                  symmetric splits (Bailey, Borwein, Lopez de Prado & Zhu).
Note the method finding from that study: symmetric CSCV CANNOT measure a FIXED cell's rank drop --
for every split the complement is also a split, so a fixed column's IS and OOS rank distributions
are identical by construction and both the difference of medians and the median pairwise drop are
identically zero. For a fixed cell read the rank DISPERSION and the walk-forward gap instead.
"""
import os, sys, itertools
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vecore as V, ve_markets as M

RNG = np.random.default_rng(909)
pd.set_option("display.width", 235)
print(__doc__)
MK = ("US100", "US30")
DS = {(k, sm): M.build(k, sess=sm) for k in MK for sm in ("ny", "utc")}
T = pd.read_parquet("results/vwapema/m2_trials.parquet")
FN = pd.read_csv("results/vwapema/m2_finalists.csv")
PKEYS = list(V.PARAMS)
L = lambda s: print("\n" + "=" * 116 + f"\n{s}\n" + "=" * 116)


def cfg_of(row):
    p = {k: (int(row[k]) if isinstance(V.PARAMS[k], int) else float(row[k])) for k in PKEYS}
    tg = row.get("tgt_R", 0.0)
    if not row.get("use_tgt", True) or not np.isfinite(float(tg)):
        tg = 0.0
    return dict(p=p, side=int(row["side"]), sess=str(row["sess"]),
                tgt_R=float(tg), flatten=bool(row["flatten"]))


PUB = dict(p=dict(V.PARAMS), side=1, sess="ny", tgt_R=3.0, flatten=False)


def trades(mk, cfg):
    D = DS[(mk, cfg["sess"])]
    sig, _ = V.triggers(D, side=cfg["side"], p=cfg["p"])
    t = M.run(D, sig, side=cfg["side"], tgt_R=cfg["tgt_R"], flatten=cfg["flatten"], p=cfg["p"])
    t["date"] = pd.DatetimeIndex(t.ts).normalize()
    t["ym"] = t.date.values.astype("datetime64[M]")
    return t


# ---- the pool: distinct sampled configurations from the search, per feed
POOL = {}
for mk in MK:
    s = T[(T.feed == mk) & (T.n_res >= 100)].drop_duplicates(subset=PKEYS + ["side", "sess", "tgt_R", "flatten"])
    s = s.sample(min(400, len(s)), random_state=3)
    POOL[mk] = [cfg_of(r) for _, r in s.iterrows()]
    print(f"  pool {mk}: {len(POOL[mk])} distinct configurations")

# ---- cache every pool cell's monthly R once
CACHE = {}
for mk in MK:
    mats = []
    for i, cfg in enumerate(POOL[mk]):
        t = trades(mk, cfg)
        mats.append(t.groupby("ym").R.mean().rename(i))
    Mm = pd.concat(mats, axis=1).sort_index()
    CACHE[mk] = Mm
    print(f"  {mk}: monthly matrix {Mm.shape}")

L("M4.1  IS THE RULE FITTED?  Rolling walk-forward, NOTHING re-selected (36m train / 12m test)")
rows = []
for mk in MK:
    for nm, cfg in (("As published", PUB), *[(f"Optuna {r.study}", cfg_of(r))
                                             for _, r in FN[FN.feed == mk].iterrows()]):
        t = trades(mk, cfg)
        mons = np.sort(t.ym.unique())
        IS, OS = [], []
        for a in range(0, len(mons) - 48, 12):
            tr = t[(t.ym >= mons[a]) & (t.ym < mons[a + 36])]
            te = t[(t.ym >= mons[a + 36]) & (t.ym < mons[min(a + 48, len(mons) - 1)])]
            if len(tr) >= 30 and len(te) >= 15:
                IS.append(tr.R.mean()); OS.append(te.R.mean())
        if len(IS) < 3:
            continue
        rows.append(dict(feed=mk, cell=nm, folds=len(IS), IS=round(np.mean(IS), 4),
                         OOS=round(np.mean(OS), 4), gap=round(np.mean(IS) - np.mean(OS), 4),
                         pos_folds=int(np.sum(np.array(OS) > 0)),
                         corr=round(float(np.corrcoef(IS, OS)[0, 1]), 3) if len(IS) > 2 else np.nan))
W = pd.DataFrame(rows)
print(W.to_string(index=False))
W.to_csv("results/vwapema/m4_wf_fixed.csv", index=False)
print("\nA negative corr(IS, OOS) with NOTHING re-selected is REGIME, not curve-fitting.")

L("M4.2  IS THE SEARCH OVERFIT?  Walk-forward with the selection RE-RUN in every fold")
rows = []
for mk in MK:
    Mm = CACHE[mk]
    mons = Mm.index.to_numpy()
    pubt = trades(mk, PUB); pubm = pubt.groupby("ym").R.mean()
    tot = {"re-chosen": 0.0, "random cell": 0.0, "As published": 0.0}
    per = {k: [] for k in tot}
    for a in range(0, len(mons) - 48, 12):
        trm = Mm.loc[(Mm.index >= mons[a]) & (Mm.index < mons[a + 36])]
        tem = Mm.loc[(Mm.index >= mons[a + 36]) & (Mm.index < mons[min(a + 48, len(mons) - 1)])]
        if len(trm) < 24 or len(tem) < 6:
            continue
        best = trm.mean().idxmax()
        rnd = int(RNG.integers(0, Mm.shape[1]))
        pm = pubm[(pubm.index >= mons[a + 36]) & (pubm.index < mons[min(a + 48, len(mons) - 1)])]
        for k, v in (("re-chosen", tem[best].mean()), ("random cell", tem[rnd].mean()),
                     ("As published", pm.mean() if len(pm) else np.nan)):
            if np.isfinite(v):
                tot[k] += v; per[k].append(v)
    for k in tot:
        rows.append(dict(feed=mk, arm=k, folds=len(per[k]), sum_OOS_R=round(tot[k], 4),
                         mean=round(np.mean(per[k]), 4) if per[k] else np.nan,
                         pos=int(np.sum(np.array(per[k]) > 0)) if per[k] else 0))
S = pd.DataFrame(rows)
print(S.to_string(index=False))
S.to_csv("results/vwapema/m4_wf_reselect.csv", index=False)
print("\nEleven re-optimisers on this branch have lost to their author's constants. If the re-chosen")
print("arm also loses to a RANDOM cell from its own pool, the search has negative value.")

L("M4.3  P(OVERFIT) -- CSCV / PBO over all symmetric splits")
rows = []
for mk in MK:
    Mm = CACHE[mk].dropna(axis=1, thresh=int(0.5 * len(CACHE[mk]))).fillna(0.0)
    S_BLK = 12
    idx = np.array_split(np.arange(len(Mm)), S_BLK)
    logits, drops = [], []
    for comb in itertools.combinations(range(S_BLK), S_BLK // 2):
        tr = np.concatenate([idx[i] for i in comb])
        te = np.concatenate([idx[i] for i in range(S_BLK) if i not in comb])
        a = Mm.iloc[tr].mean(); b = Mm.iloc[te].mean()
        j = a.idxmax()
        rk = b.rank(pct=True)[j]
        rk = min(max(float(rk), 1e-6), 1 - 1e-6)
        logits.append(np.log(rk / (1 - rk)))
        drops.append(float(a.rank(pct=True)[j] - rk))
    logits = np.array(logits)
    # slope of OOS on IS over the cells
    half = len(Mm) // 2
    a = Mm.iloc[:half].mean(); b = Mm.iloc[half:].mean()
    sl = np.polyfit(a.values, b.values, 1)[0]
    rows.append(dict(feed=mk, cells=Mm.shape[1], months=len(Mm), splits=len(logits),
                     PBO=round(float((logits <= 0).mean()), 3),
                     median_logit=round(float(np.median(logits)), 3),
                     mean_rank_drop=round(float(np.mean(drops)), 3),
                     slope_OOS_on_IS=round(float(sl), 3),
                     IS_best_OOS=round(float(b[a.idxmax()]), 4), IS_best_IS=round(float(a.max()), 4)))
B = pd.DataFrame(rows)
print(B.to_string(index=False))
B.to_csv("results/vwapema/m4_pbo.csv", index=False)
print("\nPBO > 0.5 means the in-sample winner lands BELOW the out-of-sample median more often than")
print("not -- the selection procedure is actively harmful, not merely useless.")

L("M4.4  WHERE EACH CELL SITS IN ITS OWN POOL -- median IS rank, and the rank DISPERSION")
rows = []
for mk in MK:
    Mm = CACHE[mk].dropna(axis=1, thresh=int(0.5 * len(CACHE[mk]))).fillna(0.0)
    extra = {}
    for nm, cfg in (("As published", PUB), *[(f"Optuna {r.study}", cfg_of(r))
                                             for _, r in FN[FN.feed == mk].iterrows()]):
        t = trades(mk, cfg)
        extra[nm] = t.groupby("ym").R.mean().reindex(Mm.index).fillna(0.0)
    full = pd.concat([Mm, pd.DataFrame(extra)], axis=1)
    S_BLK = 12
    idx = np.array_split(np.arange(len(full)), S_BLK)
    rk = {nm: [] for nm in extra}
    for comb in itertools.combinations(range(S_BLK), S_BLK // 2):
        tr = np.concatenate([idx[i] for i in comb])
        a = full.iloc[tr].mean().rank(pct=True)
        for nm in extra:
            rk[nm].append(float(a[nm]))
    for nm in extra:
        v = np.array(rk[nm])
        rows.append(dict(feed=mk, cell=nm, median_IS_rank=round(float(np.median(v)), 3),
                         p10=round(float(np.percentile(v, 10)), 3),
                         p90=round(float(np.percentile(v, 90)), 3),
                         dispersion=round(float(np.percentile(v, 90) - np.percentile(v, 10)), 3)))
Rk = pd.DataFrame(rows)
print(Rk.to_string(index=False))
Rk.to_csv("results/vwapema/m4_ranks.csv", index=False)
print("\nA cell chosen by CONVENTION rather than by search sits near the middle of its own pool;")
print("a cell that is the argmax of a large grid sits at the top and has nowhere to go but down.")
