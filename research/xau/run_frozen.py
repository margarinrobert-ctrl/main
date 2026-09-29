"""GATE 1 on FROZEN Donchian primaries -- geometries fitted on OTHER markets, applied to gold with
ZERO gold-specific parameters. This is the fairer test of "the Donchian strategy on XAUUSD", and in
the skill's sense it is much closer to a derived primary than the Optuna one: nothing here was
chosen on gold, so every gold block is out of sample and the deflation burden is the ORIGINAL
studies' rather than a fresh 600-trial search.

The five geometries, taken verbatim from this branch's own notes:
  V11    Donchian 55 entry / 20 exit, 2.5 ATR stop, no target        15m   long   STUDY_V11_MARKET
  V24    Donchian 30 / 20, 2.0 ATR, no target                        30m   long   STUDY_V24 (best cell)
  V38    Donchian 70 / 30, 2.5 ATR, no target                        30m   long   STUDY_V38_LINREG_GRID
  V61i   Donchian 20 / 20, 2.0 ATR, no target                        30m   long   V61 incumbent geometry
  V61h   Donchian 15 / 30, 3.0 ATR, 6 ATR target                     15m   long   V61 high-activity geometry
The CVD gate that V61 ships with is NOT applied: it needs 1-minute bars and gold has none here.
Each is also run SHORT and BOTH, which are declared arms, not a search -- 15 cells, counted.
"""
import os, sys, time, warnings, numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/xau"):
    sys.path.insert(0, os.path.join(ROOT, p))
sys.path.append("/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/mechanism-first-alpha/scripts")
import xau_core as X
from gates import primary_gate
warnings.filterwarnings("ignore"); pd.set_option("display.width", 210)
def line(t): print("\n" + "=" * 122 + f"\n{t}\n" + "=" * 122, flush=True)
OUT = os.path.join(ROOT, "results/xau"); os.makedirs(OUT, exist_ok=True)
print(__doc__)
t0 = time.time()

GEOM = {"V11  55/20 2.5N no-tp": dict(tf=15, ent=55, exN=20, stop=2.5, tp=0.0, hold=960),
        "V24  30/20 2.0N no-tp": dict(tf=30, ent=30, exN=20, stop=2.0, tp=0.0, hold=480),
        "V38  70/30 2.5N no-tp": dict(tf=30, ent=70, exN=30, stop=2.5, tp=0.0, hold=480),
        "V61i 20/20 2.0N no-tp": dict(tf=30, ent=20, exN=20, stop=2.0, tp=0.0, hold=480),
        "V61h 15/30 3.0N 6ATR ": dict(tf=15, ent=15, exN=30, stop=3.0, tp=6.0, hold=480)}
SIDES = {"long": 1, "short": -1, "both": 0}

