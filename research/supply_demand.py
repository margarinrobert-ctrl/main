"""Supply/demand zones and the Wyckoff spring, mechanised and tested.

THE ZONE RULE (Seiden-style, made falsifiable):
  BASE       k consecutive bars each with range <= base_max x ATR  -- "equilibrium"
  DEPARTURE  the next bar has range >= dep_min x ATR and closes away from the base
  ZONE       the base's high..low becomes a demand zone (departure up) or supply zone (down)
  ENTRY      price later trades back INTO the zone -> enter in the departure direction
  STOP/TGT   2 x ATR and 2R, identical to the BOS book so the two are comparable

THE WYCKOFF SPRING:
  RANGE      tr_n bars whose full span <= tr_max x ATR   -- a trading range
  SPRING     a bar's LOW pierces the range low, and the bar CLOSES back inside the range
  ENTRY      next bar's open, long. UPTHRUST is the mirror -> short.

Also tests the documents' own claim that a zone "gets weaker after each test", by tagging every
entry with which test of that zone it was.
"""
import sys; sys.path.insert(0,'research')
import numpy as np
from numba import njit
from bos_choch import prep, SPECS

S=SPECS['MNQ']; PV,TICK,COMM=S['pv'],S['tick'],1.0
EC=(S['spread_t']+S['slip_t'])*TICK; SE=S['stop_slip_t']*TICK

@njit(cache=True)
def zones(o,h,l,c,sess,trad,atr_, base_k, base_max, dep_min, max_age, max_tests,
          stop_mult, tp_r, side_mode, fresh_only):
    n=len(c); mx=n//2+8
    pnl=np.zeros(mx); ent=np.zeros(mx,np.int64); sd=np.zeros(mx,np.int64)
    tst=np.zeros(mx,np.int64); k=0
    # rolling store of live zones
    ZL=np.zeros(4000); ZH=np.zeros(4000); ZD=np.zeros(4000,np.int64)
    ZB=np.zeros(4000,np.int64); ZT=np.zeros(4000,np.int64); nz=0
    pos=0; entry=0.0; stop=0.0; tp=0.0; pend=0; pdir=0; ptest=0; prisk=0.0
    for i in range(base_k+2, n):
        a=atr_[i]
        if np.isnan(a) or a<=0.0: continue
        # ---- fill pending ----
        if pend!=0 and pos==0:
            pos=pdir; entry=o[i]; pend=0
            stop=entry-pos*prisk; tp=entry+pos*tp_r*prisk
        # ---- manage ----
        if pos!=0:
            hit=(l[i]<=stop) if pos==1 else (h[i]>=stop)
            won=(h[i]>=tp) if pos==1 else (l[i]<=tp)
            if hit:
                px=o[i] if ((pos==1 and o[i]<stop) or (pos==-1 and o[i]>stop)) else stop
                px += -SE if pos==1 else SE
                pnl[k]=pos*(px-entry)*PV-2*EC*PV-COMM; ent[k]=i; sd[k]=pos; tst[k]=ptest; k+=1
                pos=0
            elif won:
                px=o[i] if ((pos==1 and o[i]>tp) or (pos==-1 and o[i]<tp)) else tp
                pnl[k]=pos*(px-entry)*PV-2*EC*PV-COMM; ent[k]=i; sd[k]=pos; tst[k]=ptest; k+=1
                pos=0
        # ---- form a zone: base of base_k quiet bars then a departure bar ----
        allquiet=True
        bl=l[i-base_k]; bh=h[i-base_k]
        for j in range(i-base_k, i):
            if (h[j]-l[j]) > base_max*a: allquiet=False; break
            if l[j]<bl: bl=l[j]
            if h[j]>bh: bh=h[j]
        if allquiet and (h[i]-l[i])>=dep_min*a and nz<3999:
            d=0
            if c[i]>bh: d=1
            elif c[i]<bl: d=-1
            if d!=0:
                ZL[nz]=bl; ZH[nz]=bh; ZD[nz]=d; ZB[nz]=i; ZT[nz]=0; nz+=1
        # ---- retest ----
        if pos==0 and pend==0 and i+1<n and trad[i]==1 and trad[i+1]==1 and sess[i]==sess[i-1]:
            for z in range(nz):
                if ZD[z]==0: continue
                if i-ZB[z] > max_age or i-ZB[z] < 1: continue
                inzone = (l[i]<=ZH[z] and l[i]>=ZL[z]) if ZD[z]==1 else (h[i]>=ZL[z] and h[i]<=ZH[z])
                if not inzone: continue
                ZT[z]+=1
                if fresh_only==1 and ZT[z]>1: continue
                if ZT[z]>max_tests: continue
                if side_mode!=0 and side_mode!=ZD[z]: continue
                pend=ZD[z]; pdir=ZD[z]; ptest=ZT[z]; prisk=stop_mult*a
                break
    return pnl[:k], ent[:k], sd[:k], tst[:k]

