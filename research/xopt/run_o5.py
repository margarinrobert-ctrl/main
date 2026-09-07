"""O5 -- IS THE PUBLISHED VWAP-EMA GOLD SCRIPT OVERFITTED, AND HOW ROBUST IS IT?

Three questions get collapsed into one by the word "overfit", and this branch keeps them apart
(STUDY_VWAP_EMA_GOLD.md):

  * IS THE RULE FITTED?  A rolling walk-forward with NOTHING re-selected. If a three-year window
    predicts the next year, the constants generalise; if it does not, that is REGIME, not fitting.
  * IS THE SEARCH OVERFIT?  A walk-forward with the selection RE-RUN inside every training window,
    beside a random cell from the same pool.
  * WHAT IS P(OVERFIT)?  CSCV/PBO over all symmetric splits of a per-period return matrix.

The published cell is the unusual case where the first two do not apply the way they usually do:
its ten constants come from a PAPER, not from a search over this data, so it cannot have been
fitted to gold. That is testable rather than assertable -- its median in-sample rank inside its own
1,199-cell pool is the statistic, and a below-median rank is the signature of a configuration
chosen by convention.

What was NOT measured on this cell and is measured here:
  O5.1  EXECUTION perturbation -- cost and slippage drawn inside the walk, not scaled after it.
  O5.2  PRICE JITTER with EVERY INDICATOR RECOMPUTED from the jittered bars. This is the only
        perturbation that moves the SIGNAL SET; the others move the arithmetic on a fixed one.
  O5.3  JOINT +-20% parameter jitter on all ten free parameters at once (the existing read is
        one-at-a-time at +-10%, which cannot see an interaction).
  O5.4  a COST LADDER 0x..4x, because gold's round turn is 17% of a 0.5N stop and this rule is
        positive gross and negative net -- so the ladder is the whole story, not a stress test.

A perturbation prices execution and data noise ON THE TRADES YOU SELECTED. It can never price the
SELECTION (STUDY_ATME_LIVE). That is what O5.5's rank and PBO columns are for.
"""
import sys, os, time, json
sys.path.insert(0, "research"); sys.path.insert(0, "research/vwapema")
import numpy as np, pandas as pd
import vecore as V

R = "results/xopt/"
os.makedirs(R, exist_ok=True)
RNG = np.random.default_rng(20260907)
PUB = dict(V.PARAMS)
PUB["tgt_R"] = 3.0            # the target is a `run` argument in vecore, not a PARAMS key
TICK = 0.01                      # XAUUSD quote increment on this feed

print(__doc__)
print("published constants:", PUB)


def score(t, blk):
    m = t.blk == blk
    if m.sum() == 0:
        return dict(n=0, R=np.nan, pf=np.nan, totR=np.nan)
    s = V.stats(t[m])
    return dict(n=s["n"], R=s["R"], pf=s["pf"], totR=s["totR"])


t0 = time.time()
D = V.build(sess="ny")
sig, parts = V.triggers(D, side=1, p=PUB)
base = V.run(D, sig, side=1, tgt_R=PUB["tgt_R"], atr_stop=PUB["atr_stop"], p=PUB)
b_res, b_lck = score(base, 0), score(base, 1)
print(f"\nbaseline  research n {b_res['n']} R {b_res['R']:+.4f} PF {b_res['pf']:.3f}"
      f"  |  locked n {b_lck['n']} R {b_lck['R']:+.4f} PF {b_lck['pf']:.3f}   ({time.time()-t0:.0f}s)")

# ================================================================= O5.1 execution perturbation
print("\n" + "=" * 110)
print("O5.1  EXECUTION PERTURBATION -- cost and slippage drawn INSIDE the walk")
print("=" * 110)
rows = []
N_EXEC = 400
for i in range(N_EXEC):
    cr = V.COST_RT * RNG.uniform(0.5, 2.0)
    sl = V.SLIP * RNG.uniform(0.0, 2.0)
    t = V.run(D, sig, side=1, tgt_R=PUB["tgt_R"], atr_stop=PUB["atr_stop"], p=PUB,
              cost_rt=cr, slip=sl)
    rows.append(dict(draw=i, cost_rt=cr, slip=sl,
                     R_res=score(t, 0)["R"], R_lck=score(t, 1)["R"]))
