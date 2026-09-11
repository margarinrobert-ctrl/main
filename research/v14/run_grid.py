import sys, time; sys.path.insert(0,"research/v14"); sys.path.insert(0,"research/v8opt")
sys.path.insert(0,"research"); sys.path.insert(0,"research/turtleshort")
import numpy as np, pandas as pd, v14grid as G, v14tensor as T, mirror, fastbars
OUT="results/v14/claude-0/-home-user-main/e473d7de-e277-515e-b24b-75724aaa9da5/scratchpad"
frac=1.72/(2*np.nanmedian(mirror.wilder_atr(*[fastbars.bars(15)[k] for k in "hlc"],20)))
gl=G.geoms(); ng=len(gl)
def run_one(path,nm,side,block,tag):
    d,ix=G.load(path); atr,atr5,C,eh,el,adx,chop=G.prep(d)
    cost=frac*2*np.nanmedian(atr)
    blk=np.asarray(block(ix))
    sig=G.signal_bars(d,eh,el,atr,side,blk)
    if len(sig)<50: return None,None
    t0=time.time()
    xb,pnl=T.build_tensor(d,atr,atr5,C,sig,side,gl,cost)
    M,meta=G.masks_for(d,sig,adx,chop,side)
    nm_,ns=M.shape
    on=np.zeros(nm_*ng,np.int64); net=np.zeros(nm_*ng); dd=np.zeros(nm_*ng)
    gw=np.zeros(nm_*ng); gls=np.zeros(nm_*ng); wn=np.zeros(nm_*ng)
    T.eval_grid(sig,xb,pnl,M,on,net,dd,gw,gls,wn)
    mi=np.repeat(np.arange(nm_),ng); gi=np.tile(np.arange(ng),nm_)
    mm=np.array(meta,object)
    R=pd.DataFrame(dict(mask=mi,geom=gi,n=on,net=net,dd=dd,gw=gw,gl=gls,wins=wn))
    R["f"]=[meta[i][0] for i in mi]; R["s"]=[meta[i][1] for i in mi]
    R["mode"]=[meta[i][2] for i in mi]; R["adx"]=[meta[i][3] for i in mi]; R["chop"]=[meta[i][4] for i in mi]
    R["lim"]=[gl[i][0] for i in gi]; R["stop"]=[gl[i][1] for i in gi]
    R["tp"]=[gl[i][2] for i in gi]; R["exl"]=[G.EXIT_L[gl[i][3]] for i in gi]
    R["pf"]=R.gw/np.maximum(R.gl,1e-9); R["per"]=R.net/np.maximum(R.n,1)
    R["retdd"]=R.net/np.maximum(R.dd,1e-9); R["win"]=R.wins/np.maximum(R.n,1)
    print(f"  {tag:<22}{nm:<7}side{side:+d}  sig={len(sig):>5}  cells={len(R):,}  {time.time()-t0:.0f}s",flush=True)
    return R,cost
pre  =lambda ix: ix < G.JUDGE
post =lambda ix: ix >= G.JUDGE
res={}
for side in (1,-1):
    for nm,path in [("US30","data/US30_ISO_15m.csv"),("US100","data/US100_ISO_15m.csv")]:
        R,_=run_one(path,nm,side,pre,"TRAIN pre-2026")
        R.to_parquet(f"{OUT}/v14_train_{nm}_{side}.parquet")
        res[(nm,side)]=len(R)
print("done", res, flush=True)
