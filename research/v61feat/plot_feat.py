"""The feature-engineering study as one panel."""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "results/v61feat")
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"

plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
                     "font.family": "DejaVu Sans", "font.size": 9,
                     "axes.edgecolor": GRID, "axes.linewidth": 0.8,
                     "xtick.color": INK2, "ytick.color": INK2, "text.color": INK})

IC = pd.read_csv(os.path.join(OUT, "ic.csv"))
ST = pd.read_csv(os.path.join(OUT, "stability.csv"))
G2 = pd.read_csv(os.path.join(OUT, "gate2.csv"))
DR = pd.read_csv(os.path.join(OUT, "dropone.csv"))
KEEP = pd.read_csv(os.path.join(OUT, "kept.csv")).feature.tolist()

fig = plt.figure(figsize=(15.2, 10.8))
gs = fig.add_gridspec(2, 2, hspace=0.42, wspace=0.24, left=0.075, right=0.985, top=0.838, bottom=0.135)

fig.text(0.075, 0.972, "Feature engineering on the V61 CVD rule — NQ 15-minute",
         fontsize=18, fontweight="bold", color=INK, va="top")
fig.text(0.075, 0.9515,
         "51 causal features in 7 declared families (trend · breakout structure · momentum · volatility · volume · regime · fracdiff), built from raw OHLCV.",
         fontsize=9.8, color=INK2, va="top")
fig.text(0.075, 0.9345,
         "Fracdiff and the HMM are META FEATURES ONLY — neither can fire a trade. HMM parameters fitted on research and read FILTERED, never smoothed. Truncation audit: 0 mismatches / 1,020.",
         fontsize=9.8, color=INK2, va="top")

# A  IC vs shuffled twin
ax = fig.add_subplot(gs[0, 0])
IC2 = IC.assign(a=IC.ic.abs()).sort_values("a", ascending=False).head(18).iloc[::-1]
ypos = np.arange(len(IC2))
cols = [C3 if f in KEEP else (C1 if p <= 0.05 else "#c9c8c3")
        for f, p in zip(IC2.feature, IC2.p)]
ax.barh(ypos, IC2.ic, color=cols, height=0.66)
ax.plot(np.where(IC2.ic >= 0, IC2.twin_p95, -IC2.twin_p95), ypos, "k|", markersize=9,
        markeredgewidth=1.6, color=INK)
ax.axvline(0, color=INK, linewidth=1.2)
ax.set_yticks(ypos); ax.set_yticklabels(IC2.feature, fontsize=8.2)
ax.set_xlabel("Spearman IC on the 225 research events", fontsize=9, color=INK2)
ax.grid(axis="x", color=GRID, linewidth=0.7); ax.set_axisbelow(True)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.text(0.98, 0.03, "│ = the shuffled twin's 95th percentile\n"
                    "green = kept   blue = p ≤ 0.05   grey = neither\n"
                    "9 of 51 clear p ≤ 0.05 against 2.6 expected",
        transform=ax.transAxes, ha="right", va="bottom", fontsize=8.4, color=INK2, linespacing=1.7,
        bbox=dict(boxstyle="round,pad=0.4", facecolor=SURFACE, edgecolor=GRID, linewidth=0.7))
ax.set_title("A   Predictive power, each against its own shuffled twin",
             fontsize=12.5, fontweight="bold", color=INK, loc="left", pad=10)

# B  stability
ax = fig.add_subplot(gs[0, 1])
sel = ST[ST.feature.isin(KEEP + [f for f in IC.nlargest(4, "ic").feature if f not in KEEP])]
sel = ST[ST.feature.isin(KEEP)].copy()
ypos = np.arange(len(sel))
for i, (_, r) in enumerate(sel.iterrows()):
    vals = [r.ic_calm, r.ic_mid, r.ic_fast]
    ax.plot(vals, [i] * 3, "-", color=GRID, linewidth=2.0, zorder=1)
    ax.scatter(vals, [i] * 3, s=44, c=[C1, C2, C3], zorder=3, edgecolors=SURFACE, linewidth=0.8)
ax.axvline(0, color=INK, linewidth=1.3)
ax.set_yticks(ypos); ax.set_yticklabels(sel.feature, fontsize=8.4)
ax.set_xlabel("Spearman IC within each volatility regime", fontsize=9, color=INK2)
ax.grid(axis="x", color=GRID, linewidth=0.7); ax.set_axisbelow(True)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
from matplotlib.lines import Line2D
ax.legend(handles=[Line2D([], [], marker="o", ls="", color=c, label=l, markersize=7)
                   for c, l in ((C1, "calm"), (C2, "mid"), (C3, "fast"))],
          frameon=True, framealpha=1.0, edgecolor=GRID, facecolor=SURFACE,
          fontsize=8.6, labelcolor=INK2, ncol=1, loc="lower left")
