"""EMA150 trend / EMA20-50 cross aligned with EMA200 / pullback-to-EMA20 on the Turtle Scalp.
Base rates BEFORE any P&L, a declared grid read by MARGINAL AVERAGE, ablations, two controls,
cross-market, Monte Carlo, then ONE locked read of pre-declared cells. Research = US30 pre-2022."""
import os, sys, warnings, itertools
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ts_core as T
from core import _atr_wilder, _rolling_max
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
def line(t): print("\n" + "=" * 126 + f"\n{t}\n" + "=" * 126)
def hdr(): print(f"  {'':56s}{'n':>6s}{'R/trade':>9s}{'PF':>7s}{'win%':>6s}{'pts/tr':>8s}{'$ 1u':>9s}{'maxDD':>8s}{'Sharpe':>7s}  exits")
def row(nm, t):
    if len(t) < 5: print(f"  {nm:56s}{len(t):>6d}   (too few)"); return
    s = T.stats(t); mix = t["exit"].value_counts(normalize=True).mul(100).round(0).to_dict()
    print(f"  {nm:56s}{s['n']:>6d}{s['R']:>9.4f}{s['pf']:>7.3f}{s['win']:>6.1f}{s['pts']:>8.2f}{s['usd']:>9,.0f}{s['dd']:>8,.0f}{s['sharpe']:>7.2f}  "
          + " ".join(f"{k}{int(v)}%" for k, v in mix.items()))

MK, TF = "US30", 15
D = T.build(MK, TF); RES = D["blocks"]["research"]; LCK = ~RES
atr = _atr_wilder(D["h"], D["l"], D["c"], T.PRESET["atr_len"])
P = T.PRESET
# the script's raw Donchian signal bars inside its window (what every gate acts on)
hi1 = _rolling_max(D["h"], P["entry1"]); hi2 = _rolling_max(D["h"], P["entry2"])
sigb = np.zeros(D["n"], bool); sigb[1:] = (D["h"][1:] > hi1[:-1]) | (D["h"][1:] > hi2[:-1])
sigb &= (D["mod"] >= P["win0"]) & (D["mod"] < P["win1"]); sigb[:250] = False
fin = np.ones(D["n"], bool); fin[:250] = False

line("A. BASE RATES -- what each gate passes on the DONCHIAN SIGNAL BARS against all bars (lift), research")
print(f"  signal bars in the window on research: {int((sigb & RES).sum()):,}")
G = {"EMA150 above": dict(ema150="above"), "EMA150 support (<=3 ATR)": dict(ema150="support"),
     "20>50>200 state": dict(cross="state"), "fresh 20/50 cross <=5, >200": dict(cross="fresh", x_win=5),
     "pullback: low<=EMA20 in 3": dict(pullback="touch", pb_win=3), "pullback: low<=EMA20 in 5": dict(pullback="touch", pb_win=5),
     "pullback: low<=EMA20 in 10": dict(pullback="touch", pb_win=10)}
print(f"  {'gate':>32}  {'on signal bars':>14}  {'on all bars':>11}  {'lift':>6}")
for nm, kw in G.items():
    g = T.gate(D, atr=atr, **kw)
    ps = g[sigb & RES].mean(); pa = g[fin & RES].mean()
    print(f"  {nm:>32}  {100*ps:13.1f}%  {100*pa:10.1f}%  {ps/pa:6.2f}x")
print("  A gate near 100% on signal bars is the breakout restated (RSI 94.7%, Aroon 100%, MACD 99.8% here before).")

line("B. THE DECLARED GRID -- ema150 x cross x pullback(window); research; read by MARGINAL AVERAGE")
rows = []
for e1, xr, pb in itertools.product(("off", "above", "support"), ("off", "state", "fresh"), ("off", 3, 5, 10)):
    kw = dict(ema150=e1, cross=xr)
    if pb != "off": kw.update(pullback="touch", pb_win=pb)
    g = T.gate(D, atr=atr, **kw) & RES
    t = T.run(D, ok=g)
    if len(t) < 30: continue
    s = T.stats(t); rows.append(dict(ema150=e1, cross=xr, pullback=pb, **s))
Gd = pd.DataFrame(rows)
print(f"  {len(Gd)} scorable cells; share PF>1 {100*(Gd.pf>1).mean():.1f}%; median R/trade {Gd.R.median():+.4f}; base (all off) "
      + f"R {Gd[(Gd.ema150=='off')&(Gd.cross=='off')&(Gd.pullback=='off')].R.iloc[0]:+.4f}")
for ax in ("ema150", "cross", "pullback"):
    print(f"   {ax:>8}: " + "   ".join(f"{k}: R {v.R.mean():+.4f} PF {v.pf.mean():.3f} Sh {v.sharpe.mean():.2f} n~{v.n.mean():.0f}" for k, v in Gd.groupby(ax)))
