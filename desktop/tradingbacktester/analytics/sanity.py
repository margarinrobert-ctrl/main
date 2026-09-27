"""Checks that a run is measuring the market it claims to be measuring.

A backtest multiplies every price move by the instrument's point value, so a
file loaded against the wrong instrument does not fail -- it produces numbers.
US30 prices read as AUDUSD are 45,000 "dollars per Australian dollar" at
100,000 USD per point: a 100-point stop becomes a ten-million-dollar loss, one
tick of slippage ten thousand dollars, and the account is gone in two trades.
Every figure is arithmetically right and none of them means anything.

The test here is deliberately coarse, so it cannot fire on a real instrument:
the price must be between 20 and 1,000,000,000 of the instrument's own ticks.
Every instrument this application ships sits between about 10,000 and
10,000,000 ticks (AUDUSD at 0.65 is 65,000; US30 at 45,000 is 450,000; BTC at
100,000 is 10,000,000).  A currency pair loaded with index prices is billions
of ticks; an index loaded with currency prices is under ten (US30's 0.1 tick
at 0.65 is 6.5).  A $1 stock at a 0.01 tick is 100, well inside.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

__all__ = ["MIN_TICKS", "MAX_TICKS", "price_scale_problem", "run_problems"]

MIN_TICKS = 20.0
MAX_TICKS = 1e9


def _fmt(x: float) -> str:
    if abs(x) >= 100:
        return f"{x:,.0f}"
    if abs(x) >= 1:
        return f"{x:,.2f}"
    return f"{x:.6g}"


def price_scale_problem(instrument: Any, price: float) -> str | None:
    """A sentence when ``price`` cannot be a price of ``instrument``, else None."""
    try:
        tick = float(getattr(instrument, "tick_size", 0.0) or 0.0)
        value = float(getattr(instrument, "point_value", 0.0) or 0.0)
        price = abs(float(price))
    except (TypeError, ValueError):
        return None
    if tick <= 0.0 or not math.isfinite(price) or price <= 0.0:
        return None
    ticks = price / tick
    if MIN_TICKS <= ticks <= MAX_TICKS:
        return None
    symbol = getattr(instrument, "symbol", "this instrument")
    currency = getattr(instrument, "currency", "") or ""
    unit = f"{currency} {_fmt(price * value)}".strip()
    return (f"These prices (around {_fmt(price)}) cannot be {symbol}: that is "
            f"{_fmt(ticks)} of its {tick:g} ticks, and one unit would be worth "
            f"{unit} at {_fmt(value)} per point. The data was loaded against "
            f"the wrong instrument, so every profit, loss and cost below is "
            f"multiplied by the wrong amount. Re-import it as the instrument "
            f"it really is.")


def run_problems(result: Any) -> list[str]:
    """Problems that make a finished run's numbers meaningless, worst first."""
    out: list[str] = []
    trades: Sequence[Any] = list(getattr(result, "trades", None) or [])
    bars = getattr(result, "bars", None)
    instrument = getattr(bars, "instrument", None)
    if instrument is not None:
        prices = None
        if trades:
            prices = np.array([float(t.entry_price) for t in trades], dtype="float64")
        elif bars is not None and len(getattr(bars, "close", ())):
            prices = np.asarray(bars.close, dtype="float64")
        if prices is not None and prices.size:
            problem = price_scale_problem(instrument, float(np.nanmedian(prices)))
            if problem:
                out.append(problem)
    for number, trade in enumerate(trades, start=1):
        after = float(getattr(trade, "equity_after", math.nan))
        if math.isfinite(after) and after <= 0.0:
            when = ""
            try:
                import pandas as pd
                when = " on " + pd.Timestamp(int(trade.exit_ts), tz="UTC").strftime(
                    "%Y-%m-%d")
            except Exception:                     # noqa: BLE001
                pass
            out.append(
                f"The account was wiped out by trade {number}{when}: equity "
                f"fell to {_fmt(after)}. A real account is closed out long "
                f"before that, so nothing after this point could have "
                f"happened.")
            break
    return out
