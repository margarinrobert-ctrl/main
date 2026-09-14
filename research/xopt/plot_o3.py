import pickle
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
BLUE, ORANGE, AQUA, PURP, GOLD = "#2a78d6", "#eb6834", "#1baf7a", "#7a5cc7", "#c9a227"
INK, INK2, MUTE, GRID = "#1c1f24", "#4a5058", "#8b929c", "#e6e9ed"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#c8ccd2", "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "figure.facecolor": "white"})
R = "results/xopt/"
MC = pd.read_csv(R + "o3_montecarlo.csv")
curves = pickle.load(open(R + "o3_curves.pkl", "rb"))
CP = pd.read_csv(R + "o3_corr_params.csv", index_col=0)
CC = pd.read_csv(R + "o3_corr_cells.csv", index_col=0)
YP = pd.read_csv(R + "o3_years.csv", index_col=0)
W = pd.read_csv(R + "o3_walkforward.csv")
PB = pd.read_csv(R + "o3_pbo.csv")
SH = lambda s: s.replace("Optuna ", "Opt ").replace("as published", "published")

# ============================================================ FIGURE 1 -- MONTE CARLO
fig = plt.figure(figsize=(15.4, 9.6))
gs = fig.add_gridspec(2, 2, hspace=0.46, wspace=0.24, left=0.075, right=0.972, top=0.845, bottom=0.085)
fig.text(0.055, 0.955, "Monte Carlo: the edge and the path are different questions",
         fontsize=19, weight="bold", color=INK)
fig.text(0.055, 0.923, "A day-block BOOTSTRAP resamples whole days with their trades attached and prices the EDGE. A PERMUTATION reorders the realised trades and prices the PATH —",
         fontsize=10, color=INK2)
fig.text(0.055, 0.900, "it cannot move the endpoint, so it answers a drawdown question only. 3,000 draws each.",
         fontsize=10, color=INK2)
fig.text(0.055, 0.872, "Verdict: every locked-block bootstrap on an Optuna cell sits on the wrong side of zero (p 0.61 / 0.93 / 1.00), and the p99 drawdown is 1.1x-1.6x the realised one.",
         fontsize=10.4, color=ORANGE, weight="bold")

# (a) bootstrap distributions, locked
ax = fig.add_subplot(gs[0, 0])
cols = {"as published": BLUE, "Optuna excess": ORANGE, "Optuna excess_pf": PURP, "Optuna return": GOLD}
for (nm, bn), d in curves.items():
    if bn != "locked":
        continue
    ax.hist(d["boot"], bins=60, histtype="step", lw=2, color=cols.get(nm, MUTE), label=SH(nm))
ax.axvline(0, color=INK2, lw=2, ls="--")
ax.text(0.005, 0.96, " zero", transform=ax.transAxes, color=INK2, fontsize=9, va="top")
ax.set_xlabel("bootstrapped mean R per trade — LOCKED block")
ax.set_ylabel("draws")
ax.set_title("The edge: day-block bootstrap, locked", fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=8.4); ax.grid(alpha=.2, color=GRID); ax.set_axisbelow(True)

# (b) research vs locked bootstrap p
ax = fig.add_subplot(gs[0, 1])
p = MC.pivot_table(index="cell", columns="block", values="boot_p")
p = p.reindex([c for c in cols if c in p.index])
x = np.arange(len(p)); w = 0.38
ax.bar(x - w/2, p.get("research", pd.Series(dtype=float)), w, color=BLUE, label="research", zorder=3)
ax.bar(x + w/2, p.get("locked", pd.Series(dtype=float)), w, color=ORANGE, label="locked", zorder=3)
ax.axhline(0.05, color=ORANGE, lw=2, ls="--")
ax.text(0.02, 0.075, "p = 0.05", color=ORANGE, fontsize=9, weight="bold", ha="left")
ax.set_xticks(x); ax.set_xticklabels([SH(i) for i in p.index], fontsize=8.6)
ax.set_ylabel("P(mean R $\\leq$ 0)"); ax.set_ylim(0, 1.05)
ax.set_title("P(the edge is zero or worse)", fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=8.6); ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)

# (c) permutation drawdown, one panel per cell on locked
ax = fig.add_subplot(gs[1, 0])
for (nm, bn), d in curves.items():
    if bn != "locked" or nm not in cols:
        continue
    ax.hist(d["dds"], bins=60, histtype="step", lw=1.8, color=cols[nm], alpha=.9, label=SH(nm))
    ax.axvline(d["real_dd"], color=cols[nm], lw=2.2, ls=":")
ax.set_xlabel("max drawdown in R from a permutation of the SAME trades — locked")
ax.set_ylabel("draws")
ax.set_title("The path: dotted = the realised drawdown", fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=8.4); ax.grid(alpha=.2, color=GRID); ax.set_axisbelow(True)

