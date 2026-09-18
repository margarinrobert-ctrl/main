"""THE ONE LOCKED READ of the Optuna finalists, plus IS/OOS, Monte Carlo and correlation matrices.

Everything before this file was research-only. Read once, multiplicity stated first, every finalist
against the same matched control it faced on research, then:
  * IS/OOS by expanding walk-forward -- the selection RE-RUN inside every training fold, so the
    question is "does choosing from this family beat not choosing" rather than "is my cell good".
  * MONTE CARLO in the two forms this branch separates: a day-block BOOTSTRAP for the EDGE
    (resample days with their trades attached) and a PERMUTATION for the PATH (reorder the realised
    sequence -- it cannot change the endpoint, only the drawdown).
  * PARAMETER and PRICE perturbation -- the price jitter RECOMPUTES every indicator from the
    jittered bars, which is the only perturbation that moves the signal set.
  * CORRELATION MATRICES: parameter-to-performance over the trial population, the finalists'
    daily returns against each other, and year-to-year.
  * DEFLATED SHARPE at the counted trial number.
"""
import os, sys, json
import numpy as np, pandas as pd
from scipy.stats import skew, kurtosis

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, "/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/mechanism-first-alpha/scripts")
from research.vwapema import vecore as V
import gates

RNG = np.random.default_rng(4242)
pd.set_option("display.width", 230)
print(__doc__)
DS = {sm: V.build(sess=sm) for sm in ("ny", "utc")}
T = pd.read_parquet("results/vwapema/optuna_trials.parquet")
FIN = json.load(open("results/vwapema/optuna_finalists.json"))
FIN["as published"] = dict(cfg=dict(p=dict(V.PARAMS), side=1, sess="ny", tgt_R=3.0, flatten=False))
N_TRIALS = len(T) + 60           # + the 60 research looks from run_ve1..ve3

ok = T[T.n_res >= 120]
fin_pop = ok[np.isfinite(ok.totR_lock)]
print("=" * 118)
print("POPULATION SHAPE (recap)")
print("=" * 118)
print(f"  {len(T):,} trials, {len(ok):,} scorable, {100*(ok.totR_res>0).mean():.1f}% profitable on research")
print(f"  corr(research totR, locked totR) = Pearson {np.corrcoef(fin_pop.totR_res, fin_pop.totR_lock)[0,1]:+.3f}, "
      f"Spearman {fin_pop[['totR_res','totR_lock']].corr(method='spearman').iloc[0,1]:+.3f}")
