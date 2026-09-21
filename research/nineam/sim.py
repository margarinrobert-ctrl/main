"""The 09:00-range breakout, ported from the Pine and walked on 30-second bars.

WHAT IS FAITHFUL TO THE PINE, and each of these has been a bug on this branch at least once:

  * the signal bar is the CONFIRMED close; the fill is the NEXT bar's OPEN. Reading anything at
    the fill bar is the `ent_bar` leak (CLAUDE.md), so every gate here is evaluated at the signal
    bar and `trig` indexes signal bars throughout.
  * the bracket is priced from the SIGNAL bar's ATR and placed WITH the entry, so the fill bar is
    protected (STUDY_PINE_PARITY).
  * a break that a gate REFUSES still marks that side used for the session, so gating changes
    which trades happen, never how many chances the session gets.
  * one position at a time (pyramiding = 0).
  * the flatten fills at the OPEN of the flatten minute, because strategy.close_all() cannot sell
    the close of the bar that triggers it (STUDY_V16).

WHAT IS BETTER THAN THE PINE: the exit walks the 30-SECOND array, so a bar holding both barriers
is resolved by looking rather than booked as a loss by convention. `amb` reports how often the
two still land in one 30-second bar, which is the residual assumption.
"""
from __future__ import annotations

import numpy as np
from numba import njit

from bars import PV, RT_PTS, STOP_SLIP, STOP, TARGET, FLAT, MAXHOLD, NOFILL


