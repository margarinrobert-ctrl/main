"""Trend-following research lab: 200 EMA + ADX + EMA crossover + ATR + 50 EMA.

WHAT THIS CAN AND CANNOT ANSWER. One instrument (NQ/MNQ), one continuous sample,
2022-12-26 to 2025-12-12, 1-minute bars resampled to 5m/15m/60m/240m/daily. There is no second
market here and no network to fetch one, so the cross-market question is OUT OF REACH and is
reported as such rather than guessed at. Three years is also one regime: NQ roughly doubled over
it, which is why every long-side number is scored against a matched control that already contains
that drift.

Method, in the order it matters:
  * selection happens on the RESEARCH block only, the first 65% of sessions (599 of 922);
  * the LOCKED block is read once, at the end, for a handful of pre-committed candidates;
  * every candidate is scored against a matched control -- random entries with the same side,
    geometry and minute-of-day distribution -- so drift, session timing, costs and barrier width
    are priced in before a rule is credited with anything;
  * costs are itemised (broker + exchange + clearing + NFA) with bar-dependent slippage;
  * the count of configurations examined is carried everywhere, because with a grid this size
    multiplicity is the binding constraint before anything else is.

Look-ahead: a signal is read at the close of bar i and filled at the OPEN of bar i+1. Indicators
are asserted causal by truncating the series and re-checking every value before the cut
(`indpool.leak_check`). The engine is asserted against `test_suite.sim_core` trade for trade on
4.6M trades. Costs are charged on both fills.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import indpool
import tuner as U

COSTS = U.Costs(symbol="MNQ", broker="discount")
ANN = 252


# ================================================================= metrics
@dataclass
class Metrics:
    n: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    expectancy: float = 0.0
    profit_factor: float = 0.0
    net: float = 0.0
    max_dd: float = 0.0
    avg_dd: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    cagr: float = 0.0
    calmar: float = 0.0
    recovery: float = 0.0
    max_win_streak: int = 0
    max_loss_streak: int = 0
    avg_hold_bars: float = 0.0
    exposure: float = 0.0
    t_stat: float = 0.0
    months_pos: float = 0.0

    def row(self):
        return (f"{self.n:>6}{self.win_rate:>7.1f}{self.avg_win:>9.0f}{self.avg_loss:>9.0f}"
                f"{self.expectancy:>10.2f}{self.profit_factor:>7.2f}{self.net:>10,.0f}"
                f"{self.max_dd:>9,.0f}{self.sharpe:>7.2f}{self.sortino:>8.2f}"
                f"{self.calmar:>7.2f}{self.max_loss_streak:>5}")


def metrics(pnl, eb, xb, si, n_sess, n_bars, capital=25_000.0, sess_per_year=252) -> Metrics:
    """Every statistic the brief asks for that this data can actually support.

    CAGR and Calmar need an equity base, which a fixed-one-contract backtest does not have. The
    `capital` figure is an ASSUMPTION stated in the output, not a measurement, and it scales both
    linearly -- so treat their ORDERING as meaningful and their level as conditional on it.
    """
    m = Metrics()
    m.n = int(len(pnl))
    if m.n == 0:
        return m
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    m.win_rate = 100.0 * len(wins) / m.n
    m.avg_win = float(wins.mean()) if len(wins) else 0.0
    m.avg_loss = float(losses.mean()) if len(losses) else 0.0
    p = len(wins) / m.n
    # Expectancy = (win rate x average win) - (loss rate x average loss), which for a per-trade
    # P&L series is just the mean; computed both ways here because the brief asks for it
    # explicitly and the identity is worth showing rather than asserting.
    m.expectancy = p * m.avg_win + (1 - p) * m.avg_loss
    gw, gl = float(wins.sum()), float(-losses.sum())
    m.profit_factor = gw / gl if gl > 0 else (np.inf if gw > 0 else 0.0)
    m.net = float(pnl.sum())

    eq = np.cumsum(pnl)
    peak = np.maximum.accumulate(np.r_[0.0, eq])[1:]
    dd = peak - eq
    m.max_dd = float(dd.max()) if len(dd) else 0.0
    m.avg_dd = float(dd[dd > 0].mean()) if (dd > 0).any() else 0.0
    m.recovery = m.net / m.max_dd if m.max_dd > 0 else np.inf

    daily = np.zeros(n_sess)
    np.add.at(daily, si[eb], pnl)
    sd = daily.std(ddof=1)
    m.sharpe = float(daily.mean() / sd * np.sqrt(sess_per_year)) if sd > 0 else 0.0
    down = daily[daily < 0]
    dsd = np.sqrt((down ** 2).mean()) if len(down) else 0.0
    m.sortino = float(daily.mean() / dsd * np.sqrt(sess_per_year)) if dsd > 0 else 0.0

    years = n_sess / sess_per_year
    end = capital + m.net
    m.cagr = (100.0 * ((end / capital) ** (1 / years) - 1)) if end > 0 and years > 0 else -100.0
    m.calmar = m.cagr / (100.0 * m.max_dd / capital) if m.max_dd > 0 else np.inf

    sign = pnl > 0
    best = cur = 0; worst = curl = 0
    for s in sign:
        if s:
            cur += 1; curl = 0
        else:
            curl += 1; cur = 0
        best = max(best, cur); worst = max(worst, curl)
    m.max_win_streak, m.max_loss_streak = best, worst

    hold = xb - eb
    m.avg_hold_bars = float(hold.mean())
    m.exposure = 100.0 * float(hold.sum()) / max(n_bars, 1)

    v = pnl.var(ddof=1)
    m.t_stat = float(m.expectancy / np.sqrt(v / m.n)) if v > 0 else 0.0

    # monthly buckets, approximated by 21-session blocks
    blocks = si[eb] // 21
    if len(blocks):
        agg = {}
        for b, v_ in zip(blocks, pnl):
            agg[b] = agg.get(b, 0.0) + v_
        vals = np.array(list(agg.values()))
        m.months_pos = 100.0 * float((vals > 0).mean())
    return m


def trades_for(rule, tf, side, stop, target, hold=0, win="00:00-23:59", flat=0,
               stop_series=None, tag="", costs=COSTS, atr_n=14):
    """The realised trade list for one configuration."""
    d = U.bars(tf)
    wm = U.win_mask(d, win)
    T = U.tensor(tf, side, [stop], [target], [flat], [hold], atr_n, U.Entry(), only=wm,
                 stop_series=stop_series, tag=tag)
    trig = np.flatnonzero(U.mask(d, rule) & wm).astype(np.int64)
    n = len(trig)
    pnl = np.zeros(n); eb = np.zeros(n, np.int64); xb = np.zeros(n, np.int64); wo = np.zeros(n, np.int64)
    ft, fs = costs.friction(d)
    k = U._walk_one(trig, T.xb[0], T.why[0], T.raw[0], ft, fs, costs.fee_rt(),
                    costs.maker_target(), d["si"], np.int64(d["cut"]), pnl, eb, xb, wo)
    return pnl[:k], eb[:k], xb[:k], wo[:k], d, T, trig


def evaluate(rule, tf, side, stop, target, hold=0, win="00:00-23:59", block="research",
             stop_series=None, tag="", costs=COSTS, atr_n=14):
    """Metrics for one configuration, restricted to a block."""
    pnl, eb, xb, wo, d, T, trig = trades_for(rule, tf, side, stop, target, hold, win,
                                             stop_series=stop_series, tag=tag, costs=costs,
                                             atr_n=atr_n)
    si = d["si"]; cut = d["cut"]
    if block == "research":
        keep = si[eb] < cut
        n_sess = cut
    elif block == "locked":
        keep = si[eb] >= cut
        n_sess = d["n_sess"] - cut
    else:
        keep = np.ones(len(pnl), bool)
        n_sess = d["n_sess"]
    return metrics(pnl[keep], eb[keep], xb[keep], si, d["n_sess"], d["n"],
                   sess_per_year=ANN), int(keep.sum())


HEAD = (f"  {'variant':<46}{'n':>6}{'win%':>7}{'avgW':>9}{'avgL':>9}{'expect':>10}"
        f"{'PF':>7}{'net':>10}{'maxDD':>9}{'Shrp':>7}{'Sortino':>8}{'Calmar':>7}{'Lstk':>5}")


def breakeven_table(tf=60):
    """The break-even win rate for each reward:risk, before and after real costs.

    Before costs it is 1/(1+R) and that is arithmetic, not a measurement. After costs it depends on
    the risk distance in dollars, so it is quoted at the median stop distance this data actually
    produced -- which is why it is computed here rather than asserted.
    """
    d = U.bars(tf)
    atr = U._stop_atr(d, 14)
    m = np.nanmedian(atr[np.isfinite(atr)])
    pv = COSTS.model().pv
    print(f"\n  BREAK-EVEN WIN RATE BY REWARD:RISK   [{tf}m, median ATR(14) = {m:.1f} pts]")
    print(f"  {'R':>6}{'before costs':>15}{'2.0xATR stop':>15}{'1.5xATR stop':>15}{'1.0xATR stop':>15}")
    for R in (1.0, 1.25, 1.5, 2.0, 2.5, 3.0):
        row = f"  {R:>6.2f}{100.0 / (1.0 + R):>14.1f}%"
        for k in (2.0, 1.5, 1.0):
            risk = k * m * pv
            rt = COSTS.model().round_turn_points("taker", "stop") * pv
            # win*(R*risk - rt) = (1-win)*(risk + rt)  ->  solve for win
            wr = (risk + rt) / (R * risk + risk)
            row += f"{100 * wr:>14.1f}%"
        print(row)
    print("  Costs move the hurdle UP, and they move it up most where the stop is tightest --")
    print("  a 1.0xATR stop on 60-minute bars pays the same round turn against a smaller edge.")


# ================================================================= the five variants
# Written as templates so every parameter the brief asks about is a swept axis, not a choice.
# {T} trend EMA, {A} ADX threshold, {F}/{S} fast/slow crossover EMAs, {P} pullback EMA.
VARIANTS = {
    "A conservative continuation": {
        "long":  "close>ema{T} and adx14>{A} and cross({F},{S})>0",
        "short": "close<ema{T} and adx14>{A} and cross({F},{S})<0",
        "note": "trend filter + strength + crossover as the trigger",
    },
    "B same, slope-confirmed": {
        "long":  "close>ema{T} and emaslope{T}>0 and adx14>{A} and cross({F},{S})>0",
        "short": "close<ema{T} and emaslope{T}<0 and adx14>{A} and cross({F},{S})<0",
        "note": "adds the 200 EMA slope condition",
    },
    "C pullback": {
        "long":  "close>ema{T} and adx14>{A} and ema{F}>ema{S} and close<ema{P} and close>ema{P}*0.999",
        "short": "close<ema{T} and adx14>{A} and ema{F}<ema{S} and close>ema{P} and close<ema{P}*1.001",
        "note": "trend established first, entry on a touch of the pullback EMA",
    },
    "D breakout": {
        "long":  "close>ema{T} and adx14>{A} and ema{F}>ema{S} and close>hh20",
        "short": "close<ema{T} and adx14>{A} and ema{F}<ema{S} and close<ll20",
        "note": "trend regime + 20-bar breakout",
    },
    "E adaptive": {
        "long":  "close>ema{T} and adx14>{A} and ema{F}>ema{S} and emadist{T}>0.5 and bbw20>0.4",
        "short": "close<ema{T} and adx14>{A} and ema{F}<ema{S} and emadist{T}<-0.5 and bbw20>0.4",
        "note": "adds distance-from-trend and a volatility-regime condition",
    },
}

# Entry structures, including the resting-limit mechanic (BUYLEVEL = C - ATR(5)*0.75).
ENTRIES = {
    "market at next open": U.Entry(),
    "BUYLEVEL limit 0.75xATR5": U.Entry(kind="limit", k=0.75, expiry=6, thru=2.0),
}


def variant_scan(tf=60, T=200, A=25, F=9, S=21, P=21, targets=(1.0, 1.5, 2.0), stop=2.0,
                 hold=0, verbose=True):
    """Every variant x side x reward:risk x entry structure, on the RESEARCH block."""
    rows = []
    if verbose:
        print("=" * 132)
        print(f"VARIANTS   [{tf}m, trend EMA {T}, ADX>{A}, cross {F}/{S}, pullback EMA {P}, "
              f"stop {stop}xATR, MNQ real fees, RESEARCH BLOCK]")
        print("=" * 132)
        print(HEAD)
    for name, v in VARIANTS.items():
        for side_name, side in (("long", 1), ("short", -1)):
            rule = v[side_name].format(T=T, A=A, F=F, S=S, P=P)
            for R in targets:
                for ename, ent in ENTRIES.items():
                    lim = ent.kind == "limit"
                    d = U.bars(tf)
                    Tn = U.tensor(tf, side, [stop], [R], [0], [hold], 14, ent, only=None)
                    trig = np.flatnonzero(U.mask(d, rule)).astype(np.int64)
                    n = len(trig)
                    pnl = np.zeros(n); eb = np.zeros(n, np.int64)
                    xb = np.zeros(n, np.int64); wo = np.zeros(n, np.int64)
                    ft, fs = COSTS.friction(d)
                    k = U._walk_one(trig, Tn.xb[0], Tn.why[0], Tn.raw[0], ft, fs, COSTS.fee_rt(),
                                    COSTS.maker_target(), d["si"], np.int64(d["cut"]),
                                    pnl, eb, xb, wo)
                    pnl, eb, xb = pnl[:k], eb[:k], xb[:k]
                    keep = d["si"][eb] < d["cut"]
                    m = metrics(pnl[keep], eb[keep], xb[keep], d["si"], d["n_sess"], d["n"])
                    label = f"{name[:26]} {side_name} 1:{R:g} {'LIMIT' if lim else 'mkt'}"
                    rows.append(dict(variant=name, side=side_name, R=R, entry=ename, m=m,
                                     rule=rule, tf=tf, stop=stop, hold=hold))
                    if verbose and m.n >= 25:
                        print(f"  {label:<46}{m.row()}")
    return rows
