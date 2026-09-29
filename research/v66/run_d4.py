"""D4 -- Gate 2, the locked read, and the deflation.

Gate 2 asks the only question that matters about the meta layer: does scoring the primary's events
improve the UNSIZED per-event return, against two nulls at once --
  * a day-block BOOTSTRAP, for whether the uplift differs from zero;
  * a SAME-SELECTIVITY RANDOM FILTER, for whether restrictiveness alone produced it.
Both are needed. STUDY_V15_BOOK recorded that they answer different questions and can disagree.

THE LOCKED READ IS A SECOND READ. P3's locked block was opened in STUDY_BAYESOPT_DONCHIAN, so
everything printed for block 1 here is DESCRIPTIVE, and it is labelled as such rather than being
quoted as a test.

Two things are printed beside every uplift because this branch has been wrong without them:
  * THE KEPT FRACTION. A research threshold that does not keep the same share out of sample is not
    calibrated, and then no research threshold means anything (STUDY_AUTOBNN kept 105 of 105).
  * p90 OF R IN THE KEPT SET. A breakout earns in the tail; a filter that raises the win rate and
    cuts the tail has optimised the wrong thing (STUDY_V32, STUDY_V28).
"""
import os, pickle, sys, time, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.append("/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/mechanism-first-alpha/scripts")
from gates import deflated_sharpe, effective_trials, reality_check    # noqa: E402
sys.path.insert(0, "research/v66")
import torch
torch.set_num_threads(1)

t0 = time.time()
pd.set_option("display.width", 220)
print(__doc__)
FE = pd.read_parquet("results/v66/events_features.parquet")
with open("results/v66/frozen.pkl", "rb") as f:
    Z = pickle.load(f)
COLS, FAM = Z["cols"], Z["fam"]
R = FE[FE.blk == 0].reset_index(drop=True)
L = FE[FE.blk == 1].reset_index(drop=True)
LD = pd.read_csv("results/v66/d3_ladder.csv")
AB = pd.read_csv("results/v66/d3_ablation.csv")
rng = np.random.default_rng(660)

def line(t):
    print("\n" + "=" * 126); print(t); print("=" * 126, flush=True)

import runpy
_m = runpy.run_path("research/v66/_mlmod.py")
oof, fit_full, uniqueness, ic = _m["oof"], _m["fit_full"], _m["uniqueness"], _m["ic"]

y = R.R.to_numpy(float)
yl = L.R.to_numpy(float)
best = LD.sort_values("ic", ascending=False).model.iloc[0]
print(f"  best model in the ladder: {best}   research n {len(R)}   locked n {len(L)}")

line("D4.0  IS THE PIN CONTRIBUTION LARGER THAN SEED NOISE? -- the ablation over 8 seeds")
print("  D3's ablation is one seed. The PIN delta there (-0.0077) is the same size as the")
print("  participation family's and an eighth of the volatility family's, so it has to be shown")
print("  to survive the noise in the fit before it is called a contribution at all.\n")
seeds = list(range(8))
ic_all = np.array([ic(oof(R, COLS, best, seed=s_), y) for s_ in seeds])
print(f"{'feature set':>26} {'mean IC':>9} {'sd':>8} {'mean d':>9} {'d>0 in':>9} {'t':>7}")
print(f"{'ALL':>26} {ic_all.mean():>9.4f} {ic_all.std(ddof=1):>8.4f} {'':>9} {'':>9} {'':>7}")
seedrows = []
for fam in FAM + ["__pinonly"]:
    if fam == "__pinonly":
        cols = [c for c in COLS if c.startswith("pin.")]
        lbl = "PIN family alone"
    else:
        cols = [c for c in COLS if not c.startswith(fam + ".")]
        lbl = "drop " + fam
    v = np.array([ic(oof(R, cols, best, seed=s_), y) for s_ in seeds])
    d = v - ic_all
    t = d.mean() / max(d.std(ddof=1) / np.sqrt(len(d)), 1e-12)
    seedrows.append(dict(set=lbl, mean_ic=v.mean(), sd=v.std(ddof=1), mean_d=d.mean(),
                         pos=int((d > 0).sum()), t=t))
    print(f"{lbl:>26} {v.mean():>9.4f} {v.std(ddof=1):>8.4f} {d.mean():>+9.4f} "
          f"{str(int((d>0).sum()))+'/8':>9} {t:>+7.2f}", flush=True)
SR = pd.DataFrame(seedrows)
SR.to_csv("results/v66/d4_seeds.csv", index=False)
pinrow = SR[SR.set == "drop pin"].iloc[0]
volrow = SR[SR.set == "drop vol"].iloc[0]
print(f"\n  dropping PIN: mean IC change {pinrow.mean_d:+.4f} (t {pinrow.t:+.2f})")
print(f"  dropping vol: mean IC change {volrow.mean_d:+.4f} (t {volrow.t:+.2f})")

line("D4.1  GATE 2 -- unsized uplift against a bootstrap AND a same-selectivity random filter")
pr = oof(R, COLS, best, seed=1)
print(f"{'keep':>6} {'n':>5} {'R/ev':>9} {'uplift':>9} {'boot p':>8} {'rand p':>8} "
      f"{'PF':>7} {'p90 R':>8}")
