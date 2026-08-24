"""Full battery on the three supply/demand strategies: sweep -> OOS -> walk-forward -> Monte Carlo."""
import sys, time, itertools; sys.path.insert(0,'research')
import numpy as np
from sd_strategies import run_sd
from bos_choch import prep, SPECS
S=SPECS['MNQ']; ARGS=(S['pv'],S['tick'],1.0,S['spread_t'],S['slip_t'],S['stop_slip_t'])
rng=np.random.default_rng(20260823)

D={};T={};U={};CUT={}
for m in (15,30,60):
    d=prep(m); D[m]=d; T[m]=((d['mod']>=570)&(d['mod']<960)).astype(np.uint8)
    u=np.unique(d['sess']); U[m]=u; CUT[m]=u[int(0.65*len(u))]

def go(m, bk,bm,dm,zt,mo,cf,sm,sk,sp,tm,tr,ag,mt,fo,side):
    d=D[m]
    return run_sd(d['o'],d['h'],d['l'],d['c'],d['v'],d['sess'],T[m],d['atr'],
                  bk,bm,dm,zt,mo,cf,sm,sk,sp,tm,tr,ag,mt,fo,side,0.0,*ARGS)

def dser(p,e,m,uni):
    ds=np.zeros(len(uni)); ix={q:j for j,q in enumerate(uni)}
    for val,q in zip(p, D[m]['sess'][e]):
        if q in ix: ds[ix[q]]+=val
    return ds

STOPS=[(0,1.5,0.5),(0,2.0,0.5),(0,3.0,0.5),(1,2.0,0.25),(1,2.0,0.5)]
TGTS =[(0,1.5),(0,2.0),(0,3.0),(1,2.0)]
rows=[]; keys=[]; t0=time.time(); done=0
for m in (15,30,60):
  for bk,bm,dm in itertools.product((1,2,3),(0.6,1.0,1.5),(0.8,1.2,1.8)):
    for zt,mo,cf in itertools.product((0,1,2),(0,1),(0,1,2,3)):
      for (sm,sk,sp) in STOPS:
        for (tm,tr) in TGTS:
          for mt,fo in ((1,1),(99,0)):
            for side in (-1,0,1):
              p,e,s,w = go(m,bk,bm,dm,zt,mo,cf,sm,sk,sp,tm,tr,240,mt,fo,side)
              done+=1
              if len(p)<30: continue
              ss=D[m]['sess'][e]; msk=ss<CUT[m]
              if msk.sum()<15 or (~msk).sum()<10: continue
              rows.append((p[msk].sum(), p[~msk].sum(), len(p), m, mo, cf, zt, side, bk))
              keys.append((m,bk,bm,dm,zt,mo,cf,sm,sk,sp,tm,tr,240,mt,fo,side))
              if done%40000==0:
                  print(f"  {done:,} evaluated, {len(rows):,} kept, {time.time()-t0:.0f}s", flush=True)
R=np.array(rows)
print(f"\n{done:,} configurations evaluated in {time.time()-t0:.0f}s; {len(R):,} had >=30 trades")
rn,ln = R[:,0],R[:,1]
print("="*88); print("1. ROBUSTNESS / OUT-OF-SAMPLE"); print("="*88)
b=int(np.argmax(rn))
print(f"   best on RESEARCH        research ${rn[b]:>9,.0f}  ->  LOCKED ${ln[b]:>9,.0f}")
print(f"   best on LOCKED          ${ln.max():>9,.0f}   (hindsight, unattainable)")
print(f"   MEDIAN locked           ${np.median(ln):>9,.0f}")
print(f"   positive research {100*(rn>0).mean():.1f}%   locked {100*(ln>0).mean():.1f}%"
      f"   BOTH {100*((rn>0)&(ln>0)).mean():.1f}%")
print(f"   BOS/CHoCH 2R book on the same locked block: $8,932")
print(f"\n   by strategy (mode 0 = reversal, 1 = break&retest):")
for mo in (0,1):
    s=R[R[:,4]==mo]
    if len(s): print(f"      mode {mo}: n={len(s):>6}  median locked ${np.median(s[:,1]):>8,.0f}"
                     f"   positive on both {100*((s[:,0]>0)&(s[:,1]>0)).mean():>5.1f}%")
print(f"\n   by rejection confirmation:")
for cf,nm in ((0,'none'),(1,'pin bar'),(2,'engulfing'),(3,'either')):
    s=R[R[:,5]==cf]
    if len(s): print(f"      {nm:<10}: n={len(s):>6}  median locked ${np.median(s[:,1]):>8,.0f}"
                     f"   positive on both {100*((s[:,0]>0)&(s[:,1]>0)).mean():>5.1f}%")
print(f"\n   by zone type (1 = DBR/RBD reversal, 2 = continuation):")
for zt,nm in ((0,'any'),(1,'reversal'),(2,'continuation')):
    s=R[R[:,6]==zt]
    if len(s): print(f"      {nm:<13}: n={len(s):>6}  median locked ${np.median(s[:,1]):>8,.0f}")
print(f"\n   by base length:")
for bk in (1,2,3):
    s=R[R[:,8]==bk]
    if len(s): print(f"      base {bk} bar(s): n={len(s):>6}  median locked ${np.median(s[:,1]):>8,.0f}")

# ---- walk-forward + Monte Carlo on the honestly chosen winner ----
kb=keys[b]; m=kb[0]
p,e,_,_ = go(*kb)
print(); print("="*88); print(f"2. WALK-FORWARD on the research winner  {kb}"); print("="*88)
u=U[m]; folds=np.array_split(u,7); oos=[]
for kf in range(1,7):
    ins=np.concatenate(folds[:kf]); out=folds[kf]
    mi=np.isin(D[m]['sess'][e],ins); mo_=np.isin(D[m]['sess'][e],out)
    print(f"   fold {kf}: in-sample ${p[mi].sum():>9,.0f}   ->  OOS ${p[mo_].sum():>9,.0f}")
    oos.append(p[mo_].sum())
print(f"   stitched OOS ${sum(oos):>9,.0f}   (negative folds: {sum(1 for x in oos if x<0)} of 6)")
print(); print("="*88); print("3. MONTE CARLO, 5,000 block-bootstrap paths"); print("="*88)
ds=dser(p,e,m,u)
def boot(x,B=5000,mb=5):
    out=np.empty((B,2)); N=len(x)
    for i in range(B):
        path=[]
        while len(path)<N:
            s0=rng.integers(0,N); L=1+rng.geometric(1/mb)
            path.extend(x[(s0+np.arange(L))%N])
        arr=np.array(path[:N]); eq=np.cumsum(arr)
        out[i]=[arr.sum(),(np.maximum.accumulate(np.r_[0,eq])-np.r_[0,eq]).max()]
    return out
B=boot(ds); q=np.percentile(B[:,0],[5,50,95])
print(f"   net $   p5 ${q[0]:>8,.0f}   median ${q[1]:>8,.0f}   p95 ${q[2]:>8,.0f}")
print(f"   P(net < 0) = {100*(B[:,0]<0).mean():.1f}%")
print(f"   maxDD median ${np.median(B[:,1]):>8,.0f}   p95 ${np.percentile(B[:,1],95):>8,.0f}")
