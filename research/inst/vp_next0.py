"""NEXT_VP_TPO_SCALP handoff, Tier 0 -- the three free checks that can end the work, plus the
Lopez de Prado statistics the handoff asked for (deflated / probabilistic Sharpe, minimum backtest
length). Nothing here selects anything; the gate is fixed at its shipped definition.

0.1  gated locked R/trade beside %/trade, and the equity curve under constant-R sizing
0.2  the deployable trade set: the shipped 'gated' run IS the base walker with the gate as a veto
     inside one position lock (O._walk skips a vetoed signal without taking the lock) -- shown by
     construction, and the post-hoc SUBSET of base trades is reported beside it
0.3  a DAY-CLUSTERED null for the control p: random signal DAYS at the gate's own day base rate
"""
import os, sys, warnings, numpy as np, pandas as pd
from scipy.stats import norm, skew, kurtosis
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56", "research/v64", "research/inst"): sys.path.insert(0, os.path.join(ROOT, p))
import v61core as V, v64opt as O, vp_tpo as T
warnings.filterwarnings("ignore"); pd.set_option("display.width", 220)
def line(t): print("\n" + "=" * 118 + f"\n{t}\n" + "=" * 118, flush=True)
D = O.build(15); n = D["n"]; CUT = D["cut"]; c, h, l, o, atr, mod = D["c"], D["h"], D["l"], D["o"], D["atr"], D["mod"]; ix = pd.DatetimeIndex(D["ix"])
WIN = (mod >= 420) & (mod < 660); ENT = D["ent_all"][0]; EXL = D["exl_all"][0]
F, L = T.build(D); spa = F["tpo.prior_single_above_atr"].to_numpy(); near = np.nan_to_num((spa <= 3.0).astype(float)).astype(bool)
def walk(gate): return O._walk(o, h, l, c, atr, D["calm"], ENT, EXL, gate, D["d_ma"], D["chop"], D["psh_ok"], int(CUT), 3.19, 3.19, 2.3, 15, 0, 0.0, 0, 0.0, 0, V.COST, V.SLIP, int(D["last_bar"]))
def pf(q): return q[q > 0].sum() / max(1e-9, -q[q <= 0].sum())
def dd(q): e = np.cumsum(q); return float(np.max(np.maximum.accumulate(e) - e))
day = (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy()
Rb, pb, bb, sb = walk(WIN); Rg, pg, bg, sg = walk(WIN & near)

line("0.1  GATED LOCKED R/TRADE beside %/trade, and constant-R sizing")
print(f"  {'':22s} {'n':>4} {'PF(%)':>6} {'PF(R)':>6} {'%/trade':>8} {'R/trade':>8} {'sum R':>7} {'DD %':>6} {'DD R':>6}  t(R) per-trade  t(R) day-clustered")
def tday(x, d):
    s = pd.Series(x).groupby(d).sum(); return s.mean() / s.std() * np.sqrt(len(s)) if s.std() > 0 else np.nan
for nm, R_, p_, b_, s_ in (("base", Rb, pb, bb, sb), ("gated (veto in lock)", Rg, pg, bg, sg)):
    for blk, bn in ((0, "research"), (1, "locked")):
        m = b_ == blk; q = p_[m]; r = R_[m]
        print(f"  {nm+' '+bn:22s} {m.sum():>4} {pf(q):6.3f} {pf(r):6.3f} {q.mean():+8.4f} {r.mean():+8.4f} {r.sum():+7.1f} {dd(q):6.2f} {dd(r):6.2f}   {r.mean()/r.std()*np.sqrt(len(r)):+5.2f}          {tday(r, day[s_[m]]):+5.2f}")
print("  (R = (exit - fill - cost) / (3.19 x ATR at the signal); constant-R sizing = one R of risk per trade, the equity curve is the running sum of R)")
kill = Rg[bg == 1].mean()
print(f"\n  KILL CRITERION 0.1: gated locked R/trade = {kill:+.4f} -> " + ("PROCEED (clearly positive)" if kill > 0.02 else "STOP -- at or near zero"))

line("0.2  THE DEPLOYABLE TRADE SET -- veto-in-lock (what the Pine does) vs the post-hoc subset of the base's trades")
print("  O._walk tests the gate at the signal bar and `continue`s without setting `busy`, so a vetoed signal never occupies the lock;")
print("  the shipped 'gated' numbers are therefore already the single-walker, gate-as-veto build.  Overlap with the base:")
sb_set = set(sb.tolist()); sg_set = set(sg.tolist())
both = np.array([s in sb_set for s in sg]); only_g = ~both
sub = np.array([near[s] for s in sb])            # base trades whose signal bar passes the gate (post-hoc subset)
for blk, bn in ((0, "research"), (1, "locked")):
    mg = bg == blk; mb = bb == blk
    q_sub = pb[mb & sub]; r_sub = Rb[mb & sub]
    print(f"  {bn:9s} gated n {mg.sum():>4}: {both[mg].sum():>4} also in the base, {only_g[mg].sum():>3} admitted because a vetoed signal freed the lock "
          f"(those {only_g[mg].sum():>3}: PF {pf(pg[mg & only_g]):.3f}, R {Rg[mg & only_g].mean():+.4f})")
    print(f"  {'':9s} post-hoc SUBSET of base trades passing the gate: n {len(q_sub):>4}  PF {pf(q_sub):.3f}  %/trade {q_sub.mean():+.4f}  R/trade {r_sub.mean():+.4f}  DD {dd(q_sub):.2f}%")
    print(f"  {'':9s} veto-in-lock (number of record):               n {mg.sum():>4}  PF {pf(pg[mg]):.3f}  %/trade {pg[mg].mean():+.4f}  R/trade {Rg[mg].mean():+.4f}  DD {dd(pg[mg]):.2f}%")

line("0.3  DAY-CLUSTERED CONTROL NULL -- random signal DAYS at the gate's day base rate, bar count matched (250 draws)")
rng = np.random.default_rng(31)
sigbar = np.zeros(n, bool); sigbar[1000:D["last_bar"]] = (h[1000:D["last_bar"]] > ENT[1000:D["last_bar"]]) & WIN[1000:D["last_bar"]]
for blk, bn in ((0, "research"), (1, "locked")):
    inb = (np.arange(n) < CUT) if blk == 0 else (np.arange(n) >= CUT)
    sig_idx = np.flatnonzero(sigbar & inb); sdays = day[sig_idx]; udays = np.unique(sdays)
    gdays = np.unique(day[sig_idx[near[sig_idx]]]); k_bars = int(near[sig_idx].sum())
    obs = pf(pg[bg == blk]); obs_m = pg[bg == blk].mean()
    out_bar = []; out_day = []
    for _ in range(250):
        # (a) bar-matched (the published control): random signal bars
        gg = np.zeros(n, bool); gg[rng.choice(sig_idx, size=k_bars, replace=False)] = True
        R_, p_, b_, s_ = walk(gg); out_bar.append((pf(p_[b_ == blk]), p_[b_ == blk].mean()))
        # (b) day-clustered: random DAYS, same number of active days, all their signals, thinned to the same bar count
        dpick = rng.choice(udays, size=len(gdays), replace=False); cand = sig_idx[np.isin(sdays, dpick)]
        keep = rng.choice(cand, size=min(k_bars, len(cand)), replace=False); gg = np.zeros(n, bool); gg[keep] = True
        R_, p_, b_, s_ = walk(gg); out_day.append((pf(p_[b_ == blk]), p_[b_ == blk].mean()))
    ob = np.array(out_bar); od = np.array(out_day)
    print(f"  {bn:9s} gate: {len(gdays)} active days of {len(udays)} signal days ({100*len(gdays)/len(udays):.0f}%), {k_bars} bars;  observed PF {obs:.3f}, mean {obs_m:+.4f}")
    print(f"           bar-matched null : PF median {np.nanmedian(ob[:,0]):.3f} sd {np.nanstd(ob[:,0]):.3f}  p(PF) {np.nanmean(ob[:,0] >= obs):.3f}  p(mean) {np.nanmean(ob[:,1] >= obs_m):.3f}")
    print(f"           day-clustered null: PF median {np.nanmedian(od[:,0]):.3f} sd {np.nanstd(od[:,0]):.3f}  p(PF) {np.nanmean(od[:,0] >= obs):.3f}  p(mean) {np.nanmean(od[:,1] >= obs_m):.3f}" + ("   <- number of record" if blk == 1 else ""))

line("LOPEZ DE PRADO STATISTICS -- probabilistic and deflated Sharpe, minimum backtest length")
def daily(pct, sg): return pd.Series(pct).groupby(day[sg]).sum()
def sr_stats(x, T_days=252):
    x = np.asarray(x, float); sr = x.mean() / x.std(); return sr, skew(x), kurtosis(x, fisher=False), len(x)
def psr(sr, sr0, g3, g4, T): return norm.cdf((sr - sr0) * np.sqrt(T - 1) / np.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr * sr))
def dsr(sr, g3, g4, T, N, var_sr):
    e = 0.5772156649; sr0 = np.sqrt(var_sr) * ((1 - e) * norm.ppf(1 - 1 / N) + e * norm.ppf(1 - 1 / (N * np.e))); return psr(sr, sr0, g3, g4, T), sr0