base = y.mean(); base_pf = y[y > 0].sum()/max(-y[y < 0].sum(), 1e-9)
base_p90 = float(np.quantile(y, 0.90))
print(f"{'base':>6} {len(y):>5} {base:>9.4f} {'':>9} {'':>8} {'':>8} {base_pf:>7.3f} "
      f"{base_p90:>8.3f}")
days = R.day.to_numpy()
g2 = []
for keep in (0.8, 0.6, 0.5, 0.4, 0.3):
    thr = np.nanquantile(pr, 1 - keep)
    m = np.isfinite(pr) & (pr >= thr)
    sel = y[m]
    up = sel.mean() - base
    # day-block bootstrap: resample whole DAYS with their events attached
    ud = np.unique(days)
    bs = np.empty(1000)
    for j in range(1000):
        pick = rng.choice(ud, len(ud), replace=True)
        idx = np.concatenate([np.flatnonzero((days == d) & m) for d in pick])
        bs[j] = y[idx].mean() - base if len(idx) else np.nan
    bp = float(np.nanmean(bs <= 0))
    # same-selectivity random filter
    rc = np.empty(1000)
    for j in range(1000):
        pick = rng.choice(len(y), m.sum(), replace=False)
        rc[j] = y[pick].mean()
    rp = float(np.mean(rc >= sel.mean()))
    pf = sel[sel > 0].sum()/max(-sel[sel < 0].sum(), 1e-9)
    p90 = float(np.quantile(sel, 0.90))
    g2.append(dict(keep=keep, n=int(m.sum()), r=sel.mean(), up=up, boot=bp, rand=rp,
                   pf=pf, p90=p90))
    print(f"{keep:>6.2f} {int(m.sum()):>5} {sel.mean():>9.4f} {up:>+9.4f} {bp:>8.3f} "
          f"{rp:>8.3f} {pf:>7.3f} {p90:>8.3f}", flush=True)
G2 = pd.DataFrame(g2)
G2.to_csv("results/v66/d4_gate2.csv", index=False)
ok = G2[(G2.boot <= 0.05) & (G2.rand <= 0.05)]
print(f"\n  cells clearing BOTH nulls at p<=0.05: {len(ok)} of {len(G2)}")

line("D4.2  ONE LOCKED READ -- DESCRIPTIVE (P3's locked block was opened in STUDY_BAYESOPT_DONCHIAN)")
mdl = fit_full(R, COLS, best, seed=1)
sc = mdl["scaler"]
pl = mdl["predict"](L[COLS].to_numpy(float))
prf = mdl["predict"](R[COLS].to_numpy(float))
print(f"{'keep set':>10} {'thr':>9} {'n kept':>8} {'kept %':>8} {'R/ev':>9} {'uplift':>9} "
      f"{'PF':>7} {'p90 R':>8}")
lb = yl.mean(); lpf = yl[yl > 0].sum()/max(-yl[yl < 0].sum(), 1e-9)
print(f"{'base':>10} {'':>9} {len(yl):>8} {'100.0':>8} {lb:>9.4f} {'':>9} {lpf:>7.3f} "
      f"{float(np.quantile(yl,0.90)):>8.3f}")
rows = []
for keep in (0.6, 0.5, 0.4):
    thr = float(np.nanquantile(prf, 1 - keep))
    m = pl >= thr
    if m.sum() < 10:
        print(f"{keep:>10.2f} {thr:>9.4f} {int(m.sum()):>8}  -- too few --")
        continue
    sel = yl[m]
    pf = sel[sel > 0].sum()/max(-sel[sel < 0].sum(), 1e-9)
    rows.append(dict(keep=keep, kept=m.mean(), r=sel.mean(), pf=pf))
    print(f"{keep:>10.2f} {thr:>9.4f} {int(m.sum()):>8} {100*m.mean():>7.1f}% {sel.mean():>9.4f} "
          f"{sel.mean()-lb:>+9.4f} {pf:>7.3f} {float(np.quantile(sel,0.90)):>8.3f}")
LK = pd.DataFrame(rows)
if len(LK):
    d = float(np.abs(LK.kept - LK.keep).max())
    verdict = ("calibrated" if d < 0.10 else
               "NOT calibrated -- the research threshold does not transfer")
    print(f"\n  CALIBRATION: largest gap between the fraction asked for and the fraction kept "
          f"{d:.3f}  ({verdict})")

line("D4.3  DEFLATION -- the search that produced this")
trials = 4 + len(LD) * 2 + len(AB) + len(G2) + 3
sr = R.R.to_numpy()
per = sr.mean() / max(sr.std(ddof=1), 1e-9)
allsr = []
for _, r in LD.iterrows():
    allsr.append(r.ic)
var_tr = float(np.var(np.array(allsr), ddof=1))
N = effective_trials(trials, 0.7)
ds = deflated_sharpe(per, len(sr), trials, var_tr, float(pd.Series(sr).skew()),
                     float(pd.Series(sr).kurt()) + 3.0, avg_correlation=0.7)
print(f"  counted looks: {trials}   effective N (avg corr 0.7): {N:.1f}")
print(f"  per-event Sharpe {per:.4f}   var over trial statistics {var_tr:.6f}")
print(f"  deflated Sharpe {ds if np.isscalar(ds) else ds}")
print(f"\n[{time.time()-t0:.0f}s]")
