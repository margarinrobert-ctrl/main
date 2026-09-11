"""THE SHIPPED PINE'S FEATURE MATH, IN PYTHON, DIFFED AGAINST THE RESEARCH.

Two of the eight features are not ordinary indicators and could silently differ:

  FRACDIFF  the research builds the weights with numpy and convolves; the Pine builds them with a
            recursion at bar 0 and dots them against `logCvd[k]`. The ORDERING is the risk: get it
            backwards and the feature is a different series that still looks plausible.
  HMM       the research runs `posterior_filtered`; the Pine runs the forward recursion by hand in
            probability space with per-bar normalisation. Same object only if pi, A, mu, var and the
            state ORDER all line up.

Two smaller things are checked because they are known to differ by convention:
  * `ta.stdev` in Pine is POPULATION (ddof 0); pandas `.std()` is SAMPLE (ddof 1). At n = 96 and 500
    that is a factor of 1.0052 and 1.0010 on the standard deviation, which flows into `f_cvdZ` and
    into the HMM's second observation channel.
  * the Pine uses an EXPANDING minimum to shift the CVD before the log; the research used the
    GLOBAL minimum. That min sits at bar 177, before any event, so the two agree on 100% of the bars
    that matter -- but only the expanding one is causal by construction, which is why it ships.
"""
from __future__ import annotations

import os
import sys
import warnings

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "research/v61sess"))
import v61feat as V       # noqa: E402
import sess_core as S     # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 220)


def line(t):
    print("\n" + "=" * 120)
    print(t)
    print("=" * 120, flush=True)


print(__doc__)
D = S.build(15)
mR = D["blk"] == 0
X, meta = V.build_features(D, mask_research=mR)
hp = meta["hmm"]
o = hp["order"]
c, h, l, atr, n = D["c"], D["h"], D["l"], D["atr"], D["n"]

line("1  FRACDIFF -- the Pine's recursion and dot product, reproduced")
W_RES = V.ffd_weights(0.8)                       # oldest-first, 1.0 last
wk = 1.0
w_pine = [1.0]
for k in range(1, 201):
    wk = -wk * (0.8 - k + 1) / k
    if abs(wk) < 1e-4:
        break
    w_pine.append(wk)
w_pine = np.array(w_pine)                        # newest-first, 1.0 first
print(f"  research weights {len(W_RES)}, Pine weights {len(w_pine)}   "
      f"max |diff| after reversing: {np.max(np.abs(W_RES[::-1] - w_pine)):.3e}")

cv = D["cv"]
run_min = pd.Series(cv).expanding().min().to_numpy()
log_pine = np.log(np.maximum(cv - run_min + 1.0, 1e-9))
log_res = np.log(cv - np.nanmin(cv) + 1.0)
print(f"  expanding-min vs global-min log series: identical on "
      f"{100*np.mean(np.isclose(log_pine, log_res)):.2f}% of bars, first divergence at bar "
      f"{int(np.argmax(~np.isclose(log_pine, log_res))) if not np.all(np.isclose(log_pine,log_res)) else -1}")

L = len(w_pine)
ffd_pine = np.full(n, np.nan)
for i in range(L - 1, n):
    ffd_pine[i] = float(np.dot(w_pine, log_pine[i - L + 1:i + 1][::-1]))
ffd_res, _ = V.ffd(log_res, 0.8)
m = np.isfinite(ffd_pine) & np.isfinite(ffd_res)
print(f"  FFD over ALL bars incl. warm-up: max |diff| {np.max(np.abs(ffd_pine[m]-ffd_res[m])):.3e}, "
      f"correlation {np.corrcoef(ffd_pine[m], ffd_res[m])[0,1]:.4f}")
WARM = 300
m2 = m.copy(); m2[:WARM] = False
print(f"  FFD from bar {WARM} on (the first event is ~bar 1000, and f_cvdZ needs 500 more): "
      f"max |diff| {np.max(np.abs(ffd_pine[m2]-ffd_res[m2])):.3e}, "
      f"correlation {np.corrcoef(ffd_pine[m2], ffd_res[m2])[0,1]:.12f}")
print("  -> the two are EXACT once the fracdiff window has filled and the expanding minimum has")
print("     settled at bar 177. Every difference is warm-up, and no event lives there.")

line("2  HMM -- the Pine's forward recursion in probability space, reproduced")
r = np.zeros(n)
r[1:] = np.diff(np.log(c))
rv_samp = pd.Series(r).rolling(96).std().to_numpy()          # research: ddof 1
rv_pop = pd.Series(r).rolling(96).std(ddof=0).to_numpy()     # Pine ta.stdev: ddof 0
PI = hp["pi"][o]
A = hp["A"][np.ix_(o, o)]
MU = hp["mu"][o]
VAR = hp["var"][o]