@njit(cache=True)
def spring(o,h,l,c,sess,trad,atr_, tr_n, tr_max, stop_mult, tp_r, side_mode):
    n=len(c); mx=n//2+8
    pnl=np.zeros(mx); ent=np.zeros(mx,np.int64); sd=np.zeros(mx,np.int64); k=0
    pos=0; entry=0.0; stop=0.0; tp=0.0; pend=0; prisk=0.0
    for i in range(tr_n+2, n):
        a=atr_[i]
        if np.isnan(a) or a<=0.0: continue
        if pend!=0 and pos==0:
            pos=pend; entry=o[i]; pend=0
            stop=entry-pos*prisk; tp=entry+pos*tp_r*prisk
        if pos!=0:
            hit=(l[i]<=stop) if pos==1 else (h[i]>=stop)
            won=(h[i]>=tp) if pos==1 else (l[i]<=tp)
            if hit:
                px=o[i] if ((pos==1 and o[i]<stop) or (pos==-1 and o[i]>stop)) else stop
                px += -SE if pos==1 else SE
                pnl[k]=pos*(px-entry)*PV-2*EC*PV-COMM; ent[k]=i; sd[k]=pos; k+=1; pos=0
            elif won:
                px=o[i] if ((pos==1 and o[i]>tp) or (pos==-1 and o[i]<tp)) else tp
                pnl[k]=pos*(px-entry)*PV-2*EC*PV-COMM; ent[k]=i; sd[k]=pos; k+=1; pos=0
        if pos!=0 or pend!=0 or i+1>=n: continue
        if trad[i]!=1 or trad[i+1]!=1 or sess[i]!=sess[i-1]: continue
        # trading range over the tr_n bars ENDING at i-1
        rl=l[i-tr_n]; rh=h[i-tr_n]
        for j in range(i-tr_n, i):
            if l[j]<rl: rl=l[j]
            if h[j]>rh: rh=h[j]
        if (rh-rl) > tr_max*a: continue
        if l[i] < rl and c[i] > rl and side_mode>=0:            # SPRING -> long
            pend=1; prisk=stop_mult*a
        elif h[i] > rh and c[i] < rh and side_mode<=0:          # UPTHRUST -> short
            pend=-1; prisk=stop_mult*a
    return pnl[:k], ent[:k], sd[:k]

