"""Initial Value Breakout — the value area of the OPENING period, then a break of its edge.

This is not the Initial Balance study and it is not the value-area study. Initial Balance uses the
opening period's HIGH and LOW; the value-area study uses the WHOLE session's volume distribution.
IVB uses the opening period's volume distribution -- the narrowest band around its point of control
holding a given share of the volume traded so far -- and trades a break of that band's edge.

Why the distinction deserves a test rather than an assumption: the initial balance's extremes are
set by whoever was most aggressive in the first minutes, and one spike sets them. The initial VALUE
area is set by where business actually got done, so it is narrower, far less spike-sensitive, and
breaking it means something different -- price leaving the region the opening auction accepted,
rather than price exceeding the opening auction's most extreme print.

CONSTRUCTION CAVEAT, carried over from volumeProfile.ts and binding on everything downstream: a
true profile needs tick data. From OHLCV the standard approximation spreads each bar's volume
uniformly across its range. Profiles here are built from ONE-MINUTE bars whatever timeframe the
trades are taken on, which is the best resolution this repository has. The POC is approximately
right, fine node structure is not, and nothing here depends on fine node structure.

NO LOOK-AHEAD. The value area is frozen when the opening period closes and is never revised. A
signal computed from a bar's close fills at the next bar's open. Entries stop at a cutoff and any
open position is flattened there.
"""
from __future__ import annotations

import sys

import numpy as np
from numba import njit

sys.path.insert(0, "research")
from bos_choch import prep

TICK = 0.25
PV = 2.0            # MNQ
COMM = 1.0
EC = 2.0 * TICK     # (spread + slip) points, charged each side
SE = 1.0 * TICK     # extra slip on a stop
RTH = 570           # 09:30 in minutes after midnight


def build_value_areas(iv_min: int, bin_ticks: int, va_pct: float):
    """One (POC, VAH, VAL, high, low) per session from the first `iv_min` minutes of RTH.

    Returns arrays indexed by position in `np.unique(sess)` of the 1-minute series.
    """
    d1 = prep(1)
    h, l, v, mod, sess = d1["h"], d1["l"], d1["v"], d1["mod"], d1["sess"]
    m = (mod >= RTH) & (mod < RTH + iv_min)
    us = np.unique(sess)
    idx = {s: i for i, s in enumerate(us)}
    poc = np.full(len(us), np.nan)
    vah = np.full(len(us), np.nan)
    val = np.full(len(us), np.nan)
    hi = np.full(len(us), np.nan)
    lo = np.full(len(us), np.nan)
    binsz = bin_ticks * TICK

    order = np.argsort(sess[m], kind="stable")
    sm = sess[m][order]; hm = h[m][order]; lm = l[m][order]; vm = v[m][order]
    bounds = np.searchsorted(sm, us)
    bounds = np.r_[bounds, len(sm)]
    for i in range(len(us)):
        a, b = bounds[i], bounds[i + 1]
        if b - a < 3:
            continue
        hh, ll, vv = hm[a:b], lm[a:b], np.maximum(vm[a:b], 1.0)
        top, bot = hh.max(), ll.min()
        first = int(np.floor(bot / binsz))
        cnt = int(np.floor(top / binsz)) - first + 1
        if cnt < 1 or cnt > 20000:
            continue
        acc = np.zeros(cnt)
        f = (np.floor(ll / binsz).astype(np.int64) - first)
        t = (np.floor(hh / binsz).astype(np.int64) - first)
        per = vv / (t - f + 1)
        # spread each bar's volume uniformly over its range
        np.add.at(acc, f, per)
        ends = t + 1
        carry = np.zeros(cnt + 1)
        np.add.at(carry, f, per)
        np.add.at(carry, ends, -per)
        acc = np.cumsum(carry[:-1])
        tot = acc.sum()
        if tot <= 0:
            continue
        pk = int(np.argmax(acc))
        target = tot * va_pct
        low_b = up_b = pk
        s = acc[pk]
        while s < target and (low_b > 0 or up_b < cnt - 1):
            below = acc[low_b - 1] if low_b > 0 else -1.0
            above = acc[up_b + 1] if up_b < cnt - 1 else -1.0
            if above >= below:
                up_b += 1; s += acc[up_b]
            else:
                low_b -= 1; s += acc[low_b]
        price = lambda k: (first + k) * binsz + binsz * 0.5
        poc[i] = price(pk); vah[i] = price(up_b); val[i] = price(low_b)
        hi[i] = top; lo[i] = bot
    return us, poc, vah, val, hi, lo



