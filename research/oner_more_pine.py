"""Emit the four re-set versions as TradingView strategies and companion indicators.

Two of the four use thresholds the shared condition pool has no rung for -- a bearish engulfing
bar with a minimum body, and a clock window other than the five named ones. Those get their Pine
expressions registered here, next to the numpy definitions in `oner_union`, so the two cannot
drift. The rest come from `alpha_ladder.PINE`.

The window conditions are deliberately NOT in the generative pool. A finer clock grid handed to a
1.29-million-rule search is the free lottery the calendar ban exists to prevent; used as a
threshold inside a rule that already contains a clock window, it is a threshold.

Nothing here is compiled by TradingView, so `pine_lint` runs on every file before it is written.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "research")
import pine_export as PX
from alpha_ladder import PINE as LADDER_PINE
from oner_anom import _parts
from oner_more import select
from oner_union import FAMILIES, score

OUT = Path("pine/more1R")


def _register():
    PX.P.update(LADDER_PINE)
    for a, b in ((10, 20), (20, 50), (20, 100), (50, 100), (10, 50), (50, 200)):
        PX.P[f"EMA{a}>EMA{b}"] = f"ema{a} > ema{b}"
    for w in (30, 60, 90, 120, 150, 180):
        end = 570 + w
        PX.P[f"first {w}m"] = f"barMin >= 570 and barMin < {end}"
    for q in (0.0, 0.2, 0.3, 0.4, 0.5):
        PX.P[f"bear engulf b>={q:g}"] = (
            "close < open[1] and open > close[1] and close < open"
            + ("" if q <= 0 else f" and bodyFrac >= {q:g}"))
        PX.P[f"bull engulf b>={q:g}"] = (
            "close > open[1] and open < close[1] and close > open"
            + ("" if q <= 0 else f" and bodyFrac >= {q:g}"))
    for r in (0.0, 0.8, 1.0, 1.2, 1.5):
        PX.P[f"outside r>={r:g}"] = (
            "high > high[1] and low < low[1]"
            + ("" if r <= 0 else f" and (high - low) >= {r:g} * atrV"))


def main():
    from pine_lint import lint
    _register()
    OUT.mkdir(parents=True, exist_ok=True)
    bad = 0
    for key in FAMILIES:
        S = select(key, verbose=False)
        names, _m = _parts(FAMILIES[key], S["d"], S["p"])
        miss = [n for n in names if n not in PX.P]
        if miss:
            print(f"  {key}: no Pine expression for {miss}"); bad += 1; continue
        s = score(S["d"], S["si"], S["cut"], S["trig"], S["side"], S["am"], S["flat"], S["base"])
        m = S["si"][s["ent_bar"]] >= S["cut"]
        lp = s["pnl"][m]
        st = {
            "trades": f"{s['n']}  ({s['n_res']} research / {s['n_lok']} locked)",
            "win rate": f"{s['win']:.1f}%   base rate for this geometry {s['base']:.1f}%",
            "net": f"${s['net']:,.0f}   profit factor {s['pf']:.2f}",
            "locked block only": f"{len(lp)} trades, {100*(lp>0).mean():.1f}% win, "
                                 f"${lp.sum():,.0f}",
            "chosen on": "the research block only; the locked figures above were read once",
        }
        title = f"{key} 1R | " + " + ".join(names)
        for kind, fn in (("strategy", PX.emit_strategy), ("indicator", PX.emit_indicator)):
            src = fn(names, S["side"], S["am"], 1.0, S["flat"], tf=S["tf"], stats=st,
                     title=title + ("" if kind == "strategy" else " | signal"))
            errs = lint(src)
            path = OUT / f"{key}_{kind}.pine"
            if errs:
                bad += 1
                print(f"  {path}: {len(errs)} lint error(s)")
                for e in errs[:5]:
                    print(f"      {e}")
                continue
            path.write_text(src)
            print(f"  wrote {path}  ({len(src.splitlines())} lines, lint clean)")
    print("all clean" if not bad else f"{bad} problem(s)")


if __name__ == "__main__":
    main()
