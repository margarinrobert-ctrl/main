"""Where in the clock does this edge actually live, and can the session be widened?

Motivated by "CHoCH at 8am, 9am" -- i.e. can entries start earlier than 10:00 ET.
Every result is split on the same research/locked boundary used everywhere else.
"""
import sys; sys.path.insert(0,'research')
import numpy as np
from bos_choch import prep

d=prep(30); o,h,l,c=d['o'],d['h'],d['l'],d['c']; sess,mod=d['sess'],d['mod']
ph,pl,ema_,atr_=d['ph'],d['pl'],d['ema'],d['atr']; n=len(c)
tick=0.25; PV=2.0; COMM=1.0; EC=(1.0+1.0)*tick; SE=1.0*tick

def sim(s_start=570, s_end=960, tp_r=2.0, side=0):
    trad=(mod>=s_start)&(mod<s_end)
    pos=0;entry=0.;stopL=np.nan;tp=np.nan;risk=0.;bias=0;rn=0;bh=np.nan;bl=np.nan
    aSig=np.nan;pend=0;pnl=[];ent=[];hr=[];sd=[]
    for i in range(1,n):
        ns=sess[i]!=sess[i-1]
        if pend!=0 and pos==0:
            pos=pend;entry=o[i];pend=0
            risk=2.0*aSig; stopL=entry-pos*risk
            tp=entry+pos*tp_r*risk if tp_r>0 else np.nan
        if pos!=0:
            hit=(l[i]<=stopL) if pos==1 else (h[i]>=stopL)
            won=(not np.isnan(tp)) and ((h[i]>=tp) if pos==1 else (l[i]<=tp))
            if hit:
                px=o[i] if ((pos==1 and o[i]<stopL) or (pos==-1 and o[i]>stopL)) else stopL
                px += -SE if pos==1 else SE
                pnl.append(pos*(px-entry)*PV-2*EC*PV-COMM);pos=0;stopL=np.nan;tp=np.nan
            elif won:
                px=o[i] if ((pos==1 and o[i]>tp) or (pos==-1 and o[i]<tp)) else tp
                pnl.append(pos*(px-entry)*PV-2*EC*PV-COMM);pos=0;stopL=np.nan;tp=np.nan
        bU=(not np.isnan(ph[i])) and c[i]>ph[i] and (np.isnan(bh) or ph[i]!=bh)
        bD=(not np.isnan(pl[i])) and c[i]<pl[i] and (np.isnan(bl) or pl[i]!=bl)
        if bU: bh=ph[i]
        if bD: bl=pl[i]
        if bU: bias,rn=(1,rn+1) if bias==1 else (1,1)
        if bD: bias,rn=(-1,rn+1) if bias==-1 else (-1,1)
        a=atr_[i]; ready=(a>0) and not np.isnan(a) and not np.isnan(ema_[i])
        ok=(i+1<n and trad[i] and trad[i+1] and not ns)
        far=ready and abs(c[i]-ema_[i])>=1.0*a
        if pos==0 and pend==0 and ok and ready and far:
            s_=1 if (bU and rn>=2 and c[i]>ema_[i]) else (-1 if (bD and rn>=2 and c[i]<ema_[i]) else 0)
            if s_ and (side==0 or side==s_):
                aSig=a;pend=s_;ent.append(i);hr.append(mod[i]);sd.append(s_)
    return np.array(pnl),np.array(ent),np.array(hr),np.array(sd)

usess=np.unique(sess); cut=usess[int(0.65*len(usess))]
def blk(p,e):
    if len(p)==0: return f"{0:>5}{0:>9}{'--':>7}{'--':>7}"
    w=p[p>0]; ls=p[p<=0]
    pf=w.sum()/-ls.sum() if len(ls) else 99
    return f"{len(p):>5}{p.sum():>9,.0f}{pf:>7.2f}{100*len(w)/len(p):>7.1f}"

print("="*94)
print("1. HOUR OF DAY — signal bar's clock time, current 09:30-16:00 session, 2R target")
print("="*94)
p,e,hrs,sd = sim()
print(f"{'entry bar (ET)':<18}{'n':>5}{'net $':>9}{'PF':>7}{'win%':>7}{'$/trade':>10}   research | locked")
for m_ in sorted(set(hrs)):
    msk=hrs==m_
    x=p[msk]; ee=e[msk]
    if len(x)<5: continue
    r=sess[ee]<cut
    print(f"{m_//60:02d}:{m_%60:02d}{'':<13}"+blk(x,ee)+f"{x.mean():>10,.0f}   "
          f"${x[r].sum():>7,.0f} | ${x[~r].sum():>7,.0f}")

print(); print("="*94)
print("2. CAN THE SESSION START EARLIER? (pre-market / London overlap)")
print("="*94)
print(f"{'session (ET)':<26}{'RESEARCH':>28}   |{'LOCKED':>28}")
print(f"{'':<26}{'n':>5}{'net $':>9}{'PF':>7}{'win%':>7}   |{'n':>7}{'net $':>9}{'PF':>7}{'win%':>7}")
for st,en,tag in ((570,960,"09:30-16:00  (current)"),
                  (540,960,"09:00-16:00"),
                  (480,960,"08:00-16:00"),
                  (420,960,"07:00-16:00"),
                  (180,960,"03:00-16:00  (London on)"),
                  (0,1440,"24 hours")):
    pp,ee,_,_ = sim(s_start=st,s_end=en)
    r=sess[ee]<cut
    print(f"{tag:<26}"+blk(pp[r],ee[r])+"   |  "+blk(pp[~r],ee[~r]))
