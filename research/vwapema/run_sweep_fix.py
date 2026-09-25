"""Re-run the no-target slice of the 108k sweep, and re-read the Optuna target marginal.

The sweep's `tgt=0.0` rung and the Optuna study's `use_tgt=False` arm both passed a literal 0.0,
which the engine read as a target AT the entry price. `vecore` now treats <=0 and >=90 alike as NO
TARGET, agreeing with the shipped Pine's `tgtR = 0` input. 21,600 of 108,000 sweep cells and about
half the Optuna trials were affected; both are re-scored here.
"""
import os, sys, time, itertools
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from research.vwapema import vecore as V
EMA_SLOW = [100, 150, 200, 250, 300, 400]; EMA_PULL = [20, 34, 50, 70, 90, 120]
ATR_STOP = [0.25, 0.5, 0.75, 1.0, 1.5]; VOL_MULT = [1.0, 1.1, 1.3, 1.5, 1.8]
RANGE_M = [0.4, 0.6, 0.8, 1.1]; WICK = [1.5, 2.0, 3.0]; SESS = ["ny", "utc"]; MIN_N = 60

print(__doc__)
G = pd.read_parquet("results/vwapema/sweep100k.parquet")
print(f"  sweep as run: {len(G):,} cells; the broken rung is tgt==0.0 with {int((G.tgt==0).sum()):,} of them")
DS = {sm: V.build(sess=sm) for sm in SESS}
EMA = {(sm, n): V._ema(DS[sm]["c"], n) for sm in SESS for n in set(EMA_SLOW + EMA_PULL)}

t0 = time.time(); rows = []
for sm in SESS:
    D = DS[sm]
    o, h, l, c, v = D["o"], D["h"], D["l"], D["c"], D["v"]
    rth, vwap, atr, vsma = D["rth"], D["vwap"], D["atr"], D["vsma"]
    body, lw, uw = D["body"], D["lw"], D["uw"]
    prev_l = np.concatenate(([np.nan], l[:-1])); prev_o = np.concatenate(([np.nan], o[:-1]))
    prev_c = np.concatenate(([np.nan], c[:-1]))
    C2 = np.nan_to_num(c > vwap, nan=False)
    engulf = np.nan_to_num((c > prev_o) & (o < prev_c), nan=False)
    for es in EMA_SLOW:
        e200 = EMA[(sm, es)]
        base_a = (c > e200) & C2 & (np.abs(c - e200)/np.maximum(e200, 1e-9) >= V.PARAMS["ambig"]) & rth
        for ep in EMA_PULL:
            e50 = EMA[(sm, ep)]
            base_b = base_a & np.nan_to_num((np.minimum(l, prev_l) <= e50) & (e50 <= c), nan=False)
            for wb in WICK:
                base_c = base_b & (((lw >= wb*body) & (uw <= 0.5*lw)) | engulf)
                for vm in VOL_MULT:
                    base_d = base_c & (v > vm*vsma)
                    for rm in RANGE_M:
                        sig = np.nan_to_num(base_d & ((h - l) >= rm*atr), nan=False).astype(bool)
                        if sig.sum() < MIN_N:
                            continue
                        for asx in ATR_STOP:
                            t = V.run(D, sig, side=1, tgt_R=0.0, atr_stop=asx,
                                      p={"ema_slow": es, "ema_pull": ep, "ema_tight": 20,
                                         "atr_len": 14, "atr_stop": asx})
                            tr = t[t.blk == 0]; tl = t[t.blk == 1]
                            if len(tr) < MIN_N:
                                continue
                            r = tr.R.to_numpy(); cum = np.cumsum(r)
                            dd = float(np.max(np.maximum.accumulate(cum) - cum)) if len(cum) else 0.0
                            rows.append((sm, es, ep, wb, vm, rm, asx, 0.0, len(tr), float(r.mean()),
                                         float(r.sum()), float(r[r>0].sum()/max(-r[r<0].sum(),1e-9)),
                                         float(r.sum()/max(dd,1e-9)), len(tl),
                                         float(tl.R.mean()) if len(tl) else np.nan,
                                         float(tl.R.sum()) if len(tl) else np.nan))
    print(f"  {sm} re-scored ({time.time()-t0:.0f}s)")
F = pd.DataFrame(rows, columns=G.columns)
G2 = pd.concat([G[G.tgt != 0.0], F], ignore_index=True)
G2.to_parquet("results/vwapema/sweep100k.parquet")
print(f"\n  merged: {len(G2):,} cells")
print(f"  share profitable on research: {100*(G2.R_res>0).mean():.1f}% (was 42.1% with the broken rung)")
m = G2.groupby("tgt").agg(cells=("R_res","size"), R_res=("R_res","mean"), pf=("pf_res","mean"),
                          share_pos=("R_res", lambda x: 100*(x>0).mean()), trades=("n_res","mean"))
m.index = [("no target" if i == 0 else f"{i:g}R") for i in m.index]
print("\n  THE CORRECTED TARGET MARGINAL:")
print(m.to_string(float_format=lambda v: f"{v:9.4f}"))
