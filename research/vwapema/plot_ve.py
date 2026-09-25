import os, sys
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTE, GRID = "#1c1f24", "#4a5058", "#8b929c", "#e6e9ed"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#c8ccd2", "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "figure.facecolor": "white"})

B = pd.read_csv("results/vwapema/baserates.csv")
L = pd.read_csv("results/vwapema/locked.csv")
G = pd.read_csv("results/vwapema/volgradient_locked.csv")
Y = pd.read_csv("results/vwapema/byyear.csv")
E = pd.read_csv("results/vwapema/exits.csv")

fig = plt.figure(figsize=(15.6, 11.6))
gs = fig.add_gridspec(3, 2, hspace=0.62, wspace=0.24, left=0.07, right=0.965, top=0.875, bottom=0.075)
fig.text(0.07, 0.962, "VWAP-EMA regime-filtered intraday strategy on XAU/USD", fontsize=20.5, weight="bold", color=INK)
fig.text(0.07, 0.933, "Bhatti (SSRN 6650958) rules, built literally and measured on XAU_ISO_15m: 371,586 bars, 2010-01 to 2026-01, "
                      "research to 2020-05, one locked read.", fontsize=10.5, color=INK2)
fig.text(0.07, 0.910, "Verdict: the paper reports no backtest. Measured on gold the rule loses on research, beats only a control that loses more, and its one real gradient inverts.",
         fontsize=10.8, color=ORANGE, weight="bold")

# --- 1. condition base rates
ax = fig.add_subplot(gs[0, 0])
bl = B[B.side == "LONG"].set_index("cond").loc[["C1", "C2", "C3", "C4", "C5", "C6"]]
lbl = {"C1": "C1 regime\nclose>EMA200", "C2": "C2 VWAP side\nclose>VWAP", "C3": "C3 pullback\nto EMA50",
       "C4": "C4 candle\npin/engulf", "C5": "C5 volume\n>1.1x SMA20", "C6": "C6 range\n>=0.8 ATR"}
x = np.arange(6)
cols = [ORANGE if v >= 85 else (AQUA if v <= 45 else MUTE) for v in bl.given_rest_pct]
ax.bar(x, bl.given_rest_pct, 0.62, color=cols, zorder=3)
for i, v in enumerate(bl.given_rest_pct):
    ax.text(i, v + 2, f"{v:.0f}%", ha="center", fontsize=10, weight="bold", color=INK)
ax.axhline(85, color=ORANGE, ls="--", lw=1.1)
ax.text(0.15, 88, "decoration", fontsize=8.5, color=ORANGE, ha="left")
ax.set_xticks(x); ax.set_xticklabels([lbl[c] for c in bl.index], fontsize=8.2)
ax.set_ylabel("pass rate given the other five"); ax.set_ylim(0, 108)
ax.set_title("The VWAP condition removes almost nothing", fontsize=12.5, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="y", alpha=.25, color=GRID); ax.set_axisbelow(True)

# --- 2. paper's assumed vs measured outcome mix
ax = fig.add_subplot(gs[0, 1])
cats = ["3R target", "trail / partial", "initial stop"]
paper = [30, 28, 42]
meas = [12.4, 61.1, 26.5]
x = np.arange(3); w = 0.36
ax.bar(x - w/2, paper, w, color=MUTE, label="the paper's ASSUMED mix", zorder=3)
ax.bar(x + w/2, meas, w, color=BLUE, label="measured on gold", zorder=3)
for i, (a, b) in enumerate(zip(paper, meas)):
    ax.text(i - w/2, a + 1.5, f"{a}%", ha="center", fontsize=9, color=INK2)
    ax.text(i + w/2, b + 1.5, f"{b:.1f}%", ha="center", fontsize=9.5, weight="bold", color=BLUE)
ax.set_xticks(x); ax.set_xticklabels(cats, fontsize=9.5); ax.set_ylabel("share of trades"); ax.set_ylim(0, 72)
ax.set_title("The assumed distribution the paper's numbers came from", fontsize=12.5, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=9, loc="upper left"); ax.grid(axis="y", alpha=.25, color=GRID); ax.set_axisbelow(True)

# --- 3. the locked read
ax = fig.add_subplot(gs[1, 0])
names, res, loc_, ctl = [], [], [], []
for sd in ("LONG", "SHORT"):
    a = L[L.side == sd]
    names.append(sd)
    res.append(a[a.block == "research"].R.iloc[0]); loc_.append(a[a.block == "LOCKED"].R.iloc[0])
    ctl.append(a[a.block == "LOCKED"].ctl_R.iloc[0])
