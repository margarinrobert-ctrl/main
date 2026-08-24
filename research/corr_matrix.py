"""Correlation matrix across every leg studied, plus PCA and the effective number of bets.

The question a correlation matrix answers is NOT "is each leg profitable" but "are these the same
trade wearing different clothes". Two legs at rho 0.9 are one leg with twice the commission.
"""
import sys; sys.path.insert(0,'research')
import numpy as np
from bos_choch import prep, SPECS

S=SPECS['MNQ']; PV,TICK,COMM=S['pv'],S['tick'],1.0
EC=(S['spread_t']+S['slip_t'])*TICK; SE=S['stop_slip_t']*TICK

def bos(htf, tp_r=2.0, choch=False, md=1.0, side=0, n_bos=2, atr_mult=2.0):
    d=prep(htf); o,h,l,c=d['o'],d['h'],d['l'],d['c']; sess,mod=d['sess'],d['mod']
    ph,pl,ema_,atr_=d['ph'],d['pl'],d['ema'],d['atr']; n=len(c)
    trad=(mod>=570)&(mod<960)
    pos=0;entry=0.;stopL=np.nan;tp=np.nan;risk=0.;bias=0;rn=0;bh=np.nan;bl=np.nan
    aSig=np.nan;pend=0;pnl=[];ent=[]
    for i in range(1,n):
        ns=sess[i]!=sess[i-1]
        if pend!=0 and pos==0:
            pos=pend;entry=o[i];pend=0;risk=atr_mult*aSig;stopL=entry-pos*risk
            tp=entry+pos*tp_r*risk if tp_r>0 else np.nan
        if pos!=0:
            hit=(l[i]<=stopL) if pos==1 else (h[i]>=stopL)
            won=(not np.isnan(tp)) and ((h[i]>=tp) if pos==1 else (l[i]<=tp))
            if hit:
                px=o[i] if ((pos==1 and o[i]<stopL) or (pos==-1 and o[i]>stopL)) else stopL
                px += -SE if pos==1 else SE
                pnl.append(pos*(px-entry)*PV-2*EC*PV-COMM);ent.append(i);pos=0;stopL=np.nan;tp=np.nan
            elif won:
                px=o[i] if ((pos==1 and o[i]>tp) or (pos==-1 and o[i]<tp)) else tp
                pnl.append(pos*(px-entry)*PV-2*EC*PV-COMM);ent.append(i);pos=0;stopL=np.nan;tp=np.nan
        bU=(not np.isnan(ph[i])) and c[i]>ph[i] and (np.isnan(bh) or ph[i]!=bh)
        bD=(not np.isnan(pl[i])) and c[i]<pl[i] and (np.isnan(bl) or pl[i]!=bl)
        if bU: bh=ph[i]
        if bD: bl=pl[i]
        if bU: bias,rn=(1,rn+1) if bias==1 else (1,1)
        if bD: bias,rn=(-1,rn+1) if bias==-1 else (-1,1)
        a=atr_[i]; ready=(a>0) and not np.isnan(a) and not np.isnan(ema_[i])
        ok=(i+1<n and trad[i] and trad[i+1] and not ns)
        far=(md<=0) or (ready and abs(c[i]-ema_[i])>=md*a)
        if pos==0 and pend==0 and ok and ready and far:
            s_=1 if (bU and rn>=n_bos and c[i]>ema_[i]) else (-1 if (bD and rn>=n_bos and c[i]<ema_[i]) else 0)
            if s_ and (side==0 or side==s_): aSig=a;pend=s_
        if pos!=0 and choch and ((pos==1 and bD) or (pos==-1 and bU)) and i+1<n:
            pnl.append(pos*(o[i+1]-entry)*PV-2*EC*PV-COMM);ent.append(i);pos=0;stopL=np.nan;tp=np.nan
    return np.array(pnl), d['sess'][np.array(ent,dtype=int)] if ent else np.array([])

# a common daily grid, from the 30m session index
allsess = np.unique(prep(30)['sess'])
def daily(pnl, sess_of_trade):
    ds=np.zeros(len(allsess)); ix={q:j for j,q in enumerate(allsess)}
    for v,q in zip(pnl, sess_of_trade):
        if q in ix: ds[ix[q]] += v
    return ds

LEGS = {
 "30m 2R target":      bos(30, tp_r=2.0, choch=False),
 "30m CHoCH exit":     bos(30, tp_r=0.0, choch=True),
 "30m 3R target":      bos(30, tp_r=3.0, choch=False),
 "30m 1R target":      bos(30, tp_r=1.0, choch=False),
 "30m 2R, nBos=1":     bos(30, tp_r=2.0, choch=False, n_bos=1),
 "30m 2R, no filter":  bos(30, tp_r=2.0, choch=False, md=0.0),
 "30m 2R LONGS":       bos(30, tp_r=2.0, choch=False, side=1),
 "30m 2R SHORTS":      bos(30, tp_r=2.0, choch=False, side=-1),
 "60m 2R target":      bos(60, tp_r=2.0, choch=False, md=0.0),
 "15m 2R target":      bos(15, tp_r=2.0, choch=False),
}
names=list(LEGS)
D=np.array([daily(*LEGS[k]) for k in names])
C=np.corrcoef(D)

print("="*100); print("DAILY P&L CORRELATION MATRIX  (MNQ, Dec-2022..Dec-2025, "
      f"{len(allsess)} sessions)"); print("="*100)
print(f"{'':<20}" + "".join(f"{i+1:>8}" for i in range(len(names))))
for i,k in enumerate(names):
    print(f"{i+1:>2} {k:<17}" + "".join(f"{C[i,j]:>8.2f}" for j in range(len(names))))

print(); print("net $ and how much each leg is its own thing:")
print(f"{'leg':<20}{'net $':>10}{'trades':>8}{'max rho vs others':>20}")
for i,k in enumerate(names):
    off=np.delete(C[i],i)
    print(f"{k:<20}{LEGS[k][0].sum():>10,.0f}{len(LEGS[k][0]):>8}{off.max():>20.2f}")

print(); print("="*100); print("PCA — how many independent bets are actually here?"); print("="*100)
Z=(D-D.mean(1,keepdims=True))/ (D.std(1,keepdims=True)+1e-12)
ev=np.linalg.eigvalsh(np.corrcoef(Z))[::-1]
ev=ev[ev>0]; w=ev/ev.sum()
ent=-(w*np.log(w)).sum()
print("   variance explained:", "  ".join(f"PC{i+1} {100*x:.0f}%" for i,x in enumerate(w[:5])))
print(f"   effective number of bets (exp of PCA entropy) = {np.exp(ent):.2f} out of {len(names)} legs")
print(f"   PC1 alone explains {100*w[0]:.0f}% — everything here is mostly ONE trade.")
