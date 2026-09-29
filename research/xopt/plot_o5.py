"""Four figures for O5: did the published VWAP-EMA gold rule pass out of sample, is it overfitted,
how robust is it, and where does its result come from."""
import sys, os, json
sys.path.insert(0, "research")
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

R, W = "results/xopt/", "results/vwapema/"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#c9ced6",
                     "axes.linewidth": .9, "xtick.color": "#4b5158", "ytick.color": "#4b5158",
                     "text.color": "#1d2126", "axes.labelcolor": "#4b5158",
                     "figure.facecolor": "white", "axes.facecolor": "white"})
INK, INK2, MUTE, GRID = "#1d2126", "#4b5158", "#8b929c", "#dfe3e8"
BLUE, ORANGE, AQUA, PURP, GOLD, RED = "#2a78d6", "#eb6834", "#1baf7a", "#7a5cd6", "#c8a032", "#c0392b"


def head(fig, title, sub, verdict, vcol=ORANGE, y=(.955, .921, .898, .872)):
    fig.text(.055, y[0], title, fontsize=19, weight="bold", color=INK)
    for i, s in enumerate(sub):
        fig.text(.055, y[1] - i * (y[1] - y[2]), s, fontsize=10, color=INK2)
    fig.text(.055, y[3], verdict, fontsize=10.4, color=vcol, weight="bold")


# ==================================================================== FIGURE 1 -- THE OOS VERDICT
lk = pd.read_csv(W + "locked.csv")
xm = pd.read_csv(W + "m1_published.csv")
fw = pd.read_csv(W + "m3_forward.csv")

fig = plt.figure(figsize=(15.4, 9.4))
gs = fig.add_gridspec(2, 2, hspace=.52, wspace=.26, left=.075, right=.972, top=.815, bottom=.075)
head(fig, "Did it pass out of sample?",
     ["XAU_ISO_15m, 371,586 bars 2010-01..2026-01, gold's cost floor, one unit. Research block to 2020-05-25; the locked block was read ONCE.",
      "The matched control is a random New York entry running the IDENTICAL stop, target, trail, costs and position lock."],
     "Verdict: it makes money on the locked block and LOSES on research — the wrong shape — and its control loses money too, so beating it is not evidence.")

ax = fig.add_subplot(gs[0, 0])
lab = ["research\n(chose it)", "locked\n(read once)"]
L = lk[lk.side == "LONG"].reset_index(drop=True)
x = np.arange(2); w = .36
ax.bar(x - w/2, L.R, w, color=[RED, AQUA], zorder=3)
for i, v in enumerate(L.R):
    ax.text(x[i] - w/2, v + (.006 if v >= 0 else -.006), f"{v:+.4f} R", ha="center",
            va="bottom" if v >= 0 else "top", fontsize=10, weight="bold", color=INK)
ax2 = ax.twinx()
ax2.plot(x + w/2, L.pf, "o", ms=11, color=BLUE, zorder=4)
for i, v in enumerate(L.pf):
    ax2.text(x[i] + w/2, v, f"PF {v:.3f}  ", va="center", ha="right", fontsize=9.6, color=BLUE, weight="bold")
ax2.axhline(1.0, color=BLUE, lw=1, ls=":")
ax2.set_ylabel("profit factor", color=BLUE); ax2.set_ylim(.75, 1.55)
ax.axhline(0, color=INK2, lw=1.2)
ax.set_xticks(x); ax.set_xticklabels([f"{a}\nn = {int(b)}" for a, b in zip(lab, L.n)], fontsize=9.6)
ax.set_ylabel("R per trade"); ax.set_ylim(-.09, .21)
ax.set_title("The long side, as specified", fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)

ax = fig.add_subplot(gs[0, 1])
xs = np.arange(2)
ax.bar(xs - w/2, L.R, w, color=BLUE, label="the rule", zorder=3)
ax.bar(xs + w/2, L.ctl_R, w, color=MUTE, label="matched random entry", zorder=3)
for i in range(2):
    ax.text(xs[i] - w/2, L.R[i] + .01, f"{L.R[i]:+.3f}", ha="center", fontsize=9, color=INK)
    ax.text(xs[i] + w/2, L.ctl_R[i] - .014, f"{L.ctl_R[i]:+.3f}", ha="center", va="top", fontsize=9, color=INK)
    ax.text(xs[i], .225, f"p = {L.p_ctl[i]:.4f}", ha="center", fontsize=9.6, weight="bold", color=AQUA)
