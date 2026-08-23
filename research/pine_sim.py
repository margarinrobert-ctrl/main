"""Replicate the PINE control flow literally, then diff against the reference engine.

Pine semantics modelled:
  - strategy.position_size reflects the position at the START of the bar; an entry placed on bar i
    is not visible until bar i+1.
  - strategy.close() on bar i executes at the open of bar i+1.
  - strategy.exit(stop=) is a resting order checked intrabar.
  - the script's statement ORDER is: entry block, then stop block, then CHoCH block.
"""
import sys; sys.path.insert(0,'research')
import numpy as np
from bos_choch import prep, run, SPECS

d = prep(30)
o,h,l,c = d['o'],d['h'],d['l'],d['c']
sess, mod = d['sess'], d['mod']
ph, pl, ema_, atr_ = d['ph'], d['pl'], d['ema'], d['atr']
n = len(c)
S = SPECS['NQ']; pv=S['pv']; tick=S['tick']
ec = (S['spread_t']+S['slip_t'])*tick; se = S['stop_slip_t']*tick; comm=S['comm']
import os
ATRM, NBOS, MD = float(os.environ.get("AM",2.0)), int(os.environ.get("NB",2)), 1.0
tradeable = (mod>=570)&(mod<960)
entry_ok  = (mod>=570)&(mod<930)      # "0930-1530" -> last entry bar 15:00

pos=0; entry=0.0; stop=np.nan; risk=0.0
bias=0; run_=0; brokeHi=np.nan; brokeLo=np.nan
atrAtSignal=np.nan; stopLevel=np.nan
pending=0            # order placed, fills next bar
pnl=[]; why=[]
for i in range(1,n):
    # --- fill any pending order at THIS bar's open (Pine fills at next bar open) ---
    if pending!=0 and pos==0:
        pos=pending; entry=o[i]; pending=0
        stopLevel = entry - pos*ATRM*atrAtSignal
        risk = ATRM*atrAtSignal
    # --- resting stop, checked intrabar ---
    if pos!=0 and not np.isnan(stopLevel):
        hit = (l[i]<=stopLevel) if pos==1 else (h[i]>=stopLevel)
        if hit:
            px = o[i] if ((pos==1 and o[i]<stopLevel) or (pos==-1 and o[i]>stopLevel)) else stopLevel
            px += -se if pos==1 else se
            g = pos*(px-entry)
            pnl.append(g*pv - comm - 2*ec*pv); why.append(1)
            pos=0; stopLevel=np.nan
    # --- structure on this bar's close ---
    bosUp = (not np.isnan(ph[i])) and c[i]>ph[i] and (np.isnan(brokeHi) or ph[i]!=brokeHi)
    bosDn = (not np.isnan(pl[i])) and c[i]<pl[i] and (np.isnan(brokeLo) or pl[i]!=brokeLo)
    if bosUp: brokeHi=ph[i]
    if bosDn: brokeLo=pl[i]
    if bosUp:
        if bias==1: run_+=1
        else: bias=1; run_=1
    if bosDn:
        if bias==-1: run_+=1
        else: bias=-1; run_=1
    a = atr_[i]
    ready = (a>0) and not np.isnan(a) and not np.isnan(ema_[i])
    far = (MD<=0) or (ready and abs(c[i]-ema_[i])>=MD*a)
    longSig  = bosUp and run_>=NBOS and ready and far and c[i]>ema_[i] and entry_ok[i]
    shortSig = bosDn and run_>=NBOS and ready and far and c[i]<ema_[i] and entry_ok[i]
    # --- PINE ORDER: entry block first (uses position_size = state at bar start) ---
    if pos==0 and pending==0 and (longSig or shortSig):
        atrAtSignal=a; pending = 1 if longSig else -1
    # --- CHoCH block, AFTER the entry block, guarded on position_size ---
    if pos!=0 and ((pos==1 and bosDn) or (pos==-1 and bosUp)):
        if i+1<n:
            g = pos*(o[i+1]-entry)
            pnl.append(g*pv - comm - 2*ec*pv); why.append(2)
            pos=0; stopLevel=np.nan
pnl=np.array(pnl); why=np.array(why)
print(f"  PINE-SEMANTICS sim : {len(pnl)} trades  ${pnl.sum():>10,.0f}  win {100*(pnl>0).mean():.1f}%"
      f"   stops {100*(why==1).mean():.1f}%  CHoCH {100*(why==2).mean():.1f}%")
side,ti,to,rp,g2,r2,w2,dl = run(minutes=30, session='rth_0930_1600', min_ema_dist=1.0, n_bos=2)
print(f"  REFERENCE engine   : {len(rp)} trades  ${rp.sum():>10,.0f}  win {100*(rp>0).mean():.1f}%"
      f"   stops {100*(w2==1).mean():.1f}%  CHoCH {100*(w2==2).mean():.1f}%")
