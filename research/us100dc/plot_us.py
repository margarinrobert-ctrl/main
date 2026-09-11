"""One figure: the spec as given, what the trail does to it, and the account."""
import sys, os
sys.path.insert(0, "research"); sys.path.insert(0, "research/us100dc")
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import dc_run as DC

R = "results/us100dc/"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#c9ced6", "axes.linewidth": .9,
                     "xtick.color": "#4b5158", "ytick.color": "#4b5158", "text.color": "#1d2126",
                     "axes.labelcolor": "#4b5158", "figure.facecolor": "white", "axes.facecolor": "white"})
INK, INK2, MUTE, GRID = "#1d2126", "#4b5158", "#8b929c", "#dfe3e8"
BLUE, ORANGE, AQUA, RED, GOLD = "#2a78d6", "#eb6834", "#1baf7a", "#c0392b", "#c8a032"

L = pd.read_csv(R + "locked.csv")
A = pd.read_csv(R + "ablation.csv")
C = pd.read_csv(R + "control.csv")
G = pd.read_csv(R + "gate.csv")

f = DC.load_us100(); D = DC.build(f)
curves = {}
for lab, kw in (("as specified (trail 2.0N)", dict(trail_n=2.0)),
                ("no trail (stop 1.5N only)", dict(trail_n=99.0))):
    t, _, _ = DC.run(D, assumed_spread=1.0, **kw)
    curves[lab] = t

fig = plt.figure(figsize=(16.4, 9.4))
gs = fig.add_gridspec(2, 3, hspace=.80, wspace=.30, left=.062, right=.977, top=.790, bottom=.150)
fig.text(.055, .955, "US100 M15 dual-Donchian, as specified", fontsize=19, weight="bold", color=INK)
fig.text(.055, .921, "Entry Donchian 160, exit Donchian 60, ATR(80), stop 1.5×ATR, trail 2.0×ATR, long only, spread/ATR ≤ 0.20. US100_LONG_15m, 206,703 bars 2016-11..2025-10,",
         fontsize=10, color=INK2)
fig.text(.055, .898, "1.215-point round turn plus 0.25 slippage a side. Research block to 2022-08-30; the locked block read once. Clock verified — mean bar range peaks at 09:30 New York.",
         fontsize=10, color=INK2)
fig.text(.055, .868, "Verdict: as specified it loses on both blocks (PF 0.86 / 0.88) — and removing the 2.0×ATR trail alone turns it to PF 1.41 / 1.25. The trail is the whole result.",
         fontsize=10.4, color=RED, weight="bold")

ax = fig.add_subplot(gs[0, 0])
d = L[L.variant == "as specified"]
x = np.arange(2); w = .36
ax.bar(x - w/2, d.pts, w, color=RED, zorder=3)
for i, v in enumerate(d.pts):
    ax.text(x[i] - w/2, v - .08, f"{v:+.2f}", ha="center", va="top", fontsize=10, weight="bold", color=INK)
ax2 = ax.twinx()
ax2.plot(x + w/2, d.pf, "o", ms=12, color=BLUE)
for i, v in enumerate(d.pf):
    ax2.text(x[i] + w/2, v, f"PF {v:.3f}  ", va="center", ha="right", fontsize=9.6, color=BLUE, weight="bold")
ax2.axhline(1.0, color=BLUE, lw=1, ls=":"); ax2.set_ylim(.55, 1.55)
ax2.set_ylabel("profit factor", color=BLUE, labelpad=2)
ax.axhline(0, color=INK2, lw=1.2)
ax.set_xticks(x); ax.set_xticklabels([f"research\nn = {int(n)}" for n in d.n], fontsize=9.4)
ax.set_xticklabels([f"research\nn = {int(d.n.iloc[0])}", f"LOCKED\nn = {int(d.n.iloc[1])}"], fontsize=9.4)
ax.set_ylabel("points per trade"); ax.set_ylim(-3.2, .8)
ax.set_title("As specified", fontsize=12, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.062, .500, "Win rate 35.8% / 34.6%, Sharpe −0.59 / −0.66, and it loses on the block\n"
                     "that would have chosen it as well as the one read once.", fontsize=8.5, color=INK2, va="top")

