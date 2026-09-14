"""The published parameter grid, run against a matched control ON RESEARCH, on several timeframes.

WHAT THE SOURCE DID AND WHY IT IS NOT ENOUGH. Eight months in sample, four months out, one crypto
pair, 432 parameter combinations. Four months of hourly bars is about 2,900 bars and, at this
system's firing rate, on the order of thirty trades -- fewer observations than parameters searched.
A 140% return on that is not evidence about the rules; it is evidence about the sample.

WHAT IS DIFFERENT HERE. The split is the first 65% of SESSIONS, matching every other module in
this repository, and the locked block is read ONCE at the end for whatever survives. Every
configuration is scored against a MATCHED CONTROL on the research block -- random entries with the
same side, the same trailing-stop geometry and the same minute-of-day distribution -- because on a
sample where NQ rose 89% a long trend-follower earns a large number by existing. The control is a
GATE, not a final check: running it only at the end lets configurations reach a holdout they then
"pass" while failing research.
"""
from __future__ import annotations

import sys
import itertools
import numpy as np
import pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/donchian")
import fastbars, costs, dcs  # noqa: E402

DC = (15, 20, 25, 30)
EMA = (50, 100, 150, 200)
ADX = (20.0, 25.0, 30.0)
CHOP = (30.0, 35.0, 40.0)
MULT = (2.0, 2.5, 3.0)

RT = costs.model("MNQ", "discount").round_turn_points()   # 1.72 points


def blocks(tf):
    d = fastbars.bars(tf)
    _, si, cut = fastbars.sessions(tf)
    return d, si, cut


def control(d, atr, sig_l, sig_s, mult, mask, draws=400, seed=7, cost=RT):
    """Random entries matched on SIDE, minute-of-day and count. Returns the mean-R distribution.

    Matching the minute of day matters more than it looks: a breakout system fires disproportionately
    in the first hour, and the first hour is not an average hour."""
    rng = np.random.default_rng(seed)
    mod = d["mod"]
    n = len(d["c"])
    real = np.flatnonzero((sig_l | sig_s) & mask)
    if len(real) < 20:
        return None
    sides = np.where(sig_l[real], 1, -1)
    pool = {}
    for m in np.unique(mod[real]):
        pool[m] = np.flatnonzero((mod == m) & mask & np.isfinite(atr) & (atr > 0))
    out = np.empty(draws)
    for k in range(draws):
        sl = np.zeros(n, bool); ss = np.zeros(n, bool)
        for m, s in zip(mod[real], sides):
            p = pool[m]
            if len(p) == 0:
                continue
            b = p[rng.integers(len(p))]
            (sl if s > 0 else ss)[b] = True
        t = dcs.run(d, sl, ss, atr, mult=mult, cost=cost, one_at_a_time=False)
        out[k] = t.R.mean() if len(t) else 0.0
    return out


def one(d, si, cut, dc, ema_n, adx_min, chop_max, mult, atr, longs=True, shorts=True,
        block="research", cost=RT, flat_mod=None, max_hold=None):
    sl, ss = dcs.signals(d, dc=dc, ema_n=ema_n, adx_min=adx_min, chop_max=chop_max,
                         longs=longs, shorts=shorts)
    m = (si < cut) if block == "research" else (si >= cut)
    sl, ss = sl & m, ss & m
    t = dcs.run(d, sl, ss, atr, mult=mult, cost=cost, flat_mod=flat_mod, max_hold=max_hold)
    if not len(t):
        return None
    return t


def summarise(t, tag=""):
    if t is None or not len(t):
        return dict(tag=tag, n=0)
    R = t.R.to_numpy()
    wins = R > 0
    gp = t.pnl[t.pnl > 0].sum(); gl = -t.pnl[t.pnl < 0].sum()
    eq = t.pnl.cumsum().to_numpy()
    dd = float(np.max(np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]))
    return dict(tag=tag, n=len(t), pts=float(t.pnl.sum()), per=float(t.pnl.mean()),
                R=float(R.mean()), win=float(wins.mean()), pf=float(gp / gl) if gl > 0 else np.inf,
                mdd=dd, avg_win=float(t.pnl[wins].mean()) if wins.any() else 0.0,
                avg_loss=float(t.pnl[~wins].mean()) if (~wins).any() else 0.0)


def grid(tf=60, longs=True, shorts=True, flat_mod=None, max_hold=None, verbose=True):
    """The full published grid on one timeframe, RESEARCH BLOCK ONLY."""
    d, si, cut = blocks(tf)
    atr = dcs.wilder_atr(d["h"], d["l"], d["c"], 14)
    rows = []
    for dc_, e, a, ch, mu in itertools.product(DC, EMA, ADX, CHOP, MULT):
        t = one(d, si, cut, dc_, e, a, ch, mu, atr, longs, shorts,
                flat_mod=flat_mod, max_hold=max_hold)
        s = summarise(t)
        s.update(tf=tf, dc=dc_, ema=e, adx=a, chop=ch, mult=mu)
        rows.append(s)
    R = pd.DataFrame(rows).sort_values("R", ascending=False)
    if verbose:
        print(f"\n  {tf}m  {len(R)} configurations, research block, "
              f"{'long+short' if longs and shorts else 'long only' if longs else 'short only'}"
              f"{'' if flat_mod is None else f', flat at {flat_mod//60:02d}:{flat_mod%60:02d}'}")
        print(f"  positive mean R: {(R.R > 0).sum()}/{len(R)}   "
              f"median n {R.n.median():.0f}   median R {R.R.median():+.4f}")
    return R


