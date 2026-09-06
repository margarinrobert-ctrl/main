import os, sys, warnings, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.patches import Patch
ROOT="/home/user/main"
for p in ("research","research/v61","research/v53","research/v54","research/v56","research/v64"): sys.path.insert(0,os.path.join(ROOT,p))
import v64opt as O, v61core as V
warnings.filterwarnings("ignore"); OUT=os.path.join(ROOT,"results/v64"); rng=np.random.default_rng(11)
sys.path.insert(0, os.path.join(ROOT,"research/v64"))
from v64_figs import PRESETS, RUNGS, C, BG, FG, GRID, C3, C4
Z=np.load(os.path.join(OUT,"v64_mc_arrays.npz"))
Ds={tf:O.build(tf) for tf in (15,30)}; base={}
for nm,p in PRESETS.items():
    R_,pct,blk,sg=O.evaluate(Ds[p["tf"]],p); eq=np.cumsum(pct[blk==1])
    base[nm]=dict(lock=pct[blk==1], tot=float(pct[blk==1].sum()), dd=float(-(eq-np.maximum.accumulate(eq)).min()))
plt.rcParams.update({"figure.facecolor":BG,"axes.facecolor":BG,"axes.edgecolor":GRID,"axes.labelcolor":FG,"xtick.color":FG,"ytick.color":FG,"text.color":FG,"grid.color":GRID,"font.size":9.5,"axes.titlesize":10.5,"legend.facecolor":BG,"legend.edgecolor":GRID})
rung_d={}; drop_d={}
for nm,p in PRESETS.items():
    D=Ds[p["tf"]]; rr={}
    for ax_,ds in RUNGS.items():
        vals=[]
        for d in ds:
            q=dict(p); q[ax_]=int(max(1,q[ax_]+d)) if ax_ in ("ent","exN","k","w","hold") else max(0.0,q[ax_]+d)
            R_,pct,blk,sg=O.evaluate(D,q); vals.append(pct[blk==1].sum())
        rr[ax_]=vals
    rung_d[nm]=rr; lock=base[nm]["lock"]
    drop_d[nm]=[np.median([rng.choice(lock,int(round(len(lock)*(1-f))),replace=False).sum() for _ in range(400)]) for f in (0,.05,.10,.20,.40)]
fig=plt.figure(figsize=(15.5,12)); gs=fig.add_gridspec(3,3,hspace=0.62,wspace=0.28)
ax=fig.add_subplot(gs[0,0])
for nm in PRESETS:
    v=Z[f"exec_{nm}"]; ax.hist(v,bins=45,histtype="step",lw=2,color=C[nm],label=f"{nm}: p5 {np.quantile(v,.05):.1f}  p95 {np.quantile(v,.95):.1f}")
    ax.axvline(base[nm]["tot"],color=C[nm],ls="--",lw=1.2)
ax.axvline(0,color=C3,lw=1.5); ax.set_xlabel("locked total, % of entry price"); ax.set_ylabel("draws")
ax.set_title("A. Execution perturbation, 2,000 draws\nslippage U(0,2x), cost U(0.5x,2x).  P(total<=0)=0.000",loc="left")
ax.legend(fontsize=7.5); ax.grid(alpha=0.3)
ax=fig.add_subplot(gs[0,1]); pos=0; ticks=[]; tlab=[]
for nm in PRESETS:
    for s in (0.5,1.0,2.0):
        v=Z[f"price_{nm}_{s}"]
        ax.boxplot(v,positions=[pos],widths=0.6,patch_artist=True,showfliers=False,boxprops=dict(facecolor=C[nm],alpha=0.45,color=C[nm]),medianprops=dict(color=FG,lw=1.4),whiskerprops=dict(color=C[nm]),capprops=dict(color=C[nm]))
        ticks.append(pos); tlab.append(f"{s}t"); pos+=1
    ax.plot([pos-3,pos-1],[base[nm]["tot"]]*2,ls="--",color=C[nm],lw=1.3); pos+=0.8
