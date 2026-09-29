"""Figures for STUDY_VP_TPO_SCALP: equity curves, the distance ladder, the condition pool, the target
and stop ladders, and one worked example of a breakout under a prior-session single print."""
import os, sys, warnings, math
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56", "research/v64", "research/inst"): sys.path.insert(0, os.path.join(ROOT, p))
import v61core as V, v64opt as O, vp_tpo as T
warnings.filterwarnings("ignore")
OUT = os.path.join(ROOT, "results/inst"); os.makedirs(OUT, exist_ok=True)
D = O.build(15); n = D["n"]; CUT = D["cut"]; c, h, l, o, atr, mod = D["c"], D["h"], D["l"], D["o"], D["atr"], D["mod"]; ix = pd.DatetimeIndex(D["ix"])
WIN = (mod >= 420) & (mod < 660); ENT = D["ent_all"][0]; EXL = D["exl_all"][0]
F, L = T.build(D); g = lambda k: F[k].to_numpy()
def walk(gate): return O._walk(o, h, l, c, atr, D["calm"], ENT, EXL, gate, D["d_ma"], D["chop"], D["psh_ok"], int(CUT), 3.19, 3.19, 2.3, 15, 0, 0.0, 0, 0.0, 0, V.COST, V.SLIP, int(D["last_bar"]))
spa = g("tpo.prior_single_above_atr"); near = np.nan_to_num((spa <= 3.0).astype(float)).astype(bool)
Rb, pb, bb, sb = walk(WIN); Rf, pf_, bf, sf = walk(WIN & near); Ro, po, bo, so = walk(WIN & ~near)
BG = "#0f1115"; FG = "#e6e6e6"; GRID = "#2a2e36"; C1 = "#8a8f99"; C2 = "#3ec9a7"; C3 = "#e0605e"; C4 = "#f2b134"
plt.rcParams.update({"figure.facecolor": BG, "axes.facecolor": BG, "axes.edgecolor": GRID, "axes.labelcolor": FG, "xtick.color": FG, "ytick.color": FG,
                     "text.color": FG, "grid.color": GRID, "font.size": 10, "axes.titlesize": 12, "legend.facecolor": BG, "legend.edgecolor": GRID})
def pf(q): return q[q > 0].sum() / max(1e-9, -q[q <= 0].sum())

# ---------- 1. equity curves ----------
fig, ax = plt.subplots(figsize=(13, 6))
for nm, pct, sg, col, lw in (("base (all breakouts)", pb, sb, C1, 1.4), ("single print within 3 ATR above (kept)", pf_, sf, C2, 2.0), ("no single print within 3 ATR (dropped)", po, so, C3, 1.4)):
    t = ix[sg]; ax.plot(t, np.cumsum(pct), color=col, lw=lw, label=f"{nm}  n {len(pct)}  PF res {pf(pct[sg < CUT]):.2f} / lock {pf(pct[sg >= CUT]):.2f}")
ax.axvline(ix[CUT], color=C4, ls="--", lw=1); ax.text(ix[CUT], ax.get_ylim()[1] * 0.97, "  locked block begins (2024-11-27)", color=C4, va="top")
ax.axhline(0, color=GRID); ax.grid(alpha=0.4); ax.set_ylabel("cumulative % of entry price, one unit, MNQ costs"); ax.legend(loc="upper left")
ax.set_title("Donchian 10/10 07:00-11:00 scalp, NQ 15m -- split by the prior-session TPO single print overhead")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "vp_fig1_equity.png"), dpi=140); plt.close(fig)

# ---------- 2. the distance ladder (research + locked), by rung and by band ----------
rungs = (0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0); rr = []; rl = []; nr = []
for X in rungs:
    m = np.nan_to_num((spa <= X).astype(float)).astype(bool); R_, pct, blk, sg = walk(WIN & m)
    rr.append(pf(pct[blk == 0])); rl.append(pf(pct[blk == 1])); nr.append((blk == 0).sum())
bands = ((0, 1), (1, 2), (2, 3), (3, 4), (4, 6), (6, 99)); br = []; bl = []; bn = []
for a_, b_ in bands:
    m = np.nan_to_num(((spa > a_) & (spa <= b_)).astype(float)).astype(bool); R_, pct, blk, sg = walk(WIN & m)
    br.append(pct[blk == 0].mean()); bl.append(pct[blk == 1].mean()); bn.append((blk == 0).sum())
