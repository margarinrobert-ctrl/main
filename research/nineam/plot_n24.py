"""The live-settings battery as figures: validation, then live-trading readiness."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import na_core as N   # noqa: E402
import na_s30 as S    # noqa: E402
import na_live as L   # noqa: E402
import daykey as DK   # noqa: E402

INK = "#1c1917"; MUTE = "#78716c"
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
    ax.text(0, y, t, transform=ax.transAxes, fontsize=7.4, color=MUTE, va="top")


def cap(fig, t, s):
    fig.text(0.008, 0.985, t, fontsize=14, fontweight="bold", va="top")
    fig.text(0.008, 0.952, s, fontsize=8.4, color=MUTE, va="top")


c = S.ctx(tf=0.5, fix=1)
P = dict(L.LIVE)
tr = c.trades(P)
r = tr["pct"].to_numpy()
sig_g, sd_g = c.sigs(P)
sd_ = r.std(ddof=1)

# =================================================================== figure 10: does it exist?
fig, ax = plt.subplots(2, 3, figsize=(15.5, 8.6))
cap(fig, "US30 30-second, the settings actually configured: does the effect exist?",
    "2.25xATR(45) stop against a 100-POINT target -- R:R 3.8:1, so the driftless break-even win "
    "rate is 0.207, not 0.500.  44 trades on 92 tradeable sessions, 2026-05-01..2026-09-16.")

a = ax[0, 0]
eq = np.cumsum(r)
a.plot(np.arange(1, len(eq) + 1), eq, color=POS, lw=1.8)
a.fill_between(np.arange(1, len(eq) + 1), eq, 0, color=POS, alpha=0.10)
a.axhline(0, color=GRY, lw=0.8)
a.set_title("equity in % of entry price, by trade")
a.set_xlabel("trade"); a.set_ylabel("cumulative %")
note(a, f"+{r.sum():.2f}% over {len(r)} trades = {tr['pts'].sum():+.0f} points, i.e.\n"
        f"{5*tr['pts'].sum():,.0f} dollars at 1 contract and 5 dollars a point.\n"
        f"Max drawdown {float(np.max(np.maximum.accumulate(eq)-eq)):.3f}%.")

a = ax[0, 1]
lab = ["driftless\nbreak-even", "realised\nbreak-even", "ACTUAL\nwin rate"]
aw = tr.loc[tr["pts"] > 0, "pts"].mean(); al = tr.loc[tr["pts"] <= 0, "pts"].mean()
at_sig = c.atr_frame(P["atr_n"])["atr"].to_numpy()[sig_g]
bed = float(np.median(1.0 / (1.0 + 100.0 / (2.25 * at_sig))))
vals = [bed, 1 / (1 + aw / -al), float((r > 0).mean())]
a.bar(lab, vals, color=[GRY, MUTE, POS], width=0.6)
for i, v in enumerate(vals):
    a.text(i, v + 0.015, f"{v:.3f}", ha="center", fontsize=9, fontweight="bold")
a.set_ylim(0, 0.78); a.set_title("the win rate against its own base rates")
note(a, "A 64% win rate on a 3.8:1 payoff is not the same claim as a 64%\n"
        "win rate on a 1:1. The bar to beat is the middle one -- what the\n"
        "REALISED payoff needs. 22.7% of trades book the secured +0.71 pts.")

a = ax[0, 2]
nul = pd.read_csv(os.path.join(HERE, "n24_nulls.csv"))
for k, col, lb in [("entry", BLU, "random ENTRY, matched"), ("gate", ACC, "random GATE, same selectivity")]:
    v = nul[k].dropna().to_numpy()
    a.hist(v, bins=34, color=col, alpha=0.42, label=f"{lb} (med {np.median(v):+.4f})")
a.axvline(r.mean(), color=POS, lw=2.4, label=f"rule {r.mean():+.4f}")
a.set_title("the two nulls, 400 draws each"); a.set_xlabel("%/trade"); a.legend(fontsize=7.4)
note(a, "0 of 400 draws of either null reached the rule. The ENTRY null prices\n"
        "drift, costs, barrier width and session timing; the GATE null asks\n"
        "whether a filter of this selectivity is worth anything at all.")

a = ax[1, 0]
iso = pd.read_csv(os.path.join(HERE, "n24_isoos.csv"))
x = np.arange(len(iso))
a.bar(x - 0.19, iso["pct"], 0.36, color=POS, label="delivered %/trade")
a.bar(x + 0.19, iso["mde"], 0.36, color=GRY, label="MDE (2.802 sd/sqrt n)")
a.set_xticks(x); a.set_xticklabels([f"{b}\nn={int(n)}" for b, n in zip(iso["block"], iso["n"])])
a.legend(fontsize=7.6); a.set_title("IS / OOS beside the smallest detectable effect")
note(a, "The ALL bar clears its MDE at 1.18x. Each half does not -- 22 trades\n"
        "cannot resolve an effect this size. Neither half is out-of-sample in\n"
        "the protocol sense: the configuration was chosen seeing the whole file.")

a = ax[1, 1]
wf = pd.read_csv(os.path.join(HERE, "n25_walkforward.csv"))
x = np.arange(len(wf)); w = 0.27
a.bar(x - w, wf["fixed"], w, color=POS, label=f"constants FIXED ({wf.fixed.sum():+.2f})")
a.bar(x, wf["rechosen"], w, color=BLU, label=f"re-chosen on train ({wf.rechosen.sum():+.2f})")
a.bar(x + w, wf["random"], w, color=GRY, label=f"RANDOM cell ({wf.random.sum():+.2f})")
a.axhline(0, color=INK, lw=0.8)
a.set_xticks(x); a.set_xticklabels([f"fold {int(f)}" for f in wf["fold"]])
a.legend(fontsize=7.2); a.set_title("walk-forward: the random cell is the control")
note(a, "A cell drawn BLIND from the same 54-cell grid earns 87% of what the\n"
        "chosen constants earn. The exit geometry is therefore not where the\n"
        "result comes from -- the gate is (see the next panel).")

a = ax[1, 2]
do = pd.read_csv(os.path.join(HERE, "n25_dropone.csv")).query("arm != 'rule (all on)'")
do = do.sort_values("d_pct")
cols = [NEG if v < 0 else POS for v in do["d_pct"]]
a.barh(range(len(do)), do["d_pct"], color=cols)
a.set_yticks(range(len(do))); a.set_yticklabels([])
lox = do["d_pct"].min() * 1.30
for i, (s_, n_) in enumerate(zip(do["arm"], do["n"])):
    a.text(lox * 0.97, i + 0.34, f"{s_} (n={int(n_)})", va="bottom", ha="left",
           fontsize=7.4, color=INK)
a.set_xlim(lox, 0.018)
a.axvline(0, color=INK, lw=0.8)
a.set_title("drop-one: change in %/trade")
note(a, "Red = removing it HURTS. Only the fresh-cross gate matters: without it\n"
        "the rule takes 142 trades at +0.0068 instead of 44 at +0.0548.\n"
        "The opposite-cross exit is EXACTLY zero -- it never fires here.")

fig.tight_layout(rect=[0, 0.02, 1, 0.93]); fig.subplots_adjust(hspace=0.62, wspace=0.30)
fig.savefig(os.path.join(HERE, "fig10_live_validation.png"), dpi=132)
print("fig10_live_validation.png")

# ================================================================ figure 11: can it be traded?
fig, ax = plt.subplots(2, 3, figsize=(15.5, 8.6))
cap(fig, "The same configuration: can it be TRADED?",
    "Everything above asks whether the number is real. These ask whether a real number of this "
    "size survives a broker, a clock and a knob that moves.")

a = ax[0, 0]
sw = pd.read_csv(os.path.join(HERE, "n26_sweeps.csv"))
cm = sw[sw.knob == "cross_min"]
a.plot(cm["value"], cm["pct"], "o-", color=POS, lw=1.9, ms=6)
a.axhline(0, color=GRY, lw=0.8)
a.set_xscale("log"); a.set_xticks(cm["value"]); a.set_xticklabels([int(v) for v in cm["value"]])
for _, q in cm.iterrows():
    a.annotate(f"n={int(q.n)}", (q.value, q.pct), textcoords="offset points",
               xytext=(0, 9), ha="center", fontsize=7, color=MUTE)
a.scatter([5], cm.loc[cm.value == 5, "pct"], s=150, facecolors="none", edgecolors=ACC, lw=2.2,
          zorder=5, label="the configured setting")
a.legend(fontsize=7.6, loc="upper right")
a.margins(y=0.18)
a.set_title("dose-response: the fresh-cross window"); a.set_xlabel("cross must be within N minutes")
a.set_ylabel("%/trade")
note(a, "This is the shape a mechanism has. Tighter is monotonically better,\n"
        "all the way from 40 minutes to 1, and every rung is positive. The\n"
        "configured 5 minutes is mid-curve, not a peak found by searching.")

a = ax[0, 1]
lt = pd.read_csv(os.path.join(HERE, "n26_latency.csv"))
a.plot(lt["delay_min"], lt["kept"], "o-", color=NEG, lw=2.0, ms=6)
a.axhline(1.0, color=GRY, lw=0.9, ls=":"); a.axhline(0, color=INK, lw=0.8)
a.fill_between(lt["delay_min"], lt["kept"], 0, where=lt["kept"] > 0, color=NEG, alpha=0.10)
a.set_title("LATENCY: fraction of the edge left after a delayed fill")
a.set_xlabel("minutes between the signal bar closing and the fill")
a.set_ylabel("fraction of %/trade kept")
note(a, "Half a minute costs 9%. One minute costs 31%. Three minutes turns it\n"
        "NEGATIVE. The median hold is 2.5 minutes, so the delay competes with\n"
        "the trade itself. This is the hardest live-trading constraint here.")

a = ax[0, 2]
sl = pd.read_csv(os.path.join(HERE, "n26_slippage.csv"))
a.plot(sl["slip_pts_per_side"], sl["kept"], "o-", color=ACC, lw=2.0, ms=6, label="edge kept")
a.plot(sl["slip_pts_per_side"], sl["win"] / float((r > 0).mean()), "s--", color=BLU, lw=1.6,
       ms=5, label="win rate kept")
a.axhline(1.0, color=GRY, lw=0.9, ls=":")
a.set_title("ENTRY SLIPPAGE: points given up per side")
a.set_xlabel("extra points per side"); a.legend(fontsize=7.6)
note(a, "P&L is durable -- a 3-point-per-side haircut still keeps 79%. The WIN\n"
        "RATE is not: it falls 0.64 -> 0.41 at the FIRST extra point, because\n"
        "the 10 trades booking the secured +0.71 flip to losses. A live win\n"
        "rate well under the backtest's is expected, not a broken edge.")

a = ax[1, 0]
ks = ["stop_atr", "tgt_pts", "atr_n", "be_pts", "end_m", "flat_m", "range_end", "open_m"]
lo, hi, mid, live = [], [], [], []
for k in ks:
    d = sw[(sw.knob == k) & sw.pct.notna()]
    lo.append(d.pct.min()); hi.append(d.pct.max()); mid.append(d.pct.mean())
    live.append(float(d.loc[d.live == True, "pct"].iloc[0]))
y = np.arange(len(ks))
a.hlines(y, lo, hi, color=GRY, lw=6, alpha=0.55)
a.scatter(mid, y, color=BLU, s=42, zorder=4, label="grid average")
a.scatter(live, y, color=ACC, s=64, marker="D", zorder=5, label="the configured value")
a.axvline(0, color=NEG, lw=1.2)
a.set_yticks(y); a.set_yticklabels(ks, fontsize=8)
a.legend(fontsize=7.4); a.set_title("every knob's own neighbourhood, %/trade")
note(a, "49 of 50 distinct cells across nine knobs are positive. The configured\n"
        "value is the PEAK on only three of them. A hand-search that had found\n"
        "a peak would sit on the maximum of most knobs; this does not.")

a = ax[1, 1]
mo = pd.read_csv(os.path.join(HERE, "n26_months.csv"))
a.bar(mo["month"], mo["tot"], color=[POS if v > 0 else NEG for v in mo["tot"]], width=0.62)
for i, (v, n) in enumerate(zip(mo["tot"], mo["n"])):
    a.text(i, v + 0.02, f"n={int(n)}", ha="center", fontsize=7.6, color=MUTE)
a.axhline(0, color=INK, lw=0.8)
a.set_title("month by month -- the entire sample"); a.set_ylabel("total %")
note(a, "5 of 5 months positive, 14 of 19 weeks, best month 41% of net. But it\n"
        "is five months of one summer on one instrument. No bear market, no\n"
        "rate shock, no volatility event of any kind is anywhere in it.")

a = ax[1, 2]
srt = np.sort(r)[::-1]
a.bar(range(len(srt)), srt, color=[POS if v > 0 else NEG for v in srt], width=0.85)
a.axhline(0, color=INK, lw=0.8)
a.set_title("every trade, sorted"); a.set_xlabel("trade rank"); a.set_ylabel("%")
note(a, f"Top trade is 8.2% of net; removing the best three still leaves\n"
        f"+0.0446 %/trade against +0.0548. The mean is NOT carried by outliers.\n"
        f"The median trade is +0.0014% -- the secured ratchet level.")

fig.tight_layout(rect=[0, 0.02, 1, 0.93]); fig.subplots_adjust(hspace=0.68, wspace=0.28)
fig.savefig(os.path.join(HERE, "fig11_live_tradeability.png"), dpi=132)
print("fig11_live_tradeability.png")
