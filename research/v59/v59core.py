"""V59 -- an EMA 16/64 trend follower with a hard four-hour ceiling, swept as an exit tensor.

THE BRIEF: cross of the 16 and 64 EMAs, ADX and ATR as conditions, no trade held longer than
four hours, and a hundred thousand combinations to find the most robust version.

WHY IT IS A TENSOR. A trade's outcome depends only on its SIGNAL BAR and its GEOMETRY -- never on
which indicator fired -- so the price is walked once per (signal bar, geometry) and every filtered
configuration becomes an array lookup plus a position-lock pass over the signal bars. 243,000
configurations per market cost one walk.

THREE THINGS ARE CARRIED OVER FROM V58 AND ARE NOT OPTIONAL:

  * SCORING IS IN ATR UNITS AT THE SIGNAL BAR, never in R. The stop is a swept ATR multiple, so
    R = points / (stop x ATR) and ranking in R pays a configuration for tightening its own
    denominator. `STUDY_V58_INITIAL_BALANCE.md`, `STUDY_SWEEP_110K.md`.
  * EVERYTHING IS READ AT THE SIGNAL BAR, and the entry is the NEXT bar's open. Reading a
    condition at the fill bar is the `ent_bar` leak (`STUDY_AUCTION.md`).
  * THE ENTRY BAR CARRIES ITS OWN STOP. An exit order is live from the moment the position is,
    which is what a script actually does; exempting the entry bar is worth real money to half a
    grid (`STUDY_V58`).

CALENDAR CONDITIONS ARE BANNED. Sessions are a swept axis because the brief is intraday, and the
branch's own record on that axis is eleven negatives, so it is present to be measured, not
assumed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit, prange

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.v38.v38feeds import load                                  # noqa: E402

EMA_FAST, EMA_SLOW = 16, 64
MAX_HOLD_H = 4.0

# ---- swept axes ------------------------------------------------------------------------------
MODE = ["cross", "breakout confirm", "pullback to EMA16"]     # the entry mechanic
STOPM = np.array([0.5, 1.0, 1.5, 2.0, 2.5, 3.0])              # ATR multiples
TGTM = np.array([1.0, 1.5, 2.0, 3.0, 99.0])                   # R multiples of the stop; 99 = none
HOLD = np.array([4, 8, 12, 16], np.int64)                     # bars: 1h, 2h, 3h, 4h at 15m
TRAIL = ["fixed", "breakeven at 1R", "ATR trail"]
SESS = ["all hours", "09:30-16:00", "09:30-12:00"]
NG = len(STOPM) * len(TGTM) * len(HOLD) * len(TRAIL) * len(SESS)

ADX_MODE = ["off", "adx>=15", "adx>=20", "adx>=25", "adx<=20"]
ATR_MODE = ["off", "atr>=0.8x", "atr>=1.2x", "atr<=1.2x", "atr<=0.8x"]
NF = len(ADX_MODE) * len(ATR_MODE)

COST_PTS = {"US30L": 1.72, "US100L": 1.215, "NQ": 0.72}
SESS_WIN = np.array([[0, 1440], [570, 960], [570, 720]], np.int64)


def _ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def _adx(h, l, c, n=14):
    up, dn = np.diff(h, prepend=h[0]), -np.diff(l, prepend=l[0])
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    tr[0] = h[0] - l[0]
    a = pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    pdi = 100 * pd.Series(pdm).ewm(alpha=1 / n, adjust=False).mean().to_numpy() / np.maximum(a, 1e-9)
    ndi = 100 * pd.Series(ndm).ewm(alpha=1 / n, adjust=False).mean().to_numpy() / np.maximum(a, 1e-9)
    dx = 100 * np.abs(pdi - ndi) / np.maximum(pdi + ndi, 1e-9)
    return pd.Series(dx).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def build(name, frame=None):
    f = load(name) if frame is None else frame
    o, h, l, c = (f[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    ix = f.index
    mod = (ix.hour * 60 + ix.minute).to_numpy(np.int64)
    day = ix.normalize().values.astype("datetime64[D]").astype(np.int64)
    ef, es = _ema(c, EMA_FAST), _ema(c, EMA_SLOW)
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    tr[0] = h[0] - l[0]
    atr = pd.Series(tr).ewm(span=14, adjust=False).mean().to_numpy()
    adx = _adx(h, l, c)
    # the ATR regime is against its OWN trailing median, shifted, never a whole-sample quantile
    med = pd.Series(atr).rolling(480, min_periods=120).median().shift(1).to_numpy()
    return dict(o=o, h=h, l=l, c=c, mod=mod, day=day, ef=ef, es=es, atr=atr, adx=adx,
                atr_ratio=atr / np.where(np.isfinite(med) & (med > 0), med, np.nan),
                n=len(c), index=ix)


def signals(F, mode, side):
    """Signal bars. Everything is read at the signal bar; the entry is the NEXT bar's open.

    mode 0  the cross bar itself
    mode 1  after a cross, the first bar CLOSING beyond the cross bar's extreme -- confirmation
    mode 2  after a cross, the first bar TOUCHING the fast EMA -- a pullback entry
    Modes 1 and 2 expire if the cross reverses before they trigger, so a signal always belongs to
    the cross that is still live.
    """
    ef, es, c, h, l = F["ef"], F["es"], F["c"], F["h"], F["l"]
    up = (ef > es) & (np.roll(ef, 1) <= np.roll(es, 1))
    dn = (ef < es) & (np.roll(ef, 1) >= np.roll(es, 1))
    up[0] = dn[0] = False
    cross = up if side == 0 else dn
    live = (ef > es) if side == 0 else (ef < es)
    ci = np.flatnonzero(cross)
    if mode == 0:
        return ci[(ci > EMA_SLOW * 3) & (ci < F["n"] - 20)]
    out = []
    for k in ci:
        if k <= EMA_SLOW * 3:
            continue
        ref = h[k] if side == 0 else l[k]
        for j in range(k + 1, min(k + 40, F["n"] - 20)):
            if not live[j]:
                break
            if mode == 1:
                if (side == 0 and c[j] > ref) or (side == 1 and c[j] < ref):
                    out.append(j)
                    break
            else:
                if (side == 0 and l[j] <= ef[j]) or (side == 1 and h[j] >= ef[j]):
                    out.append(j)
                    break
    return np.asarray(sorted(set(out)), np.int64)


@njit(cache=True, parallel=True)
def _walk(o, h, l, c, mod, atr, sig, stopm, tgtm, hold, sesswin, side, cost,
          out_pts, out_exit):
    """Points and exit bar per (signal, geometry). Entry is the next bar's OPEN and the stop is
    live on that bar. A trade is never held past `hold` bars or past the session's end."""
    NS, NT, NH, NR, NW = len(stopm), len(tgtm), len(hold), 3, sesswin.shape[0]
    n = len(c)
    for k in prange(len(sig)):
        i = sig[k]
        e = i + 1
        if e >= n - 1:
            continue
        ent = o[e]
        a = atr[i]
        for wi in range(NW):
            lo_m, hi_m = sesswin[wi, 0], sesswin[wi, 1]
            if mod[i] < lo_m or mod[i] >= hi_m:
                continue
            for si in range(NS):
                risk = stopm[si] * a
                if risk <= 0:
                    continue
                stp0 = ent - risk if side == 0 else ent + risk
                for ti in range(NT):
                    tp = (ent + tgtm[ti] * risk if side == 0 else ent - tgtm[ti] * risk) \
                        if tgtm[ti] < 90.0 else (1e18 if side == 0 else -1e18)
                    for hi_ in range(NH):
                        for tr in range(NR):
                            stp = stp0
                            peak = ent
                            px = c[min(e + hold[hi_] - 1, n - 1)]
                            xb = min(e + hold[hi_] - 1, n - 1)
                            done = False
                            for j in range(e, min(e + hold[hi_], n)):
                                if mod[j] >= hi_m and hi_m < 1440:
                                    px = o[j]
                                    xb = j
                                    done = True
                                    break
                                if side == 0:
                                    if l[j] <= stp:
                                        px = stp; xb = j; done = True; break
                                    if h[j] >= tp:
                                        px = tp; xb = j; done = True; break
                                    if h[j] > peak:
                                        peak = h[j]
                                    if tr == 1 and peak - ent >= risk and stp < ent:
                                        stp = ent
                                    elif tr == 2:
                                        t2 = peak - risk
                                        if t2 > stp:
                                            stp = t2
                                else:
                                    if h[j] >= stp:
                                        px = stp; xb = j; done = True; break
                                    if l[j] <= tp:
                                        px = tp; xb = j; done = True; break
                                    if l[j] < peak:
                                        peak = l[j]
                                    if tr == 1 and ent - peak >= risk and stp > ent:
                                        stp = ent
                                    elif tr == 2:
                                        t2 = peak + risk
                                        if t2 < stp:
                                            stp = t2
                                if not done:
                                    px = c[j]
                                    xb = j
                            g = ((((si * NT + ti) * NH + hi_) * NR + tr) * NW + wi)
                            out_pts[k, g] = ((px - ent) if side == 0 else (ent - px)) - cost
                            out_exit[k, g] = xb


