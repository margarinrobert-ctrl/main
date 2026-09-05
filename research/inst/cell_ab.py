"""Pin the user's cell -- 15m RTH, Donchian 55 / exit 30, 1.5 adaptive ATR, no target, swing hold,
MA200 floor >= 2 ATR, CHOP <= 40 -- and write its trade table with the signal bar of every trade,
so a model can be scored on the bars the strategy actually fires on."""
import os, sys, warnings
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56", "research/inst"):
    sys.path.insert(0, os.path.join(ROOT, p))
import v61core as V
from donchian500k import signal_sets, geometry
warnings.filterwarnings("ignore")
D = V.build(15); rth = (D["mod"] >= 570) & (D["mod"] < 930)
Gd = geometry(15); rows, offs, vals, K = signal_sets(D, rth)
exlo = np.vstack([D["ex_lo"][e] for e in V.EXITS])
calm = np.zeros(D["n"], np.bool_); v = D["vpct"]; calm[np.isfinite(v)] = v[np.isfinite(v)] <= 0.5
gi = int(np.flatnonzero((Gd.exN == 30) & (Gd.stop == 1.5) & (Gd.tp == 0.0) & (Gd.hold_name == "swing") & (Gd.adapt == 1))[0])
si = int(np.flatnonzero((K.ent == 55) & (K.ma == 2.0) & (K.chop == 40.0))[0])
g1 = Gd.iloc[[gi]]
xb, R, pts = V._tensor(D["o"], D["h"], D["l"], D["c"], D["atr"], rows.astype(np.int64), exlo, calm,
                       g1["ei"].to_numpy(np.int64), g1["shi"].to_numpy(float), g1["slo"].to_numpy(float),
                       g1["tp"].to_numpy(float), g1["hold"].to_numpy(np.int64), V.COST, V.SLIP, D["n"])
epx = D["o"][np.minimum(rows + 1, D["n"] - 1)]
sel = vals[offs[si]:offs[si + 1]]
free = -1; tr = []
for kk in sel:
    if xb[kk, 0] < 0 or not np.isfinite(R[kk, 0]) or rows[kk] <= free: continue
    free = xb[kk, 0]; tr.append((int(rows[kk]), int(xb[kk, 0]), float(R[kk, 0]), 100 * float(pts[kk, 0]) / epx[kk], float(pts[kk, 0])))
T = pd.DataFrame(tr, columns=["sig", "xb", "R", "pct", "pts"]); T["research"] = T.sig < D["cut"]
T["ts"] = pd.DatetimeIndex(D["ix"])[T.sig.to_numpy()]
for bn, m in (("research", T.research), ("locked", ~T.research)):
    t = T[m]; p = t.pct.to_numpy()
    print(f"  {bn:8s} n {len(t)} PF {p[p>0].sum()/-p[p<=0].sum():.3f} win {100*(p>0).mean():.1f}% total {p.sum():+.2f}%")
T.to_parquet("results/inst/cell_ab_trades.parquet")
# every ELIGIBLE signal bar of the cell (before the position lock), for the forecaster gate
np.save("results/inst/cell_ab_sigbars.npy", rows[sel])
print("signal bars (pre-lock):", len(sel), " cut bar:", D["cut"], " n bars:", D["n"])
