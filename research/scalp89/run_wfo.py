"""Walk-forward with the selection re-run INSIDE every training fold, trail OFF.
Declared grid: trend EMA x fast EMA x min pullback x StochRSI reset lookback x stop x target
= 3^6 = 729 cells. Arms: RE-CHOSEN per fold, FIXED (the screenshot's constants), RANDOM cell."""
from __future__ import annotations
import os, sys, warnings, itertools
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s89_core as M
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
def line(t): print("\n" + "=" * 124 + f"\n{t}\n" + "=" * 124)
TREND, FAST, MINPB, RESET, STOP, TGT = (55, 89, 144), (5, 8, 13), (0.0, 15.0, 30.0), (5, 8, 12), (1.0, 1.5, 2.0), (1.5, 2.5, 4.0)
D0 = M.build("NQ", 5, dict(M.CFG, trail_on=0))
ix = pd.DatetimeIndex(D0["ts"]); c = D0["c"]
# cache the indicator variants once
emas = {n: M._ema(c, n) for n in set(TREND) | set(FAST)}
k = D0["k"]; klo = {r: pd.Series(k).rolling(r).min().to_numpy() for r in RESET}; khi = {r: pd.Series(k).rolling(r).max().to_numpy() for r in RESET}
grid = list(itertools.product(TREND, FAST, MINPB, RESET, STOP, TGT))
store = []
for tr, fa, mp, rs, st, tg in grid:
    cfg = dict(M.CFG, trail_on=0, trend=tr, fast=fa, min_pb=mp, reset_look=rs, stop_mult=st, tgt_mult=tg)
    D = dict(D0, e_tr=emas[tr], e_f=emas[fa], k_lo=klo[rs], k_hi=khi[rs])
    t = M.run(D, cfg=cfg)
    store.append((ix[t["entry_bar"].to_numpy()].to_numpy() if len(t) else np.array([], "datetime64[ns]"), t["pct"].to_numpy().astype(np.float32)))
print(f"evaluated {len(grid)} cells once each; median trades per cell {np.median([len(s[1]) for s in store]):.0f}")
fixed_i = grid.index((89, 8, 15.0, 8, 1.5, 2.5))
q = pd.PeriodIndex(ix, freq="Q").unique().sort_values()
def slc(ci, lo, hi):
    ts, v = store[ci]
    if len(ts) == 0: return np.array([], np.float32)
    return v[(ts >= np.datetime64(lo)) & (ts <= np.datetime64(hi))]
rng = np.random.default_rng(3)
for sname, mk in (("rolling 4Q", lambda i: q[i-4].start_time), ("expanding", lambda i: q[0].start_time)):
    line(f"WALK-FORWARD -- {sname} train / 1Q test, trail OFF")
    print(f"  {'fold':8s}{'chosen (trend/fast/pb/reset/stop/tgt)':40s}{'IS n':>6s}{'IS tot%':>9s}{'OOS n':>7s}{'RE-CHOSEN':>11s}{'FIXED':>9s}{'RANDOM':>9s}")
    R = []
    for i in range(4, len(q)):
        trlo, trhi = mk(i), q[i-1].end_time; telo, tehi = q[i].start_time, q[i].end_time
        best, bv = -1, -1e18
        for ci in range(len(grid)):
            v = slc(ci, trlo, trhi)
            if len(v) >= 30 and v.sum() > bv: best, bv = ci, float(v.sum())
        if best < 0: continue
        vo = slc(best, telo, tehi); vf = slc(fixed_i, telo, tehi)
        vr = np.mean([slc(int(rng.integers(len(grid))), telo, tehi).sum() for _ in range(100)])
        g = grid[best]
        R.append(dict(fold=str(q[i]), is_tot=bv, is_n=len(slc(best, trlo, trhi)), oos_n=len(vo), oos=vo.sum(), fixed=vf.sum(), rnd=vr, **dict(zip(("trend","fast","pb","reset","stop","tgt"), g))))
        print(f"  {str(q[i]):8s}{'/'.join(str(x) for x in g):40s}{R[-1]['is_n']:>6d}{bv:>9.2f}{len(vo):>7d}{vo.sum():>11.2f}{vf.sum():>9.2f}{vr:>9.2f}")
    R = pd.DataFrame(R); R.to_parquet(f"results/scalp89/wfo_{sname.split()[0]}.parquet")
    print(f"\n  {'arm':16s}{'total OOS %':>13s}{'folds +':>9s}{'worst':>8s}")
    for arm, col in (("RE-CHOSEN", "oos"), ("FIXED", "fixed"), ("RANDOM", "rnd")):
        print(f"  {arm:16s}{R[col].sum():>13.2f}{f'{int((R[col]>0).sum())}/{len(R)}':>9s}{R[col].min():>8.2f}")
    print(f"  post-cut (2025Q1+) only: RE-CHOSEN {R[R.fold>='2025Q1']['oos'].sum():+.2f}  FIXED {R[R.fold>='2025Q1']['fixed'].sum():+.2f}  RANDOM {R[R.fold>='2025Q1']['rnd'].sum():+.2f}")
    print("  stability: " + "  ".join(f"{a}={dict(R[a].value_counts())}" for a in ("trend","fast","pb","reset","stop","tgt")))
