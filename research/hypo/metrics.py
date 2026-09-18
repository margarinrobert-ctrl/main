"""The full metric suite, computed per market and per block.

Ranking is on RISK-ADJUSTED and ROBUSTNESS terms, never on net profit. Every metric here is
computed in R units so the four markets are directly comparable despite trading at 12,000
(US100), 20,000 (NQ), 31,000 (US30) and 1,400-4,900 (XAUUSD).

DAILY AGGREGATION for Sharpe/Sortino. A per-trade Sharpe is not comparable between a rule that
fires twice a day and one that fires twenty times; aggregating R to calendar days and annualising
by 252 makes them commensurable, and it is also what a risk manager actually sees.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ANN = 252.0


def suite(R, days, min_trades=30):
    """R = per-trade returns in R units; days = integer day key per trade."""
    R = np.asarray(R, float)
    if len(R) < min_trades:
        return None
    wins, losses = R[R > 0], R[R <= 0]
    gross_win = float(wins.sum()); gross_loss = float(-losses.sum())
    eq = np.cumsum(R)
    dd_curve = np.maximum.accumulate(eq) - eq
    maxdd = float(dd_curve.max()) if len(dd_curve) else 0.0

    # daily aggregation
    u, inv = np.unique(days, return_inverse=True)
    daily = np.bincount(inv, weights=R)
    sd = float(daily.std(ddof=1)) if len(daily) > 1 else np.nan
    downside = daily[daily < 0]
    dsd = float(downside.std(ddof=1)) if len(downside) > 1 else np.nan
    mean_d = float(daily.mean())
    sharpe = mean_d / sd * np.sqrt(ANN) if sd and sd > 0 else np.nan
    sortino = mean_d / dsd * np.sqrt(ANN) if dsd and dsd > 0 else np.nan
    ann_ret = mean_d * ANN
    calmar = ann_ret / maxdd if maxdd > 0 else np.nan

    # concentration: does a handful of trades carry it?
    order = np.sort(R)[::-1]
    top5 = float(order[:max(1, len(R) // 20)].sum())
    conc = top5 / float(R.sum()) if R.sum() > 0 else np.nan

    return dict(
        n=len(R), days=len(u),
        win=100.0 * float((R > 0).mean()),
        expR=float(R.mean()), medR=float(np.median(R)), totalR=float(R.sum()),
        pf=gross_win / gross_loss if gross_loss > 0 else np.inf,
        maxdd_R=maxdd, sharpe=sharpe, sortino=sortino, calmar=calmar,
        ret_dd=float(R.sum()) / maxdd if maxdd > 0 else np.nan,
        avg_win=float(wins.mean()) if len(wins) else np.nan,
        avg_loss=float(losses.mean()) if len(losses) else np.nan,
        max_losing_streak=_streak(R <= 0),
        top5pct_share=conc,
    )


def _streak(flags):
    best = cur = 0
    for f in flags:
        cur = cur + 1 if f else 0
        best = max(best, cur)
    return int(best)


def robustness_score(per_market, plateau, oos_retention, cost_stress, min_markets=3):
    """A transparent 0-100 composite. Every term is printed alongside, never just the total.

    markets_positive   how many of the four hold positive out-of-sample expectancy
    plateau            fraction of the parameter neighbourhood that stays positive
    oos_retention      out-of-sample expectancy divided by research expectancy, clipped to [0,1]
    cost_stress        expectancy at 1.5x assumed costs divided by expectancy at 1x, clipped
    """
    mk = sum(1 for m in per_market.values() if m is not None and m.get("expR", -1) > 0)
    parts = dict(
        markets=25.0 * min(mk / max(min_markets, 1), 1.0),
        plateau=25.0 * float(np.clip(plateau, 0, 1)),
        oos=30.0 * float(np.clip(oos_retention, 0, 1)),
        cost=20.0 * float(np.clip(cost_stress, 0, 1)),
    )
    return sum(parts.values()), parts
