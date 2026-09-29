"""INITIAL BALANCE RETRACEMENT ON US30 -- Phase 0, written before any number.

MECHANISM (named, so the primary can be tested without its features)
  The Initial Balance breakout-retracement is a RESTING LIMIT INSIDE A RANGE placed after the
  range breaks. The counterparty is the breakout chaser: a trader who buys the break of the
  first-hour high, is shaken out on the first pullback, and sells that pullback to the limit.
  `STUDY_V58_ANATOMY` measured this directly -- the edge is MONOTONE in the retracement depth
  (buy the break itself: p 1.000; 50% back inside: +0.3087 ATR/trade, p 0.000 on NQ) and the
  Initial Balance is only the ruler the limit is priced in. The prediction that follows, and the
  one Gate 1 tests: the primary's edge must grow with retracement depth and must vanish at zero
  retracement. A primary that earns as much chasing the break as fading it is not this mechanism.

WHAT THE RECORD ALREADY SAYS ABOUT US30, so nothing here is a surprise dressed as a discovery
  `STUDY_V58_INITIAL_BALANCE`: 777,600 cells on US30, 13% profitable on research, EVERY marginal
  negative at every setting of every axis, the published geometry PF 0.83 / 0.78, losing to a
  risk-matched random entry at p 0.76-0.99. The one positive cluster was on NQ (48 trades).
  So the prior is that Gate 1 FAILS on US30. The study is built to let it fail cleanly.

THE PRIMARY (parameters continuous so Optuna has a space, but each one named and counted)
  ib_min   length of the Initial Balance from 09:30 New York, in minutes   {30, 45, 60, 90}
  retr     entry: fraction of the IB range back INSIDE the broken edge     [0.00, 0.60]
  stopf    stop: fraction of the IB range from the broken edge             (retr, 1.60]
  tgt      target: fraction of the range BEYOND the edge, or none          [0.25, 3.00] | none
  flat_min hard flatten, minutes past midnight New York                    {13:00, 15:00, 15:55}
  side     long / short / both (first break decides)
  ib_atr_min, ib_atr_max   IB range as a multiple of ATR(14) at the plan bar -- the user's
           min/max IB filter restated in ATR units, because points are not stable over 9 years.

UNITS. Scored in PERCENT OF ENTRY PRICE for one unit, never in R: `STUDY_V58` found the risk
  `(stopf - retr) x range` can be driven to a tenth of the range, and ranking in R put an
  11.6-point stop at 10:1 on top. R is reported as a diagnostic only.

FILL BAR. The stop is tested ON THE FILL BAR (`STUDY_V58`: skipping it hands 49.5% of the grid a
  free option). No fill on the break bar itself (it spans time before the break).

BLOCKS. US30_LONG_15m 2016-10 .. 2025-07: research = first 65% of sessions (to 2022-06-29),
  locked = the rest, read ONCE at the end. US30_ISO_15m (2024-08 .. 2026-08, a DIFFERENT
  provider) is a second reserved read where its span exceeds the LONG file.

COSTS. The branch's measured US30 CFD stack: 1.72 points round turn including slippage
  (`research/v58/v58ib.COST_PTS`). 0x and 2x are run as arms.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from research.v38.v38feeds import load as _load_long   # noqa: E402

IB_OPEN = 9 * 60 + 30
SPLIT = 0.65
COST_PTS = {"US30L": 1.72, "US30I": 1.72}
FLAT_CHOICES = (13 * 60, 15 * 60, 15 * 60 + 55)
IB_CHOICES = (30, 45, 60, 90)


def load(name):
    if name == "US30I":
        d = pd.read_csv("data/US30_ISO_15m.csv", parse_dates=["ny"])
        f = pd.DataFrame({k: d[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume")},
                         index=pd.DatetimeIndex(d["ny"]))
        f = f.sort_index()
        return f[~f.index.duplicated(keep="first")]
    return _load_long(name)


def _atr(h, l, c, n=14):
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def build(name):
    f = load(name)
    o, h, l, c = (f[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    v = f["volume"].to_numpy(float)
    ix = f.index
    mod = (ix.hour * 60 + ix.minute).to_numpy(np.int64)
    dayid = ix.normalize().values.astype("datetime64[D]").astype(np.int64)
    wd = ix.dayofweek.to_numpy()
    edge = np.flatnonzero(np.diff(dayid) != 0) + 1
    starts = np.concatenate([[0], edge]); ends = np.concatenate([edge, [len(c)]])
    keep = wd[starts] < 5
    starts, ends = starts[keep], ends[keep]
    # a day is usable only if it carries the 09:30 open bar
    ok = np.array([((mod[a:b] == IB_OPEN).any()) for a, b in zip(starts, ends)])
    starts, ends = starts[ok], ends[ok]
    D = len(starts)
    cut = int(SPLIT * D)
    blk = np.zeros(D, np.int64); blk[cut:] = 1
    return dict(name=name, o=o, h=h, l=l, c=c, v=v, mod=mod, ix=ix, atr=_atr(h, l, c),
                starts=starts, ends=ends, D=D, blk=blk, cut_date=ix[starts[cut]].date(),
                dates=ix.normalize().values[starts], cost=COST_PTS.get(name, 1.72))


@njit(cache=True)
def _walk(o, h, l, c, atr, mod, starts, ends, ib_min, retr, stopf, tgt, flat_min, side_mode,
          ib_atr_min, ib_atr_max, cost, out_pct, out_pts, out_R, out_side, out_why, out_risk,
          out_plan, out_fill):
    """One trade per day at most. side_mode 0 long only, 1 short only, 2 both (first break).
    why: 0 stop, 1 target, 2 flatten, -1 no trade."""
    D = len(starts)
    for d in range(D):
        a, b = starts[d], ends[d]
        out_why[d] = -1
        hi = -1e18; lo = 1e18; last = -1; first_after = -1; flat_bar = -1
        for i in range(a, b):
            m = mod[i]
            if m >= IB_OPEN and m < IB_OPEN + ib_min:
                if h[i] > hi: hi = h[i]
                if l[i] < lo: lo = l[i]
                last = i
            elif m >= IB_OPEN + ib_min and first_after < 0:
                first_after = i
            if m >= flat_min and flat_bar < 0:
                flat_bar = i
        if last < 0 or first_after < 0 or hi <= lo:
            continue
        if flat_bar < 0:
            flat_bar = b
        if flat_bar <= first_after:
            continue
        rng = hi - lo
        A = atr[last]
        if not (A > 0):
            continue
        if ib_atr_min > 0 and rng < ib_atr_min * A:
            continue
        if ib_atr_max > 0 and rng > ib_atr_max * A:
            continue
        out_plan[d] = last
        # the break
        brk = -1; side = 0
        for i in range(first_after, flat_bar):
            bu = h[i] > hi and side_mode != 1
            bd = l[i] < lo and side_mode != 0
            if bu and bd:
                side = 0 if c[i] >= o[i] else 1
                brk = i; break
            if bu:
                side = 0; brk = i; break
            if bd:
                side = 1; brk = i; break
        if brk < 0:
            continue
        ent = hi - rng * retr if side == 0 else lo + rng * retr
        stp = hi - rng * stopf if side == 0 else lo + rng * stopf
        risk = (ent - stp) if side == 0 else (stp - ent)
        if risk <= 0:
            continue
        if tgt >= 90.0:
            tp = 1e18 if side == 0 else -1e18
        else:
            tp = hi + rng * tgt if side == 0 else lo - rng * tgt
        fill = -1
        for i in range(brk + 1, flat_bar):
            if side == 0:
                if l[i] <= ent:
                    fill = i; break
            else:
                if h[i] >= ent:
                    fill = i; break
        if fill < 0:
            continue
        # fill price: the limit, unless the bar OPENED through it
        px = ent
        if side == 0 and o[fill] < ent:
            px = o[fill]
        if side == 1 and o[fill] > ent:
            px = o[fill]
        pts = 0.0; done = False; why = 2
        # stop tested on the fill bar itself. If the bar OPENED beyond the stop the limit filled
        # at that open and the stop is already breached, so the exit is the open as well.
        if side == 0:
            if l[fill] <= stp:
                xs = stp if o[fill] > stp else o[fill]
                pts = xs - px; done = True; why = 0
        else:
            if h[fill] >= stp:
                xs = stp if o[fill] < stp else o[fill]
                pts = px - xs; done = True; why = 0
        i = fill + 1
        while (not done) and i < flat_bar:
            # a gap through the stop fills at the open (worse); a gap through the target fills at
            # the open (better). Stop first when both sit inside one bar.
            if side == 0:
                if l[i] <= stp:
                    xs = stp if o[i] > stp else o[i]
                    pts = xs - px; done = True; why = 0
                elif h[i] >= tp:
                    xt = tp if o[i] < tp else o[i]
                    pts = xt - px; done = True; why = 1
            else:
                if h[i] >= stp:
                    xs = stp if o[i] < stp else o[i]
                    pts = px - xs; done = True; why = 0
                elif l[i] <= tp:
                    xt = tp if o[i] > tp else o[i]
                    pts = px - xt; done = True; why = 1
            i += 1
        if not done:
            # flatten at the CLOSE of the last bar BEFORE the flatten time. On this CFD feed the
            # first bar at/after 15:55 is the 18:30 re-open on 1,247 of 2,246 days (the 16:00 bar
            # exists on 153), so an open-of-next-bar flatten would hold through the cash close.
            xp = c[flat_bar - 1]
            pts = (xp - px) if side == 0 else (px - xp)
            why = 2
        pts -= cost
        out_pts[d] = pts
        out_pct[d] = 100.0 * pts / px
        out_R[d] = pts / risk
        out_side[d] = side
        out_why[d] = why
        out_risk[d] = risk
        out_fill[d] = fill


def run(F, ib_min=60, retr=0.25, stopf=0.60, tgt=0.50, flat_min=15 * 60 + 55, side="both",
        ib_atr_min=0.0, ib_atr_max=0.0, cost=None):
    D = F["D"]
    cost = F["cost"] if cost is None else cost
    sm = {"long": 0, "short": 1, "both": 2}[side]
    pct = np.full(D, np.nan); pts = np.full(D, np.nan); R = np.full(D, np.nan)
    sd = np.full(D, -1, np.int64); why = np.full(D, -1, np.int64); risk = np.full(D, np.nan)
    plan = np.full(D, -1, np.int64); fill = np.full(D, -1, np.int64)
    _walk(F["o"], F["h"], F["l"], F["c"], F["atr"], F["mod"], F["starts"], F["ends"],
          int(ib_min), float(retr), float(stopf), float(tgt), int(flat_min), sm,
          float(ib_atr_min), float(ib_atr_max), float(cost),
          pct, pts, R, sd, why, risk, plan, fill)
    t = pd.DataFrame(dict(day=np.arange(D), pct=pct, pts=pts, R=R, side=sd, why=why, risk=risk,
                          plan=plan, fill=fill, blk=F["blk"], date=F["dates"]))
    return t[t.why >= 0].reset_index(drop=True)


def stats(t):
    if len(t) == 0:
        return dict(n=0, pct=np.nan, tot=np.nan, pf=np.nan, win=np.nan, dd=np.nan, ret_dd=np.nan,
                    R=np.nan)
    p = t.pct.to_numpy(); cum = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(cum) - cum)) if len(cum) else 0.0
    return dict(n=int(len(t)), pct=float(p.mean()), tot=float(p.sum()),
                pf=float(p[p > 0].sum() / max(-p[p < 0].sum(), 1e-9)),
                win=float(100 * (p > 0).mean()), dd=dd, ret_dd=float(p.sum() / max(dd, 1e-9)),
                R=float(t.R.mean()))


@njit(cache=True)
def _control(o, h, l, c, mod, starts, ends, days, ib_min, retr, stopf, tgt, flat_min,
             side_mode, ib_atr_min, ib_atr_max, atr, cost, draws, seed, out):
    """Risk-matched random entry: the same day, the same side the rule took, the same risk and
    reward IN POINTS, entered at the CLOSE of a random bar between the IB end and the flatten.
    `STUDY_TURTLE_YOUTUBE`: match the risk trade for trade, not just the exits."""
    np.random.seed(seed)
    for k in range(draws):
        s = 0.0; n = 0
        for j in range(len(days)):
            d = days[j]
            a, b = starts[d], ends[d]
            hi = -1e18; lo = 1e18; last = -1; first_after = -1; flat_bar = -1
            for i in range(a, b):
                m = mod[i]
                if m >= IB_OPEN and m < IB_OPEN + ib_min:
                    if h[i] > hi: hi = h[i]
                    if l[i] < lo: lo = l[i]
                    last = i
                elif m >= IB_OPEN + ib_min and first_after < 0:
                    first_after = i
                if m >= flat_min and flat_bar < 0:
                    flat_bar = i
            if last < 0 or first_after < 0 or hi <= lo:
                continue
            if flat_bar < 0:
                flat_bar = b
            if flat_bar - first_after < 3:
                continue
            rng = hi - lo
            A = atr[last]
            if ib_atr_min > 0 and rng < ib_atr_min * A:
                continue
            if ib_atr_max > 0 and rng > ib_atr_max * A:
                continue
            # the side the rule would take on this day
            side = -1
            for i in range(first_after, flat_bar):
                bu = h[i] > hi and side_mode != 1
                bd = l[i] < lo and side_mode != 0
                if bu and bd:
                    side = 0 if c[i] >= o[i] else 1; break
                if bu:
                    side = 0; break
                if bd:
                    side = 1; break
            if side < 0:
                continue
            i0 = first_after + np.random.randint(0, flat_bar - first_after - 1)
            ent = c[i0]
            risk = rng * (stopf - retr)
            if risk <= 0:
                continue
            rew = rng * (tgt + retr) if tgt < 90.0 else 1e18
            stp = ent - risk if side == 0 else ent + risk
            tp = ent + rew if side == 0 else ent - rew
            pts = 0.0; done = False
            for i in range(i0 + 1, flat_bar):
                if side == 0:
                    if l[i] <= stp:
                        xs = stp if o[i] > stp else o[i]
                        pts = xs - ent; done = True; break
                    if h[i] >= tp:
                        xt = tp if o[i] < tp else o[i]
                        pts = xt - ent; done = True; break
                else:
                    if h[i] >= stp:
                        xs = stp if o[i] < stp else o[i]
                        pts = ent - xs; done = True; break
                    if l[i] <= tp:
                        xt = tp if o[i] > tp else o[i]
                        pts = ent - xt; done = True; break
            if not done:
                xp = c[flat_bar - 1]
                pts = (xp - ent) if side == 0 else (ent - xp)
            s += 100.0 * (pts - cost) / ent
            n += 1
        out[k] = s / n if n > 0 else np.nan


def control(F, days, ib_min=60, retr=0.25, stopf=0.60, tgt=0.50, flat_min=15 * 60 + 55,
            side="both", ib_atr_min=0.0, ib_atr_max=0.0, cost=None, draws=1000, seed=7):
    cost = F["cost"] if cost is None else cost
    sm = {"long": 0, "short": 1, "both": 2}[side]
    out = np.full(draws, np.nan)
    _control(F["o"], F["h"], F["l"], F["c"], F["mod"], F["starts"], F["ends"],
             np.asarray(days, np.int64), int(ib_min), float(retr), float(stopf), float(tgt),
             int(flat_min), sm, float(ib_atr_min), float(ib_atr_max), F["atr"], float(cost),
             int(draws), int(seed), out)
    return out[np.isfinite(out)]
