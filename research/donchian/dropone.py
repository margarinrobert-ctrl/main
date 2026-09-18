"""Which of the four ingredients does anything? Each filter against a SELECTIVITY-MATCHED control.

THE TEST THAT MATTERS. Removing a filter changes the trade count, so comparing total dollars fails
every restrictive condition and comparing per-trade edge passes every one. The question is instead:
does this filter beat a RANDOM filter that removes the same PROPORTION of the breakouts? Anything
that does not is decoration on the breakout, whatever it does to the headline number.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/donchian")
import fastbars, indicators as I, dcs, sweep  # noqa: E402


def parts(d, dc=20, ema_n=50, adx_n=14, chop_n=14, adx_min=20.0, chop_max=40.0):
    """The raw breakout, and each filter as a separate boolean, so they can be removed one at a time."""
    h, l, c = d["h"], d["l"], d["c"]
    up, dn = dcs.bands(h, l, dc)
    xup = (c > up) & (I.shift(c, 1) <= I.shift(up, 1))
    xdn = (c < dn) & (I.shift(c, 1) >= I.shift(dn, 1))
    e = I.ema(c, ema_n)
    a = I.adx_di(h, l, c, adx_n)[0]
    ch = dcs.chop(h, l, c, chop_n)
    fin = np.isfinite(up) & np.isfinite(dn) & np.isfinite(e) & np.isfinite(a) & np.isfinite(ch)
    return dict(xup=np.nan_to_num(xup, nan=0).astype(bool) & fin,
                xdn=np.nan_to_num(xdn, nan=0).astype(bool) & fin,
                ema_l=c > e, ema_s=c < e,
                adx=np.nan_to_num(a, nan=-1) > adx_min,
                chop=np.nan_to_num(ch, nan=1e9) < chop_max)


def _mean_R(d, atr, sl, ss, mult, cost):
    T = sweep.exit_tensor(d, atr, mult, cost)
    r = np.r_[T[1][sl], T[-1][ss]]
    r = r[np.isfinite(r)]
    return (float(r.mean()) if len(r) else np.nan), len(r)


def selectivity_control(d, atr, base_l, base_s, keep, mult, draws=2000, seed=11, cost=None):
    """Random filters of the SAME selectivity, drawn from the breakout population itself."""
    cost = sweep.RT if cost is None else cost
    rng = np.random.default_rng(seed)
    T = sweep.exit_tensor(d, atr, mult, cost)
    pool = np.r_[T[1][base_l], T[-1][base_s]]
    pool = pool[np.isfinite(pool)]
    k = int(round(keep * len(pool)))
    if k < 10 or k >= len(pool):
        return None
    idx = np.argsort(rng.random((draws, len(pool))), axis=1)[:, :k]
    return pool[idx].mean(axis=1)


def table(tf=60, dc=20, ema_n=50, adx_min=20.0, chop_max=40.0, mult=3.0, block="research",
          draws=2000, verbose=True):
    d, si, cut = sweep.blocks(tf)
    atr = dcs.wilder_atr(d["h"], d["l"], d["c"], 14)
    m = (si < cut) if block == "research" else (si >= cut)
    P = parts(d, dc, ema_n, adx_min=adx_min, chop_max=chop_max)
    bl, bs = P["xup"] & m, P["xdn"] & m
    base, nb = _mean_R(d, atr, bl, bs, mult, sweep.RT)
    rows = [dict(gate="raw breakout, no filters", n=nb, R=base, keep=1.0, ctl=np.nan, p=np.nan)]
    combos = {
        "EMA only": (P["ema_l"], P["ema_s"]),
        "ADX only": (P["adx"], P["adx"]),
        "CHOP only": (P["chop"], P["chop"]),
        "EMA + ADX": (P["ema_l"] & P["adx"], P["ema_s"] & P["adx"]),
        "EMA + CHOP": (P["ema_l"] & P["chop"], P["ema_s"] & P["chop"]),
        "ADX + CHOP": (P["adx"] & P["chop"], P["adx"] & P["chop"]),
        "all three (published)": (P["ema_l"] & P["adx"] & P["chop"],
                                  P["ema_s"] & P["adx"] & P["chop"]),
        "drop EMA": (P["adx"] & P["chop"], P["adx"] & P["chop"]),
        "drop ADX": (P["ema_l"] & P["chop"], P["ema_s"] & P["chop"]),
        "drop CHOP": (P["ema_l"] & P["adx"], P["ema_s"] & P["adx"]),
    }
    for name, (fl, fs) in combos.items():
        sl, ss = bl & fl, bs & fs
        r, n = _mean_R(d, atr, sl, ss, mult, sweep.RT)
        keep = n / nb if nb else 0.0
        c = selectivity_control(d, atr, bl, bs, keep, mult, draws=draws)
        p = float((c >= r).mean()) if c is not None else np.nan
        rows.append(dict(gate=name, n=n, R=r, keep=keep,
                         ctl=float(c.mean()) if c is not None else np.nan, p=p))
    T = pd.DataFrame(rows)
    if verbose:
        print(f"\n  {tf}m {block}: dc {dc}, EMA {ema_n}, ADX>{adx_min:g}, CHOP<{chop_max:g}, "
              f"trail {mult}xATR")
        print(f"  {'gate':<26}{'n':>7}{'keep':>8}{'mean R':>10}{'sel-ctl':>10}{'p':>8}")
        for r in T.itertuples():
            print(f"  {r.gate:<26}{r.n:>7,}{100*r.keep:>7.1f}%{r.R:>+10.4f}"
                  f"{r.ctl:>+10.4f}{r.p:>8.3f}" if np.isfinite(r.p) else
                  f"  {r.gate:<26}{r.n:>7,}{100*r.keep:>7.1f}%{r.R:>+10.4f}{'--':>10}{'--':>8}")
    return T
