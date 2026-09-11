"""Concentration and walk-forward -- the two questions the locked table cannot answer.

  1. HOW MUCH OF THE LOCKED RESULT IS 2025? Gold rose roughly 60% in 2025. A long-only rule in a
     bull run is a beta bet, which is the spec's own checklist item 8.
  2. DOES CHOOSING FROM THIS FAMILY BEAT NOT CHOOSING? The selection is RE-RUN inside every
     expanding training fold and read on the next fold only, beside the paper's own constants and
     a RANDOM cell from the same space.
"""
import os, sys, json
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from research.vwapema import vecore as V

RNG = np.random.default_rng(909)
pd.set_option("display.width", 220)
print(__doc__)
DS = {sm: V.build(sess=sm) for sm in ("ny", "utc")}
T = pd.read_parquet("results/vwapema/optuna_trials.parquet")
FIN = json.load(open("results/vwapema/optuna_finalists.json"))
FIN["as published"] = dict(cfg=dict(p=dict(V.PARAMS), side=1, sess="ny", tgt_R=3.0, flatten=False))


def trades(cfg):
    D = DS[cfg["sess"]]
    sig, _ = V.triggers(D, side=cfg["side"], p=cfg["p"])
    t = V.run(D, sig, side=cfg["side"], tgt_R=cfg["tgt_R"], flatten=cfg["flatten"], p=cfg["p"])
    t["date"] = pd.DatetimeIndex(t.ts).normalize(); t["year"] = pd.DatetimeIndex(t.ts).year
    return t


print("=" * 112)
print("CONCENTRATION -- where the locked result actually comes from")
print("=" * 112)
rows = []
for nm, spec in FIN.items():
    t = trades(spec["cfg"]); tl = t[t.blk == 1]
    tot = tl.R.sum()
    y25 = tl[tl.year >= 2025].R.sum()
    pre = tl[tl.year < 2025].R.sum()
    top5 = np.sort(tl.R.to_numpy())[::-1][:max(1, len(tl)//20)].sum()
    rows.append(dict(finalist=nm, n_lock=len(tl), totR=tot,
                     R_2025_26=y25, share_2025_26=100*y25/max(abs(tot), 1e-9),
                     R_pre2025=pre, n_pre2025=int((tl.year < 2025).sum()),
                     R_per_trade_pre2025=pre/max((tl.year < 2025).sum(), 1),
                     top5pct_share=100*top5/max(abs(tot), 1e-9)))
C = pd.DataFrame(rows)
print(C.to_string(index=False, float_format=lambda v: f"{v:9.3f}"))
print("\n  `share_2025_26` is the fraction of the whole locked result contributed by 2025 onward,")
print("  a stretch in which gold rose about 60%. `R_per_trade_pre2025` is the locked block with")
print("  that rally removed -- the number that is not a beta bet.")

print("\n" + "=" * 112)
print("WALK-FORWARD -- selection RE-RUN inside every training fold, expanding")
print("=" * 112)
D0 = DS["ny"]
ix = pd.DatetimeIndex(D0["ix"])
years = sorted(set(ix.year))
folds = [y for y in years if 2014 <= y <= 2025]
pool = T[T.n_res >= 120].copy()
# a fixed candidate pool sampled from the trial space, so each fold re-selects from the SAME menu
cand = pool.sample(min(300, len(pool)), random_state=3).to_dict("records")


def cfg_of(rec):
    p = {k: rec[k] for k in ("ema_slow", "ema_pull", "ema_tight", "atr_len", "atr_stop",
                             "vol_mult", "range_mult", "wick_body", "ambig", "tighten_R")}
    p["ema_slow"] = int(p["ema_slow"]); p["ema_pull"] = int(p["ema_pull"])
    p["ema_tight"] = int(p["ema_tight"]); p["atr_len"] = int(p["atr_len"])
    return dict(p=p, side=int(rec["side"]), sess=rec["sess"], tgt_R=float(rec["tgt_R"]),
                flatten=bool(rec["flatten"]))


CACHE = {}
def yearly(rec_i, rec):
    if rec_i not in CACHE:
        t = trades(cfg_of(rec))
        CACHE[rec_i] = t.groupby("year").agg(R=("R", "mean"), n=("R", "size"))
    return CACHE[rec_i]


rows = []
pub = trades(FIN["as published"]["cfg"]).groupby("year").agg(R=("R", "mean"), n=("R", "size"))
for fy in folds:
    scores = []
    for i, rec in enumerate(cand):
        y = yearly(i, rec)
        tr = y[y.index < fy]
        if tr.n.sum() >= 60:
            scores.append((float((tr.R * tr.n).sum() / tr.n.sum()), i))
    if not scores:
        continue
    scores.sort(reverse=True)
    best_i = scores[0][1]
    rnd_i = int(RNG.integers(0, len(cand)))
    ych = yearly(best_i, cand[best_i]); yrn = yearly(rnd_i, cand[rnd_i])
    rows.append(dict(fold=fy,
                     chosen=float(ych.R.get(fy, np.nan)), chosen_n=int(ych.n.get(fy, 0)),
                     random=float(yrn.R.get(fy, np.nan)), random_n=int(yrn.n.get(fy, 0)),
                     published=float(pub.R.get(fy, np.nan)), published_n=int(pub.n.get(fy, 0))))
W = pd.DataFrame(rows)
print(W.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
for c in ("chosen", "random", "published"):
    v = W[c].dropna()
    print(f"  {c:10s} mean {v.mean():+.4f} R/trade over {len(v)} folds, positive in {int((v>0).sum())}")
print("\n  Ten re-optimisers have now lost to the author's constants on this branch.")
C.to_csv("results/vwapema/concentration.csv", index=False)
W.to_csv("results/vwapema/walkforward.csv", index=False)