EX = pd.DataFrame(rows)
EX.to_csv(R + "o5_exec.csv", index=False)
for c, lab in (("R_res", "research"), ("R_lck", "locked")):
    v = EX[c].to_numpy()
    print(f"  {lab:9s}  p5 {np.percentile(v,5):+.4f}  median {np.median(v):+.4f}  "
          f"p95 {np.percentile(v,95):+.4f}   P(R<=0) {float((v<=0).mean()):.3f}")

# ================================================================= O5.2 price jitter
print("\n" + "=" * 110)
print("O5.2  PRICE JITTER -- OHLC perturbed, bar repaired, EVERY INDICATOR RECOMPUTED")
print("=" * 110)
print("  The bar is repaired after jitter (high = max of the four, low = min) so the OHLC stays")
print("  self-consistent; ATR, all three EMAs, the session VWAP and the 20-bar volume mean are")
print("  then rebuilt from the jittered bars, so the SIGNAL SET moves and not just the fills.")
raw = V.load()
rows = []
N_JIT = 120
for ticks in (0.5, 1.0, 2.0):
    amp = ticks * TICK
    for i in range(N_JIT):
        f = raw.copy()
        for k in ("open", "high", "low", "close"):
            f[k] = f[k].to_numpy() + RNG.uniform(-amp, amp, len(f))
        oc = np.stack([f["open"].to_numpy(), f["close"].to_numpy()])
        f["high"] = np.maximum(f["high"].to_numpy(), oc.max(0))
        f["low"] = np.minimum(f["low"].to_numpy(), oc.min(0))
        Dj = V.assemble(f, sess="ny")
        sj, _ = V.triggers(Dj, side=1, p=PUB)
        tj = V.run(Dj, sj, side=1, tgt_R=PUB["tgt_R"], atr_stop=PUB["atr_stop"], p=PUB)
        a, b = score(tj, 0), score(tj, 1)
        rows.append(dict(ticks=ticks, draw=i, n_res=a["n"], R_res=a["R"], pf_res=a["pf"],
                         n_lck=b["n"], R_lck=b["R"], pf_lck=b["pf"]))
    d = pd.DataFrame(rows)
    d = d[d.ticks == ticks]
    print(f"  {ticks:>4.1f} tick   n {d.n_res.mean():6.1f}/{d.n_lck.mean():6.1f}   "
          f"research R p5 {np.percentile(d.R_res,5):+.4f} med {d.R_res.median():+.4f}   "
          f"locked R p5 {np.percentile(d.R_lck,5):+.4f} med {d.R_lck.median():+.4f}   "
          f"sign kept locked {float((d.R_lck>0).mean()):.3f}")
JI = pd.DataFrame(rows)
JI.to_csv(R + "o5_jitter.csv", index=False)

# ================================================================= O5.3 joint parameter jitter
print("\n" + "=" * 110)
print("O5.3  JOINT PARAMETER JITTER -- all ten free parameters at once, +-20%")
print("=" * 110)
INTS = ("ema_slow", "ema_pull", "ema_tight", "atr_len")
KEYS = ("ema_slow", "ema_pull", "ema_tight", "atr_len", "atr_stop", "tgt_R",
        "vol_mult", "range_mult", "wick_body", "ambig", "tighten_R")
rows = []
N_PAR = 300
for i in range(N_PAR):
    p = dict(PUB)
    for k in KEYS:
        f = RNG.uniform(0.8, 1.2)
        p[k] = max(2, int(round(PUB[k] * f))) if k in INTS else float(PUB[k] * f)
    try:
        s2, _ = V.triggers(D, side=1, p=p)
        t2 = V.run(D, s2, side=1, tgt_R=p["tgt_R"], atr_stop=p["atr_stop"], p=p)
        a, b = score(t2, 0), score(t2, 1)
    except Exception:
        continue
    rows.append(dict(draw=i, n_res=a["n"], R_res=a["R"], pf_res=a["pf"],
                     n_lck=b["n"], R_lck=b["R"], pf_lck=b["pf"]))
