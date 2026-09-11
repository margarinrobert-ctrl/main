"""The Donchian + EMA + ADX + CHOP breakout system, reconstructed from its published description.

THE SOURCE SPECIFIES THE RULES COMPLETELY, which is the reason it is worth testing: there is
nothing to guess. Long when the close crosses ABOVE the upper Donchian band, ADX above a
threshold, the choppiness index below a threshold, and price above an EMA. Short is the mirror.
The exit is an ATR trailing stop at a multiple of ATR. Entry on the NEXT candle.

FOUR DEFINITIONAL DECISIONS the description leaves open, resolved here and stated rather than
buried, because each one changes the result:

  1. BAND OFFSET. `ta.highest(high, n)` at bar i includes bar i's own high, so a close can never
     exceed it -- the signal would never fire. The band is therefore the highest high of the n bars
     ENDING AT i-1. Same for the low band. This is also what makes it causal.
  2. CROSS, not level. "Crosses above" means c[i] > up[i] and c[i-1] <= up[i-1]. Using the level
     alone turns one breakout into a run of consecutive signals.
  3. ADX AND CHOP ARE READ AT THE SIGNAL BAR, not the fill bar. `ent_bar` is the FILL bar; a
     condition read there is read on a bar that closes after the order is sent.
  4. THE TRAIL RATCHETS FROM THE ENTRY BAR ONWARD and never loosens. It is seeded at
     entry +/- mult*ATR(signal bar) and then follows the extreme of the bars since entry.

WITHIN-BAR ORDERING is pessimistic: on any bar the trailing stop is tested against that bar's
extreme BEFORE the trail is advanced by the same bar. A bar that both makes a new high and then
retraces through the old stop is a stop-out, not a ride.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
import indicators as I  # noqa: E402


def wilder_atr(h, l, c, n=14):
    """Wilder's ATR -- what `ta.atr` gives in Pine, and what the source's ATR multiplier means."""
    h, l, c = map(lambda x: np.asarray(x, float), (h, l, c))
    pc = I.shift(c, 1)
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()


def chop(h, l, c, n=14):
    """Choppiness index: 100 * log10(sum(TR, n) / (highest(h,n) - lowest(l,n))) / log10(n).

    Near 100 the bar-by-bar travel is far larger than the net range -- the market is going nowhere
    the long way round. Near 0 the range was covered in a straight line."""
    h, l, c = map(lambda x: np.asarray(x, float), (h, l, c))
    pc = I.shift(c, 1)
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    s = pd.Series(tr).rolling(n, min_periods=n).sum().to_numpy()
    rng = I.rmax(h, n) - I.rmin(l, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        v = 100.0 * np.log10(np.where(rng > 0, s / rng, np.nan)) / np.log10(n)
    return v


def bands(h, l, n):
    """Donchian bands EXCLUDING the current bar -- see decision 1 in the module docstring."""
    return I.shift(I.rmax(np.asarray(h, float), n), 1), I.shift(I.rmin(np.asarray(l, float), n), 1)


def signals(d, dc=20, ema_n=50, adx_n=14, chop_n=14, atr_n=14,
            adx_min=20.0, chop_max=40.0, longs=True, shorts=True):
    """Boolean arrays of SIGNAL bars. The trade fills at the open of the following bar."""
    h, l, c = d["h"], d["l"], d["c"]
    up, dn = bands(h, l, dc)
    e = I.ema(c, ema_n)
    a = I.adx_di(h, l, c, adx_n)[0]
    ch = chop(h, l, c, chop_n)
    xup = (c > up) & (I.shift(c, 1) <= I.shift(up, 1))
    xdn = (c < dn) & (I.shift(c, 1) >= I.shift(dn, 1))
    ok = (a > adx_min) & (ch < chop_max)
    sl = xup & ok & (c > e) if longs else np.zeros(len(c), bool)
    ss = xdn & ok & (c < e) if shorts else np.zeros(len(c), bool)
    fin = np.isfinite(up) & np.isfinite(dn) & np.isfinite(e) & np.isfinite(a) & np.isfinite(ch)
    return np.nan_to_num(sl, nan=0).astype(bool) & fin, np.nan_to_num(ss, nan=0).astype(bool) & fin


def run(d, sig_l, sig_s, atr, mult=3.0, cost=0.0, one_at_a_time=True,
        max_hold=None, flat_mod=None):
    """Walk the bars with an ATR trailing stop. Returns a trade frame.

    `cost` is charged in PRICE units per round turn. `flat_mod` closes any open position at the
    first bar whose minute-of-day is at or past it -- that is how an intraday variant is made
    without a second engine.
    """
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    mod = d["mod"]
    n = len(c)
    rows = []
    i = 0
    while i < n - 2:
        side = 1 if sig_l[i] else (-1 if sig_s[i] else 0)
        if side == 0 or not np.isfinite(atr[i]) or atr[i] <= 0:
            i += 1
            continue
        eb = i + 1                                   # fill on the NEXT bar's open
        ep = o[eb]
        stop = ep - side * mult * atr[i]             # ATR read at the SIGNAL bar
        ext = ep
        j, out, why = eb, None, "eod"
        while j < n:
            if side > 0 and l[j] <= stop:
                out, why = stop, "trail"; break
            if side < 0 and h[j] >= stop:
                out, why = stop, "trail"; break
            if flat_mod is not None and mod[j] >= flat_mod:
                out, why = c[j], "flat"; break
            if max_hold is not None and j - eb >= max_hold:
                out, why = c[j], "hold"; break
            ext = max(ext, h[j]) if side > 0 else min(ext, l[j])
            stop = max(stop, ext - mult * atr[i]) if side > 0 else min(stop, ext + mult * atr[i])
            j += 1
        if out is None:
            break
        pnl = side * (out - ep) - cost
        rows.append((i, eb, j, side, ep, out, pnl, pnl / (mult * atr[i]), why))
        i = (j + 1) if one_at_a_time else (i + 1)
    return pd.DataFrame(rows, columns=["sig_bar", "ent_bar", "exit_bar", "side", "entry", "exit",
                                       "pnl", "R", "why"])
