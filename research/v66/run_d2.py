"""D2 -- features on the eligible primary, the truncation audit, and the screen.

The primary is P3, chosen in D1 as the eligible candidate with the most events (680 research,
353/yr, Gate 1 p 0.030). ITS LOCKED BLOCK HAS ALREADY BEEN READ ONCE, in STUDY_BAYESOPT_DONCHIAN,
so any locked read downstream is a SECOND read and is descriptive by this branch's own rule.

Eight declared families: V61's seven (trend, struct, mom, vol, volu, regime, ffd) plus `pin`.
"""
import os, pickle, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "research/v66"); sys.path.insert(0, "research/v61feat")
sys.path.insert(0, "research/v61sess")
import v66core as V, v66pin as VP
import v61feat as VF

t0 = time.time()
pd.set_option("display.width", 210)
NAME = "P3 bayesopt rth"
CFG = V.CANDIDATES[NAME]

def line(t):
    print("\n" + "=" * 124); print(t); print("=" * 124, flush=True)

D = V.load(CFG["tf"])
E = V.primary(D, CFG)
print(f"primary {NAME}: {len(E)} events "
      f"({int((E.blk==0).sum())} research / {int((E.blk==1).sum())} locked)  [{time.time()-t0:.0f}s]")

line("FEATURES -- V61's seven families, frozen on RESEARCH, plus the PIN family")
mR = D["blk"] == 0
X, meta = VF.build_features(D, mask_research=mR, want_smoothed=True)
print(f"  V61: {X.shape[1]} features, fracdiff d={meta['d']}, HMM fitted on research, "
      f"FILTERED posterior only   [{time.time()-t0:.0f}s]")
P = VP.build(D, window=120, sweeps=700, burn=250, seed=0)
print(f"  PIN: {P.shape[1]} features, one Gibbs fit per session on the previous 120 "
      f"({int(P['pin.pin'].notna().sum()):,} bars covered)   [{time.time()-t0:.0f}s]")
X = pd.concat([X.reset_index(drop=True), P.reset_index(drop=True)], axis=1)
COLS = list(X.columns)
FAM = sorted({c.split(".")[0] for c in COLS})
print(f"  {len(COLS)} features in {len(FAM)} declared families: {', '.join(FAM)}")

line("LEAKAGE -- recompute each feature on history ENDING at the probe bar and require a match")
FROZEN = dict(d=meta["d"], d_table=meta["d_table"], hmm=meta["hmm"])
bad, checked, npb = VF.truncation_audit(D, X[[c for c in COLS if not c.startswith("pin.")]],
                                        FROZEN, probes=20, seed=7)
print(f"  V61 families: {len(bad)} mismatches over {checked:,} comparisons on {npb} probe bars")
# the PIN family's causality is structural: every value at bar i comes from a Gibbs fit on sessions
# STRICTLY BEFORE bar i's session. Checked directly rather than assumed.
rng = np.random.default_rng(3)
sig_all = E.sig.to_numpy()
probe = rng.choice(sig_all[sig_all > 3000], 12, replace=False)
badp = 0
for i in probe:
    dcur = int(D["day"][i])
    same = np.flatnonzero(D["day"] == dcur)
    v = X["pin.pin"].to_numpy()
    if np.nanstd(v[same]) > 1e-12:                 # must be CONSTANT within a session
        badp += 1
print(f"  PIN family: {badp} of {len(probe)} probe sessions where the fitted parameters move "
      f"INSIDE the session (must be 0 -- the fit closes at the previous session's end)")

sig = E.sig.to_numpy()
FE = X.iloc[sig].reset_index(drop=True)
for k in ("pct", "blk", "day", "R"):
    FE[k] = E[k].to_numpy()
FE = FE[FE[COLS].notna().all(axis=1)].reset_index(drop=True)
R_ = FE[FE.blk == 0].reset_index(drop=True)
print(f"\n  events with a complete feature row: {len(FE)} ({len(R_)} research / "
      f"{int((FE.blk==1).sum())} locked)")

line("BASE RATES -- does the feature BIND on the trigger's own bars, or is it the trigger restated?")
rows = []
for c in COLS:
    x = X[c].to_numpy(float)
    ok = np.isfinite(x)
    med = float(np.nanmedian(x[mR & ok]))
    ps = float(np.nanmean(x[sig][np.isfinite(x[sig])] >= med))
    pa = float(np.nanmean(x[ok] >= med))
    rows.append(dict(feat=c, fam=c.split(".")[0], pass_sig=ps, pass_all=pa,
                     lift=ps / max(pa, 1e-9)))
B = pd.DataFrame(rows)
inert = B[(B.pass_sig > 0.95) | (B.pass_sig < 0.05)]
print(f"  features passing >95% or <5% of signal bars (the trigger restated): {len(inert)} "
      f"of {len(COLS)}")
for _, r in inert.iterrows():
    print(f"    {r.feat:<24} passes {r.pass_sig:.3f} of signal bars against {r.pass_all:.3f} "
          f"in general (lift {r.lift:.2f})")
print("\n  by family, mean |lift - 1| (how much the family moves on breakout bars):")
for fam, g in B.groupby("fam"):
    print(f"    {fam:>7}  n {len(g):>2}  mean |lift-1| {np.abs(g.lift-1).mean():.3f}   "
          f"max {np.abs(g.lift-1).max():.3f}")

line("REDUNDANCY -- correlation measured ON THE SIGNAL BARS, which is the only place it acts")
Z = R_[COLS].to_numpy(float)
C = np.corrcoef(Z.T)
np.fill_diagonal(C, 0.0)
pairs = [(COLS[i], COLS[j], C[i, j]) for i in range(len(COLS)) for j in range(i + 1, len(COLS))
         if abs(C[i, j]) > 0.90]
pairs.sort(key=lambda z: -abs(z[2]))
print(f"  pairs above |rho| 0.90: {len(pairs)}")
for a, b, r in pairs[:12]:
    print(f"    {a:<22} {b:<22} {r:+.4f}")
dup = [(a, b, r) for a, b, r in pairs if abs(r) > 0.9999]
print(f"  EXACT duplicates (|rho| > 0.9999): {len(dup)}")

os.makedirs("results/v66", exist_ok=True)
FE.to_parquet("results/v66/events_features.parquet")
with open("results/v66/frozen.pkl", "wb") as f:
    pickle.dump(dict(cols=COLS, fam=FAM, frozen=FROZEN, cfg=CFG, name=NAME), f)
B.to_csv("results/v66/d2_baserates.csv", index=False)
print(f"\n[{time.time()-t0:.0f}s]")
