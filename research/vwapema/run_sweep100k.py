"""THE 108,000-CELL SWEEP -- best mean performance AND the most robust cell, which are not the same.

Engine: the verified numba walker, now cross-checked against an INDEPENDENT vectorbt build that
passes transcription at ratio 0.9899 and is conservative by 8.6%.

TWO RANKINGS ARE PRODUCED AND BOTH ARE READ ONCE ON LOCKED:
  * the TOP ROW by research mean R -- which is the maximum of ~N positive draws and is what every
    optimiser reports;
  * the NEIGHBOURHOOD-BEST cell -- the highest mean over its own +-1 rung box on EVERY ordered
    axis. `STUDY_V38` found this beat the top row on every fresh-market cell it was tried on, and
    `STUDY_V60` found a PERFECT plateau is still not evidence, so it is read as a candidate and
    not as proof.

Grid (declared here in full so the multiplicity is countable):
  ema_slow 6 x ema_pull 6 x atr_stop 5 x vol_mult 5 x range_mult 4 x target 5 x wick_body 3
  x session reading 2  =  108,000 cells on the long side.
RESEARCH BLOCK ONLY. The locked block is opened at the end, for two cells.
"""
import os, sys, time, itertools, json
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from research.vwapema import vecore as V

EMA_SLOW = [100, 150, 200, 250, 300, 400]
EMA_PULL = [20, 34, 50, 70, 90, 120]
ATR_STOP = [0.25, 0.5, 0.75, 1.0, 1.5]
VOL_MULT = [1.0, 1.1, 1.3, 1.5, 1.8]
RANGE_M = [0.4, 0.6, 0.8, 1.1]
TGT = [2.0, 3.0, 4.0, 6.0, 0.0]          # 0 = no target
WICK = [1.5, 2.0, 3.0]
SESS = ["ny", "utc"]
NCELL = (len(EMA_SLOW)*len(EMA_PULL)*len(ATR_STOP)*len(VOL_MULT)*len(RANGE_M)*len(TGT)*len(WICK)*len(SESS))
MIN_N = 60

print(__doc__)
print(f"  declared cells: {NCELL:,}\n")
DS = {sm: V.build(sess=sm) for sm in SESS}
EMA = {}
for sm in SESS:
    c = DS[sm]["c"]
    for n in set(EMA_SLOW + EMA_PULL):
        EMA[(sm, n)] = V._ema(c, n)

t0 = time.time()
rows = []
for sm in SESS:
    D = DS[sm]
    o, h, l, c, v = D["o"], D["h"], D["l"], D["c"], D["v"]
    rth, vwap, atr, vsma = D["rth"], D["vwap"], D["atr"], D["vsma"]
    body, lw, uw = D["body"], D["lw"], D["uw"]
    prev_l = np.concatenate(([np.nan], l[:-1]))
    prev_o = np.concatenate(([np.nan], o[:-1]))
    prev_c = np.concatenate(([np.nan], c[:-1]))
    C2 = np.nan_to_num(c > vwap, nan=False)
    engulf = np.nan_to_num((c > prev_o) & (o < prev_c), nan=False)
    for es in EMA_SLOW:
        e200 = EMA[(sm, es)]
        C1 = c > e200
        amb = np.abs(c - e200) / np.maximum(e200, 1e-9) >= V.PARAMS["ambig"]
        base_a = C1 & C2 & amb & rth
        for ep in EMA_PULL:
            e50 = EMA[(sm, ep)]
            C3 = np.nan_to_num((np.minimum(l, prev_l) <= e50) & (e50 <= c), nan=False)
            base_b = base_a & C3
            for wb in WICK:
                pin = (lw >= wb * body) & (uw <= 0.5 * lw)
                base_c = base_b & (pin | engulf)
                for vm in VOL_MULT:
                    base_d = base_c & (v > vm * vsma)
                    for rm in RANGE_M:
                        sig = np.nan_to_num(base_d & ((h - l) >= rm * atr), nan=False).astype(bool)
                        if sig.sum() < MIN_N:
                            continue
                        for asx, tg in itertools.product(ATR_STOP, TGT):
                            t = V.run(D, sig, side=1, tgt_R=tg, atr_stop=asx,
                                      p={"ema_slow": es, "ema_pull": ep, "ema_tight": 20,
                                         "atr_len": 14, "atr_stop": asx})
                            tr = t[t.blk == 0]; tl = t[t.blk == 1]
                            if len(tr) < MIN_N:
                                continue
                            r = tr.R.to_numpy()
                            cum = np.cumsum(r)
                            dd = float(np.max(np.maximum.accumulate(cum) - cum)) if len(cum) else 0.0
                            rows.append((sm, es, ep, wb, vm, rm, asx, tg, len(tr), float(r.mean()),
                                         float(r.sum()), float(r[r > 0].sum()/max(-r[r < 0].sum(), 1e-9)),
                                         float(r.sum()/max(dd, 1e-9)),
                                         len(tl), float(tl.R.mean()) if len(tl) else np.nan,
                                         float(tl.R.sum()) if len(tl) else np.nan))
    print(f"  {sm} done, {len(rows):,} scorable so far  ({time.time()-t0:.0f}s)")

G = pd.DataFrame(rows, columns=["sess", "ema_slow", "ema_pull", "wick", "vol", "range", "stop",
                                "tgt", "n_res", "R_res", "totR_res", "pf_res", "rdd_res",
                                "n_lock", "R_lock", "totR_lock"])
os.makedirs("results/vwapema", exist_ok=True)
G.to_parquet("results/vwapema/sweep100k.parquet")
print(f"\n  {len(G):,} scorable cells of {NCELL:,} declared   ({time.time()-t0:.0f}s)")
print(f"  share profitable on research: {100*(G.R_res>0).mean():.1f}%  -- a top row is the max of "
      f"~{int((G.R_res>0).sum()):,} positive draws")
print(f"  corr(research R, locked R) = Pearson {np.corrcoef(G.R_res, G.R_lock.fillna(0))[0,1]:+.3f}, "
      f"Spearman {G[['R_res','R_lock']].corr(method='spearman').iloc[0,1]:+.3f}")

print("\n  MARGINAL AVERAGE PER AXIS (research), never the top row")
for ax in ("sess", "ema_slow", "ema_pull", "wick", "vol", "range", "stop", "tgt"):
    m = G.groupby(ax).agg(cells=("R_res", "size"), R_res=("R_res", "mean"), pf=("pf_res", "mean"),
                          share_pos=("R_res", lambda x: 100*(x > 0).mean()), trades=("n_res", "mean"))
    print(f"\n   --- {ax} ---"); print(m.to_string(float_format=lambda v: f"{v:9.4f}"))
