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

---

# Addendum 1: three more feeds

`research/orb/orb_feeds.py`, `run_multi.py`; `results/orb/multi.txt`.

All three uploads verify against `research/datasets.py`: `US100_LONG_15m` (sha256
**c449dddfbc06a943**) and `US30_LONG_15m` (**24dcf2e1c7ba398f**) are byte-identical to the studied
copies, and the RTF unwraps to exactly the recorded **48,937 rows, 2024-08-19 01:45 → 2026-08-26
17:30 New York** (its recorded byte size is of the derivative and is a hint, not an identity, as
the registry itself states). Nothing new was cut.

| Feed | Bars | Span | RTH sessions | Volume |
| --- | ---: | --- | ---: | --- |
| NQ | 70,685 @15m | 2022-12 → 2025-12 | 765 | true contract volume |
| US100 | 206,703 | 2016-11 → 2025-10 | 2,277 | **tick volume — a proxy** |
| US30 | 193,942 | 2016-10 → 2025-07 | 2,246 | **tick volume — a proxy** |
| US30_ISO | 48,937 | 2024-08 → 2026-08 | 522 | second provider |

## The gate was written for a 15-minute chart

This is the finding, and it took a second timeframe to see:

| Market | Trading bars | Range bars | Median range/ATR | In [0.3, 1.5] |
| --- | --- | ---: | ---: | ---: |
| NQ | 15m | **1** | 1.554 | **45.9%** |
| US100 | 15m | 1 | 1.611 | 41.4% |
| US30 | 15m | 1 | 1.542 | 47.2% |
| US30_ISO | 15m | 1 | 1.878 | 29.7% |
| NQ | 5m | 3 | 2.454 | **11.1%** |

**When the trading bar IS the opening range, `range_size / ATR(14)` is ~1 by construction** — the
range is one bar and ATR(14) is the average size of one bar. `[0.3, 1.5]` is then a band around 1
and passes 30–47% of sessions. On 5-minute bars the identical band keeps the quietest ninth. The
spec's numbers are internally consistent only on a 15-minute chart, and the v1 result above was
measured on the reading that starves it.

## Costs, in the only cross-market unit

| Market | Cost/side | Round turn | Median ATR | **RT / 1 ATR stop** |
| --- | ---: | ---: | ---: | ---: |
| NQ | 0.86 | 1.72 | 43.0 | 4.0% |
| US100 | 0.75 | 1.50 | 31.9 | 4.7% |
| US30 | 1.50 | 3.00 | 55.7 | 5.4% |
| US30_ISO | 1.50 | 3.00 | 80.6 | 3.7% |

3.7–5.4% of risk everywhere. Doubling slippage moves expectancy by **$0.81–$5.14 a trade** and
flips no sign on any of the ten blocks. Execution is not what is wrong with this strategy.

## ORB v1 unfiltered, 15-minute bars, HTF 60m

| Market | Block | n | Expectancy | PF | Sharpe |
| --- | --- | ---: | ---: | ---: | ---: |
| NQ | development | 68 | −$37.67 | 0.690 | −1.136 |
| | validation | 18 | +$12.04 | 1.158 | 0.412 |
| | **out-of-sample** | 48 | −$2.17 | 0.976 | −0.071 |
| US100 | research | 168 | +$0.28 | 1.002 | 0.006 |
| | validation | 60 | +$31.57 | 1.312 | 0.675 |
| | **test** | 55 | −$13.21 | 0.888 | −0.302 |
| US30 | research | 168 | +$30.05 | 1.291 | 0.663 |
| | validation | 56 | −$33.63 | 0.699 | −0.828 |
| | **test** | 40 | −$55.87 | 0.537 | −1.370 |
| US30_ISO | reserved (2nd provider) | 43 | −$48.62 | 0.535 | −1.203 |

724 trades. **Matched control (same sessions, same side, same geometry, random post-range entry):
1 of 10 blocks clears at p ≤ 0.05 — US30 research, p 0.007 — and that is the block that would
choose.** US30's own validation and test then read **p 0.983 and p 0.973**, and the independent
second provider reads **p 0.990**. Every other block: p 0.193–0.950.

The intrabar assumption is 0.0–0.7% of trades on every feed and worth **$0** on all four, so the
conservative rule is documented and does nothing — but note that is luck of these barriers, not a
property of 15-minute data.

