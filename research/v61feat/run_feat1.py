"""GATE 1, then the feature screen: predictive power, redundancy, and stability.

ORDER OF OPERATIONS. Gate 1 first, on the raw primary alone, because a feature layer cannot rescue
a primary with no edge and the two-gate structure exists to make that impossible to smuggle in.
Only then are features built, and they are scored in this order:

  1  BASE RATES on the trigger's own bars. Four indicator families have died on this branch by being
     the breakout restated (RSI 94.7%, Aroon 100.0%, MACD 99.8%, MFI 91.7%). Two lines, no P&L.
  2  PREDICTIVE POWER as Spearman IC against the event's own return, each beside a SHUFFLED TWIN.
     If the twin scores what the feature scores, the column is noise.
  3  REDUNDANCY measured ON THE SIGNAL BARS, not on all bars -- a feature only ever acts where the
     base fires (STUDY_V40, which found two EXACT duplicates in this branch's pool that way).
  4  STABILITY across regimes and across years: a feature whose sign flips between halves of the
     research block is not a feature.
Selection is FAMILY-FIRST and then by |rho|, because five picks that all pass a correlation ceiling
were once all volatility level.
"""
from __future__ import annotations

import os
import sys
import time
import warnings

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "research/v61sess"))
sys.path.append("/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/mechanism-first-alpha/scripts")
import v61feat as V       # noqa: E402
import sess_core as S     # noqa: E402
from gates import primary_gate   # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)
OUT = os.path.join(ROOT, "results/v61feat")
os.makedirs(OUT, exist_ok=True)


def line(t):
    print("\n" + "=" * 126)
    print(t)
    print("=" * 126, flush=True)


print(__doc__)
t0 = time.time()
rng = np.random.default_rng(1515)
D = S.build(15)
g, k, w = S.gate(D, 90, 600)
CFG = dict(ent=20, exN=20, stop=2.0, tp=0.0, hold=480, piv_min=90, win_min=600, touch=True)
print(f"  NQ 15m, {D['n']:,} bars. Gate k={k} w={w} bars (90 / 600 minutes), passes {100*g.mean():.1f}%")
print(f"  research/locked split at day {D['cut_day']}")

line("GATE 1 -- the PRIMARY alone, before a single feature is written")
print("  Two 15-minute candidates. Whichever clears is the one a meta layer may be built on.\n")
print(f"  {'primary':34s} {'block':9s} {'n':>4} {'net %/event':>12} {'95% CI':>24} {'p':>7} "
      f"{'PF':>6}  verdict")
CANDS = {"15m all hours (as shipped)": dict(sess=False),
         "15m 07:00-11:00 + flatten": dict(sess=True, s_start=7 * 60, s_stop=11 * 60, flat=True)}
G1 = {}
for nm, kw in CANDS.items():
    t = S.run(D, **CFG, **kw, g=g)
    for b, bn in ((0, "research"), (1, "locked")):
        z = t[t.blk == b]
        if len(z) < 25:
            continue
        r = primary_gate(z.pct.to_numpy() / 100.0)
        lo, hi = r["net_mean_ci95"]
        p = z.pts.to_numpy()
        pf = p[p > 0].sum() / max(-p[p < 0].sum(), 1e-9)
        G1[(nm, bn)] = r
        print(f"  {nm if b==0 else '':34s} {bn:9s} {len(z):>4} {100*r['net_mean_per_event']:>12.5f} "
              f"[{100*lo:>+9.5f},{100*hi:>+9.5f}] {r['bootstrap_p_one_sided']:>7.3f} {pf:>6.3f}  "
              f"{r['verdict'].split('--')[0].strip()}")
print("\n  The all-hours primary clears on both blocks; the session+flatten one does not clear")
print("  research. The meta layer is therefore built on the ALL-HOURS primary -- building it on a")
print("  primary that fails Gate 1 is exactly the move the architecture exists to prevent.")

PRIM = dict(CFG, sess=False)
E = S.run(D, **PRIM, g=g)
print(f"\n  primary events: {len(E)}  ({int((E.blk==0).sum())} research / {int((E.blk==1).sum())} locked)")

line("FEATURES -- built once, frozen on the RESEARCH block")
mR = D["blk"] == 0
X, meta = V.build_features(D, mask_research=mR, want_smoothed=True)
print(f"  {X.shape[1]} features in {len(set(c.split('.')[0] for c in X.columns))} declared families")
print(f"  fracdiff order d = {meta['d']} (chosen by ADF on RESEARCH only), fixed window "
      f"{meta['ffd_window']} bars")
