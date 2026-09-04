"""How independent is US30 confirmation of a NAS result?

If the two instruments' 15m returns and breakout events are near-identical, then
"it works on both" is ONE observation dressed as two, and must not be counted as
independent evidence. Measure it before relying on it.
"""
import numpy as np, pandas as pd
from engine import donchian, atr
import lab, data as D

na = D.load("NAS"); us = D.load("US30")
j = na[["ts","close","high","low","tod","sess"]].merge(
    us[["ts","close","high","low"]], on="ts", suffixes=("_n","_u"))
print("="*96)
print("INDEPENDENCE OF THE TWO INSTRUMENTS")
print("="*96)
print(f"  overlapping 15m bars: {len(j):,}")
rn = np.diff(np.log(j.close_n.values)); ru = np.diff(np.log(j.close_u.values))
print(f"  corr(15m log returns)            : {np.corrcoef(rn,ru)[0,1]:.4f}")
w = (j.tod.values[1:] >= 420) & (j.tod.values[1:] < 660)
print(f"  corr within 07:00-11:00 window   : {np.corrcoef(rn[w],ru[w])[0,1]:.4f}")
d = j.groupby(j.ts.dt.normalize()).agg(n=("close_n","last"), u=("close_u","last"))
print(f"  corr(daily returns)              : {np.corrcoef(np.diff(np.log(d.n)),np.diff(np.log(d.u)))[0,1]:.4f}")

# breakout event co-occurrence
print("\n  Donchian breakout co-occurrence inside the window:")
for L in (10, 20, 40):
    hn, ln_ = donchian(na, L); hu, lu = donchian(us, L)
    bn = pd.Series((na.close.values > hn).astype(float), index=na.ts)
    bu = pd.Series((us.close.values > hu).astype(float), index=us.ts)
    m = pd.concat([bn.rename("n"), bu.rename("u")], axis=1, sort=False).dropna()
    m = m[(m.index.hour*60+m.index.minute >= 420) & (m.index.hour*60+m.index.minute < 660)]
    both = ((m.n==1)&(m.u==1)).sum(); anyb = ((m.n==1)|(m.u==1)).sum()
    print(f"    L={L:<3} NAS up-breaks {int(m.n.sum()):>6,}  US30 up-breaks {int(m.u.sum()):>6,}"
          f"  both {both:>6,}  Jaccard {both/max(anyb,1):.3f}"
          f"  phi {np.corrcoef(m.n,m.u)[0,1]:.3f}")
print("\n  READING: a Jaccard near 1.0 or phi near 1.0 would mean US30 is a re-run of")
print("  NAS, not a second test. Values in the 0.2-0.5 range mean US30 carries real")
print("  but partial independent information - worth roughly one extra half-test,")
print("  not a full replication.")
