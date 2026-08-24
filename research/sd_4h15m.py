"""The 4H-zone / 15M-confirmation strategy, implemented exactly as specified.

  ENTRY (long)   price enters a 4H DEMAND zone, then on 15M:
                   - the bar PENETRATES the zone (its low trades inside)
                   - it REJECTS lower prices and CLOSES BULLISH (close > open)
                   - it closes back above the zone low
                   - and (optionally, "ideally") BREAKS THE PREVIOUS 15M HIGH
                 fill at the next 15M open. Short is the mirror.
  STOP           zone low - buf x ATR(15M)          (spec: buf = 0.15)
  TARGET         2R, where 1R is the distance from entry to that stop

Note what the tiny buffer does: a 0.15 x ATR(15M) pad under a FOUR-HOUR zone is a very small
risk, so 1R is small, so the 2R target is close -- and the trade lives or dies on whether a 15M
wick takes out the zone edge. That is the interesting part and it is what gets measured here.
"""
import numpy as np
from numba import njit

@njit(cache=True)
def build_zones(o,h,l,c,atr_, base_k, base_max, dep_min, zone_type):
    n=len(c); NZ=4000
    ZL=np.zeros(NZ); ZH=np.zeros(NZ); ZD=np.zeros(NZ,np.int64); ZB=np.zeros(NZ,np.int64); nz=0
    for i in range(base_k+5, n):
        a=atr_[i]
        if np.isnan(a) or a<=0.0 or nz>=NZ-1: continue
        quiet=True; bl=l[i-base_k]; bh=h[i-base_k]
        for j in range(i-base_k,i):
            if (h[j]-l[j])>base_max*a: quiet=False; break
            if l[j]<bl: bl=l[j]
            if h[j]>bh: bh=h[j]
        if not quiet or (h[i]-l[i])<dep_min*a: continue
        d=0
        if c[i]>bh: d=1
        elif c[i]<bl: d=-1
        if d==0: continue
        pre=c[i-base_k-1]-c[i-base_k-4]
        rev=(d==1 and pre<0.0) or (d==-1 and pre>0.0)
        if zone_type==1 and not rev: continue
        if zone_type==2 and rev: continue
        ZL[nz]=bl; ZH[nz]=bh; ZD[nz]=d; ZB[nz]=i; nz+=1
    return ZL[:nz], ZH[:nz], ZD[:nz], ZB[:nz]

@njit(cache=True)
def run(o,h,l,c,sess,trad,atr15, zl,zh,zd,zstart, buf, tp_r, need_break, max_age, one_shot,
        side_mode, pv,tick,comm,spread_t,slip_t,stop_slip_t):
    """zstart[z] = the first 15M bar index at which zone z is KNOWN (its 4H bar has closed)."""
    n=len(c); mx=n//2+8; nz=len(zl)
    pnl=np.zeros(mx); ent=np.zeros(mx,np.int64); sd=np.zeros(mx,np.int64); why=np.zeros(mx,np.int64)
    used=np.zeros(nz,np.int64); k=0
    ec=(spread_t+slip_t)*tick; se=stop_slip_t*tick
    pos=0; entry=0.0; stop=0.0; tgt=0.0; pend=0; pstop=0.0; ptgt=0.0
    for i in range(2, n-1):
        a=atr15[i]
        if np.isnan(a) or a<=0.0: continue
        if pend!=0 and pos==0:
            pos=pend; entry=o[i]; pend=0; stop=pstop; tgt=ptgt
            if (pos==1 and stop>=entry) or (pos==-1 and stop<=entry): pos=0
        if pos!=0:
            hit=(l[i]<=stop) if pos==1 else (h[i]>=stop)
            won=(h[i]>=tgt) if pos==1 else (l[i]<=tgt)
            if hit and won: won=False
            if hit:
                px=o[i] if ((pos==1 and o[i]<stop) or (pos==-1 and o[i]>stop)) else stop
                px += -se if pos==1 else se
                pnl[k]=pos*(px-entry)*pv-comm-2.0*ec*pv; ent[k]=i; sd[k]=pos; why[k]=1; k+=1; pos=0
            elif won:
                px=o[i] if ((pos==1 and o[i]>tgt) or (pos==-1 and o[i]<tgt)) else tgt
                pnl[k]=pos*(px-entry)*pv-comm-2.0*ec*pv; ent[k]=i; sd[k]=pos; why[k]=2; k+=1; pos=0
        if pos!=0 or pend!=0: continue
        if trad[i]!=1 or trad[i+1]!=1: continue
        for z in range(nz):
            if zstart[z] > i: continue
            if i - zstart[z] > max_age: continue
            if one_shot==1 and used[z]==1: continue
            d=zd[z]
            if side_mode!=0 and side_mode!=d: continue
            if d==1:
                if l[i] > zh[z] or l[i] < zl[z]: continue      # penetrated the zone, not through it
                if c[i] <= o[i]: continue                      # must close bullish
                if c[i] <= zl[z]: continue                     # rejected lower prices
                if need_break==1 and h[i] <= h[i-1]: continue  # broke the previous 15M high
                st = zl[z] - buf*a
            else:
                if h[i] < zl[z] or h[i] > zh[z]: continue
                if c[i] >= o[i]: continue
                if c[i] >= zh[z]: continue
                if need_break==1 and l[i] >= l[i-1]: continue
                st = zh[z] + buf*a
            risk = abs(c[i]-st)
            if risk <= 0.0 or risk > 8.0*a: continue
            used[z]=1
            pend=d; pstop=st; ptgt=c[i] + d*tp_r*risk
            break
    return pnl[:k], ent[:k], sd[:k], why[:k]
