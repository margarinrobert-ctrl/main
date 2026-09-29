"""The shipped Pine's OWN order model, in Python, diffed against the engine.

Two declared differences, both of which the script cannot avoid:
  1. the channel exit fills at the NEXT bar's open, not at the breaking bar's close
  2. the stop is a FILL-RELATIVE bracket sized at the SIGNAL bar (slN x ATR), armed with the entry,
     so the fill bar is protected -- the engine anchors to the entry open, which is the same
     distance, so this one is only a difference in when the order exists.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vpus30 import vpcore as V, vpdon as D  # noqa: E402


@njit(cache=True)
def _script(o, h, l, c, at, is_rth, ent_n, ex_n, sl, side_want, cost):
    n = len(c)
    eb = np.full(n, -1, np.int64); xb = np.full(n, -1, np.int64)
    ep = np.zeros(n); xp = np.zeros(n); sd = np.zeros(n, np.int64)
    cnt = 0; last = -1
    for i in range(max(ent_n, ex_n) + 2, n - 2):
        if is_rth[i] == 0 or i <= last or at[i] <= 0 or not np.isfinite(at[i]):
            continue
        hh = h[i - ent_n]; ll = l[i - ent_n]
        for q in range(i - ent_n + 1, i):
            if h[q] > hh:
                hh = h[q]
            if l[q] < ll:
                ll = l[q]
        s = 1 if c[i] > hh else (-1 if c[i] < ll else 0)
        if s == 0 or (side_want != 0 and s != side_want):
            continue
        j = i + 1
        ent = o[j]
        risk = sl * at[i]                      # fill-relative bracket, sized at the SIGNAL bar
        stop = ent - s * risk
        x = -1; px = 0.0
        for t in range(j, n - 1):
            hs = (l[t] <= stop) if s > 0 else (h[t] >= stop)
            if hs:
                x = t; px = stop
                break
            if t > j:
                eh = h[t - ex_n]; el = l[t - ex_n]
                for q in range(t - ex_n + 1, t):
                    if h[q] > eh:
                        eh = h[q]
                    if l[q] < el:
                        el = l[q]
                if (s > 0 and c[t] < el) or (s < 0 and c[t] > eh):
                    x = t + 1; px = o[t + 1]   # the script fills at the NEXT bar's open
                    break
        if x < 0:
            x = n - 1; px = c[n - 1]
        eb[cnt] = j; xb[cnt] = x; ep[cnt] = ent; xp[cnt] = px; sd[cnt] = s
        cnt += 1
        last = x
    return eb[:cnt], xb[:cnt], ep[:cnt], xp[:cnt], sd[:cnt]


def main():
    f = V.load(); g = D.frame(f)
    sess = np.unique(g.index.normalize())
    cut = pd.Timestamp(sess[int(0.75 * len(sess))])
    eb, xb, ep, xp, sd = _script(
        g["open"].to_numpy(), g["high"].to_numpy(), g["low"].to_numpy(), g["close"].to_numpy(),
        g["atr"].to_numpy(), g["is_rth"].to_numpy(), 55, 20, 3.0, 0, D.RT_POINTS)
    s = pd.DataFrame(dict(e_bar=eb, x_bar=xb, ent=ep, out=xp, side=sd))
    s["pct"] = 100.0 * (s.side * (s.out - s.ent) - D.RT_POINTS) / s.ent
    s["ts"] = g.index[s.e_bar.to_numpy()]
    e = D.walk(g, ent_n=55, ex_n=20, sl=3.0, side=0)

    print(f"engine {len(e)} trades   script {len(s)}   ratio {len(s)/len(e):.3f}")
    m = e.merge(s, on="e_bar", suffixes=("_e", "_s"))
    print(f"shared entries {len(m)}   same exit bar "
          f"{(m.x_bar_e == m.x_bar_s).mean():.4f}   same side {(m.side_e == m.side_s).mean():.4f}")
    print(f"per-trade correlation {m.pct_e.corr(m.pct_s):.4f}")
    for nm, sel_e, sel_s in (("research", pd.DatetimeIndex(e.ts) < cut, pd.DatetimeIndex(s.ts) < cut),
                             ("HOLDOUT", pd.DatetimeIndex(e.ts) >= cut, pd.DatetimeIndex(s.ts) >= cut)):
        a, b = e[sel_e].pct, s[sel_s].pct
        gap = (b.sum() - a.sum()) / abs(a.sum()) * 100
        print(f"  {nm:<9} engine n {len(a):>5} tot {a.sum():+8.3f}%   "
              f"script n {len(b):>5} tot {b.sum():+8.3f}%   gap {gap:+.1f}%")


if __name__ == "__main__":
    main()
