"""The remaining Initial-Balance-style options, measured before they are offered as inputs.

Untested until now: a stop at a percentage of the opening range beyond the broken edge, a fixed
point stop, a target expressed as a percentage of the range beyond the edge, a second trade on
double-break days, and a move to breakeven.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
from bos_choch import prep

PV = 2.0; TICK = 0.25; COMM = 1.0
EC = 2.0 * TICK; SE = 1.0 * TICK
RTH = 570


def run(tf=15, iv_min=15, buf_atr=0.15, flat_min=900, side_mode=0,
        stop_mode="opp", stop_pct=80.0, stop_pts=20.0, atr_mult=1.5,
        tgt_mode="R", tp=1.0, tgt_pct=50.0,
        max_trades=1, be_pct=0.0, entry_retr=0.0):
    d = prep(tf)
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    mod, sess, atr_ = d["mod"], d["sess"], d["atr"]
    n = len(c)
    ivh = np.nan; ivl = np.nan
    pos = 0; entry = 0.0; stop = 0.0; tgt = 0.0; risk0 = 0.0; be_done = False
    pend = 0; pstop = 0.0; ptgt = 0.0
    armed = 0; arm_px = 0.0
    took = 0; s_prev = -1; ei = 0
    P = []; E = []
    for i in range(1, n - 1):
        m = mod[i]
        if sess[i] != s_prev:
            ivh = np.nan; ivl = np.nan; pos = 0; pend = 0; armed = 0; took = 0
            s_prev = sess[i]
        if RTH <= m < RTH + iv_min:
            ivh = h[i] if np.isnan(ivh) else max(ivh, h[i])
            ivl = l[i] if np.isnan(ivl) else min(ivl, l[i])
        if pend != 0 and pos == 0:
            pos = pend; entry = o[i]; pend = 0; stop = pstop; tgt = ptgt; ei = i
            risk0 = abs(entry - stop); be_done = False
            if (pos == 1 and stop >= entry) or (pos == -1 and stop <= entry):
                pos = 0
        if pos != 0:
            if be_pct > 0 and not be_done:
                trig = entry + pos * (be_pct / 100.0) * risk0
                if (pos == 1 and h[i] >= trig) or (pos == -1 and l[i] <= trig):
                    stop = entry; be_done = True
            hit = (l[i] <= stop) if pos == 1 else (h[i] >= stop)
            won = (h[i] >= tgt) if pos == 1 else (l[i] <= tgt)
            px = 0.0; done = False
            if hit:
                px = o[i] if ((pos == 1 and o[i] < stop) or (pos == -1 and o[i] > stop)) else stop
                px += -SE if pos == 1 else SE
                done = True
            elif won:
                px = o[i] if ((pos == 1 and o[i] > tgt) or (pos == -1 and o[i] < tgt)) else tgt
                done = True
            elif m >= flat_min:
                px = c[i]; done = True
            if done:
                P.append(pos * (px - entry) * PV - COMM - 2.0 * EC * PV); E.append(ei)
                pos = 0
        if pos != 0 or pend != 0 or took >= max_trades:
            continue
        if not (RTH + iv_min <= m < flat_min):
            continue
        a = atr_[i]
        if np.isnan(a) or a <= 0.0 or np.isnan(ivh) or np.isnan(ivl) or ivh <= ivl:
            continue
        rng = ivh - ivl
        if armed != 0:
            d_ = armed
            if (d_ == 1 and l[i] <= arm_px) or (d_ == -1 and h[i] >= arm_px):
                ref = arm_px
                st = _stop(d_, ref, ivh, ivl, rng, a, stop_mode, stop_pct, stop_pts, atr_mult)
                if st is not None and ((d_ == 1 and st < ref) or (d_ == -1 and st > ref)):
                    rk = abs(ref - st)
                    if 0 < rk <= 8 * a:
                        pos = d_; entry = ref; stop = st; risk0 = rk; be_done = False
                        tgt = _tgt(d_, ref, ivh, ivl, rng, rk, tgt_mode, tp, tgt_pct)
                        took += 1
                armed = 0
            continue
        d_ = 0
        if c[i] > ivh + buf_atr * a:
            d_ = 1
        elif c[i] < ivl - buf_atr * a:
            d_ = -1
        if d_ == 0 or (side_mode != 0 and side_mode != d_):
            continue
        lvl = ivh if d_ == 1 else ivl
        ref = c[i] if entry_retr <= 0 else lvl - d_ * (entry_retr / 100.0) * rng
        st = _stop(d_, ref, ivh, ivl, rng, a, stop_mode, stop_pct, stop_pts, atr_mult)
        if st is None or (d_ == 1 and st >= ref) or (d_ == -1 and st <= ref):
            continue
        rk = abs(ref - st)
        if rk <= 0 or rk > 8 * a:
            continue
        if entry_retr > 0:
            armed = d_; arm_px = ref
        else:
            pend = d_; pstop = st
            ptgt = _tgt(d_, ref, ivh, ivl, rng, rk, tgt_mode, tp, tgt_pct)
            took += 1
    return np.array(P), np.array(E)


def _stop(d, ref, ivh, ivl, rng, a, mode, pct, pts, am):
    if mode == "opp":
        return ivl if d == 1 else ivh
    if mode == "atr":
        return ref - d * am * a
    if mode == "mid":
        return (ivh + ivl) * 0.5
    if mode == "pct":                    # % of the range back from the broken edge
        lvl = ivh if d == 1 else ivl
        return lvl - d * (pct / 100.0) * rng
    if mode == "pts":
        return ref - d * pts
    return None


def _tgt(d, ref, ivh, ivl, rng, risk, mode, tp, tgt_pct):
    if mode == "R":
        return ref + d * tp * risk
    if mode == "rng":
        return ref + d * tp * rng
    lvl = ivh if d == 1 else ivl         # % of the range beyond the broken edge
    return lvl + d * (tgt_pct / 100.0) * rng


if __name__ == "__main__":
    us = np.unique(prep(30)["sess"]); CUT = us[int(0.65 * len(us))]

    def line(tag, **kw):
        p, e = run(**kw)
        if len(p) < 20:
            return f"   {tag:<42}   (too few trades)"
        ss = prep(kw.get("tf", 15))["sess"][e]; m = ss < CUT
        gw = p[p > 0].sum(); gl = -p[p <= 0].sum()
        eq = np.cumsum(p); dd = (np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max()
        return (f"   {tag:<42}{len(p):>5}{p.sum():>10,.0f}{(gw/gl if gl else 9.99):>6.2f}"
                f"{100*(p>0).mean():>7.1f}{p[m].sum():>10,.0f}{p[~m].sum():>9,.0f}{dd:>8,.0f}")

    H = (f"   {'':<42}{'n':>5}{'net $':>10}{'PF':>6}{'win%':>7}{'research':>10}"
         f"{'LOCKED':>9}{'DD':>8}")
    print("=" * 94)
    print("STOP METHODS — the shipped one, and the two the Initial Balance script offers")
    print("=" * 94)
    print(H)
    print(line("opposite edge  (shipped)", stop_mode="opp"))
    print(line("ATR 1.5x from entry", stop_mode="atr", atr_mult=1.5))
    print(line("midpoint of the range", stop_mode="mid"))
    for q in (60, 80, 100):
        print(line(f"{q}% of range back from the edge", stop_mode="pct", stop_pct=q))
    for q in (20, 30, 40):
        print(line(f"fixed {q} points from entry", stop_mode="pts", stop_pts=q))

    print()
    print("=" * 94)
    print("TARGET METHODS")
    print("=" * 94)
    print(H)
    print(line("1.0 x risk  (shipped)", tgt_mode="R", tp=1.0))
    print(line("2.0 x risk", tgt_mode="R", tp=2.0))
    print(line("1.0 x the opening range", tgt_mode="rng", tp=1.0))
    for q in (50, 100):
        print(line(f"{q}% of range beyond the edge", tgt_mode="pct", tgt_pct=q))

    print()
    print("=" * 94)
    print("A SECOND TRADE, AND BREAKEVEN")
    print("=" * 94)
    print(H)
    print(line("one trade a day  (shipped)", max_trades=1))
    print(line("two trades a day", max_trades=2))
    print(line("three trades a day", max_trades=3))
    for b in (50, 75, 100):
        print(line(f"stop to breakeven at {b}% of risk", be_pct=b))

    print()
    print("=" * 94)
    print("A RETRACEMENT ENTRY, as the Initial Balance script uses")
    print("=" * 94)
    print(H)
    print(line("enter on the break  (shipped)", entry_retr=0))
    for r in (0.1, 25, 50):
        print(line(f"wait for a {r}% pullback into the range", entry_retr=r))
