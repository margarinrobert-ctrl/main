"""Pricing the 11:00 FLATTEN honestly, in one specific configuration, rather than assuming it.

WHY THIS IS A SEPARATE QUESTION FROM THE ONES ALREADY SETTLED.
`docs/ib/STUDY_US30_SCALP_0711.md` settled the geometry, the trigger and the statistical power of
this cell -- do not re-run its sections 1-11. What it did NOT do is take the flatten apart as an
EXIT MECHANISM. Its section 5 read the flatten as one line of a four-row table (research -1.69,
holdout +0.47) and its section 4 read it as one axis of a marginal average. Neither says WHY, and
this branch's sixteen recorded confirmations that a hard flatten is destructive were all measured
on strategies with much longer natural holds -- `STUDY_V63`'s median winner ran TEN TRADING DAYS,
so a bell that closes it is obviously expensive there and says nothing about a rule whose median
hold is 30 minutes.

SO THE QUESTION HERE IS NARROW AND MECHANICAL: on the ONE configuration the user insists on --
Donchian 20 long, 07:00-11:00 New York, 30-point stop, 150-point target -- what does the clock
actually close, what were those trades worth at the bell, and what did they become afterwards.

WHAT THE MECHANISM PREDICTS, written before the numbers. The flatten can only cost money through
trades it closes that would otherwise have resolved BETTER. With a 1:5 payoff and a 26.7% win rate
the money is in the tail (`STUDY_V63`: the capped 14% supplied 261% of net), so if the bell is
expensive it must be truncating trades on their way to +150. If instead the flattened trades were
mostly going to hit the 30-point stop, the bell is a CHEAP exit and the branch's standing finding
does not apply at this hold length. Both are measurable directly and neither needs a p-value.

DECLARED CELLS -- 15 research hypotheses, and nothing else is scored:
  A. flatten ladder      5 exit policies x 2 geometries (30/150 and 50/150)   = 10
  B. entry sub-windows   5 windows, 30/150 geometry, flatten ON               =  5
  C. give-back           descriptive, no test
  D. tie-break bracket   every A and B cell re-read under tie=1 -- a ROBUSTNESS re-read of the
                         same 15 hypotheses, not 15 more
  E. drawdown permutation on flatten-on and flatten-off -- descriptive
RESERVED: 2 holdout reads and 2 forward reads, on cells named before either block is opened.

R IS NOT THE UNIT FOR THE GIVE-BACK. `STUDY_V43`: R = stop x whatever, so any statistic divided by
it puts the stop back in the denominator. Excursions are reported in ATR AT THE SIGNAL BAR.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "research"))
sys.path.insert(0, os.path.join(ROOT, "research", "us30scalp"))
sys.path.insert(0, os.path.join(ROOT, "research", "mr30"))
import s30core as S  # noqa: E402

COST = S.COST
W0, W1 = S.W0, S.W1

# --------------------------------------------------------------- declared configurations -----
# hold caps are in 15-MINUTE BARS. The feed carries a median 86 bars a session.
BAR_MIN = 15
CAP_4H = 16
CAP_1D = 96

# (label, flat, hold)
LADDER = [
    ("flat 11:00",        660,  0),
    ("flat 12:00",        720,  0),
    ("flat 16:00",        960,  0),
    ("no flat, 4h cap",     0, CAP_4H),
    ("no flat, 1d cap",     0, CAP_1D),
]

GEOMS = [("30/150", 30.0, 150.0), ("50/150", 50.0, 150.0)]

SUBWINDOWS = [
    ("07:00-11:00", 420, 660),
    ("08:00-11:00", 480, 660),
    ("09:30-11:00", 570, 660),
    ("07:00-09:30", 420, 570),
    ("10:00-11:00", 600, 660),
]


# --------------------------------------------------------------- the walker + excursions -----
@njit(cache=True)
def _walk_x(o, h, l, c, at, mod, day, sig, side, stop_a, tgt_a, hold, cost, m0, m1, flat, tie,
            use_pts, cont_cap):
    """`s30core._walk` with three additions and NO change to any shared output:

      mfe/mae  -- the favourable and adverse excursion in POINTS over the bars the position was
                  actually live, ending at the exit PRICE (so a target exit reads exactly +target
                  and a bell exit reads the open it filled at, never the rest of that bar).
      atr_sig  -- ATR(14) at the SIGNAL bar, which is the denominator `STUDY_V43` requires.
      cont     -- the COUNTERFACTUAL: the same position, same barriers, left open past the bell
                  until the stop, the target or `cont_cap` bars from entry. For a trade that
                  resolved on its own this is identical to its own result by construction.
    """
    n = len(c); m = len(sig)
    eb = np.full(m, -1, np.int64); xb = np.full(m, -1, np.int64)
    pts = np.zeros(m); rr = np.zeros(m); risk = np.zeros(m)
    why = np.zeros(m, np.int64); amb = np.zeros(m, np.int64); sd = np.zeros(m, np.int64)
    mfe = np.zeros(m); mae = np.zeros(m); ats = np.zeros(m)
    cont = np.zeros(m); cwhy = np.zeros(m, np.int64)
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
            continue
        s = side[q]
        ent = o[j]
        rk = stop_a if use_pts == 1 else stop_a * at[i]
        stop = ent - s * rk
        targ = ent + s * (tgt_a if use_pts == 1 else tgt_a * at[i])
        x = -1; px = 0.0; w = 2; a = 0
        best = -1e18; worst = 1e18
        for t in range(j, n):
            if flat > 0 and (mod[t] >= flat or day[t] != day[j]):
                x = t; px = o[t]; w = 3
                break
            hs = (l[t] <= stop) if s > 0 else (h[t] >= stop)
            ht = (h[t] >= targ) if s > 0 else (l[t] <= targ)
            if hs and ht:
                a = 1
                if tie == 1:
                    x = t; px = targ; w = 1
                    break
            if hs:
                x = t; px = stop; w = 0
                break
            if ht:
                x = t; px = targ; w = 1
                break
            # the bar completed with the position still live: its whole range counts
            fav = s * (h[t] - ent) if s > 0 else s * (l[t] - ent)
            adv = s * (l[t] - ent) if s > 0 else s * (h[t] - ent)
            if fav > best:
                best = fav
            if adv < worst:
                worst = adv
            if hold > 0 and t - j >= hold:
                x = t; px = c[t]; w = 2
                break
        if x < 0:
            x = n - 1; px = c[n - 1]; w = 2
        ex = s * (px - ent)
        if ex > best:
            best = ex
        if ex < worst:
            worst = ex
        # ---- the counterfactual: leave it open past the bell
        cp = px; cw = w
        if w == 3 or w == 2:
            cp = c[min(n - 1, j + cont_cap)]; cw = 2
            for t in range(x, n):
                if t - j >= cont_cap:
                    cp = c[t]; cw = 2
                    break
                hs = (l[t] <= stop) if s > 0 else (h[t] >= stop)
                ht = (h[t] >= targ) if s > 0 else (l[t] <= targ)
                if hs and ht:
                    if tie == 1:
                        cp = targ; cw = 1
                    else:
                        cp = stop; cw = 0
                    break
                if hs:
                    cp = stop; cw = 0
                    break
                if ht:
                    cp = targ; cw = 1
                    break
        eb[cnt] = j; xb[cnt] = x
        pts[cnt] = s * (px - ent) - cost
        rr[cnt] = pts[cnt] / rk
        risk[cnt] = rk; why[cnt] = w; amb[cnt] = a; sd[cnt] = s
        mfe[cnt] = best; mae[cnt] = worst; ats[cnt] = at[i]
        cont[cnt] = s * (cp - ent) - cost; cwhy[cnt] = cw
        cnt += 1
        last = x
    return (eb[:cnt], xb[:cnt], pts[:cnt], rr[:cnt], risk[:cnt], why[:cnt], amb[:cnt], sd[:cnt],
            mfe[:cnt], mae[:cnt], ats[:cnt], cont[:cnt], cwhy[:cnt])


def walkx(f, sig, side, stop_a=30.0, tgt_a=150.0, hold=0, cost=COST, m0=W0, m1=W1, flat=660,
          tie=0, use_pts=1, cont_cap=CAP_1D):
    order = np.argsort(np.asarray(sig))
    s_ = np.asarray(sig)[order].astype(np.int64)
    d_ = np.asarray(side)[order].astype(np.int64)
    day = f.index.normalize().astype(np.int64).to_numpy()
    out = _walk_x(f["open"].to_numpy(), f["high"].to_numpy(), f["low"].to_numpy(),
                  f["close"].to_numpy(), f["atr"].to_numpy(),
                  f["mod"].to_numpy().astype(np.int64), day, s_, d_,
                  float(stop_a), float(tgt_a), int(hold), float(cost), int(m0), int(m1),
                  int(flat), int(tie), int(use_pts), int(cont_cap))
    eb, xb, pts, rr, rk, why, amb, sd, mfe, mae, ats, cont, cwhy = out
    t = pd.DataFrame(dict(e_bar=eb, x_bar=xb, pts=pts, R=rr, risk=rk, why=why, amb=amb, side=sd,
                          mfe=mfe, mae=mae, atr_sig=ats, cont=cont, cont_why=cwhy))
    if not len(t):
        return t
    t["ts"] = f.index[eb]
    t["day"] = f.index.normalize()[eb]
    t["hold"] = t.x_bar - t.e_bar
    t["mins"] = t["hold"] * BAR_MIN
    t["mfe_atr"] = t.mfe / t.atr_sig
    t["mae_atr"] = t.mae / t.atr_sig
    t["gross"] = t.pts + COST
    t["give_atr"] = (t.mfe - t.gross) / t.atr_sig
    return t


# --------------------------------------------------------------- statistics -------------------
def mde(x, power_t=2.802):
    """Minimum detectable effect at 80% power: 2.802 * sd / sqrt(n). `STUDY_US30_SCALP_0711` s9."""
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return float(power_t * x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 2 else np.nan


def be_pts(stop, tgt, cost=COST):
    """Driftless two-outcome break-even. `STUDY_V45`: only valid where the FLATTEN SHARE is small,
    so it is never printed here without the flatten share beside it."""
    return (stop + cost) / (stop + tgt)


def summ(t, stop, tgt, label=""):
    if not len(t):
        return dict(cell=label, n=0)
    p = t["pts"].to_numpy()
    res = t[t.why.isin([0, 1])]
    return dict(cell=label, n=len(t), pts=float(p.mean()), sd=float(p.std(ddof=1)),
                t=float(p.mean() / (p.std(ddof=1) / np.sqrt(len(p)))),
                mde=mde(p), pf=S.pf(p), win=float((p > 0).mean()),
                res_win=float((res.why == 1).mean()) if len(res) else np.nan,
                be=be_pts(stop, tgt), amb=float(t["amb"].mean()),
                med_min=float(t["mins"].median()),
                stop_sh=float((t.why == 0).mean()), tgt_sh=float((t.why == 1).mean()),
                cap_sh=float((t.why == 2).mean()), flat_sh=float((t.why == 3).mean()))


def elig_mask(f, m0, m1):
    at = f["atr"].to_numpy()
    ok = np.isfinite(at) & (at > 0)
    mod = f["mod"].to_numpy()
    ok &= (mod >= m0) & (mod < m1)
    ok[:40] = False; ok[-2:] = False
    return ok


def control_p(f, t, m0, m1, n_draw=400, seed=0, **kw):
    """Matched random ENTRY from the same eligible in-window bars, SORTED (`STUDY_V59`)."""
    if not len(t):
        return np.nan, np.nan
    null = S.control(f, len(t), t["side"].to_numpy(), elig_mask(f, m0, m1),
                     n_draw=n_draw, seed=seed, m0=m0, m1=m1, **kw)
    if null is None or not len(null):
        return np.nan, np.nan
    obs = float(t["pts"].mean())
    return float(np.mean(null >= obs)), float(np.median(null))


# --------------------------------------------------------------- drawdown permutation ---------
def daily_pnl(f, t, mask):
    """Zero-filled over EVERY session in the block (`STUDY_V17`: over traded days only, a filter
    is paid for trading less)."""
    days = pd.Series(f.index.normalize()[mask]).drop_duplicates().sort_values()
    if not len(t):
        return pd.Series(0.0, index=pd.DatetimeIndex(days))
    g = t.groupby("day")["pts"].sum()
    return g.reindex(pd.DatetimeIndex(days)).fillna(0.0)


def maxdd(v):
    eq = np.cumsum(v)
    return float(np.max(np.maximum.accumulate(np.r_[0.0, eq]) - np.r_[0.0, eq]))


def perm_dd(v, n=4000, seed=7):
    """Permute the realised daily series -- a PATH question only (`STUDY_V31`: permuting cannot
    change the endpoint, so nothing about the edge is read from this)."""
    rng = np.random.default_rng(seed)
    v = np.asarray(v, float)
    real = maxdd(v)
    out = np.empty(n)
    for i in range(n):
        out[i] = maxdd(rng.permutation(v))
    return real, out
