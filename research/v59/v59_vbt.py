"""An INDEPENDENT re-implementation of the as-briefed configuration, in vectorbt.

The verdict rests on one engine, and vectorbt is the only second opinion available here. It is
built from the bars with no shared code path -- its own EMAs, its own cross, its own stop and
target -- and compared on the TRADE COUNT and the per-trade points. A disagreement is a finding.

Configuration: EMA 16/64 cross, both sides, 2.0 x ATR(14) stop, 2R target, a hard four-hour
ceiling (16 bars at 15 minutes), all hours, no conditions, gross of costs.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import vectorbt as vbt
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.v59 import v59core as C                                   # noqa: E402
from research.v59.run_v59 import prep, metrics, aggregate               # noqa: E402
from research.v59.v59lock import gi, fi                                 # noqa: E402
from research.v38.v38feeds import load                                  # noqa: E402

STOP_N, TGT_R, HOLD = 2.0, 2.0, 16


def run(mk):
    f = load(mk)
    c = f["close"]
    ef = c.ewm(span=C.EMA_FAST, adjust=False).mean()
    es = c.ewm(span=C.EMA_SLOW, adjust=False).mean()
    up = (ef > es) & (ef.shift(1) <= es.shift(1))
    dn = (ef < es) & (ef.shift(1) >= es.shift(1))
    tr = pd.concat([f["high"] - f["low"], (f["high"] - c.shift(1)).abs(),
                    (f["low"] - c.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=14, adjust=False).mean()
    warm = C.EMA_SLOW * 3
    up.iloc[:warm] = False
    dn.iloc[:warm] = False
    sl = (STOP_N * atr / c).shift(1).bfill()
    tp = (TGT_R * STOP_N * atr / c).shift(1).bfill()
    out = {}
    for side, ent in (("long", up), ("short", dn)):
        # vectorbt 1.1.0's from_signals has no `td_stop`, so the four-hour ceiling is expressed
        # as an explicit exit HOLD bars after each entry -- whichever of stop, target or clock
        # comes first still wins, which is the same rule the engine walks.
        tex = ent.shift(HOLD).fillna(False).astype(bool)
        pf = vbt.Portfolio.from_signals(
            close=c, entries=ent if side == "long" else False,
            short_entries=ent if side == "short" else False,
            exits=tex if side == "long" else False,
            short_exits=tex if side == "short" else False,
            sl_stop=sl, tp_stop=tp, high=f["high"], low=f["low"],
            accumulate=False, freq="15min")
        t = pf.trades.records_readable
        pts = (t["Avg Exit Price"] - t["Avg Entry Price"]) * (1 if side == "long" else -1)
        out[side] = dict(n=len(t), pts=float(pts.mean()) if len(t) else np.nan,
                         win=float((pts > 0).mean()) if len(t) else np.nan)
    return out


def main():
    print("=" * 92)
    print("VECTORBT SECOND OPINION -- EMA 16/64 cross, 2N stop, 2R target, 4-hour ceiling, GROSS")
    print("=" * 92)
    g = gi(STOP_N, TGT_R, HOLD, "fixed", "all hours")
    ffi = fi("off", "off")
    for mk in ("US30L", "US100L"):
        v = run(mk)
        F, S, nd = prep(mk, cost=0.0)
        ag = aggregate(S, np.ones(F["n"], bool), nd)
        for side, sd in (("long", 0), ("short", 1)):
            mm = metrics(ag[(0, side, ffi)], nd)
            st = S[(0, sd)]
            x = st["ptsraw"][:, g]
            x = x[np.isfinite(x)]
            b = v[side]
            agree = 100 * min(mm["n"][g], b["n"]) / max(mm["n"][g], b["n"], 1)
            print(f"  {mk:<7} {side:<6} v59  n {int(mm['n'][g]):>5d}  {x.mean():>+8.2f} pts   |   "
                  f"vectorbt  n {b['n']:>5d}  {b['pts']:>+8.2f} pts  win {b['win']*100:>5.1f}%"
                  f"   | trade count {agree:.1f}% agreed")


if __name__ == "__main__":
    main()
