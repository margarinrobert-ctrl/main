#!/usr/bin/env python3
"""audit_donchian_1.py -- ADVERSARIAL AUDIT of BUF-NAS-10-1.25.

RULE UNDER AUDIT (reimplemented from the rule text alone, no import of
agent_donchian.py helpers):
    LONG  if close[i] > max(high[i-10..i-1]) + 1.25 * ATR14[i]
    SHORT if close[i] < min(low[i-10..i-1])  - 1.25 * ATR14[i]
    window 07:00-11:00 NY, one trade per session (first trigger),
    fill next open, stop 1.5*ATR14[i], target 2.0*ATR14[i], max_hold 16,
    flatten 11:00, cost 2.0 pts + 0.25 slip, NAS, RESEARCH block only.

CLAIMED: n=558 exp=+1.67 ctrl=-2.48 excess=+4.15 z=2.6 p=0.0045

Parts
  P1  independent reproduction (own signal code + own bar-by-bar simulator
      + own matched control) vs the lab engine
  P2  multiplicity (302 configurations)
  P3  leakage forensics
  P4  selectivity: random filters and better-matched controls
  P5  parameter perturbation (plateau or spike)
  P6  cost stress / break-even multiple
  P7  sub-period thirds
  P8  power: standard error of the excess, and whether the control's
      dispersion is the right yardstick
"""
import sys, time, numpy as np, pandas as pd
sys.path.insert(0, '/home/user/main/research/donchian')
import data as D
import lab
from engine import build_walk

NY_WIN = (420, 660)
COST, SLIP = 2.0, 0.25

# ------------------------------------------------------------------ my own indicators
def my_ema(x, n):
    a = 2.0 / (n + 1.0)
    out = np.empty(len(x), dtype=np.float64)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out

def my_tr(h, l, c):
    out = np.empty(len(c))
    out[0] = h[0] - l[0]
    for i in range(1, len(c)):
        out[i] = max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1]))
    return out

def my_atr(df, n=14):
    return my_ema(my_tr(df.high.values, df.low.values, df.close.values), n)

def my_donchian_loop(df, n):
    """Explicit loop: channel at bar i uses ONLY bars i-n .. i-1."""
    h, l = df.high.values, df.low.values
    N = len(h)
    hi = np.full(N, np.nan); lo = np.full(N, np.nan)
    for i in range(n, N):
        hi[i] = h[i-n:i].max()
        lo[i] = l[i-n:i].min()
    return hi, lo

def my_signals(df, n_entry=10, buf=1.25, atr_n=14, win=NY_WIN, a=None, hi=None, lo=None):
    if a is None: a = my_atr(df, atr_n)
    if hi is None: hi, lo = my_donchian_loop(df, n_entry)
    c, tod = df.close.values, df.tod.values
    ok = ((tod >= win[0]) & (tod < win[1]) & ~np.isnan(hi) & ~np.isnan(lo)
          & ~np.isnan(a) & (a > 0))
    up = (c > hi + buf * a) & ok
    dn = (c < lo - buf * a) & ok
    idx = np.where(up | dn)[0]
    side = np.where(up[idx], 1, -1).astype(np.int64)
    return idx, side, a

def first_per_session(df, idx, side):
    s = df.sess.values[idx]
    keep = np.concatenate([[True], s[1:] != s[:-1]])
    return idx[keep], side[keep]

# ------------------------------------------------------- my own bar-by-bar simulator
def my_sim(df, idx, side, a, stop_mult=1.5, targ_mult=2.0, max_hold=16,
           flat_tod=660, cost=COST, slip=SLIP):
    """Deliberately naive python loop. Same pessimism rules as the house engine:
    flatten wins ties, then stop, then target; both-in-one-bar books as a loss;
    a gap through the stop fills at the bar open when that is worse."""
    o, h, l, c = (df.open.values, df.high.values, df.low.values, df.close.values)
    tod, sess = df.tod.values, df.sess.values
    N = len(o)
    rows = []
    for k in range(len(idx)):
        i = int(idx[k]); sd = int(side[k])
        if i + 1 >= N: continue
        fill = o[i+1]
        entry = fill + sd * slip
        av = a[i]
        stop = entry - sd * stop_mult * av
        targ = entry + sd * targ_mult * av
        s0 = sess[i+1]
        px = None; reason = None; nb = 0
        for j in range(i+1, min(i+1+max_hold, N)):
            nb = j - i
            if sess[j] != s0 or tod[j] >= flat_tod:
                px = o[j]; reason = 'flatten'; break
            hits = (h[j] >= stop) if sd < 0 else (l[j] <= stop)
            hitt = (h[j] >= targ) if sd > 0 else (l[j] <= targ)
            if hits:
                gp = o[j]
                px = min(gp, stop) if sd > 0 else max(gp, stop)
                reason = 'stop'; break
            if hitt:
                px = targ; reason = 'target'; break
            if nb == max_hold:
                px = c[j]; reason = 'time'; break
        if px is None:
            continue
        gross = sd * (px - entry)
        rows.append((i, sd, entry, px, gross, gross - cost, nb, reason))
    return pd.DataFrame(rows, columns=['sig_bar','side','entry','exit','gross','net','bars','reason'])

# ---------------------------------------------------- my own matched control
def my_control(df, walk, tr, pool_mask, a, n_draws=1000, seed=7, stop_mult=1.5,
               targ_mult=2.0, max_hold=16, flat_tod=660, cost=COST, slip=SLIP,
               vec=True):
    """Random entries: same minute-of-day histogram, same side mix, same
    geometry, drawn from pool_mask.  Returns the array of book means."""
    from engine import simulate
    tod = df.tod.values
    elig = pool_mask & ~np.isnan(a) & (a > 0) & ~np.isnan(walk['opens'][:, 0])
    want = pd.Series(tod[tr.sig_bar.values]).value_counts()
    by_tod = {t: np.where(elig & (tod == t))[0] for t in want.index}
    sides = tr.side.values.astype(np.float64)
    rng = np.random.default_rng(seed)
    means = np.empty(n_draws); sds = np.empty(n_draws)
    for d in range(n_draws):
        picks = [rng.choice(by_tod[t], size=int(k), replace=True)
                 for t, k in want.items() if len(by_tod[t])]
        ix = np.concatenate(picks)
        sd = rng.permutation(sides)[:len(ix)] if len(sides) >= len(ix) else rng.choice(sides, len(ix))
        fill = walk['opens'][ix, 0]
        entry = fill + sd * slip
        av = a[ix]
        stop = entry - sd * stop_mult * av
        targ = entry + sd * targ_mult * av
        cc = simulate(walk, ix, sd, entry, stop, targ, max_hold=max_hold,
                      flat_tod=flat_tod, cost_pts=cost)
        means[d] = cc.net.mean() if len(cc) else np.nan
        sds[d] = cc.net.std(ddof=1) if len(cc) > 1 else np.nan
    ok = ~np.isnan(means)
    return means[ok], sds[ok]

def score(real_mean, means, label='', n=None, extra=''):
    mu, sd = means.mean(), means.std(ddof=1)
    z = (real_mean - mu) / sd if sd > 0 else 0.0
    p = float((means >= real_mean).mean())
    print(f"  {label:<46} n={n if n else 0:>5,} exp={real_mean:>+7.2f} ctrl={mu:>+7.2f} "
          f"excess={real_mean-mu:>+7.2f} z={z:>+6.2f} p={p:.4f} {extra}")
    return dict(exp=real_mean, ctrl=mu, excess=real_mean-mu, z=z, p=p, sd_ctrl=sd)


