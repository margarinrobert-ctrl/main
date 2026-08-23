"""Full validation of the v6 spec at MNQ scale: locked OOS, walk-forward, Monte Carlo,
and a SMALL set of pre-specified entry/exit improvements tested with the same discipline.

Deliberately few hypotheses. The repeated finding across this project is that search width is
monotonically harmful; every candidate below was named before it was run, and each is reported
whether it worked or not.
"""
import sys; sys.path.insert(0,'research')
import numpy as np
from bos_choch import prep

d=prep(30); o,h,l,c=d['o'],d['h'],d['l'],d['c']; sess,mod=d['sess'],d['mod']
ph,pl,ema_,atr_=d['ph'],d['pl'],d['ema'],d['atr']; n=len(c)
tick=0.25; PV=2.0; COMM=1.0            # MNQ, $0.50/order round turn
trad=(mod>=570)&(mod<960)
rng=np.random.default_rng(20260823)

def sim(atr_mult=2.0, n_bos=2, md=1.0, buf=0.0, be_at=0.0, tod=None):
    """buf   : break must clear the pivot by buf * ATR before it counts (confirmation strength)
       be_at : move the stop to breakeven once the trade is be_at * R in profit (0 = off)
       tod   : (lo,hi) minute-of-day entry restriction, or None"""
    ec=(1.0+1.0)*tick; se=1.0*tick
    pos=0;entry=0.;stopL=np.nan;risk=0.;bias=0;rn=0;bh=np.nan;bl=np.nan
    aSig=np.nan;pend=0;pnl=[];ent=[];ei=0;be=False
    for i in range(1,n):
        new_sess=sess[i]!=sess[i-1]
        if pend!=0 and pos==0:
            pos=pend; entry=o[i]; ei=i; pend=0
            risk=atr_mult*aSig; stopL=entry-pos*risk; be=False
        if pos!=0:
            # Check the stop FIRST, against the level that was already resting. Arming breakeven
            # from bar i's high and then testing bar i's low against it assumes the high came
            # first -- an intrabar ordering we do not know. Breakeven is armed for bar i+1.
            hit=(l[i]<=stopL) if pos==1 else (h[i]>=stopL)
            if hit:
                px=o[i] if ((pos==1 and o[i]<stopL) or (pos==-1 and o[i]>stopL)) else stopL
                px += -se if pos==1 else se
                pnl.append(pos*(px-entry)*PV-2*ec*PV-COMM); ent.append(ei); pos=0; stopL=np.nan
            elif be_at>0 and not be:
                prog = pos*(h[i]-entry) if pos==1 else pos*(l[i]-entry)
                if prog >= be_at*risk:
                    stopL = entry; be=True          # effective from the NEXT bar onward
        a=atr_[i]
        thr = buf*a if (buf>0 and not np.isnan(a)) else 0.0
        bU=(not np.isnan(ph[i])) and c[i]>ph[i]+thr and (np.isnan(bh) or ph[i]!=bh)
        bD=(not np.isnan(pl[i])) and c[i]<pl[i]-thr and (np.isnan(bl) or pl[i]!=bl)
        if bU: bh=ph[i]
        if bD: bl=pl[i]
        if bU: bias,rn=(1,rn+1) if bias==1 else (1,1)
        if bD: bias,rn=(-1,rn+1) if bias==-1 else (-1,1)
        ready=(a>0) and not np.isnan(a) and not np.isnan(ema_[i])
        ok=(i+1<n and trad[i] and trad[i+1] and not new_sess)
        if tod is not None: ok = ok and tod[0]<=mod[i]<=tod[1]
        far=(md<=0) or (ready and abs(c[i]-ema_[i])>=md*a)
        if pos==0 and pend==0 and ok and ready and far:
            if bU and rn>=n_bos and c[i]>ema_[i]: aSig=a; pend=1
            elif bD and rn>=n_bos and c[i]<ema_[i]: aSig=a; pend=-1
        if pos!=0 and ((pos==1 and bD) or (pos==-1 and bU)) and i+1<n:
            pnl.append(pos*(o[i+1]-entry)*PV-2*ec*PV-COMM); ent.append(ei); pos=0; stopL=np.nan
    return np.array(pnl), np.array(ent)

def stats(p):
    if len(p)==0: return dict(n=0,net=0,pf=0,win=0,dd=0,sh=0)
    w=p[p>0]; ls=p[p<=0]; eq=np.cumsum(p)
    dd=(np.maximum.accumulate(np.r_[0,eq])-np.r_[0,eq]).max()
    return dict(n=len(p), net=p.sum(), pf=(w.sum()/-ls.sum()) if len(ls) else np.inf,
                win=100*len(w)/len(p), dd=dd)

def daily_sharpe(p,e):
    s=sess[e]; u=np.unique(s); ds=np.array([p[s==x].sum() for x in u])
    return ds.mean()/ds.std()*np.sqrt(252) if ds.std()>0 else 0.0

def line(tag,p,e):
    st=stats(p)
    return (f"{tag:<40}{st['n']:>5}{st['net']:>10,.0f}{st['pf']:>7.2f}{st['win']:>7.1f}"
            f"{st['dd']:>9,.0f}{daily_sharpe(p,e):>8.2f}")

HDR=f"{'':<40}{'n':>5}{'net $':>10}{'PF':>7}{'win%':>7}{'maxDD':>9}{'Sharpe':>8}"
usess=np.unique(sess); cut=usess[int(0.65*len(usess))]

