"""A2 -- the model ladder, every model beside a SHUFFLED TWIN, then GATE 2 on unsized returns.

FOUR THINGS THIS FILE DOES THAT AN ORDINARY FEATURE STUDY DOES NOT:
  * PURGED AND EMBARGOED folds. An event occupies [signal bar, exit bar] and neighbouring events
    share future bars, so an ordinary K-fold trains on the answer. `label_horizon` is the median
    hold in events, and 1% of the sample is embargoed either side.
  * A SHUFFLED TWIN for every model. On this branch the shuffled label beat the real model in 83 of
    120 research cells once (`STUDY_V32_FLOW_ML`); above 50% means the noise floor is higher than
    the signal, and no other diagnostic shows it.
  * THE OBJECTIVE IS THE RETURN, NOT WIN/LOSE. A win/lose objective is a win-rate optimiser, and a
    trend system earns in the tail: `STUDY_V28` and `STUDY_V32` both measured p90 of R FALLING in
    the kept set when trained on win, and rising when trained on R. p90 is printed for every cell.
  * EVERY CANDIDATE'S RETURN STREAM IS KEPT, including the ones that lose, because White's reality
    check needs the whole set and not the survivor.
"""
import os, sys, time, pickle
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vwapema"))
SK = "/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9"
sys.path.insert(0, SK + "/mechanism-first-alpha/scripts")
sys.path.insert(0, SK + "/quant-strategy-lab/scripts")
import gates, splits

RNG = np.random.default_rng(17)
pd.set_option("display.width", 230)
L = lambda s: print("\n" + "=" * 114 + f"\n{s}\n" + "=" * 114)
print(__doc__)
import a2lib
from a2lib import BUNDLE, FCOLS, PRIMARIES, KEEPS, prep, models, MLP, oof

L("A2.1  THE LADDER -- research block only, every model beside its shuffled twin")
rows = []
t0 = time.time()
for mk, sd in PRIMARIES:
    X, y, meta, hold = prep(mk, sd, 0)
    base = y.mean()
    print(f"\n  --- {mk} {sd}: {len(y)} research events, median hold {hold} bars, "
          f"base {1e2*base:+.4f} % of price")
    arms = list(models().items()) + [("mlp 2x64", lambda: MLP((64, 64), seed=0)),
                                     ("mlp 4x128", lambda: MLP((128, 128, 128, 128), seed=0))]
    for nm, make in arms:
        for shuf in (False, True):
            p = oof(make, X, y, hold, shuffle_y=shuf, seed=3)
            ok = np.isfinite(p)
            ic = float(pd.Series(p[ok]).corr(pd.Series(y[ok]), method="spearman"))
            row = dict(feed=mk, cell=sd, model=nm, shuffled=shuf, ic=round(ic, 4))
            for k in KEEPS:
                thr = np.nanquantile(p, 1 - k)
                keep = ok & (p >= thr)
                r = y[keep]
                row[f"keep{int(k*100)}"] = round(1e2 * r.mean(), 4)
                row[f"p90_{int(k*100)}"] = round(1e2 * np.percentile(r, 90), 3)
                if not shuf:
                    CAND[(mk, sd, nm, k)] = r
            if not shuf:
                SCORES[(mk, sd, nm)] = p
            rows.append(row)
        print(f"    {nm:18s} real IC {rows[-2]['ic']:+.4f}  shuffled {rows[-1]['ic']:+.4f}  "
              f"keep50 {rows[-2]['keep50']:+.4f} vs {rows[-1]['keep50']:+.4f}  ({time.time()-t0:.0f}s)")
A = pd.DataFrame(rows)
A.to_csv("results/vwanom/a2_ladder.csv", index=False)
pickle.dump(CAND, open("results/vwanom/a2_candidates.pkl", "wb"))
pickle.dump(SCORES, open("results/vwanom/a2_scores.pkl", "wb"))

L("A2.2  DOES THE SHUFFLED TWIN OUTSCORE THE REAL MODEL?")
p = A.pivot_table(index=["feed", "cell", "model"], columns="shuffled",
                  values=["ic", "keep30", "keep50", "keep70"])
beat = {}
for col in ("ic", "keep30", "keep50", "keep70"):
    beat[col] = float((p[(col, True)] > p[(col, False)]).mean())
print("  share of cells where the SHUFFLED twin beats the real model (0.50 = the noise floor):")
print("   " + "   ".join(f"{k} {v:.2f}" for k, v in beat.items()))
print("\n" + p.round(4).to_string())

L("A2.3  GATE 2 -- the meta layer's uplift on UNSIZED returns, research block")
rows = []
SCORES = pickle.load(open("results/vwanom/a2_scores.pkl", "rb"))
for (mk, sd, nm, k), r in CAND.items():
    X, y, meta, hold = prep(mk, sd, 0)
    p = SCORES[(mk, sd, nm)]
    thr = float(np.nanquantile(p, 1 - k))
    g = gates.meta_gate(y, np.nan_to_num(p, nan=-1e18), thr)
    rows.append(dict(feed=mk, cell=sd, model=nm, keep=k, n_kept=int(g["n_kept"]),
                     kept_frac=round(float(g["kept_fraction"]), 3),
                     base=round(1e2 * float(g["unsized_mean_unfiltered"]), 4),
                     kept=round(1e2 * float(g["unsized_mean_filtered"]), 4),
                     uplift=round(1e2 * float(g["unsized_uplift"]), 4),
                     ci_lo=round(1e2 * float(g["unsized_uplift_ci95"][0]), 4),
                     ci_hi=round(1e2 * float(g["unsized_uplift_ci95"][1]), 4),
                     boot_p=round(float(g["bootstrap_p_one_sided"]), 3),
                     hit_base=round(float(g["hit_rate_unfiltered"]), 3),
                     hit_kept=round(float(g["hit_rate_filtered"]), 3),
                     p90_base=round(1e2 * np.percentile(y, 90), 3),
                     p90_kept=round(1e2 * np.percentile(r, 90), 3),
                     verdict=str(g["verdict"])[:34]))
G = pd.DataFrame(rows).sort_values("uplift", ascending=False)
print(G.to_string(index=False))
G.to_csv("results/vwanom/a2_gate2.csv", index=False)
print(f"\n  candidates evaluated and KEPT for the reality check: {len(CAND)}")