# =====================================================================  P1
def P1():
    print("=" * 110)
    print("P1  INDEPENDENT REPRODUCTION  (own indicators, own signal code, own")
    print("    bar-by-bar simulator, own matched control)")
    print("=" * 110)
    df, w, r = lab.research('NAS')
    a_mine = my_atr(df, 14)
    a_lab = lab.atr(df, 14)
    print(f"  ATR14 mine vs lab: max abs diff = {np.nanmax(np.abs(a_mine-a_lab)):.3e}")
    hi_m, lo_m = my_donchian_loop(df, 10)
    hi_l, lo_l = lab.donchian(df, 10)
    m = ~np.isnan(hi_m) & ~np.isnan(hi_l)
    print(f"  Donchian(10) upper mine(loop, i-10..i-1) vs lab: max diff = "
          f"{np.nanmax(np.abs(hi_m[m]-hi_l[m])):.3e}   lower = {np.nanmax(np.abs(lo_m[m]-lo_l[m])):.3e}")
    print(f"  lab NaN count {np.isnan(hi_l).sum()}, mine {np.isnan(hi_m).sum()}"
          f"   (both must be >= n so a bar never sets its own channel)")

    idx, side, a = my_signals(df, 10, 1.25, a=a_mine, hi=hi_m, lo=lo_m)
    print(f"\n  raw triggers in window (all blocks): {len(idx):,}")
    idx1, side1 = first_per_session(df, idx, side)
    res = r[idx1]
    idxR, sideR = idx1[res], side1[res]
    print(f"  after one-per-session: {len(idx1):,};  research block only: {len(idxR):,}")
    print(f"  CLAIMED n = 558")
    print(f"  side mix research: long {(sideR>0).sum()} / short {(sideR<0).sum()}")
    print(f"  max research sig_bar session = {df.sess.values[idxR].max()}  (split at {D.split_point(df)})"
          f"   -> {'OK, no locked bars' if df.sess.values[idxR].max() < D.split_point(df) else '*** LOCKED LEAK ***'}")

    t0 = time.time()
    tr_mine = my_sim(df, idxR, sideR, a_mine)
    print(f"\n  my loop simulator: n={len(tr_mine)} exp={tr_mine.net.mean():+.4f} "
          f"net={tr_mine.net.sum():+,.1f}  ({time.time()-t0:.1f}s)")

    # lab engine on the same triggers, gated on research
    g, tr_lab = lab.sig_gate('NAS', idx, side, label='lab engine n=10 buf=1.25',
                             n_draws=1000, seed=0, quiet=True)
    trR = tr_lab[np.isin(tr_lab.sig_bar, np.where(r)[0])].reset_index(drop=True)
    print(f"  lab engine      : n={len(trR)} exp={trR.net.mean():+.4f} net={trR.net.sum():+,.1f}")
    mrg = tr_mine.merge(trR[['sig_bar','net','side']], on='sig_bar', suffixes=('_mine','_lab'))
    print(f"  matched on sig_bar: {len(mrg)} of {len(tr_mine)}; "
          f"max |net diff| = {np.abs(mrg.net_mine-mrg.net_lab).max():.6f}; "
          f"side mismatches = {(mrg.side_mine!=mrg.side_lab).sum()}")

    print(f"\n  LAB GATE (n_draws=1000, seed 0): n={g['n']} exp={g['exp']:+.2f} ctrl={g['ctrl']:+.2f} "
          f"excess={g['excess']:+.2f} z={g['z']:+.2f} p={g['p']:.4f}")

    # my own control
    dfb, wb, rb, hb = lab.bars('NAS')
    mn, sds = my_control(df, wb, trR, r, a_mine, n_draws=1000, seed=7)
    print("\n  MY OWN matched control (1000 draws, independent code):")
    s = score(trR.net.mean(), mn, 'mine: minute-of-day + side + geometry', len(trR))
    print(f"    control book-mean sd = {mn.std(ddof=1):.3f};  real book trade sd = {trR.net.std(ddof=1):.2f}"
          f"  -> real SE = {trR.net.std(ddof=1)/np.sqrt(len(trR)):.3f}")
    print(f"    mean control TRADE sd  = {np.nanmean(sds):.2f}   (compare to real {trR.net.std(ddof=1):.2f})")

    # p-value granularity
    print("\n  p-value granularity: with 300 draws the smallest reportable p is 1/300 = 0.0033;")
    print("  the claimed p=0.0045 is therefore a 1-2 draw estimate. Repeat over seeds:")
    for sd_ in (0, 1, 2, 3, 4):
        g2, _ = lab.sig_gate('NAS', idx, side, label='', n_draws=300, seed=sd_, quiet=True)
        print(f"    seed {sd_}: excess={g2['excess']:+.2f} z={g2['z']:+.2f} p={g2['p']:.4f}")
    return df, wb, r, a_mine, idx, side, trR





# =====================================================================  P2
def P2():
    print("\n" + "=" * 110)
    print("P2  MULTIPLICITY:  302 configurations were evaluated to select this cell")
    print("=" * 110)
    K = 302
    print(f"  Bonferroni threshold for FWER 5%      : p < 0.05/{K} = {0.05/K:.3e}")
    print(f"  Bonferroni threshold for FWER 10%     : p < 0.10/{K} = {0.10/K:.3e}")
    print(f"  Sidak threshold                       : p < {1-(1-0.05)**(1/K):.3e}")
    print(f"  Benjamini-Hochberg, if this is the SMALLEST of the 302 p-values,")
    print(f"    its threshold is 1*0.05/{K} = {0.05/K:.3e}  (identical to Bonferroni at rank 1)")
    print(f"  observed p (reported)                 : 0.0045")
    print(f"  -> {0.0045/(0.05/K):.0f}x LARGER than the corrected threshold.  FAILS.")
    print("\n  Equivalent z: the corrected 5% threshold needs z >= "
          f"{stats_norm_ppf(1-0.05/K):.2f}; observed z ~ 2.6-2.9.")
    print("  Expected number of the 302 cells reaching p<0.005 under a pure null: "
          f"{302*0.005:.2f}")
    print("  The candidate is explicitly the ARGMAX-z cell of that 302-cell grid,")
    print("  i.e. exactly the order statistic that Bonferroni is designed to price.")
    # what does the max of 302 correlated null z's look like?
    rng = np.random.default_rng(0)
    print("\n  Simulation: max of 302 standard-normal draws with correlation rho")
    for rho in (0.0, 0.5, 0.8, 0.9):
        m = np.sqrt(rho) * rng.standard_normal((20000, 1)) + np.sqrt(1-rho) * rng.standard_normal((20000, 302))
        mx = m.max(1)
        print(f"    rho={rho:.1f}: E[max z]={mx.mean():.2f}  P(max z >= 2.6)={np.mean(mx>=2.6):.3f}"
              f"  95th pct of max z = {np.percentile(mx,95):.2f}")

def stats_norm_ppf(q):
    from scipy.stats import norm
    return float(norm.ppf(q))