print("\n  top 6 by R/trade (max of many draws -- shape only):")
print(Gd.sort_values("R", ascending=False).head(6)[["ema150", "cross", "pullback", "n", "R", "pf", "win", "sharpe", "dd"]].to_string(index=False))
Gd.assign(pullback=Gd.pullback.astype(str)).to_parquet("results/tscalp/grid.parquet")

line("C. THE ASK -- EMA150 trend + 20/50 cross aligned with 200 + pullback to EMA20 then the Donchian; research")
ASK = dict(ema150="above", cross="state", pullback="touch", pb_win=5)
ASKF = dict(ema150="above", cross="fresh", x_win=5, pullback="touch", pb_win=5)
hdr()
row("script as shipped (no EMA gates)", T.run(D, ok=RES))
row("the ask (cross as STATE 20>50>200)", T.run(D, ok=T.gate(D, atr=atr, **ASK) & RES))
row("the ask (cross as FRESH <=5 bars, 20>200)", T.run(D, ok=T.gate(D, atr=atr, **ASKF) & RES))
print("  drop-one from the state version:")
row("  - no EMA150", T.run(D, ok=T.gate(D, atr=atr, cross="state", pullback="touch", pb_win=5) & RES))
row("  - no cross", T.run(D, ok=T.gate(D, atr=atr, ema150="above", pullback="touch", pb_win=5) & RES))
row("  - no pullback", T.run(D, ok=T.gate(D, atr=atr, ema150="above", cross="state") & RES))
print("  each gate ALONE on the script:")
row("  EMA150 above only", T.run(D, ok=T.gate(D, atr=atr, ema150="above") & RES))
row("  EMA150 support only", T.run(D, ok=T.gate(D, atr=atr, ema150="support") & RES))
row("  20>50>200 state only", T.run(D, ok=T.gate(D, atr=atr, cross="state") & RES))
row("  fresh cross only", T.run(D, ok=T.gate(D, atr=atr, cross="fresh") & RES))
row("  pullback(5) only", T.run(D, ok=T.gate(D, atr=atr, pullback="touch", pb_win=5) & RES))
print("  the script's own exit switches on the ask (state):")
row("  ask + channel exit ON", T.run(D, ok=T.gate(D, atr=atr, **ASK) & RES, cfg=dict(chan_exit=True)))
row("  ask + NO take profit", T.run(D, ok=T.gate(D, atr=atr, **ASK) & RES, cfg=dict(tp_r=0.0)))
row("  ask + one unit (no pyramid)", T.run(D, ok=T.gate(D, atr=atr, **ASK) & RES, cfg=dict(max_units=1, pyr_step=0.0)))
row("  ask + no flatten (hold past 11:00)", T.run(D, ok=T.gate(D, atr=atr, **ASK) & RES, cfg=dict(flat0=24*60, flat1=24*60)))
row("  ask, zero cost", T.run(D, ok=T.gate(D, atr=atr, **ASK) & RES, fee=0.0, slip=0.0))
row("  ask, 2x cost", T.run(D, ok=T.gate(D, atr=atr, **ASK) & RES, cost_mult=2.0))

line("D. CONTROL on research -- a RANDOM FILTER of the same selectivity (keep as many signal bars at random)")
def ctrl_filter(g, ndraw=300, seed=3):
    rng = np.random.default_rng(seed)
    base_sig = np.where(sigb & RES)[0]; keep = int((g & sigb & RES).sum())
    out = []
    for _ in range(ndraw):
        pick = rng.choice(base_sig, size=min(keep, len(base_sig)), replace=False)
        m = np.zeros(D["n"], bool); m[pick] = True
        t = T.run(D, ok=m); out.append(t["R"].mean() if len(t) else np.nan)
    return np.array(out)
for nm, kw in (("script as shipped", {}), ("EMA150 above", dict(ema150="above")), ("20>50>200 state", dict(cross="state")),
               ("pullback(5)", dict(pullback="touch", pb_win=5)), ("THE ASK (state)", ASK), ("THE ASK (fresh)", ASKF)):
    g = T.gate(D, atr=atr, **kw) if kw else np.ones(D["n"], bool)
    t = T.run(D, ok=g & RES); obs = t["R"].mean(); s = T.stats(t)
    if kw:
        cf = ctrl_filter(g)
        print(f"  {nm:24s} n={s['n']:>5} R {obs:+.4f} PF {s['pf']:.3f} | random FILTER of same selectivity: median {np.nanmedian(cf):+.4f} "
              f"5-95% [{np.nanpercentile(cf,5):+.4f}, {np.nanpercentile(cf,95):+.4f}]  p {np.mean(cf>=obs):.3f}")
    else:
        print(f"  {nm:24s} n={s['n']:>5} R {obs:+.4f} PF {s['pf']:.3f}  (the base every filter is scored against)")

