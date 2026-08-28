# The golden cross, against benchmarks

ChartArt's "Golden Cross, SMA 200 Long Only" (Pine v2, June 2016) came in as a *is this rigged?*
question. It is not. This is what it is instead.

Reproduce: `python3 research/goldencross.py` (calibration), or
`python3 research/goldencross.py --csv data/NQ_1m.csv --grid` (a real file).

## 1. The code is honest

Every mechanism by which a published Pine strategy inflates its own equity curve is absent:

* no `security()`, so no `lookahead_on` higher-timeframe leak
* `crossover`/`crossunder` on two SMAs of `close` are causal; the signal is read at a bar close and
  `strategy.entry` fills at the **next bar's open**
* no `calc_on_order_fills`, no `process_orders_on_close`, no negative plot offsets
* the bar colouring flickers on the forming bar, but `barcolor` touches no orders

Two real defects, neither of them cheating:

* **no costs declared.** The `strategy()` call sets no `commission_type` or `slippage`, so the
  tester charges whatever is in Properties, which defaults to zero.
* **no `barstate.isconfirmed` on the entry.** Harmless at the default `calc_on_every_tick=false`,
  but Properties can turn that on and the backtest stops matching live behaviour — the same trap
  recorded in `CLAUDE.md` under Pine.

It is also **Pine v2**: already-published v2 scripts still run, but it cannot be saved as new
without conversion.

## 2. What the benchmarks say

The real objection is not the code, it is the comparison. A 50/200 cross is long-only and holds for
months, so on a market that rose it is paid for existing (RESEARCH_PROTOCOL.md §4c). `data/NQ_1m.csv`
is git-ignored and absent from this container and the network policy blocks market-data hosts, so
these are **simulated** bars — geometric Brownian motion, no signal in the series by construction.
That makes them a Stage 0 null calibration (§2), not a backtest: the question they answer is what
the rule earns when there is provably nothing to find.

200 paths x 3,000 daily bars (11.9y), 2.5 bps per side:

| | drift 8%/yr, vol 18% | driftless, vol 18% |
| --- | --- | --- |
| golden cross 50/200 | **+42.5%** (Sharpe 0.30) | **-12.4%** (Sharpe -0.06) |
| buy and hold | +94.8% (Sharpe 0.40) | -24.8% (Sharpe -0.05) |
| exposure-matched control | +38.9% | -12.3% |
| time in market | 52.6% | 40.5% |
| closed trades | 8 | 9 |
| win rate | 44.4% | 30.0% |
| beat buy and hold | 19% of paths | 64% of paths |
| control percentile | **52.2** (>95 on 1% of paths) | 42.5 (>95 on 0%) |

Read the last row first. The **exposure-matched control** — random long entries with the same trade
count and the same holding-period distribution — earns +38.9% against the rule's +42.5%, putting the
rule at the **52nd percentile of its own null**. On a series with no predictability whatsoever, the
crossover lands exactly where a coin flip lands. Its entire +42.5% is drift collected over 52.6% of
the sample; none of it is the signal.

The driftless column is the same statement from the other side: strip the drift and the rule loses
money, at a 30% win rate, while still beating buy-and-hold on 64% of paths. **Beating buy-and-hold is
not evidence of an edge** — a strategy that is flat half the time beats it automatically whenever the
market falls. That is the number the Strategy Tester prints, and it is the wrong one.

Note the median trade count: **8 over twelve years**. Whatever CAGR, profit factor or drawdown the
tester reports is eight observations. Check "Total Closed Trades" before anything else on that tab.

## 3. The neighbourhood is flat

50/200 is one cell of a grid, and 50/200 is famous, which is the definition of a selected cell.
Median return minus each pair's *own* matched control, 60 paths, drifting series:

| fast \ slow | 100 | 150 | 200 | 250 | 300 |
| --- | --- | --- | --- | --- | --- |
| 20 | -6.2 | +7.7 | -2.5 | +6.2 | +10.0 |
| 30 | -14.0 | -5.9 | -2.0 | -1.2 | +5.5 |
| 50 | -9.2 | -6.5 | **-1.4** | -0.7 | +1.6 |
| 80 | -10.7 | -4.3 | -7.5 | -0.3 | +2.4 |
| 100 | — | -4.7 | +0.9 | -2.6 | +8.7 |

Control percentiles across all 24 pairs run 37.8 to 61.2, scattered around 50 with no structure —
noise, correctly identified as noise. This is the calibration: on data with no edge the harness
finds no edge anywhere in the neighbourhood, at any parameter pair, which is what makes a *positive*
reading on a real file worth anything.

## 4. What ships

* `research/goldencross.py` — the harness. Mirrors the Pine exactly (confirmed close, next-open fill,
  both sides), charges costs per side, and reports buy-and-hold, the exposure-matched control and the
  parameter neighbourhood. Point `--csv` at a canonical bar file to run it on real prices.
* `GoldenCross.pine` — a v5 port. Same signal logic, unchanged. Adds declared commission and
  slippage, `barstate.isconfirmed` on both the entry and the exit, and an on-chart table showing
  closed trades, time in market, buy-and-hold over the same span, the excess, and a `TOO SMALL` flag
  under 30 trades. Lints clean under `research/pine_lint.check`.

## 5. Verdict

Honest code, honest execution model, no lookahead. Also no demonstrated edge: on a null series it
sits at the 52nd percentile of an exposure-matched control, and the published parameter pair is the
flattest cell in a flat neighbourhood. The danger in the original is not that it is rigged, it is
that a zero-cost tester run over eight trades produces a curve that looks like a finding.

**Open question this container cannot close.** These numbers are calibration on simulated bars.
Running `--csv` on the real 1-minute file would say whether NQ's actual path moves the control
percentile off 50 — the prior from every other study on this branch is that it does not, but that is
a prior, not a result.
