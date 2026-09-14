import os, sys, json
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTE, GRID = "#1c1f24", "#4a5058", "#8b929c", "#e6e9ed"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#c8ccd2", "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "figure.facecolor": "white"})
T = pd.read_parquet("results/vwapema/optuna_trials.parquet"); ok = T[T.n_res >= 120]
L = pd.read_csv("results/vwapema/opt_locked.csv"); MC = pd.read_csv("results/vwapema/opt_mc.csv")
C = pd.read_csv("results/vwapema/concentration.csv"); W = pd.read_csv("results/vwapema/walkforward.csv")
CM = pd.read_csv("results/vwapema/corr_params.csv", index_col=0)
DRc = pd.read_csv("results/vwapema/corr_finalists.csv", index_col=0)

fig = plt.figure(figsize=(15.8, 11.8))
gs = fig.add_gridspec(3, 3, hspace=0.60, wspace=0.34, left=0.065, right=0.975, top=0.875, bottom=0.075)
fig.text(0.065, 0.960, "VWAP-EMA gold: 3,600 Optuna trials, IS/OOS, Monte Carlo", fontsize=20, weight="bold", color=INK)
fig.text(0.065, 0.932, "XAU_ISO_15m, 15-minute bars, 2010-01-03 to 2026-01-30. Search on the research block only (to 2020-05-25); "
                       "finalists read once on locked.", fontsize=10.4, color=INK2)
fig.text(0.065, 0.909, "Verdict: no finalist separates from zero on the locked block, the deflated Sharpe is 0.000 at 3,660 trials, and 94% of the best one's result is the 2025 gold rally.",
         fontsize=10.6, color=ORANGE, weight="bold")

# 1 research vs locked scatter
ax = fig.add_subplot(gs[0, 0])
f = ok[np.isfinite(ok.totR_lock)]
ax.scatter(f.totR_res, f.totR_lock, s=5, alpha=.20, color=MUTE, linewidths=0, rasterized=True)
top = f.sort_values("totR_res", ascending=False).head(len(f)//100)
ax.scatter(top.totR_res, top.totR_lock, s=16, color=ORANGE, label="top 1% on research", zorder=4)
ax.axhline(0, color=INK2, lw=1); ax.axvline(0, color=INK2, lw=1)
ax.set_xlabel("research total R"); ax.set_ylabel("locked total R")
cc = np.corrcoef(f.totR_res, f.totR_lock)[0, 1]
ax.text(0.03, 0.96, f"{len(f):,} trials\ncorr {cc:+.2f}", transform=ax.transAxes, va="top", fontsize=9,
        color=INK2, bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=GRID))
ax.set_title("The search population", fontsize=12, weight="bold", color=INK, loc="left", pad=7)
ax.legend(frameon=False, fontsize=8, loc="lower right"); ax.grid(alpha=.22, color=GRID)

# 2 parameter -> performance correlation
ax = fig.add_subplot(gs[0, 1])
v = CM["R_res"].drop(index=[i for i in ["R_res", "pf_res", "totR_res", "n_res"] if i in CM.index],
                     errors="ignore").sort_values()
cols = [ORANGE if abs(x) > 0.25 else MUTE for x in v]
ax.barh(np.arange(len(v)), v.values, color=cols, zorder=3)
ax.set_yticks(np.arange(len(v))); ax.set_yticklabels(v.index, fontsize=8.5)
ax.axvline(0, color=INK2, lw=1)
ax.set_xlabel("Spearman with research R/trade")
ax.set_title("Only two parameters matter", fontsize=12, weight="bold", color=INK, loc="left", pad=7)
ax.grid(axis="x", alpha=.22, color=GRID); ax.set_axisbelow(True)

# 3 finalist daily correlation heatmap
ax = fig.add_subplot(gs[0, 2])
M = DRc.values
im = ax.imshow(M, cmap="RdBu_r", vmin=-1, vmax=1)
lbl = [c.replace("as published", "published") for c in DRc.columns]
ax.set_xticks(range(len(lbl))); ax.set_xticklabels(lbl, rotation=35, ha="right", fontsize=8.5)
ax.set_yticks(range(len(lbl))); ax.set_yticklabels(lbl, fontsize=8.5)
for i in range(len(lbl)):
    for j in range(len(lbl)):
        ax.text(j, i, f"{M[i,j]:.2f}", ha="center", va="center", fontsize=8.5,
                color="white" if abs(M[i, j]) > 0.6 else INK)
ax.set_title("Finalists' daily R, locked", fontsize=12, weight="bold", color=INK, loc="left", pad=7)

