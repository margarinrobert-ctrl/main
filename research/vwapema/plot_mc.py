import os, sys, json
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTE, GRID = "#1c1f24", "#4a5058", "#8b929c", "#e6e9ed"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#c8ccd2", "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "figure.facecolor": "white"})
Z = np.load("results/vwapema/mc_full.npz", allow_pickle=True)
meta = json.loads(str(Z["meta"]))
NAMES = ["as published", "totR", "pf", "retdd"]
LAB = {"as published": "as published", "totR": "Optuna: total R", "pf": "Optuna: PF", "retdd": "Optuna: ret/DD"}
COL = {"as published": MUTE, "totR": BLUE, "pf": AQUA, "retdd": ORANGE}

fig = plt.figure(figsize=(15.6, 11.4))
gs = fig.add_gridspec(3, 2, hspace=0.52, wspace=0.22, left=0.07, right=0.97, top=0.878, bottom=0.075)
fig.text(0.07, 0.960, "Monte Carlo — VWAP-EMA gold, locked block", fontsize=20.5, weight="bold", color=INK)
fig.text(0.07, 0.932, "4,000 day-block bootstraps and 4,000 permutations per configuration, plus 120 parameter draws and 60 price-jitter draws "
                      "with every indicator recomputed.", fontsize=10.4, color=INK2)
fig.text(0.07, 0.908, "Verdict: every bootstrap distribution straddles zero. The strategies are robust to noise and not distinguishable from no edge.",
         fontsize=10.8, color=ORANGE, weight="bold")

# 1. bootstrap of the mean
ax = fig.add_subplot(gs[0, 0])
for n in NAMES:
    bs = Z[f"{n}__bs"]
    ax.hist(bs, bins=70, histtype="step", lw=2, color=COL[n], label=f"{LAB[n]}  P(≤0) {float((bs<=0).mean()):.3f}", density=True)
ax.axvline(0, color=INK, lw=1.6)
ax.set_xlabel("bootstrapped mean R per trade"); ax.set_ylabel("density")
ax.set_title("The edge: every distribution crosses zero", fontsize=12.5, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=8.6, loc="upper right"); ax.grid(alpha=.2, color=GRID)

# 2. permutation drawdown
ax = fig.add_subplot(gs[0, 1])
for n in NAMES:
    dds = Z[f"{n}__dds"]
    ax.hist(dds, bins=70, histtype="step", lw=2, color=COL[n], density=True)
    ax.axvline(meta[n]["real_dd"], color=COL[n], ls="--", lw=1.5)
ax.set_xlabel("max drawdown, R (permuted trade order)"); ax.set_ylabel("density")
ax.set_title("The path: dashed = realised, and it sits high", fontsize=12.5, weight="bold", color=INK, loc="left", pad=8)
txt = "\n".join(f"{LAB[n]}: real {meta[n]['real_dd']:.1f}  p99 {np.percentile(Z[f'{n}__dds'],99):.1f}" for n in NAMES)
ax.text(0.97, 0.95, txt, transform=ax.transAxes, ha="right", va="top", fontsize=8.4, color=INK2,
        bbox=dict(boxstyle="round,pad=0.35", fc="white", ec=GRID))
ax.grid(alpha=.2, color=GRID)

# 3+4. equity fans for the two most-traded
for k, n in enumerate(["as published", "totR"]):
    ax = fig.add_subplot(gs[1, k])
    P = Z[f"{n}__paths"]; rp = Z[f"{n}__real_path"]
    x = np.arange(P.shape[1])
    for q, a in ((5, .18), (25, .30)):
        ax.fill_between(x, np.percentile(P, q, axis=0), np.percentile(P, 100 - q, axis=0),
                        color=COL[n], alpha=a, lw=0)
    ax.plot(x, np.percentile(P, 50, axis=0), color=COL[n], lw=1.6, ls=":", label="bootstrap median")
    ax.plot(np.arange(len(rp)), rp, color=INK, lw=2.2, label="realised")
    ax.axhline(0, color=INK2, lw=1)
    ax.set_xlabel("trade"); ax.set_ylabel("cumulative R")
    ax.set_title(f"{LAB[n]} — bootstrap equity fan (5–95%)", fontsize=12, weight="bold", color=INK, loc="left", pad=8)
    ax.legend(frameon=False, fontsize=8.8, loc="upper left"); ax.grid(alpha=.2, color=GRID)
    lo = np.percentile(P[:, -1], 5)
    ax.text(0.97, 0.05, f"5th pct endpoint {lo:+.1f} R", transform=ax.transAxes, ha="right", fontsize=9,
            color=ORANGE if lo < 0 else AQUA, weight="bold")

# 5. parameter perturbation
ax = fig.add_subplot(gs[2, 0])
data = [Z[f"{n}__par"] for n in NAMES]
bp = ax.boxplot(data, vert=True, patch_artist=True, widths=.55, showfliers=False)
for patch, n in zip(bp["boxes"], NAMES):
    patch.set_facecolor(COL[n]); patch.set_alpha(.55); patch.set_edgecolor(COL[n])
for med in bp["medians"]:
    med.set_color(INK); med.set_linewidth(1.6)
for i, n in enumerate(NAMES):
    ax.scatter([i + 1], [meta[n]["real_mean"]], marker="D", s=42, color=INK, zorder=5)
ax.axhline(0, color=INK2, lw=1)
ax.set_xticks(range(1, 5)); ax.set_xticklabels([LAB[n] for n in NAMES], rotation=15, ha="right", fontsize=9)
ax.set_ylabel("mean R per trade")
ax.set_title("Parameters jittered ±10% (diamond = as chosen)", fontsize=12, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="y", alpha=.2, color=GRID)

# 6. price jitter
ax = fig.add_subplot(gs[2, 1])
data = [Z[f"{n}__pj"] for n in NAMES]
bp = ax.boxplot(data, vert=True, patch_artist=True, widths=.55, showfliers=True)
for patch, n in zip(bp["boxes"], NAMES):
    patch.set_facecolor(COL[n]); patch.set_alpha(.55); patch.set_edgecolor(COL[n])
for med in bp["medians"]:
    med.set_color(INK); med.set_linewidth(1.6)
for i, n in enumerate(NAMES):
    ax.scatter([i + 1], [meta[n]["real_mean"]], marker="D", s=42, color=INK, zorder=5)
    ax.text(i + 1, ax.get_ylim()[0], f"sign kept\n{100*float((Z[f'{n}__pj']>0).mean()):.0f}%",
            ha="center", va="bottom", fontsize=8.2, color=INK2)
ax.axhline(0, color=INK2, lw=1)
ax.set_xticks(range(1, 5)); ax.set_xticklabels([LAB[n] for n in NAMES], rotation=15, ha="right", fontsize=9)
ax.set_ylabel("mean R per trade")
ax.set_title("Price jittered, every indicator recomputed", fontsize=12, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="y", alpha=.2, color=GRID)

fig.text(0.07, 0.028, "A perturbation prices execution and data noise on the trades you already selected — it can never price the selection itself. "
                      "The bootstrap is the one that can, and it says P(mean ≤ 0) = 0.057 to 0.179.", fontsize=9.4, color=MUTE)
fig.savefig("results/vwapema/vwapema_mc.png", dpi=150, facecolor="white")
print("wrote results/vwapema/vwapema_mc.png")
