"""Do ADX and Stochastic improve the BOS/CHoCH + 2R book?

Pre-specified reasoning BEFORE any number is looked at:
  ADX   -- this is a trend-continuation rule. It should work better when a trend is actually
           present. ADX is the standard measure of that, so "ADX above a threshold" is the single
           most defensible filter anyone could bolt on. If a trend filter cannot help a trend
           strategy, that is informative.
  STOCH -- a break that fires when the oscillator is already pinned at an extreme is a break with
           nothing left to run. "Do not buy an overbought break" is the standard use, so it is
           tested as an entry veto, not as a signal.

Both are computed from closed bars only. Everything is scored on the same research/locked split,
and the daily Sharpe spans EVERY session in its block with zero on non-trading days.
"""
import sys; sys.path.insert(0,'research')
import numpy as np
from numba import njit
from bos_choch import prep

d=prep(30); o,h,l,c=d['o'],d['h'],d['l'],d['c']; sess,mod=d['sess'],d['mod']
ph,pl,ema_,atr_=d['ph'],d['pl'],d['ema'],d['atr']; n=len(c)
tick=0.25; PV=2.0; COMM=1.0; EC=(1.0+1.0)*tick; SE=1.0*tick
trad=(mod>=570)&(mod<960)

@njit(cache=True)
def adx_wilder(h, l, c, nn):
    n=len(c); pdm=np.zeros(n); ndm=np.zeros(n); tr=np.zeros(n)
    for i in range(1,n):
        up=h[i]-h[i-1]; dn=l[i-1]-l[i]
        pdm[i]= up if (up>dn and up>0) else 0.0
        ndm[i]= dn if (dn>up and dn>0) else 0.0
        a=h[i]-l[i]; b=abs(h[i]-c[i-1]); e=abs(l[i]-c[i-1])
        tr[i]=max(a,max(b,e))
    sp=np.zeros(n); sn=np.zeros(n); st=np.zeros(n)
    out=np.full(n,np.nan)
    for i in range(1,n):
        if i<=nn:
            sp[i]=sp[i-1]+pdm[i]; sn[i]=sn[i-1]+ndm[i]; st[i]=st[i-1]+tr[i]
        else:
            sp[i]=sp[i-1]-sp[i-1]/nn+pdm[i]; sn[i]=sn[i-1]-sn[i-1]/nn+ndm[i]
            st[i]=st[i-1]-st[i-1]/nn+tr[i]
    dx=np.full(n,np.nan)
    for i in range(nn,n):
        if st[i]>0:
            pdi=100.0*sp[i]/st[i]; ndi=100.0*sn[i]/st[i]
            s=pdi+ndi
            if s>0: dx[i]=100.0*abs(pdi-ndi)/s
    cnt=0; acc=0.0
    for i in range(nn,n):
        if not np.isnan(dx[i]):
            cnt+=1; acc+=dx[i]
            if cnt==nn: out[i]=acc/nn
            elif cnt>nn: out[i]=(out[i-1]*(nn-1)+dx[i])/nn
    return out

@njit(cache=True)
def stoch_kd(h, l, c, nn, dsm):
    n=len(c); k=np.full(n,np.nan)
    for i in range(nn-1,n):
        hh=h[i-nn+1]; ll=l[i-nn+1]
        for j in range(i-nn+2,i+1):
            if h[j]>hh: hh=h[j]
            if l[j]<ll: ll=l[j]
        k[i]= 100.0*(c[i]-ll)/(hh-ll) if hh>ll else 50.0
    dd=np.full(n,np.nan)
    for i in range(nn-1+dsm-1,n):
        s=0.0
        for j in range(i-dsm+1,i+1): s+=k[j]
        dd[i]=s/dsm
    return k, dd

ADX = {p: adx_wilder(h,l,c,p) for p in (7,14,21)}
STO = {}
for p in (9,14,21):
    STO[p] = stoch_kd(h,l,c,p,3)

