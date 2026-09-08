"""The container every backtest produces and every consumer reads.

A :class:`BacktestResult` is self-describing: it carries the bars it was run on,
the trades, the per-bar equity and balance curves, the indicator arrays used by
the rules, and enough configuration to reproduce the run.  The analytics, chart,
trade table, report and comparison layers all read this one object.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..core.types import BacktestConfig, ExitReason, Order, Side, Trade


@dataclass
class EquityCurves:
    """Per-bar account series, all the same length as the bars that were run."""

    ts: np.ndarray
    equity: np.ndarray
    """Balance plus the mark-to-market value of any open position."""
    balance: np.ndarray
    """Realised cash only; steps at each closed trade."""
    drawdown: np.ndarray
    """Equity minus its running peak, in cash.  Always <= 0."""
    drawdown_pct: np.ndarray
    """Drawdown as a fraction of the running peak.  Always <= 0."""
    exposure: np.ndarray
    """Signed position size per bar, for the exposure ribbon on the chart."""
    peak: np.ndarray

    def __len__(self) -> int:
        return len(self.ts)


@dataclass
class BacktestResult:
    """Everything one run produced."""

    # -- identity ---------------------------------------------------------
    run_id: str = ""
    label: str = ""
    strategy_name: str = ""
    strategy_id: str = ""
    instrument_symbol: str = ""
    timeframe_label: str = ""
    created_at: str = ""
    duration_seconds: float = 0.0
    """Wall-clock time the run took, for the status bar."""

    # -- inputs -----------------------------------------------------------
    bars: Any = None
    """The :class:`~tradingbacktester.data.models.BarSeries` actually simulated."""
    config: BacktestConfig = field(default_factory=BacktestConfig)
    strategy_dict: dict[str, Any] = field(default_factory=dict)
    """The strategy, serialised, so a saved run can be re-opened and re-run."""
    param_values: dict[str, Any] = field(default_factory=dict)

    # -- outputs ----------------------------------------------------------
    trades: list[Trade] = field(default_factory=list)
    orders: list[Order] = field(default_factory=list)
    curves: EquityCurves | None = None
    indicators: dict[str, dict[str, np.ndarray]] = field(default_factory=dict)
    """``{slot_ref: {output_name: array}}`` for everything the chart may plot."""
    signals: dict[str, np.ndarray] = field(default_factory=dict)
    """Boolean arrays: ``entry_long``, ``entry_short``, ``exit_long``, ``exit_short``,
    plus ``tradeable`` (session filter)."""
    metrics: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    rejected_orders: int = 0
    bars_processed: int = 0

    # -- convenience ------------------------------------------------------

    @property
    def trade_count(self) -> int:
        return len(self.trades)

    @property
    def final_equity(self) -> float:
        if self.curves is None or len(self.curves) == 0:
            return float(self.config.starting_capital)
        return float(self.curves.equity[-1])

    @property
    def net_profit(self) -> float:
        return self.final_equity - float(self.config.starting_capital)

    def trades_by_reason(self) -> dict[ExitReason, list[Trade]]:
        out: dict[ExitReason, list[Trade]] = {}
        for t in self.trades:
            out.setdefault(t.exit_reason, []).append(t)
        return out

    def net_pnl_array(self) -> np.ndarray:
        return np.array([t.net_pnl for t in self.trades], dtype="float64")

    def trade_at_bar(self, bar: int) -> Trade | None:
        """The trade whose holding period covers ``bar``, if any."""
        for t in self.trades:
            if t.entry_bar <= bar <= t.exit_bar:
                return t
        return None

    def long_trades(self) -> list[Trade]:
        return [t for t in self.trades if t.side is Side.LONG]

    def short_trades(self) -> list[Trade]:
        return [t for t in self.trades if t.side is Side.SHORT]

    def summary_line(self) -> str:
        m = self.metrics or {}
        return (f"{self.strategy_name} on {self.instrument_symbol} "
                f"{self.timeframe_label}: {self.trade_count} trades, "
                f"net {m.get('net_profit', 0.0):,.2f} "
                f"({m.get('return_pct', 0.0):.2f}%), "
                f"max DD {m.get('max_drawdown_pct', 0.0):.2f}%")
