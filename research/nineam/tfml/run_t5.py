"""T5  ONE READ of the holdout half (the second 46 tradeable sessions) for the single cell T4
pre-declared, then the DEFLATION over every look this study took, and the PF-1.5 arithmetic.

The model is refitted on ALL research events (pooled, same weights, same hyper-parameters), the
threshold is the research OOF cut T4 used, and the kept FRACTION on the holdout is reported against
its target -- the calibration check (`STUDY_AUTOBNN` kept 105 of 105).
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tfcore as C  # noqa: E402
import tfmodels as M  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import norm, skew, kurtosis  # noqa: E402

pd.set_option("display.width", 220)
P = C.P
F = pd.read_pickle(os.path.join(HERE, "feats_all.pkl"))
KEEP = pd.read_csv(os.path.join(HERE, "t2_keep.csv")).iloc[:, 0].tolist()
BEST = pd.read_csv(os.path.join(HERE, "t3_best.csv"), index_col=0).iloc[0, 0]
ch = pd.read_csv(os.path.join(HERE, "t4_chosen.csv"), index_col=0).iloc[:, 0]
G2 = pd.read_csv(os.path.join(HERE, "t4_gate2_scored.csv"))
sp = np.load(os.path.join(HERE, "split_days.npy"))
k_is = int(sp[0]); DAYS = sp[1:]; IS_D = DAYS[:k_is]; OOS_D = DAYS[k_is:]
TF = float(ch["tf"]); K = float(ch["keep"])
cell = G2[(G2.tf == TF) & (G2.keep == K)].iloc[0]


def hd(t):
    print("\n" + "=" * 100); print(t); print("=" * 100, flush=True)


def walk(c, sig, sd):
    o = np.argsort(sig, kind="stable")
    return c._walk_sig(P, c.atr_frame(P["atr_n"]), np.asarray(sig)[o], np.asarray(sd)[o])


hd(f"5  ONE HOLDOUT READ: tf {TF}, keep {K}, model {BEST}, threshold {cell.thr:+.5f} (research OOF cut)")
R = F[F["day"].isin(IS_D)].sort_values(["day", "t_sig", "tf"]).reset_index(drop=True)
H = F[F["day"].isin(OOS_D)].sort_values(["day", "t_sig", "tf"]).reset_index(drop=True)
seeds = (0,) if BEST == "ridge" else (0, 1, 2, 3, 4)
Xr = R[KEEP].to_numpy(float); w = M.weights(R)
hg = H[(H.tf == TF) & (H.gated == 1)].sort_values("sig")
sc = np.mean([M.fit_predict(BEST, Xr, R["pct"].to_numpy(), w, hg[KEEP].to_numpy(float), s)[0]
              for s in seeds], axis=0)
c = C.ctx(TF)
sig = hg["sig"].to_numpy(); sd = hg["side"].to_numpy()
keep = sc >= cell.thr
base = walk(c, sig, sd); kt = walk(c, sig[keep], sd[keep]) if keep.any() else None
rb = base["pct"].to_numpy()
print(f"  holdout gated signals {len(sig)}; kept {int(keep.sum())} = {keep.mean():.3f} against a "
      f"target of {K}  (research kept {cell.kept_n}/{cell.base_n})")
print(f"  holdout score IC on these events (unlocked label): {M.ic(sc, hg['pct'].to_numpy()):+.4f}")
out = dict(tf=TF, keep=K, n_sig=len(sig), kept_frac=float(keep.mean()), base_n=len(rb),
           base_pct=rb.mean(), base_pf=C.pf(rb), base_hit=float((base['why'] == 2).mean()))
if kt is not None and len(kt) > 1:
    rk = kt["pct"].to_numpy()
    up = rk.mean() - rb.mean()
    g = np.random.default_rng(55)
    nul = []
    for q in range(400):
        m = np.zeros(len(sig), bool); m[g.choice(len(sig), int(keep.sum()), replace=False)] = True
        tt = walk(c, sig[m], sd[m])
        if tt is not None and len(tt):
            nul.append(tt["pct"].mean() - rb.mean())
    nul = np.asarray(nul)
    bo = C.day_boot_uplift(base, kt, 2000, 9)
    out.update(kept_n=len(rk), kept_pct=rk.mean(), kept_pf=C.pf(rk),
               kept_hit=float((kt['why'] == 2).mean()), uplift=up,
               p_gate=float((nul >= up).mean()), p_boot=float((bo <= 0).mean()),
               mde_uplift=2.802 * nul.std(ddof=1), mde_kept=C.N.mde(rk.std(ddof=1), len(rk)))
print(pd.Series(out).to_string(float_format=lambda v: f"{v:.4f}"))
pd.DataFrame([out]).to_csv(os.path.join(HERE, "t5_holdout.csv"), index=False)

hd("6  DEFLATION")
LD = pd.read_csv(os.path.join(HERE, "t3_ladder.csv"))
AB = pd.read_csv(os.path.join(HERE, "t3_ablation.csv"))
G1 = pd.read_csv(os.path.join(HERE, "t1_gate1.csv"))
looks = dict(gate1=len(G1), ladder=len(LD), ablation=len(AB), gate2=int((G2.shape[0])),
             gate2_twin_reference=int(G2.shape[0]), holdout=1)
NL = sum(looks.values())
print("  looks:", looks, "TOTAL", NL)
emax = C.N.e_max_normal(NL)
# per-trade Sharpe of every Gate-2 kept arm (research) -> the variance across trials
g2 = pd.read_csv(os.path.join(HERE, "t4_gate2.csv"))
g2 = g2[g2.src == "score"]
srs = (g2["kept_pct"] / g2["kept_sd"]).to_numpy()
srs = srs[np.isfinite(srs)]
v = srs.var(ddof=1)
sr0 = np.sqrt(v) * emax
sr = cell.kept_pct / cell.kept_sd
# research kept trades for skew/kurt of the chosen cell
c = C.ctx(TF)
rg = F[(F.day.isin(IS_D)) & (F.tf == TF) & (F.gated == 1)].sort_values("sig")
Rp = pd.read_pickle(os.path.join(HERE, "t3_oof.pkl"))
sco = Rp[(Rp.tf == TF) & (Rp.gated == 1)].sort_values("sig")[f"oof_{BEST}"].to_numpy()
kk = sco >= cell.thr
kt_r = walk(c, rg["sig"].to_numpy()[kk], rg["side"].to_numpy()[kk])
x = kt_r["pct"].to_numpy()
g3 = skew(x); g4 = kurtosis(x, fisher=False)
dsr = norm.cdf((sr - sr0) * np.sqrt(len(x) - 1) / np.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2))
print(f"  E[max t | noise] over {NL} looks = {emax:.3f}  (detection needs 2.802)")
print(f"  chosen cell per-trade Sharpe {sr:.4f} on {len(x)} research trades; sd of per-trade Sharpe "
      f"across the {len(srs)} Gate-2 arms {np.sqrt(v):.4f} -> SR0 = {sr0:.4f}")
print(f"  deflated Sharpe = {dsr:.4f}  ({'PASS' if dsr > 0.95 else 'FAIL'} at 0.95)")

hd("7  THE PF-1.5 ARITHMETIC PER TIMEFRAME (the primary's own realised win and loss sizes)")
rows = []
for tf in C.TFS:
    t = C.ctx(tf).trades(P)
    r = t["pct"].to_numpy(); W = r[r > 0].mean(); Lq = -r[r <= 0].mean()
    wst = 1.5 * Lq / (W + 1.5 * Lq)
    gq = G2[G2.tf == tf]
    rows.append(dict(tf=tf, n=len(r), win=(r > 0).mean(), avg_win=W, avg_loss=Lq, pf=C.pf(r),
                     win_needed_pf15=wst, lift_needed=wst - (r > 0).mean(),
                     best_gate2_kept_win=gq["kept_win"].max(), best_gate2_kept_pf=gq["kept_pf"].max()))
A = pd.DataFrame(rows)
print(A.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
print("  NB a 'win' here includes the breakeven exit booking +3 - 2.29 = +0.71 points; those are")
print("  relabelled scratches, so the win rate overstates the target-hit rate (printed in T1/T4).")
A.to_csv(os.path.join(HERE, "t5_pf15.csv"), index=False)
pd.DataFrame([dict(looks=NL, emax=emax, sr=sr, sr0=sr0, dsr=dsr, n=len(x))]).to_csv(
    os.path.join(HERE, "t5_deflation.csv"), index=False)