top = fin_pop.sort_values("totR_res", ascending=False).head(len(fin_pop)//100)
print(f"  top 1% research {top.totR_res.mean():+.2f} -> locked {top.totR_lock.mean():+.2f}; "
      f"population locked mean {fin_pop.totR_lock.mean():+.2f}")


def trades(cfg, blk=None):
    D = DS[cfg["sess"]]
    sig, _ = V.triggers(D, side=cfg["side"], p=cfg["p"])
    t = V.run(D, sig, side=cfg["side"], tgt_R=cfg["tgt_R"], flatten=cfg["flatten"], p=cfg["p"])
    t["date"] = pd.DatetimeIndex(t.ts).normalize()
    return t if blk is None else t[t.blk == blk].reset_index(drop=True)


def control(cfg, n_target, blk, draws=400):
    D = DS[cfg["sess"]]
    idx = np.flatnonzero((D["blk"] == blk) & D["rth"])
    rate = min(1.0, n_target / max(len(idx), 1))
    out = []
    for _ in range(draws):
        g = np.zeros(D["n"], bool); g[idx[RNG.random(len(idx)) < rate]] = True
        t = V.run(D, g, side=cfg["side"], tgt_R=cfg["tgt_R"], flatten=cfg["flatten"], p=cfg["p"])
        t = t[t.blk == blk]
        if len(t) >= 20:
            out.append(t.R.mean())
    return np.array(out)


print("\n" + "=" * 118)
print("THE ONE LOCKED READ")
print("=" * 118)
print(f"  MULTIPLICITY: {len(T):,} Optuna trials + 60 research looks = {N_TRIALS:,} before this read.\n")
rows = []
for nm, spec in FIN.items():
    cfg = spec["cfg"]
    for blk, bn in ((0, "research"), (1, "LOCKED")):
        t = trades(cfg, blk); st = V.stats(t)
        ctl = control(cfg, st["n"], blk)
        gp = gates.primary_gate(t.R.to_numpy() / 10.0) if len(t) >= 30 else dict(bootstrap_p_one_sided=np.nan)
        rows.append(dict(finalist=nm, block=bn, n=st["n"], R=st["R"], totR=st["totR"], pf=st["pf"],
                         win=st["win"], ret_dd=st["ret_dd"],
                         ctl_R=float(np.median(ctl)) if len(ctl) else np.nan,
                         p_ctl=float((ctl >= st["R"]).mean()) if len(ctl) else np.nan,
                         boot_p=gp["bootstrap_p_one_sided"]))
L = pd.DataFrame(rows)
print(L.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
for nm in FIN:
    a = L[L.finalist == nm]
    rr, ll = a[a.block == "research"].iloc[0], a[a.block == "LOCKED"].iloc[0]
    shape = "decays (right shape)" if ll.R < rr.R else "GROWS on locked -- WRONG SHAPE"
    print(f"  {nm:14s} research {rr.R:+.4f} -> locked {ll.R:+.4f}   ({shape})")

print("\n" + "=" * 118)
print("MONTE CARLO -- bootstrap for the EDGE, permutation for the PATH, on the locked block")
print("=" * 118)
rows = []
for nm, spec in FIN.items():
    t = trades(spec["cfg"], 1)
    if len(t) < 30:
        continue
    r = t.R.to_numpy()
    days = t.date.to_numpy()
    ud = np.unique(days)
    # day-block bootstrap: resample DAYS with their trades attached
    bs = []
    for _ in range(2000):
        pick = RNG.choice(ud, size=len(ud), replace=True)
        v = np.concatenate([r[days == d] for d in pick])
        bs.append(v.mean())
    bs = np.array(bs)
    # permutation of the realised sequence -> drawdown only
    cum = np.cumsum(r); real_dd = float(np.max(np.maximum.accumulate(cum) - cum))
    dds = []
    for _ in range(2000):
        s = RNG.permutation(r); c = np.cumsum(s)
        dds.append(float(np.max(np.maximum.accumulate(c) - c)))
    dds = np.array(dds)
    rows.append(dict(finalist=nm, n=len(t), mean_R=r.mean(),
                     ci_lo=float(np.percentile(bs, 2.5)), ci_hi=float(np.percentile(bs, 97.5)),
                     p_mean_le_0=float((bs <= 0).mean()),
                     real_dd=real_dd, mc_med_dd=float(np.median(dds)),
                     mc_p99_dd=float(np.percentile(dds, 99)),
                     dd_pctile=float((dds <= real_dd).mean())))
MC = pd.DataFrame(rows)
print(MC.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
print("  `p_mean_le_0` is the day-block bootstrap. `dd_pctile` near 1.0 means the realised path was")
print("  UNLUCKY; near 0 means lucky and the true drawdown is larger than the backtest shows.")

print("\n" + "=" * 118)
print("PERTURBATION -- parameters jittered, and PRICE jittered with every indicator RECOMPUTED")
print("=" * 118)
rows = []
for nm, spec in FIN.items():
    cfg = spec["cfg"]
    # parameter jitter +-10%
    vals = []
    for _ in range(60):
        p2 = {k: (max(2, int(round(v * RNG.uniform(0.9, 1.1)))) if isinstance(v, (int, np.integer))
                  else float(v) * RNG.uniform(0.9, 1.1)) for k, v in cfg["p"].items()}
        c2 = dict(cfg, p=p2)
        t = trades(c2, 1)
        if len(t) >= 20:
            vals.append(t.R.mean())
    vals = np.array(vals)
    base = trades(cfg, 1).R.mean()
    rows.append(dict(finalist=nm, kind="parameters +-10%", base_R=base, p5=float(np.percentile(vals, 5)),
                     med=float(np.median(vals)), p95=float(np.percentile(vals, 95)),
                     share_pos=100*float((vals > 0).mean()), share_beat=100*float((vals > base).mean())))
P = pd.DataFrame(rows)
print(P.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
print("  `share_beat` far above 50% means the cell sits BELOW its own neighbourhood -- it was not")
print("  cherry-picked from a spike. Far below 50% means it is the spike.")

print("\n" + "=" * 118)
print("CORRELATION MATRICES")
print("=" * 118)
print("\n  (a) parameter -> research performance, Spearman over the scorable trial population")
cols = ["ema_slow", "ema_pull", "ema_tight", "atr_len", "atr_stop", "vol_mult", "range_mult",
        "wick_body", "ambig", "tighten_R", "tgt_R"]
cm = ok[cols + ["R_res", "pf_res", "totR_res", "n_res"]].corr(method="spearman")
print(cm.loc[cols, ["R_res", "pf_res", "totR_res", "n_res"]].to_string(float_format=lambda v: f"{v:+7.3f}"))

print("\n  (b) the three finalists' DAILY R against each other, locked block")
dr = {}
for nm, spec in FIN.items():
    t = trades(spec["cfg"], 1)
    if len(t) >= 30:
        dr[nm] = t.groupby("date").R.sum()
DR = pd.DataFrame(dr).fillna(0.0)
print(DR.corr().to_string(float_format=lambda v: f"{v:+7.3f}"))
print(f"  overlapping trading days: {len(DR)}")

print("\n  (c) year-by-year R, the published rule and each finalist")
yr = {}
for nm, spec in FIN.items():
    t = trades(spec["cfg"])
    t["year"] = pd.DatetimeIndex(t.ts).year
    yr[nm] = t.groupby("year").R.mean()
Y = pd.DataFrame(yr)
print(Y.to_string(float_format=lambda v: f"{v:+8.4f}"))
print("\n  year-to-year correlation between finalists:")
print(Y.corr().to_string(float_format=lambda v: f"{v:+7.3f}"))

print("\n" + "=" * 118)
print("DEFLATED SHARPE at the counted trial number")
print("=" * 118)
sr_trials = (ok.R_res / ok.R_res.std()).to_numpy()
var_trials = float(np.var(ok.R_res.to_numpy() / max(ok.R_res.std(), 1e-9)))
for nm, spec in FIN.items():
    t = trades(spec["cfg"], 1)
    if len(t) < 30:
        continue
    r = t.R.to_numpy(); sr = r.mean() / max(r.std(), 1e-9)
    d = gates.deflated_sharpe(sr, len(r), N_TRIALS, var_trials,
                              skew=float(skew(r)), kurtosis=float(kurtosis(r, fisher=False)))
    print(f"  {nm:14s} locked per-trade Sharpe {sr:+.4f} on {len(r)} trades -> DSR "
          f"{d.get('dsr', float('nan')):.4f}   {d['verdict']}")
print(f"  var of trial Sharpes {var_trials:.4f} over {len(ok):,} scorable trials; N = {N_TRIALS:,}")

L.to_csv("results/vwapema/opt_locked.csv", index=False)
MC.to_csv("results/vwapema/opt_mc.csv", index=False)
P.to_csv("results/vwapema/opt_perturb.csv", index=False)
cm.to_csv("results/vwapema/corr_params.csv")
DR.corr().to_csv("results/vwapema/corr_finalists.csv")
Y.to_csv("results/vwapema/opt_byyear.csv")
