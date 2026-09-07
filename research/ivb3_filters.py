"""The two confirmations in the strategy description that were never tested: a full-bodied
breakout candle, and volume on that candle against the opening range's own average.

Built on ivb2_mirror, which reproduces the research engine exactly, so any change here is the
filter and nothing else.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
from bos_choch import prep

PV = 2.0; TICK = 0.25; COMM = 1.0
EC = 2.0 * TICK; SE = 1.0 * TICK
RTH = 570


def run(tf=15, iv_min=15, buf_atr=0.15, tp_r=1.0, flat_min=900, side_mode=0,
        body_min=0.0, vol_mult=0.0):
    d = prep(tf)
    o, h, l, c, v = d["o"], d["h"], d["l"], d["c"], d["v"]
    mod, sess, atr_ = d["mod"], d["sess"], d["atr"]
    n = len(c)
    ivh = np.nan; ivl = np.nan; ivv = 0.0; ivn = 0
    pos = 0; entry = 0.0; stop = 0.0; tgt = 0.0
    pend = 0; pstop = 0.0; ptgt = 0.0
    took = 0; s_prev = -1; ei = 0
    P = []; E = []
    for i in range(1, n - 1):
        m = mod[i]
        if sess[i] != s_prev:
            ivh = np.nan; ivl = np.nan; ivv = 0.0; ivn = 0
            pos = 0; pend = 0; took = 0
            s_prev = sess[i]
        if RTH <= m < RTH + iv_min:
            ivh = h[i] if np.isnan(ivh) else max(ivh, h[i])
            ivl = l[i] if np.isnan(ivl) else min(ivl, l[i])
            ivv += v[i]; ivn += 1
        if pend != 0 and pos == 0:
            pos = pend; entry = o[i]; pend = 0; stop = pstop; tgt = ptgt; ei = i
            if (pos == 1 and stop >= entry) or (pos == -1 and stop <= entry):
                pos = 0
        if pos != 0:
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
        if pos != 0 or pend != 0 or took >= 1:
            continue
        if not (RTH + iv_min <= m < flat_min):
            continue
        a = atr_[i]
        if np.isnan(a) or a <= 0.0 or np.isnan(ivh) or np.isnan(ivl) or ivh <= ivl:
            continue
        d_ = 0
        if c[i] > ivh + buf_atr * a:
            d_ = 1
        elif c[i] < ivl - buf_atr * a:
            d_ = -1
        if d_ == 0 or (side_mode != 0 and side_mode != d_):
            continue
        # ---- "a full-bodied candle with small wicks" ------------------------------------------
        if body_min > 0.0:
            rng = h[i] - l[i]
            if rng <= 0 or abs(c[i] - o[i]) / rng < body_min:
                continue
        # ---- "high trading volume", measured against the opening range's own average ----------
        if vol_mult > 0.0:
            if ivn == 0 or v[i] < vol_mult * (ivv / ivn):
                continue
        ref = c[i]
        st = ivl if d_ == 1 else ivh
        if (d_ == 1 and st >= ref) or (d_ == -1 and st <= ref):
            continue
        risk = abs(ref - st)
        if risk <= 0.0 or risk > 8.0 * a:
            continue
        pend = d_; pstop = st; ptgt = ref + d_ * tp_r * risk
        took += 1
    return np.array(P), np.array(E)


if __name__ == "__main__":
    d15 = prep(15)
    us = np.unique(prep(30)["sess"]); CUT = us[int(0.65 * len(us))]

    def stat(tag, tf, **kw):
        p, e = run(tf=tf, **kw)
        if len(p) < 20:
            return f"   {tag:<40}  (too few trades)"
        ss = prep(tf)["sess"][e]; m = ss < CUT
        gw = p[p > 0].sum(); gl = -p[p <= 0].sum()
        eq = np.cumsum(p); dd = (np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max()
        return (f"   {tag:<40}{len(p):>5}{p.sum():>10,.0f}{(gw/gl if gl else 9.99):>6.2f}"
                f"{100*(p>0).mean():>7.1f}{p[m].sum():>10,.0f}{p[~m].sum():>9,.0f}{dd:>8,.0f}")

    W = 92
    H = (f"   {'':<40}{'n':>5}{'net $':>10}{'PF':>6}{'win%':>7}{'research':>10}"
         f"{'LOCKED':>9}{'DD':>8}")
    print("=" * W)
    print("A. THE OPENING WINDOW — 15 minutes (ORB) against 60 minutes (Initial Balance)")
    print("=" * W)
    print("   Same rules otherwise: close beyond the level by 0.15 ATR, stop at the opposite")
    print("   edge, 1.0R target, flat 15:00, both sides.\n")
    print(H)
    for iv in (15, 30, 60, 90):
        print(stat(f"{iv}-minute opening window", 15, iv_min=iv))

    print()
    print("=" * W)
    print("B. A FULL-BODIED BREAKOUT CANDLE — |close-open| / (high-low)")
    print("=" * W)
    print(H)
    for iv in (15, 60):
        for b in (0.0, 0.5, 0.6, 0.7):
            print(stat(f"{iv}m window, body >= {b:.0%}" if b else f"{iv}m window, no body filter",
                       15, iv_min=iv, body_min=b))
        print()

    print("=" * W)
    print("C. VOLUME ON THE BREAKOUT CANDLE, against the opening range's own average")
    print("=" * W)
    print("   The figure quoted online is 1.5x, said to add 8-12 points of win rate.\n")
    print(H)
    for iv in (15, 60):
        for vm in (0.0, 1.0, 1.5, 2.0):
            print(stat(f"{iv}m window, volume >= {vm:.1f}x" if vm else f"{iv}m window, no volume filter",
                       15, iv_min=iv, vol_mult=vm))
        print()

    print("=" * W)
    print("D. BOTH CONFIRMATIONS TOGETHER, as the description specifies")
    print("=" * W)
    print(H)
    for iv in (15, 60):
        print(stat(f"{iv}m window, body 60% + volume 1.5x", 15, iv_min=iv,
                   body_min=0.6, vol_mult=1.5))
        print(stat(f"{iv}m window, body 50% + volume 1.0x", 15, iv_min=iv,
                   body_min=0.5, vol_mult=1.0))
