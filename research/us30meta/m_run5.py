"""M5 -- GATE 2, AS A RE-SIMULATED VETO, AND THE ONE READ OF EACH RESERVED BLOCK.

DECLARED BEFORE ANYTHING IS LOOKED AT (this docstring is the pre-registration):

  ARMS. Two, and both are reported. `+ema34>89` is the arm the VERDICT is written about, on the
  coordinator's measurement in `research/us30rate/`: over six declared channel rungs x three blocks
  `+adx<=20` beats its own same-selectivity veto in 15 of 18 cells but only 3 of 6 on the RESERVED
  forward feed (median p 0.617), while the EMA condition is 18 of 18 including 6/6 forward, and the
  stack decomposes so that `ema34>ema89` alone carries it. `+adx<=20` is reported beside it because
  section 12 named it, and because a meta layer on an arm that fails the reserved block inherits
  that failure.

  SCORE. The M4-selected feature set, model as M4 chose it, fitted ONCE on the research block of
  the UNLOCKED `base` stream and never refitted.

  GATE. A VETO on the signal bar, re-simulated end to end. Not a subset of realised trades:
  `STUDY_AUCTION` -- refusing a signal frees the position lock and admits a LATER breakout the
  ungated run never saw, and `STUDY_XAU_CVD_FEATURES` measured that the two framings disagree.

  RUNGS. keep = 0.70 / 0.60 / 0.50 / 0.40 / 0.30, thresholds taken from the RESEARCH signal-bar
  score distribution and FROZEN.

  NULL. A random gate of the SAME SELECTIVITY, drawn over the arm's own signal bars and
  re-simulated with the position lock re-applied exactly as in the rule, 400 draws.

  THE ONE READ. The rung with the best RESEARCH random-gate p, applied to both arms, read ONCE on
  B_holdout and ONCE on C_forward (`US30_ISO_15m`, a different provider). Four cells. The KEPT
  FRACTION is reported against the fraction it was set to: a score that is not calibrated across
  the split makes any research threshold meaningless (`STUDY_AUTOBNN` kept 105 of 105).

  MDE. `2.802 * sd / sqrt(n)` is printed beside every number, and the KEPT-vs-REJECTED two-sample
  MDE beside every uplift. A gate that raises profit factor by removing trades raises the MDE at
  the same time and both are reported. `STUDY_US30_SCALP_0711` sections 9 and 13: PF 1.2 requires
  +10.61 points a trade on this primary and all thirty cells of the section-13 battery are inside
  their own MDE.
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
sys.path.append("/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/mechanism-first-alpha/scripts")
import m_core as C     # noqa: E402
import m_feat as MF    # noqa: E402
import m_ml as ML      # noqa: E402
from gates import deflated_sharpe, reality_check, expected_max_sharpe  # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 230)
print(__doc__)
t0 = time.time()
RUNGS = (0.70, 0.60, 0.50, 0.40, 0.30)
ARMS = ("+ema34>89", "+adx<=20")

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
print(f"  feature set from M4: {len(SET)} columns, families {S4['chosen_families']}, model {KIND}")

# ------------------------------------------------------------------ the new arm's Gate 1
C.line("M5.0  GATE 1 for the added arm `+ema34>89` -- recorded before it is used")
g1 = []
for arm in ("base",) + ARMS + ("+ema align",):
    t = C.locked(f, arm, M=M, blk=MR)
    p = t["pts"].to_numpy()
    ctl = C.matched_entry_control(f, arm, len(t), M=M, blk=MR, n_draw=400, seed=11)
    cp = float(np.mean(ctl >= p.mean()))
    _, bp = C.day_bootstrap(p, t.ts.dt.normalize().to_numpy(), n=2000, seed=3)
    g1.append(dict(arm=arm, n=len(p), pts=p.mean(), pf=C.pf(p), mde=C.mde(p.std(ddof=1), len(p)),
                   ctl_p=cp, boot_p=bp))
print(pd.DataFrame(g1).to_string(index=False, float_format=lambda v: f"{v:+.4f}"))

# ------------------------------------------------------------------ the score
C.line("M5.1  THE SCORE -- fitted ONCE on the research block, never refitted")
mdl = [ML.fit_full(R, SET, KIND, seed=s) for s in range(5)]
Xall = X[SET].to_numpy(float)


def score_bars(Xa):
    return np.mean([m["predict"](Xa) for m in mdl], axis=0)


sc_L = score_bars(Xall)
sig_all, _ = C.arm_signals(f, "base", M=M)
res_sig = sig_all[MR[sig_all]]
thr = {q: float(np.nanquantile(sc_L[res_sig], 1 - q)) for q in RUNGS}
print("  thresholds frozen on the research signal-bar score distribution:")
print("   " + "  ".join(f"keep {q:.2f} -> {v:+.4f}" for q, v in thr.items()))

# forward feed, same frozen d / HMM parameters
fi = C.S.load("US30I")
bli = C.S.blocks(fi, "US30I")
Mi = C.masks(fi)
Xi, _ = MF.build(fi, frozen=Z)
sc_I = score_bars(Xi[SET].to_numpy(float))
print(f"  forward feed US30_ISO_15m rebuilt with the FROZEN d={Z['d']} and HMM parameters: "
      f"{len(fi)} bars, {int(bli['C_forward'].sum())} in the reserved span")

BLOCKS = [("A_research", f, MR, M, sc_L), ("B_holdout", f, MH, M, sc_L),
          ("C_forward", fi, bli["C_forward"], Mi, sc_I)]


def cell(feed, blk, Mx, gate, arm):
    t = C.locked(feed, arm, M=Mx, gate=gate, blk=blk)
    if not len(t):
        return None
    p = t["pts"].to_numpy()
    return dict(n=len(p), pts=float(p.mean()), pf=C.pf(p), total=float(p.sum()),
                sd=float(p.std(ddof=1)), mde=C.mde(p.std(ddof=1), len(p)),
                win=float((p > 0).mean()), tgt=float((t.why == 1).mean()), t=t)


# ------------------------------------------------------------------ Gate 2 on research
C.line("M5.2  GATE 2 -- research block, VETO re-simulated, against a same-selectivity RANDOM GATE")
print("  `uplift` is per-trade points over the SAME ARM ungated. `MDE` is the kept set's own\n"
      "  detectability; `MDE split` is the two-sample resolution of KEPT vs REJECTED, which is the\n"
      "  honest question for a gate. `rand p` is 400 re-simulated random gates of the same size.\n")
res_rows = []
day_pnl = {}
sess = pd.Series(f.index[MR]).dt.normalize().unique()
for arm in ARMS:
    b = cell(f, MR, M, None, arm)
    sig_arm_R, _ = C.arm_signals(f, arm, M=M)
    sig_arm_R = sig_arm_R[MR[sig_arm_R]]
    print(f"\n  ARM {arm}  ungated: n {b['n']}  {b['pts']:+.3f} pts  PF {b['pf']:.3f}  "
          f"total {b['total']:+.0f}  MDE {b['mde']:.2f}")
    print(f"{'keep':>6} {'n':>5} {'pts/tr':>8} {'uplift':>8} {'MDE':>7} {'MDEsplit':>9} "
          f"{'inside':>7} {'PF':>7} {'total':>8} {'rand p':>7} {'boot p':>7} {'tgt hit':>8}")
    print(f"{'off':>6} {b['n']:>5} {b['pts']:>+8.3f} {'':>8} {b['mde']:>7.2f} {'':>9} {'':>7} "
          f"{b['pf']:>7.3f} {b['total']:>+8.0f} {'':>7} {'':>7} {b['tgt']:>8.3f}")
    day_pnl[(arm, "off")] = C.L.daily(b["t"], pd.DatetimeIndex(sess)).to_numpy()
    for q in RUNGS:
        g = sc_L >= thr[q]
        c_ = cell(f, MR, M, g, arm)
        if c_ is None:
            continue
        rej = b["t"][~g[b["t"].e_bar.to_numpy() - 1]]["pts"].to_numpy()
        ms = C.mde_split(c_["t"]["pts"].to_numpy(), rej) if len(rej) > 2 else np.nan
        sb = sig_arm_R[g[sig_arm_R]]
        nkeep_sig = len(sb)
        rc, rn = C.random_gate_control(f, arm, nkeep_sig, M=M, blk=MR, n_draw=400, seed=int(q*100))
        rp = float(np.mean(rc >= c_["pts"])) if rc is not None else np.nan
        _, bp = C.day_bootstrap(c_["t"]["pts"].to_numpy(),
                                c_["t"].ts.dt.normalize().to_numpy(), n=1000, seed=5, base=b["pts"])
        up = c_["pts"] - b["pts"]
        res_rows.append(dict(arm=arm, keep=q, **{k: v for k, v in c_.items() if k != "t"},
                             uplift=up, mde_split=ms, rand_p=rp, boot_p=bp,
                             n_sig_keep=nkeep_sig, ctl_n=float(np.mean(rn)) if rn is not None else np.nan))
        print(f"{q:>6.2f} {c_['n']:>5} {c_['pts']:>+8.3f} {up:>+8.3f} {c_['mde']:>7.2f} "
              f"{ms:>9.2f} {'YES' if abs(up) < (ms if np.isfinite(ms) else 1e9) else 'no':>7} "
              f"{c_['pf']:>7.3f} {c_['total']:>+8.0f} {rp:>7.3f} {bp:>7.3f} {c_['tgt']:>8.3f}"
              f"  [ctl n {np.mean(rn):.0f}]",
              flush=True)
        day_pnl[(arm, q)] = C.L.daily(c_["t"], pd.DatetimeIndex(sess)).to_numpy()
G2 = pd.DataFrame(res_rows)
G2.to_csv(os.path.join(C.OUT, "m5_gate2_research.csv"), index=False)
ok = G2[(G2.rand_p <= 0.05) & (G2.boot_p <= 0.05)]
print(f"\n  cells clearing BOTH nulls at p<=0.05: {len(ok)} of {len(G2)}   "
      f"best rand p {G2.rand_p.min():.3f}   best boot p {G2.boot_p.min():.3f}")
print(f"  cells whose uplift EXCEEDS its kept-vs-rejected MDE: "
      f"{int((G2.uplift.abs() > G2.mde_split).sum())} of {len(G2)}")
print(f"  TOTAL RETURN: the gate raises PF in {int((G2.pf > G2.arm.map(dict((a, cell(f,MR,M,None,a)['pf']) for a in ARMS))).sum())} "
      f"of {len(G2)} cells and total points in "
      f"{int((G2.total > G2.arm.map(dict((a, cell(f,MR,M,None,a)['total']) for a in ARMS))).sum())}.")

# ------------------------------------------------------------------ the one read
BEST = float(G2.sort_values("rand_p").iloc[0].keep)
C.line(f"M5.3  THE ONE READ -- rung keep={BEST:.2f} (best research rand p), both arms, B and C")
print(f"{'block':11s} {'arm':11s} {'n off':>6} {'off pts':>8} {'off PF':>7} | {'n on':>5} "
      f"{'kept':>6} {'on pts':>8} {'uplift':>8} {'MDE':>7} {'MDEsplit':>9} {'on PF':>7} "
      f"{'tot off':>8} {'tot on':>8} {'rand p':>7}")
one = []
for bn, feed, blk, Mx, scx in BLOCKS:
    g = scx >= thr[BEST]
    for arm in ARMS:
        b = cell(feed, blk, Mx, None, arm)
        c_ = cell(feed, blk, Mx, g, arm)
        if b is None or c_ is None:
            continue
        sig_b, _ = C.arm_signals(feed, arm, M=Mx)
        sig_b = sig_b[blk[sig_b]]
        kept = float(np.mean(scx[sig_b] >= thr[BEST]))
        rej = b["t"][~g[b["t"].e_bar.to_numpy() - 1]]["pts"].to_numpy()
        ms = C.mde_split(c_["t"]["pts"].to_numpy(), rej) if len(rej) > 2 else np.nan
        rc, _ = C.random_gate_control(feed, arm, int((scx[sig_b] >= thr[BEST]).sum()),
                                      M=Mx, blk=blk, n_draw=400, seed=9)
        rp = float(np.mean(rc >= c_["pts"])) if rc is not None else np.nan
        one.append(dict(block=bn, arm=arm, n_off=b["n"], off=b["pts"], off_pf=b["pf"],
                        n_on=c_["n"], kept=kept, on=c_["pts"], uplift=c_["pts"] - b["pts"],
                        mde=c_["mde"], mde_split=ms, on_pf=c_["pf"], tot_off=b["total"],
                        tot_on=c_["total"], rand_p=rp))
        print(f"{bn:11s} {arm:11s} {b['n']:>6} {b['pts']:>+8.3f} {b['pf']:>7.3f} | {c_['n']:>5} "
              f"{kept:>6.3f} {c_['pts']:>+8.3f} {c_['pts']-b['pts']:>+8.3f} {c_['mde']:>7.2f} "
              f"{ms:>9.2f} {c_['pf']:>7.3f} {b['total']:>+8.0f} {c_['total']:>+8.0f} {rp:>7.3f}",
              flush=True)
ONE = pd.DataFrame(one)
ONE.to_csv(os.path.join(C.OUT, "m5_one_read.csv"), index=False)
print(f"\n  KEPT-FRACTION CALIBRATION (target {BEST:.2f}): "
      + "  ".join(f"{r.block[:1]}/{r.arm} {r.kept:.3f}" for _, r in ONE.iterrows()))
print(f"  largest deviation from target: {float((ONE.kept - BEST).abs().max()):.3f}")
print(f"  cells with a POSITIVE uplift out of sample: "
      f"{int((ONE[ONE.block!='A_research'].uplift > 0).sum())} of {len(ONE[ONE.block!='A_research'])}")
print(f"  cells whose uplift exceeds its own MDE_split: "
      f"{int((ONE.uplift.abs() > ONE.mde_split).sum())} of {len(ONE)}")

# ------------------------------------------------------------------ deflation
C.line("M5.4  DEFLATION -- the trial count, the noise floor, and White's reality check")
TRIALS = dict(
    gate1_arms=6, ffd_d_ladder=11, hmm_K=1, leak_cells=6, hmm_ic_screen=19,
    ladder_models=8, ablation_dropone=7, ablation_solo=7, greedy_steps=28,
    single_feature=1, gate2_research=len(G2))
NT = sum(TRIALS.values())
print("  counted looks, every one of them:")
for k, v in TRIALS.items():
    print(f"    {k:22s} {v:>4}")
print(f"    {'TOTAL':22s} {NT:>4}")
srs = (G2.pts / G2.sd).to_numpy()
srs = srs[np.isfinite(srs)]
best_sr = float(srs.max())
vt = float(np.var(srs, ddof=1))
e0 = expected_max_sharpe(vt, NT)
print(f"\n  per-EVENT Sharpe of the Gate-2 research cells: mean {srs.mean():+.5f}  "
      f"var {vt:.6f}  best {best_sr:+.5f}")
print(f"  E[max Sharpe | pure noise] at N={NT}: {e0:+.5f}")
print(f"  best achieved / noise floor: {best_sr/e0:.3f}   "
      f"{'ABOVE' if best_sr > e0 else 'BELOW ITS OWN NOISE FLOOR'}")
bt = G2.sort_values("pts").iloc[-1]
row = G2.loc[G2.pts.idxmax()]
p = np.asarray(day_pnl[(row.arm, row.keep)], float)
d = deflated_sharpe(best_sr, int(row.n), NT, vt,
                    skew=float(pd.Series(srs).skew()), kurtosis=3.0)
print(f"\n  Deflated Sharpe of the best research cell ({row.arm} keep {row.keep:.2f}): "
      f"{d['dsr']:.4f}  -> {d['verdict']}")
Rm = np.column_stack([day_pnl[k] for k in day_pnl if k[1] != "off"])
rc = reality_check(Rm, block_mean=5, n_boot=2000, seed=4)
print(f"\n  White's reality check over the {Rm.shape[1]} Gate-2 candidate daily streams "
      f"({Rm.shape[0]} sessions): p {rc['reality_check_p']:.4f}")
print(f"    {rc['verdict']}")
with open(os.path.join(C.OUT, "m5_summary.pkl"), "wb") as fh:
    pickle.dump(dict(g2=G2, one=ONE, trials=TRIALS, n_trials=NT, dsr=d, rc=rc,
                     best_rung=BEST, thr=thr), fh)
print(f"\n[m_run5 done in {time.time()-t0:.0f}s]")
