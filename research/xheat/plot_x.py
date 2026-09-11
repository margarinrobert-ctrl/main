"""Three figures: the verified mechanism, what the exit work bought, and where it fails."""
import sys, os, json
sys.path.insert(0, "research"); sys.path.insert(0, "research/xheat")
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

R = "results/xheat/"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#c9ced6",
                     "axes.linewidth": .9, "xtick.color": "#4b5158", "ytick.color": "#4b5158",
                     "text.color": "#1d2126", "axes.labelcolor": "#4b5158",
                     "figure.facecolor": "white", "axes.facecolor": "white"})
INK, INK2, MUTE, GRID = "#1d2126", "#4b5158", "#8b929c", "#dfe3e8"
BLUE, ORANGE, AQUA, PURP, GOLD, RED = "#2a78d6", "#eb6834", "#1baf7a", "#7a5cd6", "#c8a032", "#c0392b"


def head(fig, title, sub, verdict, vcol=ORANGE):
    fig.text(.055, .955, title, fontsize=19, weight="bold", color=INK)
    for i, s in enumerate(sub):
        fig.text(.055, .921 - i * .023, s, fontsize=10, color=INK2)
    fig.text(.055, .921 - len(sub) * .023 - .006, verdict, fontsize=10.4, color=vcol, weight="bold")


HR = pd.read_csv(R + "p0_hours.csv")
FL = pd.read_csv(R + "p0_flatten.csv")
PRF = pd.read_csv(R + "p1_profile.csv")
LW = pd.read_csv(R + "p1_winlose.csv")
V22 = pd.read_csv(R + "p3_v22.csv")
W1 = pd.read_csv(R + "p4_w1_clock.csv")
W2 = pd.read_csv(R + "p4_w2_equalise.csv")
W3 = pd.read_csv(R + "p4_w3_trail.csv")
CF = pd.read_csv(R + "p5_configs.csv")
IC = pd.read_csv(R + "p3_ic.csv")
EN = pd.read_csv(R + "p3_entries.csv")

# ============================================================== FIGURE 1 -- THE VERIFIED MECHANISM
fig = plt.figure(figsize=(16.4, 9.6))
gs = fig.add_gridspec(2, 3, hspace=.86, wspace=.31, left=.062, right=.977, top=.790, bottom=.145)
head(fig, "The why, verified before anything was built",
     ["Four claims, each checked on its own terms rather than by the P&L it produces. Both feeds: XAU_ISO_15m (2010-2026, real tick volume) and the",
      "uploaded XAUUSD15_MT (2022-2026, a different provider — and its sixth column is the bar's LENGTH IN MINUTES, not volume, so no volume rule runs there)."],
     "Verdict: 07:00-11:00 is the right box on GOLD, heat scales as √(time left) with the exponent the data actually wants, and V22's volatility law replicates.")

ax = fig.add_subplot(gs[0, 0])
for nm, col in (("ISO", BLUE), ("MT", ORANGE)):
    d = HR[HR.feed == nm].sort_values("hour")
    ax.plot(d.hour, d.mean_range_bp, "-o", ms=4, lw=2, color=col, label=nm)
ax.axvspan(7, 11, color=AQUA, alpha=.13, zorder=0)
ax.set_ylim(5.5, 33)
ax.text(9, 32, "07:00–11:00", ha="center", fontsize=9.4, weight="bold", color=AQUA, va="top")
ax.axvline(8.5, color=RED, lw=1.8, ls="--")
ax.text(12.2, 29.5, "gold's own anchor 08:30 NY,\nderived from each feed", fontsize=8.4,
        color=RED, weight="bold", va="top")
ax.set_xlabel("New York hour"); ax.set_ylabel("mean 15m bar range (bp of price)")
ax.legend(frameon=False, fontsize=9)
ax.set_title("Where gold's activity actually is", fontsize=11.6, weight="bold", color=INK, loc="left", pad=8)
ax.grid(alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.062, .512, "The four busiest New York hours of gold's day are exactly the four\n"
                     "in the window: 27.1% of the 24-hour range against 16.7% for a flat day.",
         fontsize=8.4, color=INK2, va="top")

