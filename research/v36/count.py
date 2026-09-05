"""How many setups does each definition actually produce? Run before anything is simulated --
if a definition yields 40 trades in three years it cannot be validated whatever it earns."""
import sys, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/v36")
import numpy as np, pandas as pd
import indicators as I, levels as LV, setup as S

t0 = time.perf_counter()
d = LV.load()
atr1 = I.ema(I.true_range(d["h"], d["l"], d["c"]), 14)
pools = S.build_pools(d)
print("=" * 112)
print("SETUP CENSUS -- NQ 1m, 2022-12-26 to 2025-12-11")
print("=" * 112)
print(f"   liquidity pools in the book: {len(pools['hi'])} highs, {len(pools['lo'])} lows")
src = pd.Series([b[2] for b in pools['lo']]).value_counts()
print("   low pools by source: " + "  ".join(f"{k} {v}" for k, v in src.items()))

sw = {}
print(f"\n   {'sweep definition':<14}{'longs':>8}{'shorts':>8}{'per year':>10}"
      f"{'median pen (ATR)':>18}")
for defn in S.SWEEP_DEFS:
    a = S.find_sweeps(d, pools, +1, defn=defn, atr=atr1)
    b = S.find_sweeps(d, pools, -1, defn=defn, atr=atr1)
    sw[defn] = (a, b)
    yrs = (d["ts"][-1] - d["ts"][0]).days / 365.25
    med = pd.concat([a.pen_atr, b.pen_atr]).median() if len(a) + len(b) else float("nan")
    print(f"   {defn:<14}{len(a):>8}{len(b):>8}{(len(a) + len(b)) / yrs:>10.0f}{med:>18.3f}")

print(f"\n   {'tf':>4}{'FVGs':>9}{'IFVGs':>9}{'bull IFVG':>11}{'bear IFVG':>11}")
ifv = {}
for tf in (5, 15):
    r = S.htf_frame(d, tf)
    atr_tf = I.ema(I.true_range(r["h"], r["l"], r["c"]), 14)
    f = S.find_fvgs(r, atr_tf)
    iv = S.find_ifvgs(r, f)
    ifv[tf] = (r, iv)
    print(f"   {tf:>4}{len(f):>9}{len(iv):>9}{int((iv.pol > 0).sum()):>11}"
          f"{int((iv.pol < 0).sum()):>11}")

print(f"\n   JOINED SETUPS -- sweep then IFVG within 12 entry-timeframe bars")
print(f"   {'sweep def':<14}{'tf':>4}{'longs':>8}{'shorts':>8}{'total':>8}{'per year':>10}"
      f"{'median gap':>12}")
rows = []
for defn in S.SWEEP_DEFS:
    for tf in (5, 15):
        r, iv = ifv[tf]
        a = S.setups(d, +1, sw[defn][0], iv, r, tf)
        b = S.setups(d, -1, sw[defn][1], iv, r, tf)
        yrs = (d["ts"][-1] - d["ts"][0]).days / 365.25
        tot = len(a) + len(b)
        med = pd.concat([a.gap_bars, b.gap_bars]).median() if tot else float("nan")
        print(f"   {defn:<14}{tf:>4}{len(a):>8}{len(b):>8}{tot:>8}{tot / yrs:>10.0f}{med:>12.1f}")
        if tot:
            rows.append(pd.concat([a, b]).assign(defn=defn))
if rows:
    allsu = pd.concat(rows, ignore_index=True)
    allsu.to_csv("research/v36/v36_setups.csv", index=False)
    print(f"\n   saved {len(allsu)} setup rows across all definitions")
    print("   by liquidity source:")
    for k, v in allsu.src.value_counts().items():
        print(f"      {k:<10}{v:>6}  ({v / len(allsu):.1%})")
print(f"\n   elapsed {time.perf_counter() - t0:.0f}s")
