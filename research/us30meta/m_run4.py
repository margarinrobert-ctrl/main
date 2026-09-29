"""M4 -- THE SEEDED FAMILY ABLATION, run expecting the answer to be "delete most of the inputs".

`STUDY_V66_DL_META`: 65 features scored OOF IC 0.0983, seven volatility features 0.1407 and ONE
Parkinson estimator 0.1501 -- an 8-seed ablation said six of eight families made the model WORSE.
`STUDY_VP_DONCHIAN_US30`: dropping `don`, `ffd`, `hmm` and `str` all IMPROVED it, and 40 features
beat 62. That is five studies on this branch where feature engineering was SUBTRACTIVE. So the
ablation is not a formality; it is the measurement most likely to change what ships.

Every arm is run on EIGHT SEEDS and the seed sd is reported, because a single-seed ablation on
2,240 rows cannot separate a family effect from a random forest's own bootstrap noise. The t is
PAIRED across seeds -- the same eight seeds for the full model and the ablated one.
"""
from __future__ import annotations

import itertools
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
import m_feat as MF    # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 220)
print(__doc__)
t0 = time.time()

E = pd.read_parquet(os.path.join(C.OUT, "m3_events.parquet"))
with open(os.path.join(C.OUT, "m1_frozen.pkl"), "rb") as fh:
    Z = pickle.load(fh)
with open(os.path.join(C.OUT, "m3_best.pkl"), "rb") as fh:
    B = pickle.load(fh)
COLS = Z["cols"]
R = E[E.blk == 0].reset_index(drop=True)
y = R.y.to_numpy()
SEEDS = range(8)
KIND = B["best"]   # the ladder's best rung, chosen in M3 before this file ran
print(f"  ablation workhorse: `{KIND}` -- the LADDER'S BEST RUNG, decided in M3. Using a rung"
      f" whose own IC is near zero (rf reads +0.0096 on all 38) would make the ablation measure"
      f" the model's bootstrap noise rather than the families. Eight seeds x every arm."
      )
fams = sorted(set(MF.fam(c) for c in COLS))
print(f"  {len(COLS)} features in {len(fams)} families: "
      + ", ".join(f"{fa}({sum(MF.fam(c)==fa for c in COLS)})" for fa in fams))


def run(cols, tag):
    ics = np.array([ML.ic(ML.oof(R, list(cols), KIND, seed=s), y) for s in SEEDS])
    return ics


C.line("M4.1  DROP-ONE-FAMILY, 8 seeds, paired t")
full = run(COLS, "all")
print(f"  ALL {len(COLS)} features: IC {full.mean():+.4f}  seed sd {full.std(ddof=1):.4f}")
print(f"\n{'dropped':10s} {'n left':>7} {'IC':>9} {'delta':>9} {'seed sd':>9} {'paired t':>9} "
      f"{'verdict':>12}")
rows = []
for fa in fams:
    cs = [c for c in COLS if MF.fam(c) != fa]
    ics = run(cs, fa)
    d = ics - full
    tt = d.mean() / (d.std(ddof=1) / np.sqrt(len(d))) if d.std(ddof=1) > 0 else np.nan
    rows.append(dict(dropped=fa, n=len(cs), ic=ics.mean(), delta=d.mean(),
                     sd=ics.std(ddof=1), t=tt))
    print(f"{fa:10s} {len(cs):>7} {ics.mean():>+9.4f} {d.mean():>+9.4f} {ics.std(ddof=1):>9.4f} "
          f"{tt:>+9.2f} {'HARMFUL' if d.mean() > 0 else 'load-bearing':>12}", flush=True)
AB = pd.DataFrame(rows).sort_values("delta", ascending=False)
AB.to_csv(os.path.join(C.OUT, "m4_dropone.csv"), index=False)
harm = list(AB[AB.delta > 0].dropped)
print(f"\n  families whose REMOVAL improves the model: {len(harm)} of {len(fams)} -> {harm}")