hp = meta["hmm"]
print(f"  HMM fitted on RESEARCH only; states by drift:")
for kk, s in zip(hp["order"], ("bear", "side", "bull")):
    print(f"    {s:5s} mean 15m log-return x100 {hp['mu'][kk,0]:+8.5f}   rv {hp['mu'][kk,1]:7.4f}   "
          f"self-transition {hp['A'][kk,kk]:.4f}")
FROZEN = dict(d=meta["d"], d_table=meta["d_table"], hmm=hp)

line("LEAKAGE")
bad, checked, npb = V.truncation_audit(D, X, FROZEN, probes=20, seed=7)
print(f"  truncation audit: {len(bad)} mismatches over {checked:,} comparisons on {npb} probe bars")
for b in bad[:6]:
    print(f"    bar {b[0]}  {b[1]}  full {b[2]:.6f}  truncated {b[3]:.6f}")
sm = meta["smoothed"]
fl = np.column_stack([X["regime.hmm_bear"], X["regime.hmm_side"], X["regime.hmm_bull"]])
print(f"  filtered vs SMOOTHED HMM state agreement {100*np.mean(np.argmax(fl,1)==np.argmax(sm,1)):.1f}% "
      f"-- close enough to be easy to miss, which is why STUDY_V27 measured what it costs")

sig = E.sig.to_numpy()
FE = X.iloc[sig].reset_index(drop=True)
FE["pct"] = E.pct.to_numpy(); FE["blk"] = E.blk.to_numpy(); FE["day"] = E.day.to_numpy()
COLS = list(X.columns)
FE = FE[FE[COLS].notna().all(axis=1)].reset_index(drop=True)
R = FE[FE.blk == 0].reset_index(drop=True)
print(f"  events with a complete feature row: {len(FE)} ({len(R)} research)")

line("1  BASE RATES on the trigger's own bars -- does the feature bind at all?")
br = []
for cnm in COLS:
    x = X[cnm].to_numpy(float)
    med = float(np.nanmedian(x[mR & np.isfinite(x)]))
    ps = float(np.nanmean(x[sig] >= med))
    pa = float(np.nanmean(x >= med))
    br.append(dict(feature=cnm, pass_sig=ps, pass_all=pa, lift=ps / max(pa, 1e-9)))
BR = pd.DataFrame(br).sort_values("pass_sig", ascending=False)
BR.to_csv(os.path.join(OUT, "base_rates.csv"), index=False)
print(f"  {'feature':26s} {'on signals':>11} {'on all bars':>12} {'lift':>6}")
for _, r in pd.concat([BR.head(5), BR.tail(4)]).iterrows():
    print(f"  {r.feature:26s} {100*r.pass_sig:>10.1f}% {100*r.pass_all:>11.1f}% {r.lift:>6.2f}")
print(f"\n  features passing >95% of signal bars (the breakout restated): "
      f"{int((BR.pass_sig>0.95).sum())} of {len(BR)}")
print(f"  features with lift within 3% of 1.00 (inert here): {int((BR.lift.sub(1).abs()<0.03).sum())}")

line("2  PREDICTIVE POWER -- Spearman IC on RESEARCH events, each beside a SHUFFLED TWIN")
y = R.pct.to_numpy()
ic = []
for cnm in COLS:
    x = R[cnm].to_numpy(float)
    real = float(pd.Series(x).corr(pd.Series(y), method="spearman"))
    tw = [float(pd.Series(x).corr(pd.Series(rng.permutation(y)), method="spearman")) for _ in range(50)]
    tw = np.array(tw)
    p = float(np.mean(np.abs(tw) >= abs(real)))
    ic.append(dict(feature=cnm, family=cnm.split(".")[0], ic=real, twin_p95=float(np.quantile(np.abs(tw), .95)),
                   p=p))
IC = pd.DataFrame(ic).sort_values("p")
IC.to_csv(os.path.join(OUT, "ic.csv"), index=False)
print(f"  n = {len(R)} research events.  cells at p<=0.05: {int((IC.p<=0.05).sum())} "
      f"(expected by chance {0.05*len(IC):.1f})")
print(f"\n  {'feature':26s} {'family':8s} {'IC':>8} {'twin |IC| p95':>14} {'p':>7}")
for _, r in IC.head(12).iterrows():
    print(f"  {r.feature:26s} {r.family:8s} {r.ic:>+8.4f} {r.twin_p95:>14.4f} {r.p:>7.3f}")
print("\n  by family (mean |IC| against the twin's 95th percentile):")
fam = IC.assign(a=IC.ic.abs()).groupby("family").agg(n=("ic", "size"), mean_absIC=("a", "mean"),
                                                     twin=("twin_p95", "mean"),
                                                     hits=("p", lambda z: int((z <= 0.05).sum())))
print("   " + fam.to_string(float_format=lambda v: f"{v:8.4f}").replace("\n", "\n   "))