line("E. CROSS-MARKET -- the same gates, frozen, on NQ 15m and US100 15m (chose nothing)")
hdr()
for mk in ("US100", "NQ"):
    Dx = T.build(mk, 15); ax = _atr_wilder(Dx["h"], Dx["l"], Dx["c"], P["atr_len"])
    for bn, bm in Dx["blocks"].items():
        row(f"  {mk} [{bn}] script as shipped", T.run(Dx, ok=bm))
        row(f"  {mk} [{bn}] the ask (state)", T.run(Dx, ok=T.gate(Dx, atr=ax, **ASK) & bm))

line("F. MONTE CARLO on research -- the ask (state) beside the base")
rng = np.random.default_rng(17)
for nm, kw in (("script as shipped", {}), ("THE ASK (state)", ASK)):
    g0 = T.gate(D, atr=atr, **kw) if kw else np.ones(D["n"], bool)
    t = T.run(D, ok=g0 & RES); v = t["pnl"].to_numpy(); days = t["sess"].to_numpy(); tot = v.sum()
    # execution
    ex = np.array([T.run(D, ok=g0 & RES, fee=D["fee"] * rng.uniform(0.5, 2.0), slip=D["slip"] * rng.uniform(0, 2.0))["pnl"].sum() for _ in range(300)])
    # price jitter, EMAs / channels / ATR recomputed from the jittered bars
    jit = []
    for _ in range(100):
        o = D["o"] + rng.normal(0, D["tick"], D["n"]); h = D["h"] + rng.normal(0, D["tick"], D["n"])
        l = D["l"] + rng.normal(0, D["tick"], D["n"]); c = D["c"] + rng.normal(0, D["tick"], D["n"])
        hi = np.maximum(np.maximum(o, c), np.maximum(h, l)); lo = np.minimum(np.minimum(o, c), np.minimum(h, l))
        Dj = dict(D, o=o, h=hi, l=lo, c=c, ema20=T._ema(c, 20), ema50=T._ema(c, 50), ema150=T._ema(c, 150), ema200=T._ema(c, 200))
        aj = _atr_wilder(hi, lo, c, P["atr_len"])
        gj = T.gate(Dj, atr=aj, **kw) if kw else np.ones(D["n"], bool)
        jit.append(T.run(Dj, ok=gj & RES)["pnl"].sum())
    jit = np.array(jit)
    # day-block bootstrap (edge) and permutation (path)
    _u, inv = np.unique(days, return_inverse=True); nd = inv.max() + 1; by = [np.flatnonzero(inv == j) for j in range(nd)]
    bs = np.array([v[np.concatenate([by[j] for j in rng.integers(0, nd, nd)])].mean() for _ in range(3000)])
    def mdd(r): e = np.cumsum(r); return float(np.max(np.maximum.accumulate(e) - e))
    pm = np.array([mdd(rng.permutation(v)) for _ in range(3000)]); rd = mdd(v)
    x = np.sort(v)[::-1]
    print(f"  {nm}: n {len(v)}, total {tot:+,.0f} pts")
    print(f"     execution (slip U(0,2x), fee U(0.5x,2x)):  total p5 {np.quantile(ex,.05):+,.0f} p50 {np.median(ex):+,.0f} p95 {np.quantile(ex,.95):+,.0f}  P(total>0) {(ex>0).mean():.3f}")
    print(f"     price jitter 1 tick, indicators RECOMPUTED: total p5 {np.quantile(jit,.05):+,.0f} p50 {np.median(jit):+,.0f} p95 {np.quantile(jit,.95):+,.0f}  P(total>0) {(jit>0).mean():.3f}")
    print(f"     day-block bootstrap: mean {v.mean():+.3f} pts  95% CI [{np.quantile(bs,.025):+.3f}, {np.quantile(bs,.975):+.3f}]  P(mean<=0) {(bs<=0).mean():.3f}")
    print(f"     permutation: realised DD {rd:,.0f}  MC p50 {np.median(pm):,.0f}  p95 {np.quantile(pm,.95):,.0f}  p99 {np.quantile(pm,.99):,.0f}  realised pctile {(pm<=rd).mean():.2f}")
    print(f"     concentration: top 5% of trades = {100*x[:max(1,len(x)//20)].sum()/tot if tot else float('nan'):+.0f}% of net")

line("G. ONE LOCKED READ (validation 2022-23 + test 2024+) -- pre-declared cells only")
hdr()
for nm, kw in (("script as shipped", {}), ("the ask (state)", ASK), ("the ask (fresh)", ASKF)):
    g = T.gate(D, atr=atr, **kw) if kw else np.ones(D["n"], bool)
    t = T.run(D, ok=g & LCK)
    row(f"  {nm} [locked, pooled]", t)
    for bn in ("validation", "test"):
        row(f"    {bn}", t[t.block == bn])
