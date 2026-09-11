"""Volume profile + TPO + EMA200 + EMA 13/48 + ATR variables, as feature engineering for the
07:00-11:00 Donchian scalp -- forecasting the ENTRY (which breakouts to take), the TAKE PROFIT
(a profile level instead of a fixed ATR multiple) and the STOP (an ATR variable instead of a fixed
multiple). Base: NQ 15m, Donchian 10/10, 3.19N stop, 2.3 ATR target, 230-minute hold, entries
07:00-11:00 New York, no filters (research PF 1.164 / locked 1.110, STUDY_SCALP_FILTERS).

Discipline, as everywhere on this branch: every feature causal and truncation-audited
(`vp_tpo.truncation_audit`, `volprofile.leakage_check`); base rates on the trigger's OWN bars before
any P&L; each entry condition against a random filter of the SAME selectivity; each level target
against a random target at the SAME distance distribution; the stop axis reported in %/trade, R
AND total-at-one-unit with drawdown (STUDY_V63: three units, three answers); everything chosen on
RESEARCH, then ONE locked read of the declared finalists with the count of things looked at.

Sections:  A base rates    B feature IC vs R and vs fixed-horizon MFE, with a shuffled null
           C entry conditions vs same-selectivity control, BH   D take-profit rules
           E stop variables   F the locked read
"""
import os, sys, warnings, time
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56", "research/v64", "research/inst"):
    sys.path.insert(0, os.path.join(ROOT, p))
import v61core as V, v64opt as O, vp_tpo as T
from scipy.stats import spearmanr
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
def line(t): print("\n" + "=" * 126 + f"\n{t}\n" + "=" * 126, flush=True)
t0 = time.time()
D = O.build(15); n = D["n"]; CUT = D["cut"]; c, h, l, o, v, atr = D["c"], D["h"], D["l"], D["o"], D["v"], D["atr"]; mod = D["mod"]
WIN = (mod >= 7 * 60) & (mod < 11 * 60)
BASE = dict(ent=10, exN=10, stop=3.19, tp=2.3, hold=15)
ENT = D["ent_all"][BASE["ent"] - O.CH_MIN]; EXL = D["exl_all"][BASE["exN"] - O.CH_MIN]
F, L = T.build(D)
FEATS = [k for k in F.columns]
print(f"features {len(FEATS)} (vp {sum(k.startswith('vp.') for k in FEATS)}, tpo {sum(k.startswith('tpo.') for k in FEATS)}, "
      f"ema {sum(k.startswith('ema.') for k in FEATS)}, atr {sum(k.startswith('atr.') for k in FEATS)})   build {time.time()-t0:.0f}s")

def walk(gate, stop=BASE["stop"], tp=BASE["tp"], hold=BASE["hold"]):
    return O._walk(o, h, l, c, atr, D["calm"], ENT, EXL, gate, D["d_ma"], D["chop"], D["psh_ok"], int(CUT),
                   stop, stop, tp, hold, 0, 0.0, 0, 0.0, 0, V.COST, V.SLIP, int(D["last_bar"]))
def walk_tp(gate, stop_arr, tgt_px, hold=BASE["hold"]):
    return T.walk_tp(o, h, l, c, atr, ENT, EXL, gate, int(CUT), stop_arr, tgt_px, hold, V.COST, V.SLIP, int(D["last_bar"]))
