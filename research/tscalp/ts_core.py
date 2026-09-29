"""The submitted 'Turtle Scalp 07:00-11:00 NY' Pine, transliterated with ITS order model, plus the
three EMA gates the user asked to add, each as a per-bar entry mask so the kernel gains one
condition and nothing else.

THE SCRIPT'S ORDER MODEL, as read from its source (every line of this is a decision the study
`docs/ib/STUDY_TURTLE_SCALP.md` -- not on this branch -- would have had to make too):
  * signals at bar close: sig2 = high > highest(high, entry2)[1]; sig1 likewise; S2 takes priority;
    S1 is skipped ONCE after a winning trade (skipWin). Entry fills at the NEXT open.
  * `armedStp` (default ON): the first unit is bracketed on the SIGNAL bar at close - mult*ATR, so
    the fill bar is protected by a stop anchored to the signal close. The take-profit does not
    exist yet on the fill bar (it needs the fill price). At the fill bar's CLOSE the script
    re-anchors: stop = fill - mult*ATR(signal), tp = fill + tpR*risk, nextAdd = fill + step*ATR.
  * pyramid: while units < max and high >= nextAdd (and not in the flatten window), add a unit at
    the next open, bracketed at the level every other unit already carries; the re-anchor to the
    add's fill happens at that bar's close (Pine cannot see a fill until the bar closes).
  * exit each bar: stop = max(ATR stop, channel low) if chanExit else ATR stop, limit = tp. The
    orders are placed at bar close and live during the NEXT bar. When a bar holds both, the stop
    is booked (the script's own comment says so, and matches the research engine's pessimism).
  * flatten: `close_all` on the first bar inside 1100-1105 NY, which fills at the NEXT open.
  * winner: close on the exit bar > first fill.
  * THE SCRIPT SETS NO COMMISSION AND NO SLIPPAGE. Its own Strategy Tester report is at zero cost.
    Here every fill pays this branch's standard for the feed.

THE THREE GATES (all read at the SIGNAL bar, all causal):
  ema150   long only while close > EMA150 ('trend support').  Also a 'support' reading -- above
           AND within `near_atr` ATR of it -- because V51 measured that reading separately and it
           failed; both are offered so the difference is visible.
  cross    EMA20 > EMA50 with EMA50 > EMA200 (state), or a FRESH 20/50 cross within `x_win` bars
           with EMA20 > EMA200 (recency). V41 found the state form holds on 82.6% of breakout bars.
  pullback the low touched EMA20 within the last `pb_win` bars -- 'wait for the pullback to the
           20, then the Donchian gives the entry there or after'.
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd
from numba import njit
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v63", "research/turtle"):
    q = os.path.join(ROOT, p)
    if q not in sys.path: sys.path.insert(0, q)
import v63feeds as FD
from core import _rolling_max, _rolling_min, _atr_wilder

# per side, points: slip moves the fill, fee is cash. Same standard as research/absorb.
SPLIT = {"NQ": dict(slip=0.50, fee=0.36, pv=2.0, tick=0.25),
         "US100": dict(slip=0.45, fee=0.30, pv=1.0, tick=0.1),
         "US30": dict(slip=0.90, fee=0.60, pv=1.0, tick=0.1)}

# the pasted script's DEFAULT preset, "US30 15m 0700-1100 [locked +0.22]"
PRESET = dict(entry1=20, entry2=60, exit1=12, exit2=12, atr_len=20, atr_mult=2.5, pyr_step=0.5,
              max_units=4, tp_r=2.0, max_hold=0, skip_win=True, chan_exit=False, armed=True,
              one_shot=False, chan_lag=1, win0=7 * 60, win1=11 * 60, flat0=11 * 60, flat1=11 * 60 + 5)


def _ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def build(market="US30", tf=15):
    f = FD.bars(market, tf); ix = pd.DatetimeIndex(f.index)
    o, h, l, c, v = (f[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    n = len(c); mod = (ix.hour * 60 + ix.minute).to_numpy()
    sess = (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy()
    bl = FD.blocks(market, ix)
    sp = SPLIT[market]
    return dict(market=market, tf=tf, ts=ix.to_numpy(), o=o, h=h, l=l, c=c, v=v, n=n, mod=mod, sess=sess,
                ema20=_ema(c, 20), ema50=_ema(c, 50), ema150=_ema(c, 150), ema200=_ema(c, 200),
                blocks=bl, **sp)


def gate(D, ema150="off", near_atr=3.0, cross="off", x_win=5, pullback="off", pb_win=5, atr=None):
    """Entry eligibility from the three EMA conditions. Everything is read at the signal bar."""
    n = D["n"]; c, l = D["c"], D["l"]
    e20, e50, e150, e200 = D["ema20"], D["ema50"], D["ema150"], D["ema200"]
    g = np.ones(n, bool)
    if atr is None:
        atr = _atr_wilder(D["h"], D["l"], D["c"], PRESET["atr_len"])
    if ema150 == "above":
        g &= c > e150
    elif ema150 == "support":
        g &= (c > e150) & ((c - e150) <= near_atr * atr)
    if cross == "state":
        g &= (e20 > e50) & (e50 > e200)
    elif cross == "fresh":
        up = e20 > e50
        x = up & ~np.roll(up, 1); x[0] = False
        rec = pd.Series(x).rolling(x_win, min_periods=1).max().to_numpy().astype(bool)
        g &= rec & (e20 > e200)
    if pullback == "touch":
        t = l <= e20
        rec = pd.Series(t).rolling(pb_win, min_periods=1).max().to_numpy().astype(bool)
        g &= rec
    g[:250] = False
    return g


@njit(cache=True)
def walk(o, h, l, c, hi1, hi2, lo1, lo2, atr, mod, ok, start,
         atr_mult, pyr_step, max_units, tp_r, max_hold, skip_win, chan_exit, armed, one_shot,
         chan_lag, win0, win1, flat0, flat1, slip, fee, path):
    n = len(c); cap = n // 2 + 16
    t_pnl = np.zeros(cap); t_risk = np.zeros(cap); t_units = np.zeros(cap, np.int64)
    t_sys = np.zeros(cap, np.int64); t_why = np.zeros(cap, np.int64)
    t_in = np.zeros(cap, np.int64); t_out = np.zeros(cap, np.int64); t_sig = np.zeros(cap, np.int64)
    k = 0
    in_trade = False; units = 0; system = 0
    fills = np.zeros(8); first_fill = 0.0; risk0 = 0.0
    stop_live = 0.0      # the stop level live during the CURRENT bar (placed at the previous close)
    tp_live = np.nan     # the take-profit live during the current bar
    stop_anch = 0.0      # the re-anchored ATR stop as of the last close
    next_add = 0.0; pend_atr = 0.0
    entry_bar = 0; sig_bar = 0; last_win = False
    sess_key = -1; traded_sess = -1
    pending_entry = 0; pending_add = 0; pending_flat = False
    for i in range(start, n):
        exited = False
        day = i  # placeholder; session identity keyed below
        # ---- fills at THIS bar's open from orders placed at the previous close ----
        if pending_flat and in_trade:
            px = o[i] - slip
            pnl = 0.0
            for u in range(units):
                pnl += (px - fills[u]) - 2.0 * fee
            if k < cap:
                t_pnl[k] = pnl; t_risk[k] = risk0; t_units[k] = units; t_sys[k] = system
                t_why[k] = 3; t_in[k] = entry_bar; t_out[k] = i; t_sig[k] = sig_bar; k += 1
            last_win = c[i] > first_fill
            in_trade = False; units = 0; system = 0; exited = True
            pending_flat = False; pending_add = 0
        if pending_entry != 0:
            fp = o[i] + slip
            fills[0] = fp; first_fill = fp; units = 1; in_trade = True; system = pending_entry
            entry_bar = i
            risk0 = atr_mult * pend_atr
            # on the fill bar only the ARMED stop exists (anchored to the signal close); no TP yet
            stop_live = stop_anch if armed else -1e18
            tp_live = np.nan
            pending_entry = 0
        elif pending_add != 0 and in_trade:
            fp = o[i] + slip
            fills[units] = fp; units += 1
            pending_add = 0
            # bracket for the add = the level every other unit already carries (stop_live, tp_live)
        if in_trade and not exited:
            # ---- the bar: stop and tp live from the previous close ----
            hit_stop = stop_live > -1e17 and l[i] <= stop_live
            hit_tp = (not np.isnan(tp_live)) and h[i] >= tp_live
            why = 0; px = 0.0
            if hit_stop and hit_tp:
                if path == 1:
                    lo_first = (o[i] - l[i]) <= (h[i] - o[i])
                    if lo_first:
                        why = 1; px = (o[i] if o[i] < stop_live else stop_live) - slip
                    else:
                        why = 2; px = tp_live
                else:
                    why = 1; px = (o[i] if o[i] < stop_live else stop_live) - slip
            elif hit_stop:
                why = 1; px = (o[i] if o[i] < stop_live else stop_live) - slip
            elif hit_tp:
                why = 2; px = (o[i] if o[i] > tp_live else tp_live)
            if why != 0:
                pnl = 0.0
                for u in range(units):
                    pnl += (px - fills[u]) - 2.0 * fee
                if k < cap:
                    t_pnl[k] = pnl; t_risk[k] = risk0; t_units[k] = units; t_sys[k] = system
                    t_why[k] = why; t_in[k] = entry_bar; t_out[k] = i; t_sig[k] = sig_bar; k += 1
                last_win = c[i] > first_fill
                in_trade = False; units = 0; system = 0; exited = True
                pending_add = 0
        # ---- this bar's CLOSE: the script runs ----
        in_entry = mod[i] >= win0 and mod[i] < win1
        in_flat = mod[i] >= flat0 and mod[i] < flat1
        if in_trade and not exited:
            # re-anchor to the most recent fill (first unit on its fill bar, adds on theirs)
            if i == entry_bar or (units > 1 and fills[units - 1] > 0 and i == entry_bar + 0 and False):
                stop_anch = fills[0] - atr_mult * pend_atr
                next_add = fills[0] + pyr_step * pend_atr
                tp_live = fills[0] + tp_r * risk0 if tp_r > 0 else np.nan
            # exit orders for the NEXT bar
            held_too_long = max_hold > 0 and (i - entry_bar) >= max_hold
            if in_flat or held_too_long:
                pending_flat = True
            else:
                chan = lo1[i - chan_lag] if system == 1 else lo2[i - chan_lag]
                lvl = stop_anch
                if chan_exit and chan > lvl:
                    lvl = chan
                stop_live = lvl
                # pyramid add?
                if units < max_units and pyr_step > 0.0 and h[i] >= next_add and i + 1 < n:
                    pending_add = 1
                    pend_atr_add = atr[i]
                    # the re-anchor happens when the add fills, at that bar's close: model it now
                    # for the level that will apply from the bar AFTER the add's fill bar
                    # (the add's own fill bar carries stop_live as set above)
                    stop_anch = o[i + 1] + slip - atr_mult * pend_atr_add
                    next_add = o[i + 1] + slip + pyr_step * pend_atr_add
        elif not in_trade:
            if (not exited) and ok[i] and in_entry and i + 1 < n and atr[i] > 0:
                sig2 = h[i] > hi2[i - 1]
                sig1 = h[i] > hi1[i - 1]
                if sig2:
                    pending_entry = 2; pend_atr = atr[i]; sig_bar = i
                    stop_anch = c[i] - atr_mult * atr[i]
                elif sig1:
                    if skip_win and last_win:
                        last_win = False
                    else:
                        pending_entry = 1; pend_atr = atr[i]; sig_bar = i
                        stop_anch = c[i] - atr_mult * atr[i]
    return (t_pnl[:k], t_risk[:k], t_units[:k], t_sys[:k], t_why[:k], t_in[:k], t_out[:k], t_sig[:k])


def run(D, ok=None, cfg=PRESET, cost_mult=1.0, path=0, fee=None, slip=None):
    p = dict(PRESET, **cfg)
    hi1 = _rolling_max(D["h"], p["entry1"]); hi2 = _rolling_max(D["h"], p["entry2"])
    lo1 = _rolling_min(D["l"], p["exit1"]); lo2 = _rolling_min(D["l"], p["exit2"])
    atr = _atr_wilder(D["h"], D["l"], D["c"], p["atr_len"])
    ok = np.ones(D["n"], bool) if ok is None else np.ascontiguousarray(np.asarray(ok, bool))
    start = max(p["entry1"], p["entry2"], p["exit1"], p["exit2"], p["atr_len"], 250) + 1
    fee = D["fee"] * cost_mult if fee is None else fee
    slip = D["slip"] * cost_mult if slip is None else slip
    r = walk(D["o"], D["h"], D["l"], D["c"], hi1, hi2, lo1, lo2, atr, D["mod"], ok, start,
             float(p["atr_mult"]), float(p["pyr_step"]), int(p["max_units"]), float(p["tp_r"]),
             int(p["max_hold"]), bool(p["skip_win"]), bool(p["chan_exit"]), bool(p["armed"]),
             bool(p["one_shot"]), int(p["chan_lag"]), int(p["win0"]), int(p["win1"]),
             int(p["flat0"]), int(p["flat1"]), float(slip), float(fee), int(path))
    pnl, risk, units, sysm, why, bi, bo, sb = r
    if len(pnl) == 0:
        return pd.DataFrame()
    t = pd.DataFrame(dict(pnl=pnl, risk=risk, units=units, system=sysm, why=why, entry_bar=bi,
                          exit_bar=bo, sig_bar=sb))
    t["R"] = np.where(risk > 0, pnl / np.maximum(risk, 1e-9), 0.0)
    t["pct"] = 100.0 * pnl / D["o"][bi]
    t["usd"] = pnl * D["pv"]
    t["ts"] = D["ts"][bi]; t["sess"] = D["sess"][bi]
    t["exit"] = t["why"].map({1: "stop", 2: "target", 3: "flat"})
    for bn, bm in D["blocks"].items():
        t.loc[bm[bi], "block"] = bn
    return t


def stats(t):
    if len(t) == 0:
        return dict(n=0, R=np.nan, pf=np.nan, win=np.nan, usd=np.nan, dd=np.nan, sharpe=np.nan, pts=np.nan)
    R = t["R"].to_numpy(); P = t["pnl"].to_numpy()
    w, lo = P[P > 0].sum(), -P[P <= 0].sum()
    eq = np.cumsum(P)
    d = pd.Series(P, index=pd.DatetimeIndex(t["ts"]).normalize()).groupby(level=0).sum()
    sh = np.sqrt(252) * d.mean() / d.std(ddof=1) if len(d) > 2 and d.std(ddof=1) > 0 else np.nan
    return dict(n=len(R), R=float(R.mean()), pf=float(w / lo) if lo > 0 else np.inf,
                win=100.0 * float((P > 0).mean()), usd=float(P.sum() * 1.0),
                dd=float(np.max(np.maximum.accumulate(eq) - eq)), sharpe=float(sh), pts=float(P.mean()))
