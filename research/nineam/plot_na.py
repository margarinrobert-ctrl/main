"""Figures for the 09:00-range study. Palette: the validated categorical pair (slot 1 #2a78d6,
slot 2 #eb6834) with colour fixed to the ENTITY and never to rank. Where three blocks are shown
they get one panel each and a single hue, so no adjacent-pair separation question arises."""
from __future__ import annotations
import os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
C1, C2 = "#2a78d6", "#eb6834"
INK, MUT = "#1c1f24", "#6b7280"
plt.rcParams.update({"font.size": 9, "axes.edgecolor": "#c8cdd4", "axes.labelcolor": INK,
                     "text.color": INK, "xtick.color": MUT, "ytick.color": MUT,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "figure.facecolor": "white", "axes.facecolor": "white"})


def fig1():
    g = pd.read_csv(os.path.join(HERE, "n2_grid.csv"))
    cells = [("US30L15", "res", "US30 research\n2016-2022"),
             ("US30L15", "lock", "US30 holdout\n2023-2025"),
             ("US30I15", "res", "US30 forward\ndifferent provider")]
    axes_ = ["win", "buf", "side", "ema", "stop", "tgt", "flat"]
    fig, axs = plt.subplots(1, 3, figsize=(13.5, 6.2), sharey=True)
    for ax, (fd, bk, title) in zip(axs, cells):
        s = g[(g.feed == fd) & (g.block == bk)]
        labs, vals = [], []
        for a in axes_:
            m = s.groupby(a)["pct"].mean() * 100
            for k, v in m.items():
                labs.append(f"{a}={k}"); vals.append(v)
        y = np.arange(len(labs))
        col = [C1 if v > 0 else C2 for v in vals]
        ax.barh(y, vals, color=col, height=0.66)
        ax.set_yticks(y); ax.set_yticklabels(labs, fontsize=7)
        ax.axvline(0, color=INK, lw=1)
        ax.invert_yaxis()
        ax.set_title(title, fontsize=10, loc="left")
        ax.set_xlabel("marginal mean, bp of entry price / trade")
    fig.text(0.012, 0.015, "blue = positive, orange = negative. Every setting of every axis is "
             "negative on both blocks US30 did not choose, and only one setting of one axis "
             "(ema = fresh cross within 20 bars, +0.09 bp) is positive on the block it did.",
             fontsize=8.5, color=MUT)
    fig.suptitle("Every parameter, read by marginal average — US30, 16,200 declared cells",
                 fontsize=12.5, x=0.012, ha="left", y=0.985)
    fig.tight_layout(rect=(0, 0.045, 0.995, 0.945))
    fig.savefig(os.path.join(HERE, "fig1_marginals.png"), dpi=150)


def fig2():
    reads = ["ema13>48\nstate", "sma13>48\nstate", "wma13>48\nstate",
             "hull13>48\nstate", "vwma13>48\nstate", "fresh cross\n<= 5 bars"]
    here_ = [0.5604, 0.5334, 0.5451, 0.5512, 0.5553, 0.1156]      # US30L, N1.2
    donch = [0.826, np.nan, np.nan, np.nan, np.nan, 0.168]        # STUDY_V41 / V41 recency
    x = np.arange(len(reads)); w = 0.38
    fig, ax = plt.subplots(figsize=(9.2, 4.4))
    ax.bar(x - w / 2, here_, w, color=C1, label="09:00-range breakout (this study)")
    ax.bar(x + w / 2, donch, w, color=C2, label="Donchian-20 breakout (STUDY_V41)")
    ax.axhline(0.95, color=INK, lw=1, ls="--")
    ax.text(-0.35, 0.965, "0.95 — above this a confirmation is the trigger restated",
            ha="left", fontsize=8, color=INK)
    for xi, v in zip(x - w / 2, here_):
        ax.text(xi, v + 0.015, f"{v:.3f}", ha="center", fontsize=8, color=INK)
    for xi, v in zip(x + w / 2, donch):
        if np.isfinite(v):
            ax.text(xi, v + 0.015, f"{v:.3f}", ha="center", fontsize=8, color=INK)
    ax.set_xticks(x); ax.set_xticklabels(reads, fontsize=8)
    ax.set_ylim(0, 1.30); ax.set_ylabel("share of the trigger's OWN signal bars that pass")
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.legend(frameon=False, loc="upper right", fontsize=8, ncol=2,
              bbox_to_anchor=(1.0, 1.0))
    ax.set_title("The EMA cross binds on THIS trigger and not on a channel break", loc="left",
                 fontsize=12)
    ax.text(0, -0.28, "A range breakout clears a two-bar window from thirty minutes ago, which says "
            "nothing about a 48-bar average.\nIt is the first confirmation family measured here that "
            "is not the trigger restated. It is also worth nothing.",
            transform=ax.transAxes, fontsize=8, color=MUT)
    fig.tight_layout(rect=(0, 0.12, 1, 1))
    fig.savefig(os.path.join(HERE, "fig2_baserates.png"), dpi=150)