ax.axhline(0, color=INK2, lw=1.4)
ax.set_xticks(xs); ax.set_xticklabels(lab, fontsize=9.6)
ax.set_ylabel("R per trade"); ax.set_ylim(-.40, .28)
ax.legend(frameon=False, fontsize=9, loc="lower center", ncol=2)
ax.set_title("It clears its control — and the control LOSES on both blocks",
             fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)

ax = fig.add_subplot(gs[1, 0])
xl = xm[xm.side == "LONG"].reset_index(drop=True)
xk = [f"{r.feed}\n{r.block[:4].lower()}" for _, r in xl.iterrows()]
c = [AQUA if v > 0 else RED for v in xl.R]
ax.bar(np.arange(len(xl)), xl.R, .62, color=c, zorder=3)
for i, v in enumerate(xl.R):
    ax.text(i, v + (.008 if v >= 0 else -.008), f"{v:+.3f}", ha="center",
            va="bottom" if v >= 0 else "top", fontsize=8.4, color=INK)
ax.axhline(0, color=INK2, lw=1.2)
ax.set_xticks(np.arange(len(xl))); ax.set_xticklabels(xk, fontsize=8.4)
ax.set_ylabel("R per trade, long side")
ax.set_title("Three markets that had no part in writing it", fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)
ax.set_ylim(-.115, .325)
ax.text(.02, .96, "US30_ISO is a DIFFERENT provider, 2024-08..2026-08 — a reserved\nforward block no search of any kind has touched.",
        transform=ax.transAxes, fontsize=8.6, color=MUTE, va="top")

ax = fig.add_subplot(gs[1, 1])
fp = fw[fw.cell.astype(str).str.startswith("As published")].drop_duplicates("cell").reset_index(drop=True)
ax.axis("off")
rows = [["block", "n", "R/trade", "PF", "control p", "bootstrap"],
        ["research (chose it)", f"{int(L.n[0])}", f"{L.R[0]:+.4f}", f"{L.pf[0]:.3f}", f"{L.p_ctl[0]:.4f}", "1.000"],
        ["LOCKED (one read)", f"{int(L.n[1])}", f"{L.R[1]:+.4f}", f"{L.pf[1]:.3f}", f"{L.p_ctl[1]:.4f}", "0.054"]]
for _, r in fp.iterrows():
    rows.append([f"forward {r.cell[-1]} (US30_ISO)", f"{int(r.n)}", f"{r.R:+.4f}", f"{r.pf:.3f}",
                 f"{r.p_ctl:.3f}", f"{r.boot_p:.3f}" if pd.notna(r.boot_p) else "—"])
tb = ax.table(cellText=rows[1:], colLabels=rows[0], loc="upper center", cellLoc="center",
              colWidths=[.30, .12, .16, .12, .16, .16])
tb.auto_set_font_size(False); tb.set_fontsize(9.2); tb.scale(1, 1.85)
for j in range(6):
    tb[0, j].set_facecolor("#eef1f5"); tb[0, j].set_text_props(weight="bold", color=INK)
for i in range(1, len(rows)):
    for j in range(6):
        tb[i, j].set_edgecolor(GRID)
