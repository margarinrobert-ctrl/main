"""Emit the SAM scalps as TradingView strategies.

Only the BAR-RETURN estimator can be shipped. The intrabar estimator needs the 1-minute bars
inside each chart bar, and `request.security_lower_tf` is capped at roughly 100,000 intrabars --
three years of 15-minute bars asks for over a million. A rule using it is measurable here and not
runnable there, and saying so is more useful than shipping a script that silently returns na on
most of the chart.

The semivariance block is generated for exactly the windows a rule references, so a script that
uses SAZb2 and SARb16 carries two windows and not twelve.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, "research")
import pine_export as PX
from alpha_ladder import PINE as LADDER_PINE
from sam_pool import ZLB

OUT = Path("pine/samScalp")
_RE = re.compile(r"^(SAM|SAR|SAZ)([ib])(\d+)")


def windows_in(rule):
    ws = set()
    for c in rule:
        m = _RE.match(c)
        if m:
            ws.add(int(m.group(3)))
    return sorted(ws)


def prims(rule):
    """The semivariance prelude for exactly the windows this rule uses."""
    ws = windows_in(rule)
    if not ws:
        return ""
    out = ["// ---- realized semivariance from bar returns ------------------------------------",
           "// RS+ is the variance contributed by up bars, RS- by down bars. The paper builds",
           "// these from 30-minute returns inside a day; this is the same estimator with the",
           "// bar as the unit, which is what makes it computable without lower-timeframe data.",
           "logR  = math.log(close / close[1])",
           "rsPos = logR > 0 ? logR * logR : 0.0",
           "rsNeg = logR < 0 ? logR * logR : 0.0"]
    for w in ws:
        out += [f"sP{w}  = math.sum(rsPos, {w})",
                f"sN{w}  = math.sum(rsNeg, {w})",
                f"sam{w} = sP{w} - sN{w}",
                f"sar{w} = (sP{w} + sN{w}) > 0 ? sam{w} / (sP{w} + sN{w}) : na",
                f"sd{w}  = ta.stdev(sam{w}, {ZLB})",
                f"saz{w} = sd{w} > 0 ? (sam{w} - ta.sma(sam{w}, {ZLB})) / sd{w} : na"]
    return "\n".join(out) + "\n"


def expr(cond):
    """Pine for one SAM condition. Returns None for the intrabar estimator, which cannot ship."""
    m = _RE.match(cond)
    if not m:
        return PX.P.get(cond)
    fam, est, w = m.group(1), m.group(2), int(m.group(3))
    if est == "i":
        return None
    v = {"SAM": f"sam{w}", "SAR": f"sar{w}", "SAZ": f"saz{w}"}[fam]
    rest = cond[m.end():].strip()
    if rest.startswith("x-below"):
        t = rest.split()[1]
        return f"{v} < {t} and {v}[1] >= {t}"
    if rest.startswith("x-above"):
        t = rest.split()[1]
        return f"{v} > {t} and {v}[1] <= {t}"
    if rest.startswith("<"):
        return f"{v} < {rest[1:]}"
    if rest.startswith(">"):
        return f"{v} > {rest[1:]}"
    return None


def emit(name, rule, side, am, flat, tf, stats, outdir=OUT):
    from pine_lint import lint
    PX.P.update(LADDER_PINE)
    exprs = {c: expr(c) for c in rule}
    missing = [c for c, e in exprs.items() if e is None]
    if missing:
        print(f"  {name}: cannot ship -- {missing} need the intrabar estimator")
        return 1
    for c, e in exprs.items():
        PX.P[c] = e
    outdir.mkdir(parents=True, exist_ok=True)
    bad = 0
    for kind, fn in (("strategy", PX.emit_strategy), ("indicator", PX.emit_indicator)):
        src = fn(rule, side, am, 1.0, flat, tf=tf, stats=stats,
                 title=f"{name} | " + " + ".join(rule) + ("" if kind == "strategy" else " | signal"))
        # splice the semivariance block in after the generated prelude
        src = src.replace("\n// ---- the rule ", "\n" + prims(rule) + "\n// ---- the rule ", 1)
        errs = lint(src)
        p = outdir / f"{name}_{kind}.pine"
        if errs:
            bad += 1
            print(f"  {p}: {len(errs)} lint error(s)"); [print("     ", e) for e in errs[:4]]
            continue
        p.write_text(src)
        print(f"  wrote {p}  ({len(src.splitlines())} lines, lint clean)")
    return bad


if __name__ == "__main__":
    import numpy as np
    from oner_union import _cut, _sim, base_rate
    from sam_phases import rule_trig
    CAND = [
        ("SF1", ["SAZb2 x-below 1.5", "SARb16<-0.3"], 30, -1, 1.0, 960),
        ("SF2", ["SAZb16 x-below 1.5", "outside bar"], 15, -1, 2.0, 960),
        ("SF3", ["SAZi8 x-below -1", "SAZb6>0.5"], 15, 1, 2.5, 960),
    ]
    bad = 0
    for nm, rule, tf, side, am, flat in CAND:
        d, trig = rule_trig(tf, rule)
        si, cut, _ = _cut(d)
        pnl, eb, *_ = _sim(d, trig, side, am, flat)
        m = si[eb] >= cut; w = pnl > 0
        st = {
            "trades": f"{len(pnl)}  ({int((~m).sum())} research / {int(m.sum())} locked)",
            "win rate": f"{100*w.mean():.1f}%   base rate for this side and geometry "
                        f"{base_rate(d, side, am, flat):.1f}%",
            "net": f"${pnl.sum():,.0f}   profit factor "
                   f"{pnl[w].sum()/max(-pnl[~w].sum(),1e-9):.2f}",
            "locked block only": f"{int(m.sum())} trades, {100*(pnl[m]>0).mean():.1f}% win, "
                                 f"${pnl[m].sum():,.0f}",
            "chosen on": "the research block only; the locked figures were read once",
            "searched": "47,615,040 combinations at this timeframe; see STUDY_SAM_SCALP.md",
        }
        bad += emit(nm, rule, side, am, flat, tf, st)
    print("all clean" if not bad else f"{bad} problem(s) -- expected for the intrabar rule")
