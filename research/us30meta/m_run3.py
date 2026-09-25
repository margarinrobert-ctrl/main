"""M3 -- THE MODEL LADDER, each rung beside a SHUFFLED-LABEL TWIN.

Objective is the POINTS EARNED. Not win/lose: `STUDY_V28` and `STUDY_V32` both measured that a
win/lose objective is a win-rate optimiser -- the win rate rises exactly as trained and p90 of R
FALLS in every cell, because a breakout system earns in the tail. `STUDY_V66_DL_META` then showed
that on a target-capped primary p90 of R is DEGENERATE (a winner's R is capped by the target and
p90 reads the same number for every subset), so on this 50/150 geometry the tail question is asked
as the TARGET-HIT RATE instead.

The twin is the test, not the p-value. If a model trained on PERMUTED labels scores as well as the
real one, the noise floor is above the signal and there is nothing to filter with.

TRAINING FRAME. The UNLOCKED `base` stream: every eligible Donchian-20 long in-window signal bar
labelled under the identical 50/150 geometry, 2,240 research rows against 400 locked ones. Purged
and embargoed folds with day-level uniqueness weights, because a session's events overlap.
"""
from __future__ import annotations

import os
import pickle
import sys
import time
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import m_core as C     # noqa: E402
import m_ml as ML      # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 220)
print(__doc__)
t0 = time.time()

f = C.S.load("US30L")
bl = C.S.blocks(f, "US30L")
MR = bl["A_research"]
M = C.L.build_masks(f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy())
X = pd.read_parquet(os.path.join(C.OUT, "m1_features.parquet"))
with open(os.path.join(C.OUT, "m1_frozen.pkl"), "rb") as fh:
    Z = pickle.load(fh)
COLS = Z["cols"]

u = C.unlocked(f, "base", M=M)
E = u.join(X.reset_index(drop=True).iloc[u.sig_bar.to_numpy()].reset_index(drop=True))
E["y"] = E.pts
E["dayi"] = E.day.astype("int64")
E["blk"] = (E.ts >= "2023-01-01").astype(int)
E = E.dropna(subset=COLS).reset_index(drop=True)
R = E[E.blk == 0].reset_index(drop=True)
print(f"  training frame: {len(R)} research rows, {len(E)-len(R)} holdout rows, {len(COLS)} features")
print(f"  label: points a trade, mean {R.y.mean():+.3f}, sd {R.y.std():.1f}, "
      f"target-hit share {float((R.why==1).mean()):.3f}")
w = ML.uniqueness(R.dayi.to_numpy())
print(f"  uniqueness weights: mean concurrency {1/np.mean(w/w.sum()*len(w)):.2f}, "
      f"effective n {(w.sum()**2)/np.sum(w**2):.0f} of {len(R)}")
E.to_parquet(os.path.join(C.OUT, "m3_events.parquet"))

C.line("M3.1  THE LADDER -- OOF Spearman IC on the points earned, real vs shuffled twin")
y = R.y.to_numpy()
tgt = float(L_TGT) if (L_TGT := os.environ.get("TGT")) else float(C.L.KW["tgt_a"])
rows = []
preds = {}
print(f"{'model':12s} {'real IC':>9} {'twin IC':>9} {'twin wins':>10} "
      f"{'top30% pts':>11} {'twin top30':>11} {'tgt hit':>8}")
for kind in ML.LADDER:
    pr = ML.oof(R, COLS, kind, seed=0)
    ps = ML.oof(R, COLS, kind, seed=0, shuffle=True)
    preds[kind] = pr
    ir, is_ = ML.ic(pr, y), ML.ic(ps, y)
    thr, ths = np.nanquantile(pr, 0.7), np.nanquantile(ps, 0.7)
    tr_, ts_ = y[pr >= thr].mean(), y[ps >= ths].mean()
    hit = float((R.why.to_numpy()[pr >= thr] == 1).mean())
    rows.append(dict(model=kind, ic=ir, ic_twin=is_, top30=tr_, top30_twin=ts_,
                     twin_wins=bool(is_ > ir), tgt_hit=hit))
    print(f"{kind:12s} {ir:>+9.4f} {is_:>+9.4f} {'YES' if is_ > ir else 'no':>10} "
          f"{tr_:>+11.3f} {ts_:>+11.3f} {hit:>8.3f}", flush=True)
LD = pd.DataFrame(rows)
LD.to_csv(os.path.join(C.OUT, "m3_ladder.csv"), index=False)
tw = int(LD.twin_wins.sum())
print(f"\n  baseline (all rows): {y.mean():+.3f} pts, PF {C.pf(y):.3f}, "
      f"target-hit {float((R.why==1).mean()):.3f}")
print(f"  SHUFFLED TWIN WINS {tw} of {len(LD)} cells on IC = {tw/len(LD)*100:.0f}% "
      f"(above 50% means the noise floor is higher than the signal)")
tw2 = int((LD.top30_twin > LD.top30).sum())
print(f"  twin wins {tw2} of {len(LD)} on the top-30% mean = {tw2/len(LD)*100:.0f}%")

C.line("M3.2  CAPACITY -- is deeper better, worse, or inert?")
print(LD[["model", "ic", "ic_twin", "top30"]].to_string(index=False))
mlp = LD[LD.model.str.startswith("mlp")]
print(f"\n  MLP rungs 2x32 / 2x64 / 4x128: "
      f"{' / '.join(f'{v:+.4f}' for v in mlp.ic)}")
print(f"  XGBoost d3 -> d6: {LD[LD.model=='xgb_d3'].ic.iloc[0]:+.4f} -> "
      f"{LD[LD.model=='xgb_d6'].ic.iloc[0]:+.4f}")
print(f"  best rung: {LD.loc[LD.ic.idxmax(),'model']} at {LD.ic.max():+.4f}; "
      f"ridge {LD[LD.model=='ridge'].ic.iloc[0]:+.4f}")

C.line("M3.3  SEED STABILITY of the best rung, and the seed-averaged score")
best = LD.loc[LD.ic.idxmax(), "model"]
seeds = [ML.oof(R, COLS, best, seed=s) for s in range(5)]
ics = [ML.ic(p, y) for p in seeds]
avg = np.mean(seeds, axis=0)
print(f"  {best}: per-seed IC {' '.join(f'{v:+.4f}' for v in ics)}   "
      f"sd {np.std(ics):.4f}")
print(f"  seed-averaged score IC {ML.ic(avg, y):+.4f}")
np.save(os.path.join(C.OUT, "m3_bestpred.npy"), avg)
with open(os.path.join(C.OUT, "m3_best.pkl"), "wb") as fh:
    pickle.dump(dict(best=best, ladder=LD, twin_win_rate=tw / len(LD)), fh)
print(f"\n[m_run3 done in {time.time()-t0:.0f}s]")
