"""Eight named volatility-sizing methods, implemented distinctly, with the overlaps stated.

Several of these names describe the same arithmetic. Saying so is not pedantry -- testing eight
labels for one formula and reporting eight results would be eight ways of reporting one, and it
is exactly the mistake this repository keeps catching itself making. So they are grouped by what
they actually compute, and the ones that genuinely differ are implemented separately.

GROUP A -- risk normalising.  lots = budget / (stop distance in dollars).
    Every trade risks the same amount. Which member you have depends on two choices: what
    estimates the stop distance, and whether the budget compounds.

    VAPS  Volatility-Adjusted Position Sizing   sigma = ATR(14) at entry, budget from START capital
    DVS   Dynamic Volatility Sizing             sigma = fast realised vol (10 bars), budget from start
    RSPS  Risk-Scaled Position Sizing           sigma = ATR(14), budget = % of CURRENT equity

GROUP B -- output-volatility targeting.  Genuinely different: it does not look at the
    instrument's volatility at all, it looks at the STRATEGY's own realised P&L volatility and
    scales so that lands on a target.

    VTM   Volatility Targeting Model            lots = target_vol * equity / realised_strategy_vol

GROUP C -- regime scaling of the budget itself.
    VRS   Volatility Risk Scaling               budget * (reference_vol / current_vol), clamped
    VRSP  Volatility-Responsive Sizing          discrete step by volatility tercile, not continuous
    DRS   Dynamic Risk Scaling                  budget scaled by DRAWDOWN state, not by volatility

GROUP D -- cross-sectional.
    AVA   Adaptive Volatility Allocation        across LEGS: weight proportional to 1/sigma_leg,
                                                re-estimated on a rolling window

WHEN ANY OF THIS CAN HELP AT ALL: only when risk per trade actually varies. If a strategy's stop
distance is nearly constant across trades, every Group A method reduces to a fixed lot size and
the whole exercise is arithmetic with no effect. `dispersion()` measures that first, so a null
result can be read as "nothing to fix" rather than "the method failed".
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
from test_suite import _daily

PV = 2.0
METHODS = ["fixed", "VAPS", "DVS", "RSPS", "VTM", "VRS", "VRSP", "DRS"]


def dispersion(s, atr_mult):
    """Coefficient of variation of per-trade dollar risk. Below ~0.15 no sizing method can do
    anything, because every trade already risks nearly the same."""
    risk = atr_mult * s.bars["atr"][s.ent_bar] * PV
    return float(np.std(risk) / max(np.mean(risk), 1e-9)), risk


def _fast_vol(s, lb=10):
    ret = np.r_[0.0, np.diff(s.bars["c"])]
    v = np.array([ret[max(0, b - lb):b].std() if b > lb else np.nan for b in s.ent_bar])
    return np.nan_to_num(v, nan=np.nanmedian(v))


def _trailing_strategy_vol(pnl, lb=30):
    """Realised volatility of the strategy's OWN per-trade P&L, using only prior trades."""
    out = np.full(len(pnl), np.nan)
    for i in range(len(pnl)):
        if i >= 10:
            out[i] = np.std(pnl[max(0, i - lb):i])
    return np.nan_to_num(out, nan=np.nanmedian(out[np.isfinite(out)]) if np.isfinite(out).any() else 1.0)


def size(s, method, atr_mult, risk_pct=0.01, capital=50_000.0, target_vol=0.10,
         max_lots=10, vol_ref_lb=250, dd_floor=0.5):
    """Lots per trade under one method. Everything is causal: only prior trades and prior bars."""
    n = len(s.pnl)
    cv, risk_d = dispersion(s, atr_mult)
    risk_d = np.maximum(risk_d, 1e-9)
    lots = np.ones(n)

    if method == "fixed":
        return lots
    if method == "VAPS":
        lots = (risk_pct * capital) / risk_d
    elif method == "DVS":
        fv = _fast_vol(s)
        lots = (risk_pct * capital) / np.maximum(atr_mult * fv * PV, 1e-9)
    elif method == "RSPS":
        eq = capital
        for i in range(n):
            lots[i] = np.floor(max((risk_pct * eq) / risk_d[i], 0.0))
            lots[i] = min(lots[i], max_lots)
            eq += s.pnl[i] * lots[i]
        return lots
    elif method == "VTM":
        sv = _trailing_strategy_vol(s.pnl)
        lots = (target_vol * capital / np.sqrt(252)) / np.maximum(sv, 1e-9)
    elif method == "VRS":
        ret = np.r_[0.0, np.diff(s.bars["c"])]
        cur = np.array([ret[max(0, b - 20):b].std() if b > 20 else np.nan for b in s.ent_bar])
        ref = np.array([ret[max(0, b - vol_ref_lb):b].std() if b > vol_ref_lb else np.nan
                        for b in s.ent_bar])
        sc = np.nan_to_num(ref / np.maximum(cur, 1e-9), nan=1.0)
        lots = (risk_pct * capital) / risk_d * np.clip(sc, 0.5, 2.0)
    elif method == "VRSP":
        ret = np.r_[0.0, np.diff(s.bars["c"])]
        cur = np.array([ret[max(0, b - 20):b].std() if b > 20 else np.nan for b in s.ent_bar])
        step = np.ones(n)
        for i in range(n):
            past = cur[:i][np.isfinite(cur[:i])]
            if len(past) < 30 or not np.isfinite(cur[i]):
                continue
            lo, hi = np.percentile(past, [33.3, 66.7])
            step[i] = 1.5 if cur[i] <= lo else (0.5 if cur[i] >= hi else 1.0)
        lots = (risk_pct * capital) / risk_d * step
    elif method == "DRS":
        eq = capital; peak = capital
        for i in range(n):
            dd = (peak - eq) / max(peak, 1e-9)
            scale = max(dd_floor, 1.0 - 2.0 * dd)       # halve risk at a 25% drawdown
            lots[i] = np.floor(max((risk_pct * eq * scale) / risk_d[i], 0.0))
            lots[i] = min(lots[i], max_lots)
            eq += s.pnl[i] * lots[i]
            peak = max(peak, eq)
        return lots
    return np.clip(np.floor(lots), 0, max_lots)


def evaluate(s, method, atr_mult, **kw):
    lots = size(s, method, atr_mult, **kw)
    p = s.pnl * lots
    r = s.ent_sess < s.cut
    d = np.zeros(s.n_sess)
    for x, e in zip(p, s.ent_sess):
        d[e] += x
    eq = np.cumsum(p)
    dd = float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max())
    sh = float(d.mean() / d.std(ddof=1) * np.sqrt(252)) if d.std() > 0 else 0.0
    return dict(method=method, net=float(p.sum()), res=float(p[r].sum()), lok=float(p[~r].sum()),
                dd=dd, sharpe=sh, mar=float(p.sum() / dd) if dd > 0 else 0.0,
                mean_lots=float(lots.mean()), zero=float((lots == 0).mean()))


def ava(legs, lb=120):
    """Adaptive Volatility Allocation across LEGS: weight proportional to 1/sigma, re-estimated
    on a rolling window using only prior sessions."""
    n_sess = max(s.n_sess for s in legs)
    D = np.column_stack([np.r_[_daily(s), np.zeros(n_sess)][:n_sess] for s in legs])
    W = np.ones_like(D)
    for t in range(lb, D.shape[0]):
        sd = D[t - lb:t].std(0, ddof=1)
        w = 1.0 / np.maximum(sd, 1e-9)
        W[t] = w / w.sum() * D.shape[1]
    return (D * W).sum(1), D.sum(1)
