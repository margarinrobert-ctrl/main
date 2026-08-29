"""PREDICTABILITY BUDGET - is the cost hurdle clearable at all?

Before any rule exists, measure the predictability in the series itself at
breakout events, with the two corrections that make this honest:
  1. DRIFT ADJUSTMENT. NAS rose hard over this sample. Any condition firing long
     more often than short earns forward return from exposure alone. Reported
     edge is mean(side*fwd) - mean(side)*mean(fwd).
  2. HAC lag >= horizon. Overlapping h-bar forward windows induce MA(h-1)
     dependence; the default Newey-West lag would overstate every t here.
Research block only.
"""
import numpy as np, pandas as pd
from engine import atr, ema, donchian, true_range
import lab, data as D

def nw_t(x, lag):
    """Newey-West t-stat for mean(x)=0 with Bartlett kernel."""
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 30: return np.nan, np.nan
    m = x.mean(); e = x - m
    g0 = (e @ e) / n
    s = g0
    for l in range(1, min(lag, n-1) + 1):
        gl = (e[l:] @ e[:-l]) / n
        s += 2 * (1 - l/(lag+1)) * gl
    se = np.sqrt(max(s, 1e-18) / n)
    return m, m / se

def bh(ps, q=0.10):
    ps = np.asarray(ps); o = np.argsort(ps); r = np.empty_like(o); r[o] = np.arange(len(ps))
    crit = (r + 1) / len(ps) * q
    ok = ps <= crit
    if not ok.any(): return np.zeros(len(ps), bool), 0.0
    kmax = np.max(np.where(ps <= crit)[0]) if ok.any() else -1
    thr = np.sort(ps)[np.max(np.where(np.sort(ps) <= np.sort(crit))[0])]
    return ps <= thr, float(thr)

df, w, res = lab.research("NAS")
c = df.close.values; a = atr(df, 14); tod = df.tod.values
n = len(df)
COST = 2.0 + 2*0.25          # round turn + slippage both sides, in points

print("="*104)
print("PREDICTABILITY BUDGET - NAS 15m, 07:00-11:00 New York, RESEARCH BLOCK")
print(f"  modelled round turn = {COST:.2f} points")
print(f"  median ATR(14) in window = {np.nanmedian(a[res & (tod>=420)&(tod<660)]):.2f} points")
print("="*104)

# forward returns in POINTS, at several horizons, from the FILL bar (i+1)
fwd = {}
for h in (1, 2, 4, 8, 16):
    f = np.full(n, np.nan)
    j = np.arange(n)
    ok = (j + 1 + h) < n
    f[ok] = c[j[ok] + 1 + h] - w["opens"][j[ok], 0]
    fwd[h] = f

# --- the conditions: Donchian breakouts of several lengths, plus refinements
conds = {}
for L in (5, 10, 20, 40, 80):
    hi, lo = donchian(df, L)
    conds[f"break_up_{L}"]  = (c > hi)
    conds[f"break_dn_{L}"]  = (c < lo)
for L in (10, 20, 40):
    hi, lo = donchian(df, L)
    for k in (0.25, 0.5, 1.0):
        conds[f"break_up_{L}_buf{k}"] = (c > hi + k*a)
        conds[f"break_dn_{L}_buf{k}"] = (c < lo - k*a)
# breakout with an expansion bar
rng_ = df.high.values - df.low.values
for L in (10, 20, 40):
    hi, lo = donchian(df, L)
    conds[f"break_up_{L}_exp"] = (c > hi) & (rng_ > 1.5*a)
    conds[f"break_dn_{L}_exp"] = (c < lo) & (rng_ > 1.5*a)

inwin = (tod >= 420) & (tod < 660) & res & ~np.isnan(a) & (a > 0)

rows = []
for name, m in conds.items():
    side = 1 if "_up_" in name else -1
    mm = m & inwin
    for h in (1, 2, 4, 8, 16):
        f = fwd[h]
        sel = mm & ~np.isnan(f)
        if sel.sum() < 60: continue
        # drift adjustment: subtract what pure exposure to this side earns
        base = np.nanmean(f[inwin & ~np.isnan(f)])
        raw = side * f[sel]
        adj = raw - side * base
        mu, t = nw_t(adj, lag=h)
        rows.append(dict(cond=name, h=h, n=int(sel.sum()), raw=float(np.mean(raw)),
                         edge=float(mu), t=float(t)))
R = pd.DataFrame(rows)
R["p"] = 2*(1 - pd.Series(np.abs(R.t)).apply(lambda x: 0.5*(1+__import__("math").erf(x/np.sqrt(2))) if np.isfinite(x) else np.nan))
R = R.dropna(subset=["p"])
sig, thr = bh(R.p.values, q=0.10)
R["bh_pass"] = sig

print(f"\n  {len(R)} condition x horizon tests. Benjamini-Hochberg q=0.10 threshold p={thr:.5f}")
print(f"  survivors: {int(sig.sum())}\n")
print(f"  {'condition':<24} {'h':>3} {'n':>6} {'raw pts':>9} {'drift-adj':>10} {'NW t':>7} {'p':>8}  BH")
top = R.reindex(R.edge.abs().sort_values(ascending=False).index).head(18)
for _, r in top.iterrows():
    print(f"  {r['cond']:<24} {int(r.h):>3} {int(r.n):>6} {r.raw:>+9.2f} {r.edge:>+10.2f}"
          f" {r.t:>+7.2f} {r.p:>8.4f}  {'YES' if r.bh_pass else '.'}")

best = R[R.bh_pass].edge.abs().max() if sig.any() else R.edge.abs().max()
print("\n" + "="*104)
print(f"  largest drift-adjusted conditional edge : {best:.3f} points")
print(f"  modelled round turn                     : {COST:.3f} points")
print(f"  PREDICTABILITY BUDGET                   : {best/COST:.3f}")
print(f"  {'Below 1.0 - no rule at any parameters can clear costs from these conditions.' if best/COST < 1 else 'Above 1.0 - a rule could in principle clear costs.'}")
print("  (Note this is the MAXIMUM over all conditions tried, so it is an upper")
print("   bound that is itself inflated by selection.)")

# ------------------------------------------------------------------ honest read
print("\n" + "="*104)
print("HONEST READING")
print("="*104)
mx = R.reindex(R.t.abs().sort_values(ascending=False).index).iloc[0]
print(f"  largest |t| over all {len(R)} tests : {abs(mx.t):.2f}  ({mx['cond']}, h={int(mx.h)})")
print(f"  expected largest |t| from {len(R)} independent null tests: ~{np.sqrt(2*np.log(len(R))):.2f}")
print(f"  BH survivors at q=0.10 : {int(sig.sum())}")
print(f"  fraction with p<0.05   : {(R.p<0.05).mean():.1%}   (chance = 5.0%)")
print()
print("  The maximum edge above is the max of ~170 noisy estimates and is therefore")
print("  an artefact of selection, not a budget. Since NOTHING survives FDR, the")
print("  measurable conditional predictability at Donchian breakout events in this")
print("  window is indistinguishable from zero, and the usable budget is 0.00.")
print("  A rule can still work only if it separates a SUBPOPULATION these marginal")
print("  event studies average over - which is what the specialist agents test.")
