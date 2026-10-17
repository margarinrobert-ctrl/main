"""
Research: martingale / split-size position sizing on top of the best variant
(long-only contrarian W=1, from advanced_analysis.py).

Position-sizing schemes tested, all on the *same* entry/exit signals:

  fixed 1x        : baseline — every trade at 1x equity.
  martingale x2   : double size after each losing trade, reset to 1x on a win.
                    Caps at 4x and 8x (CFD leverage limits).
  anti-martingale : double after each *winning* trade, reset on loss (cap 4x).
  split-entry 1/3 : "splitted" averaging-down — enter 1/3 of full size on the
                    signal, add 1/3 more each day the open trade is underwater
                    (max 3 tranches). Same total cap as baseline (1x).
  split-entry 1/3 x2 : same, but tranches sized so a fully-loaded trade is 2x.

Each scheme is evaluated two ways:
  1. Historical replay on 2016-2025 (CAGR, Sharpe, maxDD, worst trade).
  2. Trade-level bootstrap Monte Carlo (10,000 resampled 9-year trade
     sequences) -> distribution of terminal wealth, max drawdown, and
     P(ruin), with ruin = equity down 50% or a margin call (equity <= 0
     intraday on levered size).

Sizing never changes the per-trade edge (EV multiplies, it doesn't improve);
what it changes is the *distribution* of outcomes. That's what this measures.
"""

import numpy as np
import pandas as pd

import backtest as bt

RNG = np.random.default_rng(7)
N_SIMS = 10_000
RUIN_DD = -0.50            # "ruin" = losing half the account at any point

# ---------------------------------------------------------------------------
# Rebuild the base strategy: long-only contrarian W=1, daily net returns
# ---------------------------------------------------------------------------

def base_strategy():
    daily = bt.load_daily_semivariances()
    pos = (bt.sam(daily, 1) < 0).astype(float)
    res = bt.run(daily, pos.fillna(0.0))
    return daily, res


