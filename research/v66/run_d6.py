"""D6 -- Gate 2 again, on the BEST feature set rather than the biggest one.

D4 ran Gate 2 on all 65 features. D5 then showed that is the WORST configuration measured: seven
volatility features score IC 0.1407 against 65 features' 0.0983 (t +17.08), and volatility + PIN
scores 0.1762. Reporting Gate 2 for a deliberately handicapped model would be reporting the wrong
number, so it is re-run on the set D5 selected -- and the extra looks are added to the trial count.
"""
import pickle, sys, time
import numpy as np, pandas as pd, runpy
sys.path.insert(0, "research/v66")
sys.path.append("/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/mechanism-first-alpha/scripts")
from gates import deflated_sharpe, effective_trials                     # noqa: E402
import torch; torch.set_num_threads(1)

t0 = time.time(); pd.set_option("display.width", 200)
print(__doc__)
_m = runpy.run_path("research/v66/_mlmod.py")
oof, fit_full, ic = _m["oof"], _m["fit_full"], _m["ic"]
FE = pd.read_parquet("results/v66/events_features.parquet")
with open("results/v66/frozen.pkl", "rb") as f:
    Z = pickle.load(f)
COLS = Z["cols"]
SET = [c for c in COLS if c.startswith("vol.") or c.startswith("pin.")]
R = FE[FE.blk == 0].reset_index(drop=True)
L = FE[FE.blk == 1].reset_index(drop=True)
y, yl = R.R.to_numpy(float), L.R.to_numpy(float)
rng = np.random.default_rng(661)
days = R.day.to_numpy()

def line(t):
    print("\n" + "=" * 116); print(t); print("=" * 116, flush=True)

line("D6.1  GATE 2 on vol + pin (21 features) -- bootstrap AND same-selectivity random filter")
pr = np.mean([oof(R, SET, "rf", seed=s) for s in range(5)], axis=0)   # seed-averaged, as scored
print(f"  OOF IC of the averaged score: {ic(pr, y):.4f}   research n {len(R)}")
base = y.mean(); bpf = y[y > 0].sum()/max(-y[y < 0].sum(), 1e-9)
print(f"\n{'keep':>6} {'n':>5} {'R/ev':>9} {'uplift':>9} {'boot p':>8} {'rand p':>8} {'PF':>7} "
      f"{'tgt hit':>8}")
tgt = float(np.nanmax(y))
print(f"{'base':>6} {len(y):>5} {base:>9.4f} {'':>9} {'':>8} {'':>8} {bpf:>7.3f} "
      f"{np.mean(y > tgt*0.98)*100:>7.1f}%")
rows = []
for keep in (0.8, 0.6, 0.5, 0.4, 0.3):
    thr = np.nanquantile(pr, 1 - keep)
    m = np.isfinite(pr) & (pr >= thr)
    sel = y[m]
    ud = np.unique(days)
    bs = np.empty(1000)
    for j in range(1000):
        pick = rng.choice(ud, len(ud), replace=True)
        idx = np.concatenate([np.flatnonzero((days == d) & m) for d in pick])
        bs[j] = y[idx].mean() - base if len(idx) else np.nan
    bp = float(np.nanmean(bs <= 0))
    rc = np.array([y[rng.choice(len(y), m.sum(), replace=False)].mean() for _ in range(1000)])
    rp = float(np.mean(rc >= sel.mean()))
    pf = sel[sel > 0].sum()/max(-sel[sel < 0].sum(), 1e-9)
    rows.append(dict(keep=keep, n=int(m.sum()), r=sel.mean(), up=sel.mean()-base,
                     boot=bp, rand=rp, pf=pf))
    print(f"{keep:>6.2f} {int(m.sum()):>5} {sel.mean():>9.4f} {sel.mean()-base:>+9.4f} "
          f"{bp:>8.3f} {rp:>8.3f} {pf:>7.3f} {np.mean(sel > tgt*0.98)*100:>7.1f}%", flush=True)
G = pd.DataFrame(rows)
G.to_csv("results/v66/d6_gate2.csv", index=False)
ok = G[(G.boot <= 0.05) & (G.rand <= 0.05)]
print(f"\n  cells clearing BOTH nulls at p<=0.05: {len(ok)} of {len(G)}   "
      f"best boot p {G.boot.min():.3f}   best rand p {G.rand.min():.3f}")

line("D6.2  ONE LOCKED READ -- DESCRIPTIVE (P3's locked block was opened in STUDY_BAYESOPT_DONCHIAN)")
mdls = [fit_full(R, SET, "rf", seed=s) for s in range(5)]
pl = np.mean([m["predict"](L[SET].to_numpy(float)) for m in mdls], axis=0)
prf = np.mean([m["predict"](R[SET].to_numpy(float)) for m in mdls], axis=0)
lb = yl.mean(); lpf = yl[yl > 0].sum()/max(-yl[yl < 0].sum(), 1e-9)
print(f"{'keep':>7} {'n kept':>8} {'kept %':>8} {'R/ev':>9} {'uplift':>9} {'PF':>7}")
print(f"{'base':>7} {len(yl):>8} {'100.0':>7}% {lb:>9.4f} {'':>9} {lpf:>7.3f}")
kk = []
for keep in (0.6, 0.5, 0.4, 0.3):
    thr = float(np.nanquantile(prf, 1 - keep))
    m = pl >= thr
    if m.sum() < 10:
        continue
    sel = yl[m]
    pf = sel[sel > 0].sum()/max(-sel[sel < 0].sum(), 1e-9)
    kk.append(dict(keep=keep, kept=m.mean(), r=sel.mean(), pf=pf))
    print(f"{keep:>7.2f} {int(m.sum()):>8} {100*m.mean():>7.1f}% {sel.mean():>9.4f} "
          f"{sel.mean()-lb:>+9.4f} {pf:>7.3f}")
K = pd.DataFrame(kk)
d = float(np.abs(K.kept - K.keep).max())
print(f"\n  CALIBRATION: largest gap between asked-for and kept {d:.3f} "
      f"({'calibrated' if d < 0.10 else 'NOT calibrated'})")

line("D6.3  DEFLATION over the whole search")
trials = 4 + 16 + 11 + 5 + 80 + 6 + 7 + 5      # D1..D6, every look counted
sr = y
per = sr.mean()/max(sr.std(ddof=1), 1e-9)
stats = np.array([0.1407, 0.1762, 0.0983, 0.0923, 0.0409, -0.0087, 0.1501, 0.0915, 0.0667,
                  0.0452, 0.0379, 0.0201, -0.0730, 0.1021, 0.0703, 0.0352, 0.0442, -0.0494,
                  -0.0015, -0.0235, 0.0196])
ds = deflated_sharpe(per, len(sr), trials, float(np.var(stats, ddof=1)),
                     float(pd.Series(sr).skew()), float(pd.Series(sr).kurt()) + 3.0,
                     avg_correlation=0.7)
print(f"  counted looks {trials}   effective N {effective_trials(trials, 0.7):.1f}")
for k, v in ds.items():
    print(f"    {k}: {v}")
print(f"\n[{time.time()-t0:.0f}s]")
