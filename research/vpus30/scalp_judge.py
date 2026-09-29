"""The scalp grid's leaders split into blocks and scored against a risk-matched random entry.

DESCRIPTIVE. US30's later block has been read several times on this branch already, and this is a
4,320-cell search on top of that, so nothing here is a pre-registered read.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vpus30 import vpcore as V  # noqa: E402
from vpus30.scalp_grid import _walk, build, RT, RTH0, RTH1  # noqa: E402
from numba import njit  # noqa: E402

RNG = np.random.default_rng(717)


@njit(cache=True)
def _walk_at(o, h, l, c, at, mod, xhi, xlo, sig, side, sl, tp, hold, sess, flat_mod, cost):
    n = len(c); m = len(sig)
    out = np.full(m, np.nan)
    last = -1
    for q in range(m):
        i = sig[q]
        if i <= last or i + 1 >= n or at[i] <= 0 or not np.isfinite(at[i]):
            continue
        s = side[q]
        j = i + 1
        if sess == 1 and mod[j] >= flat_mod:
            continue
        ent = o[j]; risk = sl * at[i]
        stop = ent - s * risk
        targ = ent + s * tp * at[i] if tp > 0 else 0.0
        x = -1; px = 0.0
        for t in range(j, n):
            if (l[t] <= stop) if s > 0 else (h[t] >= stop):
                x = t; px = stop
                break
            if tp > 0 and (((h[t] >= targ) if s > 0 else (l[t] <= targ))):
                x = t; px = targ
                break
            if t > j and not np.isnan(xlo[t]):
                if (s > 0 and c[t] < xlo[t]) or (s < 0 and c[t] > xhi[t]):
                    x = t; px = c[t]
                    break
            if t - j >= hold:
                x = t; px = c[t]
                break
            if sess == 1 and t + 1 < n and mod[t + 1] >= flat_mod and mod[t] < flat_mod:
                x = t + 1; px = o[t + 1]
                break
        if x < 0:
            x = n - 1; px = c[n - 1]
        out[q] = 100.0 * (s * (px - ent) - cost) / ent
        last = x
    return out


CELLS = [
    ("best total   15m 55/20 1.0N 3ATR h26 RTH", 15, 55, 20, 1.0, 3.0, 26, 1),
    ("<=30min hold 15m 30/20 0.75N 3ATR h26 RTH", 15, 30, 20, 0.75, 3.0, 26, 1),
    ("no target    15m 55/20 1.0N none h26 RTH", 15, 55, 20, 1.0, 0.0, 26, 1),
    ("tight scalp  15m 15/5  0.75N 1.5ATR h8 RTH", 15, 15, 5, 0.75, 1.5, 8, 1),
]


def series(tf):
    g = build(tf)
    o, h, l, c = (g[k].to_numpy() for k in ("open", "high", "low", "close"))
    return g, o, h, l, c, g["atr"].to_numpy(), g["mod"].to_numpy().astype(np.int64)


def chan(h, l, n):
    return (pd.Series(h).rolling(n).max().shift(1).to_numpy(),
            pd.Series(l).rolling(n).min().shift(1).to_numpy())


def main():
    sess_all = np.unique(V.load().index.normalize())
    cut = pd.Timestamp(sess_all[int(0.75 * len(sess_all))])
    print(f"split {str(cut)[:10]}   (last 25% of sessions)\n")
    cache = {tf: series(tf) for tf in {c[1] for c in CELLS}}
    print(f"{'cell':<44}{'blk':<10}{'n':>6}{'tot%':>9}{'mu':>9}{'PF':>7}"
          f"{'hold':>7}{'ctl':>9}{'p':>7}")
    for nm, tf, en, ex, sl, tp, hd, se in CELLS:
        g, o, h, l, c, at, mod = cache[tf]
        eh, el = chan(h, l, en)
        xh, xl = chan(h, l, ex)
        r, sd, hl, cf, eb = _walk(o, h, l, c, at, mod, eh, el, xh, xl, sl, tp, hd, se, RTH1, RT)
        ts = g.index[eb]
        elig = np.flatnonzero((mod >= RTH0) & (mod < RTH1) & np.isfinite(at) & (at > 0)) if se == 1 \
            else np.flatnonzero(np.isfinite(at) & (at > 0))
        elig = elig[(elig > 60) & (elig < len(c) - 60)]
        for bl, sel, gm in (("research", ts < cut, g.index < cut), ("HOLDOUT", ts >= cut, g.index >= cut)):
            rr = r[sel]
            if len(rr) < 40:
                continue
            k = int(sel.sum())
            e = elig[np.isin(elig, np.flatnonzero(gm))]
            ctl = np.empty(300)
            for d in range(300):
                pick = np.sort(RNG.choice(e, size=min(k, len(e)), replace=False))
                sdr = np.where(RNG.random(len(pick)) < float((sd[sel] > 0).mean()), 1, -1)
                q = _walk_at(o, h, l, c, at, mod, xh, xl, pick.astype(np.int64),
                             sdr.astype(np.int64), sl, tp, hd, se, RTH1, RT)
                ctl[d] = np.nansum(q)
            tot = float(rr.sum())
            print(f"{nm:<44}{bl:<10}{len(rr):>6}{tot:>9.2f}{rr.mean():>9.4f}"
                  f"{rr[rr>0].sum()/max(-rr[rr<0].sum(),1e-12):>7.3f}"
                  f"{np.median(hl[sel])*tf:>7.0f}{np.median(ctl):>9.2f}"
                  f"{float(np.mean(ctl >= tot)):>7.3f}")


if __name__ == "__main__":
    main()
