"""PAIRED test of the entry mechanic - the control-free way to isolate a fill.

The previous run scored the stop-entry book against a matched control that enters
at the next bar's OPEN. That control is not matched to the mechanic, so its
`excess` column was not trustworthy. Corrected here.

Same TRIGGERS, same geometry, same exit walk. The only difference is the fill:
  A: resting STOP at the channel level, filled intrabar on bar i
  B: MARKET at the open of bar i+1
The paired difference isolates the entry mechanic exactly, and needs no control.
"""
import numpy as np, pandas as pd
from engine import simulate, atr, donchian
from scipy import stats as sps
import lab

SYM = "NAS"
df, w, res = lab.research(SYM)
h, l, c = df.high.values, df.low.values, df.close.values
sess, tod = df.sess.values, df.tod.values
COST, SLIP = lab.COST[SYM], lab.SLIP[SYM]


def triggers(n_entry, win=(420, 660)):
    hi, lo = donchian(df, n_entry); a = atr(df, 14)
    ok = (tod >= win[0]) & (tod < win[1]) & ~np.isnan(hi) & ~np.isnan(a) & (a > 0)
    up = ok & (h > hi); dn = ok & (l < lo)
    both = up & dn; up &= ~both; dn &= ~both
    idx = np.where(up | dn)[0]
    side = np.where(up[idx], 1.0, -1.0)
    s_ = sess[idx]; keep = np.concatenate([[True], s_[1:] != s_[:-1]])
    idx, side = idx[keep], side[keep]
    lvl = np.where(side > 0, hi[idx], lo[idx])
    return idx, side, lvl, a


def book(idx, side, entry, a, sm, tm, mh=16, ft=660, charge_bar0=False):
    av = a[idx]
    stop = entry - side * sm * av
    targ = (entry + side * tm * av) if tm > 0 else np.where(side > 0, np.inf, -np.inf)
    tr = simulate(w, idx, side, entry, stop, targ, max_hold=mh, flat_tod=ft, cost_pts=COST)
    if charge_bar0:      # stop-order fills mid-bar: charge bar i's adverse excursion
        sb = tr.sig_bar.values; sd = tr.side.values
        hit = np.where(sd > 0, l[sb] <= tr.stop.values, h[sb] >= tr.stop.values)
        if hit.any():
            tr.loc[hit, "exit"] = tr.loc[hit, "stop"]
            tr.loc[hit, "net"] = sd[hit]*(tr.loc[hit,"exit"]-tr.loc[hit,"entry"]) - COST
            tr.loc[hit, "reason"] = 0
    return tr


print("="*104)
print("PAIRED ENTRY-MECHANIC TEST - identical triggers, only the fill differs")
print(f"  {SYM}, 07:00-11:00 New York, RESEARCH BLOCK ONLY")
print("="*104)
print(f"\n  {'n':>4} {'geom':>9} {'pairs':>6} {'STOP exp':>9} {'OPEN exp':>9} {'paired d':>9}"
      f" {'t':>7} {'p':>8}  {'fill edge':>9}")
allrows = []
for n_e in (10, 20, 40):
    idx, side, lvl, a = triggers(n_e)
    keep = np.isin(idx, np.where(res)[0])
    idx, side, lvl = idx[keep], side[keep], lvl[keep]
    opn = w["opens"][idx, 0]
    ok = ~np.isnan(opn)
    idx, side, lvl, opn = idx[ok], side[ok], lvl[ok], opn[ok]
    fill_edge = float(np.mean(side * (opn - lvl)))   # how much worse the open is
    for sm, tm in ((1.5, 2.0), (2.0, 2.0), (2.5, 2.0)):
        A = book(idx, side, lvl + side*SLIP, a, sm, tm, charge_bar0=True)
        B = book(idx, side, opn + side*SLIP, a, sm, tm, charge_bar0=False)
        m = A.merge(B, on="sig_bar", suffixes=("_a", "_b"))
        d = m.net_a.values - m.net_b.values
        t, p = sps.ttest_1samp(d, 0)
        allrows.append((n_e, sm, tm, len(m), A.net.mean(), B.net.mean(), d.mean(), t, p))
        print(f"  {n_e:>4} {f'{sm}/{tm}':>9} {len(m):>6,} {A.net.mean():>+9.2f} {B.net.mean():>+9.2f}"
              f" {d.mean():>+9.2f} {t:>+7.2f} {p:>8.4f}  {fill_edge:>+9.2f}")

print("\n  `fill edge` = mean(side*(next_open - channel_level)): how many points WORSE")
print("  the next-open fill is than the channel level. Positive means the stop order")
print("  genuinely buys lower / sells higher.")
print("\n" + "="*104)
R = pd.DataFrame(allrows, columns=["n","sm","tm","pairs","stop_exp","open_exp","d","t","p"])
print(f"  paired difference favours the STOP order in {(R.d>0).sum()}/{len(R)} configurations")
print(f"  mean paired difference: {R.d.mean():+.2f} pts/trade")
print(f"  configurations where the stop order is significantly better (p<0.05): {((R.d>0)&(R.p<0.05)).sum()}")
print(f"  configurations where it is significantly WORSE (p<0.05): {((R.d<0)&(R.p<0.05)).sum()}")
print("\n  Both books remain deeply unprofitable in absolute terms; this test only")
print("  asks whether the mechanic is a lever, not whether the family works.")
