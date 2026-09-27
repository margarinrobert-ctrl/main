"""How a strategy's trades did in each market regime, read at the SIGNAL bar.

Two regimes, both computed causally so a trade is labelled with what was
knowable when its order was sent:

* **Volatility** -- ATR(14) as a percentage of price, ranked against its own
  trailing 250 bars (the bar itself included, nothing after it).  Bottom third
  is ``low``, top third ``high``, the rest ``normal``.
* **Trend** -- the close against its 200-bar simple average: ``above`` or
  ``below``.

Every label is read at the bar that RAISED the signal (``entry_bar - 1``, as
the engine fills an order at the next bar's open), never at the fill bar.
Reading a condition at the fill bar reads a bar that closes after the order is
sent; for a short-hold rule that is the bar the trade resolves on, and it
produces splits that look highly significant and are pure leakage.

What this is NOT
----------------
A split of the trades a rule already took is a description, not a filter
test.  "The edge lives in high volatility" is a hypothesis; testing it means
filtering the rule's TRIGGERS to that regime and re-running the backtest, on
the research block, against a control of the same selectivity.  Each row also
shows the share of all bars in that regime, so a strategy that simply trades
more in one regime is visible as such.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np
import pandas as pd

__all__ = ["RegimeRow", "RegimeBreakdown", "regime_breakdown",
           "format_regimes", "volatility_regime", "trend_regime"]

ATR_PERIOD = 14
VOL_LOOKBACK = 250
VOL_MIN_PERIODS = 50
TREND_PERIOD = 200

#: A regime bucket with fewer trades than this is flagged in the text.
MIN_BUCKET_TRADES = 30


def _atr_pct(bars: Any) -> np.ndarray:
    high = np.asarray(bars.high, dtype="float64")
    low = np.asarray(bars.low, dtype="float64")
    close = np.asarray(bars.close, dtype="float64")
    prev = np.concatenate(([np.nan], close[:-1]))
    tr = np.nanmax(np.vstack([high - low, np.abs(high - prev),
                              np.abs(low - prev)]), axis=0)
    # Wilder's smoothing, the same ATR the engine sizes stops with.
    atr = pd.Series(tr).ewm(alpha=1.0 / ATR_PERIOD, adjust=False,
                            min_periods=ATR_PERIOD).mean().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(close > 0.0, atr / close * 100.0, np.nan)
    return out


def volatility_regime(bars: Any) -> np.ndarray:
    """``low`` / ``normal`` / ``high`` / ``""`` (warm-up) for every bar."""
    atr_pct = pd.Series(_atr_pct(bars))
    # Rolling percentile rank of the LAST value within its trailing window:
    # uses only this bar and the ones before it.
    rank = atr_pct.rolling(VOL_LOOKBACK, min_periods=VOL_MIN_PERIODS).rank(
        pct=True).to_numpy()
    out = np.full(len(rank), "", dtype=object)
    ok = np.isfinite(rank)
    out[ok & (rank <= 1.0 / 3.0)] = "low"
    out[ok & (rank > 1.0 / 3.0) & (rank <= 2.0 / 3.0)] = "normal"
    out[ok & (rank > 2.0 / 3.0)] = "high"
    return out


def trend_regime(bars: Any) -> np.ndarray:
    """``above`` / ``below`` the 200-bar average, ``""`` during warm-up."""
    close = pd.Series(np.asarray(bars.close, dtype="float64"))
    sma = close.rolling(TREND_PERIOD, min_periods=TREND_PERIOD).mean()
    out = np.full(len(close), "", dtype=object)
    ok = sma.notna().to_numpy()
    c = close.to_numpy()
    s = sma.to_numpy()
    out[ok & (c > s)] = "above"
    out[ok & (c <= s)] = "below"
    return out


@dataclass
class RegimeRow:
    dimension: str          # "volatility" or "trend"
    regime: str             # "low", "normal", "high", "above", "below", "warm-up"
    trades: int
    wins: int
    net_profit: float
    gross_profit: float
    gross_loss: float
    bar_share_pct: float    # share of all labelled bars in this regime

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades * 100.0 if self.trades else math.nan

    @property
    def avg_trade(self) -> float:
        return self.net_profit / self.trades if self.trades else math.nan

    @property
    def profit_factor(self) -> float:
        if self.gross_loss < 0.0:
            return self.gross_profit / -self.gross_loss
        return math.inf if self.gross_profit > 0 else math.nan

    @property
    def low_sample(self) -> bool:
        return self.trades < MIN_BUCKET_TRADES

    def to_dict(self) -> dict[str, Any]:
        def clean(v: float) -> float | None:
            return float(v) if math.isfinite(v) else None
        return {"dimension": self.dimension, "regime": self.regime,
                "trades": self.trades, "wins": self.wins,
                "win_rate": clean(self.win_rate),
                "net_profit": self.net_profit, "avg_trade": clean(self.avg_trade),
                "profit_factor": (clean(self.profit_factor)
                                  if not math.isinf(self.profit_factor) else None),
                "bar_share_pct": clean(self.bar_share_pct),
                "low_sample": self.low_sample}


@dataclass
class RegimeBreakdown:
    rows: list[RegimeRow] = field(default_factory=list)
    total_trades: int = 0
    notes: list[str] = field(default_factory=list)

    def dimension(self, name: str) -> list[RegimeRow]:
        return [r for r in self.rows if r.dimension == name]

    def to_dict(self) -> dict[str, Any]:
        return {"total_trades": self.total_trades,
                "rows": [r.to_dict() for r in self.rows],
                "notes": list(self.notes)}


_ORDER = {"volatility": ("low", "normal", "high", "warm-up"),
          "trend": ("above", "below", "warm-up")}


def regime_breakdown(bars: Any, trades: Sequence[Any], *,
                     fills_next_bar: bool = True) -> RegimeBreakdown:
    """Split ``trades`` by the regime at each trade's signal bar.

    ``fills_next_bar`` is True for the engine's default NEXT_OPEN execution,
    where the signal bar is ``entry_bar - 1``.  Pass False for THIS_CLOSE,
    where the order fills on the signal bar itself.  ``bars`` must be the
    series the trades were run on: a trade whose ``entry_bar`` is outside it
    raises rather than being quietly labelled against the wrong bar.
    """
    n_bars = len(bars.close)
    offset = 1 if fills_next_bar else 0
    for t in trades:
        if not 0 <= int(t.entry_bar) < n_bars:
            raise ValueError(
                f"A trade enters on bar {int(t.entry_bar)}, outside the "
                f"{n_bars:,} bars given. Pass the same bars the backtest ran on.")
    labels = {"volatility": volatility_regime(bars), "trend": trend_regime(bars)}
    out = RegimeBreakdown(total_trades=len(trades))
    for dim, lab in labels.items():
        labelled = lab[lab != ""]
        total_labelled = max(1, labelled.size)
        buckets: dict[str, list[float]] = {k: [] for k in _ORDER[dim]}
        for t in trades:
            signal = int(t.entry_bar) - offset
            if 0 <= signal < n_bars and lab[signal]:
                key = str(lab[signal])
            else:
                key = "warm-up"
            buckets[key].append(float(t.net_pnl))
        for key in _ORDER[dim]:
            pnl = np.asarray(buckets[key], dtype="float64")
            share = (float(np.sum(labelled == key)) / total_labelled * 100.0
                     if key != "warm-up" else math.nan)
            if key == "warm-up" and pnl.size == 0:
                continue
            out.rows.append(RegimeRow(
                dimension=dim, regime=key, trades=int(pnl.size),
                wins=int(np.sum(pnl > 0.0)), net_profit=float(pnl.sum()),
                gross_profit=float(pnl[pnl > 0.0].sum()),
                gross_loss=float(pnl[pnl < 0.0].sum()),
                bar_share_pct=share))
    out.notes.append(
        "Labels are read at the bar that raised each signal, never the fill "
        "bar. This is a description of trades already taken, not a filter "
        "test: to test 'trade only in this regime', filter the triggers and "
        "re-run on the research block against a control of the same "
        "selectivity.")
    thin = [f"{r.dimension} {r.regime}" for r in out.rows
            if r.low_sample and r.trades > 0]
    if thin:
        out.notes.append(
            f"Fewer than {MIN_BUCKET_TRADES} trades in: {', '.join(thin)}. "
            f"Differences there are mostly noise.")
    return out


def format_regimes(report: RegimeBreakdown, currency: str = "") -> str:
    unit = f", money in {currency}" if currency else ""
    lines = [f"Performance by market regime ({report.total_trades:,} trades{unit})"]
    for dim, title in (("volatility", "Volatility (ATR% rank, trailing 250 bars)"),
                       ("trend", "Trend (close vs 200-bar average)")):
        lines.append("")
        lines.append(f"  {title}")
        lines.append(f"    {'regime':<9}{'trades':>7}{'win %':>8}{'avg trade':>14}"
                     f"{'net':>16}{'PF':>7}{'% of bars':>11}")
        for r in report.dimension(dim):
            wr = f"{r.win_rate:.1f}" if math.isfinite(r.win_rate) else "-"
            avg = f"{r.avg_trade:,.2f}" if math.isfinite(r.avg_trade) else "-"
            pf = r.profit_factor
            pf_txt = ("inf" if math.isinf(pf) else f"{pf:.2f}"
                      if math.isfinite(pf) else "-")
            share = f"{r.bar_share_pct:.1f}" if math.isfinite(r.bar_share_pct) else "-"
            flag = "  LOW n" if r.low_sample and r.trades else ""
            lines.append(f"    {r.regime:<9}{r.trades:>7,}{wr:>8}{avg:>14}"
                         f"{r.net_profit:>16,.2f}{pf_txt:>7}{share:>11}{flag}")
    lines.append("")
    for note in report.notes:
        lines.append(f"  {note}")
    return "\n".join(lines)