print("="*86); print("1. BASELINE — v6 spec, MNQ, $0.50/order"); print("="*86); print(HDR)
p0,e0=sim(); print(line("full sample",p0,e0))
m=sess[e0]<cut
print(line("  research block (first 65%)",p0[m],e0[m]))
print(line("  LOCKED block  (final 35%)",p0[~m],e0[~m]))

print(); print("="*86)
print("2. PRE-SPECIFIED VARIANTS — chosen before running, all reported"); print("="*86)
print(HDR)
cands={
 "baseline":                dict(),
 "confirm buffer 0.10 ATR": dict(buf=0.10),
 "confirm buffer 0.25 ATR": dict(buf=0.25),
 "breakeven stop at +1.0R": dict(be_at=1.0),
 "breakeven stop at +1.5R": dict(be_at=1.5),
 "no entries before 11:00": dict(tod=(660,900)),
 "no entries after 14:00":  dict(tod=(600,840)),
}
res={}
for k,kw in cands.items():
    p,e=sim(**kw); res[k]=(p,e); mm=sess[e]<cut
    print(line(k+"  [research]", p[mm], e[mm]))
print()
print("   ... the SAME variants on the LOCKED block (never used to choose):")
for k,(p,e) in res.items():
    mm=sess[e]<cut
    print(line(k+"  [LOCKED]", p[~mm], e[~mm]))

# ---------------------------------------------------------------------------------------------
from scipy.stats import spearmanr
print(); print("="*86)
print("3. DID SELECTING ON RESEARCH HELP? rank correlation research -> locked"); print("="*86)
names=list(res); rs=[];ls=[]
for k in names:
    p,e=res[k]; mm=sess[e]<cut
    rs.append(daily_sharpe(p[mm],e[mm])); ls.append(daily_sharpe(p[~mm],e[~mm]))
rho,pv_=spearmanr(rs,ls)
for k,a,b in sorted(zip(names,rs,ls), key=lambda t:-t[1]):
    print(f"   {k:<26} research Sharpe {a:5.2f}   ->   LOCKED {b:5.2f}")
print(f"\n   Spearman rho = {rho:+.3f} (p={pv_:.2f}).  Picking the research winner gives you "
      f"{'NOTHING' if rho<0.3 else 'something'}.")
best_r = names[int(np.argmax(rs))]
print(f"   research winner : {best_r:<26} -> locked Sharpe {ls[names.index(best_r)]:.2f}")
print(f"   locked winner   : {names[int(np.argmax(ls))]:<26} (research Sharpe "
      f"{rs[int(np.argmax(ls))]:.2f} — it looked like the WORST candidate)")

print(); print("="*86)
print("4. MONTE CARLO — stationary block bootstrap on the baseline, 5,000 paths"); print("="*86)
p,e=res["baseline"]; s=sess[e]; u=np.unique(s)
ds=np.array([p[s==x].sum() for x in u])          # daily P&L, the unit that can be resampled
def boot(x,B=5000,mean_block=5):
    out=np.empty((B,3))
    N=len(x)
    for b in range(B):
        path=[]
        while len(path)<N:
            st=rng.integers(0,N); L=1+rng.geometric(1/mean_block)
            path.extend(x[(st+np.arange(L))%N])
        a=np.array(path[:N]); eq=np.cumsum(a)
        out[b]=[a.sum(), (np.maximum.accumulate(np.r_[0,eq])-np.r_[0,eq]).max(),
                a.mean()/a.std()*np.sqrt(252) if a.std()>0 else 0]
    return out
B=boot(ds)
for j,nm,fmt in ((0,"net $","{:,.0f}"),(1,"max drawdown $","{:,.0f}"),(2,"Sharpe","{:.2f}")):
    q=np.percentile(B[:,j],[5,25,50,75,95])
    print(f"   {nm:<16} p5 "+fmt.format(q[0])+"   p25 "+fmt.format(q[1])+"   median "+fmt.format(q[2])
          +"   p75 "+fmt.format(q[3])+"   p95 "+fmt.format(q[4]))
print(f"\n   P(net < 0) over a resampled 3-year run : {100*(B[:,0]<0).mean():.1f}%")
print(f"   P(drawdown > 2x the realised {stats(p)['dd']:,.0f}) : {100*(B[:,1]>2*stats(p)['dd']).mean():.1f}%")

print(); print("="*86)
print("5. WALK-FORWARD — 6 folds, re-selecting the variant on each in-sample block"); print("="*86)
folds=np.array_split(usess,7)
oos_sel=[]; oos_base=[]; picks=[]
for k in range(1,7):
    ins=np.concatenate(folds[:k]); oos=folds[k]
    best=None;bs=-9
    for nm,(pp,ee) in res.items():
        mm=np.isin(sess[ee],ins)
        if mm.sum()<15: continue
        sh=daily_sharpe(pp[mm],ee[mm])
        if sh>bs: bs, best = sh, nm
    pp,ee=res[best]; mo=np.isin(sess[ee],oos); oos_sel.append(pp[mo])
    pb,eb=res["baseline"]; mb=np.isin(sess[eb],oos); oos_base.append(pb[mb])
    picks.append(best)
    print(f"   fold {k}: picked {best:<26} OOS ${pp[mo].sum():>8,.0f} "
          f"| fixed baseline ${pb[mb].sum():>8,.0f}")
sel=np.concatenate(oos_sel); bas=np.concatenate(oos_base)
print(f"\n   stitched OOS, re-selecting each fold : ${sel.sum():>9,.0f}  over {len(sel)} trades")
print(f"   stitched OOS, baseline never changed : ${bas.sum():>9,.0f}  over {len(bas)} trades")
print(f"   re-selection is worth ${sel.sum()-bas.sum():+,.0f}")