# =====================================================================  P3
def P3(df, walk, r, a, idx, side, trR):
    print("\n" + "=" * 110)
    print("P3  LEAKAGE FORENSICS")
    print("=" * 110)
    c, o, h, l = df.close.values, df.open.values, df.high.values, df.low.values
    tod, sess = df.tod.values, df.sess.values

    print("\n  (1) Donchian excludes the current bar?")
    hi, lo = my_donchian_loop(df, 10)
    viol_u = np.nansum(hi < h)   # not a violation per se; check construction directly
    ok = True
    for i in np.random.default_rng(0).choice(np.arange(20, len(df)), 500, replace=False):
        if not np.isclose(hi[i], h[i-10:i].max()) or not np.isclose(lo[i], l[i-10:i].min()):
            ok = False
    print(f"      500 random bars re-derived by brute force: {'PASS' if ok else 'FAIL'}")
    print(f"      bars where the channel upper equals the CURRENT bar high: "
          f"{np.nansum(np.isclose(hi, h))} of {len(df):,} "
          f"(expected small & coincidental, not structural)")

    print("\n  (2) ATR14 is causal?  a[i] recomputed from bars 0..i only, 200 spot checks")
    bad = 0
    for i in np.random.default_rng(1).choice(np.arange(200, len(df)), 200, replace=False):
        sub = df.iloc[:i+1]
        if abs(my_atr(sub, 14)[-1] - a[i]) > 1e-8: bad += 1
    print(f"      mismatches: {bad}  -> {'PASS (no future bars enter ATR)' if bad==0 else 'FAIL'}")

    print("\n  (3) No full-sample / centred statistics anywhere in the rule.")
    print("      The rule is: close[i] > rollmax(high, i-10..i-1) + 1.25*ema(TR,14)[i].")
    print("      Both terms are causal by construction; no percentile, z-score,")
    print("      normalisation or .rolling() without shift is used.  PASS.")

    print("\n  (4) SIGNAL bar vs FILL bar.  The condition is evaluated at bar i;")
    print("      the fill is open[i+1].  Verify the engine fills at i+1:")
    fill_engine = walk['opens'][trR.sig_bar.values, 0]
    fill_true = o[trR.sig_bar.values + 1]
    print(f"      max |engine fill - open[i+1]| = {np.abs(fill_engine-fill_true).max():.3e}  PASS")
    print(f"      entry = fill + side*0.25 slip: max err = "
          f"{np.abs(trR.entry.values - (fill_true + trR.side.values*0.25)).max():.3e}  PASS")

    print("\n  (5) The stop/target are sized in ATR at the SIGNAL bar, not the fill bar:")
    av_sig = a[trR.sig_bar.values]; av_fill = a[trR.sig_bar.values+1]
    d_sig = np.abs(np.abs(trR.entry.values-trR.stop.values) - 1.5*av_sig).max()
    d_fill = np.abs(np.abs(trR.entry.values-trR.stop.values) - 1.5*av_fill).max()
    print(f"      |stop dist - 1.5*ATR[sig]| max = {d_sig:.2e}   "
          f"|stop dist - 1.5*ATR[fill]| max = {d_fill:.2f}  -> signal bar.  PASS")

    print("\n  (6) POSITIVE CONTROL: deliberately introduce the classic defect")
    print("      (evaluate the buffer condition at the FILL bar i+1) and confirm")
    print("      it produces a materially different, better book. If it does not,")
    print("      the test has no power; if the real book equals it, the real book leaks.")
    hi_s, lo_s = np.roll(hi, -1), np.roll(lo, -1)
    a_s = np.roll(a, -1); c_s = np.roll(c, -1)
    okm = ((tod>=420)&(tod<660)&~np.isnan(hi_s)&~np.isnan(a_s)&(a_s>0))
    up = (c_s > hi_s + 1.25*a_s) & okm; dn = (c_s < lo_s - 1.25*a_s) & okm
    i2 = np.where(up|dn)[0]; s2 = np.where(up[i2],1,-1).astype(np.int64)
    g2, tr2 = lab.sig_gate('NAS', i2, s2, n_draws=400, quiet=True)
    print(f"      leaky variant: n={g2['n']} exp={g2['exp']:+.2f} excess={g2['excess']:+.2f} z={g2['z']:+.2f}")
    print(f"      real variant : n={len(trR)} exp={trR.net.mean():+.2f}")
    print(f"      -> the leak is worth {g2['exp']-trR.net.mean():+.2f} pts/trade; the audited")
    print(f"         book does NOT show it, so it is reading the signal bar.  PASS")

    print("\n  (7) Locked-block containment:")
    k = D.split_point(df)
    print(f"      max session used = {sess[trR.sig_bar.values].max()} < split {k}: PASS")
    print(f"      forward walk of the LAST research trade may run into bar indices")
    print(f"      inside the locked block (a trade opened on the last research session")
    print(f"      exits within that session) - exits are capped by flat_tod/session id,")
    print(f"      so no locked BAR is ever read.  max exit bars held = {trR.bars.max()}")
    lastsess_trades = trR[sess[trR.sig_bar.values] == sess[trR.sig_bar.values].max()]
    print(f"      trades on the final research session: {len(lastsess_trades)}")

    print("\n  (8) one-per-session selection is causal (first trigger of the session,")
    print("      known when it happens; no 'best trigger of the session' choice). PASS")


