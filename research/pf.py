"""Trades -> a vectorbt Portfolio and its analytics.

The simulation is ours (it is checked trade-for-trade against the TypeScript engine); vectorbt is
used for the parts it does better than a hand-roll — the returns accessor, drawdown decomposition
and risk ratios, which are well-tested and easy to get subtly wrong by hand.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import vectorbt as vbt


def daily_returns(trades: pd.DataFrame, index: pd.DatetimeIndex, start_equity: float = 50_000.0) -> pd.Series:
    """Per-session returns on a mark-to-close equity curve, indexed by session date."""
    if len(trades) == 0:
        return pd.Series(dtype=float)
    exit_ts = index[trades["exitIndex"].to_numpy()]
    daily = pd.Series(trades["pnl"].to_numpy(), index=exit_ts.normalize()).groupby(level=0).sum()
    equity = start_equity + daily.cumsum()
    prev = equity.shift(1).fillna(start_equity)
    return (equity / prev - 1.0).rename("returns")


def stats(trades: pd.DataFrame, index: pd.DatetimeIndex, start_equity: float = 50_000.0) -> dict:
    """Headline risk statistics, computed through vectorbt's returns accessor."""
    r = daily_returns(trades, index, start_equity)
    if len(r) < 3:
        return {}
    acc = r.vbt.returns(freq="1D")
    equity = start_equity + pd.Series(trades["pnl"].to_numpy(),
                                      index=index[trades["exitIndex"].to_numpy()].normalize()).groupby(level=0).sum().cumsum()
    dd = (equity - equity.cummax()) / (start_equity + equity.cummax())
    return {
        "trades": len(trades),
        "win_rate": float((trades.pnl > 0).mean()),
        "expectancy_r": float(trades.r.mean()),
        "total_pnl": float(trades.pnl.sum()),
        "sharpe": float(acc.sharpe_ratio()),
        "sortino": float(acc.sortino_ratio()),
        "calmar": float(acc.calmar_ratio()),
        "max_dd_pct": float(-dd.min() * 100),
        "profit_factor": float(trades.pnl[trades.pnl > 0].sum() / max(-trades.pnl[trades.pnl < 0].sum(), 1e-9)),
    }
