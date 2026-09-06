"""The four results as one panel: equity by leg, the Optuna transfer, the session ablation, and the
leg-correlation matrix.

Palette is the validated categorical slots; lines use the adjacent pairlist so four series are legal,
and every line is direct-labelled so identity never rests on colour. The Optuna panel is one series
(scatter, all-pairs) so it takes slot 1 alone. Reference lines are neutral ink.
"""
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
C1, C2, C3, C4 = "#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "font.family": "DejaVu Sans",
    "font.size": 9, "axes.edgecolor": GRID, "axes.linewidth": 0.8,
    "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
})

DR = pd.read_csv(os.path.join(OUT, "daily.csv"), index_col=0)
L = pd.read_csv(os.path.join(OUT, "optuna_trials.csv"))
AB = pd.read_csv(os.path.join(OUT, "ablation.csv"))
CUT = 20241128

fig = plt.figure(figsize=(15.0, 11.6))
gs = fig.add_gridspec(2, 2, hspace=0.40, wspace=0.20, left=0.055, right=0.985, top=0.835, bottom=0.100)

fig.text(0.055, 0.972, "V61 CVD exhaustion on NQ — your configuration, in and out of sample",
         fontsize=18, fontweight="bold", color=INK, va="top")
fig.text(0.055, 0.9515,
         "Donchian 20/20 · 2.0 ATR stop · no target · long only · CVD exhausted-sellers gate (90 / 600 minutes).  "
         "MNQ at $2 a point, 0.72 points of cost and 0.25 of slippage a side.",
         fontsize=10, color=INK2, va="top")
fig.text(0.055, 0.9325,
         "Research is the first 65% of sessions (to 2024-11-27); locked is everything after and was never used to choose anything.\n"
         "3 years of 1-minute NQ — a TradingView chart holds more history, so totals will differ. The shape is what transfers.",
         fontsize=10, color=INK2, va="top")

# ---- A  equity by leg
ax = fig.add_subplot(gs[0, 0])
LEGS = [("30m all hours", C1), ("15m all hours", C2), ("30m 07-11 no flatten", C3),
        ("15m 07-11 + flatten (yours)", C4)]
x = np.arange(len(DR))
cutx = int(np.searchsorted(DR.index.to_numpy(), CUT))
for nm, col in LEGS:
    y = np.cumsum(DR[nm].to_numpy()) * 2.0
    ax.plot(x, y, color=col, linewidth=2.0)
    ax.annotate(nm, xy=(x[-1], y[-1]), xytext=(6, 0), textcoords="offset points",
                fontsize=8.6, color=col, va="center", fontweight="bold")
eq = np.cumsum((0.5 * (DR["30m all hours"] + DR["15m all hours"])).to_numpy()) * 2.0
ax.plot(x, eq, color=INK, linewidth=2.4, linestyle="--")
ax.annotate("50/50 both all-hours legs", xy=(x[-1], eq[-1]), xytext=(6, 0),
            textcoords="offset points", fontsize=8.6, color=INK, va="center", fontweight="bold")
ax.axvline(cutx, color=INK2, linewidth=1.2, linestyle=":")
ax.text(cutx, ax.get_ylim()[1], "  locked block begins", fontsize=8.4, color=INK2, va="top")
ax.set_xlim(0, len(DR) * 1.30)
ax.grid(axis="y", color=GRID, linewidth=0.7); ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.set_ylabel("cumulative $, one MNQ", fontsize=9, color=INK2)
ax.set_xlabel("trading days", fontsize=9, color=INK2)
ax.set_title("A   Equity by leg — research's best leg is not locked's best leg",
             fontsize=12, fontweight="bold", color=INK, loc="left", pad=10)

