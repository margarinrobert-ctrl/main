"""Figures for sections 14-15: the power ladder and the arm inversion."""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
BLK = ["A research", "B holdout", "C forward ISO"]
CB = {"A research": "#2b6cb0", "B holdout": "#c05621", "C forward ISO": "#2f855a"}


def fig1():
    d = pd.read_csv(os.path.join(HERE, "r1_ladder.csv"))
    r = d[(d.block == "A research") & (d.n > 0)]
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.6))

    for arm, m in [("base", "o"), ("+adx<=20", "s"), ("+ema align", "^")]:
        s = r[r.arm == arm].sort_values("ch")
        ax[0].plot(s.ch, s.per_yr, m + "-", label=arm)
        ax[1].plot(s.ch, s.pts / s.mde, m + "-", label=arm)
    ax[0].set(xlabel="Donchian entry channel (bars)", ylabel="trades per year",
              title="The rate rises as the channel shortens")
    ax[0].grid(alpha=.3); ax[0].legend(fontsize=8)

    ax[1].axhline(1.0, color="k", ls="--", lw=1)
    ax[1].text(30, 1.03, "detectable at 80% power", fontsize=7.5)
    ax[1].axhline(0, color="grey", lw=.8)
    ax[1].set(xlabel="Donchian entry channel (bars)",
              ylabel="delivered edge / its own MDE",
              title="...and the edge falls faster: no rung is detectable")
    ax[1].grid(alpha=.3); ax[1].legend(fontsize=8)

    s = r[(r.arm == "+adx<=20")].sort_values("ch")
    ax[2].plot(s.ch, s.yrs_need, "s-", color="#c05621")
    for _, row in s.iterrows():
        ax[2].annotate(f"{row.yrs_need:.0f}y", (row.ch, row.yrs_need), fontsize=7.5,
                       textcoords="offset points", xytext=(0, 6), ha="center")
    ax[2].axhline(8.7, color="k", ls="--", lw=1)
    ax[2].text(30, 11, "8.7 years of US30 on disk", fontsize=7.5)
    ax[2].set(xlabel="Donchian entry channel (bars)", ylabel="years to verify the delivered effect",
              title="Shortening the channel makes it slower, not faster")
    ax[2].grid(alpha=.3)

    fig.suptitle("US30 07:00-11:00 -- the trade rate is not a lever on detectability "
                 "(research block)", fontsize=11.5)
    fig.tight_layout()
    p = os.path.join(HERE, "rate_power_ladder.png")
    fig.savefig(p, dpi=150); plt.close(fig)
    return p


def fig2():
    c = pd.read_csv(os.path.join(HERE, "r2_control.csv"))
    f4 = pd.read_csv(os.path.join(HERE, "r4_fastema.csv"))
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.6))

    for i, arm in enumerate(["+adx<=20", "+ema align"]):
        s = c[c.arm == arm]
        for b in BLK:
            sb = s[s.block == b].sort_values("ch")
            ax[i].plot(sb.ch, sb.pts - sb.null_med, "o-", color=CB[b], label=b)
        ax[i].axhline(0, color="k", lw=1.2)
        won = int((s.pts > s.null_med).sum())
        ax[i].set(xlabel="Donchian entry channel (bars)",
                  ylabel="edge over a random gate of the SAME selectivity (pts/trade)",
                  title=f"{arm}   beats its own null in {won} of {len(s)}")
        ax[i].grid(alpha=.3); ax[i].legend(fontsize=8)
    lo = min(ax[0].get_ylim()[0], ax[1].get_ylim()[0])
    hi = max(ax[0].get_ylim()[1], ax[1].get_ylim()[1])
    ax[0].set_ylim(lo, hi); ax[1].set_ylim(lo, hi)

    lbl = ["align 13>34>89", "slow 34>89", "fast 13>34"]
    x = np.arange(len(lbl)); w = 0.26
    for k, b in enumerate(BLK):
        v = [f4[(f4.reading == r) & (f4.block == b)].delta.mean() for r in lbl]
        ax[2].bar(x + (k - 1) * w, v, w, color=CB[b], label=b)
    ax[2].axhline(0, color="k", lw=1.2)
    ax[2].set_xticks(x); ax[2].set_xticklabels(lbl, fontsize=8.5)
    ax[2].set(ylabel="mean delta over the same-rung base (pts/trade)",
              title="The fast EMA is the coin flip (mean over 6 rungs)")
    ax[2].grid(alpha=.3, axis="y"); ax[2].legend(fontsize=8)

    fig.suptitle("The arm ranking inverts once the channel is varied -- and the promoted "
                 "condition is one inequality", fontsize=11.5)
    fig.tight_layout()
    p = os.path.join(HERE, "rate_arm_inversion.png")
    fig.savefig(p, dpi=150); plt.close(fig)
    return p


if __name__ == "__main__":
    for p in (fig1(), fig2()):
        print("wrote", p)
