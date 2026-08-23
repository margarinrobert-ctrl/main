"""What actually predicts a winnable intraday trade on NQ, using the paper's barrier as the ruler.

The one genuinely useful thing MaxAI contributes is a well-defined outcome: from any bar, take a
position, exit at a $900 stop, a $1,500 target, or 16:00 -- whichever comes first. That converts
"was this a good moment to trade" into a number, for every bar, without any strategy attached.

This file asks which observable conditions shift that number. Every test is:
  - CAUSAL          the condition at bar i uses only bars <= i, and the fill is o[i+1].
  - COST-DIFFERENCED lift against the same barrier taken on ALL bars, not against zero, so the
                    round turn cancels (RESEARCH_PROTOCOL 4a).
  - DAY-CLUSTERED   one observation per session, because bars inside a session share an outcome.
                    This is the correction that turned +$201 at t=5.6 into -$153 at t=-1.37.
  - FDR-CONTROLLED  Benjamini-Hochberg across every condition x side tested.
  - SPLIT           research = first 60% of sessions, holdout = last 40%, reported side by side.

Usage: python3 research/cmf_conditions.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from numba import njit
from scipy import stats as st

sys.path.insert(0, "research")
from cmf_maxai import COSTS, POINT_VALUE, STOP_DOLLARS, TARGET_DOLLARS, cmf, load
from nqdata import minute_of_day, minutes_since_open

COST = COSTS["repo"]
STOP_PTS = STOP_DOLLARS / POINT_VALUE
TGT_PTS = TARGET_DOLLARS / POINT_VALUE
RTH_START = 570


@njit(cache=True)
def barrier_outcome(o, h, l, c, sess, stop_pts, tgt_pts):
    """Long-side dollar move for a position opened at o[i+1] and closed at stop, target or 16:00.

    Returns points, not dollars, and costs are applied by the caller so both arms of a lift test
    are charged identically. The short side is the negative of this.
    """
    n = len(c)
    out = np.full(n, np.nan)
    for i in range(n - 1):
        if sess[i + 1] != sess[i]:
            continue
        entry = o[i + 1]
        sp = entry - stop_pts
        tp = entry + tgt_pts
        res = np.nan
        j = i + 1
        while j < n and sess[j] == sess[i + 1]:
            if l[j] <= sp:
                res = -stop_pts
                break
            if h[j] >= tp:
                res = tgt_pts
                break
            j += 1
        if np.isnan(res):
            res = c[j - 1] - entry if j > i + 1 else 0.0
        out[i] = res
    return out


def bh(p):
    p = np.asarray(p, float)
    m = len(p)
    order = np.argsort(p)
    q = np.empty(m)
    prev = 1.0
    for rank in range(m - 1, -1, -1):
        i = order[rank]
        prev = min(prev, p[i] * m / (rank + 1))
        q[i] = prev
    return q


def day_lift(sig_pnl, base_pnl, mask, win, sess, days):
    """Mean(condition) - mean(all bars), computed per session then averaged across sessions."""
    per = []
    for d in days:
        a = mask & (sess == d)
        b = win & (sess == d)
        if a.sum() and b.sum():
            per.append(sig_pnl[a].mean() - base_pnl[b].mean())
    arr = np.array(per)
    if len(arr) < 30:
        return np.nan, np.nan, arr
    t = arr.mean() / (arr.std(ddof=1) / np.sqrt(len(arr)))
    return arr.mean(), t, arr


def main() -> None:
    seg, o, h, l, c, v, sess, m, sig = load()
    mod = minute_of_day(seg.index)
    mso = minutes_since_open(mod, RTH_START)
    days = np.unique(sess)
    n = len(c)

    pts = barrier_outcome(o, h, l, c, sess, STOP_PTS, TGT_PTS)
    long_d = pts * POINT_VALUE - COST
    short_d = -pts * POINT_VALUE - COST
    ok = np.isfinite(long_d)

    print("=" * 108)
    print("THE BARRIER AS A RULER: $900 stop / $1,500 target / 16:00 flat, taken from every bar")
    print("=" * 108 + "\n")
    print(f"  {ok.sum():,} bars with a resolved outcome over {len(days)} sessions")
    print(f"  unconditional: long ${long_d[ok].mean():.2f}/trade   short ${short_d[ok].mean():.2f}/trade")
    print(f"  break-even win rate for this barrier: "
          f"{100*STOP_DOLLARS/(STOP_DOLLARS+TARGET_DOLLARS):.1f}%, actual long win rate "
          f"{100*(long_d[ok]>0).mean():.1f}%")

    # ---- causal conditioning variables ----
    atr = pd.Series(np.maximum(h - l, np.maximum(abs(h - np.roll(c, 1)), abs(l - np.roll(c, 1))))
                    ).rolling(30).mean().to_numpy().copy()
    atr[:30] = np.nan
    atr_rank = pd.Series(atr).rolling(2000).rank(pct=True).to_numpy()
    vol_rel = v / pd.Series(v).rolling(60).mean().to_numpy()
    # session VWAP, reset each day, causal
    tp_ = (h + l + c) / 3
    vwap = np.full(n, np.nan)
    cum_pv = 0.0; cum_v = 0.0; cur = -1
    for i in range(n):
        if sess[i] != cur:
            cur = sess[i]; cum_pv = 0.0; cum_v = 0.0
        cum_pv += tp_[i] * v[i]; cum_v += v[i]
        vwap[i] = cum_pv / cum_v if cum_v > 0 else np.nan
    # opening-range position (first 30 min), known only after 10:00
    or_hi = np.full(n, np.nan); or_lo = np.full(n, np.nan)
    hi = -np.inf; lo = np.inf; cur = -1
    for i in range(n):
        if sess[i] != cur:
            cur = sess[i]; hi = -np.inf; lo = np.inf
        if mso[i] < 30:
            hi = max(hi, h[i]); lo = min(lo, l[i])
        elif hi > -np.inf:
            or_hi[i] = hi; or_lo[i] = lo
    or_pos = (c - or_lo) / np.where(or_hi - or_lo > 0, or_hi - or_lo, np.nan)
    # prior-session return, known at the open
    day_close = {}
    for i in range(n):
        day_close[sess[i]] = c[i]
    prev_ret = np.full(n, np.nan)
    dl = list(days)
    for i in range(n):
        k = dl.index(sess[i]) if sess[i] in dl else -1
        if k > 0:
            prev_ret[i] = day_close[dl[k - 1]] / day_close[dl[k - 2]] - 1 if k > 1 else np.nan

    cond = {}
    cond["CMF >= +0.25 (the paper's long)"] = sig == 1
    cond["CMF <= -0.25 (the paper's short)"] = sig == -1
    cond["first 30 min"] = mso < 30
    cond["09:30-11:00"] = (mod >= 570) & (mod < 660)
    cond["11:00-14:00 (midday)"] = (mod >= 660) & (mod < 840)
    cond["last hour"] = mod >= 900
    cond["ATR in top quartile"] = atr_rank > 0.75
    cond["ATR in bottom quartile"] = atr_rank < 0.25
    cond["volume > 2x its 60-bar mean"] = vol_rel > 2
    cond["price above session VWAP"] = c > vwap
    cond["price below session VWAP"] = c < vwap
    cond["above the opening range"] = or_pos > 1
    cond["below the opening range"] = or_pos < 0
    cond["inside the opening range"] = (or_pos >= 0) & (or_pos <= 1)
    cond["prior session up"] = prev_ret > 0
    cond["prior session down"] = prev_ret < 0

    cut = days[int(len(days) * 0.6)]
    rows = []
    for name, msk in cond.items():
        base_mask = ok & np.isfinite(msk.astype(float))
        mm = ok & msk
        if mm.sum() < 500:
            continue
        for sname, pnl in (("long", long_d), ("short", short_d)):
            lift, t, arr = day_lift(pnl, pnl, mm, ok, sess, days)
            if not np.isfinite(t):
                continue
            r_days = days[days < cut]
            h_days = days[days >= cut]
            lr, _, _ = day_lift(pnl, pnl, mm, ok, sess, r_days)
            hr, _, _ = day_lift(pnl, pnl, mm, ok, sess, h_days)
            rows.append(dict(cond=name, side=sname, n=int(mm.sum()), lift=lift, t=t,
                             p=2 * (1 - st.norm.cdf(abs(t))), res=lr, hold=hr,
                             net=pnl[mm].mean()))
    df = pd.DataFrame(rows)
    df["q"] = bh(df.p.to_numpy())
    df = df.sort_values("t", ascending=False)

    print("\n" + "=" * 108)
    print("WHICH CONDITIONS SHIFT THE OUTCOME  (lift vs the same barrier on all bars, per session)")
    print("=" * 108 + "\n")
    print(f"  {'condition':<36}{'side':>6}{'n':>9}{'lift $':>10}{'t':>7}{'q':>7}"
          f"{'research':>11}{'holdout':>10}{'net $':>10}")
    for _, r in df.iterrows():
        star = "  *" if r.q < 0.10 else ""
        print(f"  {r['cond']:<36}{r.side:>6}{int(r.n):>9,}{r.lift:>10.2f}{r.t:>7.2f}{r.q:>7.3f}"
              f"{r.res:>11.2f}{r.hold:>10.2f}{r.net:>10.2f}{star}")

    sv = df[df.q < 0.10]
    print(f"\n  {len(sv)} of {len(df)} survive FDR at q < 0.10")
    good = sv[(sv.lift > 0) & (sv.res > 0) & (sv.hold > 0) & (sv.net > 0)]
    print(f"  positive lift, same sign in BOTH halves, AND net positive after costs: {len(good)}")
    for _, r in good.iterrows():
        print(f"    {r['cond']} ({r.side}): +${r.lift:.2f} lift, "
              f"research +${r.res:.2f} / holdout +${r.hold:.2f}, net ${r.net:.2f}/trade")


if __name__ == "__main__":
    main()
