"""Frozen-rule signal preview (brief section 50). It never sends an order.

Reads the latest bars, applies a FROZEN rule, and reports one of NO SIGNAL / LONG SETUP
DEVELOPING / LONG SIGNAL together with the entry, stop, target and which conditions are currently
true. "Developing" means every condition but one is satisfied inside the trading window.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import data, features, discover


def preview(fz, at=None, tf=15):
    d = data.bars(tf)
    F = features.build(d)
    C = discover.conditions(F)
    ix = pd.DatetimeIndex(d["idx"])
    i = len(ix) - 1 if at is None else int(np.searchsorted(ix, pd.Timestamp(at)))
    i = min(max(i, 1), len(ix) - 1)
    mod = d["mod"][i]
    in_win = fz.win_lo <= mod < fz.win_hi
    state = {c: bool(C[c][i]) if c in C else None for c in fz.conds}
    n_true = sum(1 for v in state.values() if v)
    atr = d["atr"][i]; close = d["c"][i]
    stop_pts = fz.stop_atr * atr
    if not in_win:
        status = "NO SIGNAL (outside the trading window)"
    elif n_true == len(fz.conds):
        status = "LONG SIGNAL"
    elif n_true == len(fz.conds) - 1:
        status = "LONG SETUP DEVELOPING"
    else:
        status = "NO SIGNAL"
    lines = [f"as of {ix[i]}  ({mod//60:02d}:{mod%60:02d} New York)  close {close:.1f}  ATR {atr:.1f}",
             f"STATUS: {status}",
             f"  window {fz.win_lo//60:02d}:{fz.win_lo%60:02d}-{fz.win_hi//60:02d}:{fz.win_hi%60:02d}"
             f"  -> {'inside' if in_win else 'outside'}",
             f"  conditions {n_true}/{len(fz.conds)} true:"]
    for c, v in state.items():
        lines.append(f"    [{'x' if v else ' '}] {c}")
    if status == "LONG SIGNAL":
        entry = close
        lines += [f"  entry (next open, approx) {entry:.1f}",
                  f"  stop  {entry - stop_pts:.1f}   ({fz.stop_atr}x ATR = {stop_pts:.1f} pts)",
                  f"  target {entry + fz.rr * stop_pts:.1f}   ({fz.rr}R)",
                  f"  R:R  1:{fz.rr:g}   max hold {fz.max_hold * 15} minutes"]
    lines.append("  NO ORDER IS SENT. This is a preview only.")
    return "\n".join(lines)