def session_context(iv_min: int, bin_ticks: int = 4, va_pct: float = 0.70):
    """Everything about a session that is known the moment its opening period closes.

    Returns, indexed by session: the opening high/low, the value area, the trailing range
    percentile, and the higher-timeframe trend. Every one is causal -- the range percentile uses
    only PREVIOUS sessions and the trend uses the last 60-minute bar that closed before 09:30.
    """
    us, poc, vah, val, ivh, ivl = build_value_areas(iv_min, bin_ticks, va_pct)
    n = len(us)

    # trailing percentile of today's opening range within the previous 60 sessions
    rng = ivh - ivl
    pct = np.full(n, np.nan)
    for i in range(60, n):
        w = rng[i - 60:i]
        w = w[~np.isnan(w)]
        if len(w) >= 30 and not np.isnan(rng[i]):
            pct[i] = (w < rng[i]).mean()

    # higher-timeframe trend: the last 60m bar to CLOSE before 09:30, against its own 50 EMA
    d60 = prep(60)
    e60 = d60["df"]["close"].ewm(span=50, adjust=False).mean().to_numpy()
    c60, mod60, s60 = d60["c"], d60["mod"], d60["sess"]
    trend = np.zeros(n, np.int64)
    idx = {s: i for i, s in enumerate(us)}
    last = {}
    for j in range(len(c60)):
        if mod60[j] + 60 <= RTH:                     # closed at or before 09:30
            last[s60[j]] = j
    for s, j in last.items():
        if s in idx and not np.isnan(e60[j]):
            trend[idx[s]] = 1 if c60[j] > e60[j] else -1
    return us, poc, vah, val, ivh, ivl, pct, trend


