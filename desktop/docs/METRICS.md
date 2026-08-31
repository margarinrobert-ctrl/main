# Metric definitions

Every statistic this application reports, what it is computed from, and how to
read it. Anything the sample cannot support is labelled in the interface with a
**LOW n** or **N/A** badge and a reason; those labels are described at the end.

## Conventions

- Cash figures are in the account currency and are **net of commission, spread
  and slippage**. A trade's `net_pnl` already has its own costs taken out.
- Every `*_pct` value is a percentage, so `18.18` means 18.18%.
- `max_drawdown` and `max_drawdown_pct` are reported as **positive magnitudes**.
  The underlying curve arrays (`curves.drawdown`, `curves.drawdown_pct`) are
  signed and negative. The interface colours the magnitudes red.
- Sharpe, Sortino, volatility and the annual return figures are computed from
  **per-bar equity returns**, not from trade results.
- Everything is computed over the bars that were actually simulated, after the
  date range and warm-up were applied.

---

## Profit and loss

| Metric | Formula | Reading it |
|---|---|---|
| `net_profit` | ending equity − starting capital | What the account made. The only figure that compounds. |
| `gross_profit` | Σ net P&L of winning trades | Positive by construction. |
| `gross_loss` | Σ net P&L of losing trades | Negative by construction. |
| `return_pct` | `net_profit / starting_capital × 100` | Total return over the whole period, not annualised. |
| `starting_balance`, `ending_balance` | first and last equity | |
| `profit_factor` | `gross_profit / abs(gross_loss)` | Above 1 is profitable. `∞` when there were no losing trades, which is a fact about the sample, not the strategy. |
| `expectancy` | mean net P&L per trade | The number that actually compounds. A high win rate with a negative expectancy is a losing strategy. |
| `expectancy_r` | mean R-multiple per trade | Same idea, in units of risk rather than cash, so it is comparable across instruments. |
| `cagr` | `(ending/starting)^(1/years) − 1 × 100` | Compound annual growth. Meaningless over less than a year of data. |

## Trades

| Metric | Formula | Reading it |
|---|---|---|
| `total_trades` | count of closed trades | Scale-outs count as their own rows. |
| `winning_trades`, `losing_trades`, `breakeven_trades` | net P&L above, below, at zero | |
| `win_rate` | `winning / total × 100` | Meaningless without the payoff ratio. A 30% win rate with a 4:1 payoff is excellent. |
| `avg_trade` | mean net P&L | Identical to `expectancy`. |
| `avg_win`, `avg_loss` | mean of winners, mean of losers | |
| `payoff_ratio` | `avg_win / abs(avg_loss)` | How much bigger a winner is than a loser. |
| `largest_win`, `largest_loss` | extremes | If the largest win is a large fraction of net profit, one trade is carrying the result. |
| `max_consecutive_wins`, `max_consecutive_losses` | longest runs | The losing streak is the one that decides whether a strategy is tradeable by a human. |
| `avg_trade_duration_seconds`, `median_trade_duration_seconds` | mean and median holding time | The median is the honest one when a few trades ran for weeks. |
| `avg_bars_held` | mean bars from entry to exit | |
| `trades_per_year` | `total_trades / years covered` | Multiply by round-turn cost to see what the strategy pays to exist. |

## Risk

| Metric | Formula | Reading it |
|---|---|---|
| `max_drawdown` | largest peak-to-trough fall in **equity**, in cash | Includes open-position mark-to-market, not just closed trades. |
| `max_drawdown_pct` | that fall relative to the running peak | The number that decides whether you would still be trading. |
| `max_drawdown_duration_bars` | longest run of bars below a prior peak | Often more punishing than the depth. |
| `recovery_factor` | `net_profit / max_drawdown` | Profit earned per unit of pain. |
| `sharpe_ratio` | `mean(r − rf) / stdev(r) × √P` | `r` are per-bar equity returns, `rf` the per-period risk-free rate, `P` the annualisation factor below. |
| `sortino_ratio` | `mean(r − rf) / downside_deviation × √P` | Downside deviation is the root-mean-square of the *negative* excess returns over the **full** sample, which keeps it on Sharpe's scale. |
| `calmar_ratio` | `cagr / max_drawdown_pct` | Annual return per unit of worst drawdown. |
| `annual_volatility_pct` | `stdev(r) × √P × 100` | |
| `ulcer_index` | RMS of the percentage drawdown series | Accounts for how *long* the account was under water, not only how deep. |
| `sqn` | `√n × mean(R) / stdev(R)` | System quality. Needs R-multiples, so it needs stops. |
| `kelly_fraction` | `win_rate − (1 − win_rate) / payoff_ratio` | A theoretical upper bound on sizing, clamped to [−1, 1]. Treat it as a ceiling nobody should trade at, not a recommendation. |
| `exposure_pct` | bars with an open position / total bars × 100 | A strategy in the market 5% of the time carries very different risk from one always in. |

