"""Every version of NQ_BosChoch.pine, re-simulated on identical MNQ 30m data.

Each row is what that version's LOGIC actually did -- not the number it printed at the time, which
was often measured on a different instrument, cost model or sizing convention.
"""
import sys; sys.path.insert(0,'research')
import numpy as np
from bos_choch import prep

d=prep(30); o,h,l,c=d['o'],d['h'],d['l'],d['c']; sess,mod=d['sess'],d['mod']
ph,pl,ema_,atr_=d['ph'],d['pl'],d['ema'],d['atr']; n=len(c)
tick=0.25; PV=2.0; EC=(1.0+1.0)*tick; SE=1.0*tick
trad=(mod>=570)&(mod<960)
def sma(x,k):
    out=np.full_like(x,np.nan)
    for i in range(k-1,len(x)):
        seg=x[i-k+1:i+1]
        if not np.isnan(seg).any(): out[i]=seg.mean()
    return out
avg_atr=sma(atr_,60)

def sim(gate='v6', n_bos=2, comm_order=0.50, volsize=False, tp_r=0.0, choch=True, atr_mult=2.0):
    comm=2*comm_order
    pos=0;entry=0.;stopL=np.nan;tp=np.nan;risk=0.;bias=0;rn=0;bh=np.nan;bl=np.nan
    aSig=np.nan;pend=0;pq=1;q=1;pnl=[];ent=[]
    for i in range(1,n):
        ns=sess[i]!=sess[i-1]
        if pend!=0 and pos==0:
            pos=pend;entry=o[i];q=pq;pend=0
            risk=atr_mult*aSig; stopL=entry-pos*risk
            tp = entry+pos*tp_r*risk if tp_r>0 else np.nan
        if pos!=0:
            hit=(l[i]<=stopL) if pos==1 else (h[i]>=stopL)
            won=(not np.isnan(tp)) and ((h[i]>=tp) if pos==1 else (l[i]<=tp))
            if hit:
                px=o[i] if ((pos==1 and o[i]<stopL) or (pos==-1 and o[i]>stopL)) else stopL
                px += -SE if pos==1 else SE
                pnl.append(q*(pos*(px-entry)*PV-2*EC*PV)-q*comm);ent.append(i);pos=0;stopL=np.nan;tp=np.nan
            elif won:
                px=o[i] if ((pos==1 and o[i]>tp) or (pos==-1 and o[i]<tp)) else tp
                pnl.append(q*(pos*(px-entry)*PV-2*EC*PV)-q*comm);ent.append(i);pos=0;stopL=np.nan;tp=np.nan
        bU=(not np.isnan(ph[i])) and c[i]>ph[i] and (np.isnan(bh) or ph[i]!=bh)
        bD=(not np.isnan(pl[i])) and c[i]<pl[i] and (np.isnan(bl) or pl[i]!=bl)
        if bU: bh=ph[i]
        if bD: bl=pl[i]
        if bU: bias,rn=(1,rn+1) if bias==1 else (1,1)
        if bD: bias,rn=(-1,rn+1) if bias==-1 else (-1,1)
        a=atr_[i]; ready=(a>0) and not np.isnan(a) and not np.isnan(ema_[i])
        ok=(i+1<n and trad[i] and trad[i+1] and not ns) if gate=='v6' else ((mod[i]>=570)and(mod[i]<930))
        far=ready and abs(c[i]-ema_[i])>=1.0*a
        if pos==0 and pend==0 and ok and ready and far:
            s_=1 if (bU and rn>=n_bos and c[i]>ema_[i]) else (-1 if (bD and rn>=n_bos and c[i]<ema_[i]) else 0)
            if s_:
                aSig=a;pend=s_
                pq=max(round(min(avg_atr[i]/a,2.0)),1) if (volsize and not np.isnan(avg_atr[i])) else 1
        if pos!=0 and choch and ((pos==1 and bD) or (pos==-1 and bU)) and i+1<n:
            pnl.append(q*(pos*(o[i+1]-entry)*PV-2*EC*PV)-q*comm);ent.append(i);pos=0;stopL=np.nan;tp=np.nan
    return np.array(pnl),np.array(ent)

usess=np.unique(sess); cut=usess[int(0.65*len(usess))]
def row(tag,p,e):
    w=p[p>0]; ls=p[p<=0]; eq=np.cumsum(p)
    dd=(np.maximum.accumulate(np.r_[0,eq])-np.r_[0,eq]).max()
    u=np.unique(sess); ds=np.zeros(len(u)); ix={q:j for j,q in enumerate(u)}
    for v,q in zip(p,sess[e]): ds[ix[q]] += v
    sh=ds.mean()/ds.std()*np.sqrt(252)      # ALL sessions, zero on non-trading days
    m=sess[e]<cut
    print(f"{tag:<34}{len(p):>5}{p.sum():>10,.0f}{w.sum()/-ls.sum():>7.2f}{100*len(w)/len(p):>7.1f}"
          f"{dd:>9,.0f}{sh:>8.2f}{p[~m].sum():>11,.0f}")

VER = [
 ("v2/v3  runLen bug, old gate",  dict(gate='old', n_bos=1, comm_order=2.00, volsize=True)),
 ("v4/v5  runLen fixed",          dict(gate='old', n_bos=2, comm_order=2.00, volsize=True)),
 ("v6     entry gate fixed",      dict(gate='v6',  n_bos=2, comm_order=2.00, volsize=False)),
 ("v7a    Micro commission",      dict(gate='v6',  n_bos=2, comm_order=0.50, volsize=False)),
 ("v7b    + 2R target, no CHoCH", dict(gate='v6',  n_bos=2, comm_order=0.50, volsize=False,
                                       tp_r=2.0, choch=False)),
]
print(f"{'version':<34}{'n':>5}{'net $':>10}{'PF':>7}{'win%':>7}{'maxDD':>9}{'Sharpe':>8}{'LOCKED $':>11}")
print("-"*91)
res={}
for tag,kw in VER:
    p,e=sim(**kw); res[tag]=p; row(tag,p,e)
print("-"*91)
base=res["v2/v3  runLen bug, old gate"].sum()
best=res["v7b    + 2R target, no CHoCH"].sum()
print(f"\n  v2/v3 -> v7b :  ${base:,.0f} -> ${best:,.0f}   ({100*(best-base)/abs(base):+.0f}%)")
prev=None
for tag,_ in VER:
    s=res[tag].sum()
    if prev is not None: print(f"    {tag:<34}{s-prev:>+10,.0f}")
    prev=s
