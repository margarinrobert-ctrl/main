"""~100,000 configurations around the best version, selected IN-SAMPLE and read once out of sample.

THE PROTOCOL, because a sweep that only reports its maximum is how this branch has misled itself
before:
  * every configuration is scored on the IN-SAMPLE block only
  * the winner is then read ONCE on the untouched block, and both numbers are reported together
  * the PLATEAU is reported next to the peak -- a real parameter is a ridge, an artifact is a spike
  * the multiplicity is stated, and a Bonferroni-scale reference is given
  * P(pass) for a funded evaluation is computed for the survivors, since that is the stated goal
"""
from __future__ import annotations

import itertools
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/turtle2")
sys.path.insert(0, "research/vbt")
import ytdata, ytfilters as Y, original as O
from sweep_engine import sweep
from run_yt import COST_BP, SLIP_BP

CHART = 60
CH_LENS = [0, 10, 20, 30, 55]        # 0 = no entry trigger, enter on every admitted bar
STOP_LENS = [5, 10, 20]
EMA_PERIODS = [10, 20, 50, 100, 200]
STOP_ATRS = [1.0, 1.5, 2.0, 3.0]
TP_FIXED = [1.0, 2.0, 3.0, 5.0]
TP_LADDERS = [(1.0, 2.0, 3.0), (1.0, 2.0, 4.0), (0.5, 1.5, 3.0)]
TOLS = [0.0, 0.5, 1.0, 2.0, 3.0]
BES = [0, 1]
HOLDS = [0, 24, 72]
SIDES = [1, -1, 0]                   # long only / short only / both


def build():
    """One concatenated series over all markets, with per-market slice bounds."""
    o=[];h=[];l=[];c=[];st=[];en=[];cost=[]; names=[]
    chans_h={}; chans_l={}; emas={}; rh=[]; rl=[]; atr=[]
    pos=0
    for m in ytdata.BASE:
        b = ytdata.load(m, CHART)
        if b is None:
            continue
        n=b["n"]; names.append(m)
        o.append(b["o"]); h.append(b["h"]); l.append(b["l"]); c.append(b["c"])
        st.append(pos); en.append(pos+n); pos+=n
        cost.append((COST_BP[m]+SLIP_BP[m])/1e4)
        pc=np.roll(b["c"],1); pc[0]=b["c"][0]
        tr=np.maximum(b["h"]-b["l"], np.maximum(np.abs(b["h"]-pc), np.abs(b["l"]-pc)))
        atr.append(pd.Series(tr).ewm(span=14, adjust=False).mean().to_numpy())
        for L in set(CH_LENS+STOP_LENS):
            if L==0:
                a=np.full(n,np.nan); z=np.full(n,np.nan)
            else:
                a=np.roll(O._roll_max(b["h"],L),1); a[:L+1]=np.nan
                z=np.roll(O._roll_min(b["l"],L),1); z[:L+1]=np.nan
            chans_h.setdefault(L,[]).append(a); chans_l.setdefault(L,[]).append(z)
        for P in EMA_PERIODS:
            emas.setdefault(P,[]).append(Y.htf_ema(b["idx"], b["c"], "4H", P, "closed"))
        hi,lo = Y.major_levels(b["idx"], b["h"], b["l"])
        import warnings
        with np.errstate(invalid="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            rh.append(np.nanmin(np.where(hi>b["c"][None,:],hi,np.nan),axis=0))
            rl.append(np.nanmax(np.where(lo<b["c"][None,:],lo,np.nan),axis=0))
    keys = sorted(set(CH_LENS+STOP_LENS))
    return dict(o=np.concatenate(o),h=np.concatenate(h),l=np.concatenate(l),c=np.concatenate(c),
                atr=np.concatenate(atr), mstart=np.array(st,np.int64), mend=np.array(en,np.int64),
                cost=np.array(cost), names=names,
                his=np.vstack([np.concatenate(chans_h[k]) for k in keys]),
                los=np.vstack([np.concatenate(chans_l[k]) for k in keys]),
                lenidx={k:i for i,k in enumerate(keys)},
                emas=np.vstack([np.concatenate(emas[p]) for p in EMA_PERIODS]),
                emaidx={p:i for i,p in enumerate(EMA_PERIODS)},
                res_hi=np.concatenate(rh), res_lo=np.concatenate(rl))


def grid(D):
    rows=[]
    tps=[(0,a,0.0,0.0) for a in TP_FIXED]+[(1,)+t for t in TP_LADDERS]
    stops=[(0,0.0,L) for L in STOP_LENS]+[(1,k,STOP_LENS[0]) for k in STOP_ATRS]
    for ent,(sm,sk,sl),(tm,ta,tb,tc),P,tol,be,hold,side in itertools.product(
            CH_LENS, stops, tps, EMA_PERIODS, TOLS, BES, HOLDS, SIDES):
        rows.append((D["emaidx"][P], D["lenidx"][ent], sm, sk, D["lenidx"][sl],
                     tm, ta, tb, tc, tol, be, hold, side))
    a=np.array(rows, dtype=object)
    return dict(ema=a[:,0].astype(np.int64), ent=a[:,1].astype(np.int64),
                sm=a[:,2].astype(np.int64), sk=a[:,3].astype(np.float64),
                sl=a[:,4].astype(np.int64), tm=a[:,5].astype(np.int64),
                ta=a[:,6].astype(np.float64), tb=a[:,7].astype(np.float64),
                tc=a[:,8].astype(np.float64), tol=a[:,9].astype(np.float64),
                be=a[:,10].astype(np.int64), hold=a[:,11].astype(np.int64),
                side=a[:,12].astype(np.int64), raw=rows)


def bounds(D, block):
    st=[];en=[]
    for i,m in enumerate(D["names"]):
        b=ytdata.load(m,CHART); cut,_=ytdata.split(b)
        a0,b0=D["mstart"][i],D["mend"][i]
        if block=="is": st.append(a0); en.append(a0+cut)
        else: st.append(a0+cut); en.append(b0)
    return np.array(st,np.int64), np.array(en,np.int64)


def run(D,G,block):
    ms,me = bounds(D,block)
    return sweep(D["o"],D["h"],D["l"],D["c"],ms,me,D["emas"],D["atr"],D["his"],D["los"],
                 D["res_hi"],D["res_lo"],G["ema"],G["ent"],G["sm"],G["sk"],G["sl"],
                 G["tm"],G["ta"],G["tb"],G["tc"],G["tol"],G["be"],G["hold"],G["side"],D["cost"])


if __name__ == "__main__":
    t0=time.time(); D=build(); print(f"data built in {time.time()-t0:.0f}s, "
                                    f"{len(D['c']):,} bars over {len(D['names'])} markets", flush=True)
    G=grid(D); n=len(G["ema"]); print(f"grid: {n:,} configurations", flush=True)
    t0=time.time(); R,N,W,GP,GL,DD,MKT = run(D,G,"is")
    print(f"in-sample sweep done in {time.time()-t0:.0f}s", flush=True)
    np.savez("research/vbt/_sweep_is.npz", R=R,N=N,W=W,GP=GP,GL=GL,DD=DD,MKT=MKT,
             **{k:v for k,v in G.items() if k!="raw"})
    print("saved", flush=True)
