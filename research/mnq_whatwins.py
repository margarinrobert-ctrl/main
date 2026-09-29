"""Of the cells that beat the reasoned spec on BOTH blocks, is there a coherent structure --
or are they scattered? Scattered = noise. Concentrated = a real, findable improvement."""
import sys, itertools; sys.path.insert(0,'research')
import numpy as np
from bos_choch import prep, run

SPACE = dict(minutes=[15,30,60], swing_k=[2,3,4,5,6], ema_n=[50,100,200,300], atr_n=[10,14,20],
    atr_mult=[1.0,1.5,2.0,2.5,3.0,4.0], n_bos=[1,2,3], use_ema=[0,1], use_choch=[0,1],
    max_hold=[0,10,20,40], min_ema_dist=[0.0,0.5,1.0,1.5,2.0], side_mode=[-1,0,1])
keys=list(SPACE)
rows=np.load("results/mnq/mega_rows.npy")
ok=rows[:,4]>=20; idx=np.where(ok)[0]; R=rows[ok]
rSh,lSh=R[:,1],R[:,3]

d=prep(30); sess=d["sess"]; u=np.unique(sess); cut=int(u[int(0.65*len(u))])
side,ti,to,pnl,g,r,why,dl = run(minutes=30, session="rth_0930_1600", symbol="MNQ",
                                min_ema_dist=1.0, n_bos=2, atr_mult=2.0)
def sh(p,e,lo,hi):
    ds=np.bincount(sess[e]-lo,weights=p,minlength=hi-lo+1); return ds.mean()/ds.std()*np.sqrt(252)
m=sess[ti]<cut
sr,sl = sh(pnl[m],ti[m],int(u.min()),cut), sh(pnl[~m],ti[~m],cut,int(u.max()))

win = (lSh>=sl)&(rSh>=sr)
print(f"reasoned spec: research {sr:.2f}, locked {sl:.2f}")
print(f"cells beating it on BOTH blocks: {win.sum():,} of {len(R):,} ({100*win.mean():.2f}%)\n")

combos=list(itertools.product(*[SPACE[k] for k in keys]))
sel=[combos[i] for i in idx[win]]
allsel=[combos[i] for i in idx]
print(f"{'axis':<14}{'value':>8}{'share of winners':>18}{'share of all':>14}{'lift':>8}")
for j,k in enumerate(keys):
    for v in SPACE[k]:
        a=np.mean([c[j]==v for c in sel]); b=np.mean([c[j]==v for c in allsel])
        if a>0.001:
            flag=" <<<" if a/b>1.6 else ("  (rare)" if a/b<0.5 else "")
            print(f"{k:<14}{str(v):>8}{100*a:>17.1f}%{100*b:>13.1f}%{a/b:>8.2f}{flag}")
    print()

print("="*84)
print("IS THE SEARCH'S GAIN ANYTHING BUT THE DIRECTION BET?")
print("="*84)
sm=np.array([c[keys.index('side_mode')] for c in allsel])
rng=np.random.default_rng(20260823)
print("Same search curve, but restricted to cells that trade BOTH sides (side_mode = 0),")
print("so the long-only regime bet is unavailable.\n")
print(f"{'K':>12}{'research Sh':>14}{'LOCKED Sh':>12}{'LOCKED net $':>15}{'P(lock<0)':>11}   | both-sides only")
for K in (100,10000,100000,int((sm==0).sum())):
    for lab,mask in (("all cells", np.ones(len(R),bool)), ("both-sides", sm==0)):
        pool=np.where(mask)[0]
        if K>len(pool): continue
        ls=[];ln=[]
        for _ in range(200):
            i2=rng.choice(pool,size=K,replace=False)
            b=i2[np.argmax(rSh[i2])]; ls.append(lSh[b]); ln.append(R[b,2])
        if lab=="all cells":
            line=f"{K:>12,}{np.mean([rSh[i] for i in [0]]):>14}"
        print(f"{K:>12,}  {lab:<12}  LOCKED Sharpe {np.mean(ls):>5.2f}   net ${np.mean(ln):>7,.0f}"
              f"   P(<0) {100*np.mean(np.array(ln)<0):>3.0f}%")
    print()
print(f"reasoned spec (both sides, by construction): LOCKED Sharpe {sl:.2f}")
lo=np.where(sm==0)[0]
print(f"\nAmong both-sides cells only, {100*(lSh[lo]>=sl).mean():.2f}% beat the spec's locked Sharpe")
print(f"and {100*((lSh[lo]>=sl)&(rSh[lo]>=sr)).mean():.2f}% beat it on BOTH blocks "
      f"({int(((lSh[lo]>=sl)&(rSh[lo]>=sr)).sum()):,} cells of {len(lo):,}).")
