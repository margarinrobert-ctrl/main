"""The arithmetic that closes the argument: what the scalp geometry costs before any indicator."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sr_core as S  # noqa: E402


def main():
    print(__doc__)
    print("=" * 116)
    print("6. THE COST FLOOR THE GEOMETRY IMPLIES -- cost as a FRACTION OF RISK, which is the only")
    print("   way to compare it across instruments, and the win rate it forces")
    print("=" * 116)
    print(f"  {'feed':12s} {'median ATR':>11s} {'round turn':>11s} | "
          f"{'0.75N stop':>11s} {'cost/risk':>10s} {'BE at 2R':>9s} | "
          f"{'2.5N stop':>10s} {'cost/risk':>10s} {'BE at 2R':>9s}")
    for market, tf in S.FEEDS:
        D = S.build(market, tf)
        a = D["atr"][np.isfinite(D["atr"])]
        med = float(np.median(a))
        rt = 2 * (D["cost"] + D["slip"])
        row = f"  {market + ' ' + str(tf) + 'm':12s} {med:11.2f} {rt:11.3f} |"
        for mult in (0.75, 2.5):
            stop = mult * med
            frac = rt / stop
            # a 2R target: break-even win rate is (stop + cost) / (target + stop)
            be = (stop + rt) / (2 * stop + stop)
            row += f" {stop:11.2f} {100*frac:9.1f}% {100*be:8.1f}% |"
        print(row)
    print("\n  `BE at 2R` is the win rate a 2:1 payoff needs once the round turn is charged. The")
    print("  driftless bound with no cost is 33.3%; every point above that is the cost.")

    print("\n" + "=" * 116)
    print("7. IS THE SCALP'S LOSS A COST PROBLEM? -- the same trades with the cost set to zero")
    print("=" * 116)
    print(f"  {'trigger':32s} {'geom':6s} {'cost x1':>9s} {'cost x0':>9s} {'the cost':>9s} "
          f"{'win':>6s} {'needs':>6s}")
    for tname in ("Donchian 20 breakout", "EMA 13/34/89 stack, <=30 bars old"):
        for g in ("scalp", "swing"):
            stop, tp, hold = S.GEOM[g]
            tot = {0.0: [0.0, 0], 1.0: [0.0, 0]}
            wins = 0
            for market, tf in S.FEEDS:
                D = S.build(market, tf)
                trig = S.triggers(D)[tname].copy()
                trig[:300] = False
                trig[-(hold + 6):] = False
                trig &= np.isfinite(D["atr"]) & (D["atr"] > 0)
                rows = np.flatnonzero(trig)
                epx = D["o"][np.minimum(rows + 1, D["n"] - 1)]
                blk = np.full(D["n"], -1, np.int64)
                for i, nm in enumerate(D["blocks"]):
                    blk[np.asarray(D["blocks"][nm], bool)] = i
                for cm in (0.0, 1.0):
                    pts, xb = S.walk(D["o"], D["h"], D["l"], D["c"], D["atr"],
                                     rows.astype(np.int64), stop, tp, hold,
                                     D["cost"] * cm, D["slip"] * cm, D["n"])
                    tr = S.lock(rows, np.arange(len(rows)), pts, xb, epx, blk)
                    p = np.array([x[1] for x in tr if x[0] >= 0])
                    tot[cm][0] += p.sum()
                    tot[cm][1] += len(p)
                    if cm == 1.0:
                        wins += int((p > 0).sum())
            net = tot[1.0][0] / max(tot[1.0][1], 1)
            gross = tot[0.0][0] / max(tot[0.0][1], 1)
            wr = wins / max(tot[1.0][1], 1)
            need = 1.0 / (1.0 + (tp / stop)) if tp > 0 else np.nan
            print(f"  {tname:32s} {g:6s} {net:+9.4f} {gross:+9.4f} {gross-net:+9.4f} "
                  f"{100*wr:5.1f}% {(f'{100*need:5.1f}%' if np.isfinite(need) else '   n/a'):>6s}")
    print("\n  If the zero-cost column is also negative the geometry is wrong, not the execution.")


if __name__ == "__main__":
    main()