ax.set_title("B   Stability — the sign must hold in every volatility regime",
             fontsize=12.5, fontweight="bold", color=INK, loc="left", pad=10)
ax.set_xlabel("Spearman IC within each volatility regime      ·      18 of 51 features hold their sign\n"
              "across both halves of research AND all three regimes (chance ≈ 12.5%)",
              fontsize=8.8, color=INK2)

# C  Gate 2
ax = fig.add_subplot(gs[1, 0])
for kind, col in (("rf", C3), ("lgbm", C2), ("ridge", C1), ("logit", "#c9c8c3")):
    z = G2[G2.model == kind].sort_values("keep")
    ax.plot(100 * z.keep, z.up, "-o", color=col, linewidth=2.0, markersize=5.5, label=kind)
ax.axhline(0, color=INK, linewidth=1.3)
ax.invert_xaxis()
ax.set_xlabel("keep fraction of the primary's events (%)", fontsize=9, color=INK2)
ax.set_ylabel("unsized uplift, % of entry price per event", fontsize=9, color=INK2)
ax.grid(color=GRID, linewidth=0.7); ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.legend(frameon=False, fontsize=8.8, labelcolor=INK2, loc="upper left")
best = G2.sort_values(["p_ctl", "p"]).iloc[0]
ax.scatter([100 * best.keep], [best.up], s=150, facecolors="none", edgecolors=INK, linewidth=1.8, zorder=5)
ax.text(0.60, 0.05, f"best cell — rf @ keep 40%\nuplift {best.up:+.3f} %/event\n"
        f"bootstrap p {best.p:.3f}\nrandom-filter p {best.p_ctl:.3f}",
        transform=ax.transAxes, ha="left", va="bottom", fontsize=8.6, color=INK2, linespacing=1.7,
        bbox=dict(boxstyle="round,pad=0.4", facecolor=SURFACE, edgecolor=GRID, linewidth=0.7))
ax.set_title("C   Gate 2 — unsized uplift, 4 of 20 cells clear BOTH nulls",
             fontsize=12.5, fontweight="bold", color=INK, loc="left", pad=10)

# D  drop-one
ax = fig.add_subplot(gs[1, 1])
DR2 = DR.sort_values("delta")
ypos = np.arange(len(DR2))
ax.barh(ypos, DR2.delta, color=C2, height=0.62)
ax.axvline(0, color=INK, linewidth=1.3)
ax.set_yticks(ypos); ax.set_yticklabels(DR2.dropped, fontsize=8.6)
ax.set_xlabel("change in uplift when this feature is REMOVED (% per event)", fontsize=9, color=INK2)
ax.grid(axis="x", color=GRID, linewidth=0.7); ax.set_axisbelow(True)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.text(0.03, 0.96, "all 8 are negative — every kept feature\ncontributes incrementally",
        transform=ax.transAxes, ha="left", va="top", fontsize=8.6, color=INK2, linespacing=1.7,
        bbox=dict(boxstyle="round,pad=0.4", facecolor=SURFACE, edgecolor=GRID, linewidth=0.7))
ax.set_title("D   Drop-one — does each feature earn its place incrementally?",
             fontsize=12.5, fontweight="bold", color=INK, loc="left", pad=10)

fig.text(0.075, 0.088,
         "ONE locked read, threshold taken from the research score distribution:  unfiltered 0.1022 %/event at PF 1.862  →  filtered 0.1560 at PF 2.707 on 56 of 125 events.",
         fontsize=9.2, color=INK, va="top")
fig.text(0.075, 0.062,
         "Uplift +0.0538 — but a random filter of the same size gives p 0.145, so it does NOT clear out of sample. It kept 45% against the 40% it was set for, so the score IS calibrated across the split.",
         fontsize=9.2, color=INK2, va="top")
fig.text(0.075, 0.036,
         "Deflated Sharpe 0.750 against an expected best-of-null of 0.218 over 136 counted looks; White's reality check p 0.011. Total return falls 12.78% → 8.74% because the filter removes 55% of the trades.",
         fontsize=9.2, color=INK2, va="top")

png = os.path.join(OUT, "feature_panel.png")
fig.savefig(png, dpi=150, facecolor=SURFACE)
print("wrote", png)