ax = fig.add_subplot(gs[0, 1])
lab = ["<1h", "1-2h", "2-3h", "3-4h"]
iso = [1.46, 1.63, 2.76, 3.67]; mt = [1.47, 1.85, 3.11, 4.04]
gbi = [1.89, 2.10, 3.63, 4.94]
x = np.arange(4); w = .27
ax.bar(x - w, iso, w, color=BLUE, label="|MAE|  ISO", zorder=3)
ax.bar(x, mt, w, color=ORANGE, label="|MAE|  MT", zorder=3)
ax.bar(x + w, gbi, w, color=MUTE, label="give-back  ISO", zorder=3)
ax.set_xticks(x); ax.set_xticklabels(lab, fontsize=9.4)
ax.set_xlabel("time the trade has left before the 11:00 flatten")
ax.set_ylabel("ATR at entry")
ax.legend(frameon=False, fontsize=8.6)
ax.set_title("Heat is set by the clock", fontsize=11.6, weight="bold", color=INK, loc="left", pad=8)
e = W1[W1.block == "research"].fitted_exponent
ax.text(.03, .95, f"fitted exponent {e.iloc[0]:.3f} / {e.iloc[1]:.3f}\nagainst √t = 0.500, predicted first",
        transform=ax.transAxes, fontsize=8.8, weight="bold", color=AQUA, va="top")
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.386, .512, "|MAE| 1.46 → 3.67 ATR and give-back 1.89 → 4.94 as the time left grows.\n"
                     "A 07:15 entry and a 10:30 entry are not the same trade.",
         fontsize=8.4, color=INK2, va="top")

ax = fig.add_subplot(gs[0, 2])
d = V22[(V22.feat == "vol.atr_pct500")]
for (nm, b), g in d.groupby(["feed", "block"]):
    col = BLUE if nm == "ISO" else ORANGE
    ax.plot(g.quartile, g.mae, "-o" if b == "research" else "--s", ms=6, lw=2, color=col,
            alpha=1.0 if b == "research" else .55, label=f"{nm} {b}")
ax.set_xticks([1, 2, 3, 4]); ax.set_xticklabels(["Q1\nlowest vol", "Q2", "Q3", "Q4\nhighest vol"], fontsize=8.6)
ax.set_ylabel("|MAE| in ATR at entry")
ax.legend(frameon=False, fontsize=8.2, ncol=2)
ax.set_title("V22's law, replicated on gold", fontsize=11.6, weight="bold", color=INK, loc="left", pad=8)
ax.grid(alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.710, .512, "Q1/Q4 heat ratio 1.66×–2.24× on both feeds and both blocks,\n"
                     "monotone in all four quartiles. ATR is backward-looking and volatility\n"
                     "mean-reverts, so a FIXED multiple is too small when vol has contracted.",
         fontsize=8.4, color=INK2, va="top")

ax = fig.add_subplot(gs[1, 0])
d = LW[(LW.feed == "ISO") & (LW.block == "research")]
x = np.arange(2); w = .34
ax.bar(x - w/2, [-d.win_mae.iloc[0], -d.lose_mae.iloc[0]], w, color=[AQUA, RED], zorder=3)
ax.bar(x + w/2, [d.win_mfe.iloc[0], d.lose_mfe.iloc[0]], w, color=[AQUA, RED], alpha=.45, zorder=3)
for i, (a, b) in enumerate([(-d.win_mae.iloc[0], d.win_mfe.iloc[0]),
                            (-d.lose_mae.iloc[0], d.lose_mfe.iloc[0])]):
    ax.text(i - w/2, a + .06, f"{a:.2f}", ha="center", fontsize=9.4, weight="bold", color=INK)
    ax.text(i + w/2, b + .06, f"{b:.2f}", ha="center", fontsize=9.4, color=INK)
ax.set_xticks(x); ax.set_xticklabels(["eventual WINNERS", "eventual LOSERS"], fontsize=9.4)
ax.set_ylabel("ATR at entry")
ax.set_title("Winners take a third of the heat", fontsize=11.6, weight="bold", color=INK, loc="left", pad=8)
ax.set_ylim(0, 4.7)
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.062, .098, "Solid = |MAE|, pale = MFE. Uncensored — no stop, so nothing is\n"
                     "truncated. A 2.9× separation on adverse excursion before any feature\n"
                     "is consulted, which is why a stop is the first thing that works.",
         fontsize=8.4, color=INK2, va="top")