def stats(pct, blk, sig, b, R=None):
    q = pct[blk == b]
    if len(q) < 3: return dict(n=len(q), pf=np.nan, tot=np.nan, sh=np.nan, win=np.nan, dd=np.nan, r=np.nan)
    d = pd.Series(q).groupby(sig[blk == b] // 26).sum(); eq = np.cumsum(q)
    return dict(n=len(q), pf=q[q > 0].sum() / max(1e-9, -q[q <= 0].sum()), tot=q.sum(), win=100 * (q > 0).mean(),
                sh=np.sqrt(252) * d.mean() / d.std() if len(d) > 3 and d.std() > 0 else np.nan, dd=float(np.max(np.maximum.accumulate(eq) - eq)),
                r=np.nan if R is None else float(np.mean(R[blk == b])))
def fmt(s): return f"n {s['n']:>4} PF {s['pf']:6.3f} win {s['win']:5.1f}% total {s['tot']:+7.2f}% Sh {s['sh']:5.2f} DD {s['dd']:5.2f}%"

# ---------------- parity: walk_tp reproduces O._walk at the base ----------------
NXT = np.append(o[1:], np.nan) + V.SLIP                     # the fill price the engine uses: next open plus slippage
stop_fixed = np.full(n, BASE["stop"]); tgt_fixed = NXT + BASE["tp"] * atr
R0, pct0, blk0, sg0 = walk(WIN); R1, pct1, blk1, sg1, why1 = walk_tp(WIN, stop_fixed, tgt_fixed)
assert len(pct0) == len(pct1) and np.allclose(pct0, pct1) and np.array_equal(sg0, sg1), "walk_tp parity failed"
b_res, b_lock = stats(pct0, blk0, sg0, 0, R0), stats(pct0, blk0, sg0, 1, R0)
sigbar = np.zeros(n, bool); sigbar[1000:D["last_bar"]] = (h[1000:D["last_bar"]] > ENT[1000:D["last_bar"]]) & WIN[1000:D["last_bar"]]
sig_res = sigbar & (np.arange(n) < CUT); res_sig_idx = np.flatnonzero(sig_res)
line("A. THE BASE, and BASE RATES of the declared conditions on the base's own signal bars (research)")
print("  walk_tp parity with O._walk: exact (" + str(len(pct0)) + " trades)")
print("  base research: " + fmt(b_res) + f"  R {b_res['r']:+.4f}\n  base locked:   " + fmt(b_lock) + f"  R {b_lock['r']:+.4f}")
print(f"  signal bars research (pre-lock): {len(res_sig_idx):,}   exit mix research: stop {100*np.mean(why1[blk1==0]==0):.0f}% target {100*np.mean(why1[blk1==0]==1):.0f}% hold {100*np.mean(why1[blk1==0]==2):.0f}%")

g = lambda k: F[k].to_numpy()
# ---------------- the declared entry conditions ----------------
POOL = {
 # EMA200 as support / resistance
 "EMA200: close above": g("ema.d200_atr") > 0, "EMA200: close below (resistance side)": g("ema.d200_atr") < 0,
 "EMA200: above and within 1 ATR (support)": (g("ema.d200_atr") > 0) & (g("ema.d200_atr") <= 1.0),
 "EMA200: >= 1 ATR above (floor)": g("ema.d200_atr") >= 1.0, "EMA200: >= 2 ATR above (floor)": g("ema.d200_atr") >= 2.0,
 "EMA200: touched within 5 bars": g("ema.touch200_5") > 0, "EMA200: rising (10-bar slope > 0)": g("ema.slope200_atr") > 0,
 # EMA 13/48 as momentum
 "EMA13 > EMA48 (state)": g("ema.x1348_state") > 0, "EMA13 crossed above EMA48 <= 5 bars ago": g("ema.bars_since_x1348") <= 5,
 "EMA13 crossed above EMA48 <= 20 bars ago": g("ema.bars_since_x1348") <= 20, "EMA13-48 spread >= 0.5 ATR": g("ema.spread1348_atr") >= 0.5,
 "EMA13-48 spread rising (5 bars)": g("ema.spread_slope_atr") > 0, "EMA13 < EMA48 (counter-state)": g("ema.x1348_state") == 0,
 # volume profile (prior session)
 "VP: close above prior VAH": g("vp.prior_vah_atr") > 0, "VP: close inside prior value area": g("vp.pos_in_prior_va") == 0,
 "VP: close below prior VAL": g("vp.prior_val_atr") < 0, "VP: close above prior POC": g("vp.prior_poc_atr") > 0,
 "VP: prior VA narrow (< 3 ATR)": g("vp.prior_va_width_atr") < 3.0, "VP: prior VA wide (>= 3 ATR)": g("vp.prior_va_width_atr") >= 3.0,
 "VP: HVN within 1 ATR above (resistance)": g("vp.hvn_above_atr") <= 1.0, "VP: no HVN within 2 ATR above (room)": ~(g("vp.hvn_above_atr") <= 2.0),
 "VP: LVN within 1 ATR above": g("vp.lvn_above_atr") <= 1.0, "VP: naked POC within 3 ATR above": g("vp.naked_poc_above_atr") <= 3.0,
 "VP: prior session poor high": g("vp.prior_poor_hi") > 0, "VP: close above prior session high": g("vp.prior_hi_atr") > 0,
 # volume profile (developing)
 "VP: close above developing VAH": g("vp.dev_vah_atr") > 0, "VP: close above developing POC": g("vp.dev_poc_atr") > 0,
 "VP: developing VA narrow (< 1.5 ATR)": g("vp.dev_va_width_atr") < 1.5,
 # TPO
 "TPO: close above prior VAH": g("tpo.prior_vah_atr") > 0, "TPO: prior profile skewed low (POC in lower half)": g("tpo.prior_skew") < 0.5,
 "TPO: prior single print within 3 ATR above": g("tpo.prior_single_above_atr") <= 3.0, "TPO: no prior single print within 3 ATR above": ~(g("tpo.prior_single_above_atr") <= 3.0),
 "TPO: close above IB high": g("tpo.above_ib") > 0, "TPO: IB range < 1.5 ATR": g("tpo.ib_range_atr") < 1.5, "TPO: IB range >= 1.5 ATR": g("tpo.ib_range_atr") >= 1.5,
 "TPO: single print within 2 ATR below (support)": g("tpo.single_below_atr") <= 2.0, "TPO: close above developing VAH": g("tpo.dev_vah_atr") > 0,
 # ATR variables as entry regime
 "ATR >= 1.0x its 50-bar mean": g("atr.ratio50") >= 1.0, "ATR >= 1.2x its 250-bar mean": g("atr.ratio250") >= 1.2, "ATR < 1.0x its 50-bar mean": g("atr.ratio50") < 1.0,
 "vol percentile <= 0.5 (calm)": g("atr.vol_pct250") <= 0.5, "signal bar range >= 1.5 ATR": g("atr.range_atr") >= 1.5, "signal bar range < 0.8 ATR": g("atr.range_atr") < 0.8,
}
POOL = {k: np.nan_to_num(m.astype(float), nan=0.0).astype(bool) for k, m in POOL.items()}
elig = WIN & (np.arange(n) < CUT) & (np.arange(n) >= 1000)
rows = []
for nm, m in POOL.items():
    ps = m[sig_res].mean(); pa = m[elig].mean(); rows.append(dict(cond=nm, pass_sig=100 * ps, pass_win=100 * pa, lift=ps / max(pa, 1e-9)))
BR = pd.DataFrame(rows); print(BR.to_string(index=False, float_format=lambda x: f"{x:6.2f}"))
print("  (a pass rate near 100% on the signal bars is the trigger restated; a lift near 1 is a random filter)")

# ---------------- B. feature IC on research trades: vs realised R and vs fixed-horizon MFE ----------------
line("B. FEATURE IC on the base's RESEARCH trades -- Spearman vs realised R and vs 15-bar MFE/MAE (ATR), with a shuffled null (200 draws)")
res_tr = sg0[blk0 == 0]; Rr = R0[blk0 == 0]
def excursion(sigs, hold=BASE["hold"]):
    mfe = np.full(len(sigs), np.nan); mae = np.full(len(sigs), np.nan)
    for z, i in enumerate(sigs):
        a = i + 1; e = min(a + hold, n - 1); px = o[a]
        mfe[z] = (h[a:e + 1].max() - px) / atr[i]; mae[z] = (px - l[a:e + 1].min()) / atr[i]
    return mfe, mae
mfe, mae = excursion(res_tr)
rng = np.random.default_rng(3); nulls = []
for _ in range(200):
    perm = rng.permutation(len(Rr)); nulls.append(spearmanr(F["vp.prior_poc_atr"].to_numpy()[res_tr], Rr[perm], nan_policy="omit")[0])
null_sd = np.nanstd(nulls)
ic = []
for k in FEATS:
    x = F[k].to_numpy()[res_tr]; okm = np.isfinite(x)
    if okm.sum() < 60 or np.nanstd(x) == 0: continue
    r1 = spearmanr(x[okm], Rr[okm])[0]; r2 = spearmanr(x[okm], mfe[okm])[0]; r3 = spearmanr(x[okm], mae[okm])[0]
    ic.append(dict(feature=k, n=int(okm.sum()), ic_R=r1, ic_MFE=r2, ic_MAE=r3, z=r1 / (null_sd * np.sqrt(len(Rr) / okm.sum()))))
IC = pd.DataFrame(ic).sort_values("ic_R", key=np.abs, ascending=False)
print(f"  research trades {len(Rr)}   shuffled-null sd of the IC {null_sd:.4f}   |z|>=2 needs |IC| >= {2*null_sd:.3f};  BH over {len(IC)} features")
from scipy.stats import norm
IC["p"] = 2 * (1 - norm.cdf(np.abs(IC.z))); ps = IC.p.to_numpy(); order = np.argsort(ps); thr = 0.10 * np.arange(1, len(ps) + 1) / len(ps)
kk = np.flatnonzero(ps[order] <= thr); IC["bh"] = False
if len(kk): IC.iloc[order[:kk.max() + 1], IC.columns.get_loc("bh")] = True
print(IC.to_string(index=False, float_format=lambda x: f"{x:7.3f}"))
print(f"  features passing BH q=0.10 on IC vs R: {int(IC.bh.sum())} of {len(IC)}   (|IC|>=0.1: {int((IC.ic_R.abs()>=0.1).sum())})")
print("  MFE and MAE move together (STUDY_V44): corr(ic_MFE, ic_MAE) across features = %.3f" % np.corrcoef(IC.ic_MFE, IC.ic_MAE)[0, 1])

# ---------------- C. each condition vs a same-selectivity random filter on research ----------------
line("C. EACH ENTRY CONDITION ON RESEARCH against a random filter of the SAME selectivity (250 draws); locked NOT read")
rngc = np.random.default_rng(11)
def ctl(keep, ndraw=250, b=0, pool=None):
    pool = res_sig_idx if pool is None else pool; out = []
    for _ in range(ndraw):
        gg = np.zeros(n, bool); gg[rngc.choice(pool, size=min(keep, len(pool)), replace=False)] = True
        R_, pct, blk, sg = walk(gg); s = stats(pct, blk, sg, b); out.append((s["pf"], s["sh"], s["tot"]))
    return np.array(out)
res = []
print(f"  {'condition':48s} {'keep%':>5} {'n':>4} {'PF':>6} {'dPF%':>6} {'Sh':>5} {'total':>7} | {'ctl PF':>6} {'p(PF)':>6} {'p(Sh)':>6}")
for nm, m in POOL.items():
    gg = WIN & m; R_, pct, blk, sg = walk(gg); s = stats(pct, blk, sg, 0); keep = int((m & sig_res).sum())
    if s["n"] < 40: print(f"  {nm:48s} {100*keep/len(res_sig_idx):5.0f} {s['n']:>4}  (too few)"); continue
    cc = ctl(keep); pPF = np.nanmean(cc[:, 0] >= s["pf"]); pSh = np.nanmean(cc[:, 1] >= s["sh"])
    res.append(dict(cond=nm, keep=100 * keep / len(res_sig_idx), n=s["n"], pf=s["pf"], dpf=100 * (s["pf"] / b_res["pf"] - 1), sh=s["sh"], tot=s["tot"], ctl_pf=np.nanmedian(cc[:, 0]), p_pf=pPF, p_sh=pSh))
    print(f"  {nm:48s} {100*keep/len(res_sig_idx):5.0f} {s['n']:>4} {s['pf']:6.3f} {100*(s['pf']/b_res['pf']-1):+6.1f} {s['sh']:5.2f} {s['tot']:+7.2f} | {np.nanmedian(cc[:,0]):6.3f} {pPF:6.3f} {pSh:6.3f}", flush=True)
RS = pd.DataFrame(res); os.makedirs("results/inst", exist_ok=True); RS.to_parquet("results/inst/vp_scalp_conditions.parquet")
ps = RS.p_pf.to_numpy(); order = np.argsort(ps); m_ = len(ps); thr = 0.10 * np.arange(1, m_ + 1) / m_
passed = np.zeros(m_, bool); kk = np.flatnonzero(ps[order] <= thr)
if len(kk): passed[order[:kk.max() + 1]] = True
RS["bh"] = passed
surv = RS[(RS.bh) & (RS.n >= 100) & (RS.dpf >= 10)].sort_values("p_pf")
print(f"\n  BH q=0.10 over {m_} conditions: {int(passed.sum())} pass;  {(RS.p_pf<=0.05).sum()} at p<=0.05 against {0.05*m_:.1f} expected by chance")
print("  survivors (BH AND >= 100 research trades AND >= +10% PF):")
print(surv[["cond", "keep", "n", "pf", "dpf", "sh", "tot", "ctl_pf", "p_pf", "p_sh"]].to_string(index=False, float_format=lambda x: f"{x:6.3f}") if len(surv) else "  none")
# family marginals: the mean dPF and mean p across each family, so the reader sees the FAMILY and not its best cell
RS["family"] = RS.cond.str.split(":").str[0].str.replace("EMA13.*", "EMA13/48", regex=True).str.replace("EMA13-48.*", "EMA13/48", regex=True).str.replace("ATR.*|vol percentile.*|signal bar.*", "ATR", regex=True)
print("\n  by family (mean over its cells):"); print(RS.groupby("family").agg(cells=("cond", "size"), dPF=("dpf", "mean"), p_pf=("p_pf", "mean"), beat_ctl=("p_pf", lambda x: 100 * (x <= 0.05).mean())).to_string(float_format=lambda x: f"{x:6.2f}"))

# ---------------- D. take-profit rules: fixed ATR ladder vs profile LEVELS ----------------
line("D. TAKE PROFIT on research -- a fixed ATR ladder against PROFILE LEVELS as the target (same entries, same stop); each level vs a random target at the SAME distance distribution (200 draws)")
def tp_from_level(level, fallback=BASE["tp"], min_atr=0.5, cap_atr=None):
    """target price per signal bar = the level if it sits at least `min_atr` above the next open, else the fallback fixed target (NaN fallback = no target)."""
    t = np.full(n, np.nan); nxt = NXT
    fb = nxt + fallback * atr if fallback is not None and fallback > 0 else np.full(n, np.nan)
    usable = np.isfinite(level) & ((level - nxt) / atr >= min_atr)
    if cap_atr is not None: usable &= ((level - nxt) / atr <= cap_atr)
    t[:] = fb; t[usable] = level[usable]; return t, usable
LEVELS = {"prior VP VAH": L["vp_prior_vah"], "nearest prior HVN above": L["vp_hvn_above"], "nearest naked POC above": L["vp_naked_above"],
          "prior TPO VAH": L["pr_vah"], "prior TPO POC": L["pr_poc"], "prior TPO single print above": L["pr_spa"],
          "developing TPO VAH": L["tp_vah"], "developing TPO single print above": L["tp_spa"], "IB high": L["ib_hi"]}
print(f"  {'target rule':52s} {'n':>4} {'PF':>6} {'win':>5} {'total':>7} {'R':>7} {'Sh':>5} {'DD':>5} | {'tgt%':>4} {'medD':>5} | {'rnd PF':>6} {'p(PF)':>6} {'p(tot)':>6}")
tp_rows = []
def tprow(nm, tgt, stop_arr=stop_fixed, usable=None, control=True, hold=BASE["hold"]):
    R_, pct, blk, sg, why = walk_tp(WIN, stop_arr, tgt, hold); s = stats(pct, blk, sg, 0, R_)
    hit = 100 * np.mean(why[blk == 0] == 1)
    d = ((tgt - NXT) / atr)[sg[blk == 0]]; medd = np.nanmedian(d[np.isfinite(d) & (d < 1e6)])
    r = dict(rule=nm, n=s["n"], pf=s["pf"], win=s["win"], tot=s["tot"], R=s["r"], sh=s["sh"], dd=s["dd"], tgt_pct=hit, med_d=medd)
    if control and usable is not None and usable[sg[blk == 0]].sum() >= 30:
        # null: the same trades, a target drawn from the SAME distance distribution but assigned at random across the signal bars
        dd_ = ((tgt - NXT) / atr); pool = dd_[usable & sig_res]; pool = pool[np.isfinite(pool)]
        out = []
        for _ in range(200):
            t2 = tgt.copy(); u = np.flatnonzero(usable); t2[u] = NXT[u] + rng.choice(pool, size=len(u)) * atr[u]
            R2, p2, b2, s2, w2 = walk_tp(WIN, stop_arr, t2, hold); ss = stats(p2, b2, s2, 0); out.append((ss["pf"], ss["tot"]))
        out = np.array(out); r.update(rnd_pf=np.nanmedian(out[:, 0]), p_pf=np.nanmean(out[:, 0] >= s["pf"]), p_tot=np.nanmean(out[:, 1] >= s["tot"]))
    tp_rows.append(r)
    print(f"  {nm:52s} {s['n']:>4} {s['pf']:6.3f} {s['win']:5.1f} {s['tot']:+7.2f} {s['r']:+7.4f} {s['sh']:5.2f} {s['dd']:5.2f} | {hit:4.0f} {medd:5.2f} | "
          + (f"{r['rnd_pf']:6.3f} {r['p_pf']:6.3f} {r['p_tot']:6.3f}" if "p_pf" in r else "     -      -      -"), flush=True)
for tp in (1.0, 1.5, 2.0, 2.3, 3.0, 4.0, 6.0):
    t_ = NXT + tp * atr; tprow(f"fixed {tp:.1f} ATR", t_, control=False)
tprow("no target (stop / channel / hold only)", np.full(n, np.nan), control=False)
for nm, lv in LEVELS.items():
    t_, u = tp_from_level(lv); tprow(f"{nm} (else 2.3 ATR)", t_, usable=u)
    t_, u = tp_from_level(lv, fallback=None); tprow(f"{nm} (else no target)", t_, usable=u)
    t_, u = tp_from_level(lv, cap_atr=4.0); tprow(f"{nm} capped 4 ATR (else 2.3)", t_, usable=u)
# nearest-of-several: the closest profile level above, whichever kind
stack = np.nanmin(np.vstack([L["vp_prior_vah"], L["vp_hvn_above"], L["pr_vah"], L["pr_spa"]]), axis=0)
t_, u = tp_from_level(stack); tprow("nearest of {VP VAH, HVN, TPO VAH, single print} (else 2.3)", t_, usable=u)
# a target that is a level only when the level is NEAR (a partial profile "magnet"): 0.5-2.0 ATR
t_, u = tp_from_level(stack, cap_atr=2.0); tprow("nearest level if within 2 ATR (else 2.3)", t_, usable=u)
TP = pd.DataFrame(tp_rows); TP.to_parquet("results/inst/vp_scalp_tp.parquet")

# ---------------- E. stop variables ----------------
line("E. STOP on research -- fixed multiples, an adaptive-vol stop, ATR-ratio and range-scaled stops, and STRUCTURAL stops (profile levels); three units + drawdown")
print(f"  {'stop rule':56s} {'n':>4} {'PF':>6} {'win':>5} {'%/trade':>8} {'R/trade':>8} {'total%':>7} {'DD%':>6} {'ret/DD':>6} {'stop%':>5} {'medRisk':>7}")
st_rows = []
def strow(nm, stop_arr, tgt=tgt_fixed):
    R_, pct, blk, sg, why = walk_tp(WIN, stop_arr, tgt); s = stats(pct, blk, sg, 0, R_)
    st = 100 * np.mean(why[blk == 0] == 0); risk = np.nanmedian(stop_arr[sg[blk == 0]])
    st_rows.append(dict(rule=nm, n=s["n"], pf=s["pf"], win=s["win"], pct=s["tot"] / max(s["n"], 1), R=s["r"], tot=s["tot"], dd=s["dd"], retdd=s["tot"] / max(s["dd"], 1e-9), stop_pct=st, med_risk=risk))
    print(f"  {nm:56s} {s['n']:>4} {s['pf']:6.3f} {s['win']:5.1f} {s['tot']/max(s['n'],1):+8.4f} {s['r']:+8.4f} {s['tot']:+7.2f} {s['dd']:6.2f} {s['tot']/max(s['dd'],1e-9):6.2f} {st:5.0f} {risk:7.2f}", flush=True)
for k in (1.0, 1.5, 2.0, 2.5, 3.0, 3.19, 4.0, 6.0): strow(f"fixed {k:.2f} ATR", np.full(n, k))
vp_ = g("atr.vol_pct250"); r50 = g("atr.ratio50"); rng_ = g("atr.range_atr")
for wide, tight in ((3.19, 2.0), (4.0, 2.5), (2.5, 1.5)): strow(f"adaptive: {wide} if vol pct <= 0.5 else {tight} (V22 direction)", np.where(vp_ <= 0.5, wide, tight))
for wide, tight in ((3.19, 2.0), (2.5, 1.5)): strow(f"adaptive INVERTED: {tight} if vol pct <= 0.5 else {wide}", np.where(vp_ <= 0.5, tight, wide))
for k in (2.0, 3.19): strow(f"{k} ATR x (ATR/ATR50) -- wider when ATR is expanding", np.clip(k * r50, 0.5, 8.0))
for k in (2.0, 3.19): strow(f"{k} ATR / (ATR/ATR50) -- wider when ATR is contracting", np.clip(k / np.where(r50 > 0, r50, np.nan), 0.5, 8.0))
for k in (1.0, 1.5, 2.0): strow(f"{k} x signal-bar range (floor 1 ATR, cap 6)", np.clip(k * rng_, 1.0, 6.0))
# structural: below a profile level, capped to [1, 6] ATR; fallback the fixed 3.19
def struct_stop(level, pad=0.25, fb=3.19, lo=1.0, hi=6.0):
    d = (NXT - level) / atr + pad
    return np.where(np.isfinite(level) & (d >= lo) & (d <= hi), d, fb)
strow("below prior VP VAL + 0.25 ATR (fallback 3.19, [1,6])", struct_stop(c - g("vp.prior_val_atr") * atr))
strow("below prior VP POC + 0.25 ATR", struct_stop(c - g("vp.prior_poc_atr") * atr))
strow("below developing VP VAL + 0.25 ATR", struct_stop(c - g("vp.dev_val_atr") * atr))
strow("below TPO IB low + 0.25 ATR", struct_stop(c - g("tpo.ib_lo_atr") * atr))
strow("below nearest HVN below + 0.25 ATR", struct_stop(c - g("vp.hvn_below_atr") * atr))
strow("below EMA200 + 0.25 ATR", struct_stop(L["e200"]))
strow("below EMA48 + 0.25 ATR", struct_stop(L["e48"]))
ST = pd.DataFrame(st_rows); ST.to_parquet("results/inst/vp_scalp_stops.parquet")
print("\n  marginal read: fixed ladder %/trade " + " ".join(f"{r.med_risk:.2f}:{r.pct:+.4f}" for r in ST.itertuples() if r.rule.startswith("fixed")))
print("               fixed ladder ret/DD  " + " ".join(f"{r.med_risk:.2f}:{r.retdd:.2f}" for r in ST.itertuples() if r.rule.startswith("fixed")))

# ---------------- F. the ONE locked read ----------------
line("F. THE ONE LOCKED READ -- base, every research survivor (entry / TP / stop), each against its own locked null; multiplicity stated")
looked = len(POOL) + len(TP) + len(ST) + len(IC)
print(f"  things looked at on research: {len(POOL)} entry conditions + {len(TP)} target rules + {len(ST)} stop rules + {len(IC)} feature ICs = {looked}")
print("  base locked: " + fmt(b_lock) + f"  R {b_lock['r']:+.4f}")
lock_sig_idx = np.flatnonzero(sigbar & (np.arange(n) >= CUT)); rng2 = np.random.default_rng(23)
def ctl_lock(keep, ndraw=250):
    out = []
    for _ in range(ndraw):
        gg = np.zeros(n, bool); gg[rng2.choice(lock_sig_idx, size=min(keep, len(lock_sig_idx)), replace=False)] = True
        R_, pct, blk, sg = walk(gg); out.append(stats(pct, blk, sg, 1)["pf"])
    return np.array(out)
print("\n  entry conditions (research survivors):")
for nm in surv.cond:
    mk = POOL[nm]; R_, pct, blk, sg = walk(WIN & mk); s = stats(pct, blk, sg, 1, R_); keep = int((mk & sigbar & (np.arange(n) >= CUT)).sum())
    cc = ctl_lock(keep)
    print(f"    {nm[:56]:56s} locked: {fmt(s)}   dPF {100*(s['pf']/b_lock['pf']-1):+6.1f}%   random filter median PF {np.nanmedian(cc):.3f} p {np.nanmean(cc >= s['pf']):.3f}")
if len(surv) == 0: print("    none survived research")
# TP rules that beat the fixed 2.3 ATR target on research PF AND total AND clear their null at p<=0.05
base_tp = TP[TP.rule == "fixed 2.3 ATR"].iloc[0]
tp_surv = TP[(TP.pf > base_tp.pf) & (TP.tot > base_tp.tot) & (TP.get("p_pf", pd.Series(np.nan, index=TP.index)) <= 0.05)]
print(f"\n  target rules beating fixed 2.3 ATR on research PF and total AND clearing the random-distance null: {len(tp_surv)}")
for r in tp_surv.itertuples():
    nm = r.rule
    # rebuild the target array by name
    for lvn, lv in LEVELS.items():
        if nm.startswith(lvn):
            fb = None if "no target" in nm else BASE["tp"]; cap = 4.0 if "capped" in nm else None; t_, u = tp_from_level(lv, fallback=fb, cap_atr=cap); break
    else:
        cap = 2.0 if "within 2" in nm else None; t_, u = tp_from_level(stack, cap_atr=cap)
    R_, pct, blk, sg, why = walk_tp(WIN, stop_fixed, t_); s = stats(pct, blk, sg, 1, R_)
    print(f"    {nm[:56]:56s} locked: {fmt(s)}   R {s['r']:+.4f}   dPF vs base {100*(s['pf']/b_lock['pf']-1):+6.1f}%   target hit {100*np.mean(why[blk==1]==1):.0f}%")
best_st = ST.sort_values("retdd", ascending=False).head(3)
print("\n  stop rules: the top-3 research return/drawdown, read on locked (descriptive -- the base 3.19 is the declared stop):")
for r in best_st.itertuples():
    # rebuild by rule name
    nm = r.rule
    if nm.startswith("fixed"): sa = np.full(n, float(nm.split()[1]))
    elif nm.startswith("adaptive INVERTED"): tight, wide = float(nm.split(":")[1].split()[0]), float(nm.split("else")[1]); sa = np.where(vp_ <= 0.5, tight, wide)
    elif nm.startswith("adaptive"): wide, tight = float(nm.split(":")[1].split()[0]), float(nm.split("else")[1].split()[0]); sa = np.where(vp_ <= 0.5, wide, tight)
    elif "x (ATR/ATR50)" in nm: sa = np.clip(float(nm.split()[0]) * r50, 0.5, 8.0)
    elif "/ (ATR/ATR50)" in nm: sa = np.clip(float(nm.split()[0]) / np.where(r50 > 0, r50, np.nan), 0.5, 8.0)
    elif "signal-bar range" in nm: sa = np.clip(float(nm.split()[0]) * rng_, 1.0, 6.0)
    elif "prior VP VAL" in nm: sa = struct_stop(c - g("vp.prior_val_atr") * atr)
    elif "prior VP POC" in nm: sa = struct_stop(c - g("vp.prior_poc_atr") * atr)
    elif "developing VP VAL" in nm: sa = struct_stop(c - g("vp.dev_val_atr") * atr)
    elif "IB low" in nm: sa = struct_stop(c - g("tpo.ib_lo_atr") * atr)
    elif "HVN below" in nm: sa = struct_stop(c - g("vp.hvn_below_atr") * atr)
    elif "EMA200" in nm: sa = struct_stop(L["e200"])
    else: sa = struct_stop(L["e48"])
    R_, pct, blk, sg, why = walk_tp(WIN, sa, tgt_fixed); s = stats(pct, blk, sg, 1, R_)
    print(f"    {nm[:56]:56s} locked: {fmt(s)}   R {s['r']:+.4f}  ret/DD {s['tot']/max(s['dd'],1e-9):5.2f}   (research ret/DD {r.retdd:.2f})")
print(f"\n  total runtime {time.time()-t0:.0f}s")
