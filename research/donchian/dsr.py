"""STAGE 7 - DEFLATED SHARPE RATIO (Bailey & Lopez de Prado).

Restates a Sharpe as a probability, given three things a raw Sharpe ignores:
  - the NUMBER of configurations evaluated across the whole study
  - the cross-sectional DISPERSION of those trials' Sharpes
  - the SKEW and KURTOSIS of the realised return stream

Also reports the Minimum Track Record Length: how long a record would have to be
before this Sharpe is distinguishable from zero at 95%. That is usually the most
sobering number in a study like this.

Research block only. Applied to the ADX candidate before the holdout is opened,
so the reveal can be read against an honest prior rather than a raw p-value.
"""
import numpy as np, pandas as pd
from scipy import stats as sps
from engine import true_range, atr
import lab

def adx(dfx, n_=14):
    hh, ll, cc = dfx.high.values, dfx.low.values, dfx.close.values
    up = np.diff(hh, prepend=hh[0]); dn = -np.diff(ll, prepend=ll[0])
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = true_range(hh, ll, cc)
    def wil(x, p):
        out = np.empty_like(x); out[0] = x[0]; a = 1.0/p
        for i in range(1, len(x)): out[i] = a*x[i] + (1-a)*out[i-1]
        return out
    a_ = wil(tr, n_); pdi = 100*wil(plus, n_)/(a_+1e-12); mdi = 100*wil(minus, n_)/(a_+1e-12)
    return wil(100*np.abs(pdi-mdi)/(pdi+mdi+1e-12), n_)

EULER = 0.5772156649

def expected_max_sharpe(n_trials, sd_trials):
    """E[max Sharpe] over n independent trials with dispersion sd, under a null
    of zero true Sharpe. This is the bar a winner must clear just to be notable."""
    if n_trials < 2: return 0.0
    z1 = sps.norm.ppf(1 - 1.0/n_trials)
    z2 = sps.norm.ppf(1 - 1.0/(n_trials*np.e))
    return sd_trials * ((1-EULER)*z1 + EULER*z2)

def deflated_sharpe(returns, n_trials, sd_trials, freq=1.0):
    r = np.asarray(returns, float); n = len(r)
    sr = r.mean()/r.std(ddof=1)
    g3 = sps.skew(r); g4 = sps.kurtosis(r, fisher=False)
    sr0 = expected_max_sharpe(n_trials, sd_trials)
    denom = np.sqrt(1 - g3*sr + (g4-1)/4.0*sr**2)
    if denom <= 0 or not np.isfinite(denom): return np.nan, sr, sr0, np.nan
    z = (sr - sr0)*np.sqrt(n-1)/denom
    return float(sps.norm.cdf(z)), float(sr), float(sr0), float(denom)

def mintrl(returns, target_sr=0.0, alpha=0.05):
    r = np.asarray(returns, float)
    sr = r.mean()/r.std(ddof=1)
    g3 = sps.skew(r); g4 = sps.kurtosis(r, fisher=False)
    if sr <= target_sr: return np.inf
    return 1 + (1 - g3*sr + (g4-1)/4.0*sr**2) * (sps.norm.ppf(1-alpha)/(sr-target_sr))**2

SYM = "NAS"
df, w, res = lab.research(SYM)
tod, sess = df.tod.values, df.sess.values
A = adx(df, 14); is7 = (tod == 420)
mA = dict(zip(sess[is7], A[is7]))
at7 = np.array([mA.get(s, np.nan) for s in sess])

print("="*100)
print("STAGE 7 - DEFLATED SHARPE, research block, ADX candidate")
print("="*100)

# --- build the trial universe actually searched, to measure trial dispersion
trials = []
for n_e in (5, 10, 20, 40, 80):
    idx, side, _ = lab.signals(df, n_e)
    ok = tod[idx] > 420
    for thr in (0, 14, 18, 22, 26, 30, 34, 38):
        for sm, tm in ((1.0,1.5),(1.5,2.0),(2.0,2.0),(2.5,3.0)):
            m = ok & ((at7[idx] > thr) if thr else True)
            if m.sum() < 60: continue
            bk = lab.book(SYM, idx[m], side[m], stop_mult=sm, targ_mult=tm)
            bk = bk[np.isin(bk.sig_bar, np.where(res)[0])]
            if len(bk) < 60: continue
            s_ = bk.net.values.std(ddof=1)
            if s_ > 0: trials.append(bk.net.values.mean()/s_)
trials = np.array(trials)
N_TRIALS = len(trials)
SD_TRIALS = trials.std(ddof=1)
print(f"  trial universe actually evaluated here : {N_TRIALS} configurations")
print(f"  cross-sectional sd of trial Sharpes    : {SD_TRIALS:.4f}  (per trade)")
print(f"  max trial Sharpe observed              : {trials.max():.4f}")
print(f"  E[max Sharpe] under a zero-edge null   : {expected_max_sharpe(N_TRIALS, SD_TRIALS):.4f}")
print("  If the observed max is not clearly above the null's expected max, the")
print("  winner is what a search of this size produces from nothing.\n")

# --- the candidate itself, at several honest trial counts
idx, side, _ = lab.signals(df, 20)
m = (at7[idx] > 30) & (tod[idx] > 420)
bk = lab.book(SYM, idx[m], side[m], stop_mult=1.5, targ_mult=2.0)
bk = bk[np.isin(bk.sig_bar, np.where(res)[0])]
r = bk.net.values
print(f"  CANDIDATE: Donchian n=20, ADX(14)@07:00>30, stop 1.5 / targ 2.0")
print(f"    n trades {len(r):,}   mean {r.mean():+.3f} pts   sd {r.std(ddof=1):.2f}")
print(f"    per-trade Sharpe {r.mean()/r.std(ddof=1):.4f}   skew {sps.skew(r):+.3f}"
      f"   kurtosis {sps.kurtosis(r, fisher=False):.2f}")
print()
print(f"    {'trials assumed':>16} {'E[max SR] null':>15} {'DSR':>10}  reading")
for nt, lbl in ((N_TRIALS, f"{N_TRIALS} (this file)"), (238, "238 (trend agent)"),
                (280, "280 (whole family)"), (1000, "1000 (pessimistic)")):
    dsr, sr, sr0, _ = deflated_sharpe(r, nt, SD_TRIALS)
    verdict = "survives" if dsr > 0.95 else ("marginal" if dsr > 0.90 else "does NOT survive")
    print(f"    {lbl:>16} {sr0:>15.4f} {dsr:>10.4f}  {verdict}")
print()
mtrl = mintrl(r)
print(f"    Minimum Track Record Length at 95%: {mtrl:,.0f} trades")
print(f"    The candidate has {len(r):,}. At ~{len(r)/ (2747*0.65) * 252:.0f} trades a year that is"
      f" {mtrl/max(len(r)/((2747*0.65)/252),1):,.1f} years of live trading")
print("    before the Sharpe is distinguishable from zero at 95% confidence.")
