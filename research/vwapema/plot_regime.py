import os, sys
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTE, GRID = "#1c1f24", "#4a5058", "#8b929c", "#e6e9ed"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#c8ccd2", "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "figure.facecolor": "white"})
F = pd.read_csv("results/vwapema/regime_filter.csv")
D = pd.read_csv("results/vwapema/regime_descriptive.csv")
ORD = ["As published", "Optuna totR", "Optuna PF", "Optuna retDD", "Sweep top row", "Sweep nbhd"]
SH = {p: p.replace("As published", "published").replace("Optuna ", "Opt ").replace("Sweep ", "Swp ") for p in ORD}

fig = plt.figure(figsize=(15.6, 11.2))
gs = fig.add_gridspec(3, 2, hspace=0.60, wspace=0.24, left=0.085, right=0.965, top=0.868, bottom=0.078)
fig.text(0.06, 0.958, "Long vs short, bull vs bear — VWAP-EMA gold", fontsize=20, weight="bold", color=INK)
fig.text(0.06, 0.929, "Regime is causal: gold's daily close against its own 200-day EMA, lagged one session. 63.4% of session bars are bull "
                      "(76.2% of the locked block). Restricted and RE-SIMULATED, not split after the fact.", fontsize=10.2, color=INK2)
fig.text(0.06, 0.901, "Verdict: long-in-bull is best for all six presets — and short is negative in 18 of 18 locked cells, while the rule beats always-in in 1 of 48.",
         fontsize=10.5, color=ORANGE, weight="bold")

# 1 LONG: three filters, locked
ax = fig.add_subplot(gs[0, 0])
x = np.arange(len(ORD)); w = 0.26
def get(side, flt, blk):
    return [float(F[(F.preset == p) & (F.side == side) & (F["filter"] == flt) & (F.block == blk)].R.iloc[0])
            if len(F[(F.preset == p) & (F.side == side) & (F["filter"] == flt) & (F.block == blk)]) else np.nan for p in ORD]
ax.bar(x - w, get("LONG", "bear only", "LOCKED"), w, color=ORANGE, label="bear only", zorder=3)
ax.bar(x, get("LONG", "both regimes", "LOCKED"), w, color=MUTE, label="both regimes", zorder=3)
ax.bar(x + w, get("LONG", "bull only", "LOCKED"), w, color=AQUA, label="bull only", zorder=3)
ax.axhline(0, color=INK2, lw=1)
ax.set_xticks(x); ax.set_xticklabels([SH[p] for p in ORD], rotation=28, ha="right", fontsize=8.6)
ax.set_ylabel("R per trade (locked)")
ax.set_title("LONG — a bull filter helps all six", fontsize=12.5, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=8.6, loc="lower left"); ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)

# 2 SHORT
ax = fig.add_subplot(gs[0, 1])
ax.bar(x - w, get("SHORT", "bear only", "LOCKED"), w, color=ORANGE, label="bear only", zorder=3)
ax.bar(x, get("SHORT", "both regimes", "LOCKED"), w, color=MUTE, label="both regimes", zorder=3)
ax.bar(x + w, get("SHORT", "bull only", "LOCKED"), w, color=AQUA, label="bull only", zorder=3)
ax.axhline(0, color=INK2, lw=1)
ax.set_xticks(x); ax.set_xticklabels([SH[p] for p in ORD], rotation=28, ha="right", fontsize=8.6)
ax.set_ylabel("R per trade (locked)")
ax.set_title("SHORT — negative in 18 of 18 locked cells", fontsize=12.5, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=8.6, loc="lower left"); ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)

