import os, sys
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vstoch as V

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTE, GRID = "#1c1f24", "#4a5058", "#8b929c", "#e6e9ed"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#c8ccd2",
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "figure.facecolor": "white", "axes.facecolor": "white"})

D = V.build("NQ", 15)
lo, sh, K, Dv = V.triggers(D)
r = D["blk"] == 0
pop = r & D["rth"] & np.isfinite(D["vwap"]) & np.isfinite(K)

fig = plt.figure(figsize=(15.4, 11.4))
gs = fig.add_gridspec(3, 2, hspace=0.52, wspace=0.26,
                      left=0.075, right=0.975, top=0.885, bottom=0.105)

fig.text(0.075, 0.965, "VWAP + Stochastic + ATR on NQ 15m", fontsize=21, weight="bold", color=INK)
fig.text(0.075, 0.936, "Research block 2022-12-26 to 2024-11-28, MNQ costs.  31,752 declared cells; "
                       "the locked block was read once.", fontsize=11.5, color=INK2)
fig.text(0.075, 0.913, "Verdict: the two indicators are one reading, and the trigger does not beat a coin flip.",
         fontsize=11.5, color=ORANGE, weight="bold")

# ---------------- 1. the redundancy scatter
ax = fig.add_subplot(gs[0, 0])
idx = np.flatnonzero(pop)
s = np.random.default_rng(1).choice(idx, size=min(9000, len(idx)), replace=False)
ax.scatter(K[s], D["vwap_dist"][s], s=2.5, alpha=0.10, color=MUTE, linewidths=0, rasterized=True)
lm = lo & pop
ax.scatter(K[lm], D["vwap_dist"][lm], s=13, color=BLUE, alpha=.85, linewidths=0, label="long trigger")
sm = sh & pop
ax.scatter(K[sm], D["vwap_dist"][sm], s=13, color=ORANGE, alpha=.85, linewidths=0, label="short trigger")
ax.axhline(0, color=INK2, lw=1.1, ls="--")
cc = np.corrcoef(K[pop], np.nan_to_num(D["vwap_dist"][pop], nan=0))[0, 1]
ax.set_title("They are the same reading", fontsize=13, weight="bold", color=INK, loc="left", pad=9)
ax.set_xlabel("Stochastic %K"); ax.set_ylabel("(close - VWAP) / ATR")
ax.set_ylim(-6, 6)
ax.text(0.03, 0.05, f"corr = {cc:+.3f}", transform=ax.transAxes, fontsize=13, weight="bold",
        color=ORANGE, va="bottom",
        bbox=dict(boxstyle="round,pad=0.42", fc="white", ec=ORANGE, lw=1.1))
ax.legend(frameon=False, fontsize=9, loc="upper left", markerscale=1.6)
ax.grid(alpha=.25, color=GRID)

# ---------------- 2. base rates
ax = fig.add_subplot(gs[0, 1])
names = ["long:\nclose < VWAP", "short:\nclose > VWAP", "short:\nabove & rising"]
trg_ = [lo, sh, sh]
cond = [D["c"] < D["vwap"], D["c"] > D["vwap"],
        (D["c"] > D["vwap"]) & (D["vwap_slope"] > 0)]
sig_r, gen_r = [], []
for t_, c_ in zip(trg_, cond):
    m = t_ & pop
    sig_r.append(100 * np.nanmean(c_[m])); gen_r.append(100 * np.nanmean(c_[pop]))
x = np.arange(3); w = 0.36
ax.bar(x - w/2, gen_r, w, color=MUTE, label="all bars", zorder=3)
ax.bar(x + w/2, sig_r, w, color=BLUE, label="the trigger's own bars", zorder=3)
for i, (a, b) in enumerate(zip(gen_r, sig_r)):
    ax.text(i + w/2, b + 2, f"{b:.1f}%", ha="center", fontsize=10, weight="bold", color=BLUE)
    ax.text(i - w/2, a + 2, f"{a:.1f}%", ha="center", fontsize=9, color=INK2)
ax.set_xticks(x); ax.set_xticklabels(names, fontsize=9.5)
ax.set_ylabel("pass rate"); ax.set_ylim(0, 132)
ax.set_title("The VWAP condition removes almost nothing", fontsize=13, weight="bold",
             color=INK, loc="left", pad=9)
ax.legend(frameon=False, fontsize=9, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.02))
ax.grid(axis="y", alpha=.25, color=GRID); ax.set_axisbelow(True)

# ---------------- 3. trigger vs random entry
T = pd.read_csv("results/vstoch/trigger_vs_random.csv")
ax = fig.add_subplot(gs[1, :])
lab = [f"{a}\n{b:g}N / {c:g}R / {d:g}b" for a, b, c, d in zip(T.side, T.stop, T.tp, T.hold)]
x = np.arange(len(T)); w = 0.36
ax.bar(x - w/2, T.pct, w, color=[BLUE if s == "LONG" else ORANGE for s in T.side],
       label="the rule", zorder=3)