ax.set_xticks(ticks); ax.set_xticklabels(tlab,fontsize=8); ax.axhline(0,color=C3,lw=1.2); ax.set_ylabel("locked total %")
ax.set_title("B. Price jitter, indicators RECOMPUTED\n150 draws per level.  Sign kept 1.000 in all 9 cells",loc="left")
ax.grid(axis="y",alpha=0.3); ax.legend(handles=[Patch(facecolor=C[k],alpha=0.6,label=k) for k in PRESETS],fontsize=7.5,loc="lower left")
ax=fig.add_subplot(gs[0,2])
for nm,y in drop_d.items(): ax.plot([0,5,10,20,40],y,"o-",color=C[nm],lw=2,label=nm)
ax.axhline(0,color=C3,lw=1.2); ax.set_xlabel("% of fills missed"); ax.set_ylabel("locked total %")
ax.set_title("C. Missed fills (upper bound)\na dropped trade never frees the lock here",loc="left"); ax.legend(fontsize=7.5); ax.grid(alpha=0.3)
for j,nm in enumerate(PRESETS):
    ax=fig.add_subplot(gs[1,j]); rr=rung_d[nm]; real=base[nm]["tot"]; ay=list(rr); y=np.arange(len(ay))
    lo=np.array([min(rr[a]) for a in ay]); hi=np.array([max(rr[a]) for a in ay])
    ax.barh(y,hi-lo,left=lo,color=C[nm],alpha=0.55)
    for i,a in enumerate(ay): ax.plot(rr[a],[i,i],"o",color=FG,ms=4)
    ax.axvline(real,color=C4,lw=1.8,label=f"realised {real:+.1f}%"); ax.axvline(0,color=C3,lw=1.2)
    ax.set_yticks(y); ax.set_yticklabels(ay,fontsize=8.5); ax.invert_yaxis(); ax.set_xlabel("locked total %")
    ax.set_title(f"D{j+1}. {nm}: one rung each axis\nworst single-rung neighbour {min(lo):+.1f}%",loc="left")
    ax.legend(fontsize=7.5); ax.grid(axis="x",alpha=0.3)
ax=fig.add_subplot(gs[2,0])
for nm in PRESETS:
    v=Z[f"joint_{nm}"]; ax.hist(v,bins=40,histtype="step",lw=2,color=C[nm],label=f"{nm}: p5 {np.quantile(v,.05):+.1f}, P(<=0) {np.mean(v<=0):.3f}, {100*np.mean(v>base[nm]['tot']):.0f}% beat it")
    ax.axvline(base[nm]["tot"],color=C[nm],ls="--",lw=1.2)
ax.axvline(0,color=C3,lw=1.5); ax.set_xlabel("locked total %"); ax.set_ylabel("draws")
ax.set_title("E. Joint jitter on all six axes, 500 draws\ndashed = realised",loc="left"); ax.legend(fontsize=7); ax.grid(alpha=0.3)
ax=fig.add_subplot(gs[2,1])
for nm in PRESETS:
    v=Z[f"perm_{nm}"]; ax.hist(v,bins=50,histtype="step",lw=2,color=C[nm],label=f"{nm}: realised {base[nm]['dd']:.1f}% at pct {np.mean(v<=base[nm]['dd']):.2f}, p99 {np.quantile(v,.99):.1f}%")
    ax.axvline(base[nm]["dd"],color=C[nm],ls="--",lw=1.5)
ax.set_xlabel("max drawdown, % of entry price"); ax.set_ylabel("permutations")
ax.set_title("F. Path permutation, 5,000 reshuffles\nthe p99 is the sizing number",loc="left"); ax.legend(fontsize=7); ax.grid(alpha=0.3)
ax=fig.add_subplot(gs[2,2])
for nm in PRESETS:
    v=base[nm]["lock"]; bs=np.array([rng.choice(v,len(v),replace=True).mean() for _ in range(5000)])
    ax.hist(bs,bins=45,histtype="step",lw=2,color=C[nm],label=f"{nm}: P(mean<=0) {np.mean(bs<=0):.3f} on n {len(v)}")
ax.axvline(0,color=C3,lw=1.5); ax.set_xlabel("bootstrapped mean % per trade"); ax.set_ylabel("draws")
ax.set_title("G. Bootstrap for the EDGE\nthe permutation cannot answer this",loc="left"); ax.legend(fontsize=7.5); ax.grid(alpha=0.3)
fig.suptitle("V61 CVD -- perturbation Monte Carlo on the LOCKED block (NQ, one unit, MNQ costs)",fontsize=13,y=0.995)
fig.savefig(os.path.join(OUT,"v64_fig2_mc.png"),dpi=135,bbox_inches="tight"); print("ok")