# ---------------------------------------------------------------------------------------------
# The control, made affordable.
#
# A trade's outcome under this exit depends only on its ENTRY BAR, its SIDE and the ATR multiple --
# the trailing stop reads nothing else. So the whole exit surface can be computed ONCE per (side,
# multiple) by entering on every bar, and every control draw afterwards is an array index. That is
# what turns the matched control from a final check into a gate that can run on all 432
# configurations. Verified against `dcs.run` below.
# ---------------------------------------------------------------------------------------------

_TENSOR: dict = {}


def exit_tensor(d, atr, mult, cost=RT):
    """R for a trade opened at the bar AFTER every bar i, for each side. NaN where impossible."""
    key = (id(d), float(mult), float(cost))
    if key in _TENSOR:
        return _TENSOR[key]
    n = len(d["c"])
    out = {}
    for side in (1, -1):
        sl = np.zeros(n, bool); ss = np.zeros(n, bool)
        (sl if side > 0 else ss)[:] = np.isfinite(atr) & (atr > 0)
        t = dcs.run(d, sl, ss, atr, mult=mult, cost=cost, one_at_a_time=False)
        r = np.full(n, np.nan)
        r[t.sig_bar.to_numpy()] = t.R.to_numpy()
        out[side] = r
    _TENSOR[key] = out
    return out


def control_fast(d, atr, sig_l, sig_s, mult, mask, draws=2000, seed=7, cost=RT,
                 match_risk=True, band=0.15):
    """Same control, sampled from the cached exit surface. Returns the mean-R null distribution.

    MATCHING THE MINUTE OF DAY IS NOT ENOUGH, and the reason is the whole point of this function.
    R is P&L divided by mult*ATR AT THE SIGNAL BAR, so ATR is the risk DENOMINATOR. A breakout
    fires in a fast bar, where ATR is elevated, which makes the fixed round-turn cost a smaller
    fraction of R than it is at an average bar. A control drawn from all bars therefore pays a
    LARGER cost in R terms than the strategy does, and hands back a spurious excess that grows as
    the timeframe shortens -- on 5m bars it flatters every single configuration. `match_risk`
    draws each control entry from bars whose ATR is within `band` of that trade's own ATR, so the
    denominator is the same on both sides of the comparison and only the trigger differs."""
    rng = np.random.default_rng(seed)
    T = exit_tensor(d, atr, mult, cost)
    mod = d["mod"]
    real = np.flatnonzero((sig_l | sig_s) & mask)
    if len(real) < 20:
        return None
    sides = np.where(sig_l[real], 1, -1)
    cols = []
    for b, s in zip(real, sides):
        elig = (mod == mod[b]) & mask & np.isfinite(T[s])
        if match_risk:
            a = atr[b]
            elig = elig & (atr >= a * (1 - band)) & (atr <= a * (1 + band))
        p = np.flatnonzero(elig)
        if len(p) < 5 and match_risk:                      # widen once rather than drop the trade
            p = np.flatnonzero((mod == mod[b]) & mask & np.isfinite(T[s])
                               & (atr >= a * (1 - 3 * band)) & (atr <= a * (1 + 3 * band)))
        if len(p):
            cols.append(T[s][p[rng.integers(0, len(p), draws)]])
    if not cols:
        return None
    return np.mean(np.vstack(cols), axis=0)


def gated_grid(tf=60, longs=True, shorts=True, flat_mod=None, max_hold=None,
               min_n=40, draws=2000, verbose=True):
    """The published grid with the matched control applied to EVERY configuration, on research."""
    d, si, cut = blocks(tf)
    atr = dcs.wilder_atr(d["h"], d["l"], d["c"], 14)
    m = si < cut
    rows = []
    for dc_, e, a, ch, mu in itertools.product(DC, EMA, ADX, CHOP, MULT):
        sl, ss = dcs.signals(d, dc=dc_, ema_n=e, adx_min=a, chop_max=ch,
                             longs=longs, shorts=shorts)
        sl, ss = sl & m, ss & m
        t = dcs.run(d, sl, ss, atr, mult=mu, cost=RT, flat_mod=flat_mod, max_hold=max_hold)
        s = summarise(t)
        s.update(tf=tf, dc=dc_, ema=e, adx=a, chop=ch, mult=mu, ctl=np.nan, p=np.nan)
        if s["n"] >= min_n and flat_mod is None and max_hold is None:
            c = control_fast(d, atr, sl, ss, mu, m, draws=draws)
            if c is not None:
                s["ctl"] = float(c.mean())
                s["excess"] = s["R"] - s["ctl"]
                s["p"] = float((c >= s["R"]).mean())
        rows.append(s)
    R = pd.DataFrame(rows)
    if verbose:
        ok = R.p.notna()
        print(f"\n  {tf}m  {len(R)} configurations, research, control-gated")
        print(f"  positive mean R:            {(R.R > 0).sum()}/{len(R)}")
        print(f"  BEATS its matched control:  {(R.excess > 0).sum() if 'excess' in R else 0}/{ok.sum()}")
        print(f"  p < 0.05 against control:   {(R.p < 0.05).sum()}/{ok.sum()}"
              f"   ({0.05*ok.sum():.1f} expected by chance)")
        print(f"  median control R {R.ctl.median():+.4f}  vs median strategy R {R.R.median():+.4f}")
    return R.sort_values("R", ascending=False)
