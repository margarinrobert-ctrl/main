import os, sys
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
BLUE, ORANGE, AQUA, PURP = "#2a78d6", "#eb6834", "#1baf7a", "#7a5cc7"
INK, INK2, MUTE, GRID = "#1c1f24", "#4a5058", "#8b929c", "#e6e9ed"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#c8ccd2", "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "figure.facecolor": "white"})
R = "results/vwapema/"
pub = pd.read_csv(R + "m1_published.csv")
pop = pd.read_csv(R + "m2_population.csv")
lock = pd.read_csv(R + "m3_locked.csv")
dsr = pd.read_csv(R + "m3_dsr.csv")
fwd = pd.read_csv(R + "m3_forward.csv")
ai = pd.read_csv(R + "m5_alwaysin.csv")
pbo = pd.read_csv(R + "m4_pbo.csv")
rk = pd.read_csv(R + "m4_ranks.csv")

fig = plt.figure(figsize=(16.2, 12.4))
gs = fig.add_gridspec(3, 2, hspace=0.66, wspace=0.26, left=0.075, right=0.972, top=0.858, bottom=0.085)
fig.text(0.055, 0.962, "The VWAP-EMA rule on US100, US30 and a reserved forward block",
         fontsize=20, weight="bold", color=INK)
fig.text(0.055, 0.936, "206,703 + 193,663 + 48,937 fifteen-minute bars. Clocks re-derived (mean bar range peaks at minute 570 = 09:30 New York on all three); "
                       "tick volume verified (corr with bar range +0.71 to +0.77).", fontsize=10.2, color=INK2)
fig.text(0.055, 0.914, "Cost is 2.5-4.3% of risk here against gold's 17%, so nothing below is a cost problem. 4,800 Optuna trials, research blocks only. US30_ISO never searched.",
         fontsize=10.2, color=INK2)
fig.text(0.055, 0.893, "Verdict: two cells clear a control on research and both invert; every deflated Sharpe is below what noise delivers at 4,840 looks; the rule loses to always-in in 120 of 158 cells.",
         fontsize=10.6, color=ORANGE, weight="bold")

# 1 published rule, research vs locked
ax = fig.add_subplot(gs[0, 0])
p = pub[pub.feed != "US30_ISO"].copy()
p["lab"] = p.feed + "\n" + p.side
labs = ["US100\nLONG", "US100\nSHORT", "US30\nLONG", "US30\nSHORT"]
x = np.arange(4); w = 0.36
res = [float(p[(p.lab == l) & (p.block == "research")].R.iloc[0]) for l in labs]
loc = [float(p[(p.lab == l) & (p.block == "LOCKED")].R.iloc[0]) for l in labs]
ax.bar(x - w/2, res, w, color=BLUE, label="research", zorder=3)
ax.bar(x + w/2, loc, w, color=ORANGE, label="locked", zorder=3)
for i, (a, b) in enumerate(zip(res, loc)):
    ax.text(i - w/2, a + (0.008 if a >= 0 else -0.02), f"{a:+.3f}", ha="center", fontsize=8.4, color=INK)
    ax.text(i + w/2, b + (0.008 if b >= 0 else -0.02), f"{b:+.3f}", ha="center", fontsize=8.4, color=INK)
ax.axhline(0, color=INK2, lw=1)
ax.annotate("clears its control\nat p 0.003", xy=(2 - w/2, res[2] * 0.55), xytext=(2.35, 0.135),
            fontsize=8.4, color=ORANGE, weight="bold", ha="left",
            arrowprops=dict(arrowstyle="->", color=ORANGE, lw=1.1))
ax.annotate("p 0.010", xy=(1 - w/2, res[1]), xytext=(0.35, 0.10), fontsize=8.4, color=ORANGE,
            weight="bold", arrowprops=dict(arrowstyle="->", color=ORANGE, lw=1.1))