def sim(adx_p=14, adx_min=0.0, adx_rising=False, sto_p=14, sto_veto=0.0, sto_align=False):
    A=ADX[adx_p]; K,D=STO[sto_p]
    pos=0;entry=0.;stopL=np.nan;tp=np.nan;risk=0.;bias=0;rn=0;bh=np.nan;bl=np.nan
    aSig=np.nan;pend=0;pnl=[];ent=[]
    for i in range(1,n):
        ns=sess[i]!=sess[i-1]
        if pend!=0 and pos==0:
            pos=pend;entry=o[i];pend=0;risk=2.0*aSig;stopL=entry-pos*risk
            tp=entry+pos*2.0*risk
        if pos!=0:
            hit=(l[i]<=stopL) if pos==1 else (h[i]>=stopL)
            won=(h[i]>=tp) if pos==1 else (l[i]<=tp)
            if hit:
                px=o[i] if ((pos==1 and o[i]<stopL) or (pos==-1 and o[i]>stopL)) else stopL
                px += -SE if pos==1 else SE
                pnl.append(pos*(px-entry)*PV-2*EC*PV-COMM);ent.append(i);pos=0;stopL=np.nan
            elif won:
                px=o[i] if ((pos==1 and o[i]>tp) or (pos==-1 and o[i]<tp)) else tp
                pnl.append(pos*(px-entry)*PV-2*EC*PV-COMM);ent.append(i);pos=0;stopL=np.nan
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
            if s_:
                gate=True
                if adx_min>0:
                    if np.isnan(A[i]) or A[i] < adx_min: gate=False
                if adx_rising and gate:
                    if np.isnan(A[i]) or np.isnan(A[i-3]) or A[i] <= A[i-3]: gate=False
                if sto_veto>0 and gate:
                    if np.isnan(K[i]): gate=False
                    elif s_==1 and K[i] > sto_veto: gate=False
                    elif s_==-1 and K[i] < 100.0-sto_veto: gate=False
                if sto_align and gate:
                    if np.isnan(K[i]) or np.isnan(D[i]): gate=False
                    elif s_==1 and K[i] <= D[i]: gate=False
                    elif s_==-1 and K[i] >= D[i]: gate=False
                if gate: aSig=a;pend=s_
    return np.array(pnl),np.array(ent)

usess=np.unique(sess); cut=usess[int(0.65*len(usess))]
RES_U=usess[usess<cut]; LOCK_U=usess[usess>=cut]
def sharpe(p,e,uni):
    ds=np.zeros(len(uni)); ix={q:j for j,q in enumerate(uni)}
    for v,q in zip(p,sess[e]):
        if q in ix: ds[ix[q]]+=v
    return ds.mean()/ds.std()*np.sqrt(252) if ds.std()>0 else 0.0
def cell(p,e,uni):
    if len(p)==0: return f"{0:>5}{0:>9}{'--':>7}{'--':>7}{'--':>8}"
    w=p[p>0]; ls=p[p<=0]; pf=w.sum()/-ls.sum() if len(ls) else 99
    return f"{len(p):>5}{p.sum():>9,.0f}{pf:>7.2f}{100*len(w)/len(p):>7.1f}{sharpe(p,e,uni):>8.2f}"

CANDS = {
 "baseline (no filter)":        dict(),
 "ADX(14) > 20":                dict(adx_min=20),
 "ADX(14) > 25":                dict(adx_min=25),
 "ADX(14) > 30":                dict(adx_min=30),
 "ADX(14) rising over 3 bars":  dict(adx_rising=True),
 "ADX(14) > 20 AND rising":     dict(adx_min=20, adx_rising=True),
 "Stoch veto K>80 long/K<20 sh":dict(sto_veto=80),
 "Stoch veto K>70 long/K<30 sh":dict(sto_veto=70),
 "Stoch K>D alignment":         dict(sto_align=True),
 "ADX>20 + Stoch veto 80":      dict(adx_min=20, sto_veto=80),
}
print("="*94)
print("PRE-SPECIFIED FILTERS on the BOS/CHoCH + 2R book, MNQ 30m")
print("="*94)
print(f"{'':<32}{'RESEARCH':>36}   |{'LOCKED':>36}")
print(f"{'':<32}{'n':>5}{'net $':>9}{'PF':>7}{'win%':>7}{'Sh':>8}   |{'n':>7}{'net $':>9}{'PF':>7}{'win%':>7}{'Sh':>8}")
OUT={}
for tag,kw in CANDS.items():
    p,e=sim(**kw); m=sess[e]<cut; OUT[tag]=(p,e,m)
    print(f"{tag:<32}"+cell(p[m],e[m],RES_U)+"   |  "+cell(p[~m],e[~m],LOCK_U))

print(); print("="*94)
print("WHY THE STOCHASTIC VETO DESTROYS THE SAMPLE — %K at the moment the signal fires")
print("="*94)
K,D = STO[14]; A = ADX[14]
p0,e0 = sim()
# recover the signal bar's %K by side
sides=[]; ks=[]; adxs=[]
pos=0;bias=0;rn=0;bh=np.nan;bl=np.nan
for i in range(1,n):
    ns=sess[i]!=sess[i-1]
    bU=(not np.isnan(ph[i])) and c[i]>ph[i] and (np.isnan(bh) or ph[i]!=bh)
    bD=(not np.isnan(pl[i])) and c[i]<pl[i] and (np.isnan(bl) or pl[i]!=bl)
    if bU: bh=ph[i]
    if bD: bl=pl[i]
    if bU: bias,rn=(1,rn+1) if bias==1 else (1,1)
    if bD: bias,rn=(-1,rn+1) if bias==-1 else (-1,1)
    a=atr_[i]; ready=(a>0) and not np.isnan(a) and not np.isnan(ema_[i])
    ok=(i+1<n and trad[i] and trad[i+1] and not ns)
    far=ready and abs(c[i]-ema_[i])>=1.0*a
    if ok and ready and far:
        s_=1 if (bU and rn>=2 and c[i]>ema_[i]) else (-1 if (bD and rn>=2 and c[i]<ema_[i]) else 0)
        if s_ and not np.isnan(K[i]):
            sides.append(s_); ks.append(K[i]); adxs.append(A[i])
