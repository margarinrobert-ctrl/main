"""Three figures: the arithmetic that bounds it, the five designs, and the book."""
import sys, os
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5")
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import s5data as S

R = "results/scalp5/"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#c9ced6",
                     "axes.linewidth": .9, "xtick.color": "#4b5158", "ytick.color": "#4b5158",
                     "text.color": "#1d2126", "axes.labelcolor": "#4b5158",
                     "figure.facecolor": "white", "axes.facecolor": "white"})
INK, INK2, MUTE, GRID = "#1d2126", "#4b5158", "#8b929c", "#dfe3e8"
BLUE, ORANGE, AQUA, PURP, GOLD, RED = "#2a78d6", "#eb6834", "#1baf7a", "#7a5cd6", "#c8a032", "#c0392b"
COL = {"S1 opening drive": BLUE, "S2 level reclaim": ORANGE, "S3 flow exhaustion": AQUA,
       "S4 stretch fade": PURP, "S5 range expansion": GOLD}
SH = lambda s: s.split(" ", 1)[0]


def head(fig, title, sub, verdict, vcol=ORANGE):
    fig.text(.055, .955, title, fontsize=19, weight="bold", color=INK)
    for i, s in enumerate(sub):
        fig.text(.055, .921 - i * .023, s, fontsize=10, color=INK2)
    fig.text(.055, .921 - len(sub) * .023 - .006, verdict, fontsize=10.4, color=vcol, weight="bold")


A = pd.read_csv(R + "a_designs.csv")
G = pd.read_csv(R + "b_grid.csv")
C = pd.read_csv(R + "c_legs.csv")
BK = pd.read_csv(R + "d_books.csv")
WF = pd.read_csv(R + "d_wf.csv")
NT = pd.read_csv(R + "d_need.csv")
CR = pd.read_csv(R + "a_corr.csv", index_col=0)

# ================================================================ FIGURE 1 -- THE ARITHMETIC
base = S.load_1m()
bt = {}
for tf in (1, 3, 5, 15):
    D = S.assemble(S.resample(base, tf), tf)
    t, a = S.breakeven_table(D)
    bt[tf] = (t[t.rr == 1.0], a)

fig = plt.figure(figsize=(16.2, 7.8))
gs = fig.add_gridspec(1, 3, wspace=.30, left=.062, right=.977, top=.775, bottom=.255)
head(fig, "What a scalp in this window has to beat, before any signal",
     ["NQ, 07:00-11:00 New York, flat at 11:00, one position at a time. All-in round turn 1.72 points (MNQ commission + exchange + NFA + slippage).",
      "The clock is a real UTC→New York conversion, not a fixed shift: NQ_1m is stamped in UTC and the mean-range peak lands at 09:30 New York year round."],
     "Verdict: at a 1.5×ATR stop on 5-minute bars a 1:1 scalp needs 53.8%. Tighten to 0.5×ATR on 1-minute bars and it needs 72.8%. That is the whole design constraint.")

ax = fig.add_subplot(gs[0, 0])
for tf, col in zip((1, 3, 5, 15), (RED, ORANGE, BLUE, AQUA)):
    t, a = bt[tf]
    ax.plot(t.stop_atr, t.cost_frac_of_risk * 100, "-o", lw=2.2, ms=6, color=col,
            label=f"{tf}m  (ATR {a:.1f} pts)")
ax.axhline(10, color=MUTE, lw=1.4, ls="--")
ax.text(3.05, 11, " 10% of risk", fontsize=8.6, color=MUTE, ha="right")
ax.set_xlabel("stop distance, ×ATR"); ax.set_ylabel("round turn as a % of the risk")
ax.legend(frameon=False, fontsize=9)
ax.set_title("Cost is a fraction of risk, not a number", fontsize=11.8, weight="bold", color=INK, loc="left", pad=8)
ax.grid(alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.062, .190, "The same 1.72 points is 45.6% of a 0.5×ATR stop on 1-minute bars and\n"
                     "3.8% of a 3×ATR stop on 5-minute bars — a factor of twelve, decided\n"
                     "entirely by geometry.", fontsize=8.6, color=INK2, va="top")

