"""The US30 cross-market read as one panel."""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "results/v61sess")
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"

plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
                     "font.family": "DejaVu Sans", "font.size": 9,
                     "axes.edgecolor": GRID, "axes.linewidth": 0.8,
                     "xtick.color": INK2, "ytick.color": INK2, "text.color": INK})

AB = pd.read_csv(os.path.join(OUT, "us30_ablation.csv"))
NU = pd.read_csv(os.path.join(OUT, "us30_nulls.csv"))
PX = pd.read_csv(os.path.join(OUT, "portfolio_xmkt_stats.csv"))
PORT = pd.read_csv(os.path.join(OUT, "portfolio_xmkt.csv"), index_col=0)

fig = plt.figure(figsize=(15.0, 10.4))
gs = fig.add_gridspec(2, 2, hspace=0.46, wspace=0.22, left=0.06, right=0.985, top=0.845, bottom=0.085)

fig.text(0.06, 0.972, "V61 CVD rule frozen and run on US30 — the cross-market read",
         fontsize=18, fontweight="bold", color=INK, va="top")
fig.text(0.06, 0.9515,
         "US30_LONG_15m, 193,942 bars, 2016-10 to 2025-07, verified byte-identical to the registry copy.  Nothing fitted here: geometry and order-flow windows are NQ's.",
         fontsize=9.6, color=INK2, va="top")
fig.text(0.06, 0.9345,
         "60-minute chart, because CVD needs sub-bars and this feed's finest is 15m — FOUR sub-bars a bar against the THIRTY the NQ result was built on, and tick volume rather than contracts.",
         fontsize=9.6, color=INK2, va="top")

# A  the rule against its three nulls
ax = fig.add_subplot(gs[0, 0])
labs = ["the rule", "random\nENTRY", "random\nFILTER", "always\nlong"]
w = 0.36
for i, (b, col) in enumerate([("block A", C1), ("block B", C3)]):
    r = NU[NU.block == b].iloc[0]
    vals = [r.obs, r.ent, r.fil, r.always]
    ax.bar(np.arange(4) + (i - 0.5) * w, vals, width=w * 0.9, color=col, label=f"{b} (n={int(r.n)})")
ax.axhline(0, color=INK, linewidth=1.2)
ax.set_xticks(range(4)); ax.set_xticklabels(labs, fontsize=8.8)
ax.set_ylabel("points per trade", fontsize=9, color=INK2)
ax.grid(axis="y", color=GRID, linewidth=0.7); ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.legend(frameon=False, fontsize=8.8, labelcolor=INK2)
pa, pb = NU[NU.block == "block A"].iloc[0], NU[NU.block == "block B"].iloc[0]
ax.text(0.98, 0.97, f"random entry beats it:  p {pa.p_ent:.3f} / {pb.p_ent:.3f}\n"
                    f"random filter beats it: p {pa.p_fil:.3f} / {pb.p_fil:.3f}\n"
                    f"always-long beats it on both blocks",
        transform=ax.transAxes, ha="right", va="top", fontsize=8.6, color=INK2, linespacing=1.7,
        bbox=dict(boxstyle="round,pad=0.4", facecolor=SURFACE, edgecolor=GRID, linewidth=0.7))
ax.set_title("A   All three nulls beat the rule on US30", fontsize=12.5, fontweight="bold",
             color=INK, loc="left", pad=10)

# B  gate on vs off
ax = fig.add_subplot(gs[0, 1])
gon = {"block A": (208, 1.146, 10.94), "block B": (142, 1.101, 10.16)}
gof = {"block A": (568, 1.265, 21.96), "block B": (353, 1.143, 14.42)}
xs = np.arange(2)
ax.bar(xs - 0.18, [gon[b][2] for b in gon], width=0.34, color=C1, label="CVD gate ON")
ax.bar(xs + 0.18, [gof[b][2] for b in gof], width=0.34, color=C2, label="gate OFF (base only)")
for i, b in enumerate(gon):
    ax.text(i - 0.18, gon[b][2] + 0.5, f"PF {gon[b][1]:.3f}\nn {gon[b][0]}", ha="center",
            fontsize=8.4, color=INK2, linespacing=1.5)
    ax.text(i + 0.18, gof[b][2] + 0.5, f"PF {gof[b][1]:.3f}\nn {gof[b][0]}", ha="center",
            fontsize=8.4, color=INK2, linespacing=1.5)