ax = fig.add_subplot(gs[1, 1])
d = W2[W2.feed == "ISO"]
x = np.arange(4)
for _, r in d.iterrows():
    col = {"fixed 2.0N": RED, "vol-adaptive": GOLD, "vol + clock": AQUA}[r.policy]
    ax.plot(x, [r.q1, r.q2, r.q3, r.q4], "-o", lw=2.4, ms=7, color=col,
            label=f"{r.policy}  (spread {r.spread:.0%})")
ax.set_xticks(x); ax.set_xticklabels(["Q1\nlowest vol", "Q2", "Q3", "Q4\nhighest vol"], fontsize=8.6)
ax.set_ylabel("share of trades stopped out")
ax.legend(frameon=False, fontsize=8.4, loc="lower left")
ax.set_title("Does the scaling do what it claims?", fontsize=11.6, weight="bold", color=INK, loc="left", pad=8)
ax.set_ylim(.19, .70)
ax.grid(alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.386, .098, "The mechanism's own prediction is a FLAT line, and it is a stronger test\n"
                     "than expectancy. A fixed stop is hit 56.8% of the time in Q1 and 24.5% in\n"
                     "Q4; the scaling halves that spread — and tightens the mean stop doing it.",
         fontsize=8.4, color=INK2, va="top")

ax = fig.add_subplot(gs[1, 2])
d = IC[(IC.block == "research") & (IC.feed == "ISO")].nlargest(9, "ic_mae", keep="all")
d = IC[(IC.block == "research") & (IC.feed == "ISO")].reindex(
    IC[(IC.block == "research") & (IC.feed == "ISO")].ic_mae.abs().sort_values().index).tail(9)
ax.barh(np.arange(len(d)), d.ic_mae, .62,
        color=[AQUA if v > 0 else RED for v in d.ic_mae], zorder=3)
for i, v in enumerate(d.ic_mae):
    ax.text(v + (.008 if v >= 0 else -.008), i, f"{v:+.3f}", va="center",
            ha="left" if v >= 0 else "right", fontsize=8.6, color=INK)
ax.axvline(0, color=INK2, lw=1.2)
ax.set_yticks(np.arange(len(d))); ax.set_yticklabels(d.feat, fontsize=8.6)
ax.set_xlabel("Spearman IC against |MAE|")
ax.set_xlim(-.56, .52)
ax.set_title("What predicts the heat", fontsize=11.6, weight="bold", color=INK, loc="left", pad=8)
both = IC.pivot_table(index=["feed", "feat"], columns="block", values="ic_mae").dropna()
ax.grid(axis="x", alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.710, .098, f"research→locked IC correlation across {len(both)} feature-feed cells:\n"
                     f"+{both.corr().iloc[0,1]:.3f} Pearson, sign kept 82.5%. Heat is a PHYSICAL quantity and it\n"
                     f"transfers; returns on this branch never have.",
         fontsize=8.4, color=AQUA, weight="bold", va="top")
fig.savefig(R + "xheat_why.png", dpi=140, facecolor="white")
print("wrote", R + "xheat_why.png")

# ============================================================== FIGURE 2 -- WHAT IT BOUGHT
fig = plt.figure(figsize=(16.4, 9.6))
gs = fig.add_gridspec(2, 3, hspace=.84, wspace=.34, left=.062, right=.960, top=.790, bottom=.145)
head(fig, "What the exit engineering bought",
     ["Five configurations, each the previous one plus exactly one mechanism, scored PAIRED on the SAME trades so every line is an ablation.",
      "A = no stop, flatten at 11:00.  B = fixed 2.0×ATR stop.  C = stop scaled by volatility percentile and by time left.  D = + breakeven and trail.  E = + clock tighten."],
     "Verdict: the tail collapses and the mean does not move. The worst trade goes −17.0 → −3.2 ATR and drawdown falls in 8 of 8 cells — this is risk, not edge.",
     vcol=AQUA)

L = CF[(CF.feed == "ISO") & (CF.side == "L") & (CF.block == "research")].set_index("cfg")
order = list(L.index)
short = [c.split("  ")[0] for c in order]