ax = fig.add_subplot(gs[0, 1])
for tf, col in zip((1, 3, 5, 15), (RED, ORANGE, BLUE, AQUA)):
    t, a = bt[tf]
    ax.plot(t.stop_atr, t.breakeven_win * 100, "-o", lw=2.2, ms=6, color=col, label=f"{tf}m")
ax.axhline(50, color=INK2, lw=1.8, ls="--")
ax.text(3.05, 50.6, " driftless 1:1 bound", fontsize=8.6, color=INK2, ha="right")
ax.set_xlabel("stop distance, ×ATR"); ax.set_ylabel("win rate needed to break even at 1:1 (%)")
ax.legend(frameon=False, fontsize=9)
ax.set_title("The break-even the geometry implies", fontsize=11.8, weight="bold", color=INK, loc="left", pad=8)
ax.grid(alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.386, .190, "A scalp is not made hard by the market here — it is made hard by\n"
                     "arithmetic. Every gap above the dashed line has to be earned by the\n"
                     "signal before a single point of profit exists.", fontsize=8.6, color=INK2, va="top")

ax = fig.add_subplot(gs[0, 2])
d = NT[(NT.target_R == 1.0)]
x = np.arange(len(d)); w = .36
ax.bar(x - w/2, d.driftless * 100, w, color=MUTE, label="driftless bound", zorder=3)
ax.bar(x + w/2, d.need_win * 100, w, color=RED, label="needed for that PF", zorder=3)
for i, r in enumerate(d.itertuples()):
    ax.text(x[i] + w/2, r.need_win * 100 + .8, f"+{r.lift_needed*100:.1f}", ha="center",
            fontsize=8.8, weight="bold", color=RED)
meas = C[C.block == "research"].set_index("design").win * 100
ax.axhline(meas.max(), color=AQUA, lw=2.2, ls="--")
ax.text(len(d) - .55, meas.max() + .8, f" best design delivers {meas.max():.1f}%", fontsize=8.8,
        color=AQUA, weight="bold", ha="right")
ax.set_xticks(x); ax.set_xticklabels([f"{r.stop_atr:g}N\nPF {r.want_pf:g}" for r in d.itertuples()], fontsize=8.6)
ax.set_ylabel("win rate (%)"); ax.set_ylim(45, 78)
ax.legend(frameon=False, fontsize=9, loc="upper left")
ax.set_title("What PF 1.5 and PF 2.0 would cost", fontsize=11.8, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.710, .190, "PF 1.5 at a 3×ATR stop needs +11.8 points of win rate over a\n"
                     "coin flip. The best of the five delivers +2.4. That gap, not the\n"
                     "indicator choice, is why intraday scalping keeps failing here.",
         fontsize=8.6, color=RED, weight="bold", va="top")
fig.savefig(R + "s5_arithmetic.png", dpi=140, facecolor="white")
print("wrote", R + "s5_arithmetic.png")

# ================================================================ FIGURE 2 -- THE FIVE
fig = plt.figure(figsize=(16.2, 9.6))
gs = fig.add_gridspec(2, 3, hspace=.82, wspace=.34, left=.075, right=.977, top=.790, bottom=.145)
head(fig, "The five designs",
     ["Each is a named mechanism, not an indicator variant — a hypothesis count is not a diversification count, and eight breakout ideas on this branch",
      "correlated 0.87-0.96. Geometry is the MARGINAL CONSENSUS of an 800-cell declared grid (3×ATR stop, no target, breakeven and trail), not any design's top cell."],
     "Verdict: they are genuinely independent (mean |ρ| 0.117) — and 2 of 5 are positive on the block that chose them, and 0 of 5 clear a matched random entry.")