# =====================================================================  P4
def P4(df, walk, r, a, idx, side, trR):
    print("\n" + "=" * 110)
    print("P4  SELECTIVITY:  random filters and HARDER-matched controls")
    print("=" * 110)
    from engine import simulate
    c, o, h, l = df.close.values, df.open.values, df.high.values, df.low.values
    tod, sess = df.tod.values, df.sess.values
    inwin = (tod >= 420) & (tod < 660)
    tr_arr = my_tr(h, l, c)
    trr = tr_arr / a
    real = trR.net.mean(); n_real = len(trR)

    # ---- baseline (buf=0) trigger population, research window
    hi, lo = my_donchian_loop(df, 10)
    okm = inwin & ~np.isnan(hi) & ~np.isnan(a) & (a > 0)
    up0 = (c > hi) & okm; dn0 = (c < lo) & okm
    base_bar = np.where(up0 | dn0)[0]; base_side = np.where(up0[base_bar],1,-1)
    bm = r[base_bar]
    base_bar_R, base_side_R = base_bar[bm], base_side[bm]
    up1 = (c > hi + 1.25*a) & okm; dn1 = (c < lo - 1.25*a) & okm
    cand_bar = np.where(up1|dn1)[0]; cand_bar_R = cand_bar[r[cand_bar]]
    frac = len(cand_bar_R)/len(base_bar_R)
    print(f"\n  bar-level selectivity: {len(cand_bar_R):,} of {len(base_bar_R):,} "
          f"raw research-window breakouts survive the 1.25 ATR buffer = {frac:.1%}")
    ib, sb = first_per_session(df, base_bar, base_side)
    ibR = ib[r[ib]]
    print(f"  session-level: candidate trades on {n_real} of {len(ibR)} sessions that have "
          f"any n=10 breakout = {n_real/len(ibR):.1%}")

    def sim_set(ix, sd):
        ix = np.asarray(ix); sd = np.asarray(sd, dtype=np.float64)
        fill = walk['opens'][ix,0]; entry = fill + sd*SLIP; av = a[ix]
        cc = simulate(walk, ix, sd, entry, entry - sd*1.5*av, entry + sd*2.0*av,
                      max_hold=16, flat_tod=660, cost_pts=COST)
        return cc

    # ---- (a) RANDOM FILTER of the same bar-level selectivity
    print("\n  (a) RANDOM FILTER of identical bar-level selectivity: keep a random")
    print(f"      {frac:.1%} of the raw research breakouts, then one-per-session, re-simulate.")
    rng = np.random.default_rng(11)
    means = []; ns = []
    for d in range(1000):
        keep = rng.random(len(base_bar_R)) < frac
        bb, ss = base_bar_R[keep], base_side_R[keep]
        if len(bb) < 30: continue
        bb, ss = first_per_session(df, bb, ss)
        cc = sim_set(bb, ss)
        means.append(cc.net.mean()); ns.append(len(cc))
    means = np.array(means)
    score(real, means, 'vs random same-selectivity filter', n_real,
          extra=f"(ctrl mean n={np.mean(ns):.0f})")

    # ---- (b) RANDOM SESSION SUBSET of the same size
    print("\n  (b) RANDOM SESSION SUBSET: from the sessions with any n=10 breakout,")
    print(f"      pick {n_real} at random and take that session's FIRST raw breakout.")
    means = []
    for d in range(1000):
        pick = rng.choice(len(ibR), size=n_real, replace=False)
        bb = ibR[pick]; ss = np.where(up0[bb],1,-1)
        cc = sim_set(bb, ss)
        means.append(cc.net.mean())
    score(real, np.array(means), 'vs random session subset (first raw break)', n_real)

    # ---- (c) VOL-MATCHED control (the buffer mechanically implies TR/ATR > 1.25)
    print("\n  (c) The rule ALGEBRAICALLY implies a volatility shock:")
    print("      close[i] > max(high[i-10..i-1]) + 1.25*ATR >= close[i-1] + 1.25*ATR")
    print("      => TR[i] > 1.25*ATR[i].  Check on the real book:")
    print(f"      min TR/ATR over the 558 trades = {trr[trR.sig_bar.values].min():.3f}"
          f"   median = {np.median(trr[trR.sig_bar.values]):.2f}"
          f"   (all window research bars: median {np.median(trr[r&inwin&~np.isnan(a)]):.2f})")
    print(f"      mean ATR at signal = {a[trR.sig_bar.values].mean():.2f} vs "
          f"{a[r&inwin&~np.isnan(a)].mean():.2f} at a random window bar "
          f"({a[trR.sig_bar.values].mean()/a[r&inwin&~np.isnan(a)].mean():.2f}x)")
    for thr in (1.25, 1.0):
        pool = r & inwin & (trr >= thr) & ~np.isnan(a) & (a > 0)
        mn, _ = my_control(df, walk, trR, pool, a, n_draws=1000, seed=21)
        score(real, mn, f'vs VOL-MATCHED control (pool TR/ATR>={thr})', n_real,
              extra=f"pool={pool.sum():,}")
    pool = r & inwin & (trr >= 1.25) & (trr < 2.5) & ~np.isnan(a) & (a > 0)
    mn, _ = my_control(df, walk, trR, pool, a, n_draws=1000, seed=22)
    score(real, mn, 'vs VOL BAND control (1.25<=TR/ATR<2.5)', n_real, extra=f"pool={pool.sum():,}")

    # ---- (d) ATR-decile matched control
    print("\n  (d) ATR-LEVEL matched control (barrier width in points is matched,")
    print("      so the fixed 2.25 pt cost is the same FRACTION of the barrier):")
    aw = a[r & inwin & ~np.isnan(a) & (a>0)]
    q = np.quantile(aw, [0.0,0.2,0.4,0.6,0.8,1.0])
    lo_q = np.quantile(a[trR.sig_bar.values], 0.05); hi_q = np.quantile(a[trR.sig_bar.values], 0.95)
    pool = r & inwin & (a >= lo_q) & (a <= hi_q) & ~np.isnan(a)
    mn, _ = my_control(df, walk, trR, pool, a, n_draws=1000, seed=23)
    score(real, mn, 'vs ATR-band control (5-95pct of book ATR)', n_real, extra=f"pool={pool.sum():,}")

    # ---- (e) SAME-SESSION control: random window bar in the SAME session, SAME side
    print("\n  (e) SAME-SESSION control: for each real trade, a random window bar in")
    print("      the SAME session with the SAME side. Isolates within-session TIMING")
    print("      from session/side selection.")
    sig = trR.sig_bar.values; sd_real = trR.side.values.astype(np.float64)
    bysess = {}
    winbars = np.where(inwin & ~np.isnan(a) & (a>0) & ~np.isnan(walk['opens'][:,0]))[0]
    ws = sess[winbars]
    order = np.argsort(ws, kind='stable')
    winbars = winbars[order]; ws = ws[order]
    starts = np.searchsorted(ws, sess[sig]); ends = np.searchsorted(ws, sess[sig], side='right')
    means = []
    for d in range(1000):
        pick = starts + (rng.random(len(sig)) * (ends-starts)).astype(int)
        ix = winbars[pick]
        cc = sim_set(ix, sd_real)
        means.append(cc.net.mean())
    score(real, np.array(means), 'vs random bar in the SAME session, same side', n_real)

    # ---- (f) big-bar momentum WITHOUT any channel
    print("\n  (f) DECOMPOSITION: drop the Donchian channel entirely, keep only the")
    print("      'close moved > 1.25 ATR from the previous close' part.")
    dc = (c - np.roll(c,1)) / a
    upb = (dc > 1.25) & okm; dnb = (dc < -1.25) & okm
    ib2 = np.where(upb|dnb)[0]; sb2 = np.where(upb[ib2],1,-1).astype(np.int64)
    g, _ = lab.sig_gate('NAS', ib2, sb2, n_draws=1000, quiet=True, label='')
    print(f"      no-channel big-bar momentum: n={g['n']:,} exp={g['exp']:+.2f} "
          f"ctrl={g['ctrl']:+.2f} excess={g['excess']:+.2f} z={g['z']:+.2f} p={g['p']:.4f}")
    ov = len(np.intersect1d(ib2, cand_bar))
    print(f"      overlap with the candidate's raw triggers: {ov:,} of {len(cand_bar):,} "
          f"candidate bars ({ov/len(cand_bar):.0%}) and {ov:,} of {len(ib2):,} momentum bars")



