"""US30 07:00-11:00 New York, asked as an arithmetic question before it is asked as a rule.

WHAT THIS BRANCH ALREADY KNOWS ABOUT THIS EXACT CELL, so none of it is re-run:
  `STUDY_DL50`     a Donchian-20 + EMA200 breakout here reads research PF 1.041 -> holdout 0.956,
                   and on the holdout a RANDOM ENTRY in the same window beats it while ALWAYS-LONG
                   in that window is positive -- the failure is in the trigger, not the session.
  `STUDY_MR30`     20 declared conditions x 3 holding lengths through an exposure-matched test:
                   1 of 60 clears p<=0.05 where 3.0 are expected. Timing inside US30 is worth
                   nothing that a circular shift of the same mask cannot reproduce.
  `STUDY_SCALP_REQUIREMENTS`  the GEOMETRY flips the sign before any indicator -- the same triggers
                   earn -0.003 %/trade at scalp geometry and +0.095 at swing -- and the mechanism
                   is cost as a fraction of risk, which no indicator closes.
  `STUDY_V69_ORB`  a filter moves NET toward GROSS and can never pass it, so GROSS is the ceiling;
                   read it before building anything to fix a cost problem.

SO THE FIRST QUESTION IS NOT WHICH RULE. It is whether the arithmetic leaves a scalp open here at
all: what the round turn costs as a fraction of the stop, what break-even win rate that implies,
and what the population actually delivers. If gross sits at the driftless bound there is nothing
underneath the cost for any filter to uncover.

DATA. `US30_1m` IS MISSING from disk -- `python research/datasets.py` -- so the finest US30 series
available is 15-minute and a 07:00-11:00 session is SIXTEEN BARS. Every number here inherits that:
a "scalp" at this resolution is a 15-minute-bar trade, the true 1-minute exit path cannot be walked
(`STUDY_ATME_LIVE` cut a result fivefold on exactly that), and any barrier pair tight enough to sit
inside one bar is set by the tie-break rather than by the market. Stated once, applies throughout.

BLOCKS. A = US30L before 2023-01-01, B = the rest, C = US30_ISO after US30L ends, a DIFFERENT
PROVIDER over a span no search on this branch has touched. A and B are heavily spent -- six studies
have read them -- so a p-value on either is descriptive and C is the only one that is not.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "research"))
sys.path.insert(0, os.path.join(ROOT, "research", "mr30"))
import mr30core as M  # noqa: E402

COST = M.COST          # 2.29 index points round turn
PV = M.PV              # $5 a point
W0, W1 = 420, 660      # 07:00 .. 11:00 New York, in minutes of day
FLAT = 660             # flat at the 11:00 OPEN


def load(name="US30L"):
    return M.load(name)


def blocks(f, name="US30L"):
    return M.blocks(f, name)


def window(f, m0=W0, m1=W1):
    mod = f["mod"].to_numpy()
    return (mod >= m0) & (mod < m1)


# ------------------------------------------------------------------ the walker ---------------
@njit(cache=True)
def _walk(o, h, l, c, at, mod, day, sig, side, stop_a, tgt_a, hold, cost, m0, m1, flat, tie,
          use_pts):
    """One live position, ATR barriers at the SIGNAL bar, stop-first tie-break with the ambiguous
    share returned, and a CLOCK FLATTEN that fills at the open of the first bar at or after
    `flat` -- `STUDY_V60`: "flat by 11:00" means flat at the 11:00 OPEN, and a signal whose fill
    would land at or after the cutoff is REFUSED rather than opened for zero P&L."""
    n = len(c); m = len(sig)
    eb = np.full(m, -1, np.int64); xb = np.full(m, -1, np.int64)
    pts = np.zeros(m); rr = np.zeros(m); risk = np.zeros(m)
    why = np.zeros(m, np.int64); amb = np.zeros(m, np.int64); sd = np.zeros(m, np.int64)
    cnt = 0; last = -1
    for q in range(m):
        i = sig[q]
        if i <= last or i + 1 >= n:
            continue
        if at[i] <= 0 or not np.isfinite(at[i]):
            continue
        if m0 >= 0 and (mod[i] < m0 or mod[i] >= m1):
            continue
        j = i + 1
        if flat > 0 and (mod[j] >= flat or day[j] != day[i]):
            continue                                   # the fill itself would be at/after the bell
        s = side[q]
        ent = o[j]
        rk = stop_a if use_pts == 1 else stop_a * at[i]
        stop = ent - s * rk
        targ = ent + s * (tgt_a if use_pts == 1 else tgt_a * at[i])
        x = -1; px = 0.0; w = 2; a = 0
        for t in range(j, n):
            if flat > 0 and (mod[t] >= flat or day[t] != day[j]):
                x = t; px = o[t]; w = 3          # flattened at this bar's OPEN
                break
            hs = (l[t] <= stop) if s > 0 else (h[t] >= stop)
            ht = (h[t] >= targ) if s > 0 else (l[t] <= targ)
            if hs and ht:
                a = 1
                if tie == 1:                     # target-first: the OPTIMISTIC convention
                    x = t; px = targ; w = 1
                    break
            if hs:
                x = t; px = stop; w = 0
                break
            if ht:
                x = t; px = targ; w = 1
                break
            if hold > 0 and t - j >= hold:
                x = t; px = c[t]; w = 2
                break
        if x < 0:
            x = n - 1; px = c[n - 1]; w = 2
        eb[cnt] = j; xb[cnt] = x
        pts[cnt] = s * (px - ent) - cost
        rr[cnt] = pts[cnt] / rk
        risk[cnt] = rk; why[cnt] = w; amb[cnt] = a; sd[cnt] = s
        cnt += 1
        last = x
    return (eb[:cnt], xb[:cnt], pts[:cnt], rr[:cnt], risk[:cnt], why[:cnt], amb[:cnt], sd[:cnt])


WHY = {0: "stop", 1: "target", 2: "hold", 3: "flatten"}


def walk(f, sig, side, stop_a=1.5, tgt_a=1.5, hold=0, cost=COST, m0=W0, m1=W1, flat=FLAT,
         tie=0, use_pts=0):
    """`use_pts=1` reads stop_a/tgt_a as ABSOLUTE POINTS rather than ATR multiples. Both are
    provided because `STUDY_DL50` found the two parameterisations disagree about whether a US30
    result decays at all -- a fixed 50-point stop is 4.23 ATR in 2016 and 1.10 ATR in 2025."""
    order = np.argsort(np.asarray(sig))
    s_ = np.asarray(sig)[order].astype(np.int64)
    d_ = np.asarray(side)[order].astype(np.int64)
    day = f.index.normalize().astype(np.int64).to_numpy()
    eb, xb, pts, rr, rk, why, amb, sd = _walk(
        f["open"].to_numpy(), f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy(),
        f["atr"].to_numpy(), f["mod"].to_numpy().astype(np.int64), day, s_, d_,
        float(stop_a), float(tgt_a), int(hold), float(cost), int(m0), int(m1), int(flat),
        int(tie), int(use_pts))
    t = pd.DataFrame(dict(e_bar=eb, x_bar=xb, pts=pts, R=rr, risk=rk, why=why, amb=amb, side=sd))
    if not len(t):
        return t
    t["ts"] = f.index[eb]
    t["pct"] = 100.0 * t.pts / f["open"].to_numpy()[eb]
    t["hold"] = t.x_bar - t.e_bar
    t["mins"] = t["hold"] * 15
    return t


# ------------------------------------------------------------------ triggers ------------------
def donchian(f, n=20, side=1):
    h, l, c = f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy()
    up = pd.Series(h).rolling(n).max().shift(1).to_numpy()
    dn = pd.Series(l).rolling(n).min().shift(1).to_numpy()
    ok = (c > up) if side > 0 else (c < dn)
    ok = np.asarray(ok) & np.isfinite(up) & np.isfinite(dn)
    ok[:n + 2] = False; ok[-2:] = False
    s = np.flatnonzero(ok)
    return s, np.full(len(s), side, np.int64)


def fade(f, n=4, k=1.5):
    """`STUDY_MR30`'s primary: side FORCED to -sign(displacement)."""
    return M.events(f, n, k, fade=True)[:2]


