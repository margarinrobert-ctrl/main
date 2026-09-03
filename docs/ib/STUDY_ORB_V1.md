# ORB v1 — a one-trade-per-session opening-range breakout, built to spec

`research/orb/`, `results/orb/`. NQ 1-minute, 765 RTH sessions, 2022-12-27 → 2025-12-11.

## Verdict

Implemented exactly as specified, causality-audited clean, and **it does not have an edge that
this sample can demonstrate.** Three things decide that, in order of how much they matter:

1. **The range/ATR gate keeps 11.1% of sessions**, so the whole rule fires **31 times in three
   years** (4.1% of sessions). Every downstream statistic rests on 15 / 5 / 11 trades.
2. **The result is the wrong shape.** Development **−$88.31/trade, PF 0.367, Sharpe −1.35**;
   validation **+$127.60, PF 4.15**; out-of-sample **+$25.39, PF 1.250**. It loses on the only
   block permitted to choose anything and makes money on the two reserved ones — the ninth time
   that shape has appeared on this branch, and it is a defect, not a result.
3. **It clears no control.** Against the same sessions, same side, same 1 ATR / 1R / 2R geometry
   and the same liquidation, entered at a **random** post-range bar: **p 0.478**. Against a
   coin-flip side on its own bars: **p 0.516**. Day-block bootstrap P(mean ≤ 0) = **0.629** whole
   sample, **0.379** out of sample.

What it *does* beat is always-long on the same bars (−$28.29/trade against −$13.14), so the trend
filter is not merely picking the up-drift — but that is the weakest of the three nulls.

**Costs are not the obstacle here**, which is unusual for this branch: doubling slippage costs
**$0.80–$1.83 a trade** because a 1 ATR stop on 5-minute NQ is ~28 points and the round turn is
1.72, i.e. **~6% of risk**.

## Setup, as implemented

| | |
| --- | --- |
| Market / bars | NQ, 5-minute trading bars, **exits walked on the 1-minute path** |
| Session | 09:30–16:00 New York; liquidation 15:55, filled at the **next 1-minute bar's open** |
| Opening range | 09:30–09:45, the first 15 completed minutes (3 trading bars); breakouts are not evaluated until 09:45 and a range bar can never signal |
| Higher timeframe | 15-minute. EMA(20)/EMA(50) read from the **last CLOSED** HTF bar; "rising" compares that bar to the one before it, both closed |
| ATR | Wilder(14) on completed bars, **frozen at the signal bar** |
| Volume | SMA(20) **shifted one bar** ("using bars before the current bar") |
| VWAP | session-anchored, through the current completed bar only |
| Gate | 0.3 ≤ range/ATR ≤ 1.5 · buffer max(0.05×ATR, 0.25) · volume > 1.2× prior SMA · one trade per session |
| Risk | 0.25% of **current** equity, stop 1.0×ATR, start $100,000, quantity floored to whole lots, skipped below 1 |
| Exits | 50% at +1R (floored to a whole lot), stop to breakeven, remainder at +2R, flatten at liquidation, no trail |
| Costs | per side: spread 0.25 + slippage 0.25 as a **price adjustment**, plus 0.36 points of fees = **0.86 points**; round turn 1.72; point value 2.0 (MNQ), tick 0.25 |
| Blocks | development first 50% of sessions, validation next 15%, **out-of-sample last 35%**. dev+val is exactly the 65% research block every other study on this branch uses and the OOS block is exactly its locked block, so no reserved data was re-cut |

### The intrabar question, answered rather than assumed

The spec allows a conservative assumption when a stop and a target fall in the same bar with no
intrabar data. **There is intrabar data here** — NQ is the one feed on this branch with 1-minute
bars — so the exits are walked minute by minute instead. Residual 1-minute bars where both a stop
and a target were touched: **0.00% of trades**. Flipping the assumption to target-first changes
the result by **exactly $0**. The conservative rule is documented and is doing nothing, which is
the only honest way to report it.

### Two ambiguities in the spec, and how they were resolved

- **The ATR's timeframe is never stated**, and `range_size / ATR` compares a 15-minute range to
  an ATR on whatever bar size you picked. It is the single most consequential unstated choice:

  | ATR timeframe | median range/ATR | share inside [0.3, 1.5] |
  | --- | ---: | ---: |
  | 5m (the literal reading — the trading bars) | 2.454 | **11.1%** |
  | 15m | 2.765 | 1.4% |
  | 30m | 2.382 | 8.9% |
  | 60m | 1.652 | 39.2% |
  | 240m | 0.744 | **95.3%** |

  The literal reading is used as the base and the timeframe is swept as its own axis. Note what
  the gate *is* under that reading: median range/ATR is 2.45, so keeping [0.3, 1.5] keeps the
  **quietest ninth of sessions** — it is a compression filter, and this branch has already found
  that compression setups select the bars where a fixed cost is largest relative to the stop.

