"""M2 -- THE HMM, INTERROGATED BEFORE IT IS CREDITED.

Three questions the branch has already answered on two other instruments, asked again here because
an answer that does not reproduce is not an answer:

  1. IS THE CAUSAL BOUNDARY REAL? `STUDY_V27_HMM` measured fit-on-all + SMOOTHED decode at locked
     PF 1.351 against the causal version of the SAME model and rule at 0.973, with NEARLY IDENTICAL
     TRADE COUNTS. Filtered-vs-smoothed agreement runs 96-97%, which is why the leak is invisible.
     Both are computed here and the leaky one is run as a gate to price it.
  2. IS THE HMM A VOLATILITY READING WEARING A MARKOV COSTUME? `STUDY_V67`: p_side correlates
     -0.478 with realised vol and 0 of 32 cells had any HMM column beat the best of 71 volatility
     features. `STUDY_V61_FEATURES_15M`: vol.rv96 vs regime.hmm_side reads 0.945.
  3. DOES THE MARKOV APPARATUS ADD ANYTHING TO THE STATE LABEL? `STUDY_V27`: state==Bull vs
     signal>0.3 had Jaccard 1.0000 -- dismissible as a three-valued-signal artefact. `STUDY_V67`
     reproduced it at 0.9757 on a signal with 25,044 distinct values, which is not dismissible.
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
X = pd.read_parquet(os.path.join(C.OUT, "m1_features.parquet"))
with open(os.path.join(C.OUT, "m1_frozen.pkl"), "rb") as fh:
    Z = pickle.load(fh)
filt = np.load(os.path.join(C.OUT, "m1_filtered.npy"))
smoo = np.load(os.path.join(C.OUT, "m1_smoothed.npy"))
PRIMARY = Z["primary"]
sig, _ = C.arm_signals(f, PRIMARY, M=M)
sr = sig[MR[sig]]
allbars = np.flatnonzero(np.isfinite(X["vol.rv96"].to_numpy()))

C.line("M2.1  FILTERED vs SMOOTHED -- the diagnostic, never a feature")
lf, ls = filt.argmax(1), smoo.argmax(1)
print(f"  argmax agreement, all bars      : {float((lf == ls).mean()):.4f}  ({len(lf)} bars)")
print(f"  argmax agreement, signal bars   : {float((lf[sig] == ls[sig]).mean()):.4f}")
print(f"  mean |P_bull filtered - smoothed|: {float(np.abs(filt[:,2]-smoo[:,2]).mean()):.4f}")
print("\n  STUDY_V27 read 96.0-96.8% on two other instruments. A 96% agreement is exactly the\n"
      "  regime in which the leak is easy to miss: the trade COUNT barely moves and which bars\n"
      "  got labelled does.")

C.line("M2.2  PRICING THE LEAK -- the same gate read both ways on the primary")
print("  A bull-state gate on the primary's own signal bars, research block, at matched\n"
      "  selectivity. The smoothed column is NEVER used downstream; this exists to show what it\n"
      "  would have bought if it had been.\n")
print(f"{'gate':34s} {'n':>5} {'pts/tr':>8} {'PF':>7} {'kept':>7}")
base = C.locked(f, PRIMARY, M=M, blk=MR)
print(f"{'ungated':34s} {len(base):>5} {base.pts.mean():>+8.3f} {C.pf(base.pts.to_numpy()):>7.3f} "
      f"{1.0:>7.3f}")
rows = []
for q in (0.75, 0.5, 0.25):
    for nm, arr in (("filtered (causal)", filt), ("smoothed (LEAKY)", smoo)):
        thr = np.nanquantile(arr[sr, 2], 1 - q)
        g = arr[:, 2] >= thr
        t = C.locked(f, PRIMARY, M=M, gate=g, blk=MR)
        if not len(t):
            continue
        p = t.pts.to_numpy()
        rows.append(dict(gate=nm, keep=q, n=len(t), pts=p.mean(), pf=C.pf(p)))
        print(f"{nm + f'  keep {q:.2f}':34s} {len(t):>5} {p.mean():>+8.3f} {C.pf(p):>7.3f} "
              f"{len(t)/len(base):>7.3f}")
LK = pd.DataFrame(rows)
LK.to_csv(os.path.join(C.OUT, "m2_leak.csv"), index=False)
d = LK.pivot(index="keep", columns="gate", values="pf")
print(f"\n  mean PF advantage of the leaky decode: "
      f"{float((d['smoothed (LEAKY)'] - d['filtered (causal)']).mean()):+.3f} profit factor, "
      f"on trade counts that move by "
      f"{float((LK[LK.gate.str.startswith('smoothed')].n.to_numpy() / LK[LK.gate.str.startswith('filtered')].n.to_numpy() - 1).mean()*100):+.1f}%")

C.line("M2.3  IS THE HMM A VOLATILITY READING? correlation on the SIGNAL BARS")
hcols = [c for c in X.columns if c.startswith("hmm.")]
vcols = [c for c in X.columns if c.startswith("vol.")]
Cm = X.iloc[sr][hcols + vcols].corr(method="spearman").loc[hcols, vcols]
print(Cm.round(3).to_string())
best = Cm.abs().max(axis=1)
print("\n  strongest volatility partner of each HMM column:")
for h in hcols:
    j = Cm.loc[h].abs().idxmax()
    print(f"    {h:16s} {j:20s} {Cm.loc[h, j]:+.4f}")
print(f"\n  max |rho| anywhere in the block: {float(Cm.abs().max().max()):.4f}   "
      f"mean over HMM columns: {float(best.mean()):.4f}")
Cm.to_csv(os.path.join(C.OUT, "m2_hmm_vol_corr.csv"))

C.line("M2.4  THE COLLAPSE TEST -- does the Markov apparatus add to the state label?")
edge = X["hmm.edge"].to_numpy()
fwd = X["hmm.fwd12"].to_numpy()
lab = filt.argmax(1)
print(f"  distinct values of hmm.edge  : {len(np.unique(np.round(edge[allbars], 10))):>8,}")
print(f"  distinct values of hmm.fwd12 : {len(np.unique(np.round(fwd[allbars], 10))):>8,}")
print(f"\n{'set A':28s} {'set B':28s} {'Jaccard':>8}")


def jac(a, b):
    a, b = np.asarray(a, bool), np.asarray(b, bool)
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else np.nan


bull = lab[allbars] == 2
for nm, s in (("hmm.edge > 0.30", edge[allbars] > 0.30),
              ("hmm.edge > 0", edge[allbars] > 0),
              ("hmm.fwd12 > 0", fwd[allbars] > 0),
              ("hmm.bull > 0.50", filt[allbars, 2] > 0.5)):
    print(f"{'state == bull':28s} {nm:28s} {jac(bull, s):>8.4f}")
print(f"{'hmm.fwd12 > 0':28s} {'hmm.edge > 0':28s} "
      f"{jac(fwd[allbars] > 0, edge[allbars] > 0):>8.4f}")
print(f"\n  rho(hmm.fwd12, hmm.edge) on signal bars: "
      f"{float(pd.Series(fwd[sr]).corr(pd.Series(edge[sr]), method='spearman')):+.4f}")
print("  A twelve-step matrix power that reproduces the one-step edge at Jaccard ~1 is the same\n"
      "  filter wearing two names. STUDY_V27 measured 1.0000 on a three-valued signal and\n"
      "  STUDY_V67 0.9757 on a 25,044-valued one.")

C.line("M2.5  DOES ANY HMM COLUMN BEAT THE BEST VOLATILITY FEATURE AT PREDICTING THE LABEL?")
u = C.unlocked(f, "base", M=M)
u = u[u.ts < "2023-01-01"].reset_index(drop=True)
y = u.pts.to_numpy()
xs = u.sig_bar.to_numpy()
rows = []
for c in hcols + vcols:
    v = X[c].to_numpy()[xs]
    m = np.isfinite(v) & np.isfinite(y)
    rows.append(dict(col=c, fam=c.split(".")[0],
                     ic=float(pd.Series(v[m]).corr(pd.Series(y[m]), method="spearman")), n=int(m.sum())))
IC = pd.DataFrame(rows).assign(abs_ic=lambda d: d.ic.abs()).sort_values("abs_ic", ascending=False)
print(IC.head(12).to_string(index=False))
bh = IC[IC.fam == "hmm"].abs_ic.max()
bv = IC[IC.fam == "vol"].abs_ic.max()
print(f"\n  best |IC| among HMM columns        : {bh:.4f}  "
      f"({IC[IC.fam=='hmm'].sort_values('abs_ic').iloc[-1].col})")
print(f"  best |IC| among volatility columns : {bv:.4f}  "
      f"({IC[IC.fam=='vol'].sort_values('abs_ic').iloc[-1].col})")
print(f"  ratio {bh/bv:.3f}   -- STUDY_V67 found 0 of 32 cells where the HMM won.")
IC.to_csv(os.path.join(C.OUT, "m2_hmm_ic.csv"), index=False)
print(f"\n[m_run2 done in {time.time()-t0:.0f}s]")
