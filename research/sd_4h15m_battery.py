"""Sweep, OOS, walk-forward and Monte Carlo on the 4H-zone / 15M-confirmation strategy,
plus the diagnostic that actually matters: excess win rate over the driftless barrier bound."""
import sys, itertools, time; sys.path.insert(0,'research')
import numpy as np, pandas as pd
from sd_4h15m import build_zones, run
from bos_choch import prep, SPECS
S=SPECS['MNQ']; A=(S['pv'],S['tick'],1.0,S['spread_t'],S['slip_t'],S['stop_slip_t'])
rng=np.random.default_rng(20260823)
h4=prep(240); m15=prep(15)
trad=((m15['mod']>=570)&(m15['mod']<960)).astype(np.uint8)
u=np.unique(m15['sess']); cut=u[int(0.65*len(u))]; RU=u[u<cut]; LU=u[u>=cut]
IDX=m15['df'].index.values

ZC={}
def zones(bk,bm,dm,zt):
    key=(bk,bm,dm,zt)
    if key not in ZC:
        zl,zh,zd,zb = build_zones(h4['o'],h4['h'],h4['l'],h4['c'],h4['atr'],bk,bm,dm,zt)
        ct = h4['df'].index[zb] + pd.Timedelta(minutes=240)
        ZC[key]=(zl,zh,zd,np.searchsorted(IDX, ct.values, side='left').astype(np.int64))
    return ZC[key]

def dser(p,e,uni):
    ds=np.zeros(len(uni)); ix={q:j for j,q in enumerate(uni)}
    for v,q in zip(p, m15['sess'][e]):
        if q in ix: ds[ix[q]]+=v
    return ds

rows=[];keys=[];t0=time.time()
for bk,bm,dm,zt,buf,tp,nb,ag,os_,sm in itertools.product(
        (1,2,3),(0.6,1.0,1.5),(0.8,1.2,1.8),(0,1,2),(0.15,0.3,0.6,1.0),
        (1.5,2.0,3.0),(0,1),(200,400,1200),(0,1),(-1,0,1)):
    zl,zh,zd,zs = zones(bk,bm,dm,zt)
    if len(zl)<10: continue
    p,e,s,w = run(m15['o'],m15['h'],m15['l'],m15['c'],m15['sess'],trad,m15['atr'],
                  zl,zh,zd,zs,buf,tp,nb,ag,os_,sm,*A)
    if len(p)<40: continue
    ss=m15['sess'][e]; msk=ss<cut
    if msk.sum()<20 or (~msk).sum()<15: continue
    bound=100.0/(1.0+tp)                       # driftless P(target before stop), in %
    rows.append((p[msk].sum(), p[~msk].sum(), len(p), 100*(p>0).mean(), bound,
                 100*(p>0).mean()-bound, tp, nb, buf, zt, bk))
    keys.append((bk,bm,dm,zt,buf,tp,nb,ag,os_,sm))
R=np.array(rows)
print(f"{len(R):,} configurations with >=40 trades, {time.time()-t0:.0f}s\n")
rn,ln,ntr,wr,bd,ex = R[:,0],R[:,1],R[:,2],R[:,3],R[:,4],R[:,5]

print("="*92); print("1. OUT-OF-SAMPLE"); print("="*92)
b=int(np.argmax(rn))
print(f"   best on RESEARCH    research ${rn[b]:>9,.0f}  ->  LOCKED ${ln[b]:>9,.0f}   ({keys[b]})")
print(f"   best on LOCKED      ${ln.max():>9,.0f}  (hindsight)")
print(f"   MEDIAN locked       ${np.median(ln):>9,.0f}")
print(f"   positive research {100*(rn>0).mean():.1f}%   locked {100*(ln>0).mean():.1f}%"
      f"   BOTH {100*((rn>0)&(ln>0)).mean():.1f}%")
print(f"   BOS/CHoCH 2R book, same locked block: $8,932")

print(); print("="*92)
print("2. THE TEST THAT MATTERS — win rate against the driftless barrier bound")
print("   For a path with no drift, P(target before stop) = 1/(1+R). Any entry rule that adds")
print("   nothing scores exactly that. The BOS/CHoCH signal scores +10.7 points at 2:1.")
print("="*92)
print(f"{'target':<10}{'bound %':>9}{'mean win %':>12}{'EXCESS':>9}{'best excess':>13}{'n cfgs':>8}")
for t_ in (1.5,2.0,3.0):
    m=R[:,6]==t_
    if m.sum()==0: continue
    print(f"{f'{t_:.1f}R':<10}{bd[m][0]:>9.1f}{wr[m].mean():>12.1f}{ex[m].mean():>9.2f}"
          f"{ex[m].max():>13.2f}{int(m.sum()):>8}")
print(f"\n   share of configurations with a POSITIVE excess: {100*(ex>0).mean():.1f}%")
print(f"   mean excess across all {len(R):,} configurations: {ex.mean():+.2f} points")

print(); print("="*92); print("3. WALK-FORWARD on the research winner"); print("="*92)
p,e,s,w = run(m15['o'],m15['h'],m15['l'],m15['c'],m15['sess'],trad,m15['atr'],
              *zones(*keys[b][:4]), keys[b][4],keys[b][5],keys[b][6],keys[b][7],keys[b][8],keys[b][9], *A)
folds=np.array_split(u,7); oo=[]
for kf in range(1,7):
    ins=np.concatenate(folds[:kf]); out=folds[kf]
    mi=np.isin(m15['sess'][e],ins); mo=np.isin(m15['sess'][e],out)
    print(f"   fold {kf}: in-sample ${p[mi].sum():>9,.0f}  ->  OOS ${p[mo].sum():>9,.0f}")
    oo.append(p[mo].sum())
print(f"   stitched OOS ${sum(oo):>9,.0f}   (negative folds {sum(1 for x in oo if x<0)} of 6)")

print(); print("="*92); print("4. MONTE CARLO, 5,000 block-bootstrap paths"); print("="*92)
ds=dser(p,e,u); N=len(ds); out=np.empty((5000,2))
for i in range(5000):
    path=[]
    while len(path)<N:
        s0=rng.integers(0,N); L=1+rng.geometric(1/5)
        path.extend(ds[(s0+np.arange(L))%N])
    arr=np.array(path[:N]); eq=np.cumsum(arr)
    out[i]=[arr.sum(),(np.maximum.accumulate(np.r_[0,eq])-np.r_[0,eq]).max()]
q=np.percentile(out[:,0],[5,50,95])
print(f"   net $  p5 ${q[0]:>8,.0f}  median ${q[1]:>8,.0f}  p95 ${q[2]:>8,.0f}")
print(f"   P(net < 0) = {100*(out[:,0]<0).mean():.1f}%")
