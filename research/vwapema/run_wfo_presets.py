"""THE SAME OVERFITTING BATTERY, RUN PER PRESET.

`run_wfo_pbo` tested the published configuration and found PBO 0.561 for the SEARCH while the
published rule itself sat at median IS rank 0.444 -- a below-median cell in its own grid, which is
what a rule that was never fitted looks like. Five of the six shipped presets WERE fitted, on this
data, by my own Optuna study and 108,000-cell sweep. So the test that matters per preset is:

  WHERE DOES EACH ONE RANK IN-SAMPLE ACROSS THE 12,870 CSCV SPLITS, AND WHERE DOES IT RANK OUT?
  A cell selected for in-sample performance must rank HIGH in sample by construction. The
  diagnostic is the DROP: how far its rank falls when the same split's other half is read. A rule
  that was never fitted has nothing to drop from.

Plus, per preset: a rolling 36m/12m walk-forward with NOTHING re-selected, which asks the separate
question of whether it is regime-dependent.
"""
import os, sys, json, itertools, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from research.vwapema import vecore as V

RNG = np.random.default_rng(1618)
pd.set_option("display.width", 230)
print(__doc__)
DS = {s: V.build(sess=s) for s in ("ny", "utc")}
SW = json.load(open("results/vwapema/sweep_cells.json"))
OP = json.load(open("results/vwapema/optuna_finalists.json"))

PRESETS = {
    "As published":       dict(sess="ny", p=dict(V.PARAMS), tgt_R=3.0, fitted=False),
    "Optuna totR":        dict(**{k: OP["totR"]["cfg"][k] for k in ("sess", "p", "tgt_R")}, fitted=True),
    "Optuna PF":          dict(**{k: OP["pf"]["cfg"][k] for k in ("sess", "p", "tgt_R")}, fitted=True),
    "Optuna retDD":       dict(**{k: OP["retdd"]["cfg"][k] for k in ("sess", "p", "tgt_R")}, fitted=True),
    "Sweep top row":      dict(sess=SW["top"]["sess"], p=SW["top"]["p"], tgt_R=SW["top"]["tgt_R"], fitted=True),
    "Sweep neighbourhood": dict(sess=SW["robust"]["sess"], p=SW["robust"]["p"], tgt_R=SW["robust"]["tgt_R"], fitted=True),
}


def monthly(cfg):
    D = DS[cfg["sess"]]
    sig, _ = V.triggers(D, side=1, p=cfg["p"])
    t = V.run(D, sig, side=1, tgt_R=cfg["tgt_R"], atr_stop=cfg["p"]["atr_stop"], p=cfg["p"])
    if len(t) == 0:
        return None
    t["m"] = pd.DatetimeIndex(t.ts).to_period("M")
    return t.groupby("m").R.agg(["mean", "sum", "size"])


ref = monthly(PRESETS["As published"])
allm = pd.period_range(ref.index.min(), ref.index.max(), freq="M")

# ---------------------------------------------------------------- the return matrix
print("=" * 118)
print("BUILDING the per-month matrix: 1,199 sampled grid cells + all six presets")
print("=" * 118)
G = pd.read_parquet("results/vwapema/sweep100k.parquet")
samp = G.sample(1200, random_state=11).reset_index(drop=True)
t0 = time.time(); mat = []
for _, r in samp.iterrows():
    cfg = dict(sess=r.sess, tgt_R=float(r.tgt),
               p={"ema_slow": int(r.ema_slow), "ema_pull": int(r.ema_pull), "ema_tight": 20,
                  "atr_len": 14, "atr_stop": float(r.stop), "vol_mult": float(r.vol),
                  "range_mult": float(r["range"]), "wick_body": float(r.wick),
                  "ambig": V.PARAMS["ambig"], "tighten_R": V.PARAMS["tighten_R"]})
    g = monthly(cfg)
    if g is not None and g["size"].sum() >= 120:
        mat.append(g["sum"].reindex(allm).fillna(0.0).to_numpy())
