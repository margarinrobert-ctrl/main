"""BOS / CHoCH as a testable specification on NQ index futures.

THE HYPOTHESIS, stated so it can be falsified:

  LONG   two consecutive bullish breaks of structure (close above the last CONFIRMED swing high)
         while price is above the 200 EMA. Enter on the SECOND break, at the next bar's open.
         Stop 2 x ATR(14) below entry. Exit on a bearish CHoCH (close below the relevant confirmed
         swing low) or on the stop, whichever comes first.
  SHORT  the mirror.

NO LOOK-AHEAD, and the cost of that is measured rather than assumed. A fractal swing at bar t needs
k bars on each side to be a swing at all, so it is not KNOWABLE until t+k. Every pivot used here
carries that delay explicitly (`smc.swing_pivots`, 18 unit tests in `research/test_smc.py`), and the
delay in bars is reported in the baseline table. Entries fill at the open of the bar AFTER the
signal bar closes, so the bar that produced the signal is never traded on.

STOP FILLS ARE NOT ASSUMED. A stop is a market order once touched. If the bar opens through the
stop, the fill is the OPEN, not the stop price -- gap risk is charged, not ignored. A slippage
allowance is added on top of that, separately from the entry cost.

Usage: python3 research/bos_choch.py --stage baseline
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, "research")
import smc
from nqdata import load_bars, minute_of_day, session_index

# ---- contract specs -----------------------------------------------------------------------------
SPECS = {
    # point_value, tick, commission+fees per round turn, spread ticks, entry slip ticks, stop slip ticks
    "NQ":  dict(pv=20.0, tick=0.25, comm=4.00, spread_t=1.0, slip_t=1.0, stop_slip_t=1.0),
    "MNQ": dict(pv=2.0,  tick=0.25, comm=1.50, spread_t=1.0, slip_t=1.0, stop_slip_t=1.0),
    # ES/MES specs are correct, but there is no ES price data in this repository -- see the report.
    "ES":  dict(pv=50.0, tick=0.25, comm=4.00, spread_t=1.0, slip_t=1.0, stop_slip_t=1.0),
    "MES": dict(pv=5.0,  tick=0.25, comm=1.50, spread_t=1.0, slip_t=1.0, stop_slip_t=1.0),
}

# ---- sessions, in minutes since local midnight (ET) ----------------------------------------------
SESSIONS = {
    "globex_24h":   (0, 1440),
    "rth_0930_1600": (570, 960),
    "ny_morning":    (570, 720),
    "ny_afternoon":  (720, 960),
    "overnight":     (960, 570 + 1440),   # 16:00 -> 09:30 next day, wraps midnight
    "w_0930_1030":   (570, 630),
    "w_0930_1130":   (570, 690),
    "w_1000_1200":   (600, 720),
    "w_1330_1600":   (810, 960),
}


def in_session(mod: np.ndarray, lo: int, hi: int) -> np.ndarray:
    if hi <= 1440:
        return (mod >= lo) & (mod < hi)
    return (mod >= lo) | (mod < hi - 1440)          # wraps midnight


def resample(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Resample 1-minute bars, anchored to LOCAL midnight so a bucket lines up with 09:30."""
    if minutes == 1:
        return df
    out = df.resample(f"{minutes}min", origin="start_day", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return out.dropna()


def ema(x: np.ndarray, n: int) -> np.ndarray:
    e = pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy().copy()
    e[:n] = np.nan
    return e


def atr(h, l, c, n):
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    a = pd.Series(tr).ewm(span=n, adjust=False).mean().to_numpy().copy()
    a[:n] = np.nan
    return a


@njit(cache=True)
def simulate(o, h, l, c, sess, tradeable, ph, pl, phi, pli, ema_, atr_,
             atr_mult, n_bos, use_ema, use_stop, use_choch, max_hold,
             pv, tick, comm, spread_t, slip_t, stop_slip_t, side_mode):
    """One position at a time. Signals read bar i; fills happen at the open of bar i+1.

    `n_bos` is how many same-direction breaks are required before entering (the baseline is 2 --
    "do not enter on the first BOS"). `tradeable` gates ENTRIES by session; an open position is
    still managed outside it, because a stop does not stop existing at 16:01.
    """
    n = len(c)
    max_t = n // 2 + 8
    t_side = np.zeros(max_t, np.int64); t_in = np.zeros(max_t, np.int64)
    t_out = np.zeros(max_t, np.int64); t_pnl = np.zeros(max_t, np.float64)
    t_gross = np.zeros(max_t, np.float64); t_r = np.zeros(max_t, np.float64)
    t_reason = np.zeros(max_t, np.int64); t_delay = np.zeros(max_t, np.int64)
    k = 0

    entry_cost_pts = (spread_t + slip_t) * tick        # charged once on entry
    exit_cost_pts = (spread_t + slip_t) * tick         # charged once on a normal exit
    stop_extra_pts = stop_slip_t * tick                # additional, stops only

    pos = 0
    entry = 0.0; stop = 0.0; risk = 0.0; ent_i = -1; ent_delay = 0
    bias = 0            # +1 after a bullish BOS, -1 after a bearish
    run = 0             # how many same-direction BOS since the structure flipped
    last_hi = np.nan    # the confirmed swing levels the breaks are measured against
    last_lo = np.nan
    exit_lo = np.nan    # the swing low whose break is the bearish CHoCH for an open long
    exit_hi = np.nan

    for i in range(1, n):
        new_sess = sess[i] != sess[i - 1]

        # ---------------- manage an open position (uses bar i's own range) ----------------
        if pos != 0:
            hit = False
            px = 0.0
            if use_stop == 1:
                if pos == 1 and l[i] <= stop:
                    # a stop is a market order once touched: if the bar OPENED through it, the fill
                    # is the open, not the stop.
                    px = o[i] if o[i] < stop else stop
                    px -= stop_extra_pts
                    hit = True
                elif pos == -1 and h[i] >= stop:
                    px = o[i] if o[i] > stop else stop
                    px += stop_extra_pts
                    hit = True
            if hit:
                g = pos * (px - entry)
                t_side[k] = pos; t_in[k] = ent_i; t_out[k] = i; t_delay[k] = ent_delay
                t_gross[k] = g * pv
                t_pnl[k] = g * pv - comm - (entry_cost_pts + exit_cost_pts) * pv
                t_r[k] = g / risk if risk > 0 else 0.0
                t_reason[k] = 1; k += 1
                pos = 0
            elif max_hold > 0 and (i - ent_i) >= max_hold:
                g = pos * (o[i] - entry)
                t_side[k] = pos; t_in[k] = ent_i; t_out[k] = i; t_delay[k] = ent_delay
                t_gross[k] = g * pv
                t_pnl[k] = g * pv - comm - (entry_cost_pts + exit_cost_pts) * pv
                t_r[k] = g / risk if risk > 0 else 0.0
                t_reason[k] = 3; k += 1
                pos = 0

        # ---------------- structure update on bar i's CLOSE ----------------
        hi_lvl = ph[i]
        lo_lvl = pl[i]
        bos_up = 0
        bos_dn = 0
        if not np.isnan(hi_lvl) and c[i] > hi_lvl and hi_lvl != last_hi:
            bos_up = 1
            last_hi = hi_lvl
        if not np.isnan(lo_lvl) and c[i] < lo_lvl and lo_lvl != last_lo:
            bos_dn = 1
            last_lo = lo_lvl

        if bos_up == 1:
            if bias == 1:
                run += 1
            else:
                bias = 1
                run = 1
        if bos_dn == 1:
            if bias == -1:
                run += 1
            else:
                bias = -1
                run = 1

        # ---------------- CHoCH exit for an open position ----------------
        if pos == 1 and use_choch == 1 and bos_dn == 1:
            if i + 1 < n:
                g = (o[i + 1] - entry)
                t_side[k] = 1; t_in[k] = ent_i; t_out[k] = i + 1; t_delay[k] = ent_delay
                t_gross[k] = g * pv
                t_pnl[k] = g * pv - comm - (entry_cost_pts + exit_cost_pts) * pv
                t_r[k] = g / risk if risk > 0 else 0.0
                t_reason[k] = 2; k += 1
                pos = 0
        elif pos == -1 and use_choch == 1 and bos_up == 1:
            if i + 1 < n:
                g = (entry - o[i + 1])
                t_side[k] = -1; t_in[k] = ent_i; t_out[k] = i + 1; t_delay[k] = ent_delay
                t_gross[k] = g * pv
                t_pnl[k] = g * pv - comm - (entry_cost_pts + exit_cost_pts) * pv
                t_r[k] = g / risk if risk > 0 else 0.0
                t_reason[k] = 2; k += 1
                pos = 0

        # ---------------- entry on the n-th BOS, filled at the NEXT open ----------------
        if pos == 0 and i + 1 < n and tradeable[i] == 1 and not new_sess:
            a = atr_[i]
            if a > 0 and not np.isnan(a):
                want = 0
                if bos_up == 1 and run >= n_bos:
                    if use_ema == 0 or (not np.isnan(ema_[i]) and c[i] > ema_[i]):
                        want = 1
                elif bos_dn == 1 and run >= n_bos:
                    if use_ema == 0 or (not np.isnan(ema_[i]) and c[i] < ema_[i]):
                        want = -1
                if want != 0 and (side_mode == 0 or side_mode == want):
                    e = o[i + 1] + want * entry_cost_pts * 0.0   # cost booked in dollars, not price
                    entry = o[i + 1]
                    stop = entry - want * atr_mult * a
                    risk = atr_mult * a
                    pos = want
                    ent_i = i + 1
                    ent_delay = 0
                    # how many bars ago was the pivot that authorised this break?
                    if want == 1 and phi[i] >= 0:
                        ent_delay = i - phi[i]
                    elif want == -1 and pli[i] >= 0:
                        ent_delay = i - pli[i]

    if pos != 0:
        g = pos * (c[n - 1] - entry)
        t_side[k] = pos; t_in[k] = ent_i; t_out[k] = n - 1; t_delay[k] = ent_delay
        t_gross[k] = g * pv
        t_pnl[k] = g * pv - comm - (entry_cost_pts + exit_cost_pts) * pv
        t_r[k] = g / risk if risk > 0 else 0.0
        t_reason[k] = 3; k += 1

    return (t_side[:k], t_in[:k], t_out[:k], t_pnl[:k], t_gross[:k], t_r[:k],
            t_reason[:k], t_delay[:k])


# ------------------------------------------------------------------------------------------------
# data + statistics
# ------------------------------------------------------------------------------------------------
_CACHE: dict = {}


def prep(minutes: int, swing_k: int = 3, ema_n: int = 200, atr_n: int = 14):
    key = (minutes, swing_k, ema_n, atr_n)
    if key in _CACHE:
        return _CACHE[key]
    raw = _CACHE.get("raw")
    if raw is None:
        raw = load_bars("data/NQ_1m.csv")
        _CACHE["raw"] = raw
    df = resample(raw, minutes)
    o = df["open"].to_numpy(float); h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float);  c = df["close"].to_numpy(float)
    v = df["volume"].to_numpy(float)
    mod = minute_of_day(df.index)
    sess = session_index(df.index, 570)
    ph, pl, phi, pli = smc.swing_pivots(h, l, swing_k)
    d = dict(df=df, o=o, h=h, l=l, c=c, v=v, mod=mod, sess=sess,
             ph=ph, pl=pl, phi=phi, pli=pli, ema=ema(c, ema_n), atr=atr(h, l, c, atr_n))
    _CACHE[key] = d
    return d