### The annualisation factor

Sharpe, Sortino and volatility are scaled by `√P`, where `P` is periods per
year. `P` is **derived from the data**, not assumed: the median gap between bars
gives the bar length, and the observed elapsed time divided by that gap gives
how many such bars a year of this instrument's calendar actually contains.

This matters. An equity index trades roughly 1,638 hourly bars a year, not the
8,766 hours a calendar year contains. Using the calendar figure would overstate
`√P` by more than a factor of two and inflate every Sharpe ratio to match.
`BacktestConfig.annualization_factor` overrides the derivation when you know
better.

## Costs

| Metric | Meaning |
|---|---|
| `total_commission` | commission charged across all trades, both sides |
| `total_slippage` | cash given up to slippage |
| `total_spread_cost` | cash given up to the bid/ask spread |
| `total_costs` | the three added together |
| `turnover` | Σ notional traded |

If total costs are a large fraction of gross profit, the strategy is a good idea
traded too often, and small errors in the cost model — all of which point the
same way — are enough to erase it.

## Long and short

`long_trades`, `short_trades`, `long_win_rate`, `short_win_rate`,
`long_net_profit`, `short_net_profit`: the same statistics split by direction.

Worth reading first on any sample from a rising market. A long-only edge on data
that went up may be the market, not the strategy.

## Excursion

| Metric | Meaning |
|---|---|
| `avg_mae` | mean maximum adverse excursion, in price points |
| `avg_mfe` | mean maximum favourable excursion, in price points |
| `avg_r_multiple`, `std_r_multiple` | mean and spread of trade results in units of initial risk |

Large MFE with small net profit means the exits are leaving money on the table.
MAE close to the stop distance on winners means the stop is barely wide enough
and small changes to it will change the result a lot.

## Exit reasons

`exit_reason_breakdown` gives count, net P&L, win rate and average P&L for each
way a position was closed: signal, stop loss, take profit, trailing stop,
partial target, time stop, session end, daily loss limit, margin call, reversal,
end of data.

**Read this before anything else.** It says where the money came from. A
one-R barrier strategy whose profit arrives at the *time stop* is a directional
bet with decoration on it. One whose profit arrives at the session-end exit is
an overnight carry trade. Neither is the thing the rule claims to be.

## Period returns

`best_month_pct`, `worst_month_pct`, `profitable_months_pct` are computed from
the **equity curve** at each month boundary in UTC, not by summing trades. A
position held across a month end contributes its mark-to-market to the month it
was open, which is what an account statement would have shown.

---

## Reliability labels

Alongside the metrics, `compute_metrics` returns `reliability` (metric → `ok` /
`low_sample` / `unavailable`) and `reliability_notes` (metric → plain-language
reason). The statistics panel renders these as badges and the HTML report
repeats them.

| Label | When | What it means |
|---|---|---|
| **LOW n** | fewer than 30 trades for a per-trade ratio; fewer than 100 bars or 20 trades for a risk-adjusted ratio | The figure moves by more than its own size when one trade changes. It is not a measurement. |
| **N/A** | a degenerate denominator — no losing trades, no drawdown, no defined risk per trade, a flat equity curve | The metric has no value here. It is not zero, and it is not good news. |

Nothing in this module raises on a degenerate input. A run with no trades, one
trade, no losers or a flat curve produces a complete dictionary, with the
figures that cannot mean anything labelled rather than quietly rendered as
`0.00`.

## What none of this measures

Every number here describes what a set of rules would have done on data you
already have. The gap between that and a live account is covered in
[BACKTEST_ASSUMPTIONS.md](BACKTEST_ASSUMPTIONS.md) — queue position, partial
fills, latency, liquidity, market impact, borrow, roll and dividend adjustment,
survivorship, and the researcher's own selection bias. The last one is the
largest and the only one no software can measure.