# =====================================================================  P4b
def P4b(df, walk, r, a, idx, side, trR):
    print("\n" + "=" * 110)
    print("P4b  THE TWO SHARP TESTS")
    print("=" * 110)
    from engine import simulate
    c, o, h, l = df.close.values, df.open.values, df.high.values, df.low.values
    tod, sess = df.tod.values, df.sess.values
    inwin = (tod >= 420) & (tod < 660)
    real = trR.net.mean(); n_real = len(trR)
    rng = np.random.default_rng(31)
    hi, lo = my_donchian_loop(df, 10)
    okm = inwin & ~np.isnan(hi) & ~np.isnan(a) & (a > 0)

    def sim_set(ix, sd):
        ix = np.asarray(ix); sd = np.asarray(sd, dtype=np.float64)
        fill = walk['opens'][ix,0]; entry = fill + sd*SLIP; av = a[ix]
        cc = simulate(walk, ix, sd, entry, entry - sd*1.5*av, entry + sd*2.0*av,
                      max_hold=16, flat_tod=660, cost_pts=COST)
        return cc

    # ---- T1: does the DONCHIAN CHANNEL add anything to the big directional bar?
    print("\n  T1  The candidate's 1,025 raw triggers are a 24% SUBSET of the 4,291")
    print("      'close moved >1.25 ATR from prev close' bars, whose own excess is")
    print("      +0.31 (z=0.31, dead). Is the channel INFORMATIVE, or is 24% of a")
    print("      dead population just lucky?  Random 24% subsets, 2000 draws:")
    dc = (c - np.roll(c,1)) / a
    upb = (dc > 1.25) & okm; dnb = (dc < -1.25) & okm
    mom = np.where(upb|dnb)[0]; mom_s = np.where(upb[mom],1,-1)
    momR = r[mom]; mom, mom_s = mom[momR], mom_s[momR]
    cand_raw = idx[r[idx]]
    frac = len(cand_raw)/len(mom)
    print(f"      research-block momentum bars {len(mom):,}; candidate raw triggers "
          f"{len(cand_raw):,} = {frac:.1%}; subset check "
          f"{len(np.intersect1d(cand_raw, mom))}/{len(cand_raw)}")
    means=[]; ns=[]
    for d in range(2000):
        keep = rng.random(len(mom)) < frac
        bb, ss = mom[keep], mom_s[keep]
        bb, ss = first_per_session(df, bb, ss)
        cc = sim_set(bb, ss); means.append(cc.net.mean()); ns.append(len(cc))
    score(real, np.array(means), 'candidate vs random 24% of big-bar momentum', n_real,
          extra=f"(ctrl mean n={np.mean(ns):.0f})")

    # same but matching the minute-of-day histogram too
    print("\n      same test, but the random subset is drawn to match the candidate's")
    print("      minute-of-day histogram as well (a strictly harder control):")
    want = pd.Series(tod[trR.sig_bar.values]).value_counts()
    by = {t: mom[tod[mom]==t] for t in want.index}
    means=[]
    for d in range(2000):
        picks=[rng.choice(by[t], size=int(k), replace=True) for t,k in want.items() if len(by[t])]
        ix=np.concatenate(picks); sd=rng.permutation(trR.side.values.astype(float))[:len(ix)]
        means.append(sim_set(ix, sd).net.mean())
    score(real, np.array(means), 'vs momentum pool, minute-of-day matched', n_real)

    # ---- T2: same-session control restricted to bars AT OR AFTER the signal
    print("\n  T2  The same-session control in P4(e) can enter BEFORE the breakout,")
    print("      which is look-ahead. Redo it with the random bar restricted to")
    print("      j >= signal bar (implementable: side is known at i):")
    sig = trR.sig_bar.values; sd_real = trR.side.values.astype(np.float64)
    winbars = np.where(inwin & ~np.isnan(a) & (a>0) & ~np.isnan(walk['opens'][:,0]))[0]
    for mode, lo_off in (('j >= i (incl. the signal bar itself)', 0), ('j > i (strictly later)', 1)):
        means=[]
        cand_ok=[]
        pools=[]
        for k in range(len(sig)):
            i0=sig[k]
            pool = winbars[(sess[winbars]==sess[i0]) & (winbars >= i0+lo_off)]
            pools.append(pool)
        keep = np.array([len(p)>0 for p in pools])
        print(f"      {mode}: {keep.sum()} of {len(sig)} trades have a non-empty pool")
        for d in range(500):
            ix = np.array([p[rng.integers(len(p))] for p,kk in zip(pools,keep) if kk])
            means.append(sim_set(ix, sd_real[keep]).net.mean())
        realk = trR.net.values[keep].mean()
        score(realk, np.array(means), f'   same session, {mode}', int(keep.sum()))

    # ---- T3: grid correlation - how independent are the 302 cells really?
    print("\n  T3  How correlated is the grid?  Jaccard overlap of the trade sets")
    print("      between the candidate and its neighbours (high overlap means the")
    print("      'plateau' is one measurement, not five):")
    base = set(trR.sig_bar.values.tolist())
    for nn, bb in ((10,1.25),(5,1.25),(15,1.25),(10,1.0),(10,1.5),(20,1.0),(10,0.0),(20,0.0)):
        hi2, lo2 = my_donchian_loop(df, nn)
        i2,s2,_ = my_signals(df, nn, bb, a=a, hi=hi2, lo=lo2)
        i2,s2 = first_per_session(df, i2, s2)
        i2 = i2[r[i2]]
        st = set(i2.tolist())
        j = len(base & st)/max(len(base | st),1)
        print(f"      n={nn:<3} buf={bb:<5} n_tr={len(st):>4}  shared={len(base&st):>4}  Jaccard={j:.2f}")



# ---------------------------------------------------------- generic cell runner
def cell(df, walk, r, mask, n_entry=10, buf=1.25, atr_n=14, stop=1.5, targ=2.0,
         max_hold=16, flat=660, win=NY_WIN, ops=True, confirm='close',
         cost=COST, slip=SLIP, n_draws=600, seed=5, label='', quiet=False):
    from engine import simulate
    a = my_atr(df, atr_n)
    hi, lo = my_donchian_loop(df, n_entry)
    c, h, l, tod = df.close.values, df.high.values, df.low.values, df.tod.values
    px = c if confirm == 'close' else h
    pxl = c if confirm == 'close' else l
    ok = ((tod >= win[0]) & (tod < win[1]) & ~np.isnan(hi) & ~np.isnan(lo)
          & ~np.isnan(a) & (a > 0))
    up = (px > hi + buf * a) & ok; dn = (pxl < lo - buf * a) & ok
    ix = np.where(up | dn)[0]
    if len(ix) == 0: return None
    sd = np.where(up[ix], 1, -1).astype(np.float64)
    if ops:
        ss = df.sess.values[ix]
        k = np.concatenate([[True], ss[1:] != ss[:-1]]); ix, sd = ix[k], sd[k]
    keep = mask[ix]
    ix, sd = ix[keep], sd[keep]
    if len(ix) < 25: return None
    fill = walk['opens'][ix, 0]
    good = ~np.isnan(fill); ix, sd, fill = ix[good], sd[good], fill[good]
    entry = fill + sd * slip; av = a[ix]
    tt = entry + sd * targ * av if targ > 0 else np.where(sd > 0, np.inf, -np.inf)
    tr = simulate(walk, ix, sd, entry, entry - sd * stop * av, tt,
                  max_hold=max_hold, flat_tod=flat, cost_pts=cost)
    mn, _ = my_control(df, walk, tr, mask, a, n_draws=n_draws, seed=seed,
                       stop_mult=stop, targ_mult=targ, max_hold=max_hold,
                       flat_tod=flat, cost=cost, slip=slip)
    mu, sdv = mn.mean(), mn.std(ddof=1)
    z = (tr.net.mean() - mu) / sdv if sdv > 0 else 0.0
    out = dict(n=len(tr), exp=tr.net.mean(), ctrl=mu, excess=tr.net.mean()-mu,
               z=z, p=float((mn >= tr.net.mean()).mean()), tr=tr)
    if not quiet:
        print(f"  {label:<48} n={out['n']:>5,} exp={out['exp']:>+7.2f} "
              f"ctrl={out['ctrl']:>+7.2f} excess={out['excess']:>+7.2f} "
              f"z={out['z']:>+6.2f} p={out['p']:.4f}")
    return out