if __name__ == "__main__":
    import itertools, time
    D={}; T={}; U={}; CUT={}
    for m in (15,30,60):
        d=prep(m); D[m]=d
        T[m]=((d['mod']>=570)&(d['mod']<960)).astype(np.uint8)
        u=np.unique(d['sess']); U[m]=u; CUT[m]=u[int(0.65*len(u))]
    def sh(p,e,m,uni):
        ds=np.zeros(len(uni)); ix={q:j for j,q in enumerate(uni)}
        for v,q in zip(p, D[m]['sess'][e]):
            if q in ix: ds[ix[q]]+=v
        return ds.mean()/ds.std()*np.sqrt(252) if ds.std()>0 else 0.0
    def split(p,e,m):
        s=D[m]['sess'][e]; msk=s<CUT[m]; u=U[m]
        return p[msk], e[msk], p[~msk], e[~msk], u[u<CUT[m]], u[u>=CUT[m]]

    print("="*96); print("A. SUPPLY / DEMAND ZONE RETEST — full sweep"); print("="*96)
    rows=[]; t0=time.time(); allp=[]; allt=[]
    for m,bk,bm,dm,ag,mt,sm,tp,sd_,fr in itertools.product(
            (15,30,60),(2,3,4,5),(0.4,0.6,0.8,1.0),(1.0,1.5,2.0,2.5),
            (20,60,120,240),(1,2,3,99),(1.5,2.0,3.0),(1.5,2.0,3.0),(-1,0,1),(0,1)):
        if fr==1 and mt!=99: continue
        d=D[m]
        p,e,s,ts = zones(d['o'],d['h'],d['l'],d['c'],d['sess'],T[m],d['atr'],
                         bk,bm,dm,ag,mt,sm,tp,sd_,fr)
        if len(p)<25: continue
        rp,re,lp,le,ru,lu = split(p,e,m)
        if len(rp)<12 or len(lp)<8: continue
        rows.append((rp.sum(), sh(rp,re,m,ru), lp.sum(), sh(lp,le,m,lu), len(p), m, sd_))
        if m==30 and sd_==0 and fr==0:
            allp.append(p); allt.append(ts)
    R=np.array(rows)
    print(f"   {len(R):,} configurations with >=25 trades, {time.time()-t0:.0f}s")
    rn,rs,ln,ls = R[:,0],R[:,1],R[:,2],R[:,3]
    b=int(np.argmax(rn))
    print(f"   best on RESEARCH   : research ${rn[b]:>8,.0f}  ->  LOCKED ${ln[b]:>8,.0f}")
    print(f"   best on LOCKED     : ${ln.max():>8,.0f}   (hindsight, unattainable)")
    print(f"   MEDIAN locked      : ${np.median(ln):>8,.0f}")
    print(f"   positive on research {100*(rn>0).mean():>5.1f}%   on locked {100*(ln>0).mean():>5.1f}%"
          f"   on BOTH {100*((rn>0)&(ln>0)).mean():>5.1f}%")
    print(f"   BOS/CHoCH 2R book on the same locked block: $8,932")

    print(); print("="*96); print("B. DOES A ZONE WEAKEN WITH EACH TEST? (the documents' own claim)")
    print("="*96)
    P=np.concatenate(allp); TS=np.concatenate(allt)
    print(f"{'test number':<16}{'n':>6}{'net $':>11}{'$/trade':>10}{'win%':>8}")
    for t_ in (1,2,3):
        x=P[TS==t_]
        if len(x)<5: continue
        print(f"{'test '+str(t_):<16}{len(x):>6}{x.sum():>11,.0f}{x.mean():>10,.0f}{100*(x>0).mean():>8.1f}")
    x=P[TS>=4]
    if len(x)>=5:
        print(f"{'test 4+':<16}{len(x):>6}{x.sum():>11,.0f}{x.mean():>10,.0f}{100*(x>0).mean():>8.1f}")

    print(); print("="*96); print("C. WYCKOFF SPRING / UPTHRUST — full sweep"); print("="*96)
    rows=[]
    for m,trn,trm,sm,tp,sd_ in itertools.product(
            (15,30,60),(10,20,30,50),(1.0,1.5,2.0,3.0),(1.5,2.0,3.0),(1.5,2.0,3.0),(-1,0,1)):
        d=D[m]
        p,e,s = spring(d['o'],d['h'],d['l'],d['c'],d['sess'],T[m],d['atr'],trn,trm,sm,tp,sd_)
        if len(p)<25: continue
        rp,re,lp,le,ru,lu = split(p,e,m)
        if len(rp)<12 or len(lp)<8: continue
        rows.append((rp.sum(), sh(rp,re,m,ru), lp.sum(), sh(lp,le,m,lu), len(p), m, sd_))
    R2=np.array(rows)
    print(f"   {len(R2):,} configurations with >=25 trades")
    if len(R2):
        rn2,ln2 = R2[:,0],R2[:,2]
        b2=int(np.argmax(rn2))
        print(f"   best on RESEARCH   : research ${rn2[b2]:>8,.0f}  ->  LOCKED ${ln2[b2]:>8,.0f}")
        print(f"   best on LOCKED     : ${ln2.max():>8,.0f}   (hindsight)")
        print(f"   MEDIAN locked      : ${np.median(ln2):>8,.0f}")
        print(f"   positive on BOTH blocks: {100*((rn2>0)&(ln2>0)).mean():.1f}%")
