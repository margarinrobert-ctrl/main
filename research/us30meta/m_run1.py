"""M1 -- GATE 1 on all four arms, then the features, the truncation audit, the base rates and the
signal-bar correlation matrix. Nothing is modelled here.

ORDER MATTERS AND IT IS THE ARCHITECTURE'S: the primary is scored ALONE, before a single feature
exists, against a matched random entry with identical geometry, exits and position lock. If no arm
clears that, no meta layer is entitled to be built and the study stops. Only then are the features
computed, audited for causality, and screened for the thing that has killed four confirmation
families on this branch -- a condition the trigger already implies.
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
import m_feat as MF    # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 220)
print(__doc__)
t0 = time.time()

f = C.S.load("US30L")
bl = C.S.blocks(f, "US30L")
MR, MH = bl["A_research"], bl["B_holdout"]
M = C.L.build_masks(f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy())
CUT_A = "2023-01-01"
ARMS = ["base", "+adx<=20", "+ema align", "+both", "conventional"]

# ------------------------------------------------------------------ GATE 1
C.line("M1.1  GATE 1 -- the primary alone, research block, against a matched random ENTRY")
print("  Null: the same number of entries drawn from every eligible in-window bar, SORTED so the\n"
      "  position lock rejects the same share, identical geometry / exits / cost / flatten.\n")
print(f"{'arm':14s} {'n':>5} {'pts/tr':>8} {'PF':>6} {'win':>6} {'sd':>6} {'MDE':>7} "
      f"{'in MDE':>7} {'ctl med':>8} {'ctl p':>7} {'boot p':>7}")
g1 = []
for arm in ARMS:
    t = C.locked(f, arm, M=M, blk=MR)
    p = t["pts"].to_numpy()
    ctl = C.matched_entry_control(f, arm, len(t), M=M, blk=MR, n_draw=400, seed=11)
    cp = float(np.mean(ctl >= p.mean())) if ctl is not None else np.nan
    _, bp = C.day_bootstrap(p, t.ts.dt.normalize().to_numpy(), n=2000, seed=3)
    m = C.mde(p.std(ddof=1), len(p))
    g1.append(dict(arm=arm, n=len(p), pts=p.mean(), pf=C.pf(p), win=(p > 0).mean(),
                   sd=p.std(ddof=1), mde=m, ctl_med=np.median(ctl), ctl_p=cp, boot_p=bp))
    print(f"{arm:14s} {len(p):>5} {p.mean():>+8.3f} {C.pf(p):>6.3f} {(p>0).mean():>6.3f} "
          f"{p.std(ddof=1):>6.1f} {m:>7.2f} {'YES' if p.mean()<m else 'no':>7} "
          f"{np.median(ctl):>+8.3f} {cp:>7.3f} {bp:>7.3f}", flush=True)
G1 = pd.DataFrame(g1)
G1.to_csv(os.path.join(C.OUT, "m1_gate1.csv"), index=False)
ok = G1[(G1.ctl_p <= 0.05) & (G1.pts > 0)]
print(f"\n  arms clearing the matched entry at p<=0.05: {len(ok)} of {len(G1)}  "
      f"-> {list(ok.arm) if len(ok) else 'NONE'}")
print("  Arms INSIDE their own MDE: "
      f"{int((G1.pts < G1.mde).sum())} of {len(G1)} -- direction, not size.")

C.line("M1.2  THE DECLARED PRIMARY, and the two event streams")
PRIMARY = "+adx<=20"
print(f"  Primary declared: `{PRIMARY}` -- the only arm clearing Gate 1 and the only arm positive\n"
      f"  on all three blocks in STUDY_US30_SCALP_0711 section 13.\n")
print(f"{'arm':14s} {'locked A':>9} {'locked B':>9} {'unlocked A':>11} {'unlocked B':>11}")
for arm in ARMS[:4]:
    u = C.unlocked(f, arm, M=M)
    ua, ub = int((u.ts < CUT_A).sum()), int((u.ts >= CUT_A).sum())
    la, lb = len(C.locked(f, arm, M=M, blk=MR)), len(C.locked(f, arm, M=M, blk=MH))
    print(f"{arm:14s} {la:>9} {lb:>9} {ua:>11} {ub:>11}")
print("\n  TRAINING uses the UNLOCKED `base` stream -- every eligible Donchian-20 long in-window\n"
      "  signal bar labelled with the points it would have earned under the identical geometry.\n"
      "  STUDY_S3_NEURAL_NET: the lock decides which events one ACCOUNT can take, not which have a\n"
      "  well-defined outcome; 400 rows against 55 features is fitting noise. STUDY_CONFORMAL made\n"
      "  the same move from the other side. EVERY SCORED NUMBER IS STILL A LOCKED NUMBER.")

C.line("M1.3  FEATURES -- built once, HMM and fracdiff FROZEN on the research block")
X, Z = MF.build(f, mask_research=MR, want_smoothed=True)
print(f"  {X.shape[1]} features in {len(set(MF.fam(c) for c in X.columns))} declared families "
      f"({', '.join(sorted(set(MF.fam(c) for c in X.columns)))})")
print(f"  fracdiff d = {Z['d']} chosen by ADF on the RESEARCH BLOCK ONLY, fixed window "
      f"{Z['ffd_window']} bars")
print(Z["d_table"].to_string(index=False))
hp = Z["hmm"]
o = hp["order"]
print(f"\n  HMM K=3, Baum-Welch on research only, loglik {hp['ll']:.1f}")
print("  state means (return %, rolling vol %) after ordering by drift:")
for i, k in enumerate(o):
    print(f"    state {i} ({['bear','side','bull'][i]}): mu {hp['mu'][k][0]:+.5f} "
          f"{hp['mu'][k][1]:.4f}   self-transition {hp['A'][k, k]:.4f}")

C.line("M1.4  TRUNCATION AUDIT -- recompute every feature on history ENDING at bar i")
probes = int(os.environ.get("PROBES", 20))
rng = np.random.default_rng(7)
lo = 20000
idx = np.sort(rng.choice(np.arange(lo, int(np.flatnonzero(MR)[-1])), size=probes, replace=False))
bad, checked = [], 0
for i in idx:
    Xi, _ = MF.build(f.iloc[:i + 1], frozen=Z)
    a, b = X.iloc[i], Xi.iloc[-1]
    for col in X.columns:
        va, vb = a[col], b[col]
        if not np.isfinite(va) and not np.isfinite(vb):
            continue
        checked += 1
        if not np.isclose(va, vb, rtol=1e-6, atol=1e-8):
            bad.append((int(i), col, float(va), float(vb)))
    print(f"    probe bar {i}  mismatches so far {len(bad)}", flush=True)
print(f"\n  TRUNCATION AUDIT: {len(bad)} mismatches of {checked} value comparisons "
      f"over {len(idx)} probes")
if bad:
    print(pd.DataFrame(bad, columns=["bar", "col", "full", "truncated"]).head(20).to_string(index=False))

C.line("M1.5  BASE RATES ON THE TRIGGER'S OWN BARS -- what does the breakout already imply?")
print("  For a continuous feature the analogue of a >95% pass rate is the share of SIGNAL bars\n"
      "  above the POPULATION median. Near 1.0 or 0.0 means the trigger determines the feature and\n"
      "  it cannot refuse anything (RSI>=55 on 94.7% of breakout bars, Aroon 100.0%, MACD 99.8%).\n")
sig, _ = C.arm_signals(f, "base", M=M)
mod = f["mod"].to_numpy()
pop = np.flatnonzero((mod >= C.S.W0) & (mod < C.S.W1) & MR)
sr = sig[MR[sig]]
rows = []
for col in X.columns:
    xa = X[col].to_numpy()
    med = np.nanmedian(xa[pop])
    sh = float(np.nanmean(xa[sr] > med))
    cv = float(np.nanstd(xa[sr]) / max(abs(np.nanmean(xa[sr])), 1e-9))
    rows.append(dict(col=col, share_above_pop_median=sh, lift=sh / 0.5, cv=cv,
                     inert=bool(sh > 0.95 or sh < 0.05 or cv < 1e-6)))
BR = pd.DataFrame(rows).sort_values("share_above_pop_median", ascending=False)
BR.to_csv(os.path.join(C.OUT, "m1_baserates.csv"), index=False)
print(BR.head(10).to_string(index=False))
print("  ...")
print(BR.tail(6).to_string(index=False))
inert = list(BR[BR.inert].col)
print(f"\n  INERT (>95% or <5% of signal bars on one side, or constant): {len(inert)} -> {inert}")
print(f"  max |lift - 1| = {float((BR.lift - 1).abs().max()):.3f} "
      f"({BR.loc[(BR.lift-1).abs().idxmax(), 'col']})")

C.line("M1.6  SIGNAL-BAR CORRELATION -- collapse anything above |rho| 0.90")
keep = [c for c in X.columns if c not in inert]
Xs = X.iloc[sr][keep]
Cm = Xs.corr(method="spearman")
np.fill_diagonal(Cm.values, np.nan)
pairs = (Cm.abs().stack().sort_values(ascending=False)
         .reset_index().drop_duplicates(subset=0, keep="first"))
pairs.columns = ["a", "b", "rho"]
seen, dup = set(), []
for _, r in pairs.iterrows():
    if r.rho < 0.90:
        break
    k = tuple(sorted((r.a, r.b)))
    if k in seen:
        continue
    seen.add(k)
    dup.append((r.a, r.b, float(Cm.loc[r.a, r.b])))
print(f"  pairs at |rho| >= 0.90 on the signal bars: {len(dup)}")
for a, b, rr in dup:
    print(f"    {a:22s} {b:22s} {rr:+.4f}")
drop = set()
for a, b, _ in dup:
    if a not in drop and b not in drop:
        drop.add(b)
COLS = [c for c in keep if c not in drop]
print(f"\n  collapsed: {len(X.columns)} declared -> {len(keep)} after inert -> {len(COLS)} after "
      f"|rho|>=0.90  (dropped {sorted(drop)})")
top = pairs[pairs.rho < 0.90].head(8)
print("\n  strongest surviving pairs:")
for _, r in top.iterrows():
    print(f"    {r.a:22s} {r.b:22s} {float(Cm.loc[r.a, r.b]):+.4f}")

with open(os.path.join(C.OUT, "m1_frozen.pkl"), "wb") as fh:
    pickle.dump(dict(d=Z["d"], hmm=Z["hmm"], ffd_window=Z["ffd_window"], cols=COLS,
                     inert=inert, dropped=sorted(drop), primary=PRIMARY,
                     audit_bad=len(bad), audit_checked=checked, audit_probes=len(idx)), fh)
X.to_parquet(os.path.join(C.OUT, "m1_features.parquet"))
np.save(os.path.join(C.OUT, "m1_smoothed.npy"), Z["smoothed"])
np.save(os.path.join(C.OUT, "m1_filtered.npy"), Z["filt"])
print(f"\n[m_run1 done in {time.time()-t0:.0f}s]")