RS = pd.read_parquet(os.path.join(ROOT, "results/inst/vp_scalp_conditions.parquet"))
# the trial population's Sharpe variance, per-day units: the 41 scorable conditions' annualised research Sharpes / sqrt(252)
var_sr = np.nanvar(RS.sh.to_numpy() / np.sqrt(252))
for blk, bn in ((0, "research"), (1, "locked")):
    dl = daily(pg[bg == blk], sg[bg == blk]); sr, g3, g4, Td = sr_stats(dl.to_numpy())
    # every trading day in the block, zero-filled (the branch's convention for Sharpe)
    alld = np.unique(day[(np.arange(n) < CUT) if blk == 0 else (np.arange(n) >= CUT)]); dz = dl.reindex(alld).fillna(0.0); srz, g3z, g4z, Tz = sr_stats(dz.to_numpy())
    print(f"  {bn:9s} traded days {Td}: SR/day {sr:+.4f} (ann {sr*np.sqrt(252):+.2f}) skew {g3:+.2f} kurt {g4:.1f}   zero-filled {Tz} days: SR/day {srz:+.4f} (ann {srz*np.sqrt(252):+.2f}) skew {g3z:+.2f} kurt {g4z:.1f}")
    print(f"           PSR(SR* = 0) {psr(srz, 0, g3z, g4z, Tz):.3f}")
    for N in (43, 152):
        d_, sr0 = dsr(srz, g3z, g4z, Tz, N, var_sr); print(f"           DSR at N = {N:>3} trials (trial-SR sd {np.sqrt(var_sr):.4f}/day): expected max-of-noise SR {sr0:+.4f}/day  DSR {d_:.3f}")