def everybar(f, side=1):
    ok = np.isfinite(f["atr"].to_numpy()) & (f["atr"].to_numpy() > 0)
    ok[:30] = False; ok[-2:] = False
    s = np.flatnonzero(ok)
    return s, np.full(len(s), side, np.int64)


# ------------------------------------------------------------------ arithmetic ----------------
def breakeven(stop_a, tgt_a, cost, atr):
    """Driftless break-even win rate for a two-outcome barrier pair, cost expressed in ATR."""
    return (stop_a + cost / max(atr, 1e-9)) / (stop_a + tgt_a)


def pf(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return float(x[x > 0].sum() / max(-x[x < 0].sum(), 1e-12)) if len(x) >= 5 else np.nan


def summ(t, label=""):
    if not len(t):
        return dict(rule=label, n=0)
    r = t["R"].to_numpy(); p = t["pts"].to_numpy()
    res = t[t.why.isin([0, 1])]
    return dict(rule=label, n=len(t), pts=float(p.mean()), pct=float(t["pct"].mean()),
                R=float(r.mean()), pf=pf(p), win=float((p > 0).mean()),
                res_win=float((res.why == 1).mean()) if len(res) else np.nan,
                amb=float(t["amb"].mean()), med_min=float(t["mins"].median()),
                stop_sh=float((t.why == 0).mean()), tgt_sh=float((t.why == 1).mean()),
                flat_sh=float((t.why == 3).mean()))


def ema_state(f, fast=13, slow=48, side=1):
    c = pd.Series(f["close"].to_numpy())
    a, b = c.ewm(span=fast, adjust=False).mean(), c.ewm(span=slow, adjust=False).mean()
    ok = (a > b).to_numpy() if side > 0 else (a < b).to_numpy()
    ok[:slow * 3] = False; ok[-2:] = False
    s = np.flatnonzero(ok)
    return s, np.full(len(s), side, np.int64)


TRIGGERS = {
    "donch20 long":  lambda f: donchian(f, 20, 1),
    "donch20 short": lambda f: donchian(f, 20, -1),
    "donch10 long":  lambda f: donchian(f, 10, 1),
    "donch10 short": lambda f: donchian(f, 10, -1),
    "fade n4 k1.5":  lambda f: fade(f, 4, 1.5),
    "fade n8 k2.0":  lambda f: fade(f, 8, 2.0),
    "ema13>48 long": lambda f: ema_state(f, 13, 48, 1),
}


def control(f, n_target, side_arr, elig, n_draw=400, seed=0, **kw):
    """Matched random ENTRY: the same number of signals drawn from the ELIGIBLE in-window bars,
    the same side distribution, and SORTED so the position lock rejects the same share
    (`STUDY_V59`: unsorted draws exploded the spread and made everything fail)."""
    rng = np.random.default_rng(seed)
    pool = np.flatnonzero(elig)
    if len(pool) < n_target or n_target < 5:
        return None
    out = np.empty(n_draw)
    for i in range(n_draw):
        pick = np.sort(rng.choice(pool, size=n_target, replace=False))
        sd = rng.permutation(side_arr)[:len(pick)]
        t = walk(f, pick, sd, **kw)
        out[i] = t["pts"].mean() if len(t) else np.nan
    return out[np.isfinite(out)]