C.line("M4.2  KEEP-ONE-FAMILY -- what does each carry on its own?")
print(f"{'family':10s} {'n':>4} {'IC':>9} {'seed sd':>9}")
solo = []
for fa in fams:
    cs = [c for c in COLS if MF.fam(c) == fa]
    if not cs:
        continue
    ics = run(cs, fa)
    solo.append(dict(fam=fa, n=len(cs), ic=ics.mean(), sd=ics.std(ddof=1)))
    print(f"{fa:10s} {len(cs):>4} {ics.mean():>+9.4f} {ics.std(ddof=1):>9.4f}", flush=True)
SO = pd.DataFrame(solo).sort_values("ic", ascending=False)
SO.to_csv(os.path.join(C.OUT, "m4_solo.csv"), index=False)

C.line("M4.3  PUSHED TO ITS CONCLUSION -- greedy forward selection over FAMILIES")
print("  Over families, not features: seven ordered looks instead of 2^38, so the search is small\n"
      "  enough that its own noise floor stays below what it is looking for.\n")
chosen, cur, hist = [], -9.0, []
pool = list(fams)
while pool:
    best, bic = None, -9.0
    for fa in pool:
        cs = [c for c in COLS if MF.fam(c) in chosen + [fa]]
        v = run(cs, fa).mean()
        if v > bic:
            best, bic = fa, v
    if bic <= cur + 1e-6:
        print(f"  stop: adding `{best}` gives {bic:+.4f}, not above {cur:+.4f}")
        hist.append(dict(step=len(chosen) + 1, added=best, ic=bic, accepted=False))
        break
    chosen.append(best)
    pool.remove(best)
    cur = bic
    n = sum(MF.fam(c) in chosen for c in COLS)
    hist.append(dict(step=len(chosen), added=best, ic=bic, n=n, accepted=True))
    print(f"  + {best:10s} -> {n:3d} features, IC {bic:+.4f}", flush=True)
HS = pd.DataFrame(hist)
HS.to_csv(os.path.join(C.OUT, "m4_greedy.csv"), index=False)
SET = [c for c in COLS if MF.fam(c) in chosen]
ics = run(SET, "chosen")
print(f"\n  CHOSEN SET: {chosen} = {len(SET)} features, IC {ics.mean():+.4f} "
      f"(sd {ics.std(ddof=1):.4f}) against ALL {len(COLS)} at {full.mean():+.4f}")
d = ics - full
print(f"  paired t of chosen vs all: {d.mean()/(d.std(ddof=1)/np.sqrt(len(d))):+.2f}")

C.line("M4.4  AND ONE FEATURE? -- the V66 question")
ic1 = []
for c in COLS:
    v = R[c].to_numpy()
    m = np.isfinite(v) & np.isfinite(y)
    ic1.append((c, float(pd.Series(v[m]).corr(pd.Series(y[m]), method="spearman"))))
I1 = pd.DataFrame(ic1, columns=["col", "ic"]).assign(a=lambda d: d.ic.abs()).sort_values("a", ascending=False)
print(I1.head(10)[["col", "ic"]].to_string(index=False))
topc = I1.iloc[0].col
one = run([topc], "one")
print(f"\n  single best feature `{topc}` as a MODEL: IC {one.mean():+.4f} (sd {one.std(ddof=1):.4f})")
print(f"  its raw univariate IC: {I1.iloc[0].ic:+.4f}")
print(f"  chosen set ({len(SET)}): {ics.mean():+.4f}   all ({len(COLS)}): {full.mean():+.4f}")
with open(os.path.join(C.OUT, "m4_set.pkl"), "wb") as fh:
    pickle.dump(dict(chosen_families=chosen, set=SET, kind=KIND, ic_set=float(ics.mean()),
                     ic_all=float(full.mean()), top_feature=topc, univ=I1), fh)
print(f"\n[m_run4 done in {time.time()-t0:.0f}s]")
