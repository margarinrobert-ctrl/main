import sys, os
sys.path.insert(0, "research"); sys.path.insert(0, "research/s310")
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

R = "results/s310/"
kw = pd.read_csv(R + "t1_kw_grid.csv")
gc = pd.read_csv(R + "t2_geom_carry.csv")
gm = pd.read_csv(R + "t2_geom_matched.csv")
A = pd.read_csv(R + "t5_null_entry.csv")
B = pd.read_csv(R + "t5_null_side.csv")
DS = pd.read_csv(R + "t5_deflated.csv")
MC = pd.read_csv(R + "t3_montecarlo.csv")

INK = "#1b1d21"; MUT = "#6b7078"; ACC = "#1f6f8b"; BAD = "#b4483c"; GRY = "#a9adb4"; WARM = "#c98a3e"
plt.rcParams.update({"font.size": 8.4, "axes.edgecolor": "#c8ccd2", "axes.labelcolor": INK,
                     "text.color": INK, "xtick.color": MUT, "ytick.color": MUT,
                     "axes.titlesize": 9.5, "axes.titleweight": "bold"})

fig = plt.figure(figsize=(14.2, 10.2))
gs = fig.add_gridspec(3, 3, hspace=0.66, wspace=0.30,
                      left=0.065, right=0.972, top=0.878, bottom=0.150)
fig.suptitle("S3 flow exhaustion on a 10-minute MNQ chart: the full battery",
             fontsize=13.4, fontweight="bold", x=0.065, ha="left", y=0.963)
fig.text(0.065, 0.930, "NQ 1-minute resampled to 10m, 766 sessions 2022-12 to 2025-12, "
         "07:00-11:00 New York, flat at 11:00, MNQ all-in round turn 1.72 pts.  "
         "Research to 2024-11-27.", fontsize=8.5, color=MUT, ha="left")

# 1 -- (k,w) grid transfer
ax = fig.add_subplot(gs[0, 0])
r = kw[(kw.block == "research") & (kw.n >= 30)][["k", "w", "pts"]]
l = kw[(kw.block == "LOCKED") & (kw.n >= 30)][["k", "w", "pts"]]
j = r.merge(l, on=["k", "w"], suffixes=("_r", "_l"))
ax.scatter(j.pts_r, j.pts_l, s=42, c=ACC, alpha=0.82, edgecolor="white", linewidth=0.6)
ax.axhline(0, color=INK, lw=0.9); ax.axvline(0, color=INK, lw=0.9)
ax.axhspan(0, ax.get_ylim()[1], xmin=0, xmax=0.5, color=BAD, alpha=0.06)
ax.set_xlabel("research pts / trade"); ax.set_ylabel("LOCKED pts / trade")
ax.set_title(f"(k,w) grid: {(j.pts_r>0).mean():.0%} profitable on research,\n"
             f"{(j.pts_l>0).mean():.0%} on locked", fontsize=9.2)
ax.text(0.03, 0.95, "shaded = loses where it may choose,\nwins where it may not",
        transform=ax.transAxes, fontsize=7, color=BAD, va="top")

# 2 -- geometry marginal by stop
ax = fig.add_subplot(gs[0, 1])
for df, lab, col in ((gc, "CARRY k3/w20", ACC), (gm, "MATCHED k2/w10", WARM)):
    m = df.groupby("stop")[["pts_r", "pts_l"]].mean()
    ax.plot(m.index, m.pts_r, "o-", color=col, lw=1.9, ms=5, label=f"{lab} research")
    ax.plot(m.index, m.pts_l, "o--", color=col, lw=1.5, ms=4, alpha=0.55, label=f"{lab} locked")
ax.axhline(0, color=INK, lw=0.9)
ax.set_xlabel("stop, x ATR"); ax.set_ylabel("mean pts / trade over the grid")
ax.set_title("Every stop rung: negative on research,\npositive on locked", fontsize=9.2)
ax.legend(fontsize=6.4, frameon=False, ncol=1, loc="upper left")