---

# Addendum 2: the market-regime filter

`research/orb/orb_regime.py`, `run_regime.py`; `results/orb/regime.txt`, `regime_grid.parquet`.

Wilder ADX(14)/+DI/−DI implemented directly rather than imported (this branch has been bitten by
`ta.dmi` returning `[+DI, −DI, ADX]` and a caller reading the first element as ADX).
`normalized_slope = (EMA20 − EMA20[−3]) / (3 × ATR)`. The hysteresis is a **sequential state
machine** over completed 15-minute bars — a trend may only *begin* at ADX ≥ entry and survives to
ADX < exit — so it cannot be written as a boolean mask. The state is frozen on the last
15-minute bar whose close is at or before the trading bar's close and forward-filled; the forming
bar is never read.

## The regime is remarkably stable across four feeds — and the hysteresis is nearly inert

| Market | BULL | BEAR | CHOP | Median ADX | CHOP with entry = exit = 25 | Bars reclassified |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ | 17.5% | 15.1% | 67.4% | 24.1 | 68.2% | **0.8%** |
| US100 | 18.2% | 15.1% | 66.7% | 24.2 | 67.5% | 0.8% |
| US30 | 17.7% | 14.6% | 67.7% | 23.8 | 68.6% | 0.9% |
| US30_ISO | 17.0% | 15.4% | 67.6% | 23.9 | 68.4% | 0.8% |

Collapsing the state machine to a flat `ADX ≥ 25` moves **0.8–0.9%** of bars. ADX(14) on
15-minute bars rarely lingers in the 20–25 band, so **the hysteresis is very nearly inert**. The
sensitivity table confirms it from the other side: the `adx_exit` axis is flat to the cent
(+10.68 / +10.59 / +10.59 at 15 / 18 / 20, and identical per market on NQ and US100).

## Performance by regime, and what the filter removes

Every unfiltered ORB v1 trade, tagged by the regime frozen at its own signal bar:

| Market | BULL | BEAR | CHOP | **KEPT** | **REMOVED** |
| --- | ---: | ---: | ---: | ---: | ---: |
| NQ | −$2.14 (n 37, PF 0.98) | −$83.10 (24, 0.38) | −$5.15 (73, 0.95) | −$33.99 (61, 0.69) | −$5.15 (73, 0.95) |
| US100 | **+$56.15** (70, 1.61) | −$3.11 (45, 0.97) | −$15.33 (168, 0.88) | **+$32.96** (115, 1.34) | −$15.33 (168, 0.88) |
| US30 | +$22.53 (61, 1.23) | +$20.95 (50, 1.21) | −$9.75 (153, 0.92) | **+$21.81** (111, 1.22) | −$9.75 (153, 0.92) |
| US30_ISO | +$8.14 (10, 1.14) | −$68.58 (9, 0.29) | −$64.79 (24, 0.49) | −$28.20 (19, 0.63) | −$64.79 (24, 0.49) |

**The removed set loses money on all four feeds** (−$5.15, −$15.33, −$9.75, −$64.79; PF 0.49–0.95),
and the filter removes **54–58%** of trades. That is the most consistent single result in this
whole study — 4 of 4 with the same sign, on feeds that include an independent second provider.
BULL is the best bucket on three of four. BEAR is where it falls apart: it is the *worst* bucket
on NQ (−$83.10, PF 0.377) and on US30_ISO (−$68.58, PF 0.291) while being fine on US30.

## Filtered vs unfiltered, every block

| Market | Block | No filter | Regime | Δ |
| --- | --- | ---: | ---: | ---: |
| NQ | development | −$37.67 | −$77.82 | −40.15 |
| | validation | +$12.04 | +$59.94 | +47.90 |
| | **out-of-sample** | −$2.17 | **−$1.69** | +0.48 |
| US100 | research | +$0.28 | +$38.35 | +38.07 |
| | validation | +$31.57 | +$24.94 | −6.63 |
| | **test** | −$13.21 | **+$5.22** | **+18.43** |
| US30 | research | +$30.05 | +$51.85 | +21.80 |
| | validation | −$33.63 | +$19.75 | +53.38 |
| | **test** | −$55.87 | **−$94.38** | **−38.51** |
| US30_ISO | reserved | −$48.62 | **−$34.79** | +13.83 |