# (d) the sizing number
ax = fig.add_subplot(gs[1, 1])
m = MC[MC.block == "locked"].set_index("cell").reindex([c for c in cols if c in MC.cell.values])
x = np.arange(len(m)); w = 0.38
ax.bar(x - w/2, m.realised_dd, w, color=MUTE, label="realised drawdown", zorder=3)
ax.bar(x + w/2, m.mc_p99_dd, w, color=ORANGE, label="MC 99th percentile", zorder=3)
for i, (a_, b_, r_) in enumerate(zip(m.realised_dd, m.mc_p99_dd, m.dd_ratio)):
    ax.text(i, max(a_, b_) * 1.03, f"{r_:.2f}x", ha="center", fontsize=9.2, weight="bold", color=INK)
ax.set_xticks(x); ax.set_xticklabels([SH(i) for i in m.index], fontsize=8.6)
ax.set_ylabel("max drawdown, R"); ax.set_ylim(0, m.mc_p99_dd.max() * 1.22)
ax.set_title("Size for the p99, not for the backtest", fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=8.6, loc="upper left"); ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.savefig(R + "xopt_montecarlo.png", dpi=140, facecolor="white")
print("wrote", R + "xopt_montecarlo.png")

# ============================================================ FIGURE 2 -- CORRELATIONS
fig = plt.figure(figsize=(15.4, 8.0))
gs = fig.add_gridspec(1, 3, wspace=0.44, left=0.085, right=0.955, top=0.775, bottom=0.175)
fig.text(0.055, 0.945, "Correlation matrices", fontsize=19, weight="bold", color=INK)
fig.text(0.055, 0.910, "What the parameters do to the score, whether the candidates are actually different strategies, and how the result is spread across the years.",
         fontsize=10, color=INK2)
fig.text(0.055, 0.880, "Verdict: the excess objective loads on the stop and the range floor, and the four candidates correlate |0.06| or less in daily R — four strategies, not one wearing four names.",
         fontsize=10.4, color=ORANGE, weight="bold")

ax = fig.add_subplot(gs[0, 0])
im = ax.imshow(CP.values, cmap="RdBu_r", vmin=-0.5, vmax=0.5, aspect="auto")
ax.set_xticks(range(CP.shape[1])); ax.set_xticklabels(CP.columns, fontsize=9)
ax.set_yticks(range(CP.shape[0])); ax.set_yticklabels(CP.index, fontsize=8.6)
for i in range(CP.shape[0]):
    for j in range(CP.shape[1]):
        v = CP.values[i, j]
        ax.text(j, i, f"{v:+.2f}", ha="center", va="center", fontsize=7.6,
                color="white" if abs(v) > 0.3 else INK)
ax.set_title("parameter → research score\n(Spearman, 2,100 trials)", fontsize=11.4, weight="bold", color=INK, loc="left", pad=8)
plt.colorbar(im, ax=ax, fraction=0.046, pad=0.03)