# 4 the locked read
ax = fig.add_subplot(gs[1, :2])
names = ["as published", "totR", "pf", "retdd"]
x = np.arange(len(names)); w = 0.26
res = [L[(L.finalist == n) & (L.block == "research")].R.iloc[0] for n in names]
loc_ = [L[(L.finalist == n) & (L.block == "LOCKED")].R.iloc[0] for n in names]
ctl = [L[(L.finalist == n) & (L.block == "LOCKED")].ctl_R.iloc[0] for n in names]
ax.bar(x - w, res, w, color=BLUE, label="research (chose)", zorder=3)
ax.bar(x, loc_, w, color=AQUA, label="locked", zorder=3)
ax.bar(x + w, ctl, w, color=MUTE, label="random entry, locked", zorder=3)
ax.axhline(0, color=INK2, lw=1)
for i, n in enumerate(names):
    p = MC[MC.finalist == n]
    if len(p):
        ax.text(i, max(loc_[i], res[i]) + 0.018, f"bootstrap p {float(p.p_mean_le_0.iloc[0]):.3f}", ha="center",
                fontsize=8.8, weight="bold", color=ORANGE if float(p.p_mean_le_0.iloc[0]) > 0.05 else AQUA)
ax.set_xticks(x); ax.set_xticklabels(["as published", "Optuna: total R", "Optuna: PF", "Optuna: ret/DD"], fontsize=9.5)
ax.set_ylabel("R per trade")
ax.set_title("Every finalist beats a control that loses money, and none separates from zero",
             fontsize=12.5, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=9, loc="lower left"); ax.grid(axis="y", alpha=.22, color=GRID); ax.set_axisbelow(True)

# 5 Monte Carlo drawdown
ax = fig.add_subplot(gs[1, 2])
y = np.arange(len(MC))[::-1]
ax.barh(y, MC.real_dd, 0.34, color=BLUE, label="realised", zorder=3)
ax.barh(y - 0.36, MC.mc_p99_dd, 0.34, color=ORANGE, label="MC p99", zorder=3)
ax.set_yticks(y - 0.18); ax.set_yticklabels([n.replace("as published", "published") for n in MC.finalist], fontsize=8.5)
ax.set_xlabel("drawdown, R (locked)")
ax.set_title("Size for the p99, not the backtest", fontsize=12, weight="bold", color=INK, loc="left", pad=7)
ax.legend(frameon=False, fontsize=8.5, loc="lower right"); ax.grid(axis="x", alpha=.22, color=GRID); ax.set_axisbelow(True)

# 6 concentration
ax = fig.add_subplot(gs[2, 0])
nm = [n.replace("as published", "published") for n in C.finalist]
x = np.arange(len(nm))
ax.bar(x, C.share_2025_26, 0.6, color=[ORANGE if v > 50 else MUTE for v in C.share_2025_26], zorder=3)
for i, v in enumerate(C.share_2025_26):
    ax.text(i, v + 2, f"{v:.0f}%", ha="center", fontsize=9.5, weight="bold", color=INK)
ax.set_xticks(x); ax.set_xticklabels(nm, rotation=20, ha="right", fontsize=8.5)
ax.set_ylabel("% of locked result"); ax.set_ylim(0, 112)
ax.set_title("Share from the 2025-26 gold rally", fontsize=12, weight="bold", color=INK, loc="left", pad=7)
ax.grid(axis="y", alpha=.22, color=GRID); ax.set_axisbelow(True)

# 7 walk-forward
ax = fig.add_subplot(gs[2, 1:])
x = np.arange(len(W)); w = 0.27
ax.bar(x - w, W.chosen, w, color=BLUE, label="re-optimised each fold", zorder=3)
ax.bar(x, W.random, w, color=MUTE, label="a RANDOM cell", zorder=3)
ax.bar(x + w, W.published, w, color=AQUA, label="the paper's constants", zorder=3)
ax.axhline(0, color=INK2, lw=1)
ax.set_xticks(x); ax.set_xticklabels(W.fold, fontsize=8.5)
ax.set_ylabel("R per trade"); ax.set_xlabel("out-of-fold year")
ax.annotate("4 trades", xy=(len(W)-1-w, float(W.chosen.iloc[-1])), xytext=(len(W)-3.2, 1.0),
            fontsize=9, color=ORANGE, weight="bold", arrowprops=dict(arrowstyle="->", color=ORANGE, lw=1.3))
ax.set_title("Walk-forward: strip the four-trade 2025 fold and a random cell wins (+0.105 vs +0.059)",
             fontsize=12, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=9, loc="lower left"); ax.grid(axis="y", alpha=.22, color=GRID); ax.set_axisbelow(True)

fig.text(0.065, 0.036, "fANOVA puts 0.85-0.90 of every objective on the volume multiple -- the one component whose research gradient (Spearman +1.00)", fontsize=9.4, color=MUTE)
fig.text(0.065, 0.016, "inverts on the locked block (-0.90). Deflated Sharpe 0.000 for all four finalists at N = 3,660 counted trials.", fontsize=9.4, color=MUTE)
fig.savefig("results/vwapema/vwapema_optuna.png", dpi=150, facecolor="white")
print("wrote results/vwapema/vwapema_optuna.png")
