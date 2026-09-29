import os, sys, json
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTE, GRID = "#1c1f24", "#4a5058", "#8b929c", "#e6e9ed"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#c8ccd2", "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "figure.facecolor": "white"})
Z = np.load("results/vwapema/pbo_arrays.npz"); J = json.load(open("results/vwapema/pbo.json"))
Wf = pd.read_csv("results/vwapema/wfo_published.csv"); WF = pd.read_csv("results/vwapema/wfo_reselect.csv")

fig = plt.figure(figsize=(15.4, 11.0))
gs = fig.add_gridspec(3, 2, hspace=0.56, wspace=0.24, left=0.07, right=0.97, top=0.872, bottom=0.075)
fig.text(0.07, 0.958, "Walk-forward and the overfitting test — VWAP-EMA gold", fontsize=20, weight="bold", color=INK)
fig.text(0.07, 0.930, "CSCV over 1,199 sampled configurations x 193 months, 16 blocks, all 12,870 symmetric splits. "
                      "Rolling walk-forward is 36 months train / 12 test.", fontsize=10.3, color=INK2)
fig.text(0.07, 0.906, "Verdict: the published rule is NOT overfitted — it was never fitted. The SEARCH is, severely: PBO 0.561, and in-sample rank anti-predicts out-of-sample.",
         fontsize=10.6, color=ORANGE, weight="bold")

# 1 PBO logit distribution
ax = fig.add_subplot(gs[0, 0])
lam = Z["lam"]
ax.hist(lam[lam <= 0], bins=60, color=ORANGE, alpha=.85, label=f"below OOS median ({100*J['PBO']:.1f}%)")
ax.hist(lam[lam > 0], bins=60, color=AQUA, alpha=.85, label=f"above ({100*(1-J['PBO']):.1f}%)")
ax.axvline(0, color=INK, lw=2)
ax.set_xlabel("logit of the IS winner's OOS rank"); ax.set_ylabel("splits")
ax.set_title(f"PBO = {J['PBO']:.3f}", fontsize=13, weight="bold", color=INK, loc="left", pad=8)
ax.text(0.03, 0.95, "PBO > 0.5 means picking the\nin-sample best is worse\nthan picking at random",
        transform=ax.transAxes, va="top", fontsize=9, color=ORANGE, weight="bold",
        bbox=dict(boxstyle="round,pad=0.35", fc="white", ec=ORANGE, lw=1.1))
ax.legend(frameon=False, fontsize=8.5, loc="upper right"); ax.grid(alpha=.2, color=GRID)

# 2 IS vs OOS of the IS winner
ax = fig.add_subplot(gs[0, 1])
d_is, d_os = Z["d_is"], Z["d_os"]
ax.scatter(d_is, d_os, s=9, alpha=.30, color=BLUE, linewidths=0)
xs = np.linspace(d_is.min(), d_is.max(), 50)
sl, ic = np.polyfit(d_is, d_os, 1)
ax.plot(xs, sl*xs + ic, color=ORANGE, lw=2.4, label=f"slope {sl:+.2f}")
ax.axhline(0, color=INK2, lw=1)
ax.set_xlabel("in-sample statistic of the winner"); ax.set_ylabel("its out-of-sample statistic")
ax.set_title("In-sample performance anti-predicts out-of-sample", fontsize=13, weight="bold", color=INK, loc="left", pad=8)
ax.text(0.97, 0.05, f"IS mean {d_is.mean():+.3f}  ->  OOS {d_os.mean():+.3f}\n"
                    f"{100*(d_os>0).mean():.0f}% of winners OOS-positive",
        transform=ax.transAxes, ha="right", fontsize=9, color=INK2,
        bbox=dict(boxstyle="round,pad=0.35", fc="white", ec=GRID))
ax.legend(frameon=False, fontsize=9, loc="upper right"); ax.grid(alpha=.2, color=GRID)

# 3 rolling walk-forward of the published rule
ax = fig.add_subplot(gs[1, :])
x = np.arange(len(Wf)); w = 0.38
ax.bar(x - w/2, Wf.IS_R, w, color=MUTE, label="in-sample (36m train)", zorder=3)
ax.bar(x + w/2, Wf.OOS_R, w, color=[AQUA if v > 0 else ORANGE for v in Wf.OOS_R],
       label="out-of-sample (next 12m)", zorder=3)
ax.axhline(0, color=INK2, lw=1)
ax.set_xticks(x); ax.set_xticklabels([t.split("..")[0][:4] for t in Wf.test], fontsize=9)
ax.set_ylabel("R per trade"); ax.set_xlabel("out-of-sample year")
ax.set_title("The published rule rolled forward with nothing re-selected — "
             f"IS +{Wf.IS_R.mean():.4f} vs OOS {Wf.OOS_R.mean():+.4f}, corr {np.corrcoef(Wf.IS_R, Wf.OOS_R)[0,1]:+.2f}",
             fontsize=12.5, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=9, loc="lower left"); ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)

# 4 re-selecting walk-forward
ax = fig.add_subplot(gs[2, 0])
x = np.arange(len(WF)); w = 0.27
ax.bar(x - w, WF.chosen, w, color=BLUE, label="re-optimised each fold", zorder=3)
ax.bar(x, WF.random, w, color=MUTE, label="a RANDOM cell", zorder=3)
ax.bar(x + w, WF.published, w, color=AQUA, label="the published constants", zorder=3)
ax.axhline(0, color=INK2, lw=1)
ax.set_xticks(x); ax.set_xticklabels([t.split("..")[0][:4] for t in WF.test], fontsize=8, rotation=45)
ax.set_ylabel("total R in the fold")
ax.set_title("Re-selecting is the WORST of the three arms", fontsize=12.5, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=8.5, loc="lower left"); ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)

# 5 totals
ax = fig.add_subplot(gs[2, 1])
tot = [WF.chosen.sum(), WF.random.sum(), WF.published.sum()]
pos = [int((WF.chosen > 0).sum()), int((WF.random > 0).sum()), int((WF.published > 0).sum())]
cols = [BLUE, MUTE, AQUA]
ax.barh([2, 1, 0], tot, 0.55, color=cols, zorder=3)
for y, v, p in zip([2, 1, 0], tot, pos):
    ax.text(v + 0.7, y, f"{v:+.1f} R   ({p}/13 folds positive)", va="center", fontsize=10, weight="bold", color=INK)
ax.set_yticks([2, 1, 0]); ax.set_yticklabels(["re-optimised", "random cell", "published"], fontsize=10)
ax.axvline(0, color=INK2, lw=1); ax.set_xlim(0, 40)
ax.set_xlabel("total R across all 13 out-of-sample folds")
ax.set_title("A random cell beats the optimiser 4.9x", fontsize=12.5, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="x", alpha=.2, color=GRID); ax.set_axisbelow(True)

fig.text(0.07, 0.026, "The published rule's own median in-sample rank across the 12,870 splits is 0.444 — a below-median cell in its own grid, which is what a rule "
                      "that was never fitted to this data should look like.", fontsize=9.4, color=MUTE)
fig.savefig("results/vwapema/vwapema_pbo.png", dpi=150, facecolor="white")
print("wrote results/vwapema/vwapema_pbo.png")