def trade_table(res: pd.DataFrame) -> pd.DataFrame:
    """One row per long spell: simple net return of the trade and its
    day-by-day net log returns (needed for split-entry sizing)."""
    p = res["pos"]
    tid = (p != p.shift(1)).cumsum()
    rows = []
    for _, grp in res[p != 0].groupby(tid[p != 0]):
        rows.append({
            "ret": np.exp(grp["net"].sum()) - 1,
            "daily": grp["net"].to_numpy(),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Sizing schemes -> per-trade size multiplier sequences
# ---------------------------------------------------------------------------

def martingale_sizes(trade_rets: np.ndarray, mult: float, cap: float,
                     anti: bool = False) -> np.ndarray:
    sizes = np.empty(len(trade_rets))
    m = 1.0
    for i, r in enumerate(trade_rets):
        sizes[i] = m
        won = r > 0
        step_up = (won if anti else not won)
        m = min(m * mult, cap) if step_up else 1.0
    return sizes


def split_entry_trade_returns(trades: pd.DataFrame, full_size: float) -> np.ndarray:
    """Average-down tranches: day 1 at full_size/3; add a tranche at the next
    day's start whenever the running trade P&L is negative (max 3)."""
    out = np.empty(len(trades))
    for i, daily in enumerate(trades["daily"]):
        tranche = full_size / 3
        size, pnl, equity_mult = tranche, 0.0, 1.0
        for j, r in enumerate(daily):
            day_ret = np.exp(r) - 1        # unsized net day return
            equity_mult *= 1 + size * day_ret
            pnl += size * day_ret
            if j < len(daily) - 1 and pnl < 0 and size < full_size - 1e-9:
                size += tranche
        out[i] = equity_mult - 1
    return out


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def replay(sized_rets: np.ndarray, years: float) -> dict:
    """CAGR over calendar years of the sample, not just days in the market."""
    equity = np.cumprod(1 + sized_rets)
    peak = np.maximum.accumulate(equity)
    max_dd = (equity / peak - 1).min()
    log_r = np.log1p(sized_rets)
    return {
        "CAGR_%": 100 * (equity[-1] ** (1 / years) - 1),
        "sharpe~": log_r.mean() / log_r.std() * np.sqrt(len(sized_rets) / years),
        "max_dd_%": 100 * max_dd,
        "worst_trade_%": 100 * sized_rets.min(),
        "terminal_x": equity[-1],
    }


def monte_carlo(trade_rets: np.ndarray, sizer) -> dict:
    """Bootstrap the trade sequence, re-apply the sizing state machine on each
    resampled path (sizing depends on the win/loss sequence, so it must be
    recomputed per path)."""
    n = len(trade_rets)
    idx = RNG.integers(0, n, size=(N_SIMS, n))
    paths = trade_rets[idx]
    term = np.empty(N_SIMS)
    ruin = np.zeros(N_SIMS, dtype=bool)
    max_dd = np.empty(N_SIMS)
    for s in range(N_SIMS):
        sizes = sizer(paths[s])
        eq = np.cumprod(1 + sizes * paths[s])
        peak = np.maximum.accumulate(eq)
        dd = eq / peak - 1
        max_dd[s] = dd.min()
        ruin[s] = (dd.min() <= RUIN_DD) or (eq.min() <= 0)
        term[s] = eq[-1]
    return {
        "median_terminal_x": np.median(term),
        "p5_terminal_x": np.percentile(term, 5),
        "median_max_dd_%": 100 * np.median(max_dd),
        "p5_max_dd_%": 100 * np.percentile(max_dd, 5),
        "P_ruin_%": 100 * ruin.mean(),
    }


def main() -> None:
    daily, res = base_strategy()
    trades = trade_table(res)
    tr = trades["ret"].to_numpy()
    years = len(daily) / bt.TRADING_DAYS
    print(f"base: long-only contrarian W=1 — {len(tr)} trades, "
          f"EV {100*tr.mean():.3f}%/trade, win rate {100*(tr>0).mean():.1f}%\n")

    schemes = {
        "fixed 1x":            lambda t: np.ones(len(t)),
        "martingale x2 cap4":  lambda t: martingale_sizes(t, 2.0, 4.0),
        "martingale x2 cap8":  lambda t: martingale_sizes(t, 2.0, 8.0),
        "anti-mart x2 cap4":   lambda t: martingale_sizes(t, 2.0, 4.0, anti=True),
    }

    hist_rows, mc_rows = {}, {}
    for name, sizer in schemes.items():
        sized = sizer(tr) * tr
        hist_rows[name] = replay(sized, years)
        mc_rows[name] = monte_carlo(tr, sizer)

    # split-entry schemes resize *within* the trade, so their per-trade returns
    # are recomputed from daily paths, then treated as fixed-1x sequences.
    for name, full in [("split-entry 1/3 (1x)", 1.0), ("split-entry 1/3 (2x)", 2.0)]:
        se = split_entry_trade_returns(trades, full)
        hist_rows[name] = replay(se, years)
        mc_rows[name] = monte_carlo(se, lambda t: np.ones(len(t)))
        print(f"{name}: EV {100*se.mean():.3f}%/trade vs fixed {100*tr.mean():.3f}%"
              f" | avg deployed size {np.mean([min(1, len(d)) for d in trades['daily']]):.2f}")

    hist = pd.DataFrame(hist_rows).T.round(2)
    mc = pd.DataFrame(mc_rows).T.round(2)
    print("\n=== Historical replay 2016-2025 ===")
    print(hist.to_string())
    print("\n=== Monte Carlo, 10,000 bootstrapped 9-year trade sequences ===")
    print(f"(ruin = {abs(RUIN_DD):.0%} account drawdown at any point)")
    print(mc.to_string())

    out = bt.OUT / "martingale_comparison.csv"
    pd.concat([hist, mc], axis=1).to_csv(out)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