ax = fig.add_subplot(gs[0, 0])
ax.bar(np.arange(5), -L.mean_loss.values, .62, color=BLUE, zorder=3)
for i, v in enumerate(-L.mean_loss.values):
    ax.text(i, v + .04, f"{v:.2f}", ha="center", fontsize=9.4, weight="bold", color=INK)
ax.set_xticks(np.arange(5)); ax.set_xticklabels(short, fontsize=9.6)
ax.set_ylabel("mean loss per losing trade, ATR")
ax.set_title("Smaller losses — the first ask", fontsize=11.8, weight="bold", color=INK, loc="left", pad=8)
ax.set_ylim(0, 2.55)
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.062, .508, f"−2.22 → −1.34 ATR, a {(1-L.mean_loss.iloc[-1]/L.mean_loss.iloc[0])*100:.0f}% reduction, and most of it arrives\n"
                     "with the stop alone. The adaptive scaling adds a further 15%.",
         fontsize=8.6, color=INK2, va="top")

ax = fig.add_subplot(gs[0, 1])
ax.bar(np.arange(5) - .19, -L.p95_loss.values, .36, color=ORANGE, label="5th-percentile trade", zorder=3)
ax.bar(np.arange(5) + .19, -L.worst.values, .36, color=RED, label="worst single trade", zorder=3)
for i in range(5):
    ax.text(i - .19, -L.p95_loss.values[i] + .3, f"{-L.p95_loss.values[i]:.1f}", ha="center", fontsize=8.6, color=INK)
    ax.text(i + .19, -L.worst.values[i] + .3, f"{-L.worst.values[i]:.1f}", ha="center", fontsize=8.6, weight="bold", color=INK)
ax.set_xticks(np.arange(5)); ax.set_xticklabels(short, fontsize=9.6)
ax.set_ylabel("ATR at entry")
ax.legend(frameon=False, fontsize=9)
ax.set_title("The tail is where it acts", fontsize=11.8, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.386, .508, "The worst single trade in 2,721 falls from −17.0 ATR to −3.2, and the\n"
                     "5th percentile from −5.4 to −2.4. That is what a stop is FOR.",
         fontsize=8.6, color=INK2, va="top")

ax = fig.add_subplot(gs[0, 2])
ax.bar(np.arange(5), L.win.values * 100, .62, color=AQUA, zorder=3)
for i, v in enumerate(L.win.values * 100):
    ax.text(i, v + .5, f"{v:.1f}%", ha="center", fontsize=9.4, weight="bold", color=INK)
ax2 = ax.twinx()
ax2.plot(np.arange(5), L.R.values, "-o", lw=2.4, ms=8, color=RED)
ax2.set_ylabel("expectancy, ATR", color=RED)
ax2.axhline(0, color=RED, lw=1, ls=":")
ax.set_xticks(np.arange(5)); ax.set_xticklabels(short, fontsize=9.6)
ax.set_ylabel("win rate (bars)"); ax.set_ylim(0, 66)
ax.set_title("Winners secured, mean unmoved", fontsize=11.8, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.700, .508, f"Bars = win rate, red line = expectancy. Win rate 45.2% → {L.win.iloc[-1]:.1%};\n"
                     f"expectancy {L.R.iloc[0]:+.4f} → {L.R.iloc[-1]:+.4f} ATR, a day-block bootstrap on the\n"
                     f"difference giving p {L.boot_p.iloc[-1]:.3f}. Nothing was added and nothing was lost.",
         fontsize=8.6, color=INK2, va="top")

ax = fig.add_subplot(gs[1, 0])
cells = CF[CF.cfg.isin(["A  baseline", "E  + clock tighten"])].copy()
cells["cell"] = cells.feed + " " + cells.side + "\n" + cells.block.str[:4].str.lower()
p = cells.pivot_table(index="cell", columns="cfg", values="dd")
x = np.arange(len(p)); w = .38
ax.bar(x - w/2, p["A  baseline"], w, color=MUTE, label="A baseline", zorder=3)
ax.bar(x + w/2, p["E  + clock tighten"], w, color=AQUA, label="E full policy", zorder=3)
for i in range(len(p)):
    red = 1 - p["E  + clock tighten"].iloc[i] / p["A  baseline"].iloc[i]
    ax.text(x[i], max(p.iloc[i]) + 14, f"−{red:.0%}", ha="center", fontsize=8.6, weight="bold", color=AQUA)