x = np.arange(2); w = 0.26
ax.bar(x - w, res, w, color=BLUE, label="research (chose)", zorder=3)
ax.bar(x, loc_, w, color=AQUA, label="locked", zorder=3)
ax.bar(x + w, ctl, w, color=MUTE, label="random entry, locked", zorder=3)
ax.axhline(0, color=INK2, lw=1)
ax.set_xticks(x); ax.set_xticklabels(names, fontsize=11)
ax.set_ylabel("R per trade")
ax.set_title("Beats a control that loses more, on both blocks", fontsize=12.5, weight="bold", color=INK, loc="left", pad=8)
ax.annotate("grows on locked:\nthe wrong shape", xy=(0.0, loc_[0]), xytext=(0.52, 0.105), fontsize=9,
            color=ORANGE, weight="bold", va="center",
            arrowprops=dict(arrowstyle="->", color=ORANGE, lw=1.3))
ax.set_ylim(-0.26, 0.20)
ax.legend(frameon=False, fontsize=9, loc="lower left"); ax.grid(axis="y", alpha=.25, color=GRID); ax.set_axisbelow(True)

# --- 4. the volume gradient inverting
ax = fig.add_subplot(gs[1, 1])
for bn, col, mk in (("research", BLUE, "o"), ("LOCKED (descriptive)", ORANGE, "s")):
    g = G[G.block == bn]
    ax.plot(g.vol_mult, g.R, marker=mk, color=col, lw=2.2, ms=7, label=bn.split(" ")[0], zorder=4)
    ax.plot(g.vol_mult, g.rand_R, marker=mk, color=col, lw=1.2, ms=4, ls=":", alpha=.65,
            label=f"{bn.split(' ')[0]} random filter", zorder=3)
ax.axhline(0, color=INK2, lw=1)
ax.set_xlabel("C5 volume multiple"); ax.set_ylabel("R per trade")
ax.set_title("The one gradient that carried information, inverting", fontsize=12.5, weight="bold", color=INK, loc="left", pad=8)
ax.text(0.97, 0.05, "Spearman  research +1.00   locked -0.90", transform=ax.transAxes, ha="right",
        fontsize=9.5, weight="bold", color=ORANGE, bbox=dict(boxstyle="round,pad=0.35", fc="white", ec=ORANGE, lw=1))
ax.legend(frameon=False, fontsize=8.5, loc="upper left", ncol=2); ax.grid(alpha=.25, color=GRID)

# --- 5. by year
ax = fig.add_subplot(gs[2, 0])
Y2 = Y[Y.year < 2026]
ax.bar(Y2.year, Y2.R, color=[AQUA if v > 0 else ORANGE for v in Y2.R], zorder=3)
ax.axhline(0, color=INK2, lw=1)
ax.axvline(2020.4, color=BLUE, ls="--", lw=1.3)
ax.text(2020.6, 0.28, "locked block begins", fontsize=8.5, color=BLUE, rotation=90, va="top")
i24 = Y2[Y2.year == 2024]
ax.annotate("the paper's\nown sample", xy=(2024, float(i24.R.iloc[0])), xytext=(2021.3, 0.30), fontsize=8.8,
            color=INK2, arrowprops=dict(arrowstyle="->", color=INK2, lw=1))
ax.set_ylabel("R per trade"); ax.set_xlabel("year")
ax.set_title("Nine of sixteen full years positive, long side", fontsize=12.5, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="y", alpha=.25, color=GRID); ax.set_axisbelow(True)

# --- 6. exit architecture
ax = fig.add_subplot(gs[2, 1])
E2 = E.copy()
E2["short"] = ["as specified", "no EMA20 tighten", "no 3R target", "no target/tighten",
               "wider stop 1.5N", "wider stop, no tgt", "session flatten"]
y = np.arange(len(E2))[::-1]
ax.barh(y, E2.R, color=[AQUA if v > 0 else ORANGE for v in E2.R], zorder=3)
for yy, v, tp in zip(y, E2.R, E2.trail_pct):
    ax.text(v + (0.004 if v >= 0 else -0.004), yy, f"{tp:.0f}% on the trail",
            va="center", ha="left" if v >= 0 else "right", fontsize=8.3, color=INK2)
ax.set_yticks(y); ax.set_yticklabels(E2["short"], fontsize=9)
ax.axvline(0, color=INK2, lw=1); ax.set_xlim(-0.135, 0.055)
ax.set_xlabel("R per trade, research")
ax.set_title("The close-only EMA trail is where 61% of trades die", fontsize=12.5, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="x", alpha=.25, color=GRID); ax.set_axisbelow(True)

fig.text(0.07, 0.022, "The uploaded XAUUSD15.csv could not run this spec: its sixth field is bar duration, not volume (99.62% exactly 15, correlation with bar range +0.005), "
                      "so C5 fires on 0.033% of bars and the VWAP is not volume-weighted.", fontsize=9.3, color=MUTE)
fig.savefig("results/vwapema/vwapema_verdict.png", dpi=150, facecolor="white")
print("wrote results/vwapema/vwapema_verdict.png")
