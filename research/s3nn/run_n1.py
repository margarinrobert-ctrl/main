"""N1 -- Gate 1 on the primary, the event superset, and the causality audit.

Nothing is modelled until three things are established: the primary has an edge to refine, the
training set is big enough that a network is not guaranteed to memorise it, and every feature is
causal. This branch has spent four studies learning that a meta layer on a dead primary produces
a filter that makes a losing base less bad and never alive.
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5"); sys.path.insert(0, "research/s3nn")
import numpy as np, pandas as pd
import s5data as S, s5sig as SG
import nn_data as ND

R = "results/s3nn/"
os.makedirs(R, exist_ok=True)
print(__doc__)
t0 = time.time()
pd.set_option("display.width", 220); pd.set_option("display.max_columns", 40)

base = S.load_1m()
D = S.assemble(S.resample(base, 5), 5)
F = SG.build(D, base)
DAYS = {0: D["all_days"][D["all_days"] < D["cut_day"]], 1: D["all_days"][D["all_days"] >= D["cut_day"]]}
print(f"NQ 5m: {D['n']:,} bars, {D['n_sessions']} window sessions, research to {D['cut_date']}")

print("\n" + "=" * 104)
print("N1.1  GATE 1 -- the primary alone, before any feature exists")
print("=" * 104)
rows = []
for k, w in ((3, 20), (3, 40), (2, 40), (4, 40), (3, 60)):
    lg, sh = ND.events_s3(D, F, k=k, w=w)
    t = ND.walk(D, lg, sh)
    for b, lab in ((0, "research"), (1, "LOCKED")):
        s = t[t.blk == b]
        if len(s) < 40:
            continue
        r = s.pts.to_numpy()
        shp, _ = S.day_sharpe(s.day.to_numpy(), r, DAYS[b])
        rows.append(dict(k=k, w=w, block=lab, n=len(s),
                         per_yr=len(s) / (len(DAYS[b]) / 252), pts=r.mean(),
                         pf=r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9),
                         win=(r > 0).mean(), sharpe=shp, p90_R=np.percentile(s.R, 90)))
G1 = pd.DataFrame(rows)
G1.to_csv(R + "n1_gate1.csv", index=False)
print(G1.round(4).to_string(index=False))
print("\n  k3/w20 is the SHIPPED cell -- the one leg of the five positive on BOTH blocks.")

# the training set and the shipped cell
lg_s, sh_s = ND.events_s3(D, F, k=3, w=20)
T_CELL = ND.walk(D, lg_s, sh_s)

# THE TRAINING SET IS LABELLED WITHOUT THE POSITION LOCK.
# The lock is an execution constraint: it decides which events a single account can act on, not
# which events have a well-defined outcome. Labelling only the locked survivors of the shipped
# cell gives 380 research rows against 45 features, which is exactly the regime where every net
# on this branch has memorised. Unlocked labelling over k in {2,3} at w=40 gives ~3x that -- and
# it is what makes the labels OVERLAP, so uniqueness weights and purged folds stop being
# decoration and become load-bearing.
parts = []
for k in (2, 3):
    lg_t, sh_t = ND.events_s3(D, F, k=k, w=40)
    q = ND.label_all(D, lg_t, sh_t)
    q["k"] = k
    parts.append(q)
    print(f"  k={k} w=40 unlocked: {len(q):5d} labelled events ({int((q.blk==0).sum())} research)")
T_TRAIN = (pd.concat(parts, ignore_index=True)
             .drop_duplicates(subset=["sig", "side"])
             .sort_values("sig").reset_index(drop=True))
print(f"\n  shipped cell k3/w20 (LOCKED walk): {len(T_CELL):5d} events "
      f"({int((T_CELL.blk==0).sum())} research / {int((T_CELL.blk==1).sum())} locked)")
print(f"  training set, unlocked, pooled  : {len(T_TRAIN):5d} events "
      f"({int((T_TRAIN.blk==0).sum())} research / {int((T_TRAIN.blk==1).sum())} locked)")
cover = np.isin(T_CELL.sig.to_numpy(), T_TRAIN.sig.to_numpy()).mean()
print(f"  it covers {cover:.1%} of the shipped cell's own events")

print("\n" + "=" * 104)
print("N1.2  THE FEATURES, AND THE TRUNCATION AUDIT")
print("=" * 104)
X, names = ND.build_features(D, F)
avail = [k for k in names if np.isfinite(X[k][T_TRAIN.sig.to_numpy()]).mean() > 0.9]
print(f"  {len(names)} features declared, {len(avail)} finite on >90% of events")
fam = pd.Series([k.split(".")[0] for k in avail]).value_counts()
print("  by family: " + "  ".join(f"{k} {v}" for k, v in fam.items()))
bad = ND.truncation_audit(D, F, avail, probes=20)
print(f"  audit: {len(bad)} mismatches / {20*len(avail)} probes"
      + ("" if not bad else f"   FIRST: {bad[:3]}"))

print("\n" + "=" * 104)
print("N1.3  SAMPLE UNIQUENESS -- overlapping labels are not independent rows")
print("=" * 104)
u = ND.uniqueness(T_TRAIN, D["n"])
T_TRAIN["u"] = u
conc = np.zeros(D["n"])
for a, b in zip(T_TRAIN.sig, T_TRAIN.exit):
    conc[a:b + 1] += 1
occ = conc[conc > 0]
print(f"  mean concurrent labels while any is open: {occ.mean():.2f}   max {occ.max():.0f}")
print(f"  uniqueness weight: mean 1.000 by construction, min {u.min():.3f}, "
      f"p10 {np.percentile(u,10):.3f}, max {u.max():.3f}")
print(f"  EFFECTIVE sample size {u.sum()/u.max():.0f} against {len(T_TRAIN)} raw rows"
      f"  -- this is the number a network actually has")

np.save(R + "X.npy", np.column_stack([X[k] for k in avail]))
pd.Series(avail).to_csv(R + "feature_names.csv", index=False, header=False)
T_TRAIN.to_parquet(R + "train_events.parquet")
T_CELL.to_parquet(R + "cell_events.parquet")
print(f"\ntotal {time.time()-t0:.0f}s")
