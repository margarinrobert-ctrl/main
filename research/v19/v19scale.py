"""The diagnosis said COST, not edge. So test the one axis that changes cost-in-R: bar size.

WHAT SECTION B ESTABLISHED. At zero friction the frozen rule is positive on ALL FOUR markets
(+0.037 US30, +0.113 US30L, +0.103 XAU, +0.231 US100). With friction three of the four are negative.
The round turn is 8.1%, 11.2% and 9.8% of the stop on the three that fail against 3.1% on the one
that does not. The rule does not lack an edge; it lacks an edge LARGE ENOUGH FOR ITS OWN COST.

THE MECHANISM, AND WHY IT IS NOT FREE ARITHMETIC. A round turn is a fixed number of points, so
cost-in-R is cost_points / (stop_mult x ATR). Going to a bigger bar raises ATR and shrinks cost-in-R
proportionally -- but it shrinks the gross edge in R by the same factor, so on arithmetic alone
nothing is gained. Anything that DOES change is a real property of the market: fewer, longer trades
resolve differently from many short ones. That is the hypothesis, and it is falsifiable.

ONE AXIS, THREE MARKETS, THREE TIMEFRAMES. Nine cells, pre-declared, no other tuning.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v18")
sys.path.insert(0, "research/v19")
import indicators as I       # noqa: E402
import costs as CO           # noqa: E402
import v16core as C          # noqa: E402
import v18multi as V18       # noqa: E402
import v19frozen as F        # noqa: E402
import v19destroy as D       # noqa: E402


def ctx_tf(name, tf_min, spec=F.FROZEN):
    """The same context, on bars resampled from the 15-minute file."""
    df = V18.bars(name)
    if tf_min != 15:
        df = df.resample(f"{tf_min}min").agg({"open": "first", "high": "max", "low": "min",
                                              "close": "last", "volume": "sum"}).dropna()
    o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    ix = df.index
    mod = (ix.hour * 60 + ix.minute).to_numpy(np.int64)
    inst = V18.INSTR[name]
    base = CO.model("MNQ" if inst["pv"] <= 2.0 else "MGC", "discount")
    cost = base.__class__(**{**base.__dict__, "symbol": name, "pv": inst["pv"],
                             "tick": inst["tick"], "spread_ticks": inst["spread"]})
    f_taker, f_stop = CO.friction_arrays(cost, h, l, c, mod)
    P = dict(o=o, h=h, l=l, c=c, mod=mod, name=name,
             sess=np.asarray(ix.normalize().values).astype("datetime64[ns]").astype(np.int64),
             ts=ix.to_numpy().astype("datetime64[ns]"),
             atr=I.ema(I.true_range(h, l, c), spec["atr_len"]),
             ent_hi=I.shift(I.rmax(h, spec["entry_n"]), 1),
             ent_lo=I.shift(I.rmin(l, spec["entry_n"]), 1),
             ex_lo=I.shift(I.rmin(l, spec["exit_n"]), 1),
             ex_hi=I.shift(I.rmax(h, spec["exit_n"]), 1),
             adx=I.adx_di(h, l, c, 14)[0],
             fee2=2.0 * cost.fee_points(), f_taker=f_taker, f_stop=f_stop, cost=cost)
    P["b"] = dict(v=df["volume"].to_numpy(float), ts=P["ts"].astype(np.int64))
    P["shi"] = F.session_high(mod, h, spec["rth"])
    return P


if __name__ == "__main__":
    print("=" * 120)
    print("DOES A BIGGER BAR RESCUE IT? -- the same frozen rule at 15, 30 and 60 minutes")
    print("=" * 120)
    print("   Cost-in-R falls with bar size by arithmetic; so does gross edge in R. Anything that")
    print("   moves NET is a property of the market, not of the units.\n")
    print(f"   {'market':<8}{'tf':>5}{'n':>7}{'cost/stop':>11}{'EV gross':>11}{'EV net':>10}"
          f"{'PF':>8}{'net R':>9}{'maxDD':>8}{'MAR':>7}{'Sharpe':>8}{'Sortino':>9}{'ctl p':>8}")
    keep = {}
    for k in ("US30", "US30L", "XAU", "US100"):
        for tf in (15, 30, 60):
            P = ctx_tf(k, tf)
            full = np.ones(len(P["c"]), bool)
            O, i = F.run(P)
            Og, ig = F.run(P, cost_mult=0.0)
            m = F.metrics(P, O, i, full)
            mg = F.metrics(P, Og, ig, full)
            rt = float(P["fee2"] + np.nanmedian(P["f_taker"]) + np.nanmedian(P["f_stop"]))
            pct = 100 * rt / (F.FROZEN["stop"] * float(np.nanmedian(P["atr"])))
            ctl, p = D.control(P, full, O, i, F.FROZEN["stop"], draws=800)
            keep[(k, tf)] = (P, O, i, m, p)
            print(f"   {k:<8}{tf:>4}m{m['n']:>7}{pct:>10.1f}%{mg['ev']:>+11.4f}{m['ev']:>+10.4f}"
                  f"{m['pf']:>8.3f}{m['net']:>+9.1f}{m['dd']:>8.1f}{m['mar']:>7.2f}"
                  f"{m['sharpe']:>8.2f}{m['sortino']:>9.2f}{p:>8.3f}")
        print()
    import pickle
    with open("results/v19/v19scale.pkl", "wb") as fh:
        pickle.dump({k: (v[3], v[4]) for k, v in keep.items()}, fh)
