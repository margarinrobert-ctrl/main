"""T5 -- real edge or fluke? Two nulls, the deflation, the reality check, and the regime split.

A rule can beat zero and lose to a coin flip, or beat a coin flip and lose to zero -- this branch
has recorded both. So both nulls are run. Then the search is priced: 10 minutes was tried AFTER
five minutes, both readings of (k,w) were tried, and a 30-cell grid and a 630-cell geometry grid
were read, so the best number here is the maximum of a search and has to be deflated as one.
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5"); sys.path.insert(0, "research/s310")
import numpy as np, pandas as pd
from scipy import stats as sps
import s5sig as SG, s5data as S
import t10core as T

R = "results/s310/"
print(__doc__); t0 = time.time()
pd.set_option("display.width", 240); pd.set_option("display.max_columns", 40)
D, F, base = T.build(10)
D5, F5, _ = T.build(5)
CELLS = [("10m CARRY k3/w20", D, F, T.CARRY),
         ("10m MATCHED k2/w10", D, F, T.MATCHED),
         ("5m reference k3/w20", D5, F5, T.CARRY)]

print("=" * 122)
print("T5.1  NULL A -- a matched RANDOM ENTRY: same window, rate, side mix, geometry and lock")
print("=" * 122)
rows = []
for lab, DD, FF, p in CELLS:
    lg, sh = SG.s3_flow_exhaustion(DD, FF, p)
    t = T.run(DD, lg, sh)
    for b, bl in ((0, "research"), (1, "LOCKED")):
        if len(t[t.blk == b]) < 20:
            continue
        real, ctl, pv = T.control_random_entry(DD, t, b, n_draw=400, seed=10 + b)
        rows.append(dict(cell=lab, block=bl, n=len(t[t.blk == b]), rule=real,
                         ctl_med=np.nanmedian(ctl), ctl_p5=np.nanpercentile(ctl, 5),
                         ctl_p95=np.nanpercentile(ctl, 95), excess=real - np.nanmedian(ctl), p=pv))
        print(f"  ...{lab} {bl} done {time.time()-t0:.0f}s")
A = pd.DataFrame(rows)
A.to_csv(R + "t5_null_entry.csv", index=False)
print(A.round(3).to_string(index=False))
print("  READ THE CONTROL'S OWN LEVEL FIRST: clearing a null that loses money does not prove")
print("  profit, and failing a null that makes money does not prove there is nothing there.")

print("\n" + "=" * 122)
print("T5.2  NULL B -- the rule's OWN BARS, coin-flip SIDE. Isolates the direction call.")
print("=" * 122)
rows = []
for lab, DD, FF, p in CELLS:
    lg, sh = SG.s3_flow_exhaustion(DD, FF, p)
    for b, bl in ((0, "research"), (1, "LOCKED")):
        t = T.run(DD, lg, sh)
        if len(t[t.blk == b]) < 20:
            continue
        real, ctl, pv = T.control_coin_side(DD, lg, sh, b, n_draw=400, seed=20 + b)
        rows.append(dict(cell=lab, block=bl, rule=real, ctl_med=np.nanmedian(ctl),
                         excess=real - np.nanmedian(ctl), p=pv))
B = pd.DataFrame(rows)
B.to_csv(R + "t5_null_side.csv", index=False)
print(B.round(3).to_string(index=False))
print("  If the side is worth nothing, whatever the rule earns is the window and the geometry.")

print("\n" + "=" * 122)
print("T5.3  THE REGIME SPLIT -- where the sign actually changes")
print("=" * 122)
for lab, DD, FF, p in CELLS:
    lg, sh = SG.s3_flow_exhaustion(DD, FF, p)
    t = T.run(DD, lg, sh)
    t["yr"] = pd.to_datetime(t.day.to_numpy(), unit="D").year
    g = t.groupby("yr").pts.agg(["size", "mean", "sum"])
    g["pf"] = t.groupby("yr").pts.apply(lambda r: r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9))
    print(f"\n  {lab}")
    print(g.round(3).to_string())

print("\n" + "=" * 122)
print("T5.4  DEFLATION -- the best number here is the maximum of a search")
print("=" * 122)
# every cell that was read, so the count is not understated
kw = pd.read_csv(R + "t1_kw_grid.csv")
n_kw = kw[["k", "w"]].drop_duplicates().shape[0]
n_geo = 630 * 2
n_tf = 2
TRIALS = n_kw + n_geo + n_tf + 3
print(f"  cells read: {n_kw} (k,w) x 1 geometry, {n_geo} geometry x 2 readings, "
      f"{n_tf} timeframes, 3 declared cells  ->  N = {TRIALS}")

def dsr(sr, T_obs, N, var_tr, sk, ku):
    """Bailey & Lopez de Prado. sr is PER-OBSERVATION, never annualised."""
    g = 0.5772156649
    emax = np.sqrt(var_tr) * ((1 - g) * sps.norm.ppf(1 - 1.0 / N) +
                              g * sps.norm.ppf(1 - 1.0 / (N * np.e)))
    num = (sr - emax) * np.sqrt(T_obs - 1)
    den = np.sqrt(1 - sk * sr + (ku - 1) / 4.0 * sr ** 2)
    return float(sps.norm.cdf(num / den)), float(emax)

rows = []
allsr = []
for k in kw[["k", "w"]].drop_duplicates().itertuples(index=False):
    lg, sh = SG.s3_flow_exhaustion(D, F, dict(k=int(k.k), w=int(k.w)))
    t = T.run(D, lg, sh)
    s = t[t.blk == 0]
    if len(s) >= 30:
        r = s.pts.to_numpy()
        allsr.append(r.mean() / (r.std(ddof=1) + 1e-12))
var_tr = float(np.var(allsr, ddof=1))
for lab, DD, FF, p in CELLS:
    lg, sh = SG.s3_flow_exhaustion(DD, FF, p)
    t = T.run(DD, lg, sh)
    for b, bl in ((0, "research"), (1, "LOCKED")):
        s = t[t.blk == b]
        if len(s) < 20:
            continue
        r = s.pts.to_numpy()
        sr = r.mean() / (r.std(ddof=1) + 1e-12)
        d, emax = dsr(sr, len(r), TRIALS, var_tr, float(sps.skew(r)), float(sps.kurtosis(r) + 3))
        rows.append(dict(cell=lab, block=bl, n=len(r), sr_per_trade=sr, E_max_null=emax,
                         DSR=d, beats_noise_floor=sr > emax))
DS = pd.DataFrame(rows)
DS.to_csv(R + "t5_deflated.csv", index=False)
print(f"  variance of the trial Sharpes: {var_tr:.6f}  (measured over the (k,w) population, "
      f"per-trade, NOT annualised -- STUDY_XAU_TWO_LAYER)")
print(DS.round(4).to_string(index=False))
print("  E_max_null is the best per-trade Sharpe pure noise is expected to produce at this many")
print("  looks. A cell BELOW it is worse than the noise floor whatever its p-value says.")

print("\n" + "=" * 122)
print("T5.5  WHITE'S REALITY CHECK across the whole candidate set (research block)")
print("=" * 122)
ser = {}
for k in kw[["k", "w"]].drop_duplicates().itertuples(index=False):
    lg, sh = SG.s3_flow_exhaustion(D, F, dict(k=int(k.k), w=int(k.w)))
    t = T.run(D, lg, sh)
    if len(t[t.blk == 0]) >= 30:
        ser[f"k{int(k.k)}w{int(k.w)}"] = T.daily(t, D, 0)
P = pd.DataFrame(ser)
X = P.to_numpy()
mu = X.mean(0)
rng = np.random.default_rng(7)
nb, blk = 2000, 10
Tn = len(X)
maxstat = np.empty(nb)
for b in range(nb):
    st = rng.integers(0, Tn - blk, size=Tn // blk + 1)
    idx = np.concatenate([np.arange(s, s + blk) for st_ in [0] for s in st])[:Tn]
    Xi = X[idx]
    maxstat[b] = np.max(np.sqrt(Tn) * (Xi.mean(0) - mu))
V = np.sqrt(Tn) * mu.max()
p_rc = float((maxstat >= V).mean())
print(f"  {X.shape[1]} candidates, {Tn} research sessions, stationary block bootstrap (block 10)")
print(f"  best candidate mean/day {mu.max():+.3f} pts   V = {V:.3f}   reality-check p = {p_rc:.3f}")
print(f"  {'PASS' if p_rc <= 0.05 else 'FAIL'} -- this asks whether the BEST of the set beats zero "
      f"once the search is priced.")
print(f"\ntotal {time.time()-t0:.0f}s")
