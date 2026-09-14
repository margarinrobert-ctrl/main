"""Follow-up on the one survivor of run_vp_scalp.py: 'a prior-session TPO single print within 3 ATR
above the close'. Research: the distance ladder (is it a plateau or a spike), the mirror, what the
condition co-selects (overlap with the other TPO / VP states), the exit-mix mechanism, and a
by-year split. Then the locked NEIGHBOURHOOD and the bootstrap / permutation on the locked read --
all DESCRIPTIVE, the one pre-declared locked read was taken in run_vp_scalp.py."""
import os, sys, warnings, time
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56", "research/v64", "research/inst"):
    sys.path.insert(0, os.path.join(ROOT, p))
import v61core as V, v64opt as O, vp_tpo as T
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
def line(t): print("\n" + "=" * 126 + f"\n{t}\n" + "=" * 126, flush=True)
t0 = time.time()
D = O.build(15); n = D["n"]; CUT = D["cut"]; c, h, l, o, v, atr = D["c"], D["h"], D["l"], D["o"], D["v"], D["atr"]; mod = D["mod"]
WIN = (mod >= 7 * 60) & (mod < 11 * 60); BASE = dict(ent=10, exN=10, stop=3.19, tp=2.3, hold=15)
ENT = D["ent_all"][BASE["ent"] - O.CH_MIN]; EXL = D["exl_all"][BASE["exN"] - O.CH_MIN]
F, L = T.build(D); g = lambda k: F[k].to_numpy()
ix = pd.DatetimeIndex(D["ix"])
def walk(gate):
    return O._walk(o, h, l, c, atr, D["calm"], ENT, EXL, gate, D["d_ma"], D["chop"], D["psh_ok"], int(CUT),
                   BASE["stop"], BASE["stop"], BASE["tp"], BASE["hold"], 0, 0.0, 0, 0.0, 0, V.COST, V.SLIP, int(D["last_bar"]))