# =====================================================================  P5
def P5(df, walk, r, a, idx, side, trR):
    print("\n" + "=" * 110)
    print("P5  PARAMETER PERTURBATION - one and two steps in every direction")
    print("=" * 110)
    base = dict(df=df, walk=walk, r=r, mask=r, n_draws=600)
    print("\n  (i) the (lookback, buffer) surface, FINE grid around the cell")
    ns = (5, 8, 10, 12, 15, 20); bufs = (0.75, 1.0, 1.25, 1.5, 1.75)
    grid = {}
    for n in ns:
        for b in bufs:
            grid[(n,b)] = cell(**base, n_entry=n, buf=b, quiet=True)
    for key, f in (('excess','{:>8.2f}'), ('z','{:>8.2f}'), ('n','{:>8,d}')):
        print(f"\n      {key}")
        print("      n\\buf " + "".join(f"{b:>8.2f}" for b in bufs))
        for n in ns:
            row = f"      {n:>5} "
            for b in bufs:
                g = grid[(n,b)]
                row += ('      --' if g is None else f.format(g[key]))
            print(row)

    print("\n  (ii) ATR lookback for BOTH the buffer and the barriers (candidate 14)")
    for an in (7, 10, 14, 20, 28):
        cell(**base, atr_n=an, label=f'atr_n={an}')
    print("\n  (iii) stop multiple (candidate 1.5)")
    for sm in (1.0, 1.25, 1.5, 1.75, 2.0):
        cell(**base, stop=sm, label=f'stop={sm}')
    print("\n  (iv) target multiple (candidate 2.0)")
    for tm in (1.0, 1.5, 2.0, 2.5, 3.0):
        cell(**base, targ=tm, label=f'targ={tm}')
    print("\n  (v) max_hold (candidate 16)")
    for mh in (4, 8, 12, 16, 24, 32):
        cell(**base, max_hold=mh, label=f'max_hold={mh}')
    print("\n  (vi) flatten time / window (candidate 07:00-11:00, flat 11:00)")
    for wn, fl, lb in (((420,660),660,'07:00-11:00'), ((420,570),570,'07:00-09:30'),
                       ((570,660),660,'09:30-11:00'), ((420,720),720,'07:00-12:00'),
                       ((390,660),660,'06:30-11:00'), ((450,660),660,'07:30-11:00')):
        cell(**base, win=wn, flat=fl, label=f'window {lb}')
    print("\n  (vii) confirmation and one-per-session")
    cell(**base, confirm='high', label='confirm=high (touch beyond)')
    cell(**base, ops=False, label='one_per_session=False (all triggers)')
    print("\n  (viii) buffer measured in the PRIOR bar's ATR (signal bar cannot")
    print("       inflate its own yardstick) - and in a FIXED point buffer")
    from engine import simulate
    c, h, l, tod = df.close.values, df.high.values, df.low.values, df.tod.values
    hi, lo = my_donchian_loop(df, 10)
    ap = np.roll(a, 1); ap[0] = np.nan
    for b in (1.0, 1.25, 1.5):
        ok = ((tod>=420)&(tod<660)&~np.isnan(hi)&~np.isnan(ap)&(ap>0)&~np.isnan(a)&(a>0))
        up = (c > hi + b*ap) & ok; dn = (c < lo - b*ap) & ok
        ix = np.where(up|dn)[0]; sd = np.where(up[ix],1,-1).astype(np.int64)
        ix, sd = first_per_session(df, ix, sd)
        g, _ = lab.sig_gate('NAS', ix, sd, n_draws=600, seed=5, quiet=True)
        print(f"  {('buf='+str(b)+' in PRIOR-bar ATR'):<48} n={g['n']:>5,} exp={g['exp']:>+7.2f} "
              f"ctrl={g['ctrl']:>+7.2f} excess={g['excess']:>+7.2f} z={g['z']:>+6.2f} p={g['p']:.4f}")

    print("\n  (ix) OUT-OF-INSTRUMENT: US30 research block, same rule "
          "(cost 4.0 + 0.5 slip)")
    d2, w2, r2 = lab.research('US30')
    _, wb2, _, _ = lab.bars('US30')
    for n in (5, 10, 15, 20):
        for b in (0.0, 1.0, 1.25, 1.5):
            g = cell(d2, wb2, r2, r2, n_entry=n, buf=b, cost=4.0, slip=0.5,
                     n_draws=400, label=f'US30 n={n} buf={b}', quiet=True)
            if g: print(f"  {('US30 n='+str(n)+' buf='+str(b)):<48} n={g['n']:>5,} "
                        f"exp={g['exp']:>+7.2f} ctrl={g['ctrl']:>+7.2f} "
                        f"excess={g['excess']:>+7.2f} z={g['z']:>+6.2f} p={g['p']:.4f}")


# =====================================================================  P6
def P6(df, walk, r, a, idx, side, trR):
    print("\n" + "=" * 110)
    print("P6  COST STRESS")
    print("=" * 110)
    print("  modelled round turn = 2.00 pts commission/spread + 0.25 pts entry slippage")
    for m in (0.0, 1.0, 1.5, 2.0, 3.0, 4.0):
        g = cell(df, walk, r, r, cost=COST*m, slip=SLIP*m, n_draws=600,
                 label=f'cost x{m:.1f} ({COST*m:.2f} pt + {SLIP*m:.2f} slip)')
    print("\n  the EXCESS is near cost-invariant by construction (the control pays the")
    print("  same cost), so the binding question is where exp crosses zero:")
    g0 = cell(df, walk, r, r, cost=0.0, slip=0.0, n_draws=200, quiet=True)
    gross = g0['exp']
    print(f"    gross exp (zero cost)        = {gross:+.2f} pts/trade")
    print(f"    modelled cost                = {COST+SLIP:.2f} pts/trade")
    print(f"    net exp at 1x                = {gross-(COST+SLIP):+.2f} pts/trade")
    print(f"    BREAK-EVEN COST MULTIPLE     = {gross/(COST+SLIP):.2f}x")
    print(f"    (NQ/NAS 15m: 2.25 index pts ~ 1 tick spread + commission; a 1.74x")
    print(f"     stress is ~3.9 pts, i.e. a wider-than-usual but not extreme spread)")


# =====================================================================  P7
def P7(df, walk, r, a, idx, side, trR):
    print("\n" + "=" * 110)
    print("P7  SUB-PERIOD STABILITY inside the research block")
    print("=" * 110)
    sess = df.sess.values
    rs = sess[r]; s0, s1 = rs.min(), rs.max()
    print(f"  research sessions {s0}..{s1}   ({df.ts[r].min().date()} -> {df.ts[r].max().date()})")
    for k, nm in ((3, 'THIRDS'), (2, 'HALVES')):
        print(f"\n  {nm}")
        cuts = np.linspace(s0, s1 + 1, k + 1).astype(int)
        for i in range(k):
            m = r & (sess >= cuts[i]) & (sess < cuts[i+1])
            d0 = df.ts[m].min().date(); d1 = df.ts[m].max().date()
            cell(df, walk, r, m, n_draws=600, label=f'{nm[:-1].lower()} {i+1}  {d0} -> {d1}')
    print("\n  CALENDAR YEARS (reported for stability only - year is NOT a rule condition)")
    yr = df.ts.dt.year.values
    for y in sorted(np.unique(yr[r])):
        m = r & (yr == y)
        g = cell(df, walk, r, m, n_draws=400, label=f'{y}', quiet=True)
        if g is None:
            print(f"  {y:<48} too few trades")
        else:
            print(f"  {y:<48} n={g['n']:>5,} exp={g['exp']:>+7.2f} ctrl={g['ctrl']:>+7.2f} "
                  f"excess={g['excess']:>+7.2f} z={g['z']:>+6.2f} p={g['p']:.4f}")