# 3 research vs locked for the short side (it looked partly fine on research)
ax = fig.add_subplot(gs[1, 0])
sr = F[(F.side == "SHORT")]
pos_r = int((sr[sr.block == "research"].R > 0).sum()); n_r = len(sr[sr.block == "research"])
pos_l = int((sr[sr.block == "LOCKED"].R > 0).sum()); n_l = len(sr[sr.block == "LOCKED"])
lr = F[(F.side == "LONG")]
pl_r = int((lr[lr.block == "research"].R > 0).sum()); nl_r = len(lr[lr.block == "research"])
pl_l = int((lr[lr.block == "LOCKED"].R > 0).sum()); nl_l = len(lr[lr.block == "LOCKED"])
cats = ["LONG\nresearch", "LONG\nlocked", "SHORT\nresearch", "SHORT\nlocked"]
vals = [100*pl_r/nl_r, 100*pl_l/nl_l, 100*pos_r/n_r, 100*pos_l/n_l]
cnt = [f"{pl_r}/{nl_r}", f"{pl_l}/{nl_l}", f"{pos_r}/{n_r}", f"{pos_l}/{n_l}"]
ax.bar(np.arange(4), vals, 0.6, color=[AQUA, AQUA, MUTE, ORANGE], zorder=3)
for i, (v, c) in enumerate(zip(vals, cnt)):
    ax.text(i, v + 2, f"{v:.0f}%  ({c})", ha="center", fontsize=9.5, weight="bold", color=INK)
ax.set_xticks(range(4)); ax.set_xticklabels(cats, fontsize=9)
ax.set_ylabel("% of preset x regime cells that are positive"); ax.set_ylim(0, 118)
ax.set_title("Short looked half-workable on research and died", fontsize=12.5, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)

# 4 edge over always-in by side and regime
ax = fig.add_subplot(gs[1, 1])
d = D.dropna(subset=["edge"])
g = d.groupby(["side", "regime"]).edge.mean()
keys = [("LONG", "bull"), ("LONG", "bear"), ("SHORT", "bull"), ("SHORT", "bear")]
v = [float(g.loc[k]) for k in keys]
ax.bar(np.arange(4), v, 0.6, color=ORANGE, zorder=3)
for i, val in enumerate(v):
    ax.text(i, val + 0.026, f"{val:+.3f}", ha="center", va="bottom", fontsize=10, weight="bold", color="white")
ax.axhline(0, color=INK2, lw=1.4)
ax.set_ylim(-0.63, 0.012)
ax.set_xticks(range(4)); ax.set_xticklabels([f"{a}\n{b}" for a, b in keys], fontsize=9)
ax.set_ylabel("mean edge over always-in, R")
ax.set_title("Inside every regime, the entry conditions subtract", fontsize=12.5, weight="bold", color=INK, loc="left", pad=8)
ax.text(0.5, 0.045, "the rule beats always-in in 1 of 48 cells", transform=ax.transAxes, ha="center",
        fontsize=9.5, weight="bold", color=ORANGE, bbox=dict(boxstyle="round,pad=0.35", fc="white", ec=ORANGE, lw=1.1))
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)

# 5 the honest summary table
ax = fig.add_subplot(gs[2, :]); ax.axis("off")
ax.text(0, 1.0, "The four combinations, ranked on the locked block (best preset in each)", fontsize=12.5,
        weight="bold", color=INK, va="top")
rowsum = []
for side in ("LONG", "SHORT"):
    for flt, rn in (("bull only", "bull"), ("bear only", "bear")):
        sub = F[(F.side == side) & (F["filter"] == flt) & (F.block == "LOCKED")]
        if len(sub) == 0: continue
        best = sub.loc[sub.R.idxmax()]
        rowsum.append((f"{side} in {rn}", float(best.R), best.preset, int(best.n),
                       int((sub.R > 0).sum()), len(sub)))
rowsum.sort(key=lambda r: -r[1])
yy = 0.80
for lbl, r, pre, n, pos, tot in rowsum:
    c = AQUA if r > 0 else ORANGE
    ax.text(0.00, yy, lbl, fontsize=13, weight="bold", color=c, va="top")
    ax.text(0.20, yy, f"best {r:+.3f} R/trade", fontsize=12, color=INK, va="top")
    ax.text(0.40, yy, f"({pre}, n={n})", fontsize=10.5, color=INK2, va="top")
    ax.text(0.62, yy, f"{pos} of {tot} presets positive", fontsize=10.5, color=INK2, va="top")
    yy -= 0.20
ax.text(0, -0.06, "Gold rose 148.9% over the sample and 133.8% of that came on bull-labelled days. A long-only rule in that market is a bull-regime exposure by construction.",
        fontsize=9.6, color=MUTE, va="top")
fig.savefig("results/vwapema/vwapema_regime.png", dpi=150, facecolor="white")
print("wrote results/vwapema/vwapema_regime.png")