**Two of the four reserved blocks improve and two do not**, and the one that gets substantially
worse (US30 test, PF 0.537 → 0.332, Sharpe −1.370 → −1.619) is the market whose research block
looked best. Only US100's test block crosses zero (PF 1.047, Sharpe 0.081, n 26). Drawdown falls
on every feed, but so does the trade count — 54–58% fewer trades buys a smaller drawdown by
construction, which this branch has recorded before.

## Threshold sensitivity — 324 cells, scored in-sample only

ADX entry {20, 25, 30} × ADX exit {15, 18, 20} × slope {0.025, 0.05, 0.10} × EMA distance
{0.15, 0.25, 0.40}, with exit ≤ entry enforced. 243 scorable on the three selectable feeds
(US30_ISO has one reserved block and never enters selection).

**66.7% profitable in-sample — and in-sample to out-of-sample expectancy correlation is
Pearson −0.633 / Spearman −0.656.** When that number is negative, selecting on the in-sample
block is *worse* than not selecting.

| Axis | Setting | Mean IS expectancy | NQ | US100 | US30 |
| --- | --- | ---: | ---: | ---: | ---: |
| ADX entry | 20 / 25 / 30 | +13.23 / +10.89 / +7.75 | −29.6 / −47.7 / −67.1 | +32.4 / +33.3 / +42.5 | +36.9 / +47.0 / +47.8 |
| ADX exit | 15 / 18 / 20 | +10.68 / +10.59 / +10.59 | −48.1 / −48.1 / −48.1 | +36.1 / +36.1 / +36.1 | +44.1 / +43.8 / +43.8 |
| Slope | 0.025 / 0.05 / 0.10 | +8.60 / +9.29 / +13.98 | −50.9 / −48.8 / −44.6 | +33.9 / +37.3 / +37.0 | +42.8 / +39.4 / +49.5 |
| EMA distance | 0.15 / 0.25 / 0.40 | +9.95 / +9.79 / +12.13 | −49.7 / −50.0 / −44.5 | +36.7 / +35.1 / +36.4 | +42.9 / +44.3 / +44.6 |

**The share profitable is exactly 66.7% at every setting of every axis**, because two of the three
markets are profitable in-sample regardless of the thresholds. The spread *across markets*
(−48 to +44) is an order of magnitude larger than the spread *across thresholds within a market*
(≤ 6 on US100, ≤ 10 on US30). **The market decides, not the threshold.** And ADX entry is the one
axis with a real gradient — it runs the opposite way on NQ (looser is better) from US100 and US30
(tighter is better), which is what an axis with no transferable information looks like.

## The out-of-sample read — two threshold sets, stated

Multiplicity: 243 in-sample cells scored; **two** threshold sets read out of sample.
Marginal consensus = ADX entry 20, exit 15, slope 0.10, distance 0.40.

| Market | Block | Base (as specified) | Marginal consensus |
| --- | --- | ---: | ---: |
| NQ | out-of-sample | −$1.69 (PF 0.981) | **+$32.84 (PF 1.432)** |
| US100 | test | +$5.22 (1.047) | +$0.39 (1.004) |
| US30 | test | −$94.38 (0.332) | −$101.62 (0.358) |
| US30_ISO | reserved | −$34.79 (0.582) | −$27.36 (0.713) |

The consensus helps two feeds and hurts two — exactly what a −0.633 transfer correlation predicts,
and the NQ improvement should be read as one draw of four, not as a finding.

## Verdict on the regime filter

**One component earns its place and the rest do not.** Excluding CHOP is right on all four feeds —
the removed trades lose money everywhere, 4 of 4, including on an independent second provider, and
that is more cross-market agreement than anything else in this study. But it is a **loss-avoidance**
result, not an edge: it takes a losing strategy and makes it lose less on three feeds and cross
zero on one (US100 test, n 26). The direction restriction is the weak half — BEAR is the worst
bucket on two of four feeds — and the hysteresis is inert at 0.8% of bars, so ADX exit can be
dropped without measurable effect. The thresholds should not be tuned at all: their transfer
correlation is negative.

**ORB v1 with the regime filter is still not a strategy I would trade.** What the filter has
established is narrower and more useful: *the CHOP exclusion is real, the direction gate is not,
and the ADX hysteresis is decoration.*
