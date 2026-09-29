"""N4 -- the win/lose contrast, and the arithmetic of the ask.

The R objective is null. The obvious next move is the objective that raises a profit factor by
construction -- train on WIN/LOSE -- and the point of running it is to price what it costs. Both
objectives run on the SAME folds so the difference is the objective and nothing else.
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5"); sys.path.insert(0, "research/s3nn")
import numpy as np, pandas as pd
import nn_model as M
from scipy.stats import spearmanr

R = "results/s3nn/"
print(__doc__)
t0 = time.time()
pd.set_option("display.width", 240); pd.set_option("display.max_columns", 40)
rng = np.random.default_rng(23)

tr = pd.read_parquet(R + "n2_rows.parquet")
X = np.load(R + "n2_X.npy")
mods = pd.read_csv(R + "model_names.csv", header=None)[0].tolist()
OOF_R = np.load(R + "oof_real.npy")
y = tr.R.to_numpy(); day = tr.day.to_numpy()
w = tr.u.to_numpy(); w = w / w.mean()
sig, ex = tr.sig.to_numpy(), tr.exit.to_numpy()
folds = M.purged_folds(sig, ex, n_folds=5, embargo=0.01)
b_mean, b_p90 = y.mean(), np.percentile(y, 90)
b_pf = y[y > 0].sum() / -y[y < 0].sum()
b_win = (y > 0).mean()

print("=" * 118)
print("N4.1  SAME FOLDS, SAME FEATURES, ONE OBJECTIVE CHANGED")
print("=" * 118)
ybin = (y > 0).astype(float)
OOF_W = M.run_oof(X, ybin, w, sig, ex, folds, shuffle=False)
rows = []
for j, nm in enumerate(mods):
    for tag, sc in (("R", OOF_R[:, j]), ("win", OOF_W[nm])):
        for f in (0.3, 0.5):
            s = M.keep_stats(y, sc, f)
            k = s["kept"]
            ctl = np.array([y[rng.choice(len(y), k, replace=False)].mean() for _ in range(600)])
            rows.append(dict(model=nm, obj=tag, keep=f, R=s["mean"], pf=s["pf"],
                             win=s["win"], p90=s["p90"], p_ctl=(ctl >= s["mean"]).mean()))
C = pd.DataFrame(rows)
C.to_csv(R + "n4_objective.csv", index=False)
print(f"  baseline: R {b_mean:+.4f}  PF {b_pf:.3f}  win {b_win:.3f}  p90 {b_p90:.3f}\n")
piv = C.pivot_table(index=["model", "keep"], columns="obj",
                    values=["win", "pf", "p90", "R"]).round(4)
print(piv.to_string())
gw = C[C.obj == "win"]; gr = C[C.obj == "R"]
print(f"\n  trained on WIN: win rate rises above baseline in {(gw.win>b_win).sum()} of {len(gw)} "
      f"cells, and p90 of R FALLS in {(gw.p90<b_p90).sum()} of {len(gw)}")
print(f"  trained on R  : win rate rises in {(gr.win>b_win).sum()} of {len(gr)}, "
      f"p90 falls in {(gr.p90<b_p90).sum()} of {len(gr)}")
print(f"  best PF on the win objective {gw.pf.max():.3f} at control p "
      f"{gw.loc[gw.pf.idxmax(),'p_ctl']:.3f}; on the R objective {gr.pf.max():.3f} at "
      f"p {gr.loc[gr.pf.idxmax(),'p_ctl']:.3f}")
print(f"  cells clearing the control at p<=0.05: win {int((gw.p_ctl<=0.05).sum())}/{len(gw)}, "
      f"R {int((gr.p_ctl<=0.05).sum())}/{len(gr)}  (chance {0.05*len(gw):.1f} each)")

print("\n" + "=" * 118)
print("N4.2  WHAT THE ASK ACTUALLY REQUIRES -- arithmetic, not a backtest")
print("=" * 118)
pos, neg = y[y > 0], y[y < 0]
gp, gl = pos.mean(), -neg.mean()
print(f"  on the event population: mean win {gp:+.3f} R, mean loss {-gl:+.3f} R, "
      f"win rate {b_win:.3f}  ->  PF {b_pf:.3f}")
print(f"  {'target PF':>10} {'win rate needed':>16} {'lift over base':>15} "
      f"{'best delivered':>15}")
best_lift = gw.win.max() - b_win
for target in (1.5, 2.0, 3.0):
    need = target * gl / (target * gl + gp)
    print(f"  {target:>10.1f} {need:>16.3f} {need-b_win:>+15.3f} {best_lift:>+15.3f}")
print("\n  that holds the win/loss SIZES fixed, which is the generous reading -- a filter that")
print("  raises the win rate here also cuts p90 of R, so the real requirement is larger.")

print("\n" + "=" * 118)
print("N4.3  SHARPE, THE OTHER HALF OF THE ASK")
print("=" * 118)
import s5data as S
DAYS = np.unique(day)
best = OOF_W[max(OOF_W, key=lambda m: spearmanr(OOF_W[m], ybin).statistic)]
for lab, sc in (("none (base)", None), ("R objective, mlp_4x128", OOF_R[:, mods.index("mlp_4x128")]),
                ("win objective, best IC", best)):
    for f in ([1.0] if sc is None else [0.3, 0.5]):
        idx = np.arange(len(y)) if sc is None else np.argsort(-sc)[:int(round(f*len(y)))]
        sp, _ = S.day_sharpe(day[idx], tr.pts.to_numpy()[idx], DAYS)
        r = y[idx]
        print(f"  {lab:24s} keep {f:>4.0%}: n {len(idx):4d}  Sharpe {sp:+.3f}  "
              f"PF {r[r>0].sum()/max(-r[r<0].sum(),1e-9):.3f}  R {r.mean():+.4f}")
print("  Sharpe is computed over EVERY research trading day, zero-filled -- a filter is not paid")
print("  for trading less.")
print(f"\n  TRIALS: 83 (N1-N3) + 8 models x 2 rungs (N4) = 99. No locked read was taken: nothing")
print(f"  cleared Gate 2 on research, so the block is unspent.")
print(f"\ntotal {time.time()-t0:.0f}s")
