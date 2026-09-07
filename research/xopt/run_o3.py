"""O3 -- the three tests O2 did not cover: MONTE CARLO, CORRELATION MATRICES, WALK-FORWARD/PBO.

MONTE CARLO IS TWO DIFFERENT QUESTIONS AND THIS BRANCH KEEPS THEM APART:
  * a day-block BOOTSTRAP (resample whole days WITH their trades attached) prices the EDGE;
  * a PERMUTATION of the realised trade order prices the PATH. It cannot change the endpoint, so
    reporting an endpoint distribution from a permutation is meaningless -- it answers a DRAWDOWN
    question only.

WALK-FORWARD IS ALSO TWO QUESTIONS:
  * rolling folds with NOTHING re-selected asks whether the RULE is fitted;
  * folds with the selection RE-RUN inside each training window asks whether the SEARCH is,
    and it needs a RANDOM cell from the same pool beside it or "the optimiser won" is unfalsifiable.
CSCV/PBO then gives P(the selection procedure is harmful) over all symmetric splits.
"""
import os, sys, itertools, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vwapema"))
import xcore as C, vecore as V

RNG = np.random.default_rng(4242)
pd.set_option("display.width", 235)
L = lambda s: print("\n" + "=" * 114 + f"\n{s}\n" + "=" * 114)
print(__doc__)

T = pd.read_parquet("results/xopt/o1_trials.parquet")
FIN = pd.read_csv("results/xopt/o1_finalists.csv")
PK = ["ema_slow", "ema_pull", "ema_tight", "atr_len", "atr_stop", "vol_mult",
      "range_mult", "wick_body", "ambig", "tighten_R"]


def cfg_of(r):
    c = {k: (int(r[k]) if isinstance(V.PARAMS.get(k), int) else float(r[k])) for k in PK}
    c.update(side=int(r["side"]), trail=bool(r["trail"]), tighten=bool(r["tighten"]),
             flatten=bool(r["flatten"]), use_vol=bool(r["use_vol"]), sess=str(r["sess"]))
    tg = r.get("tgt_R", 0.0)
    c["tgt_R"] = float(tg) if r.get("use_tgt", True) and np.isfinite(float(tg)) else 0.0
    return c


CELLS = {"as published": dict()}
for _, r in FIN.iterrows():
    CELLS[f"Optuna {r.study}"] = cfg_of(r)


def trades(cfg, blk=None):
    D = C.data(cfg.get("sess", "ny"))
    p = {**V.PARAMS, **{k: v for k, v in cfg.items() if k in V.PARAMS}}
    side = int(cfg.get("side", 1))
    sig, _ = V.triggers(D, side=side, p=p, use_vwap_vol=cfg.get("use_vol", True))
    t = V.run(D, sig, side=side, tgt_R=float(cfg.get("tgt_R", 3.0)), atr_stop=p["atr_stop"],
              tighten=bool(cfg.get("tighten", True)), flatten=bool(cfg.get("flatten", False)),
              trail=bool(cfg.get("trail", True)), p=p)
    t["date"] = pd.DatetimeIndex(t.ts).normalize()
    t["ym"] = t.date.values.astype("datetime64[M]")
    return t if blk is None else t[t.blk == blk].reset_index(drop=True)


# ---------------------------------------------------------------- 1. Monte Carlo
L("O3.1  MONTE CARLO -- day-block bootstrap for the EDGE, permutation for the PATH")
rows, curves = [], {}
for nm, cfg in CELLS.items():
    for blk, bn in ((0, "research"), (1, "locked")):
        t = trades(cfg, blk)
        if len(t) < 30:
            continue
        r = t.R.to_numpy()
        # edge: resample whole DAYS with their trades attached
        arr = list(t.groupby("date").R.apply(list).values)
        boot = np.array([np.mean(np.concatenate([arr[i] for i in RNG.integers(0, len(arr), len(arr))]))
                         for _ in range(3000)])
        # path: permute the realised order -- the endpoint cannot move, only the drawdown
        cum = np.cumsum(r)
        real_dd = float(np.max(np.maximum.accumulate(cum) - cum))
        dds = np.empty(3000)
        for i in range(3000):
            c2 = np.cumsum(RNG.permutation(r))
            dds[i] = np.max(np.maximum.accumulate(c2) - c2)
        rows.append(dict(cell=nm, block=bn, n=len(t), mean_R=round(float(r.mean()), 4),
                         boot_p=round(float((boot <= 0).mean()), 4),
                         ci_lo=round(float(np.percentile(boot, 2.5)), 4),
                         ci_hi=round(float(np.percentile(boot, 97.5)), 4),
                         realised_dd=round(real_dd, 2),
                         dd_pctile=round(float((dds <= real_dd).mean()), 3),
                         mc_p99_dd=round(float(np.percentile(dds, 99)), 2),
                         dd_ratio=round(float(np.percentile(dds, 99) / max(real_dd, 1e-9)), 2)))
        curves[(nm, bn)] = dict(boot=boot, dds=dds, real_dd=real_dd, cum=cum)
MC = pd.DataFrame(rows)
print(MC.to_string(index=False))
MC.to_csv("results/xopt/o3_montecarlo.csv", index=False)
np.save("results/xopt/o3_curves.npy", np.array([1]))     # marker; curves re-derived in the plot
import pickle; pickle.dump(curves, open("results/xopt/o3_curves.pkl", "wb"))
print("\n  `dd_ratio` is the MC 99th percentile drawdown over the realised one. That is the sizing")
print("  number: a ratio of 2 means the backtest's worst run was half of what the same trades in a")
print("  different order can produce.")