fig, axs = plt.subplots(1, 2, figsize=(13, 5))
x = np.arange(len(rungs)); axs[0].bar(x - 0.2, rr, 0.4, color=C2, label="research"); axs[0].bar(x + 0.2, rl, 0.4, color=C4, label="locked (descriptive)")
axs[0].axhline(pf(pb[bb == 0]), color=C1, ls="--", label="base research 1.164"); axs[0].axhline(pf(pb[bb == 1]), color=C1, ls=":", label="base locked 1.110")
axs[0].set_xticks(x); axs[0].set_xticklabels([f"<= {r}\nn {k}" for r, k in zip(rungs, nr)]); axs[0].set_xlabel("single print within X ATR above the close"); axs[0].set_ylabel("profit factor")
axs[0].set_title("Ladder: a hump peaking at 3 ATR, not a gradient"); axs[0].legend(fontsize=8); axs[0].grid(axis="y", alpha=0.4); axs[0].set_ylim(0.9, 1.55)
x = np.arange(len(bands)); axs[1].bar(x - 0.2, br, 0.4, color=C2, label="research"); axs[1].bar(x + 0.2, bl, 0.4, color=C4, label="locked (descriptive)")
axs[1].axhline(0, color=GRID); axs[1].set_xticks(x); axs[1].set_xticklabels([f"{a}-{b if b < 99 else '..'}\nn {k}" for (a, b), k in zip(bands, bn)]); axs[1].set_xlabel("distance band of the nearest single print above (ATR)")
axs[1].set_ylabel("mean % per trade"); axs[1].set_title("By band: the 3-6 ATR bands are negative, so the 3 ATR ceiling does work"); axs[1].legend(fontsize=8); axs[1].grid(axis="y", alpha=0.4)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "vp_fig2_ladder.png"), dpi=140); plt.close(fig)

# ---------- 3. the condition pool: dPF vs control p, coloured by family ----------
RS = pd.read_parquet(os.path.join(OUT, "vp_scalp_conditions.parquet"))
fam = RS.cond.str.split(":").str[0].str.replace("EMA13.*", "EMA 13/48", regex=True).str.replace("EMA13-48.*", "EMA 13/48", regex=True).str.replace("ATR.*|vol percentile.*|signal bar.*", "ATR", regex=True)
cols = {"TPO": C2, "VP": "#4f9de6", "EMA200": C4, "EMA 13/48": C3, "ATR": C1}
fig, ax = plt.subplots(figsize=(13, 7))
for f_, col in cols.items():
    m = fam == f_; ax.scatter(RS.p_pf[m], RS.dpf[m], s=RS.n[m] / 3, color=col, alpha=0.85, label=f_, edgecolor="none")
for r in RS.itertuples():
    if r.p_pf <= 0.06 or r.dpf <= -15: ax.annotate(r.cond, (r.p_pf, r.dpf), fontsize=7.5, xytext=(6, 2), textcoords="offset points", color=FG)
ax.axvline(0.05, color=C4, ls="--", lw=1); ax.text(0.052, ax.get_ylim()[0] + 2, "p 0.05", color=C4, fontsize=8); ax.axhline(0, color=GRID)
ax.set_xlabel("p against a random filter of the same selectivity (research, 250 draws)"); ax.set_ylabel("research PF change vs the base (%)")
ax.set_title("43 entry conditions: one survives BH (TPO single print); every EMA200 / EMA 13/48 / ATR reading sits right of the line  (marker size = trades)")
ax.legend(title="family", loc="lower right"); ax.grid(alpha=0.3)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "vp_fig3_conditions.png"), dpi=140); plt.close(fig)

# ---------- 4. target and stop ladders ----------
TP = pd.read_parquet(os.path.join(OUT, "vp_scalp_tp.parquet")); ST = pd.read_parquet(os.path.join(OUT, "vp_scalp_stops.parquet"))
fig, axs = plt.subplots(1, 2, figsize=(14, 6.5))
fx = TP[TP.rule.str.startswith("fixed")]; lv = TP[~TP.rule.str.startswith("fixed") & (TP.rule != "no target (stop / channel / hold only)")]
axs[0].plot([float(r.split()[1]) for r in fx.rule], fx.pf, "o-", color=C2, lw=2, label="fixed ATR ladder"); axs[0].axhline(TP[TP.rule.str.startswith("no target")].pf.iloc[0], color=C1, ls=":", label="no target")
axs[0].scatter(lv.med_d, lv.pf, color=C4, s=30, alpha=0.9, label="a profile LEVEL as the target (median distance)")
for r in lv.itertuples():
    if r.pf > 1.13: axs[0].annotate(r.rule.replace(" (else 2.3 ATR)", "").replace(" (else 2.3)", ""), (r.med_d, r.pf), fontsize=7, xytext=(5, 3), textcoords="offset points")
