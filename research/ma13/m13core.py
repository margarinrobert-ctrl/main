"""The submitted MA 13/48/200 rule with 100-point barriers, and the two additions measured.

The strategy as pasted: EMA(13) crossing EMA(48) in either direction, entered at the NEXT bar's
open, a fixed 100-point take profit and 100-point stop measured FROM THE FILL, one position at a
time and no reversal on an opposite cross. The MA(200) is plotted and never traded on.

Three things are added here and each is measured before it ships:

  SESSION   entries admitted only inside [start, end) New York minutes.
  FLATTEN   optionally close at the window's end, filled at the NEXT bar's OPEN because
            `strategy.close_all()` cannot sell the close of the bar that triggers it.
  BREAKEVEN once the favourable excursion reaches `be_pts` from the fill, the stop moves to the
            fill + `be_off`. It ARMS on that bar and can only BIND from the bar after -- inside one
            bar OHLC cannot order the excursion against the pullback.

Two arithmetic facts govern the reading and are printed before any P&L:

  A POINT IS NOT A GEOMETRY. 100 points is 2.35x the median in-window ATR on US30 and 4.36x on
  US100, and on US30 alone it was 4.23 ATR in 2016 against 1.10 in 2025 (`STUDY_DL50`), so a points
  barrier confounds geometry with market and with era.

  A BREAKEVEN AT OR BEYOND THE TARGET CANNOT FIRE, because the target resolves first on the same
  bar -- so those rungs are INERT and must be excluded from the multiplicity count.
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd
from numba import njit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "nineam"))
import na_core as N                                    # loader, blocks, costs, mde, e_max_normal

COST = N.COST
load = N.load
blocks = N.blocks
mde = N.mde
e_max_normal = N.e_max_normal
pval = N.pval
boot_edge = N.boot_edge
attach_day = N.attach_day


def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def signals(f, fast=13, slow=48, side="both"):
    """EMA cross in either direction. The signal is known at the bar's CLOSE and fills next open."""
    c = f["close"].to_numpy()
    mf, ms = ema(c, fast), ema(c, slow)
    up = (mf > ms) & ~(np.r_[False, mf[:-1] > ms[:-1]])
    dn = (mf < ms) & ~(np.r_[False, mf[:-1] < ms[:-1]])
    sig, sd = [], []
    for i in range(len(c)):
        if side in ("long", "both") and up[i]:
            sig.append(i); sd.append(1)
        elif side in ("short", "both") and dn[i]:
            sig.append(i); sd.append(-1)
    return np.asarray(sig, np.int64), np.asarray(sd, np.int64)


@njit(cache=True)
def _walk(o, h, l, c, mod, sig, side, tp, sl, s0, s1, flat_m, cost, be_pts, be_off):
    n = len(c); m = len(sig)
    eb = np.full(m, -1, np.int64); xb = np.full(m, -1, np.int64)
    pts = np.zeros(m); why = np.zeros(m, np.int64); amb = np.zeros(m, np.int64)
    last = -1
    for q in range(m):
        i = sig[q]
        if i <= last or i + 1 >= n:
            continue
        if s0 >= 0 and not (mod[i] >= s0 and mod[i] < s1):
            continue
        s = side[q]
        e = o[i + 1]
        stop = e - s * sl
        tgt = e + s * tp
        j = i + 1
        ex = np.nan; rsn = 0
        armed = False
        be_lvl = e + s * be_off
        while j < n:
            hs = (l[j] <= stop) if s > 0 else (h[j] >= stop)
            ht = (h[j] >= tgt) if s > 0 else (l[j] <= tgt)
            if hs and ht:
                amb[q] = 1
            if hs:
                ex = stop; rsn = 1; break
            if ht:
                ex = tgt; rsn = 2; break
            if flat_m > 0 and j + 1 < n and mod[j + 1] >= flat_m and mod[j] < flat_m:
                ex = o[j + 1]; rsn = 3; j = j + 1; break
            if flat_m > 0 and j + 1 < n and mod[j + 1] < mod[j]:
                ex = c[j]; rsn = 4; break
            if be_pts > 0 and not armed:
                fav = (h[j] - e) if s > 0 else (e - l[j])
                if fav >= be_pts:
                    armed = True
                    if (s > 0 and be_lvl > stop) or (s < 0 and be_lvl < stop):
                        stop = be_lvl
            j += 1
        if not np.isfinite(ex):
            ex = c[n - 1]; rsn = 5; j = n - 1
        p = s * (ex - e) - cost
        eb[q] = i + 1; xb[q] = j; pts[q] = p; why[q] = rsn
        last = j
    return eb, xb, pts, why, amb


def run(f, sig, side, tp=100.0, sl=100.0, s0=-1, s1=-1, flat_m=0, cost=2.29,
        be_pts=0.0, be_off=0.0):
    o = f["open"].to_numpy(); h = f["high"].to_numpy(); l = f["low"].to_numpy()
    c = f["close"].to_numpy(); mod = f["mod"].to_numpy()
    eb, xb, pts, why, amb = _walk(o, h, l, c, mod, sig, side, float(tp), float(sl),
                                  int(s0), int(s1), int(flat_m), float(cost),
                                  float(be_pts), float(be_off))
    k = eb >= 0
    ent = o[np.where(k, eb, 0)]
    return pd.DataFrame(dict(sig=sig[k], eb=eb[k], xb=xb[k], side=side[k], pts=pts[k],
                             why=why[k], amb=amb[k], ent=ent[k], atr=f["atr"].to_numpy()[sig[k]],
                             pct=100.0 * pts[k] / ent[k]))


def control(f, tr, sig_all, seed=0, n_draw=300, s0=-1, s1=-1, **kw):
    """A RANDOM eligible bar in the same window with the same side mix and identical barriers.
    The drawn bars are SORTED before the walk -- the position lock rejects out-of-order signals and
    an unsorted control keeps a different fraction of its trades every draw (`STUDY_V59`)."""
    mod = f["mod"].to_numpy()
    ok = np.ones(len(f), bool)
    if s0 >= 0:
        ok &= (mod >= s0) & (mod < s1)
    elig = np.flatnonzero(ok)
    sd = tr["side"].to_numpy()
    nt = len(tr)
    rng = np.random.default_rng(seed)
    out = np.zeros(n_draw)
    for d in range(n_draw):
        pick = rng.choice(elig, size=min(int(nt * 1.6), len(elig)), replace=False)
        pick.sort()
        sides = rng.choice(sd, size=len(pick), replace=True)
        t = run(f, pick, sides, s0=s0, s1=s1, **kw)
        out[d] = t["pct"].mean() if len(t) else np.nan
    return out


WHY = {1: "stop", 2: "target", 3: "flat", 4: "roll", 5: "end"}


def mix(t):
    v = t["why"].to_numpy()
    return {WHY[k]: round(float((v == k).mean()), 3) for k in (1, 2, 3)}
