import sys; sys.path.insert(0,'research')
import numpy as np, pandas as pd
from itertools import combinations
from bos_report import sc
from bos_choch import prep, random_control, nw_t

TF, MD = 30, 1.0
s = sc(TF, session="rth_0930_1600", min_ema_dist=MD)
pnl = s['_pnl']; n=len(pnl)
rng = np.random.default_rng(20250822)

print(f"  SHIPPED SPEC: {TF}m RTH, EMA200, 2xATR, k=3, refuse within {MD} ATR, in-session fills")
print(f"  n={n}  net=${pnl.sum():,.0f}  ${pnl.mean():.0f}/trade  PF={s['pf']:.2f}  "
      f"Sharpe={s['sharpe']:.2f}  maxDD={100*s['maxdd']:.1f}%  t={s['t']:.2f}\n")

# 1 bootstrap
bs=np.array([rng.choice(pnl,n,replace=True).mean() for _ in range(10000)])
lo,hi=np.percentile(bs,[2.5,97.5])
print(f"  bootstrap 95% CI            [{lo:+.0f}, {hi:+.0f}]   P(edge<=0)={100*(bs<=0).mean():.1f}%"
      f"   -> {'PASS' if lo>0 else 'FAIL'}")

# 2 random control on the FILTERED spec
long_share=float((s['_side']==1).mean())
ctrl=random_control(TF,"rth_0930_1600",n,long_share,reps=300,min_ema_dist=MD)
tot=ctrl[:,0]; pct=100*(tot<pnl.sum()).mean()
print(f"  random-entry control        BOS at {pct:.1f}th pctile (mean ${tot.mean():,.0f}, sd ${tot.std():,.0f})"
      f"   -> {'PASS' if pct>=95 else 'FAIL'}")

# 3 PBO on the filtered surface
GRID=[dict(ema_n=e,atr_mult=m,swing_k=k,min_ema_dist=MD) for e in (100,200,300) for m in (1.0,2.0,3.0) for k in (2,3,5)]
per=[]
for g in GRID:
    x=sc(TF, session="rth_0930_1600", **g)
    per.append((x['_pnl'],x['_ti']) if x.get('n',0)>=40 else None)
ok=[i for i,x in enumerate(per) if x is not None]
d=prep(TF); N=len(d['c']); S=8; b=np.linspace(0,N,S+1).astype(int)
M=np.full((len(ok),S),np.nan)
for r,i in enumerate(ok):
    p2,t2=per[i]
    for j in range(S):
        m=(t2>=b[j])&(t2<b[j+1])
        if m.sum()>=3: M[r,j]=p2[m].mean()
ranks=[]
for comb in combinations(range(S),S//2):
    ins=list(comb); oos=[x for x in range(S) if x not in ins]
    a=np.nanmean(M[:,ins],axis=1); bb=np.nanmean(M[:,oos],axis=1)
    if np.all(np.isnan(a)) or np.all(np.isnan(bb)): continue
    ranks.append(float(np.nanmean(bb<=bb[int(np.nanargmax(a))])))
ranks=np.array(ranks); pbo=(ranks<0.5).mean()
print(f"  PBO (CSCV, {len(ok)} configs)       {pbo:.3f}   -> {'PASS' if pbo<0.3 else 'FAIL'}")

# 4 monte carlo
dd=[];end=[];cap=100_000.
for _ in range(10000):
    x=rng.permutation(pnl); eq=cap+np.cumsum(x); pk=np.maximum.accumulate(eq)
    dd.append(((pk-eq)/pk).max()); end.append(eq[-1])
dd=np.array(dd);end=np.array(end)
print(f"  Monte Carlo (20k paths)     medianDD {100*np.median(dd):.1f}%  p95DD {100*np.percentile(dd,95):.1f}%"
      f"  P(loss) {100*(end<cap).mean():.1f}%  -> {'PASS' if (end<cap).mean()<0.10 else 'FAIL'}")

# 5 multiple-testing hurdle
for k,label in ((40,"timeframe x filter (8x5)"),(72,"the tf x session matrix")):
    h=np.sqrt(2*np.log(k))
    print(f"  E[max z] over {k:>2} cells ({label:<24}) = {h:.2f}  vs t={s['t']:.2f}"
          f"  -> {'PASS' if s['t']>h else 'FAIL'}")

# 6 both sides
for sm,nm in ((1,'longs'),(-1,'shorts')):
    x=sc(TF, session="rth_0930_1600", min_ema_dist=MD, side_mode=sm)
    print(f"  {nm:<6} only                 n={x['n']:>4}  ${x['total']:>9,.0f}  t={x['t']:.2f}")
