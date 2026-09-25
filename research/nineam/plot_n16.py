"""Four panels: the kernel artifact, the transfer, the population, and the 30-second arbiter."""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402
import numpy as np                # noqa: E402
import pandas as pd               # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

K = pd.read_csv(os.path.join(HERE, "n16_kernel.csv"))
R = pd.read_csv(os.path.join(HERE, "n17_read.csv"))
P = pd.read_csv(os.path.join(HERE, "n16_trials_intraday_sharpe.csv"))
A = pd.read_csv(os.path.join(HERE, "n18_arbiter.csv"))

fig, ax = plt.subplots(2, 2, figsize=(15.5, 10.4))
fig.suptitle("Optuna and vectorbt on the 09:00-range breakout, US30 "
             "(objective: daily zero-filled Sharpe / Sortino)", fontsize=13, y=0.985)

# 1 the kernel artifact
a = ax[0, 0]
K2 = K[K.be_pts > 0].copy()
lab = [f"{int(r.be_pts)}/{int(r.be_off)}" for _, r in K2.iterrows()]
x = np.arange(len(K2))
a.bar(x - 0.2, K2.pts_fix0, 0.4, label="as published (stop fills at its level)", color="#c0392b")
a.bar(x + 0.2, K2.pts_fix1, 0.4, label="corrected (worse of level and open)", color="#2c6fbb")
a.set_xticks(x); a.set_xticklabels(lab, fontsize=8)
a.set_xlabel("breakeven arms at / secures (points)"); a.set_ylabel("points per trade")
a.set_title("1  the ratchet artifact the search found in 1,000 trials", fontsize=11)
a.axhline(0, color="k", lw=0.6); a.legend(fontsize=8); a.grid(alpha=0.25)
for i, (_, r) in enumerate(K2.iterrows()):
    a.text(i, max(r.pts_fix0, r.pts_fix1) + 0.3, f"{r.through_share:.0%}",
           ha="center", fontsize=7, color="#c0392b")
a.text(0.02, 0.80, "% = share of trades filling THROUGH the market", transform=a.transAxes,
       fontsize=7.5, va="top", color="#c0392b")

# 2 transfer
a = ax[0, 1]
order = ["intraday_sharpe", "intraday_sortino", "intraday_retdd",
         "free_sharpe", "free_sortino", "free_retdd", "DEFAULT (shipped)", "USER (their inputs)"]
blocks = [("A_research", "US30L", "#2c6fbb"), ("B_holdout", "US30L", "#e67e22"),
          ("C_forward", "US30I", "#16a085")]
w = 0.26
for j, (b, fd, col) in enumerate(blocks):
    v = [float(R[(R.arm == o) & (R.block == b) & (R.feed == fd)].sharpe.iloc[0])
         if len(R[(R.arm == o) & (R.block == b) & (R.feed == fd)]) else np.nan for o in order]
    a.bar(np.arange(len(order)) + (j - 1) * w, v, w, label=f"{b} ({fd})", color=col)
a.set_xticks(np.arange(len(order)))
a.set_xticklabels([o.replace(" (shipped)", "").replace(" (their inputs)", "") for o in order],
                  rotation=28, ha="right", fontsize=8)
a.axhline(0, color="k", lw=0.6)
a.set_ylabel("Sharpe, daily zero-filled")
a.set_title("2  every finalist inverts; the un-searched default does not", fontsize=11)
a.legend(fontsize=8); a.grid(alpha=0.25)

# 3 population
a = ax[1, 0]
k = P[P.ok]
a.scatter(k.r_sharpe, k.h_sharpe, s=7, alpha=0.35, color="#555", label=f"{len(k)} scorable trials")
q = k.nlargest(max(1, len(k) // 100), "r_sharpe")
a.scatter(q.r_sharpe, q.h_sharpe, s=22, color="#c0392b", label="research top 1%")
a.axhline(0, color="k", lw=0.6); a.axvline(0, color="k", lw=0.6)
sp = k.r_sharpe.corr(k.h_sharpe, method="spearman")
pe = k.r_sharpe.corr(k.h_sharpe)
a.set_xlabel("research Sharpe"); a.set_ylabel("holdout Sharpe")
a.set_title(f"3  intraday_sharpe population: Pearson {pe:+.3f}, "
            f"Spearman {sp:+.3f}", fontsize=11)
a.legend(fontsize=8); a.grid(alpha=0.25)

# 4 the arbiter
a = ax[1, 1]
A2 = A.dropna(subset=["stop_first"]).copy()
lab = [f"{int(r.stop_pts)}/{int(r.tgt_pts)}" for _, r in A2.iterrows()]
x = np.arange(len(A2))
a.bar(x, A2.stop_first, 0.55, color="#c0392b", label="stop came first")
a.bar(x, A2.tgt_first, 0.55, bottom=A2.stop_first, color="#2c6fbb", label="target came first")
a.axhline(0.5, color="k", lw=0.8, ls="--")
a2 = a.twinx()
a2.plot(x, A2.amb_share, "o-", color="#111", lw=1.4, ms=5, label="ambiguous share (right)")
a2.set_ylabel("share of trades ambiguous on a 15m bar")
a.set_xticks(x); a.set_xticklabels(lab, rotation=0, fontsize=8)
a.set_xlabel("stop / target, points"); a.set_ylabel("of the ambiguous trades")
a.set_title("4  the 30-second feed settles which barrier came first", fontsize=11)
a.legend(fontsize=8, loc="lower left"); a2.legend(fontsize=8, loc="upper right")
a.grid(alpha=0.2)

fig.tight_layout(rect=(0, 0, 1, 0.965))
out = os.path.join(HERE, "fig5_optuna_vbt.png")
fig.savefig(out, dpi=125)
print("wrote", out)
