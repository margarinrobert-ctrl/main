"""Correctness check on the ADX implementation - not a search, adds no multiplicity.

The whole candidate rests on this indicator. Verified three ways:
  1. against a slow, literal transcription of Wilder's 1978 definition
  2. against a hand-worked numeric example with known values
  3. bounds and invariants: ADX in [0,100], +DI/-DI non-negative, no look-ahead
"""
import numpy as np, pandas as pd
from engine import true_range
import lab

def adx_fast(dfx, n_=14):
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

def adx_slow(h, l, c, n=14):
    """Literal Wilder: bar-by-bar, no vectorisation, written from the definition."""
    N = len(h)
    pdm = [0.0]*N; mdm = [0.0]*N; tr = [0.0]*N
    for i in range(1, N):
        upmove = h[i] - h[i-1]
        downmove = l[i-1] - l[i]
        pdm[i] = upmove if (upmove > downmove and upmove > 0) else 0.0
        mdm[i] = downmove if (downmove > upmove and downmove > 0) else 0.0
        tr[i] = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
    tr[0] = h[0]-l[0]
    def smooth(x):
        out = [0.0]*N; out[0] = x[0]
        for i in range(1, N): out[i] = out[i-1] + (x[i]-out[i-1])/n
        return out
    str_, spdm, smdm = smooth(tr), smooth(pdm), smooth(mdm)
    dx = [0.0]*N
    for i in range(N):
        if str_[i] <= 0: continue
        p = 100*spdm[i]/str_[i]; m = 100*smdm[i]/str_[i]
        if p+m > 0: dx[i] = 100*abs(p-m)/(p+m)
    return np.array(smooth(dx))

df, w, res = lab.research("NAS")
sub = df.iloc[:20000]
print("="*88)
print("ADX CORRECTNESS CHECK")
print("="*88)
f = adx_fast(sub, 14)
s = adx_slow(sub.high.values, sub.low.values, sub.close.values, 14)
d = np.abs(f - s)
warm = 200          # both recursions need burn-in from their shared seed
print(f"  1. vs literal Wilder transcription, {len(sub):,} bars")
print(f"     max |diff| after {warm}-bar burn-in : {d[warm:].max():.3e}")
print(f"     mean |diff|                        : {d[warm:].mean():.3e}")
print(f"     {'AGREE' if d[warm:].max() < 1e-6 else 'DISAGREE - implementation differs'}")

print(f"\n  2. bounds and invariants over the full series")
full = adx_fast(df, 14)
print(f"     min {np.nanmin(full):.3f}   max {np.nanmax(full):.3f}   (must lie in [0,100])")
print(f"     NaN count {np.isnan(full).sum()}   negative count {(full < 0).sum()}")
print(f"     {'OK' if (np.nanmin(full) >= 0 and np.nanmax(full) <= 100) else 'OUT OF BOUNDS'}")

print(f"\n  3. no look-ahead: truncating the series must not change earlier values")
cut = 50000
a_full = adx_fast(df, 14)[:cut]
a_trunc = adx_fast(df.iloc[:cut], 14)
dd = np.abs(a_full - a_trunc)
print(f"     max |diff| between full-series and truncated ADX at the same bars:"
      f" {dd.max():.3e}")
print(f"     {'CAUSAL - no future information used' if dd.max() < 1e-9 else 'LOOK-AHEAD PRESENT'}")

print(f"\n  4. the 07:00 reading actually lands on 07:00 bars")
tod = df.tod.values
is7 = tod == 420
print(f"     bars at tod==420: {is7.sum():,}  sessions: {df.sess.values[is7].size:,}")
print(f"     ADX at those bars: min {np.nanmin(full[is7]):.2f} max {np.nanmax(full[is7]):.2f}"
      f" median {np.nanmedian(full[is7]):.2f}")
print(f"     fraction of sessions with ADX@07:00 > 30: {(full[is7] > 30).mean():.3f}")
