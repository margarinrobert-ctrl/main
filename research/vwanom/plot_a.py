import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
BLUE, ORANGE, AQUA, PURP = "#2a78d6", "#eb6834", "#1baf7a", "#7a5cc7"
INK, INK2, MUTE, GRID = "#1c1f24", "#4a5058", "#8b929c", "#e6e9ed"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#c8ccd2", "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "figure.facecolor": "white"})
R = "results/vwanom/"
g1 = pd.read_csv(R + "a1_gate1.csv")
lad = pd.read_csv(R + "a2_ladder.csv")
anom = pd.read_csv(R + "a3_anomaly_ladder.csv")
lock = pd.read_csv(R + "a3_locked.csv")
ic = pd.read_csv(R + "a1_ic.csv")

fig = plt.figure(figsize=(16.0, 11.4))
gs = fig.add_gridspec(3, 2, hspace=0.66, wspace=0.26, left=0.075, right=0.97, top=0.855, bottom=0.085)
fig.text(0.055, 0.960, "Feature engineering and deep learning on the VWAP-EMA event stream",
         fontsize=19.5, weight="bold", color=INK)
fig.text(0.055, 0.932, "51 causal features in nine declared families; anomaly scores from an autoencoder, an isolation forest and a Mahalanobis distance, every model fitted on the research block only.",
         fontsize=10.1, color=INK2)
fig.text(0.055, 0.910, "Purged and embargoed folds, objective = the return not win/lose, and every model run beside a SHUFFLED TWIN.",
         fontsize=10.1, color=INK2)

# 1 Gate 1
ax = fig.add_subplot(gs[0, 0])
d = g1.copy()
d["lab"] = d.feed.str.replace("US30_ISO", "ISO") + "\n" + d.cell.str[:1] + " " + d.block.str[:3]
d = d.sort_values("pct")
cols = [AQUA if v > 0 else ORANGE for v in d.pct]
ax.barh(np.arange(len(d)), d.pct, 0.66, color=cols, zorder=3)
for i, (v, p) in enumerate(zip(d.pct, d.boot_p)):
    ax.text(v + (0.003 if v >= 0 else -0.003), i, f"p {p:.3f}", va="center",
            ha="left" if v >= 0 else "right", fontsize=8.2,
            color=INK if p <= 0.10 else MUTE, weight="bold" if p <= 0.10 else "normal")
ax.axvline(0, color=INK2, lw=1)
ax.set_yticks(np.arange(len(d))); ax.set_yticklabels(d.lab, fontsize=8.2)
ax.set_xlabel("% of entry price per event"); ax.set_xlim(-0.105, 0.125)
ax.set_title("Gate 1 — the primary alone, before any feature", fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="x", alpha=.2, color=GRID); ax.set_axisbelow(True)
ax.text(0.5, 0.03, "passes on every block it was chosen on, and on none of the others",
        transform=ax.transAxes, ha="center", fontsize=8.8, weight="bold", color=ORANGE,
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=ORANGE, lw=1.0))

# 2 the ladder: real vs shuffled IC
ax = fig.add_subplot(gs[0, 1])
p = lad.pivot_table(index=["feed", "cell", "model"], columns="shuffled", values="ic")
p = p.reset_index()
p["lab"] = p.feed.str.replace("US100", "N") .str.replace("US30", "D") + " " + p.model
x = np.arange(len(p)); w = 0.38
ax.bar(x - w/2, p[False], w, color=BLUE, label="real labels", zorder=3)
ax.bar(x + w/2, p[True], w, color=MUTE, label="SHUFFLED twin", zorder=3)
ax.axhline(0, color=INK2, lw=1)
ax.set_xticks(x); ax.set_xticklabels(p.lab, rotation=32, ha="right", fontsize=7.6)
ax.set_ylabel("out-of-fold Spearman IC")
ax.set_title("Every model beside its shuffled twin", fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=8.4); ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)
share = float((p[True] > p[False]).mean())
ax.text(0.02, 0.04, f"the shuffled twin wins {100*share:.0f}% of cells  (50% = the noise floor)",
        transform=ax.transAxes, fontsize=8.8, weight="bold",
        color=ORANGE if share >= 0.45 else INK2)