def outcomes(F, sig, side, cost):
    pts = np.full((len(sig), NG), np.nan)
    xb = np.full((len(sig), NG), -1, np.int64)
    if len(sig):
        _walk(F["o"], F["h"], F["l"], F["c"], F["mod"], F["atr"], sig,
              STOPM, TGTM, HOLD, SESS_WIN, side, float(cost), pts, xb)
    return pts, xb


@njit(cache=True, parallel=True)
def _lock(pts, xb, sig, keep, dayid, ndays, out):
    """Position lock plus the daily moments, in one pass over the signal bars.

    A signal is skipped while the previous trade is still open -- without this a `strategy` can
    silently be a portfolio of overlapping positions (`STUDY_ATME`). Daily totals are accumulated
    as the walk goes so Sharpe can be taken over EVERY trading day in the block, zero-filled on
    days that did not trade: over traded days only, a filter is paid for trading less.

    out columns: 0 sum, 1 n, 2 gross positive, 3 gross negative, 4 sum of squared DAILY totals.
    """
    NGg = pts.shape[1]
    for g in prange(NGg):
        last = -1
        s = 0.0; nn = 0.0; pp = 0.0; ng = 0.0; sq = 0.0
        cur_day = -1
        cur_tot = 0.0
        for k in range(len(sig)):
            if not keep[k]:
                continue
            if sig[k] <= last:
                continue
            v = pts[k, g]
            if not np.isfinite(v):
                continue
            last = xb[k, g]
            d = dayid[k]
            if d != cur_day:
                if cur_day >= 0:
                    sq += cur_tot * cur_tot
                cur_day = d
                cur_tot = 0.0
            cur_tot += v
            s += v; nn += 1.0
            if v > 0:
                pp += v
            else:
                ng += v
        if cur_day >= 0:
            sq += cur_tot * cur_tot
        out[g, 0] = s; out[g, 1] = nn; out[g, 2] = pp; out[g, 3] = ng; out[g, 4] = sq


