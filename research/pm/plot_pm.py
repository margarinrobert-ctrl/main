"""Figures for the PM book."""
from __future__ import annotations
import os, sys
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pm_book as P

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    L = P.load(); R, A, av = P.panel(L)
    r23, _, n_ok = P.book(R, A, "equal")
    gcut = pd.Timestamp("2021-12-17")
    old = [c for c in R.columns if (R[c] != 0).idxmax() <= gcut]
    A11 = A.copy()
    for c in A11.columns:
        if c not in old: A11[c] = False
    r11, _, _ = P.book(R, A11, "equal")

    fig, ax = plt.subplots(1, 3, figsize=(16, 4.8))

    ax[0].plot(r23.index, r23.cumsum(), lw=1.6, color="#2b6cb0", label="all 23 legs (per-leg availability)")
    ax[0].plot(r11.index, r11.cumsum(), lw=1.4, color="#c05621", label="11 legs (published global cut)")
    ax[0].axvline(pd.Timestamp("2024-11-28"), color="grey", ls="--", lw=1)
    ax[0].text(pd.Timestamp("2024-11-28"), 1.0, " full book live", fontsize=7.5, rotation=90, va="bottom")
    ax[0].set(ylabel="cumulative % of entry price, 1 unit/trade",
              title="Fixing the construction: +0.16 Sharpe")
    ax[0].grid(alpha=.3); ax[0].legend(fontsize=8, loc="upper left")
    ax2 = ax[0].twinx(); ax2.plot(n_ok.index, n_ok.values, lw=.8, color="#2f855a", alpha=.55)
    ax2.set_ylabel("legs live", color="#2f855a", fontsize=8); ax2.tick_params(labelsize=7)

    st = P.stats(r23); pm = P.perm_dd(r23); p99 = float(np.percentile(pm, 99))
    tg = np.array([5, 10, 15, 20, 30], float); lev = tg / st["ann_ret"]
    ax[1].plot(tg, p99 * lev, "o-", color="#c53030", label="MC p99 drawdown")
    ax[1].plot(tg, st["maxdd"] * lev, "s--", color="#718096", label="realised drawdown")
    for t, l in zip(tg, lev):
        ax[1].annotate(f"{l:.1f}x", (t, p99*l), fontsize=7.5, textcoords="offset points",
                       xytext=(0, 7), ha="center")
    ax[1].set(xlabel="target return, %/yr", ylabel="drawdown, %",
              title="Return is a leverage decision (labels = leverage)")
    ax[1].grid(alpha=.3); ax[1].legend(fontsize=8)

    lc = R.corr().values; iu = np.triu_indices_from(lc, 1); rho = float(np.nanmean(lc[iu]))
    solo = [R[c][A[c]].mean()/R[c][A[c]].std()*np.sqrt(P.TDY) for c in R.columns
            if A[c].sum() > 60 and R[c][A[c]].std() > 0]
    s_bar = float(np.mean(solo))
    N = np.arange(2, 220)
    ax[2].plot(N, s_bar*np.sqrt(N)/np.sqrt(1+(N-1)*rho), color="#2b6cb0", lw=1.8, label="theory")
    ax[2].axhline(s_bar/np.sqrt(rho), color="#c53030", ls="--", lw=1.2,
                  label=f"ceiling {s_bar/np.sqrt(rho):.2f} (set by rho={rho:.3f})")
    ax[2].scatter([23], [st["sharpe"]], s=55, color="#2f855a", zorder=5, label="measured, 23 legs")
    ax[2].scatter([11], [P.stats(r11)["sharpe"]], s=45, color="#c05621", zorder=5, label="measured, 11")
    ax[2].set(xlabel="number of legs", ylabel="book Sharpe",
              title="More legs of this kind cannot pass ~1.9")
    ax[2].grid(alpha=.3); ax[2].legend(fontsize=8, loc="lower right")

    fig.suptitle("The profitability constraint is rho and leverage, not another parameter search",
                 fontsize=12)
    fig.tight_layout()
    p = os.path.join(HERE, "pm_book.png"); fig.savefig(p, dpi=150); plt.close(fig)
    print("wrote", p)


if __name__ == "__main__":
    main()