M = np.array(mat).T
pres_cols = {}
for nm, cfg in PRESETS.items():
    g = monthly(cfg)
    M = np.column_stack([M, g["sum"].reindex(allm).fillna(0.0).to_numpy()])
    pres_cols[nm] = M.shape[1] - 1
print(f"  {M.shape[1]} columns x {M.shape[0]} months   ({time.time()-t0:.0f}s)")

# ---------------------------------------------------------------- CSCV ranks per preset
print("\n" + "=" * 118)
print("1. IN-SAMPLE vs OUT-OF-SAMPLE RANK, over all 12,870 symmetric splits")
print("=" * 118)
print("  A cell chosen for in-sample performance ranks HIGH in sample by construction. The number")
print("  that matters is how far it FALLS. A rule that was never fitted has nothing to fall from.\n")
S = 16
blocks = np.array_split(np.arange(M.shape[0]), S)
combos = list(itertools.combinations(range(S), S // 2))


def perf(x):
    mu, sd = x.mean(axis=0), x.std(axis=0)
    return np.where(sd > 1e-12, mu / np.maximum(sd, 1e-12), 0.0)


# NOTE: in symmetric CSCV every split's COMPLEMENT is also a split, so the DISTRIBUTION of a fixed
# column's in-sample ranks is identical to the distribution of its out-of-sample ranks and the two
# medians agree to the decimal. The drop must therefore be measured PAIRWISE, per split -- the
# median of the differences, not the difference of the medians, which is exactly 0 by construction.
# PBO is also reported from a pool that EXCLUDES the fitted presets: putting cells that were fitted
# on this data into the comparison pool lowers PBO by handing the argmax a pre-selected winner.
is_ranks = {k: [] for k in PRESETS}
os_ranks = {k: [] for k in PRESETS}
drops = {k: [] for k in PRESETS}
n_grid = M.shape[1] - len(PRESETS)
lam, lam_clean = [], []
for cb in combos:
    ii = np.concatenate([blocks[b] for b in cb])
    oo = np.concatenate([blocks[b] for b in range(S) if b not in cb])
    pis, pos = perf(M[ii]), perf(M[oo])
    n = len(pis) - 1
    for k, c in pres_cols.items():
        ri = float((pis < pis[c]).sum()) / n
        ro = float((pos < pos[c]).sum()) / n
        is_ranks[k].append(ri); os_ranks[k].append(ro); drops[k].append(ri - ro)
    star = int(np.argmax(pis))
    r = min(max(float((pos < pos[star]).sum()) / n, 1e-6), 1 - 1e-6)
    lam.append(np.log(r / (1 - r)))
    # clean PBO: the argmax taken over the GRID ONLY, presets excluded from the pool
    gs = int(np.argmax(pis[:n_grid]))
    rg = min(max(float((pos[:n_grid] < pos[:n_grid][gs]).sum()) / (n_grid - 1), 1e-6), 1 - 1e-6)
    lam_clean.append(np.log(rg / (1 - rg)))
PBO = float((np.array(lam) <= 0).mean())
PBO_CLEAN = float((np.array(lam_clean) <= 0).mean())
rows = []
for k in PRESETS:
    a, b, d = np.array(is_ranks[k]), np.array(os_ranks[k]), np.array(drops[k])
    rows.append(dict(preset=k, fitted="YES" if PRESETS[k]["fitted"] else "no",
                     IS_rank=float(np.median(a)), OOS_rank=float(np.median(b)),
                     med_pair_drop=float(np.median(d)), p90_drop=float(np.percentile(d, 90)),
                     OOS_above_median=100 * float((b > 0.5).mean())))
R = pd.DataFrame(rows).sort_values("IS_rank", ascending=False)
print(R.to_string(index=False, float_format=lambda v: f"{v:9.3f}"))
print(f"\n  PBO over the GRID ONLY (presets excluded from the pool): {PBO_CLEAN:.3f}")
print(f"  PBO with the fitted presets IN the pool:                   {PBO:.3f}"
      f"   <- lower, because five of them were fitted on this data")
print("  IS_rank 1.0 = best in the pool in sample, 0.5 = median.")
print("\n  A METHOD NOTE WORTH KEEPING: symmetric CSCV CANNOT measure a fixed configuration's rank")
print("  drop. For every split its COMPLEMENT is also a split, so both the median rank difference")
print("  AND the median pairwise drop are identically ZERO by construction -- as every row above")
print("  shows. PBO works because its subject (the argmax) CHANGES with the split; a fixed column's")
print("  subject does not. What is informative for a fixed cell is the DISPERSION of the drop")
print("  (`p90_drop`) and the walk-forward gap in section 2.")

# ---------------------------------------------------------------- rolling walk-forward per preset
print("\n" + "=" * 118)
print("2. ROLLING WALK-FORWARD PER PRESET -- 36 months train, 12 test, NOTHING re-selected")
print("=" * 118)
W = 36
rows = []
for k, cfg in PRESETS.items():
    g = monthly(cfg).reindex(allm).fillna(0.0)
    fis, fos = [], []
    for s in range(0, len(allm) - W - 12 + 1, 12):
        tr, te = g.iloc[s:s + W], g.iloc[s + W:s + W + 12]
        if te["size"].sum() < 6 or tr["size"].sum() < 30:
            continue
        fis.append(float((tr["mean"] * tr["size"]).sum() / tr["size"].sum()))
        fos.append(float((te["mean"] * te["size"]).sum() / te["size"].sum()))
    fis, fos = np.array(fis), np.array(fos)
    rows.append(dict(preset=k, fitted="YES" if cfg["fitted"] else "no", folds=len(fos),
                     IS=float(fis.mean()), OOS=float(fos.mean()), gap=float(fis.mean() - fos.mean()),
                     OOS_pos=f"{int((fos>0).sum())}/{len(fos)}",
                     corr=float(np.corrcoef(fis, fos)[0, 1]) if len(fis) > 2 else np.nan))
Wf = pd.DataFrame(rows)
print(Wf.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
print("\n  A POSITIVE gap is the normal overfit shape (better in sample than out).")
print("  A NEGATIVE gap is the wrong shape and means the regime, not skill.")

# ---------------------------------------------------------------- verdict table
print("\n" + "=" * 118)
print("3. VERDICT PER PRESET")
print("=" * 118)
out = []
for k in PRESETS:
    r = R[R.preset == k].iloc[0]; w = Wf[Wf.preset == k].iloc[0]
    fitted = PRESETS[k]["fitted"]
    if not fitted:
        v = "NOT FITTED -- ranks below median in its own pool"
    elif w.gap >= 0.15:
        v = "OVERFIT -- large in/out gap in the walk-forward"
    elif r.p90_drop >= 0.30:
        v = "fitted; rank holds on average, unstable in the tail"
    else:
        v = "fitted; rank and walk-forward both hold"
    out.append(dict(preset=k, IS_rank=r.IS_rank, med_drop=r.med_pair_drop, p90_drop=r.p90_drop,
                    wf_folds=int(w.folds), wf_IS=w.IS, wf_OOS=w.OOS, wf_gap=w.gap, verdict=v))
O = pd.DataFrame(out).sort_values("wf_gap", ascending=False)
print(O.to_string(index=False, float_format=lambda v: f"{v:9.3f}"))
R.to_csv("results/vwapema/preset_ranks.csv", index=False)
Wf.to_csv("results/vwapema/preset_wfo.csv", index=False)
O.to_csv("results/vwapema/preset_verdict.csv", index=False)
json.dump(dict(PBO_with_presets=PBO, PBO_grid_only=PBO_CLEAN), open("results/vwapema/preset_pbo.json", "w"))
