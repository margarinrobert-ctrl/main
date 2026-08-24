"""Long/short split, EMA-distance structure, and the 1:1 RR question."""
import sys; sys.path.insert(0,'research')
import numpy as np
from bos_choch import prep

d=prep(30); o,h,l,c=d['o'],d['h'],d['l'],d['c']; sess,mod=d['sess'],d['mod']
ph,pl,ema_,atr_=d['ph'],d['pl'],d['ema'],d['atr']; n=len(c)
tick=0.25; PV=2.0; COMM=1.0; EC=(1.0+1.0)*tick; SE=1.0*tick
trad=(mod>=570)&(mod<960)

def sim(atr_mult=2.0, n_bos=2, dmin=1.0, dmax=1e9, tp_r=0.0, side=0):
    """dmin/dmax : |close-EMA| in ATRs must lie in [dmin, dmax]
       tp_r      : take-profit at tp_r x risk (0 = none, CHoCH/stop only)
       side      : 0 both, 1 long only, -1 short only"""
    pos=0;entry=0.;stopL=np.nan;tp=np.nan;risk=0.;bias=0;rn=0;bh=np.nan;bl=np.nan
    aSig=np.nan;pend=0;pnl=[];ent=[];sd=[];why=[];ei=0
    for i in range(1,n):
        ns=sess[i]!=sess[i-1]
        if pend!=0 and pos==0:
            pos=pend;entry=o[i];ei=i;pend=0
            risk=atr_mult*aSig; stopL=entry-pos*risk
            tp = entry+pos*tp_r*risk if tp_r>0 else np.nan
        if pos!=0:
            hit=(l[i]<=stopL) if pos==1 else (h[i]>=stopL)
            won=(not np.isnan(tp)) and ((h[i]>=tp) if pos==1 else (l[i]<=tp))
            if hit and won:
                # both touched in one bar: assume the STOP filled first (conservative)
                won=False
            if hit:
                px=o[i] if ((pos==1 and o[i]<stopL) or (pos==-1 and o[i]>stopL)) else stopL
                px += -SE if pos==1 else SE
                pnl.append(pos*(px-entry)*PV-2*EC*PV-COMM);ent.append(ei);sd.append(pos);why.append(1)
                pos=0;stopL=np.nan;tp=np.nan
            elif won:
                px=o[i] if ((pos==1 and o[i]>tp) or (pos==-1 and o[i]<tp)) else tp
                pnl.append(pos*(px-entry)*PV-2*EC*PV-COMM);ent.append(ei);sd.append(pos);why.append(3)
                pos=0;stopL=np.nan;tp=np.nan
        bU=(not np.isnan(ph[i])) and c[i]>ph[i] and (np.isnan(bh) or ph[i]!=bh)
        bD=(not np.isnan(pl[i])) and c[i]<pl[i] and (np.isnan(bl) or pl[i]!=bl)
        if bU: bh=ph[i]
        if bD: bl=pl[i]
        if bU: bias,rn=(1,rn+1) if bias==1 else (1,1)
        if bD: bias,rn=(-1,rn+1) if bias==-1 else (-1,1)
        a=atr_[i]; ready=(a>0) and not np.isnan(a) and not np.isnan(ema_[i])
        ok=(i+1<n and trad[i] and trad[i+1] and not ns)
        dist = abs(c[i]-ema_[i])/a if ready else np.nan
        band = ready and (dist>=dmin) and (dist<=dmax)
        if pos==0 and pend==0 and ok and ready and band:
            s_=1 if (bU and rn>=n_bos and c[i]>ema_[i]) else (-1 if (bD and rn>=n_bos and c[i]<ema_[i]) else 0)
            if s_ and (side==0 or side==s_): aSig=a; pend=s_
        if pos!=0 and tp_r<=0 and ((pos==1 and bD) or (pos==-1 and bU)) and i+1<n:
            pnl.append(pos*(o[i+1]-entry)*PV-2*EC*PV-COMM);ent.append(ei);sd.append(pos);why.append(2)
            pos=0;stopL=np.nan
    return np.array(pnl),np.array(ent),np.array(sd),np.array(why)

