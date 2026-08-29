"""Is the ADX gate really an ATR gate in disguise?

Gated days have median ATR 15.73 against 13.86 ungated, so ADX>30 does select
more volatile sessions. If a pure volatility gate of the SAME selectivity
reproduces the effect, then ATR is the simpler explanation and ADX adds nothing -
which is the whole "does this filter add genuine incremental information" test.

Four arms, all at matched selectivity:
  1. ADX(14)@07:00 > 30                       (the candidate)
  2. ATR percentile @07:00, top 27%           (pure volatility, matched selectivity)
  3. ADX>30 AND high ATR                      (the overlap)
  4. ADX>30 AND *LOW* ATR                     (the decisive cell: if the effect
     survives here, it is NOT volatility)
Plus a conditional test: ADX residualised on ATR.
"""
import numpy as np, pandas as pd
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

for SYM in ("NAS", "US30"):
    df, w, res = lab.research(SYM)
    tod, sess = df.tod.values, df.sess.values
    A = adx(df, 14); a14 = atr(df, 14)
    is7 = (tod == 420)
    mA = dict(zip(sess[is7], A[is7])); mT = dict(zip(sess[is7], a14[is7]))
    at7 = np.array([mA.get(s, np.nan) for s in sess])
    tr7 = np.array([mT.get(s, np.nan) for s in sess])
    # causal ATR percentile: rank the session's 07:00 ATR within the trailing 250 sessions
    su = np.array(sorted(set(sess[is7])))
    vals = np.array([mT[s] for s in su])
    pct = np.full(len(su), np.nan)
    for i in range(250, len(su)):
        pct[i] = (vals[i-250:i] < vals[i]).mean()
    mP = dict(zip(su, pct))
    tp7 = np.array([mP.get(s, np.nan) for s in sess])

    idx, side, _ = lab.signals(df, 20)
    ok = (tod[idx] > 420) & ~np.isnan(at7[idx]) & ~np.isnan(tp7[idx])
    idx, side = idx[ok], side[ok]
    hi_adx = at7[idx] > 30
    sel = hi_adx.mean()
    thr_atr = np.nanquantile(tp7[idx], 1 - sel)      # matched selectivity
    hi_atr = tp7[idx] > thr_atr

    print("\n" + "="*104)
    print(f"{SYM}: is ADX>30 just a volatility gate?  (matched selectivity {sel:.0%})")
    print("="*104)
    base, _ = lab.sig_gate(SYM, idx, side, stop_mult=1.5, targ_mult=2.0, n_draws=300, quiet=True)
    print(f"  {'arm':<34} {'sel':>6} {'n':>6} {'exp':>8} {'excess':>8} {'z':>7} {'p':>7} {'wr':>6}")
    print(f"  {'ungated baseline':<34} {1.0:>6.2f} {base['n']:>6,} {base['exp']:>+8.2f}"
          f" {base['excess']:>+8.2f} {base['z']:>+7.2f} {base['p']:>7.4f} {base['wr']:>6.1%}")
    arms = [
        ("ADX>30 (the candidate)",      hi_adx),
        ("ATR pct top (matched sel)",   hi_atr),
        ("ADX>30 AND high ATR",         hi_adx & hi_atr),
        ("ADX>30 AND LOW ATR  <-key",   hi_adx & ~hi_atr),
        ("high ATR AND ADX<=30",        hi_atr & ~hi_adx),
    ]
    for nm, m in arms:
        if m.sum() < 40:
            print(f"  {nm:<34} {m.mean():>6.2f} {m.sum():>6,}   too few"); continue
        g, _ = lab.sig_gate(SYM, idx[m], side[m], stop_mult=1.5, targ_mult=2.0,
                            n_draws=300, quiet=True)
        print(f"  {nm:<34} {m.mean():>6.2f} {g['n']:>6,} {g['exp']:>+8.2f}"
              f" {g['excess']:>+8.2f} {g['z']:>+7.2f} {g['p']:>7.4f} {g['wr']:>6.1%}")
    print(f"  overlap: P(high ATR | ADX>30) = {(hi_atr & hi_adx).sum()/max(hi_adx.sum(),1):.2f}"
          f"   corr(ADX@07, ATRpct@07) = {np.corrcoef(at7[idx], tp7[idx])[0,1]:.3f}")

print("\n" + "="*104)
print("READING: if 'ADX>30 AND LOW ATR' still earns, the gate is not a volatility")
print("proxy. If only 'high ATR' arms earn, ATR is the simpler explanation and the")
print("ADX framing should be dropped in its favour.")
