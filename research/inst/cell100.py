"""Pin the >=100 trades/yr envelope cell exactly (rebuild tf 15 only) and print everything the
Pine header needs: parameters, both blocks, exit mix, hold, drawdown, neighbourhood."""
import os, sys, warnings
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56", "research/inst"):
    sys.path.insert(0, os.path.join(ROOT, p))
import v61core as V
from frontier import signal_sets, geometry
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
D = V.build(15); rth = (D["mod"] >= 570) & (D["mod"] < 930)
Gd = geometry(15); rows, offs, vals, K = signal_sets(D, rth)
exlo = np.vstack([D["ex_lo"][e] for e in V.EXITS])
calm = np.zeros(D["n"], np.bool_); v = D["vpct"]; calm[np.isfinite(v)] = v[np.isfinite(v)] <= 0.5
xb, R, pts = V._tensor(D["o"], D["h"], D["l"], D["c"], D["atr"], rows.astype(np.int64), exlo, calm,
                       Gd["ei"].to_numpy(np.int64), Gd["shi"].to_numpy(float), Gd["slo"].to_numpy(float),
                       Gd["tp"].to_numpy(float), Gd["hold"].to_numpy(np.int64), V.COST, V.SLIP, D["n"])
epx = D["o"][np.minimum(rows + 1, D["n"] - 1)]
st = V._sweep(offs, vals, rows.astype(np.int64), xb, R, pts, epx, D["cut"], len(Gd))
ls = V._sweep_loss(offs, vals, rows.astype(np.int64), xb, R, D["cut"], len(Gd))
d = V.table(dict(G=Gd, K=K, stat=st, loss=ls), 15)
d["hold_name"] = Gd["hold_name"].to_numpy()[np.tile(np.arange(len(Gd)), len(K))]
d["tpy_res"] = d.n_res / V.YEARS["res"]; d["tpy_lock"] = d.n_lock / V.YEARS["lock"]
ok = d[(d.n_res >= 40) & (d.tpy_res >= 100) & (d.hold_name != "swing")]
i = ok.pf_res.idxmax(); b = d.loc[i]
cols = ["ent","exN","stop","tp","hold","adapt","k","w","ma","chop","psh","n_res","pf_res","win_res","pct_res","tpy_res","n_lock","pf_lock","win_lock","pct_lock","tpy_lock"]
print("THE CELL:"); print(b[cols].to_string())
# its trade table under the position lock
s_idx = i // len(Gd); g = i % len(Gd)
sel = vals[offs[s_idx]:offs[s_idx + 1]]; free = -1; tr = []
for kk in sel:
    if xb[kk, g] < 0 or not np.isfinite(R[kk, g]) or rows[kk] <= free: continue
    free = xb[kk, g]; tr.append((rows[kk], xb[kk, g], float(R[kk, g]), 100 * float(pts[kk, g]) / epx[kk], float(pts[kk, g])))
T = pd.DataFrame(tr, columns=["sig", "xb", "R", "pct", "pts"]); T["research"] = T.sig < D["cut"]
T["hold"] = T.xb - T.sig - 1
for bn, m in (("research", T.research), ("locked", ~T.research)):
    t = T[m]; p = t.pct.to_numpy(); eq = np.cumsum(p); dd = (np.maximum.accumulate(eq) - eq).max()
    hit_hold = (t.hold >= 26).mean()
    print(f"  {bn:8s} n {len(t)} PF {p[p>0].sum()/-p[p<=0].sum():.3f} win {100*(p>0).mean():.1f}% pct/trade {p.mean():+.4f} total {p.sum():+.2f}% "
          f"maxDD {dd:.2f}% median hold {t.hold.median():.0f} bars, hold-cap exits {100*hit_hold:.0f}%, $/trade 1 MNQ {2*t.pts.mean():+.1f}, p90 R {np.quantile(t.R,.9):.2f}")
x = np.sort(T[T.research].pct.to_numpy())[::-1]; print(f"  research top 5% of trades = {100*x[:len(x)//20].sum()/x.sum():.0f}% of net")
print("\nONE-RUNG NEIGHBOURS on research (ent/exN/stop/ma/chop each moved one step), research PF -> locked PF:")
key = ["ent","exN","stop","ma","chop"]; lev = {a: sorted(d[a].unique()) for a in key}
base = {a: b[a] for a in ["ent","exN","stop","tp","hold","adapt","k","w","ma","chop","psh"]}
for a in key:
    j = lev[a].index(b[a]); out = []
    for jj in (j-1, j+1):
        if 0 <= jj < len(lev[a]):
            q = dict(base); q[a] = lev[a][jj]
            m = np.ones(len(d), bool)
            for kk_, vv in q.items(): m &= (d[kk_] == vv).to_numpy()
            r = d[m]
            if len(r): out.append(f"{a}={q[a]}: {r.pf_res.iloc[0]:.3f} -> {r.pf_lock.iloc[0]:.3f} ({r.tpy_res.iloc[0]:.0f}/yr)")
    print("  " + " | ".join(out))
T.to_parquet("results/inst/cell100_trades.parquet")