Ds = {}
for tf in (15, 30):
    if tf == 15:
        Ds[tf] = X.build()
    else:
        f = X.load()
        g = f.resample("30min").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
        tmp = os.path.join(OUT, "_tmp30.csv")
        D = X.build.__wrapped__ if hasattr(X.build, "__wrapped__") else None
        # rebuild the dict directly from the resampled frame
        o, h, l, c, v = (g[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
        ix = pd.DatetimeIndex(g.index); n = len(c)
        d = dict(n=n, o=o, h=h, l=l, c=c, v=v, ix=ix, atr=X._atr(h, l, c),
                 mod=(ix.hour * 60 + ix.minute).to_numpy(), day=(ix.year * 10000 + ix.month * 100 + ix.day).to_numpy())
        sh, sl = pd.Series(h), pd.Series(l)
        d["ent_hi"] = np.vstack([sh.rolling(k).max().shift(1).to_numpy() for k in range(2, 121)])
        d["ent_lo"] = np.vstack([sl.rolling(k).min().shift(1).to_numpy() for k in range(2, 121)])
        d["ex_lo"] = np.vstack([sl.rolling(k).min().shift(1).to_numpy() for k in range(2, 81)])
        d["ex_hi"] = np.vstack([sh.rolling(k).max().shift(1).to_numpy() for k in range(2, 81)])
        d["blk"] = np.full(n, -1, np.int64)
        for i, (nm, (a, b)) in enumerate(X.BLOCKS.items()):
            d["blk"][(ix >= a) & (ix <= b)] = i
        d["last_bar"] = n - 500
        Ds[tf] = d
        print(f"  30m resampled: {n:,} bars")

line("GATE 1 -- five FROZEN geometries x three sides. Every block is out of sample; nothing fitted on gold")
print(f"  {'geometry':24s} {'side':6s} {'block':10s} {'n':>5} {'/yr':>5} {'net %/ev':>10} {'gross':>9} {'95% CI':>23} {'p':>7} {'hit':>6}  verdict")
rows = []
for gn, g in GEOM.items():
    D = Ds[g["tf"]]
    for sn, sv in SIDES.items():
        p = dict(g, side=sv)
        E = X.run(D, p)
        Eg = X.run(D, p, cost=0.0, slip=0.0)
        for i, bn in enumerate(X.BLOCKS):
            e = E[E.blk == i]; eg = Eg[Eg.blk == i]
            if len(e) < 30:
                continue
            yrs = max((e.ts.iloc[-1] - e.ts.iloc[0]).days / 365.25, 1e-9)
            r = primary_gate(e.pct.to_numpy() / 100.0, cost_per_event=0.0); lo, hi = r["net_mean_ci95"]
            rows.append(dict(geom=gn, side=sn, block=bn, n=len(e), per_yr=len(e) / yrs, net=e.pct.mean(),
                             gross=eg.pct.mean(), p=r["bootstrap_p_one_sided"], hit=100 * r["hit_rate"],
                             lo=100 * lo, hi=100 * hi, verdict=r["verdict"].split("--")[0].strip()))
            print(f"  {gn:24s} {sn:6s} {bn:10s} {len(e):>5} {len(e)/yrs:>5.0f} {e.pct.mean():>10.5f} {eg.pct.mean():>9.5f} "
                  f"[{100*lo:>+8.4f},{100*hi:>+8.4f}] {r['bootstrap_p_one_sided']:>7.3f} {100*r['hit_rate']:>5.1f}%  {r['verdict'].split('--')[0].strip()}", flush=True)
T = pd.DataFrame(rows); T.to_parquet(os.path.join(OUT, "frozen_gate1.parquet"))

line("HOW MANY CELLS CLEAR, AND WHERE")
print(f"  cells scored: {len(T)} (5 geometries x 3 sides x 3 blocks, minus thin cells)")
for bn in X.BLOCKS:
    s = T[T.block == bn]
    print(f"  {bn:10s} net-positive {int((s.net > 0).sum()):>2}/{len(s):<2}   p<=0.10 {int((s.p <= 0.10).sum()):>2}/{len(s):<2}   "
          f"GROSS-positive {int((s.gross > 0).sum()):>2}/{len(s):<2}   mean net {s.net.mean():+.5f}")
print("\n  by side (all blocks pooled -- gold rose ~4.4x over the sample, so read the long column with that in mind):")
print(T.groupby("side").agg(cells=("net", "size"), mean_net=("net", "mean"), mean_gross=("gross", "mean"),
                            pos=("net", lambda x: 100 * (x > 0).mean())).to_string(float_format=lambda v: f"{v:8.5f}"))
print("\n  the three cells with the best OUT-OF-SAMPLE evidence (blocks B and C only, ranked by net):")
oos = T[T.block != "A_primary"].sort_values("net", ascending=False).head(6)
print(oos[["geom", "side", "block", "n", "net", "gross", "p", "hit", "verdict"]].to_string(index=False, float_format=lambda v: f"{v:8.4f}"))

line("BUY AND HOLD, for scale")
f = X.load()
for i, (bn, (a, b)) in enumerate(X.BLOCKS.items()):
    s = f[(f.index >= a) & (f.index <= b)]
    if len(s) < 10: continue
    print(f"  {bn:10s} gold {s.close.iloc[0]:8.1f} -> {s.close.iloc[-1]:8.1f}   {100*(s.close.iloc[-1]/s.close.iloc[0]-1):+8.1f}% over the block")
print(f"\n  runtime {time.time()-t0:.0f}s")