ax.bar(x + w/2, T.ctl_pct, w, color=MUTE, label="random entry, identical geometry", zorder=3)
ax.axhline(0, color=INK2, lw=1)
for i, p in enumerate(T.p_pct):
    ax.text(i, max(T.pct[i], T.ctl_pct[i]) + 0.006, f"p {p:.2f}", ha="center", fontsize=9, color=INK2)
ax.set_xticks(x); ax.set_xticklabels(lab, fontsize=9)
ax.set_ylabel("% of entry price per trade")
ax.set_title("The trigger against a coin flip with the same stop, target and hold  "
             "— 0 of 8 cells clear p ≤ 0.05", fontsize=13, weight="bold", color=INK, loc="left", pad=9)
ax.legend(frameon=False, fontsize=9.5, loc="lower left")
ax.grid(axis="y", alpha=.25, color=GRID); ax.set_axisbelow(True)

# ---------------- 4. grid marginals
G = pd.read_parquet("results/vstoch/grid_research.parquet")
ax = fig.add_subplot(gs[2, 0])
m = G.groupby("atr")["pct"].mean().sort_values()
cols = [AQUA if v > 0 else ORANGE for v in m.values]
ax.barh(np.arange(len(m)), m.values, color=cols, zorder=3)
ax.set_yticks(np.arange(len(m))); ax.set_yticklabels(m.index, fontsize=9.5)
ax.axvline(0, color=INK2, lw=1)
ax.set_xlabel("marginal mean, % of entry price per trade")
ax.set_title("The ATR sign moved again: ceilings win, floors lose", fontsize=13,
             weight="bold", color=INK, loc="left", pad=9)
ax.grid(axis="x", alpha=.25, color=GRID); ax.set_axisbelow(True)

# ---------------- 5. gross vs net by side
ax = fig.add_subplot(gs[2, 1])
rows = []
for side_nm, trg, s in (("LONG", lo, 1), ("SHORT", sh, -1)):
    for stop, tp, hold in ((2.0, 0.0, 96), (2.0, 2.0, 96), (1.5, 1.5, 48), (3.0, 0.0, 192)):
        for lab_, cost, slip in (("net", None, None), ("gross", 0.0, 0.0)):
            t = V.run(D, trg & D["rth"], side=s, stop=stop, tp=tp, hold=hold, cost=cost, slip=slip)
            rows.append(dict(side=side_nm, arm=lab_, pct=V.stats(t[t.blk == 0])["pct"]))
Zz = pd.DataFrame(rows).groupby(["side", "arm"])["pct"].apply(list)
x = np.arange(4)
for i, side_nm in enumerate(("LONG", "SHORT")):
    ax.scatter(x + i * 0.0, Zz[(side_nm, "gross")], s=95, marker="o",
               facecolors="none", edgecolors=BLUE if i == 0 else ORANGE, lw=2, zorder=4)
    ax.scatter(x, Zz[(side_nm, "net")], s=55, color=BLUE if i == 0 else ORANGE, zorder=5)
    for xi, (gv, nv) in enumerate(zip(Zz[(side_nm, "gross")], Zz[(side_nm, "net")])):
        ax.plot([xi, xi], [gv, nv], color=BLUE if i == 0 else ORANGE, lw=1.4, alpha=.6, zorder=3)
ax.axhline(0, color=INK2, lw=1)
ax.set_xticks(x); ax.set_xticklabels(["2N\nno TP", "2N\n2R", "1.5N\n1.5R", "3N\nno TP"], fontsize=9)
ax.set_ylabel("% of entry price per trade")
ax.set_title("Long gross-positive 4/4, short gross-negative 4/4", fontsize=13,
             weight="bold", color=INK, loc="left", pad=9)
ax.legend(handles=[Line2D([], [], marker="o", ls="", mfc="none", mec=INK2, mew=2, ms=10, label="gross"),
                   Line2D([], [], marker="o", ls="", color=INK2, ms=8, label="net"),
                   Line2D([], [], color=BLUE, lw=3, label="long"),
                   Line2D([], [], color=ORANGE, lw=3, label="short")],
          frameon=False, fontsize=9, loc="lower left", ncol=2)
ax.grid(axis="y", alpha=.25, color=GRID); ax.set_axisbelow(True)

fig.text(0.075, 0.028, "Cost is 1.4–2.9% of the stop, so cost is not the objection.  "
                       "The win rate tracks its own driftless break-even within 0.6 points at every rung.",
         fontsize=10, color=MUTE)
os.makedirs("results/vstoch", exist_ok=True)
fig.savefig("results/vstoch/vstoch_verdict.png", dpi=150, facecolor="white")
print("wrote results/vstoch/vstoch_verdict.png")
