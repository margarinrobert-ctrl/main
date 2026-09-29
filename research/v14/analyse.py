"""Rank the grid under the rules that were agreed, and only then read 2026.

THE RULES, FIXED BEFORE THE GRID RAN.
  * entries only inside 07:00-11:00 New York; exits run free
  * a configuration must hold on US30 AND US100 independently -- ranked on the WORSE of the two,
    so a cell cannot buy its place with one instrument
  * ranked on RETURN OVER MAX DRAWDOWN, the one criterion on this branch whose in-sample ordering
    has survived out of sample; Sharpe and profit factor are carried but do not order anything
  * 2026 is read ONCE, at the end, for the survivors

WHAT THE MULTIPLICITY ACTUALLY IS. 1,290,240 cells per side. If a fraction f of them are profitable
by luck alone, the top of the ranking is the maximum of that many draws -- so the share of the grid
that passes is reported FIRST, because it is what tells you how to read everything after it.
"""
from __future__ import annotations
import sys
import numpy as np, pandas as pd
OUT="results/v14/claude-0/-home-user-main/e473d7de-e277-515e-b24b-75724aaa9da5/scratchpad"
KEY=["mask","geom"]
DESC=["f","s","mode","adx","chop","lim","stop","tp","exl"]
MODE={0:"off",1:"state",2:"fresh8"}

def load_side(side):
    a=pd.read_parquet(f"{OUT}/v14_train_US30_{side}.parquet")
    b=pd.read_parquet(f"{OUT}/v14_train_US100_{side}.parquet")
    j=a.merge(b,on=KEY,suffixes=("_a","_b"))
    for c in DESC: j[c]=j[f"{c}_a"]
    return j

def rank(j, min_n=60):
    ok=(j.n_a>=min_n)&(j.n_b>=min_n)
    j=j[ok].copy()
    j["retdd"]=np.minimum(j.retdd_a,j.retdd_b)      # the WORSE of the two instruments
    j["pf"]=np.minimum(j.pf_a,j.pf_b)
    j["per"]=np.minimum(j.per_a,j.per_b)
    return j.sort_values("retdd",ascending=False).reset_index(drop=True)

def describe(r):
    return (f"MA {int(r.f)}/{int(r.s)} {MODE[int(r['mode'])]:<6} ADX>={int(r.adx):<3} "
            f"CHOP<={r.chop:<5.4g} entry {'mkt' if r.lim==0 else f'lim{r.lim:.2f}N'} "
            f"stop {r.stop:.1f}N tp {'none' if r.tp==0 else f'{r.tp:.1f}R'} exit {int(r.exl)}")
