"""Is my 'high volatility hurts these breakouts' claim an EPISODE?

The volatility agent killed its own ATR-percentile regime finding by showing the
top-decile damage is concentrated: 59% of the loss in five months, absent
2016-2019, absent on US30. I made a similar claim from adx_confound.py, where a
matched-selectivity ATR gate was -3.82 excess on NAS and -6.29 on US30.

The agent's critique may or may not apply to my cut, which used a ~28% quantile
rather than a decile. Run the same episode test on MY numbers rather than
assuming either way.
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
    hi_atr = tp7[idx] > thr

    bk = lab.book(SYM, idx[hi_atr], side[hi_atr], stop_mult=1.5, targ_mult=2.0)
    bk = bk[np.isin(bk.sig_bar, np.where(res)[0])].reset_index(drop=True)
    ts = df.ts.values[bk.sig_bar.values]
    ym = pd.Series(pd.to_datetime(ts)).dt.to_period("M")
    net = bk.net.values

    print("="*96)
    print(f"{SYM}: is the HIGH-ATR damage an episode?  (n={len(bk):,}, total {net.sum():+,.0f} pts)")
    print("="*96)
    bym = pd.Series(net).groupby(ym.values).sum().sort_values()
    tot = net.sum()
    worst5 = bym.head(5)
    print(f"  worst 5 months contribute {worst5.sum():+,.0f} of {tot:+,.0f}"
          f"  = {worst5.sum()/tot*100 if tot!=0 else 0:.0f}% of the loss")
    print("    " + "  ".join(f"{k}:{v:+,.0f}" for k, v in worst5.items()))
    yr = pd.Series(net).groupby(pd.Series(pd.to_datetime(ts)).dt.year.values)
    print("  by year:  " + "  ".join(f"{y}:{v.sum():+,.0f}(n{len(v)})" for y, v in yr))
    early = pd.Series(pd.to_datetime(ts)).dt.year.values <= 2019
    print(f"  2016-2019: n={early.sum():>4} exp={net[early].mean():+7.2f}"
          f"   |   2020+: n={(~early).sum():>4} exp={net[~early].mean():+7.2f}")
    # drop the worst 5 months and re-measure
    keep = ~ym.isin(worst5.index).values
    print(f"  dropping those 5 months: n={keep.sum():,} exp={net[keep].mean():+.2f}"
          f"   (was {net.mean():+.2f})")
    print()
