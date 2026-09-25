import sys, os
sys.path.insert(0, "research"); sys.path.insert(0, "research/s3nn")
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

R = "results/s3nn/"; os.makedirs(R, exist_ok=True)
L = pd.read_csv(R + "n2_ladder.csv")
G = pd.read_csv(R + "n3_gate2.csv")
C = pd.read_csv(R + "n4_objective.csv")
tr = pd.read_parquet(R + "n2_rows.parquet")
y = tr.R.to_numpy(); b_pf = y[y > 0].sum() / -y[y < 0].sum(); b_win = (y > 0).mean()

INK = "#1b1d21"; MUT = "#6b7078"; ACC = "#1f6f8b"; BAD = "#b4483c"; GRY = "#a9adb4"
plt.rcParams.update({"font.size": 8.4, "axes.edgecolor": "#c8ccd2", "axes.labelcolor": INK,
                     "text.color": INK, "xtick.color": MUT, "ytick.color": MUT,
                     "axes.titlesize": 9.6, "axes.titleweight": "bold"})

fig = plt.figure(figsize=(13.6, 9.4))
gs = fig.add_gridspec(3, 2, hspace=0.62, wspace=0.24,
                      left=0.075, right=0.975, top=0.905, bottom=0.115)
fig.suptitle("A neural network on the S3 order-flow scalp (NQ 5m, 07:00-11:00 NY, flat at 11:00)",
             fontsize=13, fontweight="bold", x=0.075, ha="left", y=0.965)
fig.text(0.075, 0.932, "1,672 labelled events / effective n 960 against 45 causal features "
         "(truncation audit 0 of 900).  Research block only; the locked block was never opened.",
         fontsize=8.6, color=MUT, ha="left")

# 1 -- ladder PF at keep 50 vs shuffled twin
ax = fig.add_subplot(gs[0, 0])
x = np.arange(len(L))
ax.bar(x - 0.19, L["PF@50"], 0.38, color=ACC, label="real labels")
ax.bar(x + 0.19, L["shufPF@50"], 0.38, color=GRY, label="SHUFFLED twin")
ax.axhline(b_pf, color=BAD, lw=1.4, ls="--", label=f"unfiltered base {b_pf:.3f}")
ax.set_xticks(x); ax.set_xticklabels(L.model, rotation=38, ha="right", fontsize=7.4)
ax.set_ylim(0.6, 1.15); ax.set_ylabel("profit factor, top 50% kept")
ax.set_title("The shuffled twin wins 58% of cells")
ax.legend(fontsize=7, frameon=False, loc="upper left")

# 2 -- capacity
ax = fig.add_subplot(gs[0, 1])
cap = ["ridge", "mlp_2x32", "mlp_2x64", "mlp_4x128"]
sub = L.set_index("model").loc[cap]
ax.plot(range(4), sub["ic"], "o-", color=ACC, lw=1.8, ms=6, label="real")
ax.plot(range(4), sub["ic_shuf"], "o--", color=GRY, lw=1.5, ms=5, label="shuffled")
ax.axhline(0, color=INK, lw=0.8)
ax.set_xticks(range(4)); ax.set_xticklabels(["ridge", "2x32", "2x64", "4x128"], fontsize=7.6)
ax.set_ylabel("out-of-fold Spearman IC vs R")
ax.set_title("Capacity buys nothing; the gap to the twin is the whole signal")
ax.legend(fontsize=7, frameon=False)

# 3 -- Gate 2 control p
ax = fig.add_subplot(gs[1, 0])
ordr = G.sort_values("p_ctl")
cols = [ACC if p <= 0.05 else (MUT if p < 0.5 else BAD) for p in ordr.p_ctl]
ax.barh(np.arange(len(ordr)), ordr.p_ctl, color=cols, height=0.72)
ax.axvline(0.05, color=BAD, lw=1.3, ls="--")
ax.set_yticks(np.arange(len(ordr)))
ax.set_yticklabels([f"{m} @{int(k*100)}%" for m, k in zip(ordr.model, ordr.keep)], fontsize=6.6)
ax.invert_yaxis(); ax.set_xlim(0, 1.04)
ax.set_xlabel("p vs a random filter keeping the same number of events  "
              "(dashed line = 0.05)")