def fig3():
    g = pd.read_csv(os.path.join(HERE, "n2_grid.csv"))
    feeds = ["US30L15", "US100L15", "NQ15"]
    res = [100 * (g[(g.feed == f) & (g.block == "res")].pct > 0).mean() for f in feeds]
    lok = [100 * (g[(g.feed == f) & (g.block == "lock")].pct > 0).mean() for f in feeds]
    x = np.arange(len(feeds)); w = 0.38
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11.5, 4.4))
    a1.bar(x - w / 2, res, w, color=C1, label="research block")
    a1.bar(x + w / 2, lok, w, color=C2, label="holdout block")
    for xi, v in zip(x - w / 2, res):
        a1.text(xi, v + 1, f"{v:.1f}%", ha="center", fontsize=8)
    for xi, v in zip(x + w / 2, lok):
        a1.text(xi, v + 1, f"{v:.1f}%", ha="center", fontsize=8)
    a1.set_xticks(x); a1.set_xticklabels(feeds)
    a1.set_ylabel("share of the 16,200-cell grid that is profitable")
    a1.legend(frameon=False, fontsize=8)
    a1.set_title("Population first — a top row is the max of this many positive draws",
                 loc="left", fontsize=10)

    tops = {"US30L15": (0.0556, -0.0550, -0.0380), "US100L15": (0.1255, 0.0812, -0.0029),
            "NQ15": (0.1793, 0.2394, 0.0133)}
    for i, f in enumerate(feeds):
        r, l, pop = tops[f]
        a2.plot([0, 1], [r * 100, l * 100], "-o", color=C1 if l > 0 else C2, lw=2, ms=6)
        a2.text(1.03, l * 100, f" {f}", fontsize=8, va="center")
        a2.plot([1], [pop * 100], "s", color=MUT, ms=5)
    a2.axhline(0, color=INK, lw=1)
    a2.set_xticks([0, 1]); a2.set_xticklabels(["research top 1%", "the same cells, holdout"])
    a2.set_xlim(-0.15, 1.5)
    a2.set_ylabel("mean bp of entry price / trade")
    a2.set_title("Grey squares = the WHOLE population on the holdout", loc="left", fontsize=10)
    fig.suptitle("Selecting on research", fontsize=12, x=0.06, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(os.path.join(HERE, "fig3_population.png"), dpi=150)


def fig4():
    o = pd.read_csv(os.path.join(HERE, "n4_consensus.csv"))
    labels = [f"{r.feed}\n{r.block}" for r in o.itertuples()]
    fig, axs = plt.subplots(1, 3, figsize=(13, 4.2))
    x = np.arange(len(o))
    col = [C1 if v > 0 else C2 for v in o["pct"]]
    axs[0].bar(x, o["pct"] * 100, color=col)
    axs[0].errorbar(x, o["pct"] * 100, yerr=o["mde"] * 100, fmt="none", ecolor=INK, capsize=4, lw=1)
    axs[0].axhline(0, color=INK, lw=1)
    axs[0].set_xticks(x); axs[0].set_xticklabels(labels, fontsize=8)
    axs[0].set_ylabel("bp / trade")
    axs[0].set_title("delivered edge, with its own MDE as the bar", loc="left", fontsize=10)

    axs[1].bar(x - 0.2, o["p_ent"], 0.38, color=C1, label="vs a random ENTRY")
    axs[1].bar(x + 0.2, o["p_gate"], 0.38, color=C2, label="vs a random GATE")
    axs[1].axhline(0.05, color=INK, lw=1, ls="--")
    axs[1].set_xticks(x); axs[1].set_xticklabels(labels, fontsize=8)
    axs[1].set_ylim(0, 1.05); axs[1].set_ylabel("p")
    axs[1].legend(frameon=False, fontsize=8)
    axs[1].set_title("neither null is cleared anywhere", loc="left", fontsize=10)

    axs[2].bar(x, o["boot_le0"], color=[C2 if v > 0.5 else C1 for v in o["boot_le0"]])
    axs[2].axhline(0.05, color=INK, lw=1, ls="--")
    axs[2].set_xticks(x); axs[2].set_xticklabels(labels, fontsize=8)
    axs[2].set_ylim(0, 1.05); axs[2].set_ylabel("P(mean <= 0), day-block bootstrap")
    axs[2].set_title("and it does not clear zero either", loc="left", fontsize=10)
    fig.suptitle("The marginal-consensus cell, chosen on US30 research, read once on each other block",
                 fontsize=12, x=0.06, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(os.path.join(HERE, "fig4_consensus.png"), dpi=150)


if __name__ == "__main__":
    fig1(); fig2(); fig3(); fig4()
    print("wrote 4 figures")
