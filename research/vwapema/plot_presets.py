import os, sys, json
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTE, GRID = "#1c1f24", "#4a5058", "#8b929c", "#e6e9ed"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#c8ccd2", "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "figure.facecolor": "white"})
R = pd.read_csv("results/vwapema/preset_ranks.csv")
W = pd.read_csv("results/vwapema/preset_wfo.csv")
O = pd.read_csv("results/vwapema/preset_verdict.csv")
P = json.load(open("results/vwapema/preset_pbo.json"))
L = pd.read_csv("results/vwapema/opt_locked.csv") if os.path.exists("results/vwapema/opt_locked.csv") else None
order = list(O.sort_values("wf_gap", ascending=False).preset)
col = {p: (ORANGE if O.set_index("preset").loc[p, "wf_gap"] >= 0.15 else
           (MUTE if p == "As published" else AQUA)) for p in order}

fig = plt.figure(figsize=(15.4, 10.6))
gs = fig.add_gridspec(2, 2, hspace=0.50, wspace=0.26, left=0.145, right=0.97, top=0.855, bottom=0.105)
fig.text(0.055, 0.955, "Which presets are overfitted — VWAP-EMA gold", fontsize=20, weight="bold", color=INK)
fig.text(0.055, 0.925, "Five of the six presets were fitted on this data by my own Optuna search and 108,000-cell sweep. The published one never was. "
                       "Rolling walk-forward: 36m train / 12m test, nothing re-selected.", fontsize=10.2, color=INK2)
fig.text(0.055, 0.898, "Verdict: the two SWEEP cells are overfitted. The three Optuna cells hold. The published rule was never fitted — and none of them separates from zero.",
         fontsize=10.6, color=ORANGE, weight="bold")

# 1 walk-forward IS vs OOS
ax = fig.add_subplot(gs[0, 0])
y = np.arange(len(order))[::-1]
wi = [float(W[W.preset == p].IS.iloc[0]) for p in order]
wo = [float(W[W.preset == p].OOS.iloc[0]) for p in order]
ax.barh(y + 0.19, wi, 0.36, color=MUTE, label="in-sample (36m)", zorder=3)
ax.barh(y - 0.19, wo, 0.36, color=[col[p] for p in order], label="out-of-sample (next 12m)", zorder=3)
ax.axvline(0, color=INK2, lw=1)
ax.set_yticks(y); ax.set_yticklabels(order, fontsize=9)
ax.set_xlabel("R per trade")
ax.set_title("Rolling walk-forward, nothing re-selected", fontsize=12.5, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=8.5, loc="lower right"); ax.grid(axis="x", alpha=.2, color=GRID); ax.set_axisbelow(True)

# 2 the gap
ax = fig.add_subplot(gs[0, 1])
g = [float(O[O.preset == p].wf_gap.iloc[0]) for p in order]
ax.barh(y, g, 0.6, color=[col[p] for p in order], zorder=3)
ax.axvline(0, color=INK2, lw=1)
ax.axvline(0.15, color=ORANGE, ls="--", lw=1.5)
ax.text(0.157, y[0] + 0.35, "overfit threshold", fontsize=8.5, color=ORANGE, weight="bold")
for yy, v, p in zip(y, g, order):
    f = int(W[W.preset == p].folds.iloc[0])
    ax.text(max(v, 0.0) + 0.012, yy, f"{v:+.3f}  ({f} folds)", va="center",
            ha="left", fontsize=8.6, color=INK)
ax.set_yticks(y); ax.set_yticklabels(order, fontsize=9)
ax.set_xlabel("in-sample minus out-of-sample R"); ax.set_xlim(-0.09, 0.40)
ax.set_title("The generalization gap", fontsize=12.5, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="x", alpha=.2, color=GRID); ax.set_axisbelow(True)

# 3 rank in its own pool
ax = fig.add_subplot(gs[1, 0])
ir = [float(R[R.preset == p].IS_rank.iloc[0]) for p in order]
p90 = [float(R[R.preset == p].p90_drop.iloc[0]) for p in order]
ax.barh(y, ir, 0.6, color=[col[p] for p in order], zorder=3)
ax.axvline(0.5, color=INK2, ls="--", lw=1.5)
ax.text(0.51, y[-1] - 0.55, "median cell", fontsize=8.5, color=INK2)
for yy, v, d in zip(y, ir, p90):
    ax.text(v + 0.012, yy, f"{v:.3f}   p90 rank swing {d:.2f}", va="center", fontsize=8.5, color=INK)
ax.set_yticks(y); ax.set_yticklabels(order, fontsize=9)
ax.set_xlabel("median in-sample rank among 1,199 grid cells"); ax.set_xlim(0, 1.42)
ax.set_title("Where each sits in its own parameter pool", fontsize=12.5, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="x", alpha=.2, color=GRID); ax.set_axisbelow(True)

# 4 verdict text panel
ax = fig.add_subplot(gs[1, 1]); ax.axis("off")
ax.text(0, 1.0, "Per-preset verdict", fontsize=12.5, weight="bold", color=INK, va="top")
yy = 0.88
for p in order:
    r = O[O.preset == p].iloc[0]
    w = W[W.preset == p].iloc[0]
    c = col[p]
    ax.text(0, yy, p, fontsize=10.5, weight="bold", color=c, va="top")
    ax.text(0, yy - 0.052, r.verdict, fontsize=9.2, color=INK2, va="top")
    ax.text(0, yy - 0.098, f"IS {w.IS:+.3f} -> OOS {w.OOS:+.3f} over {int(w.folds)} folds, "
                           f"{w.OOS_pos} positive", fontsize=8.6, color=MUTE, va="top")
    yy -= 0.148
ax.text(0, -0.10, f"PBO over the grid alone: {P['PBO_grid_only']:.3f}   |   with the fitted presets in the pool: {P['PBO_with_presets']:.3f}",
        fontsize=9, color=ORANGE, weight="bold", va="bottom")

fig.text(0.055, 0.042, "Method note: symmetric CSCV cannot measure a FIXED cell's rank drop — every split's complement is also a split, so both the median rank", fontsize=9.2, color=MUTE)
fig.text(0.055, 0.020, "difference and the median pairwise drop are identically zero by construction. PBO works because its subject, the argmax, changes with the split.", fontsize=9.2, color=MUTE)
fig.savefig("results/vwapema/vwapema_presets.png", dpi=150, facecolor="white")
print("wrote results/vwapema/vwapema_presets.png")