def st(p):
    if len(p)==0: return "        (no trades)"
    w=p[p>0]; ls=p[p<=0]; eq=np.cumsum(p)
    dd=(np.maximum.accumulate(np.r_[0,eq])-np.r_[0,eq]).max()
    pf = w.sum()/-ls.sum() if len(ls) else np.inf
    return f"{len(p):>5}{p.sum():>10,.0f}{pf:>7.2f}{100*len(w)/len(p):>7.1f}{p.mean():>9,.0f}{dd:>9,.0f}"

H=f"{'':<44}{'n':>5}{'net $':>10}{'PF':>7}{'win%':>7}{'$/trade':>9}{'maxDD':>9}"
print("="*82); print("1. LONGS vs SHORTS — baseline v7 spec"); print("="*82); print(H)
p,e,s,w = sim()
print(f"{'all trades':<44}"+st(p))
print(f"{'  LONGS only':<44}"+st(p[s==1]))
print(f"{'  SHORTS only':<44}"+st(p[s==-1]))
print(f"\n   long share of trades {100*(s==1).mean():.1f}%   of net P&L {100*p[s==1].sum()/p.sum():.1f}%")

print(); print("="*82)
print("2. WHERE ARE ENTRIES ACTUALLY PAID? distance from EMA-200 at the signal")
print("="*82); print(H)
bands=[(0.0,0.5),(0.5,1.0),(1.0,1.5),(1.5,2.5),(2.5,1e9)]
for lo,hi in bands:
    pp,ee,ss,ww = sim(dmin=lo,dmax=hi)
    tag=f"  |close-EMA| in [{lo:.1f}, {hi:.1f}) ATR" if hi<1e9 else f"  |close-EMA| >= {lo:.1f} ATR"
    print(f"{tag:<44}"+st(pp))
print()
pn,_,_,_ = sim(dmin=0.0, dmax=1.0)
pf_,_,_,_ = sim(dmin=1.0, dmax=1e9)
print(f"{'  NEAR the EMA only (< 1 ATR)  <- your idea':<44}"+st(pn))
print(f"{'  FAR from the EMA (>= 1 ATR)  <- current':<44}"+st(pf_))

print(); print("="*82)
print("3. CAN A 1:1 RR REACH 65% WIN? — take-profit sweep, stop fixed at 2 x ATR")
print("="*82); print(H)
for r in (0.5,0.75,1.0,1.5,2.0,3.0):
    pp,ee,ss,ww=sim(tp_r=r)
    tag=f"  take-profit at {r:.2f} R  (RR {r:.2f}:1)"
    print(f"{tag:<44}"+st(pp))
print(f"{'  no take-profit (CHoCH exit) = baseline':<44}"+st(sim()[0]))
print("""
   THE BOUND. For a price path with no drift, the probability of touching +R before -R is
   exactly  R_down / (R_up + R_down).  At 1:1 that is 50.0% BEFORE costs -- it is a property of
   the barriers, not of the signal. To print 65% at 1:1 the entry would need to shift that
   probability by 15 points, which is an enormous directional edge; nothing in three years of
   this data comes close. The numbers above are what the barriers actually pay.""")

print(); print("="*82)
print("4. THE TAKE-PROFIT LOOKS LIKE A BIG WIN IN-SAMPLE. HOLD IT OUT.")
print("="*82)
usess=np.unique(sess); cut=usess[int(0.65*len(usess))]
print(f"{'':<30}{'RESEARCH (first 65%)':>34}   |{'LOCKED (final 35%)':>34}")
print(f"{'':<30}{'n':>5}{'net $':>10}{'PF':>7}{'win%':>7}   |{'n':>7}{'net $':>10}{'PF':>7}{'win%':>7}")
def blk(p,e,m):
    x=p[m]
    if len(x)==0: return f"{0:>5}{0:>10}{0:>7}{0:>7}"
    w=x[x>0]; ls=x[x<=0]
    pf=w.sum()/-ls.sum() if len(ls) else 99
    return f"{len(x):>5}{x.sum():>10,.0f}{pf:>7.2f}{100*len(w)/len(x):>7.1f}"
