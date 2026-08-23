"""What TradingView's "Script execution" checkboxes actually do to a result.

The Strategy Tester offers four:

    On bar close          always on
    On order fill         re-run the script the moment an order fills, mid-bar
    On history bar tick   resolve historical bars tick by tick, not as one OHLC block
    On realtime bar tick  same, live

The research engine assumes exactly one of these. Signals are read at the close of a completed
bar, the fill is the next bar's open, and when a bar contains BOTH the stop and the target it
books the stop, because a 30-minute OHLC bar does not say which came first.

This module replaces that last assumption with the answer, by walking the 1-minute bars inside
each 30-minute bar. Three execution models, all on the same signals:

    A  pessimistic   both levels in one bar -> stop.  The engine's model.
    B  true path     both levels in one bar -> whichever the 1-minute path reached first.
    C  true path + refill   a new entry may open at the exit, in the same bar, rather than
                            waiting for the next bar's open. This is what "On order fill" adds.

It also measures entry-timing dispersion: the same signal filled at each 1-minute bar of the
following 30 minutes, which brackets what tick-level entry timing can do to the result.

WHAT IT DOES NOT SIMULATE, and why. "On history bar tick" and "On realtime bar tick" also
re-evaluate the ENTRY CONDITIONS on unfinished bars. A rule reading `close > EMA10` then fires
on a partial close that may be gone by the bar's end. That is not a different execution of the
same strategy -- it is a different strategy, one whose signals were never measured here, and
simulating it would be inventing a result rather than checking one. The honest answer is that
those two boxes take the script outside what the research covers.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, "research")
from bos_choch import load_bars, prep

PV = 2.0; TICK = 0.25; COMM = 1.0
EC = 2.0 * TICK; SE = 1.0 * TICK

_M1 = {}


def minute_map(tf=30):
    """For each tf-minute bar, the half-open range of 1-minute bars it is built from."""
    if tf in _M1:
        return _M1[tf]
    raw = load_bars("data/NQ_1m.csv")
    d = prep(tf)
    idx1 = raw.index.values
    edges = d["df"].index.values
    lo = np.searchsorted(idx1, edges, side="left")
    hi = np.searchsorted(idx1, edges + np.timedelta64(tf, "m"), side="left")
    m = dict(o=raw["open"].to_numpy(float), h=raw["high"].to_numpy(float),
             l=raw["low"].to_numpy(float), c=raw["close"].to_numpy(float),
             mod=(raw.index.hour * 60 + raw.index.minute).to_numpy(np.int64),
             lo=lo.astype(np.int64), hi=hi.astype(np.int64), d=d)
    _M1[tf] = m
    return m


@njit(cache=True)
def _walk(o1, h1, l1, c1, mod1, lo, hi, atr_, trig, side, atr_mult, tp_r, flat_min,
          refill, pv, comm, ec, se):
    """Walk the real 1-minute path. `refill` allows a new entry at the exit, in the same bar.

    A minute that contains both levels is still unresolvable, so it books the stop -- the same
    pessimism the engine applies to a whole 30-minute bar, now applied to 1/30th of one. How
    often that happens is returned, so the residue is measurable rather than assumed away.
    """
    n = len(lo); m = len(trig); cap = m * 3
    pnl = np.zeros(cap); eb = np.zeros(cap, np.int64); xb = np.zeros(cap, np.int64)
    why = np.zeros(cap, np.int64); amb = np.zeros(cap, np.int64)
    k = 0; free = -1
    for t in range(m):
        i = trig[t]
        if i < free:
            continue
        a = atr_[i]
        if np.isnan(a) or a <= 0.0 or i + 1 >= n:
            continue
        p = lo[i + 1]
        if p >= len(c1):
            break
        entry = o1[p]
        fills = 0
        while k < cap - 1:
            st = entry - side * atr_mult * a
            tg = entry + side * tp_r * atr_mult * a
            j = p; done = 0; ambig = 0
            while j < len(c1):
                hit = (l1[j] <= st) if side == 1 else (h1[j] >= st)
                won = (h1[j] >= tg) if side == 1 else (l1[j] <= tg)
                if hit and won:
                    ambig = 1
                    won = False
                if hit:
                    through = (side == 1 and o1[j] < st) or (side == -1 and o1[j] > st)
                    px = o1[j] if through else st
                    px += -se if side == 1 else se
                    pnl[k] = side * (px - entry) * pv - comm - 2.0 * ec * pv
                    why[k] = 1; done = 1; break
                if won:
                    through = (side == 1 and o1[j] > tg) or (side == -1 and o1[j] < tg)
                    px = o1[j] if through else tg
                    pnl[k] = side * (px - entry) * pv - comm - 2.0 * ec * pv
                    why[k] = 2; done = 1; break
                if flat_min > 0 and mod1[j] >= flat_min:
                    pnl[k] = side * (c1[j] - entry) * pv - comm - 2.0 * ec * pv
                    why[k] = 3; done = 1; break
                j += 1
            if done == 0:
                break
            b = i + 1
            while b + 1 < n and lo[b + 1] <= j:
                b += 1
            eb[k] = i + 1; xb[k] = b; amb[k] = ambig; k += 1
            free = b
            fills += 1
            if refill == 1 and b == i + 1 and fills < 3 and j + 1 < len(c1):
                entry = c1[j]; p = j + 1
                continue
            break
    return pnl[:k], eb[:k], xb[:k], why[:k], amb[:k]


@njit(cache=True)
def _entry_timing(o1, c1, h1, l1, lo, atr_, trig, side, atr_mult, tp_r, offs, out):
    """The same signals filled at minute `offs` of the following bar instead of its open."""
    n = len(lo)
    for oi in range(len(offs)):
        off = offs[oi]
        tot = 0.0; free = -1
        for t in range(len(trig)):
            i = trig[t]
            if i < free or i + 1 >= n:
                continue
            a = atr_[i]
            if np.isnan(a) or a <= 0.0:
                continue
            p = lo[i + 1] + off
            if p >= len(c1):
                break
            entry = o1[p]
            st = entry - side * atr_mult * a
            tg = entry + side * tp_r * atr_mult * a
            j = p
            while j < len(c1):
                hit = (l1[j] <= st) if side == 1 else (h1[j] >= st)
                won = (h1[j] >= tg) if side == 1 else (l1[j] <= tg)
                if hit:
                    tot += side * (st - entry) * PV - COMM - 2.0 * EC * PV - SE * PV
                    break
                if won:
                    tot += side * (tg - entry) * PV - COMM - 2.0 * EC * PV
                    break
                j += 1
            b = i + 1
            while b + 1 < n and lo[b + 1] <= j:
                b += 1
            free = b
        out[oi] = tot


def compare(conds, side=1, atr_mult=2.5, tp_r=3.0, flat_min=0, tf=30):
    """The engine's model, the true 1-minute path, and the path with same-bar refills."""
    from test_suite import build
    s = build(conds, side=side, atr_mult=atr_mult, tp_r=tp_r, flat_min=flat_min, tf=tf)
    m = minute_map(tf)
    d = m["d"]
    args = (m["o"], m["h"], m["l"], m["c"], m["mod"], m["lo"], m["hi"], d["atr"],
            s.trig, np.int64(side), float(atr_mult), float(tp_r), np.int64(flat_min))
    out = {"A pessimistic (the engine)": (s.pnl, s.why, None)}
    for label, rf in (("B true 1-minute path", 0), ("C true path + refill on fill", 1)):
        pnl, eb, xb, why, amb = _walk(*args, np.int64(rf), PV, COMM, EC, SE)
        out[label] = (pnl, why, amb)
    offs = np.array([0, 1, 2, 5, 10, 20, 29], np.int64)
    tim = np.zeros(len(offs))
    _entry_timing(m["o"], m["c"], m["h"], m["l"], m["lo"], d["atr"], s.trig,
                  np.int64(side), float(atr_mult), float(tp_r), offs, tim)
    return s, out, (offs, tim)


