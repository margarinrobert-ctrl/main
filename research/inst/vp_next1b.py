"""Tier 1.2-1.5 of the handoff, research block only (locked shown in brackets, descriptive):
1.2  the stop ladder INSIDE the gate, judged on R/trade and MC p99 drawdown, not PF
1.3  the extension factor: is the single print just the best-measured reading of 'room above /
     not extended'? Spearman matrix, conditional IC inside the gate, decile monotonicity
1.4  drop-one extended: the gate within terciles of each extension variable
1.5  the DAY effect without the Donchian: single-print days vs the rest, and a random entry
     inside the gate's own days (day alpha vs interaction with the breakout)
"""
import os, sys, warnings, numpy as np, pandas as pd
from scipy.stats import spearmanr, ttest_ind
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56", "research/v64", "research/inst"): sys.path.insert(0, os.path.join(ROOT, p))
import v61core as V, v64opt as O, vp_tpo as T
warnings.filterwarnings("ignore"); pd.set_option("display.width", 220)
def line(t): print("\n" + "=" * 118 + f"\n{t}\n" + "=" * 118, flush=True)
D = O.build(15); n = D["n"]; CUT = D["cut"]; c, h, l, o, v, atr, mod = D["c"], D["h"], D["l"], D["o"], D["v"], D["atr"], D["mod"]; ix = pd.DatetimeIndex(D["ix"])
WIN = (mod >= 420) & (mod < 660); ENT = D["ent_all"][0]; EXL = D["exl_all"][0]; day = (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy()
F, L = T.build(D); g = lambda k: F[k].to_numpy(); spa = g("tpo.prior_single_above_atr"); near = np.nan_to_num((spa <= 3.0).astype(float)).astype(bool)
NXT = np.append(o[1:], np.nan) + V.SLIP; tgt = NXT + 2.3 * atr
def wtp(gate, stop_arr): return T.walk_tp(o, h, l, c, atr, ENT, EXL, gate, int(CUT), stop_arr, tgt, 15, V.COST, V.SLIP, int(D["last_bar"]))
def pf(q): return q[q > 0].sum() / max(1e-9, -q[q <= 0].sum())
def dd(q): e = np.cumsum(q); return float(np.max(np.maximum.accumulate(e) - e))
rng = np.random.default_rng(53)
def p99(q, B=2000): return float(np.percentile([dd(rng.permutation(q)) for _ in range(B)], 99))
sigbar = np.zeros(n, bool); sigbar[1000:D["last_bar"]] = (h[1000:D["last_bar"]] > ENT[1000:D["last_bar"]]) & WIN[1000:D["last_bar"]]
sig_res = sigbar & (np.arange(n) < CUT)

line("1.2  STOP LADDER INSIDE THE GATE (research; locked in brackets) -- judge on R/trade and MC p99 drawdown")
vp_ = g("atr.vol_pct250")
rules = {f"fixed {k:.2f} ATR": np.full(n, k) for k in (1.5, 2.0, 2.5, 3.0, 3.19, 4.0, 6.0)}
def struct(level, pad=0.25, fb=3.19): d = (NXT - level) / atr + pad; return np.where(np.isfinite(level) & (d >= 1.0) & (d <= 6.0), d, fb)
rules["below EMA200 + 0.25 ATR (fallback 3.19)"] = struct(L["e200"]); rules["below EMA48 + 0.25 ATR"] = struct(L["e48"])
rules["adaptive 4.0 calm / 2.5 hot (V22)"] = np.where(vp_ <= 0.5, 4.0, 2.5); rules["adaptive 3.19 calm / 2.0 hot"] = np.where(vp_ <= 0.5, 3.19, 2.0)
print(f"  {'stop':40s} {'n':>4} {'PF':>6} {'%/tr':>8} {'R/tr':>8} {'sumR':>6} {'tot%':>6} {'DD%':>5} {'p99DD':>6} {'tot/p99':>7} {'stop%':>5} | {'n':>4} {'PF':>6} {'R/tr':>8} {'tot%':>6} {'DD%':>5} {'p99':>5} {'tot/p99':>7}")
for nm, sa in rules.items():
    R_, p_, b_, s_, w_ = wtp(WIN & near, sa); m0 = b_ == 0; m1 = b_ == 1
    q = p_[m0]; q1 = p_[m1]; pp = p99(q); pp1 = p99(q1)
    print(f"  {nm:40s} {m0.sum():>4} {pf(q):6.3f} {q.mean():+8.4f} {R_[m0].mean():+8.4f} {R_[m0].sum():+6.1f} {q.sum():+6.2f} {dd(q):5.2f} {pp:6.2f} {q.sum()/pp:7.2f} {100*np.mean(w_[m0]==0):5.0f} | {m1.sum():>4} {pf(q1):6.3f} {R_[m1].mean():+8.4f} {q1.sum():+6.2f} {dd(q1):5.2f} {pp1:5.2f} {q1.sum()/pp1:7.2f}", flush=True)

line("1.3  THE EXTENSION FACTOR on the research signal bars -- Spearman matrix, conditional IC inside the gate, decile monotonicity")
S = lambda x: pd.Series(x)
def vwap_from(start):
    m = mod >= start; tp_ = (h + l + c) / 3; d = pd.DataFrame({"pv": np.where(m, tp_ * v, 0.0), "vv": np.where(m, v, 0.0), "s": day}); gg = d.groupby("s", sort=False)
    w = (gg["pv"].cumsum() / gg["vv"].cumsum().replace(0, np.nan)).to_numpy(); w[~m] = np.nan; return w
X = pd.DataFrame({"d_sp (single print above, ATR)": spa, "e13_48 (EMA13-EMA48)/ATR": g("ema.spread1348_atr"), "e200 (close-EMA200)/ATR": g("ema.d200_atr"),
                  "d_poc (close-prior POC)/ATR": g("vp.prior_poc_atr"), "d_vwap07 (close-VWAP from 07:00)/ATR": (c - vwap_from(420)) / atr,
                  "d_hi (close-prior high)/ATR": g("vp.prior_hi_atr"), "d_hvn_above (nearest HVN above, ATR)": g("vp.hvn_above_atr")})
fwd = np.full(n, np.nan); fwd[:-16] = (c[16:] - o[1:-15]) / atr[:-16]           # 15-bar forward return from the next open, in ATR
Xs = X[sig_res]; print("  Spearman among the extension variables (research signal bars, pairwise complete):"); print(Xs.corr(method="spearman").round(2).to_string())
print("\n  IC vs 15-bar forward return (ATR):  all signal bars | inside the gate | outside;  decile monotonicity = Spearman(decile index, decile mean fwd)")
for k in X.columns:
    x = X[k].to_numpy();
    def ic(m):
        mm = m & np.isfinite(x) & np.isfinite(fwd); return (spearmanr(x[mm], fwd[mm])[0], int(mm.sum())) if mm.sum() > 40 else (np.nan, int(mm.sum()))
    a, na_ = ic(sig_res); b, nb = ic(sig_res & near); d_, nd = ic(sig_res & ~near)
    mm = sig_res & np.isfinite(x) & np.isfinite(fwd); dec = pd.qcut(x[mm], 10, labels=False, duplicates="drop"); dm = pd.Series(fwd[mm]).groupby(dec).mean()
    mono = spearmanr(np.arange(len(dm)), dm.to_numpy())[0]
    print(f"  {k:40s} {a:+.3f} (n {na_:>4}) | {b:+.3f} (n {nb:>4}) | {d_:+.3f} (n {nd:>4})   deciles: low {dm.iloc[0]:+.3f} mid {dm.iloc[len(dm)//2]:+.3f} high {dm.iloc[-1]:+.3f}  mono {mono:+.2f}")

line("1.4  DROP-ONE EXTENDED -- the gate within terciles of each extension variable (research PF gated / ungated; locked in brackets)")
def walk(gate): return O._walk(o, h, l, c, atr, D["calm"], ENT, EXL, gate, D["d_ma"], D["chop"], D["psh_ok"], int(CUT), 3.19, 3.19, 2.3, 15, 0, 0.0, 0, 0.0, 0, V.COST, V.SLIP, int(D["last_bar"]))
for k in ("e13_48 (EMA13-EMA48)/ATR", "e200 (close-EMA200)/ATR", "d_poc (close-prior POC)/ATR", "d_vwap07 (close-VWAP from 07:00)/ATR"):
    x = X[k].to_numpy(); qs = np.nanquantile(x[sig_res], [1 / 3, 2 / 3])
    for lab, m in (("low", x <= qs[0]), ("mid", (x > qs[0]) & (x <= qs[1])), ("high", x > qs[1])):
        m = np.nan_to_num(m.astype(float)).astype(bool)
        Rg, pg, bg, sg = walk(WIN & m & near); Ru, pu, bu, su = walk(WIN & m & ~near)
        print(f"  {k[:24]:24s} {lab:4s} tercile: gated n {int((bg==0).sum()):>3} PF {pf(pg[bg==0]):5.3f} R {Rg[bg==0].mean():+.3f} | ungated n {int((bu==0).sum()):>3} PF {pf(pu[bu==0]):5.3f} R {Ru[bu==0].mean():+.3f}   [locked gated {pf(pg[bg==1]):5.3f} n {int((bg==1).sum()):>3} | ungated {pf(pu[bu==1]):5.3f} n {int((bu==1).sum()):>3}]")

line("1.5  THE DAY EFFECT WITHOUT THE DONCHIAN -- single-print days vs the rest, and a random entry inside the gate's own days")
first = pd.Series(np.arange(n)).groupby(day).apply(lambda s: s[mod[s] >= 420].min() if (mod[s] >= 420).any() else -1).to_numpy()
first = first[first >= 0]; cond_day = near[first]; dday = day[first]
def sess_ret(mods0, mods1):
    out = {}
    for d_, i0 in zip(dday, first):
        m = np.flatnonzero(day == d_); a = m[mod[m] >= mods0]; b = m[mod[m] < mods1]
        if len(a) and len(b): out[d_] = (c[b[-1]] - o[a[0]]) / atr[a[0]]
    return pd.Series(out)
for nm, r in (("07:00 open -> 11:00 close", sess_ret(420, 660)), ("09:30 open -> 16:00 close", sess_ret(570, 960))):
    cd = pd.Series(cond_day, index=dday).reindex(r.index).fillna(False).astype(bool)
    for blk, bn in ((0, "research"), (1, "locked")):
        inb = (r.index < day[CUT]) if blk == 0 else (r.index >= day[CUT]); a = r[inb & cd]; b = r[inb & ~cd]
        t, p = ttest_ind(a, b, equal_var=False)
        print(f"  {nm:26s} {bn:9s} single-print days n {len(a):>3} mean {a.mean():+.3f} ATR (share up {100*(a>0).mean():.0f}%) | other days n {len(b):>3} mean {b.mean():+.3f} ({100*(b>0).mean():.0f}%)   Welch t {t:+.2f} p {p:.3f}")
# interaction: random ENTRY at a random 07:00-11:00 bar inside the gate's active days, same geometry, same count -- does the breakout add within those days?
Rg, pg, bg, sg = walk(WIN & near)
for blk, bn in ((0, "research"), (1, "locked")):
    inb = (np.arange(n) < CUT) if blk == 0 else (np.arange(n) >= CUT); mg = bg == blk
    act = np.unique(day[sg[mg]]); pool = np.flatnonzero(WIN & inb & np.isin(day, act) & (np.arange(n) >= 1000)); k = int(mg.sum()); out = []
    for _ in range(300):
        bars = np.sort(rng.choice(pool, size=min(k * 2, len(pool)), replace=False))
        pc = O._walk_at(o, h, l, c, atr, D["calm"], EXL, bars, 3.19, 3.19, 2.3, 15, V.COST, V.SLIP, int(D["last_bar"])); pc = pc[np.isfinite(pc)]; out.append((pf(pc), pc.mean()))
    out = np.array(out); obs = pf(pg[mg]); obm = pg[mg].mean()
    print(f"  random entry inside the gate's {len(act)} active days, {bn:9s}: control PF median {np.nanmedian(out[:,0]):.3f} mean {np.nanmedian(out[:,1]):+.4f} | gated breakout PF {obs:.3f} mean {obm:+.4f}   p(PF) {np.nanmean(out[:,0] >= obs):.3f} p(mean) {np.nanmean(out[:,1] >= obm):.3f}")
