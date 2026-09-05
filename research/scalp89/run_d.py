"""D. Is there ANY geometry that captures the short signal's 15-30 minute information net of costs?
Research block, NQ 5m, trail OFF, read by MARGINAL AVERAGE per axis. Net and gross."""
from __future__ import annotations
import os, sys, warnings, itertools
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s89_core as M
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
def line(t): print("\n" + "=" * 124 + f"\n{t}\n" + "=" * 124)
D = M.build("NQ", 5); rng = np.random.default_rng(9)
STOPS, TGTS, HOLDS = (1.0, 1.5, 2.0, 3.0), (0.5, 1.0, 1.5, 2.5, 99.0), (3, 6, 12, 0)
sig = M.signals(D, dict(M.CFG, trail_on=0))
rows = []
for side_nm, so in (("short", np.where(sig == -1, -1, 0)), ("long", np.where(sig == 1, 1, 0))):
    for st, tg, hd in itertools.product(STOPS, TGTS, HOLDS):
        cfg = dict(M.CFG, trail_on=0, stop_mult=st, tgt_mult=tg)
        t = M.run(D, cfg=cfg, side_override=so, max_hold=hd); r = t[t.block == "research"]
        g = M.run(D, cfg=cfg, side_override=so, max_hold=hd, cost=0.0, slip=0.0); gr = g[g.block == "research"]
        s = M.stats(r); rows.append(dict(side=side_nm, stop=st, tgt=tg, hold=hd, n=s["n"], pct=s["pct"],
                                         pf=s["pf"], win=s["win"], gross=gr["pct"].mean() if len(gr) else np.nan,
                                         usd=s["usd_tot"]))
G = pd.DataFrame(rows); G.to_parquet("results/scalp89/geom.parquet")
for side_nm in ("short", "long"):
    g = G[G.side == side_nm]
    line(f"{side_nm.upper()} -- {len(g)} cells, share net-profitable {100*(g.pct>0).mean():.1f}%, gross-profitable {100*(g.gross>0).mean():.1f}%")
    for ax, vals in (("stop", STOPS), ("tgt", TGTS), ("hold", HOLDS)):
        print(f"  {ax}")
        for v in vals:
            m = g[g[ax] == v]
            print(f"    {str(v):>5s}   cells {len(m):3d}   mean net %/t {m.pct.mean():+.4f}   mean GROSS {m.gross.mean():+.4f}"
                  f"   share net+ {100*(m.pct>0).mean():5.1f}%   median n {m.n.median():5.0f}")
    top = g.nlargest(5, "pct")
    print("  top 5 net cells (printed because they are NOT the answer):")
    print(top[["stop","tgt","hold","n","pct","gross","pf","win","usd"]].to_string(index=False, float_format=lambda v: f"{v:,.4f}"))

line("THE SHORT SIGNAL'S BEST MARGINAL GEOMETRY against a random-entry control (same session, same geometry)")
gs = G[G.side == "short"]
best = {ax: gs.groupby(ax)["pct"].mean().idxmax() for ax in ("stop", "tgt", "hold")}
print(f"  marginal consensus: stop {best['stop']} ATR, target {best['tgt']} ATR, max hold {best['hold']} bars")
cfg = dict(M.CFG, trail_on=0, stop_mult=float(best["stop"]), tgt_mult=float(best["tgt"]))
so = np.where(sig == -1, -1, 0)
t = M.run(D, cfg=cfg, side_override=so, max_hold=int(best["hold"])); r = t[t.block == "research"]
obs = r["pct"].mean()
ins = (D["mod"] >= M.CFG["sess_start"]) & (D["mod"] < M.CFG["sess_end"]) & D["blocks"]["research"] & np.isfinite(D["atr"]) & (D["atr"] > 0)
pool = np.flatnonzero(ins); draws = np.zeros(400)
for d in range(400):
    pick = np.sort(rng.choice(pool, size=min(len(pool), 3 * len(r)), replace=False))
    co = np.zeros(D["n"], np.int64); co[pick] = -1
    tc = M.run(D, cfg=cfg, side_override=co, max_hold=int(best["hold"])); tc = tc[tc.block == "research"]
    draws[d] = tc["pct"].mean() if len(tc) else 0.0
gross_best = M.run(D, cfg=cfg, side_override=so, max_hold=int(best["hold"]), cost=0.0, slip=0.0)
gross_best = gross_best[gross_best.block == "research"]["pct"].mean()
print(f"  n {len(r)}  observed {obs:+.4f} %/trade (gross {gross_best:+.4f})"
      f"  control median {np.median(draws):+.4f}  5-95% [{np.quantile(draws,.05):+.4f}, {np.quantile(draws,.95):+.4f}]  p {(draws>=obs).mean():.3f}")
print(f"  multiplicity: {len(G)} geometry cells were scored to pick this one.")
