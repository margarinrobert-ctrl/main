"""Figures for the S10 battery. Two sheets: out-of-sample + walk-forward, then MC + correlations."""
from __future__ import annotations

import os
import pickle
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "s10_results.pkl"), "rb") as fh:
    R = pickle.load(fh)

ARMS = ["base", "+adx<=20", "+ema align", "+both", "conventional"]
COL = {"base": "#7a7a7a", "+adx<=20": "#1f6fb4", "+ema align": "#2e8b57",
       "+both": "#8b5cf6", "conventional": "#c0392b"}
BLOCKS = [("A_research", "A — research (US30L, to 2023)"),
          ("B_holdout", "B — holdout (US30L, 2023-25)"),
          ("C_forward", "C — forward (US30_ISO, different provider)")]


def sheet1():
    fig = plt.figure(figsize=(15, 10))
    gs = fig.add_gridspec(2, 3, height_ratios=[1.15, 1], hspace=0.32, wspace=0.22)
    for j, (bn, title) in enumerate(BLOCKS):
        ax = fig.add_subplot(gs[0, j])
        for a in ARMS:
            if (a, bn) not in R["curves"]:
                continue
            ts, eq = R["curves"][(a, bn)]
            ax.plot(ts, eq, lw=1.7 if a == "+adx<=20" else 1.1,
                    color=COL[a], label=a, alpha=1.0 if a == "+adx<=20" else 0.8,
                    zorder=3 if a == "+adx<=20" else 2)
        ax.axhline(0, color="k", lw=0.8)
        ax.set_title(title, fontsize=10)
        ax.set_ylabel("cumulative points, 1 unit" if j == 0 else "")
        ax.grid(alpha=0.3); ax.tick_params(axis="x", rotation=30, labelsize=8)
        if j == 0:
            ax.legend(fontsize=8, loc="upper left")

    W = R["wf"]
    ax = fig.add_subplot(gs[1, :2])
    x = np.arange(len(W)); w = 0.15
    for i, a in enumerate(ARMS):
        ax.bar(x + (i - 2) * w, W[a].fillna(0), w, color=COL[a], label=a,
               edgecolor="white", linewidth=0.4)
    ax.axhline(0, color="k", lw=0.9)
    ax.set_xticks(x); ax.set_xticklabels(W["year"])
    ax.set_title("Walk-forward, constants FIXED — points per trade by calendar year\n"
                 "(the rule is derived, not fitted, so a fixed arm is the honest test)",
                 fontsize=10)
    ax.set_ylabel("points / trade"); ax.grid(alpha=0.3, axis="y")
    ax.legend(fontsize=8, ncol=5, loc="upper left")

    ax = fig.add_subplot(gs[1, 2])
    names = ARMS + ["re-chosen", "random arm"]
    means = [W[n].dropna().mean() for n in names]
    pos = [f"{int((W[n].dropna() > 0).sum())}/{len(W[n].dropna())}" for n in names]
    cols = [COL.get(n, "#d18f00") for n in names]
    b = ax.barh(range(len(names)), means, color=cols, edgecolor="white")
    ax.set_yticks(range(len(names))); ax.set_yticklabels(names, fontsize=9)
    ax.invert_yaxis(); ax.axvline(0, color="k", lw=0.9)
    for i, (m, p) in enumerate(zip(means, pos)):
        ax.text(m + (0.4 if m >= 0 else -0.4), i, p, va="center",
                ha="left" if m >= 0 else "right", fontsize=8)
    ax.set_title("mean over 8 folds, with folds-positive", fontsize=10)
    ax.set_xlabel("points / trade"); ax.grid(alpha=0.3, axis="x")

    fig.suptitle("US30 07:00–11:00 NY, flat at 11:00 · Donchian 20 long, 50-pt stop / 150-pt target\n"
                 "Out-of-sample across two providers, and a fixed-constant walk-forward",
                 fontsize=12, y=0.985)
    p = os.path.join(HERE, "s10_oos_walkforward.png")
    fig.savefig(p, dpi=125, bbox_inches="tight"); print("wrote", p)