ax.set_title("Gate 2: 0 of 24 cells clear; best p is 0.348")

# 4 -- p90 of R
ax = fig.add_subplot(gs[1, 1])
b90 = np.percentile(y, 90)
ax.scatter(G.uplift, G.p90, s=34, c=[ACC if o == "R" else ACC for o in G.model], alpha=0.8)
ax.axhline(b90, color=BAD, lw=1.3, ls="--")
ax.axvline(0, color=INK, lw=0.8)
ax.text(G.uplift.min(), b90 + 0.02, f"baseline p90 = {b90:.2f} R", fontsize=7.2, color=BAD)
ax.set_xlabel("uplift in mean R over the unfiltered base")
ax.set_ylabel("p90 of R in the kept set")
ax.set_title("Every filter that keeps fewer events trims the tail (21 of 24)")

# 5 -- objective contrast
ax = fig.add_subplot(gs[2, 0])
c3 = C[C.keep == 0.3].set_index(["model", "obj"])
ms = [m for m in L.model if (m, "win") in c3.index]
xw = np.arange(len(ms))
ax.bar(xw - 0.19, [c3.loc[(m, "R"), "win"] for m in ms], 0.38, color=ACC, label="objective = R")
ax.bar(xw + 0.19, [c3.loc[(m, "win"), "win"] for m in ms], 0.38, color="#c98a3e",
       label="objective = win/lose")
ax.axhline(b_win, color=BAD, lw=1.3, ls="--", label=f"base {b_win:.3f}")
ax.axhline(0.676, color=INK, lw=1.2, ls=":", label="PF 2.0 needs 0.676")
ax.set_xticks(xw); ax.set_xticklabels(ms, rotation=38, ha="right", fontsize=7.2)
ax.set_ylim(0.40, 0.78); ax.set_ylabel("win rate, top 30% kept")
ax.set_title("Both objectives, same folds")
ax.legend(fontsize=6.6, frameon=False, ncol=2, loc="upper left", bbox_to_anchor=(0,1.02))

# 6 -- the arithmetic
ax = fig.add_subplot(gs[2, 1]); ax.axis("off")
pos, neg = y[y > 0], y[y < 0]; gp, gl = pos.mean(), -neg.mean()
tg = [1.5, 2.0, 3.0]
need = [t * gl / (t * gl + gp) for t in tg]
rows = [["target PF", "win rate", "lift needed", "best found"]]
best = 0.030
for t, n in zip(tg, need):
    rows.append([f"{t:.1f}", f"{n:.3f}", f"+{n-b_win:.3f}", f"+{best:.3f}"])
tb = ax.table(cellText=rows[1:], colLabels=rows[0], loc="center", cellLoc="center",
              bbox=[0.02, 0.34, 0.96, 0.46])
tb.auto_set_font_size(False); tb.set_fontsize(8.6)
for (r, c), cell in tb.get_celld().items():
    cell.set_edgecolor("#d8dbe0")
    if r == 0:
        cell.set_facecolor("#eef1f4"); cell.set_text_props(weight="bold")
    elif c == 3:
        cell.set_text_props(color=BAD)
ax.set_title("What the ask requires, at the measured win and loss sizes", y=0.90)
ax.text(0.02, 0.24, "Mean win +0.824 R, mean loss -0.859 R, win rate 0.519.\n"
        "PF 2.0 needs +15.7 points of win rate; the best of 99 model cells\n"
        "delivered +3.0, and could not be told from a random filter.",
        transform=ax.transAxes, fontsize=8.2, color=MUT, va="top")

fig.text(0.075, 0.038,
         "Verdict: 0 of 24 gate cells clear a same-selectivity random filter or a day-block bootstrap; the shuffled-label twin outscores the real model in 58% of\n"
         "ladder cells; every tree model ranks BACKWARDS.  Capacity is inert -- ridge and a four-layer net are the same number.  No locked read was taken.",
         fontsize=8.4, color=INK, ha="left", va="top")
fig.savefig(R + "nn_verdict.png", dpi=155, facecolor="white")
print("wrote " + R + "nn_verdict.png")
