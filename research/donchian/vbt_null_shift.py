"""A SOUND null for the max-combination sweep: circular-shift the signals.

The synthetic-series null was not matched. Driftless bars have different
volatility structure, so far fewer cells reached the 100-trade floor (15k vs
62k), and comparing max-of-15k against max-of-62k favours the real data by
construction.

This null keeps the REAL price series, the REAL bar geometry and the REAL signal
density, and destroys only the ALIGNMENT between signal and forward return, by
circularly shifting the entry signals within the compressed in-window series.
Trade counts per cell are therefore preserved almost exactly and the grids are
directly comparable. Same pipeline, same cost model, same 100-trade floor.
"""
import vectorbt as vbt, numpy as np, pandas as pd, itertools, sys, time
from vbt_sweep import prep, NE, BUF, STOP, TARG, COST

def sweep_shift(P, side, shift):
    c,a,idx,last,pxa,ss = P["c"],P["a"],P["idx"],P["last"],P["pxa"],P["sess"]
    px = pd.Series(c, index=pd.RangeIndex(len(c)))
    cols, sig = [], np.zeros((len(c), len(NE)*len(BUF)), bool)
    k = 0
    for n in NE:
        hi, lo = P["ch"][n]
        for b in BUF:
            raw = (c > hi[idx] + b*a) if side>0 else (c < lo[idx] - b*a)
            raw &= ~np.isnan(P["nxt"])
            raw = np.roll(raw, shift)                      # <-- the null
            raw &= ~np.isnan(P["nxt"])
            fs = np.zeros(len(raw), bool); seen = -1
            for t in np.where(raw)[0]:
                if ss[t] != seen: fs[t] = True; seen = ss[t]
            sig[:,k] = fs; cols.append((n,b)); k += 1
    S = pd.DataFrame(sig); ex = pd.DataFrame(np.tile(last[:,None],(1,len(cols))))
    out = []
    for sm,tm in itertools.product(STOP, TARG):
        sl = np.clip(sm*a/c,1e-6,.95); tp = np.clip(tm*a/c,1e-6,5.)
        pf = vbt.Portfolio.from_signals(px, S, ex, price=pxa[:,None],
             open=P["o"][:,None], high=P["hh"][:,None], low=P["ll"][:,None],
             sl_stop=sl[:,None], tp_stop=tp[:,None],
             direction='longonly' if side>0 else 'shortonly',
             size=1.0, size_type='amount', init_cash=1e9, fees=0.0, freq='15min')
        tr = pf.trades; cnt = tr.count().values.astype(float)
        net = tr.pnl.sum().values.astype(float) - cnt*COST[P["sym"]]
        with np.errstate(invalid='ignore', divide='ignore'):
            e = np.where(cnt>0, net/np.maximum(cnt,1), np.nan)
        for j,(n,b) in enumerate(cols): out.append((n,b,sm,tm,cnt[j],net[j],e[j]))
    R = pd.DataFrame(out, columns=["n_entry","buffer","stop","targ","trades","net","exp"])
    R["side"]=side; R["shift"]=shift; return R

if __name__ == "__main__":
    sym = sys.argv[1]; shift = int(sys.argv[2])
    P = prep(sym)
    fr = [sweep_shift(P, s, shift) for s in (1,-1)]
    R = pd.concat(fr, ignore_index=True)
    R.to_parquet(f"/home/user/main/data/donchian/vbtshift_{sym}_{shift}.parquet")
    q = R[R.trades>=100]
    print(f"  {sym} shift {shift}: {len(q):,} cells >=100 trades, "
          f"median exp {q.exp.median():+.2f}, MAX {q.exp.max():+.2f}", flush=True)
