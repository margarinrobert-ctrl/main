"""Figure for the handoff follow-up: the gate's profit factor beside its base on every block that was read, in the order they were opened."""
import os, numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); OUT = os.path.join(ROOT, "results/inst")
rows = [("NQ research\n(selected here)", 1.164, 1.446, 765, 350, "sel"), ("NQ locked\n(one read)", 1.110, 1.382, 389, 187, "lock"),
        ("US100 post-2022\n(same weeks as NQ)", 1.122, 1.203, 1125, 556, "par"), ("US100 PRE-2022\n(primary, 7 yrs unseen)", 0.970, 0.907, 2264, 1092, "pri"),
        ("US30 2016-2025\n(mechanism test)", 0.973, 0.927, 3131, 1555, "mech")]
BG = "#0f1115"; FG = "#e6e6e6"; GRID = "#2a2e36"
plt.rcParams.update({"figure.facecolor": BG, "axes.facecolor": BG, "axes.edgecolor": GRID, "axes.labelcolor": FG, "xtick.color": FG, "ytick.color": FG, "text.color": FG, "grid.color": GRID, "legend.facecolor": BG, "legend.edgecolor": GRID})
fig, ax = plt.subplots(figsize=(13, 6)); x = np.arange(len(rows))
ax.bar(x - 0.2, [r[1] for r in rows], 0.4, color="#8a8f99", label="base: Donchian 10/10, 07:00-11:00, 3.0 ATR stop, 2.3 ATR target")
ax.bar(x + 0.2, [r[2] for r in rows], 0.4, color=["#3ec9a7" if r[2] > r[1] else "#e0605e" for r in rows], label="+ prior-session single print <= 4 ATR above (3 ATR on the NQ blocks)")
for i, r in enumerate(rows):
    ax.text(i - 0.2, r[1] + 0.02, f"{r[1]:.2f}\nn {r[3]}", ha="center", fontsize=8); ax.text(i + 0.2, r[2] + 0.02, f"{r[2]:.2f}\nn {r[4]}", ha="center", fontsize=8, fontweight="bold")
ax.axhline(1.0, color=FG, lw=0.8, ls="--"); ax.axvline(2.5, color="#f2b134", lw=1, ls=":"); ax.text(2.55, 0.82, "blocks the NQ selection never saw", color="#f2b134", fontsize=9)
ax.set_xticks(x); ax.set_xticklabels([r[0] for r in rows], fontsize=9); ax.set_ylabel("profit factor"); ax.set_ylim(0.8, 1.65); ax.grid(axis="y", alpha=0.3); ax.legend(loc="upper right", fontsize=8)
ax.set_title("The single-print gate on every block read, in the order they were opened: it lifts the two Nasdaq blocks of 2023-2025 and lowers everything else")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "vp_fig8_crossmarket.png"), dpi=140); print("ok")
