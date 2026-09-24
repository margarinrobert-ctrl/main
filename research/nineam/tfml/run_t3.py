"""T3  THE LADDER, RESEARCH HALF ONLY: ridge -> RF -> LightGBM -> XGBoost d3 -> MLP 2x32/2x64/4x128,
objective = the percent of price each event earned (walked unlocked), purged/embargoed folds grouped
by session, uniqueness weights, and EVERY model beside a shuffled-label twin (5 permutations).
Datasets: each timeframe alone, and all seven pooled with `tf.min` as a feature.
Then the family ablation, keep-one AND drop-one, on the pooled set with the best pooled model.

PRE-DECLARED here, before the ladder runs: the Gate-2 score is the OOF prediction of the model with
the highest REAL pooled OOF IC on the research half.
"""
from __future__ import annotations

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tfcore as C  # noqa: E402
import tfmodels as M  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

pd.set_option("display.width", 220)
t0 = time.time()
F = pd.read_pickle(os.path.join(HERE, "feats_all.pkl"))
KEEP = pd.read_csv(os.path.join(HERE, "t2_keep.csv")).iloc[:, 0].tolist()
sp = np.load(os.path.join(HERE, "split_days.npy"))
k_is = int(sp[0]); DAYS = sp[1:]; IS_D = DAYS[:k_is]
R = F[F["day"].isin(IS_D)].sort_values(["day", "t_sig", "tf"]).reset_index(drop=True)
print(f"research half: {len(R)} events on {R['day'].nunique()} sessions, {len(KEEP)} features")
NTW = 5


def hd(t):
    print("\n" + "=" * 100); print(t); print("=" * 100, flush=True)


def run_cell(df, cols, name, seeds=(0,)):
    X = df[cols].to_numpy(float); y = df["pct"].to_numpy(); w = M.weights(df)
    d = df["day"].to_numpy()
    preds = [M.oof(name, X, y, w, d, seed=s) for s in seeds]
    p = np.nanmean(np.vstack(preds), axis=0)
    return p, M.ic(p, y)


def twins(df, cols, name, n=NTW):
    X = df[cols].to_numpy(float); y = df["pct"].to_numpy(); w = M.weights(df)
    d = df["day"].to_numpy()
    g = np.random.default_rng(99)
    out = []
    for q in range(n):
        ys = g.permutation(y)
        p = M.oof(name, X, ys, w, d, seed=q)
        out.append(M.ic(p, ys))
    return np.asarray(out)


hd("3a  LADDER -- OOF Spearman IC against the event's %-of-price, each model beside its shuffled twin")
sets = [("pooled", R)] + [(f"tf{tf}", R[R.tf == tf].reset_index(drop=True)) for tf in C.TFS]
cols_by = {}
rows = []
OOF = {}
for lab, df in sets:
    cols = [k for k in KEEP if not (lab != "pooled" and k == "tf.min")]
    cols_by[lab] = cols
    for name in M.MODELS:
        p, icr = run_cell(df, cols, name)
        tw = twins(df, cols, name)
        OOF[(lab, name)] = p
        rows.append(dict(set=lab, model=name, n=len(df), ic=icr, twin_ic=float(np.nanmean(tw)),
                         twin_sd=float(np.nanstd(tw)), twin_beats=float(np.mean(tw >= icr)),
                         twin_wins=bool(np.nanmean(tw) >= icr)))
        print(f"  {lab:8s} {name:10s} n {len(df):>3}  IC {icr:+.4f}  twin {np.nanmean(tw):+.4f} "
              f"(sd {np.nanstd(tw):.3f})  twin>=real {np.mean(tw >= icr):.1f}  ({time.time()-t0:.0f}s)",
              flush=True)
LD = pd.DataFrame(rows)
LD.to_csv(os.path.join(HERE, "t3_ladder.csv"), index=False)
print()
print(LD.pivot(index="model", columns="set", values="ic").to_string(float_format=lambda v: f"{v:+.4f}"))
print(f"\n  twin mean IC >= real IC in {int(LD.twin_wins.sum())} of {len(LD)} cells "
      f"({100*LD.twin_wins.mean():.0f}%)")
# noise floor of a single IC at these n: the twin's own sd
print(f"  median twin IC sd {LD.twin_sd.median():.3f}; pooled cells: "
      f"{LD[LD.set=='pooled'].twin_sd.median():.3f}")

pooled = LD[LD.set == "pooled"].sort_values("ic", ascending=False)
BEST = pooled.iloc[0]["model"]
print(f"\n  PRE-DECLARED Gate-2 model = best REAL pooled IC: {BEST} (IC {pooled.iloc[0]['ic']:+.4f}, "
      f"twin {pooled.iloc[0]['twin_ic']:+.4f})")
# per-timeframe IC of the pooled model's OOF scores
Rp = R.copy()
for name in M.MODELS:
    Rp[f"oof_{name}"] = OOF[("pooled", name)]
print("\n  pooled OOF IC broken out by timeframe (all 7 models):")
bt = pd.DataFrame({name: [M.ic(Rp.loc[Rp.tf == tf, f"oof_{name}"].to_numpy(),
                               Rp.loc[Rp.tf == tf, "pct"].to_numpy()) for tf in C.TFS]
                   for name in M.MODELS}, index=C.TFS)
print(bt.to_string(float_format=lambda v: f"{v:+.4f}"))
bt.to_csv(os.path.join(HERE, "t3_pooled_by_tf.csv"))
Rp.to_pickle(os.path.join(HERE, "t3_oof.pkl"))
pd.Series({"best": BEST}).to_csv(os.path.join(HERE, "t3_best.csv"))

hd(f"3b  FAMILY ABLATION on the pooled set with {BEST}: KEEP-ONE and DROP-ONE")
seeds = (0,) if BEST == "ridge" else (0, 1, 2, 3, 4)
cols = cols_by["pooled"]
fams = sorted({k.split(".")[0] for k in cols})
_, full_ic = run_cell(R, cols, BEST, seeds)
ab = [dict(arm="ALL", family="-", k=len(cols), ic=full_ic)]
for fm in fams:
    kc = [k for k in cols if k.split(".")[0] == fm]
    dc = [k for k in cols if k.split(".")[0] != fm]
    _, a = run_cell(R, kc, BEST, seeds)
    _, b = run_cell(R, dc, BEST, seeds)
    ab.append(dict(arm="keep-one", family=fm, k=len(kc), ic=a))
    ab.append(dict(arm="drop-one", family=fm, k=len(dc), ic=b))
    print(f"  {fm:5s}  keep-one ({len(kc):>2}) IC {a:+.4f}   drop-one ({len(dc):>2}) IC {b:+.4f} "
          f"(delta vs ALL {b-full_ic:+.4f})", flush=True)
AB = pd.DataFrame(ab)
AB.to_csv(os.path.join(HERE, "t3_ablation.csv"), index=False)
print(f"\n  ALL features IC {full_ic:+.4f}. A family whose DROP raises IC is subtractive; a family whose")
print("  KEEP-ONE beats ALL says the rest is noise the model fits (STUDY_V66).")
print(f"\ndone in {time.time()-t0:.0f}s")
