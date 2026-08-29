"""PHASE 3 on the ADX@07:00 gate - walk-forward, the test nobody has run.

The trend agent established: circular-shift p=0.0006, jackknife-stable across
all 7 year-drops, sign-replicated on US30 at n=20 and n=40, and a STEP at
ADX 30 rather than a gradient. Cost stress: +2.25 at 1x, -0.07 at 2x.

Walk-forward asks the question none of those do: if you had to CHOOSE the ADX
threshold from data available at the time, re-choosing it as you roll forward,
would you have made money? That includes the cost of having to pick, which a
single in-sample fit hides entirely.

Research block only.
"""
import numpy as np, pandas as pd
from engine import atr, ema, donchian, true_range
import lab, robust

SYM = "NAS"
df, w, res = lab.research(SYM)
c, h, l = df.close.values, df.high.values, df.low.values
tod, sess = df.tod.values, df.sess.values
n = len(df)

def adx(dfx, n_=14):
    """Wilder ADX, causal."""
    hh, ll, cc = dfx.high.values, dfx.low.values, dfx.close.values
    up = np.diff(hh, prepend=hh[0]); dn = -np.diff(ll, prepend=ll[0])
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = true_range(hh, ll, cc)
    def wil(x, p):
        out = np.empty_like(x); out[0] = x[0]; a = 1.0/p
        for i in range(1, len(x)): out[i] = a*x[i] + (1-a)*out[i-1]
        return out
    atr_ = wil(tr, n_); pdi = 100*wil(plus, n_)/(atr_+1e-12); mdi = 100*wil(minus, n_)/(atr_+1e-12)
    dx = 100*np.abs(pdi-mdi)/(pdi+mdi+1e-12)
    return wil(dx, n_)

ADX = adx(df, 14)
# the 07:00 reading, broadcast to the whole session - a PRE-WINDOW state
at7 = np.full(n, np.nan)
is7 = (tod == 420)
s7 = sess[is7]; v7 = ADX[is7]
m7 = dict(zip(s7, v7))
at7 = np.array([m7.get(s, np.nan) for s in sess])

print("="*100)
print("LEAKAGE RE-CHECK: is the 07:00 ADX reading knowable at 07:00?")
print("  ADX(14) is Wilder-smoothed over bars <= the 07:00 bar, and the 07:00 bar")
print("  CLOSES at 07:15. A trade entered at 07:15 or later may use it; a trade")
print("  entered in the 07:00 bar itself may NOT.")
idx0, side0, _ = lab.signals(df, 20)
early = (tod[idx0] == 420).sum()
print(f"  triggers at tod==420 (the 07:00 bar itself): {early} of {len(idx0)}")
print("  -> those must be excluded; the agent's window starts at 420 so they are")
print("     included unless handled. Testing BOTH ways below.\n")

def build(thr, n_entry=20, drop_first_bar=True):
    idx, side, _ = lab.signals(df, n_entry)
    keep = at7[idx] > thr
    if drop_first_bar:
        keep &= (tod[idx] > 420)
    return idx[keep], side[keep]

print("="*100)
print("A. Does dropping the 07:00 bar itself change the result?")
print("="*100)
for thr in (26, 30, 34):
    for drop in (False, True):
        i_, s_ = build(thr, 20, drop)
        g, _ = lab.sig_gate(SYM, i_, s_, stop_mult=1.5, targ_mult=2.0,
                            n_draws=400, quiet=True)
        print(f"  ADX>{thr}  drop_07:00_bar={str(drop):<5}  n={g['n']:>4}  exp={g['exp']:>+6.2f}"
              f"  excess={g['excess']:>+6.2f}  z={g['z']:>+5.2f}  p={g['p']:.4f}")

print("\n" + "="*100)
print("B. WALK-FORWARD: re-choose the ADX threshold on each training window")
print("="*100)
GRID = [14, 18, 22, 26, 30, 34, 38]
def bf(p):
    i_, s_ = build(p, 20, True)
    return i_, s_, dict(stop_mult=1.5, targ_mult=2.0, max_hold=16, flat_tod=660)
for tr_s, te_s in ((250, 80), (400, 120), (150, 60)):
    print(f"\n  --- train {tr_s} / test {te_s} sessions ---")
    oos, fd = robust.walk_forward(SYM, bf, GRID, train_sess=tr_s, test_sess=te_s, mask=res)
    if len(oos):
        print(f"    stitched OOS: n={len(oos):,}  exp={oos.net.mean():+.2f} pts"
              f"  total={oos.net.sum():+,.0f} pts")

print("\n" + "="*100)
print("C. MONTE CARLO on the fixed ADX>30 book")
print("="*100)
i_, s_ = build(30, 20, True)
bk = lab.book(SYM, i_, s_, stop_mult=1.5, targ_mult=2.0)
bk = bk[np.isin(bk.sig_bar, np.where(res)[0])]
mc = robust.monte_carlo(bk, n=4000, seed=1)
for k, v in mc.items():
    print(f"    {k:<24} {v}")