line("3  REDUNDANCY -- correlation measured ON THE SIGNAL BARS, family-first selection")
C = R[COLS].corr(method="spearman").abs()
pairs = [(a, b, C.loc[a, b]) for i, a in enumerate(COLS) for b in COLS[i + 1:]]
pairs.sort(key=lambda z: -z[2])
print(f"  the 8 most redundant pairs of {len(pairs)}:")
for a, b, r in pairs[:8]:
    tag = "  <- EXACT DUPLICATE" if r > 0.995 else ""
    print(f"    {a:26s} {b:26s} |rho| {r:.4f}{tag}")
dups = [(a, b, r) for a, b, r in pairs if r > 0.995]
print(f"\n  exact duplicates (|rho| > 0.995): {len(dups)}")

RHO_MAX = 0.65
IC2 = IC.assign(a=IC.ic.abs()).sort_values("a", ascending=False)
picks, used_fam = [], set()
for _, r in IC2.iterrows():
    if r.family in used_fam:
        continue
    if any(C.loc[r.feature, p] > RHO_MAX for p in picks):
        continue
    picks.append(r.feature); used_fam.add(r.family)
for _, r in IC2.iterrows():          # second pass: fill out, still respecting the rho ceiling
    if len(picks) >= 10 or r.feature in picks:
        continue
    if any(C.loc[r.feature, p] > RHO_MAX for p in picks):
        continue
    picks.append(r.feature)
print(f"\n  FAMILY-FIRST selection at |rho| <= {RHO_MAX}: {len(picks)} features")
for p in picks:
    r = IC[IC.feature == p].iloc[0]
    print(f"    {p:26s} IC {r.ic:>+7.4f}  p {r.p:.3f}")
mx = max((C.loc[a, b] for i, a in enumerate(picks) for b in picks[i + 1:]), default=0.0)
print(f"  worst pairwise |rho| among the picks: {mx:.3f}")

line("4  STABILITY -- does the sign hold across halves of RESEARCH, and across volatility regimes?")
half = R.index < len(R) // 2
volq = pd.qcut(R["vol.atr_rank250"].rank(method="first"), 3, labels=["calm", "mid", "fast"])
st = []
for cnm in COLS:
    x = R[cnm].to_numpy(float)
    i1 = float(pd.Series(x[half]).corr(pd.Series(y[half]), method="spearman"))
    i2 = float(pd.Series(x[~half]).corr(pd.Series(y[~half]), method="spearman"))
    regs = []
    for lab in ("calm", "mid", "fast"):
        m = (volq == lab).to_numpy()
        regs.append(float(pd.Series(x[m]).corr(pd.Series(y[m]), method="spearman")))
    same_half = np.sign(i1) == np.sign(i2)
    same_reg = len(set(np.sign(np.array(regs)))) == 1
    st.append(dict(feature=cnm, ic_h1=i1, ic_h2=i2, half_sign=bool(same_half),
                   ic_calm=regs[0], ic_mid=regs[1], ic_fast=regs[2], regime_sign=bool(same_reg),
                   stable=bool(same_half and same_reg)))
ST = pd.DataFrame(st)
ST.to_csv(os.path.join(OUT, "stability.csv"), index=False)
print(f"  sign holds across both halves of research: {int(ST.half_sign.sum())} of {len(ST)}")
print(f"  sign holds across all three volatility regimes: {int(ST.regime_sign.sum())} of {len(ST)}")
print(f"  BOTH: {int(ST.stable.sum())} of {len(ST)}   (chance for a null feature is about 0.5 x 0.25 = 12.5%)")
print(f"\n  of the {len(picks)} selected features, {int(ST[ST.feature.isin(picks)].stable.sum())} are stable:")
for p in picks:
    r = ST[ST.feature == p].iloc[0]
    print(f"    {p:26s} halves {r.ic_h1:>+7.4f} / {r.ic_h2:>+7.4f}   "
          f"regimes {r.ic_calm:>+6.3f} {r.ic_mid:>+6.3f} {r.ic_fast:>+6.3f}   "
          f"{'STABLE' if r.stable else 'unstable'}")

KEEP = [p for p in picks if bool(ST[ST.feature == p].stable.iloc[0])]
print(f"\n  KEPT after the stability filter: {len(KEEP)} of {len(picks)}")
pd.Series(KEEP).to_csv(os.path.join(OUT, "kept.csv"), index=False, header=["feature"])
FE.to_parquet(os.path.join(OUT, "events_features.parquet"))
import pickle
with open(os.path.join(OUT, "frozen.pkl"), "wb") as f:
    pickle.dump(dict(d=FROZEN["d"], hmm=FROZEN["hmm"], cols=COLS, picks=picks, keep=KEEP), f)
print(f"\n  runtime {time.time()-t0:.0f}s")
