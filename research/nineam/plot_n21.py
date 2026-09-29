"""Every table in `run_n21`..`run_n23` as a figure. Four sheets, in the order the study reads."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import na_core as N   # noqa: E402
import na_s30 as S    # noqa: E402
import na_30s as T    # noqa: E402
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '.'))
import daykey as DK  # noqa: E402  (pandas 3 made us the default resolution; see the module)

INK = "#1c1917"; MUTE = "#78716c"; FAINT = "#e7e5e4"
POS = "#0f766e"; NEG = "#b91c1c"; ACC = "#c2410c"; BLU = "#1e40af"; GRY = "#a8a29e"
plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.edgecolor": "#d6d3d1", "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": MUTE, "ytick.color": MUTE, "font.size": 9,
    "axes.titlesize": 10.5, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "axes.grid": True, "grid.color": "#f5f5f4", "grid.linewidth": 0.9,
    "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
})


def note(ax, t, y=-0.30):
    ax.text(0, y, t, transform=ax.transAxes, fontsize=7.6, color=MUTE, va="top", wrap=True)


def cap(fig, t, s):
    fig.text(0.008, 0.985, t, fontsize=14, fontweight="bold", va="top")
    fig.text(0.008, 0.956, s, fontsize=8.6, color=MUTE, va="top")


c = S.ctx(tf=0.5, fix=1)
P = dict(S.CFG)
tr = c.trades(P)
r = tr["pct"].to_numpy()
f = c.f0
mod = f["mod"].to_numpy(); day = f["day"].to_numpy()
sess = np.unique(day[mod >= 570])
have = np.unique(day[(mod >= 540) & (mod < 545)])

# ============================================================ FIG 6  what the feed can carry
fig, ax = plt.subplots(2, 2, figsize=(13.0, 8.4))
cap(fig, "US30 at 30 seconds — what the feed can carry",
    "The rule cannot see its own 09:00 range on 69% of sessions, and the coverage begins mid-file. "
    "Everything downstream lives on a 4.5-month tail.")

a = ax[0, 0]
mo = pd.DataFrame({"m": DK.from_day(pd.Series(sess)).dt.to_period("M").astype(str),
                   "have": np.isin(sess, have)}).groupby("m")["have"].agg(["sum", "size"])
x = np.arange(len(mo))
a.bar(x, mo["size"], color=FAINT, width=0.74, label="sessions in the file")
a.bar(x, mo["sum"], color=BLU, width=0.74, label="…carrying the 09:00–09:05 range")
a.set_xticks(x); a.set_xticklabels([m[2:] for m in mo.index], rotation=90, fontsize=7)
a.set_ylabel("sessions"); a.legend(fontsize=7.6, loc="upper left")
a.set_title("Coverage is all-or-nothing and starts 2026-04-30")
note(a, "Bars with no activity are omitted from the export, and the pre-open is where a Dow CFD is\n"
        "quiet. Where the range exists it is the full ten bars; where it does not there is no bar at\n"
        "all. 92 of 293 sessions (31.4%). The change lands three days after the volume column starts.")

a = ax[0, 1]
mix = tr.groupby("why")["pct"].agg(["size", "sum"])
lab = {1: "stop / ratchet", 2: "target", 6: "opposite cross", 3: "flatten"}
names = [lab.get(i, str(i)) for i in mix.index]
col = [NEG if v < 0 else POS for v in mix["sum"]]
a.barh(names, mix["sum"], color=col, height=0.55)
for i, (n_, s_) in enumerate(zip(mix["size"], mix["sum"])):
    a.text(s_ + (0.06 if s_ > 0 else -0.06), i, f"n={n_}  {s_:+.2f}", va="center",
           ha="left" if s_ > 0 else "right", fontsize=8)
a.axvline(0, color=INK, lw=0.9); a.set_xlabel("total % of entry price")
a.set_xlim(-3.2, 5.4); a.set_title("Where the money is, and where the win rate is")
note(a, "17 of 57 trades book EXACTLY +2.71 points — the secured 5 minus the 2.29 round turn. A\n"
        "breakeven stop is a losing trade by construction; the secured offset relabels it, which is\n"
        "why the win rate is 70.2% while the target-hit rate is 36.8%.")

a = ax[1, 0]
ar = pd.read_csv(os.path.join(HERE, "n21_fillmodel.csv"))
k = ar.pivot_table(index=["be_pts", "be_off"], columns="fix", values="pts")
idx = [f"{int(i)}/{int(j)}" for i, j in k.index]
x = np.arange(len(k))
a.bar(x - 0.18, k[0], width=0.34, color=GRY, label="fill at the stop's level (published kernel)")
a.bar(x + 0.18, k[1], width=0.34, color=ACC, label="fill at the WORSE of level and open (corrected)")
a.set_xticks(x); a.set_xticklabels(idx); a.set_xlabel("breakeven arm / secure, points")
a.set_ylabel("points per trade"); a.legend(fontsize=7.4)
a.set_title("The ratchet artifact, priced before the result is quoted")
note(a, "A breakeven stop arms on the bar's favourable EXTREME, so the moved stop can be written\n"
        "ABOVE the market. At the user's 43/5 the artifact is worth only −0.07 pts (−0.4%) because 5\n"
        "points is small against a 30-second bar; at 25/5 it is −1.80. Everything here uses fix=1.")

a = ax[1, 1]
br = pd.read_csv(os.path.join(HERE, "n21_baserates.csv"))
y = np.arange(len(br))
a.barh(y, br["on_signal"], color=BLU, height=0.34, label="on the trigger's own bars")
a.barh(y + 0.36, br["on_all_bars"], color=FAINT, height=0.34, label="on all bars")
a.set_yticks(y + 0.18); a.set_yticklabels([t.replace(" (", "\n(") for t in br["cond"]], fontsize=7.6)
for i, v in enumerate(br["lift"]):
    a.text(0.80, i + 0.18, f"lift {v:.2f}×", fontsize=8, color=ACC, va="center")
a.axvline(0.95, color=NEG, ls=":", lw=1.1)
a.set_xlim(0, 1.0); a.set_xlabel("pass rate"); a.legend(fontsize=7.4, loc="lower right")
a.set_title("Base rates — the gate is not the trigger restated")
note(a, "A pass rate near the dotted line would mean the confirmation is the breakout restated (nine\n"
        "families have died that way here); a lift near 1.00 would mean it carries nothing. The fresh\n"
        "cross keeps a third of signals at lift 1.86× — it binds, and it is a real second reading.")

fig.tight_layout(rect=[0, 0, 1, 0.945]); fig.subplots_adjust(hspace=0.62, wspace=0.34)
fig.savefig(os.path.join(HERE, "fig6_30s_feed.png"), dpi=155, bbox_inches="tight")
plt.close(fig)

# ============================================================ FIG 7  IS/OOS + walk-forward
fig, ax = plt.subplots(2, 2, figsize=(13.0, 8.4))
cap(fig, "In sample, out of sample, and forward",
    "57 trades on 54 sessions. The rule clears both nulls and is 0.74× its own minimum detectable "
    "effect — two true statements that answer different questions.")

a = ax[0, 0]
eq = np.cumsum(r); xs = np.arange(1, len(r) + 1)
half = len(r) // 2
a.plot(xs, eq, color=BLU, lw=1.8)
a.fill_between(xs, np.maximum.accumulate(eq), eq, color=NEG, alpha=0.12)
a.axvline(half, color=ACC, ls="--", lw=1.2)
a.text(half + 0.6, eq.min(), " IS | OOS", color=ACC, fontsize=8, va="bottom")
a.set_xlabel("trade"); a.set_ylabel("cumulative % of entry price")
a.set_title("Equity, one unit, percent of entry price")
note(a, "Shaded is underwater. Realised max drawdown 0.428%, which the permutation puts at the 31.6th\n"
        "percentile of reshuffles of these same trades — a smoother path than the trades imply, and\n"
        "the MC p99 is 2.28× it. Size for the p99, not for the backtest.")

a = ax[0, 1]
res = pd.read_csv(os.path.join(HERE, "n21_isoos.csv"))
x = np.arange(len(res))
a.bar(x, res["pct"], color=[GRY, BLU, ACC], width=0.5)
a.errorbar(x, res["pct"], yerr=res["mde"], fmt="none", ecolor=INK, capsize=5, lw=1.1)
for i, (v, m, n_) in enumerate(zip(res["pct"], res["mde"], res["n"])):
    a.text(i, v + m + 0.004, f"{v:+.4f}\nn={n_}", ha="center", fontsize=8)
a.set_xticks(x); a.set_xticklabels(res["block"]); a.axhline(0, color=INK, lw=0.9)
a.set_ylabel("% of entry price per trade"); a.set_ylim(-0.02, 0.16)
a.set_title("Per-trade result with each block's own MDE")
note(a, "The bar is the effect; the whisker is the smallest effect that block could resolve at 80%\n"
        "power. Every bar is INSIDE its own whisker. OOS reads higher than IS — the wrong shape — but\n"
        "neither block chose anything here: the settings came from the user, not from a search.")

a = ax[1, 0]
wf = pd.read_csv(os.path.join(HERE, "n22_walkforward.csv"))
x = np.arange(len(wf)); w = 0.26
a.bar(x - w, wf["fixed"], width=w, color=BLU, label="the user's constants, fixed")
a.bar(x, wf["rechosen"], width=w, color=ACC, label="re-chosen inside each training window")
a.bar(x + w, wf["random"], width=w, color=GRY, label="a random cell from the same grid")
a.axhline(0, color=INK, lw=0.9); a.set_xticks(x); a.set_xticklabels([f"fold {i}" for i in wf["fold"]])
a.set_ylabel("total % over the test fold"); a.legend(fontsize=7.4)
a.set_title("Walk-forward — the seventeenth re-optimiser to lose")
note(a, "Totals +2.226 fixed, +1.515 re-chosen, +2.528 random; 4 of 5 folds positive for all three.\n"
        "The re-chooser never settles — it picks a different cell in every fold — and a RANDOM cell\n"
        "beats it. Selecting inside the fold buys nothing over not selecting at all.")

a = ax[1, 1]
mo = pd.read_csv(os.path.join(HERE, "n23_months.csv"))
col = [POS if v > 0 else NEG for v in mo["sum"]]
a.bar(np.arange(len(mo)), mo["sum"], color=col, width=0.6)
for i, (s_, n_) in enumerate(zip(mo["sum"], mo["size"])):
    a.text(i, s_ + 0.02, f"n={n_}", ha="center", fontsize=7.6)
a.set_xticks(np.arange(len(mo))); a.set_xticklabels([m[2:] for m in mo["m"]], fontsize=8)
a.axhline(0, color=INK, lw=0.9); a.set_ylabel("total % of entry price")
a.set_title("Month by month — 4.5 months is the entire sample")
note(a, "Every month is positive and the largest carries 14 trades. The whole tradeable sample is one\n"
        "summer of one year on one market — no bear tape, no volatility event, no January. A season is\n"
        "not a regime test, and there is no month here that was not also used to check the rule.")

fig.tight_layout(rect=[0, 0, 1, 0.945]); fig.subplots_adjust(hspace=0.62, wspace=0.26)
fig.savefig(os.path.join(HERE, "fig7_30s_isoos.png"), dpi=155, bbox_inches="tight")
plt.close(fig)

# ============================================================ FIG 8  the four Monte Carlos
fig, ax = plt.subplots(2, 2, figsize=(13.0, 8.4))
cap(fig, "Four Monte Carlos, kept apart",
    "Edge, path, execution and data answer four different questions. Read the last two last — a "
    "100-point barrier on a 2.29-point round turn makes the execution band nearly free.")

a = ax[0, 0]
b = np.asarray(N.boot_edge(tr, n=6000, seed=1, col="pct"))
a.hist(b, bins=60, color=FAINT, edgecolor="white", lw=0.4)
a.axvline(0, color=NEG, lw=1.4)
a.axvline(r.mean(), color=BLU, lw=1.8)
a.axvline(np.percentile(b, 2.5), color=INK, ls=":", lw=1.0)
a.axvline(np.percentile(b, 97.5), color=INK, ls=":", lw=1.0)
a.set_xlabel("% of entry price per trade"); a.set_ylabel("draws")
a.set_title(f"1 · EDGE — day-block bootstrap, P(mean≤0) = {(b<=0).mean():.3f}")
note(a, "Whole days resampled with their trades attached, so clustered signals are not counted as\n"
        "independent. 95% CI [+0.0020, +0.0699] excludes zero on the whole sample; on the IS half\n"
        "alone it does not (P 0.102) and on the OOS half it barely does (0.047).")

a = ax[0, 1]
pm = pd.read_csv(os.path.join(HERE, "n22_mc_path.csv"))["dd"].to_numpy()
real = float(np.max(np.maximum.accumulate(np.cumsum(r)) - np.cumsum(r)))
a.hist(pm, bins=60, color=FAINT, edgecolor="white", lw=0.4)
a.axvline(real, color=BLU, lw=1.8)
a.axvline(np.percentile(pm, 99), color=NEG, lw=1.4, ls="--")
a.text(real, a.get_ylim()[1] * 0.92, " realised", color=BLU, fontsize=8)
a.text(np.percentile(pm, 99), a.get_ylim()[1] * 0.80, " p99", color=NEG, fontsize=8)
a.set_xlabel("max drawdown, % of entry price"); a.set_ylabel("draws")
a.set_title("2 · PATH — 6,000 permutations of the same trades")
note(a, "The realised drawdown sits at the 31.6th percentile of reshuffles of its OWN trades, so the\n"
        "path was smoother than the trade distribution implies. The p99 is 2.28× the realised figure\n"
        "and is the number to size against.")

a = ax[1, 0]
ex = pd.read_csv(os.path.join(HERE, "n22_mc_exec.csv"))["mean"].to_numpy()
cs = pd.read_csv(os.path.join(HERE, "n23_cost.csv"))
a.plot(cs["cost_mult"], cs["pct"], "-o", color=BLU, lw=1.8, ms=6)
a.fill_between([0.5, 2.0], np.percentile(ex, 5), np.percentile(ex, 95), color=ACC, alpha=0.22,
               label="perturbed band, round turn U(0.5×, 2×) per trade")
a.axhline(0, color=NEG, lw=1.2)
for x_, y_ in zip(cs["cost_mult"], cs["pct"]):
    a.annotate(f"{y_:+.4f}", (x_, y_), textcoords="offset points", xytext=(0, 8),
               ha="center", fontsize=7.2)
a.set_xlabel("round turn, multiples of the assumed 2.29 points")
a.set_ylabel("% of entry price per trade"); a.legend(fontsize=7.2, loc="lower left")
a.set_ylim(-0.004, 0.050)
a.set_title("3 · EXECUTION — the cost ladder and its perturbation band")
note(a, "The perturbed band is 0.0343 to 0.0351 — a spike, and P(total ≤ 0) = 0.000. The ladder is\n"
        "still positive at EIGHT times the assumed round turn. That says the IMPLEMENTATION is not\n"
        "fragile, not that the edge is real: 2.29 points is 2.3% of a 100-point stop.")

a = ax[1, 1]
mj = pd.read_csv(os.path.join(HERE, "n22_mc_jitter.csv"))
x = np.arange(len(mj))
a.errorbar(x, mj["mean_med"], yerr=[mj["mean_med"] - mj["mean_p5"], mj["mean_p95"] - mj["mean_med"]],
           fmt="o", color=BLU, ecolor=BLU, capsize=6, ms=7, lw=1.4)
a.axhline(r.mean(), color=ACC, ls="--", lw=1.2, label="unjittered")
a.axhline(0, color=NEG, lw=0.9)
a.set_xticks(x); a.set_xticklabels([f"±{v:g} tick" for v in mj["jitter_ticks"]])
a.set_ylabel("% of entry price per trade"); a.legend(fontsize=7.6)
for i, v in enumerate(mj["sign_kept"]):
    a.text(i, mj["mean_p95"].iloc[i] + 0.002, f"sign kept {v:.3f}", ha="center", fontsize=7.6)
a.set_title("4 · DATA — price jitter, every indicator recomputed")
note(a, "Each bar's OHLC is jittered independently, the bar repaired, and the ATR, both EMAs, the\n"
        "09:00 range and the cross state ALL rebuilt from the jittered series. The sign survives every\n"
        "draw at every noise level and the trade count moves 57 → 60.")

fig.tight_layout(rect=[0, 0, 1, 0.945]); fig.subplots_adjust(hspace=0.62, wspace=0.26)
fig.savefig(os.path.join(HERE, "fig8_30s_montecarlo.png"), dpi=155, bbox_inches="tight")
plt.close(fig)

# ============================================================ FIG 9  correlations + resolution
fig, ax = plt.subplots(2, 2, figsize=(13.0, 8.4))
cap(fig, "Correlations, components, and the bar size",
    "Three matrices answer three questions — which arms are the same strategy, which conditions are "
    "the same column, and whether the result is the rule or the resolution.")


def heat(a, M, title, fmt="{:.2f}", cmap="RdBu_r", vmin=-1, vmax=1):
    im = a.imshow(M.to_numpy(), cmap=cmap, vmin=vmin, vmax=vmax)
    a.set_xticks(range(len(M.columns))); a.set_xticklabels(M.columns, rotation=38, ha="right", fontsize=7.4)
    a.set_yticks(range(len(M.index))); a.set_yticklabels(M.index, fontsize=7.4)
    for i in range(len(M.index)):
        for j in range(len(M.columns)):
            v = M.to_numpy()[i, j]
            a.text(j, i, fmt.format(v), ha="center", va="center", fontsize=7,
                   color="white" if abs(v) > 0.62 else INK)
    a.grid(False); a.set_title(title)
    return im


A = pd.read_csv(os.path.join(HERE, "n22_corr_arms.csv"), index_col=0)
heat(ax[0, 0], A, "(a) between ARMS — zero-filled daily percent")
note(ax[0, 0], "The rule correlates 0.965 with itself minus the cross exit and 0.837 minus the breakeven —\n"
                "those are the same strategy. It correlates 0.424 with itself ungated and only 0.150 with\n"
                "always-long, so it is not a drift exposure. Long and short are −0.057 to each other.", -0.42)

C = pd.read_csv(os.path.join(HERE, "n22_corr_cond.csv"), index_col=0)
heat(ax[0, 1], C, "(b) between CONDITIONS — on the signal bars only")
note(ax[0, 1], "Measured where a filter actually acts. Nothing here duplicates: the strongest pair is the\n"
                "fresh cross against the 13>48 state at +0.393, which is the recency form against the state\n"
                "form of one indicator. This branch has caught its own pool duplicating nine times.", -0.42)

a = ax[1, 0]
rr = pd.read_csv(os.path.join(HERE, "n23_resolution.csv"))
asis = rr[rr["how"].str.startswith("as configured")]
mtch = rr[rr["how"].str.startswith("matched")]
x = np.arange(3)
a.bar(x - 0.19, asis["pct"], width=0.36, color=BLU, label="EMA 13/48 as configured")
a.bar(x + 0.19, mtch["pct"], width=0.36, color=ACC, label="EMA held at 6.5 / 24 MINUTES")
for i, (v, n_) in enumerate(zip(asis["pct"], asis["n"])):
    a.text(i - 0.19, v + (0.003 if v > 0 else -0.008), f"n={n_}", ha="center", fontsize=7.4)
for i, (v, n_) in enumerate(zip(mtch["pct"], mtch["n"])):
    a.text(i + 0.19, v + (0.003 if v > 0 else -0.008), f"n={n_}", ha="center", fontsize=7.4)
a.axhline(0, color=INK, lw=0.9); a.set_xticks(x); a.set_xticklabels(["30s", "1m", "5m"])
a.set_ylabel("% of entry price per trade"); a.legend(fontsize=7.4)
a.set_title("(c) the same rule on 30s / 1m / 5m bars of the SAME file")
note(a, "A bar count is not a setting. The script converts the fresh-cross reach from MINUTES and does\n"
        "NOT convert the EMA lengths, so 13/48 spans 6.5 and 24 minutes here against 13 and 48 on a\n"
        "one-minute chart. Neither reading reproduces the 30-second result at another bar size.")

a = ax[1, 1]
do = pd.read_csv(os.path.join(HERE, "n23_dropone.csv"))
do = do[do["arm"].str.startswith("-") | (do["arm"] == "as configured")]
y = np.arange(len(do))[::-1]
col = [ACC if s == "as configured" else (POS if d < 0 else NEG)
       for s, d in zip(do["arm"], do["d_vs_full"])]
a.barh(y, do["pct"], color=col, height=0.55)
for i, (v, n_) in zip(y, zip(do["pct"], do["n"])):
    a.text(max(v, 0.0) + 0.0015, i, f"  n={n_}", va="center", ha="left", fontsize=7.6)
a.set_yticks(y); a.set_yticklabels(do["arm"], fontsize=8)
a.axvline(0, color=INK, lw=0.9); a.axvline(r.mean(), color=ACC, ls=":", lw=1.1)
a.set_xlim(-0.022, 0.055)
a.set_xlabel("% of entry price per trade")
a.set_title("(d) drop-one — the MA gate is the strategy")
note(a, "Removing the fresh-cross confirmation takes the rule from +0.0358 on 57 trades to −0.0130 on\n"
        "131, PF 2.02 → 0.78. Nothing else moves it by more than a third of that. Teal = removing the\n"
        "component HURTS, so it earns its place; red = removing it HELPS. Dotted = the configured result.", -0.30)

fig.tight_layout(rect=[0, 0, 1, 0.945]); fig.subplots_adjust(hspace=0.78, wspace=0.30)
fig.savefig(os.path.join(HERE, "fig9_30s_corr.png"), dpi=155, bbox_inches="tight")
plt.close(fig)
print("wrote fig6_30s_feed.png fig7_30s_isoos.png fig8_30s_montecarlo.png fig9_30s_corr.png")
