"""Select on the in-sample block, read the untouched block ONCE, and report the plateau."""
from __future__ import annotations
import sys, itertools
import numpy as np, pandas as pd
sys.path.insert(0,"research"); sys.path.insert(0,"research/turtle2"); sys.path.insert(0,"research/vbt")
import run_sweep as RS

def stats(R,N,W,GP,GL,DD,MKT):
    with np.errstate(invalid="ignore", divide="ignore"):
        exp = np.where(N>0, R/np.maximum(N,1), np.nan)
        pf  = np.where(GL>0, GP/np.maximum(GL,1e-9), np.nan)
        win = np.where(N>0, 100.0*W/np.maximum(N,1), np.nan)
        rdd = np.where(DD>0, R/np.maximum(DD,1e-9), np.nan)
    return exp, pf, win, rdd

if __name__=="__main__":
    D=RS.build(); G=RS.grid(D); n=len(G["ema"])
    print(f"{n:,} configurations, {len(D['names'])} markets\n", flush=True)
    IS=RS.run(D,G,"is"); OOS=RS.run(D,G,"oos")
    e_is,pf_is,w_is,rdd_is = stats(*IS)
    e_o ,pf_o ,w_o ,rdd_o  = stats(*OOS)
    N_is, MKT_is = IS[1], IS[6]

    # a configuration must be tradeable before it is rankable
    elig = (N_is>=150) & np.isfinite(e_is) & (OOS[1]>=50)
    print(f"eligible (>=150 in-sample trades, >=50 out-of-sample): {elig.sum():,}\n")

    order = np.argsort(np.where(elig, e_is, -1e9))[::-1]
    lab=["ema","ent","stop_mode","stop_k","stop_len","tp_mode","tp_a","tp_b","tp_c",
         "tol","be","hold","side"]
    def desc(k):
        r=G["raw"][k]
        ent = RS.CH_LENS[[i for i,v in enumerate(sorted(set(RS.CH_LENS+RS.STOP_LENS))) ][0]] if False else None
        keys=sorted(set(RS.CH_LENS+RS.STOP_LENS))
        return (f"ema{RS.EMA_PERIODS[r[0]]:>4} ent{keys[r[1]]:>3} "
                f"stop{'ATR%.1f'%r[3] if r[2]==1 else 'ch%d'%keys[r[4]]:>7} "
                f"tp{'fix%.1f'%r[6] if r[5]==0 else 'lad%.1f/%.1f/%.1f'%(r[6],r[7],r[8]):>16} "
                f"tol{r[9]:>4.1f} be{r[10]} hold{r[11]:>3} "
                f"side{'L' if r[12]==1 else ('S' if r[12]==-1 else 'B')}")
    print("TOP 12 BY IN-SAMPLE EXPECTANCY -- and what each does on the untouched block")
    print(f"  {'#':>3} {'configuration':<62}{'IS n':>7}{'IS E[R]':>9}{'IS PF':>7}"
          f"{'| OOS n':>9}{'OOS E[R]':>10}{'OOS PF':>8}{'mkts+':>7}")
    for i,k in enumerate(order[:12]):
        print(f"  {i+1:>3} {desc(k):<62}{N_is[k]:>7}{e_is[k]:>+9.3f}{pf_is[k]:>7.2f}"
              f"{OOS[1][k]:>9}{e_o[k]:>+10.3f}{pf_o[k]:>8.2f}{MKT_is[k]:>7}")

    top = order[:max(1,int(0.001*elig.sum()))]
    print(f"\nDECAY: the top 0.1% ({len(top)} configs) average IS {e_is[top].mean():+.4f} "
          f"and OOS {e_o[top].mean():+.4f}")
    print(f"  the whole eligible population averages IS {e_is[elig].mean():+.4f} "
          f"and OOS {e_o[elig].mean():+.4f}")
    print(f"  correlation between IS and OOS expectancy across eligible configs: "
          f"{np.corrcoef(e_is[elig], e_o[elig])[0,1]:+.4f}")
    print(f"  eligible configs positive OOS: {100*np.mean(e_o[elig]>0):.1f}%   "
          f"top 0.1% positive OOS: {100*np.mean(e_o[top]>0):.1f}%")
    np.savez("research/vbt/_sweep_both.npz", e_is=e_is, e_o=e_o, pf_is=pf_is, pf_o=pf_o,
             n_is=N_is, n_o=OOS[1], elig=elig)
