"""Four panels: the arms with their MDE, the overlap matrix, the unit disagreement, the power."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xm_core as X  # noqa: E402

C = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_cache")
R = pd.read_csv(f"{C}/x3_cells.csv")
OV = pd.read_csv(f"{C}/x2_overlap.csv")
MD = pd.read_csv(f"{C}/x4_mde.csv")
DE = pd.read_csv(f"{C}/x7_deltas.csv")

fig = plt.figure(figsize=(17.5, 11.2))
fig.suptitle("The section-12 rule FROZEN and run on four markets that chose nothing",
             x=0.5, y=0.985, fontsize=15, fontweight="bold")
fig.text(0.5, 0.955, "Donchian 20 long, 07:00-11:00 New York, flat at the 11:00 open, "
         "50/150 expressed as the matched ATR multiple (1.613N / 4.838N).  "
         "70 declared cells, one read each.", ha="center", fontsize=10, color="#444")

ARMC = {"base": "#888888", "+adx<=20": "#d1495b", "+ema align": "#2a7fbf",
        "+both": "#7b4fa0", "conventional": "#e08e0b"}

# ---- panel 1: the arms, ATR units, with MDE bars ------------------------------------------
ax = fig.add_axes([0.055, 0.545, 0.50, 0.365])
A = R[(R.param == "atr")].copy()
A["cell"] = A.market + "\n" + A.block.str.replace("_", " ")
order = ["US100 A first70", "US100 B last30", "NQ A first70", "NQ B last30",
         "XAU A first70", "XAU B last30", "US30I C forward",
         "US30 A research", "US30 B holdout"]
A["cell"] = A["cell"].str.replace("\n", " ")
xs = np.arange(len(order))
w = 0.16
for k, (arm, _) in enumerate(X.ARMS):
    sub = A[A.arm == arm].set_index("cell").reindex(order)
    ax.bar(xs + (k - 2) * w, sub["mean"], w, color=ARMC[arm], label=arm,
           edgecolor="white", linewidth=0.4)
    ax.errorbar(xs + (k - 2) * w, np.zeros(len(order)), yerr=sub["mde80"], fmt="none",
                ecolor="#333", elinewidth=0.8, capsize=1.6, alpha=0.55)
ax.axhline(0, color="k", lw=0.9)
ax.axvline(6.5, color="#999", lw=1.2, ls="--")
ax.text(7.5, ax.get_ylim()[1] * 0.92, "US30 reference\n(spent blocks)", ha="center",
        fontsize=8, color="#666")
ax.set_xticks(xs)
ax.set_xticklabels([o.replace(" ", "\n", 1) for o in order], fontsize=8)
ax.set_ylabel("mean ATR units per trade")
ax.set_title("Every arm against its own 80%-power MDE (black bars) — nothing clears it anywhere",
             fontsize=11, loc="left")
ax.legend(fontsize=8, ncol=5, loc="lower left", framealpha=0.9)
ax.grid(axis="y", alpha=0.25)

# ---- panel 2: overlap matrix ---------------------------------------------------------------
ax = fig.add_axes([0.615, 0.545, 0.24, 0.365])
M = X.MARKETS
Z = np.full((len(M), len(M)), np.nan)
for _, r in OV.iterrows():
    a, b = r["pair"].split("/")
    i, j = M.index(a), M.index(b)
    Z[i, j] = r["same_ab"]
    Z[j, i] = r["same_ba"]
np.fill_diagonal(Z, 1.0)
im = ax.imshow(Z, cmap="RdYlGn_r", vmin=0, vmax=1)
ax.set_xticks(range(len(M)))
ax.set_xticklabels(M, fontsize=8, rotation=45)
ax.set_yticks(range(len(M)))
ax.set_yticklabels(M, fontsize=8)
for i in range(len(M)):
    for j in range(len(M)):
        if np.isfinite(Z[i, j]):
            ax.text(j, i, f"{Z[i, j]:.2f}", ha="center", va="center", fontsize=8,
                    color="white" if Z[i, j] > 0.6 or Z[i, j] < 0.15 else "black")
ax.set_title("Share of row's in-window breakout bars\nthat are ALSO the column's, same timestamp",
             fontsize=10, loc="left")
fig.colorbar(im, ax=ax, fraction=0.045, pad=0.03)

# ---- panel 3: the unit disagreement --------------------------------------------------------
ax = fig.add_axes([0.055, 0.075, 0.36, 0.36])
for arm in ("+adx<=20", "+ema align", "+both", "conventional"):
    s = DE[DE.arm == arm]
    ax.scatter(s.d_pts, s.d_atru, s=42, color=ARMC[arm], label=arm, alpha=0.85,
               edgecolor="white", linewidth=0.5)
h30 = DE[(DE.market == "US30") & (DE.block == "A_research") & (DE.arm == "+adx<=20")]
for _, r in h30.iterrows():
    ax.annotate("US30 research\n(section 12's cell)", (r.d_pts, r.d_atru),
                textcoords="offset points", xytext=(12, -26), fontsize=8, color="#d1495b",
                arrowprops=dict(arrowstyle="->", color="#d1495b", lw=0.9))
ax.axhline(0, color="k", lw=0.9)
ax.axvline(0, color="k", lw=0.9)
lim = max(abs(DE.d_pts).max() * 1.1, 1)
ax.fill_between([0, lim], 0, -1, color="#d1495b", alpha=0.07)
ax.fill_between([-lim, 0], 0, 1, color="#d1495b", alpha=0.07)
ax.set_xlim(-lim, lim)
ax.set_ylim(-0.45, 0.45)
ax.set_xlabel("arm minus base, POINTS per trade")
ax.set_ylabel("arm minus base, ATR UNITS per trade")
ax.set_title("The two units disagree in 10 of 72 comparisons — and the flagship cell is one",
             fontsize=11, loc="left")
ax.legend(fontsize=8, loc="lower right")
ax.grid(alpha=0.25)

# ---- panel 4: the power curve --------------------------------------------------------------
ax = fig.add_axes([0.50, 0.075, 0.40, 0.36])
b = MD[MD.arm == "base"].copy()
b = b.set_index("set").reindex(["US30I", "NQ", "US100", "XAU", "DEDUP 3", "ALL 4"])
xs = np.arange(len(b))
ax.bar(xs, b["mde80"], 0.55, color="#bbb", edgecolor="#666", label="MDE at 80% power")
ax.plot(xs, np.abs(b["mean"]), "o-", color="#d1495b", lw=1.8, ms=7,
        label="|measured edge| (negative on 5 of 6)")
ax.axhline(b["need_pf12"].mean(), color="#2a7fbf", ls="--", lw=1.6,
           label=f"what PF 1.2 requires ({b['need_pf12'].mean():.3f})")
ax.axhline(b["need_pf11"].mean(), color="#4fa04f", ls=":", lw=1.6,
           label=f"what PF 1.1 requires ({b['need_pf11'].mean():.3f})")
ax.axhline(0.1849, color="#000", ls="-.", lw=1.2, label="US30 alone (section 12): 0.185")
for i, (nm, r) in enumerate(b.iterrows()):
    ax.text(i, b["mde80"].iloc[i] + 0.012, f"n={int(r['n'])}", ha="center", fontsize=8)
ax.set_xticks(xs)
ax.set_xticklabels(b.index, fontsize=9)
ax.set_ylabel("ATR units per trade")
ax.set_title("Pooling DID buy the power — and PF 1.2 is now inside resolution, with nothing in it",
             fontsize=11, loc="left")
ax.legend(fontsize=8)
ax.grid(axis="y", alpha=0.25)

p = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "docs/ib/team_xmkt.png")
fig.savefig(p, dpi=118, facecolor="white")
print("wrote", p)