ax = fig.add_subplot(gs[0, 0])
d = C[C.block == "research"].set_index("design")
o = d.sharpe.sort_values()
ax.barh(np.arange(len(o)), o.values, .62, color=[COL[i] for i in o.index], zorder=3)
for i, v in enumerate(o.values):
    ax.text(v + (.03 if v >= 0 else -.03), i, f"{v:+.2f}", va="center",
            ha="left" if v >= 0 else "right", fontsize=9, weight="bold", color=INK)
ax.axvline(0, color=INK2, lw=1.4)
ax.set_yticks(np.arange(len(o))); ax.set_yticklabels([SH(i) for i in o.index], fontsize=9.4)
ax.set_xlabel("Sharpe, research block"); ax.set_xlim(-1.6, 1.0)
ax.set_title("Sharpe on the block that chose them", fontsize=11.6, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="x", alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.062, .500, "Sharpe is computed over EVERY trading day, zero-filled on days that did\n"
                     "not trade. Over traded days only, a rule is paid for trading less.",
         fontsize=8.4, color=INK2, va="top")

ax = fig.add_subplot(gs[0, 1])
o = d.EV.sort_values()
ax.barh(np.arange(len(o)), o.values, .62, color=[COL[i] for i in o.index], zorder=3)
for i, (v, n) in enumerate(zip(o.values, d.loc[o.index, "n"])):
    ax.text(v + (.12 if v >= 0 else -.12), i, f"{v:+.2f}  (n {int(n)})", va="center",
            ha="left" if v >= 0 else "right", fontsize=8.6, color=INK)
ax.axvline(0, color=INK2, lw=1.4)
ax.set_yticks(np.arange(len(o))); ax.set_yticklabels([SH(i) for i in o.index], fontsize=9.4)
ax.set_xlabel("EV per trade, points"); ax.set_xlim(-8.5, 6.5)
ax.set_title("Expectancy per trade", fontsize=11.6, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="x", alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.386, .500, "One MNQ point is $2. 170-220 trades a year a leg, median hold 50-86\n"
                     "minutes — intraday, but not a scalp; see the hold panel.",
         fontsize=8.4, color=INK2, va="top")