def run(minutes=5, session="rth_0930_1600", swing_k=3, ema_n=200, atr_n=14, atr_mult=2.0,
        n_bos=2, use_ema=1, use_stop=1, use_choch=1, max_hold=0, symbol="NQ", side_mode=0,
        cost_mult=1.0):
    d = prep(minutes, swing_k, ema_n, atr_n)
    lo, hi = SESSIONS[session]
    tradeable = in_session(d["mod"], lo, hi).astype(np.uint8)
    s = SPECS[symbol]
    return simulate(d["o"], d["h"], d["l"], d["c"], d["sess"], tradeable,
                    d["ph"], d["pl"], d["phi"], d["pli"], d["ema"], d["atr"],
                    atr_mult, n_bos, use_ema, use_stop, use_choch, max_hold,
                    s["pv"], s["tick"], s["comm"] * cost_mult,
                    s["spread_t"] * cost_mult, s["slip_t"] * cost_mult,
                    s["stop_slip_t"] * cost_mult, side_mode)


def nw_t(x, lag=10):
    x = np.asarray(x, float)
    n = len(x)
    if n < 20:
        return np.nan
    e = x - x.mean()
    s = (e @ e) / n
    for j in range(1, lag + 1):
        s += 2 * (1 - j / (lag + 1)) * (e[j:] @ e[:-j]) / n
    return np.nan if s <= 0 else x.mean() / np.sqrt(s / n)