- **"No trade has already been taken"** vs "skip the trade if quantity is below the minimum".
  Taken as: only the **first** qualifying signal of a session is ever considered, and if sizing
  rejects it the session has no trade. The looser reading — hunt for a second signal after a
  size rejection — can only flatter the rule, so it was not used. Cost: 8 later signals discarded,
  2 trades skipped for size.

## The filter chain

| | Sessions | |
| --- | ---: | ---: |
| RTH sessions | 765 | |
| … range/ATR inside [0.3, 1.5] | **85** | 11.1% |
| … producing at least one complete signal | 34 | 4.4% |
| … actually traded (first signal only) | **31** | 4.1% |

## Results

| Metric | Development | Validation | **Out-of-sample** |
| --- | ---: | ---: | ---: |
| Trades | 15 | 5 | **11** |
| % of sessions traded | 3.93 | 4.35 | 4.10 |
| Expectancy after costs | **−$88.31** | +$127.60 | **+$25.39** |
| Net | −$1,324.60 | +$638.00 | +$279.30 |
| Profit factor | **0.367** | 4.152 | **1.250** |
| Win rate | 40.0% | 80.0% | 45.5% |
| Average win | $127.70 | $210.10 | $279.20 |
| Average loss | −$232.30 | −$202.40 | −$186.10 |
| Max drawdown | −$1,604.40 | −$202.40 | −$389.00 |
| Sharpe (daily, annualised) | **−1.352** | 1.765 | 0.327 |
| Longest losing streak | 3 | 1 | 2 |
| Mean R | −0.391 | +0.674 | +0.155 |
| % long | 60.0 | 80.0 | 72.7 |

Whole sample: 31 trades, **−$13.14/trade, net −$407, PF 0.881**, final equity $99,593.
By year: **2023 −$976 (n 12), 2024 +$41 (n 9), 2025 +$528 (n 10)**.

**Exit mix** (development / validation / out-of-sample): stop 60.0 / 20.0 / 45.5%, target
6.7 / 40.0 / 27.3%, breakeven-stop 33.3 / 40.0 / 18.2%, liquidation 0 / 0 / 9.1%.

**Sizing reality:** median quantity 3 lots (min 1, max 6). On **12.9% of trades the 50% scale-out
rounds to zero lots**, so the whole position runs to +2R behind a breakeven stop. That is a real
consequence of a 0.25% risk budget on a $100k account with MNQ's $2 point value, not a modelling
shortcut — at this account size the "exit 50%" instruction is partly unavailable.

## The nulls

| Control | Median | Mean | 5–95% | Observed | p |
| --- | ---: | ---: | ---: | ---: | ---: |
| Random bar, same session / side / geometry | −$15.08 | −$14.52 | [−81.11, +54.75] | −$13.14 | **0.478** |
| Coin-flip side on the strategy's own bars | −$11.45 | −$11.31 | [−76.82, +54.37] | −$13.14 | **0.516** |
| Always long on the same bars | −$28.29 | −$28.29 | — | −$13.14 | 0.000 |

Day-block bootstrap: development P(mean ≤ 0) **0.962**, validation 0.075, out-of-sample **0.379**,
all 31 trades **0.629**.

With 11 out-of-sample trades the control distribution spans ±$135, so a non-rejection is a
statement about the sample size as much as about the rule. That is the point: **the range/ATR gate
makes the strategy untestable on three years of one instrument.**

## Parameter sensitivity — 4,320 configurations

Seven axes swept around the base: trading timeframe (1, 5), HTF (15, 30, 60), ATR timeframe
(5, 30, 60, 240), ratio band (four bands + off), volume multiple (1.0–1.4), buffer (0, 0.05, 0.10),
stop (0.75, 1.0, 1.5). 3,835 cells clear 20 in-sample trades.

**Grid shape first: only 24.2% of scorable cells are profitable in-sample**, median cell
−$11.46/trade. In-sample to out-of-sample expectancy correlation **Pearson +0.186 /
Spearman +0.228**.