PJ = pd.DataFrame(rows).dropna(subset=["R_res", "R_lck"])
PJ.to_csv(R + "o5_paramjitter.csv", index=False)
print(f"  {len(PJ)} scorable of {N_PAR}   (NaN draws dropped and counted, never averaged over)")
for c, lab, b0 in (("R_res", "research", b_res["R"]), ("R_lck", "locked", b_lck["R"])):
    v = PJ[c].to_numpy()
    print(f"  {lab:9s}  p5 {np.percentile(v,5):+.4f}  median {np.median(v):+.4f}  "
          f"p95 {np.percentile(v,95):+.4f}   share > 0 {float((v>0).mean()):.3f}   "
          f"share BEATING the published cell {float((v>b0).mean()):.3f}")

# ================================================================= O5.4 cost ladder
print("\n" + "=" * 110)
print("O5.4  COST LADDER -- gold's round turn is 17% of a 0.5N stop, so this is the whole story")
print("=" * 110)
rows = []
for mult in (0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0):
    t = V.run(D, sig, side=1, tgt_R=PUB["tgt_R"], atr_stop=PUB["atr_stop"], p=PUB,
              cost_rt=V.COST_RT * mult, slip=V.SLIP * mult)
    a, b = score(t, 0), score(t, 1)
    rows.append(dict(mult=mult, R_res=a["R"], pf_res=a["pf"], R_lck=b["R"], pf_lck=b["pf"]))
    print(f"  {mult:4.2f}x   research R {a['R']:+.4f} PF {a['pf']:.3f}   "
          f"locked R {b['R']:+.4f} PF {b['pf']:.3f}")
CL = pd.DataFrame(rows)
CL.to_csv(R + "o5_costladder.csv", index=False)
bx = CL[CL.R_res > 0]
print(f"  research crosses zero below {bx.mult.max() if len(bx) else 0:.2f}x the assumed cost"
      if len(bx) else "  research is negative at EVERY cost rung including zero")

# ================================================================= O5.5 verdict
print("\n" + "=" * 110)
print("O5.5  THE VERDICT TABLE")
print("=" * 110)
pk = json.load(open("results/vwapema/pbo.json"))
pr = pd.read_csv("results/vwapema/preset_ranks.csv")
pub_rank = float(pr.loc[pr.preset == "As published", "IS_rank"].iloc[0])
wf = pd.read_csv("results/vwapema/wfo_published.csv")
mc = pd.read_csv("results/vwapema/opt_mc.csv")
mc = mc[mc.finalist == "as published"].iloc[0]
ver = dict(
    is_rank_in_own_pool=pub_rank,
    pbo=pk["PBO"], slope_oos_on_is=pk["slope"],
    wf_folds=int(len(wf)), wf_mean_is=float(wf.IS_R.mean()), wf_mean_oos=float(wf.OOS_R.mean()),
    wf_gap=float(wf.IS_R.mean() - wf.OOS_R.mean()),
    wf_corr_is_oos=float(wf.IS_R.corr(wf.OOS_R)),
    locked_boot_p=float(mc.p_mean_le_0), locked_dd_pctile=float(mc.dd_pctile),
    locked_dd_ratio=float(mc.mc_p99_dd / mc.real_dd),
    jitter1_sign_kept_locked=float((JI[JI.ticks == 1.0].R_lck > 0).mean()),
    param_share_pos_locked=float((PJ.R_lck > 0).mean()),
    param_share_beating=float((PJ.R_lck > b_lck["R"]).mean()),
    exec_P_R_le_0_locked=float((EX.R_lck <= 0).mean()),
    cost_positive_at_1x_research=bool(b_res["R"] > 0),
)
json.dump(ver, open(R + "o5_verdict.json", "w"), indent=2)
for k, v in ver.items():
    print(f"  {k:32s} {v}")
print(f"\ntotal {time.time()-t0:.0f}s")