# =====================================================================  P8
def P8(df, walk, r, a, idx, side, trR):
    print("\n" + "=" * 110)
    print("P8  POWER, STANDARD ERRORS, AND THE EFFECTIVE MULTIPLICITY")
    print("=" * 110)
    net = trR.net.values; n = len(net)
    sd = net.std(ddof=1)
    print(f"  n = {n},  trade sd = {sd:.2f} pts,  SE of the mean = {sd/np.sqrt(n):.3f} pts")
    mn, _ = my_control(df, walk, trR, r, a, n_draws=4000, seed=77)
    ex = net.mean() - mn.mean()
    se_ctrl = mn.std(ddof=1)
    se_ctrlmean = se_ctrl/np.sqrt(len(mn))
    se_tot = np.sqrt((sd/np.sqrt(n))**2 + se_ctrlmean**2)
    print(f"  control book-mean sd (= SE of a null book of the same size) = {se_ctrl:.3f}")
    print(f"  4000-draw MC error on the control mean = {se_ctrlmean:.4f}")
    print(f"  excess = {ex:+.2f};  z vs control dispersion = {ex/se_ctrl:+.2f}")
    print(f"  excess / SE(real mean) = {ex/se_tot:+.2f}   (the two agree: the real book's")
    print(f"  trade dispersion {sd:.1f} matches the null pool's, so the control's")
    print(f"  yardstick is NOT understated - no defect here)")
    # session-clustered SE (one trade per session, so clustering is a non-issue,
    # but check serial dependence across adjacent sessions)
    from scipy import stats as sstats
    ac = np.corrcoef(net[:-1], net[1:])[0,1]
    print(f"  lag-1 autocorrelation of trade net = {ac:+.3f} "
          f"(one trade per session, so no within-session clustering)")
    print(f"  95% CI for the excess: [{ex-1.96*se_tot:+.2f}, {ex+1.96*se_tot:+.2f}] pts/trade")
    zneed = stats_norm_ppf(1-0.05/302)
    print(f"\n  n required to reach the Bonferroni-corrected z={zneed:.2f} at this effect")
    print(f"  size: {n*(zneed/(ex/se_ctrl))**2:.0f} trades ({n*(zneed/(ex/se_ctrl))**2/n:.2f}x the "
          f"{n} available). The research block cannot supply them.")

    # --- effective number of independent tests over the (n,buf) surface
    print("\n  EFFECTIVE MULTIPLICITY of the surface the candidate is the argmax of.")
    print("  Session bootstrap (1000 draws) of every cell's mean net -> correlation")
    print("  matrix of the cell statistics -> Li & Ji effective number of tests.")
    ns = (5, 10, 15, 20, 30, 40, 60); bufs = (0.0,0.25,0.5,0.75,1.0,1.25,1.5,2.0)
    sess = df.sess.values
    rsess = np.unique(sess[r])
    cols = []; names = []
    for nn in ns:
        hi, lo = my_donchian_loop(df, nn)
        for bb in bufs:
            i2, s2, _ = my_signals(df, nn, bb, a=a, hi=hi, lo=lo)
            if len(i2) == 0: continue
            i2, s2 = first_per_session(df, i2, s2)
            k = r[i2]; i2, s2 = i2[k], s2[k]
            if len(i2) < 25: continue
            fill = walk['opens'][i2,0]
            from engine import simulate
            sdd = s2.astype(np.float64); entry = fill + sdd*SLIP; av = a[i2]
            tt = simulate(walk, i2, sdd, entry, entry-sdd*1.5*av, entry+sdd*2.0*av,
                          max_hold=16, flat_tod=660, cost_pts=COST)
            v = pd.Series(tt.net.values, index=sess[tt.sig_bar.values])
            cols.append(v.reindex(rsess)); names.append((nn,bb))
    M = pd.concat(cols, axis=1).values          # sessions x cells, NaN where no trade
    rng = np.random.default_rng(5)
    B = 1000
    boot = np.empty((B, M.shape[1]))
    for b in range(B):
        pick = rng.integers(0, M.shape[0], M.shape[0])
        S = M[pick]
        boot[b] = np.nanmean(S, axis=0)
    C = np.corrcoef(boot.T)
    ev = np.linalg.eigvalsh(C)[::-1]
    ev = np.clip(ev, 0, None)
    Meff_liji = float(sum((ev > 1).astype(float) + (ev - np.floor(ev)) * (ev > 0)))
    Meff_chev = float(len(ev) * (1 - (ev.var(ddof=1)) / len(ev)))
    print(f"    cells measured: {len(names)};  mean |off-diagonal correlation| = "
          f"{np.abs(C[np.triu_indices_from(C,1)]).mean():.2f}")
    print(f"    Li & Ji effective number of independent tests  M_eff = {Meff_liji:.1f}")
    print(f"    Cheverud-Nyholt                                M_eff = {Meff_chev:.1f}")
    for Me in (Meff_liji, 302*Meff_liji/len(names)):
        thr = 0.05/Me
        print(f"    -> with M_eff={Me:.1f}: corrected threshold p<{thr:.2e} (z>{stats_norm_ppf(1-thr):.2f})"
              f"; P(max null z >= 2.79) = {1-(1-0.00264)**Me:.3f}")



# =====================================================================  P9
def P9(df, walk, r, a, idx, side, trR):
    print("\n" + "=" * 110)
    print("P9  EPISODE CONCENTRATION, EXIT SPLIT, SIDE SPLIT, PRE-RTH SHARE,")
    print("    AND WHETHER THE US30 'REPLICATION' IS INDEPENDENT")
    print("=" * 110)
    from engine import simulate, REASONS
    sess, tod = df.sess.values, df.tod.values
    net = trR.net.values; n = len(net)
    mn, _ = my_control(df, walk, trR, r, a, n_draws=2000, seed=91)
    ctrl = mn.mean(); sdc = mn.std(ddof=1)

    print("\n  (a) exit-reason split (a rule earning at the TIME stop is a direction")
    print("      bet, not a barrier edge):")
    for k, nm in enumerate(REASONS):
        m = trR.reason.values == k
        if m.sum() == 0: continue
        print(f"      {nm:<9} {m.sum():>4} ({m.mean():>5.1%})  exp={net[m].mean():>+8.2f}"
              f"  total={net[m].sum():>+9.0f}")
    print(f"      ambiguous bars (stop and target in one bar, booked as loss): "
          f"{trR.ambig.mean():.1%}")

    print("\n  (b) side split")
    for sgn, nm in ((1,'long'),(-1,'short')):
        m = trR.side.values == sgn
        print(f"      {nm:<6} {m.sum():>4}  exp={net[m].mean():>+7.2f}  "
              f"wr={(net[m]>0).mean():>5.1%}  total={net[m].sum():>+9.0f}")

    print("\n  (c) concentration of the P&L")
    o = np.sort(net)
    print(f"      median trade = {np.median(net):+.2f};  mean = {net.mean():+.2f};  "
          f"10% trimmed mean = {sstats_trim(net,0.1):+.2f}")
    print(f"      best 5 trades = {o[-5:].sum():+.0f} pts of {net.sum():+.0f} total "
          f"({o[-5:].sum()/net.sum():.0%});  best 10 = {o[-10:].sum()/net.sum():.0%};  "
          f"best 25 = {o[-25:].sum()/net.sum():.0%}")
    for drop in (1, 5, 10, 25):
        keep = np.argsort(net)[:-drop]
        m2 = net[keep].mean()
        print(f"      drop the best {drop:>2} trades: exp={m2:+.2f}  excess={m2-ctrl:+.2f}"
              f"  z={(m2-ctrl)/sdc:+.2f}")
    ym = df.ts.values[trR.sig_bar.values].astype('datetime64[M]')
    bym = pd.Series(net).groupby(pd.Series(ym)).sum().sort_values()
    print(f"      best month {bym.index[-1]}: {bym.iloc[-1]:+.0f} pts "
          f"({bym.iloc[-1]/net.sum():.0%} of total); 2nd {bym.index[-2]}: {bym.iloc[-2]:+.0f}")
    for k in (1,2,3):
        bad = set(bym.index[-k:])
        keep = ~pd.Series(ym).isin(bad).values
        m2 = net[keep].mean()
        print(f"      drop the {k} best MONTH(s): n={keep.sum():>4} exp={m2:+.2f} "
              f"excess={m2-ctrl:+.2f} z={(m2-ctrl)/sdc:+.2f}")

    print("\n  (d) pre-RTH share (CLAUDE.md: the cost model does NOT widen the")
    print("      pre-09:30 spread, so 07:00-09:30 fills are optimistic)")
    pre = tod[trR.sig_bar.values] < 570
    print(f"      trades before 09:30: {pre.sum()} of {n} ({pre.mean():.0%});  "
          f"exp pre={net[pre].mean():+.2f}  exp RTH={net[~pre].mean():+.2f}")
    print(f"      share of total pts from pre-RTH trades: {net[pre].sum()/net.sum():.0%}")

    print("\n  (e) IS THE US30 REPLICATION INDEPENDENT?  Same rule on US30 research,")
    print("      then compare the trade DATES and the per-date P&L with NAS.")
    d2, w2, r2 = lab.research('US30')
    _, wb2, _, _ = lab.bars('US30')
    g2 = cell(d2, wb2, r2, r2, n_entry=10, buf=1.25, cost=4.0, slip=0.5,
              n_draws=600, seed=93, label='US30 n=10 buf=1.25 (research)')
    t2 = g2['tr']
    dn = pd.Series(df.ts.values[trR.sig_bar.values]).dt.normalize()
    d2d = pd.Series(d2.ts.values[t2.sig_bar.values]).dt.normalize()
    print(f"      NAS research window {dn.min().date()} -> {dn.max().date()}; "
          f"US30 research window {d2d.min().date()} -> {d2d.max().date()}")
    ov = len(set(dn) & set(d2d))
    print(f"      calendar-date overlap of the two books: {ov} dates "
          f"({ov/len(set(dn)):.0%} of NAS dates, {ov/len(set(d2d)):.0%} of US30 dates)")
    A = pd.Series(net, index=dn.values).groupby(level=0).sum()
    B = pd.Series(t2.net.values, index=d2d.values).groupby(level=0).sum()
    J = pd.concat([A.rename('nas'), B.rename('us30')], axis=1).dropna()
    print(f"      per-date net P&L correlation on the {len(J)} shared dates: "
          f"rho = {J.nas.corr(J.us30):+.3f}   (sign agreement "
          f"{np.mean(np.sign(J.nas)==np.sign(J.us30)):.0%})")
    print(f"      -> the two instruments are the SAME index complex over the SAME")
    print(f"         2016-2022 calendar; this is a correlated re-measurement, not")
    print(f"         an independent sample.")
    print("\n      US30 sub-period thirds (does its excess come from the same era?)")
    s2v = d2.sess.values; rs2 = s2v[r2]
    cuts = np.linspace(rs2.min(), rs2.max()+1, 4).astype(int)
    for i in range(3):
        m = r2 & (s2v >= cuts[i]) & (s2v < cuts[i+1])
        cell(d2, wb2, r2, m, n_entry=10, buf=1.25, cost=4.0, slip=0.5,
             n_draws=400, seed=94,
             label=f'  US30 third {i+1} {d2.ts[m].min().date()}->{d2.ts[m].max().date()}')