axs[0].set_xlabel("target distance (ATR)"); axs[0].set_ylabel("research profit factor"); axs[0].set_title("Take profit: no level beats the fixed 2.3 ATR"); axs[0].legend(fontsize=8); axs[0].grid(alpha=0.3)
fs = ST[ST.rule.str.startswith("fixed")]; xs = [float(r.split()[1]) for r in fs.rule]
ax2 = axs[1]; ax2.plot(xs, fs.pct * 100, "o-", color=C2, lw=2, label="% per trade (x100)"); ax2.plot(xs, fs.R * 10, "s-", color="#4f9de6", lw=1.5, label="R per trade (x10)"); ax2.plot(xs, fs.retdd, "^-", color=C4, lw=1.5, label="return / drawdown")
st_ = ST[~ST.rule.str.startswith("fixed")]
ax2.scatter(st_.med_risk, st_.retdd, color=C3, s=28, alpha=0.9, label="adaptive / ratio / range / structural stops (ret/DD at median risk)")
ax2.axhline(0, color=GRID); ax2.set_xlabel("stop distance (ATR, median)"); ax2.set_title("Stop: the fixed ladder peaks at 3.0 ATR in all three units"); ax2.legend(fontsize=8); ax2.grid(alpha=0.3)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "vp_fig4_tp_stop.png"), dpi=140); plt.close(fig)

# ---------- 5. worked example: a locked-block trade under a single print, with the prior session's TPO profile ----------
sess = (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy(); TB = T.TBIN
cand = [(i, r) for i, r, b in zip(sf, Rf, bf) if b == 1 and r > 0.6 and 570 <= mod[i] < 660]
i0 = cand[len(cand) // 2][0]; day = sess[i0]; prev = sorted(set(sess[(sess < day) & (mod >= 570) & (mod < 960)]))[-1]
pidx = np.flatnonzero((sess == prev) & (mod >= 570) & (mod < 960)); didx = np.flatnonzero((sess == day) & (mod >= 420) & (mod <= 960))
# prior session letter profile
bmin = math.floor(l[pidx].min() / TB); bmax = math.floor(h[pidx].max() / TB); cnt = np.zeros(bmax - bmin + 1, int); last = np.full(len(cnt), -1)
for j in pidx:
    Lt = (mod[j] - 570) // 30; a_, b_ = math.floor(l[j] / TB) - bmin, math.floor(h[j] / TB) - bmin
    for k in range(a_, b_ + 1):
        if last[k] != Lt: cnt[k] += 1; last[k] = Lt
fig, (axp, axd) = plt.subplots(1, 2, figsize=(15, 7), gridspec_kw={"width_ratios": [1.6, 1]}, sharey=True)
def candles(ax, idx, xs):
    for x_, j in zip(xs, idx):
        col = C2 if c[j] >= o[j] else C3; ax.plot([x_, x_], [l[j], h[j]], color=col, lw=1); ax.add_patch(plt.Rectangle((x_ - 0.3, min(o[j], c[j])), 0.6, abs(c[j] - o[j]) + 1e-9, color=col))
xs_p = np.arange(len(pidx)); candles(axp, pidx, xs_p); axp.set_xlim(-1, len(pidx) + 14)
ctr = (bmin + np.arange(len(cnt)) + 0.5) * TB
axp.barh(ctr, cnt * 0.9, height=TB * 0.9, left=len(pidx) + 1, color="#4f9de6", alpha=0.55, label="TPO letters per 2.5-pt bin")
sp = ctr[cnt == 1]; axp.barh(sp, 0.9, height=TB * 0.9, left=len(pidx) + 1, color=C4, alpha=1.0, label="single prints (one letter)")
axp.set_title(f"prior session {str(prev)[:4]}-{str(prev)[4:6]}-{str(prev)[6:]}  RTH 09:30-16:00, 15m bars -> 30-minute letters"); axp.set_xlabel("15m bar of the prior session  |  TPO profile"); axp.legend(loc="upper left", fontsize=8); axp.grid(alpha=0.25)
xs_d = np.arange(len(didx)); candles(axd, didx, xs_d)
k0 = int(np.flatnonzero(didx == i0)[0]); px = o[i0 + 1] + V.SLIP; risk = 3.19 * atr[i0]; tgt = px + 2.3 * atr[i0]
axd.axhline(ENT[i0], color=C1, ls="--", lw=1, label=f"10-bar entry channel {ENT[i0]:.1f}")
axd.annotate("breakout\nsignal bar", (k0, h[i0]), xytext=(k0 - 4, h[i0] + 1.5 * atr[i0]), arrowprops=dict(arrowstyle="->", color=FG), fontsize=8)
axd.hlines([px, px - risk, tgt], k0 + 1, min(k0 + 16, len(didx) - 1), colors=[FG, C3, C2], linestyles=["-", "-", "-"], lw=1.2)
axd.text(min(k0 + 16, len(didx) - 1), tgt, f"  target +2.3 ATR", color=C2, va="center", fontsize=8); axd.text(min(k0 + 16, len(didx) - 1), px - risk, f"  stop -3.19 ATR", color=C3, va="center", fontsize=8)
spa_px = L["pr_spa"][i0]
for s_ in sp: axd.axhline(s_, color=C4, lw=0.8, alpha=0.5)
axd.axhline(spa_px, color=C4, lw=2, label=f"nearest prior single print above: {spa_px:.1f}  ({(spa_px - c[i0]) / atr[i0]:.2f} ATR over the close)")
axd.axvspan(-0.5, np.flatnonzero(mod[didx] >= 570)[0] - 0.5, color=GRID, alpha=0.35); axd.text(0.2, axd.get_ylim()[0] if False else l[didx].min(), " 07:00-09:30 pre-open", fontsize=7, color=C1, va="bottom")
axd.set_title(f"signal day {str(day)[:4]}-{str(day)[4:6]}-{str(day)[6:]}  entry {ix[i0 + 1].strftime('%H:%M')} NY  R {Rf[sf == i0][0]:+.2f}"); axd.set_xlabel("15m bar from 07:00 NY"); axd.legend(loc="upper left", fontsize=8); axd.grid(alpha=0.25)
axp.set_ylabel("NQ (synthetic level)")
fig.suptitle("The mechanism: the breakout is heading into a zone the prior session crossed in ONE 30-minute letter -- no acceptance overhead", fontsize=12)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "vp_fig5_example.png"), dpi=140); plt.close(fig)

