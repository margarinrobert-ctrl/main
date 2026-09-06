"""Visuals for the V61 CVD strategy: walk-forward / out-of-sample, the perturbation Monte Carlo,
and the correlation matrices. Reads the saved walk-forward folds; re-runs the Monte Carlo so the
raw draw arrays exist to plot (the published run printed summaries only).

Figures written to results/v64/:
  v64_fig1_wfo.png    per-fold OOS by arm, cumulative OOS, and the optimiser's parameter stability
  v64_fig2_mc.png     execution / price-jitter / missed-fill / parameter perturbation, + drawdown MC
  v64_fig3_corr.png   preset-to-preset and ablation correlation matrices on daily returns

Takes ~400 s, almost all of it the price jitter (indicators are recomputed on every draw). The raw
draws are saved to v64_mc_arrays.npz; `v64_fig2_replot.py` re-renders figure 2 from them in seconds.
"""
import os, sys, time, warnings
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56", "research/v64"):
    sys.path.insert(0, os.path.join(ROOT, p))
import v54cvd as CV, v64opt as O, v61core as V
warnings.filterwarnings("ignore")
OUT = os.path.join(ROOT, "results/v64"); os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(11)
N_EXEC, N_PRICE, N_JOINT, N_PERM = 2000, 150, 500, 5000

PRESETS = {
    "incumbent 30m": dict(tf=30, ent=20, exN=20, stop=2.0, tp=0.0, hold=480, adapt=0, k=3, w=20,
                          use_ma=0, ma_thr=0.0, use_chop=0, chop_thr=99.0, psh=0),
    "15m preset": dict(tf=15, ent=15, exN=30, stop=3.0, tp=6.0, hold=480, adapt=0, k=3, w=30,
                       use_ma=0, ma_thr=0.0, use_chop=0, chop_thr=99.0, psh=0),
    "Pareto 15m": dict(tf=15, ent=20, exN=34, stop=3.14, tp=5.38, hold=255, adapt=0, k=5, w=58,
                       use_ma=0, ma_thr=0.0, use_chop=0, chop_thr=99.0, psh=0),
}
RUNGS = dict(ent=[-5, 5], exN=[-5, 5], stop=[-0.5, 0.5], tp=[-1.0, 1.0], hold=[-120, 120], k=[-1, 1], w=[-10, 10])
BG, FG, GRID = "#0f1115", "#e6e6e6", "#2a2e36"
C = {"incumbent 30m": "#8a8f99", "15m preset": "#3ec9a7", "Pareto 15m": "#f2b134"}
C1, C2, C3, C4, C5 = "#8a8f99", "#3ec9a7", "#e0605e", "#f2b134", "#4f9de6"
plt.rcParams.update({"figure.facecolor": BG, "axes.facecolor": BG, "axes.edgecolor": GRID, "axes.labelcolor": FG,
                     "xtick.color": FG, "ytick.color": FG, "text.color": FG, "grid.color": GRID,
                     "font.size": 9.5, "axes.titlesize": 11, "legend.facecolor": BG, "legend.edgecolor": GRID})
t0 = time.time()
Ds = {tf: O.build(tf) for tf in (15, 30)}
base = {}
for nm, p in PRESETS.items():
    R_, pct, blk, sg = O.evaluate(Ds[p["tf"]], p)
    eq = np.cumsum(pct[blk == 1])
    base[nm] = dict(pct=pct, blk=blk, sig=sg, lock=pct[blk == 1], res=pct[blk == 0],
                    lock_tot=float(pct[blk == 1].sum()), lock_dd=float(-(eq - np.maximum.accumulate(eq)).min()))
print(f"presets evaluated {time.time()-t0:.0f}s: " + ", ".join(f"{k} lock {v['lock_tot']:+.2f}% n {len(v['lock'])}" for k, v in base.items()))

# =====================================================================================
# FIGURE 1 -- walk-forward / out of sample
# =====================================================================================
WR = pd.read_parquet(os.path.join(OUT, "wfo_rolling.parquet")); WE = pd.read_parquet(os.path.join(OUT, "wfo_expanding.parquet"))
folds = WR.fold.tolist(); nf = len(folds)
POST = 5   # folds 0..4 are inside the research block the fixed arms were built on; 5..8 are post-cut
fig = plt.figure(figsize=(15, 10.5))
gs = fig.add_gridspec(3, 2, height_ratios=[1.05, 1.0, 1.15], hspace=0.42, wspace=0.22)

