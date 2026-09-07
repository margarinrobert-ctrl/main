import sys, os
sys.path.insert(0, "research"); sys.path.insert(0, "research/ftm")
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

R = "results/ftm2/"
C = pd.read_csv(R + "o1_controls.csv")
K = pd.read_csv(R + "o2_knobs.csv")
D = pd.read_csv(R + "o2_dropone.csv")
M = pd.read_csv(R + "o3_mc.csv")
t = pd.read_parquet(R + "o1_a2.parquet"); t["time"] = pd.to_datetime(t.time)
OOS = pd.Timestamp("2025-01-01")

INK="#1b1d21"; MUT="#6b7078"; ACC="#1f6f8b"; BAD="#b4483c"; GRY="#a9adb4"; WARM="#c98a3e"; GRN="#3f7d5a"
plt.rcParams.update({"font.size": 8.3, "axes.edgecolor": "#c8ccd2", "axes.labelcolor": INK,
                     "text.color": INK, "xtick.color": MUT, "ytick.color": MUT,
                     "axes.titlesize": 9.4, "axes.titleweight": "bold"})
fig = plt.figure(figsize=(14.4, 10.0))
gs = fig.add_gridspec(3, 3, hspace=0.70, wspace=0.30,
                      left=0.135, right=0.975, top=0.876, bottom=0.135)
fig.suptitle("FTM ORB 1.8.0-alpha.2 — out-of-sample, robustness, Monte Carlo",
             fontsize=13.2, fontweight="bold", x=0.048, ha="left", y=0.962)
fig.text(0.048, 0.928, "1.05M one-minute NQ bars, 342 trades 2023-09 to 2025-10, MNQ, costs in.  "
         "Split at 2025-01-01 — a POST-HOC split of a sample this branch has already read whole "
         "three times.", fontsize=8.4, color=MUT, ha="left")

# 1 equity by block
ax = fig.add_subplot(gs[0, 0])
eq = t.set_index("time").usd.cumsum()
ax.plot(eq.index, eq.values, color=ACC, lw=1.7)
ax.axvline(OOS, color=BAD, lw=1.3, ls="--")
ax.text(OOS, eq.max()*0.12, " out of sample →", fontsize=7.2, color=BAD)
ax.axhline(0, color=INK, lw=0.8)
ax.set_ylabel("cumulative $ (1 MNQ)")
ax.set_title("Equity, fixed constants")
ax.tick_params(axis="x", labelrotation=32, labelsize=6.6)

# 2 control p by block
ax = fig.add_subplot(gs[0, 1])
lbl = [f"{v.split(' ')[0]}\n{b.replace('OUT-OF-SAMPLE','OOS').replace('in-sample','IS')}"
       for v, b in zip(C.version, C.block)]
x = np.arange(len(C))
ax.bar(x - 0.19, C.rule_R, 0.38, color=ACC, label="rule")
ax.bar(x + 0.19, C.ctl_med, 0.38, color=GRY, label="random quarter-hour entry")
for i, p in enumerate(C.p):
    ax.text(i, 0.225, f"p {p:.3f}", ha="center", fontsize=6.8, color=BAD if p > .05 else ACC)
ax.set_xticks(x); ax.set_xticklabels(lbl, fontsize=6.4)
ax.set_ylim(0, 0.30); ax.set_ylabel("R / trade")
ax.set_title("The published p 0.004 is in-sample")
ax.legend(fontsize=6.5, frameon=False, loc="upper left", bbox_to_anchor=(0, 0.86))

# 3 prior_bars axis
ax = fig.add_subplot(gs[0, 2])
m = K.groupby("prior_bars")[["R_is", "R_oos"]].mean()
ax.plot(m.index, m.R_is, "o-", color=ACC, lw=1.8, ms=6, label="in-sample")
ax.plot(m.index, m.R_oos, "o-", color=WARM, lw=1.8, ms=6, label="out-of-sample")
ax.scatter([1], [m.R_oos.loc[1]], s=150, facecolor="none", edgecolor=BAD, lw=1.8, zorder=5)
ax.text(1.08, m.R_oos.loc[1]-0.004, "alpha.2's choice —\nworst of five OOS", fontsize=6.8, color=BAD)
ax.set_xticks([1,2,3,4,5]); ax.set_xlabel("prior-session observation bars")
ax.set_ylabel("R / trade"); ax.set_title("The one axis alpha.2 moves has no gradient")
ax.legend(fontsize=6.8, frameon=False, loc="center right")

# 4 drop-one OOS
ax = fig.add_subplot(gs[1, :2])
d = D.sort_values("R_oos")
base = float(D[D.component == "as shipped"].R_oos.iloc[0])
cols = [BAD if v > base else (GRN if "SIDE" in c else ACC) for v, c in zip(d.R_oos, d.component)]
ax.barh(np.arange(len(d)), d.R_oos, color=cols, height=0.7)
ax.axvline(base, color=INK, lw=1.5, ls="--")
ax.text(base + 0.004, 0.2, f"as shipped {base:+.3f}", fontsize=7, color=INK)
ax.set_yticks(np.arange(len(d))); ax.set_yticklabels(d.component, fontsize=6.8)
ax.axvline(0, color=INK, lw=0.8)
ax.set_xlabel("out-of-sample R / trade with that component REMOVED")
ax.set_title("Drop-one: 8 of 12 components improve the out-of-sample result when removed  "
             "(red = removal helps)")