ax = fig.add_subplot(gs[0, 1])
o = A.set_index("variant").loc[["tighter trail 1.5N", "as specified", "wider trail 3.0N",
                                "no trail (stop 1.5N only)"]]
lab = ["trail 1.5N", "trail 2.0N\n(as specified)", "trail 3.0N", "no trail"]
c = [RED if v < 0 else AQUA for v in o.pts]
ax.bar(np.arange(4), o.pts, .62, color=c, zorder=3)
for i, v in enumerate(o.pts):
    ax.text(i, v + (.25 if v >= 0 else -.25), f"{v:+.2f}", ha="center",
            va="bottom" if v >= 0 else "top", fontsize=9.6, weight="bold", color=INK)
ax.axhline(0, color=INK2, lw=1.2)
ax.set_xticks(np.arange(4)); ax.set_xticklabels(lab, fontsize=8.8)
ax.set_ylabel("points per trade, research")
ax.set_title("The trail axis is monotone", fontsize=12, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.386, .500, "−3.63 → −1.57 → +1.37 → +8.06 as the trail widens and then goes away.\n"
                     "Nothing else in the specification was changed.", fontsize=8.5, color=INK2, va="top")

ax = fig.add_subplot(gs[0, 2])
sp = A.set_index("variant")
ax.bar([0, 1], [sp.loc["as specified", "p_stop"] * 100, sp.loc["as specified", "p_chan"] * 100],
       .5, color=[RED, MUTE], zorder=3, label="as specified")
ax.bar([2.6, 3.6], [sp.loc["no trail (stop 1.5N only)", "p_stop"] * 100,
                    sp.loc["no trail (stop 1.5N only)", "p_chan"] * 100], .5,
       color=[AQUA, GOLD], zorder=3)
for i, v in zip([0, 1, 2.6, 3.6],
                [sp.loc["as specified", "p_stop"] * 100, sp.loc["as specified", "p_chan"] * 100,
                 sp.loc["no trail (stop 1.5N only)", "p_stop"] * 100,
                 sp.loc["no trail (stop 1.5N only)", "p_chan"] * 100]):
    ax.text(i, v + 2, f"{v:.1f}%", ha="center", fontsize=9.4, weight="bold", color=INK)
ax.set_xticks([0, 1, 2.6, 3.6])
ax.set_xticklabels(["stop/trail", "channel 60", "stop", "channel 60"], fontsize=8.8)
ax.text(.5, -14, "as specified", ha="center", fontsize=9.2, weight="bold", color=RED)
ax.text(3.1, -14, "no trail", ha="center", fontsize=9.2, weight="bold", color=AQUA)
ax.set_ylabel("share of exits"); ax.set_ylim(-20, 115)
ax.set_title("The exit Donchian 60 never fires", fontsize=12, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.710, .500, "With the 2.0×ATR trail on it closes 100.0% of trades and the\n"
                     "60-bar exit channel closes 0.0% — the specification's exit\n"
                     "period is dead code. Remove the trail and the channel takes\n"
                     "28% of exits and the hold goes 3.1h → 13.7h.",
         fontsize=8.5, color=ORANGE, weight="bold", va="top")

ax = fig.add_subplot(gs[1, 0])
for lab_, col in (("as specified (trail 2.0N)", RED), ("no trail (stop 1.5N only)", AQUA)):
    t = curves[lab_]
    ax.plot(t.ts.values, np.cumsum(t.pts.to_numpy()), lw=2, color=col, label=lab_)