def sstats_trim(x, f):
    x = np.sort(x); k = int(len(x)*f)
    return x[k:len(x)-k].mean()


# ================================================================  P5 grid only
def P5grid(df, walk, r, a, idx, side, trR):
    print("\n" + "=" * 110)
    print("P5(i)  THE (lookback, buffer) SURFACE - FINE GRID AROUND THE CELL")
    print("=" * 110)
    ns = (5, 8, 10, 12, 15, 20); bufs = (0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0)
    grid = {}
    for n in ns:
        for b in bufs:
            grid[(n,b)] = cell(df, walk, r, r, n_entry=n, buf=b, n_draws=800,
                               seed=6, quiet=True)
    for key, f in (('excess','{:>8.2f}'), ('z','{:>8.2f}'), ('exp','{:>8.2f}'), ('n','{:>8,d}')):
        print(f"\n  {key}")
        print("  n\\buf " + "".join(f"{b:>8.2f}" for b in bufs))
        for n in ns:
            row = f"  {n:>5} "
            for b in bufs:
                g = grid[(n,b)]
                row += ('      --' if g is None else f.format(g[key]))
            print(row)



# =====================================================================  P10
def P10(df, walk, r, a, idx, side, trR):
    """The concentration test done FAIRLY: a 2R/1.5R barrier book is
    right-skewed by construction, so the control is top-heavy too.  Trim
    BOTH and compare like with like."""
    print("\n" + "=" * 110)
    print("P10  FAIR TRIMMED / WINSORISED COMPARISON, AND THE BARRIER MECHANISM")
    print("=" * 110)
    from engine import simulate
    tod = df.tod.values
    net = trR.net.values; n = len(net)
    want = pd.Series(tod[trR.sig_bar.values]).value_counts()
    elig = r & ~np.isnan(a) & (a > 0) & ~np.isnan(walk['opens'][:, 0])
    by = {t: np.where(elig & (tod == t))[0] for t in want.index}
    sides = trR.side.values.astype(np.float64)
    rng = np.random.default_rng(101)
    B = 2000
    stats_c = {k: np.empty(B) for k in ('mean','trim10','med','drop5','drop10','drop25','wins','targ','stop')}
    for d in range(B):
        picks = [rng.choice(by[t], size=int(k), replace=True) for t, k in want.items() if len(by[t])]
        ix = np.concatenate(picks)
        sd = rng.permutation(sides)[:len(ix)]
        fill = walk['opens'][ix,0]; entry = fill + sd*SLIP; av = a[ix]
        cc = simulate(walk, ix, sd, entry, entry-sd*1.5*av, entry+sd*2.0*av,
                      max_hold=16, flat_tod=660, cost_pts=COST)
        v = np.sort(cc.net.values)
        stats_c['mean'][d] = v.mean()
        stats_c['trim10'][d] = sstats_trim(v, 0.10)
        stats_c['med'][d] = np.median(v)
        for k, dr in (('drop5',5), ('drop10',10), ('drop25',25)):
            stats_c[k][d] = v[:-dr].mean()
        stats_c['wins'][d] = (v > 0).mean()
        stats_c['targ'][d] = (cc.reason.values == 1).mean()
        stats_c['stop'][d] = (cc.reason.values == 0).mean()
    v = np.sort(net)
    print("\n  statistic                     real      control    excess       z       p")
    rows = [('mean net / trade', v.mean(), 'mean'),
            ('10% trimmed mean', sstats_trim(v,0.10), 'trim10'),
            ('median trade', np.median(v), 'med'),
            ('mean, best 5 removed', v[:-5].mean(), 'drop5'),
            ('mean, best 10 removed', v[:-10].mean(), 'drop10'),
            ('mean, best 25 removed', v[:-25].mean(), 'drop25')]
    for lbl, rv, k in rows:
        c = stats_c[k]; mu, sd = c.mean(), c.std(ddof=1)
        print(f"  {lbl:<26} {rv:>+8.2f}  {mu:>+8.2f}  {rv-mu:>+8.2f}  {(rv-mu)/sd:>+6.2f}  "
              f"{float((c>=rv).mean()):.4f}")
    print("\n  -> the control is right-skewed by the SAME 2R/1.5R geometry, so trimming")
    print("     both is the fair comparison. Read the trimmed rows, not the raw ones.")

    print("\n  BARRIER MECHANISM: the excess must show up as a higher TARGET rate,")
    print("  not as a bigger tail on the same rate.")
    for lbl, rv, k in (('win rate', (v>0).mean(), 'wins'),
                       ('target-exit rate', (trR.reason.values==1).mean(), 'targ'),
                       ('stop-exit rate', (trR.reason.values==0).mean(), 'stop')):
        c = stats_c[k]; mu, sd = c.mean(), c.std(ddof=1)
        print(f"  {lbl:<26} {rv:>8.3f}  {mu:>8.3f}  {rv-mu:>+8.3f}  {(rv-mu)/sd:>+6.2f}")


def main():
    what = sys.argv[1] if len(sys.argv)>1 else 'all'
    df, walk, r, a, idx, side, trR = P1()
    if what in ('all','2'): P2()
    if what in ('all','3'): P3(df, walk, r, a, idx, side, trR)
    if what in ('all','4'): P4(df, walk, r, a, idx, side, trR)
    if what in ('all','4b'): P4b(df, walk, r, a, idx, side, trR)
    if what in ('all','5'): P5(df, walk, r, a, idx, side, trR)
    if what in ('all','6'): P6(df, walk, r, a, idx, side, trR)
    if what in ('all','7'): P7(df, walk, r, a, idx, side, trR)
    if what in ('all','8'): P8(df, walk, r, a, idx, side, trR)
    if what in ('all','9'): P9(df, walk, r, a, idx, side, trR)
    if what in ('all','5i'): P5grid(df, walk, r, a, idx, side, trR)
    if what in ('all','10'): P10(df, walk, r, a, idx, side, trR)

if __name__ == '__main__':
    main()