def stats(pnl, r, ti, to, index, capital=100_000.0, bars_per_day=None):
    n = len(pnl)
    if n == 0:
        return dict(n=0)
    wins = pnl[pnl > 0]; losses = pnl[pnl < 0]
    eq = capital + np.cumsum(pnl)
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / peak
    days = (index[-1] - index[0]).days or 1
    yrs = days / 365.25
    total = pnl.sum()
    cagr = ((eq[-1] / capital) ** (1 / yrs) - 1) if eq[-1] > 0 and yrs > 0 else np.nan
    sd = pnl.std(ddof=1) if n > 1 else 0.0
    tpd = n / max(days * 252 / 365.25, 1)
    sharpe = (pnl.mean() / sd * np.sqrt(252 * tpd)) if sd > 0 else np.nan
    downs = pnl[pnl < 0]
    sortino = (pnl.mean() / downs.std(ddof=1) * np.sqrt(252 * tpd)) if len(downs) > 1 and downs.std(ddof=1) > 0 else np.nan
    mdd = dd.max()
    # consecutive runs
    sgn = np.sign(pnl)
    mx_w = mx_l = cur_w = cur_l = 0
    for s_ in sgn:
        if s_ > 0:
            cur_w += 1; cur_l = 0
        elif s_ < 0:
            cur_l += 1; cur_w = 0
        mx_w = max(mx_w, cur_w); mx_l = max(mx_l, cur_l)
    held = (to - ti).astype(float)
    return dict(
        n=n, total=total, cagr=cagr, sharpe=sharpe, sortino=sortino,
        calmar=(cagr / mdd if mdd > 0 and np.isfinite(cagr) else np.nan),
        maxdd=mdd, maxdd_dollars=(peak - eq).max(),
        pf=(wins.sum() / -losses.sum() if len(losses) and losses.sum() < 0 else np.inf),
        exp=pnl.mean(), win=100 * (pnl > 0).mean(),
        avg_win=(wins.mean() if len(wins) else np.nan),
        avg_loss=(losses.mean() if len(losses) else np.nan),
        payoff=(wins.mean() / -losses.mean() if len(losses) and losses.mean() < 0 else np.nan),
        tpd=tpd, t=nw_t(pnl), er=np.mean(r),
        mx_win=mx_w, mx_loss=mx_l, ret_dd=(total / (peak - eq).max() if (peak - eq).max() > 0 else np.nan),
        avg_bars=held.mean(), yrs=yrs)