ax = fig.add_subplot(gs[0, 1])
lab = [SH(i) for i in CC.index]
im = ax.imshow(CC.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
ax.set_xticks(range(len(lab))); ax.set_xticklabels(lab, rotation=35, ha="right", fontsize=8.6)
ax.set_yticks(range(len(lab))); ax.set_yticklabels(lab, fontsize=8.6)
for i in range(len(lab)):
    for j in range(len(lab)):
        v = CC.values[i, j]
        ax.text(j, i, f"{v:+.2f}", ha="center", va="center", fontsize=8,
                color="white" if abs(v) > 0.55 else INK)
ax.set_title("candidates' DAILY R\nagainst each other", fontsize=11.4, weight="bold", color=INK, loc="left", pad=8)
plt.colorbar(im, ax=ax, fraction=0.046, pad=0.03)

ax = fig.add_subplot(gs[0, 2])
im = ax.imshow(YP.values, cmap="RdBu_r", vmin=-1.2, vmax=1.2, aspect="auto")
ax.set_xticks(range(YP.shape[1])); ax.set_xticklabels([SH(c) for c in YP.columns], rotation=35, ha="right", fontsize=8.4)
ax.set_yticks(range(YP.shape[0])); ax.set_yticklabels(YP.index.astype(int), fontsize=8)
for i in range(YP.shape[0]):
    for j in range(YP.shape[1]):
        v = YP.values[i, j]
        if np.isfinite(v):
            ax.text(j, i, f"{v:+.2f}", ha="center", va="center", fontsize=6.8,
                    color="white" if abs(v) > 0.7 else INK)
ax.set_title("R per trade, year by year", fontsize=11.4, weight="bold", color=INK, loc="left", pad=8)
plt.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
fig.text(0.055, 0.045, "The year grid is where a single strong year hides: a column that is carried by one or two rows is a regime, not an edge.", fontsize=9.4, color=MUTE)
fig.savefig(R + "xopt_correlations.png", dpi=140, facecolor="white")
print("wrote", R + "xopt_correlations.png")

# ============================================================ FIGURE 3 -- WALK-FORWARD / PBO
fig = plt.figure(figsize=(15.4, 9.2))
gs = fig.add_gridspec(2, 2, hspace=0.52, wspace=0.24, left=0.075, right=0.972, top=0.818, bottom=0.085)
fig.text(0.055, 0.955, "Walk-forward and the overfitting probability", fontsize=19, weight="bold", color=INK)
fig.text(0.055, 0.921, "Rolling 36-month train / 12-month test. The re-chosen arm re-runs the SELECTION inside every training window; a random cell from the same pool sits beside it,",
         fontsize=10, color=INK2)
fig.text(0.055, 0.898, "because without one 'the optimiser won' is unfalsifiable. CSCV then gives P(overfit) over all C(12,6) = 924 symmetric splits.",
         fontsize=10, color=INK2)
fig.text(0.055, 0.870, "Read the SHADED folds only for the three Optuna arms: the research block ends 2020-05, so every earlier fold is a fold those cells were chosen on.",
         fontsize=10.4, color=ORANGE, weight="bold")

arms = [c for c in ("re_chosen", "random_cell", "as published", "Optuna excess",
                    "Optuna excess_pf", "Optuna return") if c in W.columns]
COL = {"re_chosen": ORANGE, "random_cell": MUTE, "as published": BLUE,
       "Optuna excess": AQUA, "Optuna excess_pf": PURP, "Optuna return": GOLD}

POST = np.asarray(W.test_from.astype(str) >= "2021-01")

ax = fig.add_subplot(gs[0, :])
x = np.arange(len(W)); w = 0.8 / len(arms)
if POST.any():
    ax.axvspan(x[POST][0] - 0.5, x[-1] + 0.5, color=ORANGE, alpha=.07, zorder=0)
for i, a in enumerate(arms):
    ax.bar(x + (i - len(arms)/2 + 0.5) * w, W[a], w, color=COL.get(a, MUTE), label=SH(a), zorder=3)
ax.axhline(0, color=INK2, lw=1.2)
ax.set_xticks(x); ax.set_xticklabels([f"{a}\n→{b}" for a, b in zip(W.test_from, W.test_to)], fontsize=8.4)
ax.set_ylabel("out-of-sample R per trade")
ax.set_title("Per fold — the re-chosen arm against a random cell and the fixed constants",
             fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=8.4, ncol=len(arms))
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)
if POST.any():
    ax.text(x[POST][0] - 0.4, ax.get_ylim()[0] * 0.93, " post research cut", fontsize=9,
            color=ORANGE, weight="bold", va="bottom", ha="left")

ax = fig.add_subplot(gs[1, 0])
mean = W[arms].mean()
post = W.loc[POST, arms].mean()
order = mean.sort_values()
ax.barh(np.arange(len(order)), order.values, 0.62,
        color=[COL.get(i, MUTE) for i in order.index], zorder=3, label="all 13 folds")
ax.scatter(post[order.index].values, np.arange(len(order)), s=64, marker="D",
           facecolor="white", edgecolor=INK, lw=1.6, zorder=5, label="post-cut folds only (5)")
lo = min(order.values.min(), post.min()); hi = max(order.values.max(), post.max())
pad = (hi - lo) * 0.30
ax.set_xlim(lo - pad, hi + pad)
for i, v in enumerate(order.values):
    ax.text(v + (hi - lo) * 0.015 * (1 if v >= 0 else -1), i - 0.30, f"{v:+.3f}", va="center",
            ha="left" if v >= 0 else "right", fontsize=8.6, color=INK)
ax.axvline(0, color=INK2, lw=1.2)
ax.set_yticks(np.arange(len(order))); ax.set_yticklabels([SH(i) for i in order.index], fontsize=9)
ax.set_xlabel("mean OOS R per trade across the folds")
ax.legend(frameon=False, fontsize=8.4, loc="lower right")
ax.set_title("Mean across folds", fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="x", alpha=.2, color=GRID); ax.set_axisbelow(True)

ax = fig.add_subplot(gs[1, 1])
lg = PB.logit.to_numpy()
pbo = float((lg <= 0).mean())
ax.hist(lg, bins=50, color=BLUE, alpha=.85, zorder=3)
ax.axvline(0, color=ORANGE, lw=2.4, ls="--", zorder=4)
ax.text(0.02, 0.95, f"PBO = {pbo:.3f}\nmedian logit {np.median(lg):+.3f}",
        transform=ax.transAxes, fontsize=11, weight="bold",
        color=ORANGE if pbo > 0.5 else AQUA, va="top")
ax.text(0.98, 0.95, "left of the dashed line =\nthe in-sample winner landed\nbelow the OOS median",
        transform=ax.transAxes, fontsize=8.6, color=MUTE, va="top", ha="right")
ax.set_xlabel("logit of the IS-best cell's out-of-sample rank")
ax.set_ylabel("splits")
ax.set_title("CSCV — 924 symmetric splits", fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
ax.grid(alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.savefig(R + "xopt_walkforward.png", dpi=140, facecolor="white")
print("wrote", R + "xopt_walkforward.png")
