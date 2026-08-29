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


def _pretty(name):
    """Grid labels are terse on purpose; the chart legend is not the place for them."""
    if name.startswith("outside r>="):
        r = float(name.split(">=")[1])
        return "outside bar" if r <= 0 else f"outside bar, range>={r:g}xATR"
    if name.startswith("first ") and name.endswith("m"):
        end = 570 + int(name[6:-1])
        return f"09:30-{end//60:02d}:{end%60:02d} New York"
    if "engulf b>=" in name:
        q = float(name.split(">=")[1])
        side = "bearish" if name.startswith("bear") else "bullish"
        return f"{side} engulfing" if q <= 0 else f"{side} engulfing, body>={q*100:.0f}%"
    return name


def _register():
    PX.P.update(LADDER_PINE)
    for a, b in ((10, 20), (20, 50), (20, 100), (50, 100), (10, 50), (50, 200)):
        PX.P[f"EMA{a}>EMA{b}"] = f"ema{a} > ema{b}"
        PX.P[f"EMA{a}<EMA{b}"] = f"ema{a} < ema{b}"
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


def emit(names, side, am, flat, tf, st, title, stem, outdir):
    """One rule -> a strategy and an indicator, both linted before anything is written."""
    from pine_lint import lint
    show = [_pretty(n) for n in names]
    for a, b in zip(names, show):
        PX.P[b] = PX.P[a]
    bad = 0
    outdir.mkdir(parents=True, exist_ok=True)
    for kind, fn in (("strategy", PX.emit_strategy), ("indicator", PX.emit_indicator)):
        src = fn(show, side, am, 1.0, flat, tf=tf, stats=st,
                 title=title + ("" if kind == "strategy" else " | signal"))
        errs = lint(src)
        path = outdir / f"{stem}_{kind}.pine"
        if errs:
            bad += 1
            print(f"  {path}: {len(errs)} lint error(s)")
            for e in errs[:5]:
                print(f"      {e}")
            continue
        path.write_text(src)
        print(f"  wrote {path}  ({len(src.splitlines())} lines, lint clean)")
    return bad


def mega2(path="results/oner/phase5_mega2.npy", outdir=Path("pine/mega2_1R")):
    """The four the 139,740,876-combination sweep returned."""
    from test_suite import build, use_pool, _daily, _sharpe
    _register()
    use_pool("ladder")
    rows = list(np.load(path, allow_pickle=True))
    bad = 0
    for i, r in enumerate(rows):
        names = list(r["rule"])
        miss = [n for n in names if n not in PX.P]
        if miss:
            print(f"  M{i+1}: no Pine expression for {miss}"); bad += 1; continue
        s = build(names, side=r["side"], atr_mult=r["am"], tp_r=1.0, flat_min=r["flat"],
                  tf=r["tf"])
        m = s.ent_sess >= s.cut
        w = s.pnl > 0
        st = {
            "trades": f"{len(s.pnl)}  ({int((~m).sum())} research / {int(m.sum())} locked)",
            "win rate": f"{100*w.mean():.1f}%   base rate for this geometry {r['base']:.1f}%",
            "net": f"${s.pnl.sum():,.0f}   profit factor "
                   f"{s.pnl[w].sum()/max(-s.pnl[~w].sum(),1e-9):.2f}",
            "locked block only": f"{int(m.sum())} trades, {100*(s.pnl[m]>0).mean():.1f}% win, "
                                 f"${s.pnl[m].sum():,.0f}",
            "chosen on": "the research block only; the locked figures above were read once",
        }
        bad += emit(names, r["side"], r["am"], r["flat"], r["tf"], st,
                    f"M{i+1} 1R | " + " + ".join(_pretty(n) for n in names),
                    f"M{i+1}", outdir)
    print("all clean" if not bad else f"{bad} problem(s)")


def mirror(outdir=Path("pine/more1R")):
    """B from `v2_long` -- V2's mechanism mirrored onto the long side, which is not the same
    thing as ticking "Allow longs" on V2 and is the only one of three long variants that works."""
    import numpy as _np
    from v2_long import B_CONDS, B_GEO, b_strategy
    _register()
    s = b_strategy()
    m = s.ent_sess >= s.cut
    w = s.pnl > 0
    st = {
        "trades": f"{len(s.pnl)}  ({int((~m).sum())} research / {int(m.sum())} locked)",
        "win rate": f"{100*w.mean():.1f}%   base rate for a LONG at this geometry 48.9%",
        "net": f"${s.pnl.sum():,.0f}   profit factor "
               f"{s.pnl[w].sum()/max(-s.pnl[~w].sum(),1e-9):.2f}",
        "locked block only": f"{int(m.sum())} trades, {100*(s.pnl[m]>0).mean():.1f}% win, "
                             f"${s.pnl[m].sum():,.0f}",
        "chosen on": "the research block only; the locked figures above were read once",
        "not a flipped V2": "V2's own trigger taken long loses $7,717. See STUDY_V2_LONG.md",
    }
    bad = emit(B_CONDS, 1, B_GEO["am"], B_GEO["flat"], 30, st,
               "V2L 1R | " + " + ".join(_pretty(n) for n in B_CONDS), "V2L", outdir)
    print("all clean" if not bad else f"{bad} problem(s)")


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
        show = [_pretty(n) for n in names]
        for a, b in zip(names, show):
            PX.P[b] = PX.P[a]
        names = show
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