rows={}
for r in (0.0,1.0,1.5,2.0,3.0):
    p,e,s,w = sim(tp_r=r)
    m=sess[e]<cut
    rows[r]=(p,e,m)
    tag = "baseline (CHoCH exit)" if r==0 else f"take-profit {r:.1f} R"
    print(f"{tag:<30}"+blk(p,e,m)+"   |"+blk(p,e,~m).replace(f"{len(p[m]):>5}",f"{len(p[~m]):>7}",1))
print()
for r in (0.0,1.0,1.5,2.0,3.0):
    p,e,m = rows[r]
    a,b = p[m].sum(), p[~m].sum()
    tag = "baseline" if r==0 else f"TP {r:.1f}R"
    print(f"   {tag:<12} research ${a:>8,.0f}   LOCKED ${b:>8,.0f}   "
          f"locked/research ratio {b/a if a>0 else float('nan'):>5.2f}")

def sim2(atr_mult=2.0, tp_r=0.0, keep_choch=True, dmin=1.0, n_bos=2, side=0):
    """As sim() but the CHoCH exit can COEXIST with a take-profit."""
    pos=0;entry=0.;stopL=np.nan;tp=np.nan;risk=0.;bias=0;rn=0;bh=np.nan;bl=np.nan
    aSig=np.nan;pend=0;pnl=[];ent=[];sd=[];ei=0
    for i in range(1,n):
        ns=sess[i]!=sess[i-1]
        if pend!=0 and pos==0:
            pos=pend;entry=o[i];ei=i;pend=0
            risk=atr_mult*aSig; stopL=entry-pos*risk
            tp = entry+pos*tp_r*risk if tp_r>0 else np.nan
        if pos!=0:
            hit=(l[i]<=stopL) if pos==1 else (h[i]>=stopL)
            won=(not np.isnan(tp)) and ((h[i]>=tp) if pos==1 else (l[i]<=tp))
            if hit:
                px=o[i] if ((pos==1 and o[i]<stopL) or (pos==-1 and o[i]>stopL)) else stopL
                px += -SE if pos==1 else SE
                pnl.append(pos*(px-entry)*PV-2*EC*PV-COMM);ent.append(ei);sd.append(pos);pos=0;stopL=np.nan;tp=np.nan
            elif won:
                px=o[i] if ((pos==1 and o[i]>tp) or (pos==-1 and o[i]<tp)) else tp
                pnl.append(pos*(px-entry)*PV-2*EC*PV-COMM);ent.append(ei);sd.append(pos);pos=0;stopL=np.nan;tp=np.nan
        bU=(not np.isnan(ph[i])) and c[i]>ph[i] and (np.isnan(bh) or ph[i]!=bh)
        bD=(not np.isnan(pl[i])) and c[i]<pl[i] and (np.isnan(bl) or pl[i]!=bl)
        if bU: bh=ph[i]
        if bD: bl=pl[i]
        if bU: bias,rn=(1,rn+1) if bias==1 else (1,1)
        if bD: bias,rn=(-1,rn+1) if bias==-1 else (-1,1)
        a=atr_[i]; ready=(a>0) and not np.isnan(a) and not np.isnan(ema_[i])
        ok=(i+1<n and trad[i] and trad[i+1] and not ns)
        band = ready and abs(c[i]-ema_[i])/a >= dmin
        if pos==0 and pend==0 and ok and ready and band:
            s_=1 if (bU and rn>=n_bos and c[i]>ema_[i]) else (-1 if (bD and rn>=n_bos and c[i]<ema_[i]) else 0)
            if s_ and (side==0 or side==s_): aSig=a; pend=s_
        if pos!=0 and keep_choch and ((pos==1 and bD) or (pos==-1 and bU)) and i+1<n:
            pnl.append(pos*(o[i+1]-entry)*PV-2*EC*PV-COMM);ent.append(ei);sd.append(pos);pos=0;stopL=np.nan;tp=np.nan
    return np.array(pnl),np.array(ent),np.array(sd)

