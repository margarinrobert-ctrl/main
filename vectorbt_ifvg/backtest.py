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


def run_backtest(
    df: pd.DataFrame,
    p: Params | None = None,
    init_cash: float = 100_000.0,
    contracts: float = 1.0,
    commission_per_order: float = 2.04,
    slippage_ticks: float = 2.0,
):
    """Run one backtest. Returns (portfolio, signals, stats_dict).

    The strategy emits explicit signed orders (entry, the TP1 partial, and the
    runner exit), so we drive ``vbt.Portfolio.from_orders`` directly. To get NQ
    economics we run in "dollar price" units (price x $20/pt) so 1 order unit == 1
    contract; slippage is modelled as a fractional move on the fill price.
    """
    p = p or Params()
    sig = generate(df, p, contracts=contracts)

    close = pd.Series(df["close"].to_numpy(float) * POINT_VALUE, index=df.index)
    # Order fill price: use the per-order price where present, else the close.
    fill = np.where(np.isnan(sig.order_price), df["close"].to_numpy(float),
                    sig.order_price) * POINT_VALUE
    fill = pd.Series(fill, index=df.index)
    size = pd.Series(sig.order_size, index=df.index)  # NaN where no order

    slip = (slippage_ticks * MINTICK * POINT_VALUE) / fill  # fractional slippage

    # NQ's notional (~$400k/contract) dwarfs the $100k account, and this vbt build has
    # no leverage/margin param, so a literal cash account would shrink every order to
    # fit. We instead fund the simulator with ample headroom (futures PnL is cash-
    # additive) and recenter all % metrics onto the intended capital afterwards.
    headroom = max(init_cash, float(np.nanmax(np.abs(size)) if np.isfinite(
        np.nanmax(np.abs(size))) else 1.0) * float(fill.max()) * 4.0)

    pf = vbt.Portfolio.from_orders(
        close=close,
        size=size,
        price=fill,
        size_type="amount",
        direction="both",
        init_cash=headroom,
        fees=0.0,
        fixed_fees=commission_per_order,
        slippage=slip,
        freq="1min",
    )

    cost_per_order = commission_per_order + slippage_ticks * MINTICK * POINT_VALUE
    stats = _compact_stats(pf, sig, init_cash=init_cash, vbt_cash=headroom,
                           cost_per_order=cost_per_order)
    return pf, sig, stats


def _compact_stats(pf, sig: Signals, init_cash: float, vbt_cash: float,
                   cost_per_order: float) -> dict:
    # Recenter the (over-funded) equity curve onto the intended capital. Futures PnL
    # is cash-additive, so real_equity(t) = init_cash + (vbt_value(t) - vbt_cash).
    real_equity = init_cash + (pf.value() - vbt_cash)
    pnl = float(real_equity.iloc[-1] - init_cash)
    rets = real_equity.pct_change().fillna(0.0)
    run_max = real_equity.cummax()
    dd = (real_equity - run_max) / run_max
    # Annualise the 1-minute Sharpe over a 252*390 trading-minute year.
    ann = np.sqrt(252 * 390)
    sharpe = float(rets.mean() / rets.std() * ann) if rets.std() > 0 else float("nan")

    # POSITION-LEVEL trade stats (net of costs). vbt's own trade records split each
    # partial-fill leg into its own "trade", which distorts win rate / profit factor;
    # the strategy thinks in whole positions, so report those.
    net = np.array([t["pnl"] - t["n_orders"] * cost_per_order for t in sig.trades])
    n_trades = int(len(net))
    out = {
        "total_return_pct": float(pnl / init_cash * 100),
        "final_value": float(real_equity.iloc[-1]),
        "max_drawdown_pct": float(dd.min() * 100),
        "n_trades": n_trades,
        "sharpe": sharpe,
    }
    if n_trades > 0:
        wins = net[net > 0]
        losses = net[net < 0]
        gross_w = float(wins.sum())
        gross_l = float(-losses.sum())
        out["win_rate_pct"] = float(len(wins) / n_trades * 100)
        out["profit_factor"] = float(gross_w / gross_l) if gross_l > 0 else float("inf")
        out["avg_pnl"] = float(net.mean())
        out["expectancy"] = float(net.mean())
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
