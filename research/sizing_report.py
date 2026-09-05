"""What 173,340 sizing combinations actually buy, and what the selection among them costs."""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
from sizing_sweep import (CAPITAL, EQ_FILTER, MAX_LOTS, RISK_PCT, SCHEMES, STOPS,
                          VOL_LB, VOL_MULT)

Z = np.load("results/sizing/sizing.npz", allow_pickle=True)
grid = Z["grid"]
COLS = ["net", "maxDD", "sharpe", "res_net", "lok_net", "mar", "ruin"]


def describe(g):
    sc = SCHEMES[int(g[0])]
    bits = [sc]
    if sc != "fixed":
        bits.append(f"risk {100*g[1]:.2f}%")
    if sc == "vol target":
        bits.append(f"vol lb {VOL_LB[int(g[2])]}"); bits.append(f"x{g[3]:g}")
    bits.append(f"cap {int(g[4])} lots" if g[4] < 999 else "no lot cap")
    bits.append(f"${int(g[5]):,}")
    if g[6]:
        bits.append(f"eq filter {int(g[6])}")
    return ", ".join(bits)


print("=" * 104)
print("  SIZING SWEEP -- 173,340 combinations on RSI14>70 AND lower wick>50%, long, 1R, 60m")
print("=" * 104)
print("\n  Sizing creates no edge. It reshapes one. Net dollars are therefore meaningless across")
print("  configurations -- more leverage buys more dollars for free -- so everything below is")
print("  ranked on RISK-ADJUSTED terms, and the locked block is read once after choosing.\n")

for si, am in enumerate(STOPS):
    RES = Z[f"RES{si}"]; BOOT = Z[f"BOOT{si}"]; RANK = Z[f"RANK{si}"]
    base = np.flatnonzero(grid[:, 0] == 0)          # the fixed-1-lot baseline rows
    b = base[np.argmax(RES[base, 2])]
    print(f"  STOP {am}xATR")
    print(f"    baseline, one contract:  research ${RES[b,3]:>9,.0f}   locked ${RES[b,4]:>8,.0f}"
          f"   Sharpe {RES[b,2]:>5.2f}   maxDD ${RES[b,1]:>8,.0f}   MAR {RES[b,5]:>6.2f}")
    # choose on research Sharpe, read locked once
    k = int(RANK[0])
    print(f"    best on research Sharpe: research ${RES[k,3]:>9,.0f}   locked ${RES[k,4]:>8,.0f}"
          f"   Sharpe {RES[k,2]:>5.2f}   maxDD ${RES[k,1]:>8,.0f}   MAR {RES[k,5]:>6.2f}")
    print(f"       -> {describe(grid[k])}")
    # the same choice, but made robust: rank the top 5,000 by their 5th-percentile bootstrap net
    j = int(np.argmax(BOOT[:, 0]))
    kk = int(RANK[j])
    print(f"    best on bootstrap p5:    research ${RES[kk,3]:>9,.0f}   locked ${RES[kk,4]:>8,.0f}"
          f"   Sharpe {RES[kk,2]:>5.2f}   maxDD ${RES[kk,1]:>8,.0f}   MAR {RES[kk,5]:>6.2f}")
    print(f"       -> {describe(grid[kk])}")
    print(f"       bootstrap over 400 trade orderings: p5 net ${BOOT[j,0]:,.0f}, "
          f"median ${BOOT[j,1]:,.0f}, p95 drawdown ${BOOT[j,2]:,.0f}, "
          f"ruin {100*BOOT[j,3]:.1f}%")
    print()

print("=" * 104)
print("  BY SCHEME -- median across every configuration of that scheme, at 2.5xATR")
print("=" * 104)
RES = Z["RES1"]
print(f"  {'scheme':<14}{'n cfgs':>8}{'med Sharpe':>12}{'med MAR':>10}{'med locked $':>14}"
      f"{'% locked +ve':>14}{'% ruined':>10}")
for si, sc in enumerate(SCHEMES):
    m = grid[:, 0] == si
    print(f"  {sc:<14}{int(m.sum()):>8}{np.median(RES[m,2]):>12.2f}{np.median(RES[m,5]):>10.2f}"
          f"{np.median(RES[m,4]):>14,.0f}{100*(RES[m,4]>0).mean():>13.0f}%"
          f"{100*(RES[m,6]>0).mean():>9.0f}%")

print("\n" + "=" * 104)
print("  THE SELECTION PROBLEM")
print("=" * 104)
RES = Z["RES1"]; BOOT = Z["BOOT1"]; RANK = Z["RANK1"]
ordr = np.argsort(-RES[:, 2])
for n in (1, 10, 100, 1000, 10000):
    sel = ordr[:n]
    print(f"    top {n:>6,} by research Sharpe -> median locked ${np.median(RES[sel,4]):>8,.0f}"
          f"   {100*(RES[sel,4]>0).mean():>3.0f}% positive")
print(f"    all {len(RES):>6,}                        -> median locked "
      f"${np.median(RES[:,4]):>8,.0f}   {100*(RES[:,4]>0).mean():>3.0f}% positive")
b = np.flatnonzero(grid[:, 0] == 0)
print(f"\n    fixed one contract, for comparison:  locked ${RES[b,4].max():,.0f}")
print(f"    Ruin (equity below half) somewhere in the grid: "
      f"{100*(RES[:,6]>0).mean():.1f}% of configurations")
