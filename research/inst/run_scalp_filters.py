"""Can any declared indicator or rule raise the 07:00-11:00 scalp's LOCKED profit factor by 25%?

The target is a locked-block number, so the locked block is never consulted to choose. Procedure:
a pool of conditions at the signal bar, each scored on RESEARCH against a same-selectivity random
filter (the control as a gate), Benjamini-Hochberg across the pool, survivors stacked on research
by marginal consensus, then ONE locked read of the base, each survivor and the stack. The pool is
drawn from what this branch has measured as helping a scalp (STUDY_SCALP_REQUIREMENTS: the clock,
participation, a volatility floor, MA200 distance, the prior RTH high, CHOP, the two bullish CVD
patterns) plus the momentum confirmations that are known to be the breakout restated, kept as
base-rate controls. Base: 15m, entries 07:00-11:00 NY, Donchian 7/8, 3.19 ATR stop, 2.3 ATR
target, 230-minute hold, no filters (research PF 1.18 / locked 1.13). Channels are 10/10: the Optuna
study printed 7/8 because its evaluator clips to CH_MIN=10 (corrected)."""
import os, sys, warnings, time
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56", "research/v64", "research/inst"):
    sys.path.insert(0, os.path.join(ROOT, p))
import v61core as V, v64opt as O, v53abs as A
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
def line(t): print("\n" + "=" * 126 + f"\n{t}\n" + "=" * 126, flush=True)
t0 = time.time()
D = O.build(15); n = D["n"]; CUT = D["cut"]; c, h, l, o, v = D["c"], D["h"], D["l"], D["o"], D["v"]; mod = D["mod"]
WIN = (mod >= 7 * 60) & (mod < 11 * 60)
BASE = dict(ent=10, exN=10, stop=3.19, tp=2.3, hold=15, adapt=0)      # 230 min = 15 bars on 15m
# NOTE: the Optuna study reported this finalist as "Donchian 7/8" -- its evaluator clips channel lengths to
# CH_MIN=10, so the cell that was actually measured is 10/10. Corrected here and in the study.
def walk(gate, stop=BASE["stop"], tp=BASE["tp"], hold=BASE["hold"], ent=BASE["ent"], exN=BASE["exN"]):
    return O._walk(o, h, l, c, D["atr"], D["calm"], D["ent_all"][ent - O.CH_MIN], D["exl_all"][exN - O.CH_MIN], gate, D["d_ma"], D["chop"], D["psh_ok"], int(CUT),
                   stop, stop, tp, hold, 0, 0.0, 0, 0.0, 0, V.COST, V.SLIP, int(D["last_bar"]))
