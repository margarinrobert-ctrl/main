import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
BLUE, ORANGE, AQUA, PURP = "#2a78d6", "#eb6834", "#1baf7a", "#7a5cc7"
INK, INK2, MUTE, GRID = "#1c1f24", "#4a5058", "#8b929c", "#e6e9ed"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#c8ccd2", "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "figure.facecolor": "white"})
L = pd.read_csv("results/vwapema/m6_ladder.csv")
fig = plt.figure(figsize=(14.6, 6.8))
gs = fig.add_gridspec(1, 3, wspace=0.30, left=0.065, right=0.975, top=0.735, bottom=0.155)
fig.text(0.048, 0.945, "The volume multiple — a real gradient that clears nothing",
         fontsize=18, weight="bold", color=INK)
fig.text(0.048, 0.905, "The one axis the 4,800-trial search actually depends on (fANOVA 0.22-0.46). Seven rungs, each against a RANDOM FILTER "
                       "keeping the same number of the un-gated rule's", fontsize=10, color=INK2)
fig.text(0.048, 0.878, "signal bars, re-simulated end to end. Selectivity falls from 92% to 33% of signals across the ladder.",
         fontsize=10, color=INK2)
fig.text(0.048, 0.838, "0 of 70 rungs clear p <= 0.05 where 3.5 are expected by chance — and the gradient is absent on the one block no search touched.",
         fontsize=10.4, color=ORANGE, weight="bold")

cells = [("US100", "LONG"), ("US30", "LONG"), ("US30_ISO", "LONG")]
titles = ["US100 long", "US30 long", "US30_ISO long  (reserved forward block)"]
for k, ((feed, side), ttl) in enumerate(zip(cells, titles)):
    ax = fig.add_subplot(gs[0, k])
    s = L[(L.feed == feed) & (L.side == side)]
    for blk, col, mk in (("research", BLUE, "o"), ("LOCKED", ORANGE, "s"), ("whole", PURP, "D")):
        g = s[s.block == blk].sort_values("vol_mult")
        if len(g) == 0:
            continue
        ax.plot(g.vol_mult, g.R, marker=mk, color=col, lw=2.1, ms=6,
                label=blk if blk != "whole" else "whole (never split)", zorder=4)
        ax.plot(g.vol_mult, g.ctl_R, marker=mk, color=col, lw=1.4, ms=4, ls="--", alpha=.55,
                label=f"{blk} — random filter" if blk != "whole" else "random filter", zorder=3)
    ax.axhline(0, color=INK2, lw=1)
    ax.axvline(1.1, color=MUTE, lw=1.2, ls=":")
    ax.text(1.13, ax.get_ylim()[0], " published 1.1", fontsize=8.2, color=MUTE, va="bottom")
    ax.set_xlabel("volume multiple (C5)"); ax.set_ylabel("R per trade" if k == 0 else "")
    ax.set_title(ttl, fontsize=12.2, weight="bold", color=INK, loc="left", pad=8)
    ax.legend(frameon=False, fontsize=7.8, loc="lower left" if k < 2 else "center left")
    ax.grid(alpha=.2, color=GRID); ax.set_axisbelow(True)
    rho = [f"{b} rho {g2.vol_mult.corr(g2.R, method='spearman'):+.2f}"
           for b, g2 in s.groupby("block") if len(g2) >= 4]
    ax.text(0.02, 0.985, "   ".join(rho), transform=ax.transAxes,
            fontsize=8.4, color=INK2, va="top")
fig.text(0.048, 0.045, "Best p anywhere is 0.060 (US30 long research, at the published 1.1); the best on any locked block is 0.180. Removing the range condition C6 gives the same answer, "
                       "so it is not the range confound.", fontsize=9.2, color=MUTE)
fig.text(0.048, 0.018, "The ladder is a SELECTIVITY ladder, and restrictiveness alone raises a profit factor — the dashed control climbs with the rule.",
         fontsize=9.2, color=MUTE)
fig.savefig("results/vwapema/vwapema_volume_ladder.png", dpi=145, facecolor="white")
print("wrote results/vwapema/vwapema_volume_ladder.png")