ax.set_xticks(x); ax.set_xticklabels(p.index, fontsize=8.2)
ax.set_ylabel("max drawdown, ATR"); ax.set_ylim(0, 700)
ax.legend(frameon=False, fontsize=9)
ax.set_title("Drawdown falls in 8 of 8 cells", fontsize=11.8, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.062, .092, "16% to 83% lower, on both feeds, both sides and both blocks. The most\n"
                     "consistent effect in the study, and the one a sizing decision rests on.",
         fontsize=8.6, color=INK2, va="top")

ax = fig.add_subplot(gs[1, 1])
d = CF[CF.cfg == "E  + clock tighten"].copy()
d["cell"] = d.feed + " " + d.side + " " + d.block.str[:4].str.lower()
d = d.sort_values("dR")
c = [AQUA if v > 0 else RED for v in d.dR]
ax.barh(np.arange(len(d)), d.dR, .62, color=c, zorder=3)
for i, (v, p_) in enumerate(zip(d.dR, d.boot_p)):
    ax.text(v + (.012 if v >= 0 else -.012), i, f"{v:+.3f}  (p {p_:.2f})", va="center",
            ha="left" if v >= 0 else "right", fontsize=8.4, color=INK)
ax.axvline(0, color=INK2, lw=1.4)
ax.set_yticks(np.arange(len(d))); ax.set_yticklabels(d.cell, fontsize=8.6)
ax.set_xlabel("change in expectancy vs the baseline, ATR")
ax.set_xlim(-.68, .48)
ax.set_title("Expectancy: 7 of 8 up, 0 of 8 significant", fontsize=11.8, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="x", alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.386, .092, "Seven of eight cells improve and not one clears p ≤ 0.05. The single large\n"
                     "negative is MT long on the locked block — the gold rally again.",
         fontsize=8.6, color=INK2, va="top")

ax = fig.add_subplot(gs[1, 2])
d = W3.copy(); d["cell"] = d.feed + " " + d.block.str[:4].str.lower()
x = np.arange(len(d)); w = .36
ax.bar(x - w/2, d.trail_paid, w, color=AQUA, label="what the trail paid", zorder=3)
ax.bar(x + w/2, d.flatten_would_pay, w, color=MUTE, label="what 11:00 would have paid", zorder=3)
for i in range(len(d)):
    ax.text(x[i], max(d.trail_paid.iloc[i], d.flatten_would_pay.iloc[i]) + .05,
            f"{d.edge.iloc[i]:+.3f}", ha="center", fontsize=8.8, weight="bold",
            color=AQUA if d.edge.iloc[i] > 0 else RED)
ax.set_xticks(x); ax.set_xticklabels(d.cell, fontsize=8.8)
ax.set_ylabel("ATR on the trades the trail closed")
ax.legend(frameon=False, fontsize=8.6)
ax.set_title("The trail's counterfactual", fontsize=11.8, weight="bold", color=INK, loc="left", pad=8)
ax.set_ylim(0, 2.15)
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.700, .092, "Positive on three cells and −0.67 ATR on MT locked — the gold\n"
                     "rally, where the tail arrived before 11:00 and the trail cut it off.\n"
                     "On every cell about half the trades it closed would have\n"
                     "finished better without it.",
         fontsize=8.6, color=RED, weight="bold", va="top")
fig.savefig(R + "xheat_bought.png", dpi=140, facecolor="white")
print("wrote", R + "xheat_bought.png")

# ============================================================== FIGURE 3 -- THE LIMITS
fig = plt.figure(figsize=(16.4, 7.4))
gs = fig.add_gridspec(1, 3, wspace=.42, left=.135, right=.985, top=.760, bottom=.180)
head(fig, "Where this stops",
     ["The exit work does what was asked. What it cannot do is create an edge that the entry does not have, and that limit is measurable rather than rhetorical."],
     "Verdict: 0 of 6 declared entries is profitable in this window on the long feed, and 0 of 4,480 exit configurations turns that around. The entry is the hole.",
     vcol=RED)

