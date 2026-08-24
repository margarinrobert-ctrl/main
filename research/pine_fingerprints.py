import sys; sys.path.insert(0,'research')
import numpy as np
from bos_choch import run, SPECS

# The Pine hardcoded $2.00 per ORDER -> $4.00 round turn, regardless of contract.
SPECS['MNQ'] = dict(SPECS['NQ']); SPECS['MNQ']['pv'] = 2.0        # comm stays 4.0
SPECS['MNQ_fair'] = dict(SPECS['NQ']); SPECS['MNQ_fair']['pv'] = 2.0; SPECS['MNQ_fair']['comm'] = 0.4

def show(tag, sym, nb, am):
    _,_,_,rp,_,_,_,_ = run(minutes=30, session='rth_0930_1600', min_ema_dist=1.0,
                           n_bos=nb, atr_mult=am, symbol=sym)
    w=rp[rp>0]; l=rp[rp<=0]; gp,gl=w.sum(),-l.sum()
    comm = SPECS[sym]['comm']*len(rp)
    print(f"{tag:<34} n={len(rp):<4} net ${rp.sum():>9,.0f}  PF {gp/gl:>5.2f}  win {100*len(w)/len(rp):>5.1f}%"
          f"  avgW ${w.mean():>7,.0f}  avgL ${l.mean():>7,.0f}  comm ${comm:,.0f} = {100*comm/gp:>5.2f}% of gross profit")

print("--- tested spec (nBos 2, stop 2.0 x ATR) ---")
for s in ('NQ','MNQ','MNQ_fair'): show(s, s, 2, 2.0)
print("\n--- user's apparent spec (nBos 1, stop 1.0 x ATR) ---")
for s in ('NQ','MNQ','MNQ_fair'): show(s, s, 1, 1.0)