# 5 MC
ax = fig.add_subplot(gs[1, 2])
xb = np.arange(len(M))
ax.bar(xb, M.usd_trade, 0.5, color=ACC)
ax.errorbar(xb, M.usd_trade, yerr=[M.usd_trade - M.boot_lo, M.boot_hi - M.usd_trade],
            fmt="none", ecolor=INK, capsize=4, lw=1.2)
ax.axhline(0, color=BAD, lw=1.3, ls="--")
for i, p in enumerate(M.P_mean_le0):
    ax.text(i, M.boot_hi[i] + 4, f"P(≤0)\n{p:.3f}", ha="center", fontsize=6.6,
            color=BAD if p > .05 else ACC)
ax.set_xticks(xb)
ax.set_xticklabels([b.replace("OUT-OF-SAMPLE", "OOS").replace("in-sample", "IS") for b in M.block],
                   fontsize=7)
ax.set_ylim(-40, 105); ax.set_ylabel("$ / trade")
ax.set_title("Session bootstrap:\nOOS does not clear zero")

# 6 exit mix
ax = fig.add_subplot(gs[2, 0])
oos = t[t.time >= OOS]
g = oos.groupby("reason").usd.sum() / oos.usd.sum()
order = ["stop", "target", "cond1530", "close1600"]
ax.bar(range(4), [g.get(k, 0) for k in order],
       color=[BAD, GRN, GRN, ACC])
ax.axhline(0, color=INK, lw=0.9); ax.axhline(1, color=MUT, lw=1.0, ls=":")
ax.text(3.1, 1.06, "100% of net", fontsize=6.6, color=MUT, ha="right")
ax.set_xticks(range(4)); ax.set_xticklabels(order, fontsize=7.2)
ax.set_ylabel("share of out-of-sample net")
ax.set_title("The exits carry it: the 15:30 rule\nalone is 206% of OOS net")

# 7 forward test
ax = fig.add_subplot(gs[2, 1])
ns = [40, 100, 159, 300]
sd = 295.0
ax.plot(ns, [1.96*sd/np.sqrt(n) for n in ns], "o-", color=ACC, lw=1.9, ms=6)
ax.axhline(25.89, color=GRN, lw=1.4, ls="--")
ax.text(150, 29, "the OOS edge, $25.89/trade", fontsize=6.9, color=GRN)
ax.axhline(36.99, color=WARM, lw=1.2, ls=":")
ax.text(150, 40, "the IS edge, $36.99", fontsize=6.9, color=WARM)
ax.set_xlabel("forward-test trades"); ax.set_ylabel("95% CI half-width, $/trade")
ax.set_title("500 trades (3.1 yr) to show the OOS\nedge differs from zero")

# 8 verdict
ax = fig.add_subplot(gs[2, 2]); ax.axis("off")
rows = [["test", "out-of-sample"],
        ["matched control", "p 0.257  FAIL"],
        ["session bootstrap vs 0", "P(≤0) 0.138"],
        ["always-long, same machine", "+0.256 R vs rule +0.096"],
        ["coin-flip side", "+0.071 R vs rule +0.096"],
        ["drop-one improves R", "8 of 12"],
        ["h2_cap effect on R", "ZERO (size only)"],
        ["MC p99 drawdown", "$4,669 = 2.0x realised"],
        ["cost 4x", "still +$2,284"]]
tb = ax.table(cellText=rows[1:], colLabels=rows[0], loc="center", cellLoc="left",
              bbox=[0.0, 0.05, 1.0, 0.88])
tb.auto_set_font_size(False); tb.set_fontsize(7.4)
for (r, c), cell in tb.get_celld().items():
    cell.set_edgecolor("#d8dbe0")
    if r == 0:
        cell.set_facecolor("#eef1f4"); cell.set_text_props(weight="bold")
    elif c == 1:
        cell.set_text_props(color=BAD if r not in (8,) else GRN)
ax.set_title("Verdict", y=0.99)

fig.text(0.048, 0.072,
         "Out of sample the direction call is worth +0.025 R over a coin flip against +0.216 in sample, ALWAYS-LONG with the identical machine earns 2.7x the rule,\n"
         "and 8 of 12 components improve the result when removed.  Cost is not the objection — it survives 4x.  What it owns is the EXIT MACHINE, not the entry:\n"
         "the conditional 15:30 rule alone is 206% of out-of-sample net while stops are -368%.",
         fontsize=8.3, color=INK, ha="left", va="top")
fig.savefig(R + "ftm2_battery.png", dpi=150, facecolor="white")
print("wrote " + R + "ftm2_battery.png")