ax.set_xticks(xs); ax.set_xticklabels(["block A  2016–2022", "block B  2022–2025"], fontsize=9)
ax.set_ylabel("points per trade", fontsize=9, color=INK2)
ax.set_ylim(0, 27)
ax.grid(axis="y", color=GRID, linewidth=0.7); ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.legend(frameon=False, fontsize=8.8, labelcolor=INK2, loc="upper left")
ax.set_title("B   The gate is SUBTRACTIVE here — the opposite of NQ", fontsize=12.5,
             fontweight="bold", color=INK, loc="left", pad=10)

# C  the session ablation on US30
ax = fig.add_subplot(gs[1, 0])
arms = ["all hours, no flatten", "07:00-11:00, NO flatten", "all hours, flatten 11:00",
        "07:00-11:00 + flatten"]
for i, (b, col) in enumerate([("block A", C1), ("block B", C3)]):
    vals = [AB[(AB.arm == a) & (AB.block == b)].pf.mean() for a in arms]
    ax.bar(np.arange(len(arms)) + (i - 0.5) * 0.36, vals, width=0.33, color=col, label=b)
ax.axhline(1.0, color=INK, linewidth=1.3)
ax.set_xticks(np.arange(len(arms)))
ax.set_xticklabels([a.replace(", ", ",\n") for a in arms], fontsize=8.4)
ax.set_ylabel("profit factor", fontsize=9, color=INK2)
ax.grid(axis="y", color=GRID, linewidth=0.7); ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.legend(frameon=False, fontsize=8.8, labelcolor=INK2)
ax.text(0.98, 0.97, "your 07:00–11:00 + flatten is BELOW 1.0\non both US30 blocks",
        transform=ax.transAxes, ha="right", va="top", fontsize=8.8, color=INK2, linespacing=1.6,
        bbox=dict(boxstyle="round,pad=0.4", facecolor=SURFACE, edgecolor=GRID, linewidth=0.7))
ax.set_title("C   Session ablation — the NQ flatten finding does not replicate",
             fontsize=12.5, fontweight="bold", color=INK, loc="left", pad=10)

# D  portfolio
ax = fig.add_subplot(gs[1, 1])
order = ["NQ 30m all hours", "NQ 15m all hours", "US30 gate ON",
         "EQUAL NQ 30m + NQ 15m", "EQUAL NQ 30m + NQ 15m + US30 gate ON"]
short = ["NQ 30m", "NQ 15m", "US30", "NQ 30m+15m", "NQ 30m+15m\n+ US30"]
cols = [C1, C1, C2, C3, C3]
vals = [PX[PX.cfg == c].ret_dd.iloc[0] for c in order]
sh = [PX[PX.cfg == c].sharpe.iloc[0] for c in order]
bars = ax.bar(np.arange(len(order)), vals, color=cols, width=0.62)
for i, (v, s_) in enumerate(zip(vals, sh)):
    ax.text(i, v + 0.35, f"{v:.2f}\nSharpe {s_:.2f}", ha="center", fontsize=8.6, color=INK2,
            linespacing=1.5)
ax.set_xticks(np.arange(len(order))); ax.set_xticklabels(short, fontsize=8.6)
ax.set_ylabel("return / max drawdown", fontsize=9, color=INK2)
ax.set_ylim(0, 18.5)
ax.grid(axis="y", color=GRID, linewidth=0.7); ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.text(0.98, 0.97, "US30 correlates only 0.11–0.23 with the NQ legs\n"
                    "and adding it still makes the book WORSE\n"
                    "(ret/DD 13.34 → 9.37, Sharpe 1.78 → 1.60)",
        transform=ax.transAxes, ha="right", va="top", fontsize=8.6, color=INK2, linespacing=1.7,
        bbox=dict(boxstyle="round,pad=0.4", facecolor=SURFACE, edgecolor=GRID, linewidth=0.7))
ax.set_title("D   A decorrelated leg still has to have an edge", fontsize=12.5,
             fontweight="bold", color=INK, loc="left", pad=10)

fig.text(0.06, 0.045,
         "Both US30 blocks are out of sample: US30 chose none of this rule's parameters. The caveat that stays attached is RESOLUTION —",
         fontsize=9, color=INK2, va="top")
fig.text(0.06, 0.026,
         "four sub-bars a bar against thirty, on tick volume rather than contracts, so this is a weaker refutation of the CVD than a null on NQ would be.",
         fontsize=9, color=INK2, va="top")

png = os.path.join(OUT, "us30_panel.png")
fig.savefig(png, dpi=150, facecolor=SURFACE)
print("wrote", png)
