"""A line-for-line mirror of the IVB Pine script, checked against the research engine.

Everything the Pine has to do differently from the research engine is modelled here first:

  * the 60-minute trend series is built BY HAND from 30-minute bars rather than pulled with
    request.security, so there is no aggregation choice and no lookahead argument to get wrong
  * the trailing range distribution is a bounded rolling array, not a pandas window
  * the initial value high/low accumulate bar by bar during 09:30-10:30 instead of being
    computed from a slice
  * the EMA of the 60-minute close is a running recursion, not a vectorised call

If any of those diverge, the Pine is not the strategy that was tested.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
from bos_choch import prep

PV = 2.0
TICK = 0.25
COMM = 1.0
EC = 2.0 * TICK
SE = 1.0 * TICK
RTH = 570


def pine_mirror(iv_min=60, tp_mult=1.5, flat_min=945, trend_len=50,
                lookback=60, lo_pct=0.20, hi_pct=0.80, side_mode=0,
                use_trend=True, use_rng=True):
    d = prep(30)
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    mod, sess, atr_ = d["mod"], d["sess"], d["atr"]
    n = len(c)

    # ---- state the Pine carries in `var` ---------------------------------------------------
    ivh = np.nan; ivl = np.nan; iv_done = False
    hist = []                      # the trailing initial-value ranges
    # hand-built 60-minute bars, and the EMA of their closes
    b60_h = np.nan; b60_l = np.nan; b60_c = np.nan
    e60 = np.nan; n60 = 0; seed = []
    trend_at_open = 0              # frozen at 09:30 each session
    trend_live = 0

    pos = 0; entry = 0.0; stop = 0.0; tgt = 0.0
    pend = 0; pstop = 0.0; ptgt = 0.0
    took = 0; s_prev = -1
    P = []; E = []; X = []; S = []

    for i in range(1, n - 1):
        m = mod[i]
        # ---------- a 60-minute bar closes whenever the NEXT bar starts a new hour ----------
        if m % 60 == 0:
            if not np.isnan(b60_c):
                if n60 < trend_len:
                    seed.append(b60_c); n60 += 1
                    if n60 == trend_len:
                        e60 = float(np.mean(seed))
                elif not np.isnan(e60):
                    e60 += (2.0 / (trend_len + 1.0)) * (b60_c - e60)
                if not np.isnan(e60):
                    trend_live = 1 if b60_c > e60 else -1
            b60_h = h[i]; b60_l = l[i]; b60_c = c[i]
        else:
            b60_h = max(b60_h, h[i]) if not np.isnan(b60_h) else h[i]
            b60_l = min(b60_l, l[i]) if not np.isnan(b60_l) else l[i]
            b60_c = c[i]

        # ---------- session boundaries -----------------------------------------------------
        if sess[i] != s_prev:
            if not np.isnan(ivh) and not np.isnan(ivl) and iv_done:
                hist.append(ivh - ivl)
                if len(hist) > lookback:
                    hist.pop(0)
            ivh = np.nan; ivl = np.nan; iv_done = False
            pos = 0; pend = 0; took = 0
            s_prev = sess[i]

        # the trend is frozen at the open and not revised during the session
        if m < RTH:
            trend_at_open = trend_live

        # ---------- accumulate the initial value -------------------------------------------
        if RTH <= m < RTH + iv_min:
            ivh = h[i] if np.isnan(ivh) else max(ivh, h[i])
            ivl = l[i] if np.isnan(ivl) else min(ivl, l[i])
        if m >= RTH + iv_min and not np.isnan(ivh):
            iv_done = True

        # ---------- fills ------------------------------------------------------------------
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
        # the engine gates on the CLOCK, not on a latched flag: a session runs 09:30 -> 09:30,
        # so without this the next morning's pre-open bars would qualify as "after the opening
        # period" and enter at 03:00.
        if not (RTH + iv_min <= m < flat_min):
            continue
        if not iv_done:
            continue
        a = atr_[i]
        if np.isnan(a) or a <= 0.0:
            continue
        if np.isnan(ivh) or np.isnan(ivl) or ivh <= ivl:
            continue

        # ---------- the range-size filter --------------------------------------------------
        if use_rng:
            if len(hist) < 30:
                continue
            arr = np.array(hist)
            p = (arr < (ivh - ivl)).mean()
            if p < lo_pct or p > hi_pct:
                continue

        # ---------- the break --------------------------------------------------------------
        d_ = 0
        if c[i] > ivh:
            d_ = 1
        elif c[i] < ivl:
            d_ = -1
        if d_ == 0:
            continue
        if side_mode != 0 and side_mode != d_:
            continue
        if use_trend and trend_at_open != d_:
            continue

        ref = c[i]
        st = ivl if d_ == 1 else ivh
        if (d_ == 1 and st >= ref) or (d_ == -1 and st <= ref):
            continue
        risk = abs(ref - st)
        if risk <= 0.0 or risk > 8.0 * a:
            continue
        pend = d_; pstop = st; ptgt = ref + d_ * tp_mult * (ivh - ivl)
        took += 1

    return np.array(P), np.array(E), np.array(X), np.array(S)


if __name__ == "__main__":
    import ivb_ladder as LAD
    from book import IVB_BEST
    ref = LAD.go(**IVB_BEST)
    p, e, x, s = pine_mirror()
    print("=" * 92)
    print("PINE-SEMANTICS MIRROR vs THE RESEARCH ENGINE")
    print("=" * 92)
    print("   60m initial value, 30m bars, close beyond IVH/IVL, no retest, stop at the opposite")
    print("   edge, target 1.5x the range, 60m trend must agree, range in the 20-80th percentile,")
    print("   flat 15:45, both sides.\n")
    print(f"   engine  {ref['n']:>4} trades   net ${ref['net']:>9,.0f}   PF {ref['pf']:.2f}   "
          f"win {ref['win']:.1f}%")
    gw = p[p > 0].sum(); gl = -p[p <= 0].sum()
    print(f"   mirror  {len(p):>4} trades   net ${p.sum():>9,.0f}   PF {gw/gl:.2f}   "
          f"win {100*(p>0).mean():.1f}%")
    print()
    if len(p) == ref["n"] and abs(p.sum() - ref["net"]) < 1.0:
        print("   IDENTICAL")
    else:
        print(f"   DIFFERENT by {len(p)-ref['n']} trades and ${p.sum()-ref['net']:,.0f}")