# ---------- 6. heat: MAE / MFE inside vs outside, and the exit mix ----------
def exc(sigs):
    mfe = np.array([(h[i + 1:min(i + 16, n - 1) + 1].max() - o[i + 1]) / atr[i] for i in sigs]); mae = np.array([(o[i + 1] - l[i + 1:min(i + 16, n - 1) + 1].min()) / atr[i] for i in sigs]); return mfe, mae
fig, axs = plt.subplots(1, 2, figsize=(13, 5))
for nm, sg, col in (("kept: single print <= 3 ATR above", sf, C2), ("dropped: none within 3 ATR", so, C3)):
    mfe, mae = exc(sg[np.array([True] * len(sg))]); axs[0].hist(mae, bins=np.linspace(0, 12, 49), histtype="step", lw=2, color=col, density=True, label=f"{nm}: mean MAE {mae.mean():.2f} ATR, MFE {mfe.mean():.2f}")
axs[0].set_xlabel("maximum adverse excursion over the 15-bar hold (ATR)"); axs[0].set_ylabel("density"); axs[0].set_title("Less heat under a single print, the same upside"); axs[0].legend(fontsize=8); axs[0].grid(alpha=0.3)
NXT = np.append(o[1:], np.nan) + V.SLIP
mix = {}
for nm, gg in (("kept", WIN & near), ("dropped", WIN & ~near)):
    R_, pct, blk, sg, why = T.walk_tp(o, h, l, c, atr, ENT, EXL, gg, int(CUT), np.full(n, 3.19), NXT + 2.3 * atr, 15, V.COST, V.SLIP, int(D["last_bar"]))
    mix[nm] = [100 * np.mean(why == w) for w in (1, 0, 2)]
x = np.arange(3); axs[1].bar(x - 0.2, mix["kept"], 0.4, color=C2, label="kept"); axs[1].bar(x + 0.2, mix["dropped"], 0.4, color=C3, label="dropped")
axs[1].set_xticks(x); axs[1].set_xticklabels(["target (+2.3 ATR)", "stop (-3.19 ATR)", "hold cap (230 min)"]); axs[1].set_ylabel("% of trades"); axs[1].set_title("Exit mix, both blocks"); axs[1].legend(); axs[1].grid(axis="y", alpha=0.3)
for xi, (a_, b_) in enumerate(zip(mix["kept"], mix["dropped"])): axs[1].text(xi - 0.2, a_ + 0.5, f"{a_:.0f}%", ha="center", fontsize=8); axs[1].text(xi + 0.2, b_ + 0.5, f"{b_:.0f}%", ha="center", fontsize=8)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "vp_fig6_heat.png"), dpi=140); plt.close(fig)
print("figures written to", OUT)