# ---- B  Optuna transfer
ax = fig.add_subplot(gs[0, 1])
z = L.dropna(subset=["l_pf"])
ax.scatter(z.r_pf, z.l_pf, s=9, color=C1, alpha=0.30, edgecolors="none")
ax.axhline(1.0, color=INK, linewidth=1.3)
ax.axvline(1.0, color=INK, linewidth=1.3)
top = z.nlargest(max(1, len(z) // 100), "r_pf")
ax.scatter(top.r_pf, top.l_pf, s=30, color="#e34948", edgecolors=SURFACE, linewidth=0.6, zorder=3)
r = z.r_pf.corr(z.l_pf)
ax.text(0.025, 0.975, f"2,400 Optuna trials, {len(z):,} scorable on both blocks\n"
                      f"corr(research PF, locked PF)   Pearson {r:+.3f}\n"
                      f"top 1% by research PF (red):  {top.r_pf.mean():.2f} research  →  "
                      f"{top.l_pf.mean():.2f} locked\nwhole population on locked:  {z.l_pf.mean():.2f}",
        transform=ax.transAxes, ha="left", va="top", fontsize=8.8, color=INK2, linespacing=1.7,
        bbox=dict(boxstyle="round,pad=0.45", facecolor=SURFACE, edgecolor=GRID, linewidth=0.7))
ax.set_xlim(0.6, 2.8); ax.set_ylim(0.2, 3.0)
ax.grid(color=GRID, linewidth=0.7); ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.set_xlabel("profit factor on the research block (what the optimiser saw)", fontsize=9, color=INK2)
ax.set_ylabel("profit factor on the locked block", fontsize=9, color=INK2)
ax.set_title("B   Optuna — the research ranking runs backwards",
             fontsize=12, fontweight="bold", color=INK, loc="left", pad=10)

# ---- C  session / flatten ablation
ax = fig.add_subplot(gs[1, 0])
arms = ["all hours, no flatten", "07:00-11:00, NO flatten", "all hours, flatten 11:00",
        "07:00-11:00 + flatten"]
w = 0.2
for i, (tf, blk, col, lab) in enumerate([(30, "research", C1, "30m research"),
                                         (30, "locked", C3, "30m locked"),
                                         (15, "research", C2, "15m research"),
                                         (15, "locked", C4, "15m locked")]):
    vals = [AB[(AB.tf == f"{tf}m") & (AB.arm == a) & (AB.block == blk)].pf.mean() for a in arms]
    ax.bar(np.arange(len(arms)) + (i - 1.5) * w, vals, width=w * 0.9, color=col, label=lab)
ax.axhline(1.0, color=INK, linewidth=1.3)
ax.set_xticks(np.arange(len(arms)))
ax.set_xticklabels([a.replace(", ", ",\n") for a in arms], fontsize=8.4)
ax.grid(axis="y", color=GRID, linewidth=0.7); ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.set_ylabel("profit factor", fontsize=9, color=INK2)
ax.legend(frameon=False, fontsize=8.6, ncol=2, labelcolor=INK2, loc="upper right")
ax.set_title("C   The window is fine — the FLATTEN is what costs",
             fontsize=12, fontweight="bold", color=INK, loc="left", pad=10)

# ---- D  correlation matrix
ax = fig.add_subplot(gs[1, 1])
short = {"30m all hours": "30m\nall hours", "30m 07-11 no flatten": "30m\n07-11",
         "15m all hours": "15m\nall hours", "15m 07-11 + flatten (yours)": "15m 07-11\n+flat (yours)"}
M = DR.corr()
im = ax.imshow(M.to_numpy(), cmap="Blues", vmin=0.0, vmax=1.0)
ax.set_xticks(range(len(M))); ax.set_yticks(range(len(M)))
ax.set_xticklabels([short[c] for c in M.columns], fontsize=8.2)
ax.set_yticklabels([short[c] for c in M.index], fontsize=8.2)
for i in range(len(M)):
    for j in range(len(M)):
        v = M.iat[i, j]
        ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=10.5,
                color="#ffffff" if v > 0.55 else INK,
                fontweight="bold" if i != j else "normal")
for s in ("top", "right", "left", "bottom"):
    ax.spines[s].set_visible(False)
ax.set_title("D   Daily-return correlation between legs",
             fontsize=12, fontweight="bold", color=INK, loc="left", pad=10)
ax.set_xlabel("zero-filled on days a leg did not trade", fontsize=8.4, color=INK2, labelpad=8)

fig.text(0.055, 0.052,
         "The strategy tester's report is at ZERO commission unless you set it in Properties — this script ships with none. "
         "Costs here are 4.6–21.9% of gross depending on the configuration.",
         fontsize=9, color=INK2, va="top")
fig.text(0.055, 0.030,
         "Permutation p99 drawdown runs 1.2× to 3.5× the realised on every leg. Size against that, not against the equity curve.",
         fontsize=9, color=INK2, va="top")

png = os.path.join(OUT, "session_panel.png")
fig.savefig(png, dpi=150, facecolor=SURFACE)
print("wrote", png)