# ---------------------------------------------------------------- 2. correlations
L("O3.2  CORRELATION MATRICES")
ok = T[T.n >= 80].copy()
print("(a) parameter -> research performance, Spearman, over the scorable trial population")
cols = PK + ["tgt_R"]
cm = ok[cols + ["R", "excess", "pf"]].corr(method="spearman")[["R", "excess", "pf"]].loc[cols]
print(cm.round(3).to_string())
cm.to_csv("results/xopt/o3_corr_params.csv")

print("\n(b) the candidates' DAILY R against each other, whole sample")
dl = {}
for nm, cfg in CELLS.items():
    t = trades(cfg)
    if len(t) >= 60:
        dl[nm] = t.groupby("date").R.sum()
Dm = pd.DataFrame(dl).fillna(0.0)
cc = Dm.corr()
print(cc.round(3).to_string())
cc.to_csv("results/xopt/o3_corr_cells.csv")

print("\n(c) YEAR BY YEAR, R per trade")
rows = []
for nm, cfg in CELLS.items():
    t = trades(cfg)
    if len(t) < 60:
        continue
    g = t.groupby(pd.DatetimeIndex(t.ts).year).R.agg(["size", "mean"])
    for y, r in g.iterrows():
        rows.append(dict(cell=nm, year=int(y), n=int(r["size"]), R=round(float(r["mean"]), 3)))
Y = pd.DataFrame(rows)
YP = Y.pivot_table(index="year", columns="cell", values="R")
print(YP.round(3).to_string())
YP.to_csv("results/xopt/o3_years.csv")

# ---------------------------------------------------------------- 3. walk-forward + PBO
L("O3.3  WALK-FORWARD -- nothing re-selected, then the selection re-run in every fold")
pool_src = (T[T.n >= 80].drop_duplicates(subset=PK + ["side", "trail", "flatten", "sess", "tgt_R"])
            .sample(min(260, len(T[T.n >= 80])), random_state=5))
POOL = [cfg_of(r) for _, r in pool_src.iterrows()]
print(f"  pool: {len(POOL)} distinct configurations from the 2,100 trials")
t0 = time.time()
mats = []
for i, cfg in enumerate(POOL):
    t = trades(cfg)
    if len(t) < 40:
        continue
    mats.append(t.groupby("ym").R.mean().rename(i))
M = pd.concat(mats, axis=1).sort_index()
print(f"  monthly matrix {M.shape}   ({time.time()-t0:.0f}s)")
M.to_csv("results/xopt/o3_monthly.csv")

fixed = {nm: trades(cfg).groupby("ym").R.mean() for nm, cfg in CELLS.items()}
mons = M.index.to_numpy()
rows = []
for a in range(0, len(mons) - 48, 12):
    t0m, t1m = mons[a + 36], mons[min(a + 48, len(mons) - 1)]
    trm = M.loc[(M.index >= mons[a]) & (M.index < t0m)]
    tem = M.loc[(M.index >= t0m) & (M.index < t1m)]
    if len(trm) < 24 or len(tem) < 6:
        continue
    best = trm.mean().idxmax()
    rnd = int(RNG.integers(0, M.shape[1]))
    row = dict(test_from=str(t0m)[:7], test_to=str(t1m)[:7],
               re_chosen=round(float(tem[best].mean()), 4),
               random_cell=round(float(tem[rnd].mean()), 4))
    for nm, sm in fixed.items():
        seg = sm[(sm.index >= t0m) & (sm.index < t1m)]
        row[nm] = round(float(seg.mean()), 4) if len(seg) else np.nan
    rows.append(row)
W = pd.DataFrame(rows)
print("\n" + W.to_string(index=False))
W.to_csv("results/xopt/o3_walkforward.csv", index=False)
print("\n  mean OOS R per arm:")
print(W.drop(columns=["test_from", "test_to"]).mean().round(4).to_string())

L("O3.4  CSCV / PBO over all symmetric splits")
Mm = M.dropna(axis=1, thresh=int(0.5 * len(M))).fillna(0.0)
S_BLK = 12
idx = np.array_split(np.arange(len(Mm)), S_BLK)
logits, drops = [], []
for comb in itertools.combinations(range(S_BLK), S_BLK // 2):
    tr = np.concatenate([idx[i] for i in comb])
    te = np.concatenate([idx[i] for i in range(S_BLK) if i not in comb])
    a, b = Mm.iloc[tr].mean(), Mm.iloc[te].mean()
    j = a.idxmax()
    rk = min(max(float(b.rank(pct=True)[j]), 1e-6), 1 - 1e-6)
    logits.append(np.log(rk / (1 - rk)))
    drops.append(float(a.rank(pct=True)[j] - rk))
logits = np.array(logits)
half = len(Mm) // 2
a, b = Mm.iloc[:half].mean(), Mm.iloc[half:].mean()
slope = float(np.polyfit(a.values, b.values, 1)[0])
print(f"  cells {Mm.shape[1]}   months {len(Mm)}   splits {len(logits)}")
print(f"  PBO = {float((logits <= 0).mean()):.3f}   median logit {float(np.median(logits)):+.3f}   "
      f"mean rank drop {float(np.mean(drops)):+.3f}")
print(f"  slope of OOS on IS across cells: {slope:+.3f}    "
      f"IS-best cell: IS {float(a.max()):+.4f} -> OOS {float(b[a.idxmax()]):+.4f}")
pd.DataFrame(dict(logit=logits, drop=drops)).to_csv("results/xopt/o3_pbo.csv", index=False)
print("\n  PBO > 0.5 means the in-sample winner lands BELOW the out-of-sample median more often")
print("  than not -- the selection procedure is actively harmful, not merely useless.")