ax = fig.add_subplot(gs[0, 0])
d = EN[(EN.block == "research")].pivot_table(index="entry", columns="feed", values="R")
d = d.sort_values("ISO")
x = np.arange(len(d)); w = .38
ax.barh(x - w/2, d.ISO, w, color=[AQUA if v > 0 else RED for v in d.ISO], label="ISO 2010-2026", zorder=3)
ax.barh(x + w/2, d.MT, w, color=[AQUA if v > 0 else RED for v in d.MT], alpha=.5, label="MT 2022-2026", zorder=3)
ax.axvline(0, color=INK2, lw=1.4)
ax.set_yticks(x); ax.set_yticklabels(d.index, fontsize=9)
ax.set_xlabel("expectancy in ATR, research block")
ax.set_xlim(-.40, .13)
ax.legend(frameon=False, fontsize=8.8, loc="upper left")
ax.set_title("Six declared entries, none tuned", fontsize=11.8, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="x", alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.135, .105, "All six negative on the long feed. Four are marginally positive on MT,\n"
                     "whose 2022-2026 span is the gold rally and whose research block\n"
                     "is 2022-2024 — not an independent second opinion on direction.",
         fontsize=8.6, color=INK2, va="top")

ax = fig.add_subplot(gs[0, 1])
S_ = FL[FL.feed == "ISO"]
ax.hist(S_.ext_up.clip(-3, 4), bins=48, color=BLUE, alpha=.85, zorder=3)
ax.axvline(0, color=RED, lw=2.4, ls="--")
ax.set_xlabel("how much further the session ran AFTER 11:00, ATR")
ax.set_ylabel("sessions")
ax.set_title("What the 11:00 flatten forfeits", fontsize=11.8, weight="bold", color=INK, loc="left", pad=8)
ax.grid(alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.text(.432, .105, f"Only {(S_.ext_up>0).mean():.1%} of sessions extend past their own 11:00 high at all,\n"
                     f"and the window holds a median 71% of the whole 07:00-16:00\n"
                     f"upside range. That is WHY a trail is affordable here and destructive\n"
                     f"on every open-ended system this branch has measured.",
         fontsize=8.6, color=INK2, va="top")

ax = fig.add_subplot(gs[0, 2])
ax.axis("off")
rows = [["", "baseline", "full policy", "change"],
        ["mean loss / losing trade", "−2.215 ATR", "−1.336 ATR", "−40%"],
        ["5th-percentile trade", "−5.357 ATR", "−2.368 ATR", "−56%"],
        ["worst single trade", "−17.00 ATR", "−3.204 ATR", "−81%"],
        ["max drawdown", "435.7 ATR", "366.8 ATR", "−16%"],
        ["win rate", "45.2%", "47.8%", "+2.6 pts"],
        ["expectancy", "−0.127 ATR", "−0.128 ATR", "flat"]]
tb = ax.table(cellText=rows[1:], colLabels=rows[0], loc="upper center", cellLoc="center",
              colWidths=[.46, .21, .21, .20])
tb.auto_set_font_size(False); tb.set_fontsize(8.8); tb.scale(1, 2.0)
for j in range(4):
    tb[0, j].set_facecolor("#eef1f5"); tb[0, j].set_text_props(weight="bold", color=INK)
for i in range(1, len(rows)):
    for j in range(4):
        tb[i, j].set_edgecolor(GRID)
    tb[i, 0].set_text_props(ha="left")
tb[6, 3].set_text_props(weight="bold", color=RED)
for i in (1, 2, 3, 4):
    tb[i, 3].set_text_props(weight="bold", color=AQUA)
ax.set_title("ISO long, research block", fontsize=11.8, weight="bold", color=INK, loc="left", pad=8)
fig.text(.728, .105, "Every risk number improves by a lot and the mean does\n"
                     "not move at all. The exits transform the same trades into a\n"
                     "much smaller-tailed distribution with the same expectancy.\n"
                     "If the entry had an edge, this is the machinery that would\n"
                     "let you size it — it does not supply one.",
         fontsize=8.6, color=INK2, va="top")
fig.savefig(R + "xheat_limits.png", dpi=140, facecolor="white")
print("wrote", R + "xheat_limits.png")