# 3 -- the one-rung box
ax = fig.add_subplot(gs[0, 2])
box = gc[(gc.stop.between(2.0, 4.0)) & (gc.tgt.isin([0.0, 3.0, 4.0])) &
         (gc.be.isin([0.0, 1.0])) & (gc.arm.isin([0.0, 1.0]))]
parts = ax.violinplot([box.pts_r.to_numpy(), box.pts_l.to_numpy()], showmedians=True)
for i, pc in enumerate(parts["bodies"]):
    pc.set_facecolor(BAD if i == 0 else ACC); pc.set_alpha(0.55)
for key in ("cbars", "cmins", "cmaxes", "cmedians"):
    parts[key].set_color(INK); parts[key].set_linewidth(1.0)
ax.axhline(0, color=INK, lw=1.1, ls="--")
ax.set_xticks([1, 2]); ax.set_xticklabels(["research", "LOCKED"])
ax.set_ylabel("pts / trade")
ax.set_title(f"One-rung box, {len(box)} cells:\n0% profitable on research, 100% on locked",
             fontsize=9.2)

# 4 -- null A
ax = fig.add_subplot(gs[1, 0])
lbl = [c.split(" k")[0].replace("10m ", "10m\n").replace("5m reference", "5m\nREF") + "\n" + ("res" if b == "research" else "LOCK") for c, b in zip(A.cell, A.block)]
x = np.arange(len(A))
ax.bar(x - 0.19, A.rule, 0.38, color=ACC, label="the rule")
ax.bar(x + 0.19, A.ctl_med, 0.38, color=GRY, label="matched random entry")
ax.axhline(0, color=INK, lw=0.9)
for i, p in enumerate(A.p):
    ax.text(i, 14.4, f"p {p:.3f}", ha="center", fontsize=6.5,
            color=BAD if p > 0.05 else ACC)
ax.set_xticks(x); ax.set_xticklabels(lbl, fontsize=6.0)
ax.set_ylabel("pts / trade"); ax.set_ylim(-11, 17.5)
ax.set_title("Null A: random entry, same geometry", fontsize=9.2)
ax.legend(fontsize=6.4, frameon=False, loc="lower right")

# 5 -- null B
ax = fig.add_subplot(gs[1, 1])
ax.bar(x - 0.19, B.rule, 0.38, color=ACC, label="the rule")
ax.bar(x + 0.19, B.ctl_med, 0.38, color=GRY, label="coin-flip side, same bars")
ax.axhline(0, color=INK, lw=0.9)
for i, p in enumerate(B.p):
    ax.text(i, 14.4, f"p {p:.3f}", ha="center", fontsize=6.5,
            color=BAD if p > 0.05 else ACC)
ax.set_xticks(x); ax.set_xticklabels(lbl, fontsize=6.0)
ax.set_ylabel("pts / trade"); ax.set_ylim(-11, 17.5)
ax.set_title("Null B: the direction call alone", fontsize=9.2)
ax.legend(fontsize=6.4, frameon=False, loc="lower right")

# 6 -- deflation
ax = fig.add_subplot(gs[1, 2])
emax = DS.E_max_null.iloc[0]
ax.barh(np.arange(len(DS)), DS.sr_per_trade,
        color=[BAD if v < 0 else ACC for v in DS.sr_per_trade], height=0.66)
ax.axvline(emax, color=INK, lw=1.6, ls="--")
ax.set_xlim(min(DS.sr_per_trade.min() * 1.15, -0.02), emax * 1.55)
ax.text(emax * 1.05, 0.2, f"E[max | pure noise]\n{emax:.3f}", fontsize=6.6, color=INK, va="top")
ax.set_yticks(np.arange(len(DS)))
ax.set_yticklabels([f"{c.split(' k')[0]} {b}" for c, b in zip(DS.cell, DS.block)], fontsize=6.4)
ax.invert_yaxis(); ax.axvline(0, color=INK, lw=0.9)
ax.set_xlabel("Sharpe per trade")
ax.set_title("Deflation at N = 1,295 looks:\nnothing clears the noise floor", fontsize=9.2)