def stats(pct, blk, sig, b):
    q = pct[blk == b]
    if len(q) < 3: return dict(n=len(q), pf=np.nan, tot=np.nan, sh=np.nan, win=np.nan, dd=np.nan)
    d = pd.Series(q).groupby(sig[blk == b] // 26).sum(); eq = np.cumsum(q)
    return dict(n=len(q), pf=q[q > 0].sum() / max(1e-9, -q[q <= 0].sum()), tot=q.sum(), win=100 * (q > 0).mean(),
                sh=np.sqrt(252) * d.mean() / d.std() if len(d) > 3 and d.std() > 0 else np.nan, dd=float(np.max(np.maximum.accumulate(eq) - eq)))
def fmt(s): return f"n {s['n']:>4} PF {s['pf']:6.3f} win {s['win']:5.1f}% total {s['tot']:+7.2f}% Sh {s['sh']:5.2f} DD {s['dd']:5.2f}%"

# ---------------- the conditions, all at the signal bar, all causal ----------------
S = lambda x: pd.Series(x)
ema = lambda x, k: S(x).ewm(span=k, adjust=False).mean().to_numpy()
ix = pd.DatetimeIndex(D["ix"]); sess = (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy()
# volume against its own time-of-day baseline over the prior 20 sessions (causal: shifted by one session per slot)
vdf = pd.DataFrame({"v": v, "mod": mod, "s": sess})
tod = vdf.groupby("mod")["v"].transform(lambda x: x.shift(1).rolling(20, min_periods=5).mean()).to_numpy()
vol_ratio = np.where(tod > 0, v / tod, np.nan)
atr = D["atr"]; atr_sma50 = S(atr).rolling(50).mean().to_numpy(); atr_sma250 = S(atr).rolling(250).mean().to_numpy()
rng_bar = (h - l) / atr
# session VWAP from 07:00 (the window's own anchor) and from the RTH open
def vwap_from(start_min):
    m = mod >= start_min; tp_ = (h + l + c) / 3; d = pd.DataFrame({"pv": np.where(m, tp_ * v, 0.0), "vv": np.where(m, v, 0.0), "s": sess}); g = d.groupby("s", sort=False)
    w = (g["pv"].cumsum() / g["vv"].cumsum().replace(0, np.nan)).to_numpy(); w[~m] = np.nan; return w
vw7 = vwap_from(7 * 60)
# prior session (previous NY day) close and the overnight gap
day_close = pd.Series(c).groupby(sess).last(); prev_close = day_close.shift(1).reindex(sess).to_numpy()
gap_atr = (o - prev_close) / atr
# indicators
def rsi(x, k=14):
    d = np.diff(x, prepend=x[0]); up = S(np.where(d > 0, d, 0)).ewm(alpha=1 / k, adjust=False).mean(); dn = S(np.where(d < 0, -d, 0)).ewm(alpha=1 / k, adjust=False).mean()
    return (100 - 100 / (1 + up / dn.replace(0, np.nan))).to_numpy()
rsi14 = rsi(c); macd_h = ema(c, 12) - ema(c, 26) - ema(ema(c, 12) - ema(c, 26), 9); e13, e48 = ema(c, 13), ema(c, 48)
def adx(k=14):
    up = np.diff(h, prepend=h[0]); dn = -np.diff(l, prepend=l[0]); pdm = np.where((up > dn) & (up > 0), up, 0.0); mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1)))); atrw = S(tr).ewm(alpha=1 / k, adjust=False).mean()
    pdi = 100 * S(pdm).ewm(alpha=1 / k, adjust=False).mean() / atrw; mdi = 100 * S(mdm).ewm(alpha=1 / k, adjust=False).mean() / atrw
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan); return S(dx).ewm(alpha=1 / k, adjust=False).mean().to_numpy(), pdi.to_numpy(), mdi.to_numpy()
adx14, pdi, mdi = adx()
er20 = np.abs(c - np.roll(c, 20)) / S(np.abs(np.diff(c, prepend=c[0]))).rolling(20).sum().to_numpy()
cvd_es = A.recent(D["pats"][3][0], 20); cvd_as = A.recent(D["pats"][3][1], 20); cvd_slope = np.gradient(D["cv"]) if "cv" in D else np.zeros(n)
cv = D["cv"]; cvd_up = cv > np.roll(cv, 8)
POOL = {
 # clock
 "clock: entries from 08:30 only": mod >= 8 * 60 + 30, "clock: entries from 09:30 only": mod >= 9 * 60 + 30, "clock: skip 09:30-10:00": ~((mod >= 570) & (mod < 600)),
 "clock: before 09:30 only": mod < 9 * 60 + 30,
 # participation
 "volume >= 1.2x time-of-day mean": vol_ratio >= 1.2, "volume >= 1.5x time-of-day mean": vol_ratio >= 1.5, "volume >= 2.0x time-of-day mean": vol_ratio >= 2.0, "volume < 1.0x time-of-day mean": vol_ratio < 1.0,
 # volatility
 "ATR >= 1.0x its 50-bar mean": atr >= atr_sma50, "ATR >= 1.2x its 50-bar mean": atr >= 1.2 * atr_sma50, "ATR >= 1.2x its 250-bar mean": atr >= 1.2 * atr_sma250, "ATR < 1.0x its 50-bar mean": atr < atr_sma50,
 "vol percentile <= 0.5 (calm)": D["calm"], "vol percentile > 0.5": ~D["calm"], "signal bar range >= 1.5 ATR": rng_bar >= 1.5, "signal bar range < 0.8 ATR": rng_bar < 0.8,
 # location
 "MA200 distance >= 1 ATR": D["d_ma"] >= 1.0, "MA200 distance >= 2 ATR": D["d_ma"] >= 2.0, "MA200 distance < 1 ATR": D["d_ma"] < 1.0, "close above prior RTH high": D["psh_ok"],
 "close above VWAP(07:00)": c > vw7, "close >= 1 ATR above VWAP(07:00)": (c - vw7) / atr >= 1.0, "gap up >= 0.5 ATR vs prior close": gap_atr >= 0.5, "gap down / flat (< 0 ATR)": gap_atr < 0,
 # regime
 "CHOP <= 40": D["chop"] <= 40, "CHOP <= 45": D["chop"] <= 45, "CHOP <= 50": D["chop"] <= 50, "ADX >= 20": adx14 >= 20, "ADX >= 25": adx14 >= 25, "ADX < 20": adx14 < 20, "ER(20) >= 0.3": er20 >= 0.3, "+DI > -DI": pdi > mdi,
 # order flow
 "CVD exhausted sellers (k3) within 20": cvd_es, "CVD absorbed selling (k3) within 20": cvd_as, "CVD rising over 8 bars": cvd_up,
 # confirmations known to be the trigger restated
 "RSI14 >= 55": rsi14 >= 55, "MACD hist > 0": macd_h > 0, "EMA13 > EMA48": e13 > e48,
}
# the signal bars the base fires on (pre-lock), inside the window
sigbar = np.zeros(n, bool); sigbar[1000:D["last_bar"]] = (h[1000:D["last_bar"]] > D["ent_all"][BASE["ent"] - O.CH_MIN][1000:D["last_bar"]]) & WIN[1000:D["last_bar"]]
sig_res = sigbar & (np.arange(n) < CUT)
line("A. BASE RATES on the base's own signal bars (research) -- pass rate, lift vs window bars, and the base itself")
R0, pct0, blk0, sg0 = walk(WIN); b_res, b_lock = stats(pct0, blk0, sg0, 0), stats(pct0, blk0, sg0, 1)
print("  base research: " + fmt(b_res) + "\n  base locked:   " + fmt(b_lock))
print(f"  signal bars (research, pre-lock): {int(sig_res.sum()):,}")
rows = []
for nm, m in POOL.items():
    m = np.nan_to_num(m.astype(float), nan=0.0).astype(bool)
    ps = m[sig_res].mean(); pa = m[WIN & (np.arange(n) < CUT) & (np.arange(n) >= 1000)].mean()
    rows.append(dict(cond=nm, pass_sig=100 * ps, pass_all=100 * pa, lift=ps / max(pa, 1e-9)))