ax.set_title("Every out-of-sample read in one place", fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
ax.text(0, .16, "The bootstrap is the column that matters: on the locked block P(mean R ≤ 0) = 0.054, so the 95%\n"
                "interval touches zero. It beats a losing null and it does not beat zero — both are true, and a\n"
                "214-trade block can answer the first question and not the second.",
        transform=ax.transAxes, fontsize=9, color=INK2, va="top")
fig.savefig(R + "o5_oos.png", dpi=140, facecolor="white")
print("wrote", R + "o5_oos.png")

# ==================================================================== FIGURE 2 -- OVERFITTING
pk = json.load(open(W + "pbo.json"))
za = np.load(W + "pbo_arrays.npz", allow_pickle=True)
pr = pd.read_csv(W + "preset_ranks.csv")
wf = pd.read_csv(W + "wfo_published.csv")
nb = pd.read_csv(W + "neighbourhood.csv")

fig = plt.figure(figsize=(15.4, 9.4))
gs = fig.add_gridspec(2, 2, hspace=.62, wspace=.40, left=.105, right=.972, top=.815, bottom=.115)
head(fig, "Is it overfitted?",
     ["Three different questions wear that word. Is the RULE fitted (rolling walk-forward, nothing re-selected)? Is the SEARCH overfit (selection re-run per fold)?",
      "And what is P(overfit) — CSCV over all 12,870 symmetric splits of a 1,839-cell pool. This rule is the rare case where the first question has a clean answer."],
     "Verdict: NOT overfitted. Its ten constants came from a paper, and it ranks BELOW MEDIAN (0.443) in its own pool — the signature of a cell chosen by convention.",
     vcol=AQUA)

ax = fig.add_subplot(gs[0, 0])
o = pr.sort_values("IS_rank")
cols = [AQUA if p == "As published" else MUTE for p in o.preset]
ax.barh(np.arange(len(o)), o.IS_rank, .6, color=cols, zorder=3)
for i, (v, p) in enumerate(zip(o.IS_rank, o.preset)):
    ax.text(v + .012, i, f"{v:.3f}", va="center", fontsize=9,
            color=AQUA if p == "As published" else INK, weight="bold" if p == "As published" else "normal")
ax.axvline(.5, color=ORANGE, lw=2, ls="--")
ax.text(.505, -.75, " median of the pool", color=ORANGE, fontsize=9, weight="bold", va="bottom")
ax.set_yticks(np.arange(len(o))); ax.set_yticklabels(o.preset, fontsize=9.4)
ax.set_xlabel("median in-sample rank inside its own 1,839-cell pool"); ax.set_xlim(0, 1.12)
ax.set_title("A fitted cell sits at the top of its own pool. This one does not.",
             fontsize=11.8, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="x", alpha=.2, color=GRID); ax.set_axisbelow(True)

ax = fig.add_subplot(gs[0, 1])
lam = za["lam"]
ax.hist(lam, bins=55, color=BLUE, alpha=.85, zorder=3)
ax.axvline(0, color=ORANGE, lw=2.4, ls="--", zorder=4)
ax.text(.02, .95, f"PBO = {pk['PBO']:.3f}\nslope of OOS on IS = {pk['slope']:+.3f}",
        transform=ax.transAxes, fontsize=11, weight="bold", color=ORANGE, va="top")
ax.text(.02, .68, "this is the POOL's PBO, not the rule's:\nselecting a winner from this grid is\n"
                  "actively harmful — and the published\nrule is not a product of that selection",
        transform=ax.transAxes, fontsize=8.4, color=MUTE, va="top")
ax.set_xlabel("logit of the in-sample winner's out-of-sample rank"); ax.set_ylabel("splits")
ax.set_title("CSCV — 12,870 symmetric splits", fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
ax.grid(alpha=.2, color=GRID); ax.set_axisbelow(True)

ax = fig.add_subplot(gs[1, 0])
xw = np.arange(len(wf)); w = .38
ax.bar(xw - w/2, wf.IS_R, w, color=MUTE, label="in-sample (3-yr train)", zorder=3)
ax.bar(xw + w/2, wf.OOS_R, w, color=BLUE, label="out-of-sample (next year)", zorder=3)
ax.axhline(0, color=INK2, lw=1.2)
ax.set_xticks(xw); ax.set_xticklabels([t[:4] for t in wf.test], fontsize=8.4)
ax.set_ylabel("R per trade")
ax.legend(frameon=False, fontsize=8.8, ncol=2, loc="lower left")
ax.set_title("Rolling walk-forward, NOTHING re-selected", fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
fig.text(.105, .055, f"mean IS {wf.IS_R.mean():+.4f} vs OOS {wf.OOS_R.mean():+.4f}  →  gap {wf.IS_R.mean()-wf.OOS_R.mean():+.4f};   "
                     f"corr(IS, OOS) = {wf.IS_R.corr(wf.OOS_R):+.3f} — a 3-year window ANTI-predicts\n"
                     "the next year even though nothing is fitted here. That is REGIME, not curve-fitting.",
         fontsize=8.8, color=INK2, va="top")
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)

ax = fig.add_subplot(gs[1, 1])
params = list(dict.fromkeys(nb.param))
yy, ranks = [], []
for i, p in enumerate(params):
    d = nb[nb.param == p].sort_values("R").reset_index(drop=True)
    k = int(d.index[d.spec][0]); ranks.append((k + 1, len(d)))
    ax.plot(np.arange(len(d)) / (len(d) - 1), [i] * len(d), "-", color=GRID, lw=6, zorder=1,
            solid_capstyle="round")
    ax.scatter(np.arange(len(d)) / (len(d) - 1), [i] * len(d), s=42, color=MUTE, zorder=3)
    ax.scatter([k / (len(d) - 1)], [i], s=130, color=ORANGE, zorder=4, edgecolor="white", lw=1.4)
ax.set_yticks(np.arange(len(params)))
ax.set_yticklabels([f"{p}   (spec is {a} of {b})" for p, (a, b) in zip(params, ranks)], fontsize=8.8)
ax.set_xticks([0, .5, 1]); ax.set_xticklabels(["worst rung", "", "best rung"], fontsize=9)
ax.set_xlim(-.08, 1.08)
ax.set_title("Where the spec's own value sits on each ladder", fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
fig.text(.585, .055, "Orange = the published value. It is NEVER the best rung on any axis — exactly what a\n"
                     "configuration nobody tuned on this data looks like, and the opposite of an optimised cell.",
         fontsize=8.8, color=INK2, va="top")
ax.grid(axis="x", alpha=.15, color=GRID); ax.set_axisbelow(True)
fig.savefig(R + "o5_overfit.png", dpi=140, facecolor="white")
print("wrote", R + "o5_overfit.png")

# ==================================================================== FIGURE 3 -- ROBUSTNESS
JI = pd.read_csv(R + "o5_jitter.csv")
PJ = pd.read_csv(R + "o5_paramjitter.csv")
CL = pd.read_csv(R + "o5_costladder.csv")
EX = pd.read_csv(R + "o5_exec.csv")
VD = json.load(open(R + "o5_verdict.json"))
TB = pd.read_csv(R + "o6_tiebreak.csv")
TJ = json.load(open(R + "o6_tiebreak.json"))
_L = pd.read_csv(W + "locked.csv").query("side=='LONG'").reset_index(drop=True)
b_res, b_lck = float(_L.R[0]), float(_L.R[1])
n_res, n_lck = int(_L.n[0]), int(_L.n[1])

fig = plt.figure(figsize=(16.6, 9.6))
gs = fig.add_gridspec(2, 3, hspace=.58, wspace=.30, left=.062, right=.977, top=.805, bottom=.155)
head(fig, "How robust is it?",
     ["Four perturbations, weakest first. Execution and cost move the arithmetic on a FIXED trade set; a joint parameter jitter moves the rules; price jitter with every",
      "indicator RECOMPUTED is the only one that moves the signal set — and here it did something a robustness test is not supposed to do, which is the last two panels."],
     "Verdict: nothing breaks it — and the cost ladder shows why that is faint praise, while the tie-break shows its trade count is a property of your data provider.")

ax = fig.add_subplot(gs[0, 0])
for tk, col in zip(sorted(JI.ticks.unique()), (BLUE, ORANGE, PURP)):
    d = JI[JI.ticks == tk]
    ax.hist(d.R_lck, bins=30, histtype="step", lw=2, color=col, label=f"{tk:g} tick")
ax.axvline(b_lck, color=INK, lw=2, ls="--")
ax.axvline(0, color=RED, lw=1.6, ls=":")
ax.text(b_lck, ax.get_ylim()[1] * .97, " unjittered", fontsize=8.6, color=INK, va="top")
ax.set_xlabel("locked-block R per trade"); ax.set_ylabel("draws")
ax.legend(frameon=False, fontsize=8.6, title="OHLC noise", title_fontsize=8.6)
ax.set_title("Price jitter, indicators recomputed", fontsize=11.4, weight="bold", color=INK, loc="left", pad=8)
ax.text(.03, .58, f"sign kept: {VD['jitter1_sign_kept_locked']:.3f}", transform=ax.transAxes,
        fontsize=9.4, weight="bold", color=AQUA)
ax.grid(alpha=.2, color=GRID); ax.set_axisbelow(True)

ax = fig.add_subplot(gs[0, 1])
mm = JI.groupby("ticks")[["n_res", "n_lck"]].mean()
xt = np.arange(len(mm)); w = .36
ax.bar(xt - w/2, mm.n_res, w, color=RED, label="research", zorder=3)
ax.bar(xt + w/2, mm.n_lck, w, color=AQUA, label="locked", zorder=3)
ax.axhline(n_res, color=RED, lw=1.8, ls="--"); ax.axhline(n_lck, color=AQUA, lw=1.8, ls="--")
ax.set_xlim(-.55, 3.35)
ax.text(2.62, n_res, f"unjittered\n{n_res}", fontsize=8.2, color=RED, ha="left", va="center", weight="bold")
ax.text(2.62, n_lck, f"unjittered\n{n_lck}", fontsize=8.2, color=AQUA, ha="left", va="center", weight="bold")
ax.set_xticks(xt); ax.set_xticklabels([f"{t:g} tick" for t in mm.index], fontsize=9)
ax.set_ylabel("trades"); ax.set_ylim(0, 760)
ax.legend(frameon=False, fontsize=8.8, loc="upper right", ncol=2)
ax.set_title("...and the TRADE COUNT jumps and then flatlines", fontsize=11.0, weight="bold", color=INK, loc="left", pad=8)
ax.text(.03, .80, "A level shift with no dose response is a\nDEGENERATE BOUNDARY, not sensitivity.\nIt is C4b — see the last panel.",
        transform=ax.transAxes, fontsize=8.4, color=ORANGE, va="top", weight="bold")
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)

ax = fig.add_subplot(gs[0, 2])
ax.scatter(PJ.R_res, PJ.R_lck, s=13, color=MUTE, alpha=.6, zorder=3)
ax.scatter([b_res], [b_lck], s=150, marker="*", color=ORANGE, zorder=5, edgecolor="white", lw=1.2)
ax.annotate("as published", (b_res, b_lck), textcoords="offset points", xytext=(10, 7),
            fontsize=8.8, weight="bold", color=ORANGE)
ax.axhline(0, color=INK2, lw=1); ax.axvline(0, color=INK2, lw=1)
ax.set_xlabel("research R per trade"); ax.set_ylabel("locked R per trade")
ax.set_title("Joint ±20% jitter, all ten parameters", fontsize=11.4, weight="bold", color=INK, loc="left", pad=8)
ax.text(.03, .96, f"{len(PJ)} draws · locked positive {VD['param_share_pos_locked']:.0%}\n"
                  f"research positive {float((PJ.R_res>0).mean()):.0%}",
        transform=ax.transAxes, fontsize=8.8, va="top", color=INK)
ax.text(.03, .06, "left of zero on research, right of it on locked:\nthe wrong shape belongs to the FAMILY",
        transform=ax.transAxes, fontsize=8.2, color=MUTE, ha="left", va="bottom")
ax.grid(alpha=.2, color=GRID); ax.set_axisbelow(True)

ax = fig.add_subplot(gs[1, 0])
ax.plot(CL.mult, CL.R_res, "o-", lw=2.4, ms=7, color=RED, label="research")
ax.plot(CL.mult, CL.R_lck, "o-", lw=2.4, ms=7, color=AQUA, label="locked")
ax.axhline(0, color=INK2, lw=1.4)
ax.axvline(1.0, color=ORANGE, lw=2, ls="--")
ax.text(1.06, CL.R_res.min() * .55, "gold's real\ncost floor", fontsize=8.4, color=ORANGE, weight="bold")
ax.set_xlabel("multiple of the assumed cost"); ax.set_ylabel("R per trade")
ax.legend(frameon=False, fontsize=9)
ax.set_title("The cost ladder is the whole story", fontsize=11.4, weight="bold", color=INK, loc="left", pad=8)
ax.text(.03, .06, "At ZERO cost research is POSITIVE (+0.076). The round turn is\n~17% of a 0.5×ATR stop on gold — that is what takes it under.",
        transform=ax.transAxes, fontsize=8.4, color=INK2, va="bottom")
ax.grid(alpha=.2, color=GRID); ax.set_axisbelow(True)

ax = fig.add_subplot(gs[1, 1])
ax.hist(EX.R_lck, bins=36, color=AQUA, alpha=.8, zorder=3, label="locked")
ax.hist(EX.R_res, bins=36, color=RED, alpha=.6, zorder=3, label="research")
ax.axvline(0, color=INK2, lw=1.8)
ax.set_xlabel("R per trade, cost U(0.5×,2×) · slip U(0,2×)"); ax.set_ylabel("draws")
ax.legend(frameon=False, fontsize=9)
ax.set_title("Execution perturbation — run first, weakest", fontsize=11.4, weight="bold", color=INK, loc="left", pad=8)
ax.text(.97, .95, f"P(locked ≤ 0) = {VD['exec_P_R_le_0_locked']:.3f}\nP(research ≤ 0) = {float((EX.R_res<=0).mean()):.3f}",
        transform=ax.transAxes, fontsize=9, weight="bold", color=INK, ha="right", va="top")
ax.grid(alpha=.2, color=GRID); ax.set_axisbelow(True)

ax = fig.add_subplot(gs[1, 2])
lbl = ["STRICT\nopen < prev close\n(the script)", "TOUCH\nopen ≤ prev close\n(a feed with a gap)"]
xt = np.arange(2); w = .34
ax.bar(xt - w/2, TB.signals, w, color=MUTE, label="signals", zorder=3)
ax.bar(xt + w/2, TB.n_lck, w, color=BLUE, label="locked trades", zorder=3)
for i in range(2):
    ax.text(xt[i] - w/2, TB.signals[i] + 18, f"{int(TB.signals[i])}", ha="center", fontsize=9, color=INK)
    ax.text(xt[i] + w/2, TB.n_lck[i] + 18, f"{int(TB.n_lck[i])}", ha="center", fontsize=9, color=BLUE, weight="bold")
    ax.text(xt[i], -235, f"locked PF {TB.pf_lck[i]:.3f}\nlocked totR {TB.totR_lck[i]:+.1f}",
            ha="center", fontsize=8.8, color=INK, weight="bold")
ax.set_xticks(xt); ax.set_xticklabels(lbl, fontsize=8.4)
ax.set_ylim(-430, 1330)
ax.set_ylabel("count")
ax.legend(frameon=False, fontsize=8.8, loc="upper center", ncol=2)
ax.set_title("The same rule, two tie-break conventions", fontsize=11.4, weight="bold", color=INK, loc="left", pad=8)
fig.text(.680, .075, f"open == prev close EXACTLY on {100*TJ['tie_share']:.1f}% of bars, and C4b needs a\n"
                     "STRICT `<`, so those bars are refused. Accepting them gives +50%\n"
                     "signals — and PF falls 1.318 → 1.208 while total R barely moves, so the\n"
                     "tie-rejection is an accidental filter, not a rule anyone wrote.",
         fontsize=8.4, color=ORANGE, va="top", weight="bold")
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.savefig(R + "o5_robust.png", dpi=140, facecolor="white")
print("wrote", R + "o5_robust.png")

# ==================================================================== FIGURE 4 -- ANATOMY
by = pd.read_csv(W + "byyear.csv")
ex = pd.read_csv(W + "exits.csv")
d1 = pd.read_csv(W + "dropone_long.csv")
br = pd.read_csv(W + "baserates.csv")
br = br[br.side == "LONG"]

fig = plt.figure(figsize=(15.4, 9.4))
gs = fig.add_gridspec(2, 2, hspace=.52, wspace=.26, left=.075, right=.972, top=.815, bottom=.135)
head(fig, "Where does the result come from?",
     ["A verdict on a strategy is not complete without its anatomy: which years carry it, which exit actually fires, and which of the six conditions earns its place.",
      "Base rates are computed on the bars the OTHER five conditions already admit — a confirmation that passes 88% of them is not a filter."],
     "Verdict: the trail is the dominant exit and a consistent loser, the paper's assumed outcome distribution is wrong, and only C3 and C5 bind.")

ax = fig.add_subplot(gs[0, 0])
c = [AQUA if v > 0 else RED for v in by.R]
ax.bar(by.year, by.R, .7, color=c, zorder=3)
ax.axhline(0, color=INK2, lw=1.2)
ax.set_ylabel("R per trade"); ax.set_xlabel("")
ax.set_ylim(-.72, .46)
ax.xaxis.set_major_locator(matplotlib.ticker.MultipleLocator(2))
ax.xaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%d"))
lastr = float(by.R.iloc[-1]); lastn = int(by.n.iloc[-1])
ax.annotate(f"{lastr:+.2f} on n = {lastn}\n(off scale — ignore it)", xy=(int(by.year.iloc[-1]), .44),
            xytext=(int(by.year.iloc[-1]) - 5.6, .385), fontsize=8.6, color=ORANGE, weight="bold",
            arrowprops=dict(arrowstyle="->", color=ORANGE, lw=1.4))
ax.text(.36, .05, "2024 is the paper's own sample and the 2nd best of sixteen: +0.244 R,\nPF 1.55, win 41.3% — against its claimed +0.414 R, PF 1.76, 45.3%.",
        transform=ax.transAxes, fontsize=8.8, color=INK2, va="bottom")
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)

ax = fig.add_subplot(gs[0, 1])
sp = ex.iloc[0]
meas = [sp.stop_pct, sp.tgt_pct, sp.trail_pct]
assumed = [42.0, 30.0, 28.0]
xe = np.arange(3); w = .37
ax.bar(xe - w/2, assumed, w, color=MUTE, label="the paper's ASSUMED distribution", zorder=3)
ax.bar(xe + w/2, meas, w, color=BLUE, label="measured on gold", zorder=3)
for i in range(3):
    ax.text(xe[i] - w/2, assumed[i] + 1.2, f"{assumed[i]:.0f}%", ha="center", fontsize=9, color=INK)
    ax.text(xe[i] + w/2, meas[i] + 1.2, f"{meas[i]:.1f}%", ha="center", fontsize=9, weight="bold", color=BLUE)
ax.set_xticks(xe); ax.set_xticklabels(["initial stop", "3R target", "EMA trail\n(+ breakeven)"], fontsize=9.4)
ax.set_ylabel("share of trades"); ax.set_ylim(0, 74)
ax.legend(frameon=False, fontsize=9)
ax.set_title("The assumed outcome distribution is wrong", fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
ax.text(.02, .58, "The trail is the DOMINANT exit at 61.1% and a consistent loser\n(mean −0.190 R). The paper's four-outcome table calls it a breakeven.",
        transform=ax.transAxes, fontsize=8.8, color=INK2, va="top")
ax.grid(axis="y", alpha=.2, color=GRID); ax.set_axisbelow(True)

ax = fig.add_subplot(gs[1, 0])
dd = d1[d1.dropped != "-- none (full rule) --"].reset_index(drop=True)
c = [RED if v < 0 else AQUA for v in dd.dR]
ax.barh(np.arange(len(dd)), dd.dR, .6, color=c, zorder=3)
for i, (v, n) in enumerate(zip(dd.dR, dd.n)):
    ax.text(v + (.003 if v >= 0 else -.003), i, f"{v:+.3f}   (n {int(n)})", va="center",
            ha="left" if v >= 0 else "right", fontsize=8.8, color=INK)
ax.axvline(0, color=INK2, lw=1.4)
ax.set_yticks(np.arange(len(dd))); ax.set_yticklabels(dd.dropped, fontsize=9.4)
ax.set_xlabel("change in R per trade when this condition is REMOVED")
ax.set_xlim(-.16, .05)
ax.set_title("Drop-one: which condition earns its place", fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
fig.text(.075, .052, "Negative = removing it makes the rule worse, so it contributes. C3 (the EMA50 pullback) and\n"
                     "C5 (volume) carry it; C2 — the VWAP the paper is named for — is +0.001, i.e. nothing.",
         fontsize=8.8, color=INK2, va="top")
ax.grid(axis="x", alpha=.2, color=GRID); ax.set_axisbelow(True)

ax = fig.add_subplot(gs[1, 1])
bo = br.sort_values("given_rest_pct").reset_index(drop=True)
c = [RED if v > 80 else (GOLD if v > 55 else AQUA) for v in bo.given_rest_pct]
ax.barh(np.arange(len(bo)), bo.given_rest_pct, .6, color=c, zorder=3)
for i, v in enumerate(bo.given_rest_pct):
    ax.text(v + 1.2, i, f"{v:.1f}%", va="center", fontsize=9, color=INK)
ax.axvline(80, color=RED, lw=2, ls="--")
ax.text(110, 1.0, "above here it is\nthe trigger restated", color=RED, fontsize=8.8,
        weight="bold", va="center", ha="right")
ax.set_yticks(np.arange(len(bo))); ax.set_yticklabels(bo.cond, fontsize=9.6)
ax.set_xlabel("pass rate on the bars the OTHER conditions already admit"); ax.set_xlim(0, 112)
ax.set_title("Condition base rates — computed before any P&L", fontsize=12.4, weight="bold", color=INK, loc="left", pad=8)
ax.grid(axis="x", alpha=.2, color=GRID); ax.set_axisbelow(True)
fig.savefig(R + "o5_anatomy.png", dpi=140, facecolor="white")
print("wrote", R + "o5_anatomy.png")
