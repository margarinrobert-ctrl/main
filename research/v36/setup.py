"""V36 -- the sweep and the IFVG, defined so that nothing is left to interpretation.

THE SETUP, in order, with every term made objective:

  1. A LIQUIDITY POOL exists and is knowable: a confirmed 1H or 4H swing level, a frozen Asia or
     London extreme, a previous-day level, or the running session extreme.

  2. A SWEEP occurs. Four definitions are implemented and tested against each other rather than
     assumed:
       WICK        the bar's extreme pierces the level by >= `pen` x ATR, and it closes back inside
       CLOSE       the bar closes BEYOND the level and a later bar closes back inside within
                   `reclaim_bars`
       PEN_ONLY    the extreme pierces by >= `pen` x ATR, no close condition at all
       DISPLACE    WICK, plus a displacement candle away from the level within `disp_bars`
     A pool is CONSUMED when swept, so the same level is never traded twice.

  3. AN IFVG FORMS AFTER THE SWEEP. The chain is explicit:
       FVG           three candles on the entry timeframe. BULLISH when low[i] > high[i-2], zone
                     [high[i-2], low[i]]. BEARISH when high[i] < low[i-2], zone [high[i], low[i-2]].
                     Knowable at the close of bar i, never before.
       INVALIDATION  a candle CLOSES through the zone. A bearish FVG closing above its top is
                     invalidated; a bullish FVG closing below its bottom is invalidated.
       IFVG          the invalidated zone, now taken with the opposite polarity. A BEARISH FVG
                     closed through to the upside becomes a BULLISH IFVG -- support. That is the
                     one a long reversal needs after sweeping lows.
     The inversion candle must close AFTER the sweep bar and within `max_gap` bars of it.

  4. ENTRY. Three variants, tested separately:
       EDGE      a limit at the proximal boundary of the IFVG zone, on first retest
       MID       a limit at the zone midpoint, on first retest
       CLOSE     a market order at the next bar's open after the inversion candle
     `retest_bars` caps how long the limit may rest. An unfilled limit is a missed trade and is
     counted, because per-signal accounting is the only honest denominator (`STUDY_V34`).

NOTHING HERE READS A BAR THAT HAS NOT CLOSED. FVGs are stamped at bar i, inversions at the closing
bar, entries at the NEXT bar's open or at a resting limit level. The pivot confirmation lag is
already handled in `levels.py`.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v36")
import indicators as I        # noqa: E402
import levels as LV           # noqa: E402

SWEEP_DEFS = ("wick", "close", "pen_only", "displace")
ENTRY_MODES = ("edge", "mid", "close")


# ------------------------------------------------------------------------------------------------
# the pool book
# ------------------------------------------------------------------------------------------------
def build_pools(d, htf=((60, 3), (240, 2))):
    """Every liquidity level with the 1-minute bar it becomes knowable on, and its source label.
    Returns two arrays of (price, from_bar, source) -- one for highs, one for lows."""
    hi, lo = [], []
    for tf, k in htf:
        p = LV.htf_pools(d, tf, k)
        tag = f"{tf}m"
        hi += [(px, int(b), tag) for px, b in zip(p["hi_price"], p["hi_conf_1m"])]
        lo += [(px, int(b), tag) for px, b in zip(p["lo_price"], p["lo_conf_1m"])]
    L = LV.session_levels(d)
    n = len(d["c"])
    for name, key_h, key_l in (("asia", "asia_h", "asia_l"), ("london", "lon_h", "lon_l"),
                               ("prevday", "pd_h", "pd_l")):
        for key, bucket in ((key_h, hi), (key_l, lo)):
            v = L[key]
            fin = np.isfinite(v)
            if not fin.any():
                continue
            # the first bar of each contiguous run of a constant value is when it became knowable
            change = np.r_[True, (v[1:] != v[:-1]) | (~fin[1:]) | (~fin[:-1])]
            starts = np.flatnonzero(change & fin)
            bucket += [(float(v[b]), int(b), name) for b in starts]
    hi.sort(key=lambda r: r[1]); lo.sort(key=lambda r: r[1])
    return dict(hi=hi, lo=lo, L=L)


# ------------------------------------------------------------------------------------------------
# sweeps
# ------------------------------------------------------------------------------------------------
MAX_AGE = 5 * 1440          # a pool is live for 5 trading days after it becomes knowable


def find_sweeps(d, pools, side, defn="wick", pen=0.10, reclaim_bars=15, disp_bars=10,
                disp_mult=1.0, atr=None, cooldown=60, max_age=MAX_AGE):
    """A sweep of a LOW (side +1, a long setup) or of a HIGH (side -1, a short setup).

    ITERATES OVER POOLS, NOT BARS. The first version walked every bar against every live pool,
    which is 1M bars x thousands of pools and does not terminate. It also implied that a swing low
    from two years ago is still a liquidity pool. Both are fixed by the same change: each pool is
    live for `max_age` minutes from the bar it becomes knowable, and its sweep is found by a
    vectorised scan of that bounded window.

    Returns one row per sweep: the bar it completes on, the level, its source, the penetration in
    ATR, and the sweep extreme -- which is what a structural stop is placed beyond."""
    h, l, c, o = d["h"], d["l"], d["c"], d["o"]
    n = len(c)
    if atr is None:
        atr = I.ema(I.true_range(h, l, c), 14)
    book = pools["lo"] if side > 0 else pools["hi"]
    rows = []
    for lev, b0, src in book:
        a0, b1 = max(b0 + 1, 200), min(b0 + max_age, n - 5)
        if b1 <= a0:
            continue
        sl = slice(a0, b1)
        a = atr[sl]
        ok = np.isfinite(a) & (a > 0)
        if side > 0:
            pierced = ok & (l[sl] < lev - pen * a)
            back_in = c[sl] > lev
            beyond = c[sl] < lev
        else:
            pierced = ok & (h[sl] > lev + pen * a)
            back_in = c[sl] < lev
            beyond = c[sl] > lev

        if defn == "pen_only":
            hit = pierced
        elif defn == "wick":
            hit = pierced & back_in
        elif defn == "close":
            # closed beyond, then a later close back inside within reclaim_bars
            cand = np.flatnonzero(pierced & beyond)
            hit = np.zeros(b1 - a0, bool)
            for j in cand:
                w = slice(a0 + j + 1, min(a0 + j + 1 + reclaim_bars, n))
                if ((c[w] > lev).any() if side > 0 else (c[w] < lev).any()):
                    hit[j] = True
                    break
        elif defn == "displace":
            cand = np.flatnonzero(pierced & back_in)
            hit = np.zeros(b1 - a0, bool)
            for j in cand:
                w = slice(a0 + j + 1, min(a0 + j + 1 + disp_bars, n))
                if ((c[w] - o[w]) * side >= disp_mult * atr[a0 + j]).any():
                    hit[j] = True
                    break
        else:
            raise ValueError(defn)

        f = np.flatnonzero(hit)
        if not len(f):
            continue
        t = a0 + int(f[0])
        ext = float(l[t]) if side > 0 else float(h[t])
        rows.append(dict(bar=t, level=float(lev), src=src, side=side,
                         pen_atr=float(abs(ext - lev) / atr[t]), sweep_ext=ext,
                         atr=float(atr[t]), age=int(t - b0)))
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values("bar").reset_index(drop=True)
    # one setup at a time: drop any sweep inside the cooldown of the one before it
    keep, last = [], -10 ** 9
    for i, b in enumerate(df.bar.to_numpy()):
        if b - last >= cooldown:
            keep.append(i); last = b
    return df.iloc[keep].reset_index(drop=True)


# ------------------------------------------------------------------------------------------------
# FVG -> invalidation -> IFVG
# ------------------------------------------------------------------------------------------------
def htf_frame(d, tf):
    r = LV.resample(d, tf)
    return r


def find_fvgs(r, atr_tf, disp_mult=0.0):
    """Every FVG on a timeframe, with the bar it is knowable on and its zone."""
    h, l, c, o = r["h"], r["l"], r["c"], r["o"]
    n = len(c)
    out = []
    for i in range(2, n):
        mid_body = abs(c[i - 1] - o[i - 1])
        a = atr_tf[i]
        if disp_mult > 0 and (not np.isfinite(a) or mid_body < disp_mult * a):
            continue
        if l[i] > h[i - 2]:
            out.append((i, +1, h[i - 2], l[i]))          # bullish zone [lo, hi]
        elif h[i] < l[i - 2]:
            out.append((i, -1, h[i], l[i - 2]))          # bearish zone [lo, hi]
    return out


def find_ifvgs(r, fvgs, max_life=200):
    """An FVG is INVALIDATED when a candle closes through it; the zone then inverts. Returns the
    inversion bar, the zone, and the NEW polarity."""
    c = r["c"]
    n = len(c)
    out = []
    for (i, pol, zlo, zhi) in fvgs:
        stop = min(i + max_life, n)
        for j in range(i + 1, stop):
            if pol > 0 and c[j] < zlo:
                out.append(dict(inv_bar=j, pol=-1, zlo=zlo, zhi=zhi, born=i)); break
            if pol < 0 and c[j] > zhi:
                out.append(dict(inv_bar=j, pol=+1, zlo=zlo, zhi=zhi, born=i)); break
    return pd.DataFrame(out)


def setups(d, side, sweeps, ifvg, r_tf, tf, max_gap_bars=12):
    """Join a sweep to the FIRST IFVG of the matching polarity that INVERTS AFTER it, within
    `max_gap_bars` bars of the entry timeframe."""
    if not len(sweeps) or not len(ifvg):
        return pd.DataFrame()
    last_i = r_tf["last_i"]
    inv1m = last_i[np.minimum(ifvg.inv_bar.to_numpy(), len(last_i) - 1)]
    want = ifvg.pol.to_numpy() == side
    inv1m = inv1m[want]
    sub = ifvg[want].reset_index(drop=True)
    order = np.argsort(inv1m)
    inv1m, sub = inv1m[order], sub.iloc[order].reset_index(drop=True)
    rows = []
    for s in sweeps.itertuples():
        j = np.searchsorted(inv1m, s.bar, side="right")
        if j >= len(inv1m):
            continue
        gap_bars = (ifvg.inv_bar.to_numpy()[want][order][j]
                    - np.searchsorted(last_i, s.bar, side="left"))
        if gap_bars < 0 or gap_bars > max_gap_bars:
            continue
        z = sub.iloc[j]
        rows.append(dict(sweep_bar=s.bar, inv_bar_1m=int(inv1m[j]), gap_bars=int(gap_bars),
                         level=s.level, src=s.src, side=side, pen_atr=s.pen_atr,
                         sweep_ext=s.sweep_ext, atr=s.atr, zlo=float(z.zlo), zhi=float(z.zhi),
                         tf=tf))
    return pd.DataFrame(rows)