BR = pd.DataFrame(rows); print(BR.to_string(index=False, float_format=lambda x: f"{x:6.1f}"))
line("B. EACH CONDITION ON RESEARCH, against a random filter of the SAME selectivity (250 draws); locked NOT read")
rng = np.random.default_rng(11); res_sig_idx = np.flatnonzero(sig_res)
def ctl(keep, ndraw=250):
    out = []
    for _ in range(ndraw):
        g = np.zeros(n, bool); g[rng.choice(res_sig_idx, size=min(keep, len(res_sig_idx)), replace=False)] = True
        R, pct, blk, sg = walk(g); s = stats(pct, blk, sg, 0); out.append((s["pf"], s["sh"]))
    return np.array(out)
res = []
print(f"  {'condition':40s} {'keep%':>5} {'n':>4} {'PF':>6} {'dPF%':>6} {'Sh':>5} {'total':>7} | {'ctl PF':>6} {'p(PF)':>6} {'p(Sh)':>6}")
for nm, m in POOL.items():
    m = np.nan_to_num(m.astype(float), nan=0.0).astype(bool); g = WIN & m
    R, pct, blk, sg = walk(g); s = stats(pct, blk, sg, 0); keep = int((m & sig_res).sum())
    if s["n"] < 40: print(f"  {nm:40s} {100*keep/len(res_sig_idx):5.0f} {s['n']:>4}  (too few)"); continue
    cc = ctl(keep); pPF = np.nanmean(cc[:, 0] >= s["pf"]); pSh = np.nanmean(cc[:, 1] >= s["sh"])
    res.append(dict(cond=nm, keep=100 * keep / len(res_sig_idx), n=s["n"], pf=s["pf"], dpf=100 * (s["pf"] / b_res["pf"] - 1), sh=s["sh"], tot=s["tot"], ctl_pf=np.nanmedian(cc[:, 0]), p_pf=pPF, p_sh=pSh))
    print(f"  {nm:40s} {100*keep/len(res_sig_idx):5.0f} {s['n']:>4} {s['pf']:6.3f} {100*(s['pf']/b_res['pf']-1):+6.1f} {s['sh']:5.2f} {s['tot']:+7.2f} | {np.nanmedian(cc[:,0]):6.3f} {pPF:6.3f} {pSh:6.3f}", flush=True)
