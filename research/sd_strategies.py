"""The three strategies from 'Supply and Demand Zone Trading Strategies', made falsifiable.

Every element named in the document is a switch, so nothing is assumed away:

  ZONE FORMATION   base of base_k bars each <= base_max x ATR, then a departure bar >= dep_min x ATR
  ZONE TYPE        0 all | 1 REVERSAL only (drop-base-rally / rally-base-drop)
                          2 CONTINUATION only (rally-base-rally / drop-base-drop)
  MODE             0 REVERSAL   -- price returns INTO the zone, trade the bounce  (Strategy 1 & 3)
                   1 BREAK+RETEST -- zone is broken, price returns to it, trade the flip (Strategy 2)
  CONFIRM          0 none | 1 pin bar | 2 engulfing | 3 either        ("wait for rejection")
  STOP             0 = k x ATR | 1 = the far side of the zone plus pad x ATR   ("SL outside the zone")
  TARGET           0 = R multiple | 1 = the next opposing zone                 ("TP at next zone")
  FIRST RETEST     max_tests, and fresh_only for "trade the first retest"

Entries fill at the next bar's open. Same costs, session gate and instrument as the BOS/CHoCH book.
"""
import numpy as np
from numba import njit

@njit(cache=True)
def run_sd(o,h,l,c,v,sess,trad,atr_,
           base_k, base_max, dep_min, zone_type, mode, confirm,
           stop_mode, stop_k, stop_pad, tp_mode, tp_r,
           max_age, max_tests, fresh_only, side_mode, vol_mult,
           pv, tick, comm, spread_t, slip_t, stop_slip_t):
    n=len(c); mx=n//2+8
    pnl=np.zeros(mx); ent=np.zeros(mx,np.int64); sd=np.zeros(mx,np.int64)
    why=np.zeros(mx,np.int64); k=0
    ec=(spread_t+slip_t)*tick; se=stop_slip_t*tick
    NZ=6000
    ZL=np.zeros(NZ); ZH=np.zeros(NZ); ZD=np.zeros(NZ,np.int64)
    ZB=np.zeros(NZ,np.int64); ZT=np.zeros(NZ,np.int64); ZBRK=np.zeros(NZ,np.int64); nz=0
    pos=0; entry=0.0; stop=0.0; tgt=0.0; pend=0; pdir=0
    pstop=0.0; ptgt=0.0
    for i in range(base_k+4, n-1):
        a=atr_[i]
        if np.isnan(a) or a<=0.0: continue
        if pend!=0 and pos==0:
            pos=pend; entry=o[i]; pend=0; stop=pstop; tgt=ptgt
            # a stop on the wrong side is unusable
            if (pos==1 and stop>=entry) or (pos==-1 and stop<=entry): pos=0
        if pos!=0:
            hit=(l[i]<=stop) if pos==1 else (h[i]>=stop)
            won=(h[i]>=tgt) if pos==1 else (l[i]<=tgt)
            if hit and won: won=False                     # ambiguous bar -> the stop
            if hit:
                px=o[i] if ((pos==1 and o[i]<stop) or (pos==-1 and o[i]>stop)) else stop
                px += -se if pos==1 else se
                pnl[k]=pos*(px-entry)*pv-comm-2.0*ec*pv; ent[k]=i; sd[k]=pos; why[k]=1; k+=1; pos=0
            elif won:
                px=o[i] if ((pos==1 and o[i]>tgt) or (pos==-1 and o[i]<tgt)) else tgt
                pnl[k]=pos*(px-entry)*pv-comm-2.0*ec*pv; ent[k]=i; sd[k]=pos; why[k]=2; k+=1; pos=0

        # ---------- form a zone ----------
        quiet=True; bl=l[i-base_k]; bh=h[i-base_k]
        for j in range(i-base_k, i):
            if (h[j]-l[j]) > base_max*a: quiet=False; break
            if l[j]<bl: bl=l[j]
            if h[j]>bh: bh=h[j]
        if quiet and (h[i]-l[i])>=dep_min*a and nz<NZ-1:
            if vol_mult<=0.0 or v[i] >= vol_mult*((v[i-1]+v[i-2]+v[i-3])/3.0):
                d=0
                if c[i]>bh: d=1
                elif c[i]<bl: d=-1
                if d!=0:
                    # approach direction BEFORE the base: DBR/RBD are reversals, RBR/DBD continuations
                    pre = c[i-base_k-1] - c[i-base_k-4]
                    rev = (d==1 and pre<0.0) or (d==-1 and pre>0.0)
                    ok = (zone_type==0) or (zone_type==1 and rev) or (zone_type==2 and not rev)
                    if ok:
                        ZL[nz]=bl; ZH[nz]=bh; ZD[nz]=d; ZB[nz]=i; ZT[nz]=0; ZBRK[nz]=0; nz+=1

        # ---------- mark broken zones ----------
        for z in range(nz):
            if ZD[z]==0 or ZBRK[z]==1: continue
            if (ZD[z]==1 and c[i] < ZL[z]) or (ZD[z]==-1 and c[i] > ZH[z]): ZBRK[z]=1

        # ---------- look for an entry ----------
        if pos!=0 or pend!=0: continue
        if trad[i]!=1 or trad[i+1]!=1 or sess[i]!=sess[i-1]: continue
        for z in range(nz):
            if ZD[z]==0: continue
            age=i-ZB[z]
            if age>max_age or age<1: continue
            if mode==0:
                if ZBRK[z]==1: continue
                d=ZD[z]
                inz = (l[i]<=ZH[z] and l[i]>=ZL[z]) if d==1 else (h[i]>=ZL[z] and h[i]<=ZH[z])
            else:
                if ZBRK[z]==0: continue
                d=-ZD[z]                       # the flip: a broken demand zone becomes supply
                inz = (h[i]>=ZL[z] and h[i]<=ZH[z]) if d==-1 else (l[i]<=ZH[z] and l[i]>=ZL[z])
            if not inz: continue
            ZT[z]+=1
            if fresh_only==1 and ZT[z]>1: continue
            if ZT[z]>max_tests: continue
            if side_mode!=0 and side_mode!=d: continue
            # ---- rejection confirmation on THIS bar ----
            if confirm>0:
                rng=h[i]-l[i]
                if rng<=0.0: continue
                body=abs(c[i]-o[i])
                pin = False; eng = False
                if d==1:
                    lw = (o[i] if o[i]<c[i] else c[i]) - l[i]
                    pin = (lw > 2.0*body) and (c[i] > l[i]+0.6*rng)
                    eng = (c[i]>o[i]) and (c[i-1]<o[i-1]) and (c[i]>o[i-1]) and (o[i]<c[i-1])
                else:
                    uw = h[i] - (o[i] if o[i]>c[i] else c[i])
                    pin = (uw > 2.0*body) and (c[i] < h[i]-0.6*rng)
                    eng = (c[i]<o[i]) and (c[i-1]>o[i-1]) and (c[i]<o[i-1]) and (o[i]>c[i-1])
                if confirm==1 and not pin: continue
                if confirm==2 and not eng: continue
                if confirm==3 and not (pin or eng): continue
            # ---- stop ----
            if stop_mode==0:
                st = c[i] - d*stop_k*a
            else:
                st = (ZL[z]-stop_pad*a) if d==1 else (ZH[z]+stop_pad*a)
            risk = abs(c[i]-st)
            if risk<=0.0 or risk>6.0*a: continue
            # ---- target ----
            if tp_mode==0:
                tg = c[i] + d*tp_r*risk
            else:
                tg = 0.0; bestdist=1e18
                for z2 in range(nz):
                    if ZD[z2]==0 or z2==z or ZBRK[z2]==1: continue
                    lvl = ZL[z2] if d==1 else ZH[z2]
                    if d==1 and lvl>c[i] and (lvl-c[i])<bestdist: bestdist=lvl-c[i]; tg=lvl
                    if d==-1 and lvl<c[i] and (c[i]-lvl)<bestdist: bestdist=c[i]-lvl; tg=lvl
                if tg==0.0: continue                      # no next zone -> no trade
            if (d==1 and tg<=c[i]) or (d==-1 and tg>=c[i]): continue
            pend=d; pdir=d; pstop=st; ptgt=tg
            break
    return pnl[:k], ent[:k], sd[:k], why[:k]
