#!/usr/bin/env python3
"""Stitched out-of-sample equity chart for the walk-forward runs (see walkforward_sam.py)."""
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from walkforward_sam import (load_days, build_signals, run, sharpe,
                             W_MAX, IS_LEN, OOS_LEN)

CSV = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else "wf_equity.png"

d = load_days(CSV)
strength, samneg = build_signals(d)
n = len(d)
n0 = int(np.argmax(~np.isnan(strength)))

rets = {}
for W in range(1, W_MAX + 1):
    tgt = np.where(np.isnan(strength), np.nan, samneg[:, W].astype(float))
    rets[f"W{W}"], _ = run(tgt, d)
rets["ENS"], _ = run(strength, d)
bh = np.zeros(n)
bh[:-1] = d["px"].to_numpy()[1:] / d["px"].to_numpy()[:-1] - 1.0

# rolling walk-forward, process A picks (refit best single W by IS Sharpe)
oos_idx, picksA = [], []
start = n0
single = {k: v for k, v in rets.items() if k != "ENS"}
while start + IS_LEN + OOS_LEN <= n - 1:
    lo, hi = start, start + IS_LEN
    best = max(single, key=lambda k: sharpe(single[k][lo:hi]))
    picksA.append(best)
    oos_idx.append((hi, hi + OOS_LEN))
    start += OOS_LEN

sA = np.concatenate([single[p][a:b] for p, (a, b) in zip(picksA, oos_idx)])
sB = np.concatenate([rets["ENS"][a:b] for a, b in oos_idx])
sH = np.concatenate([bh[a:b] for a, b in oos_idx])
dates = pd.to_datetime(pd.concat([d["date"][a:b] for a, b in oos_idx]).to_numpy())

eq = lambda x: np.cumprod(1 + x)

# palette (validated): slot1 blue = ensemble (hero), slot2 aqua = refit, gray = benchmark
BLUE, AQUA, GRAY = "#2a78d6", "#1baf7a", "#8a8983"
INK, INK2 = "#1a1a19", "#6b6a63"

fig, ax = plt.subplots(figsize=(10.5, 5.6), dpi=200)
fig.patch.set_facecolor("#fcfcfb"); ax.set_facecolor("#fcfcfb")

ax.plot(dates, eq(sH), color=GRAY, lw=1.6, ls=(0, (4, 3)), zorder=2)
ax.plot(dates, eq(sA), color=AQUA, lw=2.0, zorder=3)
ax.plot(dates, eq(sB), color=BLUE, lw=2.4, zorder=4)

# fold boundaries (recessive)
for a, _ in oos_idx[1:]:
    ax.axvline(pd.to_datetime(d["date"][a]), color="#e4e3dd", lw=0.8, zorder=1)

# direct labels at line ends
for y, txt, c in [(eq(sB)[-1], f"Fixed ensemble W2–30\nSR 0.73 · maxDD −25%", BLUE),
                  (eq(sA)[-1], f"Refit best single W\nSR 0.34 · maxDD −31%", AQUA),
                  (eq(sH)[-1], f"Buy & hold\nSR 0.72 · maxDD −36%", GRAY)]:
    ax.annotate(txt, xy=(dates[-1], y), xytext=(8, 0), textcoords="offset points",
                va="center", ha="left", fontsize=8.5, color=c, fontweight="bold")

ax.set_title("SAM-Best walk-forward — stitched out-of-sample equity",
             loc="left", fontsize=13, color=INK, fontweight="bold", pad=14)
ax.text(0, 1.015, "Rolling IS = 756 d, OOS = 126 d, 11 folds · NAS100 30 m data 2016–2025 · "
        "2 bps/side, gross of financing · fold boundaries in light gray",
        transform=ax.transAxes, fontsize=8.5, color=INK2)

ax.set_ylabel("Equity (indexed to 1.0 at first OOS day)", fontsize=9, color=INK2)
ax.yaxis.set_major_formatter(lambda v, _: f"{v:.1f}×")
ax.xaxis.set_major_locator(mdates.YearLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
ax.tick_params(colors=INK2, labelsize=8.5, length=0)
ax.grid(axis="y", color="#e4e3dd", lw=0.7)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.spines["bottom"].set_color("#d0cfc7")
ax.margins(x=0.01)
ax.legend(["Buy & hold (same OOS days)", "A: refit best single W per fold",
           "B: fixed plateau ensemble W2–30"],
          loc="upper left", frameon=False, fontsize=8.5, labelcolor=INK)

plt.subplots_adjust(right=0.82, top=0.86, bottom=0.09, left=0.075)
plt.savefig(OUT, facecolor=fig.get_facecolor(), bbox_inches="tight")
print("saved", OUT)