print(); print("="*82)
print("5. TAKE-PROFIT **PLUS** THE CHoCH EXIT (whichever comes first)"); print("="*82)
print(f"{'':<32}{'RESEARCH':>26}   |{'LOCKED':>26}")
print(f"{'':<32}{'n':>5}{'net $':>9}{'PF':>6}{'win%':>6}   |{'n':>7}{'net $':>9}{'PF':>6}{'win%':>6}")
cands={}
for tag,kw in (("baseline: CHoCH only",dict(tp_r=0.0,keep_choch=True)),
               ("TP 2R only (no CHoCH)",dict(tp_r=2.0,keep_choch=False)),
               ("TP 2R + CHoCH",        dict(tp_r=2.0,keep_choch=True)),
               ("TP 3R + CHoCH",        dict(tp_r=3.0,keep_choch=True)),
               ("TP 1.5R + CHoCH",      dict(tp_r=1.5,keep_choch=True))):
    p,e,s = sim2(**kw); m=sess[e]<cut; cands[tag]=(p,e,m)
    def f(x):
        if len(x)==0: return f"{0:>5}{0:>9}{0:>6}{0:>6}"
        w=x[x>0]; ls=x[x<=0]; pf=w.sum()/-ls.sum() if len(ls) else 99
        return f"{len(x):>5}{x.sum():>9,.0f}{pf:>6.2f}{100*len(w)/len(x):>6.1f}"
    print(f"{tag:<32}"+f(p[m])+"   |  "+f(p[~m]))

print(); print("="*82)
print("6. WALK-FORWARD, 6 expanding folds, re-selecting the exit each fold"); print("="*82)
folds=np.array_split(usess,7)
# SHARPE: the series must span EVERY session in the block, with zero on days that did not trade.
# Building it from sessions that HELD a trade and then multiplying by sqrt(252) annualises a
# ~140-day series as though every day of the year were a trading day. This rule is flat on ~85%
# of sessions, so that inflated Sharpe by ~2.6x (see docs/ib/STUDY_MNQ_LIVE.md).
def dsh(p,e,mask,universe=None):
    x=p[mask]; s=sess[e][mask]
    if len(x)<5: return -9
    if universe is None: universe = np.unique(sess)
    ds = np.zeros(len(universe)); idx = {q:j for j,q in enumerate(universe)}
    for v,q in zip(x,s):
        if q in idx: ds[idx[q]] += v
    return ds.mean()/ds.std()*np.sqrt(252) if ds.std()>0 else 0
sel=[];bas=[];fix=[]
for k in range(1,7):
    ins=np.concatenate(folds[:k]); oos=folds[k]
    best=None;bs=-9
    for tag,(p,e,m) in cands.items():
        sh=dsh(p,e,np.isin(sess[e],ins))
        if sh>bs: bs,best=sh,tag
    p,e,_=cands[best]; mo=np.isin(sess[e],oos); sel.append(p[mo])
    pb,eb,_=cands["baseline: CHoCH only"]; bas.append(pb[np.isin(sess[eb],oos)])
    pf2,ef2,_=cands["TP 2R + CHoCH"];      fix.append(pf2[np.isin(sess[ef2],oos)])
    print(f"   fold {k}: picked {best:<24} OOS ${p[mo].sum():>7,.0f}")
S,B,F=np.concatenate(sel),np.concatenate(bas),np.concatenate(fix)
print(f"\n   stitched OOS, re-selecting each fold      ${S.sum():>8,.0f}")
print(f"   stitched OOS, fixed baseline (CHoCH only) ${B.sum():>8,.0f}")
print(f"   stitched OOS, fixed 'TP 2R + CHoCH'       ${F.sum():>8,.0f}")

