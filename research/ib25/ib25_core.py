"""The "IB 25 retracement" as posted, on 1-minute NQ.

THE RULE, TRANSCRIBED. Session VWAP anchored to the 09:30 open. Nothing before the 10:20 close.
The morning range runs 09:30 to min(now, 10:30) -- the post says draw the fib at 10:21 and keep
adjusting until 09:30-10:30 is formed, which is a RUNNING range that freezes at 10:30. Direction
comes from the VWAP slope. A resting limit at `retr` of the range measured from the target-side
extreme, target that extreme, stop at `stop_frac` of the range. No new setup after the cutoff or
once the range is swept.

THREE THINGS THE POST LEAVES TO JUDGEMENT AND THIS FILE MAKES EXPLICIT, because they cannot be
coded from prose and each is a free parameter:

  "VWAP sloping in your direction"   the VWAP's change over `slope_win` minutes, divided by ATR so
                                     it is scale-free, against a threshold. Zero threshold means
                                     any slope counts.
  "price hasn't chopped around it    the number of times price has CLOSED across the VWAP since
   too much"                         09:30, against a ceiling.
  "the IB high or low is swept"      price trading beyond the frozen 09:30-10:30 range voids the
                                     session -- no new order, and a resting one is cancelled.

ONE LIVE ORDER. `STUDY_V15_BOOK` and `STUDY_V34_MECHANIC` both caught this branch's own engines
holding a BOOK of resting limits where a script holds one, which inflated every limit-entry figure
they produced. Here a session places at most one order and takes at most one trade.

SCORE IN PERCENT OF ENTRY PRICE. The risk is `(stop_frac - retr) x range`, a DIFFERENCE of two
swept fractions of a swept range, so it can be driven arbitrarily small -- exactly the denominator
trap `STUDY_V58_INITIAL_BALANCE` and `STUDY_SWEEP_110K` were caught by. R is reported only as a
diagnostic and the risk distribution is printed beside it.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v63"):
    q = os.path.join(ROOT, p)
    if q not in sys.path:
        sys.path.insert(0, q)

import v63feeds as FD  # noqa: E402

OPEN_M = 9 * 60 + 30
RANGE_END = 10 * 60 + 30
FIRST_ENTRY = 10 * 60 + 21          # "wait till the 10:20 candle to close"
CUTOFF = 12 * 60                    # "I stopped mainly looking for an entry past 12 noon"
FLAT_M = 15 * 60 + 55

COST = {"NQ": (0.86, 2.0, 0.25)}    # points per side, point value, tick


def build(market="NQ"):
    f = FD.bars(market, 1)
    ix = pd.DatetimeIndex(f.index)
    mod = (ix.hour * 60 + ix.minute).to_numpy()
    o, h, l, c = (f[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    v = f["volume"].to_numpy(float)
    sess = (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy()
    rth = (mod >= OPEN_M) & (mod < 16 * 60)

    # session VWAP from 09:30, through the CURRENT completed bar only
    tp = (h + l + c) / 3.0
    d = pd.DataFrame({"pv": np.where(rth, tp * v, 0.0), "v": np.where(rth, v, 0.0), "s": sess})
    g = d.groupby("s", sort=False)
    vwap = (g["pv"].cumsum() / g["v"].cumsum().replace(0, np.nan)).to_numpy()
    vwap[~rth] = np.nan

    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()

    us = np.unique(sess)
    cut = us[int(0.65 * len(us))]
    return dict(market=market, ts=ix.to_numpy(), o=o, h=h, l=l, c=c, v=v, mod=mod, sess=sess,
                rth=rth, vwap=vwap, atr=atr, n=len(c), cut=int(cut),
                cost=COST[market][0], pv=COST[market][1], tick=COST[market][2],
                blocks={"research": sess < cut, "locked": sess >= cut})


@njit(cache=True)
def walk(o, h, l, c, mod, sess, vwap, atr, starts, ends,
         retr, stop_frac, slope_win, slope_thr, max_cross, cutoff, use_sweep,
         cost, slip, allow_long, allow_short, tgt_frac):
    """One session at a time, one resting order, one trade.

    `tgt_frac` is the target as a fraction of the range measured from the target-side extreme;
    0.0 is the post's "target low". Returns per-session arrays; sessions with no trade are -1.

    SLIPPAGE SIGN. P&L is s x (exit - entry), so slippage hurts only if the ENTRY is worse by
    `+ s * slip` (a long pays more, a short receives less) and the EXIT is worse by `- s * slip`
    (a long receives less, a short pays more). The first build of this file had both backwards,
    which paid the trader the slippage instead of charging it -- worth 2 x slip = 0.5 points =
    $1.00 an MNQ trade, and it showed up as expectancy RISING with the assumed slippage.
    """
    ns = len(starts)
    e_bar = np.full(ns, -1, np.int64)
    e_px = np.full(ns, np.nan)
    x_px = np.full(ns, np.nan)
    side = np.zeros(ns, np.int64)
    risk = np.full(ns, np.nan)
    rng_sz = np.full(ns, np.nan)
    code = np.full(ns, -1, np.int64)      # 0 stop, 1 target, 2 flat/cutoff
    for si in range(ns):
        a, b = starts[si], ends[si]
        if b - a < 60:
            continue
        # ---- running range, VWAP crossings
        hi = -1e18
        lo = 1e18
        cross = 0
        prev_above = 0
        placed = 0
        s = 0
        lvl = 0.0
        tgt = 0.0
        stp = 0.0
        rr = 0.0
        swept = 0
        fill_bar = -1
        for i in range(a, b + 1):
            m = mod[i]
            if m < OPEN_M:
                continue
            if m <= RANGE_END:
                if h[i] > hi:
                    hi = h[i]
                if l[i] < lo:
                    lo = l[i]
            w = vwap[i]
            if np.isfinite(w):
                ab = 1 if c[i] > w else -1
                if prev_above != 0 and ab != prev_above:
                    cross += 1
                prev_above = ab
            if hi <= -1e17 or lo >= 1e17:
                continue
            rg = hi - lo
            if rg <= 0.0:
                continue
            # ---- the sweep voids the session once the range is frozen
            if use_sweep == 1 and m > RANGE_END and (h[i] > hi or l[i] < lo):
                swept = 1
            # ---- an order already resting?
            if placed == 1 and fill_bar < 0:
                if swept == 1 or m >= cutoff:
                    placed = 0                      # cancelled
                elif (s < 0 and h[i] >= lvl) or (s > 0 and l[i] <= lvl):
                    fill_bar = i
                    e_bar[si] = i
                    e_px[si] = lvl + s * slip
                    side[si] = s
                    risk[si] = rr
                    rng_sz[si] = rg
            # ---- manage an open trade
            if fill_bar >= 0 and i > fill_bar:
                hit_stop = (h[i] >= stp) if s < 0 else (l[i] <= stp)
                hit_tgt = (l[i] <= tgt) if s < 0 else (h[i] >= tgt)
                if hit_stop:
                    x_px[si] = stp - s * slip
                    code[si] = 0
                    break
                if hit_tgt:
                    x_px[si] = tgt - s * slip
                    code[si] = 1
                    break
                if m >= FLAT_M:
                    x_px[si] = c[i] - s * slip
                    code[si] = 2
                    break
                continue
            # ---- look for a new setup
            if placed == 1 or fill_bar >= 0 or swept == 1:
                continue
            if m < FIRST_ENTRY or m >= cutoff:
                continue
            if cross > max_cross:
                continue
            k = i - slope_win
            if k < a or not np.isfinite(vwap[k]) or not np.isfinite(w):
                continue
            aa = atr[i]
            if not np.isfinite(aa) or aa <= 0.0:
                continue
            sl = (w - vwap[k]) / aa
            if sl <= -slope_thr and allow_short == 1:
                s = -1
            elif sl >= slope_thr and allow_long == 1:
                s = 1
            else:
                continue
            if s < 0:
                lvl = lo + retr * rg
                tgt = lo + tgt_frac * rg
                stp = lo + stop_frac * rg
                if c[i] >= lvl:                     # already through it: no limit to rest
                    s = 0
                    continue
            else:
                lvl = hi - retr * rg
                tgt = hi - tgt_frac * rg
                stp = hi - stop_frac * rg
                if c[i] <= lvl:
                    s = 0
                    continue
            rr = abs(lvl - stp)
            if rr <= 0.0:
                s = 0
                continue
            placed = 1
        if fill_bar >= 0 and not np.isfinite(x_px[si]):
            x_px[si] = c[b] - side[si] * slip
            code[si] = 2
    return e_bar, e_px, x_px, side, risk, rng_sz, code


def sessions(D):
    s = D["sess"]
    ch = np.flatnonzero(np.r_[True, s[1:] != s[:-1]])
    st = ch
    en = np.r_[ch[1:] - 1, len(s) - 1]
    return st.astype(np.int64), en.astype(np.int64), s[st]


def run(D, retr=0.25, stop_frac=0.50, slope_win=20, slope_thr=0.0, max_cross=99,
        cutoff=CUTOFF, use_sweep=True, allow_long=True, allow_short=True, tgt_frac=0.0,
        slip=None, cost=None):
    st, en, skey = sessions(D)
    slip = D["tick"] if slip is None else slip
    cost = D["cost"] if cost is None else cost
    e_bar, e_px, x_px, side, risk, rng_sz, code = walk(
        D["o"], D["h"], D["l"], D["c"], D["mod"], D["sess"], D["vwap"], D["atr"], st, en,
        float(retr), float(stop_frac), int(slope_win), float(slope_thr), int(max_cross),
        int(cutoff), 1 if use_sweep else 0, float(cost), float(slip),
        1 if allow_long else 0, 1 if allow_short else 0, float(tgt_frac))
    m = e_bar >= 0
    if not m.any():
        return pd.DataFrame()
    gross = side[m] * (x_px[m] - e_px[m])
    net = gross - 2 * cost
    t = pd.DataFrame(dict(sess=skey[m], entry_bar=e_bar[m], entry_px=e_px[m], exit_px=x_px[m],
                          side=side[m], risk=risk[m], rng=rng_sz[m], code=code[m],
                          net_pts=net, pct=100.0 * net / e_px[m],
                          R=net / np.maximum(risk[m], 1e-9)))
    t["block"] = np.where(t["sess"] < D["cut"], "research", "locked")
    t["exit_reason"] = t["code"].map({0: "stop", 1: "target", 2: "flat"})
    return t


def stats(t):
    if len(t) == 0:
        return dict(n=0, pct=np.nan, tot=np.nan, pf=np.nan, win=np.nan, dd=np.nan,
                    pts=np.nan, R=np.nan, risk_med=np.nan)
    v = t["pct"].to_numpy()
    g, b = v[v > 0].sum(), -v[v <= 0].sum()
    eq = np.cumsum(v)
    return dict(n=len(v), pct=float(v.mean()), tot=float(v.sum()),
                pf=float(g / b) if b > 0 else np.nan, win=100.0 * float((v > 0).mean()),
                dd=float((eq - np.maximum.accumulate(eq)).min()),
                pts=float(t["net_pts"].mean()), R=float(t["R"].mean()),
                risk_med=float(t["risk"].median()))
