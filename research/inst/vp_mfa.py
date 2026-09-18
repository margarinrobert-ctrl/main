"""The VP/TPO work re-scored under the mechanism-first-alpha architecture.

Two things the earlier deflation did not do, both of which the skill calls out as the common
errors: (1) it counted the 43 conditions as 43 INDEPENDENT trials when they are built from a
feature set with 20 pairs at |rho| >= 0.9, and (2) it never kept the discarded candidates' return
streams, so White's reality check could not be run. Both are fixed here by regenerating every
candidate's daily return stream from the declared pool.

Also runs Gate 1 (the primary alone, unfiltered, equal-weighted, costs in) on each block and on
each market, which is the gate this branch never had as a named step.
"""
import os, sys, warnings, numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56", "research/v63", "research/v64", "research/inst"):
    sys.path.insert(0, os.path.join(ROOT, p))
# the skill's scripts go AFTER the research dirs so `metrics`/`splits` are not shadowed (CLAUDE.md)
sys.path.append("/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/mechanism-first-alpha/scripts")
import v61core as V, v64opt as O, v63feeds as FD, vp_tpo as T, vp_tpo2 as T2
from gates import primary_gate, deflated_sharpe, effective_trials, reality_check
warnings.filterwarnings("ignore"); pd.set_option("display.width", 200)
def line(t): print("\n" + "=" * 112 + f"\n{t}\n" + "=" * 112, flush=True)

