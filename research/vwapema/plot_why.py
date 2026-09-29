import os, sys
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTE, GRID = "#1c1f24", "#4a5058", "#8b929c", "#e6e9ed"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#c8ccd2", "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "figure.facecolor": "white"})
C = pd.read_csv("results/vwapema/why_corr.csv", index_col=0)
B = pd.read_csv("results/vwapema/why_beta.csv")
A = pd.read_csv("results/vwapema/why_control_risk.csv")
F = pd.read_csv("results/vwapema/why_folds.csv")
S = pd.read_csv("results/vwapema/why_selectivity.csv")
W = pd.read_csv("results/vwapema/preset_wfo.csv"); W["preset"] = W.preset.replace({"Sweep neighbourhood": "Sweep nbhd"})
M = S.merge(W[["preset", "folds", "gap"]], on="preset")

fig = plt.figure(figsize=(15.6, 11.6))
gs = fig.add_gridspec(3, 2, hspace=0.56, wspace=0.28, left=0.075, right=0.965, top=0.870, bottom=0.075)
fig.text(0.055, 0.958, "Why the Optuna presets 'hold' out of sample", fontsize=20, weight="bold", color=INK)
fig.text(0.055, 0.929, "Four candidate explanations tested: gold beta, sample size, selectivity, and a real edge. "
                       "Monthly R, 193 months, 2010-2026.", fontsize=10.3, color=INK2)
fig.text(0.055, 0.902, "Verdict: they hold because they trade more (fewer noisy folds) — and 11 of 12 preset-blocks LOSE to simply being long from the session open with the same stop.",
         fontsize=10.5, color=ORANGE, weight="bold")

# 1 correlation heatmap
ax = fig.add_subplot(gs[0, 0])
lab = [c.replace("As published", "published").replace("Optuna ", "Opt ").replace("Sweep ", "Swp ").replace(" (log ret)", "") for c in C.columns]
Mx = C.values
im = ax.imshow(Mx, cmap="RdBu_r", vmin=-1, vmax=1)
ax.set_xticks(range(len(lab))); ax.set_xticklabels(lab, rotation=42, ha="right", fontsize=8)
ax.set_yticks(range(len(lab))); ax.set_yticklabels(lab, fontsize=8)
for i in range(len(lab)):
    for j in range(len(lab)):
        ax.text(j, i, f"{Mx[i,j]:.2f}", ha="center", va="center", fontsize=7.4,
                color="white" if abs(Mx[i, j]) > 0.62 else INK)
ax.add_patch(plt.Rectangle((-0.5, len(lab)-1.5), len(lab), 1, fill=False, ec=ORANGE, lw=2.4))
ax.set_title("Monthly R correlation — the GOLD row is the one to read", fontsize=12, weight="bold", color=INK, loc="left", pad=8)

# 2 share of result from gold beta
ax = fig.add_subplot(gs[0, 1])
B2 = B.sort_values("pct_from_gold")
y = np.arange(len(B2))
ax.barh(y, B2.pct_from_gold, 0.6, color=[ORANGE if v > 50 else MUTE for v in B2.pct_from_gold], zorder=3)
for yy, v, r2 in zip(y, B2.pct_from_gold, B2.r2):
    ax.text(v + 2, yy, f"{v:.0f}%   (R² {r2:.3f})", va="center", fontsize=9, color=INK)
ax.set_yticks(y); ax.set_yticklabels([p.replace("As published", "published") for p in B2.preset], fontsize=9)
ax.set_xlabel("% of total R explained by the gold-beta term"); ax.set_xlim(0, 155)
ax.set_title("Every preset is a long-gold exposure", fontsize=12, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="x", alpha=.2, color=GRID); ax.set_axisbelow(True)

# 3 THE decisive panel
ax = fig.add_subplot(gs[1, :])
A2 = A[A.block == "LOCKED"].copy()
Ar = A[A.block == "research"].copy()
order = ["As published", "Optuna totR", "Optuna PF", "Optuna retDD", "Sweep top row", "Sweep nbhd"]
x = np.arange(len(order)); w = 0.2
for off, (df, lbl, col) in enumerate([(Ar, "research", 0), (A2, "locked", 1)]):
    pass
