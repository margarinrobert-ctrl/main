"""Trend -> pullback -> continuation on NQ, searched and validated.

STRUCTURE (fixed before any search, because the structure is the hypothesis):
  1. TREND        a fast/slow EMA relationship, optionally confirmed by slope and session VWAP.
  2. PULLBACK     price retraces INTO a zone around the fast EMA, measured in ATR units, or gives
                  back a fraction of the impulse leg, or returns inside a VWAP deviation band.
  3. CONTINUATION an explicit momentum trigger resumes the trend; the fill is the NEXT bar's open.

Three decisions are PRE-REGISTERED and are not searched, each because this repository has already
measured the cost of getting them wrong:

  * DIRECTION IS NOT A FREE PARAMETER. Every search in this project handed a side switch has
    returned "longs only" and was fitting the 2023-25 NQ uptrend, now on the eighth sighting. Both
    sides always trade. What a side switch WOULD have bought is reported separately, as a diagnostic
    rather than as a candidate.
  * SELECTION IS ON DOLLARS, NOT R. Maximising mean R converges on tiny-stop configurations: an
    Asia-session candidate reached E = +0.351R while losing $707.
  * COSTS ARE CHARGED BEFORE SELECTION, not after. $19.00 per NQ round turn (1 tick spread + 1 tick
    slippage per side + $4), and every reported figure is net.

Usage:
    python3 research/trend_pullback.py --stage prespec     # the pre-specified set, holdout closed
    python3 research/trend_pullback.py --stage search      # the systematic search
    python3 research/trend_pullback.py --stage validate    # full battery on the survivor
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, "research")
from nqdata import load_bars, minute_of_day, minutes_since_open, session_index, session_slice

POINT_VALUE_NQ = 20.0
POINT_VALUE_MNQ = 2.0
COST_NQ = 19.00          # 1 tick spread + 1 tick slippage per side + $4 commission
COST_MNQ = 3.30          # 1 tick (=$0.50) spread + 1 tick slippage per side + ~$1.50 commission
RTH_START, RTH_END = 570, 960

EMA_LENS = (9, 21, 34, 50, 100, 200)
ATR_LEN = 14


def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def atr_series(h, l, c, n):
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    a = pd.Series(tr).ewm(span=n, adjust=False).mean().to_numpy()
    a[:n] = np.nan
    return a


@njit(cache=True)
def simulate(o, h, l, c, sess, mso, ef, es, slope, atr, atr_rank, vwap, vwsd,
             trend_mode, pull_mode, pull_depth, entry_mode,
             atr_lo, atr_hi, tod_start, tod_end,
             stop_mode, stop_mult, target_mode, target_r,
             point_value, cost, side_mode, max_per_sess, cooldown):
    """One position at a time, flat at the session end, next-bar-open fills.

    A bar containing both the stop and the target books the STOP: the intrabar path is unknown and
    the pessimistic branch is the only honest one.
    """
    n = len(c)
    max_t = n // 4 + 16
    t_side = np.zeros(max_t, np.int64); t_in = np.zeros(max_t, np.int64)
    t_out = np.zeros(max_t, np.int64); t_pnl = np.zeros(max_t, np.float64)
    t_r = np.zeros(max_t, np.float64); t_reason = np.zeros(max_t, np.int64)
    k = 0

    pos = 0
    entry = 0.0; stop = 0.0; target = 0.0; risk = 0.0; ent_i = -1
    armed = 0            # +1 armed long, -1 armed short
    pull_ext = 0.0       # extreme reached during the pullback
    prev_sess = -1
    n_sess = 0           # trades taken this session
    last_exit = -10_000  # bar index of the last exit, for the cooldown

    for i in range(1, n):
        new_sess = sess[i] != prev_sess
        if new_sess:
            prev_sess = sess[i]
            armed = 0
            n_sess = 0

        # ---------------- manage an open position ----------------
        if pos != 0:
            if new_sess or mso[i] >= tod_end:
                px = o[i]
                t_side[k] = pos; t_in[k] = ent_i; t_out[k] = i
                t_pnl[k] = pos * (px - entry) * point_value - cost
                t_r[k] = (pos * (px - entry)) / risk if risk > 0 else 0.0
                t_reason[k] = 3; k += 1
                pos = 0; armed = 0; last_exit = i
            else:
                hit_stop = (l[i] <= stop) if pos == 1 else (h[i] >= stop)
                hit_tgt = (h[i] >= target) if pos == 1 else (l[i] <= target)
                if hit_stop:
                    t_side[k] = pos; t_in[k] = ent_i; t_out[k] = i
                    t_pnl[k] = pos * (stop - entry) * point_value - cost
                    t_r[k] = -1.0; t_reason[k] = 1; k += 1
                    pos = 0; armed = 0; last_exit = i
                elif hit_tgt and target_mode != 2:
                    t_side[k] = pos; t_in[k] = ent_i; t_out[k] = i
                    t_pnl[k] = pos * (target - entry) * point_value - cost
                    t_r[k] = (pos * (target - entry)) / risk if risk > 0 else 0.0
                    t_reason[k] = 2; k += 1
                    pos = 0; armed = 0; last_exit = i

        if pos != 0:
            continue
        # Entry timing controls. Without these the structure re-arms within a bar or two of every
        # exit and takes ~19 trades a session, which at a $19 round turn spends $361/day on costs
        # before the rule has said anything. Both are part of the searched space.
        if max_per_sess > 0 and n_sess >= max_per_sess:
            continue
        if i - last_exit < cooldown:
            continue
        if mso[i] < tod_start or mso[i] >= tod_end:
            continue
        a = atr[i - 1]
        if not (a > 0) or np.isnan(ef[i - 1]) or np.isnan(es[i - 1]):
            continue
        r = atr_rank[i - 1]
        if np.isnan(r) or r < atr_lo or r > atr_hi:
            continue

        # ---------------- 1. trend ----------------
        up = 0
        if trend_mode == 0:
            up = 1 if ef[i - 1] > es[i - 1] else (-1 if ef[i - 1] < es[i - 1] else 0)
        elif trend_mode == 1:                       # EMA stack plus slow-EMA slope
            if ef[i - 1] > es[i - 1] and slope[i - 1] > 0:
                up = 1
            elif ef[i - 1] < es[i - 1] and slope[i - 1] < 0:
                up = -1
        else:                                       # EMA stack confirmed by session VWAP
            if ef[i - 1] > es[i - 1] and c[i - 1] > vwap[i - 1]:
                up = 1
            elif ef[i - 1] < es[i - 1] and c[i - 1] < vwap[i - 1]:
                up = -1
        if up == 0:
            armed = 0
            continue
        if armed != 0 and armed != up:
            armed = 0

        # ---------------- 2. pullback ----------------
        in_zone = False
        if pull_mode == 0:                          # into an ATR band around the fast EMA
            if up == 1:
                in_zone = l[i - 1] <= ef[i - 1] + pull_depth * a
            else:
                in_zone = h[i - 1] >= ef[i - 1] - pull_depth * a
        elif pull_mode == 1:                        # back inside a VWAP deviation band
            if not np.isnan(vwsd[i - 1]) and vwsd[i - 1] > 0:
                dev = (c[i - 1] - vwap[i - 1]) / vwsd[i - 1]
                in_zone = (dev <= pull_depth) if up == 1 else (dev >= -pull_depth)
        else:                                       # a give-back of pull_depth ATR from the extreme
            if up == 1:
                in_zone = (ef[i - 1] - l[i - 1]) >= -pull_depth * a
            else:
                in_zone = (h[i - 1] - ef[i - 1]) >= -pull_depth * a

        if in_zone:
            if armed != up:
                armed = up
                pull_ext = l[i - 1] if up == 1 else h[i - 1]
            else:
                if up == 1 and l[i - 1] < pull_ext:
                    pull_ext = l[i - 1]
                if up == -1 and h[i - 1] > pull_ext:
                    pull_ext = h[i - 1]

        if armed != up:
            continue

        # ---------------- 3. continuation trigger ----------------
        trig = False
        if entry_mode == 0:                         # close back through the fast EMA
            trig = (c[i - 1] > ef[i - 1]) if up == 1 else (c[i - 1] < ef[i - 1])
        elif entry_mode == 1:                       # take out the previous bar's extreme
            trig = (h[i - 1] > h[i - 2]) if up == 1 else (l[i - 1] < l[i - 2])
        else:                                       # a bar that closes in the top/bottom third
            rng = h[i - 1] - l[i - 1]
            if rng > 0:
                po = (c[i - 1] - l[i - 1]) / rng
                trig = (po > 0.66) if up == 1 else (po < 0.34)
        if not trig:
            continue
        if side_mode != 0 and side_mode != up:
            armed = 0
            continue

        # ---------------- size the trade ----------------
        e = o[i]
        if stop_mode == 0:
            s = e - up * stop_mult * a
        elif stop_mode == 1:
            s = pull_ext - up * 0.10 * a            # just beyond the pullback extreme
        else:
            s = e - up * stop_mult * 10.0           # fixed points
        rr = up * (e - s)
        if rr <= 0:
            armed = 0
            continue
        if target_mode == 0:
            tgt = e + up * target_r * rr
        elif target_mode == 1:
            tgt = e + up * target_r * a
        else:
            tgt = e + up * 1e6                      # ride to the session close

        pos = up; entry = e; stop = s; target = tgt; risk = rr; ent_i = i
        armed = 0; n_sess += 1

    if pos != 0:
        t_side[k] = pos; t_in[k] = ent_i; t_out[k] = n - 1
        t_pnl[k] = pos * (c[n - 1] - entry) * point_value - cost
        t_r[k] = (pos * (c[n - 1] - entry)) / risk if risk > 0 else 0.0
        t_reason[k] = 3; k += 1

    return t_side[:k], t_in[:k], t_out[:k], t_pnl[:k], t_r[:k], t_reason[:k]


def load(path="data/NQ_1m.csv"):
    seg = session_slice(load_bars(path), RTH_START, RTH_END)
    o = seg["open"].to_numpy(float); h = seg["high"].to_numpy(float)
    l = seg["low"].to_numpy(float);  c = seg["close"].to_numpy(float)
    v = seg["volume"].to_numpy(float)
    sess = session_index(seg.index, RTH_START)
    mso = minutes_since_open(minute_of_day(seg.index), RTH_START).astype(np.float64)
    n = len(c)

    emas = {L: ema(c, L) for L in EMA_LENS}
    atr = atr_series(h, l, c, ATR_LEN)
    atr_rank = pd.Series(atr).rolling(2000, min_periods=500).rank(pct=True).to_numpy()

    tp = (h + l + c) / 3
    vwap = np.empty(n); vwsd = np.empty(n)
    cum_pv = cum_v = cum_p2 = 0.0
    cur = -1
    for i in range(n):
        if sess[i] != cur:
            cur = sess[i]; cum_pv = cum_v = cum_p2 = 0.0
        cum_pv += tp[i] * v[i]; cum_v += v[i]; cum_p2 += tp[i] * tp[i] * v[i]
        if cum_v > 0:
            vwap[i] = cum_pv / cum_v
            var = cum_p2 / cum_v - vwap[i] ** 2
            vwsd[i] = np.sqrt(var) if var > 0 else np.nan
        else:
            vwap[i] = np.nan; vwsd[i] = np.nan

    return dict(seg=seg, o=o, h=h, l=l, c=c, v=v, sess=sess, mso=mso,
                emas=emas, atr=atr, atr_rank=atr_rank, vwap=vwap, vwsd=vwsd)


# ------------------------------------------------------------------------------------------------
# statistics
# ------------------------------------------------------------------------------------------------
def nw_t(x, lag=10):
    x = np.asarray(x, float)
    n = len(x)
    if n < 20:
        return np.nan
    e = x - x.mean()
    s = (e @ e) / n
    for k in range(1, lag + 1):
        s += 2 * (1 - k / (lag + 1)) * (e[k:] @ e[:-k]) / n
    return np.nan if s <= 0 else x.mean() / np.sqrt(s / n)


def stats(pnl, rmult, n_days):
    if len(pnl) == 0:
        return dict(n=0, net=0.0, exp=np.nan, pf=np.nan, win=np.nan, t=np.nan,
                    mdd=np.nan, sharpe=np.nan, er=np.nan)
    gp = pnl[pnl > 0].sum(); gl = -pnl[pnl < 0].sum()
    eq = np.cumsum(pnl)
    dd = (np.maximum.accumulate(eq) - eq).max()
    sh = (pnl.mean() / pnl.std() * np.sqrt(len(pnl) / max(n_days, 1) * 252)) if pnl.std() > 0 else 0.0
    return dict(n=len(pnl), net=pnl.sum(), exp=pnl.mean(), pf=(gp / gl if gl > 0 else np.inf),
                win=100 * (pnl > 0).mean(), t=nw_t(pnl), mdd=dd, sharpe=sh, er=np.mean(rmult))


HDR = (f"  {'':<40}{'n':>7}{'net $':>11}{'$/trade':>10}{'PF':>7}{'win':>7}"
       f"{'t':>7}{'E[R]':>7}{'maxDD':>10}")


def row(label, s):
    if s["n"] == 0:
        return f"  {label:<40}{'no trades':>7}"
    return (f"  {label:<40}{s['n']:>7,}{s['net']:>11,.0f}{s['exp']:>10.2f}{s['pf']:>7.3f}"
            f"{s['win']:>6.1f}%{s['t']:>7.2f}{s['er']:>7.3f}{s['mdd']:>10,.0f}")


def run(d, p, point_value=POINT_VALUE_NQ, cost=COST_NQ, side_mode=0):
    ef = d["emas"][p["ema_fast"]]
    es = d["emas"][p["ema_slow"]]
    slope = np.gradient(es)
    return simulate(d["o"], d["h"], d["l"], d["c"], d["sess"], d["mso"], ef, es, slope,
                    d["atr"], d["atr_rank"], d["vwap"], d["vwsd"],
                    p["trend_mode"], p["pull_mode"], p["pull_depth"], p["entry_mode"],
                    p["atr_lo"], p["atr_hi"], p["tod_start"], p["tod_end"],
                    p["stop_mode"], p["stop_mult"], p["target_mode"], p["target_r"],
                    point_value, cost, side_mode,
                    p.get("max_per_sess", 0), p.get("cooldown", 0))


def three_way(sess, research=0.5, validate=0.25):
    """Split on SESSION boundaries: research / validation / LOCKED holdout."""
    days = np.unique(sess)
    a = days[int(len(days) * research)]
    b = days[int(len(days) * (research + validate))]
    return sess < a, (sess >= a) & (sess < b), sess >= b


def label(p):
    return (f"ema{p['ema_fast']}/{p['ema_slow']} tm{p['trend_mode']} pm{p['pull_mode']}"
            f"@{p['pull_depth']:g} em{p['entry_mode']} sm{p['stop_mode']}x{p['stop_mult']:g}"
            f" tg{p['target_mode']}x{p['target_r']:g} vol[{p['atr_lo']:g},{p['atr_hi']:g}]"
            f" tod[{int(p['tod_start'])},{int(p['tod_end'])}]")


DEFAULT = dict(ema_fast=21, ema_slow=50, trend_mode=0, pull_mode=0, pull_depth=0.5,
               entry_mode=1, atr_lo=0.0, atr_hi=1.0, tod_start=15.0, tod_end=375.0,
               stop_mode=0, stop_mult=1.5, target_mode=0, target_r=2.0,
               max_per_sess=2, cooldown=15)


def spec(**kw):
    p = dict(DEFAULT)
    p.update(kw)
    return p


# The pre-specified set. Chosen from this repository's prior findings and from what the structure
# implies, BEFORE any search was run, so that a survivor here is worth more than a searched one.
PRESPEC = {
    "A textbook 21/50, 0.5xATR pullback, 1:2": spec(),
    "B slower trend 34/100, same geometry": spec(ema_fast=34, ema_slow=100),
    "C slope-confirmed trend": spec(trend_mode=1),
    "D VWAP-confirmed trend": spec(trend_mode=2),
    "E VWAP-band pullback (1 sigma)": spec(pull_mode=1, pull_depth=1.0),
    "F deeper pullback, wider stop": spec(pull_depth=1.0, stop_mult=2.0),
    "G swing stop instead of ATR": spec(stop_mode=1),
    "H morning only (first 2 hours)": spec(tod_start=15.0, tod_end=135.0),
    "I high-volatility regime only": spec(atr_lo=0.5, atr_hi=1.0),
    "J ride to the close, no target": spec(target_mode=2),
}


def stage_prespec(d) -> None:
    sess = d["sess"]
    r_m, v_m, h_m = three_way(sess)
    days = lambda m: len(np.unique(sess[m]))
    print("=" * 112)
    print("STAGE 1 — THE PRE-SPECIFIED SET (holdout stays closed)")
    print("=" * 112)
    print(f"\n  {len(d['c']):,} RTH 1-minute bars, {len(np.unique(sess))} sessions, "
          f"{d['seg'].index[0].date()} - {d['seg'].index[-1].date()}")
    print(f"  research {days(r_m)} sessions / validation {days(v_m)} / LOCKED holdout {days(h_m)}")
    print(f"  costs ${COST_NQ:.2f} per NQ round turn, charged before any selection\n")
    print(HDR)
    for name, p in PRESPEC.items():
        side, ti, to, pnl, rm, why = run(d, p)
        s_all = stats(pnl, rm, len(np.unique(sess)))
        rr = np.isin(ti, np.where(r_m)[0]); vv = np.isin(ti, np.where(v_m)[0])
        print(row(name, s_all))
        print(row("    research", stats(pnl[rr], rm[rr], days(r_m))))
        print(row("    validation", stats(pnl[vv], rm[vv], days(v_m))))
    print("\n  Nothing above has touched the holdout. Stage 3 opens it once.")


def grid():
    """The searched space. Deliberately enumerated in one place so its SIZE is visible."""
    from itertools import product
    axes = dict(
        max_per_sess=[1, 2, 3],
        cooldown=[5, 15, 30],
        ema_fast=[9, 21, 34],
        ema_slow=[50, 100, 200],
        trend_mode=[0, 1, 2],
        pull_mode=[0, 1, 2],
        pull_depth=[0.25, 0.5, 1.0, 1.5],
        entry_mode=[0, 1, 2],
        stop_mode=[0, 1],
        stop_mult=[1.0, 1.5, 2.0],
        target_mode=[0, 1, 2],
        target_r=[1.0, 1.5, 2.0, 3.0],
        vol=[(0.0, 1.0), (0.0, 0.5), (0.5, 1.0), (0.25, 0.75)],
        tod=[(15.0, 375.0), (15.0, 135.0), (15.0, 210.0), (90.0, 375.0)],
    )
    keys = list(axes)
    for combo in product(*[axes[k] for k in keys]):
        p = dict(DEFAULT)
        for k, val in zip(keys, combo):
            if k == "vol":
                p["atr_lo"], p["atr_hi"] = val
            elif k == "tod":
                p["tod_start"], p["tod_end"] = val
            else:
                p[k] = val
        if p["ema_fast"] >= p["ema_slow"]:
            continue
        # target_mode 2 rides to the close, so target_r is inert -- keep one copy only
        if p["target_mode"] == 2 and p["target_r"] != 1.0:
            continue
        # stop_mode 1 is the swing stop, so stop_mult is inert -- keep one copy only
        if p["stop_mode"] == 1 and p["stop_mult"] != 1.0:
            continue
        yield p


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="prespec")
    a = ap.parse_args()
    d = load()
    if a.stage == "prespec":
        stage_prespec(d)
