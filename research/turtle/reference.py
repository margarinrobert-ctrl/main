"""A slow, literal transliteration of the supplied JS, used only to verify `core.run`.

This deliberately mirrors the original's control flow line for line -- including its quirks (the
skip flag cleared on use, the pyramid branch sitting in the same else-if chain as the exits, so a
bar cannot both exit and add) -- so that any divergence in the fast version shows up as a trade
difference rather than as a plausible-looking number.
"""
from __future__ import annotations

import numpy as np

from .core import _atr_wilder, _rolling_max, _rolling_min


def run_reference(d, entry1=20, entry2=55, exit1=10, exit2=20, atr_len=20, atr_mult=2.0,
                  pyramid_step=0.5, max_units=4, skip_after_winner=True,
                  allow_s1=True, allow_s2=True, cost_pts=0.0, slip_pts=0.0):
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    hi1 = _rolling_max(h, entry1); hi2 = _rolling_max(h, entry2)
    lo1 = _rolling_min(l, exit1); lo2 = _rolling_min(l, exit2)
    atr = _atr_wilder(h, l, c, atr_len)
    n = len(c)
    st = dict(inTrade=False, system=0, entry=0.0, stop=0.0, units=0, nextAdd=0.0,
              lastWinner=False, fills=[], bar_in=0, hi=0.0, lo=0.0, risk=0.0)
    trades = []
    start = max(entry1, entry2, exit1, exit2, atr_len) + 1
    for i in range(start, n):
        exitTriggered = False
        if st["inTrade"]:
            st["hi"] = max(st["hi"], h[i]); st["lo"] = min(st["lo"], l[i])
            why = 0; px = 0.0
            if l[i] <= st["stop"]:
                why = 1; px = min(o[i], st["stop"]) - slip_pts
            elif st["system"] == 1 and l[i] <= lo1[i - 1]:
                why = 2; px = min(o[i], lo1[i - 1]) - slip_pts
            elif st["system"] == 2 and l[i] <= lo2[i - 1]:
                why = 3; px = min(o[i], lo2[i - 1]) - slip_pts
            if why:
                pnl = sum((px - f) - cost_pts for f in st["fills"])
                trades.append(dict(pnl=pnl, risk=st["risk"], units=st["units"],
                                   system=st["system"], why=why,
                                   bar_in=st["bar_in"], bar_out=i,
                                   mfe=st["hi"] - st["entry"], mae=st["entry"] - st["lo"]))
                st["lastWinner"] = c[i] > st["entry"]
                st.update(inTrade=False, system=0, units=0, fills=[])
                exitTriggered = True
            elif pyramid_step > 0 and st["units"] < max_units and h[i] >= st["nextAdd"]:
                if i + 1 < n:
                    fp = o[i + 1]
                    st["fills"].append(fp + slip_pts)
                    st["units"] += 1
                    st["stop"] = fp - atr_mult * atr[i]
                    st["nextAdd"] = fp + pyramid_step * atr[i]
        if not st["inTrade"] and not exitTriggered:
            if allow_s2 and h[i] > hi2[i - 1] and i + 1 < n:
                fp = o[i + 1]
                st.update(inTrade=True, system=2, entry=fp, units=1,
                          fills=[fp + slip_pts], risk=atr_mult * atr[i],
                          stop=fp - atr_mult * atr[i],
                          nextAdd=fp + pyramid_step * atr[i],
                          bar_in=i + 1, hi=fp, lo=fp)
            elif allow_s1 and h[i] > hi1[i - 1] and i + 1 < n:
                if skip_after_winner and st["lastWinner"]:
                    st["lastWinner"] = False
                else:
                    fp = o[i + 1]
                    st.update(inTrade=True, system=1, entry=fp, units=1,
                              fills=[fp + slip_pts], risk=atr_mult * atr[i],
                              stop=fp - atr_mult * atr[i],
                              nextAdd=fp + pyramid_step * atr[i],
                              bar_in=i + 1, hi=fp, lo=fp)
    return trades


def assert_matches(d, tol=1e-9, **kw):
    from .core import backtest
    ref = run_reference(d, **kw)
    fast = backtest(d, **kw)
    assert len(ref) == len(fast["pnl"]), f"trade count: reference {len(ref)} vs fast {len(fast['pnl'])}"
    for f, key in ((fast["pnl"], "pnl"), (fast["risk"], "risk")):
        a = np.array([t[key] for t in ref]); b = np.asarray(f)
        md = float(np.max(np.abs(a - b))) if len(a) else 0.0
        assert md < tol, f"{key} differs by {md}"
    for key in ("units", "system", "why", "bar_in", "bar_out"):
        a = np.array([t[key] for t in ref], np.int64); b = np.asarray(fast[key])
        assert (a == b).all(), f"{key} differs"
    return len(ref)