rule_r = [float(Ar[Ar.preset == p].rule_R.iloc[0]) for p in order]
rule_l = [float(A2[A2.preset == p].rule_R.iloc[0]) for p in order]
ctl_r = [float(Ar[Ar.preset == p].open_stopped_R.iloc[0]) for p in order]
ctl_l = [float(A2[A2.preset == p].open_stopped_R.iloc[0]) for p in order]
ax.bar(x - 1.5*w, rule_r, w, color=BLUE, label="rule, research", zorder=3)
ax.bar(x - 0.5*w, ctl_r, w, color="#9dc2ea", label="session-open + same stop, research", zorder=3)
ax.bar(x + 0.5*w, rule_l, w, color=AQUA, label="rule, locked", zorder=3)
ax.bar(x + 1.5*w, ctl_l, w, color="#a8ddc6", label="session-open + same stop, locked", zorder=3)
ax.axhline(0, color=INK2, lw=1)
for i, p in enumerate(order):
    if rule_l[i] > ctl_l[i]:
        ax.annotate("only\nwinner", xy=(i + 0.5*w, rule_l[i]), xytext=(i + 0.1, rule_l[i] + 0.30),
                    fontsize=8.5, color=ORANGE, weight="bold", ha="center",
                    arrowprops=dict(arrowstyle="->", color=ORANGE, lw=1.3))
ax.set_xticks(x); ax.set_xticklabels([p.replace("As published", "published") for p in order], fontsize=9.5)
ax.set_ylabel("R per trade")
ax.set_title("The decisive test: on the SAME days, just buy the session open and use the SAME stop — 11 of 12 blocks lose to it",
             fontsize=12.5, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=8.6, loc="upper left", ncol=2)
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)

# 4 sample size vs gap
ax = fig.add_subplot(gs[2, 0])
ax.scatter(M.folds, M.gap, s=95, color=[ORANGE if g >= 0.15 else AQUA for g in M.gap], zorder=4)
for _, r in M.iterrows():
    ax.annotate(r.preset.replace("As published", "published"), (r.folds, r.gap),
                textcoords="offset points", xytext=(7, 5), fontsize=8.4, color=INK2)
z = np.polyfit(M.folds, M.gap, 1); xs = np.linspace(4, 14, 20)
ax.plot(xs, z[0]*xs + z[1], color=MUTE, ls="--", lw=1.6)
ax.axhline(0, color=INK2, lw=1)
ax.set_xlabel("walk-forward folds the preset supports"); ax.set_ylabel("generalization gap")
ax.set_title(f"The gap is sample size: corr = {np.corrcoef(M.folds, M.gap)[0,1]:+.2f}",
             fontsize=12, weight="bold", color=INK, loc="left", pad=8)
ax.grid(alpha=.2, color=GRID)

# 5 fold result when gold rose vs fell
ax = fig.add_subplot(gs[2, 1])
F2 = F.copy(); F2["preset"] = F2.preset.replace({"As published": "published"})
y = np.arange(len(F2))[::-1]; w = 0.36
ax.barh(y + w/2, F2.mean_R_gold_up, w, color=AQUA, label="folds where gold ROSE", zorder=3)
ax.barh(y - w/2, F2.mean_R_gold_down, w, color=MUTE, label="folds where gold FELL", zorder=3)
ax.axvline(0, color=INK2, lw=1)
ax.set_yticks(y); ax.set_yticklabels(F2.preset, fontsize=9)
ax.set_xlabel("mean total R in the fold")
ax.set_title("Optuna totR earns 32x more when gold rises", fontsize=12, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=8.6, loc="lower right"); ax.grid(axis="x", alpha=.2, color=GRID); ax.set_axisbelow(True)

fig.text(0.055, 0.038, "The control enters at the session open on the SAME days and carries the SAME ATR stop, so it cannot be accused of taking more risk — its worst", fontsize=9.2, color=MUTE)
fig.text(0.055, 0.017, "trades match the rules' to two decimals. Only Optuna totR on the locked block beats it: 1 of 12.", fontsize=9.2, color=MUTE)
fig.savefig("results/vwapema/vwapema_why.png", dpi=150, facecolor="white")
print("wrote results/vwapema/vwapema_why.png")