HDR = (f"  {'':<30}{'n':>7}{'net $':>11}{'$/trd':>8}{'PF':>7}{'win%':>7}{'Shrp':>7}"
       f"{'Sort':>7}{'Clmr':>7}{'maxDD%':>8}{'t':>7}{'E[R]':>7}")


def row(label, s):
    if s.get("n", 0) == 0:
        return f"  {label:<30}{'no trades':>7}"
    f = lambda v, d=2: ("nan" if not np.isfinite(v) else f"{v:.{d}f}")
    return (f"  {label:<30}{s['n']:>7,}{s['total']:>11,.0f}{s['exp']:>8.1f}{f(s['pf']):>7}"
            f"{s['win']:>7.1f}{f(s['sharpe']):>7}{f(s['sortino']):>7}{f(s['calmar']):>7}"
            f"{100*s['maxdd']:>8.1f}{f(s['t']):>7}{s['er']:>7.3f}")


@njit(cache=True)
def sim_given_entries(o, h, l, c, sess, ent_side, ph, pl, atr_, atr_mult, use_stop, use_choch,
                      pv, tick, comm, spread_t, slip_t, stop_slip_t):
    """Identical management, but entries are handed in. This is the random-entry control.

    If BOS carries information, replacing the entry signal with a coin flip -- same count, same
    stop, same CHoCH exit, same costs -- must make things worse. If it does not, the signal is
    decoration on a risk-management scheme.
    """
    n = len(c)
    max_t = n // 2 + 8
    t_pnl = np.zeros(max_t, np.float64); t_r = np.zeros(max_t, np.float64)
    t_in = np.zeros(max_t, np.int64); t_out = np.zeros(max_t, np.int64)
    t_side = np.zeros(max_t, np.int64)
    k = 0
    ec = (spread_t + slip_t) * tick
    se = stop_slip_t * tick
    pos = 0; entry = 0.0; stop = 0.0; risk = 0.0; ent_i = -1
    last_hi = np.nan; last_lo = np.nan
    for i in range(1, n):
        if pos != 0:
            hit = False; px = 0.0
            if use_stop == 1:
                if pos == 1 and l[i] <= stop:
                    px = o[i] if o[i] < stop else stop; px -= se; hit = True
                elif pos == -1 and h[i] >= stop:
                    px = o[i] if o[i] > stop else stop; px += se; hit = True
            if hit:
                g = pos * (px - entry)
                t_side[k] = pos; t_in[k] = ent_i; t_out[k] = i
                t_pnl[k] = g * pv - comm - 2 * ec * pv
                t_r[k] = g / risk if risk > 0 else 0.0
                k += 1; pos = 0
        bos_up = 0; bos_dn = 0
        if not np.isnan(ph[i]) and c[i] > ph[i] and ph[i] != last_hi:
            bos_up = 1; last_hi = ph[i]
        if not np.isnan(pl[i]) and c[i] < pl[i] and pl[i] != last_lo:
            bos_dn = 1; last_lo = pl[i]
        if pos != 0 and use_choch == 1 and i + 1 < n:
            if (pos == 1 and bos_dn == 1) or (pos == -1 and bos_up == 1):
                g = pos * (o[i + 1] - entry)
                t_side[k] = pos; t_in[k] = ent_i; t_out[k] = i + 1
                t_pnl[k] = g * pv - comm - 2 * ec * pv
                t_r[k] = g / risk if risk > 0 else 0.0
                k += 1; pos = 0
        if pos == 0 and i + 1 < n and ent_side[i] != 0:
            a = atr_[i]
            if a > 0 and not np.isnan(a):
                pos = ent_side[i]; entry = o[i + 1]
                stop = entry - pos * atr_mult * a; risk = atr_mult * a; ent_i = i + 1
    return t_side[:k], t_in[:k], t_out[:k], t_pnl[:k], t_r[:k]