Marginal average per axis, in-sample (the only block allowed to choose):

| Axis | Best setting | Mean IS expectancy | Worst setting | |
| --- | --- | ---: | --- | ---: |
| ATR timeframe | **240m** | +2.68 (55.9% profitable) | 60m | −19.17 (4.4%) |
| Ratio band | **0.3–1.5** (as specified) | −9.71 (34.7%) | 0.2–2.0 | −14.96 |
| Buffer | **0.10** | −9.28 (31.3%) | 0.05 (as specified) | −14.40 |
| Stop | **1.5 ATR** | −8.21 | 1.0 (as specified) | −15.29 |
| HTF | **15m** (as specified) | −7.24 (32.3%) | 30m | −20.44 |
| Volume multiple | 1.1 | −10.81 | 1.0 | −13.50 |
| Trading timeframe | 5m (as specified) | −10.09 | 1m | −14.79 |

**Every axis has a negative marginal except the 240-minute ATR** — and that one wins by making
the ratio gate inert (95.3% pass), i.e. by switching off the condition rather than tuning it. The
spec's own choices are the best setting on three axes (ratio band, HTF, trading timeframe) and the
worst on two (buffer, stop). The stop preference toward **wider** replicates a finding this branch
has now made on six separate families.

### The out-of-sample block was read twice, and both reads are reported

Multiplicity stated: 4,320 configurations scored in-sample, **two** read out of sample.

| Configuration | Dev | Valid | **OOS** |
| --- | ---: | ---: | ---: |
| Spec as written | −$88.31 (PF 0.367) | +$127.60 (4.15) | **+$25.39 (PF 1.250, n 11)** |
| Marginal consensus | +$6.22 (PF 1.088) | +$132.99 (4.26) | **−$26.50 (PF 0.711, n 23, losing streak 9)** |

The marginal consensus — 5m / HTF 15 / **ATR 240m** / ratio 0.3–1.5 / vol 1.1 / buffer 0.10 /
stop 1.5, chosen axis-by-axis on development+validation only — **turns positive in-sample and
negative out of sample**. Seventh re-optimiser on this branch to lose to the configuration it
started from.

The top ten in-sample cells are printed in `results/orb/sweep.txt` **because they are not the
answer**: mean in-sample expectancy +$55.17 against +$46.77 out of sample, on 20–22 in-sample
trades each. A 20-trade cell taken from the top of a 3,835-cell ranking is a draw, not a
configuration.

## Doubled slippage

| Configuration | Block | Expectancy | 2× slippage | Δ | PF | PF 2× |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Spec as written | development | −88.31 | −90.14 | −1.83 | 0.367 | 0.358 |
| | validation | +127.60 | +126.50 | −1.10 | 4.152 | 4.109 |
| | out-of-sample | +25.39 | +24.12 | −1.27 | 1.250 | 1.236 |
| Marginal consensus | development | +6.22 | +5.35 | −0.87 | 1.088 | 1.075 |
| | validation | +132.99 | +132.16 | −0.83 | 4.260 | 4.219 |
| | out-of-sample | −26.50 | −27.31 | −0.80 | 0.711 | 0.703 |

Nothing changes sign. **This is the first candidate on the branch in a long while where execution
is genuinely not the binding constraint** — the 1 ATR stop is wide enough that a fixed round turn
is ~6% of risk, against the 24% a 0.75 ATR scalping stop carries on 5-minute NQ.

## Causality audit

40 probe bars × 3 recomputed series (ATR, volume SMA, session VWAP), each rebuilt on history that
**ends** at the probe bar: **0 mismatches**. Opening-range bars measured at exactly 3.00 per
session and none is evaluable. The HTF EMA is sampled from the last bar whose close time is at or
before the trading bar's close, so the forming HTF bar is never read.

## What would move it

Not a parameter. The gate that makes this untestable is **range/ATR ≤ 1.5 measured against a
5-minute ATR**, which keeps 85 of 765 sessions. Either the ATR is meant to be a longer timeframe
(in which case say so — at 240 minutes the gate keeps 95% and is not a gate), or the band is
meant to sit around the actual median of 2.45. Both are spec decisions, not tuning, and both
should be made **before** looking at another block: the out-of-sample read has now been spent
twice here.

Beyond that: a second instrument. US100 and US30 exist on this branch at 15-minute resolution,
which cannot carry a 15-minute opening range or a 1-minute exit path — so ORB v1 as specified is
a **single-market** result, and 31 trades on one market is not a footing.
