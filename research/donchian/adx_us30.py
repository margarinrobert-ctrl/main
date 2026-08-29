"""Cross-instrument test of the ADX mechanism with the threshold FIXED a priori.

The gate was discovered on NAS. US30 is a genuine partial replication: its
breakout events overlap NAS's at only Jaccard 0.23-0.28. Fixing the threshold at
30 - no re-selection, no per-instrument tuning - is the fair test of whether the
MECHANISM transfers, as opposed to whether a tuned number does.

Also asks what the gate actually does: does high pre-window ADX change the
breakout population, or just the market it breaks out into?
"""
import numpy as np, pandas as pd
from engine import true_range, atr, donchian
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

print("="*104)
print("ADX(14)@07:00 > 30 - FIXED threshold, applied unchanged to both instruments")
print("="*104)
for SYM in ("NAS", "US30"):
    df, w, res = lab.research(SYM)
    tod, sess = df.tod.values, df.sess.values
    A = adx(df, 14)
    is7 = (tod == 420)
    m7 = dict(zip(sess[is7], A[is7]))
    at7 = np.array([m7.get(s, np.nan) for s in sess])
    print(f"\n  --- {SYM} ---")
    print(f"  {'n_entry':>7} {'arm':<12} {'n':>6} {'exp':>8} {'ctrl':>8} {'excess':>8} {'z':>7} {'p':>7} {'wr':>6}")
    for n_e in (10, 20, 40, 80):
        idx, side, _ = lab.signals(df, n_e)
        base, _ = lab.sig_gate(SYM, idx, side, stop_mult=1.5, targ_mult=2.0,
                               n_draws=300, quiet=True)
        keep = (at7[idx] > 30) & (tod[idx] > 420)
        if keep.sum() < 40: continue
        g, _ = lab.sig_gate(SYM, idx[keep], side[keep], stop_mult=1.5, targ_mult=2.0,
                            n_draws=300, quiet=True)
        print(f"  {n_e:>7} {'ungated':<12} {base['n']:>6,} {base['exp']:>+8.2f} {base['ctrl']:>+8.2f}"
              f" {base['excess']:>+8.2f} {base['z']:>+7.2f} {base['p']:>7.4f} {base['wr']:>6.1%}")
        print(f"  {'':>7} {'ADX>30':<12} {g['n']:>6,} {g['exp']:>+8.2f} {g['ctrl']:>+8.2f}"
              f" {g['excess']:>+8.2f} {g['z']:>+7.2f} {g['p']:>7.4f} {g['wr']:>6.1%}"
              f"   gap={g['exp']-base['exp']:+.2f}")

print("\n" + "="*104)
print("WHAT DOES THE GATE ACTUALLY SELECT?  (NAS, research block)")
print("="*104)
df, w, res = lab.research("NAS")
tod, sess = df.tod.values, df.sess.values
A = adx(df, 14); a14 = atr(df, 14)
is7 = (tod == 420); m7 = dict(zip(sess[is7], A[is7]))
at7 = np.array([m7.get(s, np.nan) for s in sess])
idx, side, _ = lab.signals(df, 20)
idx = idx[np.isin(idx, np.where(res)[0])]
hi_, lo_ = donchian(df, 20)
c = df.close.values
hot = at7[idx] > 30; cold = (at7[idx] <= 30) & ~np.isnan(at7[idx])
print(f"  {'measure':<38} {'ADX>30':>12} {'ADX<=30':>12}")
rows = [
    ("sessions gated in",            hot.sum(),                cold.sum()),
    ("median ATR(14) at signal",     np.nanmedian(a14[idx[hot]]), np.nanmedian(a14[idx[cold]])),
    ("median channel width / ATR",   np.nanmedian((hi_-lo_)[idx[hot]]/a14[idx[hot]]),
                                     np.nanmedian((hi_-lo_)[idx[cold]]/a14[idx[cold]])),
    ("median break distance / ATR",  np.nanmedian(np.abs(c[idx[hot]]-np.where(side[:len(idx)][hot]>0,hi_[idx[hot]],lo_[idx[hot]]))/a14[idx[hot]]),
                                     np.nanmedian(np.abs(c[idx[cold]]-np.where(side[:len(idx)][cold]>0,hi_[idx[cold]],lo_[idx[cold]]))/a14[idx[cold]])),
    ("mean signal minute-of-day",    np.mean(tod[idx[hot]]),   np.mean(tod[idx[cold]])),
    ("long fraction",                np.mean(side[:len(idx)][hot]>0), np.mean(side[:len(idx)][cold]>0)),
]
for nm, a_, b_ in rows:
    print(f"  {nm:<38} {a_:>12.3f} {b_:>12.3f}")
print("\n  If the two columns look alike, the gate is not changing WHICH breakouts")
print("  are taken - it is selecting the days on which breakouts pay.")