ax = fig.add_subplot(gs[0, :])
arms = [("re-chosen each fold, rolling 4Q", WR.oos_tot.to_numpy(), C5), ("re-chosen each fold, expanding", WE.oos_tot.to_numpy(), "#9b7fd4"),
        ("FIXED incumbent 30m", WR.fixed.to_numpy(), C1), ("FIXED 15m preset", WR.fixed15.to_numpy(), C2), ("RANDOM cell from the grid", WR.rnd.to_numpy(), C3)]
w = 0.16; x = np.arange(nf)
for i, (nm, y, col) in enumerate(arms):
    ax.bar(x + (i - 2) * w, y, w, color=col, label=f"{nm}   sum {y.sum():+.1f}%")
ax.axhline(0, color=FG, lw=0.8); ax.axvline(POST - 0.5, color=C4, ls="--", lw=1.2)
ax.text(POST - 0.45, ax.get_ylim()[1] * 0.94, " post-cut: the fixed arms had never seen these quarters", color=C4, fontsize=9, va="top")
ax.set_xticks(x); ax.set_xticklabels(folds); ax.set_ylabel("out-of-sample return, % of entry price")
ax.set_title("A. Walk-forward: each quarter is held out, the optimiser re-selects from 19,200 cells inside the training window only")
ax.legend(fontsize=8, ncol=2, loc="upper left"); ax.grid(axis="y", alpha=0.3)

ax = fig.add_subplot(gs[1, 0])
for nm, y, col in arms:
    ax.plot(np.arange(nf + 1), np.concatenate(([0], np.cumsum(y))), "o-", color=col, lw=2 if "FIXED 15m" in nm else 1.5, ms=4, label=nm)
ax.axvline(POST, color=C4, ls="--", lw=1); ax.axhline(0, color=GRID)
ax.set_xticks(np.arange(nf + 1)); ax.set_xticklabels([""] + folds, rotation=45, fontsize=8)
ax.set_ylabel("cumulative OOS %"); ax.set_title("B. Cumulative across the nine quarters"); ax.grid(alpha=0.3); ax.legend(fontsize=7.5, loc="upper left")

ax = fig.add_subplot(gs[1, 1])
post = slice(POST, nf)
lab = ["rolling\nre-chosen", "expanding\nre-chosen", "FIXED\nincumbent", "FIXED\n15m", "RANDOM\ncell"]
allv = [y.sum() for _, y, _ in arms]; pv = [y[post].sum() for _, y, _ in arms]; cols = [c for _, _, c in arms]
xx = np.arange(5)
ax.bar(xx - 0.2, allv, 0.4, color=cols, alpha=0.45)
ax.bar(xx + 0.2, pv, 0.4, color=cols)
for i, (a_, b_) in enumerate(zip(allv, pv)):
    ax.text(i - 0.2, a_ + 0.4, f"{a_:+.1f}", ha="center", fontsize=8); ax.text(i + 0.2, b_ + 0.4, f"{b_:+.1f}", ha="center", fontsize=8, fontweight="bold")
ax.set_xticks(xx); ax.set_xticklabels(lab, fontsize=8); ax.axhline(0, color=GRID); ax.set_ylabel("total OOS %")
ax.set_title("C. All folds vs the four the fixed arms never saw"); ax.grid(axis="y", alpha=0.3)
ax.legend(fontsize=7.5, handles=[Patch(facecolor=C1, alpha=0.45, label="all 9 folds"), Patch(facecolor=C1, label="4 post-cut folds")])

ax = fig.add_subplot(gs[2, :])
axes_ = ["tf", "ent", "exN", "stop", "tp", "k", "w"]
grid = np.zeros((len(axes_), nf))
labels = np.empty((len(axes_), nf), dtype=object)
for j, f_ in enumerate(folds):
    for i, a_ in enumerate(axes_):
        vals = WR[a_].to_numpy(); modal = pd.Series(vals).mode().iloc[0]
        grid[i, j] = 1.0 if vals[j] == modal else 0.0; labels[i, j] = f"{vals[j]:g}"
