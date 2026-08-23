"""Mirror of the corrected IVB Pine — 15m bars, 15m initial value, break and go, no filters.

Deliberately the simplest configuration that survived the corrected sweep, because the two things
that went wrong last time both lived in the filters: the trend filter carried a look-ahead, and
the range filter needed a rolling window the Pine would have had to reimplement. Neither is here.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
from bos_choch import prep

PV = 2.0; TICK = 0.25; COMM = 1.0
EC = 2.0 * TICK; SE = 1.0 * TICK
RTH = 570


def pine_mirror(tf=15, iv_min=15, buf_atr=0.15, tp_r=1.0, flat_min=900, side_mode=0):
    d = prep(tf)
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    mod, sess, atr_ = d["mod"], d["sess"], d["atr"]
    n = len(c)
    ivh = np.nan; ivl = np.nan
    pos = 0; entry = 0.0; stop = 0.0; tgt = 0.0
    pend = 0; pstop = 0.0; ptgt = 0.0
    took = 0; s_prev = -1; ei = 0
    P = []; E = []; X = []; S = []
    for i in range(1, n - 1):
        m = mod[i]
        if sess[i] != s_prev:
            ivh = np.nan; ivl = np.nan; pos = 0; pend = 0; took = 0
            s_prev = sess[i]
        if RTH <= m < RTH + iv_min:
            ivh = h[i] if np.isnan(ivh) else max(ivh, h[i])
            ivl = l[i] if np.isnan(ivl) else min(ivl, l[i])
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
                P.append(pos * (px - entry) * PV - COMM - 2.0 * EC * PV)
                E.append(ei); X.append(i); S.append(pos)
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
        ref = c[i]
        st = ivl if d_ == 1 else ivh
        if (d_ == 1 and st >= ref) or (d_ == -1 and st <= ref):
            continue
        risk = abs(ref - st)
        if risk <= 0.0 or risk > 8.0 * a:
            continue
        pend = d_; pstop = st; ptgt = ref + d_ * tp_r * risk
        took += 1
    return np.array(P), np.array(E), np.array(X), np.array(S)


if __name__ == "__main__":
    from ivb_ladder import go
    B = dict(tf=15, iv_min=15, use_ib=1, entry_mode=0, stop_mode=1, tgt_mode=0, tp=1.0,
             trend_mode=0, rng_filter=0, flat_min=900, side_mode=0, atr_mult=1.0,
             buf_atr=0.15)
    r = go(**B)
    p, e, x, s = pine_mirror()
    gw = p[p > 0].sum(); gl = -p[p <= 0].sum()
    print("=" * 88)
    print("PINE-SEMANTICS MIRROR vs THE CORRECTED ENGINE")
    print("=" * 88)
    print("   15m bars, 09:30-09:45 initial value, IVH/IVL, close beyond by 0.15 x ATR, enter")
    print("   next open, stop at the opposite edge, target 1.0R, flat 15:00, both sides.\n")
    print(f"   engine  {r['n']:>4} trades   net ${r['net']:>9,.0f}   PF {r['pf']:.2f}   "
          f"win {r['win']:.1f}%   research ${r['res']:>7,.0f}   locked ${r['lock']:>7,.0f}")
    print(f"   mirror  {len(p):>4} trades   net ${p.sum():>9,.0f}   PF {gw/gl:.2f}   "
          f"win {100*(p>0).mean():.1f}%")
    print()
    print("   IDENTICAL" if len(p) == r["n"] and abs(p.sum() - r["net"]) < 1.0
          else f"   DIFFERENT by {len(p)-r['n']} trades and ${p.sum()-r['net']:,.0f}")