def random_control(minutes, session, n_entries, long_share, reps=200, seed=20250822, **kw):
    """Random entries with identical mechanics. Returns the distribution of net P&L."""
    d = prep(minutes, kw.get("swing_k", 3), kw.get("ema_n", 200), kw.get("atr_n", 14))
    lo, hi = SESSIONS[session]
    ok = in_session(d["mod"], lo, hi)
    idx = np.where(ok)[0]
    idx = idx[(idx > 250) & (idx < len(d["c"]) - 2)]
    s = SPECS[kw.get("symbol", "NQ")]
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(reps):
        ent = np.zeros(len(d["c"]), np.int64)
        pick = rng.choice(idx, size=min(n_entries, len(idx)), replace=False)
        ent[pick] = np.where(rng.random(len(pick)) < long_share, 1, -1)
        _, _, _, pnl, r = sim_given_entries(
            d["o"], d["h"], d["l"], d["c"], d["sess"], ent, d["ph"], d["pl"], d["atr"],
            kw.get("atr_mult", 2.0), 1, 1, s["pv"], s["tick"], s["comm"],
            s["spread_t"], s["slip_t"], s["stop_slip_t"])
        out.append((pnl.sum(), pnl.mean() if len(pnl) else np.nan, len(pnl)))
    return np.array(out)