ax = fig.add_subplot(gs[0, 2])
im = ax.imshow(CR.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
lab = [SH(i) for i in CR.index]
ax.set_xticks(range(5)); ax.set_xticklabels(lab, fontsize=9)
ax.set_yticks(range(5)); ax.set_yticklabels(lab, fontsize=9)
for i in range(5):
    for j in range(5):
        v = CR.values[i, j]
        ax.text(j, i, f"{v:+.2f}", ha="center", va="center", fontsize=8.6,
                color="white" if abs(v) > .55 else INK)
ax.set_title("Daily P&L correlation", fontsize=11.6, weight="bold", color=INK, loc="left", pad=8)
plt.colorbar(im, ax=ax, fraction=.046, pad=.03)
_off = CR.to_numpy()[np.triu_indices(5, 1)]
fig.text(.710, .500, f"Mean |ρ| {np.abs(_off).mean():.3f}, max {np.abs(_off).max():.3f} (0.117 / 0.266 at the shipped\n"
                     "geometry). This branch's eight-breakout programme scored 0.87-0.96\n"
                     "here — one strategy wearing eight names. Five different MECHANISMS\n"
                     "is what produced this matrix.",
         fontsize=8.4, color=AQUA, weight="bold", va="top")

ax = fig.add_subplot(gs[1, 0])
x = np.arange(len(d))
ax.bar(x, d.p_ctl.values, .62, color=[COL[i] for i in d.index], zorder=3)
ax.axhline(.05, color=RED, lw=2, ls="--")
ax.text(.98, .075, "p = 0.05", transform=ax.transAxes, fontsize=9, weight="bold", color=RED, ha="right")
for i, v in enumerate(d.p_ctl.values):
    ax.text(i, v + .015, f"{v:.3f}", ha="center", fontsize=8.8, color=INK)
ax.set_xticks(x); ax.set_xticklabels([SH(i) for i in d.index], fontsize=9)
ax.set_ylabel("share of controls beating it", fontsize=9)
ax.set_ylim(0, 1.0)
ax.set_title("Against a matched random entry", fontsize=11.6, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.062, .086, "Same window, same rate, same side mix, same geometry, same position lock.\n"
                     "Not one design clears it — and the control itself loses 1.5 to 2.3 points a\n"
                     "trade, so beating it would not have meant profit either.",
         fontsize=8.4, color=INK2, va="top")

ax = fig.add_subplot(gs[1, 1])
g = G[G.tf == 5]
for ax_name, col, lab_ in (("stop", BLUE, "stop ×ATR"), ("tgt", ORANGE, "target R")):
    t = g.groupby(ax_name).sharpe.mean()
    ax.plot(t.index, t.values, "-o", lw=2.4, ms=7, color=col, label=lab_)
ax.axhline(0, color=INK2, lw=1.2)
ax.set_xlabel("setting"); ax.set_ylabel("mean Sharpe over the whole grid")
ax.legend(frameon=False, fontsize=9)
ax.set_title("The marginals, read across 800 cells", fontsize=11.6, weight="bold", color=INK, loc="left", pad=8)
ax.grid(alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.386, .086, "Sharpe rises monotonically as the stop WIDENS and no take profit is the\n"
                     "best target rung — the 23rd time on this branch. Both point away from a\n"
                     "scalp and toward a held intraday position.",
         fontsize=8.4, color=INK2, va="top")

ax = fig.add_subplot(gs[1, 2])
h = C[C.block == "research"].set_index("design").hold_min
ax.barh(np.arange(len(h)), h.values, .62, color=[COL[i] for i in h.index], zorder=3)
for i, v in enumerate(h.values):
    ax.text(v + 1.5, i, f"{v:.0f} min", va="center", fontsize=9, color=INK)
ax.axvline(15, color=RED, lw=2, ls="--")
ax.text(16, -.6, " a scalp", fontsize=8.8, color=RED, weight="bold", va="bottom")
ax.set_yticks(np.arange(len(h))); ax.set_yticklabels([SH(i) for i in h.index], fontsize=9.4)
ax.set_xlabel("median hold, minutes"); ax.set_xlim(0, 105)
ax.set_title("What the winning geometry actually holds", fontsize=11.4, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="x", alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.710, .086, "At the geometry that makes money the median hold is 50-86 minutes, so\n"
                     "one to three trades a session. Squeeze it back to a scalp and the\n"
                     "break-even climbs faster than any signal here closes the gap.",
         fontsize=8.4, color=INK2, va="top")
fig.savefig(R + "s5_designs.png", dpi=140, facecolor="white")
print("wrote", R + "s5_designs.png")

# ================================================================ FIGURE 3 -- THE BOOK
fig = plt.figure(figsize=(16.2, 8.4))
gs = fig.add_gridspec(1, 3, wspace=.32, left=.062, right=.977, top=.755, bottom=.190)
head(fig, "The book, and whether it earns its own complexity",
     ["Three declared books, the selection rule of each written before it was scored. A book is only worth building if it beats its own best leg.",
      "Then the walk-forward with the leg selection re-run inside every training window, and a random subset of the same size beside it."],
     "Verdict: the two-leg book beats its best leg by 0.04 Sharpe on research and LOSES to it out of sample — diversification bought almost nothing here.",
     vcol=RED)

ax = fig.add_subplot(gs[0, 0])
p = BK.pivot_table(index="book", columns="block", values="sharpe").loc[
    ["ALL FIVE", "RESEARCH-POSITIVE", "BEST LEG ALONE"]]
x = np.arange(len(p)); w = .36
ax.bar(x - w/2, p.research, w, color=MUTE, label="research (chose it)", zorder=3)
ax.bar(x + w/2, p.LOCKED, w, color=AQUA, label="LOCKED (read once)", zorder=3)
for i in range(len(p)):
    ax.text(x[i] - w/2, p.research.iloc[i] + (.05 if p.research.iloc[i] >= 0 else -.05),
            f"{p.research.iloc[i]:+.2f}", ha="center",
            va="bottom" if p.research.iloc[i] >= 0 else "top", fontsize=9, color=INK)
    ax.text(x[i] + w/2, p.LOCKED.iloc[i] + .05, f"{p.LOCKED.iloc[i]:+.2f}", ha="center",
            fontsize=9, weight="bold", color=INK)
ax.axhline(0, color=INK2, lw=1.4)
ax.set_xticks(x); ax.set_xticklabels(["all five", "research-positive\n(S1 + S3)", "best leg\n(S3)"], fontsize=9)
ax.set_ylabel("Sharpe"); ax.set_ylim(-.9, 2.1)
ax.legend(frameon=False, fontsize=9, loc="upper left")
ax.set_title("Three books", fontsize=11.8, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.062, .130, "The all-five book LOSES on research and makes money on locked — the wrong\n"
                     "shape, and the fourteenth time on this branch. The two-leg book is the only\n"
                     "one positive on both, and it does not beat S3 alone out of sample.",
         fontsize=8.6, color=INK2, va="top")

ax = fig.add_subplot(gs[0, 1])
arms = ["re_chosen", "random_subset", "all_five", "best_fixed"]
cols = [ORANGE, MUTE, BLUE, AQUA]
x = np.arange(len(WF)); w = .2
for i, (a, c) in enumerate(zip(arms, cols)):
    ax.bar(x + (i - 1.5) * w, WF[a], w, color=c, label=a.replace("_", " "), zorder=3)
ax.axhline(0, color=INK2, lw=1.2)
ax.set_xticks(x); ax.set_xticklabels(WF.fold, fontsize=8, rotation=45, ha="right")
ax.set_ylabel("points per day, out of sample")
ax.legend(frameon=False, fontsize=8.4, ncol=2)
ax.set_title("Walk-forward, selection re-run per fold", fontsize=11.6, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.386, .130, "Means: all five +7.63, best fixed +5.97, re-chosen +3.65, random +2.34.\n"
                     "Re-selecting the legs every fold LOSES to simply holding all five — the\n"
                     "thirteenth re-optimiser on this branch to lose to its own starting point.",
         fontsize=8.6, color=INK2, va="top")

ax = fig.add_subplot(gs[0, 2])
ax.axis("off")
rows = [["", "research", "LOCKED"],
        ["trades / year", "409", "384"],
        ["EV per trade", "+2.95 pts", "+5.96 pts"],
        ["points / day", "+2.39", "+9.09"],
        ["profit factor", "1.115", "1.353"],
        ["Sharpe", "+0.59", "+1.60"],
        ["return / drawdown", "1.03", "3.06"],
        ["beats a random entry?", "no  (p 0.11–0.26)", "not read"]]
tb = ax.table(cellText=rows[1:], colLabels=rows[0], loc="upper center", cellLoc="center",
              colWidths=[.40, .32, .28])
tb.auto_set_font_size(False); tb.set_fontsize(9.4); tb.scale(1, 2.0)
for j in range(3):
    tb[0, j].set_facecolor("#eef1f5"); tb[0, j].set_text_props(weight="bold", color=INK)
for i in range(1, len(rows)):
    for j in range(3):
        tb[i, j].set_edgecolor(GRID)
    tb[i, 0].set_text_props(ha="left")
tb[7, 1].set_text_props(weight="bold", color=RED)
ax.set_title("The two-leg book: S1 + S3", fontsize=11.8, weight="bold", color=INK, loc="left", pad=8)
fig.text(.710, .130, "This is the best honest object the five produce: ~400 trades a year at\n"
                     "PF 1.12 on the block that chose it. It is positive on both blocks and it\n"
                     "does not separate from a random entry with the same geometry, so it is a\n"
                     "candidate to forward-test, not a system to size.",
         fontsize=8.6, color=INK2, va="top")
fig.savefig(R + "s5_book.png", dpi=140, facecolor="white")
print("wrote", R + "s5_book.png")
