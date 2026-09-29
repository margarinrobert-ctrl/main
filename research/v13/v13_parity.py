"""The V13 Pine's order model in Python, diffed against the engine.

One unit, a market order at the next open and a bracket that rides with the entry -- the two things
that broke earlier ports (a ladder re-anchoring inside a bar, a limit fill that has to be ordered
against the exits) are both absent, so this should be close to exact. Anything left is the bracket
reading the SIGNAL bar's exit channel for the entry bar, one bar staler than the engine.
"""
from __future__ import annotations
import sys
import numpy as np, pandas as pd
sys.path.insert(0,"research/v13"); sys.path.insert(0,"research/v8opt")
import eem  # noqa: E402


def run_pine(d, atr, C, mask, *, side=1, atr_mult=2.0, cost, flat_mod=None):
    o,h,l,c,mod = d["o"],d["h"],d["l"],d["c"],d["mod"]
    n=len(c); rows=[]; exit_bar=-1; i=1
    hi_k = "hi1" if side>0 else "elo1"
    ex_k = "lo1" if side>0 else "xhi1"
    while i < n-1:
        trig = (np.isfinite(C[hi_k][i]) and h[i] > C[hi_k][i]) if side>0 else \
               (np.isfinite(C[hi_k][i]) and l[i] < C[hi_k][i])
        if not mask[i] or not np.isfinite(atr[i]) or atr[i]<=0 or i<=exit_bar or not trig:
            i += 1; continue
        eb=i+1; a=atr[i]; px0=o[eb]; ch_sig=C[ex_k][i]; pnl=-cost; j=eb
        while j < n:
            a_stop = px0 - side*atr_mult*a
            ch = ch_sig if j==eb else C[ex_k][j-1]
            if side>0:
                lvl = a_stop if not np.isfinite(ch) else max(a_stop,ch)
                lvl = min(lvl, px0 if j==eb else c[j-1])
                hit = l[j] <= lvl
            else:
                lvl = a_stop if not np.isfinite(ch) else min(a_stop,ch)
                lvl = max(lvl, px0 if j==eb else c[j-1])
                hit = h[j] >= lvl
            if hit:
                pnl += side*(lvl-px0); rows.append((i,eb,j,px0,lvl,pnl,"stop")); break
            if flat_mod is not None and mod[j] >= flat_mod:
                k=min(j+1,n-1); pnl += side*(o[k]-px0)
                rows.append((i,eb,k,px0,o[k],pnl,"flat")); j=k; break
            j += 1
        else:
            break
        exit_bar=j; i=j+1
    return pd.DataFrame(rows,columns=["sig","ent","exit","px0","exitpx","pnl","reason"])


if __name__ == "__main__":
    import v13ctx as V
    GEO=dict(atr_mult=2.0,max_units=1,tp_r=None,skip_win=False)
    b=lambda x: np.nan_to_num(np.asarray(x,float),nan=0).astype(bool)
    print("V13: engine vs the shipped script's order model\n")
    hdr=(f"{'market / block':<24}{'eng n':>7}{'pine n':>8}{'sig match':>11}{'exit bar':>10}"
         f"{'eng PF':>9}{'pine PF':>9}{'eng pts':>10}{'pine pts':>10}{'corr':>8}")
    print(hdr); print("-"*len(hdr))
    for nm,path in [("US100 9yr","data/US100_LONG_15m.csv"),("US30","data/US30_ISO_15m.csv"),
                    ("XAU","data/XAU_ISO_15m.csv")]:
        d,ix=V.load(path); atr,F=V.build(d); C=V.channels(d); cost=V.cost_for(atr)
        fin=np.isfinite(atr)&(atr>0)
        m=fin&b(F["regime_trend"]>0)&b(F["ma13_48_state"]>0)&b(F["ma12_100_state"]>0)
        e=eem.run(d,atr,C,m,side=1,cost=cost,**GEO)
        q=run_pine(d,atr,C,m,side=1,atr_mult=2.0,cost=cost)
        j=e.set_index("sig").join(q.set_index("sig"),how="inner",lsuffix="_e",rsuffix="_q")
        pf=lambda x: x[x>0].sum()/abs(x[x<0].sum())
        sx=float((j["exit_e"]==j["exit_q"]).mean()) if len(j) else np.nan
        cr=np.corrcoef(j.pnl_e,j.pnl_q)[0,1] if len(j)>2 else np.nan
        print(f"{nm:<24}{len(e):>7}{len(q):>8}{len(set(e.sig)&set(q.sig))/max(len(set(e.sig)),1):>10.1%}"
              f"{sx:>10.1%}{pf(e.pnl.to_numpy()):>9.2f}{pf(q.pnl.to_numpy()):>9.2f}"
              f"{e.pnl.mean():>+10.2f}{q.pnl.mean():>+10.2f}{cr:>8.4f}")