@njit(cache=True, parallel=True)
def _lock2(ptsA, xbA, sigA, keepA, dayA, ptsB, xbB, sigB, keepB, dayB, out):
    """The same lock with BOTH sides sharing one position -- a long and a short cannot be open at
    the same time, and merging two independently-locked streams would pretend they can."""
    NGg = ptsA.shape[1]
    for g in prange(NGg):
        last = -1
        s = 0.0; nn = 0.0; pp = 0.0; ng = 0.0; sq = 0.0
        cur_day = -1
        cur_tot = 0.0
        ia = 0; ib = 0
        while ia < len(sigA) or ib < len(sigB):
            takeA = False
            if ia >= len(sigA):
                pass
            elif ib >= len(sigB):
                takeA = True
            elif sigA[ia] <= sigB[ib]:
                takeA = True
            if takeA:
                k = ia; ia += 1
                sg = sigA[k]; kp = keepA[k]; v = ptsA[k, g]; xe = xbA[k, g]; d = dayA[k]
            else:
                k = ib; ib += 1
                sg = sigB[k]; kp = keepB[k]; v = ptsB[k, g]; xe = xbB[k, g]; d = dayB[k]
            if not kp or sg <= last or not np.isfinite(v):
                continue
            last = xe
            if d != cur_day:
                if cur_day >= 0:
                    sq += cur_tot * cur_tot
                cur_day = d
                cur_tot = 0.0
            cur_tot += v
            s += v; nn += 1.0
            if v > 0:
                pp += v
            else:
                ng += v
        if cur_day >= 0:
            sq += cur_tot * cur_tot
        out[g, 0] = s; out[g, 1] = nn; out[g, 2] = pp; out[g, 3] = ng; out[g, 4] = sq


def geom_name(g):
    wi = g % len(SESS); g //= len(SESS)
    tr = g % len(TRAIL); g //= len(TRAIL)
    hi = g % len(HOLD); g //= len(HOLD)
    ti = g % len(TGTM); g //= len(TGTM)
    si = g
    return dict(stop=float(STOPM[si]), tgt=float(TGTM[ti]), hold=int(HOLD[hi]),
                trail=TRAIL[tr], sess=SESS[wi])


def filt_name(f):
    a = f // len(ATR_MODE)
    return dict(adx=ADX_MODE[a], atr=ATR_MODE[f % len(ATR_MODE)])