def sheet2():
    mc = R["mc"]
    fig = plt.figure(figsize=(15, 10))
    gs = fig.add_gridspec(2, 4, hspace=0.35, wspace=0.28)

    panels = [("boot", "Bootstrap — the EDGE\n(day-block, 4,000 draws)", "mean daily points"),
              ("perm", "Permutation — the PATH\n(4,000 reshuffles)", "max drawdown, points"),
              ("exec", "Execution perturbation\n(slip U(0,2x), cost U(0.5x,2x))", "points / trade"),
              ("jit", "Price jitter, ADX/EMA/ATR/Donchian\nALL recomputed", "points / trade")]
    for j, (key, title, xl) in enumerate(panels):
        ax = fig.add_subplot(gs[0, j])
        for bn, c in (("A_research", "#1f6fb4"), ("B_holdout", "#d18f00")):
            v = mc[bn][key]
            ax.hist(v, bins=45, alpha=0.55, color=c, label=bn, density=True)
        if key == "perm":
            for bn, c in (("A_research", "#1f6fb4"), ("B_holdout", "#d18f00")):
                ax.axvline(mc[bn]["realised_dd"], color=c, ls="--", lw=1.8)
            ax.text(0.02, 0.95, "dashed = realised", transform=ax.transAxes, fontsize=7,
                    va="top")
        else:
            ax.axvline(0, color="k", lw=1.0)
            for bn, c in (("A_research", "#1f6fb4"), ("B_holdout", "#d18f00")):
                ax.axvline(mc[bn]["realised"], color=c, ls="--", lw=1.5)
        ax.set_title(title, fontsize=9.5); ax.set_xlabel(xl, fontsize=8)
        ax.grid(alpha=0.3); ax.tick_params(labelsize=7)
        if j == 0:
            ax.legend(fontsize=7)

    mats = [(R["corr_arms"], "a. between the ARMS (daily P&L, research)\n"
                             "one strategy in five hats?", "coolwarm", -1, 1),
            (R["corr_cond"], "b. between the CONDITIONS on the SIGNAL BARS\n"
                             "is the pool duplicating?", "coolwarm", -1, 1)]
    for j, (Mx, title, cm, lo, hi) in enumerate(mats):
        ax = fig.add_subplot(gs[1, j * 2:(j + 1) * 2 - (1 if j else 0)] if j == 0
                             else gs[1, 2])
        im = ax.imshow(Mx.to_numpy(), cmap=cm, vmin=lo, vmax=hi)
        ax.set_xticks(range(len(Mx))); ax.set_yticks(range(len(Mx)))
        ax.set_xticklabels(Mx.columns, rotation=40, ha="right", fontsize=7.5)
        ax.set_yticklabels(Mx.index, fontsize=7.5)
        for a in range(len(Mx)):
            for b in range(len(Mx)):
                v = Mx.to_numpy()[a, b]
                ax.text(b, a, f"{v:.2f}", ha="center", va="center", fontsize=7,
                        color="white" if abs(v) > 0.55 else "black")
        ax.set_title(title, fontsize=9.5)
        fig.colorbar(im, ax=ax, fraction=0.046)

    C3 = R["corr_block"].reindex(ARMS)
    ax = fig.add_subplot(gs[1, 3])
    im = ax.imshow(C3.to_numpy(), cmap="RdYlGn", vmin=-12, vmax=12)
    ax.set_xticks(range(C3.shape[1])); ax.set_yticks(range(len(C3)))
    ax.set_xticklabels([c.replace("_", "\n") for c in C3.columns], fontsize=7.5)
    ax.set_yticklabels(C3.index, fontsize=7.5)
    for a in range(C3.shape[0]):
        for b in range(C3.shape[1]):
            v = C3.to_numpy()[a, b]
            if np.isfinite(v):
                ax.text(b, a, f"{v:+.1f}", ha="center", va="center", fontsize=8)
    ax.set_title("c. points/trade by ARM x BLOCK\nSpearman A→B +0.90, A→C −0.40, B→C −0.70",
                 fontsize=9.5)
    fig.colorbar(im, ax=ax, fraction=0.046)

    fig.suptitle("Monte Carlo (edge, path, execution, data) and three correlation matrices\n"
                 "`+adx<=20` on US30 07:00–11:00, 50/150, flat at 11:00", fontsize=12, y=0.985)
    p = os.path.join(HERE, "s10_montecarlo_correlations.png")
    fig.savefig(p, dpi=125, bbox_inches="tight"); print("wrote", p)


sheet1()
sheet2()
