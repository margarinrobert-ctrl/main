"""Render the Monte Carlo battery as one panel. Small multiples: rows = test, columns = block.

Design notes. One series per cell, so identity comes from the column heading and never from colour
alone; the three block hues are fixed across the whole grid (colour follows the entity, not the row
number). The palette is the validated categorical slots 1/2/3 -- blue, orange, aqua -- which clear
the all-pairs CVD and normal-vision floors in both modes; the aqua sits below 3:1 on a light surface
so the relief rule applies and every cell carries its numbers as visible text. Reference lines are
neutral ink, never a series hue, because they are annotation rather than data, and they are
explained once in a key rather than labelled on all fifteen panels.

Row titles are positioned from the axes' ACTUAL rendered coordinates rather than from guessed figure
fractions, and each stat block is placed in whichever top corner holds less of the distribution --
both because the first draft collided on every row.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "results/xaucvd")

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
HUE = {"A_primary": "#2a78d6", "B_meta": "#eb6834", "C_locked": "#1baf7a"}
LABEL = {"A_primary": "A   2010–2017", "B_meta": "B   2018–2022", "C_locked": "C   2023–2026"}
SUBL = {"A_primary": "research", "B_meta": "research", "C_locked": "locked"}
BLOCKS = ["A_primary", "B_meta", "C_locked"]

Z = np.load(os.path.join(OUT, "mc.npz"))
PR = pd.read_csv(os.path.join(OUT, "mc_params.csv"))
EV = pd.read_csv(os.path.join(OUT, "mc_events.csv"))
REF = {b: dict(mean=EV[EV.blk == i].pct.mean(), total=EV[EV.blk == i].pct.sum(),
               n=len(EV[EV.blk == i])) for i, b in enumerate(BLOCKS)}

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "font.family": "DejaVu Sans", "font.size": 8.5,
    "axes.edgecolor": GRID, "axes.linewidth": 0.8,
    "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
    "xtick.major.size": 2.5, "ytick.major.size": 0, "ytick.labelleft": False,
})

ROWS = [
    ("Edge — day-block bootstrap", "%/event",
     "2,000 draws. Whole days resampled with their trades attached, then the trade-weighted mean, because trades cluster inside a day.   "
     "The question: is the per-event edge distinguishable from zero?", "boot"),
    ("Path — permutation of the realised trades", "max drawdown, % of price",
     "2,000 reshuffles of the same trades. The sum is invariant under permutation, so only the DRAWDOWN is read — never an endpoint.   "
     "The question: was the realised path lucky, and what should size be set against?", "perm"),
    ("Execution — cost and slippage perturbed inside the walk", "total return, % of price",
     "300 draws, cost ~ U(0.5×, 2×) and slippage ~ U(0, 2×). Gold's 0.30 USD/oz round turn is an assumption no feed here can check, "
     "so this prices the input most likely to be wrong.", "exec"),
    ("Data — price jitter with every indicator recomputed", "total return, % of price",
     "150 draws at 1 tick. OHLC jittered, the bar repaired, then ATR, both Donchian channels, the CVD and the whole pivot structure rebuilt "
     "from the jittered bars — the only test that can move the signal set.", "jit1.0"),
    ("Parameters — five axes jittered together", "%/event",
     "400 draws. Entry 15–25, exit 15–25, stop 1.5–2.5 ATR, pivot half-width 1–3, recency window 12–28 bars.   "
     "The question: is the shipped cell a spike, or the middle of a neighbourhood?", "par"),
]

fig = plt.figure(figsize=(14.0, 19.5))
gs = fig.add_gridspec(len(ROWS), 3, hspace=0.95, wspace=0.11,
                      left=0.042, right=0.988, top=0.856, bottom=0.055)

for r, (title, xlab, sub, key) in enumerate(ROWS):
    for c, b in enumerate(BLOCKS):
        ax = fig.add_subplot(gs[r, c])
        col = HUE[b]
        arr = PR[b].dropna().to_numpy() if key == "par" else np.asarray(Z[f"{key}_{b}"], float)
        arr = arr[np.isfinite(arr)]
        ax.hist(arr, bins=42, color=col, alpha=0.85, edgecolor=SURFACE, linewidth=0.45)
        ax.grid(axis="y", color=GRID, linewidth=0.7)
        ax.set_axisbelow(True)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(GRID)

        if key == "boot":
            ax.axvline(0.0, color=INK, linewidth=1.5)
            ax.axvline(REF[b]["mean"], color=INK2, linewidth=1.3, linestyle="--")
            note = (f"P(mean ≤ 0)   {np.mean(arr <= 0):.3f}\n"
                    f"5–95%   {np.quantile(arr,0.05):+.3f} to {np.quantile(arr,0.95):+.3f}\n"
                    f"realised   {REF[b]['mean']:+.3f}   ·   n = {REF[b]['n']}")
        elif key == "perm":
            real = float(Z[f"realdd_{b}"]); p99 = float(np.quantile(arr, 0.99))
            pct = float(np.mean(arr <= real))
            ax.axvline(real, color=INK, linewidth=1.7)
            ax.axvline(p99, color=INK2, linewidth=1.3, linestyle=":")
            verdict = "the realised path was LUCKY" if pct < 0.25 else (
                "the realised path was UNLUCKY" if pct > 0.75 else "a typical path")
            note = (f"realised   {real:.2f}%   at the {100*pct:.0f}th percentile\n"
                    f"MC p99   {p99:.2f}%   =   {p99/max(real,1e-9):.2f}× realised\n"
                    f"{verdict}")
        elif key in ("exec", "jit1.0"):
            ax.axvline(0.0, color=INK, linewidth=1.5)
            ax.axvline(REF[b]["total"], color=INK2, linewidth=1.3, linestyle="--")
            lo = min(0.0, float(arr.min())) - 1.0
            hi = float(arr.max()) + (float(arr.max()) - lo) * 0.02
            ax.set_xlim(lo, hi)
            note = (f"P(total ≤ 0)   {np.mean(arr <= 0):.3f}\n"
                    f"5–95%   {np.quantile(arr,0.05):.1f}% to {np.quantile(arr,0.95):.1f}%\n"
                    f"as measured   {REF[b]['total']:.1f}%")
        else:
            ref = REF[b]["mean"]
            ax.axvline(0.0, color=INK, linewidth=1.5)
            ax.axvline(ref, color=INK2, linewidth=1.4, linestyle="--")
            note = (f"{100*np.mean(arr>0):.0f}% of jittered cells positive\n"
                    f"{100*np.mean(arr>ref):.0f}% beat the shipped cell\n"
                    f"5–95%   {np.quantile(arr,0.05):+.3f} to {np.quantile(arr,0.95):+.3f}")

        # put the stat block in whichever top corner holds less of the distribution
        x0, x1 = ax.get_xlim()
        mid = x0 + (x1 - x0) / 2.0
        left_heavy = float(np.mean(arr < mid)) > 0.5
        ax.text(0.975 if left_heavy else 0.025, 0.975, note, transform=ax.transAxes,
                ha="right" if left_heavy else "left", va="top", fontsize=7.8, color=INK2,
                linespacing=1.75,
                bbox=dict(boxstyle="round,pad=0.42", facecolor=SURFACE, edgecolor=GRID, linewidth=0.7))

        ax.set_title(f"{LABEL[b]}      {SUBL[b]}", fontsize=9.5,
                     color=col if r == 0 else INK2,
                     fontweight="bold" if r == 0 else "normal", pad=7, loc="left")
        ax.set_xlabel(xlab, fontsize=8, color=INK2, labelpad=3)
        ax.tick_params(labelsize=7.8)
        if c == 0:
            ax._rowmeta = (title, sub)

# row headings placed from the axes' ACTUAL positions, so nothing can collide
fig.canvas.draw()
for r, (title, xlab, sub, key) in enumerate(ROWS):
    ax0 = fig.axes[r * 3]
    y = ax0.get_position().y1
    fig.text(0.042, y + 0.041, title, fontsize=13.5, fontweight="bold", color=INK, va="bottom")
    fig.text(0.042, y + 0.0225, sub, fontsize=8.6, color=INK2, va="bottom")

fig.text(0.042, 0.972, "Gold Donchian + CVD exhausted-sellers gate — Monte Carlo battery",
         fontsize=18, fontweight="bold", color=INK, va="top")
fig.text(0.042, 0.9525,
         "XAUUSD 60m  ·  Donchian 20/20  ·  2.0 ATR stop  ·  no take profit  ·  long only  ·  "
         "gate = price lower low with CVD higher low at a confirmed pivot, within 20 bars",
         fontsize=9.8, color=INK2, va="top")
fig.text(0.042, 0.9375,
         "Five separate simulations because they answer five different questions. Bootstrap for the edge, permute for the path — "
         "an endpoint read off a permutation is meaningless.",
         fontsize=9.8, color=INK2, va="top")

key_items = [Line2D([], [], color=INK, lw=1.6, label="zero, or the realised drawdown"),
             Line2D([], [], color=INK2, lw=1.4, ls="--", label="the strategy as measured"),
             Line2D([], [], color=INK2, lw=1.4, ls=":", label="Monte Carlo p99 — the sizing number")]
fig.legend(handles=key_items, loc="upper left", bbox_to_anchor=(0.042, 0.928), ncol=3,
           frameon=False, fontsize=9, labelcolor=INK2, handlelength=2.4, columnspacing=2.6)

fig.text(0.042, 0.0335,
         "What this prices:  execution noise, data noise and parameter noise ON THE TRADES SELECTED.",
         fontsize=9.2, color=INK, va="top")
fig.text(0.042, 0.0205,
         "What it cannot price:  THE SELECTION. This gate is one cell of a 229-cell screen in which 13 cleared p ≤ 0.05 against 11.5 expected by chance,",
         fontsize=9.2, color=INK2, va="top")
fig.text(0.042, 0.0085,
         "and block C had already been read once before this study. No Monte Carlo addresses selection — only a fresh market or a fresh block does.",
         fontsize=9.2, color=INK2, va="top")

png = os.path.join(OUT, "montecarlo.png")
fig.savefig(png, dpi=150, facecolor=SURFACE)
print("wrote", png)