cut = pd.Timestamp(D["cut_day"], unit="D")
ax.axvline(cut, color=INK2, lw=1.6, ls="--")
ax.text(cut, ax.get_ylim()[1] * .96, " locked block →", fontsize=8.8, color=INK2, va="top")
ax.axhline(0, color=INK2, lw=1)
ax.set_ylabel("cumulative points, one unit")
ax.legend(frameon=False, fontsize=8.8, loc="upper left")
ax.set_title("The same signals, two exits", fontsize=12, weight="bold", color=INK, loc="left", pad=8)
ax.grid(alpha=.2, color=GRID); ax.set_axisbelow(True)

ax = fig.add_subplot(gs[1, 1])
d = C.copy()
d["cell"] = d.variant + "\n" + d.block.str[:4].str.lower()
x = np.arange(len(d)); w = .36
ax.bar(x - w/2, d.rule_pts, w, color=BLUE, label="the rule", zorder=3)
ax.bar(x + w/2, d.control_pts, w, color=MUTE, label="random entry, same exits", zorder=3)
for i in range(len(d)):
    ax.text(x[i], 9.4, f"p {d.p.iloc[i]:.3f}", ha="center", fontsize=8.8, weight="bold",
            color=AQUA if d.p.iloc[i] <= .05 else ORANGE)
ax.axhline(0, color=INK2, lw=1.2)
ax.set_xticks(x); ax.set_xticklabels(d.cell, fontsize=8)
ax.set_ylabel("points per trade"); ax.set_ylim(-4.2, 11.2)
ax.legend(frameon=False, fontsize=8.6, loc="lower left")
ax.set_title("Neither version clears a coin flip", fontsize=12, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)

ax = fig.add_subplot(gs[1, 2])
ax.axis("off")
rows = [["", "research", "LOCKED"],
        ["trades", "1,073", "717"],
        ["points / trade", "−1.57", "−2.19"],
        ["profit factor", "0.863", "0.880"],
        ["win rate", "35.8%", "34.6%"],
        ["Sharpe", "−0.59", "−0.66"],
        ["total, 1 unit", "−1,683 pts", "−1,567 pts"],
        ["max drawdown", "1,965 pts", "2,210 pts"],
        ["…on a $1,000 account", "−168%", "−157%"]]
tb = ax.table(cellText=rows[1:], colLabels=rows[0], loc="upper center", cellLoc="center",
              colWidths=[.44, .28, .28])
tb.auto_set_font_size(False); tb.set_fontsize(8.8); tb.scale(1, 1.62)
for j in range(3):
    tb[0, j].set_facecolor("#eef1f5"); tb[0, j].set_text_props(weight="bold", color=INK)
for i in range(1, len(rows)):
    for j in range(3):
        tb[i, j].set_edgecolor(GRID)
    tb[i, 0].set_text_props(ha="left")
for j in (1, 2):
    tb[8, j].set_text_props(weight="bold", color=RED)
ax.set_title("The $1,000 account at 1:100", fontsize=12, weight="bold", color=INK, loc="left", pad=8)
fig.text(.710, .062, "At $1 a point one unit needs $93-$180 of margin, so the deposit affords\n"
                     "5-11 units — and ONE unit already loses more than the whole deposit on\n"
                     "either block, with a drawdown twice it. The leverage is not the\n"
                     "constraint; the sign of the expectancy is.", fontsize=8.5, color=INK2, va="top")
fig.text(.062, .092, "The spread-to-ATR filter is inert: with a fixed spread it IS an ATR floor of spread/0.20, and at\n"
                     "the stated 0.20 with a 1-point spread it keeps 91% of bars and moves the result by 0.01 points.\n"
                     "No feed here carries bid/ask, so its strength is an assumption — swept at 0.5/1/2/3 points.",
         fontsize=8.5, color=INK2, va="top")
fig.savefig(R + "us100_spec.png", dpi=140, facecolor="white")
print("wrote", R + "us100_spec.png")