sides=np.array(sides); ks=np.array(ks); adxs=np.array(adxs)
for s_,nm in ((1,"LONG signals "),(-1,"SHORT signals")):
    x=ks[sides==s_]
    print(f"   {nm}: n={len(x):>3}   median %K {np.median(x):>5.1f}   "
          f"{'above 80' if s_==1 else 'below 20'}: {100*((x>80) if s_==1 else (x<20)).mean():>5.1f}%")
print(f"""
   A break of structure IS a new extreme of the recent range, and %K measures exactly where the
   close sits in that range. So a bullish BOS almost mechanically prints %K near 100. Vetoing
   "overbought" longs therefore vetoes the strategy: 92 trades become 9. The two ideas are not
   merely unhelpful together, they are contradictory by construction -- the oscillator is
   measuring the same thing the entry rule is built on.""")
print(f"   median ADX at signal: {np.median(adxs[~np.isnan(adxs)]):.1f}   "
      f"share of signals with ADX>25: {100*(adxs[~np.isnan(adxs)]>25).mean():.1f}%")

print(); print("="*94)
print("IS ADX REDUNDANT? — the 1-ATR-from-EMA range filter may already be a trend filter")
print("="*94)
Aok = A[~np.isnan(A)]
allbars = trad[~np.isnan(A)]
print(f"   ADX(14) across ALL in-session bars : median {np.median(Aok[allbars]):.1f}   "
      f"share > 25: {100*(Aok[allbars]>25).mean():.1f}%")
print(f"   ADX(14) at BOS signal bars         : median {np.median(adxs[~np.isnan(adxs)]):.1f}   "
      f"share > 25: {100*(adxs[~np.isnan(adxs)]>25).mean():.1f}%")
# what does the range filter alone do to the ADX distribution?
dist = np.abs(c-ema_)/atr_
sel = trad & (~np.isnan(A)) & (~np.isnan(dist))
print(f"   ADX where |close-EMA| >= 1 ATR     : median {np.median(A[sel & (dist>=1.0)]):.1f}   "
      f"share > 25: {100*(A[sel & (dist>=1.0)]>25).mean():.1f}%")
print(f"   ADX where |close-EMA| <  1 ATR     : median {np.median(A[sel & (dist<1.0)]):.1f}   "
      f"share > 25: {100*(A[sel & (dist<1.0)]>25).mean():.1f}%")
print("""
   The range filter already selects the high-ADX half of the tape. Requiring ADX on top of it is
   asking the same question twice: it removes trades without changing what kind of trade is left,
   which is why every ADX threshold cut the locked result while leaving the profile intact.""")

print(); print("="*94)
print("WIDER SEARCH — 3 ADX periods x 13 thresholds x rising on/off x 3 stoch periods x 6 vetos")
print("="*94)
rows=[]
for ap in (7,14,21):
    for amin in (0,10,12,15,18,20,22,25,28,30,35,40,45):
        for ar in (False,True):
            for sp in (9,14,21):
                for sv in (0,60,70,80,90,95):
                    p,e = sim(adx_p=ap, adx_min=amin, adx_rising=ar, sto_p=sp, sto_veto=sv)
                    if len(p)<20: continue
                    m=sess[e]<cut
                    if m.sum()<10 or (~m).sum()<8: continue
                    rows.append((p[m].sum(), sharpe(p[m],e[m],RES_U),
                                 p[~m].sum(), sharpe(p[~m],e[~m],LOCK_U), len(p),
                                 amin, sv, int(ar)))
R=np.array(rows)
print(f"   {len(R):,} cells with enough trades on both blocks")
rn_,rs_,ln_,ls_,ntr_,amin_,sv_,ar_ = [R[:,i] for i in range(8)]
b = int(np.argmax(rn_))
print(f"   best on RESEARCH  : research ${rn_[b]:,.0f} (Sh {rs_[b]:.2f})  ->  "
      f"LOCKED ${ln_[b]:,.0f} (Sh {ls_[b]:.2f})   [ADX>{amin_[b]:.0f}, stochVeto {sv_[b]:.0f}, rising {int(ar_[b])}]")
print(f"   BASELINE (no filter at all)          :  LOCKED $8,932 (Sh 1.70)")
print(f"   cells beating the baseline on LOCKED : {int((ln_>8932).sum())} of {len(R)} "
      f"({100*(ln_>8932).mean():.1f}%)")
print(f"   cells beating it on BOTH blocks      : {int(((ln_>8932)&(rn_>2747)).sum())}")