def stats(pct, blk, sig, b, R=None):
    q = pct[blk == b]
    if len(q) < 3: return dict(n=len(q), pf=np.nan, tot=np.nan, sh=np.nan, win=np.nan, dd=np.nan, r=np.nan)
    d = pd.Series(q).groupby(sig[blk == b] // 26).sum(); eq = np.cumsum(q)
    return dict(n=len(q), pf=q[q > 0].sum() / max(1e-9, -q[q <= 0].sum()), tot=q.sum(), win=100 * (q > 0).mean(),
                sh=np.sqrt(252) * d.mean() / d.std() if len(d) > 3 and d.std() > 0 else np.nan, dd=float(np.max(np.maximum.accumulate(eq) - eq)),
                r=np.nan if R is None else float(np.mean(R[blk == b])))
def fmt(s): return f"n {s['n']:>4} PF {s['pf']:6.3f} win {s['win']:5.1f}% total {s['tot']:+7.2f}% Sh {s['sh']:5.2f} DD {s['dd']:5.2f}%"
sigbar = np.zeros(n, bool); sigbar[1000:D["last_bar"]] = (h[1000:D["last_bar"]] > ENT[1000:D["last_bar"]]) & WIN[1000:D["last_bar"]]
sig_res = sigbar & (np.arange(n) < CUT); sig_lock = sigbar & (np.arange(n) >= CUT)
rng = np.random.default_rng(7)
def ctl(keep, b, ndraw=200):
    pool = np.flatnonzero(sig_res if b == 0 else sig_lock); out = []
    for _ in range(ndraw):
        gg = np.zeros(n, bool); gg[rng.choice(pool, size=min(keep, len(pool)), replace=False)] = True
        R_, pct, blk, sg = walk(gg); out.append(stats(pct, blk, sg, b)["pf"])
    return np.array(out)
R0, pct0, blk0, sg0 = walk(WIN); b_res, b_lock = stats(pct0, blk0, sg0, 0), stats(pct0, blk0, sg0, 1)
spa = g("tpo.prior_single_above_atr"); spb = g("tpo.single_below_atr"); pr_spb_atr = None

line("1. THE DISTANCE LADDER on research -- 'prior-session single print within X ATR above', and its mirror 'none within X'")
print(f"  {'rung':44s} {'keep%':>5} {'n':>4} {'PF':>6} {'dPF%':>6} {'Sh':>5} {'total':>7} {'R':>7} | {'ctl PF':>6} {'p':>6}    [locked, descriptive: n PF]")
for X in (0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0):
    for nm, m in ((f"single print within {X} ATR above", spa <= X), (f"NO single print within {X} ATR above", ~(spa <= X))):
        m = np.nan_to_num(m.astype(float), nan=0.0).astype(bool)
        R_, pct, blk, sg = walk(WIN & m); s = stats(pct, blk, sg, 0, R_); s1 = stats(pct, blk, sg, 1); keep = int((m & sig_res).sum())
        if s["n"] < 30: continue
        cc = ctl(keep, 0)
        print(f"  {nm:44s} {100*keep/sig_res.sum():5.0f} {s['n']:>4} {s['pf']:6.3f} {100*(s['pf']/b_res['pf']-1):+6.1f} {s['sh']:5.2f} {s['tot']:+7.2f} {s['r']:+7.4f} | {np.nanmedian(cc):6.3f} {np.nanmean(cc >= s['pf']):6.3f}    [{s1['n']:>4} {s1['pf']:6.3f}]", flush=True)
# a BAND: single print between a and b ATR above (is the effect at the near end or spread out?)
print("  by distance band (research):")
for a_, b_ in ((0, 1), (1, 2), (2, 3), (3, 4), (4, 6), (6, 99)):
    m = (spa > a_) & (spa <= b_); m = np.nan_to_num(m.astype(float), nan=0.0).astype(bool)
    R_, pct, blk, sg = walk(WIN & m); s = stats(pct, blk, sg, 0, R_); s1 = stats(pct, blk, sg, 1)
    print(f"    single print {a_}-{b_} ATR above: research n {s['n']:>4} PF {s['pf']:6.3f} R {s['r']:+7.4f} win {s['win']:5.1f}   [locked n {s1['n']:>4} PF {s1['pf']:6.3f}]")

line("2. WHAT IT CO-SELECTS -- pass rates of the other declared states inside vs outside the condition, on the research signal bars")
cond = np.nan_to_num((spa <= 3.0).astype(float), nan=0.0).astype(bool)
others = {"close above prior TPO VAH": g("tpo.prior_vah_atr") > 0, "close above prior VP VAH": g("vp.prior_vah_atr") > 0, "close above prior POC": g("vp.prior_poc_atr") > 0,
          "prior profile skewed low": g("tpo.prior_skew") < 0.5, "prior VA wide >= 3 ATR": g("vp.prior_va_width_atr") >= 3.0, "close above prior session high": g("vp.prior_hi_atr") > 0,
          "EMA13 > EMA48": g("ema.x1348_state") > 0, "EMA200 >= 1 ATR below": g("ema.d200_atr") >= 1.0, "ATR >= 1.0x ATR50": g("atr.ratio50") >= 1.0,
          "single print within 2 ATR BELOW": spb <= 2.0, "prior RTH high above close (psh not ok)": ~D["psh_ok"]}
inn = cond & sig_res; out_ = ~cond & sig_res
print(f"  {'state':44s} {'inside':>7} {'outside':>7} {'ratio':>6}")
for nm, m in others.items():
    m = np.nan_to_num(m.astype(float), nan=0.0).astype(bool); a_, b_ = m[inn].mean(), m[out_].mean()
    print(f"  {nm:44s} {100*a_:7.1f} {100*b_:7.1f} {a_/max(b_,1e-9):6.2f}")
# where does the single print sit relative to the prior session's range? (a single print ABOVE the close, within 3 ATR, after a breakout
# means yesterday's profile has a fast, unaccepted move just overhead -- the breakout is going INTO yesterday's vacuum)
d_hi = g("vp.prior_hi_atr")  # close - prior session high, in ATR (negative = below yesterday's high)
print(f"\n  inside the condition, close vs prior session high (ATR): median {np.nanmedian(d_hi[inn]):+.2f}  (outside {np.nanmedian(d_hi[out_]):+.2f});"
      f"  prior VA width median {np.nanmedian(g('vp.prior_va_width_atr')[inn]):.2f} vs {np.nanmedian(g('vp.prior_va_width_atr')[out_]):.2f} ATR")

line("3. MECHANISM -- exit mix, target-hit rate and fixed-horizon excursion, inside vs outside (research trades)")
NXT = np.append(o[1:], np.nan) + V.SLIP; tgt = NXT + BASE["tp"] * atr; stopa = np.full(n, BASE["stop"])
for nm, gg in (("inside (single print <= 3 ATR above)", WIN & cond), ("outside", WIN & ~cond), ("base", WIN)):
    R_, pct, blk, sg, why = T.walk_tp(o, h, l, c, atr, ENT, EXL, gg, int(CUT), stopa, tgt, BASE["hold"], V.COST, V.SLIP, int(D["last_bar"]))
    m = blk == 0; s = sg[m]
    mfe = np.array([(h[i + 1:min(i + 16, n - 1) + 1].max() - o[i + 1]) / atr[i] for i in s]); mae = np.array([(o[i + 1] - l[i + 1:min(i + 16, n - 1) + 1].min()) / atr[i] for i in s])
    print(f"  {nm:40s} n {m.sum():>4}  stop {100*np.mean(why[m]==0):4.0f}%  target {100*np.mean(why[m]==1):4.0f}%  hold {100*np.mean(why[m]==2):4.0f}%   mean R {R_[m].mean():+.4f}"
          f"   MFE {np.mean(mfe):.2f} ATR  MAE {np.mean(mae):.2f}  MFE/MAE {np.mean(mfe)/np.mean(mae):.2f}   p90 R {np.percentile(R_[m], 90):.2f}")

line("4. BY YEAR (both blocks; the locked block is 2024-11-27 onward) -- which fold carries it")
R_, pct, blk, sg = walk(WIN & cond); yr = ix.year.to_numpy()[sg]
Rb, pctb, blkb, sgb = walk(WIN); yrb = ix.year.to_numpy()[sgb]
for y in np.unique(yr):
    q = pct[yr == y]; qb = pctb[yrb == y]
    print(f"  {y}: filtered n {len(q):>4} PF {q[q>0].sum()/max(1e-9,-q[q<=0].sum()):6.3f} total {q.sum():+7.2f}%   |  base n {len(qb):>4} PF {qb[qb>0].sum()/max(1e-9,-qb[qb<=0].sum()):6.3f} total {qb.sum():+7.2f}%")

line("5. LOCKED, DESCRIPTIVE -- day-block bootstrap P(mean<=0), permutation drawdown percentile and MC p99 on the filtered locked trades")
q = pct[blk == 1]; days = (sg[blk == 1] // 26)
def boot(q, days, B=2000):
    ud = np.unique(days); out = []
    for _ in range(B):
        pick = rng.choice(ud, size=len(ud), replace=True); out.append(np.concatenate([q[days == d] for d in pick]).mean())
    return np.array(out)
bb = boot(q, days); eq = np.cumsum(q); dd_real = float(np.max(np.maximum.accumulate(eq) - eq))
perm = np.array([float(np.max(np.maximum.accumulate(np.cumsum(rng.permutation(q))) - np.cumsum(rng.permutation(q)))) for _ in range(2000)])
print(f"  filtered locked: n {len(q)} mean {q.mean():+.4f} %/trade  bootstrap P(mean<=0) {np.mean(bb<=0):.3f}  95% CI [{np.percentile(bb,2.5):+.4f}, {np.percentile(bb,97.5):+.4f}]")
print(f"  realised DD {dd_real:.2f}%  permutation percentile {np.mean(perm <= dd_real):.2f}  MC median {np.median(perm):.2f}  p95 {np.percentile(perm,95):.2f}  p99 {np.percentile(perm,99):.2f}  (p99/realised {np.percentile(perm,99)/dd_real:.2f}x)")
qb_ = pctb[blkb == 1]; bbb = boot(qb_, sgb[blkb == 1] // 26)
print(f"  base locked:     n {len(qb_)} mean {qb_.mean():+.4f}  bootstrap P(mean<=0) {np.mean(bbb<=0):.3f}")
print(f"\n  total runtime {time.time()-t0:.0f}s")
