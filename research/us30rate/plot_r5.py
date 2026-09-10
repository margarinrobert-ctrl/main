"""Figure for section 16: the two arms disagree by which test you ask."""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ARMS = ["base", "+adx<=20", "+ema align", "+slow 34>89"]
AC = {"base": "#718096", "+adx<=20": "#c05621", "+ema align": "#2b6cb0",
      "+slow 34>89": "#2f855a"}


def main():
    O = pd.read_csv(os.path.join(HERE, "r5_oos.csv"))
    W = pd.read_csv(os.path.join(HERE, "r5_wf.csv"))
    C = pd.read_csv(os.path.join(HERE, "r5_corr.csv"), index_col=0)
    fig, ax = plt.subplots(1, 3, figsize=(15.5, 4.8))

    # 1. per-trade edge with its own MDE as the error bar
    blocks = ["A_research", "B_holdout", "C_forward"]
    x = np.arange(len(blocks)); w = 0.2
    for k, a in enumerate(ARMS):
        s = O[O.arm == a].set_index("block").reindex(blocks)
        ax[0].bar(x + (k - 1.5) * w, s.pts, w, color=AC[a], label=a)
        ax[0].errorbar(x + (k - 1.5) * w, s.pts, yerr=s.mde, fmt="none", ecolor="k",
                       elinewidth=.9, capsize=2.5)
    ax[0].axhline(0, color="k", lw=1.2)
    ax[0].set_xticks(x); ax[0].set_xticklabels(["research", "holdout", "forward (ISO)"])
    ax[0].set(ylabel="points per trade", title="Every arm is inside its own MDE (bars = MDE)")
    ax[0].grid(alpha=.3, axis="y"); ax[0].legend(fontsize=8)

    # 2. walk-forward cumulative, constants fixed
    for a in ARMS:
        ax[1].plot(W.year, W[a].cumsum(), "o-", color=AC[a], label=a)
    ax[1].axhline(0, color="k", lw=1.2)
    ax[1].set(xlabel="fold (year)", ylabel="cumulative points, constants FIXED",
              title="...and here the ADX arm wins, reversing the null test")
    ax[1].grid(alpha=.3); ax[1].legend(fontsize=8)

    # 3. correlation
    lab = ARMS + ["always-long"]
    Cm = C.reindex(index=lab, columns=lab).to_numpy(float)
    im = ax[2].imshow(Cm, cmap="RdBu_r", vmin=-1, vmax=1)
    ax[2].set_xticks(range(len(lab))); ax[2].set_xticklabels(lab, rotation=35, ha="right",
                                                             fontsize=8)
    ax[2].set_yticks(range(len(lab))); ax[2].set_yticklabels(lab, fontsize=8)
    for i in range(len(lab)):
        for j in range(len(lab)):
            ax[2].text(j, i, f"{Cm[i, j]:+.2f}", ha="center", va="center", fontsize=7.5,
                       color="white" if abs(Cm[i, j]) > .6 else "black")
    ax[2].set_title("Daily P&L: the two conditions are distinct (+0.46)")
    fig.colorbar(im, ax=ax[2], fraction=.046)

    fig.suptitle("US30 07:00-11:00 -- neither arm dominates; they disagree by which test you ask",
                 fontsize=11.5)
    fig.tight_layout()
    p = os.path.join(HERE, "rate_battery.png")
    fig.savefig(p, dpi=150); plt.close(fig)
    print("wrote", p)


if __name__ == "__main__":
    main()
