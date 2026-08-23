import sys, os; sys.path.insert(0,'research')
import numpy as np
from bos_choch import prep, run, SPECS

d = prep(30)
o,h,l,c = d['o'],d['h'],d['l'],d['c']; sess,mod = d['sess'],d['mod']
ph,pl,ema_,atr_ = d['ph'],d['pl'],d['ema'],d['atr']
n=len(c); S=SPECS['NQ']; pv=S['pv']; tick=S['tick']
ec=(S['spread_t']+S['slip_t'])*tick; se=S['stop_slip_t']*tick; comm=S['comm']
ATRM,NBOS,MD = 2.0,2,1.0
entry_ok=(mod>=570)&(mod<930)

def sim(flatten):
    pos=0;entry=0.0;stopL=np.nan;bias=0;run_=0;bh=np.nan;bl=np.nan
    aSig=np.nan;pend=0;pnl=[];why=[]
    for i in range(1,n):
        new_sess = sess[i]!=sess[i-1]
        if flatten and pos!=0 and new_sess:          # force flat at the close (fill next open)
            g=pos*(o[i]-entry); pnl.append(g*pv-comm-2*ec*pv); why.append(3); pos=0; stopL=np.nan
        if pend!=0 and pos==0:
            pos=pend; entry=o[i]; pend=0; stopL=entry-pos*ATRM*aSig
        if pos!=0 and not np.isnan(stopL):
            hit=(l[i]<=stopL) if pos==1 else (h[i]>=stopL)
            if hit:
                px=o[i] if ((pos==1 and o[i]<stopL) or (pos==-1 and o[i]>stopL)) else stopL
                px += -se if pos==1 else se
                g=pos*(px-entry); pnl.append(g*pv-comm-2*ec*pv); why.append(1); pos=0; stopL=np.nan
        bU=(not np.isnan(ph[i])) and c[i]>ph[i] and (np.isnan(bh) or ph[i]!=bh)
        bD=(not np.isnan(pl[i])) and c[i]<pl[i] and (np.isnan(bl) or pl[i]!=bl)
        if bU: bh=ph[i]
        if bD: bl=pl[i]
        if bU: bias,run_=(1,run_+1) if bias==1 else (1,1)
        if bD: bias,run_=(-1,run_+1) if bias==-1 else (-1,1)
        a=atr_[i]; ready=(a>0) and not np.isnan(a) and not np.isnan(ema_[i])
        far=(MD<=0) or (ready and abs(c[i]-ema_[i])>=MD*a)
        lS=bU and run_>=NBOS and ready and far and c[i]>ema_[i] and entry_ok[i]
        sS=bD and run_>=NBOS and ready and far and c[i]<ema_[i] and entry_ok[i]
        if pos==0 and pend==0 and (lS or sS): aSig=a; pend=1 if lS else -1
        if pos!=0 and ((pos==1 and bD) or (pos==-1 and bU)) and i+1<n:
            g=pos*(o[i+1]-entry); pnl.append(g*pv-comm-2*ec*pv); why.append(2); pos=0; stopL=np.nan
    return np.array(pnl), np.array(why)

for tag,f in (("hold overnight (as tested & as the Pine does)",False),
              ("FORCED FLAT at 16:00 each day            ",True)):
    p,w = sim(f); win=p[p>0]; los=p[p<=0]
    print(f"{tag}: n={len(p):<4} net ${p.sum():>9,.0f}  PF {win.sum()/-los.sum():>5.2f}  win {100*len(win)/len(p):>5.1f}%")
