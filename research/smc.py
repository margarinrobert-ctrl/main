"""Smart-money-concept features, defined mechanically enough to be tested.

Every concept below is written as an explicit rule on OHLCV bars. That is the point: SMC is usually
taught visually, and a visual rule cannot be falsified. If a feature here has no predictive content,
that is a fact about the concept as specified, not about a chart someone drew afterwards.

Causality: every feature at bar i uses only bars <= i, and swing pivots are confirmed only after
`k` bars have passed, so a pivot at t is not visible until t+k. Nothing here can see the future.

  SWING PIVOTS   fractal highs/lows confirmed k bars later
  BOS            close beyond the last confirmed swing in the direction of structure
  CHoCH          the first BOS against the prevailing structure — the reversal signal
  FVG            three-bar imbalance: low[i] > high[i-2] (bullish) or high[i] < low[i-2] (bearish)
  ORDER BLOCK    last opposing candle before the impulse that broke structure
  LIQUIDITY SWEEP wick beyond a prior swing that closes back inside — a stop hunt
  PREMIUM/DISCOUNT position inside the current dealing range; SMC says buy discount, sell premium
"""
from __future__ import annotations

import numpy as np
from numba import njit


@njit(cache=True)
def swing_pivots(h, l, k):
    """Fractal pivots, CONFIRMED k bars after the fact.

    `ph[i]`/`pl[i]` hold the price of the most recent pivot that is knowable at bar i, and
    `phi`/`pli` its bar index. A pivot at t only becomes visible at t+k, which is what stops this
    from being a look-ahead dressed up as structure.
    """
    n = h.shape[0]
    ph = np.full(n, np.nan); pl = np.full(n, np.nan)
    phi = np.full(n, -1, np.int64); pli = np.full(n, -1, np.int64)
    last_ph = np.nan; last_pl = np.nan
    last_phi = -1; last_pli = -1
    for i in range(n):
        t = i - k                      # the bar we can now judge
        if t >= k:
            is_h = True; is_l = True
            for j in range(1, k + 1):
                if h[t] <= h[t - j] or h[t] <= h[t + j]:
                    is_h = False
                if l[t] >= l[t - j] or l[t] >= l[t + j]:
                    is_l = False
            if is_h:
                last_ph = h[t]; last_phi = t
            if is_l:
                last_pl = l[t]; last_pli = t
        ph[i] = last_ph; pl[i] = last_pl
        phi[i] = last_phi; pli[i] = last_pli
    return ph, pl, phi, pli


@njit(cache=True)
def structure(c, ph, pl):
    """Break of structure and change of character.

    `bias` is the prevailing structure: +1 after a bullish BOS, -1 after a bearish one. A BOS in the
    SAME direction as the bias is continuation; the FIRST break against it is a CHoCH, which is the
    signal SMC treats as a reversal. Both are returned as event flags plus a bars-since counter,
    because "how long ago" is usually what carries the information rather than the event itself.
    """
    n = c.shape[0]
    bos = np.zeros(n, np.int8)
    choch = np.zeros(n, np.int8)
    bias = np.zeros(n, np.int8)
    since_bos = np.full(n, 9999, np.int64)
    since_choch = np.full(n, 9999, np.int64)
    b = 0
    sb = 9999; sc = 9999
    for i in range(n):
        ev = 0
        if not np.isnan(ph[i]) and c[i] > ph[i]:
            ev = 1
        elif not np.isnan(pl[i]) and c[i] < pl[i]:
            ev = -1
        if ev != 0:
            if b != 0 and ev != b:
                choch[i] = ev
                sc = 0
            bos[i] = ev
            b = ev
            sb = 0
        else:
            sb = sb + 1 if sb < 9999 else 9999
            sc = sc + 1 if sc < 9999 else 9999
        bias[i] = b
        since_bos[i] = sb
        since_choch[i] = sc
    return bos, choch, bias, since_bos, since_choch


