"""
VectorBT backtest wrapper for the IFVG + Liquidity Sweep model.

``run_backtest`` feeds the strategy's explicit entry/exit signals and fill prices
into ``vbt.Portfolio.from_signals`` with NQ futures economics (point value $20,
$2.04/order commission, 2-tick slippage modelled on the fill price), then returns
the portfolio plus a compact stats dict.

Because the signal generator already resolves every exit (stop / TP / IFVG-close /
EOD) to an exact bar and price, VectorBT is used as the accounting + metrics engine
rather than re-deriving stops. We pass ``price`` so fills land on the computed
levels, and size in whole contracts via ``vbt`` cash sizing scaled by point value.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import vectorbt as vbt

from .strategy import Params, Signals, generate, POINT_VALUE, MINTICK


def _price_series(df: pd.DataFrame, sig: Signals) -> pd.Series:
    """Fill price at each bar: entry price on entry bars, exit price on exit bars,
    else the close. VectorBT executes signals at this price."""
    px = df["close"].to_numpy(float).copy()
    ent = ~np.isnan(sig.entry_price)
    ext = ~np.isnan(sig.exit_price)
    px[ent] = sig.entry_price[ent]
    px[ext] = sig.exit_price[ext]
    return pd.Series(px, index=df.index)


def run_backtest(
    df: pd.DataFrame,
    p: Params | None = None,
    init_cash: float = 100_000.0,
    contracts: int = 1,
    commission_per_order: float = 2.04,
    slippage_ticks: float = 2.0,
):
    """Run one backtest. Returns (portfolio, signals, stats_dict)."""
    p = p or Params()
    sig = generate(df, p)

    price = _price_series(df, sig)
    # Trade $1 of "asset" per point => set size so 1 unit == 1 contract of $20/pt.
    # vectorbt works in asset units priced at `price`; to get NQ economics we treat
    # each contract as POINT_VALUE units of a $1 instrument is awkward, so instead we
    # rescale: run vbt on the raw price with size = contracts, then multiply the
    # resulting PnL by POINT_VALUE via a post-hoc scale on cash flows. Simpler &
    # exact: convert price to "dollar price" = price * POINT_VALUE so 1 unit == 1 NQ.
    dollar_price = price * POINT_VALUE
    slip = (slippage_ticks * MINTICK * POINT_VALUE) / dollar_price  # fractional slippage

    pf = vbt.Portfolio.from_signals(
        close=dollar_price,
        entries=sig.long_entries,
        exits=sig.long_exits,
        short_entries=sig.short_entries,
        short_exits=sig.short_exits,
        price=dollar_price,
        size=contracts,
        size_type="amount",
        init_cash=init_cash,
        fees=0.0,
        fixed_fees=commission_per_order,
        slippage=slip,
        freq="1min",
        accumulate=False,
    )

    stats = _compact_stats(pf, sig)
    return pf, sig, stats


def _compact_stats(pf, sig: Signals) -> dict:
    # vectorbt 1.0 exposes these as methods.
    trades = pf.trades
    n_trades = int(trades.count())
    out = {
        "total_return_pct": float(pf.total_return() * 100),
        "final_value": float(pf.value().iloc[-1]),
        "max_drawdown_pct": float(pf.max_drawdown() * 100),
        "n_trades": n_trades,
    }
    try:
        out["sharpe"] = float(pf.sharpe_ratio())
    except Exception:
        out["sharpe"] = float("nan")
    if n_trades > 0:
        out["win_rate_pct"] = float(trades.win_rate() * 100)
        out["profit_factor"] = float(trades.profit_factor())
        out["avg_pnl"] = float(trades.pnl.mean())
        out["expectancy"] = float(trades.expectancy())
    else:
        out.update(win_rate_pct=float("nan"), profit_factor=float("nan"),
                   avg_pnl=float("nan"), expectancy=float("nan"))
    return out


def format_stats(stats: dict, source: str = "", params: Params | None = None) -> str:
    lines = ["=" * 60, "IFVG + Liquidity Sweep | VectorBT backtest", "=" * 60]
    if source:
        lines.append(f"data source     : {source}")
    lines += [
        f"trades          : {stats['n_trades']}",
        f"total return    : {stats['total_return_pct']:+.2f} %",
        f"final value     : ${stats['final_value']:,.0f}",
        f"max drawdown    : {stats['max_drawdown_pct']:.2f} %",
        f"sharpe (1min)   : {stats['sharpe']:.2f}",
        f"win rate        : {stats['win_rate_pct']:.1f} %",
        f"profit factor   : {stats['profit_factor']:.2f}",
        f"avg trade PnL   : ${stats['avg_pnl']:,.2f}",
        f"expectancy      : ${stats['expectancy']:,.2f}",
        "=" * 60,
    ]
    return "\n".join(lines)