def report(conds, **kw):
    s, out, (offs, tim) = compare(conds, **kw)
    print("=" * 96)
    print("  " + " AND ".join(conds) + f"   [{'long' if kw.get('side',1)==1 else 'short'}]")
    print("=" * 96)
    print(f"  {'execution model':<32}{'trades':>8}{'net $':>11}{'PF':>7}{'win %':>8}"
          f"{'stop %':>8}{'unresolved':>12}")
    base = None
    for label, (pnl, why, amb) in out.items():
        w = pnl[pnl > 0].sum(); l = -pnl[pnl <= 0].sum()
        pf = w / l if l > 0 else np.inf
        un = f"{100*amb.mean():.1f}%" if amb is not None else "n/a"
        print(f"  {label:<32}{len(pnl):>8}{pnl.sum():>11,.0f}{pf:>7.2f}"
              f"{100*(pnl>0).mean():>8.1f}{100*(why==1).mean():>8.0f}{un:>12}")
        if base is None:
            base = pnl.sum()
    print("\n  entry filled N minutes into the fill bar instead of at its open:")
    print("  " + "  ".join(f"{o}m ${v:,.0f}" for o, v in zip(offs, tim)))
    sp = (tim.max() - tim.min()) / abs(tim[0]) * 100 if tim[0] else np.nan
    print(f"  spread across timings: {sp:.0f}% of the at-open result")
    return s, out


if __name__ == "__main__":
    report(["close>EMA10", "body>60%", "5-bar momentum>0"], side=1, atr_mult=2.5, tp_r=3.0)
    print()
    report(["RSI14<30", "Williams%R<-80", "ADX>25"], side=1, atr_mult=2.5, tp_r=3.0)
