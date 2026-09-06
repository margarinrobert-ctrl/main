import os, sys, json
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTE, GRID = "#1c1f24", "#4a5058", "#8b929c", "#e6e9ed"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#c8ccd2", "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "figure.facecolor": "white"})
L = pd.read_csv("results/ibopt/gate1_ladder.csv")
T = pd.read_parquet("results/ibopt/optuna_trials.parquet"); ok = T[T.n_res >= 150]
Rf = pd.read_csv("results/ibopt/locked_finalists.csv")
M = pd.read_csv("results/ibopt/locked_meta_retdd.csv")

fig = plt.figure(figsize=(15.4, 11.2))
gs = fig.add_gridspec(2, 2, hspace=0.5, wspace=0.26, left=0.07, right=0.95, top=0.87, bottom=0.11)
fig.text(0.07, 0.96, "Initial Balance retracement on US30", fontsize=21, weight="bold", color=INK)
fig.text(0.07, 0.93, "US30_LONG_15m 2016-10 to 2025-07 (research to 2022-06-27), US30_ISO_15m 2025-07 to 2026-08 as a second provider. "
                     "3,600 Optuna trials, 30 features, one locked read.", fontsize=10.5, color=INK2)
fig.text(0.07, 0.905, "Verdict: Gate 1 fails as published, the search finds a long drift exposure, and every finalist is negative on the untouched 2025-26 block.",
         fontsize=11, color=ORANGE, weight="bold")

# 1. the mechanism's own prediction: the retracement ladder
ax = fig.add_subplot(gs[0, 0])
x = np.arange(len(L))
ax.bar(x - 0.18, L.pct, 0.36, color=ORANGE, label="the rule", zorder=3)
ax.bar(x + 0.18, L.ctl_med, 0.36, color=MUTE, label="risk-matched random entry", zorder=3)
ax.axhline(0, color=INK2, lw=1)
for i, p in enumerate(L.p):
    ax.text(i, 0.002, f"p {p:.2f}", ha="center", fontsize=8.5, color=INK2)
ax.set_xticks(x); ax.set_xticklabels([f"{r:.2f}" for r in L.retr])
ax.set_xlabel("retracement into the IB range (fraction)"); ax.set_ylabel("% of entry price per trade")
ax.set_title("The mechanism predicts a rising ladder; US30 gives a flat one", fontsize=12.5, weight="bold", color=INK, loc="left", pad=9)
ax.legend(frameon=False, fontsize=9, loc="lower left"); ax.grid(axis="y", alpha=.25, color=GRID); ax.set_axisbelow(True)

# 2. the search population: research vs locked
ax = fig.add_subplot(gs[0, 1])
fin = ok[np.isfinite(ok.tot_lock)]
ax.scatter(fin.tot_res, fin.tot_lock, s=6, alpha=.25, color=MUTE, linewidths=0, rasterized=True)
ax.axhline(0, color=INK2, lw=1); ax.axvline(0, color=INK2, lw=1)
best = fin.sort_values("tot_res", ascending=False).head(28)
ax.scatter(best.tot_res, best.tot_lock, s=22, color=ORANGE, label="top 1% on research", zorder=4)
cc = np.corrcoef(fin.tot_res, fin.tot_lock)[0, 1]
ax.text(0.03, 0.95, f"{len(fin):,} scorable trials, 62.6% profitable on research\ncorr(research, locked) {cc:+.2f}\ntop 1%: research +31.9% -> locked +13.8%",
        transform=ax.transAxes, va="top", fontsize=9.5, color=INK2, bbox=dict(boxstyle="round,pad=0.4", fc="white", ec=GRID))
ax.set_xlabel("research total, % of price"); ax.set_ylabel("locked total, % of price")
ax.set_title("The Optuna population, locked never used for selection", fontsize=12.5, weight="bold", color=INK, loc="left", pad=9)
ax.legend(frameon=False, fontsize=9, loc="lower right"); ax.grid(alpha=.25, color=GRID)

# 3. finalists across the three blocks
ax = fig.add_subplot(gs[1, 0])
iso = {"total": -0.0570, "pf": -0.0925, "retdd": -0.0412, "published": -0.0320}
names = ["published", "total", "pf", "retdd"]
x = np.arange(len(names)); w = 0.26
res = [Rf[(Rf.primary == n) & (Rf.block == "research")].pct.iloc[0] for n in names]
loc = [Rf[(Rf.primary == n) & (Rf.block == "LOCKED")].pct.iloc[0] for n in names]
ax.bar(x - w, res, w, color=BLUE, label="research (chose)", zorder=3)
ax.bar(x, loc, w, color=AQUA, label="locked LONG", zorder=3)
ax.bar(x + w, [iso[n] for n in names], w, color=ORANGE, label="ISO 2025-26 (untouched)", zorder=3)
ax.axhline(0, color=INK2, lw=1)
ax.set_xticks(x); ax.set_xticklabels(["as published", "Optuna: total", "Optuna: PF", "Optuna: ret/DD"], fontsize=9.5)
ax.set_ylabel("% of entry price per trade")
ax.set_title("Every finalist is negative on the block nothing touched", fontsize=12.5, weight="bold", color=INK, loc="left", pad=9)
ax.legend(frameon=False, fontsize=9, loc="lower left", ncol=1); ax.grid(axis="y", alpha=.25, color=GRID); ax.set_axisbelow(True)

# 4. the meta layer: calibration and uplift on locked
ax = fig.add_subplot(gs[1, 1])
kp = M.keep.to_numpy(); kf = M.kept_frac.to_numpy()
ax.plot(kp, kp, ls="--", color=MUTE, lw=1.2, label="calibrated (kept = keep)")
ax.plot(kp, kf, marker="o", color=BLUE, lw=2, ms=7, label="fraction actually kept on locked")
ax2 = ax.twinx()
ax2.bar(kp, M.uplift.fillna(0), width=0.06, color=[AQUA if u > 0 else ORANGE for u in M.uplift.fillna(0)], alpha=.55, zorder=2)
ax2.axhline(0, color=INK2, lw=0.8); ax2.set_ylabel("locked uplift, %/event (bars)", color=INK2)
ax2.set_ylim(-0.12, 0.30)
ax.set_xlabel("research keep fraction"); ax.set_ylabel("kept fraction on locked")
ax.set_ylim(0, 0.9); ax.set_xlim(0.35, 0.85)
ax.set_title("Meta layer: not calibrated, best research cell inverts", fontsize=12.5, weight="bold", color=INK, loc="left", pad=9)
ax.legend(frameon=False, fontsize=9, loc="lower right"); ax.grid(alpha=.25, color=GRID)
for k, u, p in zip(kp, M.uplift.fillna(0), M.rand_filter_p.fillna(1)):
    ax2.text(k, u + (0.004 if u >= 0 else -0.012), f"p {p:.2f}", ha="center", fontsize=8, color=INK2)

fig.text(0.07, 0.03, "Gate 1 as published: -0.0167 %/trade, bootstrap p 1.000, gross negative at zero cost. Always-long on the same days beats the total-return optimum (+0.0675 vs +0.0450). "
                     "Deflated Sharpe 0.000 at 3,698 looks.", fontsize=9.5, color=MUTE, wrap=True)
fig.savefig("results/ibopt/ibopt_verdict.png", dpi=150, facecolor="white"); print("wrote results/ibopt/ibopt_verdict.png")
