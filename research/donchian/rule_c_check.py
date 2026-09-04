"""Does rule C (ADX>30 AND low ATR) still beat rule B (ADX>30 alone)?

My justification for adding the low-ATR leg was that high-ATR breakouts do badly.
The episode check shows that damage is 74-77% concentrated in five crisis months.
If C's advantage over B rests on those months, the leg is not justified and C
should be dropped from the frozen reveal set rather than defended.

Decision rule, fixed before looking: keep C only if it beats B on BOTH
instruments AFTER excluding each instrument's five worst months.
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
    A = adx(df, 14); a14 = atr(df, 14); is7 = tod == 420
    mA = dict(zip(sess[is7], A[is7])); mT = dict(zip(sess[is7], a14[is7]))
    at7 = np.array([mA.get(s, np.nan) for s in sess])
    su = np.array(sorted(set(sess[is7]))); vals = np.array([mT[s] for s in su])
    pct = np.full(len(su), np.nan)
    for i in range(250, len(su)): pct[i] = (vals[i-250:i] < vals[i]).mean()
    mP = dict(zip(su, pct)); tp7 = np.array([mP.get(s, np.nan) for s in sess])

    idx, side, _ = lab.signals(df, 20)
    ok = (tod[idx] > 420) & ~np.isnan(at7[idx]) & ~np.isnan(tp7[idx])
    idx, side = idx[ok], side[ok]
    selA = (at7[idx] > 30).mean()
    thr = np.nanquantile(tp7[idx], 1 - selA)

    # the five worst months of the HIGH-ATR book, as identified in episode_check
    hb = lab.book(SYM, idx[tp7[idx] > thr], side[tp7[idx] > thr], stop_mult=1.5, targ_mult=2.0)
    hb = hb[np.isin(hb.sig_bar, np.where(res)[0])]
    hm = pd.Series(pd.to_datetime(df.ts.values[hb.sig_bar.values])).dt.to_period("M")
    worst5 = set(pd.Series(hb.net.values).groupby(hm.values).sum().sort_values().head(5).index)

    print("="*98)
    print(f"{SYM}: rule B vs rule C, with and without the five worst high-ATR months")
    print("="*98)
    print(f"  excluded months: {', '.join(str(m) for m in sorted(worst5))}")
    print(f"  {'rule':<28} {'scope':<16} {'n':>5} {'exp':>8} {'excess':>8} {'z':>7} {'p':>7}")
    for nm, m in (("B  ADX>30", at7[idx] > 30),
                  ("C  ADX>30 & low ATR", (at7[idx] > 30) & (tp7[idx] <= thr))):
        bk = lab.book(SYM, idx[m], side[m], stop_mult=1.5, targ_mult=2.0)
        bk = bk[np.isin(bk.sig_bar, np.where(res)[0])].reset_index(drop=True)
        mo = pd.Series(pd.to_datetime(df.ts.values[bk.sig_bar.values])).dt.to_period("M")
        keep = ~mo.isin(worst5).values
        g = lab.gate(SYM, bk, 1.5, 2.0, n_draws=500, quiet=True)
        print(f"  {nm:<28} {'all months':<16} {g['n']:>5,} {g['exp']:>+8.2f}"
              f" {g['excess']:>+8.2f} {g['z']:>+7.2f} {g['p']:>7.4f}")
        g2 = lab.gate(SYM, bk[keep].reset_index(drop=True), 1.5, 2.0, n_draws=500, quiet=True)
        print(f"  {'':<28} {'ex-5 months':<16} {g2['n']:>5,} {g2['exp']:>+8.2f}"
              f" {g2['excess']:>+8.2f} {g2['z']:>+7.2f} {g2['p']:>7.4f}")
    print()
