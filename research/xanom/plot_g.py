import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
BLUE, ORANGE, AQUA, PURP = "#2a78d6", "#eb6834", "#1baf7a", "#7a5cc7"
INK, INK2, MUTE, GRID = "#1c1f24", "#4a5058", "#8b929c", "#e6e9ed"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#c8ccd2", "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "figure.facecolor": "white"})
R = "results/xanom/"
ic = pd.read_csv(R + "g1_ic.csv")
h2 = pd.read_csv(R + "g2_h2_signed.csv")

fig = plt.figure(figsize=(15.6, 10.4))
gs = fig.add_gridspec(2, 2, hspace=0.52, wspace=0.26, left=0.078, right=0.972, top=0.845, bottom=0.085)
fig.text(0.055, 0.958, "Gold at 15 minutes: what is predictable, and what it is worth",
         fontsize=19.5, weight="bold", color=INK)
fig.text(0.055, 0.928, "43 causal bar-level features on 371,586 ISO bars, every unsupervised model fitted on the research block only and applied unchanged to a "
                       "different-provider forward block.", fontsize=10.1, color=INK2)
fig.text(0.055, 0.906, "344 Newey-West tests (the horizons overlap), each beside a shuffled twin, Benjamini-Hochberg at q = 0.10.",
         fontsize=10.1, color=INK2)
fig.text(0.055, 0.878, "Verdict: forward RANGE is hugely predictable and mostly the ATR denominator; forward RETURN is not, and the best IC found is worth 0.18x the round turn.",
         fontsize=10.5, color=ORANGE, weight="bold")

# 1 return vs range: how many tests survive
ax = fig.add_subplot(gs[0, 0])
fam = ic.groupby(["fam", "label"]).ic.apply(lambda s: np.abs(s).mean()).unstack()
fam = fam.sort_values("rng")
x = np.arange(len(fam)); w = 0.38
ax.barh(x - w/2, fam["ret"], w, color=BLUE, label="forward RETURN", zorder=3)
ax.barh(x + w/2, fam["rng"], w, color=PURP, label="forward RANGE", zorder=3)
sh = ic.ic_shuf.abs().mean()
ax.axvline(sh, color=ORANGE, lw=2, ls="--", zorder=4)
ax.text(sh + 0.006, 0.6, f"shuffled-twin floor {sh:.4f}", color=ORANGE,
        fontsize=8.8, weight="bold", va="center")
ax.set_yticks(x); ax.set_yticklabels(fam.index, fontsize=9)
ax.set_xlabel("mean |Spearman IC| on the research block")
ax.set_title("Every family predicts the RANGE and none predicts the RETURN",
             fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=8.8, loc="lower right")
ax.grid(axis="x", alpha=.2, color=GRID); ax.set_axisbelow(True)

# 2 the denominator check
ax = fig.add_subplot(gs[0, 1])
rows = [("vol.atr_pct500 h96", -0.5327, 0.0507), ("vol.rv24 h96", -0.4517, 0.3566),
        ("vol.atr_pct500 h16", -0.3391, 0.1687), ("vol.rv24 h16", -0.2965, 0.3930),
        ("anm.ae_err h96", 0.0456, 0.0067), ("anm.ae_err h16", 0.0320, -0.0038)]
lab = [r[0] for r in rows]
x = np.arange(len(rows)); w = 0.38
ax.barh(x - w/2, [r[1] for r in rows], w, color=PURP, label="range / ATR at the bar", zorder=3)
ax.barh(x + w/2, [r[2] for r in rows], w, color=AQUA, label="RAW range in USD", zorder=3)
ax.axvline(0, color=INK2, lw=1.2)
ax.set_yticks(x); ax.set_yticklabels(lab, fontsize=8.6)
ax.set_xlabel("Spearman IC against the forward range")
ax.set_title("Four of six flip sign once the ATR denominator goes",
             fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=8.4, loc="lower right")
ax.grid(axis="x", alpha=.2, color=GRID); ax.set_axisbelow(True)

# 3 the signed anomaly test across the three blocks
ax = fig.add_subplot(gs[1, 0])
sc = "anm.iso"
s = h2[h2.score == sc].pivot_table(index="h", columns="block", values="spread_bp")
s = s[["research", "locked", "FORWARD"]]
x = np.arange(len(s)); w = 0.26
for i, (cname, col) in enumerate(zip(s.columns, (BLUE, PURP, ORANGE))):
    ax.bar(x + (i - 1) * w, s[cname], w, color=col, label=cname, zorder=3)
ax.axhline(0, color=INK2, lw=1.2)
ax.axhspan(-2.65, 2.65, color=ORANGE, alpha=0.10, zorder=1)
ax.set_ylim(-3.0, 6.2)
ax.text(-0.42, 5.9, "shaded = inside the 2.65 bp round turn, i.e. not tradeable",
        fontsize=8.6, color=ORANGE, weight="bold", ha="left", va="top")
ax.text(3.0, 5.0, "h=96 forward is one\nn=13,560 block", fontsize=8.2, color=MUTE, ha="center")
ax.set_xticks(x); ax.set_xticklabels([f"h={int(v)}" for v in s.index], fontsize=9)
ax.set_ylabel("Q5 - Q1 signed forward return, basis points")
ax.set_title("The signed test: reversal, consistent, and far below cost",
             fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=8.6, loc="lower left")
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)

# 4 what an IC is worth
ax = fig.add_subplot(gs[1, 1])
ics = np.linspace(0, 0.30, 200)
bp = ics * 10.59
ax.plot(ics, bp, color=BLUE, lw=2.4, zorder=3)
ax.axhline(2.65, color=ORANGE, lw=2.2, ls="--", zorder=4)
ax.text(0.005, 2.85, "round turn 2.65 bp", color=ORANGE, fontsize=9.2, weight="bold")
ax.axvline(0.046, color=INK2, lw=1.6, ls=":", zorder=4)
ax.text(0.050, 0.35, "best RETURN IC\nmeasured here: 0.046\n= 0.18x the round turn",
        fontsize=9, color=INK, weight="bold")
be = 2.65 / 10.59
ax.plot([be], [2.65], marker="o", ms=9, color=ORANGE, zorder=5)
ax.annotate(f"break-even needs IC = {be:.3f}", xy=(be, 2.65), xytext=(0.115, 3.05),
            fontsize=9, color=ORANGE, weight="bold", ha="left",
            arrowprops=dict(arrowstyle="->", color=ORANGE, lw=1.1))
ax.set_xlabel("information coefficient against the next bar's return")
ax.set_ylabel("expected return per trade, basis points")
ax.set_xlim(0, 0.30); ax.set_ylim(0, 3.3)
ax.set_title("The arithmetic, before any backtest", fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
ax.grid(alpha=.2, color=GRID); ax.set_axisbelow(True)

fig.text(0.055, 0.040, "A 15-minute gold return has sd 10.59 bp, and gold's round turn is 0.40 USD/oz = 2.65 bp of a 1,511 median price, or 23% of a 1xATR stop.",
         fontsize=9.2, color=MUTE)
fig.text(0.055, 0.017, "`STUDY_V13` ran the identical arithmetic on US100 and reached the same conclusion by the same route: you need an IC an order of magnitude larger than anything measured.",
         fontsize=9.2, color=MUTE)
fig.savefig("results/xanom/xanom_summary.png", dpi=140, facecolor="white")
print("wrote results/xanom/xanom_summary.png")