def fwd(rv):
    x1 = r * 100.0
    x2 = np.nan_to_num(rv * 100.0, nan=0.0)
    a = None
    out = np.full(n, np.nan)
    for i in range(n):
        if not np.isfinite(x1[i]) or not np.isfinite(rv[i]):
            continue
        b = np.array([np.exp(-0.5 * (((x1[i] - MU[k, 0]) ** 2) / VAR[k, 0]
                                     + ((x2[i] - MU[k, 1]) ** 2) / VAR[k, 1]))
                      / np.sqrt(VAR[k, 0] * VAR[k, 1]) for k in range(3)])
        p = PI if a is None else a @ A
        nn = p * b
        t = nn.sum()
        if t > 0 and np.isfinite(t):
            a = nn / t
            out[i] = a[1]
    return out


side_pine = fwd(rv_pop)
side_pine_samp = fwd(rv_samp)
side_res = X["regime.hmm_side"].to_numpy()
m = np.isfinite(side_pine) & np.isfinite(side_res)
print(f"  Pine recursion (ddof 0, as ta.stdev) vs research: max |diff| "
      f"{np.max(np.abs(side_pine[m]-side_res[m])):.3e}, correlation "
      f"{np.corrcoef(side_pine[m], side_res[m])[0,1]:.8f}")
m2 = np.isfinite(side_pine_samp) & np.isfinite(side_res)
print(f"  same recursion with ddof 1 (matching pandas)  : max |diff| "
      f"{np.max(np.abs(side_pine_samp[m2]-side_res[m2])):.3e}, correlation "
      f"{np.corrcoef(side_pine_samp[m2], side_res[m2])[0,1]:.10f}")
print("  -> the residual is the standard-deviation convention alone, and it is small; the recursion")
print("     itself is exact. Both are FILTERED -- alpha_t depends on alpha_{t-1} and bar t only.")

line("3  THE SIX ORDINARY FEATURES")
ehi = pd.Series(h).rolling(20).max().shift(1).to_numpy()
pine = {
    "mom.roc240": 100.0 * (c / np.concatenate((np.full(240, np.nan), c[:-240])) - 1.0),
    "vol.atr_pct": atr / c,
    "trend.er20": V._er(c, 20),
    "trend.er60": V._er(c, 60),
    "regime.chop48": V._chop(h, l, c, 48),
    "struct.excess": (h - ehi) / atr,
}
print(f"  {'feature':18s} {'max |diff|':>12} {'correlation':>14}")
for k_, v_ in pine.items():
    a = X[k_].to_numpy()
    m = np.isfinite(a) & np.isfinite(v_)
    print(f"  {k_:18s} {np.max(np.abs(a[m]-v_[m])):>12.3e} {np.corrcoef(a[m], v_[m])[0,1]:>14.10f}")

line("4  DOES THE CONVENTION GAP MOVE THE DECISION? the ridge score on the primary's events")
E = S.run(D, ent=20, exN=20, stop=2.0, tp=0.0, hold=480, piv_min=90, win_min=600, touch=True,
          g=S.gate(D, 90, 600)[0])
sig = E.sig.to_numpy()
KEEP = ["mom.roc240", "vol.atr_pct", "ffd.cvd_z", "regime.hmm_side", "trend.er20",
        "regime.chop48", "trend.er60", "struct.excess"]
MEAN = [0.366515, 0.001299, 0.830523, 0.344640, 0.187666, 50.360108, 0.123946, 0.469034]
SD = [1.411577, 0.000643, 1.450333, 0.461228, 0.133227, 7.320107, 0.101950, 0.545266]
CO = [0.100522, 0.035454, -0.042431, -0.038275, 0.036386, -0.020397, -0.012324, -0.037647]
cz_pine = (ffd_pine - pd.Series(ffd_pine).rolling(500).mean().to_numpy()) / \
          pd.Series(ffd_pine).rolling(500).std(ddof=0).to_numpy()
P = dict(pine)
P["ffd.cvd_z"] = cz_pine
P["regime.hmm_side"] = side_pine
sR = np.full(n, 0.069665)
sP = np.full(n, 0.069665)
for f_, mn, sd_, co in zip(KEEP, MEAN, SD, CO):
    sR = sR + co * (X[f_].to_numpy() - mn) / sd_
    sP = sP + co * (P[f_] - mn) / sd_
a, b = sR[sig], sP[sig]
m = np.isfinite(a) & np.isfinite(b)
print(f"  ridge score on {int(m.sum())} events: max |diff| {np.max(np.abs(a[m]-b[m])):.3e}, "
      f"correlation {np.corrcoef(a[m], b[m])[0,1]:.10f}")
for thr, lab in ((0.011065, "70%"), (0.037338, "60%"), (0.058696, "50%"), (0.079043, "40%")):
    agree = np.mean((a[m] >= thr) == (b[m] >= thr))
    print(f"  keep {lab}: the two versions agree on the TAKE/SKIP decision for "
          f"{100*agree:.2f}% of events")
