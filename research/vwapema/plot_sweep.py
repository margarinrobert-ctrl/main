import os, sys
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTE, GRID = "#1c1f24", "#4a5058", "#8b929c", "#e6e9ed"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#c8ccd2", "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "figure.facecolor": "white"})
G = pd.read_parquet("results/vwapema/sweep100k.parquet")
L = pd.read_csv("results/vwapema/sweep_locked.csv")

fig = plt.figure(figsize=(15.6, 11.2))
gs = fig.add_gridspec(3, 2, hspace=0.56, wspace=0.24, left=0.07, right=0.97, top=0.872, bottom=0.075)
fig.text(0.07, 0.958, "108,000-cell sweep — VWAP-EMA gold", fontsize=20.5, weight="bold", color=INK)
fig.text(0.07, 0.930, "Verified numba engine, cross-checked against an independent vectorbt build (ratio 0.9899, 8.6% conservative). "
                      "Research block only; two cells read once on locked.", fontsize=10.3, color=INK2)
fig.text(0.07, 0.906, "Verdict: 93.5% of the whole grid is profitable on the locked block, because the locked block is the gold rally. Neither chosen cell separates from zero.",
         fontsize=10.6, color=ORANGE, weight="bold")

# 1 research vs locked
ax = fig.add_subplot(gs[0, 0])
s = G.sample(30000, random_state=1)
ax.scatter(s.R_res, s.R_lock, s=3, alpha=.12, color=MUTE, linewidths=0, rasterized=True)
t100 = G.nlargest(100, "R_res")
ax.scatter(t100.R_res, t100.R_lock, s=14, color=ORANGE, label="top 100 on research", zorder=4)
ax.axhline(0, color=INK2, lw=1); ax.axvline(0, color=INK2, lw=1)
ax.set_xlabel("research R/trade"); ax.set_ylabel("locked R/trade")
ax.text(0.03, 0.96, f"corr +{np.corrcoef(G.R_res, G.R_lock.fillna(0))[0,1]:.2f}\n"
                    f"research 53.3% positive\nlocked 93.5% positive", transform=ax.transAxes,
        va="top", fontsize=9, color=INK2, bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=GRID))
ax.set_title("The grid", fontsize=12.5, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=8.5, loc="lower right"); ax.grid(alpha=.2, color=GRID)

# 2 locked-positive rate: selection vs chance
ax = fig.add_subplot(gs[0, 1])
buckets = ["whole grid", "top 1000", "top 100", "top 10"]
vals = [100*(G.R_lock > 0).mean(), 100*(G.nlargest(1000, "R_res").R_lock > 0).mean(),
        100*(G.nlargest(100, "R_res").R_lock > 0).mean(), 100*(G.nlargest(10, "R_res").R_lock > 0).mean()]
ax.bar(np.arange(4), vals, 0.6, color=[MUTE, BLUE, BLUE, BLUE], zorder=3)
ax.axhline(vals[0], color=ORANGE, ls="--", lw=1.6)
ax.text(3.4, vals[0] + 1.2, "chance", fontsize=9, color=ORANGE, ha="right", weight="bold")
for i, v in enumerate(vals):
    ax.text(i, v + 1.2, f"{v:.0f}%", ha="center", fontsize=10, weight="bold", color=INK)
ax.set_xticks(range(4)); ax.set_xticklabels(buckets, fontsize=9.5)
ax.set_ylabel("% locked-positive"); ax.set_ylim(0, 112)
ax.set_title("Selecting on research buys 6 points over chance", fontsize=12.5, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)

