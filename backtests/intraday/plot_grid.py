#!/usr/bin/env python3
"""Entry x exit Sharpe heatmap (graded ensemble) from intraday_grid.py's grid.npz."""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

z = np.load("grid.npz", allow_pickle=True)
sr, cfgs, slots = z["sr_full"], z["cfgs"], list(z["slots"])
S = len(slots)
mat = np.full((S, S), np.nan)
for (vn, e, x), s in zip(cfgs, sr):
    if vn == "GRAD":
        mat[int(e), int(x)] = s

# diverging: serious red -> neutral -> blue (palette slots), midpoint at 0
cmap = LinearSegmentedColormap.from_list("div", ["#e34948", "#f5f4ef", "#2a78d6"])
norm = TwoSlopeNorm(vmin=-1.0, vcenter=0.0, vmax=1.0)  # clip: short-window cells hit -5 on costs alone

fig, ax = plt.subplots(figsize=(9.8, 8.2), dpi=200)
fig.patch.set_facecolor("#fcfcfb")
im = ax.imshow(np.clip(mat, -1, 1), cmap=cmap, norm=norm, aspect="auto", origin="lower")
ax.set_title("Intraday SAM-Best — net Sharpe by entry × exit time (graded ensemble)",
             loc="left", fontsize=12.5, color="#1a1a19", fontweight="bold", pad=34)
ax.text(0, 1.055, "2,253 days · 2 bps/side (4 bps/round trip) · flat by session close · "
        "best cell 0.50 vs noise-deflation threshold ≈ 1.24 · server time (US cash ≈ 16:30–23:00)",
        transform=ax.transAxes, fontsize=8.2, color="#6b6a63")
step = 4
ax.set_xticks(range(0, S, step), [slots[i] for i in range(0, S, step)],
              fontsize=7.5, rotation=45, color="#6b6a63")
ax.set_yticks(range(0, S, step), [slots[i] for i in range(0, S, step)],
              fontsize=7.5, color="#6b6a63")
ax.set_xlabel("Exit slot (close of bar)", fontsize=9, color="#6b6a63")
ax.set_ylabel("Entry slot (close of bar)", fontsize=9, color="#6b6a63")
for s_ in ax.spines.values():
    s_.set_visible(False)
ax.tick_params(length=0)

# annotate the pre-specified candidate and the plateau
e0, x0 = slots.index("01:00"), slots.index("23:30")
ax.scatter([x0], [e0], marker="o", s=90, facecolor="none", edgecolor="#1a1a19", lw=1.6)
ax.annotate("C2: enter first bar, exit last bar\n(pre-specified; OOS SR 0.34)",
            xy=(x0, e0), xytext=(-215, 14), textcoords="offset points",
            fontsize=8.3, color="#1a1a19", fontweight="bold",
            arrowprops=dict(arrowstyle="-", color="#1a1a19", lw=0.8))

cb = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02, extend="both")
cb.set_label("Full-sample net annualized Sharpe (clipped at ±1)", fontsize=8.5, color="#6b6a63")
cb.ax.tick_params(labelsize=7.5, colors="#6b6a63")
cb.outline.set_visible(False)

plt.tight_layout()
plt.savefig("intraday_grid.png", facecolor=fig.get_facecolor(), bbox_inches="tight")
print("saved intraday_grid.png")