@njit(cache=True)
def fair_value_gaps(h, l, atr):
    """Nearest UNFILLED three-bar imbalance, above and below.

    A bullish FVG forms when low[i] > high[i-2] — price moved so fast the middle bar left a gap. SMC
    holds that price returns to fill it. A gap is retired the moment price trades back through it.
    Returned as distance to the nearest live gap in ATR units, and its size, separately for the gap
    above and the gap below.
    """
    n = h.shape[0]
    dist_up = np.full(n, np.nan); size_up = np.full(n, np.nan)
    dist_dn = np.full(n, np.nan); size_dn = np.full(n, np.nan)
    # Track one live gap each side; a newer gap replaces an older one.
    up_lo = np.nan; up_hi = np.nan     # bullish gap (support below price)
    dn_lo = np.nan; dn_hi = np.nan     # bearish gap (resistance above price)
    for i in range(n):
        if i >= 2:
            if l[i] > h[i - 2]:
                up_lo = h[i - 2]; up_hi = l[i]
            if h[i] < l[i - 2]:
                dn_lo = h[i]; dn_hi = l[i - 2]
        # fill checks
        if not np.isnan(up_lo) and l[i] <= up_lo:
            up_lo = np.nan; up_hi = np.nan
        if not np.isnan(dn_hi) and h[i] >= dn_hi:
            dn_lo = np.nan; dn_hi = np.nan
        a = atr[i]
        if a > 0:
            if not np.isnan(up_hi):
                dist_up[i] = (l[i] - up_hi) / a
                size_up[i] = (up_hi - up_lo) / a
            if not np.isnan(dn_lo):
                dist_dn[i] = (dn_lo - h[i]) / a
                size_dn[i] = (dn_hi - dn_lo) / a
    return dist_up, size_up, dist_dn, size_dn


@njit(cache=True)
def liquidity_sweeps(h, l, c, ph, pl):
    """Stop hunts: a wick beyond a prior swing that closes back inside.

    This is the single most-cited SMC pattern — liquidity resting above a high gets taken, then
    price reverses. Returned as an event flag and a bars-since counter for each side.
    """
    n = h.shape[0]
    sweep = np.zeros(n, np.int8)
    since = np.full(n, 9999, np.int64)
    s = 9999
    for i in range(n):
        ev = 0
        if not np.isnan(ph[i]) and h[i] > ph[i] and c[i] < ph[i]:
            ev = -1                      # swept the highs, closed back under: bearish
        elif not np.isnan(pl[i]) and l[i] < pl[i] and c[i] > pl[i]:
            ev = 1                       # swept the lows, closed back above: bullish
        sweep[i] = ev
        if ev != 0:
            s = 0
        else:
            s = s + 1 if s < 9999 else 9999
        since[i] = s
    return sweep, since


@njit(cache=True)
def dealing_range(c, ph, pl):
    """Where price sits inside the current swing range: 0 = at the low, 1 = at the high.

    SMC's premium/discount idea. Above 0.5 is 'premium' (sell zone), below is 'discount' (buy zone).
    """
    n = c.shape[0]
    pos = np.full(n, np.nan)
    for i in range(n):
        if not np.isnan(ph[i]) and not np.isnan(pl[i]) and ph[i] > pl[i]:
            pos[i] = (c[i] - pl[i]) / (ph[i] - pl[i])
    return pos


@njit(cache=True)
def order_block_distance(o, c, h, l, bos, atr):
    """Distance to the last order block, in ATR units.

    The order block is the last opposing candle before the impulse that broke structure: the last
    down-candle before a bullish BOS, the last up-candle before a bearish one. SMC treats a return
    to it as the entry. Sign is kept so the model can tell an untested block above from one below.
    """
    n = o.shape[0]
    dist = np.full(n, np.nan)
    ob_lo = np.nan; ob_hi = np.nan; ob_dir = 0
    for i in range(n):
        if bos[i] != 0:
            # walk back for the last candle against the break
            for j in range(i - 1, max(-1, i - 60), -1):
                if bos[i] == 1 and c[j] < o[j]:
                    ob_lo = l[j]; ob_hi = h[j]; ob_dir = 1
                    break
                if bos[i] == -1 and c[j] > o[j]:
                    ob_lo = l[j]; ob_hi = h[j]; ob_dir = -1
                    break
        a = atr[i]
        if a > 0 and not np.isnan(ob_lo):
            if ob_dir == 1:
                dist[i] = (c[i] - ob_hi) / a
            else:
                dist[i] = (ob_lo - c[i]) / a
    return dist


@njit(cache=True)
def atr_series(h, l, c, n_len):
    """Wilder-style ATR on the bar series handed in."""
    n = h.shape[0]
    out = np.full(n, np.nan)
    acc = 0.0
    for i in range(n):
        tr = h[i] - l[i]
        if i > 0:
            d1 = abs(h[i] - c[i - 1]); d2 = abs(l[i] - c[i - 1])
            if d1 > tr: tr = d1
            if d2 > tr: tr = d2
        if i < n_len:
            acc += tr
            if i == n_len - 1:
                out[i] = acc / n_len
        else:
            out[i] = (out[i - 1] * (n_len - 1) + tr) / n_len
    return out