# 7 -- regime by year
ax = fig.add_subplot(gs[2, 0])
yr = pd.read_csv(R + "t5_years.csv") if os.path.exists(R + "t5_years.csv") else None
years = [2023, 2024, 2025]
series = {"10m carry": [-10.08, -5.53, 6.02], "10m matched": [-4.98, 0.19, 9.17],
          "5m carry": [-1.82, 8.45, 10.32]}
xx = np.arange(3)
for i, (k, v) in enumerate(series.items()):
    ax.bar(xx + (i - 1) * 0.27, v, 0.27,
           color=[ACC, WARM, "#4a7c59"][i], label=k)
ax.axhline(0, color=INK, lw=0.9)
ax.axvline(1.35, color=BAD, lw=1.2, ls=":")
ax.text(1.40, -9.4, "research ends\n2024-11", fontsize=6.6, color=BAD)
ax.set_xticks(xx); ax.set_xticklabels(years)
ax.set_ylabel("pts / trade"); ax.set_title("The sign flips in 2024 at 5m\nand not until 2025 at 10m",
                                           fontsize=9.2)
ax.legend(fontsize=6.6, frameon=False, loc="upper left")

# 8 -- correlation across timeframes
ax = fig.add_subplot(gs[2, 1])
C = pd.read_csv(R + "t4_corr_tf_research.csv", index_col=0)
im = ax.imshow(C.to_numpy(), cmap="RdBu_r", vmin=-1, vmax=1)
ax.set_xticks(range(len(C))); ax.set_yticks(range(len(C)))
short = [c.replace("always-long", "long") for c in C.columns]
ax.set_xticklabels(short, rotation=42, ha="right", fontsize=6.2)
ax.set_yticklabels(short, fontsize=6.2)
for i in range(len(C)):
    for jx in range(len(C)):
        v = C.to_numpy()[i, jx]
        ax.text(jx, i, f"{v:.2f}", ha="center", va="center", fontsize=5.8,
                color="white" if abs(v) > 0.6 else INK)
ax.set_title("Daily P&L correlation, research", fontsize=9.2)
plt.colorbar(im, ax=ax, fraction=0.045, pad=0.03).ax.tick_params(labelsize=6)

# 9 -- verdict panel
ax = fig.add_subplot(gs[2, 2]); ax.axis("off")
rows = [["test", "10m result"],
        ["research block", "NEGATIVE at every setting"],
        ["grid profitable (research)", "0% of 630"],
        ["corr(research, locked)", "-0.823"],
        ["random-entry null", "p 0.922 / 0.678"],
        ["coin-flip-side null", "p 0.958 / 0.735"],
        ["execution MC", "P(total<=0) = 1.00"],
        ["reality check", "p 0.660  FAIL"],
        ["deflated Sharpe", "0.000 - 0.110"]]
tb = ax.table(cellText=rows[1:], colLabels=rows[0], loc="center", cellLoc="left",
              bbox=[0.0, 0.06, 1.0, 0.90])
tb.auto_set_font_size(False); tb.set_fontsize(7.6)
for (rr, cc), cell in tb.get_celld().items():
    cell.set_edgecolor("#d8dbe0")
    if rr == 0:
        cell.set_facecolor("#eef1f4"); cell.set_text_props(weight="bold")
    elif cc == 1:
        cell.set_text_props(color=BAD)
ax.set_title("Verdict", fontsize=9.5, y=0.99)

fig.text(0.065, 0.092,
         "The rule does not survive the move to 10 minutes: it loses on the block permitted to choose it and wins on the block read once, at EVERY one of 630 geometry\n"
         "cells, with corr(research, locked) = -0.823.  Cost is ruled out in advance - the round turn is 2.93% of a 3xATR stop at 10m against 3.78% at 5m.  And at the\n"
         "counted trial count NOT EVEN THE 5-MINUTE VERSION clears the noise floor: its locked Sharpe/trade is 0.137 against an E[max | pure noise] of 0.216.",
         fontsize=8.3, color=INK, ha="left", va="top")
fig.savefig(R + "s310_battery.png", dpi=150, facecolor="white")
print("wrote " + R + "s310_battery.png")