@njit(cache=True)
def run(o, h, l, c, mod, sidx, atr_,
        vah, val, poc, ivh, ivl, pct, trend,
        iv_min, use_ib, entry_mode, stop_mode, atr_mult, tgt_mode, tp,
        buf_atr, trend_mode, rng_filter, flat_min, side_mode, cut_idx, out, row):
    """One position at a time, one session at a time.

    use_ib      0 break the VALUE AREA edge (the section-10 variant)   1 break the opening HIGH/LOW
    entry_mode  0 break and go at the next open
                1 wait for a retest OF the level and fill there
                2 wait for a retest halfway back to the middle (POC, or the IV midpoint)
                3 FAILED breakout: close beyond the edge then close back inside -> trade the other way
    stop_mode   0 ATR multiple   1 the opposite edge   2 the middle   3 the trigger bar's extreme
    tgt_mode    0 target at tp x risk    1 target at tp x the initial range
    trend_mode  0 off   1 the 60m trend must agree with the break   2 it must DISAGREE
    """
    n = len(c)
    cnt = np.zeros(2, np.int64); net = np.zeros(2, np.float64)
    wins = np.zeros(2, np.int64); gw = np.zeros(2, np.float64); gl = np.zeros(2, np.float64)
    eq = np.zeros(2, np.float64); peak = np.zeros(2, np.float64); dd = np.zeros(2, np.float64)
    lcnt = np.zeros(2, np.int64)
    why = np.zeros(3, np.int64)          # 0 stop, 1 target, 2 session cutoff
    whyw = np.zeros(3, np.int64)
    pos = 0; entry = 0.0; stop = 0.0; tgt = 0.0
    pend = 0; pstop = 0.0; ptgt = 0.0
    armed = 0; arm_px = 0.0; arm_stop = 0.0; arm_rng = 0.0
    broke = 0                      # which way this session has already broken, for entry_mode 3
    took = 0; s_prev = -1
    for i in range(1, n - 1):
        s = sidx[i]
        if s != s_prev:
            pos = 0; pend = 0; armed = 0; took = 0; broke = 0
            s_prev = s
        if s < 0:
            continue
        a = atr_[i]
        if np.isnan(a) or a <= 0.0:
            continue
        up = ivh[s] if use_ib == 1 else vah[s]
        dn = ivl[s] if use_ib == 1 else val[s]
        mid = (ivh[s] + ivl[s]) * 0.5 if use_ib == 1 else poc[s]
        if np.isnan(up) or np.isnan(dn) or np.isnan(mid) or up <= dn:
            continue
        ivr = up - dn
        m = mod[i]
        after = m >= RTH + iv_min
        open_still = m < flat_min

        if pend != 0 and pos == 0:
            pos = pend; entry = o[i]; pend = 0; stop = pstop; tgt = ptgt
            if (pos == 1 and stop >= entry) or (pos == -1 and stop <= entry):
                pos = 0
        if pos != 0:
            hit = (l[i] <= stop) if pos == 1 else (h[i] >= stop)
            won = (h[i] >= tgt) if pos == 1 else (l[i] <= tgt)
            px = 0.0; done = 0; rsn = 0
            if hit:
                px = o[i] if ((pos == 1 and o[i] < stop) or (pos == -1 and o[i] > stop)) else stop
                px += -SE if pos == 1 else SE
                done = 1; rsn = 0
            elif won:
                px = o[i] if ((pos == 1 and o[i] > tgt) or (pos == -1 and o[i] < tgt)) else tgt
                done = 1; rsn = 1
            elif not open_still:
                px = c[i]; done = 1; rsn = 2
            if done == 1:
                p = pos * (px - entry) * PV - COMM - 2.0 * EC * PV
                b = 0 if s < cut_idx else 1
                cnt[b] += 1; net[b] += p
                if p > 0:
                    wins[b] += 1; gw[b] += p
                else:
                    gl[b] -= p
                why[rsn] += 1
                if p > 0:
                    whyw[rsn] += 1
                if pos == 1:
                    lcnt[b] += 1
                eq[b] += p
                if eq[b] > peak[b]:
                    peak[b] = eq[b]
                if peak[b] - eq[b] > dd[b]:
                    dd[b] = peak[b] - eq[b]
                pos = 0
        if pos != 0 or pend != 0 or not after or not open_still or took >= 1:
            continue
        if rng_filter == 1 and (np.isnan(pct[s]) or pct[s] < 0.2 or pct[s] > 0.8):
            continue

        if armed != 0:
            d = armed
            touched = (l[i] <= arm_px) if d == 1 else (h[i] >= arm_px)
            if touched:
                st = arm_stop
                if stop_mode == 3:
                    st = (l[i] - 0.25 * a) if d == 1 else (h[i] + 0.25 * a)
                risk = abs(arm_px - st)
                if risk > 0.0 and risk <= 8.0 * a and ((d == 1 and st < arm_px) or (d == -1 and st > arm_px)):
                    pos = d; entry = arm_px; stop = st
                    tgt = arm_px + d * (tp * risk if tgt_mode == 0 else tp * arm_rng)
                    took += 1
                armed = 0
            continue

        # ---- what happened on this bar --------------------------------------------------
        brk = 0
        if c[i] > up + buf_atr * a:
            brk = 1
        elif c[i] < dn - buf_atr * a:
            brk = -1
        if brk != 0:
            broke = brk
        d = 0
        if entry_mode == 3:
            # a failed breakout: the session broke one way, and price is now back inside
            if broke != 0 and c[i] < up and c[i] > dn:
                d = -broke
                broke = 0
        else:
            d = brk
        if d == 0:
            continue
        if side_mode != 0 and side_mode != d:
            continue
        if trend_mode == 1 and trend[s] != d:
            continue
        if trend_mode == 2 and trend[s] == d:
            continue

        lvl = up if d == 1 else dn
        opp = dn if d == 1 else up
        if entry_mode == 0 or entry_mode == 3:
            ref = c[i]
        elif entry_mode == 1:
            ref = lvl
        else:
            ref = lvl + (mid - lvl) * 0.5
        if stop_mode == 0:
            st = ref - d * atr_mult * a
        elif stop_mode == 1:
            st = opp
        elif stop_mode == 2:
            st = mid
        else:
            st = (l[i] - 0.25 * a) if d == 1 else (h[i] + 0.25 * a)
        if (d == 1 and st >= ref) or (d == -1 and st <= ref):
            continue
        risk = abs(ref - st)
        if risk <= 0.0 or risk > 8.0 * a:
            continue
        if entry_mode == 0 or entry_mode == 3:
            pend = d; pstop = st
            ptgt = ref + d * (tp * risk if tgt_mode == 0 else tp * ivr)
            took += 1
        else:
            armed = d; arm_px = ref; arm_stop = st; arm_rng = ivr
    for b in range(2):
        out[row, b * 7 + 0] = cnt[b]; out[row, b * 7 + 1] = net[b]
        out[row, b * 7 + 2] = wins[b]; out[row, b * 7 + 3] = gw[b]
        out[row, b * 7 + 4] = gl[b]; out[row, b * 7 + 5] = dd[b]
        out[row, b * 7 + 6] = lcnt[b]
    for q in range(3):
        out[row, 14 + q] = why[q]
        out[row, 17 + q] = whyw[q]