# 3 marginals
ax = fig.add_subplot(gs[1, :])
axes = ["ema_slow", "ema_pull", "wick", "vol", "range", "stop", "tgt"]
xoff = 0; ticks, labs = [], []
for a in axes:
    m = G.groupby(a).R_res.mean()
    keys = list(m.index)
    if a == "tgt":
        keys = [2.0, 3.0, 4.0, 6.0, 0.0]; m = m.reindex(keys)
    xs = np.arange(len(keys)) + xoff
    ax.plot(xs, m.values, marker="o", lw=2, ms=5, color=BLUE)
    for x, k in zip(xs, keys):
        ticks.append(x); labs.append("none" if (a == "tgt" and k == 0) else f"{k:g}")
    ax.axvspan(xoff - 0.5, xoff + len(keys) - 0.5, color=GRID, alpha=.25 if axes.index(a) % 2 else .06, lw=0)
    ax.text(xoff + (len(keys)-1)/2, 0.088, a, ha="center", fontsize=9.5, weight="bold", color=INK2)
    xoff += len(keys) + 1
ax.axhline(0, color=INK2, lw=1)
ax.set_xticks(ticks); ax.set_xticklabels(labs, fontsize=8)
ax.set_ylabel("marginal mean research R/trade"); ax.set_ylim(-0.10, 0.105)
ax.set_title("Marginal average per axis — the volume threshold dominates, the stop wants to be WIDER",
             fontsize=12.5, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="y", alpha=.2, color=GRID)

# 4 the two picks
ax = fig.add_subplot(gs[2, 0])
names = ["TOP ROW", "NEIGHBOURHOOD-BEST"]
x = np.arange(2); w = 0.26
res = [L[(L.cell == n) & (L.block == "research")].R.iloc[0] for n in names]
loc_ = [L[(L.cell == n) & (L.block == "LOCKED")].R.iloc[0] for n in names]
ctl = [L[(L.cell == n) & (L.block == "LOCKED")].ctl_R.iloc[0] for n in names]
ax.bar(x - w, res, w, color=BLUE, label="research", zorder=3)
ax.bar(x, loc_, w, color=AQUA, label="locked", zorder=3)
ax.bar(x + w, ctl, w, color=MUTE, label="random entry, locked", zorder=3)
ax.axhline(0, color=INK2, lw=1)
for i, n in enumerate(names):
    bp = L[(L.cell == n) & (L.block == "LOCKED")].boot_p.iloc[0]
    ax.text(i, max(res[i], loc_[i]) + 0.022, f"bootstrap p {bp:.3f}", ha="center", fontsize=9,
            weight="bold", color=ORANGE)
ax.set_xticks(x); ax.set_xticklabels(["top row", "neighbourhood-best"], fontsize=9.5)
ax.set_ylabel("R per trade"); ax.set_ylim(-0.45, 0.55)
ax.set_title("Both cells, read once", fontsize=12.5, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=8.5, loc="lower left"); ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)

# 5 concentration
ax = fig.add_subplot(gs[2, 1])
sh = [L[(L.cell == n) & (L.block == "LOCKED")].share_2025.iloc[0] for n in names]
ax.barh([1, 0], sh, 0.5, color=ORANGE, zorder=3)
for i, v in zip([1, 0], sh):
    ax.text(v + 1.5, i, f"{v:.0f}%", va="center", fontsize=11, weight="bold", color=INK)
ax.set_yticks([1, 0]); ax.set_yticklabels(["top row", "neighbourhood-best"], fontsize=9.5)
ax.set_xlabel("% of the locked result from 2025-26"); ax.set_xlim(0, 100)
ax.set_title("Where the locked money comes from", fontsize=12.5, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="x", alpha=.2, color=GRID); ax.set_axisbelow(True)

fig.text(0.07, 0.026, "Both chosen cells sit at the EXTREME rung of two axes (volume 1.8 = swept maximum, stop 0.25 = swept minimum) — and the stop marginal says wider is better, "
                      "so the top of the grid contradicts its own average.", fontsize=9.3, color=MUTE)
fig.savefig("results/vwapema/vwapema_sweep.png", dpi=150, facecolor="white")
print("wrote results/vwapema/vwapema_sweep.png")