im = ax.imshow(grid, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto", alpha=0.55)
for i in range(len(axes_)):
    for j in range(nf):
        ax.text(j, i, labels[i, j], ha="center", va="center", fontsize=8.5, color=FG)
ax.set_yticks(range(len(axes_))); ax.set_yticklabels(["timeframe", "entry ch", "exit ch", "stop ATR", "target ATR", "pivot k", "window w"])
ax.set_xticks(range(nf)); ax.set_xticklabels(folds)
shares = [100 * np.mean(WR[a_].to_numpy() == pd.Series(WR[a_].to_numpy()).mode().iloc[0]) for a_ in axes_]
ax.set_title("D. What the optimiser chose in each training window -- green = its modal value.  Modal share: "
             + ", ".join(f"{a_} {s:.0f}%" for a_, s in zip(axes_, shares)) + "   (entry 15 in 9/9, exit 30 in 8/9, no target in 8/9)")
fig.suptitle("V61 CVD -- walk-forward, NQ, 19,200 declared cells re-searched inside every training window", fontsize=13, y=0.985)
fig.savefig(os.path.join(OUT, "v64_fig1_wfo.png"), dpi=135, bbox_inches="tight"); plt.close(fig)
print(f"fig1 done {time.time()-t0:.0f}s")

# =====================================================================================
# FIGURE 2 -- the perturbation Monte Carlo (arrays saved; v64_fig2_replot.py redraws them)
# =====================================================================================
exec_d, price_d, joint_d, perm_d = {}, {}, {}, {}
for nm, p in PRESETS.items():
    D = Ds[p["tf"]]
    v = np.zeros(N_EXEC)
    for i in range(N_EXEC):
        R_, pct, blk, sg = O.evaluate(D, p, cost=V.COST * rng.uniform(0.5, 2.0), slip=rng.uniform(0.0, 2.0 * V.SLIP))
        v[i] = pct[blk == 1].sum()
    exec_d[nm] = v
    for sig_t in (0.5, 1.0, 2.0):
        tt = np.zeros(N_PRICE)
        for i in range(N_PRICE):
            o_, h_, l_, c_ = O.perturb_bars(D, sig_t, rng)
            R_, pct, blk, sg = O.evaluate_perturbed(D, p, o_, h_, l_, c_, CV)
            tt[i] = pct[blk == 1].sum()
        price_d[(nm, sig_t)] = tt
    jj = np.zeros(N_JOINT)
    for i in range(N_JOINT):
        q = dict(p)
        q["ent"] = int(max(5, q["ent"] + rng.integers(-5, 6))); q["exN"] = int(max(5, q["exN"] + rng.integers(-5, 6)))
        q["stop"] = float(max(0.5, q["stop"] + rng.uniform(-0.5, 0.5))); q["tp"] = float(max(0.0, q["tp"] + rng.uniform(-1, 1))) if q["tp"] > 0 else 0.0
        q["k"] = int(np.clip(q["k"] + rng.integers(-1, 2), 2, 6)); q["w"] = int(max(3, q["w"] + rng.integers(-10, 11)))
        R_, pct, blk, sg = O.evaluate(D, q); jj[i] = pct[blk == 1].sum()
    joint_d[nm] = jj
    lock = base[nm]["lock"]
    dds = np.zeros(N_PERM)
    for i in range(N_PERM):
        eq = np.cumsum(rng.permutation(lock)); dds[i] = -(eq - np.maximum.accumulate(eq)).min()
    perm_d[nm] = dds
    print(f"  MC {nm} done {time.time()-t0:.0f}s")
np.savez(os.path.join(OUT, "v64_mc_arrays.npz"), **{f"exec_{k}": v for k, v in exec_d.items()},
         **{f"price_{k}_{s}": v for (k, s), v in price_d.items()}, **{f"joint_{k}": v for k, v in joint_d.items()},
         **{f"perm_{k}": v for k, v in perm_d.items()})
print("  arrays saved -- run v64_fig2_replot.py to redraw figure 2 without re-running this")

# =====================================================================================
# FIGURE 3 -- correlation matrices
# =====================================================================================
def daily(pct, sig, D, blk_mask):
    ix = pd.DatetimeIndex(D["ix"]); dd = (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy()
    return pd.Series(pct[blk_mask]).groupby(dd[sig[blk_mask]]).sum()

ABL = {nm: dict(p) for nm, p in PRESETS.items()}
p15 = PRESETS["15m preset"]
ABL["15m, gate OFF"] = dict(p15, k=0)
ABL["15m, k=2"] = dict(p15, k=2); ABL["15m, k=5"] = dict(p15, k=5)
ABL["15m, w=10"] = dict(p15, w=10); ABL["15m, w=40"] = dict(p15, w=40)
ABL["15m, no target"] = dict(p15, tp=0.0); ABL["15m, stop 2.0N"] = dict(p15, stop=2.0)
ABL["15m + CHOP<=45"] = dict(p15, use_chop=1, chop_thr=45.0)
ABL["15m + MA200 floor"] = dict(p15, use_ma=1, ma_thr=1.0)
ABL["15m + prior RTH high"] = dict(p15, psh=1)
p30 = PRESETS["incumbent 30m"]
ABL["30m, gate OFF"] = dict(p30, k=0)
ABL["30m, target 4 ATR"] = dict(p30, tp=4.0)      # the incumbent already has NO target, so `tp=0` would be an inert twin
cols = {}
for nm, p in ABL.items():
    D = Ds[p["tf"]]; R_, pct, blk, sg = O.evaluate(D, p)
    m = blk == 1
    if m.sum() < 15: continue
    cols[nm] = daily(pct, sg, D, m)
allday = sorted(set().union(*[set(s.index) for s in cols.values()]))
DF = pd.DataFrame({k: s.reindex(allday).fillna(0.0) for k, s in cols.items()})
CM = DF.corr(method="pearson")
fig, axs = plt.subplots(1, 2, figsize=(19, 8.5), gridspec_kw={"width_ratios": [1, 1.55]})
sub = CM.loc[list(PRESETS), list(PRESETS)]
im = axs[0].imshow(sub.values, cmap="RdBu_r", vmin=-1, vmax=1)
for i in range(3):
    for j in range(3):
        axs[0].text(j, i, f"{sub.values[i, j]:.3f}", ha="center", va="center", fontsize=13, color=FG, fontweight="bold" if i != j else "normal")
axs[0].set_xticks(range(3)); axs[0].set_xticklabels(list(PRESETS), rotation=20, fontsize=10)
axs[0].set_yticks(range(3)); axs[0].set_yticklabels(list(PRESETS), fontsize=10)
axs[0].set_title("A. The three shipped presets, daily locked returns\nthey are ONE strategy at three settings -- not three legs", fontsize=11)
order = list(CM.columns)
im2 = axs[1].imshow(CM.values, cmap="RdBu_r", vmin=-1, vmax=1)
for i in range(len(order)):
    for j in range(len(order)):
        axs[1].text(j, i, f"{CM.values[i, j]:.2f}", ha="center", va="center", fontsize=7, color=FG)
axs[1].set_xticks(range(len(order))); axs[1].set_xticklabels(order, rotation=90, fontsize=8)
axs[1].set_yticks(range(len(order))); axs[1].set_yticklabels(order, fontsize=8)
axs[1].set_title("B. Presets plus every ablation and filter variant -- what is a genuinely different bet and what is the same one renamed", fontsize=11)
cb = fig.colorbar(im2, ax=axs, fraction=0.014, pad=0.01); cb.set_label("Pearson correlation of daily returns")
fig.suptitle("V61 CVD -- correlation of daily returns on the locked block", fontsize=13, y=0.98)
fig.savefig(os.path.join(OUT, "v64_fig3_corr.png"), dpi=135, bbox_inches="tight"); plt.close(fig)
CM.to_csv(os.path.join(OUT, "v64_corr.csv"))
print("\ncorrelation of the three presets:"); print(sub.round(3).to_string())
print("\ngate ON vs gate OFF:  15m", round(CM.loc["15m preset", "15m, gate OFF"], 3), " 30m", round(CM.loc["incumbent 30m", "30m, gate OFF"], 3))
print(f"\nall three figures written to {OUT}   total {time.time()-t0:.0f}s")
