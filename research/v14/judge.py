import sys; sys.path.insert(0,"research/v14"); sys.path.insert(0,"research/v8opt")
sys.path.insert(0,"research"); sys.path.insert(0,"research/turtleshort")
import numpy as np, pandas as pd, v14grid as G, v14tensor as T, analyse as A, mirror, fastbars
OUT="results/v14/claude-0/-home-user-main/e473d7de-e277-515e-b24b-75724aaa9da5/scratchpad"
frac=1.72/(2*np.nanmedian(mirror.wilder_atr(*[fastbars.bars(15)[k] for k in "hlc"],20)))
gl=G.geoms()
def block_stats(path,side,which):
    d,ix=G.load(path); atr,atr5,C,eh,el,adx,chop=G.prep(d)
    cost=frac*2*np.nanmedian(atr)
    blk=np.asarray(ix>=G.JUDGE) if which=="post" else np.asarray(ix<G.JUDGE)
    sig=G.signal_bars(d,eh,el,atr,side,blk)
    xb,pnl=T.build_tensor(d,atr,atr5,C,sig,side,gl,cost)
    M,meta=G.masks_for(d,sig,adx,chop,side)
    nm,ng=M.shape[0],len(gl)
    on=np.zeros(nm*ng,np.int64); net=np.zeros(nm*ng); dd=np.zeros(nm*ng)
    gw=np.zeros(nm*ng); gls=np.zeros(nm*ng); wn=np.zeros(nm*ng)
    T.eval_grid(sig,xb,pnl,M,on,net,dd,gw,gls,wn)
    R=pd.DataFrame(dict(mask=np.repeat(np.arange(nm),ng),geom=np.tile(np.arange(ng),nm),
                        n=on,net=net,dd=dd,gw=gw,gl=gls,wins=wn))
    R["pf"]=R.gw/np.maximum(R.gl,1e-9); R["retdd"]=R.net/np.maximum(R.dd,1e-9)
    R["per"]=R.net/np.maximum(R.n,1); R["win"]=R.wins/np.maximum(R.n,1)
    return R
if __name__=="__main__":
    for side,lab in ((1,"LONG"),(-1,"SHORT")):
        top=pd.read_parquet(f"{OUT}/v14_top_{side}.parquet")
        a=block_stats("data/US30_ISO_15m.csv",side,"post")
        b=block_stats("data/US100_ISO_15m.csv",side,"post")
        j=top[["mask","geom"]+A.DESC].merge(a,on=["mask","geom"]).merge(
            b,on=["mask","geom"],suffixes=("_a","_b"))
        ok=(j.n_a>=15)&(j.n_b>=15)
        j=j[ok].copy()
        j["retdd"]=np.minimum(j.retdd_a,j.retdd_b); j["pf"]=np.minimum(j.pf_a,j.pf_b)
        print(f"=== {lab}: the top 1000 from train, read ONCE on 2026 ===")
        print(f"  scorable (>=15 trades on both in 2026): {len(j):,} of 1000")
        print(f"  still profitable on BOTH in 2026      : {((j.retdd_a>0)&(j.retdd_b>0)).mean():.1%}")
        print(f"  still PF>1.2 on BOTH                  : {((j.pf_a>1.2)&(j.pf_b>1.2)).mean():.1%}")
        print(f"  median 2026 PF (worse instrument)     : {j.pf.median():.2f}")
        print(f"  median 2026 ret/DD (worse instrument) : {j.retdd.median():.2f}")
        print(f"  the TRAIN #1 config on 2026           : ", end="")
        r0=j.iloc[0] if len(j) else None
        if r0 is not None:
            print(f"PF {r0.pf_a:.2f}/{r0.pf_b:.2f}  ret/DD {r0.retdd_a:.2f}/{r0.retdd_b:.2f}  n {int(r0.n_a)}/{int(r0.n_b)}")
        best=j.sort_values("retdd",ascending=False).head(5)
        print(f"\n  best 5 of the top-1000 ON 2026 (this is a SECOND selection -- read as such):")
        print(f"  {'configuration':<70}{'n30':>5}{'n100':>6}{'PF30':>7}{'PF100':>7}{'rdd30':>7}{'rdd100':>7}")
        for _,x in best.iterrows():
            print(f"  {A.describe(x):<70}{int(x.n_a):>5}{int(x.n_b):>6}{x.pf_a:>7.2f}{x.pf_b:>7.2f}{x.retdd_a:>7.2f}{x.retdd_b:>7.2f}")
        print()