print(); print("="*82)
print("7. FULL VALIDATION OF 'STOP 2xATR / TARGET 2R, NO CHoCH EXIT'"); print("="*82)
rng=np.random.default_rng(20260823)
pB,eB,sB = sim2(tp_r=0.0,keep_choch=True)
pT,eT,sT = sim2(tp_r=2.0,keep_choch=False)
def full(tag,p,e):
    w=p[p>0]; ls=p[p<=0]; eq=np.cumsum(p)
    dd=(np.maximum.accumulate(np.r_[0,eq])-np.r_[0,eq]).max()
    u=np.unique(sess); ds=np.zeros(len(u)); ix={q:j for j,q in enumerate(u)}
    for v,q in zip(p,sess[e]): ds[ix[q]] += v
    sh=ds.mean()/ds.std()*np.sqrt(252)
    print(f"{tag:<26}{len(p):>5}{p.sum():>10,.0f}{w.sum()/-ls.sum():>7.2f}"
          f"{100*len(w)/len(p):>7.1f}{dd:>9,.0f}{sh:>8.2f}{p.sum()/dd:>8.2f}")
    return ds
print(f"{'':<26}{'n':>5}{'net $':>10}{'PF':>7}{'win%':>7}{'maxDD':>9}{'Sharpe':>8}{'Calmar':>8}")
dsB=full("baseline (CHoCH)",pB,eB)
dsT=full("TP 2R, no CHoCH",pT,eT)

print(f"\n   LONG vs SHORT under the new exit:")
for nm,msk in (("longs",sT==1),("shorts",sT==-1)):
    x=pT[msk]; w=x[x>0]
    print(f"      {nm:<8}{len(x):>5} trades  ${x.sum():>8,.0f}  PF {w.sum()/-x[x<=0].sum():>5.2f}"
          f"  win {100*len(w)/len(x):>5.1f}%")

def boot(x,B=5000,mb=5):
    out=np.empty((B,3)); N=len(x)
    for b in range(B):
        path=[]
        while len(path)<N:
            st_=rng.integers(0,N); L=1+rng.geometric(1/mb)
            path.extend(x[(st_+np.arange(L))%N])
        a=np.array(path[:N]); eq=np.cumsum(a)
        out[b]=[a.sum(),(np.maximum.accumulate(np.r_[0,eq])-np.r_[0,eq]).max(),
                a.mean()/a.std()*np.sqrt(252) if a.std()>0 else 0]
    return out
print(f"\n   Monte Carlo, 5,000 block-bootstrap paths (TP 2R):")
Bt=boot(dsT)
for j,nm,f_ in ((0,"net $","{:,.0f}"),(1,"max drawdown $","{:,.0f}"),(2,"Sharpe","{:.2f}")):
    q=np.percentile(Bt[:,j],[5,50,95])
    print(f"      {nm:<16} p5 "+f_.format(q[0])+"   median "+f_.format(q[1])+"   p95 "+f_.format(q[2]))
print(f"      P(net < 0) = {100*(Bt[:,0]<0).mean():.1f}%")
Bb=boot(dsB)
print(f"      baseline for comparison: median net ${np.median(Bb[:,0]):,.0f}, "
      f"P(net<0) {100*(Bb[:,0]<0).mean():.1f}%")
print(f"\n   Paired daily difference (TP2R - baseline), same sessions:")
u=np.union1d(np.unique(sess[eT]),np.unique(sess[eB]))
a=np.array([pT[sess[eT]==q].sum() for q in u]); b=np.array([pB[sess[eB]==q].sum() for q in u])
dif=a-b
t=dif.mean()/(dif.std(ddof=1)/np.sqrt(len(dif)))
print(f"      mean ${dif.mean():+,.1f}/session over {len(dif)} sessions, t = {t:+.2f}")