# ------------------------------------------------------------------ the session range
def levels(b: dict, r0: int, r1: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-bar running range high/low for its own session, and whether the range is closed.

    Built causally: a bar inside the window sees the range SO FAR, a bar after it sees the final
    range. `ready` is false until the window has ended, which is what gates the break.
    """
    n, mod, si = b["n"], b["mod"], b["si"]
    hi = np.full(n, np.nan); lo = np.full(n, np.nan); ready = np.zeros(n, bool)
    curH = np.nan; curL = np.nan; cur = -1; seen = False
    for i in range(n):
        if si[i] != cur:
            cur = si[i]; curH = np.nan; curL = np.nan; seen = False
        m = mod[i]
        if r0 <= m < r1:
            curH = b["h"][i] if np.isnan(curH) else max(curH, b["h"][i])
            curL = b["l"][i] if np.isnan(curL) else min(curL, b["l"][i])
            seen = True
        hi[i] = curH; lo[i] = curL
        ready[i] = seen and (m >= r1) and not np.isnan(curH)
    return hi, lo, ready


def triggers(b: dict, r0: int, r1: int, arm: int, last: int, atr: np.ndarray,
             buf: float = 0.0, side: str = "both", touch: bool = True):
    """Signal bars and their side (+1 long, -1 short), before any gate.

    Returns (idx, side, upLvl, dnLvl) where idx are SIGNAL bars -- the fill is idx+1.
    """
    hi, lo, ready = levels(b, r0, r1)
    mod = b["mod"]
    up = hi + buf * atr
    dn = lo - buf * atr
    armed = ready & (mod >= max(r1, arm)) & (mod < last) & np.isfinite(atr) & (atr > 0)
    hitU = armed & ((b["h"] >= up) if touch else (b["h"] > up))
    hitD = armed & ((b["l"] <= dn) if touch else (b["l"] < dn))
    if side == "long":
        hitD = np.zeros_like(hitD)
    elif side == "short":
        hitU = np.zeros_like(hitU)
    return hitU, hitD, up, dn


@njit(cache=True)
def _walk(s0, s1, t30h, t30l, t30o, t30mod,
          hitU, hitD, si, stopD, tgtD, flatm, maxhold, allow,
          n, entry_slip):
    """One pass over the bars: Pine's position/first-break state machine, exits on 30s bars.

    stopD/tgtD are ABSOLUTE point distances per signal bar (tgtD <= 0 means no target).
    `allow` is the gate mask read at the SIGNAL bar.
    """
    eb = np.empty(n, np.int64); xb = np.empty(n, np.int64); sd = np.empty(n, np.int64)
    why = np.empty(n, np.int64); gross = np.empty(n, np.float64); amb = np.empty(n, np.int64)
    k = 0
    tookU = False; tookD = False; cur = -1
    busy_until = -1          # bar index at which the open position is released
    for i in range(n - 1):
        if si[i] != cur:
            cur = si[i]; tookU = False; tookD = False
        u = hitU[i]; dd = hitD[i]
        if not (u or dd):
            continue
        want = 0
        if u and not tookU:
            want = 1
        elif dd and not tookD:
            want = -1
        # a refused break still burns the side for the session
        if u:
            tookU = True
        if dd:
            tookD = True
        if want == 0 or i < busy_until or not allow[i]:
            continue
        j = i + 1                      # the fill bar
        if j >= n:
            continue
        fill = t30o[s0[j]] + entry_slip * want
        sp = stopD[i]; tg = tgtD[i]
        if sp <= 0:
            continue
        stop_px = fill - sp * want
        tgt_px = fill + tg * want if tg > 0 else np.nan
        # walk 30s bars from the fill
        e30 = s0[j]
        lim = s1[n - 1]
        res = 0; px = np.nan; a = 0
        last_bar = j
        p = e30
        while p < lim:
            # which aggregated bar are we in?  advance last_bar lazily
            while last_bar + 1 < n and s0[last_bar + 1] <= p:
                last_bar += 1
            if si[last_bar] != si[i]:
                res = FLAT; px = t30o[p]; break
            m = t30mod[p]
            if flatm > 0 and m >= flatm:
                res = FLAT; px = t30o[p]; break
            if maxhold > 0 and (last_bar - j) >= maxhold:
                res = MAXHOLD; px = t30o[p]; break
            hh = t30h[p]; ll = t30l[p]
            hitS = (ll <= stop_px) if want == 1 else (hh >= stop_px)
            hitT = False
            if tg > 0:
                hitT = (hh >= tgt_px) if want == 1 else (ll <= tgt_px)
            if hitS and hitT:
                a = 1
                res = STOP; px = stop_px          # both in one 30s bar: book the stop
                break
            if hitS:
                res = STOP; px = stop_px; break
            if hitT:
                res = TARGET; px = tgt_px; break
            p += 1
        if res == 0:
            res = FLAT; px = t30o[lim - 1]
        while last_bar + 1 < n and s0[last_bar + 1] <= p:
            last_bar += 1
        eb[k] = i; xb[k] = last_bar; sd[k] = want; why[k] = res
        gross[k] = (px - fill) * want
        amb[k] = a
        k += 1
        busy_until = last_bar + 1
    return eb[:k], xb[:k], sd[:k], why[:k], gross[:k], amb[:k]


def run(b, atr, r0=540, r1=555, arm=570, last=960, flat=960,
        stop_k=1.5, tgt_k=0.0, stop_mode="atr", tgt_mode="none",
        buf=0.0, side="both", touch=True, maxhold=0, allow=None,
        rt=RT_PTS, stop_slip=STOP_SLIP, entry_slip=0.0, trig=None):
    """Simulate and return a trade record. Costs are applied here, never cached."""
    n = b["n"]
    if trig is None:
        hitU, hitD, _u, _d = triggers(b, r0, r1, arm, last, atr, buf, side, touch)
    else:
        hitU, hitD = trig
    if stop_mode == "atr":
        stopD = stop_k * atr
    else:
        stopD = np.full(n, float(stop_k))
    if tgt_mode == "none" or tgt_k <= 0:
        tgtD = np.zeros(n)
    elif tgt_mode == "atr":
        tgtD = tgt_k * atr
    elif tgt_mode == "r":
        tgtD = tgt_k * stopD
    else:
        tgtD = np.full(n, float(tgt_k))
    if allow is None:
        allow = np.ones(n, bool)
    stopD = np.nan_to_num(stopD, nan=-1.0)
    tgtD = np.nan_to_num(tgtD, nan=0.0)
    eb, xb, sd, why, gross, amb = _walk(
        b["s0"], b["s1"], b["t30h"], b["t30l"], b["t30o"], b["t30mod"],
        hitU.astype(np.bool_), hitD.astype(np.bool_), b["si"],
        stopD, tgtD, int(flat), int(maxhold), allow.astype(np.bool_), n, float(entry_slip))
    cost = rt + stop_slip * (why == STOP)
    return dict(eb=eb, xb=xb, side=sd, why=why, gross=gross, amb=amb,
                pnl=(gross - cost) * PV, n=len(eb), sess=b["si"][eb])


# ------------------------------------------------------------------ scoring
def score(t, mask=None):
    p = t["pnl"] if mask is None else t["pnl"][mask]
    if len(p) == 0:
        return dict(n=0, net=0.0, pf=np.nan, win=np.nan, per=np.nan, exp=np.nan)
    w = p[p > 0].sum(); l = -p[p < 0].sum()
    return dict(n=len(p), net=float(p.sum()),
                pf=float(w / l) if l > 0 else np.inf,
                win=float(100 * (p > 0).mean()),
                per=float(p.mean()),
                sharpe=float(p.mean() / p.std(ddof=1)) if len(p) > 1 and p.std(ddof=1) > 0 else np.nan)


# ------------------------------------------------------------------ fixed-entry walk (controls)
@njit(cache=True)
def _walk_fixed(s0, s1, t30h, t30l, t30o, t30mod, si,
                ent, sides, stopD, tgtD, flatm, n, entry_slip, nolap):
    """Walk a GIVEN list of (signal bar, side) with the same geometry and no-overlap rule.

    Used by the matched control, which needs entries that did not come from the rule. Everything
    downstream of the fill is identical to `_walk`, so a difference between the two can only be
    the choice of entry bar -- which is the whole point of the comparison.
    """
    k = len(ent)
    xb = np.empty(k, np.int64); why = np.empty(k, np.int64)
    gross = np.empty(k, np.float64); keep = np.empty(k, np.bool_)
    busy = -1
    for q in range(k):
        i = ent[q]; want = sides[q]
        keep[q] = False
        if (nolap == 0 and i < busy) or i + 1 >= n:
            continue
        sp = stopD[i]; tg = tgtD[i]
        if sp <= 0:
            continue
        j = i + 1
        fill = t30o[s0[j]] + entry_slip * want
        stop_px = fill - sp * want
        tgt_px = fill + tg * want if tg > 0 else np.nan
        p = s0[j]; lim = s1[n - 1]; res = 0; px = np.nan; last_bar = j
        while p < lim:
            while last_bar + 1 < n and s0[last_bar + 1] <= p:
                last_bar += 1
            if si[last_bar] != si[i]:
                res = FLAT; px = t30o[p]; break
            if flatm > 0 and t30mod[p] >= flatm:
                res = FLAT; px = t30o[p]; break
            hh = t30h[p]; ll = t30l[p]
            hs = (ll <= stop_px) if want == 1 else (hh >= stop_px)
            ht = False
            if tg > 0:
                ht = (hh >= tgt_px) if want == 1 else (ll <= tgt_px)
            if hs:
                res = STOP; px = stop_px; break
            if ht:
                res = TARGET; px = tgt_px; break
            p += 1
        if res == 0:
            res = FLAT; px = t30o[lim - 1]
        while last_bar + 1 < n and s0[last_bar + 1] <= p:
            last_bar += 1
        xb[q] = last_bar; why[q] = res; gross[q] = (px - fill) * want
        keep[q] = True
        busy = last_bar + 1
    return xb, why, gross, keep


def run_fixed(b, ent, sides, stopD, tgtD, flat=960, rt=RT_PTS, stop_slip=STOP_SLIP,
              entry_slip=0.0, nolap=False):
    """`nolap=True` drops the one-position lock, so EVERY entry gets an outcome.

    That is what the meta layer has to be trained on: it answers "was this event worth taking?"
    for each event on its own, and a training set that silently omits the events the lock skipped
    is conditioned on the lock, which depends on which OTHER events were taken.
    """
    o = np.argsort(ent, kind="stable")
    ent = np.asarray(ent, np.int64)[o]; sides = np.asarray(sides, np.int64)[o]
    xb, why, gross, keep = _walk_fixed(
        b["s0"], b["s1"], b["t30h"], b["t30l"], b["t30o"], b["t30mod"], b["si"],
        ent, sides, np.nan_to_num(stopD, nan=-1.0), np.nan_to_num(tgtD, nan=0.0),
        int(flat), b["n"], float(entry_slip), 1 if nolap else 0)
    eb = ent[keep]; why = why[keep]; gross = gross[keep]; xb = xb[keep]
    cost = rt + stop_slip * (why == STOP)
    return dict(eb=eb, xb=xb, side=sides[keep], why=why, gross=gross,
                pnl=(gross - cost) * PV, n=len(eb), sess=b["si"][eb])


@njit(cache=True)
def _events(hitU, hitD, si, n):
    """The bars the primary actually EMITS, independent of the one-position lock.

    Same state machine as `_walk`'s first-break bookkeeping -- first break per session per side,
    a simultaneous two-sided break resolving long, and a break of either side burning that side
    for the session. What it deliberately does NOT apply is the position lock, because whether an
    event exists must not depend on which OTHER events happened to be open at the time. That
    coupling is fine in a backtest and fatal in a training set.
    """
    eb = np.empty(n, np.int64); sd = np.empty(n, np.int64)
    k = 0; tookU = False; tookD = False; cur = -1
    for i in range(n - 1):
        if si[i] != cur:
            cur = si[i]; tookU = False; tookD = False
        u = hitU[i]; d = hitD[i]
        if not (u or d):
            continue
        want = 0
        if u and not tookU:
            want = 1
        elif d and not tookD:
            want = -1
        if u:
            tookU = True
        if d:
            tookD = True
        if want != 0:
            eb[k] = i; sd[k] = want; k += 1
    return eb[:k], sd[:k]


def events(b, r0, r1, arm, last, atr, buf=0.0, side="both", touch=True):
    hitU, hitD, _u, _d = triggers(b, r0, r1, arm, last, atr, buf, side, touch)
    return _events(hitU.astype(np.bool_), hitD.astype(np.bool_), b["si"], b["n"])


# ------------------------------------------------------------------ the shipped Pine's extras
@njit(cache=True)
def _walk_be(s0, s1, t30h, t30l, t30o, t30mod, si,
             ent, sides, stopD, tgtD, flatm, n, be_arm, be_off, nolap):
    """`_walk_fixed` plus the points breakeven ratchet, with the fill model its own Pine warns about.

    THE RATCHET ARMS on the 30-second bar whose favourable extreme reaches `be_arm` from the fill,
    and the moved stop only BINDS from the bar after -- within one bar the path cannot say whether
    the excursion came before or after the pullback, and arming plus filling on the same bar
    invents that information.

    THE MOVED STOP FILLS AT THE WORSE OF ITS LEVEL AND THE NEXT BAR'S OPEN. When the secured
    offset is near the arming distance the ratchet writes a sell stop ABOVE the market (the high
    touched +43, the bar closed at +8, the stop goes to +5), and a walker that pays it at its
    level is booking a fill that could not happen. The Pine header records this artifact as worth
    up to -11.0 points a trade, so it is modelled rather than inherited.
    """
    k = len(ent)
    xb = np.empty(k, np.int64); why = np.empty(k, np.int64)
    gross = np.empty(k, np.float64); keep = np.empty(k, np.bool_)
    busy = -1
    for q in range(k):
        i = ent[q]; want = sides[q]
        keep[q] = False
        if (nolap == 0 and i < busy) or i + 1 >= n:
            continue
        sp = stopD[i]; tg = tgtD[i]
        if sp <= 0:
            continue
        j = i + 1
        fill = t30o[s0[j]]
        stop_px = fill - sp * want
        tgt_px = fill + tg * want if tg > 0 else np.nan
        armed = False
        p = s0[j]; lim = s1[n - 1]; res = 0; px = np.nan; last_bar = j
        while p < lim:
            while last_bar + 1 < n and s0[last_bar + 1] <= p:
                last_bar += 1
            if si[last_bar] != si[i]:
                res = FLAT; px = t30o[p]; break
            if flatm > 0 and t30mod[p] >= flatm:
                res = FLAT; px = t30o[p]; break
            hh = t30h[p]; ll = t30l[p]
            hs = (ll <= stop_px) if want == 1 else (hh >= stop_px)
            ht = False
            if tg > 0:
                ht = (hh >= tgt_px) if want == 1 else (ll <= tgt_px)
            if hs and ht:
                res = STOP; px = stop_px; break
            if hs:
                # a stop already through the market fills at the open, not at its level
                o_ = t30o[p]
                px = stop_px
                if want == 1 and o_ < stop_px:
                    px = o_
                elif want == -1 and o_ > stop_px:
                    px = o_
                res = STOP; break
            if ht:
                res = TARGET; px = tgt_px; break
            if be_arm > 0 and not armed:
                fav = (hh - fill) if want == 1 else (fill - ll)
                if fav >= be_arm:
                    armed = True
                    stop_px = fill + be_off * want      # binds from the NEXT bar
            p += 1
        if res == 0:
            res = FLAT; px = t30o[lim - 1]
        while last_bar + 1 < n and s0[last_bar + 1] <= p:
            last_bar += 1
        xb[q] = last_bar; why[q] = res; gross[q] = (px - fill) * want
        keep[q] = True
        busy = last_bar + 1
    return xb, why, gross, keep


def run_be(b, ent, sides, stopD, tgtD, flat=960, be_arm=0.0, be_off=0.0,
           rt=RT_PTS, stop_slip=STOP_SLIP, nolap=False):
    o = np.argsort(ent, kind="stable")
    ent = np.asarray(ent, np.int64)[o]; sides = np.asarray(sides, np.int64)[o]
    xb, why, gross, keep = _walk_be(
        b["s0"], b["s1"], b["t30h"], b["t30l"], b["t30o"], b["t30mod"], b["si"],
        ent, sides, np.nan_to_num(stopD, nan=-1.0), np.nan_to_num(tgtD, nan=0.0),
        int(flat), b["n"], float(be_arm), float(be_off), 1 if nolap else 0)
    eb = ent[keep]
    cost = rt + stop_slip * (why[keep] == STOP)
    return dict(eb=eb, xb=xb[keep], side=sides[keep], why=why[keep], gross=gross[keep],
                pnl=(gross[keep] - cost) * PV, n=len(eb), sess=b["si"][eb])


def ma_gate(b, mode="fresh", fast=13, slow=48, long_=200, recency_min=7, tf=None):
    """The Pine's MA confirmation, as two masks read at the SIGNAL bar.

    `recency_min` is a reach in TIME converted with the bar size, which is how the Pine declares
    it, so the same number means the same thing on any chart.
    """
    from bars import ema
    tf = tf or b["tf"]
    nbar = max(1, int(round(recency_min / tf)))
    c = b["c"]
    mf, ms, ml = ema(c, fast), ema(c, slow), ema(c, long_)
    bull = mf > ms
    up = bull & ~np.concatenate(([False], bull[:-1]))
    dn = (~bull) & np.concatenate(([False], bull[:-1]))
    ageU = _age(up); ageD = _age(dn)
    if mode == "state":
        return bull, ~bull
    if mode == "fresh":
        return ageU <= nbar, ageD <= nbar
    if mode == "200state":
        return (mf > ml) & (ms > ml), (mf < ml) & (ms < ml)
    return np.ones(b["n"], bool), np.ones(b["n"], bool)


def _age(flag):
    out = np.full(len(flag), 10**6, np.int64); k = 10**6
    for i in range(len(flag)):
        k = 0 if flag[i] else k + 1
        out[i] = k
    return out
