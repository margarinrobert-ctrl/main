"""What does search width DO to the thing you find? Measured, not asserted."""
import sys; sys.path.insert(0,'research')
import numpy as np
rows=np.load("results/mnq/mega_rows.npy")
ok = rows[:,4] >= 20
R = rows[ok]
rNet,rSh,lNet,lSh,nT = R[:,0],R[:,1],R[:,2],R[:,3],R[:,4]
rng=np.random.default_rng(20260823)
print(f"{len(rows):,} cells searched; {ok.sum():,} produced >=20 trades\n")

print("="*80); print("THE SEARCH CURVE"); print("="*80)
print("Draw K cells at random, keep the one with the best RESEARCH Sharpe, then look at what")
print("that cell actually earned on the LOCKED block it never saw. 200 repeats per K.\n")
print(f"{'K cells searched':>18}{'research Sharpe':>17}{'LOCKED Sharpe':>15}{'LOCKED net $':>15}{'P(locked<0)':>13}")
for K in (1,10,100,1000,10000,100000,len(R)):
    rs=[];ls=[];ln=[]
    for _ in range(200):
        idx = rng.choice(len(R), size=min(K,len(R)), replace=False)
        b = idx[np.argmax(rSh[idx])]
        rs.append(rSh[b]); ls.append(lSh[b]); ln.append(lNet[b])
    print(f"{K:>18,}{np.mean(rs):>17.2f}{np.mean(ls):>15.2f}{np.mean(ln):>15,.0f}"
          f"{100*np.mean(np.array(ln)<0):>12.0f}%")

print("\n"+"="*80); print("THE GLOBAL WINNER"); print("="*80)
b=int(np.argmax(rSh))
print(f"  best of all {len(R):,} on RESEARCH : research Sharpe {rSh[b]:.2f}, net ${rNet[b]:,.0f}"
      f"  ->  LOCKED Sharpe {lSh[b]:.2f}, net ${lNet[b]:,.0f}")
b2=int(np.argmax(lSh))
print(f"  best of all on LOCKED            : LOCKED Sharpe {lSh[b2]:.2f}, net ${lNet[b2]:,.0f}"
      f"  ->  its research Sharpe was {rSh[b2]:.2f}")
from scipy.stats import spearmanr
rho,pv = spearmanr(rSh,lSh)
print(f"\n  Spearman rho(research Sharpe, locked Sharpe) over all {len(R):,} cells = {rho:+.3f}  (p={pv:.1e})")
print(f"  cells positive on research: {100*(rNet>0).mean():.1f}%   also positive on locked: "
      f"{100*(lNet[rNet>0]>0).mean():.1f}%")

print("\n"+"="*80); print("HOW DOES THE HAND-BUILT SPEC RANK?"); print("="*80)
# Recompute the reasoned spec under the SEARCH's Sharpe convention (bincount over every day in
# the block, flat days included). The 2.93 quoted elsewhere counted only days that traded, and
# comparing the two conventions would be meaningless.
from bos_choch import prep, run
import numpy as _np
d=prep(30); sess=d["sess"]; u=_np.unique(sess); cut=int(u[int(0.65*len(u))])
side,ti,to,pnl,g,r,why,dl = run(minutes=30, session="rth_0930_1600", symbol="MNQ",
                                min_ema_dist=1.0, n_bos=2, atr_mult=2.0)
def sh(p,e,lo,hi):
    ds=_np.bincount(sess[e]-lo, weights=p, minlength=hi-lo+1)
    return ds.mean()/ds.std()*_np.sqrt(252)
m=sess[ti]<cut
spec_r = sh(pnl[m], ti[m], int(u.min()), cut)
spec_l = sh(pnl[~m], ti[~m], cut, int(u.max()))
print(f"  reasoned spec, SAME convention as the search: research Sharpe {spec_r:.2f}, "
      f"LOCKED Sharpe {spec_l:.2f}")
print(f"  its LOCKED Sharpe sits at the {100*(lSh < spec_l).mean():.1f}th percentile of all "
      f"{len(R):,} cells")
print(f"  {100*(lSh >= spec_l).mean():.2f}% of the search space beat it out of sample "
      f"({int((lSh>=spec_l).sum()):,} cells)")
print(f"  of those, how many ALSO beat it on research (i.e. were findable)? "
      f"{int(((lSh>=spec_l)&(rSh>=spec_r)).sum()):,}")
print("\n  NOTE: no PBO figure is reported. The CSCV statistic requires complementary train/test")
print("  splits of the SAME return series; splitting the cell universe in half, as a first cut of")
print("  this script did, is a different quantity and gave a meaningless 0.000.")