ax.set_xticks(x); ax.set_xticklabels(labs, fontsize=9)
ax.set_ylabel("R per trade"); ax.set_ylim(-0.20, 0.26)
ax.set_title("The published rule, frozen — both research passes invert",
             fontsize=12.6, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=9, loc="lower left"); ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)

# 2 population transfer
ax = fig.add_subplot(gs[0, 1])
pop["lab"] = pop.feed.str.replace("US1", "US1") + "\n" + pop.study
x = np.arange(len(pop)); w = 0.28
ax.bar(x - w, pop.top1pct_res, w, color=BLUE, label="top 1% on research", zorder=3)
ax.bar(x, pop.top1pct_lock, w, color=ORANGE, label="those cells, locked", zorder=3)
ax.bar(x + w, pop.pop_lock, w, color=MUTE, label="whole population, locked", zorder=3)
ax.axhline(0, color=INK2, lw=1)
ax.set_xticks(x); ax.set_xticklabels(pop.lab, fontsize=8.6)
ax.set_ylabel("R per trade")
ax.set_title("Selecting on research bought nothing", fontsize=12.6, weight="bold", color=INK, loc="left", pad=8)
ax.set_ylim(-0.10, 1.24)
ax.legend(frameon=False, fontsize=8.6, loc="upper left", bbox_to_anchor=(0.30, 1.0))
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)
ax.text(0.02, 0.90, "85-93% of every population is profitable\non research; 30-69% on locked",
        transform=ax.transAxes, fontsize=8.6, color=INK2)

# 3 the locked read
ax = fig.add_subplot(gs[1, 0])
cells = ["Optuna totR", "Optuna pf", "Optuna retdd"]
lab, resv, locv, cols = [], [], [], []
for f in ("US100", "US30"):
    for c in cells:
        s = lock[(lock.feed == f) & (lock.cell == c)]
        lab.append(f"{f}\n{c.replace('Optuna ','')}")
        resv.append(float(s[s.block == "research"].R.iloc[0]))
        locv.append(float(s[s.block == "LOCKED"].R.iloc[0]))
x = np.arange(len(lab)); w = 0.36
ax.bar(x - w/2, resv, w, color=BLUE, label="research (all clear their control, p<=0.010)", zorder=3)
ax.bar(x + w/2, locv, w, color=ORANGE, label="locked (none clears, best p 0.100)", zorder=3)
for i, b in enumerate(locv):
    ax.text(i + w/2, b + 0.03, f"{b:+.3f}", ha="center", fontsize=8.4, color=INK)
ax.axhline(0, color=INK2, lw=1)
ax.set_xticks(x); ax.set_xticklabels(lab, fontsize=8.6)
ax.set_ylabel("R per trade")
ax.set_title("Six Optuna finalists, one locked read", fontsize=12.6, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=8.4, loc="upper right"); ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)

# 4 deflated sharpe against the noise floor
ax = fig.add_subplot(gs[1, 1])
d = dsr.copy(); d["lab"] = d.feed + " " + d.cell.str.replace("Optuna ", "Opt ").str.replace("As published ", "pub ")
d = d.sort_values("sharpe_per_trade")
ax.barh(np.arange(len(d)), d.sharpe_per_trade, 0.62,
        color=[AQUA if v > 0 else ORANGE for v in d.sharpe_per_trade], zorder=3)
ax.axvline(0.2892, color=PURP, lw=2.2, ls="--", zorder=4)
ax.text(0.2892, len(d) - 0.4, "  E[max Sharpe | pure noise]\n  over 4,840 looks = 0.289",
        color=PURP, fontsize=9, weight="bold", va="top")
ax.axvline(0, color=INK2, lw=1)
ax.set_yticks(np.arange(len(d))); ax.set_yticklabels(d.lab, fontsize=8.4)
ax.set_xlabel("Sharpe per trade, whole sample"); ax.set_xlim(-0.06, 0.40)
ax.set_title("Nothing reaches the noise floor", fontsize=12.6, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="x", alpha=.2, color=GRID); ax.set_axisbelow(True)