# minimum backtest length (Bailey & Lopez de Prado): T >= (2 ln N) / SR^2 roughly, using the research daily SR
srr = daily(pg[bg == 0], sg[bg == 0]); alld = np.unique(day[np.arange(n) < CUT]); srr = srr.reindex(alld).fillna(0.0); s = srr.mean() / srr.std()
for N in (43, 152): print(f"  MinBTL at N = {N}: {2*np.log(N)/s**2:.0f} trading days needed for a true SR of {s*np.sqrt(252):.2f} ann to be distinguishable from the best of {N} noise trials; research has {len(alld)}, locked {len(np.unique(day[np.arange(n) >= CUT]))}")
# power: gated trades needed for t = 1.96 / 2.33 / 3.0 at the observed locked effect (per-trade, unclustered and day-clustered)
r = Rg[bg == 1]; es = r.mean() / r.std()
dl = pd.Series(r).groupby(day[sg[bg == 1]]).sum(); esd = dl.mean() / dl.std(); tpd = len(r) / len(dl)
print(f"\n  POWER at the observed locked effect (R): per-trade d = {es:.3f}, day-clustered d = {esd:.3f} ({tpd:.2f} trades/day)")
for t in (1.96, 2.33, 3.0): print(f"    t = {t}: {int(np.ceil((t/es)**2)):>5} trades unclustered   |  {int(np.ceil((t/esd)**2)):>5} days = {int(np.ceil((t/esd)**2*tpd)):>5} trades day-clustered  (~{np.ceil((t/esd)**2*tpd/15):.0f} forward months at 15/mo)")
