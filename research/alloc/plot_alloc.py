"""Equity curves for the walk-forward books, at matched volatility."""
from __future__ import annotations

import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import alloccore as C  # noqa: E402
from run_a2 import prep, ALL  # noqa: E402
from run_a3 import wf, MINHIST  # noqa: E402
from run_a4 import wf_select, topk  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    X, span, use, cut = prep()
    base = wf(X, span, ALL["equal"])
    idx = X.index[MINHIST:MINHIST + len(base)]
    sd = base.std(ddof=1)
    arms = {"all 11, equal": base,
            "top 5 by train Sharpe, equal": wf_select(X, span, topk(5), ALL["equal"]),
            "top 5, risk parity": wf_select(X, span, topk(5), ALL["riskparity"]),
            "all 11, risk parity": wf(X, span, ALL["riskparity"])}
    rg = np.random.default_rng(11)
    rnd = [wf(X, span, lambda Z, r=rg: r.dirichlet(np.ones(Z.shape[1]))) for _ in range(60)]

    fig, ax = plt.subplots(2, 1, figsize=(11, 9), sharex=True,
                           gridspec_kw=dict(height_ratios=[3, 2]))
    for d in rnd:
        ax[0].plot(idx, np.cumsum(d[:len(idx)] * sd / d.std(ddof=1)), color="0.85", lw=0.6, zorder=1)
    ax[0].plot([], [], color="0.85", lw=0.6, label="random allocator (60 draws)")
    for nm, d in arms.items():
        ax[0].plot(idx, np.cumsum(d[:len(idx)] * sd / d.std(ddof=1)), lw=1.6, label=nm, zorder=3)
    ax[0].set_title("Walk-forward books, scaled to the equal-weight book's own volatility\n"
                    "(weights and legs re-chosen inside every training window)")
    ax[0].set_ylabel("cumulative % of entry price, one unit per leg")
    ax[0].legend(fontsize=8, loc="upper left")
    ax[0].grid(alpha=0.3)

    for nm, d in list(arms.items())[1:]:
        z = np.cumsum(d[:len(idx)] * sd / d.std(ddof=1) - base[:len(idx)])
        ax[1].plot(idx, z, lw=1.4, label=nm)
    ax[1].axhline(0, color="k", lw=0.8)
    ax[1].set_title("cumulative difference against the all-legs equal-weight book, at matched volatility")
    ax[1].set_ylabel("cumulative excess")
    ax[1].legend(fontsize=8, loc="upper left")
    ax[1].grid(alpha=0.3)
    fig.tight_layout()
    p = os.path.join(HERE, "alloc_curves.png")
    fig.savefig(p, dpi=130)
    print("wrote", p)


if __name__ == "__main__":
    main()
