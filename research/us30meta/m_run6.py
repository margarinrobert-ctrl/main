"""M6 -- THE CALIBRATION POST-MORTEM, and the one diagnostic that separates the two failures.

M5's one read came back with a threshold that keeps 0.70 of the research signal bars, 0.34-0.39 of
the holdout's and 0.12-0.19 of the forward feed's. A score whose threshold does not mean the same
thing out of sample makes every research rung meaningless -- `STUDY_AUTOBNN` recorded the same
defect with the opposite sign (a research cut that kept 105 of 105 locked events).

Two very different things produce that, and they have different verdicts:
  (a) THE SCORE RANKS CORRECTLY AND THE THRESHOLD DRIFTS. Fixable: cut by RANK inside each block.
  (b) THE SCORE'S INPUTS DRIFT. Not fixable by re-cutting -- the model is reading a level.

So: the block drift of every input, then the same gate cut BY RANK so selectivity is fixed by
construction. The rank cut is a DIAGNOSTIC and is counted as trials; it is not a new candidate,
because it was chosen after the reserved blocks were read.
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
import m_ml as ML      # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 230)
print(__doc__)
t0 = time.time()
KEEP = 0.70

f = C.S.load("US30L")
bl = C.S.blocks(f, "US30L")
MR, MH = bl["A_research"], bl["B_holdout"]
M = C.masks(f)
X = pd.read_parquet(os.path.join(C.OUT, "m1_features.parquet"))
with open(os.path.join(C.OUT, "m1_frozen.pkl"), "rb") as fh:
    Z = pickle.load(fh)
with open(os.path.join(C.OUT, "m4_set.pkl"), "rb") as fh:
    S4 = pickle.load(fh)
E = pd.read_parquet(os.path.join(C.OUT, "m3_events.parquet"))
R = E[E.blk == 0].reset_index(drop=True)
SET, KIND = S4["set"], S4["kind"]
mdl = [ML.fit_full(R, SET, KIND, seed=s) for s in range(5)]
sc_L = np.mean([m["predict"](X[SET].to_numpy(float)) for m in mdl], axis=0)
fi = C.S.load("US30I")
bli = C.S.blocks(fi, "US30I")
Mi = C.masks(fi)
Xi, _ = MF.build(fi, frozen=Z)
sc_I = np.mean([m["predict"](Xi[SET].to_numpy(float)) for m in mdl], axis=0)
BLOCKS = [("A_research", f, MR, M, sc_L, X), ("B_holdout", f, MH, M, sc_L, X),
          ("C_forward", fi, bli["C_forward"], Mi, sc_I, Xi)]
ARMS = ("+ema34>89", "+adx<=20")

C.line("M6.1  WHY THE THRESHOLD MOVED -- block drift of the score and of every input")
rows = []
ref = None
for bn, feed, blk, Mx, scx, Xx in BLOCKS:
    sg, _ = C.arm_signals(feed, "base", M=Mx)
    sg = sg[blk[sg]]
    d = dict(block=bn, n=len(sg), score_mean=float(np.nanmean(scx[sg])),
             score_sd=float(np.nanstd(scx[sg])))
    for c in SET:
        d[c] = float(np.nanmean(Xx[c].to_numpy()[sg]))
    rows.append(d)
DR = pd.DataFrame(rows).set_index("block")
sd0 = {c: float(np.nanstd(X[c].to_numpy()[C.arm_signals(f, "base", M=M)[0][MR[C.arm_signals(f, "base", M=M)[0]]]])) for c in SET}
print("  mean on the signal bars, and the same expressed in RESEARCH standard deviations:")
print(f"{'feature':18s} {'A':>10} {'B':>10} {'C':>10} | {'B-A (sd)':>9} {'C-A (sd)':>9}")
print(f"{'SCORE':18s} {DR.score_mean.iloc[0]:>10.3f} {DR.score_mean.iloc[1]:>10.3f} "
      f"{DR.score_mean.iloc[2]:>10.3f} | "
      f"{(DR.score_mean.iloc[1]-DR.score_mean.iloc[0])/DR.score_sd.iloc[0]:>9.2f} "
      f"{(DR.score_mean.iloc[2]-DR.score_mean.iloc[0])/DR.score_sd.iloc[0]:>9.2f}")
drift = []
for c in SET:
    a, b, cc = DR[c].iloc[0], DR[c].iloc[1], DR[c].iloc[2]
    s = max(sd0[c], 1e-12)
    drift.append(dict(col=c, A=a, B=b, C=cc, dB=(b - a) / s, dC=(cc - a) / s))
    print(f"{c:18s} {a:>10.3f} {b:>10.3f} {cc:>10.3f} | {(b-a)/s:>9.2f} {(cc-a)/s:>9.2f}")
DF = pd.DataFrame(drift).assign(m=lambda d: d[["dB", "dC"]].abs().max(axis=1)).sort_values("m", ascending=False)
DF.to_csv(os.path.join(C.OUT, "m6_drift.csv"), index=False)
print(f"\n  worst-drifting input: {DF.iloc[0].col} at {DF.iloc[0].m:.2f} research sd")

C.line("M6.2  IS `ffd.price` LEVEL-FREE? -- the truncated weight sum")
for d in (0.2, 0.4, 0.6, 0.8, 1.0):
    w = MF.ffd_weights(d)
    print(f"    d {d:.1f}   window {len(w):>5}   sum(w) {w.sum():+.6f}   "
          f"|sum| x log-price range {abs(w.sum()) * float(np.log(f.close.max()/f.close.min())):.6f}")
w = MF.ffd_weights(Z["d"])
lc = np.log(f["close"].to_numpy())
print(f"\n  At d={Z['d']} the weights sum to {w.sum():+.6f}, NOT zero: a fixed-width fractional")
print("  difference truncated at tau=1e-4 keeps a LEVEL term. US30 log price rises "
      f"{float(lc.max()-lc.min()):.3f} over this file, so the level term alone moves ffd.price by "
      f"{abs(w.sum())*float(lc.max()-lc.min()):.4f}")
print(f"  measured block means of ffd.price on signal bars: "
      f"A {DR['ffd.price'].iloc[0]:+.4f}  B {DR['ffd.price'].iloc[1]:+.4f}  "
      f"C {DR['ffd.price'].iloc[2]:+.4f}")

C.line("M6.3  THE RANK CUT -- selectivity fixed by construction (DIAGNOSTIC, read after the fact)")
print("  Same score, same model, but the threshold is the block's OWN 30th percentile over its own\n"
      "  signal bars. This cannot be traded as stated (it needs the block's future distribution),\n"
      "  so it is a diagnostic that separates 'the ranking is wrong' from 'the threshold drifted'.\n")
print(f"{'block':11s} {'arm':11s} {'n off':>6} {'off pts':>8} | {'n on':>5} {'kept':>6} "
      f"{'on pts':>8} {'uplift':>8} {'MDEsplit':>9} {'on PF':>7} {'tot off':>8} {'tot on':>8} "
      f"{'rand p':>7}")
rows = []
for bn, feed, blk, Mx, scx, _ in BLOCKS:
    for arm in ARMS:
        sg, _ = C.arm_signals(feed, arm, M=Mx)
        sg = sg[blk[sg]]
        thr = float(np.nanquantile(scx[sg], 1 - KEEP))
        g = scx >= thr
        b = C.locked(feed, arm, M=Mx, blk=blk)
        t = C.locked(feed, arm, M=Mx, gate=g, blk=blk)
        if not len(t) or not len(b):
            continue
        p, pb = t.pts.to_numpy(), b.pts.to_numpy()
        rej = pb[~g[b.e_bar.to_numpy() - 1]]
        ms = C.mde_split(p, rej) if len(rej) > 2 else np.nan
        nk = int((scx[sg] >= thr).sum())
        rc, _ = C.random_gate_control(feed, arm, nk, M=Mx, blk=blk, n_draw=400, seed=21)
        rp = float(np.mean(rc >= p.mean())) if rc is not None else np.nan
        rows.append(dict(block=bn, arm=arm, n_off=len(pb), off=pb.mean(), n_on=len(p),
                         kept=nk / len(sg), on=p.mean(), uplift=p.mean() - pb.mean(),
                         mde_split=ms, pf=C.pf(p), tot_off=pb.sum(), tot_on=p.sum(), rand_p=rp))
        print(f"{bn:11s} {arm:11s} {len(pb):>6} {pb.mean():>+8.3f} | {len(p):>5} "
              f"{nk/len(sg):>6.3f} {p.mean():>+8.3f} {p.mean()-pb.mean():>+8.3f} {ms:>9.2f} "
              f"{C.pf(p):>7.3f} {pb.sum():>+8.0f} {p.sum():>+8.0f} {rp:>7.3f}", flush=True)
RK = pd.DataFrame(rows)
RK.to_csv(os.path.join(C.OUT, "m6_rankcut.csv"), index=False)
oos = RK[RK.block != "A_research"]
print(f"\n  out-of-sample cells with a positive uplift: {int((oos.uplift > 0).sum())} of {len(oos)}")
print(f"  out-of-sample cells clearing the random gate at p<=0.05: "
      f"{int((oos.rand_p <= 0.05).sum())} of {len(oos)}   best p {oos.rand_p.min():.3f}")
print(f"  cells whose uplift exceeds its own MDE_split: "
      f"{int((RK.uplift.abs() > RK.mde_split).sum())} of {len(RK)}")
print(f"  cells where TOTAL points rise: {int((RK.tot_on > RK.tot_off).sum())} of {len(RK)}")

C.line("M6.4  DOES THE SCORE RANK AT ALL OUT OF SAMPLE? -- IC on the unlocked labelled stream")
print(f"{'block':11s} {'n':>6} {'IC':>9} {'top30 pts':>10} {'bot70 pts':>10} {'all pts':>9}")
for bn, feed, blk, Mx, scx, _ in BLOCKS:
    u = C.unlocked(feed, "base", M=Mx)
    sb = u.sig_bar.to_numpy()
    keep = blk[sb]
    u, sb = u[keep], sb[keep]
    y = u.pts.to_numpy()
    s = scx[sb]
    m = np.isfinite(s) & np.isfinite(y)
    icv = float(pd.Series(s[m]).corr(pd.Series(y[m]), method="spearman"))
    thr = np.nanquantile(s, 1 - 0.30)
    print(f"{bn:11s} {len(y):>6} {icv:>+9.4f} {y[s >= thr].mean():>+10.3f} "
          f"{y[s < thr].mean():>+10.3f} {y.mean():>+9.3f}")
print("\n  This is the ranking question with the threshold taken out of it. A positive IC with a\n"
      "  broken threshold is failure (a); a null IC is failure (b).")
print(f"\n[m_run6 done in {time.time()-t0:.0f}s]")
