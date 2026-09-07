import sys; sys.path.insert(0,'research')
import numpy as np
from bos_choch import prep, run, SPECS
d=prep(30); o,h,l,c=d['o'],d['h'],d['l'],d['c']; sess,mod=d['sess'],d['mod']
ph,pl,ema_,atr_=d['ph'],d['pl'],d['ema'],d['atr']; n=len(c)
S=SPECS['NQ']; pv=S['pv']; tick=S['tick']
ec=(S['spread_t']+S['slip_t'])*tick; se=S['stop_slip_t']*tick; comm=S['comm']
ATRM,NBOS,MD=2.0,2,1.0
trad=(mod>=570)&(mod<960)

def sim(gate, same_bar_reversal):
    pos=0;entry=0.;stopL=np.nan;bias=0;rn=0;bh=np.nan;bl=np.nan
    aSig=np.nan;pend=0;pnl=[]
    for i in range(1,n):
        new_sess = sess[i]!=sess[i-1]
        if pend!=0 and pos==0:
            pos=pend; entry=o[i]; pend=0; stopL=entry-pos*ATRM*aSig
        if pos!=0 and not np.isnan(stopL):
            hit=(l[i]<=stopL) if pos==1 else (h[i]>=stopL)
            if hit:
                px=o[i] if ((pos==1 and o[i]<stopL) or (pos==-1 and o[i]>stopL)) else stopL
                px += -se if pos==1 else se
                pnl.append(pos*(px-entry)*pv-comm-2*ec*pv); pos=0; stopL=np.nan
        bU=(not np.isnan(ph[i])) and c[i]>ph[i] and (np.isnan(bh) or ph[i]!=bh)
        bD=(not np.isnan(pl[i])) and c[i]<pl[i] and (np.isnan(bl) or pl[i]!=bl)
        if bU: bh=ph[i]
        if bD: bl=pl[i]
        if bU: bias,rn=(1,rn+1) if bias==1 else (1,1)
        if bD: bias,rn=(-1,rn+1) if bias==-1 else (-1,1)
        if same_bar_reversal and pos!=0 and ((pos==1 and bD) or (pos==-1 and bU)) and i+1<n:
            pnl.append(pos*(o[i+1]-entry)*pv-comm-2*ec*pv); pos=0; stopL=np.nan
        a=atr_[i]; ready=(a>0) and not np.isnan(a) and not np.isnan(ema_[i])
        if gate=='engine': ok = i+1<n and trad[i] and trad[i+1] and not new_sess
        else:              ok = (mod[i]>=570) and (mod[i]<930)
        far=(MD<=0) or (ready and abs(c[i]-ema_[i])>=MD*a)
        if pos==0 and pend==0 and ok and ready and far:
            if bU and rn>=NBOS and c[i]>ema_[i]: aSig=a; pend=1
            elif bD and rn>=NBOS and c[i]<ema_[i]: aSig=a; pend=-1
        if (not same_bar_reversal) and pos!=0 and ((pos==1 and bD) or (pos==-1 and bU)) and i+1<n:
            pnl.append(pos*(o[i+1]-entry)*pv-comm-2*ec*pv); pos=0; stopL=np.nan
    return np.array(pnl)

for gate in ('pine','engine'):
    for rev in (False,True):
        p=sim(gate,rev); w=p[p>0]
        print(f"gate={gate:<7} same-bar-reversal={str(rev):<6} n={len(p):<4} net ${p.sum():>9,.0f} "
              f" PF {w.sum()/-p[p<=0].sum():>5.2f}  win {100*len(w)/len(p):>5.1f}%")
_,_,_,rp,_,_,_,_ = run(minutes=30, session='rth_0930_1600', min_ema_dist=1.0, n_bos=2)
w=rp[rp>0]
print(f"{'REFERENCE ENGINE':<32} n={len(rp):<4} net ${rp.sum():>9,.0f}  PF {w.sum()/-rp[rp<=0].sum():>5.2f}  win {100*len(w)/len(rp):>5.1f}%")
