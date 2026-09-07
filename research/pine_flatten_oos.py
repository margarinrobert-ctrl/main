import sys; sys.path.insert(0,'research')
import numpy as np
from bos_choch import prep, SPECS

d = prep(30)
o,h,l,c = d['o'],d['h'],d['l'],d['c']; sess,mod = d['sess'],d['mod']
ph,pl,ema_,atr_ = d['ph'],d['pl'],d['ema'],d['atr']
n=len(c); S=SPECS['NQ']; pv=S['pv']; tick=S['tick']
ec=(S['spread_t']+S['slip_t'])*tick; se=S['stop_slip_t']*tick; comm=S['comm']
ATRM,NBOS,MD = 2.0,2,1.0
entry_ok=(mod>=570)&(mod<930)

def sim(flatten):
    pos=0;entry=0.0;stopL=np.nan;bias=0;run_=0;bh=np.nan;bl=np.nan
    aSig=np.nan;pend=0;pnl=[];ent=[]; ei=0
    for i in range(1,n):
        if flatten and pos!=0 and sess[i]!=sess[i-1]:
            pnl.append(pos*(o[i]-entry)*pv-comm-2*ec*pv); ent.append(ei); pos=0; stopL=np.nan
        if pend!=0 and pos==0:
            pos=pend; entry=o[i]; ei=i; pend=0; stopL=entry-pos*ATRM*aSig
        if pos!=0 and not np.isnan(stopL):
            hit=(l[i]<=stopL) if pos==1 else (h[i]>=stopL)
            if hit:
                px=o[i] if ((pos==1 and o[i]<stopL) or (pos==-1 and o[i]>stopL)) else stopL
                px += -se if pos==1 else se
                pnl.append(pos*(px-entry)*pv-comm-2*ec*pv); ent.append(ei); pos=0; stopL=np.nan
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
            pnl.append(pos*(o[i+1]-entry)*pv-comm-2*ec*pv); ent.append(ei); pos=0; stopL=np.nan
    return np.array(pnl), np.array(ent)

usess = np.unique(sess); cut = usess[int(0.65*len(usess))]      # same 0.65 split used elsewhere
print(f"research: first {int(0.65*len(usess))} sessions   LOCKED: {len(usess)-int(0.65*len(usess))} after\n")
print(f"{'variant':<26}{'block':<10}{'n':>5}{'net $':>11}{'PF':>7}{'win%':>7}{'$/trade':>10}{'Sharpe':>8}")
for tag,f in (("hold overnight",False), ("FLAT at 16:00",True)):
    p,e = sim(f); blk = sess[e] < cut
    for bname, m in (("research", blk), ("LOCKED", ~blk)):
        x=p[m]; w=x[x>0]; ls=x[x<=0]
        # daily Sharpe from per-session sums
        s=sess[e][m]; dsum=np.array([x[s==u].sum() for u in np.unique(s)])
        sh = dsum.mean()/dsum.std()*np.sqrt(252) if dsum.std()>0 else 0
        print(f"{tag:<26}{bname:<10}{len(x):>5}{x.sum():>11,.0f}{w.sum()/-ls.sum():>7.2f}"
              f"{100*len(w)/len(x):>7.1f}{x.mean():>10,.0f}{sh:>8.2f}")