RS = pd.DataFrame(res); RS.to_parquet("results/inst/scalp_filters.parquet")
# BH across the pool on p(PF)
q = 0.10; ps = RS.p_pf.to_numpy(); order = np.argsort(ps); m = len(ps); thr = q * (np.arange(1, m + 1)) / m
passed = np.zeros(m, bool); k = np.flatnonzero(ps[order] <= thr)
if len(k): passed[order[:k.max() + 1]] = True
RS["bh"] = passed
surv = RS[(RS.bh) & (RS.n >= 100) & (RS.dpf >= 10)].sort_values("p_pf")
line(f"C. SURVIVORS -- BH at q=0.10 over {m} conditions ({int(passed.sum())} pass; {(RS.p_pf<=0.05).sum()} at p<=0.05 vs {0.05*m:.1f} expected), AND >=100 research trades AND >= +10% PF")
print(surv[["cond", "keep", "n", "pf", "dpf", "sh", "tot", "ctl_pf", "p_pf", "p_sh"]].to_string(index=False, float_format=lambda x: f"{x:6.3f}") if len(surv) else "  none")
line("D. STACKS on research -- pairs of survivors, then the marginal consensus; each against its own control")
masks = {nm: np.nan_to_num(POOL[nm].astype(float), nan=0.0).astype(bool) for nm in surv.cond}
stack_rows = []
names = list(masks)
for i in range(len(names)):
    for j in range(i + 1, len(names)):
        g = WIN & masks[names[i]] & masks[names[j]]; R, pct, blk, sg = walk(g); s = stats(pct, blk, sg, 0); keep = int((masks[names[i]] & masks[names[j]] & sig_res).sum())
        if s["n"] < 60: continue
        cc = ctl(keep, 150); stack_rows.append(dict(a=names[i], b=names[j], n=s["n"], pf=s["pf"], sh=s["sh"], tot=s["tot"], p_pf=np.nanmean(cc[:, 0] >= s["pf"])))
ST = pd.DataFrame(stack_rows)
if len(ST): print(ST.sort_values("pf", ascending=False).head(12).to_string(index=False, float_format=lambda x: f"{x:6.3f}"))
else: print("  no pair with >= 60 research trades")
# the marginal consensus: every survivor ANDed, if it keeps >= 60 trades; else the best pair by research PF
final_name, final_mask = None, None
if len(names) >= 2:
    g_all = np.ones(n, bool)
    for nm in names: g_all &= masks[nm]
    R, pct, blk, sg = walk(WIN & g_all); s_all = stats(pct, blk, sg, 0)
    if s_all["n"] >= 60: final_name, final_mask = " AND ".join(names), g_all
    elif len(ST): b = ST.sort_values("pf", ascending=False).iloc[0]; final_name, final_mask = f"{b.a} AND {b.b}", masks[b.a] & masks[b.b]
elif len(names) == 1: final_name, final_mask = names[0], masks[names[0]]
line("E. THE ONE LOCKED READ -- base, each survivor, and the stack chosen on research; the target is +25% locked PF")
print("  base                          locked: " + fmt(b_lock))
rng2 = np.random.default_rng(23); lock_sig_idx = np.flatnonzero(sigbar & (np.arange(n) >= CUT))
def ctl_lock(keep, ndraw=250):
    out = []
    for _ in range(ndraw):
        g = np.zeros(n, bool); g[rng2.choice(lock_sig_idx, size=min(keep, len(lock_sig_idx)), replace=False)] = True
        R, pct, blk, sg = walk(g); out.append(stats(pct, blk, sg, 1)["pf"])
    return np.array(out)
for nm in names + ([final_name] if final_name and final_name not in names else []):
    mk = masks[nm] if nm in masks else final_mask
    R, pct, blk, sg = walk(WIN & mk); s = stats(pct, blk, sg, 1); keep = int((mk & sigbar & (np.arange(n) >= CUT)).sum())
    cc = ctl_lock(keep); tag = "STACK " if nm == final_name and nm not in masks else ""
    print(f"  {tag}{nm[:60]:60s} locked: {fmt(s)}   dPF {100*(s['pf']/b_lock['pf']-1):+6.1f}%   random filter median PF {np.nanmedian(cc):.3f} p {np.nanmean(cc >= s['pf']):.3f}")
print(f"\n  total runtime {time.time()-t0:.0f}s")
