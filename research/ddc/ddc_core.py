"""Double Donchian Channel Breakout (omererkan, Pine v5) on US30, US100 and NQ hourly bars.

THE RULES AS PUBLISHED. Slow channel 50, fast channel 30, both lagged one bar. Long when close
crosses over the slow upper band and the slow channel's width exceeds 3% of its lower band;
short mirrored on the slow lower band. Exit everything when close crosses the fast band on
the other side. A limit take-profit at +/-2% for 50% of the position. 100% of equity per
entry, 0.05% commission per side, no stop loss, no slippage. Chosen for BTC; nothing here
was fitted to an index, so every block below is out of sample for the parameters.

THE ORDER MODEL, AS THE STRATEGY TESTER RUNS IT (calc_on_every_tick off, orders at next bar):
  - a signal at bar t's close fills at bar t+1's OPEN; a `close_all` likewise;
  - `strategy.entry` on the opposite side REVERSES the position at the open;
  - `strategy.exit(limit=...)` is placed at the close of the first bar the position exists on,
    so it is live from the SECOND bar after the fill, and fills at the limit intrabar or at the
    open if the bar opens through it;
  - `strategy.exit("TP1", qty_percent=50)` IS RE-ISSUED ON EVERY BAR the position exists. Once
    it has filled, the next bar's call creates a fresh order for 50% of what REMAINS at a limit
    the market is already beyond, which fills at that bar's open -- so the position is halved
    again on every bar the price stays past the TP level, until the channel exit. `mode="literal"`
    reproduces that; `mode="intended"` fires the partial once per position, which is what the
    author evidently meant. Both are reported, because the report a user gets from TradingView is
    the literal one.

Everything fills on the bars that decide the exits, so a TP and a channel exit inside one bar
are resolved in favour of the TP if the bar touches it (the emulator's own convention) -- a
1-minute walk is not attempted, and none of the results here rest on that ordering.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from ibs import ibs_core as IC  # noqa: E402  (feed loaders on a New York clock)

MARKETS = ("US30", "US100", "NQ")


def bars(market, tf="60min"):
    f, _ = IC.load(market)
    r = f.resample(tf, label="left", closed="left").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
    return r.dropna()


def signals(b, slow=50, fast=30, vol=3.0):
    h, l, c = b["high"], b["low"], b["close"]
    ub_s = h.rolling(slow).max().shift(1)
    lb_s = l.rolling(slow).min().shift(1)
    ub_f = h.rolling(fast).max().shift(1)
    lb_f = l.rolling(fast).min().shift(1)
    fark = (ub_s - lb_s) / lb_s * 100.0
    x_up = (c > ub_s) & (c.shift(1) <= ub_s.shift(1))
    x_dn = (c < lb_s) & (c.shift(1) >= lb_s.shift(1))
    long_sig = (x_up & (fark > vol)).fillna(False).to_numpy()
    short_sig = (x_dn & (fark > vol)).fillna(False).to_numpy()
    exit_long = ((c < lb_f) & (c.shift(1) >= lb_f.shift(1))).fillna(False).to_numpy()
    exit_short = ((c > ub_f) & (c.shift(1) <= ub_f.shift(1))).fillna(False).to_numpy()
    return dict(long=long_sig, short=short_sig, exit_long=exit_long, exit_short=exit_short,
                fark=fark.to_numpy(), raw_up=x_up.fillna(False).to_numpy(),
                raw_dn=x_dn.fillna(False).to_numpy())


@njit(cache=True)
def _sign(x):
    return 1.0 if x > 0 else (-1.0 if x < 0 else 0.0)


@njit(cache=True)
def simulate(o, h, l, c, long_sig, short_sig, exit_long, exit_short, tp_pct, tp_share,
             literal, comm, use_long, use_short, eq0):
    """Pine order model on bars. Returns (equity curve, trades[n, 6]) with columns
    entry bar, exit bar, side, entry price, avg exit price, pnl in cash for the whole trade."""
    n = len(o)
    eq = np.empty(n)
    cash = eq0
    pos = 0.0            # signed quantity
    avg = 0.0
    ent_bar = -1
    tp_live = False      # a TP order is resting for this bar
    tp_qty = 0.0
    tp_px = 0.0
    tp_done = False      # `intended` mode: the partial has already fired for this position
    pend_close = False
    pend_long = False
    pend_short = False
    trades = np.zeros((n, 6))
    nt = 0
    real = 0.0           # realised cash of the open trade
    fills_exit = 0.0     # sum(qty * price) of exits, for the average exit price
    qty_exit = 0.0

    for t in range(n):
        op = o[t]
        # ---- at the open: market orders from the previous close
        if pend_close and pos != 0.0:
            pnl = pos * (op - avg) - abs(pos) * op * comm
            real += pnl
            fills_exit += abs(pos) * op
            qty_exit += abs(pos)
            trades[nt, 0] = ent_bar; trades[nt, 1] = t; trades[nt, 2] = _sign(pos)
            trades[nt, 3] = avg; trades[nt, 4] = fills_exit / qty_exit; trades[nt, 5] = real
            nt += 1
            cash += real
            pos = 0.0; real = 0.0; fills_exit = 0.0; qty_exit = 0.0
            tp_live = False; tp_done = False
        want = 0
        if pend_long and use_long:
            want = 1
        if pend_short and use_short:
            want = -1 if want == 0 else want   # both at once: cannot happen on one bar
        if want != 0 and _sign(pos) != want:
            if pos != 0.0:                       # reverse: close at the open first
                pnl = pos * (op - avg) - abs(pos) * op * comm
                real += pnl
                fills_exit += abs(pos) * op
                qty_exit += abs(pos)
                trades[nt, 0] = ent_bar; trades[nt, 1] = t; trades[nt, 2] = _sign(pos)
                trades[nt, 3] = avg; trades[nt, 4] = fills_exit / qty_exit; trades[nt, 5] = real
                nt += 1
                cash += real
                pos = 0.0; real = 0.0; fills_exit = 0.0; qty_exit = 0.0
            qty = cash / op                       # 100% of equity
            pos = want * qty
            avg = op
            ent_bar = t
            real = -qty * op * comm
            tp_live = False; tp_done = False
        pend_close = False; pend_long = False; pend_short = False
        # ---- intrabar: the resting take-profit
        if tp_live and pos != 0.0:
            filled = False
            px = 0.0
            if pos > 0:
                if op >= tp_px:
                    filled = True; px = op
                elif h[t] >= tp_px:
                    filled = True; px = tp_px
            else:
                if op <= tp_px:
                    filled = True; px = op
                elif l[t] <= tp_px:
                    filled = True; px = tp_px
            if filled:
                side = _sign(pos)
                q = min(tp_qty, abs(pos))
                pnl = side * q * (px - avg) - q * px * comm
                real += pnl
                fills_exit += q * px
                qty_exit += q
                pos -= side * q
                tp_done = True
                if abs(pos) < 1e-12:
                    trades[nt, 0] = ent_bar; trades[nt, 1] = t; trades[nt, 2] = side
                    trades[nt, 3] = avg; trades[nt, 4] = fills_exit / qty_exit; trades[nt, 5] = real
                    nt += 1
                    cash += real
                    pos = 0.0; real = 0.0; fills_exit = 0.0; qty_exit = 0.0
            tp_live = False
        # ---- at the close: signals for the next open, and the exit order
        eq[t] = cash + (pos * (c[t] - avg) + real if pos != 0.0 else 0.0)
        if long_sig[t] and use_long:
            pend_long = True
        if short_sig[t] and use_short:
            pend_short = True
        if pos > 0 and exit_long[t]:
            pend_close = True
        if pos < 0 and exit_short[t]:
            pend_close = True
        if pos != 0.0 and (literal or not tp_done):
            tp_live = True
            tp_qty = abs(pos) * tp_share
            tp_px = avg * (1.0 + tp_pct) if pos > 0 else avg * (1.0 - tp_pct)
    return eq, trades[:nt]


def run(b, S, tp_pct=0.02, tp_share=0.5, literal=True, comm=0.0005, use_long=True,
        use_short=True, eq0=1000.0):
    eq, tr = simulate(b["open"].to_numpy(), b["high"].to_numpy(), b["low"].to_numpy(),
                      b["close"].to_numpy(), S["long"], S["short"], S["exit_long"],
                      S["exit_short"], tp_pct, tp_share, literal, comm, use_long, use_short, eq0)
    t = pd.DataFrame(tr, columns=["ent", "ex", "side", "entry", "exit", "pnl"])
    t["ent"] = t["ent"].astype(int); t["ex"] = t["ex"].astype(int)
    t["ret"] = t["side"] * (t["exit"] / t["entry"] - 1.0)          # gross % move captured
    t["hold_h"] = t["ex"] - t["ent"]
    return pd.Series(eq, index=b.index), t


def metrics(eq, t, eq0=1000.0):
    if len(t) == 0:
        return dict(n=0, net=np.nan, pf=np.nan, win=np.nan, dd=np.nan, ret=np.nan, hold=np.nan)
    g = t.pnl[t.pnl > 0].sum(); l = -t.pnl[t.pnl <= 0].sum()
    dd = float(((eq.cummax() - eq) / eq.cummax()).max())
    return dict(n=int(len(t)), net=float(eq.iloc[-1] / eq0 - 1.0), pf=float(g / l) if l else np.inf,
                win=float((t.pnl > 0).mean()), dd=dd, ret=float(t.ret.mean()),
                hold=float(t.hold_h.median()))


def _draw(b, S, rng, K_long, K_short, pool_long, pool_short, **kw):
    n = len(b)
    S2 = dict(S)
    ls = np.zeros(n, bool); ss = np.zeros(n, bool)
    if K_long > 0:
        ls[rng.choice(pool_long, min(K_long, len(pool_long)), replace=False)] = True
    if K_short > 0:
        ss[rng.choice(pool_short, min(K_short, len(pool_short)), replace=False)] = True
    S2["long"] = ls; S2["short"] = ss
    eq, t = run(b, S2, **kw)
    return eq, t


def control(b, S, n_draws=300, seed=0, pool="filter", **kw):
    """Random entry bars with identical exits, take-profit, sizing and costs, MATCHED ON THE
    NUMBER OF TRADES TAKEN per side (a random signal is taken more often than a clustered
    breakout, so matching signal counts would hand the control more trades and more
    commission). `pool="filter"` draws from bars where the width filter passes, so the control
    keeps the regime and loses only the breakout timing; `pool="any"` draws from every bar.
    Returns (net returns of the draws, mean trades per draw)."""
    rng = np.random.default_rng(seed)
    n = len(b)
    eq, t = run(b, S, **kw)
    n_long = int((t.side > 0).sum()); n_short = int((t.side < 0).sum())
    warm = 60
    fark = S["fark"]
    okf = np.isfinite(fark) & (fark > 3.0) if pool == "filter" else np.ones(n, bool)
    okf[:warm] = False
    pl = np.where(okf)[0]; ps = pl
    # calibrate how many random signals give the same trade count, on pilot draws
    K_long, K_short = n_long, n_short
    for _ in range(6):
        tl = []; ts = []
        for _d in range(8):
            _, td = _draw(b, S, rng, K_long, K_short, pl, ps, **kw)
            tl.append((td.side > 0).sum()); ts.append((td.side < 0).sum())
        ml, ms = max(np.mean(tl), 1), max(np.mean(ts), 1)
        K_long = int(round(K_long * n_long / ml)) if n_long else 0
        K_short = int(round(K_short * n_short / ms)) if n_short else 0
    out = np.empty(n_draws); cnt = np.empty(n_draws)
    for d in range(n_draws):
        eqd, td = _draw(b, S, rng, K_long, K_short, pl, ps, **kw)
        out[d] = eqd.iloc[-1] / 1000.0 - 1.0
        cnt[d] = len(td)
    return out, float(cnt.mean())
