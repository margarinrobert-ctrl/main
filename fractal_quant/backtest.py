"""No-lookahead backtest + performance stats (Sections 2.6, 2.7, 7.4 costs).

NON-NEGOTIABLE: the position decided at the close of bar i is executed on bar
i+1, i.e. ``stratRet[i] = pos[i-1] * ret[i]``. Transaction costs are charged on
the bar a position change takes effect.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Stats:
    total: float
    cagr: float
    vol: float
    sharpe: float
    max_dd: float

    def as_row(self):
        return [self.total, self.cagr, self.vol, self.sharpe, self.max_dd]


def _stats(rets: np.ndarray, eq: np.ndarray) -> Stats:
    """Performance stats (Section 2.7). ``rets`` aligned with ``eq`` (eq has the
    extra starting point); the first return is dropped, matching the HTML."""
    r = rets[1:]
    yrs = r.size / 252.0
    tot = eq[-1] / eq[0] - 1.0
    cagr = (eq[-1] / eq[0]) ** (1.0 / yrs) - 1.0 if yrs > 0 else 0.0
    sd = float(np.std(r))
    v = sd * np.sqrt(252)
    sh = (float(np.mean(r)) / sd) * np.sqrt(252) if sd > 0 else 0.0
    peak = eq[0]
    mdd = 0.0
    for e in eq:
        if e > peak:
            peak = e
        dd = e / peak - 1.0
        if dd < mdd:
            mdd = dd
    return Stats(tot, cagr, v, sh, mdd)


@dataclass
class BacktestResult:
    strat_ret: np.ndarray
    ret: np.ndarray
    eq_strat: np.ndarray
    eq_bh: np.ndarray
    pos: np.ndarray
    s: Stats          # strategy
    b: Stats          # buy & hold
    trades: int
    exposure: float
    cost_bps: float


def backtest(ret, pos, cost_bps: float = 0.0, start: float = 10000.0) -> BacktestResult:
    """Vectorized no-lookahead backtest.

    Parameters
    ----------
    ret : array-like        simple returns per bar
    pos : array-like        position decided at close of each bar (-1/0/1)
    cost_bps : float        round-trip-agnostic cost per unit turnover, in bps
                            per side (e.g. 1.0 = 1bp). Applied to |Δposition|.
    """
    ret = np.asarray(ret, dtype=float)
    pos = np.asarray(pos, dtype=float)
    n = ret.size

    # execution lag: hold yesterday's decided position through today's return
    held = np.concatenate(([0.0], pos[:-1]))           # held[i] = pos[i-1]
    strat = held * ret

    # transaction costs: the change pos[i-1] vs pos[i-2] takes effect at bar i
    turnover = np.zeros(n)
    turnover[2:] = np.abs(pos[1:-1] - pos[:-2])
    # also the very first entry (pos[0] from flat) executes at bar 1
    turnover[1] = abs(pos[0] - 0.0)
    cost = cost_bps * 1e-4
    strat = strat - turnover * cost

    # build cumulative equity with the leading start point, matching HTML:
    eq_strat = np.empty(n)
    eq_bh = np.empty(n)
    eq_strat[0] = start
    eq_bh[0] = start
    for i in range(1, n):
        eq_strat[i] = eq_strat[i - 1] * (1.0 + strat[i])
        eq_bh[i] = eq_bh[i - 1] * (1.0 + ret[i])

    # trades = any change in pos[i] vs pos[i-1]; exposure = fraction held nonzero
    trades = int(np.sum(pos[1:] != pos[:-1]))
    inmkt = int(np.sum(held[1:] != 0.0))
    exposure = inmkt / (n - 1) if n > 1 else 0.0

    return BacktestResult(
        strat_ret=strat, ret=ret, eq_strat=eq_strat, eq_bh=eq_bh, pos=pos,
        s=_stats(strat, eq_strat), b=_stats(ret, eq_bh),
        trades=trades, exposure=exposure, cost_bps=cost_bps,
    )