D = O.build(15); n = D["n"]; CUT = D["cut"]; c, h, l, o, v, atr, mod = D["c"], D["h"], D["l"], D["o"], D["v"], D["atr"], D["mod"]; ix = pd.DatetimeIndex(D["ix"])
WIN = (mod >= 420) & (mod < 660); ENT = D["ent_all"][0]; EXL = D["exl_all"][0]; day = (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy()
F, L = T.build(D); g = lambda k: F[k].to_numpy()
def walk(gate): return O._walk(o, h, l, c, atr, D["calm"], ENT, EXL, gate, D["d_ma"], D["chop"], D["psh_ok"], int(CUT), 3.19, 3.19, 2.3, 15, 0, 0.0, 0, 0.0, 0, V.COST, V.SLIP, int(D["last_bar"]))

line("GATE 1 -- the PRIMARY alone: every breakout in the window, no filter, equal-weighted, costs in")
print("  The primary is Donchian 10/10 long, 07:00-11:00 NY, 3.19 ATR stop, 2.3 ATR target, 230-min hold.")
print("  Skill's own caveat applies and is stated: this primary has SIX tuned parameters chosen by 3,600 Optuna")
print("  trials, so it is a fitted primary, not a derived one, and inherits the full deflation burden.\n")
R0, p0, b0, s0 = walk(WIN)
for blk, bn in ((0, "NQ research"), (1, "NQ locked")):
    m = b0 == blk
    for unit, x in (("% of price", p0[m]), ("R (constant risk)", R0[m])):
        r = primary_gate(x / 100.0 if unit.startswith("%") else x, cost_per_event=0.0)
        lo, hi = r['net_mean_ci95']
        print(f"  {bn:12s} {unit:18s} n {r['n_events']:>4}  mean {r['net_mean_per_event']:+.5f}  CI [{lo:+.5f}, {hi:+.5f}]  p {r['bootstrap_p_one_sided']:.3f}  hit {100*r['hit_rate']:.1f}%  -> {r['verdict'].split('--')[0].strip()}")
# the primary on the two markets the selection never saw
STOP, TP, HOLD = 3.0, 2.3, 15
for mk, cut_ts in (("US100", "2022-12-26"), ("US30", None)):
    f = FD.bars(mk, 15); oo, hh, ll, cc = (f[k].to_numpy(float) for k in ("open", "high", "low", "close")); nn = len(cc)
    ii = pd.DatetimeIndex(f.index); mm = (ii.hour * 60 + ii.minute).to_numpy(); aa = V._atr(hh, ll, cc)
    en = pd.Series(hh).rolling(10).max().shift(1).to_numpy(); ex = pd.Series(ll).rolling(10).min().shift(1).to_numpy()
    win = (mm >= 420) & (mm < 660); nxt = np.append(oo[1:], np.nan) + 0.1
    cut = int(np.searchsorted(ii.values, np.datetime64(cut_ts))) if cut_ts else nn
    Rr, pp, bb, ss, ww = T.walk_tp(oo, hh, ll, cc, aa, en, ex, win, cut, np.full(nn, STOP), nxt + TP * aa, HOLD, FD.COST[mk][0], 0.1, nn - 25)
    m = bb == 0; r = primary_gate(pp[m] / 100.0, cost_per_event=0.0)
    lab = f"{mk} pre-{cut_ts}" if cut_ts else f"{mk} 2016-2025"
    lo, hi = r['net_mean_ci95']
    print(f"  {lab:22s} % of price      n {r['n_events']:>4}  mean {r['net_mean_per_event']:+.5f}  CI [{lo:+.5f}, {hi:+.5f}]  p {r['bootstrap_p_one_sided']:.3f}  hit {100*r['hit_rate']:.1f}%  -> {r['verdict'].split('--')[0].strip()}")

line("SEARCH ACCOUNTING -- the 43 candidates regenerated, their correlation measured, the trial count corrected")
POOL = {
 "EMA200 above": g("ema.d200_atr") > 0, "EMA200 below": g("ema.d200_atr") < 0, "EMA200 within 1 ATR above": (g("ema.d200_atr") > 0) & (g("ema.d200_atr") <= 1.0),
 "EMA200 >= 1 ATR": g("ema.d200_atr") >= 1.0, "EMA200 >= 2 ATR": g("ema.d200_atr") >= 2.0, "EMA200 touched 5": g("ema.touch200_5") > 0, "EMA200 rising": g("ema.slope200_atr") > 0,
 "EMA13>48 state": g("ema.x1348_state") > 0, "EMA cross <=5": g("ema.bars_since_x1348") <= 5, "EMA cross <=20": g("ema.bars_since_x1348") <= 20,
 "EMA spread >=0.5": g("ema.spread1348_atr") >= 0.5, "EMA spread rising": g("ema.spread_slope_atr") > 0, "EMA13<48 counter": g("ema.x1348_state") == 0,
 "VP above prior VAH": g("vp.prior_vah_atr") > 0, "VP inside prior VA": g("vp.pos_in_prior_va") == 0, "VP below prior VAL": g("vp.prior_val_atr") < 0,
 "VP above prior POC": g("vp.prior_poc_atr") > 0, "VP VA narrow": g("vp.prior_va_width_atr") < 3.0, "VP VA wide": g("vp.prior_va_width_atr") >= 3.0,
 "VP HVN <=1 above": g("vp.hvn_above_atr") <= 1.0, "VP no HVN 2 above": ~(g("vp.hvn_above_atr") <= 2.0), "VP LVN <=1 above": g("vp.lvn_above_atr") <= 1.0,
 "VP naked POC <=3": g("vp.naked_poc_above_atr") <= 3.0, "VP poor high": g("vp.prior_poor_hi") > 0, "VP above prior high": g("vp.prior_hi_atr") > 0,
 "VP above dev VAH": g("vp.dev_vah_atr") > 0, "VP above dev POC": g("vp.dev_poc_atr") > 0, "VP dev VA narrow": g("vp.dev_va_width_atr") < 1.5,
 "TPO above prior VAH": g("tpo.prior_vah_atr") > 0, "TPO skew low": g("tpo.prior_skew") < 0.5, "TPO single print <=3 [WINNER]": g("tpo.prior_single_above_atr") <= 3.0,
 "TPO no single <=3": ~(g("tpo.prior_single_above_atr") <= 3.0), "TPO above IB high": g("tpo.above_ib") > 0, "TPO IB range <1.5": g("tpo.ib_range_atr") < 1.5,
 "TPO IB range >=1.5": g("tpo.ib_range_atr") >= 1.5, "TPO single below <=2": g("tpo.single_below_atr") <= 2.0, "TPO above dev VAH": g("tpo.dev_vah_atr") > 0,
 "ATR >=1.0x sma50": g("atr.ratio50") >= 1.0, "ATR >=1.2x sma250": g("atr.ratio250") >= 1.2, "ATR <1.0x sma50": g("atr.ratio50") < 1.0,
 "vol pct <=0.5": g("atr.vol_pct250") <= 0.5, "bar range >=1.5": g("atr.range_atr") >= 1.5, "bar range <0.8": g("atr.range_atr") < 0.8,
}
alld = np.unique(day[(np.arange(n) < CUT) & (np.arange(n) >= 1000)])
streams = {}; names = []
for nm, m in POOL.items():
    m = np.nan_to_num(m.astype(float), nan=0.0).astype(bool)
    R_, p_, b_, s_ = walk(WIN & m); k = b_ == 0
    if k.sum() < 40: continue
    streams[nm] = pd.Series(p_[k] / 100.0).groupby(day[s_[k]]).sum().reindex(alld).fillna(0.0).to_numpy(); names.append(nm)
M = np.column_stack([streams[k] for k in names])
C = np.corrcoef(M.T); avg_corr = float(C[np.triu_indices_from(C, 1)].mean())
Nraw = len(names); Neff = effective_trials(Nraw, avg_corr)
print(f"  candidates with >= 40 research trades: {Nraw} of {len(POOL)};  {len(alld)} research days")
print(f"  average pairwise correlation of their DAILY RETURN STREAMS: {avg_corr:.3f}")
print(f"  effective independent trials  N_hat = rho + (1-rho)*M = {Neff:.1f}  (raw M = {Nraw})")
print(f"  (the earlier study deflated at raw N = 43 and N = 152 -- that OVER-deflates a correlated pool)")

line("DEFLATED SHARPE, corrected for the correlation among trials")
win_ = streams["TPO single print <=3 [WINNER]"]
sr = win_.mean() / win_.std(); Tn = len(win_)
from scipy.stats import skew as _sk, kurtosis as _ku
sk_, ku_ = float(_sk(win_)), float(_ku(win_, fisher=False))
var_tr = float(np.var([s.mean() / s.std() for s in M.T if s.std() > 0]))
print(f"  winner: SR/day {sr:+.4f} (ann {sr*np.sqrt(252):+.2f}), T {Tn} days, skew {sk_:+.2f}, kurtosis {ku_:.1f}")
print(f"  variance of the candidates' per-day Sharpe: {var_tr:.6f} (sd {np.sqrt(var_tr):.4f})")
for lab, N_ in (("raw M = 43 (what the study reported)", float(Nraw)), (f"effective N = {Neff:.1f} (correlation-adjusted)", Neff),
                ("raw 152 (all research looks)", 152.0), (f"effective 152 at the same rho", effective_trials(152, avg_corr))):
    d = deflated_sharpe(sr, Tn, N_, var_tr, sk_, ku_)
    print(f"  DSR at {lab:44s} {d['dsr']:.3f}   (expected max-of-noise SR/day {d['expected_max_sr_under_null']:+.4f})")

line("WHITE'S REALITY CHECK over the full candidate set -- the test the study could not run")
rc = reality_check(M, n_boot=2000)
bi = int(rc['best_candidate']) if not isinstance(rc['best_candidate'], str) else names.index(rc['best_candidate'])
print(f"  candidates {rc['n_candidates']}, observations {rc['n_obs']};  best by mean daily return: {names[bi]} ({rc['best_mean']:+.6f}/day)")
print(f"  reality-check p = {rc['reality_check_p']:.4f}   null max p95 {rc['null_max_p95']:+.6f}")
print(f"  -> {rc['verdict']}")
w = names.index("TPO single print <=3 [WINNER]")
print("  the study's winner IS the pool's best on this statistic." if w == bi else f"  note: the study's winner ranks below {names[bi]} on mean daily return (the study ranked on profit factor).")