# 3 the anomaly ladder
ax = fig.add_subplot(gs[1, 0])
sub = anom[anom.score == "anm.ae_err"]
for i, (_, r) in enumerate(sub.iterrows()):
    ys = [r[f"Q{k}"] for k in range(1, 6)]
    ax.plot(range(1, 6), ys, marker="o", lw=1.8, ms=4.5, alpha=.85,
            label=f"{r.feed} {r.cell[:1]} {r.block[:3]}")
ax.axhline(0, color=INK2, lw=1)
ax.set_xticks(range(1, 6)); ax.set_xticklabels(["Q1\nleast\nanomalous", "Q2", "Q3", "Q4", "Q5\nmost\nanomalous"], fontsize=8)
ax.set_ylabel("% of entry price per event")
ax.set_title("Autoencoder reconstruction error, by quintile", fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=7.4, ncol=2); ax.grid(alpha=.2, color=GRID); ax.set_axisbelow(True)

# 4 sign consistency of the anomaly scores
ax = fig.add_subplot(gs[1, 1])
sg = anom.groupby("score").agg(mean_rho=("rho", "mean"),
                               share_pos=("rho", lambda s: float((s > 0).mean())),
                               cells=("rho", "size")).reset_index()
sg["lab"] = sg.score.str.replace("anm.", "", regex=False)
sg = sg.sort_values("share_pos")
ax.barh(np.arange(len(sg)), sg.share_pos, 0.6,
        color=[AQUA if abs(v - .5) > .25 else MUTE for v in sg.share_pos], zorder=3)
ax.axvline(0.5, color=ORANGE, lw=2, ls="--")
ax.text(0.5, len(sg) - 0.35, "  a coin flip", color=ORANGE, fontsize=9, weight="bold", va="top")
for i, (s_, m_, n_) in enumerate(zip(sg.share_pos, sg.mean_rho, sg.cells)):
    ax.text(s_ + 0.02, i, f"{s_:.2f}   mean rho {m_:+.3f}  (n{int(n_)})", va="center", fontsize=8.2, color=INK)
ax.set_yticks(np.arange(len(sg))); ax.set_yticklabels(sg.lab, fontsize=8.6)
ax.set_xlabel("share of feed x cell x block cells where rho > 0"); ax.set_xlim(0, 1.42)
ax.set_title("Does an anomaly score keep its sign?", fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="x", alpha=.2, color=GRID); ax.set_axisbelow(True)

# 5 the locked read
ax = fig.add_subplot(gs[2, 0])
d = lock.copy()
d["lab"] = d.feed + " " + d.cell[:1] + "\n" + d.block
x = np.arange(len(d)); w = 0.38
ax.bar(x - w/2, d.base, w, color=MUTE, label="all events (base)", zorder=3)
ax.bar(x + w/2, d.kept, w, color=BLUE, label="kept by the model", zorder=3)
ax.axhline(0, color=INK2, lw=1)
for i, (u, f) in enumerate(zip(d.uplift, d.kept_frac)):
    ax.text(i, max(d.base.iloc[i], d.kept.iloc[i]) + 0.004, f"{u:+.3f}\nkept {100*f:.0f}%",
            ha="center", fontsize=8, color=INK)
ax.set_xticks(x); ax.set_xticklabels(d.lab, fontsize=8.4)
ax.set_ylabel("% of entry price per event")
ax.set_title("One pre-declared locked read", fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=8.4, loc="upper left"); ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)

# 6 IC by family, real vs shuffled
ax = fig.add_subplot(gs[2, 1])
fam = ic.groupby("fam").agg(real=("ic", lambda s: np.abs(s).mean()),
                            sh=("ic_shuffled", lambda s: np.abs(s).mean())).reset_index().sort_values("real")
x = np.arange(len(fam)); w = 0.38
ax.barh(x - w/2, fam.real, w, color=BLUE, label="real labels", zorder=3)
ax.barh(x + w/2, fam.sh, w, color=MUTE, label="shuffled", zorder=3)
ax.set_yticks(x); ax.set_yticklabels(fam.fam, fontsize=9)
ax.set_xlabel("mean |Spearman IC| on the research block")
ax.set_title("Family IC against its own noise floor", fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
ax.legend(frameon=False, fontsize=8.4, loc="lower right"); ax.grid(axis="x", alpha=.2, color=GRID); ax.set_axisbelow(True)

fig.savefig("results/vwanom/vwanom_summary.png", dpi=140, facecolor="white")
print("wrote results/vwanom/vwanom_summary.png")