# 5 always-in
ax = fig.add_subplot(gs[2, 0])
g = ai.groupby(["side", "regime"]).agg(edge=("edge", "mean"), rule=("R", "mean"),
                                       always=("always_R", "mean"), n=("edge", "size"),
                                       wins=("edge", lambda s: int((s > 0).sum())))
keys = [("LONG", "bull"), ("LONG", "bear"), ("SHORT", "bull"), ("SHORT", "bear")]
x = np.arange(4); w = 0.36
ax.bar(x - w/2, [g.loc[k, "rule"] for k in keys], w, color=BLUE, label="the rule", zorder=3)
ax.bar(x + w/2, [g.loc[k, "always"] for k in keys], w, color=MUTE, label="always-in (same days,\nsame side, RULE'S OWN stop)", zorder=3)
for i, k in enumerate(keys):
    top = max(g.loc[k, "rule"], g.loc[k, "always"])
    ax.text(i, top + 0.018, f"edge {g.loc[k,'edge']:+.3f}", ha="center", fontsize=8.8,
            weight="bold", color=ORANGE)
ax.axhline(0, color=INK2, lw=1)
ax.set_xticks(x); ax.set_xticklabels([f"{a}\n{b}" for a, b in keys], fontsize=9)
ax.set_ylabel("R per trade"); ax.set_ylim(-0.16, 0.62)
ax.set_title("Inside every regime, the conditions subtract", fontsize=12.6, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=8.4, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.02))
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)
ax.text(0.5, 0.055, f"the rule beats always-in in {int(ai.edge.gt(0).sum())} of {len(ai)} cells",
        transform=ax.transAxes, ha="center", fontsize=9.2, weight="bold", color=ORANGE,
        bbox=dict(boxstyle="round,pad=0.32", fc="white", ec=ORANGE, lw=1.1))

# 6 the forward block
ax = fig.add_subplot(gs[2, 1])
z = fwd.copy()
z["lab"] = np.where(z.cell.str.startswith("As published"), z.cell,
                    z.chosen_on + " " + z.cell.str.replace("Optuna ", "Opt "))
z = z.drop_duplicates(subset="lab").dropna(subset=["R"]).sort_values("R")
ax.barh(np.arange(len(z)), z.R, 0.62, color=[AQUA if v > 0 else ORANGE for v in z.R], zorder=3)
for i, (v, n) in enumerate(zip(z.R, z.n)):
    ax.text(v + (0.012 if v >= 0 else -0.012), i, f"{v:+.3f}  (n{int(n)})",
            va="center", ha="left" if v >= 0 else "right", fontsize=8.4, color=INK)
ax.axvline(0, color=INK2, lw=1)
ax.set_yticks(np.arange(len(z))); ax.set_yticklabels(z.lab, fontsize=8.4)
ax.set_xlabel("R per trade on US30_ISO"); ax.set_xlim(-0.70, 0.34)
ax.set_title("The reserved forward block — 1 of 6 finalists survives",
             fontsize=12.6, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="x", alpha=.2, color=GRID); ax.set_axisbelow(True)

fig.text(0.055, 0.040, f"PBO {float(pbo[pbo.feed=='US100'].PBO.iloc[0]):.3f} on US100 and {float(pbo[pbo.feed=='US30'].PBO.iloc[0]):.3f} on US30 — above 0.5 means the selection is actively harmful, and the two markets disagree.",
         fontsize=9.4, color=MUTE)
fig.text(0.055, 0.018, f"The published rule's median in-sample rank in its own 400-cell pool is {float(rk[(rk.feed=='US100')&(rk.cell=='As published')].median_IS_rank.iloc[0]):.3f} on US100 and "
         f"{float(rk[(rk.feed=='US30')&(rk.cell=='As published')].median_IS_rank.iloc[0]):.3f} on US30 — below median, which is what a configuration chosen by convention looks like.",
         fontsize=9.4, color=MUTE)
fig.savefig("results/vwapema/vwapema_indices.png", dpi=140, facecolor="white")
print("wrote results/vwapema/vwapema_indices.png")
